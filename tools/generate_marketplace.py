#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_marketplace.py — 从 plugins/*/.drifox-plugin/plugin.json 自动生成 marketplace.json

用法:
    python tools/generate_marketplace.py           # 生成/更新 marketplace.json
    python tools/generate_marketplace.py --check    # 仅检查一致性，不写文件

退出码:
    0 — marketplace.json 已是最新（或已成功生成）
    1 — marketplace.json 与实际不一致（--check 模式）
    2 — 致命错误（如无插件目录）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from downloads_stats import load_downloads_cache

# ============================================================
# 路径定位
# ============================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
MARKETPLACE_PATH = REPO_ROOT / "marketplace.json"
MANIFEST_PATH = Path(".drifox-plugin") / "plugin.json"
# 下载量缓存（由 tools/fetch_downloads.py 定时拉取计数服务生成）
DOWNLOADS_CACHE_PATH = REPO_ROOT / "downloads_cache.json"
# tarball 构建产物索引（tools/build_plugin_tarballs.py 生成；不入库，缺失时保留现有清单字段）
TARBALL_INDEX_PATH = REPO_ROOT / "dist" / "tarball_index.json"

# 仓库元信息（硬编码，与 README 中的 GitHub 链接一致）
REPO_NAME = "drifox-official"
REPO_DESCRIPTION = "DriFox 官方插件市场 — 托管官方插件与社区贡献插件的统一入口"
REPO_URL = "https://github.com/martin98-afk/drifox-plugins"
DEFAULT_REF = "main"
DEFAULT_LICENSE = "GPL-3.0-or-later"

# DriFox 运行时内置插件（D:/work/DriFox/plugins/ 下的插件）。
# 这些插件随 DriFox 分发，无需从市场安装，出现在市场中会让用户困惑，
# 因此生成 marketplace.json 时一律跳过。
DRIFOX_BUILTIN_PLUGINS = {
    "file-tree",
    "plugin-manager",
    "plugin-marketplace",
    "share-history",
    "shortcut-manager",
    "system",
    "system-cleaner",
}

# ============================================================
# 输出样式
# ============================================================

_IS_TTY = sys.stdout.isatty()


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if _IS_TTY else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if _IS_TTY else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if _IS_TTY else s


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _IS_TTY else s


# ============================================================
# 插件发现与 manifest 读取
# ============================================================


