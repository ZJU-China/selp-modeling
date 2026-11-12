#!/usr/bin/env python3
"""SELP figure service: render task figures from platform data as SVG.

GET /charts/<chart>.svg?task=<task>   -> image/svg+xml
GET /health                            -> json
GET /tasks                             -> json
"""
from __future__ import annotations

import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import charts

ROOT = Path(__file__).resolve().parent
TASKS = json.loads(Path(os.environ.get("SELP_TASKS", ROOT / "tasks.json")).read_text())
PORT = int(os.environ.get("SELP_CHARTS_PORT", "8766"))
HOST = os.environ.get("SELP_CHARTS_HOST", "127.0.0.1")

_cache = {}
_lock = threading.Lock()


def signature(task):
    parts = []
    for value in task.values():
        path = Path(value)
        if path.is_dir():
            files = sorted(path.glob("*.csv"))
            parts.extend((f.name, f.stat().st_mtime_ns) for f in files)
        elif path.exists():
            parts.append((path.name, path.stat().st_mtime_ns))
    return tuple(parts)


def render(name, task_id):
    task = TASKS[task_id]
    sig = (name, task_id, signature(task))
    with _lock:
        hit = _cache.get(sig)
    if hit:
        return hit
    fig = charts.CHARTS[name](task)
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", facecolor="white")
    plt.close(fig)
    data = buf.getvalue()
    with _lock:
        _cache.clear()
        _cache[sig] = data
    return data


class Handler(BaseHTTPRequestHandler):
    server_version = "SELPFigures/1.0"

    def _send(self, status, body, ctype, cache="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        try:
            if path == "/health":
                body = json.dumps({"status": "ok", "charts": sorted(charts.CHARTS),
                                   "tasks": sorted(TASKS)}).encode()
                return self._send(200, body, "application/json")
            if path == "/tasks":
                body = json.dumps({k: sorted(v) for k, v in TASKS.items()}, indent=1).encode()
                return self._send(200, body, "application/json")
            if path.startswith("/charts/") and path.endswith(".svg"):
                name = path[len("/charts/"):-4]
                if name not in charts.CHARTS:
                    return self._send(404, b"unknown chart\n", "text/plain")
                task = parse_qs(url.query).get("task", ["joint"])[0]
                if task not in TASKS:
                    return self._send(404, b"unknown task\n", "text/plain")
                svg = render(name, task)
                return self._send(200, svg, "image/svg+xml; charset=utf-8")
            return self._send(404, b"not found\n", "text/plain")
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            return self._send(500, f"render error: {exc}\n".encode(), "text/plain")

    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    print(f"SELP figures on http://{HOST}:{PORT} charts={sorted(charts.CHARTS)}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
