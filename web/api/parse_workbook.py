"""Vercel serverless function — accept an OpenVal workbook upload, return
the parsed ``Property`` as JSON ready to feed back into ``/api/cashflow``.

The frontend posts the raw .xlsx bytes as the request body with
``Content-Type: application/octet-stream`` (or ``application/...xlsx``).
No multipart form needed — single file per upload.
"""

from __future__ import annotations

import json
import sys
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from openval.io import read_property_workbook  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self._cors_preflight()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            self._send_json(400, {"error": "empty upload"})
            return
        body = self.rfile.read(length)
        # ``read_property_workbook`` expects a Path; write to a temp file and
        # let pandas read from there. tempfile is auto-deleted on close.
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=True) as tmp:
            tmp.write(body)
            tmp.flush()
            try:
                prop = read_property_workbook(tmp.name)
            except Exception as e:  # noqa: BLE001 — surface parse errors
                self._send_json(
                    400,
                    {"error": type(e).__name__, "detail": str(e)},
                )
                return
        self._send_json(200, prop.model_dump(mode="json"))

    def do_GET(self) -> None:
        self._send_json(200, {
            "ok": True,
            "expects": "POST application/octet-stream — body is the .xlsx workbook bytes",
        })

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

    def _cors_preflight(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return
