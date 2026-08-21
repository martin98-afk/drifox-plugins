# -*- coding: utf-8 -*-
"""
weather_query — 天气查询工具（weather-query 插件）。

数据源：wttr.in 免费接口（无需 API key），format=j1 结构化 JSON。
自包含实现：仅标准库 urllib，不依赖主程序与第三方库。
"""
import json
import urllib.parse
import urllib.request

from app.tools.result import ToolResult

_API = "https://wttr.in"
_TIMEOUT = 10

_WMO = {
    "Clear": "晴", "Sunny": "晴", "Partly cloudy": "局部多云", "Partly sunny": "局部晴",
    "Cloudy": "多云", "Overcast": "阴", "Mist": "薄雾", "Fog": "雾", "Freezing fog": "冻雾",
    "Patchy rain possible": "可能有零星降雨", "Patchy rain nearby": "附近零星降雨",
    "Light rain": "小雨", "Moderate rain": "中雨", "Heavy rain": "大雨",
    "Light drizzle": "毛毛雨", "Patchy light drizzle": "零星毛毛雨",
    "Light freezing rain": "小雨冻雨", "Heavy freezing rain": "大冻雨",
    "Light snow": "小雪", "Moderate snow": "中雪", "Heavy snow": "大雪",
    "Patchy snow possible": "可能有零星降雪", "Patchy snow nearby": "附近零星降雪",
    "Light snow showers": "小阵雪", "Heavy snow showers": "大阵雪",
    "Light rain shower": "小阵雨", "Torrential rain shower": "暴雨",
    "Patchy light rain": "零星小雨", "Thundery outbreaks possible": "可能有雷暴",
    "Thundery outbreaks in nearby": "附近雷暴", "Thunder": "雷暴",
    "Thunderstorm": "雷暴", "Rain with thunderstorm": "雷雨",
    "Snow with thunderstorm": "雷雪", "Ice pellets": "冰粒",
    "Blowing snow": "吹雪", "Blizzard": "暴风雪",
}


def _desc(entry: dict, code: str) -> str:
    """优先取 API weatherDesc 英文→中文映射，未命中回退英文原描述"""
    descs = entry.get("weatherDesc") or []
    raw = (descs[0].get("value", "") if descs else "").strip()
    return _WMO.get(raw, raw or f"天气代码{code}")


def _fetch(city: str) -> dict:
    url = f"{_API}/{urllib.parse.quote(city)}?format=j1&lang=zh"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fmt(data: dict, city: str) -> str:
    cur = data["current_condition"][0]
    lines = [f"📍 {city} 当前天气", "─" * 28]
    lines.append(f"🌡 气温：{cur['temp_C']}°C（体感 {cur['FeelsLikeC']}°C）")
    lines.append(f"☁ 天况：{_desc(cur, cur['weatherCode'])}")
    lines.append(f"💧 湿度：{cur['humidity']}%")
    lines.append(f"🌬 风速：{cur['windspeedKmph']} km/h {cur['winddir16Point']}")
    lines.append(f"👁 能见度：{cur['visibility']} km  UV：{cur['uvIndex']}")
    for w in data.get("weather", [])[1:3]:
        date = w.get("date", "")
        hi = w["maxtempC"]
        lo = w["mintempC"]
        day_desc = _desc(w["hourly"][4], w["hourly"][4]["weatherCode"]) if w.get("hourly") else "?"
        lines.append(f"📅 {date}  {day_desc}  {lo}~{hi}°C")
    lines.append("")
    lines.append("数据源：wttr.in")
    return "\n".join(lines)


def _impl(tool_ctx, **kwargs):
    city = (kwargs.get("city") or "").strip()
    if not city:
        return ToolResult(False, error="请提供 city 参数（城市名，支持中英文，如 北京 / Shanghai / Tokyo）")
    try:
        data = _fetch(city)
        return ToolResult(True, content=_fmt(data, city))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return ToolResult(False, error=f"未找到城市「{city}」，请检查拼写或换用英文名")
        return ToolResult(False, error=f"天气服务返回 HTTP {e.code}")
    except urllib.error.URLError as e:
        return ToolResult(False, error=f"网络请求失败：{e.reason}（wttr.in 可能不可达）")
    except (KeyError, IndexError, ValueError) as e:
        return ToolResult(False, error=f"解析天气数据失败：{e!r}")
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"weather_query 内部异常：{type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "weather_query",
        "description": (
            "查询指定城市的实时天气与未来 2 天预报"
            "（气温/体感/天况/湿度/风速/能见度/UV）。"
            "数据源 wttr.in 免费 API，支持中英文城市名。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名（中文或英文，如 北京 / Shanghai / Tokyo）",
                },
            },
            "required": ["city"],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "weather_query", _SCHEMA, impl=_impl,
        danger="safe", icon="weather_query", cn_name="天气查询",
        group="实用工具",
        description="查询城市实时天气与预报（wttr.in，无需 key）",
        aliases=["WeatherQuery"],
    )
