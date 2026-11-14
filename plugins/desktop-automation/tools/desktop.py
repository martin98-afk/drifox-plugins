# -*- coding: utf-8 -*-
"""
desktop-automation 插件 — 桌面自动化工具（自包含实现）

从 DriFox 主程序 `plugins/system/tools/automation_tools.py` 迁出。
mouse / keyboard / screenshot 三个工具完全自包含：pynput + mss 直接实现，
不依赖主程序 services。运行环境从 tool_ctx 获取（app_data_dir 截图目录、
desktop_automation 开关）。

迁出差异（vs 主程序 system 版）：
- 移除 `from app.widgets.render_helpers import _extract_screenshot_image_path`
  与 `escape`（主程序 internal API），改为 `from html import escape` +
  `_extract_screenshot_image_path` 内联实现（字符串兜底分支保留）。
- screenshot 注册时保留 `metadata={"provides_image": True}`（视觉注入声明）。
"""
import ast
import atexit
import base64
import json
import os
import subprocess
import sys
import re
import threading
import time
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Optional

# ── 插件自包含依赖注入：优先加载本插件 deps/ 目录 ────────────────
# 主程序打包时已排除 pynput/mss，运行时依赖本插件自带 deps/
_plugin_deps = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deps"))
if _plugin_deps not in sys.path:
    sys.path.insert(0, _plugin_deps)

from loguru import logger
from pynput import keyboard as _pynput_kb
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController
import mss
import mss.tools

from app.tools.registry import make_summarize_from_preview
from app.tools.result import ToolResult

GROUP_DESKTOP = "桌面控制"

_MOUSE_ACTIONS = {"move", "click", "double_click", "right_click", "scroll", "drag", "position"}
_MOUSE_ACTIONS_NO_COORD = frozenset({"position"})
_MOUSE_BUTTONS = {"left": Button.left, "right": Button.right, "middle": Button.middle}


def _app_data_dir(tool_ctx) -> Path:
    """截图默认目录（<app_data>/.drifox/screenshots）"""
    app_data = tool_ctx.get("env", {}).get("app_data_dir")
    if app_data:
        return Path(app_data) / ".drifox" / "screenshots"
    return Path.home() / ".drifox" / "screenshots"


def _automation_enabled(tool_ctx) -> bool:
    """桌面自动化开关：配置缺失时默认启用（设置 → 桌面自动化）"""
    return tool_ctx.get("env", {}).get("desktop_automation_enabled", True)


def _check_enabled(tool_ctx) -> Optional[ToolResult]:
    if not _automation_enabled(tool_ctx):
        return ToolResult(False, error="桌面自动化未开启（设置 → 桌面自动化）")
    return None


def _extract_screenshot_image_path(result: str) -> str:
    """从 screenshot 工具结果字符串中提取截图文件绝对路径

    自包含实现（从主程序 render_helpers._extract_screenshot_image_path 迁出）。
    result 格式类似 Python dict str():
        {'path': 'D:/...png', 'absolute_path': 'D:/...png', ...}

    impl 已直接返回 dict 走快路径；此函数仅作字符串兜底（与其他工具结果
    字符串化兼容）。
    """
    if not result:
        return ""
    # 策略1: ast.literal_eval 解析 Python dict 字面量
    try:
        data = ast.literal_eval(result)
        if isinstance(data, dict):
            path = data.get("absolute_path") or data.get("path") or ""
            if path and os.path.isfile(path):
                return path
    except (ValueError, SyntaxError, MemoryError):
        pass
    # 策略2: 正则提取 'absolute_path': '...' 或 'path': '...'
    for key in ("absolute_path", "path"):
        m = re.search(r"""['"]""" + key + r"""['"]\s*:\s*['"]([^'"]+\.png)['"]""", result)
        if m:
            path = m.group(1)
            if os.path.isfile(path):
                return path
    # 策略3: 直接匹配 .png 的绝对路径
    m = re.search(r"""['"]([A-Za-z]:[^'"]+\.png)['"]""", result)
    if m:
        path = m.group(1)
        if os.path.isfile(path):
            return path
    return ""


# ========== UIA 桥（无障碍元素树） ==========
#
# 设计取舍（实测后定下的）：
# - 不用 pywinauto / uiautomation：两者都依赖 comtypes，Python 3.14 上兼容性未知，
#   而插件本身是自包含分发的，不愿再背一个带 C 扩展的依赖。
# - 改走 PowerShell + 系统自带 .NET UIAutomationClient：零新依赖，
#   代价是每次调用起一个进程（约 1~1.5s，展开树时更久）。
# - 元素引用不把 RuntimeId 暴露给模型（太长易抄错），而是缓存在进程内，
#   模型只用序号 element，由本模块换回 rid。

_UIA_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts", "uia.ps1")
)
_UIA_ISSUE = ""
if sys.platform != "win32":
    _UIA_ISSUE = "元素树仅支持 Windows（当前平台无 UIA）"
