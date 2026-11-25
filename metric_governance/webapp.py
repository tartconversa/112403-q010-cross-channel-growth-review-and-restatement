"""只读 Web 查询界面（http.server 标准库实现）。

路由：
- /                      HTML 总览仪表盘
- /metric/<name>         单项指标档案 HTML
- /api/overview          总览 JSON
- /api/metric/<name>     指标档案 JSON
- /api/pending           当前待处理 JSON
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from .dossier import build_dossier, pending_items
from .overview import build_overview
from .registry import Registry
from .render_html import render_dashboard, render_metric_page


def make_handler(reg: Registry):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # 安静日志
            return

        def _send(self, body: bytes, ctype: str = "text/html; charset=utf-8",
                  status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload, status: int = 200) -> None:
            self._send(json.dumps(payload, ensure_ascii=False, indent=2,
                                  default=str).encode("utf-8"),
                       "application/json; charset=utf-8", status)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            try:
                if path in {"/", "/index.html"}:
                    ov = build_overview(reg)
                    self._send(render_dashboard(ov).encode("utf-8"))
                elif path == "/api/overview":
                    self._json(build_overview(reg).to_dict())
                elif path == "/api/pending":
                    self._json([p.to_dict() for p in pending_items(reg)])
                elif path.startswith("/api/metric/"):
                    name = unquote(path.rsplit("/", 1)[-1])
                    self._json(build_dossier(reg, name).to_dict())
                elif path.startswith("/metric/"):
                    name = unquote(path.rsplit("/", 1)[-1]).replace(".html", "")
                    self._send(render_metric_page(
                        build_dossier(reg, name)).encode("utf-8"))
                elif path == "/healthz":
                    self._json({"ok": True})
                else:
                    self._json({"error": "not found", "path": path}, 404)
            except Exception as exc:  # noqa: BLE001
                self._json({"error": type(exc).__name__, "message": str(exc)}, 500)

    return Handler


def serve(reg: Registry, host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(reg))
    print(f"指标治理查询界面: http://{host}:{port}/  (Ctrl+C 停止)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
