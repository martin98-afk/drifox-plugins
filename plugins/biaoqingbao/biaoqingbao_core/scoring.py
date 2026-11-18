# -*- coding: utf-8 -*-
"""表情包核心纯函数 — 打分、偏好、频率门控、文本工具。

移植自 moononnn/DeepSeek-Harness-biaoqingbao（MIT）的 lib/core.js，
保持算法与阈值一致，便于对照验证。
"""
from __future__ import annotations

import random
import re
from typing import Any, Iterable

# ═══════════════ 标签清洗 ═══════════════

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SPECIAL_RE = re.compile(r"[`$'\"\[\]{}]")


def sanitize_tag(raw: Any, max_len: int = 30) -> str:
    """清洗标签：去控制字符与特殊符号，截断到 max_len。"""
    if raw is None:
        return ""
    cap = max_len or 30
    s = _SPECIAL_RE.sub("", _CTRL_RE.sub("", str(raw))).strip()
    return s[:cap]


def str_arr(v: Any) -> list[str]:
    """把 str / list 归一成清洗后的非空字符串列表。"""
    if isinstance(v, (list, tuple)):
        return [t for t in (sanitize_tag(x) for x in v) if t]
    if isinstance(v, str) and v.strip():
        return [sanitize_tag(v)]
    return []


# ═══════════════ 自然度 / 仪式词 / 频率门控 ═══════════════

_NATURAL_FILTERS = [
    re.compile(r"```[\s\S]*?```"),
    re.compile(r"https?://[^\s'\"]{40,}"),
    re.compile(r"\b(pip|npm|git|ssh|cd|ls|rm|cp|mv|mkdir|powershell|cmd)\s+[^\n]{10,}"),
]

RITUAL_WORDS = [
    "早安", "早呀", "早上好", "早安呀", "中午好", "下午好", "晚安", "晚安安",
    "不早了", "该睡了", "你好", "哈喽", "嗨", "hi", "hello", "在吗", "想你",
]

_WORK_KEYWORDS = [
    "代码", "bug", "修复", "测试", "插件", "报错", "部署", "服务器", "数据库",
    "接口", "命令", "终端", "编译", "重构", "git", "npm", "脚本", "函数", "日志",
    "api", "sql", "ssh", "docker", "json", "验收", "编程", "调试", "仓库", "提交",
    "分支", "冲突",
]


def looks_natural(text: str) -> bool:
    """判断文本是否像自然聊天（剔除代码块/长 URL/命令行后，正文占比 >= 60%）。"""
    if not text or not isinstance(text, str) or len(text) < 2:
        return False
    rest = text
    for pat in _NATURAL_FILTERS:
        rest = pat.sub(" ", rest)
    return len(rest.strip()) / max(len(text), 1) >= 0.6


def _match_ritual_word(text: str, word: str) -> bool:
    if re.fullmatch(r"[a-z]+", word):
        return re.search(rf"\b{re.escape(word)}\b", text) is not None
    return text == word or word in text


def detect_ritual(text: str) -> dict[str, str] | None:
    """识别早安/晚安这类仪式性问候。"""
    t = str(text or "").lower().strip()
    if not t:
        return None
    for w in RITUAL_WORDS:
        if _match_ritual_word(t, w):
            return {"word": w}
    return None


def passes_frequency(percent: Any, random_value: float | None = None) -> bool:
    """频率门控：percent 为 0~100 的百分比。"""
    try:
        p = float(percent)
    except (TypeError, ValueError):
        p = 0.0
    probability = max(0.0, min(100.0, p))
    rv = random.random() if random_value is None else random_value
    return rv < probability / 100


def is_work_talk(text: str) -> bool:
    """检测是否是正经工作对话（代码/bug/部署等），用于自动降频。"""
    if not text:
        return False
    t = str(text).lower()
    return any(k in t for k in _WORK_KEYWORDS)


def should_boost_round(messages_length: int, random_value: float | None = None) -> bool:
    """对话早期（<= 8 条）更愿意配图，之后降到 60% 概率。"""
    if not isinstance(messages_length, int) or messages_length < 0:
        return False
    if messages_length <= 8:
        return True
    rv = random.random() if random_value is None else random_value
    return rv < 0.6


# ═══════════════ 偏好与打分 ═══════════════

def collect_prefs_for_emotion(mappings: Iterable[dict] | None, emotion: str) -> dict:
    """按情绪收集偏好：preferred / vetoed / dislikes。

    情绪匹配用互相包含（「委屈」能命中「委屈想哭」这类上下文）。
    """
    result: dict[str, Any] = {"preferred": [], "vetoed": [], "dislikes": {}}
    if not emotion:
        return result
    for m in (mappings or []):
        ctx_emotion = (m.get("context") or {}).get("emotion") if isinstance(m, dict) else None
        if not ctx_emotion:
            continue
        if emotion in ctx_emotion or ctx_emotion in emotion:
            result["preferred"].extend(m.get("preferred_ids") or [])
            result["vetoed"].extend(m.get("vetoed_ids") or [])
            for key, cnt in (m.get("dislike_counts") or {}).items():
                if cnt and cnt > 0:
                    result["dislikes"][key] = result["dislikes"].get(key, 0) + cnt
    return result


