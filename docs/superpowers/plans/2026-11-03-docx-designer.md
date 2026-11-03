# docx-designer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DriFox UI 插件：独立窗口预览 docx，页内拾取元素，回填（文本+锚点+截图）到输入框。

**Architecture:** XML 流遍历解析 → 中间结构 Block → 自生成 HTML（data-anchor + QWebChannel）→ QWebEngineView 展示；拾取走页面内 JS 点击监听回传锚点与矩形，Python 侧裁剪截图并经能力池 `input.write` 回填。设计文档：`docs/superpowers/specs/2026-11-03-docx-designer-design.md`。

**Tech Stack:** Python 3.10（宿主同栈）、PyQt5（QWebEngineView + QWebChannel）、python-docx（解析 + lxml）、pytest（纯函数单测）。

**环境事实（已验证）：**
- 系统 `python` 3.10.16，`python-docx` 1.2.0 可用；本机无可运行的 PyQt5（UI 层只能静态校验）
- 宿主模块名规则：`ui_plugin_{name.replace('-','_')}` → `ui_plugin_docx_designer`
- `input.write(text, append=False, focus=True)`（`ui_core.py:780`）；`storage.data_dir` 返回数据根字符串（`ui_core.py:1279`，surface="ui" 已注册）
- OMML 测试样本现成：`plugins/omml-docx/skills/omml-docx/scripts/demo_omml.docx`；公式构造器 `omml_utils.py`（纯标准库）可直接 import

---

### Task 1: 插件骨架

**Files:**
- Create: `plugins/docx-designer/.drifox-plugin/plugin.json`
- Create: `plugins/docx-designer/__init__.py`
- Create: `plugins/docx-designer/ui/__init__.py`
- Create: `plugins/docx-designer/ui/theme.py`
- Create: `plugins/docx-designer/icon.svg`、`plugins/docx-designer/icon_dark.svg`

- [ ] **Step 1: 写 plugin.json**

```json
{
    "name": "docx-designer",
    "description": "docx 文档设计模式 — 独立窗口预览 Word 文档，页内拾取元素（段落/表格/公式/图片），锚点+文本+截图回填输入框，让模型精确修改。",
    "icon": {
        "light": "icon.svg",
        "dark": "icon_dark.svg"
    },
    "version": "0.1.0",
    "author": {
        "name": "DriFox Contributors"
    },
    "license": "GPL-3.0-or-later",
    "type": "user",
    "api_version": 2,
    "min_host_version": "0.6.10",
    "capabilities": [
        "input.read",
        "input.write",
        "storage.data_dir"
    ],
    "keywords": [
        "docx",
        "word",
        "document",
        "preview"
    ],
    "dependencies": {
        "pip": [
            "python-docx>=1.1.0"
        ]
    },
    "components": {
        "commands": false,
        "ui": true,
        "tools": true
    }
}
```

- [ ] **Step 2: 写包标记与 UI 注册入口**

`plugins/docx-designer/__init__.py`：

```python
# -*- coding: utf-8 -*-
"""docx-designer — docx 文档设计模式插件"""
```

`plugins/docx-designer/ui/__init__.py`：

```python
# -*- coding: utf-8 -*-
"""docx-designer UI 组件入口

注册浮动卡片「文档设计」（/docx-designer 命令由 register_floating_card 自动注册）。
热重载语义与 browser 插件一致：
1. 清理 sys.modules 中残留的 ui_plugin_docx_designer.* 子模块缓存
2. 清理 function handlers 中残留的旧引用
3. 注册浮动卡片
"""

import sys

from loguru import logger


def register_ui(registry):
    # 1) 清理旧子模块缓存（热重载防旧 .pyc）
    prefix = "ui_plugin_docx_designer."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    # 2) 清理 function handlers 残留
    try:
        from app.core.commands.builtin_commands import FunctionCommandHandlers

        FunctionCommandHandlers._handlers.pop("docx-designer", None)
    except Exception:
        pass

    # 3) 注册浮动卡片
    from .docx_window import DocxWindowCard

    registry.register_floating_card(
        plugin_name="docx-designer",
        card_id="docx-designer",
        widget_class=DocxWindowCard,
        container="right",
        title="文档设计",
        default_visible=False,
    )
    logger.info("[docx-designer] UI components registered")


def unload_ui(registry):
    """无外部资源需手动释放；窗口随 registry 清理。"""
```

- [ ] **Step 3: 写主题色模块（自 browser 精简，插件自包含不跨插件 import）**

`plugins/docx-designer/ui/theme.py`：

```python
# -*- coding: utf-8 -*-
"""主题色派生（精简自 browser 插件同款实现，键名保持一致）。"""


def _ctx(owner=None) -> dict:
    provider = getattr(owner, "_context_provider", None)
    if provider is None:
        return {}
    try:
        return provider() or {}
    except Exception:
        return {}


def theme_colors(owner=None) -> dict:
    try:
        from qfluentwidgets import isDarkTheme

        _is_dark = isDarkTheme()
    except Exception:
        _is_dark = True

    ctx = _ctx(owner)
    ctx_is_dark = ctx.get("is_dark")
    is_dark = ctx_is_dark if isinstance(ctx_is_dark, bool) else _is_dark
    colors = ctx.get("colors", {}) or {} if isinstance(ctx, dict) else {}
    ff = ctx.get("font_family") or "Microsoft YaHei"
    fs = ctx.get("font_size") or 14
    try:
        fs = int(fs)
    except (TypeError, ValueError):
        fs = 14
    return {
        "is_dark": is_dark,
        "ff": ff,
        "fs": fs,
        "text": colors.get("text_primary")
        or ("rgba(255,255,255,0.90)" if is_dark else "rgba(0,0,0,0.85)"),
        "secondary": colors.get("text_secondary")
        or ("rgba(255,255,255,0.58)" if is_dark else "rgba(0,0,0,0.55)"),
        "muted": colors.get("text_muted") or ("#8b98ad" if is_dark else "#666666"),
        "surface": colors.get("card_bg_solid") or ("#161e2d" if is_dark else "#ffffff"),
        "raised": colors.get("content_bg") or ("#1d2533" if is_dark else "#f5f5f5"),
        "border": colors.get("border")
        or ("rgba(128,128,128,0.25)" if is_dark else "rgba(0,0,0,0.18)"),
        "accent": colors.get("accent") or ("#66c6ff" if is_dark else "#0078d4"),
        "hover": colors.get("hover_bg")
        or ("rgba(255,255,255,0.10)" if is_dark else "rgba(0,0,0,0.08)"),
    }
```

- [ ] **Step 4: 写图标（两套 SVG，简洁文档图形）**

`plugins/docx-designer/icon.svg`（浅色主题，深色描边）：

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#2c3e50" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
  <path d="M14 3v6h6"/>
  <path d="M8 13h8M8 17h5"/>
