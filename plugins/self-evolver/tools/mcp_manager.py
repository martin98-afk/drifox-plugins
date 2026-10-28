# -*- coding: utf-8 -*-
"""
evolution_mcp — 自进化工具 4：管理 DriFox 插件的 MCP 服务器配置（.mcp.json）。

操作：
- list   列出指定插件（或全部插件）已配置的 MCP 服务器
- add    添加 MCP 服务器（stdio 或 url 型）
- remove 删除 MCP 服务器
- enable/disable 切换启用状态

格式对齐官方：{ "mcpServers": { <name>: { type/command/args/env/enabled/url/headers } } }
注意：MCP 配置变更后主程序通常自动监听并重连；极个别情况（新增 stdio 服务器首次启动等）需重启 DriFox。
"""
import json
from pathlib import Path

from app.tools.result import ToolResult


def _plugin_roots():
    roots = []
    try:
        from app.plugins.loaders.plugin_tool_loader import _plugin_roots as _lr

        for p in _lr():
            roots.append(Path(p))
    except Exception:
        pass
    try:
        from app.utils.utils import get_app_data_dir

        roots.append(Path(get_app_data_dir()) / "plugins")
    except Exception:
        roots.append(Path.home() / ".drifox" / "plugins")
    seen, uniq = set(), []
    for p in roots:
        if p.is_dir() and str(p) not in seen:
            seen.add(str(p))
            uniq.append(p)
    return uniq


def _load_mcp_file(base: Path) -> tuple[Path, dict]:
    """读取插件 .mcp.json；不存在时返回空骨架"""
    f = base / ".mcp.json"
    if f.exists():
        cfg = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            cfg = {}
    else:
        cfg = {"mcpServers": {}}
    cfg.setdefault("mcpServers", {})
    return f, cfg


def _find_plugin(plugin_name: str) -> Path | None:
    for root in _plugin_roots():
        cand = root / plugin_name
        if cand.is_dir():
            return cand
    return None


def _server_brief(name: str, s: dict) -> str:
    typ = s.get("type", "?")
    enabled = s.get("enabled", True)
    endpoint = s.get("command", "") or s.get("url", "")
    flag = "✅" if enabled else "⛔"
    return f"  {flag} {name} [{typ}] {endpoint}"


