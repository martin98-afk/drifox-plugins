# -*- coding: utf-8 -*-
"""token-usage 离线单测：zstd 解压 + 净占用口径 + 窗口补零 + 色阶 + 热力图几何。

不依赖 PyQt5 / 宿主 / 真实数据库：
- 用 data.decode_messages 验三种存储格式（ZSTD / 裸 JSON / 垃圾数据）
- 用合成 daily 验净占用口径（每会话取末次 usage）与窗口补零
- 用 render 的纯函数验数字缩写、色阶分位、热力图周列对齐
"""

import importlib.util
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

_PLUGIN_UI = Path(__file__).resolve().parent.parent / "plugins" / "token-usage" / "ui"


@pytest.fixture(scope="module")
def data_mod():
    spec = importlib.util.spec_from_file_location("tu_data", _PLUGIN_UI / "data.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tu_data"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ui_pkg(data_mod):
    """把 ui 目录注册成可相对导入的包（render 内部 from .data / . import collector）"""
    import types

    pkg = types.ModuleType("tu_pkg")
    pkg.__path__ = [str(_PLUGIN_UI)]
    sys.modules["tu_pkg"] = pkg
    sys.modules["tu_pkg.data"] = data_mod
    return pkg


@pytest.fixture(scope="module")
def render_mod(ui_pkg):
    spec = importlib.util.spec_from_file_location("tu_pkg.render", _PLUGIN_UI / "render.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tu_pkg.render"] = mod
    spec.loader.exec_module(mod)
    return mod


# ── decode_messages：三种存储格式 ──


def _zstd_blob(payload: bytes) -> bytes:
    from compression import zstd

    comp = zstd.ZstdCompressor(level=3)
    comp.set_pledged_input_size(len(payload))
    return b"ZSTD" + b"\x01" + comp.compress(payload) + comp.flush()


def test_decode_zstd_blob(data_mod):
    msgs = [{"role": "assistant", "token_usage": {"input": 100, "output": 20}}]
    blob = _zstd_blob(json.dumps(msgs).encode("utf-8"))
    assert data_mod.decode_messages(blob) == msgs


def test_decode_plain_json_bytes(data_mod):
    msgs = [{"role": "user", "content": "hi"}]
    assert data_mod.decode_messages(json.dumps(msgs).encode("utf-8")) == msgs


def test_decode_plain_json_str(data_mod):
    msgs = [{"role": "user", "content": "hi"}]
    assert data_mod.decode_messages(json.dumps(msgs)) == msgs


def test_decode_garbage_returns_empty(data_mod):
    assert data_mod.decode_messages(None) == []
    assert data_mod.decode_messages(b"") == []
    assert data_mod.decode_messages(123) == []
    # 有 magic 但内容损坏 → 不抛异常，返回空
    assert data_mod.decode_messages(b"ZSTD\x01garbage") == []
    # 裸 JSON 但非法 → 返回空
    assert data_mod.decode_messages(b"{not json") == []


def test_decode_non_list_returns_empty(data_mod):
    assert data_mod.decode_messages(json.dumps({"a": 1}).encode("utf-8")) == []


# ── 净占用口径 ──


def _patch_db(monkeypatch, data_mod, sessions):
    """把 find_db / sqlite3.connect 换成内存 sqlite，注入合成 sessions.messages"""
    import sqlite3
    import tempfile
    from pathlib import Path

    tmpdir = Path(tempfile.mkdtemp())
    db_path = tmpdir / "sessions.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE sessions (session_id TEXT, messages BLOB, project TEXT)"
    )
    for i, msgs in enumerate(sessions):
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?)",
            (f"s{i}", json.dumps(msgs).encode("utf-8"), "demo"),
        )
    conn.commit()
    conn.close()

    monkeypatch.setattr(data_mod, "_found_db_path", db_path, raising=False)
    monkeypatch.setattr(data_mod, "_host_db_path", lambda: db_path)
    return db_path