</svg>
```

`plugins/docx-designer/icon_dark.svg`（同形，浅描边）：

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#dfe7f3" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
  <path d="M14 3v6h6"/>
  <path d="M8 13h8M8 17h5"/>
</svg>
```

- [ ] **Step 5: 静态校验**

Run: `python -m json.tool plugins/docx-designer/.drifox-plugin/plugin.json`
Expected: 输出 JSON 无报错

- [ ] **Step 6: Commit**

```bash
git add plugins/docx-designer/.drifox-plugin/plugin.json plugins/docx-designer/__init__.py plugins/docx-designer/ui/__init__.py plugins/docx-designer/ui/theme.py plugins/docx-designer/icon.svg plugins/docx-designer/icon_dark.svg
git commit -m "feat(docx-designer): 插件骨架（manifest/UI注册入口/主题色/图标）"
```

---

### Task 2: docx_parser 核心（段落/runs/标题/列表/锚点）

**Files:**
- Create: `plugins/docx-designer/ui/docx_parser.py`
- Test: `plugins/docx-designer/tests/test_parser.py`

- [ ] **Step 1: 写失败测试**

`plugins/docx-designer/tests/test_parser.py`：

```python
# -*- coding: utf-8 -*-
"""docx_parser 纯函数单测（无 Qt 依赖，系统 python + python-docx 直接跑）。

Run: python -m pytest plugins/docx-designer/tests/test_parser.py -v
"""
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN))

from ui.docx_parser import parse_document  # noqa: E402

DEMO_OMML = (
    PLUGIN.parent / "omml-docx" / "skills" / "omml-docx" / "scripts" / "demo_omml.docx"
)


@pytest.fixture(scope="session")
def sample_docx(tmp_path_factory):
    """基本样本：标题/正文/加粗斜体/列表/合并表格。"""
    from docx import Document

    doc = Document()
    doc.add_heading("测试文档", level=1)
    doc.add_heading("第一章", level=2)
    doc.add_paragraph("普通段落内容。")
    p = doc.add_paragraph()
    r1 = p.add_run("加粗")
    r1.bold = True
    r2 = p.add_run("普通")
    r2.italic = True
    doc.add_paragraph("列表项一", style="List Bullet")
    doc.add_paragraph("列表项二", style="List Bullet")
    doc.save(str(tmp_path_factory.mktemp("s") / "sample.docx"))
    return tmp_path_factory.mktemp("s") / "sample.docx"


def _save(doc, tmp_path, name="t.docx"):
    path = tmp_path / name
    doc.save(str(path))
    return path


def test_blocks_have_sequential_anchors(sample_docx):
    blocks = parse_document(str(sample_docx))
    assert [b["index"] for b in blocks] == list(range(len(blocks)))
    assert all(b["anchor"] == str(b["index"]) for b in blocks)


def test_heading_levels(sample_docx):
    blocks = parse_document(str(sample_docx))
    heads = [b for b in blocks if b["kind"] == "heading"]
    assert heads[0]["text"] == "测试文档" and heads[0]["level"] == 1
    assert heads[1]["text"] == "第一章" and heads[1]["level"] == 2


def test_runs_styles(sample_docx):
    blocks = parse_document(str(sample_docx))
    p = next(b for b in blocks if "加粗" in b["text"])
    bold = next(r for r in p["runs"] if r.get("text") == "加粗")
    assert bold["bold"] is True
    italic = next(r for r in p["runs"] if r.get("text") == "普通")
    assert italic["italic"] is True and italic["bold"] is False


def test_list_flag(sample_docx):
    blocks = parse_document(str(sample_docx))
    lists = [b for b in blocks if b.get("is_list")]
    assert len(lists) == 2
    assert lists[0]["text"] == "列表项一"


def test_table_gridspan_vmerge(tmp_path):
    from docx import Document

    doc = Document()
    tbl = doc.add_table(rows=3, cols=3)
    tbl.cell(0, 0).merge(tbl.cell(0, 1))  # 首行横跨 2 列 → colspan=2
    tbl.cell(1, 0).merge(tbl.cell(2, 0))  # 首列纵跨 2 行 → rowspan=2
    tbl.cell(0, 0).text = "跨列"
    tbl.cell(0, 2).text = "右上"
    tbl.cell(1, 1).text = "中"
    path = _save(doc, tmp_path)
    blocks = parse_document(str(path))
    t = next(b for b in blocks if b["kind"] == "table")
    row0 = t["rows"][0]
    assert row0[0]["colspan"] == 2
    assert row0[0]["text"] == "跨列"
    assert row0[0]["anchor"] == f"{t['index']}:r0c0"
    assert row0[1]["text"] == "右上"
    # 纵向合并：r1c0 rowspan=2，r2 首格被吞并
    r1c0 = t["rows"][1][0]
    assert r1c0["rowspan"] == 2 and r1c0["anchor"] == f"{t['index']}:r1c0"
    assert all(c["col"] != 0 for c in t["rows"][2])


def test_omml_math_extracted(tmp_path):
    """用 omml-docx 的构造器造一个含下标公式的文档。"""
    import sys as _sys

    sys.path.insert(0, str(PLUGIN.parent / "omml-docx" / "skills" / "omml-docx" / "scripts"))
    from omml_utils import build_docx, mixed_para, sub_math

    body = mixed_para([("text", "状态 "), ("math", sub_math("x", "t")), ("text", "。")])
    out = tmp_path / "m.docx"
    build_docx(body, str(out))
    blocks = parse_document(str(out))
    p = next(b for b in blocks if "状态" in b["text"])
    assert any("math" in r for r in p["runs"])
    assert "xt" in p["text"] or "x" in p["text"]


@pytest.mark.skipif(not DEMO_OMML.exists(), reason="demo_omml.docx 不存在")
def test_demo_omml_parses():
    blocks = parse_document(str(DEMO_OMML))
    maths = [b for b in blocks if any("math" in r for r in b["runs"])]
    assert len(maths) >= 3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest plugins/docx-designer/tests/test_parser.py -v`
Expected: FAIL（`ModuleNotFoundError: ui.docx_parser`）

- [ ] **Step 3: 实现 docx_parser.py**

`plugins/docx-designer/ui/docx_parser.py`：

