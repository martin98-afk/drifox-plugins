# -*- coding: utf-8 -*-
"""
evolution_scaffold — 自进化工具 1：按需求生成 DriFox 插件骨架。

写入目标默认 user 根（~/.drifox/plugins/<name>/），保存即热重载。
支持 DriFox 全部 **17 类组件**（对齐主程序 kernel.KNOWN_COMPONENTS）：
tools / commands / agents / skills / hooks / mcp / lsp / themes /
ui / providers / team_templates /
model_adapters / loop_policies / storages / serializers / gateways / engines。

安全约束：
- 插件名必须 ^[a-z][a-z0-9-]{1,63}$（kebab-case）
- 拒绝覆盖已存在插件（force=true 除外，且只清空重建属危险操作，仍保留备份提示）
- 所有生成的 Python 模板通过 py_compile 语法级保证
"""
import json
import re
import shutil
import time
from pathlib import Path

from app.tools.result import ToolResult

VALID_COMPONENTS = (
    "tools", "commands", "agents", "skills", "hooks", "mcp", "lsp", "themes",
    "ui", "providers", "team_templates",
    "model_adapters", "loop_policies", "storages", "serializers", "gateways", "engines",
)

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


def _user_root(tool_ctx) -> Path:
    """插件写入根：优先平台 app_data，回退 ~/.drifox/plugins"""
    env = tool_ctx.get("env") or {}
    app_data = env.get("app_data_dir")
    if app_data:
        root = Path(app_data) / "plugins"
        if root.is_dir():
            return root
    return Path.home() / ".drifox" / "plugins"


# ---------- 各组件模板 ----------

_TOOL_PY = '''# -*- coding: utf-8 -*-
"""{tool_name} — 由 evolution_scaffold 生成的工具骨架。impl 签名：impl(tool_ctx, **kwargs) -> ToolResult"""
from app.tools.result import ToolResult


def _impl(tool_ctx, **kwargs):
    # TODO: 实现工具逻辑；tool_ctx 提供 workdir/env/services
    return ToolResult(True, content="{plugin} 工具骨架已就绪，请填充实现。")


_SCHEMA = {{
    "type": "function",
    "function": {{
        "name": "{tool_name}",
        "description": "{tool_name} 工具（骨架，待实现）",
        "parameters": {{
            "type": "object",
            "properties": {{}},
            "required": [],
        }},
    }},
}}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "{tool_name}", _SCHEMA, impl=_impl,
        danger="safe",  # 必填：safe | dangerous
        cn_name="{cn_tool_name}",
        group="{group}",
        description="{plugin} 工具（骨架）",
        # ── 可选注册参数（按需取消注释） ──
        # render_mode="inline",     # 完成框形态：""=折叠卡 / "inline"=单行无body / "expand"=常开 / "none"=不渲染
        # keep_in_content=True,     # True=完成卡常驻消息正文；缺省=简洁模式收进「工具与思考」折叠区
        # preview=_preview_fn,      # 自然语言参数预览：preview(tool_args) -> str（inline卡/折叠头显示）
        # metadata={{"permission_arg": "path"}},  # 权限/视觉/交互等语义声明，详见 docs/plugins
    )
'''

_COMMAND_MD = '''---
description: {description}
type: prompt
---

# /{cmd}

TODO: 编写命令提示词正文。可用模板变量：$ARGUMENTS、$PLUGIN_NAME、$PLUGIN_DIR、$PROJECT_ROOT。
'''

_AGENT_MD = '''---
description: {description}。触发词：{plugin}、{plugin} 智能体。
mode: subagent
steps: 20
temperature: 0.3
permission:
  "*": allow
---

# Role

你是 {plugin} 插件的智能体（骨架）。TODO: 定义角色职责与输出格式。
'''

_SKILL_MD = '''---
name: {plugin}
description: {description}。触发关键词：{plugin}。
---

# {plugin} 技能

TODO: 编写技能知识正文（最佳实践、约束、流程）。
'''

_HOOKS_JSON = '''{{
  "description": "{plugin} Hook",
  "hooks": {{
    "PostToolUse": [
      {{
        "hooks": [
          {{
            "type": "python",
            "function": ".{plugin}_hook:handle",
            "timeout": 5,
            "enabled": true,
            "id": "{hook_id}"
          }}
        ]
      }}
    ]
  }}
}}
'''