def test_collect_uses_incremental_input(data_mod, monkeypatch):
    """输入按增量扣基线；输出逐轮相加；请求数记全部条数

    会话1 prompt 1000 → 5000：首轮全额 1000，次轮增量 4000，合计 5000
    """
    sessions = [
        [
            {"role": "user", "timestamp": "2026-10-10 10:00:00"},
            {
                "role": "assistant",
                "timestamp": "2026-10-10 10:01:00",
                "token_usage": {"input": 1000, "output": 100},
            },
            {
                "role": "assistant",
                "timestamp": "2026-10-10 10:05:00",
                "token_usage": {"input": 5000, "output": 300},
            },
        ],
        [
            {
                "role": "assistant",
                "timestamp": "2026-10-11 09:00:00",
                "token_usage": {"input": 200, "output": 20},
            },
        ],
    ]
    _patch_db(monkeypatch, data_mod, sessions)
    result = data_mod.collect()
    assert result["error"] is None
    assert result["sessions"] == 2
    assert result["daily"]["2026-10-10"] == [5000, 400, 2]
    assert result["daily"]["2026-10-11"] == [200, 20, 1]


def test_collect_incremental_baseline_is_per_session(data_mod, monkeypatch):
    """增量基线按会话独立：每会话首轮都是全额，不跨会话相减

    两个单轮会话：3000 与 1000。若基线跨会话共享，第二轮会算成
    max(0, 1000-3000)=0，总数变 3000 而非 4000。
    """
    sessions = [
        [
            {
                "role": "assistant",
                "timestamp": "2026-10-10 10:00:00",
                "token_usage": {"input": 3000, "output": 10},
            },
        ],
        [
            {
                "role": "assistant",
                "timestamp": "2026-10-10 11:00:00",
                "token_usage": {"input": 1000, "output": 5},
            },
        ],
    ]
    _patch_db(monkeypatch, data_mod, sessions)
    result = data_mod.collect()
    # 两会话首轮都全额计：3000 + 1000，若跨会话相减会得到 3000
    assert result["daily"]["2026-10-10"] == [4000, 15, 2]


def test_collect_prompt_shrink_counts_zero_not_negative(data_mod, monkeypatch):
    """prompt 回退（上下文压缩后变小）时增量按 0 计，不产生负数"""
    sessions = [
        [
            {
                "role": "assistant",
                "timestamp": "2026-10-10 10:00:00",
                "token_usage": {"input": 50000, "output": 10},
            },
            {
                "role": "assistant",
                "timestamp": "2026-10-10 10:30:00",
                "token_usage": {"input": 8000, "output": 10},
            },
        ],
    ]
    _patch_db(monkeypatch, data_mod, sessions)
    result = data_mod.collect()
    # 首轮 50000 全额，第二轮压缩后 8000 → 增量 0（不是 -42000）
    assert result["daily"]["2026-10-10"] == [50000, 20, 2]


def test_collect_skips_messages_without_timestamp(data_mod, monkeypatch):
    _patch_db(
        monkeypatch,
        data_mod,
        [[{"role": "assistant", "token_usage": {"input": 999, "output": 9}}]],
    )
    result = data_mod.collect()
    assert result["daily"] == {}
    assert result["sessions"] == 0


