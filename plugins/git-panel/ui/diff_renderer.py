# -*- coding: utf-8 -*-
"""diff 文本 → 词级高亮 HTML 渲染（纯函数，无 Qt 依赖）

行级着色 + 词级差异高亮：
- 对配对的 -/+ 行用 difflib.SequenceMatcher 计算词级差异（按空白分词）
- + 行中的新增词：粗体 + 浅绿底
- - 行中的删除词：粗体 + 浅红底 + 删除线
- 不依赖 `git --word-diff`，仅用 stdlib
"""

import difflib
import html
import re

_TOKEN_RE = re.compile(r"\S+|\s+")


def _escape(token: str) -> str:
    return html.escape(token, quote=False)


def _render_word_diff(del_line: str, add_line: str,
                      add_color: str, del_color: str,
                      add_bg: str, del_bg: str) -> str:
    """渲染一对 -/+ 行的词级差异 HTML。

    del_line / add_line 为原始行内容（不含 +/- 前缀）。
    """
    del_tokens = _TOKEN_RE.findall(del_line)
    add_tokens = _TOKEN_RE.findall(add_line)

    matcher = difflib.SequenceMatcher(None, del_tokens, add_tokens, autojunk=False)
    del_html: list[str] = []
    add_html: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            del_html.append("".join(_escape(t) for t in del_tokens[i1:i2]))
            add_html.append("".join(_escape(t) for t in add_tokens[j1:j2]))
        elif tag == "replace":
            del_html.append(
                f'<b style="background:{del_bg};color:{del_color};'
                f'text-decoration:line-through;">'
                + "".join(_escape(t) for t in del_tokens[i1:i2]) + "</b>"
            )
            add_html.append(
                f'<b style="background:{add_bg};color:{add_color};">'
                + "".join(_escape(t) for t in add_tokens[j1:j2]) + "</b>"
            )
        elif tag == "delete":
            del_html.append(
                f'<b style="background:{del_bg};color:{del_color};'
                f'text-decoration:line-through;">'
                + "".join(_escape(t) for t in del_tokens[i1:i2]) + "</b>"
            )
        elif tag == "insert":
            add_html.append(
                f'<b style="background:{add_bg};color:{add_color};">'
                + "".join(_escape(t) for t in add_tokens[j1:j2]) + "</b>"
            )

    return "".join(del_html), "".join(add_html)


def _palette(dark: bool) -> dict:
    """按主题返回 diff 行级/词级调色板。

    深色主题用亮色系（浅绿/红/蓝），浅色主题用深色系保证对比度。
    """
    if dark:
        return {
            "add": "#50e3c2",
            "del": "#f14c4c",
            "hunk": "#62a0ea",
            "add_bg": "rgba(80,227,194,0.28)",
            "del_bg": "rgba(241,76,76,0.28)",
        }
    return {
        "add": "#1a7f37",
        "del": "#cf222e",
        "hunk": "#0969da",
        "add_bg": "rgba(26,127,55,0.20)",
        "del_bg": "rgba(207,34,46,0.20)",
    }


def render_diff_html(diff_text: str,
                     base_color: str = "rgba(255,255,255,0.9)",
                     secondary_color: str = "rgba(255,255,255,0.55)",
                     dark: bool = True) -> str:
    """将 diff 文本渲染为带行级 + 词级高亮的 HTML。

    行级颜色沿用 git 惯例：
    - + 行：绿
    - - 行：红
    - @@ 行：蓝
    - diff --git / index / --- / +++ 行：次要色

    dark=False 时使用浅色主题调色板（深绿/深红/深蓝），避免浅色背景上看不清。
    """
    pal = _palette(dark)
    ADD_COLOR = pal["add"]
    DEL_COLOR = pal["del"]
    HUNK_COLOR = pal["hunk"]
    ADD_BG = pal["add_bg"]
    DEL_BG = pal["del_bg"]

    lines = diff_text.splitlines()
    parts = ['<pre style="margin:0; white-space:pre-wrap;">']

    pending_del: str | None = None  # 等待配对的 - 行

    def _flush_del():
        nonlocal pending_del
        if pending_del is None:
            return
        del_body = pending_del[1:]
        parts.append(
            f'<span style="color:{DEL_COLOR};">{_escape(pending_del[:1])}</span>'
            f'<span style="color:{DEL_COLOR};">{_escape(del_body)}</span>\n'
        )
        pending_del = None

    for line in lines:
        if line.startswith("+") and not line.startswith("+++"):
            if pending_del is not None:
                # 配对：渲染词级差异
                del_body = pending_del[1:]
                add_body = line[1:]
                del_html, add_html = _render_word_diff(
                    del_body, add_body, ADD_COLOR, DEL_COLOR, ADD_BG, DEL_BG
                )
                parts.append(
                    f'<span style="color:{DEL_COLOR};">{_escape(line[0])}</span>'
                    f'<span style="color:{DEL_COLOR};">{del_html}</span>\n'
                )
                parts.append(
                    f'<span style="color:{ADD_COLOR};">{_escape(line[0])}</span>'
                    f'<span style="color:{ADD_COLOR};">{add_html}</span>\n'
                )
                pending_del = None
            else:
                parts.append(
                    f'<span style="color:{ADD_COLOR};">{_escape(line[0])}</span>'
                    f'<span style="color:{ADD_COLOR};">{_escape(line[1:])}</span>\n'
                )
        elif line.startswith("-") and not line.startswith("---"):
            # 缓存 - 行，等待可能的 + 行配对
            pending_del = line
        elif line.startswith("@@"):
            _flush_del()
            parts.append(
                f'<span style="color:{HUNK_COLOR};font-weight:bold;">'
                f'{_escape(line)}</span>\n'
            )
        elif (line.startswith("diff --git") or line.startswith("index ")
              or line.startswith("---") or line.startswith("+++")):
            _flush_del()
            parts.append(
                f'<span style="color:{secondary_color};">{_escape(line)}</span>\n'
            )
        else:
            _flush_del()
            parts.append(
                f'<span style="color:{base_color};">{_escape(line)}</span>\n'
            )

    _flush_del()
    parts.append("</pre>")
    return "".join(parts)


def render_plain_text(text: str,
                      base_color: str = "rgba(255,255,255,0.9)",
                      secondary_color: str = "rgba(255,255,255,0.55)") -> str:
    """普通文本（非 diff）渲染为 HTML，保留换行。"""
    parts = ['<pre style="margin:0; white-space:pre-wrap;">']
    for line in text.splitlines():
        if line.strip():
            parts.append(f'<span style="color:{base_color};">{_escape(line)}</span>\n')
        else:
            parts.append("<br/>")
    parts.append("</pre>")
    return "".join(parts)