```python
# -*- coding: utf-8 -*-
"""docx 解析：XML 流遍历 → 中间结构（纯函数，无 Qt 依赖）。

锚点约定：body 级块索引（str，0 起）；表格单元格 "idx:r{row}c{col}"（col 为网格列号）。
Block["runs"] 项三种形态：
- {"text": str, "bold"/"italic"/"underline": bool}
- {"image": data_uri}
- {"math": OMML XML 字符串}
已知简化：run 级样式只看直接 rPr（不做样式表继承）；嵌套表格降级忽略；
公式在 text 中以平文本呈现。
"""

import base64
import re

from docx import Document
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_HEADING_NAME_RE = re.compile(r"^(?:Heading|标题)\s*(\d+)$", re.I)
_HEADING_ID_RE = re.compile(r"^Heading\s*(\d+)$", re.I)


def parse_document(path):
    """解析 docx，返回 Block 列表（body 顺序，index 连续）。"""
    doc = Document(str(path))
    style_names = _style_name_map(doc)
    blocks = []
    body = doc.element.body
    for child in body.iterchildren():
        try:
            local = etree.QName(child).localname
        except ValueError:
            continue
        if local == "p":
            blocks.append(_parse_paragraph(child, doc, len(blocks), style_names))
        elif local == "tbl":
            blocks.append(_parse_table(child, doc, len(blocks), style_names))
    return blocks


def _style_name_map(doc):
    """styleId → 显示名（如 "Heading 1" / "标题 1"）。"""
    out = {}
    try:
        for s in doc.styles:
            try:
                out[s.style_id] = s.name or ""
            except Exception:
                continue
    except Exception:
        pass
    return out


def _heading_level(p, style_id, style_name):
    for pat, val in ((_HEADING_NAME_RE, style_name), (_HEADING_ID_RE, style_id)):
        m = pat.match((val or "").strip())
        if m:
            return max(1, min(4, int(m.group(1))))
    pPr = p.find(f"{{{W}}}pPr")
    if pPr is not None:
        o = pPr.find(f"{{{W}}}outlineLvl")
        if o is not None:
            try:
                return max(1, min(4, int(o.get(f"{{{W}}}val")) + 1))
            except (TypeError, ValueError):
                pass
    return 0


def _parse_paragraph(p, doc, index, style_names):
    pPr = p.find(f"{{{W}}}pPr")
    style_id = ""
    if pPr is not None:
        ps = pPr.find(f"{{{W}}}pStyle")
        if ps is not None:
            style_id = ps.get(f"{{{W}}}val") or ""
    style_name = style_names.get(style_id, style_id)
    level = _heading_level(p, style_id, style_name)
    runs, text = _parse_runs(p, doc)
    is_list = pPr is not None and pPr.find(f"{{{W}}}numPr") is not None
    has_image = any("image" in r for r in runs)
    if has_image and not text.strip():
        kind = "image"
    elif level:
        kind = "heading"
    else:
        kind = "paragraph"
    block = {
        "kind": kind,
        "index": index,
        "anchor": str(index),
        "style": style_name,
        "level": level,
        "text": text,
        "runs": runs,
        "is_list": is_list,
    }
    if kind == "image":
        block["image"] = next(r["image"] for r in runs if "image" in r)
    return block


def _parse_runs(p, doc):
    """段落 → (runs, 纯文本)。遍历直接子级与 hyperlink/sdtContent，公式与图片单独成项。"""
    runs = []
    texts = []

    def add_text(t, rpr):
        if not t:
            return
        runs.append({"text": t, **_run_flags(rpr)})
        texts.append(t)

    def walk(elem):
        for node in elem:
            try:
                q = etree.QName(node)
            except ValueError:
                continue
            if q.namespace == M and q.localname in ("oMath", "oMathPara"):
                xml = etree.tostring(node, encoding="unicode")
                runs.append({"math": xml})
                texts.append(_omml_plain_text(node))
            elif q.namespace != W:
                continue
            elif q.localname == "r":
                rpr = node.find(f"{{{W}}}rPr")
                blip = node.find(f".//{{{A}}}blip")
                if blip is not None:
                    data_uri = _image_data_uri(doc, blip.get(f"{{{R}}}embed"))
                    if data_uri:
                        runs.append({"image": data_uri})
                for sub in node:
                    try:
                        sq = etree.QName(sub)
                    except ValueError:
                        continue
                    if sq.namespace != W:
                        continue
                    if sq.localname == "t":
                        add_text(sub.text or "", rpr)
                    elif sq.localname == "br":
                        add_text("\n", None)
                    elif sq.localname == "tab":
                        add_text("\t", None)
            elif q.localname in ("hyperlink", "smartTag"):
                walk(node)
            elif q.localname == "sdt":
                content = node.find(f"{{{W}}}sdtContent")
                if content is not None:
                    walk(content)

    walk(p)
    return runs, "".join(texts)


def _run_flags(rpr):
    if rpr is None:
        return {"bold": False, "italic": False, "underline": False}

    def _on(tag):
        e = rpr.find(f"{{{W}}}{tag}")
        if e is None:
            return False
        v = e.get(f"{{{W}}}val")
        return v not in ("0", "false", "none", "")

    u = rpr.find(f"{{{W}}}u")
    underline = u is not None and (u.get(f"{{{W}}}val") or "single") not in ("none", "0", "false")
    return {"bold": _on("b"), "italic": _on("i"), "underline": underline}


def _image_data_uri(doc, rid):
    if not rid:
        return None
    try:
        part = doc.part.rels[rid].target_part
        blob = part.blob
        ct = part.content_type or "image/png"
        return f"data:{ct};base64,{base64.b64encode(blob).decode('ascii')}"
    except Exception:
        return None


def _omml_plain_text(omath):
    return "".join(t.text or "" for t in omath.iter(f"{{{M}}}t"))


def _parse_table(tbl, doc, index, style_names):
    raw_rows = []
    for r_i, tr in enumerate(tbl.findall(f"{{{W}}}tr")):
        row_cells = []
        col = 0
        for tc in tr.findall(f"{{{W}}}tc"):
            tcPr = tc.find(f"{{{W}}}tcPr")
            colspan = 1
            vmerge = None
            if tcPr is not None:
                gs = tcPr.find(f"{{{W}}}gridSpan")
                if gs is not None:
                    try:
                        colspan = max(1, int(gs.get(f"{{{W}}}val") or "1"))
                    except ValueError:
                        colspan = 1
                vm = tcPr.find(f"{{{W}}}vMerge")
                if vm is not None:
                    vmerge = vm.get(f"{{{W}}}val") or "continue"
            runs, text = _cell_content(tc, doc)
            row_cells.append(
                {
                    "text": text,
                    "runs": runs,
                    "colspan": colspan,
                    "rowspan": 1,
                    "col": col,
                    "anchor": f"{index}:r{r_i}c{col}",
                    "_vmerge": vmerge,
                }
            )
            col += colspan
        raw_rows.append(row_cells)

    # 纵向合并：restart 格向下吞 continue 格（col 对齐）
    for r_i, row in enumerate(raw_rows):
        for cell in row:
            if cell.get("_vmerge") == "restart":
                span = 1
                c = cell["col"]
                for r2 in range(r_i + 1, len(raw_rows)):
                    cont = next(
                        (x for x in raw_rows[r2]
                         if x.get("_vmerge") == "continue" and x["col"] == c),
                        None,
                    )
                    if cont is None:
                        break
                    span += 1
                    cont["_drop"] = True
                cell["rowspan"] = span

    final_rows = []
    for row in raw_rows:
        kept = []
        for cell in row:
            cell.pop("_vmerge", None)
            if cell.pop("_drop", None):
                continue
            kept.append(cell)
        final_rows.append(kept)

    return {
        "kind": "table",
        "index": index,
        "anchor": str(index),
        "style": "",
        "level": 0,
        "text": _table_plain_text(final_rows),
        "runs": [],
        "rows": final_rows,
        "is_list": False,
    }


def _cell_content(tc, doc):
    """单元格 → (首段 runs, 各段落文本 join)。"""
    texts = []
    first_runs = None
    for p in tc.findall(f"{{{W}}}p"):
        runs, text = _parse_runs(p, doc)
        if first_runs is None and runs:
            first_runs = runs
        if text.strip():
            texts.append(text)
    return (first_runs or []), "\n".join(texts)


def _table_plain_text(rows):
    lines = []
    for row in rows:
        lines.append(" | ".join(c["text"].replace("\n", " ") for c in row))
    return "\n".join(lines)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest plugins/docx-designer/tests/test_parser.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/docx-designer/ui/docx_parser.py plugins/docx-designer/tests/test_parser.py
git commit -m "feat(docx-designer): 解析器（段落/标题/列表/表格合并/图片/OMML）+ 单测"
```