elif not os.path.isfile(_UIA_SCRIPT):
    _UIA_ISSUE = f"缺少 UIA 脚本：{_UIA_SCRIPT}"

# 快照缓存：snapshot_id -> payload。只保留最近若干个，避免长会话堆积。
_SNAPSHOTS: dict = {}
_SNAPSHOT_ORDER: list = []
_SNAPSHOT_KEEP = 8
_SNAPSHOT_LOCK = threading.Lock()


class _UiaServer:
    """常驻 UIA 桥客户端。

    每次起 PowerShell 进程约 500ms（加载程序集 + 初始化 UIA），对多步任务是纯浪费。
    这里维持一个长期存活的服务进程，用行协议收发；崩了就标记失效让调用方退回单次模式。
    """

    def __init__(self, script: str):
        self._script = script
        self._proc = None
        self._lock = threading.Lock()
        self._seq = 0
        self._dead = False

    def _spawn(self) -> None:
        self._proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", self._script, "-Server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=1, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _kill(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass

    def call(self, op: str, timeout: int, payload: dict):
        """成功返回响应 dict；返回 None 表示常驻不可用，调用方应退回单次模式。"""
        with self._lock:
            if self._dead:
                return None
            try:
                if self._proc is None or self._proc.poll() is not None:
                    self._spawn()
                self._seq += 1
                req = {"id": self._seq, "op": op, "args": payload}
                self._proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()
            except Exception:
                self._dead = True
                self._kill()
                return None

            box = {}

            def _reader():
                try:
                    box["line"] = self._proc.stdout.readline()
                except Exception:
                    box["line"] = ""

            th = threading.Thread(target=_reader, daemon=True)
            th.start()
            th.join(timeout)
            if th.is_alive():
                # 目标应用卡住会连累常驻进程，直接杀掉，下次重建
                self._kill()
                return {"ok": False, "error": f"UIA 桥超时（>{timeout}s），目标应用可能无响应"}

            line = (box.get("line") or "").strip()
            if not line:
                # 进程异常退出
                self._dead = True
                self._kill()
                return None
            try:
                return json.loads(line)
            except Exception:
                self._dead = True
                self._kill()
                return None

    def close(self) -> None:
        with self._lock:
            self._kill()


_SERVER = None
_SERVER_LOCK = threading.Lock()


def _uia_call_once(op: str, timeout: int = 20, **kwargs) -> dict:
    """单次模式：起一个进程跑完就退。常驻不可用时的兜底。"""
    payload = {k: v for k, v in kwargs.items() if v is not None}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    b64 = base64.b64encode(raw).decode("ascii")
    cmd = [
        "powershell", "-NoProfile", "-NonInteractive",
        "-ExecutionPolicy", "Bypass", "-File", _UIA_SCRIPT,
        "-Op", op, "-ArgsB64", b64,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"UIA 桥超时（>{timeout}s），目标应用可能无响应"}
    except Exception as e:
        return {"ok": False, "error": f"UIA 桥启动失败：{e}"}

    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if not out:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        return {"ok": False, "error": f"UIA 桥无输出（exit={proc.returncode}）：{err[:400]}"}
    # PowerShell 可能先打警告行，取最后一个 JSON 行
    line = out.splitlines()[-1]
    try:
        return json.loads(line)
    except Exception:
        return {"ok": False, "error": f"UIA 桥返回无法解析：{out[:400]}"}


def _uia_call(op: str, timeout: int = 20, **kwargs) -> dict:
    """调 UIA 桥。优先常驻进程，不可用时退回单次进程。"""
    global _SERVER
    if _UIA_ISSUE:
        return {"ok": False, "error": _UIA_ISSUE}
    payload = {k: v for k, v in kwargs.items() if v is not None}
    with _SERVER_LOCK:
        if _SERVER is None:
            _SERVER = _UiaServer(_UIA_SCRIPT)
        server = _SERVER
    res = server.call(op, timeout, payload)
    if res is not None:
        # 目标应用重绘时 UIA 会偶发「无法识别的错误」，重试一次通常就过
        err = str(res.get("error") or "")
        if not res.get("ok") and ("无法识别" in err or "unrecognized" in err.lower()):
            res2 = server.call(op, timeout, payload)
            if res2 is not None:
                return res2
        return res
    return _uia_call_once(op, timeout, **kwargs)


def _shutdown_server() -> None:
    with _SERVER_LOCK:
        if _SERVER is not None:
            _SERVER.close()


atexit.register(_shutdown_server)


_DPI_SCALE = None


def _dpi_scale() -> float:
    """物理像素 → 光标坐标的换算系数。

    UIA 桥自身声明了 per-monitor DPI 感知，返回的矩形是物理像素；
    而本进程（PyQt 未初始化时）可能是 DPI 不感知的，鼠标 API 收到的是
    逻辑坐标。两者相差系统缩放倍率（如 225% 时为 2.25）。
    换算只在有元素矩形时使用；用户直接给的 x/y 保持原语义不做换算。
    """
    global _DPI_SCALE
    if _DPI_SCALE is not None:
        return _DPI_SCALE
    _DPI_SCALE = 1.0
    try:
        res = _uia_call("screen", timeout=10)
        phys = (res.get("data") or {}).get("width")
        if phys:
            import ctypes
            logical = ctypes.windll.user32.GetSystemMetrics(0)
            if logical and logical > 0:
                ratio = float(phys) / float(logical)
                if 0.5 <= ratio <= 8.0:
                    _DPI_SCALE = ratio
    except Exception:
        pass
    return _DPI_SCALE


def _to_cursor(x: float, y: float) -> tuple:
    """把元素矩形的物理坐标换算成本进程可用的光标坐标。"""
    s = _dpi_scale()
    if s == 1.0:
        return int(round(x)), int(round(y))
    return int(round(x / s)), int(round(y / s))


def _locate_by_name(app: str, name: str, pid=None):
    """按「窗口 + 元素名」直接定位，省掉模型先拿整棵树再引序号的两步流程。

    窗口优先用 pid：标题会随文档名/会话名变，pid 不会。
    返回 (element, snapshot, error)。多个同名元素时返回错误并附候选，避免误点。
    """
    res = _uia_call("snapshot", app=app or None, pid=pid, find=name, max_elements=12, timeout=25)
    if not res.get("ok"):
        return None, None, res.get("error", "定位失败")
    data = res.get("data") or {}
    els = data.get("elements") or []
    if not els:
        return None, None, f'窗口 "{app}" 中没有名字包含 "{name}" 的可交互元素'
    if len(els) > 1:
        lines = []
        for e in els[:6]:
            r = e.get("rect") or [0, 0, 0, 0]
            lines.append(f'  {e.get("role")} "{e.get("name")}" @({r[0]},{r[1]})')
        return None, None, (
            f'匹配到 {len(els)} 个元素，改用 ui_tree 看清位置后指定 element：\n' + "\n".join(lines)
        )
    e = els[0]
    win = data.get("window") or {}
    snap = {"window": win, "elements": [{
        "i": 0,
        "rid": e.get("rid") or "",
        "name": e.get("name") or "",
        "role": e.get("role") or "",
        "cls": e.get("cls") or "",
        "rect": e.get("rect") or [],
        "value": e.get("value") or "",
    }], "ts": time.time()}
    return snap["elements"][0], snap, ""


def _remember_snapshot(sid: str, payload: dict) -> None:
    with _SNAPSHOT_LOCK:
        _SNAPSHOTS[sid] = payload
        _SNAPSHOT_ORDER.append(sid)
        while len(_SNAPSHOT_ORDER) > _SNAPSHOT_KEEP:
            old = _SNAPSHOT_ORDER.pop(0)
            _SNAPSHOTS.pop(old, None)


def _resolve_element(snapshot_id: str, element: int):
    """把模型给的 (snapshot_id, element 序号) 换成快照里的元素 dict。

    返回 (element, snapshot, error)，error 非空表示失败。
    """
    with _SNAPSHOT_LOCK:
        snap = _SNAPSHOTS.get(snapshot_id)
        if not snap:
            recent = _SNAPSHOT_ORDER[-1] if _SNAPSHOT_ORDER else ""
            hint = f"，最近的快照 id 是 {recent}" if recent else "，请先调用 ui_tree 取元素树"
            return None, None, f"快照已失效（{snapshot_id or '未提供'}）{hint}"
        els = snap.get("elements") or []
    if not isinstance(element, int) or element < 0 or element >= len(els):
        return None, None, f"元素序号 {element} 超出范围（0~{len(els) - 1}）"
    return els[element], snap, ""


_UI_TREE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ui_tree",
        "description": (
            "列出可交互桌面窗口，或读取某个窗口的无障碍元素树（按钮/输入框/列表项等，带序号和坐标）。"
            "不传 app 时只列窗口；传 app（窗口标题/进程名片段）或 pid 时返回该窗口的元素清单。"
            "拿到元素序号后，用 mouse(element=序号) 或 keyboard(element=序号) 直接操作，比按坐标点击稳。"
            "界面变化后旧序号会失效，重新调用本工具即可。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "窗口标题或进程名片段，如 '记事本'、'vscode'；留空=只列窗口"},
                "pid": {"type": "integer", "description": "按进程 ID 精确指定窗口（比 app 更稳）"},
                "max_elements": {"type": "integer", "description": "最多返回多少个元素（默认 60，上限 300）"},
                "include_offscreen": {"type": "boolean", "description": "是否包含不可见元素（默认 false）"},
            },
            "required": [],
        },
    },
}