def prefs_score_bonus(sticker_id: str, prefs: dict | None) -> int:
    """偏好加减分：喜欢 +10，否决 -20，不喜欢的次数每级 -5（最多 -25）。"""
    p = prefs or {}
    bonus = 0
    if sticker_id in (p.get("preferred") or []):
        bonus += 10
    if sticker_id in (p.get("vetoed") or []):
        bonus -= 20
    dc = (p.get("dislikes") or {}).get(sticker_id, 0)
    if dc and dc > 0:
        bonus -= min(dc, 5) * 5
    return bonus


def score_stickers(
    stickers: Iterable[dict],
    emotion: str,
    exclude_ids: Iterable[str] | None = None,
    prefs: dict | None = None,
) -> list[dict]:
    """标签三档打分：emotion / scene / keywords，叠加偏好后按分数降序。

    档位权重（与上游一致）：
      emotion  精确 +8 / 包含 +5 / 小写包含 +3
      scene    精确 +5 / 包含 +3
      keywords 精确 +4 / 包含 +2
      description 包含 +3
    """
    emo = sanitize_tag(emotion, 60)
    emo_lower = emo.lower()
    excluded = set(exclude_ids or [])
    out: list[dict] = []
    for sticker in stickers:
        if not sticker or sticker.get("id") in excluded:
            continue
        score = 0
        tags = sticker.get("tags") or {}
        for tag in (tags.get("emotion") or []):
            tag = str(tag)
            tag_lower = tag.lower()
            if tag == emo:
                score += 8
            elif tag in emo or emo in tag:
                score += 5
            elif tag_lower in emo_lower or emo_lower in tag_lower:
                score += 3
        for tag in (tags.get("scene") or []):
            tag = str(tag)
            if tag == emo:
                score += 5
            elif tag in emo or emo in tag:
                score += 3
        for tag in (tags.get("keywords") or []):
            tag = str(tag)
            if tag == emo:
                score += 4
            elif tag in emo or emo in tag:
                score += 2
        desc = sticker.get("description") or ""
        if desc and emo in desc:
            score += 3
        total = score + prefs_score_bonus(str(sticker.get("id") or ""), prefs)
        if total > 0:
            item = dict(sticker)
            item["_score"] = total
            out.append(item)
    out.sort(key=lambda s: s["_score"], reverse=True)
    return out


def substring_match(stickers: Iterable[dict], query: str) -> list[dict]:
    """描述/标签子串兜底匹配（精确标签没命中时用）。"""
    q = (query or "").strip()
    if not q:
        return []
    out = []
    for s in stickers:
        desc = s.get("description") or ""
        tags = s.get("tags") or {}
        hay = " ".join([
            desc,
            *[str(x) for x in (tags.get("emotion") or [])],
            *[str(x) for x in (tags.get("scene") or [])],
            *[str(x) for x in (tags.get("keywords") or [])],
        ])
        if q in hay:
            out.append(dict(s))
    return out


# ═══════════════ per-preset 配置合并 ═══════════════

def effective_preset_config(global_cfg: dict | None, override: dict | None) -> dict:
    """全局默认 + 助手级覆盖 → 生效配置；只覆盖显式出现的字段。"""
    g = global_cfg or {}
    o = override if isinstance(override, dict) else None

    def pick_bool(key: str, default: bool) -> bool:
        if o and isinstance(o.get(key), bool):
            return o[key]
        return g.get(key, default) if isinstance(g.get(key), bool) else default

    dialect = o.get("dialect") if o and isinstance(o.get("dialect"), dict) else {}
    g_dialect = g.get("dialect") if isinstance(g.get("dialect"), dict) else {}
    freq = o.get("freq") if o and isinstance(o.get("freq"), dict) else {}
    g_freq = g.get("freq") if isinstance(g.get("freq"), dict) else {}
    return {
        "enabled": pick_bool("enabled", True),
        "dialect": {
            "id": dialect.get("id") if isinstance(dialect.get("id"), str)
            else (g_dialect.get("id") or ""),
            "boost": dialect.get("boost") if isinstance(dialect.get("boost"), bool)
            else bool(g_dialect.get("boost")),
        },
        "freq": {
            "daily": freq.get("daily") if isinstance(freq.get("daily"), (int, float))
            else (g_freq.get("daily") if isinstance(g_freq.get("daily"), (int, float)) else 50),
            "task": freq.get("task") if isinstance(freq.get("task"), (int, float))
            else (g_freq.get("task") if isinstance(g_freq.get("task"), (int, float)) else 20),
        },
    }