---

### Task 3: html_renderer 核心（壳/CSS/段落/标题/runs）

**Files:**
- Create: `plugins/docx-designer/ui/html_renderer.py`
- Test: `plugins/docx-designer/tests/test_renderer.py`

- [ ] **Step 1: 写失败测试**

`plugins/docx-designer/tests/test_renderer.py`：

```python
# -*- coding: utf-8 -*-
"""html_renderer 纯函数单测。

Run: python -m pytest plugins/docx-designer/tests/test_renderer.py -v
"""
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN))

from ui.html_renderer import render_html  # noqa: E402


def _para(idx, text, **kw):
    b = {
        "kind": "paragraph", "index": idx, "anchor": str(idx),
        "style": "", "level": 0, "text": text, "runs": kw.get("runs") or [
            {"text": text, "bold": False, "italic": False, "underline": False}
        ],
        "is_list": kw.get("is_list", False),
    }
    return b


def test_html_contains_anchors():
    html = render_html([_para(0, "第一段"), _para(1, "第二段")])
    assert 'data-anchor="0"' in html and 'data-anchor="1"' in html
    assert "第一段" in html


def test_heading_tags():
    h = {
        "kind": "heading", "index": 0, "anchor": "0", "style": "Heading 1",
        "level": 1, "text": "大标题", "runs": [{"text": "大标题", "bold": True,
        "italic": False, "underline": False}], "is_list": False,
    }
    html = render_html([h])
    assert "<h1" in html and "</h1>" in html


def test_run_style_tags():
    p = _para(0, "x", runs=[
        {"text": "粗", "bold": True, "italic": False, "underline": False},
        {"text": "斜", "bold": False, "italic": True, "underline": False},
        {"text": "下", "bold": False, "italic": False, "underline": True},
    ])
    html = render_html([p])
    assert "<strong>粗</strong>" in html
    assert "<em>斜</em>" in html
    assert "<u>下</u>" in html


def test_table_col_row_span():
    t = {
        "kind": "table", "index": 5, "anchor": "5", "style": "", "level": 0,
        "text": "", "runs": [], "is_list": False,
        "rows": [[
            {"text": "跨", "runs": [], "colspan": 2, "rowspan": 1,
             "col": 0, "anchor": "5:r0c0"},
            {"text": "右", "runs": [], "colspan": 1, "rowspan": 1,
             "col": 2, "anchor": "5:r0c2"},
        ]],
    }
    html = render_html([t])
    assert 'colspan="2"' in html
    assert 'data-anchor="5:r0c2"' in html


def test_math_html_frac_sub_sup():
    from lxml import etree

    from ui.html_renderer import omml_to_html

    M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    frac_xml = (
        f'<m:oMath xmlns:m="{M}"><m:f><m:num><m:r><m:t>a</m:t></m:r></m:num>'
        f'<m:den><m:r><m:t>b</m:t></m:r></m:den></m:f>'
        f'<m:sSub><m:e><m:r><m:t>x</m:t></m:r></m:e>'
        f'<m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:oMath>'
    )
    html = omml_to_html(etree.fromstring(frac_xml.encode()))
    assert 'class="frac"' in html and "<sub>i</sub>" in html


def test_image_block_renders_img():
    p = _para(3, "", runs=[{"image": "data:image/png;base64,AAAA"}])
    p["kind"] = "image"
    p["image"] = "data:image/png;base64,AAAA"
    html = render_html([p])
    assert "<figure" in html and 'src="data:image/png;base64,AAAA"' in html


def test_pick_js_and_channel_script():
    html = render_html([_para(0, "x")])
    assert "qwebchannel.js" in html
    assert "docxbridge" in html
    assert "classList.contains('pick')" in html
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest plugins/docx-designer/tests/test_renderer.py -v`
Expected: FAIL（`ModuleNotFoundError: ui.html_renderer`）

- [ ] **Step 3: 实现 html_renderer.py**

`plugins/docx-designer/ui/html_renderer.py`：

