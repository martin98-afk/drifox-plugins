# -*- coding: utf-8 -*-
"""走宿主 PluginToolLoader 真实加载 showcase 插件，验证注册结果与调用链路。"""
import sys
from pathlib import Path

HOST = Path(r"D:\work\DriFox")
REPO = Path(r"D:\work\drifox-plugins2")
sys.path.insert(0, str(HOST))

from app.plugins.loaders.plugin_tool_loader import load_plugin_tools
from app.tools.registry import ToolRegistry

loaded = load_plugin_tools(plugin_roots=[str(REPO / "plugins")])
print("loaded plugins:", len(loaded))
assert "showcase" in loaded, f"showcase 未被加载，已加载: {sorted(loaded)}"
print("showcase tools:", sorted(loaded["showcase"]))
assert loaded["showcase"] == {"showcase"}, loaded["showcase"]

reg = ToolRegistry.get_instance()
regd = reg.get("showcase")
assert regd is not None, "registry 里取不到 showcase"
print("source:", getattr(regd, "source", None))
print("danger:", getattr(regd, "danger", None))
print("cn_name:", getattr(regd, "cn_name", None))
print("group:", getattr(regd, "group", None))
print("aliases:", getattr(regd, "aliases", None))
assert getattr(regd, "danger", None) == "safe"
assert getattr(regd, "source", "") == "plugin:showcase"

# schema 能被宿主接受（工具列表构造路径）
schemas = reg.get_schemas() if hasattr(reg, "get_schemas") else None
if schemas is not None:
    hit = [s for s in schemas if s.get("function", {}).get("name") == "showcase"]
    print("schema 出现在工具列表:", bool(hit))
    assert hit, "showcase 的 schema 未进入工具列表"

print("\nLOAD PASS")
