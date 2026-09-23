"""Local-only runtime health and Prometheus endpoint.

The server binds to loopback by default and is intentionally separate from the authenticated
operator cockpit. It exposes no broker credentials or secrets.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Callable, Mapping


class MetricsHTTPServer:
    def __init__(self, *, host: str = "127.0.0.1", port: int = 9300, snapshot_provider: Callable[[], Mapping[str, object]]) -> None:
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("metrics server is loopback-only")
        if port < 1024 or port > 65535:
            raise ValueError("metrics port must be between 1024 and 65535")
        self.host = host
        self.port = port
        self.snapshot_provider = snapshot_provider
        provider = snapshot_provider

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                payload = dict(provider())
                if self.path == "/healthz":
                    body = json.dumps(payload, separators=(",", ":")).encode()
                    self.send_response(200 if payload.get("healthy") else 503)
                    self.send_header("Content-Type", "application/json")
                elif self.path == "/readyz":
                    body = json.dumps(payload, separators=(",", ":")).encode()
                    self.send_response(200 if payload.get("ready") else 503)
                    self.send_header("Content-Type", "application/json")
                elif self.path == "/metrics":
                    body = _prometheus(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                else:
                    self.send_response(404)
                    body = b"not found\n"
                    self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = Thread(target=self._server.serve_forever, name="ag-metrics", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)


def _prometheus(payload: Mapping[str, object]) -> str:
    lines = []
    for key, value in sorted(payload.items()):
        metric = "ag_runtime_" + "".join(ch if ch.isalnum() else "_" for ch in key).lower()
        if isinstance(value, bool):
            numeric = 1 if value else 0
            lines.append(f"{metric} {numeric}")
        elif isinstance(value, (int, float)):
            lines.append(f"{metric} {value}")
    return "\n".join(lines) + "\n"


__all__ = ["MetricsHTTPServer"]