```python
# -*- coding: utf-8 -*-
"""中间结构 → 完整 HTML（纯函数，无 Qt 依赖）。

页面固定白纸黑字（Word 文档本色），外围背景随主题传入；
拾取态由 body.pick 驱动 CSS hover 高亮；QWebChannel 桥对象名固定 docxbridge。
"""

from html import escape

from lxml import etree

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"

_HEADING_TAGS = {1: "h1", 2: "h2", 3: "h3", 4: "h4"}

_CSS = (
    ":root { --doc-fs: 15px; --accent: %(accent)s; } "
    "* { box-sizing: border-box; } "
    "html, body { margin: 0; padding: 0; } "
    "body { background: %(outer)s; font-family: 'Microsoft YaHei', sans-serif; } "
    ".page { max-width: 860px; margin: 20px auto; background: #ffffff; color: #1a1a1a; "
    "padding: 56px 72px; box-shadow: 0 2px 12px rgba(0,0,0,0.35); "
    "font-size: var(--doc-fs); line-height: 1.75; } "
    "h1, h2, h3, h4 { line-height: 1.4; margin: 0.9em 0 0.4em; } "
    "p { margin: 0.45em 0; } "
    "img { max-width: 100%%; height: auto; } "
    "figure { margin: 0.8em 0; text-align: center; } "
    "table { border-collapse: collapse; margin: 0.8em 0; width: 100%%; } "
    "td, th { border: 1px solid #b9b9b9; padding: 5px 9px; font-size: 0.92em; "
    "vertical-align: top; } "
    "body.pick [data-anchor] { cursor: crosshair; } "
    "body.pick [data-anchor]:hover { outline: 2px solid var(--accent); "
    "outline-offset: 1px; background: %(tint)s; } "
    ".mr { font-family: 'Cambria Math', 'Cambria', serif; font-style: italic; } "
    ".mrb { font-weight: bold; } "
    ".frac { display: inline-block; vertical-align: middle; text-align: center; margin: 0 2px; } "
    ".frac .num { display: block; border-bottom: 1px solid currentColor; padding: 0 4px; } "
    ".frac .den { display: block; padding: 0 4px; } "
    ".rad .radsig { border-top: 1px solid currentColor; padding: 0 2px; } "
    ".raddeg { font-size: 0.7em; vertical-align: super; margin-right: 1px; } "
    "sub, sup { font-size: 0.72em; } "
    ".nary .nlim { display: inline-flex; flex-direction: column; font-size: 0.72em; "
    "vertical-align: middle; line-height: 1.1; margin-left: -2px; } "
    ".mathbox { display: inline-block; border: 1px dashed #b8860b; background: #fffbe6; "
    "padding: 1px 6px; border-radius: 3px; font-family: 'Cambria Math', serif; } "
)

_BOOT_JS = (
    "if (window.qt && qt.webChannelTransport) {"
    " new QWebChannel(qt.webChannelTransport, function(ch) {"
    " window.__bridge = ch.objects.docxbridge; }); }"
)

_PICK_JS = (
    "document.addEventListener('click', function(ev){"
    " var el = ev.target.closest('[data-anchor]');"
    " if (!el || !document.body.classList.contains('pick')) return;"
    " ev.preventDefault(); ev.stopPropagation();"
    " el.scrollIntoView({block: 'center'});"
    " var r = el.getBoundingClientRect();"
    " if (window.__bridge) window.__bridge.pick("
    " el.getAttribute('data-anchor'), r.left, r.top, r.width, r.height,"
    " (el.textContent || '').replace(/\\s+/g, ' ').slice(0, 200)); });"
    "document.addEventListener('keydown', function(ev){"
    " if (ev.key === 'Escape' && window.__bridge) window.__bridge.escape(); });"
)


def render_html(blocks, *, outer="#1d2533", accent="#66c6ff"):
    tint = "rgba(102, 198, 255, 0.10)" if accent == "#66c6ff" else "rgba(0, 120, 212, 0.08)"
    body = "".join(_render_block(b) for b in blocks)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<style>{_CSS % {'accent': accent, 'outer': outer, 'tint': tint}}</style>"
        '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>'
        f"<script>{_BOOT_JS}</script>"
        f"</head><body><div class=\"page\">{body}</div>"
        f"<script>{_PICK_JS}</script></body></html>"
    )


def _render_block(b):
    a = escape(b["anchor"], quote=True)
    kind = b["kind"]
    if kind == "table":
        return _render_table(b)
    if kind == "image":
        return (
            f'<figure data-anchor="{a}">'
            f'<img src="{b["image"]}" alt=""></figure>'
        )
    tag = _HEADING_TAGS.get(b.get("level") or 0, "h4") if kind == "heading" else "p"
    inner = _render_runs(b.get("runs"))
    if b.get("is_list"):
        inner = '<span style="display:inline-block;width:1.4em;">&#8226;</span>' + inner
    return f'<{tag} data-anchor="{a}">{inner}</{tag}>'


def _render_runs(runs):
    out = []
    for r in runs or []:
        if "image" in r:
            out.append(f'<img src="{r["image"]}" style="vertical-align:middle;">')
        elif "math" in r:
            out.append(_render_math(r["math"]))
        else:
            t = escape(r.get("text", ""))
            if not t:
                continue
            t = t.replace("\n", "<br>").replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
            if r.get("bold"):
                t = f"<strong>{t}</strong>"
            if r.get("italic"):
                t = f"<em>{t}</em>"
            if r.get("underline"):
                t = f"<u>{t}</u>"
            out.append(t)
    return "".join(out)


def _render_table(b):
    a = escape(b["anchor"], quote=True)
    parts = [f'<table data-anchor="{a}">']
    for row in b["rows"]:
        parts.append("<tr>")
        for cell in row:
            attrs = f' data-anchor="{escape(cell["anchor"], quote=True)}"'
            if cell.get("colspan", 1) > 1:
                attrs += f' colspan="{cell["colspan"]}"'
            if cell.get("rowspan", 1) > 1:
                attrs += f' rowspan="{cell["rowspan"]}"'
            inner = _render_runs(cell.get("runs")) or escape(cell.get("text", ""))
            parts.append(f"<td{attrs}>{inner}</td>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def _render_math(xml_str):
    try:
        el = etree.fromstring(xml_str.encode())
    except etree.XMLSyntaxError:
        return '<span class="mathbox">[公式]</span>'
    return f'<span class="doc-math">{omml_to_html(el)}</span>'


def _kids(el):
    """递归拼接子元素（含直接文本）。"""
    if el is None:
        return ""
    out = el.text or ""
    for c in el:
        if isinstance(c.tag, str):
            out += omml_to_html(c)
        if c.tail:
            out += c.tail
    return out


def omml_to_html(el):
    """OMML 元素 → HTML/CSS 模拟公式。未覆盖结构降级为其子内容的拼接。"""
    try:
        q = etree.QName(el)
    except ValueError:
        return ""
    if q.namespace != M:
        return _kids(el)
    t = q.localname
    if t == "r":
        txt = "".join(x.text or "" for x in el.findall(f"{{{M}}}t"))
        if not txt:
            return ""
        sty = el.find(f"{{{M}}}rPr/{{{M}}}sty")
        bold = sty is not None and sty.get(f"{{{M}}}val") == "b"
        cls = "mr mrb" if bold else "mr"
        return f'<span class="{cls}">{escape(txt)}</span>'
    if t == "f":
        return (
            '<span class="frac">'
            f'<span class="num">{_kids(el.find(f"{{{M}}}num"))}</span>'
            f'<span class="den">{_kids(el.find(f"{{{M}}}den"))}</span></span>'
        )
    if t == "sSub":
        return f'{_kids(el.find(f"{{{M}}}e"))}<sub>{_kids(el.find(f"{{{M}}}sub"))}</sub>'
    if t == "sSup":
        return f'{_kids(el.find(f"{{{M}}}e"))}<sup>{_kids(el.find(f"{{{M}}}sup"))}</sup>'
    if t == "sSubSup":
        return (
            f'{_kids(el.find(f"{{{M}}}e"))}'
            f'<sub>{_kids(el.find(f"{{{M}}}sub"))}</sub>'
            f'<sup>{_kids(el.find(f"{{{M}}}sup"))}</sup>'
        )
    if t == "rad":
        deghide = el.find(f"{{{M}}}radPr/{{{M}}}degHide") is not None
        deg = "" if deghide else f'<span class="raddeg">{_kids(el.find(f"{{{M}}}deg"))}</span>'
        return f'<span class="rad">{deg}&#8730;<span class="radsig">{_kids(el.find(f"{{{M}}}e"))}</span></span>'
    if t == "nary":
        chr_el = el.find(f"{{{M}}}naryPr/{{{M}}}chr")
        sym = chr_el.get(f"{{{M}}}val") if chr_el is not None else "&#8747;"
        sub = el.find(f"{{{M}}}sub")
        sup = el.find(f"{{{M}}}sup")
        lims = ""
        if sub is not None or sup is not None:
            lims = (
                '<span class="nlim">'
                f'<span>{_kids(sub)}</span><span>{_kids(sup)}</span></span>'
            )
        return f'<span class="nary">{sym}{lims}</span>{_kids(el.find(f"{{{M}}}e"))}'
    if t == "d":
        beg = el.find(f"{{{M}}}dPr/{{{M}}}begChr")
        end = el.find(f"{{{M}}}dPr/{{{M}}}endChr")
        b = beg.get(f"{{{M}}}val") if beg is not None else "("
        e = end.get(f"{{{M}}}val") if end is not None else ")"
        inner = "".join(_kids(x) for x in el.findall(f"{{{M}}}e"))
        return f"{escape(b)}{inner}{escape(e)}"
    return _kids(el)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest plugins/docx-designer/tests/test_renderer.py -v`
