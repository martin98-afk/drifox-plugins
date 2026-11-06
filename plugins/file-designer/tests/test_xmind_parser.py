# -*- coding: utf-8 -*-
"""XMind 解析/渲染单测（无 Qt 依赖）。

Run: python -m pytest plugins/file-designer/tests/test_xmind_parser.py -q --noconftest
"""
import importlib
import json
import sys
import zipfile
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

def _json_zip(path):
    tree = {
        "id": "sheet0", "title": "产品规划",
        "rootTopic": {
            "id": "root", "title": "产品规划", "labels": ["重点"],
            "notes": {"plain": {"content": "总纲"}},
            "children": {"attached": [
                {"id": "a", "title": "Q3", "children": {"attached": [
                    {"id": "a1", "title": "登录改版", "notes": {"plain": {"content": "兼容 SSO"}}},
                    {"id": "a2", "title": "支付重构"},
                ]}},
                {"id": "b", "title": "Q4", "children": {"attached": [
                    {"id": "b1", "title": "搜索优化"},
                ]}},
            ]},
        },
    }
    with zipfile.ZipFile(str(path), "w") as z:
        z.writestr("content.json", json.dumps([tree], ensure_ascii=False))
        z.writestr("META-INF/manifest.xml", "<manifest/>")
    return path

def _xml_zip(path):
    content = """<?xml version="1.0" encoding="UTF-8"?>
<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0">
  <sheet id="s0" title="老版导图">
    <topic id="r">
      <title>根节点</title>
      <children><topics type="attached">
        <topic id="c1"><title>分支甲</title>
          <notes><plain>甲的备注</plain></notes>
          <children><topics type="attached">
            <topic id="g1"><title>孙节点</title></topic>
          </topics></children>
        </topic>
        <topic id="c2"><title>分支乙</title></topic>
      </topics></children>
    </topic>
  </sheet>
</xmap-content>"""
    with zipfile.ZipFile(str(path), "w") as z:
        z.writestr("content.xml", content.encode("utf-8"))
    return path

def test_content_json_tree_and_anchors(tmp_path):
    xp = _mod("xmind_parser")
    m = xp.parse_xmind(str(_json_zip(tmp_path / "a.xmind")))
    assert m["mode"] == "xmind" and not m["truncated"]
    assert len(m["sheets"]) == 1
    root = m["sheets"][0]["root"]
    assert root["anchor"] == "s0/n/0" and root["title"] == "产品规划"
    assert root["labels"] == ["重点"] and root["note"] == "总纲"
    assert [c["anchor"] for c in root["children"]] == ["s0/n/0.0", "s0/n/0.1"]
    assert m["lookup"]("s0/n/0.0.1")["text"] == "支付重构"
    assert m["lookup"]("s9/n/0") is None

def test_lookup_node_fields(tmp_path):
    xp = _mod("xmind_parser")
    m = xp.parse_xmind(str(_json_zip(tmp_path / "a.xmind")))
    b = m["lookup"]("s0/n/0.0.0")
    assert b["mode"] == "xmind" and b["kind"] == "xmind_node"
    assert b["text"] == "登录改版" and b["note"] == "兼容 SSO"
    assert b["path"] == ["产品规划", "Q3", "登录改版"]
    assert set(b["siblings"]) == {"登录改版", "支付重构"} - {"登录改版"}

def test_content_xml_fallback(tmp_path):
    xp = _mod("xmind_parser")
    m = xp.parse_xmind(str(_xml_zip(tmp_path / "legacy.xmind")))
    assert m["sheets"][0]["name"] == "老版导图"
    assert m["lookup"]("s0/n/0.0.0")["text"] == "孙节点"
    assert m["lookup"]("s0/n/0")["note"] == ""
    assert "甲的备注" in m["lookup"]("s0/n/0.0")["note"]

def test_bad_zip_reports_clear_error(tmp_path):
    xp = _mod("xmind_parser")
    p = tmp_path / "bad.xmind"
    with zipfile.ZipFile(str(p), "w") as z:
        z.writestr("readme.txt", "nothing")
    with pytest.raises(ValueError, match="content.json"):
        xp.parse_xmind(str(p))
    with pytest.raises(FileNotFoundError):
        xp.parse_xmind(str(tmp_path / "missing.xmind"))

def test_node_limit_truncates(tmp_path):
    xp = _mod("xmind_parser")
    tree = {
        "title": "大图",
        "rootTopic": {
            "title": "根",
            "children": {"attached": [
                {"title": "N%d" % i,
                 "children": {"attached": [{"title": "C%d-%d" % (i, j)} for j in range(20)]}}
                for i in range(60)
            ]},
        },
    }
    p = tmp_path / "big.xmind"
    with zipfile.ZipFile(str(p), "w") as z:
        z.writestr("content.json", json.dumps([tree], ensure_ascii=False))
    m = xp.parse_xmind(str(p))
    assert m["truncated"] is True

def test_renderer_html_contract(tmp_path):
    xp, xr = _mod("xmind_parser"), _mod("xmind_renderer")
    hr = _mod("html_renderer")
    m = xp.parse_xmind(str(_json_zip(tmp_path / "a.xmind")))
    html = xr.render_xmind_html(m, restored=[{"anchor": "s0/n/0", "comment": "改这里", "seq": 1}])
    assert 'qrc:///qtwebchannel/qwebchannel.js' in html
    assert hr._BOOT_JS in html and hr._PICK_JS in html and hr._ANNOTATE_JS in html
    assert 'id="note-box"' in html
    assert 'data-anchor="s0/n/0.0.0"' in html
    assert '<svg' in html and '登录改版' in html
    assert '改这里' in html

def test_renderer_escapes_html(tmp_path):
    xp, xr = _mod("xmind_parser"), _mod("xmind_renderer")
    tree = {"title": "s", "rootTopic": {"title": "<script>alert(1)</script>",
            "children": {"attached": [{"title": 'A & "B"'}]}}}
    p = tmp_path / "esc.xmind"
    with zipfile.ZipFile(str(p), "w") as z:
        z.writestr("content.json", json.dumps([tree], ensure_ascii=False))
    html = xr.render_xmind_html(xp.parse_xmind(str(p)))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html and 'A &amp; &quot;B&quot;' in html