def _ui_tree_impl(tool_ctx, **kwargs):
    err = _check_enabled(tool_ctx)
    if err:
        return err
    if _UIA_ISSUE:
        return ToolResult(False, error=_UIA_ISSUE)

    app = (kwargs.get("app") or "").strip()
    pid = kwargs.get("pid")
    max_elements = int(kwargs.get("max_elements") or 60)
    max_elements = max(1, min(max_elements, 300))
    include_offscreen = bool(kwargs.get("include_offscreen") or False)

    # 没有窗口线索：只列窗口清单
    if not app and not pid:
        res = _uia_call("list")
        if not res.get("ok"):
            return ToolResult(False, error=res.get("error", "枚举窗口失败"))
        wins = (res.get("data") or {}).get("windows") or []
        if not wins:
            return ToolResult(True, content={"windows": [], "hint": "没有可见窗口"})
        lines = []
        for w in wins:
            proc = w.get("process") or ""
            lines.append(
                f'[{w.get("pid")}] {w.get("title") or "(无标题)"}'
                f'  ({proc}, {w.get("cls") or "?"})'
            )
        return ToolResult(True, content={
            "windows": wins,
            "summary": "\n".join(lines),
            "hint": "用 ui_tree(app=窗口标题片段) 或 ui_tree(pid=...) 读取某个窗口的元素树",
        })

    res = _uia_call(
        "snapshot", pid=pid, app=app or None,
        max_elements=max_elements, include_offscreen=include_offscreen,
    )
    if not res.get("ok"):
        return ToolResult(False, error=res.get("error", "读取元素树失败"))
    data = res.get("data") or {}
    sid = data.get("snapshot_id") or ""
    win = data.get("window") or {}
    elements = data.get("elements") or []

    # 缓存（rid 不外露，只留序号）
    slim = []
    for e in elements:
        slim.append({
            "i": e.get("i"),
            "rid": e.get("rid") or "",
            "name": e.get("name") or "",
            "role": e.get("role") or "",
            "cls": e.get("cls") or "",
            "rect": e.get("rect") or [],
            "value": e.get("value") or "",
        })
    _remember_snapshot(sid, {"window": win, "elements": slim, "ts": time.time()})

    # 给模型看的视图：去掉 rid，长名字截断
    view = []
    for e in slim:
        name = e["name"]
        if len(name) > 60:
            name = name[:57] + "..."
        item = {
            "i": e["i"],
            "role": e["role"],
            "name": name,
            "rect": e["rect"],
        }
        if e["cls"]:
            # ClassName 是跨框架识别控件类型的唯一稳定线索
            # （WinForms 把按钮和输入框都报成 Pane；Qt 常常不给 name）
            item["cls"] = e["cls"][:48]
        if e["value"]:
            item["value"] = e["value"][:80]
        view.append(item)

    notes = []
    if data.get("activated"):
        notes.append("首次访问该应用，无障碍树已激活并重新读取")
    if data.get("truncated"):
        notes.append(f"元素超过 {max_elements} 个已截断，可提高 max_elements")

    return ToolResult(True, content={
        "snapshot_id": sid,
        "window": {
            "title": win.get("title"),
            "pid": win.get("pid"),
            "rect": win.get("rect"),
            "process": win.get("process") or win.get("cls"),
        },
        "elements": view,
        "total_raw": data.get("total_raw"),
        "notes": notes,
        "hint": (
            f"操作元素：mouse(action=\"click\", snapshot_id=\"{sid}\", element=序号)；"
            f"写值：keyboard(action=\"set_value\", snapshot_id=\"{sid}\", element=序号, text=...)"
        ),
    })


