# -*- coding: utf-8 -*-
"""
文件 IO 层 — 路径解析 / 二进制检测 / 文本加载 / mtime 记录（窗口隔离感知）

与系统 file_tools.py 对齐的契约：
- 路径解析：绝对路径直接用；~ 展开；相对路径基于 workdir
- 二进制检测：扩展名 + NUL 字节启发式
- mtime 记录：外部修改检测（read 后文件被外部改动则拒绝编辑）

mtime 状态存放（快照池）：
- 优先 tool_ctx.services.window_state（窗口隔离，跨工具调用共享）
- 无 window_state 时降级模块级 dict（测试/降级场景）

注意：本文件是 IO 辅助模块，`register()` 为占位实现（满足仓库校验器
「tools/*.py 必须定义顶层 register(registry)」的要求），不注册任何工具。
"""
from pathlib import Path
from typing import Optional

# 二进制扩展名（与系统 file_tools 对齐）
_BINARY_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".pdf", ".zip",
     ".tar", ".gz", ".7z", ".exe", ".dll", ".so", ".dylib", ".pyc", ".pyo",
     ".woff", ".woff2", ".ttf", ".otf", ".eot", ".bin", ".dat", ".db", ".sqlite"}
)

_TEXT_EXTENSIONS = frozenset(
    {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss", ".json",
     ".md", ".txt", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".sh",
     ".bat", ".cmd", ".ps1", ".c", ".h", ".cpp", ".hpp", ".java", ".kt", ".go",
     ".rs", ".rb", ".php", ".swift", ".m", ".sql", ".xml", ".svg", ".vue", ".svelte"}
)

_BINARY_NULL_LIMIT = 8192

# 图片扩展名（read 视觉协议 B：image_data 返回）
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})

# 模块级 mtime 缓存（无 window_state 时降级）
_file_mtimes: dict = {}


def _mtimes_state(tool_ctx) -> dict:
    """获取 mtime 状态字典：有 window_state → 窗口隔离；无 → 模块级降级。

    返回共享 dict 引用，原地修改（勿新建替换，否则隔离失效）。
    """
    try:
        ws = (tool_ctx or {}).get("services", {}).get("window_state")
        if ws is not None:
            d = ws["get"]("hashline_mtimes")
            if d is None:
                d = {}
                ws["set"]("hashline_mtimes", d)
            return d
    except Exception:
        pass
    return _file_mtimes


def resolve(workdir, path: str) -> Path:
    """解析路径：绝对路径直接用；~ 展开；相对路径基于 workdir"""
    if not path:
        return Path(workdir or Path.cwd())
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    base = workdir or Path.cwd()
    return base / p


def display_path(workdir, full_path: Path, original: str) -> str:
    """显示路径：workdir 内用相对路径，外部回退原始路径"""
    if workdir is not None:
        try:
            return str(full_path.relative_to(workdir))
        except ValueError:
            pass
    return original


def is_binary(full_path: Path) -> bool:
    """二进制文件检测：扩展名 + NUL 字节启发式"""
    ext = full_path.suffix.lower()
    if ext in _BINARY_EXTENSIONS:
        return True
    if ext in _TEXT_EXTENSIONS:
        return False
    try:
        with open(full_path, "rb") as f:
            head = f.read(_BINARY_NULL_LIMIT)
        return b"\x00" in head
    except OSError:
        return True


def load_text(full_path: Path) -> tuple:
    """读取文本文件 → (lines, trailing_newline)

    - lines 为去掉行尾换行的行列表，空行保留（split("\n") 语义）
    - trailing_newline：原文是否以换行结尾（写回时保留）
    - 空文件 → ([], False)
    """
    text = full_path.read_text(encoding="utf-8", errors="replace")
    if not text:
        return [], False
    if text.endswith("\n"):
        return text[:-1].split("\n"), True
    return text.split("\n"), False


def record_mtime(tool_ctx, full_path: Path) -> None:
    """记录文件 mtime（窗口隔离感知）"""
    try:
        _mtimes_state(tool_ctx)[str(full_path)] = full_path.stat().st_mtime
    except OSError:
        pass


def check_modified(tool_ctx, workdir, full_path: Path, original: str) -> Optional[str]:
    """外部修改检测：read 后文件被外部改动则返回错误消息，否则 None。

    与系统 edit 行为一致：mtime 变化即拒绝（编辑基于过期内容）。
    无 read 记录（首次编辑）→ 不校验，放行。
    """
    key = str(full_path)
    recorded = _mtimes_state(tool_ctx).get(key)
    if recorded is not None:
        try:
            current = full_path.stat().st_mtime
        except OSError:
            return None
        if abs(current - recorded) > 1e-6:
            display = display_path(workdir, full_path, original)
            return (
                f"[错误] 文件自上次读取后已被外部修改：{display}。"
                f"当前编辑基于过期内容，可能覆盖最新变更。"
                f"请先用 read 工具重新读取该文件，拿到最新锚点后再重试编辑。"
            )
    return None


def register(registry):
    """占位入口：IO 辅助模块不注册工具（满足仓库校验器要求）。"""
    return None
