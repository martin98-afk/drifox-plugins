# -*- coding: utf-8 -*-
"""showcase 工具冒烟测试：不依赖宿主 GUI，直接喂假 tool_ctx 跑 impl。"""
import importlib.util
import sys
from pathlib import Path

HOST = Path(r"D:\work\DriFox")
PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOST))

spec = importlib.util.spec_from_file_location("showcase_tool", PLUGIN / "tools" / "showcase.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

import shutil

tmp = Path(__file__).parent / "_tmp_showcase"
# 每次重建：否则上次跑出的 many/ 会被「目录递归」用例扫到，断言假失败
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir(parents=True)
(tmp / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
(tmp / "b.md").write_text("# hi", encoding="utf-8")
(tmp / "c.bin").write_bytes(b"\x00\x01")
sub = tmp / "sub"
sub.mkdir(exist_ok=True)
(sub / "d.mp4").write_bytes(b"0" * 16)

ctx = {"workdir": str(tmp)}

def show(title, r):
    print(f"--- {title}")
    print("success:", r.success)
    print("content:", (r.content or r.error or "").replace("\n", " | ")[:300])
    arts = getattr(r, "artifacts", None) or []
    for a in arts:
        print("  artifact:", {k: a[k] for k in ("kind", "name") if k in a},
              "| size:", a.get("size"), "| caption:", a.get("caption"))
    assert all(set(a) <= {"path", "kind", "name", "size", "caption", "meta"} for a in arts), "条目含非法字段"
    return r

# 1 单图 + caption
show("单个图片带说明", mod._showcase_impl(ctx, paths=["a.png"], caption="最终版海报"))

# 2 目录递归（应收到 a.png/b.md/d.mp4，跳过 c.bin）
r = show("目录递归", mod._showcase_impl(ctx, paths=["."], caption=""))
kinds = sorted(a["kind"] for a in r.artifacts)
assert kinds == ["image", "text", "video"], kinds
assert all("c.bin" not in a["name"] for a in r.artifacts)

# 3 绝对路径 + 混合
show("绝对路径", mod._showcase_impl(ctx, paths=[str(tmp / "b.md")]))

# 4 缺失路径
r = show("缺失路径", mod._showcase_impl(ctx, paths=["nope.png"]))
assert not r.success

# 5 空参数
r = show("空参数", mod._showcase_impl(ctx, paths=[]))
assert not r.success

# 6 上限截断
many = tmp / "many"
many.mkdir(exist_ok=True)
for i in range(mod.MAX_ITEMS + 5):
    (many / f"f{i:02d}.txt").write_text("x", encoding="utf-8")
r = show("上限截断", mod._showcase_impl(ctx, paths=["many"]))
assert len(r.artifacts) == mod.MAX_ITEMS, len(r.artifacts)
assert "另有 5 个" in (r.content or ""), r.content

# 7 预览/摘要闭包
print("--- 预览/摘要")
print(mod._preview({"paths": ["a.png"]}))
print(mod._preview({"paths": ["a.png", "b.md"]}))
print(mod._summarize("showcase", {"paths": ["x/y/z.png"]}, ""))

# 8 schema 自检
fn = mod._SCHEMA["function"]
assert fn["name"] == "showcase"
assert fn["parameters"]["required"] == ["paths"]

# 9 register 契约：假 registry 收集参数
class R:
    def __init__(self):
        self.calls = []
    def register(self, *a, **kw):
        self.calls.append((a, kw))

reg = R()
mod.register(reg)
args, kw = reg.calls[0]
assert args[0] == fn["name"]
assert kw["danger"] == "safe"
assert callable(kw["impl"]) and callable(kw["preview"]) and callable(kw["summarize"])
print("--- register ok:", args[0], kw["cn_name"], kw["group"], kw["danger"])

print("\nALL PASS")
shutil.rmtree(tmp, ignore_errors=True)