def _preview_ui_tree(tool_args: dict) -> str:
    app = tool_args.get("app") or ""
    pid = tool_args.get("pid")
    if app:
        return f'读取窗口元素树 "{app}"'
    if pid:
        return f"读取窗口元素树 pid={pid}"
    return "列出桌面窗口"


# ========== screenshot ==========

_SCREENSHOT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "screenshot",
        "description": "截屏并保存PNG。支持全屏或区域截图。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "输出PNG路径(可选，空则自动生成到.drifox/screenshots/)"},
                "region": {
                    "type": "array",
                    "description": "区域(left,top,width,height)如[100,200,800,600]；空=全屏",
                    "items": {"type": "integer"},
                    "minItems": 4,
                    "maxItems": 4,
                },
            },
        },
    },
}


def _screenshot_impl(tool_ctx, **kwargs):
    err = _check_enabled(tool_ctx)
    if err:
        return err
    path = kwargs.get("path") or ""
    region = kwargs.get("region") or None
    try:
        with mss.mss() as sct:
            if region is not None:
                if len(region) != 4:
                    return ToolResult(False, error="region must be (left, top, width, height)")
                left, top, width, height = region
                monitor = {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}
            else:
                monitor = sct.monitors[1]  # 主显示器
            raw = sct.grab(monitor)
            if path:
                out_path = Path(path).expanduser()
                if not out_path.is_absolute():
                    out_path = Path.cwd() / out_path
                out_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                save_dir = _app_data_dir(tool_ctx)
                save_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_path = save_dir / f"desktop_{stamp}.png"
            mss.tools.to_png(raw.rgb, raw.size, output=str(out_path))
            size_bytes = out_path.stat().st_size
            width, height = raw.size
            return ToolResult(
                True,
                content={
                    "path": str(out_path),
                    "absolute_path": str(out_path.resolve()),
                    "width": width,
                    "height": height,
                    "size_bytes": size_bytes,
                    "markdown": f"![截图]({out_path.as_posix()})",
                },
            )
    except Exception as e:
        return ToolResult(False, error=f"Screenshot error: {str(e)}")