def discover_plugins() -> list[Path]:
    """发现 plugins/ 下所有合法插件目录。"""
    if not PLUGINS_DIR.exists():
        return []
    return sorted(
        d for d in PLUGINS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def load_manifest(plugin_dir: Path) -> dict | None:
    """读取插件 manifest，失败返回 None。"""
    manifest_file = plugin_dir / MANIFEST_PATH
    if not manifest_file.exists():
        return None
    try:
        return json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def normalize_author(author: Any) -> str:
    """将 author 字段统一为字符串。"""
    if isinstance(author, str):
        return author
    if isinstance(author, dict):
        return author.get("name", "unknown")
    return "unknown"


def infer_categories(manifest: dict) -> list[str]:
    """从 components 和 keywords 推断插件分类。"""
    categories: list[str] = []
    comps = manifest.get("components", {})
    keywords = [k.lower() for k in manifest.get("keywords", [])]

    # 按组件推断
    if comps.get("themes"):
        categories.append("theme")
    if comps.get("mcp"):
        categories.append("mcp")
    if comps.get("lsp"):
        categories.append("lsp")
    if comps.get("ui"):
        categories.append("ui")
    if comps.get("agents"):
        categories.append("agent")
    if comps.get("tools"):
        categories.append("tool")
    if comps.get("providers"):
        categories.append("provider")

    # 按 keywords 推断
    kw_category_map = {
        "git": "workflow",
        "workflow": "workflow",
        "commit": "workflow",
        "branch": "workflow",
        "pr": "workflow",
        "code-review": "workflow",
        "review": "workflow",
        "test": "workflow",
        "testing": "workflow",
        "tdd": "workflow",
        "coverage": "workflow",
        "python": "language",
        "frontend": "language",
        "react": "language",
        "vue": "language",
        "javascript": "language",
        "typescript": "language",
        "java": "language",
        "go": "language",
        "rust": "language",
        "stats": "stats",
        "statistics": "stats",
        "analytics": "stats",
        "usage": "stats",
        "token": "stats",
        "context": "stats",
        "dashboard": "stats",
    }
    for kw in keywords:
        cat = kw_category_map.get(kw)
        if cat and cat not in categories:
            categories.append(cat)

    # 默认分类
    if not categories:
        if comps.get("commands") or comps.get("skills") or comps.get("hooks"):
            categories.append("workflow")

    return categories


# ============================================================
# marketplace.json 生成
# ============================================================


def load_tarball_index() -> dict:
    """读取 tarball 构建索引：{插件名: {"version":..., "tarball": {...}}}

    索引缺失（未跑构建 / CI checkout 无 dist）时返回空字典——调用方应回退
    到旧 marketplace.json 里的 tarball 字段，避免一次生成就把已发布的
    tarball 信息清掉。
    """
    if not TARBALL_INDEX_PATH.is_file():
        return {}
    try:
        data = json.loads(TARBALL_INDEX_PATH.read_text(encoding="utf-8"))
        return data.get("plugins") or {}
    except Exception as e:
        print(_yellow(f"[warn] tarball 索引读取失败（忽略）: {e}"))
        return {}


def load_existing_tarballs() -> dict:
    """旧 marketplace.json 里的 tarball 字段：{插件名: tarball}"""
    if not MARKETPLACE_PATH.is_file():
        return {}
    try:
        data = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
        return {
            p.get("name"): p.get("tarball")
            for p in data.get("plugins", [])
            if p.get("name") and p.get("tarball")
        }
    except Exception:
        return {}


def build_plugin_entry(plugin_dir: Path, manifest: dict, tarball_entry: dict | None = None) -> dict:
    """从 plugin.json 构建一条 marketplace 插件条目。"""
    entry: dict = {
        "name": manifest["name"],
        "description": manifest["description"],
        "version": manifest["version"],
        "author": normalize_author(manifest.get("author")),
        "license": manifest.get("license", DEFAULT_LICENSE),
        "categories": infer_categories(manifest),
        "source": {
            "type": "git-subdir",
            "url": REPO_URL,
            "path": f"plugins/{plugin_dir.name}",
            "ref": DEFAULT_REF,
        },
        "components": manifest.get("components", {}),
    }

    # 下载量：从本地缓存读取（无缓存/未知插件则不写字段，保持向后兼容）
    downloads = _downloads_cache.get("downloads", {}).get(manifest["name"])
    if isinstance(downloads, int) and downloads > 0:
        entry["downloads"] = downloads

    # 选填字段
    if manifest.get("keywords"):
        entry["keywords"] = manifest["keywords"]

    # 平台声明（platforms）与 pip 依赖（dependencies）：透传给市场端，
    # 客户端据此显示兼容徽标/置灰不兼容平台的安装按钮，并在安装时自动装依赖
    if manifest.get("platforms"):
        entry["platforms"] = manifest["platforms"]
    if manifest.get("dependencies"):
        entry["dependencies"] = manifest["dependencies"]

    # 宿主版本门槛：市场端据此把版本不足的「安装 / 更新」按钮置灰并说明原因。
    # 注意 drifox.min_version 是废字段（宿主从不读取），真正生效的是 min_host_version，
    # 历史条目里的 drifox 块不再透传。
    if manifest.get("min_host_version"):
        entry["min_host_version"] = manifest["min_host_version"]
    # api_version：宿主插件 API 契约版本，市场端可用于标注「需新版 DriFox」
    if manifest.get("api_version"):
        entry["api_version"] = manifest["api_version"]

    if manifest.get("homepage"):
        entry["homepage"] = manifest["homepage"]

    # icon 字段：透传 manifest 中的 string 或 {light, dark} 对象
    # 由客户端从 _marketplace_source 拼 raw.githubusercontent.com URL 异步加载
    icon_value = manifest.get("icon")
    if icon_value:
        entry["icon"] = icon_value

    # tarball 按平台分发（工具出库后的主通道，含 deps）；无产物则字段缺失，
    # 老客户端继续走 source=git-subdir，新客户端走 tarball——双轨兼容。
    if tarball_entry:
        tb = tarball_entry.get("tarball") if isinstance(tarball_entry, dict) else None
        if tb:
            entry["tarball"] = tb

    return entry


def _published_version(tarball: dict) -> str:
    """从清单的 tarball 字段反推已发布版本（取任一平台 URL 里的版本号）。"""
    if not isinstance(tarball, dict):
        return ""
    for key, meta in tarball.items():
        if key == "mirrors" or not isinstance(meta, dict):
            continue
        m = re.search(r"/download/plugin-[^/]+?-v(\d+\.\d+\.\d+)", str(meta.get("url") or ""))
        if m:
            return m.group(1)
    return ""

def _version_lt(a: str, b: str) -> bool:
    """a < b 的语义版本比较（只处理点分数字，解析失败视为不小于）。"""
    def _parts(v: str) -> list[int]:
        return [int(x) for x in re.findall(r"\d+", v)]

    pa, pb = _parts(a), _parts(b)
    if not pa or not pb:
        return False
    # 补齐长度后逐段比较
    width = max(len(pa), len(pb))
    pa += [0] * (width - len(pa))
    pb += [0] * (width - len(pb))
    return pa < pb

def _same_tarball(a: dict, b: dict) -> bool:
    """两份 tarball 字段是否等价（比 url + sha256：url 同但 sha 异视为两批不同构建）。

    url 由插件名+版本拼出，本地重建永远产相同 url，只比 url 会漏掉
    「同版本不同构建平台导致 sha 不同」的场景（2026-11 本机 Windows 构建
    vs CI Linux 构建实测触发），指纹必须包含 sha256。
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        return a == b

    def _fingerprint(t: dict) -> dict:
        return {
            k: (v.get("url"), v.get("sha256"))
            for k, v in t.items()
            if k != "mirrors" and isinstance(v, dict)
        }

    return _fingerprint(a) == _fingerprint(b)

def generate_marketplace() -> dict:
    """扫描所有插件，生成完整的 marketplace.json 结构。"""
    global _downloads_cache
    _downloads_cache = load_downloads_cache(DOWNLOADS_CACHE_PATH)
    tarball_index = load_tarball_index()
    existing_tarballs = load_existing_tarballs()
    plugins = discover_plugins()
    entries: list[dict] = []

    for plugin_dir in plugins:
        manifest = load_manifest(plugin_dir)
        if manifest is None:
            print(f"  {_yellow('SKIP')} {plugin_dir.name} — 无有效 manifest")
            continue
        if manifest.get("name") in DRIFOX_BUILTIN_PLUGINS:
            print(f"  {_yellow('SKIP')} {plugin_dir.name} — DriFox 运行时内置插件，不进市场")
            continue
        name = manifest.get("name") or plugin_dir.name
        # 优先级：本次构建产物 > 旧清单保留字段（避免无 dist 的生成把产物信息抹掉）
        # 但本地 dist/ 可能是几小时前的旧构建，直接采信会把远端已发布的新版本
        # 回退成旧版本（实测：本地索引里 bili-scroll 仍是 0.2.2，而清单已发布 0.2.4，
        # 一次 generate 就把清单退回 0.2.2）。因此要求索引版本不低于已发布版本。
        tb_entry = tarball_index.get(name)
        if tb_entry:
            idx_ver = str(tb_entry.get("version") or "")
            pub_tb = existing_tarballs.get(name) or {}
            pub_ver = _published_version(pub_tb)
            if pub_ver and _version_lt(idx_ver, pub_ver):
                print(
                    f"  {_yellow('KEEP')} {name} — 本地索引 {idx_ver} 低于已发布 "
                    f"{pub_ver}，保留清单现值（dist/ 是旧构建？）"
                )
                tb_entry = None
            elif pub_ver and idx_ver == pub_ver and not _same_tarball(
                tb_entry.get("tarball") or {}, pub_tb
            ):
                # 同版本但产物指纹不同：本地 dist/ 与远端已发布的是两批不同构建。
                # 已发布的是既成事实，本地旧索引不该改写清单（否则 sha 与线上 asset
                # 对不上，客户端校验必然失败）。
                print(
                    f"  {_yellow('KEEP')} {name} — 本地索引与已发布同版本但内容不同，"
                    f"保留清单现值"
                )
                tb_entry = None
        if not tb_entry and existing_tarballs.get(name):
            tb_entry = {"tarball": existing_tarballs[name]}
        entries.append(build_plugin_entry(plugin_dir, manifest, tb_entry))

    return {
        "name": REPO_NAME,
        "description": REPO_DESCRIPTION,
        "homepage": REPO_URL,
        "plugins": entries,
    }


# ============================================================
# 一致性检查
# ============================================================

# 下载量缓存（模块级，generate_marketplace 时加载）
_downloads_cache: dict = {}


def check_consistency(generated: dict, existing: dict) -> list[str]:
    """比对生成的 marketplace 与现有文件，返回差异列表。"""
    diffs: list[str] = []

    gen_plugins = {p["name"]: p for p in generated.get("plugins", [])}
    ex_plugins = {p["name"]: p for p in existing.get("plugins", [])}

    # 检查缺失的插件
    for name in gen_plugins:
        if name not in ex_plugins:
            diffs.append(f"marketplace.json 缺少插件: {name}")

    # 检查多余的插件
    for name in ex_plugins:
        if name not in gen_plugins:
            diffs.append(f"marketplace.json 包含已不存在的插件: {name}")

    # 检查字段一致性
    for name in gen_plugins:
        if name not in ex_plugins:
            continue
        gen_p = gen_plugins[name]
        ex_p = ex_plugins[name]

        for field in ("name", "description", "version", "author", "license", "components"):
            if gen_p.get(field) != ex_p.get(field):
                diffs.append(
                    f"插件 {name} 字段 {field} 不一致: "
                    f"marketplace={ex_p.get(field)!r} vs plugin.json={gen_p.get(field)!r}"
                )

        # source.path 应为 plugins/<name>
        ex_source = ex_p.get("source", {})
        if ex_source.get("path") != f"plugins/{name}":
            diffs.append(
                f"插件 {name} source.path 应为 'plugins/{name}'，"
                f"当前为 {ex_source.get('path')!r}"
            )

    return diffs


# ============================================================
# 主流程
# ============================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从 plugins/*/.drifox-plugin/plugin.json 生成 marketplace.json"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检查 marketplace.json 是否与实际一致，不写文件",
    )
    args = parser.parse_args(argv if argv is not None else None)

    print(_bold("DriFox marketplace generator"))
    print(f"  repo:         {REPO_ROOT}")
    print(f"  marketplace:  {MARKETPLACE_PATH.relative_to(REPO_ROOT)}")
    print()

    generated = generate_marketplace()
    plugin_count = len(generated["plugins"])

    if plugin_count == 0:
        print(_yellow("未发现任何插件。"))
        return 2

    print(f"发现 {plugin_count} 个插件:")
    for p in generated["plugins"]:
        print(f"  {p['name']:20s} v{p['version']:10s} {p['description'][:50]}")
    print()

    if args.check:
        # 检查模式
        if not MARKETPLACE_PATH.exists():
            print(_red("✗ marketplace.json 不存在，请先运行 generate_marketplace.py 生成"))
            return 1

        try:
            existing = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(_red(f"✗ marketplace.json 不是合法 JSON: {e}"))
            return 1

        diffs = check_consistency(generated, existing)
        if diffs:
            print(_red(f"✗ marketplace.json 与实际不一致（{len(diffs)} 处差异）:"))
            for d in diffs:
                print(f"        {_red('diff')}: {d}")
            print()
            print(_yellow("请运行 `python tools/generate_marketplace.py` 更新 marketplace.json"))
            return 1
        else:
            print(_green("✓ marketplace.json 与所有 plugin.json 一致"))
            return 0
    else:
        # 生成模式
        output = json.dumps(generated, indent=4, ensure_ascii=False) + "\n"
        MARKETPLACE_PATH.write_text(output, encoding="utf-8")
        print(_green(f"✓ 已生成 {MARKETPLACE_PATH.relative_to(REPO_ROOT)}（{plugin_count} 个插件）"))
        return 0


if __name__ == "__main__":
    sys.exit(main())
