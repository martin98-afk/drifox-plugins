# -*- coding: utf-8 -*-
"""
hashline 锚点引擎 — 纯逻辑模块（无 IO、无状态、无第三方依赖）

锚点协议（pi 风格）：
- read 每行前缀 `LINE#HASH:`（如 `9#KT: console.log('world')`）
- LINE = 1 起始行号；HASH = 2-4 字符内容哈希
- 哈希 = xxh32 低 4N 位映射到 16 字符字母表（Python 用 zlib.crc32 实现）
- **上下文哈希**：hash = f(prev + curr + next) 三行窗口
  → 相同行不同上下文产生不同 hash；编辑行 N 只影响 N-1/N/N+1 三个锚点，
  其余行锚点保持稳定，链式编辑不失效

注意：本文件是纯逻辑模块，`register()` 为占位实现（满足仓库校验器
「tools/*.py 必须定义顶层 register(registry)」的要求），不注册任何工具。
"""
import re
import zlib

# 16 字符字母表（每 4 bit 映射 1 字符）
ALPHABET = "ZPMQVRWSNKTXJBYH"

# 默认哈希宽度（2-4 字符；16^2=256 种组合，三行窗口下冲突概率可接受）
DEFAULT_WIDTH = 2
MIN_WIDTH = 2
MAX_WIDTH = 4

# 锚点正则：LINE#HASH（LINE 从 1 起；HASH 为字母表字符 2-4 位）
ANCHOR_RE = re.compile(r"^([1-9]\d*)#([ZPMQVRWSNKTXJBYH]{2,4})$")

# 行内容注入检测：锚点显示前缀 / unified diff 标记（E_INVALID_PATCH）
_ANCHOR_PREFIX_RE = re.compile(r"^\d+#[ZPMQVRWSNKTXJBYH]{2,4}\s*[:：]")
_DIFF_MARK_RE = re.compile(r"^(@@|--- |\+\+\+ |diff --git|index )")
_DIFF_LINE_RE = re.compile(r"^[+\-] ")


def _clamp_width(width: int) -> int:
    """钳制哈希宽度到 [MIN_WIDTH, MAX_WIDTH]"""
    try:
        w = int(width)
    except (TypeError, ValueError):
        return DEFAULT_WIDTH
    return max(MIN_WIDTH, min(w, MAX_WIDTH))


def context_hash(prev: str, curr: str, nxt: str, width: int = DEFAULT_WIDTH) -> str:
    """三行窗口上下文哈希 → 字母表字符串

    prev/nxt 为边界缺行时传空串。窗口用 \x01 分隔（区别于内容内换行）。
    """
    w = _clamp_width(width)
    window = "\x01".join((prev or "", curr, nxt or ""))
    crc = zlib.crc32(window.encode("utf-8")) & 0xFFFFFFFF
    bits = crc & ((1 << (4 * w)) - 1)
    chars = []
    for _ in range(w):
        chars.append(ALPHABET[bits & 0xF])
        bits >>= 4
    return "".join(chars)


def line_hash(lines, idx: int, width: int = DEFAULT_WIDTH) -> str:
    """lines 中第 idx 行（0 起始）的上下文哈希；边界行按空串补全"""
    n = len(lines)
    prev = lines[idx - 1] if idx > 0 else ""
    curr = lines[idx]
    nxt = lines[idx + 1] if idx + 1 < n else ""
    return context_hash(prev, curr, nxt, width)


def hash_all(lines, width: int = DEFAULT_WIDTH) -> list:
    """全部行哈希（index 对齐 lines）"""
    w = _clamp_width(width)
    return [line_hash(lines, i, w) for i in range(len(lines))]


def parse_anchor(pos) -> tuple:
    """解析锚点 `LINE#HASH` → (lineno 1 起始, hash 文本)

    格式非法抛 ValueError（调用方转 E_INVALID_PATCH）。
    """
    if not isinstance(pos, str):
        raise ValueError(f"锚点必须是 LINE#HASH 字符串（如 9#KT），当前为 {pos!r}")
    m = ANCHOR_RE.match(pos.strip())
    if not m:
        raise ValueError(f"非法锚点格式（应为 LINE#HASH，如 9#KT）: {pos!r}")
    return int(m.group(1)), m.group(2)


def format_line(lineno: int, h: str, text: str) -> str:
    """单行锚点输出：`9#KT: text`"""
    return f"{lineno}#{h}: {text}"


def format_anchors_block(start: int, end: int, lines, hashes) -> str:
    """链式编辑返回的新锚点块：`--- Anchors A-B ---` + 行锚点

    start/end 为 1 起始闭区间 [start, end]，自动裁剪到 lines 范围。
    供 ToolResult.anchors 字段回传，LLM 可基于新锚点继续编辑。
    """
    lo = max(1, start)
    hi = min(len(lines), end)
    if lo > hi:
        lo, hi = 1, len(lines)
    block = [f"--- Anchors {lo}-{hi} ---"]
    for i in range(lo - 1, hi):
        block.append(format_line(i + 1, hashes[i], lines[i]))
    return "\n".join(block)


def validate_line_content(text: str):
    """行内容注入检测：含锚点显示前缀 / diff 标记 → 返回错误消息，否则 None"""
    if _ANCHOR_PREFIX_RE.match(text):
        return f"行内容含锚点显示前缀（{text[:40]!r}），不允许作为编辑内容"
    if _DIFF_MARK_RE.match(text) or _DIFF_LINE_RE.match(text):
        return f"行内容含 diff 标记（{text[:40]!r}），不允许作为编辑内容"
    return None


def register(registry):
    """占位入口：纯逻辑模块不注册工具（满足仓库校验器要求）。"""
    return None