# ========== mouse ==========

_MOUSE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "mouse",
        "description": "桌面鼠标操作。支持移动/单击/双击/右键/滚动/拖拽/查位置。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["move", "click", "double_click", "right_click", "scroll", "drag", "position"],
                    "description": "move=移动,click=单击,double_click=双击,right_click=右键,scroll=滚动,drag=拖到(x,y),position=查坐标+屏幕尺寸",
                },
                "x": {"type": "integer", "description": "目标屏幕 X 坐标（像素）"},
                "y": {"type": "integer", "description": "目标屏幕 Y 坐标（像素）"},
                "element": {
                    "type": "integer",
                    "description": "ui_tree 返回的元素序号，优先于 x/y。能走无障碍动作时不移动光标；不支持时自动退回坐标点击",
                },
                "snapshot_id": {"type": "string", "description": "ui_tree 返回的快照 id，与 element 配套使用"},
                "app": {"type": "string", "description": "窗口标题或进程名片段。与 name 一起用可跳过 ui_tree，一步定位并操作"},
                "pid": {"type": "integer", "description": "目标窗口进程 ID（比 app 稳，窗口标题会变）"},
                "name": {"type": "string", "description": "元素名字（精确优先，模糊次之）。同名多个时会报错并列出候选"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "鼠标按钮(默认left)"},
                "clicks": {"type": "integer", "description": "点击次数(默认1),double_click固定2次"},
                "dx": {"type": "integer", "description": "scroll水平滚动"},
                "dy": {"type": "integer", "description": "scroll垂直滚动(负上正下)"},
                "duration": {"type": "number", "description": "move/drag过渡秒数；move默认0瞬移，drag默认0.3"},
            },
            "required": ["action"],
        },
    },
}


def _mouse_impl(tool_ctx, **kwargs):
    err = _check_enabled(tool_ctx)
    if err:
        return err
    action = kwargs.get("action", "")
    x = int(kwargs.get("x") or 0)
    y = int(kwargs.get("y") or 0)
    button = kwargs.get("button", "left")
    clicks = int(kwargs.get("clicks") or 1)
    dx = int(kwargs.get("dx") or 0)
    dy = int(kwargs.get("dy") if kwargs.get("dy") is not None else -1)
    duration = float(kwargs.get("duration") or 0)
    element = kwargs.get("element")
    snapshot_id = kwargs.get("snapshot_id") or ""
    app_q = (kwargs.get("app") or "").strip()
    name_q = (kwargs.get("name") or "").strip()
    pid_q = kwargs.get("pid")
    el = None
    snap = None
    if element is None and name_q and (pid_q or app_q):
        # 直连定位：一步完成「找窗口 + 找元素 + 点击」
        el, snap, locate_err = _locate_by_name(app_q, name_q, pid=pid_q)
        if locate_err:
            return ToolResult(False, error=locate_err)
        element = 0
    if element is not None:
        try:
            element_int = int(element)
        except (TypeError, ValueError):
            return ToolResult(False, error=f"element 必须是整数，收到 {element!r}")
        el, snap, err = _resolve_element(snapshot_id, element_int)
        if err:
            return ToolResult(False, error=err)
        rect = el.get("rect") or []
        if len(rect) >= 4 and rect[2] > 0 and rect[3] > 0:
            x, y = _to_cursor(rect[0] + rect[2] / 2.0, rect[1] + rect[3] / 2.0)
        elif not x and not y:
            return ToolResult(False, error="该元素没有有效矩形，无法定位，请改传 x/y 坐标")
    try:
        if action not in _MOUSE_ACTIONS:
            return ToolResult(False, error=f"Unknown action: {action!r}. Valid: {sorted(_MOUSE_ACTIONS)}")
        if action not in _MOUSE_ACTIONS_NO_COORD and not element and not x and not y:
            return ToolResult(False, error="move/click/drag 需要 x/y 坐标，或先 ui_tree 后传 element")
        mouse = MouseController()
        if action == "position":
            pos = mouse.position
            result = {"x": pos[0], "y": pos[1]}
            try:
                with mss.mss() as sct:
                    result["screen_width"] = sct.monitors[1]["width"]
                    result["screen_height"] = sct.monitors[1]["height"]
                    result["monitors"] = [
                        {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}
                        for m in sct.monitors[1:]
                    ]
            except Exception:
                pass
            return ToolResult(True, content=result)
        if action == "move":
            mouse.position = (x, y)
            if duration > 0:
                time.sleep(duration)
            return ToolResult(True, content=f"鼠标移动到 ({x}, {y})")
        if action == "click":
            # 优先走无障碍动作：不动光标、不需要窗口在前台，也不受 DPI 缩放影响。
            # 失败（目标未实现 InvokePattern，如 WinForms）才退回坐标点击。
            if element is not None and el is not None and button == "left" and clicks == 1:
                rid = el.get("rid") or ""
                win_pid = ((snap or {}).get("window") or {}).get("pid")
                if rid and win_pid:
                    res = _uia_call("invoke", pid=win_pid, rid=rid, name=el.get("name") or None)
                    if res.get("ok"):
                        return ToolResult(True, content={
                            "via": "uia-invoke",
                            "element": el.get("i"),
                            "name": el.get("name"),
                            "note": "通过无障碍接口触发，未移动鼠标",
                        })
            mouse.position = (x, y)
            btn = _MOUSE_BUTTONS.get(button, Button.left)
            # 坐标点击前把目标窗口带到前台：Windows 对后台窗口的首次点击只用于激活，
            # 不会传到控件上，不先激活就会出现「点了没反应」。
            if element is not None and snap:
                win_pid = (snap.get("window") or {}).get("pid")
                if win_pid:
                    _uia_call("activate", pid=win_pid)
                    time.sleep(0.12)
            for _ in range(clicks):
                mouse.click(btn)
                time.sleep(0.05)
            return ToolResult(True, content=f"点击 ({x}, {y}) {clicks} 次 [{button}]")
        if action == "double_click":
            mouse.position = (x, y)
            mouse.click(_MOUSE_BUTTONS.get(button, Button.left), 2)
            return ToolResult(True, content=f"双击 ({x}, {y})")
        if action == "right_click":
            mouse.position = (x, y)
            mouse.click(Button.right)
            return ToolResult(True, content=f"右键点击 ({x}, {y})")
        if action == "scroll":
            mouse.scroll(dx, dy)
            return ToolResult(True, content=f"滚动 dx={dx} dy={dy}")
        if action == "drag":
            mouse.position = (x, y)
            btn = _MOUSE_BUTTONS.get(button, Button.left)
            mouse.press(btn)
            time.sleep(duration or 0.3)
            mouse.position = (x + dx, y + dy)
            time.sleep(0.1)
            mouse.release(btn)
            return ToolResult(True, content=f"拖拽 ({x}, {y}) → ({x + dx}, {y + dy})")
        return ToolResult(False, error=f"Unhandled action: {action}")
    except Exception as e:
        return ToolResult(False, error=f"Mouse error: {str(e)}")