_HOOK_PY = '''# -*- coding: utf-8 -*-
"""{plugin} hook（骨架）。事件见 hooks/hooks.json；handler 入参为事件 payload dict。"""


def handle(payload: dict) -> dict:
    # TODO: 实现钩子逻辑；返回 {{}} 或附加数据
    return {{}}
'''

_MCP_JSON = '''{
  "mcpServers": {
    "example-server": {
      "type": "stdio",
      "command": "TODO-command",
      "args": [],
      "env": {},
      "enabled": false,
      "url": "",
      "headers": {}
    }
  }
}
'''

_LSP_JSON = '''{
  "TODO-language": {
    "command": "TODO-lsp-command",
    "args": []
  }
}
'''

# ---------- UI / Providers / TeamTemplates / 运行时组件模板 ----------

# ---------- 主题模板（对齐 laputa-fog/fe-fw 真实结构：themes/<id>/<id>.yaml） ----------

_THEME_YAML = '''# ─────────────────────────────────────────────
# {plugin} 主题（骨架）
# 完整字段参考 plugins/laputa-fog/themes/laputa-fog/laputa-fog.yaml
# 背景图可选：把 <plugin>_bg.jpg 放同目录，取消 background 注释
# ─────────────────────────────────────────────
name: TODO 中文名
id: {plugin}
mode: light  # light | dark
window:
  gradient_start: rgba(228, 236, 242, 255)
  gradient_end: rgba(210, 220, 228, 255)
# background:
#   chat_list:
#     image: {plugin}_bg.jpg
#     opacity: 0.13
#     enabled: true
colors:
  # ── 基础色 ──
  accent: '#5B7E8E'
  accent_warm: '#C49A5C'
  border: '#B6C2CC'
  text_primary: '#1F2D38'
  text_secondary: rgba(31, 45, 56, 0.60)
  text_muted: '#7A8A96'
  card_bg: rgba(233, 238, 242, 238)
  card_bg_solid: rgba(233, 238, 242, 252)
  content_bg: '#DDE5EC'
  hover_bg: rgba(91, 126, 142, 0.08)
  selected_bg: rgba(91, 126, 142, 0.18)

  # ── 全局 UI 基底 ──
  toolbar_bg: rgba(91, 126, 142, 0.05)
  divider_color: rgba(0, 0, 0, 0.07)
  scrollbar_handle_bg: rgba(0, 0, 0, 0.15)

  # ── 语法高亮 ──
  syntax_step: '#059669'
  syntax_tool: '#B45309'
  syntax_success: '#16A34A'
  syntax_error: '#DC2626'
  syntax_result: '#7C3AED'

  # ── 用户 / AI 卡片 ──
  user_card_bg: rgba(200, 222, 236, 195)
  user_card_accent: '#5B7E8E'
  user_card_text: '#1F2D38'
  assistant_card_bg: rgba(245, 230, 200, 225)
  assistant_card_accent: '#C49A5C'
  assistant_card_text: '#1F2D38'

  # ── 输入框 ──
  input_bg_start: rgba(215, 230, 240, 210)
  input_bg_end: rgba(205, 222, 234, 210)
  input_text: '#1F2D38'
  input_border: '#B6C2CC'
  input_focus_border: '#5B7E8E'
  input_placeholder: rgba(31, 45, 56, 0.35)

  # ── 发送按钮 ──
  send_btn_start: '#5B7E8E'
  send_btn_end: '#4A6A78'
  send_btn_radius: 17

  # ── 上下文圆环 / 时间线（可按需扩展更多字段）──
  ring_normal: '#5B7E8E'
  ring_warning: '#C49A5C'
  ring_danger: '#EF4444'
  timeline_node: '#B0C0CC'
  timeline_line: '#C8D4DE'
'''

