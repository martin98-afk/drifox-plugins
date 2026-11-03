# -*- coding: utf-8 -*-
"""redirect_config pdf 拦截判定单测（无 Qt 依赖分支）。

Run: python -m pytest plugins/browser/tests/test_redirect_pdf.py -v
"""
import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]


def _load_module(mod_name, filename):
    """按文件路径加载插件 ui 模块（避免与其它插件的顶层 ui 包名冲突）"""
    spec = importlib.util.spec_from_file_location(mod_name, PLUGIN / "ui" / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_rc = _load_module("browser_redirect_config", "redirect_config.py")
_is_local_doc = _rc._is_local_doc
_is_local_pdf = _rc._is_local_pdf
_HTML_SUFFIX_RE = _rc._HTML_SUFFIX_RE


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path):
    _rc.reset_config_for_test(tmp_path / "browser-redirect.json")


def test_local_pdf_detected():
    assert _is_local_pdf("D:/docs/report.pdf")
    assert _is_local_pdf(r"C:\a b\file.PDF")
    assert _is_local_pdf("file:///C:/x.pdf")


def test_non_pdf_rejected():
    assert not _is_local_pdf("D:/docs/report.docx")
    assert not _is_local_pdf("https://example.com/a.pdf")  # 网页 URL 不算本地
    assert not _is_local_pdf("ftp://host/a.pdf")
    assert not _is_local_pdf("")


def test_should_intercept_pdf(tmp_path):
    pdf = str(tmp_path / "a.pdf")
    assert _rc.should_intercept(pdf, "startfile")
    _rc.reset_config_for_test(tmp_path / "c.json")
    _rc.get_config().set("intercept_pdf", False)
    assert not _rc.should_intercept(pdf, "startfile")


def test_should_intercept_global_off(tmp_path):
    _rc.reset_config_for_test(tmp_path / "g.json")
    _rc.get_config().set("enabled", False)
    assert not _rc.should_intercept("D:/a.pdf", "startfile")


def test_is_local_doc_html_regression():
    # 重构后 html 判定行为不变
    assert _rc._is_local_doc("D:/a.html", _HTML_SUFFIX_RE)
    assert _rc._is_local_doc("D:/a.htm", _HTML_SUFFIX_RE)
    assert not _rc._is_local_doc("https://x.com/a.html", _HTML_SUFFIX_RE)