# ========== keyboard ==========

_KEYBOARD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "keyboard",
        "description": "桌面键盘操作。支持打字/按单键/组合热键。需先开启桌面自动化。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["type", "press", "hotkey", "set_value"], "description": "type=输入文本,press=按单键,hotkey=组合热键,set_value=直接向元素写入值（需配合 element）"},
                "text": {"type": "string", "description": "type/set_value 操作要写入的文本（支持 Unicode）"},
                "key": {"type": "string", "description": "单键名: enter/f5/ctrl_l/esc/tab"},
                "keys": {"type": "string", "description": "组合键用+连接: ctrl+c,ctrl+shift+n"},
                "element": {"type": "integer", "description": "set_value 时的目标元素序号（来自 ui_tree）"},
                "snapshot_id": {"type": "string", "description": "set_value 时配套的快照 id"},
                "app": {"type": "string", "description": "窗口标题或进程名片段。与 name 一起用可跳过 ui_tree"},
                "pid": {"type": "integer", "description": "目标窗口进程 ID（比 app 稳）"},
                "name": {"type": "string", "description": "目标元素名字（精确优先，模糊次之）"},
            },
            "required": ["action"],
        },
    },
}

_KEY_ALIASES = {
    "enter": _pynput_kb.Key.enter, "return": _pynput_kb.Key.enter,
    "esc": _pynput_kb.Key.esc, "escape": _pynput_kb.Key.esc,
    "tab": _pynput_kb.Key.tab,
    "space": _pynput_kb.Key.space, "backspace": _pynput_kb.Key.backspace,
    "delete": _pynput_kb.Key.delete, "del": _pynput_kb.Key.delete,
    "insert": getattr(_pynput_kb.Key, "insert", None),  # darwin(macOS) 无此键
    "home": _pynput_kb.Key.home, "end": _pynput_kb.Key.end,
    "page_up": _pynput_kb.Key.page_up, "page_down": _pynput_kb.Key.page_down,
    "up": _pynput_kb.Key.up, "down": _pynput_kb.Key.down,
    "left": _pynput_kb.Key.left, "right": _pynput_kb.Key.right,
    "f1": _pynput_kb.Key.f1, "f2": _pynput_kb.Key.f2, "f3": _pynput_kb.Key.f3,
    "f4": _pynput_kb.Key.f4, "f5": _pynput_kb.Key.f5, "f6": _pynput_kb.Key.f6,
    "f7": _pynput_kb.Key.f7, "f8": _pynput_kb.Key.f8, "f9": _pynput_kb.Key.f9,
    "f10": _pynput_kb.Key.f10, "f11": _pynput_kb.Key.f11, "f12": _pynput_kb.Key.f12,
    "ctrl": _pynput_kb.Key.ctrl, "ctrl_l": _pynput_kb.Key.ctrl_l, "ctrl_r": _pynput_kb.Key.ctrl_r,
    "shift": _pynput_kb.Key.shift, "shift_l": _pynput_kb.Key.shift_l, "shift_r": _pynput_kb.Key.shift_r,
    "alt": _pynput_kb.Key.alt, "alt_l": _pynput_kb.Key.alt_l, "alt_r": _pynput_kb.Key.alt_r,
    "cmd": _pynput_kb.Key.cmd, "win": _pynput_kb.Key.cmd,
    "caps_lock": _pynput_kb.Key.caps_lock,
}


