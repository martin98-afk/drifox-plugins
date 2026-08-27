# -*- coding: utf-8 -*-
"""gateway-feishu 命令卡片解析器验证（不依赖 lark SDK，独立跑解析逻辑）"""
import ast
import json
import re
import sys
import types
from typing import List, Optional

sys.path.insert(0, "plugins/gateway-feishu/gateways")

# ── 宿主真实文案样本（engine.py 生成格式）──────────────────────────

HELP_TEXT = """🤖 **DriFox Gateway 命令**

**会话管理**
- `/new` 或 `/reset` — 重置当前会话，开始新的对话
- `/clear` — 清空当前会话的聊天记录
- `/session` — 列出所有历史会话
- `/session <id>` — 切换到指定会话

**模型 & Agent**
- `/model` — 查看所有服务商及当前模型
- `/model 服务商名` — 查看该服务商的可用模型
- `/model 服务商名 模型名` — 切换服务商和模型
- `/agent` — 查看当前使用的 Agent
- `/agent <名称>` — 切换到指定 Agent

**通用**
- `/help` — 显示此帮助

--------
💡 Gateway 会话与桌面端完全隔离，互不影响。
   历史会话可在桌面端 UI 列表中查看。"""

MODEL_TEXT = """📋 **可用模型**:

**DeepSeek** ◀ 当前服务商
  模型: `deepseek-chat`
  可选: `deepseek-chat`, `deepseek-reasoner`, `deepseek-v3`

**OpenRouter**
  模型: `qwen/qwen3-235b`
  可选: `qwen/qwen3-235b`, `meta-llama/llama-4-maverick`

**本地 Ollama** ⚡ 会话覆盖 — `qwen3:8b`"""

SESSION_TEXT = """📋 **Gateway 会话** (3 个):

- `a1b2c3d4e5f6`... **[飞书] 马丁** (12 条) ◀ 当前
- `f6e5d4c3b2a1`... **[微信] 张三** (5 条)
- `112233445566`... **新对话** (0 条)"""

AGENT_TEXT = """📋 **可用 Agent** (3 个):

- **plan** ◀ 当前: 制定实施计划
- **build**: 编码实现
- **code-reviewer**: 代码审查"""

# ── 从 feishu.py 提取被测函数（避免 import 整个模块） ─────────────

src = open("plugins/gateway-feishu/gateways/feishu.py", encoding="utf-8").read()
tree = ast.parse(src)
mod = types.ModuleType("feishu_funcs")
mod.__dict__.update({"re": re, "List": List, "Optional": Optional, "logger": None})

WANTED = {"_detect_command_card", "_parse_model_list", "_parse_session_list",
          "_parse_agent_list", "_build_help_card", "_build_model_card",
          "_build_session_card", "_build_agent_card", "_btn"}
ns = {"re": re, "List": List, "Optional": Optional, "logger": types.SimpleNamespace(warning=lambda *a, **k: None)}
for node in tree.body:
    if isinstance(node, ast.ClassDef):
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name in WANTED:
                # staticmethod 无 self；_detect_command_card 引用 FeishuAdapter.xxx → 注入类名
                code = ast.get_source_segment(src, item)
                code = code.replace("FeishuAdapter._", "ns._") if False else code
                exec(code, ns)

# 类名引用替换：把函数体内的 FeishuAdapter 绑定到 ns 自身
class _FA:
    pass


for k in list(ns.keys()):
    setattr(_FA, k, ns[k])
ns["FeishuAdapter"] = _FA

ok = True

def check(name, cond, detail=""):
    global ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"[{status}] {name} {detail}")

# 1. help 识别
card = ns["_detect_command_card"](HELP_TEXT)
check("help 识别", card is not None and card["header"]["title"]["content"] == "🤖 DriFox Gateway 命令")
btns = card["elements"][-2]["actions"]
check("help 按钮 4 个", len(btns) == 4, str([b["text"]["content"] for b in btns]))
check("help 按钮 value", btns[0]["value"]["drifox_cmd"] == "/new")