def test_collect_reports_missing_db(data_mod, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(data_mod, "_found_db_path", None, raising=False)
    monkeypatch.setattr(data_mod, "_host_db_path", lambda: None)
    monkeypatch.setattr(data_mod, "_DEV_CANDIDATES", [Path("Z:/nope/sessions.db")])
    result = data_mod.collect()
    assert result["error"] == "未找到会话数据库"
    assert result["daily"] == {}


# ── 窗口补零与汇总 ──


def _daily_today_plus(days_ago: int, inp: int, out: int, req: int) -> dict:
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    return {d: [inp, out, req]}


def test_sum_window_pads_missing_days(data_mod):
    daily = _daily_today_plus(0, 100, 10, 2)
    s = data_mod.sum_window(daily, 30)
    assert s["input"] == 100 and s["output"] == 10
    assert s["total"] == 110 and s["requests"] == 2
    assert s["active_days"] == 1


def test_sum_window_excludes_out_of_range(data_mod):
    daily = _daily_today_plus(40, 999, 99, 9)  # 30 天窗口外
    s = data_mod.sum_window(daily, 30)
    assert s["total"] == 0 and s["requests"] == 0


def test_last_n_days_length_and_order(data_mod):
    rows = data_mod.last_n_days({}, 30)
    assert len(rows) == 30
    # 从旧到新，最后一个是今天
    assert rows[-1][0] == date.today().isoformat()
    assert rows[0][0] == (date.today() - timedelta(days=29)).isoformat()
    assert rows[0][1:] == (0, 0, 0)


def test_active_day_totals_only_with_requests(data_mod):
    daily = _daily_today_plus(0, 100, 10, 0)  # 有 token 但零请求 → 不算活跃
    daily.update(_daily_today_plus(1, 50, 5, 1))
    totals = data_mod.active_day_totals(daily, 30)
    assert totals == [55]


# ── 数字缩写 ──


@pytest.mark.parametrize(
    "n,expected",
    [
        (0, "0"),
        (999, "999"),
        (1000, "1K"),
        (1234, "1.2K"),
        (50500, "50.5K"),
        (130000, "130K"),
        (1_000_000, "1M"),
        (2_500_000, "2.5M"),
        (3_000_000_000, "3B"),
    ],
)
def test_fmt_k(render_mod, n, expected):
    assert render_mod._fmt_k(n) == expected


# ── 色阶分位 ──


def test_thresholds_empty_when_no_activity(render_mod):
    assert render_mod._thresholds([0, 0, 0], 4) == []


def test_thresholds_small_sample_falls_back(render_mod):
    # 样本 < 8 走等距切分
    th = render_mod._thresholds([10, 20, 100], 4)
    assert len(th) == 4
    assert th == sorted(th)


def test_thresholds_large_sample_deduped_and_ordered(render_mod):
    vals = list(range(1, 100))
    th = render_mod._thresholds(vals, 4)
    assert th == sorted(th)
    assert len(set(th)) == len(th)


def test_level_of_zero_is_empty(render_mod):
    assert render_mod._level_of(0, [10, 20]) == 0


def test_level_of_beyond_max_is_top(render_mod):
    assert render_mod._level_of(999, [10, 20]) == 3  # thresholds 2 档 + 1


# ── 热力图几何 ──


def test_heatmap_starts_on_monday(render_mod):
    end = date(2026, 10, 14)
    weeks, _ = render_mod._heatmap_cells({}, end, 365)
    first = weeks[0][0]["date"]
    assert date.fromisoformat(first).weekday() == 0


def test_heatmap_has_exactly_365_in_range_cells(render_mod):
    end = date(2026, 10, 14)
    weeks, _ = render_mod._heatmap_cells({}, end, 365)
    in_range = [c for w in weeks for c in w if c["in_range"]]
    assert len(in_range) == 365
    assert in_range[0]["date"] == (end - timedelta(days=364)).isoformat()
    assert in_range[-1]["date"] == end.isoformat()


def test_heatmap_month_labels_are_ordered(render_mod):
    end = date(2026, 10, 14)
    weeks, labels = render_mod._heatmap_cells({}, end, 365)
    assert labels, "应至少有一个月标签"
    idxs = [i for i, _ in labels]
    assert idxs == sorted(idxs)
    assert len(labels) == len(set(idxs)), "每月只打一次标"
    # 每个标签都应落在实际列数范围内
    assert all(0 <= i < len(weeks) for i in idxs)


def test_heatmap_marks_active_cells(render_mod):
    end = date(2026, 10, 14)
    daily = {end.isoformat(): [1000, 100, 5]}
    weeks, _ = render_mod._heatmap_cells(daily, end, 30)
    last = weeks[-1]
    today_cell = [c for c in last if c["date"] == end.isoformat()][0]
    assert today_cell["total"] == 1100
    assert today_cell["requests"] == 5
    assert today_cell["in_range"] is True


def test_heatmap_html_contains_cell_tooltips(render_mod):
    end = date(2026, 10, 14)
    daily = {end.isoformat(): [1000, 100, 5]}
    html = render_mod._render_heatmap(daily, end, 30, render_mod._palette(True))
    assert 'class="tu-grid"' in html
    assert "2026-10-14" in html
    assert "次请求" in html


# ── tooltip（回归：曾用原生 title → 纯 CSS 伪元素 → JS 自绘视口钳制）──
#
# 演化史：①原生 title 由 OS 绘制，浅色下黑底大字号；②改纯 CSS ::after 后伪元素
# 无法测量自身宽度，只能靠 nth-child 硬编码边缘列翻转（只兜右 3 列），卡片宽度
# 动态变化时仍会溢出被 html{overflow:hidden} 裁掉（用户截图反馈）；③改为 JS 自绘
# #tu-tip，getBoundingClientRect 实测 + 视口双向钳制。


def test_heatmap_uses_data_tip_not_native_title(render_mod):
    """格子必须用 data-tip，不得回退原生 title"""
    end = date(2026, 10, 14)
    daily = {end.isoformat(): [1000, 100, 5]}
    html = render_mod._render_heatmap(daily, end, 30, render_mod._palette(True))
    assert "data-tip=" in html
    assert 'title="' not in html, "不得使用原生 title（OS 绘制，样式不可控）"


def test_tooltip_is_js_drawn_not_pseudo_element(render_mod):
    """必须用 JS 自绘 #tu-tip，不得回退 CSS 伪元素（伪元素测不到宽度，边缘列必被裁）"""
    css = render_mod._css(True)
    assert "#tu-tip {" in css, "#tu-tip 样式规则缺失（无样式 = 裸文本块）"
    assert "position: fixed" in css
    assert "attr(data-tip)" not in css, "不得回退 CSS 伪元素 tooltip"
    assert ":hover::after" not in css, "不得回退 :hover::after 伪元素 tooltip"
    # 旧实现的 nth-child 边缘列硬编码也一并死去，防回潮
    assert "nth-last-child(-n+3)" not in css


def test_heatmap_binds_delegated_mouse_events(render_mod):
    """工具提示必须挂在 .tu-grid 的委托事件上（一个属性覆盖全部格子）"""
    end = date(2026, 10, 14)
    daily = {end.isoformat(): [1000, 100, 5]}
    html = render_mod._render_heatmap(daily, end, 30, render_mod._palette(True))
    assert 'class="tu-grid"' in html
    assert "onmouseover=" in html
    assert "onmouseout=" in html
    # 宿主 innerHTML 注入下 <script> 不执行，必须走内联事件属性（同 calendar 先例）
    assert "<script" not in html


def test_tooltip_js_clamps_to_viewport(render_mod):
    """定位必须实测宽度 + 视口双向钳制（纯 CSS 方案失败的根因）"""
    js = render_mod._TIP_SHOW_JS
    assert "getBoundingClientRect" in js, "必须实测格子几何"
    assert "offsetWidth" in js and "offsetHeight" in js, "必须实测 tooltip 自身尺寸"
    assert "innerWidth" in js and "innerHeight" in js, "必须按视口钳制"
    assert "Math.min" in js and "Math.max" in js, "钳制需要 min/max"


def test_tooltip_js_hides_on_leave_and_on_non_tip(render_mod):
    """mouseout 离格即隐藏；入住非 tip 元素（如图例格）也要隐藏"""
    show, hide = render_mod._TIP_SHOW_JS, render_mod._TIP_HIDE_JS
    assert "display='none'" in hide or 'display="none"' in hide
    # relatedTarget 仍在带 data-tip 的格子内则不隐藏（在格间移动不闪）
    assert "relatedTarget" in hide
    assert ".tu-cell[data-tip]" in hide, "入住元素判据必须限定带 data-tip 的格子"
    # 悬停到无 data-tip 的元素（图例色块）时展示函数主动隐藏
    assert "'none'" in show


def test_tooltip_palette_matches_context_stats(render_mod):
    """tooltip 配色与 context-stats 的 echarts tooltip 同源，两插件观感一致"""
    dark = render_mod._palette(True)
    light = render_mod._palette(False)
    # context-stats/ui/render.py 的 tooltip_bg / tooltip_border
    assert dark["tooltip_bg"] == "rgba(30,34,42,0.92)"
    assert dark["tooltip_border"] == "rgba(98,160,234,0.5)"
    assert light["tooltip_bg"] == "rgba(255,255,255,0.96)"
    assert light["tooltip_border"] == "rgba(40,120,220,0.45)"


def test_tooltip_colours_injected_into_css(render_mod):
    """tooltip_bg / tooltip_border 必须真的填进 CSS（未填 = 透明无边框）"""
    css_dark = render_mod._css(True)
    assert "rgba(30,34,42,0.92)" in css_dark
    css_light = render_mod._css(False)
    assert "rgba(255,255,255,0.96)" in css_light


def test_tooltip_does_not_block_clicks(render_mod):
    """tooltip 不能拦截鼠标（否则格子点不动）"""
    assert "pointer-events: none" in render_mod._css(True)


def test_heatmap_columns_share_width_flexibly(render_mod):
    """热力图列必须 flex 均分，不能写死 px 宽

    卡片宽度是动态的（主程序按 parent_width - 20 算，下限 320px），
    列宽写死 px 会在窄窗口溢出、宽窗口留白。
    回归锚点：曾把 .tu-week 改成 flex:0 0 12px。
    """
    css = render_mod._css(True)
    assert ".tu-week { flex: 1 1 0" in css
    assert "flex: 0 0" not in css, "列宽不得写死"
    # 格子靠百分比 + padding-bottom 撑正方形（Chromium 83 无 aspect-ratio）
    assert ".tu-cell { display: block; width: 100%; padding-bottom: 100%" in css


def test_heatmap_no_fixed_px_column_width(render_mod):
    """列/格子的**宽度**不得写死 px（会导致窄窗口横向溢出）

    只查 px 宽度；百分比（width:100%）、列间距（margin-right）都是对的。
    """
    import re

    end = date(2026, 10, 14)
    html = render_mod._render_heatmap({}, end, 30, render_mod._palette(True))
    css = render_mod._css(True)
    for rule_start, rule_end in ((".tu-week {", ".tu-cell {"), (".tu-cell {", ".tu-week:last")):
        rule = css[css.index(rule_start) : css.index(rule_end)]
        fixed = re.search(r"(?<!min-)\bwidth:\s*\d+px", rule)
        assert fixed is None, f"宽度不得写死 px: {rule.strip()}"
    # 格子 span 的内联样式只允许带 background（尺寸一律走 CSS 类）
    for cell in html.split('<span class="tu-cell"')[1:]:
        inline = cell.split('style="')[1].split('"')[0]
        assert inline.startswith("background:"), f"格子内联样式应只有背景色: {inline}"


def test_month_labels_split_number_and_suffix(render_mod):
    """数字与「月」分两个 span：窄容器用 media query 隐藏后缀防粘连"""
    labels = [(0, "10月"), (4, "11月"), (9, "12月")]
    spans = render_mod._month_label_spans(labels, 12)
    joined = "".join(spans)
    assert "10" in joined and "11" in joined and "12" in joined
    assert joined.count("tu-month-suffix") == 3
    # 后缀在独立 span 内
    assert ">月</span>" in joined
    # 媒体查询规则必须存在于 CSS 中
    assert "max-width: 560px" in render_mod._css(True)
    assert "tu-month-suffix { display: none" in render_mod._css(True)


def test_month_label_flex_growth_matches_span(render_mod):
    """每个标签的 flex-grow = 本月起始周 → 下月起始周的跨度"""
    labels = [(0, "10月"), (4, "11月"), (9, "12月")]
    spans = render_mod._month_label_spans(labels, 12)
    assert "flex:4 1 0" in spans[0]  # 0 → 4
    assert "flex:5 1 0" in spans[1]  # 4 → 9
    assert "flex:3 1 0" in spans[2]  # 9 → n_cols(12) 收尾


# ── 完整渲染 ──


def test_render_html_empty_state(render_mod):
    html = render_mod.render_html({"is_dark": True}, {"daily": {}, "sessions": 0})
    assert "暂无 API 用量记录" in html
    # 空态不画格子（.tu-grid 的 CSS 规则仍在，故查实际格子元素）
    assert 'class="tu-grid"' not in html
    assert '<div class="tu-week">' not in html


def test_render_html_full_layout(render_mod):
    end = date.today()
    daily = {
        end.isoformat(): [2300000, 2700, 2200],
        (end - timedelta(days=2)).isoformat(): [100000, 500, 20],
    }
    html = render_mod.render_html({"is_dark": True}, {"daily": daily, "sessions": 2})
    # 四指标都在
    for label in ("总 Token", "输入 Token", "输出 Token", "请求次数"):
        assert label in html
    # 30 天窗口说明 + 热力图标题
    assert "过去 30 天" in html
    assert "每日活动" in html
    assert "过去一年" in html
    # 刷新按钮挂 context-tag（主程序点击链）
    assert 'data-type="tu-refresh"' in html
    assert "刷新用量" in html
    # 样式内联（Chromium 83 下 <style> 可用）
    assert "<style>" in html


def test_render_html_input_output_split(render_mod):
    end = date.today()
    daily = {end.isoformat(): [50500, 4900, 90]}
    html = render_mod.render_html({"is_dark": False}, {"daily": daily, "sessions": 1})
    assert "50.5K" in html  # 输入
    assert "4.9K" in html  # 输出
    assert "55.4K" in html  # 总
    assert "90" in html


def test_render_light_and_dark_differ(render_mod):
    end = date.today()
    daily = {end.isoformat(): [1000, 100, 5]}
    dark = render_mod.render_html({"is_dark": True}, {"daily": daily, "sessions": 1})
    light = render_mod.render_html({"is_dark": False}, {"daily": daily, "sessions": 1})
    assert dark != light


def test_render_tolerates_missing_ctx(render_mod):
    end = date.today()
    daily = {end.isoformat(): [1000, 100, 5]}
    html = render_mod.render_html(None, {"daily": daily, "sessions": 1})
    assert 'class="tu-grid"' in html


@pytest.fixture(scope="module")
def collector_mod(data_mod, ui_pkg):
    spec = importlib.util.spec_from_file_location("tu_pkg.collector", _PLUGIN_UI / "collector.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tu_pkg.collector"] = mod
    # collector 顶层就 import PyQt5，测试环境无 Qt 时跳过
    pytest.importorskip("PyQt5.QtCore")
    spec.loader.exec_module(mod)
    return mod


# ── 缓存 key：写/读必须同源（回归：曾用 db mtime 做读取判据）──
#
# 症状：页签永远停在「加载中」。
# 原因：读取时重新计算 key（db mtime + 日期），而采集期间有新会话写入 →
#       mtime 变化 → 写缓存时的 key 与读缓存时的 key 不等 → 判定未命中 →
#       每次都重新起线程，采集完 mtime 又变，永远追不上。
# 修法：读取只看 TTL；db 是否变化由 _is_stale() 单独判。


def test_collect_cache_hit_survives_db_change(collector_mod, monkeypatch):
    """采集完成后 db 再变化，get_cached() 仍应命中（TTL 内）"""
    monkeypatch.setattr(collector_mod, "_cache", {"daily": {"d": [1, 2, 3]}, "sessions": 1})
    monkeypatch.setattr(collector_mod, "_cache_key", (1, "2026-01-01"))
    monkeypatch.setattr(collector_mod, "_cache_ts", time.monotonic())
    # 让 build_cache_key 返回完全不同的 key（模拟 mtime 已变）
    monkeypatch.setattr(collector_mod, "build_cache_key", lambda: (999, "2026-10-14"))
    assert collector_mod.get_cached() is not None


def test_collect_cache_expires_by_ttl(collector_mod, monkeypatch):
    """超过 TTL 即失效（避免长期展示陈旧数据）"""
    monkeypatch.setattr(collector_mod, "_cache", {"daily": {}, "sessions": 0})
    monkeypatch.setattr(collector_mod, "_cache_key", (1, "2026-01-01"))
    monkeypatch.setattr(collector_mod, "_cache_ts", time.monotonic() - 999)
    assert collector_mod.get_cached() is None


def test_collect_cache_none_when_empty(collector_mod, monkeypatch):
    monkeypatch.setattr(collector_mod, "_cache", None)
    assert collector_mod.get_cached() is None


def test_collect_error_cache_short_ttl(collector_mod, monkeypatch):
    """错误结果短 TTL：过期视为未命中，允许自动重采"""
    monkeypatch.setattr(collector_mod, "_cache", {"daily": {}, "sessions": 0, "error": "boom"})
    monkeypatch.setattr(collector_mod, "_cache_key", (1, "2026-01-01"))
    monkeypatch.setattr(collector_mod, "_cache_ts", time.monotonic() - (collector_mod._ERROR_TTL + 1))
    assert collector_mod.get_cached() is None


def test_is_stale_detects_db_change(collector_mod, monkeypatch):
    """_is_stale 只比对 db key，与 TTL 判据分离"""
    monkeypatch.setattr(collector_mod, "_cache", {"daily": {}, "sessions": 0})
    monkeypatch.setattr(collector_mod, "_cache_key", (1, "2026-01-01"))
    monkeypatch.setattr(collector_mod, "build_cache_key", lambda: (2, "2026-01-01"))
    assert collector_mod._is_stale() is True
    monkeypatch.setattr(collector_mod, "build_cache_key", lambda: (1, "2026-01-01"))
    assert collector_mod._is_stale() is False


def test_is_stale_false_when_no_cache(collector_mod, monkeypatch):
    monkeypatch.setattr(collector_mod, "_cache", None)
    assert collector_mod._is_stale() is False


def test_get_cached_never_recomputes_db_key(collector_mod, monkeypatch):
    """get_cached 不得调用 build_cache_key —— 那正是原 bug 的根

    读取路径一旦重算 key，采集期间的写入就会让缓存永久判未命中。
    """
    monkeypatch.setattr(collector_mod, "_cache", {"daily": {}, "sessions": 0})
    monkeypatch.setattr(collector_mod, "_cache_key", (1, "2026-01-01"))
    monkeypatch.setattr(collector_mod, "_cache_ts", time.monotonic())

    def _boom():
        raise AssertionError("get_cached 不应重算 db key")

    monkeypatch.setattr(collector_mod, "build_cache_key", _boom)
    assert collector_mod.get_cached() is not None


def test_invalidate_clears_cache(collector_mod, monkeypatch):
    """invalidate 后立刻不可命中（与 TTL 无关，锁内直接清）

    ⚠️ 必须让缓存本处于「TTL 内有效」状态，否则 get_cached() 会因 TTL 过期
    返回 None，断言就变成假阳性——这正是本测试第一版的毛病。
    """
    monkeypatch.setattr(collector_mod, "_cache", {"daily": {}, "sessions": 0})
    monkeypatch.setattr(collector_mod, "_cache_key", (1, "2026-01-01"))
    monkeypatch.setattr(collector_mod, "_cache_ts", time.monotonic())
    # 先确认此刻确实命中（TTL 内）
    assert collector_mod.get_cached() is not None, "前置：缓存应在 TTL 内命中"
    # 再 invalidate
    collector_mod.invalidate()
    assert collector_mod._cache is None
    assert collector_mod._cache_key is None
    assert collector_mod._cache_ts == 0.0
    assert collector_mod.get_cached() is None


def test_notify_refresh_survives_missing_host(collector_mod):
    """宿主不可用时 notify_refresh 不得抛异常（插件跑在裸解释器里也安全）"""
    collector_mod.notify_refresh()


# ── 采集收尾不依赖信号投递（回归：打包版市场安装后永远卡「正在统计」）──
#
# 症状：通过市场安装插件后，用量页签永远停在加载占位，日志只有「采集已启动」。
# 根因：register_ui 的预热 start() 在市场安装 worker 线程执行（QTimer.singleShot
#       回调归调用线程所有），_collector 单例诞生在该线程；采集完成后
#       finished.emit 是 queued 信号，投给已退出 exec() 的死线程，永不消费——
#       缓存永不写入、_running 永不清零，后续 start() 全被 is_running() 拦截。
# 修法：写缓存/日志/状态清理在 worker.run 内就地完成（_finalize_collect），
#       线程退出由 run 内 quit() 自主完成；信号回调仅剩幂等兜底。


def test_finalize_collect_writes_cache_without_signal(collector_mod, monkeypatch):
    """_finalize_collect 就地生效：缓存命中、_running 清零，全程无 Qt 信号参与"""
    monkeypatch.setattr(collector_mod, "_cache", None)
    monkeypatch.setattr(collector_mod, "_cache_key", None)
    monkeypatch.setattr(collector_mod, "_cache_ts", 0.0)
    monkeypatch.setattr(collector_mod, "_running", True)
    monkeypatch.setattr(collector_mod, "build_cache_key", lambda: (7, "2026-10-14"))

    data = {"daily": {"2026-10-14": [10, 2, 1]}, "sessions": 1, "error": None}
    collector_mod._finalize_collect(data)

    assert collector_mod.get_cached() == data
    assert collector_mod._cache_key == (7, "2026-10-14")
    assert collector_mod._running is False


def test_worker_run_finalizes_even_when_signal_never_delivered(collector_mod, monkeypatch):
    """worker.run 完成 → 缓存与运行态立即就绪；信号从未投递也不受影响

    直接在测试线程同步调 run()（不经过 moveToThread/事件循环），等价于
    「finished 事件投进死线程永不消费」的极端场景：只要 run 跑完，数据必须可用。
    """
    monkeypatch.setattr(collector_mod, "_cache", None)
    monkeypatch.setattr(collector_mod, "_cache_key", None)
    monkeypatch.setattr(collector_mod, "_cache_ts", 0.0)
    monkeypatch.setattr(collector_mod, "_running", True)
    monkeypatch.setattr(collector_mod, "build_cache_key", lambda: (9, "2026-10-14"))

    data = {"daily": {"2026-10-13": [5, 1, 1]}, "sessions": 1, "error": None}
    import sys

    data_mod = sys.modules["tu_pkg.data"]
    monkeypatch.setattr(data_mod, "collect", lambda: data)

    collector = collector_mod._Collector()
    collector._thread = object()  # 模拟运行中：is_running() True 挡住新采集
    worker = collector_mod._CollectWorker((9, "2026-10-14"), collector)
    worker.run()

    assert collector_mod.get_cached() == data
    assert collector_mod._running is False
    assert collector._thread is None, "worker 收尾必须清 _thread，否则 is_running 永远 True"
    assert collector.is_running() is False


def test_css_has_no_unfilled_placeholders(render_mod):
    css = render_mod._css(True)
    assert "{fs_" not in css
    for key in ("border", "panel", "text", "muted", "faint", "accent"):
        assert "{" + key + "}" not in css


def test_css_has_single_brace_rules(render_mod):
    """CSS 规则必须用单花括号

    历史坑：模板写成 `.tu-wrap {{ ... }}`（f-string 残留写法），
    配 `.replace()` 填充导致双花括号从未折叠，整份样式表失效——
    页面全部退回浏览器默认样式，而字符串断言型测试完全查不出来。
    """
    css = render_mod._css(True)
    assert "{{" not in css
    assert "}}" not in css
    assert ".tu-cell {" in css
    assert ".tu-metrics { display: flex" in css


def test_dark_palette_levels_are_opaque(render_mod):
    """暗色色阶用实色：半透明蓝叠在深底上偏灰，档位区分不出来"""
    levels = render_mod._palette(True)["levels"]
    assert len(levels) == 5
    for c in levels:
        assert c.startswith("#"), f"暗色档位应为实色: {c}"
        assert "rgba" not in c


# ── 色阶方向：越深 = 越多（明暗两版必须一致）──
#
# 回归：暗色版最初做成「越亮 = 越多」，与浅色的「越深 = 越多」语义相反。
# 用户反馈「颜色反了，应该越深代表越多」。


def _lum(c: str) -> float:
    """颜色相对亮度（#rrggbb 与 rgba() 都支持，半透明按不透明度折算到白底/黑底不适用，
    这里直接取 RGB 值的感知亮度，足以判断单调性）"""
    c = c.strip()
    if c.startswith("#"):
        h = c.lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
        a = 1.0
    else:
        inner = c[c.find("(") + 1 : c.rfind(")")]
        parts = [p.strip() for p in inner.split(",")]
        r, g, b = (int(float(p)) for p in parts[:3])
        a = float(parts[3]) if len(parts) > 3 else 1.0
    # 半透明色按 alpha 朝白底混合，得到"看起来"的亮度
    blended = tuple(v * a + 255 * (1 - a) for v in (r, g, b))
    return 0.2126 * blended[0] + 0.7152 * blended[1] + 0.0722 * blended[2]


@pytest.mark.parametrize("is_dark", [True, False])
def test_heatmap_levels_go_dark_with_more_usage(render_mod, is_dark):
    """5 档色阶必须亮度单调递减：档1(少) 最亮 → 档5(多) 最深"""
    levels = render_mod._palette(is_dark)["levels"]
    assert len(levels) == 5
    lums = [_lum(c) for c in levels]
    for i in range(1, len(lums)):
        assert lums[i] < lums[i - 1], (
            f"色阶方向反了（{'暗色' if is_dark else '浅色'}）: "
            f"档{i + 1} 应比档{i} 更深，实测亮度 {lums[i]:.1f} >= {lums[i - 1]:.1f}"
        )


def test_heatmap_dark_top_level_visible_against_background(render_mod):
    """暗色最高档不能沉进背景（#1e1e1e 亮度约 30）

    这是「越深越多」在深色底上的固有约束：一味求深会让用量最高的日子最不显眼。
    要求档5 与背景的亮度差 >= 30（约 2 倍背景亮度）。
    """
    bg = _lum("#1e1e1e")
    top = _lum(render_mod._palette(True)["levels"][-1])
    assert top - bg >= 30, f"最高档太暗，与背景差仅 {top - bg:.1f}"


def test_heatmap_levels_are_distinguishable(render_mod):
    """相邻档位之间要能看出差别（亮度差 >= 15）"""
    for is_dark in (True, False):
        lums = [_lum(c) for c in render_mod._palette(is_dark)["levels"]]
        for i in range(1, len(lums)):
            gap = lums[i - 1] - lums[i]
            assert gap >= 15, (
                f"相邻档位区分度不足（{'暗色' if is_dark else '浅色'}）: "
                f"档{i}→档{i + 1} 亮度差仅 {gap:.1f}"
            )