_UI_INIT = '''# -*- coding: utf-8 -*-
"""{plugin} UI 组件骨架 — DriFox 启动时 UIPluginRegistry.load_plugin 调用。

主程序 UIPluginRegistry（app/plugins/registries/ui_plugin_registry.py）提供
**8 类扩展点**（按需选用，可同时注册多个，不要全用）：

| 扩展点 | 用途 | 典型场景 |
|--------|------|----------|
| register_content_renderer     | 自定义消息流内容块渲染（type_name → html） | 消息里出现特殊块时插入自定义 html |
| register_welcome_tab          | 欢迎页加自定义 tab                          | 启动展示自定义页面 |
| register_floating_card        | 浮动卡片（自动注册 /<card_id> 命令）        | 全屏/侧边/底部的卡片 UI |
| register_sidebar_item         | 侧边栏插件项                                | 左/右侧导航新增图标入口 |
| register_input_button         | 输入框插件按钮                              | 输入区旁的快捷按钮（图+提示） |
| register_context_menu_action  | 右键菜单项（target ∈ message_card / tab）   | 消息卡片/标签右键加项 |
| register_settings_card        | 设置面板卡片                                | 设置界面新增分类卡 |
| register_message_factory      | 消息元素工厂（condition 命中 → 生成 widget）| 特定消息结构 → 自定义 QWidget |

container 取值（仅 floating_card）：top / bottom / left / right / full（full=完整覆盖对话区，与系统配置卡片一致）。

真实案例（强烈建议参照）：
- 浮动卡片：plugins/context-usage-stats/ui/__init__.py + ui/cards.py（container="full"、title="用量统计"、default_visible=False）
- 浮动卡片：plugins/file-tree / plugin-marketplace / share-history / shortcut-manager / system-cleaner

热重载兼容（强烈建议照抄下面三行，避免旧 __pycache__ 残留导致 NameError）：
    import sys
    prefix = "{plugin}."  # 按需改成你的子模块前缀
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]
"""


def register_ui(registry):
    """UI 注册入口（必须此函数名，PluginToolLoader 反射调用）"""
    import sys
    prefix = "{plugin}."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    # TODO: 按需选用下列扩展点之一/多个，调对应 register_* 方法。
    # 真实案例（从 .cards 导入 QWidget 子类）：
    #     from .cards import MyCard
    #     registry.register_floating_card(
    #         plugin_name="{plugin}", card_id="my-card", widget_class=MyCard,
    #         container="top", title="...", default_visible=False)
    pass
'''

_PROVIDER_PY = '''# -*- coding: utf-8 -*-
"""{provider} 服务商骨架 — 被 ProviderWatcher 扫描调用。

写法参考 app.plugins.registries.provider_registry.ProviderDef 字段定义。
"""
from app.plugins.registries.provider_registry import ProviderDef


def register(registry):
    registry.register(
        ProviderDef(
            name="{provider}",           # 服务商唯一名
            icon="{provider}",            # 图标 key（icons/ 文件名，可省略回退 qrc）
            api_url="https://TODO.api.endpoint",
            auth_type="bearer",           # bearer / bce / none / anthropic
            default_model="TODO-model",
            register_url="https://TODO.get.key",
            # models=["model-a"], family="xxx", capabilities={{...}},
            # balance_fetcher=..., coding_plan_fetcher=...,  可选
        )
    )
'''

_TEAM_YAML = '''# 用法：/team --load={plugin}
schema_version: 1
template_name: {plugin}
description: {description}（TODO 替换描述）
agents:
  - agent_name: build
    description: 构建智能体，负责读写代码与验证
  # agent_name 必须引用已存在的 @角色（plugins/system/agents/），加载时校验
'''

_RUNTIME_PY = '''# -*- coding: utf-8 -*-
"""{kind} 组件骨架 — 被 runtime_component_loader.scan_roots 调用。

{kind_note}
"""
# TODO: 按目标 contracts 协议实现类，参考 plugins/system/{sys_dir}/ 同类实现


class {cls_name}:
    """TODO: 实现组件协议（id 属性 + 协议方法）"""

    id = "{plugin}"


def register(registry):
    """注册入口 — 与 tools/providers 插件约定一致（source 由 loader 强制注入）"""
    registry.register({cls_name}())
'''