Expected: 7 passed

- [ ] **Step 5: 全量回归（parser 不受影响）**

Run: `python -m pytest plugins/docx-designer/tests/ -v`
Expected: 全部 passed

- [ ] **Step 6: Commit**

```bash
git add plugins/docx-designer/ui/html_renderer.py plugins/docx-designer/tests/test_renderer.py
git commit -m "feat(docx-designer): HTML 渲染器（锚点/样式/表格跨行列/OMML 转 CSS 公式）+ 单测"
```

---

### Task 4: docx_window 窗口（工具栏/拖拽/缩放/QWebChannel 装配）

**Files:**
- Create: `plugins/docx-designer/ui/docx_window.py`
- Create: `plugins/docx-designer/ui/picker.py`

> 本机无 PyQt5 运行时，UI 任务用 py_compile + ruff 静态校验替代单测；行为验证在 Task 6 宿主实测。

- [ ] **Step 1: 实现 picker.py（Bridge + 拾取态 + 截图 + 回填）**

`plugins/docx-designer/ui/picker.py`：

```python
# -*- coding: utf-8 -*-
"""拾取模式：body.pick 切换 → JS 点击回传锚点与矩形 → 视口截图裁剪 → input.write 回填。

回填格式（同 browser design_mode 惯例）：
  📎 docx 拾取 #N [文件名]
  [段落 #12 | Heading 1] "文本预览"
  截图：<picks 绝对路径>
"""

import time
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSlot


class DocxBridge(QObject):
    """QWebChannel 桥：页面 JS → Python。挂在 window 上防 GC。"""

    def __init__(self, window):
        super().__init__(window)
        self._window = window

    @pyqtSlot(str, float, float, float, float, str)
    def pick(self, anchor, x, y, w, h, preview):
        self._window.on_element_picked(anchor, x, y, w, h, preview)

    @pyqtSlot()
    def escape(self):
        self._window.set_pick_mode(False)


def make_picks_dir():
    """截图目录：能力池 storage.data_dir（数据根，自拼 plugin_data/<name>/）。"""
    try:
        from app.plugins.sdk import caps_for

        root = Path(str(caps_for("storage.data_dir", plugin="docx-designer", surface="ui")))
        root = root / "plugin_data" / "docx-designer" / "picks"
    except Exception:
        root = Path.home() / ".drifox" / "plugin_data" / "docx-designer" / "picks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_input(text, count):
    """经能力池写输入框。首条覆盖，后续追加，全程不抢焦点。"""
    try:
        from app.plugins.sdk import caps_for

        write = caps_for("input.write", plugin="docx-designer", surface="ui")
    except Exception:
        write = None
    if write is None:
        return False
    try:
        write(text, append=count > 1, focus=False)
        return True
    except Exception:
        return False


def capture_view_rect(view, x, y, w, h):
    """view.grab() 全视口 → 按 CSS 矩形（dpr 换算）裁剪 → PNG 存盘。失败返回 None。"""
    pm = view.grab()
    if pm.isNull() or w <= 0 or h <= 0:
        return None
    dpr = view.devicePixelRatioF() or 1.0
    ix = max(0, min(int(x * dpr), pm.width() - 1))
    iy = max(0, min(int(y * dpr), pm.height() - 1))
    iw = min(int(w * dpr), pm.width() - ix)
    ih = min(int(h * dpr), pm.height() - iy)
    if iw <= 0 or ih <= 0:
        return None
    cropped = pm.copy(ix, iy, iw, ih)
    if cropped.isNull():
        return None
    path = make_picks_dir() / f"pick_{int(time.time() * 1000)}.png"
    return path if cropped.save(str(path), "PNG") else None


def format_pick(count, path_name, anchor, block, preview, shot_path):
    """组装回填文本。anchor 含 ":r" 即表格单元格。"""
    if ":r" in anchor:
        base, cell = anchor.split(":", 1)
        desc = f"[表格 #{base} 单元格 {cell}]"
    elif block is not None:
        style = block.get("style") or block.get("kind", "?")
        desc = f"[{block.get('kind', '?')} #{anchor} | {style}]"
    else:
        desc = f"[元素 #{anchor}]"
    lines = [f"📎 docx 拾取 #{count} [{path_name}]", f'{desc} "{preview}"']
    if shot_path:
        lines.append(f"截图：{shot_path}")
    return "\n".join(lines)
```

- [ ] **Step 2: 实现 docx_window.py**

`plugins/docx-designer/ui/docx_window.py`：

