# -*- coding: utf-8 -*-
"""calendar UI 组件入口 — 欢迎卡片日历 tab

通过 register_welcome_tab 注册为欢迎卡片的新 tab（mode_key="calendar"）。
render_func 返回独立 HTML 片段（内联样式 + 预渲染网格 + onclick 切换），
经欢迎卡片 markdown→CodeWebViewer(QWebEngineView) 管线渲染。

渲染约束（骨架 updateContent 用 innerHTML 注入内容）：
- `<script>` 标签不会执行（HTML 规范，innerHTML 注入的 script 被忽略）→
  日历网格由 Python 预渲染，上/下月切换用 onclick 内联立即执行函数
- `<style>` 标签注入后生效 → 样式全部内联在此
"""

import calendar as _calendar
import sys
from datetime import datetime

# 上/下月切换 JS（onclick 内联，无 <script> 依赖）。
# 占位符由 Python 注入：TODAY_Y / TODAY_M / TODAY_D（今天）、DELTA（±1）。
# 用 DOM API 构建格子（textContent），避免 HTML 字符串引号与 onclick 属性冲突。
_CAL_SHIFT_JS = """(function(b,dl){{
var w=b.closest('.cal-wrap'),y=+w.getAttribute('data-y'),m=+w.getAttribute('data-m');
m+=dl;if(m<1){{m=12;y--}}if(m>12){{m=1;y++}}
w.setAttribute('data-y',y);w.setAttribute('data-m',m);
var g=w.querySelector('.cal-grid');g.innerHTML='';
var off=(new Date(y,m-1,1).getDay()+6)%7,days=new Date(y,m,0).getDate(),pd=new Date(y,m-1,0).getDate();
var i,n=1;
function add(num,extra){{var e=document.createElement('div');e.className='cal-cell'+(extra||'');e.textContent=num;g.appendChild(e)}}
for(i=0;i<off;i++)add(pd-off+1+i,' cal-other');
for(i=1;i<=days;i++){{if(i===TODAY_D&&y===TODAY_Y&&m===TODAY_M)add(i,' cal-today');else add(i,'')}}
while((off+days+n-1)%7!==0){{add(n,' cal-other');n++}}
w.querySelector('.cal-title').textContent=y+' 年 '+m+' 月';
}})(this,DELTA)"""


def _build_calendar_cells(year: int, month: int, day: int) -> str:
    """预渲染当月日期网格 HTML（周一起始 + 前后月补位 + 今天高亮）

    Returns:
        网格内各 <div class="cal-cell"> 拼接串（7 列整数行）
    """
    first_weekday = _calendar.weekday(year, month, 1)  # 周一=0
    days_in_month = _calendar.monthrange(year, month)[1]
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    prev_days = _calendar.monthrange(prev_year, prev_month)[1]

    cells = []
    for i in range(first_weekday):
        cells.append(f'<div class="cal-cell cal-other">{prev_days - first_weekday + 1 + i}</div>')
    for d in range(1, days_in_month + 1):
        cls = "cal-cell cal-today" if d == day else "cal-cell"
        cells.append(f'<div class="{cls}">{d}</div>')
    n = 1
    while len(cells) % 7 != 0:
        cells.append(f'<div class="cal-cell cal-other">{n}</div>')
        n += 1
    return "".join(cells)


def _build_clock_ticks_html() -> str:
    """预渲染 12 个表盘刻度（整点 12/3/6/9 加长加粗）

    刻度用绝对定位 + transform: rotate(a) translateY(-r) 对齐表盘圆周，
    整点与普通刻度共 12 个，Python 预渲染（无 <script> 依赖）。
    """
    ticks = []
    for i in range(12):
        angle = i * 30
        if i % 3 == 0:
            ticks.append(
                f'<div class="tick tick-major" style="transform:rotate({angle}deg) translateY(-70px)"></div>'
            )
        else:
            ticks.append(
                f'<div class="tick" style="transform:rotate({angle}deg) translateY(-74px)"></div>'
            )
    return "".join(ticks)


def _build_clock_html(now: datetime) -> str:
    """预渲染圆形时钟：表盘 + 刻度 + 时/分/秒针 + 中心点 + 日期

    指针走纯 CSS 动画（innerHTML 注入的 <script> 不执行）：
    - 每根指针一个 @keyframes cal-spin 旋转动画
    - animation-delay 取负秒数对齐渲染时刻的真实时间（如秒针 -{s}s → 立即停在第 s 格）
    - 秒针 steps(60) 每秒跳一格，分/时针 linear 平滑走动
    """
    h, m, s = now.hour % 12, now.minute, now.second
    week_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
    return f"""<div class="cal-clock">
<div class="clock-face">
  {_build_clock_ticks_html()}
  <div class="hand hand-hour" style="animation-delay:-{h * 3600 + m * 60 + s}s"></div>
  <div class="hand hand-minute" style="animation-delay:-{m * 60 + s}s"></div>
  <div class="hand hand-second" style="animation-delay:-{s}s"></div>
  <div class="clock-dot"></div>
</div>
<div class="clock-date">{now.month} 月 {now.day} 日 · {week_cn}</div>
</div>"""


