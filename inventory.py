from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
import json
import re
import uuid


DEFAULT_INVENTORY = [
    {
        "id": "bulk_bandage",
        "name": "붕대/파스 묶음",
        "aliases": ["붕대", "파스", "대형 패드", "압박 붕대"],
        "layer": 1,
        "cell": "1-1",
        "quantity": 1,
        "expiry_date": "2026-12-31",
        "is_medicine": False,
        "auto_open_allowed": True,
        "sensor_id": "stock_1_1",
    },
    {
        "id": "fucidin",
        "name": "후시딘",
        "aliases": ["후시딘", "상처 연고", "연고"],
        "layer": 2,
        "cell": "2-1",
        "quantity": 1,
        "expiry_date": "2026-09-30",
        "is_medicine": True,
        "auto_open_allowed": True,
        "sensor_id": "stock_2_1",
    },
    {
        "id": "disinfectant",
        "name": "소독제",
        "aliases": ["소독제", "알코올 솜", "소독솜"],
        "layer": 2,
        "cell": "2-2",
        "quantity": 4,
        "expiry_date": "2026-10-31",
        "is_medicine": False,
        "auto_open_allowed": True,
        "sensor_id": "stock_2_2",
    },
    {
        "id": "band_aid",
        "name": "밴드",
        "aliases": ["밴드", "반창고", "일회용 밴드"],
        "layer": 3,
        "cell": "3-1",
        "quantity": 12,
        "expiry_date": "2027-01-31",
        "is_medicine": False,
        "auto_open_allowed": True,
        "sensor_id": "stock_3_1",
    },
    {
        "id": "personal_pills",
        "name": "개인 상비약 통",
        "aliases": ["개인약", "상비약", "알약통"],
        "layer": 3,
        "cell": "3-2",
        "quantity": 1,
        "expiry_date": "2026-08-31",
        "is_medicine": True,
        "auto_open_allowed": True,
        "sensor_id": "stock_3_2",
    },
    {
        "id": "ppe",
        "name": "장갑/마스크",
        "aliases": ["장갑", "마스크", "보호 장비"],
        "layer": 3,
        "cell": "3-3",
        "quantity": 2,
        "expiry_date": "2028-12-31",
        "is_medicine": False,
        "auto_open_allowed": True,
        "sensor_id": "stock_3_3",
    },
]


@dataclass
class InventoryItem:
    id: str
    name: str
    aliases: list[str]
    layer: int
    cell: str
    quantity: int
    expiry_date: str
    is_medicine: bool = False
    auto_open_allowed: bool = True
    sensor_id: str = ""
    present: bool = True

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "InventoryItem":
        aliases = payload.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [alias.strip() for alias in aliases.split(",") if alias.strip()]
        name = str(payload.get("name", "")).strip()
        item_id = str(payload.get("id") or make_item_id(name))
        return cls(
            id=item_id,
            name=name,
            aliases=[str(alias).strip() for alias in aliases if str(alias).strip()],
            layer=int(payload.get("layer", 1)),
            cell=str(payload.get("cell", "1-1")),
            quantity=max(0, int(payload.get("quantity", 0))),
            expiry_date=str(payload.get("expiry_date", "")),
            is_medicine=bool(payload.get("is_medicine", False)),
            auto_open_allowed=bool(payload.get("auto_open_allowed", True)),
            sensor_id=str(payload.get("sensor_id", "")),
            present=bool(payload.get("present", True)),
        )

    def available(self) -> bool:
        return self.present and self.quantity > 0


class InventoryStore:
    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.runtime_dir / "inventory.json"
        self.items = self._load_items()

    def list_items(self) -> list[dict[str, Any]]:
        return [self._item_payload(item) for item in self.items]

    def query(self, text: str) -> dict[str, Any]:
        item = self.find_item(text)
        if not item:
            return {
                "found": False,
                "openable": False,
                "item": None,
                "message": "등록된 물품 중에는 없습니다.",
            }
        if not item.available():
            return {
                "found": False,
                "openable": False,
                "item": self._item_payload(item),
                "message": f"{item.name}은 등록되어 있지만 현재 재고가 없습니다.",
            }

        location = f"{item.layer}단 {item.cell}칸"
        prompt = " 열어 드릴까요?" if item.auto_open_allowed else ""
        message = f"네, 있습니다. 위치는 {location}입니다.{prompt}"
        if item.is_medicine:
            message += " 등록된 위치 정보만 안내합니다."
        return {
            "found": True,
            "openable": item.auto_open_allowed,
            "item": self._item_payload(item),
            "message": message,
        }

    def find_item(self, text: str) -> InventoryItem | None:
        query = normalize(text)
        best: tuple[int, InventoryItem] | None = None
        for item in self.items:
            terms = [item.name, *item.aliases]
            score = 0
            for term in terms:
                needle = normalize(term)
                if not needle:
                    continue
                if needle in query:
                    score = max(score, len(needle))
                elif query and query in needle:
                    score = max(score, len(query))
            if score and (best is None or score > best[0]):
                best = (score, item)
        return best[1] if best else None

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        for item in self.items:
            if item.id == item_id:
                return self._item_payload(item)
        return None

    def add_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = InventoryItem.from_payload(payload)
        if not item.name:
            raise ValueError("물품명이 필요합니다.")
        if item.layer not in {1, 2, 3}:
            raise ValueError("층은 1, 2, 3 중 하나여야 합니다.")
        if not re.fullmatch(r"[1-3]-[1-3]", item.cell):
            raise ValueError("칸은 1-1, 2-1, 3-2 같은 형식이어야 합니다.")
        if not item.aliases:
            item.aliases = [item.name]
        if not item.sensor_id:
            item.sensor_id = f"stock_{item.cell.replace('-', '_')}"

        self.items = [existing for existing in self.items if existing.id != item.id]
        self.items.append(item)
        self._persist()
        return self._item_payload(item)

    def update_stock_from_sensor(self, sensor_id: str, present: bool) -> dict[str, Any]:
        for item in self.items:
            if item.sensor_id == sensor_id:
                item.present = bool(present)
                self._persist()
                return {"updated": True, "item": self._item_payload(item)}
        return {"updated": False, "item": None}

    def set_quantity(self, item_id: str, quantity: int) -> dict[str, Any]:
        for item in self.items:
            if item.id == item_id:
                item.quantity = max(0, int(quantity))
                self._persist()
                return {"updated": True, "item": self._item_payload(item)}
        return {"updated": False, "item": None}

    def _load_items(self) -> list[InventoryItem]:
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                return [InventoryItem.from_payload(item) for item in payload.get("items", [])]
            except (json.JSONDecodeError, OSError, ValueError):
                pass
        items = [InventoryItem.from_payload(item) for item in DEFAULT_INVENTORY]
        self._write_items(items)
        return items

    def _persist(self) -> None:
        self._write_items(self.items)

    def _write_items(self, items: list[InventoryItem]) -> None:
        self.path.write_text(
            json.dumps({"items": [asdict(item) for item in items]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _item_payload(self, item: InventoryItem) -> dict[str, Any]:
        payload = asdict(item)
        payload["available"] = item.available()
        payload["expired"] = is_expired(item.expiry_date)
        return payload


def make_item_id(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9가-힣]+", "_", name.strip()).strip("_").lower()
    return base or f"item_{uuid.uuid4().hex[:8]}"


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def is_expired(value: str) -> bool:
    try:
        return date.fromisoformat(value) < date.today()
    except ValueError:
        return False
