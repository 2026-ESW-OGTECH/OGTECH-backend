from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import os


@dataclass
class LedState:
    active_drawers: list[str]
    mode: str
    color: str


class LedController:
    """모의 구현을 우선 사용하는 LED 컨트롤러.

    Raspberry Pi에서는 LED 개수와 GPIO 핀이 확정된 뒤 모의 분기를
    WS2812B 드라이버로 교체하세요. 안전을 위해 API는 의도적으로 작게 유지합니다.
    """

    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.state = LedState(active_drawers=[], mode="idle", color="#64748b")
        self.mode = os.getenv("SAFEAID_LED_MODE", "mock")

    def show_drawers(self, drawer_ids: list[str], color: str = "#dc2626") -> dict[str, Any]:
        self.state = LedState(active_drawers=drawer_ids, mode="drawers", color=color)
        return self._persist()

    def show_emergency(self) -> dict[str, Any]:
        self.state = LedState(active_drawers=[], mode="emergency", color="#ef4444")
        return self._persist()

    def clear(self) -> dict[str, Any]:
        self.state = LedState(active_drawers=[], mode="idle", color="#64748b")
        return self._persist()

    def payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "state": {
                "active_drawers": self.state.active_drawers,
                "display_mode": self.state.mode,
                "color": self.state.color,
            },
        }

    def _persist(self) -> dict[str, Any]:
        payload = self.payload()
        (self.runtime_dir / "led_state.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload


@dataclass
class KitState:
    open_layer: int | None = None
    active_cell: str | None = None
    stock_sensors: dict[str, bool] = field(default_factory=dict)
    battery: dict[str, Any] = field(
        default_factory=lambda: {
            "voltage": 7.4,
            "percent": 74,
            "charging": True,
            "low": False,
        }
    )


class KitController:
    """3단 자동 인출형 키트 컨트롤러.

    기본값은 모의 모드입니다. 실제 STM32 연결 시 `SAFEAID_KIT_MODE=stm32`와
    `SAFEAID_STM32_PORT`를 설정하면 같은 API로 Serial 명령을 보냅니다.
    """

    LOW_BATTERY_PERCENT = 10
    LOW_BATTERY_VOLTAGE = 6.4

    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.mode = os.getenv("SAFEAID_KIT_MODE", "mock")
        self.port = os.getenv("SAFEAID_STM32_PORT", "")
        self.state = KitState()
        self._persist()

    def open_layer(self, layer: int, cell: str | None = None) -> dict[str, Any]:
        if self.state.battery["low"]:
            return {"opened": False, "reason": "low_battery", "state": self._state_payload()}
        if layer not in {1, 2, 3}:
            return {"opened": False, "reason": "invalid_layer", "state": self._state_payload()}

        self._send_serial(f"OPEN_LAYER {layer}")
        self.state.open_layer = layer
        if cell:
            self.set_cell_led(cell)
        return {"opened": True, "reason": None, "state": self._persist()}

    def close_layers(self) -> dict[str, Any]:
        self._send_serial("CLOSE_ALL")
        self.state.open_layer = None
        self.state.active_cell = None
        return {"closed": True, "state": self._persist()}

    def set_cell_led(self, cell: str) -> dict[str, Any]:
        self._send_serial(f"SET_CELL_LED {cell}")
        self.state.active_cell = cell
        return {"state": self._persist()}

    def update_stock_sensor(self, sensor_id: str, present: bool) -> dict[str, Any]:
        self.state.stock_sensors[sensor_id] = bool(present)
        return {"state": self._persist()}

    def update_battery(self, voltage: float, percent: int, charging: bool) -> dict[str, Any]:
        percent = max(0, min(100, int(percent)))
        low = not charging and (percent <= self.LOW_BATTERY_PERCENT or voltage <= self.LOW_BATTERY_VOLTAGE)
        self.state.battery = {
            "voltage": float(voltage),
            "percent": percent,
            "charging": bool(charging),
            "low": low,
        }
        return {"state": self._persist()}

    def payload(self) -> dict[str, Any]:
        return {"mode": self.mode, "state": self._state_payload()}

    def _state_payload(self) -> dict[str, Any]:
        return {
            "open_layer": self.state.open_layer,
            "active_cell": self.state.active_cell,
            "stock_sensors": dict(self.state.stock_sensors),
            "battery": dict(self.state.battery),
        }

    def _persist(self) -> dict[str, Any]:
        payload = self._state_payload()
        (self.runtime_dir / "kit_state.json").write_text(
            json.dumps({"mode": self.mode, "state": payload}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload

    def _send_serial(self, command: str) -> None:
        if self.mode != "stm32" or not self.port:
            return
        try:
            import serial  # type: ignore

            with serial.Serial(self.port, 115200, timeout=0.8) as connection:
                connection.write((command + "\n").encode("ascii"))
                connection.flush()
        except Exception:
            return