# 2. model 解析
providers = ns["_parse_model_list"](MODEL_TEXT)
check("model 服务商数", len(providers) == 3)
p0 = providers[0]
check("model p0 名称", p0["display"] == "DeepSeek", str(p0["display"]))
check("model p0 current", p0["current"] is True)
check("model p0 default", p0["default_model"] == "deepseek-chat")
check("model p0 可选数", len(p0["models"]) == 3, str(p0["models"]))
p2 = providers[2]
check("model p2 单行式", p2["display"] == "本地 Ollama" and p2["default_model"] == "qwen3:8b" and p2["session"] is True, str(p2))
check("model p2 无可选", p2["models"] == [])

card = ns["_detect_command_card"](MODEL_TEXT)
check("model 卡片生成", card is not None)
action_els = [e for e in card["elements"] if e.get("tag") == "action"]
check("model 按钮区 2 个（p2 含空格降级）", len(action_els) == 2, str(len(action_els)))
first_btns = action_els[0]["actions"]
check("model 按钮数 3", len(first_btns) == 3)
check("model 按钮命令", first_btns[0]["value"]["drifox_cmd"] == "/model DeepSeek deepseek-chat")
check("model 当前默认模型按钮禁用", first_btns[0].get("disabled") is True)
check("model 非默认按钮可用", "disabled" not in first_btns[1])
# 含空格服务商降级为文本提示
md_els = [e for e in card["elements"] if e.get("tag") == "markdown" and "服务商名含空格" in e.get("content", "")]
check("model 空格服务商降级提示", len(md_els) == 1)

# 3. session 解析
sessions = ns["_parse_session_list"](SESSION_TEXT)
check("session 数", len(sessions) == 3)
s0 = sessions[0]
check("session p0", s0["sid"] == "a1b2c3d4e5f6" and s0["name"] == "[飞书] 马丁" and s0["count"] == 12 and s0["current"] is True, str(s0))
card = ns["_detect_command_card"](SESSION_TEXT)
action_els = [e for e in card["elements"] if e.get("tag") == "action"]
check("session 按钮 3 个", len(action_els) == 3)
check("session 当前禁用", action_els[0]["actions"][0].get("disabled") is True)
check("session 切换命令", action_els[1]["actions"][0]["value"]["drifox_cmd"] == "/session f6e5d4c3b2a1")
check("session 切换 primary", action_els[1]["actions"][0]["type"] == "primary")

# 4. agent 解析
agents = ns["_parse_agent_list"](AGENT_TEXT)
check("agent 数", len(agents) == 3)
a0 = agents[0]
check("agent p0", a0["name"] == "plan" and a0["current"] is True and a0["desc"] == "制定实施计划", str(a0))
card = ns["_detect_command_card"](AGENT_TEXT)
action_els = [e for e in card["elements"] if e.get("tag") == "action"]
check("agent 按钮命令", action_els[1]["actions"][0]["value"]["drifox_cmd"] == "/agent build")

# 5. 非命令文本 → None（AI 回复不误伤）
check("AI 普通文本不命中", ns["_detect_command_card"]("这是一段普通 AI 回复，**含粗体**") is None)
check("空列表文案不命中", ns["_detect_command_card"]("📋 没有历史会话。") is None)
check("✅ 提示不命中", ns["_detect_command_card"]("✅ 已切换到 **DeepSeek** 的模型: `deepseek-chat`\n（仅当前 Gateway 会话生效）") is None)

# 6. JSON 可序列化（卡片 content 会 json.dumps）
for name, text in [("help", HELP_TEXT), ("model", MODEL_TEXT), ("session", SESSION_TEXT), ("agent", AGENT_TEXT)]:
    card = ns["_detect_command_card"](text)
    try:
        json.dumps(card, ensure_ascii=False)
        check(f"{name} 卡片 JSON 序列化", True)
    except Exception as e:
        check(f"{name} 卡片 JSON 序列化", False, str(e))

print("\n结果:", "全部通过 ✅" if ok else "存在失败 ❌")
sys.exit(0 if ok else 1)