```python
# -*- coding: utf-8 -*-
"""文档设计窗口：工具栏（打开/拾取/缩放）+ QWebEngineView 预览 + 状态栏。

拾取交互：页面内 JS 点击监听（HTML 自生成，元素自带 data-anchor），
bridge 回传锚点与矩形，Python 裁剪截图并回填；Esc 由页面 keydown 上报。
"""

from pathlib import Path

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel

from .docx_parser import parse_document
from .html_renderer import render_html
from .picker import DocxBridge, capture_view_rect, format_pick, write_input
from .theme import theme_colors

_CURRENT_CARD = None


def _get_current_card():
    return _CURRENT_CARD


class DocxWindowCard(QWidget):
    """文档设计浮动卡片。widget 契约：__init__(parent=None) + show_card + set_context_provider。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        global _CURRENT_CARD
        _CURRENT_CARD = self

        self._context_provider = None
        self._blocks = []
        self._current_path = ""
        self._pick_on = False
        self._count = 0
        self._fs = 15
        self._setup_ui()
        self._setup_webchannel()
        self.setAcceptDrops(True)
        try:
            from app.utils.theme_manager import theme_manager

            theme_manager.register_refresh_target(self)
        except Exception:
            pass

    def set_context_provider(self, provider):
        self._context_provider = provider

    def show_card(self):
        self.refresh_theme()
        self.setVisible(True)

    def refresh_theme(self):
        self._apply_theme()

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumSize(560, 420)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(10, 8, 10, 8)
        top.setSpacing(8)
        self._name_label = QLabel("未打开文档")
        top.addWidget(self._name_label, 1)
        self._btn_open = QPushButton("打开")
        self._btn_open.clicked.connect(self._on_open_clicked)
        self._btn_pick = QPushButton("拾取")
        self._btn_pick.clicked.connect(self.toggle_pick)
        self._btn_smaller = QPushButton("A−")
        self._btn_smaller.clicked.connect(lambda: self._zoom(-1))
        self._btn_bigger = QPushButton("A+")
        self._btn_bigger.clicked.connect(lambda: self._zoom(1))
        for b in (self._btn_open, self._btn_pick, self._btn_smaller, self._btn_bigger):
            top.addWidget(b)
        root.addLayout(top)

        self._view = QWebEngineView(self)
        root.addWidget(self._view, 1)

        self._status = QLabel("拖入 .docx 文件，或点「打开」")
        self._status.setContentsMargins(10, 4, 10, 6)
        root.addWidget(self._status)
        self._apply_theme()

    def _setup_webchannel(self):
        self._bridge = DocxBridge(self)
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("docxbridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

    def _apply_theme(self):
        c = theme_colors(self)
        accent_hex = "#66c6ff" if c["is_dark"] else "#0078d4"
        self._accent_hex = accent_hex
        self.setStyleSheet(
            f"DocxWindowCard {{ background: {c['surface']}; }}"
            f"QLabel {{ color: {c['text']}; font-size: 12px; }}"
            f"QPushButton {{ background: {c['raised']}; border: 1px solid {c['border']};"
            f" border-radius: 6px; color: {c['text']}; padding: 5px 14px; }}"
            f"QPushButton:hover {{ background: {c['hover']}; }}"
            f"QPushButton:checked {{ border-color: {accent_hex}; }}"
        )
        self._outer_bg = c["raised"]

    # ── 打开文档 ──

    def _on_open_clicked(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 Word 文档", "", "Word 文档 (*.docx)")
        if path:
            self.open_path(path)

    def open_path(self, path):
        """解析并渲染 docx。供工具侧调用；返回是否成功。"""
        p = Path(path)
        if not p.is_file():
            self._set_status(f"文件不存在: {path}")
            return False
        if p.suffix.lower() != ".docx":
            self._set_status("仅支持 .docx 文件")
            return False
        try:
            blocks = parse_document(str(p))
        except Exception as e:
            self._set_status(f"解析失败: {e}")
            return False
        self._blocks = blocks
        self._current_path = str(p)
        self._count = 0
        if self._pick_on:
            self._pick_on = False
        html = render_html(blocks, outer=self._outer_bg, accent=self._accent_hex)
        self._view.setHtml(html, QUrl("http://docx-designer.local/"))
        self._name_label.setText(p.name)
        self._set_status(f"已打开 {p.name}（{len(blocks)} 个块），点「拾取」开始选取元素")
        return True

    # ── 拾取 ──

    def toggle_pick(self):
        self.set_pick_mode(not self._pick_on)

    def set_pick_mode(self, on):
        self._pick_on = bool(on)
        flag = "true" if on else "false"
        self._view.page().runJavaScript(f"document.body.classList.toggle('pick', {flag});")
        self._btn_pick.setDown(on)
        if on:
            self._set_status("拾取模式：点击文档元素回填输入框（Esc 退出）")
        else:
            self._set_status("拾取模式已退出" if self._count else "拾取模式已退出（未拾取元素）")

    def on_element_picked(self, anchor, x, y, w, h, preview):
        shot = capture_view_rect(self._view, x, y, w, h)
        self._count += 1
        text = format_pick(
            self._count,
            Path(self._current_path).name if self._current_path else "?",
            anchor,
            self._block_by_anchor(anchor),
            preview,
            str(shot) if shot else None,
        )
        if write_input(text, self._count):
            self._set_status(f"已回填第 {self._count} 个元素（Esc 退出）")
        else:
            self._set_status("已拾取，但输入框写入失败（能力 input.write 不可用）")

    def _block_by_anchor(self, anchor):
        if ":r" in anchor:
            return None
        idx_s = anchor.split(":", 1)[0]
        for b in self._blocks:
            if b["anchor"] == idx_s:
                return b
        return None

    # ── 缩放 ──

    def _zoom(self, delta):
        self._fs = max(11, min(24, self._fs + delta))
        self._view.page().runJavaScript(
            f"document.documentElement.style.setProperty('--doc-fs', '{self._fs}px');"
        )
        self._set_status(f"正文字号 {self._fs}px")

    def _set_status(self, text):
        self._status.setText(text)

    # ── 拖拽 ──

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(".docx"):
                self.open_path(p)
                break

    def dragMoveEvent(self, event):
        event.acceptProposedAction()
```

- [ ] **Step 3: 静态校验**

Run: `python -m py_compile plugins/docx-designer/ui/docx_window.py plugins/docx-designer/ui/picker.py && ruff check plugins/docx-designer/ui/`
Expected: 无输出（ruff 未安装时以 py_compile 为准）

- [ ] **Step 4: Commit**

```bash
git add plugins/docx-designer/ui/docx_window.py plugins/docx-designer/ui/picker.py
git commit -m "feat(docx-designer): 预览窗口（工具栏/拖拽/缩放/QWebChannel）+ 拾取回填"
```

---

### Task 5: tools 注册（open_docx）

**Files:**
- Create: `plugins/docx-designer/tools/docx_tools.py`

- [ ] **Step 1: 实现工具**

`plugins/docx-designer/tools/docx_tools.py`：

