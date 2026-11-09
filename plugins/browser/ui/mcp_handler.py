# -*- coding: utf-8 -*-
"""browser 插件的进程内 MCP handler。

工具实现直接复用 control_server 的 _OP_HANDLERS（args -> dict），
不再经 HTTP 自调用，也不 import mcp SDK；宿主 LocalMcpGateway 负责讲
Streamable HTTP 的 JSON-RPC 帧，本模块只负责「工具名 + 参数 → 文本结果」。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from .control_server import _OP_HANDLERS


def _schema(props: Dict[str, Dict[str, Any]], required: List[str] | None = None) -> dict:
    schema = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


MCP_TOOLS: List[dict] = [
    {"name": "browser_status", "description": "查询浏览器控制服务器状态（是否可用、浏览器是否已打开）",
     "inputSchema": _schema({})},
    {"name": "browser_navigate", "description": "在插件浏览器中打开/导航到指定 URL（浏览器未开时自动打开）",
     "inputSchema": _schema({"url": {"type": "string", "description": "完整 URL"},
                              "wait": {"type": "boolean", "description": "等待页面加载完成，默认 True"}}, ["url"])},
    {"name": "browser_read", "description": "读取插件浏览器当前页面的内容（正文或完整 HTML）",
     "inputSchema": _schema({"mode": {"type": "string", "description": "text 或 html，默认 text"}})},
    {"name": "browser_execute_js", "description": "在当前页面执行任意 JavaScript（点击/输入/滚动/查询状态）",
     "inputSchema": _schema({"js": {"type": "string", "description": "要执行的 JS 代码"}}, ["js"])},
    {"name": "browser_click", "description": "点击页面中匹配 CSS 选择器的元素",
     "inputSchema": _schema({"selector": {"type": "string", "description": "CSS 选择器"},
                              "index": {"type": "integer", "description": "匹配元素序号，默认 0"}}, ["selector"])},
    {"name": "browser_type", "description": "在匹配 CSS 选择器的输入框中输入文本（模拟原生 input 事件）",
     "inputSchema": _schema({"selector": {"type": "string", "description": "CSS 选择器"},
                              "text": {"type": "string", "description": "要输入的文本"},
                              "index": {"type": "integer", "description": "匹配元素序号，默认 0"}},
                             ["selector", "text"])},
    {"name": "browser_scroll", "description": "滚动当前页面",
     "inputSchema": _schema({"direction": {"type": "string", "description": "down/up/top/bottom"},
                              "amount": {"type": "integer", "description": "像素数，down/up 时有效"}})},
    {"name": "browser_screenshot", "description": "截取插件浏览器当前页面截图（返回本地 PNG 路径）",
     "inputSchema": _schema({})},
    {"name": "browser_back", "description": "浏览器后退到上一页", "inputSchema": _schema({})},
    {"name": "browser_forward", "description": "浏览器前进到下一页", "inputSchema": _schema({})},
    {"name": "browser_reload", "description": "刷新当前页面", "inputSchema": _schema({})},
    {"name": "browser_tabs", "description": "列出插件浏览器的全部标签页", "inputSchema": _schema({})},
    {"name": "browser_switch_tab", "description": "切换到指定索引的标签页",
     "inputSchema": _schema({"index": {"type": "integer", "description": "标签索引（从 0 开始）"}}, ["index"])},
    {"name": "browser_new_tab", "description": "新建标签页（可带 URL）",
     "inputSchema": _schema({"url": {"type": "string", "description": "可选，新标签要打开的 URL"}})},
    {"name": "browser_close_tab", "description": "关闭指定索引的标签页",
     "inputSchema": _schema({"index": {"type": "integer", "description": "标签索引（从 0 开始）"}}, ["index"])},
]


def _call(op: str, args: dict) -> dict:
    handler = _OP_HANDLERS.get(op)
    if handler is None:
        return {"ok": False, "error": f"未知操作: {op}"}
    return handler(args or {})


def _js_result(data: dict, prefix: str) -> str:
    if not data.get("ok"):
        return f"失败: {data.get('error', 'unknown')}"
    result = data.get("result")
    if result is None:
        return f"{prefix}（无返回值）"
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False)
    return str(result)


def mcp_handle(req: dict) -> dict:
    """gateway 回调：params.name + params.arguments -> {'text': str}。"""
    params = req.get("params") or {}
    name = params.get("name", "")
    args = params.get("arguments") or {}
    try:
        if name == "browser_status":
            tabs = _call("tabs", {})
            text = (f"浏览器控制可用。插件浏览器{'已打开' if tabs.get('ok') else '未打开'}。"
                    "未打开时可先调用 browser_navigate（会自动打开）或 browser_new_tab。")
            return {"text": text}

        if name == "browser_navigate":
            data = _call("navigate", {"url": args.get("url", ""), "wait": args.get("wait", True)})
            text = (f"已打开: {data.get('url', args.get('url', ''))}（标题: {data.get('title', '')}）"
                    if data.get("ok") else f"打开失败: {data.get('error', 'unknown')}")
            return {"text": text}

        if name == "browser_read":
            data = _call("read", {"mode": args.get("mode", "text")})
            if not data.get("ok"):
                return {"text": f"读取失败: {data.get('error', 'unknown')}"}
            head = f"URL: {data.get('url', '')}\n标题: {data.get('title', '')}\n"
            return {"text": head + "\n" + (data.get("content", "") or "")[:200000]}

        if name == "browser_execute_js":
            return {"text": _js_result(_call("execute_js", {"js": args.get("js", "")}), "执行成功")}

        if name == "browser_click":
            js = ("(()=>{const els=document.querySelectorAll(%r);"
                  "if(!els.length)return 'NO_MATCH';"
                  "const el=els[%d];el.scrollIntoView({block:'center'});el.click();"
                  "return 'CLICKED:'+el.tagName;})();"
                  % (args.get("selector", ""), int(args.get("index", 0))))
            data = _call("execute_js", {"js": js})
            return {"text": (f"点击结果: {data.get('result', '')}" if data.get("ok")
                             else f"点击失败: {data.get('error', 'unknown')}")}

        if name == "browser_type":
            js = ("(()=>{const els=document.querySelectorAll(%r);"
                  "if(!els.length)return 'NO_MATCH';"
                  "const el=els[%d];el.focus();"
                  "const setter=Object.getOwnPropertyDescriptor("
                  "window.HTMLInputElement.prototype,'value')||"
                  "Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value');"
                  "if(setter&&setter.set)setter.set.call(el,%s);"
                  "el.dispatchEvent(new Event('input',{bubbles:true}));"
                  "el.dispatchEvent(new Event('change',{bubbles:true}));"
                  "return 'TYPED';})();"
                  % (args.get("selector", ""), int(args.get("index", 0)),
                     json.dumps(args.get("text", ""))))
            data = _call("execute_js", {"js": js})
            return {"text": (f"输入结果: {data.get('result', '')}" if data.get("ok")
                             else f"输入失败: {data.get('error', 'unknown')}")}

        if name == "browser_scroll":
            direction = args.get("direction", "down")
            amount = int(args.get("amount", 600))
            if direction == "top":
                js = "window.scrollTo(0,0);'TOP';"
            elif direction == "bottom":
                js = "window.scrollTo(0,document.body.scrollHeight);'BOTTOM';"
            elif direction == "up":
                js = f"window.scrollBy(0,-{amount});'UP';"
            else:
                js = f"window.scrollBy(0,{amount});'DOWN';"
            data = _call("execute_js", {"js": js})
            return {"text": (f"滚动: {data.get('result', '')}" if data.get("ok")
                             else f"滚动失败: {data.get('error', 'unknown')}")}

        if name == "browser_screenshot":
            data = _call("screenshot", {})
            return {"text": data["path"] if data.get("ok") else f"截图失败: {data.get('error', 'unknown')}"}

        if name == "browser_back":
            data = _call("back", {})
            return {"text": f"后退: {data.get('url', '')}" if data.get("ok") else f"失败: {data.get('error')}"}

        if name == "browser_forward":
            data = _call("forward", {})
            return {"text": f"前进: {data.get('url', '')}" if data.get("ok") else f"失败: {data.get('error')}"}

        if name == "browser_reload":
            data = _call("reload", {})
            return {"text": "已刷新" if data.get("ok") else f"失败: {data.get('error')}"}

        if name == "browser_tabs":
            data = _call("tabs", {})
            if not data.get("ok"):
                return {"text": f"失败: {data.get('error')}"}
            lines = [f"{'▶' if t.get('active') else ' '} [{t.get('index')}] "
                     f"{t.get('title', '')} — {t.get('url', '')}" for t in data.get("tabs", [])]
            return {"text": "\n".join(lines) or "无标签"}

        if name == "browser_switch_tab":
            data = _call("switch_tab", {"index": int(args.get("index", 0))})
            return {"text": f"已切换到标签 {args.get('index', 0)}" if data.get("ok")
                    else f"失败: {data.get('error')}"}

        if name == "browser_new_tab":
            data = _call("new_tab", {"url": args.get("url", "")})
            return {"text": f"已新建标签 [{data.get('index')}]" if data.get("ok")
                    else f"失败: {data.get('error')}"}

        if name == "browser_close_tab":
            data = _call("close_tab", {"index": int(args.get("index", 0))})
            return {"text": f"已关闭标签 {args.get('index', 0)}" if data.get("ok")
                    else f"失败: {data.get('error')}"}

        return {"text": f"未知工具: {name}", "isError": True}
    except Exception as e:
        return {"text": f"调用失败: {e}", "isError": True}