# storages 增强模板：预置已沉淀的正确实践（详见 self-evolver references/storage_engine.md）
# 1) __init__ 末尾立即 _ensure_init() → is_initialized=True（history_manager 靠它探测）
# 2) register() 末尾自激活（StorageRegistry 默认 sqlite，不自动按 enabled 切）
# 3) 提示 config_schema 字段类型用 bool
_STORAGE_PY = '''# -*- coding: utf-8 -*-
"""storages 组件骨架 — 被 runtime_component_loader.scan_roots 调用。

存储引擎：会话/数据持久化（参考 system/storages/sqlite.py）。

⚠ 已沉淀踩坑（详见 self-evolver references/storage_engine.md）：
1. 必须实现 is_initialized 且 __init__ 末尾立即 _ensure_init()，否则
   history_manager._init_storage 读 is_initialized=False 回退 JSON，
   save_session 永远走不到本引擎（input_history 因直接调用不受影响）。
2. 主程序 StorageRegistry 默认 _active="sqlite"，不会自动按 config_schema.enabled
   调 set_active —— 插件必须在 register() 末尾自激活。
3. config_schema 字段类型用 "bool"（不是 "switch"）；在 plugin.json 加：
   "enabled"(bool) + "db_dir"(text) 字段，引擎 __init__ 读 PluginConfigStore。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


class {cls_name}:
    """会话存储引擎 — 行为对齐 system/storages/sqlite.py（同名方法）"""

    id = "{plugin}"

    def __init__(self, db_dir: Optional[str] = None):
        # ⚠ 先设 False 再调 _ensure_init（_ensure_init 首行 if self._initialized 需要属性存在）
        self._initialized = False
        if db_dir:
            self._base = Path(db_dir)
        else:
            self._base = Path.home() / ".drifox" / "data" / "{plugin}"
        self._sessions_dir = self._base / "sessions"
        self._lock = threading.RLock()
        # ⚠ 必须立即初始化：history_manager 靠 is_initialized 探测
        self._ensure_init()

    def _ensure_init(self) -> None:
        if self._initialized:
            return
        for d in (self._base, self._sessions_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # TODO: 实现 save/get/get_all/get_by_project/delete/update_session_title/
    #       get_session_counts/get_input_history/add_input_history（对齐 sqlite.py）
    def save(self, session: Dict[str, Any]) -> bool:
        return False  # TODO


def register(registry):
    """注册入口 — source 由 loader 强制注入"""
    engine = {cls_name}()
    registry.register(engine)
    # ⚠ 自激活：主程序不基于 config_schema.enabled 自动 set_active
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore
        if PluginConfigStore().get("{plugin}", "enabled"):
            registry.set_active("{plugin}")
    except Exception:
        pass
'''


_KIND_NOTES = {
    "model_adapters": ("model_adapters", "模型适配器：统一不同厂商 API 差异（参考 system/model_adapters/openai_family.py）"),
    "loop_policies": ("loop_policies", "循环策略：决定 agent loop 继续/停止（参考 system/loop_policies/default.py，协议在 app.plugins.contracts.loop_policy）"),
    "storages": ("storages", "存储引擎：会话/数据持久化（参考 system/storages/sqlite.py）"),
    "serializers": ("serializers", "序列化器：消息格式转换（参考 system/serializers/openai.py）"),
    "gateways": ("gateways", "网关：外部消息平台接入（参考 gateway-feishu/gateways/feishu.py，协议在 app.plugins.contracts.gateway_platform）"),
    "engines": ("engines", "对话引擎：可替换的对话处理核心（参考 system/ 下 engines 实现）"),
}


def _manifest(name: str, description: str, comps: list, author: str = "self-evolver") -> str:
    # components 覆盖 kernel.KNOWN_COMPONENTS 全集 17 类（缺省 false）
    all_comps = [
        "tools", "commands", "agents", "skills", "hooks", "mcp", "lsp", "themes",
        "ui", "providers", "team_templates",
        "model_adapters", "loop_policies", "storages", "serializers", "gateways", "engines",
    ]
    components = {c: (c in comps) for c in all_comps}
    manifest = {
        "name": name,
        "description": description[:200],
        "version": "0.1.0",
        "author": {"name": author},
        "license": "GPL-3.0-or-later",
        "type": "user",
        "drifox": {"min_version": "0.5.0"},
        "keywords": [name.split("-")[0], "evolved"],
        "components": components,
    }
    return json.dumps(manifest, ensure_ascii=False, indent=4)


def _gen_hook_id() -> str:
    return f"{int(time.time() * 1000):032x}"[-32:]


