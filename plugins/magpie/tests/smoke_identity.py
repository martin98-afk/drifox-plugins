# -*- coding: utf-8 -*-
"""magpie provider 身份/会话能力声明验证（不起网关。

跑法（项目 venv，工作目录 = 仓库根）：
    python tools/smoke_magpie_identity.py
"""
import importlib.util

SPEC = importlib.util.spec_from_file_location("magpie_provider", "plugins/magpie/providers/magpie.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class _Reg:
    def __init__(self):
        self.defs = []

    def register(self, d):
        self.defs.append(d)


reg = _Reg()
mod.register(reg)
assert len(reg.defs) == 1
caps = reg.defs[0].capabilities

# 会话头：magpie 用它切会话，宿主 resolve_extra_headers 填 DriFox 的 session_id
assert caps.get("session_header") == "X-Magpie-Session", caps.get("session_header")

# 归属兜底头：magpie 无 key 时按 User-Agent 首词归属
ua = (caps.get("extra_headers") or {}).get("User-Agent")
assert ua == "DriFox", ua

# 已有能力不能被这两处声明挤掉
assert caps.get("models_hook") is mod._fetch_models
assert caps.get("thinking_param") == "reasoning_effort"
assert caps.get("supports_thinking") is True

print("identity caps ok:", caps["session_header"], "|", ua)
