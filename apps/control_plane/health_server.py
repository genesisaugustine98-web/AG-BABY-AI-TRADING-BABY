"""Minimal Render health/control-plane surface.

This process has no broker credentials and does not place orders.
It exists only to expose an operational health endpoint for the repository
control plane. Heavy research and trading execution remain outside this
public service.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    server_version = "AG-BABY-Control-Plane/1.0"

    def _write(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._write(
                200,
                {
                    "status": "ok",
                    "service": "ag-baby-control-plane",
                    "environment": os.getenv("EXECUTION_ENV", "research"),
                    "live_trading": False,
                },
            )
            return

        if self.path == "/":
            self._write(
                200,
                {
                    "service": "ag-baby-control-plane",
                    "health": "/health",
                    "live_trading": False,
                },
            )
            return

        self._write(404, {"status": "not_found"})

    def log_message(self, format: str, *args: object) -> None:
        # Keep Render logs compact and secret-safe.
        print("control-plane", format % args)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"AG BABY control-plane health server listening on :{port}")
    server.serve_forever()
