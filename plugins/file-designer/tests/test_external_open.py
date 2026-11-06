# -*- coding: utf-8 -*-
"""external_open 多格式目标判定单测（无 Qt 依赖）。

Run: python -m pytest plugins/file-designer/tests/test_external_open.py -v
"""
import importlib.util
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]


def _load_module(mod_name, filename):
    """按文件路径加载插件 ui 模块（避免与其它插件的顶层 ui 包名冲突）"""
    spec = importlib.util.spec_from_file_location(mod_name, PLUGIN / "ui" / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_external_open = _load_module("file_designer_external_open", "external_open.py")
_file_local_path = _external_open._file_local_path


def test_plain_path(tmp_path):
    p = tmp_path / "doc.docx"
    got = _file_local_path(str(p))
    assert got is not None and got.name == "doc.docx"


def test_suffix_case_insensitive(tmp_path):
    p = tmp_path / "doc.DOCX"
    assert _file_local_path(str(p)) is not None


def test_file_url_with_escape(tmp_path):
    got = _file_local_path("file:///C:/my%20docs/a.docx")
    assert got is not None
    assert got.name == "a.docx"
    assert "my docs" in str(got)


def test_rejects_other_suffix(tmp_path):
    assert _file_local_path(str(tmp_path / "a.doc")) is None
    assert _file_local_path(str(tmp_path / "a.pdf")) is None
    assert _file_local_path(str(tmp_path / "a.txt")) is None
    assert _file_local_path("") is None
    assert _file_local_path(None) is None


def test_new_formats_accepted(tmp_path):
    for name in ("a.xmind", "a.xlsx", "a.xlsm", "a.csv", "a.mmd", "a.mermaid", "a.pptx"):
        assert _file_local_path(str(tmp_path / name)) is not None, name

def test_rejects_relative_and_unc():
    assert _file_local_path("relative/a.docx") is None
    assert _file_local_path("http://x.com/a.docx") is None
    # UNC 路径合法
    assert _file_local_path("//server/share/a.docx") is not None
