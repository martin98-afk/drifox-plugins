# -*- coding: utf-8 -*-
"""Mermaid 行号锚点解析与渲染单测（无 Qt 依赖）。

Run: python -m pytest plugins/file-designer/tests/test_mermaid_anchor.py -q --noconftest
"""
import importlib
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]

@pytest.fixture(scope="module", autouse=True)
def _ui_package():
    if str(PLUGIN) not in sys.path:
        sys.path.insert(0, str(PLUGIN))
    for key in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        del sys.modules[key]

def _mod(name):
    return importlib.import_module(f"ui.{name}")

SRC = """flowchart TD
  A[开始] --> B{是否登录?}
  B -->|是| C[进入工作台]
  B -->|否| D[跳转登录]
  C --> E[结束]
  D --> B
"""

@pytest.fixture
def mmd(tmp_path):
    p = tmp_path / "flow.mmd"
    p.write_text(SRC, encoding="utf-8")
    return p

def test_diagram_type_and_lines(mmd):
    mp = _mod("mermaid_parser")
    m = mp.parse_mermaid(str(mmd))
    assert m["mode"] == "mermaid" and "flowchart TD" in m["diagram_type"]
    assert len(m["lines"]) == 6
    assert m["lines"][2].strip().startswith("B -->|是|")

def test_line_anchor_lookup(mmd):
    mp = _mod("mermaid_parser")
    m = mp.parse_mermaid(str(mmd))
    b = m["lookup"]("L3")
    assert b["mode"] == "mermaid" and b["kind"] == "mermaid_line"
    assert "B -->|是| C" in b["text"]
    assert b["diagram_type"].startswith("flowchart")
    assert " 3 | " in b["context"] and " 1 | " in b["context"]
    assert m["lookup"]("L999") is None and m["lookup"]("bad") is None

def test_node_reverse_lookup(mmd):
    mp = _mod("mermaid_parser")
    m = mp.parse_mermaid(str(mmd))
    assert "A" in m["nodes"] and m["nodes"]["A"]["first_line"] == 2
    assert m["lookup"]("node:A")["anchor"] == "L2"
    assert mp.anchor_for_node(m, "C") == "L3"
    assert mp.anchor_for_node(m, "不存在") is None

def test_other_diagram_types(tmp_path):
    mp = _mod("mermaid_parser")
    p = tmp_path / "seq.mmd"
    p.write_text("sequenceDiagram\n  Alice->>Bob: Hi\n  Bob-->>Alice: Yo\n", encoding="utf-8")
    m = mp.parse_mermaid(str(p))
    assert m["diagram_type"].startswith("sequenceDiagram")
    assert "Alice->>Bob: Hi" in m["lookup"]("L2")["text"]

def test_utf8_and_bom(tmp_path):
    mp = _mod("mermaid_parser")
    p = tmp_path / "cn.mmd"
    p.write_bytes("graph LR\n  甲[中文] --> 乙[节点]\n".encode("utf-8-sig"))
    m = mp.parse_mermaid(str(p))
    assert "甲[中文]" in m["lookup"]("L2")["text"]

def test_missing_file():
    mp = _mod("mermaid_parser")
    with pytest.raises(FileNotFoundError):
        mp.parse_mermaid("__no_such_mmd_file__.mmd")

def test_renderer_html_contract(mmd):
    mp, mr = _mod("mermaid_parser"), _mod("mermaid_renderer")
    hr = _mod("html_renderer")
    m = mp.parse_mermaid(str(mmd))
    html = mr.render_mermaid_html(m, restored=[{"anchor": "L3", "comment": "补分支", "seq": 1}])
    assert 'qrc:///qtwebchannel/qwebchannel.js' in html
    assert hr._BOOT_JS in html and hr._PICK_JS in html and hr._ANNOTATE_JS in html
    assert 'id="note-box"' in html
    assert 'data-anchor="L3"' in html and 'B --&gt;|是| C' in html
    assert 'mermaid.initialize' in html and 'window.__mermaidSrc' in html
    assert '补分支' in html

def test_renderer_inlines_library(mmd):
    mp, mr = _mod("mermaid_parser"), _mod("mermaid_renderer")
    html = mr.render_mermaid_html(mp.parse_mermaid(str(mmd)))
    # 3.3MB UMD 应内联进页面（离线可用）
    assert len(html) > 3_000_000
    assert "mermaid.min.js 未随插件安装" in html or "JM.mermaid" in html

def test_renderer_escapes_html(tmp_path):
    mp, mr = _mod("mermaid_parser"), _mod("mermaid_renderer")
    p = tmp_path / "x.mmd"
    p.write_text('graph TD\n  A[<script>alert(1)</script>]\n', encoding="utf-8")
    html = mr.render_mermaid_html(mp.parse_mermaid(str(p)))
    # 源码里 script 标签必须转义（内联库本身也含 script 文本，故只检查 srow 段）
    srow = html.split('class="src"')[1].split("</div></div>")[0] if 'class="src"' in html else ""
    assert "&lt;script&gt;" in srow
