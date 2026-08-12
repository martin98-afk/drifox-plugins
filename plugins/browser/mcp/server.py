# -*- coding: utf-8 -*-
"""浏览器控制 MCP 服务器 — 让 AI 通过工具控制 DriFox 内置浏览器

工作流：
    AI → mcp__browser__* 工具 → 本服务器(stdio) → HTTP → 插件控制端点(主进程) → QWebEngineView

启动：
    python mcp/server.py [--timeout 20]
    由插件 .mcp.json 声明（command=python, args=[${CLAUDE_PLUGIN_ROOT}/mcp/server.py]）。

自引导：
    - 若当前解释器无 mcp 包（如系统 python），从 bridge.json 读取主程序
      venv python 并 os.execv 重启自己（bridge.json 由插件主进程启动时写入）。
    - bridge.json 不存在或端口未就绪时轮询等待（插件加载有先后时序）。

工具集：
    browser_status     服务器/浏览器状态
    browser_open       （别名 navigate）打开 URL（若浏览器未开则自动打开并导航）
    browser_navigate   当前标签导航到 URL
    browser_read       读取当前页正文（text）或 HTML（html）
    browser_execute_js 执行任意 JS（DOM 操作：点击/输入/滚动/查询）
    browser_screenshot 截取当前页（保存本地 PNG 并返回文件路径）
    browser_back / browser_forward / browser_reload
    browser_tabs / browser_switch_tab / browser_new_tab / browser_close_tab
"""

import json
import os
import sys
import time
from pathlib import Path

# ── 自引导：确保 mcp 包可用 ─────────────────────────────
def _can_import_mcp(python: str) -> bool:
    """验证解释器能 import mcp（subprocess 测试，避免 execv 到错误解释器）"""
    import subprocess

    kwargs = {}
    if os.name == "nt":
        flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if flag:
            kwargs["creationflags"] = flag
    try:
        r = subprocess.run(
            [python, "-c", "import mcp, httpx"],
            capture_output=True,
            timeout=10,
            **kwargs,
        )
        return r.returncode == 0
    except Exception:
        return False


def _bootstrap():
    try:
        import mcp  # noqa: F401
        return
    except ImportError:
        pass

    candidates = []
    # 1. bridge.json 中主程序探测到的可用 python（需再次验证）
    try:
        bridge = Path(__file__).resolve().parent / "bridge.json"
        if bridge.exists():
            py = json.loads(bridge.read_text(encoding="utf-8")).get("python_executable")
            if py:
                candidates.append(py)
    except Exception:
        pass
    # 2. 常见 venv / PATH python
    for p in (
        Path(sys.executable).parent.parent / ".venv" / "Scripts" / "python.exe",
        Path(r"D:\work\DriFox\.venv\Scripts\python.exe"),
        Path.home() / "work" / "DriFox" / ".venv" / "Scripts" / "python.exe",
    ):
        if p.exists():
            candidates.append(str(p))
    import shutil

    for name in ("python", "python3", "py"):
        p = shutil.which(name)
        if p:
            candidates.append(p)

    for py in candidates:
        try:
            if os.path.realpath(py) == os.path.realpath(sys.executable):
                continue
        except Exception:
            pass
        if _can_import_mcp(py):
            os.execv(py, [py] + sys.argv)
    sys.stderr.write(
        "[browser-mcp] 未找到能 import mcp 的 python 解释器。\n"
        "请确保系统 Python 可用并安装: pip install mcp httpx\n"
    )
    sys.exit(1)


_bootstrap()

import httpx  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("drifox-browser")

_BRIDGE_PATH = Path(__file__).resolve().parent / "bridge.json"
_HTTP_TIMEOUT = 20.0


def _bridge() -> dict:
    return json.loads(_BRIDGE_PATH.read_text(encoding="utf-8"))


def _api(op: str, payload: dict = None, timeout: float = None) -> dict:
    """调用主进程控制端点"""
    bridge = _bridge()
    base = f"http://127.0.0.1:{bridge['port']}"
    body = {"token": bridge["token"]}
    if payload:
        body.update(payload)
    resp = httpx.post(f"{base}/api/{op}", json=body, timeout=timeout or _HTTP_TIMEOUT)
    return resp.json()


