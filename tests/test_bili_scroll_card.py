"""B站值班卡片：布局、状态和异步入口回归，不访问网络。"""
import importlib.util
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")
pytest.importorskip("qfluentwidgets")
from PyQt5.QtCore import QEventLoop, QTimer, Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QApplication, QBoxLayout


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def card(app):
    path = Path(__file__).resolve().parents[1] / "plugins/bili-scroll/ui/cards.py"
    spec = importlib.util.spec_from_file_location("bili_card_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    widget = module.BiliScrollCard()
    yield widget
    widget.deleteLater()
    app.processEvents()


def snapshot(**overrides):
    data = {
        "status": {
            "数据目录": "/tmp/" + "long-path/" * 40,
            "自带依赖": "就绪（随插件自带）",
            "B站工具": "MCP 已注入 20 个 B站工具",
            "扫码凭证": "已存在（登录过）",
            "今日已挑/配额": "2 / 6",
            "自动评论": "关",
            "自动跑": "午间 夜间",
            "最近判重": [{"title": "不应出现在诊断中的视频字典"}],
        },
        "report": "# 今日精选\n\n### BV123\n\n**推荐理由**：值得一看。",
        "seen_rows": [{"title": "<b>不是 HTML 标题</b>" * 20,
                       "up": "测试 UP", "date": "2026-11-17",
                       "bvid": "BV123", "status": "挑了"}],
    }
    data.update(overrides)
    return data


def test_summary_and_diagnostics_are_separate(card):
    card._render_snapshot(snapshot())
    assert card._metric_values["quota"].text() == "2 / 6"
    assert card._metric_values["credential"].text() == "已保存"
    assert "未校验" in card._metric_values["credential"].toolTip()
    assert card._diagnostics.isHidden()
    assert "long-path" in card._diagnostics.toPlainText()
    assert "不应出现在诊断" not in card._diagnostics.toPlainText()
    card._details_btn.click()
    assert not card._diagnostics.isHidden()


def test_markdown_and_escaped_video_rows(card):
    card._render_snapshot(snapshot())
    assert card._report_stack.currentIndex() == 1
    assert "**推荐理由**" not in card._report_view.toPlainText()
    assert "<b>不是 HTML 标题</b>" in card._seen_view.toPlainText()
    assert "测试 UP" in card._seen_view.toPlainText()
    card._render_snapshot(snapshot(report="", seen_rows=[]))
    assert card._report_stack.currentIndex() == 0
    assert card._seen_stack.currentIndex() == 0


@pytest.mark.parametrize("width, direction, columns", [
    (1100, QBoxLayout.LeftToRight, 4),
    (620, QBoxLayout.TopToBottom, 2),
    (460, QBoxLayout.TopToBottom, 2),
])
def test_responsive_layout_does_not_overflow(card, app, width, direction, columns):
    card._render_snapshot(snapshot())
    card.resize(width, 780)
    card.show()
    app.processEvents()
    assert card._body_layout.direction() == direction
    assert card._summary_columns == columns
    assert card._page_scroll.horizontalScrollBar().maximum() == 0
    assert card.minimumSizeHint().width() <= 460
    assert card._report_panel.width() <= width
    if width < 900:
        assert card._page.height() < 1000
    card.hide()


def test_round_has_explicit_renderer_and_short_button(card, app, monkeypatch):
    calls = []
    monkeypatch.setattr(card, "_start_worker", lambda fn, render=None: calls.append((fn, render)))
    card.resize(620, 780)
    card.show()
    app.processEvents()
    width = card._run_btn.width()
    card._on_run_round()
    app.processEvents()
    assert card._run_btn.width() == width
    assert calls == [(card._run_round, card._render_round)]
    assert card._run_btn.text() == "值班中…"
    assert not card._run_btn.isEnabled()
    card._on_run_round()
    assert len(calls) == 1


def test_loading_blocks_round_and_error_restores_controls(card, monkeypatch):
    calls = []
    card._thread = object()
    monkeypatch.setattr(card, "_start_worker", lambda *args: calls.append(args))
    card._on_run_round()
    assert calls == []
    card._thread = None
    card._on_worker_error("模拟读取失败")
    assert card._run_btn.isEnabled()
    assert card._refresh_btn.isEnabled()
    assert "模拟读取失败" in card._hint_lb.text()


def test_context_theme_and_close_signal(card):
    closed = []
    card.closed.connect(lambda: closed.append(True))
    for dark, text in [(True, "#eeeeee"), (False, "#202020")]:
        card.set_context_provider(lambda: {"is_dark": dark, "font_size": 14,
                                           "colors": {"text_primary": text, "accent": "#987654"}})
        card.refresh_style()
        assert text in card.styleSheet()
        assert "#987654" in card.styleSheet()
        assert card._report_view.textInteractionFlags() & Qt.TextSelectableByMouse
    card._close_btn.click()
    assert closed == [True]


def test_real_worker_routes_round_then_refreshes(card, app, monkeypatch):
    monkeypatch.setattr(card, "_run_round", lambda: {"round": {"status": "success"}})
    monkeypatch.setattr(card, "_load_snapshot", lambda: snapshot())
    card._on_run_round()
    loop = QEventLoop()
    probe = QTimer()
    probe.setInterval(10)
    probe.timeout.connect(lambda: loop.quit() if card._thread is None else None)
    probe.start()
    QTimer.singleShot(3000, loop.quit)
    loop.exec_()
    probe.stop()
    assert card._thread is None
    assert not card._round_running
    assert card._run_btn.isEnabled()
    assert card._run_btn.text() == "跑一轮"
    assert card._metric_values["quota"].text() == "2 / 6"


def test_report_links_only_open_http_and_https(card, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    for url in ["file:///etc/passwd", "javascript:alert(1)", "https://www.bilibili.com/video/BV123"]:
        card._report_view._open_link(QUrl(url))
    assert opened == ["https://www.bilibili.com/video/BV123"]


@pytest.mark.parametrize("credential, expected", [
    ("不存在（未登录）", "未登录"),
    ("存在但读不出（损坏）", "需重新登录"),
    ("", "未知"),
])
def test_credential_does_not_claim_online_login(card, credential, expected):
    data = snapshot()
    data["status"]["扫码凭证"] = credential
    card._render_snapshot(data)
    assert card._metric_values["credential"].text() == expected


@pytest.mark.parametrize("status", ["busy", "error"])
def test_round_failure_remains_visible_and_restores_controls(card, status):
    card._round_running = True
    card._run_btn.setEnabled(False)
    card._refresh_btn.setEnabled(False)
    card._render_round({"round": {"status": status, "error": "测试错误"}})
    assert not card._round_running
    assert card._run_btn.isEnabled()
    assert card._refresh_btn.isEnabled()
    assert "运行" in card._hint_lb.text() if status == "busy" else "测试错误" in card._hint_lb.text()


def test_theme_context_failure_keeps_card_usable(card):
    def unavailable():
        raise RuntimeError("窗口正在切换")
    card.set_context_provider(unavailable)
    card.refresh_style()
    assert "biliDutyCard" in card.styleSheet()
    assert card._run_btn.isEnabled()
