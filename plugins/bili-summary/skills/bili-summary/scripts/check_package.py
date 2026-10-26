#!/usr/bin/env python3
"""包结构自检 — 入口存在、引用可达、资产完整。

用法:
    python check_package.py [skill_dir]
"""
from __future__ import annotations

import os
import re
import sys

SKILL_FILES = [
    "SKILL.md",
    "references/api.md",
    "references/frames.md",
    "references/fallback.md",
    "assets/summary-template.md",
    "scripts/bili_fetch.py",
    "scripts/check_env.py",
    "evals/trigger-eval.json",
]
PLUGIN_FILES = [
    ".drifox-plugin/plugin.json",
    "README.md",
    "CHANGELOG.md",
    "icon.svg",
    "icon_dark.svg",
]
REQUIRED_FRONTMATTER = ("name", "description")


def check(skill_dir: str, plugin_dir: str) -> list[tuple[bool, str]]:
    results: list[tuple[bool, str]] = []

    for rel in SKILL_FILES:
        p = os.path.join(skill_dir, rel)
        results.append((os.path.isfile(p), f"skill/{rel}"))

    for rel in PLUGIN_FILES:
        p = os.path.join(plugin_dir, rel)
        results.append((os.path.isfile(p), f"plugin/{rel}"))

    # frontmatter 检查
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if os.path.isfile(skill_md):
        with open(skill_md, encoding="utf-8") as f:
            head = f.read(400)
        if head.startswith("---"):
            for key in REQUIRED_FRONTMATTER:
                results.append((bool(re.search(rf"^{key}:", head, re.M)), f"frontmatter.{key}"))
        else:
            results.append((False, "frontmatter 缺失"))

    # description 触发词覆盖
    if os.path.isfile(skill_md):
        with open(skill_md, encoding="utf-8") as f:
            head = f.read(1500)
        for kw in ("bilibili", "BV", "弹幕"):
            results.append((kw.lower() in head.lower(), f"description 含触发词 {kw}"))

    # plugin.json 与目录名一致
    pj = os.path.join(plugin_dir, ".drifox-plugin/plugin.json")
    if os.path.isfile(pj):
        import json
        with open(pj, encoding="utf-8") as f:
            data = json.load(f)
        expected = os.path.basename(os.path.normpath(plugin_dir))
        results.append((data.get("name") == expected, f"plugin.json name == {expected}"))
        results.append((bool(data.get("components", {}).get("skills")), "components.skills=true"))

    return results


def default_paths() -> tuple[str, str]:
    """本脚本位于 <plugin>/skills/<skill>/scripts/check_package.py

    dirname 一层 -> <skill> 根；再退两层（skills、<skill>）-> <plugin> 根。
    """
    here = os.path.dirname(os.path.abspath(__file__))          # .../scripts
    skill_dir = os.path.dirname(here)                          # .../<skill>
    plugin_dir = os.path.dirname(os.path.dirname(skill_dir))   # .../<plugin>
    return skill_dir, plugin_dir


def main() -> int:
    d_skill, d_plugin = default_paths()
    skill_dir = sys.argv[1] if len(sys.argv) > 1 else d_skill
    plugin_dir = os.path.dirname(os.path.dirname(skill_dir))
    results = check(skill_dir, plugin_dir)

    failed = [name for ok, name in results if not ok]
    for ok, name in results:
        print(f"  {'✅' if ok else '❌'} {name}")

    print(f"\n{len(results) - len(failed)}/{len(results)} 通过")
    if failed:
        print(f"缺失：{', '.join(failed)}")
        return 1
    print("包结构完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
