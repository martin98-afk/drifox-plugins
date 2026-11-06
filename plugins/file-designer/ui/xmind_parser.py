# -*- coding: utf-8 -*-
"""XMind 解析（纯函数，无 Qt 依赖）。

支持两种文件形态：
  XMind 2020+  content.json —— 多 sheet + rootTopic + children.attached
  XMind 8      content.xml  —— sheet/topic/title + children/topics

产出 model：
  {"mode": "xmind", "sheets": [{"name", "root": node}], "truncated": bool,
   "lookup": callable}
node = {"anchor", "title", "note", "labels", "children", "path", "sibling_titles",
        "sheet", "sheet_name"}
锚点 s{sheet}/n/{index_path}，index_path 以 0 起（0 为根），如 s0/n/0.2.1。
lookup(anchor) -> {"mode","kind":"xmind_node","text","path","siblings","note","anchor"}
"""

import json
import zipfile
from pathlib import Path

from lxml import etree

MAX_NODES = 800

_NS = {"x": "urn:xmind:xmap:xmlns:content:2.0"}


def _find(el, tag):
    return el.find("x:" + tag, _NS) if el.find("x:" + tag, _NS) is not None else el.find(tag)


def _findall(el, tag):
    got = el.findall("x:" + tag, _NS)
    return got if got else el.findall(tag)


def _clean(s):
    return " ".join(str(s or "").split()).strip()


def _json_notes(topic):
    notes = topic.get("notes") or {}
    txt = _clean((notes.get("plain") or {}).get("content"))
    if txt:
        return txt
    html = (notes.get("realHTML") or {}).get("content") or ""
    if html:
        try:
            return _clean(etree.tostring(
                etree.fromstring(html.encode("utf-8"), etree.HTMLParser()),
                encoding="unicode", method="text",
            ))
        except Exception:
            return ""
    return ""


def _json_children(topic):
    ch = topic.get("children") or {}
    out = []
    for key in ("attached", "detached", "summary", "callout"):
        out.extend(c for c in (ch.get(key) or []) if isinstance(c, dict))
    return out


def _json_labels(topic):
    return [x for x in (_clean(v) for v in (topic.get("labels") or [])) if x]


def _json_sheets(data):
    out = []
    for sh in (data if isinstance(data, list) else [data]):
        if isinstance(sh, dict) and isinstance(sh.get("rootTopic"), dict):
            out.append({"name": _clean(sh.get("title")) or "Sheet", "root": sh["rootTopic"]})
    return out


def _xml_title(topic):
    t = _find(topic, "title")
    return _clean(t.text if t is not None else "")


def _xml_notes(topic):
    n = _find(topic, "notes")
    if n is None:
        return ""
    return _clean((_find(n, "plain").text or "") if _find(n, "plain") is not None else "")


def _xml_children(topic):
    out = []
    for ch in _findall(topic, "children"):
        for group in _findall(ch, "topics"):
            out.extend(_findall(group, "topic"))
    return out


def _xml_sheets(root):
    out = []
    for sh in root.findall(".//x:sheet", _NS) or root.findall(".//sheet"):
        topic = _find(sh, "topic")
        if topic is not None:
            out.append({"name": _clean(sh.get("title")) or "Sheet", "root": topic})
    return out


def _read_sheets(path):
    with zipfile.ZipFile(str(path)) as zf:
        names = set(zf.namelist())
        if "content.json" in names:
            return _json_sheets(json.loads(zf.read("content.json").decode("utf-8-sig"))), "json"
        if "content.xml" in names:
            return _xml_sheets(etree.fromstring(zf.read("content.xml"))), "xml"
    raise ValueError("不是有效 XMind 文件（缺 content.json / content.xml）")


def parse_xmind(path):
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    raw_sheets, flavor = _read_sheets(p)

    def title_of(t):
        return _clean(t.get("title")) if flavor == "json" else _xml_title(t)

    def note_of(t):
        return _json_notes(t) if flavor == "json" else _xml_notes(t)

    def children_of(t):
        return _json_children(t) if flavor == "json" else _xml_children(t)

    def labels_of(t):
        return _json_labels(t) if flavor == "json" else []

    index = {}
    state = {"count": 0, "truncated": False}

    def walk(topic, sheet_i, sheet_name, idx_path, parent_path, sibling_titles):
        state["count"] += 1
        if state["count"] > MAX_NODES:
            state["truncated"] = True
            return None
        title = title_of(topic) or "（未命名主题）"
        path_titles = parent_path + [title]
        anchor = "s%d/n/%s" % (sheet_i, ".".join(str(i) for i in idx_path))
        kids_raw = children_of(topic)
        child_titles = [title_of(k) or "（未命名主题）" for k in kids_raw]
        node = {
            "anchor": anchor, "title": title, "note": note_of(topic),
            "labels": labels_of(topic), "children": [], "path": path_titles,
            "sibling_titles": sibling_titles, "sheet": sheet_i, "sheet_name": sheet_name,
        }
        index[anchor] = {
            "mode": "xmind", "kind": "xmind_node", "anchor": anchor,
            "text": title, "path": path_titles,
            "siblings": [x for x in sibling_titles if x != title], "note": node["note"],
        }
        for i, k in enumerate(kids_raw):
            built = walk(k, sheet_i, sheet_name, idx_path + [i], path_titles, child_titles)
            if built is None:
                break
            node["children"].append(built)
        return node

    sheets = []
    for i, sh in enumerate(raw_sheets):
        root = walk(sh["root"], i, sh["name"], [0], [], [title_of(sh["root"]) or "（未命名主题）"])
        if root is None:
            break
        sheets.append({"name": sh["name"], "root": root})

    if not sheets:
        raise ValueError("XMind 文件里没有可解析的 sheet")

    return {
        "mode": "xmind", "sheets": sheets, "truncated": state["truncated"],
        "lookup": lambda anchor: index.get(anchor),
    }
