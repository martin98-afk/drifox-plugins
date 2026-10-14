# -*- coding: utf-8 -*-
"""tts_text 离线单测：正文提取 + 朗读清洗 + 截断。

不依赖 PyQt5（tts_text.py 只 import re），用假卡片驱动：
- 块列表卡片：只应读出 text 块，reasoning / tool_result / custom / image 一律剔除
- 兜底卡片：只有 get_plain_text()，内联 <think> 与 [tool:xxx] 行靠正则补刀
"""

import importlib.util
from pathlib import Path

import pytest

_PLUGIN_UI = Path(__file__).resolve().parent.parent / "plugins" / "voice-reply" / "ui"


@pytest.fixture(scope="module")
def tt():
    spec = importlib.util.spec_from_file_location("voice_reply_tts_text", _PLUGIN_UI / "tts_text.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeCard:
    """模拟 MessageCard：有 _content_data 块列表。"""

    def __init__(self, blocks):
        self._content_data = blocks

    def get_plain_text(self):  # 兜底路径不该被走到
        raise AssertionError("块列表可用时不应退回 get_plain_text()")


class FlatCard:
    """模拟拿不到块列表的老卡片：只有 get_plain_text()。"""

    def __init__(self, text):
        self._text = text

    def get_plain_text(self):
        return self._text


def _blocks(*texts):
    return [{"type": "text", "text": t} for t in texts]


# ── 正文提取 ──


def test_only_text_blocks_are_spoken(tt):
    card = FakeCard([
        {"type": "reasoning", "content": "用户问的是汇率，我需要先查最新牌价"},
        {"type": "text", "text": "今天美元现汇买入价是 7.08。"},
        {"type": "tool_result", "name": "web_search", "result": '{"rate":7.08,"ts":1}'},
        {"type": "image_url", "image_url": {"url": "https://a.com/x.png"}},
        {"type": "custom", "custom_type": "echarts", "data": {}},
        {"type": "text", "text": "以上仅供参考。"},
    ])
    out = tt.build_speakable_text(card)
    assert "汇率" not in out and "牌价" not in out
    assert "web_search" not in out and "7.08," not in out
    assert "x.png" not in out
    assert "今天美元现汇买入价是 7.08。" in out
    assert "以上仅供参考。" in out


def test_thinking_only_card_is_empty(tt):
    card = FakeCard([{"type": "reasoning", "content": "只想了一大段，没说话"}])
    assert tt.build_speakable_text(card) == ""


def test_tool_only_card_is_empty(tt):
    card = FakeCard([
        {"type": "tool_result", "name": "read_file", "result": "A" * 500},
    ])
    assert tt.build_speakable_text(card) == ""


def test_flat_card_falls_back_and_strips_tool_lines(tt):
    text = (
        "先看结论：可以。\n"
        "[tool:read_file] def main():\n    print('hi')\n"
        "具体步骤见下。"
    )
    out = tt.build_speakable_text(FlatCard(text))
    assert "先看结论：可以。" in out
    assert "具体步骤见下。" in out
    assert "tool:" not in out
    assert "def main" not in out


def test_flat_card_strips_inline_think(tt):
    text = "这是正文。<think>这段是旁白内容</think>这是正文。收尾。"
    out = tt.build_speakable_text(FlatCard(text))
    assert "旁白" not in out
    assert "这是正文。" in out
    assert "收尾。" in out


def test_none_card_is_empty(tt):
    assert tt.build_speakable_text(None) == ""


# ── 清洗 ──


def test_code_block_collapsed(tt):
    out = tt.clean_for_tts("前言。\n```python\nimport os\nprint(os.getcwd())\n```\n后记。")
    assert "import os" not in out
    assert "代码略" in out
    assert "前言。" in out and "后记。" in out


def test_inline_code_keeps_content(tt):
    assert "调用 foo 函数" in tt.clean_for_tts("调用 `foo` 函数")


def test_url_and_data_uri_dropped_but_keeps_punctuation(tt):
    out = tt.clean_for_tts("详情见 https://example.com/a?b=1。图示 data:image/png;base64,iVBORw0KGgoAAAANS。完")
    assert "https://" not in out
    assert "base64" not in out
    assert out.endswith("完")
    assert "。" in out


def test_long_base64_blob_dropped(tt):
    blob = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5ejAxMjM0NTY3ODk"
    out = tt.clean_for_tts(f"前面 {blob} 后面")
    assert blob not in out
    assert "前面" in out and "后面" in out


def test_html_tags_dropped(tt):
    out = tt.clean_for_tts("标题<b>加粗</b>与换行<br/>结束")
    assert "<b>" not in out and "<br/>" not in out
    assert "加粗" in out and "结束" in out


def test_emoji_and_control_chars_dropped(tt):
    out = tt.clean_for_tts("很好😀完成\x07\u200d✅")
    assert "很好" in out and "完成" in out
    assert "\x07" not in out and "\u200d" not in out


def test_markdown_structure_markers_dropped(tt):
    src = (
        "# 标题\n"
        "1. 第一项\n"
        "- 第二项\n"
        "> 引用一句\n"
        "**粗体**与*斜体*与~~删除~~\n"
        "---\n"
        "| 列A | 列B |\n"
        "脚注[^1]\n"
    )
    out = tt.clean_for_tts(src)
    for marker in ("#", "1.", "- ", "> ", "**", "~~", "|", "[^1]"):
        assert marker not in out, f"标记 {marker!r} 未被清除"
    assert "标题" in out and "第一项" in out and "第二项" in out
    assert "引用一句" in out and "粗体" in out and "斜体" in out and "删除" in out


def test_repeated_punctuation_collapsed(tt):
    out = tt.clean_for_tts("表格，，结束。。。")
    assert "，，" not in out and "。。" not in out


def test_edge_commas_around_code_block_dropped(tt):
    out = tt.clean_for_tts("也可以用 pip：\n\n```bash\npip install x\n```\n\n后面。")
    assert "代码略" in out
    # 代码块替换串自带前后逗号，贴在换行两侧时清掉，避免朗读器多报一声「逗号」
    assert "：，\n" not in out and "\n，" not in out
    assert "后面。" in out


def test_link_keeps_anchor_text(tt):
    out = tt.clean_for_tts("见 [官方文档](https://driFox.dev/doc) 说明")
    assert "官方文档" in out
    assert "driFox.dev" not in out


def test_image_keeps_alt(tt):
    out = tt.clean_for_tts("架构图：![系统架构图](https://a.com/a.png) 如上")
    assert "系统架构图" in out
    assert "a.png" not in out


# ── 截断 ──


def test_truncate_to_max(tt):
    long_text = "内" * (tt.MAX_TEXT_LEN + 500)
    out = tt.build_speakable_text(FakeCard(_blocks(long_text)))
    assert len(out) == tt.MAX_TEXT_LEN + 2  # + 省略号（两个 U+2026 字符）
    assert out.endswith("……")


def test_short_text_untouched(tt):
    src = "很短的一句。"
    assert tt.build_speakable_text(FakeCard(_blocks(src))) == src


def test_max_len_is_2000(tt):
    assert tt.MAX_TEXT_LEN == 2000