def _write_components(base: Path, name: str, description: str, comps: list) -> list:
    """写入各组件骨架文件，返回相对路径清单"""
    written = []

    if "tools" in comps:
        d = base / "tools"
        d.mkdir(exist_ok=True)
        tool_name = name.replace("-", "_")
        (d / f"{tool_name}.py").write_text(
            _TOOL_PY.format(
                tool_name=tool_name, plugin=name, cn_tool_name=name,
                group=name, description=description,
            ),
            encoding="utf-8",
        )
        written.append(f"tools/{tool_name}.py")

    if "commands" in comps:
        d = base / "commands"
        d.mkdir(exist_ok=True)
        cmd = name.split("-")[0]
        (d / f"{cmd}.md").write_text(
            _COMMAND_MD.format(description=description[:80], cmd=cmd),
            encoding="utf-8",
        )
        written.append(f"commands/{cmd}.md")

    if "agents" in comps:
        d = base / "agents"
        d.mkdir(exist_ok=True)
        (d / "assistant.md").write_text(
            _AGENT_MD.format(description=description[:80], plugin=name),
            encoding="utf-8",
        )
        written.append("agents/assistant.md")

    if "skills" in comps:
        d = base / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            _SKILL_MD.format(plugin=name, description=description[:80]),
            encoding="utf-8",
        )
        written.append(f"skills/{name}/SKILL.md")

    if "hooks" in comps:
        d = base / "hooks"
        d.mkdir(exist_ok=True)
        (d / "hooks.json").write_text(
            _HOOKS_JSON.format(plugin=name, hook_id=_gen_hook_id()),
            encoding="utf-8",
        )
        (d / f"{name}_hook.py").write_text(
            _HOOK_PY.format(plugin=name), encoding="utf-8"
        )
        written.extend(["hooks/hooks.json", f"hooks/{name}_hook.py"])

    if "mcp" in comps:
        (base / ".mcp.json").write_text(_MCP_JSON, encoding="utf-8")
        written.append(".mcp.json")

    if "lsp" in comps:
        (base / ".lsp.json").write_text(_LSP_JSON, encoding="utf-8")
        written.append(".lsp.json")

    if "themes" in comps:
        # 真实主题结构：themes/<id>/<id>.yaml（背景图可选）
        d = base / "themes" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.yaml").write_text(
            _THEME_YAML.format(plugin=name), encoding="utf-8"
        )
        written.append(f"themes/{name}/{name}.yaml")

    if "ui" in comps:
        d = base / "ui"
        d.mkdir(exist_ok=True)
        (d / "__init__.py").write_text(_UI_INIT.format(plugin=name), encoding="utf-8")
        written.append("ui/__init__.py")

    if "providers" in comps:
        d = base / "providers"
        d.mkdir(exist_ok=True)
        provider = name.replace("-", "_")
        (d / f"{provider}.py").write_text(
            _PROVIDER_PY.format(provider=provider), encoding="utf-8"
        )
        written.append(f"providers/{provider}.py")

    if "team_templates" in comps:
        d = base / "team_templates"
        d.mkdir(exist_ok=True)
        (d / f"{name}.yaml").write_text(
            _TEAM_YAML.format(plugin=name, description=description[:40]),
            encoding="utf-8",
        )
        written.append(f"team_templates/{name}.yaml")

    for kind in ("model_adapters", "loop_policies", "storages", "serializers", "gateways", "engines"):
        if kind in comps:
            sys_dir, note = _KIND_NOTES[kind]
            d = base / kind
            d.mkdir(exist_ok=True)
            mod = name.replace("-", "_")
            cls = mod.title().replace("_", "")
            if kind == "storages":
                # storages 用增强模板：预置 is_initialized 初始化 + register 自激活
                content = _STORAGE_PY.format(plugin=name, cls_name=cls)
            else:
                content = _RUNTIME_PY.format(
                    kind=kind, kind_note=note, sys_dir=sys_dir, plugin=name, cls_name=cls,
                )
            (d / f"{mod}.py").write_text(content, encoding="utf-8")
            written.append(f"{kind}/{mod}.py")

    return written