def _list_servers(plugin_name: str) -> str:
    lines = []
    if plugin_name:
        base = _find_plugin(plugin_name)
        if base is None:
            return f"未找到插件 {plugin_name}"
        f, cfg = _load_mcp_file(base)
        if not f.exists():
            return f"插件 {plugin_name} 无 .mcp.json（可用 operation=add server_name=xx 添加）"
        lines.append(f"插件 {plugin_name} 的 MCP 服务器（{f}）：")
        servers = cfg.get("mcpServers", {})
        if not servers:
            lines.append("  （空）")
        for n, s in servers.items():
            lines.append(_server_brief(n, s))
        return "\n".join(lines)

    # 全部插件扫描
    lines.append("各插件 MCP 服务器配置总览：")
    for root in _plugin_roots():
        for d in sorted(root.iterdir()):
            f = d / ".mcp.json"
            if d.is_dir() and f.exists():
                try:
                    cfg = json.loads(f.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    lines.append(f"  ✗ {d.name}: .mcp.json JSON 损坏")
                    continue
                servers = cfg.get("mcpServers", {})
                if servers:
                    lines.append(f"  {d.name}:")
                    for n, s in servers.items():
                        lines.append(_server_brief(n, s))
    if len(lines) == 1:
        lines.append("  （所有插件均无 MCP 服务器配置）")
    return "\n".join(lines)


_AUTH_SCHEMES = ("bearer", "token", "basic", "bot", "apikey")


def _looks_like_secret(value: str) -> bool:
    """粗略判断一个值像不像凭据。

    先剥掉认证 scheme 前缀（`Bearer xxx` 是最常见写法，带空格不能直接排除），
    再按长度、典型前缀与字符熵判断；`${env.VAR}` 占位一律不算。
    """
    v = (value or "").strip()
    if not v or "${env." in v:
        return False
    parts = v.split(None, 1)
    if len(parts) == 2 and parts[0].lower() in _AUTH_SCHEMES:
        v = parts[1].strip()
    if len(v) < 20 or " " in v:
        return False
    if v.startswith(("sk-", "ghp_", "gho_", "github_pat_", "xoxb-", "xoxp-", "AKIA", "eyJ")):
        return True
    alnum = sum(c.isalnum() for c in v)
    return alnum / len(v) > 0.85


def _plaintext_secrets(server: dict) -> list:
    """列出被明文写进 .mcp.json 的凭据位置（字段.键名）。"""
    hits = []
    for field in ("env", "headers"):
        for k, v in (server.get(field) or {}).items():
            if isinstance(v, str) and _looks_like_secret(v):
                hits.append(f"{field}.{k}")
    return hits


def _add_server(plugin_name: str, server_name: str, kwargs: dict):
    base = _find_plugin(plugin_name)
    if base is None:
        return None, f"未找到插件 {plugin_name}（先创建插件再挂 MCP）"

    command = (kwargs.get("command") or "").strip()
    url = (kwargs.get("url") or "").strip()
    if not command and not url:
        return None, "必须提供 command（stdio 型）或 url（远程型）至少一个"

    server: dict = {"enabled": True}
    if command:
        server.update({
            "type": "stdio",
            "command": command,
            "args": kwargs.get("args") or [],
            "env": kwargs.get("env") or {},
            "url": "",
            "headers": {},
        })
    else:
        server.update({
            "type": "http",
            "command": "",
            "args": [],
            "env": {},
            "url": url,
            "headers": kwargs.get("headers") or {},
        })

    # credential 声明（推荐）：只声明要什么 Key 与注入方式，用户在设置页填，
    # Key 存 <app_data>/plugin_data/<插件>/config.json，不进 git。
    credential = kwargs.get("credential")
    if credential:
        if isinstance(credential, str):
            try:
                credential = json.loads(credential)
            except json.JSONDecodeError as e:
                return None, f"credential 不是合法 JSON：{e}"
        if not isinstance(credential, dict):
            return None, (
                'credential 需要是对象，如 {"label":"Token",'
                '"inject":{"type":"header","name":"Authorization","scheme":"Bearer"}}'
            )
        inject = credential.get("inject")
        if not isinstance(inject, dict) or inject.get("type") not in ("header", "query", "url"):
            return None, "credential.inject.type 必须是 header / query / url 之一（见 docs/mcp.md）"
        if inject["type"] in ("header", "query") and not inject.get("name"):
            return None, "credential.inject.type 为 header/query 时必须给 name"
        server["credential"] = credential

    f, cfg = _load_mcp_file(base)
    cfg["mcpServers"][server_name] = server
    f.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    # manifest components.mcp 若未启用则补上
    mf = base / ".drifox-plugin" / "plugin.json"
    if mf.exists():
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
            comps = m.setdefault("components", {})
            if not comps.get("mcp"):
                comps["mcp"] = True
                mf.write_text(json.dumps(m, ensure_ascii=False, indent=4), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass

    msg = f"已添加 MCP 服务器「{server_name}」到插件 {plugin_name} 的 {f.name}\n" \
          f"端点：{command or url}\n配置已写入；DriFox 会自动启动连接，如未生效再重启。"
    secrets = _plaintext_secrets(server)
    if secrets:
        msg += (
            "\n\n⚠️ 检测到明文凭据已写入 .mcp.json：" + "、".join(secrets) + "\n"
            "docs/mcp.md 要求「密钥不要写进 .mcp.json 提交到 git」。两种正确做法：\n"
            "  1. credential 声明（推荐）：只声明要什么 Key 与注入方式，用户在设置页填，"
            "Key 存 plugin_data/<插件>/config.json 不进 git：\n"
            '     evolution_mcp operation=add ... credential={"label":"Token",'
            '"inject":{"type":"header","name":"Authorization","scheme":"Bearer"}}\n'
            "  2. ${env.VAR} 占位（CI/脚本场景）：把值改成 ${env.YOUR_VAR}，连接时读进程环境变量。\n"
            "请改用其一，避免凭据随仓库泄露。"
        )
    if credential:
        msg += "\n\ncredential 已声明：设置 → MCP 连接器会为它渲染输入框，用户填完即生效。"
    return msg, None


def _remove_server(plugin_name: str, server_name: str):
    base = _find_plugin(plugin_name)
    if base is None:
        return None, f"未找到插件 {plugin_name}"
    f, cfg = _load_mcp_file(base)
    servers = cfg.get("mcpServers", {})
    if server_name not in servers:
        return None, f"插件 {plugin_name} 无名为「{server_name}」的 MCP 服务器；现有：{sorted(servers)}"
    del servers[server_name]
    f.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"已删除 MCP 服务器「{server_name}」（{f}）\n配置已写入；DriFox 会自动断开连接，如未生效再重启。", None


def _toggle_server(plugin_name: str, server_name: str, enabled: bool):
    base = _find_plugin(plugin_name)
    if base is None:
        return None, f"未找到插件 {plugin_name}"
    f, cfg = _load_mcp_file(base)
    s = cfg.get("mcpServers", {}).get(server_name)
    if s is None:
        return None, f"插件 {plugin_name} 无名为「{server_name}」的 MCP 服务器"
    s["enabled"] = enabled
    f.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    state = "启用" if enabled else "停用"
    return f"MCP 服务器「{server_name}」已{state}。\n配置已写入；DriFox 会自动应用（已实测 disable 热加载即时生效），如未生效再重启。", None


def _impl(tool_ctx, **kwargs):
    try:
        op = (kwargs.get("operation") or "list").strip()
        plugin_name = (kwargs.get("plugin_name") or "").strip()
        server_name = (kwargs.get("server_name") or "").strip()

        if op == "list":
            return ToolResult(True, content=_list_servers(plugin_name))

        if not plugin_name:
            return ToolResult(False, error=f"operation={op} 需要提供 plugin_name")

        if op == "add":
            if not server_name:
                return ToolResult(False, error="add 需要 server_name")
            msg, err = _add_server(plugin_name, server_name, kwargs)
            if err:
                return ToolResult(False, error=err)
            return ToolResult(True, content=msg)

        if op == "remove":
            if not server_name:
                return ToolResult(False, error="remove 需要 server_name")
            msg, err = _remove_server(plugin_name, server_name)
            if err:
                return ToolResult(False, error=err)
            return ToolResult(True, content=msg)

        if op in ("enable", "disable"):
            if not server_name:
                return ToolResult(False, error=f"{op} 需要 server_name")
            msg, err = _toggle_server(plugin_name, server_name, op == "enable")
            if err:
                return ToolResult(False, error=err)
            return ToolResult(True, content=msg)

        return ToolResult(False, error=f"未知 operation: {op!r}；可用 list/add/remove/enable/disable")
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"evolution_mcp 内部异常：{type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "evolution_mcp",
        "description": (
            "自进化：管理 MCP 服务器配置（读写插件 .mcp.json）。"
            "operation=list 列出配置；add/remove/enable/disable 增删启停。"
            "stdio 型用 command+args，远程型用 url+headers。"
            "凭据优先用 credential 声明（用户在设置页填，Key 不进 git），"
            "CI 场景用 ${env.VAR} 占位；明文写 env/headers 会被检测并告警。"
            "可自动补齐 manifest 的 components.mcp 标记。配置变更后 DriFox 自动监听重连；如未生效再重启。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "add", "remove", "enable", "disable"],
                    "description": "操作类型，默认 list",
                },
                "plugin_name": {
                    "type": "string",
                    "description": "目标插件名（add/remove/enable/disable 必填；list 可省略表全部）",
                },
                "server_name": {
                    "type": "string",
                    "description": "MCP 服务器名（add/remove/enable/disable 必填）",
                },
                "command": {
                    "type": "string",
                    "description": "stdio 型启动命令（如 npx/uvx/python）",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "stdio 型命令参数列表",
                },
                "env": {
                    "type": "object",
                    "description": "stdio 型环境变量。切勿写明文密钥，用 ${env.VAR} 占位或改用 credential",
                },
                "url": {
                    "type": "string",
                    "description": "远程型服务器 URL",
                },
                "headers": {
                    "type": "object",
                    "description": "远程型请求头。切勿写明文密钥，用 ${env.VAR} 占位或改用 credential",
                },
                "credential": {
                    "type": "object",
                    "description": (
                        "凭据声明（推荐）。只写要什么 Key 与注入方式，DriFox 在设置页渲染输入框，"
                        "Key 存 plugin_data/<插件>/config.json 不进 git。"
                        '示例：{"label":"Token","placeholder":"GitHub PAT",'
                        '"getUrl":"https://github.com/settings/tokens",'
                        '"inject":{"type":"header","name":"Authorization","scheme":"Bearer"}}'
                    ),
                },
            },
            "required": ["operation"],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "evolution_mcp", _SCHEMA, impl=_impl,
        danger="safe", icon="evolution_mcp", cn_name="管理 MCP 配置",
        group="自进化", description="读写插件 .mcp.json 管理 MCP 服务器（增删启停）",
        metadata={"permission_arg": "plugin_name"},
    )