def _render_calendar_html(ctx: dict | None = None) -> str:
    """渲染当月日历 HTML：左侧日历（月标题 + 周表头 + 日期网格）+ 右侧圆形时钟

    网格与时钟刻度由 Python 预渲染（innerHTML 注入的 <script> 不执行），
    上/下月切换走 onclick 内联 JS，指针走 CSS 动画。
    明暗配色跟随主程序注入的 ctx["is_dark"]（与 context-stats 等插件一致），
    ctx 缺失（旧主程序）时默认暗色（DriFox 默认深色主题）。
    """
    now = datetime.now()
    y, m, d = now.year, now.month, now.day
    cells = _build_calendar_cells(y, m, d)
    shift = _CAL_SHIFT_JS.replace("TODAY_Y", str(y)).replace("TODAY_M", str(m)).replace("TODAY_D", str(d))
    is_dark = ctx.get("is_dark") if isinstance(ctx, dict) else None
    if is_dark is None:
        is_dark = True
    # 明暗两套 CSS 变量，按 is_dark 注入（不用 prefers-color-scheme，它与 Qt 主题不同步）
    vars_light = (
        "--cal-text: #333; --cal-muted: #999; --cal-other: #ccc; "
        "--cal-border: rgba(0,0,0,0.12); --cal-nav-bg: rgba(0,0,0,0.04); "
        "--cal-nav-hover: rgba(0,0,0,0.09); --cal-accent: #2d8cf0; "
        "--cal-clock-bg: rgba(0,0,0,0.04); --cal-hand: #333;"
    )
    vars_dark = (
        "--cal-text: #e6e6e6; --cal-muted: #8a8a8a; --cal-other: #555; "
        "--cal-border: rgba(255,255,255,0.14); --cal-nav-bg: rgba(255,255,255,0.06); "
        "--cal-nav-hover: rgba(255,255,255,0.12); --cal-accent: #5aa2f5; "
        "--cal-clock-bg: rgba(255,255,255,0.06); --cal-hand: #e6e6e6;"
    )
    css_vars = vars_dark if is_dark else vars_light
    return f"""<div class="cal-wrap" data-y="{y}" data-m="{m}">
<div class="cal-main">
<div class="cal-head">
  <button class="cal-nav" onclick="{shift.replace('DELTA', '-1')}" title="上一月">‹</button>
  <div class="cal-title">{y} 年 {m} 月</div>
  <button class="cal-nav" onclick="{shift.replace('DELTA', '1')}" title="下一月">›</button>
</div>
<div class="cal-week"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
<div class="cal-grid">{cells}</div>
</div>
{_build_clock_html(now)}
</div>
<style>
.cal-wrap {{ max-width: 760px; margin: 0 auto; font-family: inherit; display: flex; align-items: center; justify-content: center; gap: 44px; flex-wrap: wrap; }}
.cal-main {{ flex: 1 1 300px; max-width: 480px; min-width: 280px; }}
.cal-head {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }}
.cal-title {{ font-size: 15px; font-weight: 600; letter-spacing: 0.02em; }}
.cal-nav {{
  width: 28px; height: 28px; border: 1px solid var(--cal-border); border-radius: 8px;
  background: var(--cal-nav-bg); color: var(--cal-text) !important; font-size: 16px; line-height: 1;
  cursor: pointer; padding: 0;
}}
.cal-nav:hover {{ background: var(--cal-nav-hover); }}
.cal-week {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; margin-bottom: 4px; }}
.cal-week span {{ text-align: center; font-size: 11px; color: var(--cal-muted) !important; padding: 4px 0; }}
.cal-grid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }}
.cal-cell {{
  text-align: center; font-size: 13px; padding: 7px 0; border-radius: 8px;
  color: var(--cal-text) !important;
}}
.cal-other {{ color: var(--cal-other) !important; }}
.cal-today {{
  background: var(--cal-accent); color: #fff !important; font-weight: 700;
}}
.cal-clock {{ display: flex; flex-direction: column; align-items: center; gap: 10px; }}
.clock-face {{
  position: relative; width: 160px; height: 160px; border-radius: 50%;
  background: var(--cal-clock-bg); border: 1px solid var(--cal-border);
  box-shadow: inset 0 0 8px rgba(0,0,0,0.05);
}}
.tick {{ position: absolute; left: 50%; top: 50%; width: 2px; height: 8px; margin: -4px 0 0 -1px; border-radius: 1px; background: var(--cal-muted); }}
.tick-major {{ height: 16px; margin-top: -8px; background: var(--cal-text); }}
@keyframes cal-spin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
.hand {{ position: absolute; left: 50%; bottom: 50%; transform-origin: 50% 100%; border-radius: 3px 3px 1px 1px; }}
.hand-hour {{ width: 5px; height: 34px; margin-left: -2.5px; background: var(--cal-hand); animation: cal-spin 43200s linear infinite; }}
.hand-minute {{ width: 3px; height: 50px; margin-left: -1.5px; background: var(--cal-hand); animation: cal-spin 3600s linear infinite; }}
.hand-second {{ width: 1.5px; height: 58px; margin-left: -0.75px; background: var(--cal-accent); animation: cal-spin 60s steps(60) infinite; }}
.clock-dot {{ position: absolute; left: 50%; top: 50%; width: 12px; height: 12px; margin: -6px 0 0 -6px; border-radius: 50%; background: var(--cal-hand); border: 2px solid var(--cal-clock-bg); }}
.clock-date {{ font-size: 12px; color: var(--cal-muted); letter-spacing: 0.03em; }}
:root {{
  {css_vars}
}}
</style>
"""


def register_ui(registry):
    """注册 calendar 的 UI 组件（欢迎卡片日历 tab）"""
    # 清理旧子模块缓存（热重载兼容，与 file-tree/share-history 一致）
    prefix = "ui_plugin_calendar."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    registry.register_welcome_tab(
        plugin_name="calendar",
        mode_key="calendar",
        label="📅 日历",
        render_func=lambda ctx: _render_calendar_html(ctx),
    )
