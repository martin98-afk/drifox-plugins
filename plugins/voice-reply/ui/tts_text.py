# -*- coding: utf-8 -*-
"""voice-reply 朗读文本策略：只取正文，剔除一切不适合朗读的内容。

为什么独立成模块：`ui/__init__.py` 已承载按钮状态机、双引擎调度、图标切换，
文本清洗是纯函数逻辑（无 Qt 依赖），拆开后便于离线单测与单独演进。

正文口径（按内容块类型过滤，而非字符串猜测）：
- 只保留 `type == "text"` 块。思考过程（reasoning）、工具调用与结果
  （tool_result）、自定义渲染块（custom）、图片块都不是正文，不进朗读。
- 兜底路径（拿不到块列表、退回 `get_plain_text()`）再用正则补刀：内联
  `<think>...</think>` 段整段删除，`[tool:xxx]` 开头的行整行删除 ——
  扁平文本里这些串已经和正文混在一起，只能按特征识别。

清洗口径（朗读器会把符号读成人话，或干脆读成乱码）：
- markdown 标记：代码块整体替换为「代码略」提示音；行内代码去反引号；
  图片留 alt、链接留文字；粗体/斜体/删除线/标题/列表/引用/分隔线去标记。
- 机器串：裸 URL、data URI、超长 base64/哈希串、HTML 标签。
- emoji 与装饰符号：多数 TTS 会读成「笑脸」「右箭头」之类的人话，直接剔除。
- 控制字符、连续标点：折叠成单个停顿。
"""

from __future__ import annotations

import re
from typing import Any, List

# 朗读文本上限（字）。原 500 字常把长回复切断在句中，2000 字覆盖绝大多数回答；
# 在线引擎合成耗时随字数近似线性增长，2000 字仍在可接受范围内。
MAX_TEXT_LEN = 2000

# ── 兜底路径特征串（块列表不可用时才靠它们补刀） ──
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.S)
_TOOL_LINE_RE = re.compile(r"^[ \t]*\[tool:[^\]]*\][^\n]*$", re.M)

# URL / data URI 尾部排除中文与常见闭合符，避免把句末标点一起吞掉
_TAIL = r"[^\s，。；：、！？）)】\]>\"'」』]"
_URL_RE = re.compile(rf"(?:https?://|www\.){_TAIL}+", re.I)
_DATA_URI_RE = re.compile(rf"data:{_TAIL}+", re.I)
# 超长无分隔 ASCII 串：base64 图片数据、sha/commit hash、长路径
_BASE64_RE = re.compile(r"[A-Za-z0-9+/_\-]{60,}")
_HTML_TAG_RE = re.compile(r"<[a-zA-Z/][^>]{0,200}>")
# emoji / 装饰符号 / 变体选择符 / 零宽连接符
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2190-\u21FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]"
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_MARKDOWN_PATTERNS = [
    (re.compile(r"```.*?```", re.S), "，代码略，"),  # 代码块整体略读
    (re.compile(r"`([^`]*)`"), r"\1"),  # 行内代码去反引号
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), r"\1"),  # 图片留 alt
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),  # 链接留文字
    (re.compile(r"(\*\*|__)(.*?)\1"), r"\2"),  # 粗体
    (re.compile(r"(\*|_)(.*?)\1"), r"\2"),  # 斜体
    (re.compile(r"~~(.*?)~~"), r"\1"),  # 删除线
    (re.compile(r"\[\^[^\]]*\]"), ""),  # 脚注引用
    (re.compile(r"^#{1,6}\s*", re.M), ""),  # 标题井号
    (re.compile(r"^\s*[-*+]\s+", re.M), ""),  # 无序列表符号
    (re.compile(r"^\s*\d{1,3}[.)]\s+", re.M), ""),  # 有序列表序号
    (re.compile(r"^\s*>\s?", re.M), ""),  # 引用尖括号
    (re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", re.M), "。"),  # 分隔线
    (re.compile(r"\|"), "，"),  # 表格竖线
    (re.compile(r"\n{2,}"), "。\n"),  # 多空行收成句号停顿
]

# 代码块/表格替换产生的「换行两侧孤逗号」：逗号贴在行首或行尾没有语义，
# 只会让朗读器多报一声「逗号」，清掉。
_EDGE_COMMA_RE = re.compile(r"[，,]\s*\n|\n\s*[，,]")


def extract_body_text(card: Any) -> str:
    """从消息卡片提取正文（只取 text 块）。

    优先读卡片 `_content_data` 块列表按类型过滤；块列表不可用（老卡片 /
    接口变动 / 传进来的不是卡片）时退回 `get_plain_text()`，此时文本已混入
    工具结果，靠 `clean_for_tts` 的正则补刀。
    """
    if card is None:
        return ""
    blocks = getattr(card, "_content_data", None)
    if isinstance(blocks, list):
        parts: List[str] = []
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            piece = str(block.get("text") or "")
            if piece.strip():
                parts.append(piece)
        return "\n\n".join(parts).strip()
    try:
        return str(card.get_plain_text() or "")
    except Exception:  # noqa: BLE001 — 卡片接口异常按空文本处理
        return ""


def clean_for_tts(text: str) -> str:
    """轻度清洗 markdown 标记与机器串，避免朗读器读出符号或乱码。"""
    for pattern, repl in _MARKDOWN_PATTERNS:
        text = pattern.sub(repl, text)
    # 顺序要紧：先删整段 think / 工具行，再删 HTML 标签。
    # 否则 `<think>` 会被 HTML 标签正则当成开标签吃掉一半，残留 `</think>` 被朗读。
    text = _THINK_BLOCK_RE.sub("", text)
    text = _TOOL_LINE_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _DATA_URI_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = _BASE64_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"，{2,}", "，", text)  # 表格竖线等替换产生的连续逗号
    text = _EDGE_COMMA_RE.sub("\n", text)  # 换行两侧的孤逗号
    text = re.sub(r"。{2,}", "。", text)  # 分隔线/多空行替换产生的连续句号
    return text.strip()


def build_speakable_text(card: Any) -> str:
    """提取正文 → 清洗 → 截断，返回可直接交给 TTS 引擎的文本。"""
    text = clean_for_tts(extract_body_text(card))
    if len(text) > MAX_TEXT_LEN:
        text = text[:MAX_TEXT_LEN] + "……"
    return text