def _impl(tool_ctx, **kwargs):
    try:
        name = (kwargs.get("name") or "").strip()
        description = (kwargs.get("description") or f"{name} 插件（self-evolver 生成）").strip()
        components = kwargs.get("components") or ["tools"]
        force = bool(kwargs.get("force"))

        # 参数校验
        if not name:
            return ToolResult(False, error="必须提供 name（kebab-case 插件名，如 my-tool-plugin）")
        if not _NAME_RE.match(name):
            return ToolResult(
                False,
                error=f"插件名 {name!r} 不符合 ^[a-z][a-z0-9-]{{1,63}}$ 规则",
            )
        if isinstance(components, str):
            components = [c.strip() for c in components.split(",") if c.strip()]
        bad = [c for c in components if c not in VALID_COMPONENTS]
        if bad:
            return ToolResult(
                False,
                error=f"不支持的组件类型 {bad}；可用：{list(VALID_COMPONENTS)}",
            )

        root = _user_root(tool_ctx)
        base = root / name
        bak = None

        if base.exists():
            if not force:
                return ToolResult(
                    False,
                    error=f"插件 {name} 已存在于 {base}。确认覆盖请设 force=true"
                          f"（旧版本会备份为 {name}.bak.<ts>）",
                )
            bak = root / f"{name}.bak.{int(time.time())}"
            shutil.move(str(base), str(bak))

        root.mkdir(parents=True, exist_ok=True)
        base.mkdir()

        # manifest
        manifest_dir = base / ".drifox-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            _manifest(name, description, components, author=(kwargs.get("author") or "self-evolver").strip()),
            encoding="utf-8",
        )
        written = [".drifox-plugin/plugin.json"]

        # 组件骨架
        written += _write_components(base, name, description, components)

        # README + 包标记
        (base / "__init__.py").write_text(
            f'# -*- coding: utf-8 -*-\n"""{name} — self-evolver 生成"""\n',
            encoding="utf-8",
        )
        (base / "README.md").write_text(
            f"# {name}\n\n{description}\n\n> 由 evolution_scaffold 生成，"
            f"骨架文件已就位，请填充 TODO 实现。\n",
            encoding="utf-8",
        )
        written += ["__init__.py", "README.md"]

        backup_note = f"\n旧版本已备份：{bak.name}" if bak else ""
        content = (
            f"插件骨架 {name} 已生成 ✅\n\n"
            f"路径：{base}\n"
            f"组件：{components}\n"
            f"文件清单：\n" + "\n".join(f"  - {w}" for w in written) +
            f"\n\n下一步：\n"
            f"1. 填充各 TODO 实现（read/edit 直接改，热重载自动生效）\n"
            f"2. 用 evolution_validate plugin_name={name} 校验\n"
            f"3. 用 evolution_journal 记录本次进化{backup_note}"
        )
        return ToolResult(True, content=content)
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"evolution_scaffold 内部异常：{type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "evolution_scaffold",
        "description": (
            "自进化：按需求生成 DriFox 插件骨架（manifest+组件模板+README），"
            "写入 user 根（~/.drifox/plugins/<name>/）保存即热重载。"
            "生成后填充 TODO 即得新插件。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "插件名，kebab-case（如 my-tool-plugin），与目录名一致",
                },
                "description": {
                    "type": "string",
                    "description": "一句话插件描述（≤200字），写入 manifest",
                },
                "components": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": list(VALID_COMPONENTS),
                    },
                    "description": (
                        "要启用的组件列表，默认 ['tools']。支持全部 17 类："
                        "tools/commands/agents/skills/hooks/mcp/lsp/themes/ui/providers/"
                        "team_templates/model_adapters/loop_policies/storages/serializers/gateways/engines"
                    ),
                },
                "force": {
                    "type": "boolean",
                    "description": "同名插件已存在时覆盖（旧版备份为 .bak.<ts>），默认 false",
                    "default": False,
                },
                "author": {
                    "type": "string",
                    "description": "插件作者名（写入 manifest author.name），默认 self-evolver",
                },
            },
            "required": ["name"],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "evolution_scaffold", _SCHEMA, impl=_impl,
        danger="safe", icon="evolution_scaffold", cn_name="生成插件骨架",
        group="自进化", description="按需求生成 DriFox 插件骨架（热重载即时生效）",
        metadata={"permission_arg": "name"},
    )