def _wait_bridge(timeout: float = 30.0) -> bool:
    """等待插件主进程写好 bridge.json 并可用"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _BRIDGE_PATH.exists():
            try:
                st = httpx.get(
                    f"http://127.0.0.1:{_bridge()['port']}/healthz", timeout=2
                )
                if st.status_code == 200:
                    return True
            except Exception:
                pass
        time.sleep(1)
    return False


# ── 工具实现 ────────────────────────────────────────────


@mcp.tool()
def browser_status() -> str:
    """查询浏览器控制服务器状态（是否可用、浏览器是否已打开）"""
    try:
        data = _api("status")
        if not data.get("ok"):
            return f"控制端点异常: {data.get('error', 'unknown')}"
        browser_ok = data.get("browser", False)
        return (
            f"浏览器控制可用。插件浏览器{'已打开' if browser_ok else '未打开'}。"
            "未打开时可先调用 browser_navigate（会自动打开）或 browser_new_tab。"
        )
    except Exception as e:
        return f"控制端点不可达: {e}（插件可能未加载，稍后重试）"


@mcp.tool()
def browser_navigate(url: str, wait: bool = True) -> str:
    """在插件浏览器中打开/导航到指定 URL（浏览器未开时自动打开）。

    Args:
        url: 完整 URL（如 https://example.com）
        wait: 是否等待页面加载完成（默认 True）
    """
    try:
        data = _api("navigate", {"url": url, "wait": wait})
        if data.get("ok"):
            return f"已打开: {data.get('url', url)}（标题: {data.get('title', '')}）"
        return f"打开失败: {data.get('error', 'unknown')}"
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_read(mode: str = "text") -> str:
    """读取插件浏览器当前页面的内容。

    Args:
        mode: "text"（正文纯文本，默认）或 "html"（完整 HTML）
    """
    try:
        data = _api("read", {"mode": mode})
        if not data.get("ok"):
            return f"读取失败: {data.get('error', 'unknown')}"
        head = f"URL: {data.get('url', '')}\n标题: {data.get('title', '')}\n"
        content = data.get("content", "") or ""
        return head + "\n" + content[:200000]
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_execute_js(js: str) -> str:
    """在插件浏览器当前页面执行任意 JavaScript（点击/输入/滚动/查询状态）。

    Args:
        js: JavaScript 代码（返回 JSON 可序列化值，如 'document.title'、
            "document.querySelector('a').click()" 等）
    """
    try:
        data = _api("execute_js", {"js": js})
        if not data.get("ok"):
            return f"执行失败: {data.get('error', 'unknown')}"
        result = data.get("result")
        if result is None:
            return "执行成功（无返回值）"
        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False)
        return str(result)
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_click(selector: str, index: int = 0) -> str:
    """点击页面中匹配 CSS 选择器的元素（第 index 个匹配）。

    Args:
        selector: CSS 选择器，如 'a[href*="github"]'、'#submit'、'.btn'
        index: 匹配元素序号（默认 0 第一个）
    """
    js = (
        "(()=>{const els=document.querySelectorAll(%r);"
        "if(!els.length)return 'NO_MATCH';"
        "const el=els[%d];"
        "el.scrollIntoView({block:'center'});el.click();"
        "return 'CLICKED:'+el.tagName;})();" % (selector, index)
    )
    try:
        data = _api("execute_js", {"js": js})
        if not data.get("ok"):
            return f"点击失败: {data.get('error', 'unknown')}"
        return f"点击结果: {data.get('result', '')}"
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_type(selector: str, text: str, index: int = 0) -> str:
    """在匹配 CSS 选择器的输入框中输入文本（模拟原生 input 事件）。

    Args:
        selector: CSS 选择器（input/textarea 等）
        text: 要输入的文本
        index: 匹配元素序号（默认 0）
    """
    import json as _json

    js = (
        "(()=>{const els=document.querySelectorAll(%r);"
        "if(!els.length)return 'NO_MATCH';"
        "const el=els[%d];el.focus();"
        "const setter=Object.getOwnPropertyDescriptor("
        "window.HTMLInputElement.prototype,'value')||"
        "Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value');"
        "if(setter&&setter.set)setter.set.call(el,%s);"
        "el.dispatchEvent(new Event('input',{bubbles:true}));"
        "el.dispatchEvent(new Event('change',{bubbles:true}));"
        "return 'TYPED';})();" % (selector, index, _json.dumps(text))
    )
    try:
        data = _api("execute_js", {"js": js})
        if not data.get("ok"):
            return f"输入失败: {data.get('error', 'unknown')}"
        return f"输入结果: {data.get('result', '')}"
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_scroll(direction: str = "down", amount: int = 600) -> str:
    """滚动当前页面。

    Args:
        direction: "down"/"up"/"top"/"bottom"
        amount: 像素数（down/up 时有效）
    """
    if direction == "top":
        js = "window.scrollTo(0,0);'TOP';"
    elif direction == "bottom":
        js = "window.scrollTo(0,document.body.scrollHeight);'BOTTOM';"
    elif direction == "up":
        js = f"window.scrollBy(0,-{amount});'UP';"
    else:
        js = f"window.scrollBy(0,{amount});'DOWN';"
    try:
        data = _api("execute_js", {"js": js})
        if not data.get("ok"):
            return f"滚动失败: {data.get('error', 'unknown')}"
        return f"滚动: {data.get('result', '')}"
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_screenshot() -> str:
    """截取插件浏览器当前页面截图（保存本地 PNG 并返回文件路径）"""
    try:
        data = _api("screenshot")
        if not data.get("ok"):
            return f"截图失败: {data.get('error', 'unknown')}"
        return data["path"]
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_back() -> str:
    """浏览器后退到上一页"""
    try:
        data = _api("back")
        return f"后退: {data.get('url', '')}" if data.get("ok") else f"失败: {data.get('error')}"
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_forward() -> str:
    """浏览器前进到下一页"""
    try:
        data = _api("forward")
        return f"前进: {data.get('url', '')}" if data.get("ok") else f"失败: {data.get('error')}"
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_reload() -> str:
    """刷新当前页面"""
    try:
        data = _api("reload")
        return "已刷新" if data.get("ok") else f"失败: {data.get('error')}"
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_tabs() -> str:
    """列出插件浏览器的全部标签页"""
    try:
        data = _api("tabs")
        if not data.get("ok"):
            return f"失败: {data.get('error')}"
        lines = []
        for t in data.get("tabs", []):
            marker = "▶" if t.get("active") else " "
            lines.append(f"{marker} [{t.get('index')}] {t.get('title', '')} — {t.get('url', '')}")
        return "\n".join(lines) or "无标签"
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_switch_tab(index: int) -> str:
    """切换到指定索引的标签页。

    Args:
        index: 标签索引（从 0 开始，见 browser_tabs）
    """
    try:
        data = _api("switch_tab", {"index": index})
        return f"已切换到标签 {index}" if data.get("ok") else f"失败: {data.get('error')}"
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_new_tab(url: str = "") -> str:
    """新建标签页（可带 URL）。

    Args:
        url: 可选，新标签要打开的 URL
    """
    try:
        data = _api("new_tab", {"url": url})
        return f"已新建标签 [{data.get('index')}]" if data.get("ok") else f"失败: {data.get('error')}"
    except Exception as e:
        return f"调用失败: {e}"


@mcp.tool()
def browser_close_tab(index: int) -> str:
    """关闭指定索引的标签页。

    Args:
        index: 标签索引（从 0 开始）
    """
    try:
        data = _api("close_tab", {"index": index})
        return f"已关闭标签 {index}" if data.get("ok") else f"失败: {data.get('error')}"
    except Exception as e:
        return f"调用失败: {e}"


# ── 启动 ────────────────────────────────────────────────

if __name__ == "__main__":
    if not _wait_bridge():
        sys.stderr.write("[browser-mcp] 等待插件控制端点超时，仍启动（工具调用会报错）\n")
    mcp.run()