```python
# -*- coding: utf-8 -*-
"""open_docx 工具：让模型打开 docx 设计预览窗口。

impl 通过 tool_ctx 获取上下文；UI 联动走 UIPluginRegistry（同 autoloop 模式）。
已知约束：若宿主将工具 impl 调度到非主线程，此处需改主线程派发
（参考 browser/ui/control_server.py 的主线程派发器）。
"""

from pathlib import Path

from app.tools.result import ToolResult


def _open_docx_impl(tool_ctx, **kwargs):
    path = (kwargs.get("path") or "").strip()
    if not path:
        return ToolResult(False, content="缺少 path 参数（.docx 文件路径）")
    p = Path(path).expanduser()
    if not p.is_file():
        return ToolResult(False, content=f"文件不存在: {path}")
    if p.suffix.lower() != ".docx":
        return ToolResult(False, content=f"仅支持 .docx，收到: {p.suffix}")
    try:
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        registry = UIPluginRegistry.get_instance()
        registry.toggle_floating_card(
            "docx-designer", main_widget=tool_ctx.get("main_widget")
        )
        card = registry.get_card_widget("docx-designer")
        if card is None:
            return ToolResult(False, content="预览窗口初始化失败")
        ok = card.open_path(str(p))
        if ok:
            return ToolResult(
                True,
                content=(
                    f"已打开预览: {p.name}\n"
                    "窗口内点「拾取」按钮后点击文档元素，锚点+文本+截图会回填到输入框。"
                ),
            )
        return ToolResult(False, content=f"解析失败: {p.name}")
    except Exception as e:
        return ToolResult(False, content=f"打开预览失败: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "open_docx",
        "description": (
            "打开 docx 文档设计预览窗口：解析 Word 文档并渲染可拾取预览，"
            "用户在窗口内点「拾取」后点击任意段落/表格/公式/图片，"
            "元素的锚点+文本+截图会自动回填到输入框，供你针对精确元素做修改。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "docx 文件绝对路径"},
            },
            "required": ["path"],
        },
    },
}


def register(registry):
    """PluginToolLoader 注册入口。"""
    registry.register(
        "open_docx", _SCHEMA, impl=_open_docx_impl,
        danger="safe", cn_name="打开文档预览",
        group="文档", description="打开 docx 设计预览窗口（可拾取元素回填）",
    )
```

- [ ] **Step 2: 静态校验**

Run: `python -m py_compile plugins/docx-designer/tools/docx_tools.py && ruff check plugins/docx-designer/tools/`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add plugins/docx-designer/tools/docx_tools.py
git commit -m "feat(docx-designer): open_docx 工具（模型侧打开预览窗口）"
```

---

### Task 6: README + 全量验证 + 同步宿主目录 + 宿主实测

**Files:**
- Create: `plugins/docx-designer/README.md`

- [ ] **Step 1: 写 README**

`plugins/docx-designer/README.md`：

```markdown
# docx-designer

docx 文档设计模式 — 独立窗口预览 Word 文档，页内拾取元素，锚点+文本+截图回填输入框，让大模型针对精确元素做修改。

## 功能

- **预览**：python-docx XML 流遍历解析 → 自生成 HTML（QWebEngineView 渲染）
  - 标题层级 / 段落 / 粗斜体下划线 / 列表
  - 表格（colspan / rowspan，vMerge + gridSpan）
  - 内嵌图片（data URI）
  - OMML 公式 HTML/CSS 模拟（上下标/分数/根号/nary，复杂结构降级带边框文本块）
- **拾取**：点「拾取」进入拾取态（hover 高亮 + crosshair），点击元素即回填：
  - 元素锚点（body 块索引，表格单元格 `idx:r{n}c{n}`）
  - 元素类型 / 样式 / 文本预览（≤200 字符）
  - 元素区域截图 PNG（存 `plugin_data/docx-designer/picks/`）
  - 连续拾取连续追加，Esc 退出，全程不抢输入框焦点
- **入口**：`/docx-designer` 命令、欢迎页插件入口、`open_docx(path)` 工具、拖拽 docx 到窗口

## 架构

```
ui/docx_parser.py   XML 流遍历 → 中间结构 Block（纯函数，可单测）
ui/html_renderer.py Block → HTML（data-anchor + QWebChannel 桥，纯函数，可单测）
ui/docx_window.py   窗口（工具栏/拖拽/缩放/状态栏）
ui/picker.py        Bridge + 拾取态 + 截图裁剪 + input.write 回填
tools/docx_tools.py open_docx 工具
```

锚点契约：`Block["anchor"]` = body 级块索引（0 起）；表格单元格 `"<idx>:r{row}c{col}"`（col 为网格列号）。文档不修改则锚点稳定；模型按锚点在 python-docx 中定位元素（遍历 body 第 N 个 `w:p`/`w:tbl`）。

## 测试

```bash
python -m pytest plugins/docx-designer/tests/ -v
```

## 已知简化

- 窗口为浮动卡片单例（`register_floating_card` 机制约束），同一时刻一篇文档；再打开新文档即替换当前预览
- run 级样式只读直接 rPr，不做样式表继承推断
- 嵌套表格内容降级忽略
- 工具侧打开窗口若遇非主线程调度需改主线程派发
```

- [ ] **Step 2: 全量测试**

Run: `python -m pytest plugins/docx-designer/tests/ -v`
Expected: 全部 passed

- [ ] **Step 3: 静态校验全模块**

Run: `python -m py_compile plugins/docx-designer/__init__.py plugins/docx-designer/ui/__init__.py plugins/docx-designer/ui/theme.py plugins/docx-designer/ui/docx_parser.py plugins/docx-designer/ui/html_renderer.py plugins/docx-designer/ui/docx_window.py plugins/docx-designer/ui/picker.py plugins/docx-designer/tools/docx_tools.py && ruff check plugins/docx-designer/`
Expected: 无输出

- [ ] **Step 4: manifest 校验（须 3.10 侧跑）**

Run: `python tools/validate_plugins.py plugins/docx-designer`（若无此脚本则 `python -c "import json,jsonschema; jsonschema.validate(json.load(open('plugins/docx-designer/.drifox-plugin/plugin.json',encoding='utf-8')), json.load(open('schemas/plugin.schema.json',encoding='utf-8')))"`)
Expected: PASS / 无 ValidationError

- [ ] **Step 5: 同步宿主目录 + 清 pyc**

```bash
robocopy plugins\docx-designer C:\Users\mading\.drifox\plugins\docx-designer /E /NFL /NDL /NJH /NJS
powershell -Command "Get-ChildItem -Recurse C:\Users\mading\.drifox\plugins\docx-designer -Include *.pyc -Force | Remove-Item -Force"
```
Expected: robocopy 退出码 0-7 均为成功；pyc 清空

> 同步后需在宿主内重载插件（或重启宿主）再实测：打开带标题/表格/公式/图片的 docx → 拾取段落确认回填文本与截图路径 → Esc 退出。

- [ ] **Step 6: Commit**

```bash
git add plugins/docx-designer/README.md
git commit -m "docs(docx-designer): README（功能/架构/锚点契约/已知简化）"
```

- [ ] **Step 7: 市场收尾（用户确认功能后）**

- 跑 `python tools/generate_marketplace.py`，单独提交
- CHANGELOG 增补条目，单独提交
- 版本若改，同步 plugin.json 的 `version`
