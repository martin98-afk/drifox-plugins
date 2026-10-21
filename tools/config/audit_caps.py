# -*- coding: utf-8 -*-
"""排查：插件代码用了宿主 services legacy 键，但 plugin.json capabilities 漏声明。"""
import json
import re
from pathlib import Path

# legacy 键 -> (能力 ID, surfaces)；state.kv/plugin.log 免声明不列
LEGACY = {
    "get_tools_schema": ("model.schema", {"ui", "tool"}),
    "get_model_config": ("model.config", {"ui", "tool"}),
    "get_provider_config": ("model.config", {"ui", "tool"}),
    "save_messages_to_session": ("session.write", {"ui", "tool"}),
    "get_agent_manager": ("agent.read", {"ui", "tool"}),
    "get_agent_prompt": ("agent.read", {"ui", "tool"}),
    "get_workdir": ("workdir.read", {"ui", "tool"}),
    "set_workdir": ("workdir.write", {"ui"}),
    "sync_working_directory": ("workdir.write", {"ui"}),
    "get_compactor": ("context.compact", {"ui", "tool"}),
    "get_tool_executor": ("tool.execute", {"ui", "tool"}),
    "create_engine_session": ("engine.session", {"ui"}),
    "conversation_stack": ("engine.stack", {"ui"}),
    "send_to_platform": ("platform.send", {"ui"}),
    "list_platform_sessions": ("platform.read", {"ui"}),
    "list_platforms": ("platform.read", {"ui"}),
    "mcp": ("mcp.call", {"tool"}),
    "lsp": ("lsp.query", {"tool"}),
    "gitee": ("net.upload", {"tool"}),
    "notify": ("ui.notify", {"ui"}),
    "hide_card": ("ui.card.hide", {"ui"}),
    "enter_exclusive_ui_mode": ("ui.exclusive", {"ui"}),
    "exit_exclusive_ui_mode": ("ui.exclusive", {"ui"}),
    "get_setting": ("config.read", {"ui"}),
    "subagent": ("subagent.run", {"tool"}),
}
# manifest 扁平别名（A3 时代写法）
ALIASES = {
    "lsp": "lsp.query", "mcp": "mcp.call", "gitee": "net.upload",
    "subagent": "subagent.run", "window_state": "state.kv",
    "notify": "ui.notify", "hide_card": "ui.card.hide",
}
USE_RE = re.compile(r'services(?:\[|\.get\()\s*["\'](\w+)["\']')

root = Path("plugins")
problems = []
for pjson in sorted(root.glob("*/.drifox-plugin/plugin.json")):
    pdir = pjson.parent.parent
    name = pdir.name
    try:
        manifest = json.loads(pjson.read_text(encoding="utf-8"))
    except Exception as e:
        problems.append((name, [], [f"plugin.json 解析失败: {e}"]))
        continue
    caps = set()
    for raw in manifest.get("capabilities", []) or []:
        caps.add(ALIASES.get(str(raw).strip(), str(raw).strip()))
    # surface 判定：ui 组件 or 非 ui 组件
    comps = manifest.get("components", {})
    surfaces = set()
    if comps.get("ui"):
        surfaces.add("ui")
    if any(k for k in comps if k != "ui"):
        surfaces.add("tool")
    if not surfaces:
        surfaces.add("tool")  # 无 ui 组件按 tool 上下文对待
    # 扫代码里的 services 用法（跳过 .drifox-plugin 与文档）
    used = {}
    for py in pdir.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in USE_RE.finditer(text):
            key = m.group(1)
            if key in LEGACY:
                used.setdefault(key, py.relative_to(pdir))
    missing = []
    for key, rel in sorted(used.items()):
        cap, srf = LEGACY[key]
        if cap not in caps and srf & surfaces:
            missing.append(f"{key} -> {cap} (用见 {rel})")
    if missing:
        problems.append((name, sorted(caps), missing))

if not problems:
    print("OK: 全部插件声明齐备")
for name, caps, missing in problems:
    print(f"\n[漏声明] {name}  capabilities={caps or '[]'}")
    for m in missing:
        print(f"  - {m}")
