"""stdlib HTTP server for the Vank mint node GUI and JSON API."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from vank.core import DEFAULT_GRADE_PPM_MAX, DEFAULT_UG_PER_TOKEN, VankState, load_state, save_state

_STATIC_DIR = Path(__file__).parent / "static"


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def _json(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _error(handler: BaseHTTPRequestHandler, message: str, status: int = 400) -> None:
    _json(handler, {"ok": False, "error": message}, status)


class _MintApp:
    def __init__(self, state_path: str | None, demo_authority: bool) -> None:
        self.state_path = state_path
        self.state: VankState = load_state(state_path, demo_authority=demo_authority)
        save_state(self.state, state_path)

    def save(self) -> None:
        save_state(self.state, self.state_path)

    def public_state(self) -> dict:
        node = self.state.node
        return {
            "ok": True,
            "producer_public_key": node.producer_public_key,
            "demo_authority": self.state.authority is not None,
            "has_grant": node.grant is not None,
            "grant": node.grant.to_dict() if node.grant else None,
            "balance": node.balance(),
            "unit_count": len(node.unit_state()),
            "events": [e.to_dict() for e in node.events],
            "audit": node.audit(),
            "defaults": {
                "ug_per_token": DEFAULT_UG_PER_TOKEN,
                "grade_ppm_max": DEFAULT_GRADE_PPM_MAX,
            },
        }


_app: _MintApp | None = None


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        assert _app is not None
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._static("index.html", "text/html; charset=utf-8")
        if path == "/style.css":
            return self._static("style.css", "text/css; charset=utf-8")
        if path == "/app.js":
            return self._static("app.js", "application/javascript; charset=utf-8")
        if path == "/api/state":
            return _json(self, _app.public_state())
        if path == "/api/export":
            return _json(self, _app.state.node.export_report())
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        assert _app is not None
        path = urlparse(self.path).path
        try:
            body = _read_body(self)
            if path == "/api/register":
                if _app.state.authority is None:
                    return _error(self, "no local demo authority available")
                materials = body.get("materials") or []
                if isinstance(materials, str):
                    materials = [m.strip() for m in materials.split(",")]
                grant = _app.state.node.register(
                    _app.state.authority,
                    kvk_number=body.get("kvk_number", ""),
                    xrf_lab_accreditation=body.get("xrf_lab_accreditation", ""),
                    sample_custody_ref=body.get("sample_custody_ref", ""),
                    materials=materials,
                    ug_per_token=int(body.get("ug_per_token") or DEFAULT_UG_PER_TOKEN),
                    grade_ppm_max=int(body.get("grade_ppm_max") or DEFAULT_GRADE_PPM_MAX),
                )
                _app.save()
                return _json(self, {"ok": True, "grant": grant.to_dict(), "state": _app.public_state()})
            if path == "/api/measure":
                event = _app.state.node.measure(
                    material=body.get("material", ""),
                    batch_id=body.get("batch_id", ""),
                    mass_kg=str(body.get("mass_kg", "")),
                    grade_ppm=int(body.get("grade_ppm")),
                    assay_id=body.get("assay_id", ""),
                )
                _app.save()
                return _json(self, {"ok": True, "event": event.to_dict(), "state": _app.public_state()})
            if path == "/api/revalue":
                event = _app.state.node.revalue(
                    material=body.get("material", ""),
                    batch_id=body.get("batch_id", ""),
                    mass_kg=str(body.get("mass_kg", "")),
                    grade_ppm=int(body.get("grade_ppm")),
                    assay_id=body.get("assay_id", ""),
                )
                _app.save()
                return _json(self, {"ok": True, "event": event.to_dict(), "state": _app.public_state()})
        except Exception as exc:
            return _error(self, str(exc))
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _static(self, name: str, content_type: str) -> None:
        path = _STATIC_DIR / name
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8799,
    state_path: str | None = None,
    demo_authority: bool = True,
) -> None:
    global _app
    _app = _MintApp(state_path, demo_authority)
    server = HTTPServer((host, port), _Handler)
    print(f"Vank Mint Node  →  http://{host}:{port}/")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
