# -*- coding: utf-8 -*-
"""biaoqingbao 核心逻辑测试 — 对齐上游 verify-scoring.js 的用例。

跑法：python3 plugins/biaoqingbao/tests/test_core.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from biaoqingbao_core import store  # noqa: E402
from biaoqingbao_core.scoring import (  # noqa: E402
    collect_prefs_for_emotion,
    detect_ritual,
    effective_preset_config,
    is_work_talk,
    looks_natural,
    passes_frequency,
    prefs_score_bonus,
    sanitize_tag,
    score_stickers,
)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILS.append(name)


STICKERS = [
    {"id": "a", "description": "开心猫咪挥手",
     "tags": {"emotion": ["开心"], "scene": ["问候"], "keywords": ["猫咪"]}},
    {"id": "b", "description": "笑着打招呼",
     "tags": {"emotion": ["开心"], "scene": ["早安"], "keywords": ["挥手"]}},
    {"id": "c", "description": "伤心落泪",
     "tags": {"emotion": ["难过"], "scene": ["安慰"], "keywords": ["眼泪"]}},
]


def test_scoring() -> None:
    print("[scoring]")
    # 上游用例 1：偏好与否决
    r = score_stickers(STICKERS, "开心", [], {"preferred": ["b"], "vetoed": ["a"], "dislikes": {}})
    ids = [s["id"] for s in r]
    check("偏好否决：只剩 b", ids == ["b"], f"got {ids}")

    # 上游用例 2：排除名单
    r = score_stickers(STICKERS, "开心", ["b"], {"preferred": [], "vetoed": [], "dislikes": {}})
    ids = [s["id"] for s in r]
    check("排除 b：只剩 a", ids == ["a"], f"got {ids}")

    # 上游用例 3：不喜欢次数递减（分数压到 <=0 会被过滤，与上游一致）
    none = score_stickers(STICKERS, "开心", [], {"preferred": [], "vetoed": [], "dislikes": {}})
    once = score_stickers(STICKERS, "开心", [], {"preferred": [], "vetoed": [], "dislikes": {"a": 1}})
    twice = score_stickers(STICKERS, "开心", [], {"preferred": [], "vetoed": [], "dislikes": {"a": 2}})
    thrice = score_stickers(STICKERS, "开心", [], {"preferred": [], "vetoed": [], "dislikes": {"a": 3}})
    s0 = next(s["_score"] for s in none if s["id"] == "a")
    s1 = next(s["_score"] for s in once if s["id"] == "a")
    s2 = next(s["_score"] for s in twice if s["id"] == "a")
    check("不喜欢 1 次降权", s1 < s0, f"{s0} vs {s1}")
    check("不喜欢 2 次继续降权", s2 < s1, f"{s1} vs {s2}")
    check("不喜欢 3 次压到负分出局", all(s["id"] != "a" for s in thrice),
          f"got {[s['id'] for s in thrice]}")

    # 否决优先级高于不喜欢
    both = score_stickers(STICKERS, "开心", [], {"preferred": [], "vetoed": ["a"], "dislikes": {"a": 2}})
    check("否决直接出局", all(s["id"] != "a" for s in both))

    # 情绪互相包含
    r = score_stickers(STICKERS, "委屈想哭", [], {"preferred": [], "vetoed": [], "dislikes": {}})
    check("无匹配返回空", r == [], f"got {[s['id'] for s in r]}")

    # 情绪包含匹配
    r = score_stickers(STICKERS, "难过", [], {"preferred": [], "vetoed": [], "dislikes": {}})
    check("「难过」命中 c", [s["id"] for s in r] == ["c"], f"got {[s['id'] for s in r]}")

    # 描述包含加分
    r = score_stickers(STICKERS, "猫咪", [], {"preferred": [], "vetoed": [], "dislikes": {}})
    check("「猫咪」靠 keywords 命中 a", [s["id"] for s in r] == ["a"], f"got {[s['id'] for s in r]}")


def test_prefs() -> None:
    print("[prefs]")
    mappings = [
        {"context": {"emotion": "开心"}, "preferred_ids": ["b"], "vetoed_ids": ["a"], "dislike_counts": {"c": 2}},
        {"context": {"emotion": "难过"}, "preferred_ids": ["c"], "vetoed_ids": [], "dislike_counts": {}},
    ]
    p = collect_prefs_for_emotion(mappings, "开心")
    check("收集 preferred", p["preferred"] == ["b"], str(p))
    check("收集 vetoed", p["vetoed"] == ["a"], str(p))
    check("收集 dislikes", p["dislikes"] == {"c": 2}, str(p))

    p2 = collect_prefs_for_emotion(mappings, "开心得跳起来")
    check("情绪包含也能收集", p2["preferred"] == ["b"], str(p2))

    check("喜欢 +10", prefs_score_bonus("b", {"preferred": ["b"]}) == 10)
    check("否决 -20", prefs_score_bonus("a", {"vetoed": ["a"]}) == -20)
    check("不喜欢 3 次 -15", prefs_score_bonus("c", {"dislikes": {"c": 3}}) == -15)
    check("不喜欢封顶 -25", prefs_score_bonus("c", {"dislikes": {"c": 9}}) == -25)


def test_text_tools() -> None:
    print("[text]")
    check("代码块不算自然", not looks_natural("```python\nprint(1)\n```"))
    check("闲聊算自然", looks_natural("今天天气真好呀，出去走走？"))
    check("早安识别", detect_ritual("早安呀") == {"word": "早安"}, str(detect_ritual("早安呀")))
    check("英文 hi 识别", detect_ritual("hi") is not None)
    check("工作对话识别", is_work_talk("这段代码有 bug 要修"))
    check("闲聊不算工作", not is_work_talk("今天吃什么呀"))
    check("频率 0 永不发", not passes_frequency(0, 0.0))
    check("频率 100 必发", passes_frequency(100, 0.99))
    check("频率 50 半概率", passes_frequency(50, 0.49) and not passes_frequency(50, 0.51))


def test_config() -> None:
    print("[config]")
    g = {"enabled": True, "freq": {"daily": 50, "task": 20}, "dialect": {"id": "dongbei", "boost": False}}
    eff = effective_preset_config(g, None)
    check("默认继承全局", eff["freq"]["daily"] == 50 and eff["enabled"] is True, str(eff))
    eff = effective_preset_config(g, {"enabled": False, "freq": {"daily": 10}})
    check("助手覆盖 enabled", eff["enabled"] is False)
    check("助手覆盖 daily", eff["freq"]["daily"] == 10)
    check("未覆盖沿用全局 task", eff["freq"]["task"] == 20)


def test_store() -> None:
    print("[store]")
    tmp = Path(tempfile.mkdtemp(prefix="bqb_test_"))
    try:
        # 造一张假图
        src = tmp / "src.png"
        src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)

        st = store.import_image(tmp, src, description="开心猫咪", tags={"emotion": ["开心"]})
        check("导入生成 id", st["id"].startswith("stk_"))
        check("图片落盘", store.sticker_abs_path(tmp, st) is not None)

        loaded = store.load_stickers(tmp)
        check("图库记录 1 条", len(loaded) == 1)

        upd = store.update_sticker(tmp, st["id"], description="新描述", tags={"emotion": ["委屈"]})
        check("更新描述", upd["description"] == "新描述")
        check("更新标签", upd["tags"]["emotion"] == ["委屈"])

        store.record_feedback(tmp, emotion="开心", sticker_id=st["id"], positive=True)
        prefs = store.load_prefs(tmp)
        m = prefs["users"]["default"]["mappings"][0]
        check("偏好写入 preferred", m["preferred_ids"] == [st["id"]], str(m))

        store.record_feedback(tmp, emotion="开心", sticker_id=st["id"], positive=False)
        prefs = store.load_prefs(tmp)
        m = prefs["users"]["default"]["mappings"][0]
        check("反向反馈移入 vetoed", st["id"] in m["vetoed_ids"] and st["id"] not in m["preferred_ids"], str(m))

        check("删除成功", store.delete_sticker(tmp, st["id"]))
        check("删除后图库空", store.load_stickers(tmp) == [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    test_scoring()
    test_prefs()
    test_text_tools()
    test_config()
    test_store()
    print()
    if FAILS:
        print(f"✗ {len(FAILS)} 项失败: {FAILS}")
        return 1
    print("✓ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