def _resolve_key(name: str):
    name_lower = name.lower()
    if name_lower in _KEY_ALIASES:
        val = _KEY_ALIASES[name_lower]
        if val is None:
            raise ValueError(f"当前平台不支持按键: {name}")
        return val
    if len(name) == 1:
        return name
    return name


def _keyboard_impl(tool_ctx, **kwargs):
    err = _check_enabled(tool_ctx)
    if err:
        return err
    action = kwargs.get("action", "")
    text = kwargs.get("text") or ""
    key = kwargs.get("key") or ""
    keys = kwargs.get("keys") or ""
    element = kwargs.get("element")
    snapshot_id = kwargs.get("snapshot_id") or ""
    app_q = (kwargs.get("app") or "").strip()
    name_q = (kwargs.get("name") or "").strip()
    pid_q = kwargs.get("pid")
    try:
        kb = _pynput_kb.Controller()
        if element is None and name_q and (pid_q or app_q):
            el_located, snap_located, locate_err = _locate_by_name(app_q, name_q, pid=pid_q)
            if locate_err:
                return ToolResult(False, error=locate_err)
            element = 0
            snapshot_id = ""
            kwargs["_pre_located"] = (el_located, snap_located)
        if action == "set_value":
            raw_text = kwargs.get("text")
            if raw_text is None:
                return ToolResult(False, error="set_value 操作需要 text 参数（清空请传空串）")
            text = str(raw_text)
            if element is None:
                return ToolResult(False, error="set_value 需要 element（先用 ui_tree 取元素序号）")
            try:
                element_int = int(element)
            except (TypeError, ValueError):
                return ToolResult(False, error=f"element 必须是整数，收到 {element!r}")
            pre = kwargs.get("_pre_located")
            if pre:
                el, snap = pre
                el_err = ""
            else:
                el, snap, el_err = _resolve_element(snapshot_id, element_int)
            if el_err:
                return ToolResult(False, error=el_err)
            rid = el.get("rid") or ""
            win_pid = ((snap or {}).get("window") or {}).get("pid")
            # 优先 ValuePattern：一步写入，不依赖键盘焦点与输入法
            if rid and win_pid:
                res = _uia_call("setvalue", pid=win_pid, rid=rid, text=text)
                if res.get("ok"):
                    return ToolResult(True, content={
                        "via": "uia-value",
                        "element": el.get("i"),
                        "name": el.get("name"),
                        "len": len(text),
                        "note": "通过无障碍接口直接写值，未触发键盘输入",
                    })
            # 退化：点中元素 → 全选 → 键入
            rect = el.get("rect") or []
            if len(rect) < 4:
                return ToolResult(False, error="元素缺少矩形，无法退化写入；请改用 action=type")
            mouse = MouseController()
            if win_pid:
                _uia_call("activate", pid=win_pid)
                time.sleep(0.12)
            cx, cy = _to_cursor(rect[0] + rect[2] / 2.0, rect[1] + rect[3] / 2.0)
            mouse.position = (cx, cy)
            mouse.click(Button.left)
            time.sleep(0.15)
            kb.press(_pynput_kb.Key.ctrl_l)
            kb.press("a")
            kb.release("a")
            kb.release(_pynput_kb.Key.ctrl_l)
            time.sleep(0.05)
            kb.type(text)
            return ToolResult(True, content={
                "via": "click+type",
                "element": el.get("i"),
                "len": len(text),
                "note": "目标不支持 ValuePattern，已退化为点击后键入",
            })
        if action == "type":
            if not text:
                return ToolResult(False, error="type 操作需要 text 参数")
            kb.type(text)
            return ToolResult(True, content=f"已输入 {len(text)} 字符")
        if action == "press":
            if not key:
                return ToolResult(False, error="press 操作需要 key 参数")
            kb.press(_resolve_key(key))
            time.sleep(0.05)
            kb.release(_resolve_key(key))
            return ToolResult(True, content=f"已按下 {key}")
        if action == "hotkey":
            if not keys:
                return ToolResult(False, error="hotkey 操作需要 keys 参数（如 ctrl+c）")
            parts = [_resolve_key(p.strip()) for p in keys.split("+") if p.strip()]
            if not parts:
                return ToolResult(False, error="无效组合键")
            for p in parts:
                kb.press(p)
            time.sleep(0.05)
            for p in reversed(parts):
                kb.release(p)
            return ToolResult(True, content=f"已执行组合键 {keys}")
        return ToolResult(False, error=f"Unknown action: {action!r}. Valid: type/press/hotkey/set_value")
    except Exception as e:
        return ToolResult(False, error=f"Keyboard error: {str(e)}")


