# -*- coding: utf-8 -*-
"""格式注册表与旧插件数据迁移（共享契约，无 Qt / 第三方依赖）。

约定（通用格式必须遵守）：
  parse(path) -> dict model，含 "mode" 键与 lookup(anchor) 回调
  render(model, *, outer, accent, restored) -> str HTML
  HTML 必须内联 qrc:///qtwebchannel/qwebchannel.js 标签、_BOOT_JS、_PICK_JS、_ANNOTATE_JS，
  可拾取元素带 data-anchor，值为该格式锚点字符串。
  model["lookup"](anchor) -> dict 或 None，供窗口回填上下文（见 docx_window._lookup_block）。

docx / pptx 走窗口内专用分支（解析与渲染签名历史遗留，保持不动）；
其余格式走 spec_for 返回的 parse/render callable。
"""

import importlib
import shutil
from pathlib import Path

PLUGIN_NAME = "file-designer"
LEGACY_NAME = "docx-designer"

def _data_root():
    try:
        from app.plugins.sdk import caps_for

        return Path(str(caps_for("storage.data_dir", plugin=PLUGIN_NAME, surface="ui")))
    except Exception:
        return Path.home() / ".drifox"

def plugin_data_dir():
    return _data_root() / "plugin_data" / PLUGIN_NAME

def migrate_data_dir():
    """docx-designer -> file-designer 整目录复制；目标已存在则跳过（幂等）。"""
    dst = plugin_data_dir()
    src = _data_root() / "plugin_data" / LEGACY_NAME
    if dst.exists() or not src.is_dir():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(src), str(dst))
    return True

FORMATS = {}          # suffix -> {"mode", "status", "parse", "render"}；parse=None 表示窗口专用分支
SUPPORTED_SUFFIXES = ()

def register_format(suffix, mode, status, parse=None, render=None):
    global SUPPORTED_SUFFIXES
    FORMATS[suffix] = {
        "mode": mode, "status": status, "parse": parse, "render": render,
    }
    SUPPORTED_SUFFIXES = tuple(sorted(FORMATS))

def suffix_label():
    return " / ".join(SUPPORTED_SUFFIXES)

def spec_for(suffix):
    """返回 spec 副本；通用格式把 parse/render 解析成 callable。"""
    f = FORMATS.get(suffix.lower())
    if f is None:
        return None
    out = dict(f)
    out["generic"] = f["parse"] is not None
    if out["generic"]:
        pkg = __package__ or "ui_plugin_file_designer"
        for key in ("parse", "render"):
            mod_name, func_name = f[key]
            out[key] = getattr(importlib.import_module(mod_name, package=pkg), func_name)
    return out

# fmt: off
register_format(".docx",    "docx",    "Word 文档")     # 窗口专用分支
register_format(".pptx",    "pptx",    "PowerPoint")     # 窗口专用分支
register_format(".xmind",   "xmind",   "XMind 思维导图", (".xmind_parser",  "parse_xmind"),   (".xmind_renderer",  "render_xmind_html"))
register_format(".xlsx",    "xlsx",    "Excel 工作簿",   (".sheet_parser",  "parse_xlsx"),    (".sheet_renderer",  "render_sheet_html"))
register_format(".xlsm",    "xlsx",    "Excel 工作簿",   (".sheet_parser",  "parse_xlsx"),    (".sheet_renderer",  "render_sheet_html"))
register_format(".csv",     "csv",     "CSV 表格",       (".sheet_parser",  "parse_csv"),     (".sheet_renderer",  "render_sheet_html"))
register_format(".mmd",     "mermaid", "Mermaid 流程图", (".mermaid_parser","parse_mermaid"), (".mermaid_renderer","render_mermaid_html"))
register_format(".mermaid", "mermaid", "Mermaid 流程图", (".mermaid_parser","parse_mermaid"), (".mermaid_renderer","render_mermaid_html"))
# fmt: on
