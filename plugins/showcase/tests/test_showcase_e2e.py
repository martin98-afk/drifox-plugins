# -*- coding: utf-8 -*-
"""端到端：showcase 产出的 artifacts → 宿主 normalize_artifact_items 归一化，
断言字段不被丢掉（落库/历史恢复口径），并检查 inline panel 的 _normalize_item 也能吃下。
"""
import importlib.util
import sys
from pathlib import Path

HOST = Path(r"D:\work\DriFox")
PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOST))

from app.core.conversation.message_content import normalize_artifact_items

spec = importlib.util.spec_from_file_location("showcase_tool_e2e", PLUGIN / "tools" / "showcase.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

tmp = Path(__file__).parent / "_tmp_e2e"
import shutil
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True)
(tmp / "poster.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 100)
(tmp / "page.html").write_text("<html></html>", encoding="utf-8")
(tmp / "clip.mp4").write_bytes(b"v" * 50)
(tmp / "data.bin").write_bytes(b"\x00" * 10)

r = mod._showcase_impl({"workdir": str(tmp)}, paths=["poster.png", "page.html", "clip.mp4", "data.bin"],
                       caption="测试批次")
assert r.success, r.error
raw = r.artifacts
print("raw kinds:", [a["kind"] for a in raw])
assert [a["kind"] for a in raw] == ["image", "html", "video", "file"], raw

# 1 宿主落库归一化：关键字段必须全部存活
norm = normalize_artifact_items(raw)
assert len(norm) == len(raw), (len(norm), len(raw))
for src, dst in zip(raw, norm):
    assert dst["path"] == src["path"]
    assert dst["kind"] == src["kind"]
    assert dst["name"] == src["name"]
    assert dst.get("size") == src.get("size"), (dst, src)
print("normalize ok, kinds:", [n["kind"] for n in norm])

# 2 panel 侧归一化：kind 合法且不丢 path
from app.widgets.inline_artifact_panel import _normalize_item, _KIND_META
for item in norm:
    n = _normalize_item(item)
    assert n is not None, item
    assert n["kind"] in _KIND_META, n
    assert n["path"] == item["path"]
print("panel ok, kinds:", [ _normalize_item(n)["kind"] for n in norm ])

# 3 脏数据容忍：非法条目被丢弃而不是崩
dirty = [{"path": ""}, "not a dict", {"path": str(tmp / "poster.png"), "kind": "weird"}]
cleaned = normalize_artifact_items(dirty)
assert len(cleaned) == 1, cleaned
assert _normalize_item(cleaned[0])["kind"] == "image", _normalize_item(cleaned[0])
print("dirty tolerated ok")

# 4 tool result to_dict 序列化后 artifacts 仍在
d = r.to_dict()
assert d["artifacts"] == raw
print("to_dict ok, artifacts count:", len(d["artifacts"]))

shutil.rmtree(tmp, ignore_errors=True)
print("\nE2E PASS")
