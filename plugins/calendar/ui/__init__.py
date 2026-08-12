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
var w=b.parentNode.parentNode,y=+w.getAttribute('data-y'),m=+w.getAttribute('data-m');
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


def _render_calendar_html() -> str:
    """渲染当月日历 HTML：月标题 + 周表头（周一起始）+ 预渲染日期网格 + 今天高亮

    网格由 Python 预渲染（innerHTML 注入的 <script> 不执行），
    上/下月切换走 onclick 内联 JS。明暗配色 prefers-color-scheme。
    """
    now = datetime.now()
    y, m, d = now.year, now.month, now.day
    cells = _build_calendar_cells(y, m, d)
    shift = _CAL_SHIFT_JS.replace("TODAY_Y", str(y)).replace("TODAY_M", str(m)).replace("TODAY_D", str(d))
    return f"""<div class="cal-wrap" data-y="{y}" data-m="{m}">
<div class="cal-head">
  <button class="cal-nav" onclick="{shift.replace('DELTA', '-1')}" title="上一月">‹</button>
  <div class="cal-title">{y} 年 {m} 月</div>
  <button class="cal-nav" onclick="{shift.replace('DELTA', '1')}" title="下一月">›</button>
</div>
<div class="cal-week"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
<div class="cal-grid">{cells}</div>
</div>
<style>
.cal-wrap {{ max-width: 560px; margin: 0 auto; font-family: inherit; }}
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
:root {{
  --cal-text: #333; --cal-muted: #999; --cal-other: #ccc;
  --cal-border: rgba(0,0,0,0.12); --cal-nav-bg: rgba(0,0,0,0.04);
  --cal-nav-hover: rgba(0,0,0,0.09); --cal-accent: #2d8cf0;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --cal-text: #e6e6e6; --cal-muted: #8a8a8a; --cal-other: #555;
    --cal-border: rgba(255,255,255,0.14); --cal-nav-bg: rgba(255,255,255,0.06);
    --cal-nav-hover: rgba(255,255,255,0.12); --cal-accent: #5aa2f5;
  }}
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
        render_func=lambda ctx: _render_calendar_html(),
    )
