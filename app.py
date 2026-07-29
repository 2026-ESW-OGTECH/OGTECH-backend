from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
import base64
import json
import mimetypes
import os
import urllib.request

from hardware import KitController, LedController
from inventory import InventoryStore
from safeaid_core import DISCLAIMER, DRAWERS, SCENARIOS, SafeAidEngine, encode_json
from vision import analyze_image_bytes, result_payload


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
RUNTIME_DIR = ROOT / "runtime"

engine = SafeAidEngine()
leds = LedController(RUNTIME_DIR)
kit = KitController(RUNTIME_DIR)
inventory = InventoryStore(RUNTIME_DIR)


class SafeAidHandler(BaseHTTPRequestHandler):
    server_version = "SafeAidKit/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            return self.serve_file(STATIC_DIR / "index.html")
        if path.startswith("/static/"):
            relative = unquote(path.removeprefix("/static/"))
            return self.serve_file(STATIC_DIR / relative)
        if path == "/api/state":
            return self.send_json(
                {
                    "disclaimer": DISCLAIMER,
                    "scenarios": engine.list_scenarios(),
                    "drawers": [{"id": key, **value} for key, value in DRAWERS.items()],
                    "led": leds.payload(),
                    "kit": kit.payload(),
                    "inventory": inventory.list_items(),
                    "events": engine.events[:12],
                }
            )
        if path == "/api/inventory":
            return self.send_json({"inventory": inventory.list_items(), "kit": kit.payload()})
        if path == "/api/logs":
            return self.send_json({"events": engine.events})
        if path == "/api/emergency":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [None])[0]
            leds.show_emergency()
            return self.send_json({"emergency": engine.emergency_summary(session_id), "led": leds.payload()})
        if path == "/api/latest-image":
            latest = RUNTIME_DIR / "latest_upload.jpg"
            if latest.exists():
                return self.serve_file(latest)
            return self.send_error_json(HTTPStatus.NOT_FOUND, "업로드된 이미지가 없습니다")

        return self.send_error_json(HTTPStatus.NOT_FOUND, "찾을 수 없습니다")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/classify":
            payload = self.read_json()
            text = str(payload.get("text", "")).strip()
            if not text:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, "텍스트가 필요합니다")
            result = classify_with_optional_ollama(text)
            return self.send_json(result)

        if path == "/api/inventory/query":
            payload = self.read_json()
            text = str(payload.get("text", "")).strip()
            if not text:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, "검색할 물품명이 필요합니다.")
            result = inventory.query(text)
            engine.log("inventory_query", {"text": text, "result": result})
            return self.send_json({"result": result, "inventory": inventory.list_items(), "kit": kit.payload()})

        if path == "/api/inventory/open":
            payload = self.read_json()
            item_id = str(payload.get("item_id", "")).strip()
            item = inventory.get_item(item_id)
            if not item:
                return self.send_error_json(HTTPStatus.NOT_FOUND, "등록된 물품을 찾을 수 없습니다.")
            if not item["available"]:
                return self.send_error_json(HTTPStatus.CONFLICT, "현재 재고가 없습니다.")
            if not item["auto_open_allowed"]:
                return self.send_error_json(HTTPStatus.FORBIDDEN, "자동 개방이 허용되지 않은 물품입니다.")
            result = kit.open_layer(int(item["layer"]), str(item["cell"]))
            status = HTTPStatus.OK if result["opened"] else HTTPStatus.CONFLICT
            engine.log("inventory_open", {"item_id": item_id, "kit": result})
            return self.send_json({"item": item, "kit": result, "inventory": inventory.list_items()}, status=status)

        if path == "/api/inventory/items":
            payload = self.read_json()
            try:
                item = inventory.add_item(payload)
            except ValueError as exc:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            engine.log("inventory_add", {"item": item})
            return self.send_json({"item": item, "inventory": inventory.list_items(), "kit": kit.payload()})

        if path == "/api/inventory/stock":
            payload = self.read_json()
            sensor_id = str(payload.get("sensor_id", "")).strip()
            present = bool(payload.get("present", False))
            if not sensor_id:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, "sensor_id가 필요합니다.")
            kit_result = kit.update_stock_sensor(sensor_id, present)
            inventory_result = inventory.update_stock_from_sensor(sensor_id, present)
            engine.log("inventory_stock", {"sensor_id": sensor_id, "present": present, "updated": inventory_result["updated"]})
            return self.send_json({"stock": inventory_result, "kit": kit_result, "inventory": inventory.list_items()})

        if path == "/api/kit/battery":
            payload = self.read_json()
            result = kit.update_battery(
                voltage=float(payload.get("voltage", 13.2)),
                percent=int(payload.get("percent", 0)),
                charging=bool(payload.get("charging", False)),
            )
            engine.log("kit_battery", result)
            return self.send_json({"kit": kit.payload()})

        if path == "/api/start":
            payload = self.read_json()
            scenario_id = str(payload.get("scenario_id", ""))
            source = str(payload.get("source", "touch"))
            risk_flags = payload.get("risk_flags") or []
            try:
                session = engine.start_session(scenario_id, source=source, risk_flags=list(risk_flags))
            except ValueError as exc:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            apply_leds_for_session(session)
            return self.send_json({"session": session, "led": leds.payload()})

        if path == "/api/cpr/start":
            session = engine.start_session("cpr", source="life_threat", risk_flags=["unconscious", "abnormal_breathing"])
            leds.show_emergency()
            return self.send_json({"session": session, "led": leds.payload()})

        if path.startswith("/api/session/") and path.endswith("/action"):
            parts = path.strip("/").split("/")
            session_id = parts[2] if len(parts) >= 4 else ""
            payload = self.read_json()
            action = str(payload.get("action", "done"))
            try:
                session = engine.advance_session(session_id, action)
            except ValueError as exc:
                return self.send_error_json(HTTPStatus.NOT_FOUND, str(exc))
            apply_leds_for_session(session)
            return self.send_json({"session": session, "led": leds.payload()})

        if path == "/api/vision/upload":
            image_bytes = self.read_image_payload()
            if not image_bytes:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, "이미지 데이터가 필요합니다")
            RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            (RUNTIME_DIR / "latest_upload.jpg").write_bytes(image_bytes)
            analysis = result_payload(analyze_image_bytes(image_bytes))
            suggestion = suggested_scenario_from_vision(analysis["flags"])
            engine.log("vision_upload", {"analysis": analysis, "suggested_scenario_id": suggestion})
            return self.send_json(
                {
                    "analysis": analysis,
                    "suggested_scenario_id": suggestion,
                    "suggested_title": SCENARIOS[suggestion]["title"] if suggestion else None,
                    "image_url": "/api/latest-image",
                }
            )

        if path == "/api/sensor/co":
            payload = self.read_json()
            ppm = float(payload.get("ppm", 0))
            danger = ppm >= float(os.getenv("SAFEAID_CO_DANGER_PPM", "50"))
            event_payload = {"ppm": ppm, "danger": danger}
            if danger:
                session = engine.start_session("co", source="co_sensor", risk_flags=["co_exposure"])
                leds.show_emergency()
                event_payload["session_id"] = session["id"]
                engine.log("co_sensor_danger", event_payload)
                return self.send_json({"danger": True, "session": session, "led": leds.payload()})
            engine.log("co_sensor_ok", event_payload)
            return self.send_json({"danger": False, "ppm": ppm, "led": leds.payload()})

        return self.send_error_json(HTTPStatus.NOT_FOUND, "찾을 수 없습니다")

    def serve_file(self, file_path: Path) -> None:
        try:
            resolved = file_path.resolve()
            if not str(resolved).startswith(str(ROOT.resolve())):
                return self.send_error_json(HTTPStatus.FORBIDDEN, "접근할 수 없습니다")
            if not resolved.exists() or not resolved.is_file():
                return self.send_error_json(HTTPStatus.NOT_FOUND, "찾을 수 없습니다")
            content = resolved.read_bytes()
            mime = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
            if resolved.suffix == ".html":
                mime = "text/html; charset=utf-8"
            elif resolved.suffix == ".css":
                mime = "text/css; charset=utf-8"
            elif resolved.suffix == ".js":
                mime = "application/javascript; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except OSError as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def read_image_payload(self) -> bytes:
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        if "application/json" in content_type:
            try:
                payload = json.loads(raw.decode("utf-8"))
                if "image_b64" in payload:
                    return base64.b64decode(payload["image_b64"])
            except Exception:
                return b""
        return raw

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = encode_json(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def log_message(self, format: str, *args) -> None:
        print(f"[SafeAid] {self.address_string()} - {format % args}")


def classify_with_optional_ollama(text: str) -> dict:
    fallback = engine.classify_text(text)
    if os.getenv("SAFEAID_USE_OLLAMA", "0") != "1":
        fallback["classifier"] = "keyword_fallback"
        return fallback

    model = os.getenv("SAFEAID_OLLAMA_MODEL", "qwen2.5:1.5b")
    prompt = {
        "instruction": "응급처치 방법을 생성하지 말고 사용자 발화를 아래 scenario_id 중 하나로만 분류해 JSON만 반환하세요.",
        "scenario_ids": list(SCENARIOS.keys()),
        "text": text,
        "schema": {"scenario_id": "string", "confidence": "low|medium|high", "risk_flags": ["string"]},
    }
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=json.dumps(
                {
                    "model": model,
                    "prompt": json.dumps(prompt, ensure_ascii=False),
                    "stream": False,
                    "format": "json",
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            ollama_payload = json.loads(response.read().decode("utf-8"))
        parsed = json.loads(ollama_payload.get("response", "{}"))
        scenario_id = parsed.get("scenario_id")
        if scenario_id in SCENARIOS:
            parsed["scenario_title"] = SCENARIOS[scenario_id]["title"]
            parsed["risk_flags"] = sorted(set(parsed.get("risk_flags", [])) | set(fallback["risk_flags"]))
            parsed["raw_text"] = text
            parsed["classifier"] = f"ollama:{model}"
            engine.log("classify_ollama", parsed)
            return parsed
    except Exception as exc:
        fallback["ollama_error"] = str(exc)

    fallback["classifier"] = "keyword_fallback"
    return fallback


def suggested_scenario_from_vision(flags: list[str]) -> str | None:
    if "bleeding_possible" in flags:
        return "bleeding"
    if "burn_possible" in flags:
        return "burn"
    return None


def apply_leds_for_session(session: dict) -> None:
    if session.get("force_emergency"):
        leds.show_emergency()
        return
    drawer_ids = [drawer["id"] for drawer in session.get("drawers", [])]
    if drawer_ids:
        color = session["drawers"][0].get("color", "#dc2626")
        leds.show_drawers(drawer_ids, color=color)
    else:
        leds.clear()


def run() -> None:
    host = os.getenv("SAFEAID_HOST", "0.0.0.0")
    port = int(os.getenv("SAFEAID_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), SafeAidHandler)
    print(f"오프라인 SafeAid Kit 실행 중: http://{host}:{port}")
    print("중지하려면 Ctrl+C를 누르세요.")
    server.serve_forever()


if __name__ == "__main__":
    run()
