# -*- coding: utf-8 -*-
"""
live_data — 实时数据查询工具集（live-data 插件）。

大模型训练数据有截止时间，凡是「此刻的真实数值」只能靠联网取回。
本插件把 8 个免密钥公开接口聚合成 4 个工具：

    finance_live   汇率 / A股个股 / 大盘指数 / 国际金价
    dev_live       npm 包版本 / PyPI 包版本 / GitHub 仓库信息
    weather_live   实时天气 + 未来预报（城市名 → 经纬度自动解析）
    misc_live      B站视频数据 / IP 归属地

纯标准库实现（urllib），无第三方依赖，无需任何 API key。
所有接口于 2026-10-27 本机实测通过，契约见 README.md §数据源。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from app.tools.result import ToolResult

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
TIMEOUT = 15

# 新浪行情返回 GBK 且有多条 var 声明，必须用 GBK 解码
SINA_UA_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://finance.sina.com.cn/",
    "Accept": "*/*",
}


class LiveDataError(Exception):
    """数据源不可用或数据不符合预期。"""


# ---------------------------------------------------------------- HTTP 基础

class HttpStatusError(LiveDataError):
    """带状态码的请求失败，供调用方区分配额/不存在等情况。"""

    def __init__(self, status: int, url: str = ""):
        super().__init__(f"接口返回 HTTP {status}")
        self.status = status
        self.url = url


def _get(url: str, headers: dict | None = None, encoding: str = "utf-8",
         timeout: int = TIMEOUT) -> str:
    h = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(encoding, "replace")
    except urllib.error.HTTPError as e:
        raise HttpStatusError(e.code, url) from e
    except urllib.error.URLError as e:
        raise LiveDataError(f"网络不可达：{e.reason}") from e
    except TimeoutError as e:
        raise LiveDataError(f"请求超时（{timeout}s）") from e


def _get_json(url: str, headers: dict | None = None) -> dict:
    try:
        return json.loads(_get(url, headers=headers))
    except json.JSONDecodeError as e:
        raise LiveDataError(f"响应不是合法 JSON：{e}") from e


# ---------------------------------------------------------------- 格式化小工具

def _wan(value: float) -> str:
    """按中文习惯给金额加万/亿单位。"""
    neg = value < 0
    v = abs(value)
    if v >= 1e8:
        return f"{'-' if neg else ''}{v / 1e8:.2f}亿"
    if v >= 1e4:
        return f"{'-' if neg else ''}{v / 1e4:.2f}万"
    return f"{value:.2f}"


def _signed(value: float, unit: str = "") -> str:
    return f"{value:+.2f}{unit}"


# ================================================================ finance_live

# 常见货币中文名，未命中回退代码本身
_CCY = {
    "CNY": "人民币", "USD": "美元", "EUR": "欧元", "JPY": "日元", "GBP": "英镑",
    "HKD": "港币", "KRW": "韩元", "AUD": "澳元", "CAD": "加元", "SGD": "新加坡元",
    "CHF": "瑞士法郎", "TWD": "新台币", "THB": "泰铢", "MYR": "林吉特",
    "RUB": "卢布", "INR": "印度卢比", "NZD": "新西兰元", "TRY": "里拉",
    "BRL": "雷亚尔", "MXN": "墨西哥比索", "ZAR": "南非兰特", "AED": "迪拉姆",
}


def _ccy_name(code: str) -> str:
    return f"{_CCY.get(code, code)}（{code}）"


_INDEX_MAP = {
    "上证": "s_sh000001", "上证指数": "s_sh000001", "sh000001": "s_sh000001",
    "深证": "s_sz399001", "深证成指": "s_sz399001", "sz399001": "s_sz399001",
    "创业板": "s_sz399006", "创业板指": "s_sz399006", "sz399006": "s_sz399006",
    "沪深300": "s_sh000300", "sh000300": "s_sh000300",
    "科创50": "s_sh000688", "sh000688": "s_sh000688",
}


def _fx(base: str, target: str, amount: float) -> str:
    data = _get_json(f"https://open.er-api.com/v6/latest/{base.upper()}")
    if data.get("result") != "success":
        raise LiveDataError(f"汇率接口返回异常：{data.get('error-type', '未知')}")
    rates = data.get("rates") or {}
    t = target.upper()
    if t not in rates:
        raise LiveDataError(f"不支持的目标币种「{target}」，可用币种见 open.er-api.com")
    rate = float(rates[t])
    inv = 1.0 / rate if rate else 0.0
    updated = data.get("time_last_update_utc", "")
    lines = [
        f"💱 汇率  {_ccy_name(base.upper())} → {_ccy_name(t)}",
        "─" * 30,
        f"  1 {base.upper()} = {rate:.6f} {t}",
        f"  反向：1 {t} = {inv:.6f} {base.upper()}",
        f"  换算：{amount:g} {base.upper()} = {amount * rate:.2f} {t}",
        f"  参考报价（百元）：100 {base.upper()} = {100 * rate:.2f} {t}",
        "",
        f"更新于 {updated}",
        "数据源：open.er-api.com",
    ]
    return "\n".join(lines)


def _stock(code: str) -> str:
    code = code.strip().lower()
    if not code:
        raise LiveDataError("请提供股票代码，如 sh600519 / sz000001 / 600519")
    if code.isdigit():
        # 6 开头默认沪市，其余默认深市
        code = ("sh" if code.startswith("6") else "sz") + code
    raw = _get(f"https://hq.sinajs.cn/list={code}", headers=SINA_UA_HEADERS, encoding="gbk")
    # 形如：var hq_str_sh600519="贵州茅台,今开,昨收,现价,最高,最低,...";
    key = f'hq_str_{code}="'
    i = raw.find(key)
    if i < 0:
        raise LiveDataError(f"未取到「{code}」行情，代码可能不存在或格式不对")
    j = raw.find('"', i + len(key))
    fields = raw[i + len(key):j].split(",")
    if len(fields) < 32 or not fields[0]:
        raise LiveDataError(f"「{code}」返回空数据，请确认代码是否正确")
    name, open_, prev, price = fields[0], float(fields[1]), float(fields[2]), float(fields[3])
    high, low = float(fields[4]), float(fields[5])
    volume = float(fields[8]) / 100.0     # 股 → 手
    amount = float(fields[9])             # 元
    date, time_ = fields[30], fields[31]
    if price == 0:
        raise LiveDataError(f"「{name}（{code}）」当前无成交价，可能停牌或未开盘")
    delta = price - prev
    pct = delta / prev * 100 if prev else 0.0
    return "\n".join([
        f"📈 A股行情  {name}（{code}）",
        "─" * 30,
        f"  现价    {price:.2f} 元   {_signed(delta)}（{_signed(pct, '%')}）",
        f"  今开 / 昨收  {open_:.2f} / {prev:.2f}",
        f"  最高 / 最低  {high:.2f} / {low:.2f}",
        f"  成交量  {volume:.0f} 手   成交额  {_wan(amount)}元",
        "",
        f"时间 {date} {time_}",
        "数据源：新浪财经",
    ])


def _index(name: str) -> str:
    sym = _INDEX_MAP.get(name.strip())
    if not sym:
        opts = "、".join(["上证", "深证", "创业板", "沪深300", "科创50"])
        raise LiveDataError(f"未知指数「{name}」，可选：{opts}")
    raw = _get(f"https://hq.sinajs.cn/list={sym}", headers=SINA_UA_HEADERS, encoding="gbk")
    # 形如：var hq_str_s_sh000001="上证指数,点位,涨跌额,涨跌幅,成交量,成交额";
    key = f'hq_str_{sym}="'
    i = raw.find(key)
    if i < 0:
        raise LiveDataError(f"未取到「{name}」行情")
    j = raw.find('"', i + len(key))
    fields = raw[i + len(key):j].split(",")
    if len(fields) < 6 or not fields[0]:
        raise LiveDataError(f"「{name}」返回空数据")
    title, point, delta, pct = fields[0], float(fields[1]), float(fields[2]), float(fields[3])
    volume = float(fields[4])       # 手
    amount = float(fields[5])       # 万元
    return "\n".join([
        f"📊 大盘指数  {title}",
        "─" * 30,
        f"  点位    {point:.2f}   {_signed(delta)}（{_signed(pct, '%')}）",
        f"  成交量  {_wan(volume * 100)}股",
        f"  成交额  {_wan(amount * 1e4)}元",
        "",
        "数据源：新浪财经",
    ])


def _gold() -> str:
    raw = _get("https://hq.sinajs.cn/list=hf_XAU", headers=SINA_UA_HEADERS, encoding="gbk")
    # 形如：var hq_str_hf_XAU="现价,买价,卖价,最高,最低,昨收,时间,昨结,开盘,...";
    key = 'hq_str_hf_XAU="'
    i = raw.find(key)
    if i < 0:
        raise LiveDataError("未取到国际金价数据")
    j = raw.find('"', i + len(key))
    fields = raw[i + len(key):j].split(",")
    if len(fields) < 9 or not fields[0]:
        raise LiveDataError("国际金价返回空数据")
    price = float(fields[0])
    high, low, prev = float(fields[3]), float(fields[4]), float(fields[5])
    stamp = fields[6]
    date = fields[12] if len(fields) > 12 else ""
    delta = price - prev
    pct = delta / prev * 100 if prev else 0.0

    lines = [
        "🥇 国际金价  伦敦金现货（XAU/USD）",
        "─" * 30,
        f"  最新价  {price:.2f} 美元/盎司   {_signed(delta)}（{_signed(pct, '%')}）",
        f"  昨收    {prev:.2f} 美元/盎司",
        f"  最高 / 最低  {high:.2f} / {low:.2f}",
    ]

    # 折算人民币克价：1 金衡盎司 = 31.1035 克
    try:
        fx = _get_json("https://open.er-api.com/v6/latest/USD")
        rate = float((fx.get("rates") or {}).get("CNY") or 0)
        if rate > 0:
            cny_g = price * rate / 31.1035
            lines += [
                "",
                f"  折算：{cny_g:.2f} 元/克（1 美元 = {rate:.4f} 元）",
                "  公式：元/克 = 美元/盎司 × 汇率 ÷ 31.1035",
            ]
    except LiveDataError:
        lines.append("")
        lines.append("  （汇率接口暂不可用，跳过人民币折算）")

    lines += ["", f"时间 {date} {stamp}".strip(), "数据源：新浪财经 + open.er-api.com", ""]
    lines.append("注：此处为国际原料金价，金店零售含加工费与品牌溢价，高于此价")
    return "\n".join(lines)


def _finance(kind: str, kwargs: dict) -> str:
    if kind == "汇率":
        return _fx(kwargs.get("base") or "USD", kwargs.get("target") or "CNY",
                   float(kwargs.get("amount") or 100))
    if kind == "股票":
        return _stock(kwargs.get("code") or "")
    if kind == "指数":
        return _index(kwargs.get("index_name") or "上证")
    return _gold()


# ================================================================ dev_live

def _npm(pkg: str) -> str:
    # scoped 包名需要 URL 编码：@scope/name → @scope%2fname
    path = urllib.parse.quote(pkg.strip(), safe="@")
    data = _get_json(f"https://registry.npmjs.org/{path}/latest")
    name = data.get("name") or pkg
    version = data.get("version") or "?"
    desc = data.get("description") or "（无描述）"
    lines = [
        f"📦 npm 包  {name}",
        "─" * 30,
        f"  最新版  {version}",
        f"  简介    {desc}",
    ]
    lic = data.get("license")
    if lic:
        lines.append(f"  许可    {lic if isinstance(lic, str) else lic.get('type', '?')}")
    repo = data.get("repository")
    repo_url = repo.get("url", "") if isinstance(repo, dict) else str(repo or "")
    if repo_url:
        repo_url = repo_url.replace("git+", "").replace(".git", "")
        lines.append(f"  仓库    {repo_url}")
    homepage = data.get("homepage")
    if homepage:
        lines.append(f"  主页    {homepage}")
    deps = data.get("dependencies") or {}
    lines.append(f"  依赖数  {len(deps)}")
    if deps:
        top = list(deps.keys())[:8]
        lines.append(f"  主要依赖  {', '.join(top)}{' …' if len(deps) > 8 else ''}")
    dist = data.get("dist") or {}
    if dist.get("unpackedSize"):
        lines.append(f"  包体积  {dist['unpackedSize'] / 1024:.0f} KB")
    lines += ["", "数据源：registry.npmjs.org"]
    return "\n".join(lines)


def _pypi(pkg: str) -> str:
    pkg = pkg.strip()
    data = _get_json(f"https://pypi.org/pypi/{urllib.parse.quote(pkg)}/json")
    info = data.get("info") or {}
    name = info.get("name") or pkg
    version = info.get("version") or "?"
    summary = info.get("summary") or "（无摘要）"
    lines = [
        f"🐍 PyPI 包  {name}",
        "─" * 30,
        f"  最新版  {version}",
        f"  摘要    {summary}",
    ]
    pv = info.get("requires_python")
    if pv:
        lines.append(f"  Python  {pv}")
    lic = info.get("license") or ""
    if lic and len(lic) < 40:
        lines.append(f"  许可    {lic}")
    author = info.get("author")
    if author:
        lines.append(f"  作者    {author}")
    home = info.get("home_page") or info.get("project_url") or ""
    if home:
        lines.append(f"  主页    {home}")
    reqs = info.get("requires_dist") or []
    if reqs:
        lines.append(f"  依赖    {', '.join(reqs[:6])}{' …' if len(reqs) > 6 else ''}")

    # 发布时间：从 urls 里取 upload_time
    urls = data.get("urls") or []
    stamps = [u.get("upload_time") for u in urls if u.get("upload_time")]
    if stamps:
        lines.append(f"  发布    {min(stamps)[:10]}")
    lines += ["", "数据源：pypi.org"]
    return "\n".join(lines)


def _github(repo: str) -> str:
    repo = repo.strip().strip("/")
    # 支持完整 URL 或直接 owner/repo
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if repo.startswith(prefix):
            repo = repo[len(prefix):]
    if repo.count("/") != 1:
        raise LiveDataError(f"仓库格式应为 owner/repo，收到「{repo}」")
    headers = {"Accept": "application/vnd.github+json"}
    # 未认证限额 60 次/小时且按出口 IP 共享，配了 token 就带上（5000 次/小时）
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    authed = False
    if token:
        headers["Authorization"] = f"Bearer {token}"
        authed = True
    endpoints = [f"https://api.github.com/repos/{repo}"]
    # 仓库接口被限流时回退到搜索接口（独立配额桶），取其基础字段兜底
    endpoints.append(
        f"https://api.github.com/search/repositories?q="
        + urllib.parse.quote(f"repo:{repo}", safe=":") + "&per_page=1"
    )
    data = None
    for idx, url in enumerate(endpoints):
        try:
            raw = _get_json(url, headers=headers)
        except HttpStatusError as e:  # noqa: PERF203
            if e.status == 403:
                if idx == 0:
                    continue  # 主接口限流 → 试搜索接口
                raise LiveDataError(
                    "GitHub API 已限流（未认证 60 次/小时，按出口 IP 共享）。"
                    "设置 GITHUB_TOKEN 环境变量可提到 5000 次/小时"
                ) from e
            if e.status == 404:
                raise LiveDataError(
                    f"仓库不存在或已私有：{repo}"
                ) from e
            raise LiveDataError(f"GitHub 返回 HTTP {e.status}") from e
        if idx == 0:
            data = raw
            break
        # 搜索 — 结果需解包再走同一套渲染，补回 search 独有的字段
        items = raw.get("items") or []
        if not items:
            raise LiveDataError(f"仓库不存在或已私有：{repo}")
        data = items[0]
        data = dict(data)
        data.setdefault("subscribers_count", data.get("watchers_count"))
        break
    if not data:
        raise LiveDataError(f"未取到仓库数据：{repo}")
    name = data.get("full_name") or repo
    desc = data.get("description") or "（无描述）"
    stars = data.get("stargazers_count") or 0
    forks = data.get("forks_count") or 0
    issues = data.get("open_issues_count") or 0
    lang = data.get("language") or "—"
    watchers = data.get("subscribers_count") or 0
    lines = [
        f"🐙 GitHub 仓库  {name}",
        "─" * 30,
        f"  简介    {desc}",
        f"  ★ Star  {stars:,}     🍴 Fork  {forks:,}     👁 Watch  {watchers:,}",
        f"  未关闭 issue  {issues:,}",
        f"  主语言  {lang}",
    ]
    if data.get("license"):
        lines.append(f"  许可    {(data['license'] or {}).get('spdx_id') or (data['license'] or {}).get('name') or '?'}")
    if data.get("created_at"):
        lines.append(f"  创建于  {data['created_at'][:10]}")
    if data.get("pushed_at"):
        lines.append(f"  最后推送  {data['pushed_at'][:10]}")
    if data.get("homepage"):
        lines.append(f"  主页    {data['homepage']}")
    lines += ["", "数据源：api.github.com（未认证限额 60 次/小时）"]
    return "\n".join(lines)


def _dev(kind: str, target: str) -> str:
    target = (target or "").strip()
    if not target:
        raise LiveDataError(f"请提供包名/仓库名（kind={kind}）")
    if kind == "npm":
        return _npm(target)
    if kind == "pypi":
        return _pypi(target)
    return _github(target)


# ================================================================ weather_live

# Open-Meteo WMO weather code → 中文
_WMO = {
    0: "晴", 1: "大部晴朗", 2: "局部多云", 3: "阴",
    45: "雾", 48: "冻雾",
    51: "毛毛雨（弱）", 53: "毛毛雨（中）", 55: "毛毛雨（强）",
    56: "冻毛毛雨（弱）", 57: "冻毛毛雨（强）",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨（弱）", 67: "冻雨（强）",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "中阵雨", 82: "强阵雨",
    85: "小阵雪", 86: "大阵雪",
    95: "雷暴", 96: "雷暴伴冰雹", 99: "强雷暴伴冰雹",
}


def _beaufort(kmh: float) -> str:
    table = [(1, 0), (5, 1), (11, 2), (19, 3), (28, 4), (38, 5), (49, 6), (61, 7),
             (74, 8), (88, 9), (102, 10), (117, 11)]
    for limit, lv in table:
        if kmh < limit:
            return f"{lv} 级"
    return "12 级以上"


def _geocode(city: str) -> tuple[str, float, float, str]:
    url = ("https://geocoding-api.open-meteo.com/v1/search?name="
           f"{urllib.parse.quote(city)}&count=1&language=zh&format=json")
    data = _get_json(url)
    results = data.get("results") or []
    if not results:
        raise LiveDataError(f"未找到城市「{city}」，建议换用英文名或更具体的地名")
    r = results[0]
    label = "、".join([x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x])
    return label, float(r["latitude"]), float(r["longitude"]), r.get("timezone", "auto")


def _weather_impl(city: str) -> str:
    city = (city or "").strip()
    if not city:
        raise LiveDataError("请提供城市名（中英文均可，如 北京 / Shanghai / Tokyo）")
    label, lat, lon, tz = _geocode(city)
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "weather_code,wind_speed_10m,precipitation"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max"
        "&forecast_days=4&timezone=" + urllib.parse.quote(tz)
    )
    data = _get_json(url)
    cur = data.get("current") or {}
    if not cur:
        raise LiveDataError("天气接口未返回实况数据")
    temp = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    hum = cur.get("relative_humidity_2m")
    code = int(cur.get("weather_code") or 0)
    wind = cur.get("wind_speed_10m")
    desc = _WMO.get(code, f"天气代码 {code}")

    lines = [
        f"🌤 天气实况  {label}",
        "─" * 30,
        f"  气温    {temp}°C（体感 {feels}°C）",
        f"  天况    {desc}",
        f"  湿度    {hum}%",
        f"  风速    {wind} km/h（{_beaufort(float(wind or 0))}）",
    ]
    now = cur.get("time", "")
    if now:
        lines.append(f"  观测时间  {now.replace('T', ' ')}")

    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    if dates:
        lines.append("")
        lines.append("📅 未来预报")
        for i, d in enumerate(dates[:3]):
            hi = daily.get("temperature_2m_max", [])[i]
            lo = daily.get("temperature_2m_min", [])[i]
            dc = _WMO.get(daily.get("weather_code", [])[i], "?")
            pop = daily.get("precipitation_probability_max", [])[i]
            pop_txt = f"  降水概率 {pop}%" if pop is not None else ""
            tag = "今天" if i == 0 else d
            lines.append(f"  {tag}  {dc}  {lo}~{hi}°C{pop_txt}")

    lines += ["", f"坐标 {lat:.2f}, {lon:.2f}", "数据源：Open-Meteo"]
    return "\n".join(lines)


# ================================================================ misc_live

def _bili(target: str) -> str:
    """按 BV/av/URL 取视频数据。接口契约与 bili-summary 插件同源。"""
    t = (target or "").strip()
    if not t:
        raise LiveDataError("请提供 BV 号、av 号或视频链接")
    m = (None, )
    bv = None
    aid = None
    import re as _re
    mm = _re.search(r"(BV[0-9A-Za-z]{10})", t)
    if mm:
        bv = mm.group(1)
    else:
        mm = _re.search(r"(?:av|aid[=_])(\d{1,15})", t)
        if mm:
            aid = mm.group(1)
    if not bv and not aid:
        raise LiveDataError(f"未能从「{t}」中解析出 BV 号或 av 号")
    url = ("https://api.bilibili.com/x/web-interface/view?"
           + (f"bvid={bv}" if bv else f"aid={aid}"))
    data = _get_json(url, headers={"Referer": "https://www.bilibili.com/"})
    if data.get("code") != 0:
        raise LiveDataError(f"B 站返回错误：{data.get('message')}（code={data.get('code')}）")
    d = data.get("data") or {}
    stat = d.get("stat") or {}
    owner = d.get("owner") or {}
    sec = int(d.get("duration") or 0)
    dur = f"{sec // 60}:{sec % 60:02d}" if sec < 3600 else f"{sec // 3600}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"
    pub = d.get("pubdate")
    pub_txt = time.strftime("%Y-%m-%d", time.localtime(pub)) if pub else "—"
    lines = [
        f"📺 B站视频  {d.get('title') or '?'}",
        "─" * 30,
        f"  UP 主  {owner.get('name') or '?'}（mid {owner.get('mid') or '?'}）",
        f"  BV    {d.get('bvid') or '?'}    av{d.get('aid') or '?'}",
        f"  时长  {dur}    发布  {pub_txt}",
        f"  分区  {d.get('tname') or '—'}",
        "",
        f"  ▶ 播放  {_wan(float(stat.get('view') or 0))}"
        f"    💬 弹幕  {_wan(float(stat.get('danmaku') or 0))}",
        f"  💬 评论  {_wan(float(stat.get('reply') or 0))}"
        f"    👍 点赞  {_wan(float(stat.get('like') or 0))}",
        f"  🪙 投币  {_wan(float(stat.get('coin') or 0))}"
        f"    ⭐ 收藏  {_wan(float(stat.get('favorite') or 0))}",
        f"  🔁 分享  {_wan(float(stat.get('share') or 0))}",
        "",
        f"https://www.bilibili.com/video/{d.get('bvid') or ''}",
        "数据源：api.bilibili.com",
    ]
    desc = (d.get("desc") or "").strip()
    if desc:
        lines.insert(3, f"  简介  {desc[:80]}{'…' if len(desc) > 80 else ''}")
    return "\n".join(lines)


def _ip(target: str) -> str:
    t = (target or "").strip()
    url = f"https://api.ip.sb/geoip/{urllib.parse.quote(t)}" if t else "https://api.ip.sb/geoip/"
    data = _get_json(url)
    lines = [
        f"🌐 IP 归属地  {data.get('ip') or t or '本机出口'}",
        "─" * 30,
        f"  位置    {data.get('country') or '—'} {data.get('region') or ''} {data.get('city') or ''}".strip(),
        f"  运营商  {data.get('organization') or data.get('isp') or '—'}",
        f"  ASN     {data.get('asn') or '—'} {data.get('asn_organization') or ''}".strip(),
        f"  时区    {data.get('timezone') or '—'}",
    ]
    lat, lon = data.get("latitude"), data.get("longitude")
    if lat is not None and lon is not None:
        lines.append(f"  坐标    {lat}, {lon}")
    lines += ["", "数据源：api.ip.sb"]
    return "\n".join(lines)


def _misc(kind: str, target: str) -> str:
    if kind == "bilibili":
        return _bili(target)
    return _ip(target)


# ================================================================ 工具实现与注册

_FINANCE_KINDS = ["汇率", "股票", "指数", "金价"]
_DEV_KINDS = ["npm", "pypi", "github"]
_MISC_KINDS = ["bilibili", "ip"]


def _impl(tool_ctx, **kwargs):
    tool = ""
    if tool_ctx is not None:
        tool = getattr(tool_ctx, "tool_name", "") or getattr(tool_ctx, "name", "") or ""
    if not tool:
        tool = kwargs.pop("__tool__", "")
    try:
        if tool == "finance_live":
            kind = (kwargs.get("kind") or "").strip()
            if kind not in _FINANCE_KINDS:
                return ToolResult(False, error=f"kind 必须是 {'/'.join(_FINANCE_KINDS)} 之一，收到「{kind}」")
            return ToolResult(True, content=_finance(kind, kwargs))
        if tool == "dev_live":
            kind = (kwargs.get("kind") or "").strip()
            if kind not in _DEV_KINDS:
                return ToolResult(False, error=f"kind 必须是 {'/'.join(_DEV_KINDS)} 之一，收到「{kind}」")
            return ToolResult(True, content=_dev(kind, kwargs.get("target") or ""))
        if tool == "weather_live":
            return ToolResult(True, content=_weather_impl(kwargs.get("city") or ""))
        if tool == "misc_live":
            kind = (kwargs.get("kind") or "").strip()
            if kind not in _MISC_KINDS:
                return ToolResult(False, error=f"kind 必须是 {'/'.join(_MISC_KINDS)} 之一，收到「{kind}」")
            return ToolResult(True, content=_misc(kind, kwargs.get("target") or ""))
        return ToolResult(False, error=f"未知工具：{tool}")
    except LiveDataError as e:
        return ToolResult(False, error=str(e))
    except (KeyError, IndexError, ValueError) as e:
        return ToolResult(False, error=f"解析数据失败：{type(e).__name__}: {e}")
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"live_data 内部异常：{type(e).__name__}: {e}")


_SCHEMA_COMMON_HEAD = {
    "type": "object",
    "additionalProperties": False,
}


def _schema(name: str, desc: str, props: dict, required: list) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


_FINANCE_SCHEMA = _schema(
    "finance_live",
    "查询实时金融数据，用 kind 选择类别："
    "汇率（原币种 base → 目标币种 target 的实时汇率与换算，数据源 open.er-api.com，覆盖 160+ 法币）；"
    "股票（A 股个股实时行情：现价/涨跌/开高低/成交量额，代码如 sh600519、sz000001，纯数字按 6 开头归沪市，数据源新浪财经）；"
    "指数（大盘指数实时点位：上证/深证/创业板/沪深300/科创50）；"
    "金价（国际伦敦金现货 XAU/USD，美元每盎司 + 按实时汇率折算人民币每克）。"
    "全部接口免密钥、无需任何 API key。注意：行情数据仅供参考，不构成投资建议。",
    {
        "kind": {"type": "string", "enum": _FINANCE_KINDS,
                 "description": "数据类别：汇率 / 股票 / 指数 / 金价"},
        "base": {"type": "string",
                 "description": "仅 kind=汇率，原币种代码，如 USD / CNY / EUR / JPY，默认 USD"},
        "target": {"type": "string",
                   "description": "仅 kind=汇率，目标币种代码，如 CNY / USD，默认 CNY"},
        "amount": {"type": "number",
                   "description": "仅 kind=汇率，要换算的原币种金额，默认 100"},
        "code": {"type": "string",
                 "description": "仅 kind=股票，股票代码：sh600519 / sz000001 / 600519"},
        "index_name": {"type": "string",
                       "description": "仅 kind=指数，指数名：上证 / 深证 / 创业板 / 沪深300 / 科创50，默认上证"},
    },
    ["kind"],
)

_DEV_SCHEMA = _schema(
    "dev_live",
    "查询开发者生态的实时公开数据，用 kind 选择平台："
    "npm（Node 包最新版本号、简介、许可、仓库、依赖数与包体积）；"
    "pypi（Python 包最新版本、摘要、requires_python、依赖与发布日期）；"
    "github（仓库 star/fork/watch/未关闭 issue/主语言/许可/创建与最后推送时间，"
    "target 可填 owner/repo 或完整 GitHub URL）。"
    "全部免密钥。GitHub 未认证调用限额 60 次/小时。",
    {
        "kind": {"type": "string", "enum": _DEV_KINDS,
                 "description": "平台：npm / pypi / github"},
        "target": {"type": "string",
                   "description": "包名或仓库标识。npm/pypi 填包名（支持 @scope/name）；"
                                  "github 填 owner/repo 或完整 URL"},
    },
    ["kind", "target"],
)

_WEATHER_SCHEMA = _schema(
    "weather_live",
    "查询指定城市的实时天气与未来 3 天预报：气温与体感温度、天况、湿度、风速（附蒲福风级）、"
    "观测时间，以及每日最高/最低温和降水概率。"
    "城市名支持中英文，自动完成地名→经纬度解析。"
    "数据源 Open-Meteo，免费免密钥。",
    {
        "city": {"type": "string",
                 "description": "城市名（中文或英文，如 北京 / Shanghai / Tokyo）"},
    },
    ["city"],
)

_MISC_SCHEMA = _schema(
    "misc_live",
    "杂项实时数据查询，用 kind 选择："
    "bilibili（B 站视频实时数据：标题/UP主/时长/分区/播放/弹幕/评论/点赞/投币/收藏/分享，"
    "target 支持 BV 号、av 号或视频链接）；"
    "ip（IP 归属地查询：国家/地区/城市/运营商/ASN/时区/坐标，target 留空则查本机公网出口 IP）。"
    "全部免密钥。",
    {
        "kind": {"type": "string", "enum": _MISC_KINDS,
                 "description": "类别：bilibili / ip"},
        "target": {"type": "string",
                   "description": "bilibili 填 BV 号/av 号/视频链接；ip 填 IP 地址，留空查本机"},
    },
    ["kind"],
)


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "finance_live", _FINANCE_SCHEMA, impl=_impl,
        danger="safe", icon="live_finance", cn_name="金融实时数据",
        group="实时数据",
        description="汇率/A股/大盘指数/国际金价实时查询（免密钥）",
        aliases=["FinanceLive"],
    )
    registry.register(
        "dev_live", _DEV_SCHEMA, impl=_impl,
        danger="safe", icon="live_dev", cn_name="开发包实时数据",
        group="实时数据",
        description="npm/PyPI/GitHub 包与仓库实时信息（免密钥）",
        aliases=["DevLive"],
    )
    registry.register(
        "weather_live", _WEATHER_SCHEMA, impl=_impl,
        danger="safe", icon="live_weather", cn_name="天气实况查询",
        group="实时数据",
        description="城市实时天气与 3 天预报（Open-Meteo，免密钥）",
        aliases=["WeatherLive"],
    )
    registry.register(
        "misc_live", _MISC_SCHEMA, impl=_impl,
        danger="safe", icon="live_misc", cn_name="杂项实时数据",
        group="实时数据",
        description="B站视频数据与 IP 归属地查询（免密钥）",
        aliases=["MiscLive"],
    )