# ========== 渲染闭包 ==========

def _render_screenshot_body(result, tool_name, tool_args, success):
    """screenshot 完成框渲染闭包：直接展示截图图片

    签名：render(result, tool_name, tool_args, success) -> str | None
    返回 None 时回退通用渲染。
    """
    raw = getattr(result, "content", "") or ""
    if isinstance(raw, dict):
        img_path = raw.get("absolute_path") or raw.get("path") or ""
    else:
        img_path = _extract_screenshot_image_path(str(raw))
    if not img_path:
        return None
    return (
        '<div class="screenshot-preview" style="margin: 0; padding: 0;">'
        f'<img src="{escape(img_path)}" '
        'style="width: 100%; height: auto; display: block; border-radius: 8px;" '
        'alt="Screenshot" />'
        '</div>'
    )


def _preview_screenshot(tool_args: dict) -> str:
    region = tool_args.get("region")
    if region and isinstance(region, (list, tuple)) and len(region) == 4:
        return f"截取屏幕 ({region[2]}×{region[3]})"
    return "截取屏幕"


def _preview_mouse(tool_args: dict) -> str:
    action = tool_args.get("action", "")
    x = tool_args.get("x", "")
    y = tool_args.get("y", "")
    action_labels = {
        "move": "移动",
        "click": "点击",
        "double_click": "双击",
        "right_click": "右键",
        "scroll": "滚动",
        "drag": "拖拽",
        "position": "查询位置",
    }
    action_label = action_labels.get(action, action or "操作")
    if action == "position":
        return "查询鼠标位置"
    element = tool_args.get("element")
    if element is not None:
        return f"鼠标{action_label} 元素 #{element}"
    if x != "" and y != "":
        return f"鼠标{action_label} ({x}, {y})"
    return f"鼠标{action_label}"


def _preview_keyboard(tool_args: dict) -> str:
    action = tool_args.get("action", "")
    if action == "type":
        text = tool_args.get("text", "")
        preview = text[:30] + ("…" if len(text) > 30 else "")
        return f'键盘输入 "{preview}"' if preview else "键盘输入"
    if action == "set_value":
        text = tool_args.get("text", "")
        preview = text[:24] + ("…" if len(text) > 24 else "")
        element = tool_args.get("element")
        return f'写入元素 #{element} "{preview}"'
    if action == "press":
        key = tool_args.get("key", "")
        return f"按键 {key}" if key else "按键"
    if action == "hotkey":
        keys = tool_args.get("keys", "")
        return f"热键 {keys}" if keys else "热键"
    return "键盘操作"


# ========== 注册入口 ==========

def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "ui_tree", _UI_TREE_SCHEMA, impl=_ui_tree_impl,
        danger="dangerous", icon="裁剪", cn_name="界面元素树",
        group=GROUP_DESKTOP, description="读取窗口无障碍元素树（可定位到具体按钮与输入框）",
        aliases=["UITree"],
        render_mode="expand",
        preview=_preview_ui_tree,
        summarize=make_summarize_from_preview(_preview_ui_tree),
    )
    registry.register(
        "screenshot", _SCREENSHOT_SCHEMA, impl=_screenshot_impl,
        danger="safe", icon="裁剪", cn_name="截图",
        group=GROUP_DESKTOP, description="截取屏幕截图",
        render_mode="expand",  # 图片直接展示，禁用折叠框
        render=_render_screenshot_body,
        preview=_preview_screenshot,
        summarize=make_summarize_from_preview(_preview_screenshot),
        # 视觉注入声明：结果可解析出本地图片路径（协议 A），供 chat_worker 视觉模型注入
        metadata={"provides_image": True},
    )
    registry.register(
        "mouse", _MOUSE_SCHEMA, impl=_mouse_impl,
        danger="dangerous", icon="鼠标", cn_name="鼠标",
        group=GROUP_DESKTOP, description="鼠标操作",
        aliases=["Mouse"],
        preview=_preview_mouse,
        summarize=make_summarize_from_preview(_preview_mouse),
    )
    registry.register(
        "keyboard", _KEYBOARD_SCHEMA, impl=_keyboard_impl,
        danger="dangerous", icon="233键盘-线性", cn_name="键盘",
        group=GROUP_DESKTOP, description="键盘操作",
        aliases=["Keyboard"],
        preview=_preview_keyboard,
        summarize=make_summarize_from_preview(_preview_keyboard),
    )