# -*- coding: utf-8 -*-
"""magpie provider 冒烟测试（假网关，不依赖真实 magpie）。

跑法（项目 venv）：
    python tools/smoke_magpie_provider.py
"""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

SPEC = importlib.util.spec_from_file_location("magpie_provider", "plugins/magpie/providers/magpie.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

# 纯函数
assert mod._gateway_base("http://127.0.0.1:3425/v1/") == "http://127.0.0.1:3425"
assert mod._gateway_base("http://127.0.0.1:3425/") == "http://127.0.0.1:3425"
assert mod._gateway_base("http://127.0.0.1:9000/V1") == "http://127.0.0.1:9000"
assert mod._auth_headers({})["Authorization"] == "Bearer magpie-drifox"
assert mod._auth_headers({"API_KEY": "magpie-acme"})["Authorization"] == "Bearer magpie-acme"
print("pure ok")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/api/hello":
            self._send({"name": "magpie", "version": "1.2.3"})
        elif self.path == "/v1/models":
            self._send(
                {
                    "data": [
                        {"id": "deepseek/deepseek-v4-pro"},
                        {"id": "group/opus-anywhere"},
                        {"id": ""},
                    ]
                }
            )
        else:
            self.send_response(404)
            self.end_headers()

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = HTTPServer(("127.0.0.1", 0), Handler)
port = srv.server_port
threading.Thread(target=srv.serve_forever, daemon=True).start()

models = mod._fetch_models({"API_URL": f"http://127.0.0.1:{port}/v1"})
assert models == ["deepseek/deepseek-v4-pro", "group/opus-anywhere"], models
print("models ok:", models)
srv.shutdown()

# 端口关闭 → 可读错误
try:
    mod._fetch_models({"API_URL": f"http://127.0.0.1:{port}/v1"})
    raise AssertionError("端口关闭时应抛 RuntimeError")
except RuntimeError as e:
    print("closed-port err ok:", str(e)[:60])


# 对端不是 magpie → 明确拒绝
class NotMagpie(Handler):
    def do_GET(self):
        self._send({"name": "ollama"})


srv2 = HTTPServer(("127.0.0.1", 0), NotMagpie)
p2 = srv2.server_port
threading.Thread(target=srv2.serve_forever, daemon=True).start()
try:
    mod._fetch_models({"API_URL": f"http://127.0.0.1:{p2}/v1"})
    raise AssertionError("非 magpie 对端时应抛 RuntimeError")
except RuntimeError as e:
    print("not-magpie err ok:", str(e)[:70])
srv2.shutdown()

print("ALL OK")
