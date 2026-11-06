# -*- coding: utf-8 -*-
"""gateway-feishu 命令卡片解析器验证（不依赖 lark SDK，独立跑解析逻辑）

pytest 规范：模块级只做 AST 提取（无副作用出口），断言全部在 test_* 函数内。
Run: python -m pytest tests/test_feishu_cmd_card.py -v
"""
import ast
import json
import re
import types
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

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

src = (REPO_ROOT / "plugins" / "gateway-feishu" / "gateways" / "feishu.py").read_text(encoding="utf-8")
tree = ast.parse(src)

WANTED = {"_detect_command_card", "_parse_model_list", "_parse_session_list",
          "_parse_agent_list", "_build_help_card", "_build_model_card",
          "_build_session_card", "_build_agent_card", "_btn"}
ns = {"re": re, "List": List, "Optional": Optional,
      "logger": types.SimpleNamespace(warning=lambda *a, **k: None)}
for node in tree.body:
    if isinstance(node, ast.ClassDef):
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name in WANTED:
                exec(ast.get_source_segment(src, item), ns)


# 类名引用替换：把函数体内的 FeishuAdapter 绑定到 ns 自身
class _FA:
    pass


for k in list(ns.keys()):
    setattr(_FA, k, ns[k])
ns["FeishuAdapter"] = _FA

_detect_command_card = ns["_detect_command_card"]
_parse_model_list = ns["_parse_model_list"]
_parse_session_list = ns["_parse_session_list"]
_parse_agent_list = ns["_parse_agent_list"]


def test_help_card():
    card = _detect_command_card(HELP_TEXT)
    assert card is not None
    assert card["header"]["title"]["content"] == "🤖 DriFox Gateway 命令"
    btns = card["elements"][-2]["actions"]
    assert len(btns) == 4, str([b["text"]["content"] for b in btns])
    assert btns[0]["value"]["drifox_cmd"] == "/new"


def test_model_list():
    providers = _parse_model_list(MODEL_TEXT)
    assert len(providers) == 3
    p0 = providers[0]
    assert p0["display"] == "DeepSeek", str(p0["display"])
    assert p0["current"] is True
    assert p0["default_model"] == "deepseek-chat"
    assert len(p0["models"]) == 3, str(p0["models"])
    p2 = providers[2]
    assert p2["display"] == "本地 Ollama" and p2["default_model"] == "qwen3:8b" and p2["session"] is True, str(p2)
    assert p2["models"] == []

    card = _detect_command_card(MODEL_TEXT)
    assert card is not None
    action_els = [e for e in card["elements"] if e.get("tag") == "action"]
    assert len(action_els) == 2, f"p2 含空格应降级为文本提示，实际 {len(action_els)}"
    first_btns = action_els[0]["actions"]
    assert len(first_btns) == 3
    assert first_btns[0]["value"]["drifox_cmd"] == "/model DeepSeek deepseek-chat"
    assert first_btns[0].get("disabled") is True
    assert "disabled" not in first_btns[1]
    md_els = [e for e in card["elements"] if e.get("tag") == "markdown" and "服务商名含空格" in e.get("content", "")]
    assert len(md_els) == 1


def test_session_list():
    sessions = _parse_session_list(SESSION_TEXT)
    assert len(sessions) == 3
    s0 = sessions[0]
    assert s0["sid"] == "a1b2c3d4e5f6" and s0["name"] == "[飞书] 马丁" and s0["count"] == 12 and s0["current"] is True, str(s0)
    card = _detect_command_card(SESSION_TEXT)
    action_els = [e for e in card["elements"] if e.get("tag") == "action"]
    assert len(action_els) == 3
    assert action_els[0]["actions"][0].get("disabled") is True
    assert action_els[1]["actions"][0]["value"]["drifox_cmd"] == "/session f6e5d4c3b2a1"
    assert action_els[1]["actions"][0]["type"] == "primary"


def test_agent_list():
    agents = _parse_agent_list(AGENT_TEXT)
    assert len(agents) == 3
    a0 = agents[0]
    assert a0["name"] == "plan" and a0["current"] is True and a0["desc"] == "制定实施计划", str(a0)
    card = _detect_command_card(AGENT_TEXT)
    action_els = [e for e in card["elements"] if e.get("tag") == "action"]
    assert action_els[1]["actions"][0]["value"]["drifox_cmd"] == "/agent build"


def test_negative_cases():
    # 非命令文本 → None（AI 回复不误伤）
    assert _detect_command_card("这是一段普通 AI 回复，**含粗体**") is None
    assert _detect_command_card("📋 没有历史会话。") is None
    assert _detect_command_card("✅ 已切换到 **DeepSeek** 的模型: `deepseek-chat`\n（仅当前 Gateway 会话生效）") is None


def test_cards_json_serializable():
    # 卡片 content 会 json.dumps，必须可序列化
    for name, text in [("help", HELP_TEXT), ("model", MODEL_TEXT), ("session", SESSION_TEXT), ("agent", AGENT_TEXT)]:
        card = _detect_command_card(text)
        try:
            json.dumps(card, ensure_ascii=False)
        except Exception as e:
            raise AssertionError(f"{name} 卡片 JSON 序列化失败: {e}")
