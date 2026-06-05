"""Vercel Python serverless function — POST a Property JSON, get the
Argus cashflow block back as JSON.

Local invocation lives in ``web/api/_lib.py::build_cashflow_report``; this
file is just the HTTP wrapper.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

# When this file is loaded by Vercel the runtime serves it as a serverless
# function; ``_lib`` is a sibling module in the same directory. The bare
# import works because Vercel adds the function's directory to sys.path.
try:
    from ._lib import build_cashflow_report  # type: ignore[import-not-found]
except ImportError:
    from _lib import build_cashflow_report  # type: ignore[no-redef]


class handler(BaseHTTPRequestHandler):
    """Vercel discovers this class by name and dispatches HTTP methods to
    the matching ``do_*`` handlers.
    """

    def do_OPTIONS(self) -> None:
        self._send_cors_preflight()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": f"invalid JSON: {e}"})
            return
        frequency = self._parse_frequency()
        try:
            report = build_cashflow_report(payload, frequency=frequency)
        except Exception as e:  # noqa: BLE001 — surface engine/validation errors verbatim
            self._send_json(400, {"error": type(e).__name__, "detail": str(e)})
            return
        self._send_json(200, report)

    def _parse_frequency(self) -> str:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        val = (qs.get("frequency") or qs.get("freq") or ["annual"])[0]
        return "monthly" if val == "monthly" else "annual"

    def do_GET(self) -> None:
        # Health check + a hint at the expected POST shape.
        self._send_json(200, {
            "ok": True,
            "expects": "POST application/json with a Property model body; "
                       "see openval.Property for the schema.",
        })

    # --- helpers ---------------------------------------------------

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def _send_cors_preflight(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002 — stdlib signature
        # Silence the default access-log spam on Vercel; their platform
        # captures requests separately.
        return
