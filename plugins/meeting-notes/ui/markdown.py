# -*- coding: utf-8 -*-
"""轻量 Markdown → HTML（只覆盖会议纪要会出现的语法）。

两个踩坑点，直接决定了实现方式：
1. 不能用 QTextDocument.setMarkdown：它对 heading 不吃 setDefaultStyleSheet，
   标题永远按内置倍率渲染（比正文大一大截，且带衬线字体）。
2. 也不能用 <h1>/<h2> 标签 + 默认样式表：Qt 富文本引擎同样优先内置 heading
   格式，覆盖不了。

所以标题一律输出 <p style="...">，样式全部内联——这是 QTextDocument 唯一
稳定生效的通道。调用方给 css 字典（按元素名给 style 串），本模块只负责结构。

支持：# / ## / ### 标题、- 列表、**粗体**、`代码`、--- 分隔线、
| 表格 |（首行为表头）、普通段落。
"""

from __future__ import annotations

import re
from typing import Dict, Optional

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_SEP_CELLS = set("-: ")


def _inline(text: str) -> str:
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _CODE.sub(r"<code>\1</code>", text)
    return text


def _wrap(tag: str, content: str, css: Dict[str, str], extra_attr: str = "") -> str:
    style = css.get(tag, "")
    attr = f' style="{style}"' if style else ""
    return f"<{tag}{attr}{extra_attr}>{content}</{tag}>"


def to_html(md: str, css: Optional[Dict[str, str]] = None) -> str:
    """Markdown → HTML 片段。css 键：h1/h2/h3/p/li/td/th/code/table。"""
    css = css or {}
    lines = (md or "").splitlines()
    out: list[str] = []
    in_ul = False
    in_table = False

    def close_blocks() -> None:
        nonlocal in_ul, in_table
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_table:
            out.append("</table>")
            in_table = False

    for raw in lines:
        s = raw.strip()
        if not s:
            close_blocks()
            continue

        heading_level = 0
        for n in (3, 2, 1):
            if s.startswith("#" * n + " "):
                heading_level = n
                break
        if heading_level:
            close_blocks()
            # 用 p + 内联样式，不用 hN：Qt 富文本对 heading 有内置格式，
            # 会盖掉 CSS 的字号且强制衷线字体
            style = css.get(f"h{heading_level}", "")
            attr = f' style="{style}"' if style else ""
            out.append(f"<p{attr}>{_inline(s[heading_level + 1 :].strip())}</p>")
            continue

        if s in ("---", "***", "___"):
            close_blocks()
            out.append("<hr/>")
            continue

        if s.startswith(("- ", "* ", "+ ")):
            if in_table:
                out.append("</table>")
                in_table = False
            # 列表也用 p 自绘圆点：Qt 对 ul/li 的字号继承不可靠
            style = css.get("li", "")
            attr = f' style="{style}"' if style else ""
            out.append(f"<p{attr}>• {_inline(s[2:].strip())}</p>")
            continue

        if s.startswith("|") and s.endswith("|") and len(s) > 2:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if cells and all(set(c) <= _SEP_CELLS for c in cells if c):
                continue
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_table:
                out.append('<table border="1" cellspacing="0" cellpadding="6">')
                in_table = True
                out.append(
                    "<tr>"
                    + "".join(_wrap("th", _inline(c), css) for c in cells)
                    + "</tr>"
                )
            else:
                out.append(
                    "<tr>"
                    + "".join(_wrap("td", _inline(c), css) for c in cells)
                    + "</tr>"
                )
            continue

        close_blocks()
        out.append(_wrap("p", _inline(s), css))

    close_blocks()
    return "\n".join(out)
