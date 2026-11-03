# -*- coding: utf-8 -*-
"""design_mode_core 纯函数单测。

plugins/ 没有 __init__.py，不能按包导入，走 importlib 按路径加载，
与 tests/conftest.py 里 ip-switcher 的加载方式一致。
"""

import importlib.util
from pathlib import Path

_CORE = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "browser"
    / "ui"
    / "design_mode_core.py"
)


def _load_core():
    spec = importlib.util.spec_from_file_location("browser_design_core", _CORE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_core()


def test_clamp_rect_expands_by_padding():
    assert core.clamp_rect(100, 100, 50, 40, 800, 600, pad=40) == (60, 60, 130, 120)


def test_clamp_rect_clips_at_viewport_edges():
    assert core.clamp_rect(0, 0, 20, 20, 800, 600, pad=40) == (0, 0, 60, 60)
    assert core.clamp_rect(780, 580, 20, 20, 800, 600, pad=40) == (740, 540, 60, 60)


def test_clamp_rect_returns_none_for_degenerate_input():
    assert core.clamp_rect(10, 10, 0, 0, 800, 600, pad=0) is None
    assert core.clamp_rect(900, 900, 10, 10, 800, 600, pad=0) is None


def test_filter_styles_keeps_whitelist_only():
    raw = {
        "display": "flex",
        "color": "rgb(0, 0, 0)",
        "cursor": "pointer",
    }
    out = dict(core.filter_styles(raw))
    assert out["display"] == "flex"
    assert out["color"] == "rgb(0, 0, 0)"
    assert "cursor" not in out


def test_filter_styles_drops_noise_values():
    raw = {"margin-top": "0px", "background-image": "none", "font-size": "16px"}
    out = dict(core.filter_styles(raw))
    assert "margin-top" not in out
    assert "background-image" not in out
    assert out["font-size"] == "16px"


def test_filter_styles_drops_flex_props_under_block_layout():
    raw = {"display": "block", "flex-direction": "row", "justify-content": "center"}
    out = dict(core.filter_styles(raw))
    assert "flex-direction" not in out
    assert "justify-content" not in out


def test_filter_styles_keeps_flex_props_under_flex_layout():
    raw = {"display": "flex", "flex-direction": "column", "justify-content": "center"}
    out = dict(core.filter_styles(raw))
    assert out["flex-direction"] == "column"
    assert out["justify-content"] == "center"


def test_filter_styles_drops_zero_borders_and_initial_values():
    raw = {
        "border-top": "0px none rgb(34, 34, 34)",
        "position": "static",
        "opacity": "1",
        "visibility": "visible",
        "font-weight": "400",
        "transition": "all 0s ease 0s",
        "text-decoration": "none solid rgb(34, 34, 34)",
    }
    assert core.filter_styles(raw) == []


def test_filter_styles_dedupes_overflow_shorthand():
    raw = {"overflow": "hidden", "overflow-x": "hidden", "overflow-y": "auto"}
    out = dict(core.filter_styles(raw))
    assert "overflow-x" not in out
    assert out["overflow-y"] == "auto"


def test_filter_styles_drops_offsets_when_not_positioned():
    raw = {
        "position": "static",
        "top": "auto",
        "right": "auto",
        "bottom": "auto",
        "left": "auto",
        "z-index": "auto",
        "overflow": "visible",
        "background-size": "auto",
    }
    assert core.filter_styles(raw) == []


def test_filter_styles_keeps_offsets_when_positioned():
    raw = {"position": "absolute", "top": "12px", "left": "0px"}
    out = dict(core.filter_styles(raw))
    assert out["position"] == "absolute"
    assert out["top"] == "12px"


def test_filter_styles_keeps_non_default_box_sizing():
    raw = {"display": "block", "box-sizing": "border-box"}
    assert dict(core.filter_styles(raw))["box-sizing"] == "border-box"


def test_style_keys_has_no_duplicates():
    assert len(core.STYLE_KEYS) == len(set(core.STYLE_KEYS))


def test_build_prompt_contains_all_sections():
    text = core.build_prompt(
        index=2,
        url="https://example.com/a",
        title="示例",
        selector="div.card > h2.title",
        html='<h2 class="title">示例</h2>',
        styles=[("display", "block"), ("font-size", "20px")],
        shot_path="C:/tmp/pick_2.png",
    )
    assert "<!-- drifox-pick 2 -->" in text
    assert "https://example.com/a" in text
    assert "div.card > h2.title" in text
    assert "C:/tmp/pick_2.png" in text
    assert '<h2 class="title">示例</h2>' in text
    assert "display: block" in text
    assert "font-size: 20px" in text


def test_build_prompt_omits_missing_shot():
    text = core.build_prompt(
        index=1,
        url="https://example.com",
        title="",
        selector="body",
        html="<body></body>",
        styles=[],
        shot_path=None,
    )
    assert "截图：" not in text


def test_js_pick_uses_element_from_point():
    script = core.js_pick(120, 340)
    assert "elementFromPoint(x, y)" in script
    assert script.rstrip().endswith("})(120, 340)")
    assert "(function(x, y)" in script


def test_js_hit_returns_rect_only():
    script = core.js_hit(10, 20)
    assert script.rstrip().endswith("})(10, 20)")
    assert "outerHTML" not in script


def test_js_pick_embeds_style_keys():
    assert '"display"' in core.js_pick(0, 0)

def test_js_pick_targets_visible_element():
    script = core.js_pick(120, 340)
    assert "_drifoxTarget(x, y)" in script
    assert "elementsFromPoint" in script
    assert "_drifoxVisible" in script
    assert "is_svg" in script

def test_js_pick_embeds_svg_keys():
    script = core.js_pick(0, 0)
    assert '"fill"' in script
    assert '"fill-opacity"' in script
    assert '"stroke-width"' in script

def test_js_hit_targets_visible_element():
    script = core.js_hit(10, 20)
    assert "_drifoxTarget(x, y)" in script
    assert "_drifoxVisible" in script

def test_filter_svg_styles_keeps_painted_fill_and_stroke():
    raw = {
        "fill": "rgb(253, 141, 60)",
        "fill-opacity": "0",
        "stroke": "rgb(0, 0, 0)",
        "stroke-width": "2px",
        "stroke-opacity": "1",
        "opacity": "1",
        "transform": "matrix(1, 0, 0, 1, 0, 0)",
        "font-family": "Inter",
    }
    out = dict(core.filter_svg_styles(raw))
    assert out["fill"] == "rgb(253, 141, 60)"
    assert out["fill-opacity"] == "0"
    assert out["stroke-width"] == "2px"
    assert "stroke-opacity" not in out
    assert "opacity" not in out
    assert "transform" not in out

def test_filter_svg_styles_drops_unpainted_groups():
    raw = {
        "fill": "none",
        "fill-opacity": "0",
        "stroke": "none",
        "stroke-width": "1px",
        "stroke-opacity": "1",
    }
    assert core.filter_svg_styles(raw) == []

def test_filter_svg_styles_keeps_transparent_only_with_painted_counterpart():
    raw = {"fill": "none", "stroke": "rgb(255, 0, 0)", "stroke-width": "1px"}
    out = dict(core.filter_svg_styles(raw))
    assert out["stroke"] == "rgb(255, 0, 0)"
    assert "fill" not in out
    assert "fill-opacity" not in out
    assert "stroke-width" in out

def test_filter_pick_styles_dispatches_by_svg_flag():
    html_raw = {"display": "flex", "color": "rgb(0, 0, 0)", "fill": "none"}
    assert "display" in dict(core.filter_pick_styles(html_raw, False))
    assert "fill" not in dict(core.filter_pick_styles(html_raw, False))
    svg_raw = {"fill": "rgb(1, 2, 3)", "fill-opacity": "1"}
    out = dict(core.filter_pick_styles(svg_raw, True))
    assert out["fill"] == "rgb(1, 2, 3)"
    assert "fill-opacity" not in out
