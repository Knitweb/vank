"""stdlib HTTP server for the Scrum Poker UI.

Usage::

    python -m vank.poker_server [--port 8000] [--tolerance 1]
    # or via the installed script:
    vank-poker [--port 8000] [--tolerance 1]

Endpoints
---------
GET  /                          → poker.html
GET  /api/deck                  → {"deck": [...], "version": N}
GET  /api/state?player=X        → session state for viewer X
POST /api/join    {"player":"X"}
POST /api/vote    {"player":"X","card":"8"}
POST /api/reveal
POST /api/revote
POST /api/finalize
POST /api/reset
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from vank.poker import FIBONACCI_DECK, PokerSession

_STATIC_DIR = Path(__file__).parent / "static"

# Module-level session (replaced on /api/reset or --tolerance changes)
_session: PokerSession = PokerSession(name="default", tolerance=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if length > 0:
        raw = handler.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _send_json(handler: BaseHTTPRequestHandler, data: dict, status: int = 200) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(
    handler: BaseHTTPRequestHandler, msg: str, status: int = 400
) -> None:
    _send_json(handler, {"error": msg, "version": _session._version}, status)


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------


class _PokerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:  # suppress default output
        pass

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            html_path = _STATIC_DIR / "poker.html"
            try:
                body = html_path.read_bytes()
            except FileNotFoundError:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/deck":
            _send_json(self, {"deck": list(FIBONACCI_DECK), "version": _session._version})
            return

        if path == "/api/state":
            qs = parse_qs(parsed.query)
            viewer = (qs.get("player") or [""])[0]
            state = _session.state_for(viewer)
            _send_json(self, state)
            return

        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        global _session

        parsed = urlparse(self.path)
        path = parsed.path

        try:
            body = _read_body(self)
        except Exception:
            body = {}

        if path == "/api/join":
            player = body.get("player", "").strip()
            if not player:
                _send_error(self, "player name required")
                return
            _session.join(player)
            _send_json(self, {"ok": True, "version": _session._version})
            return

        if path == "/api/vote":
            player = body.get("player", "").strip()
            card = body.get("card", "")
            if not player or not card:
                _send_error(self, "player and card are required")
                return
            try:
                _session.vote(player, card)
                _send_json(self, {"ok": True, "version": _session._version})
            except ValueError as exc:
                _send_error(self, str(exc))
            return

        if path == "/api/reveal":
            try:
                result = _session.reveal()
                _send_json(
                    self,
                    {"ok": True, "result": result.as_dict(), "version": _session._version},
                )
            except ValueError as exc:
                _send_error(self, str(exc))
            return

        if path == "/api/revote":
            _session.revote()
            _send_json(self, {"ok": True, "version": _session._version})
            return

        if path == "/api/finalize":
            try:
                val = _session.finalize()
                _send_json(self, {"ok": True, "value": val, "version": _session._version})
            except ValueError as exc:
                _send_error(self, str(exc))
            return

        if path == "/api/reset":
            tol = _session.tolerance
            _session = PokerSession(name="default", tolerance=tol)
            _send_json(self, {"ok": True, "version": _session._version})
            return

        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrum Poker HTTP server")
    parser.add_argument("--port", type=int, default=8000, help="TCP port (default 8000)")
    parser.add_argument(
        "--tolerance",
        type=int,
        default=1,
        help="Consensus tolerance in deck-steps (default 1)",
    )
    args = parser.parse_args()

    global _session
    _session = PokerSession(name="default", tolerance=args.tolerance)

    server = HTTPServer(("0.0.0.0", args.port), _PokerHandler)
    print(f"Scrum Poker  →  http://localhost:{args.port}/")
    print(f"Tolerance    :  {args.tolerance} deck-step(s)")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
