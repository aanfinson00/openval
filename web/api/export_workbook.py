"""Vercel serverless function — POST a Property JSON, get back the
.xlsx workbook as a binary download.

Round-trip companion to ``parse_workbook.py``: same file can be uploaded
into the web app or opened in Excel + run through
``scripts/run_workbook.py`` to bake outputs.
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

from openval import Property  # noqa: E402
from openval.io import write_property_workbook  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self._cors_preflight()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": f"invalid JSON: {e}"})
            return
        try:
            prop = Property.model_validate(payload)
        except Exception as e:  # noqa: BLE001
            self._send_json(400, {"error": type(e).__name__, "detail": str(e)})
            return

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=True) as tmp:
            tmp.close()  # write_property_workbook reopens via openpyxl
            try:
                write_property_workbook(prop, tmp.name)
            except Exception as e:  # noqa: BLE001
                self._send_json(500, {"error": type(e).__name__, "detail": str(e)})
                return
            data = Path(tmp.name).read_bytes()
            Path(tmp.name).unlink(missing_ok=True)

        filename = self._safe_filename(prop.name)
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Content-Disposition", f'attachment; filename="{filename}.xlsx"'
        )
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self._send_json(200, {
            "ok": True,
            "expects": "POST application/json with a Property model body; "
                       "response is the .xlsx workbook binary.",
        })

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _cors_preflight(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    @staticmethod
    def _safe_filename(name: str) -> str:
        clean = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
        return (clean.strip() or "openval-workbook").replace(" ", "_")

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return
