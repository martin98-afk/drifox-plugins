#!/usr/bin/env python3
"""B 站视频数据采集器 — 按阶梯抓取元信息/弹幕/评论/官方总结/字幕/抽帧。

纯标准库实现。所有接口契约见 references/api.md（2026-10-27 实测）。

用法:
    python bili_fetch.py <BV号|av号|b23短链|视频URL> [选项]

选项:
    --out DIR           输出目录（默认 out/<bvid>）
    --frames N          抽帧数量（默认按时长自适应，0=不抽帧）
    --danmaku-limit N   弹幕条数上限（默认 0=全部）
    --comment-limit N   评论条数上限（默认 50）
    --sessdata COOKIE   登录 SESSDATA（仅用于尝试取字幕；不传则跳过 L4）
    --no-ai             跳过 L3 官方 AI 总结
    --json              输出 JSON 摘要到 stdout
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    # 关键：不声明 br，否则标准库解不了
    "Accept-Encoding": "gzip, deflate",
}
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]
FILTER = set("!'()*")


# ---------------------------------------------------------------- HTTP 基础

def http_get(url: str, cookie: str | None = None, timeout: int = 25,
             headers: dict | None = None) -> tuple[int, bytes, dict]:
    """返回 (status, body_bytes, response_headers)。"""
    h = dict(HEADERS)
    if headers:
        h.update(headers)
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers or {})
    except Exception as e:  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}".encode(), {}


def decode_body(raw: bytes, encoding: str) -> bytes:
    """按 Content-Encoding 解压；deflate 兼容 zlib 头与裸流。"""
    encoding = (encoding or "").lower()
    if "gzip" in encoding:
        try:
            return gzip.decompress(raw)
        except Exception:
            return raw
    if "deflate" in encoding:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            try:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
            except Exception:
                return raw
    return raw


def get_json(url: str, cookie: str | None = None, timeout: int = 25):
    st, raw, hd = http_get(url, cookie=cookie, timeout=timeout)
    body = decode_body(raw, hd.get("Content-Encoding", ""))
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return {"__parse_error__": True, "status": st, "raw": body[:300].decode("utf-8", "replace")}


# ---------------------------------------------------------------- WBI 签名

_wbi_cache: dict = {"keys": None, "ts": 0.0}
_WBI_TTL = 3600.0


def get_wbi_keys(cookie: str | None = None) -> tuple[str, str]:
    """nav 接口取 img_key/sub_key，缓存 1 小时（官方建议每日更替即可）。"""
    now = time.time()
    if _wbi_cache["keys"] and now - _wbi_cache["ts"] < _WBI_TTL:
        return _wbi_cache["keys"]
    j = get_json("https://api.bilibili.com/x/web-interface/nav", cookie=cookie)
    wbi = (j.get("data") or {}).get("wbi_img") or {}
    img_url = wbi.get("img_url", "")
    sub_url = wbi.get("sub_url", "")
    keys = (img_url.rsplit("/", 1)[-1].split(".")[0],
            sub_url.rsplit("/", 1)[-1].split(".")[0])
    if keys[0] and keys[1]:
        _wbi_cache.update(keys=keys, ts=now)
    return keys


def mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def wbi_sign(params: dict, img_key: str, sub_key: str) -> str:
    mk = mixin_key(img_key, sub_key)
    clean = {k: "".join(c for c in str(v) if c not in FILTER) for k, v in params.items()}
    clean["wts"] = int(time.time())
    query = urllib.parse.urlencode(sorted(clean.items()), safe="!*'()",
                                   quote_via=urllib.parse.quote)
    return query + "&w_rid=" + hashlib.md5((query + mk).encode()).hexdigest()


def signed_get_json(base: str, params: dict, cookie: str | None = None, timeout: int = 25):
    ik, sk = get_wbi_keys(cookie)
    query = wbi_sign(params, ik, sk)
    return get_json(f"{base}?{query}", cookie=cookie, timeout=timeout)


# ---------------------------------------------------------------- 输入解析

_BV_RE = re.compile(r"\b(BV[0-9A-Za-z]{10})\b")
_AV_RE = re.compile(r"\bav(\d{1,15})\b", re.IGNORECASE)
_SHORT_RE = re.compile(r"b23\.tv/[0-9A-Za-z]+")


def resolve_input(text: str) -> str:
    """把任意形态输入归一成 bvid。短链会跟随重定向。"""
    m = _BV_RE.search(text)
    if m:
        return m.group(1)

    m = _AV_RE.search(text)
    if m:
        return av_to_bv(int(m.group(1)))

    m = _SHORT_RE.search(text)
    if m:
        url = "https://" + m.group(0)
        st, raw, hd = http_get(url, timeout=15)
        final = hd.get("Location") or url
        m2 = _BV_RE.search(final)
        if m2:
            return m2.group(1)
        raise SystemExit(f"短链重定向后未找到 BV 号：{final}")

    raise SystemExit(f"无法从输入中解析 B 站视频标识：{text!r}")


def av_to_bv(aid: int) -> str:
    """av 号 → BV 号。B 站官方算法（base58 + 异或置换）。"""
    table = "fZodR9XQDSUm21yCkr6zBqiveYah8bt4xsWpHnJE7jL5VG3guMTKNPAwcF"
    s = [11, 10, 3, 8, 4, 6]
    xor = 177451812
    add = 8728348608
    tr = {i: table[i] for i in range(58)}

    aid = (aid ^ xor) + add
    r = list("BV1  4 1 7  ")
    for i in range(6):
        r[s[i]] = tr[aid // (58 ** i) % 58]
    return "".join(r)


# ---------------------------------------------------------------- L0 元信息

def fetch_meta(bvid: str, cookie: str | None = None) -> dict:
    j = get_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", cookie=cookie)
    if j.get("code") != 0:
        return {"ok": False, "code": j.get("code"), "message": j.get("message")}
    d = j.get("data") or {}
    return {
        "ok": True,
        "bvid": d.get("bvid"),
        "aid": d.get("aid"),
        "cid": d.get("cid"),
        "title": d.get("title"),
        "desc": d.get("desc"),
        "duration": d.get("duration"),
        "owner": (d.get("owner") or {}).get("name"),
        "pubdate": d.get("pubdate"),
        "pages": [{"page": p.get("page"), "cid": p.get("cid"), "part": p.get("part")}
                  for p in (d.get("pages") or [])],
        "stat": d.get("stat"),
    }


# ---------------------------------------------------------------- L1 弹幕

def fetch_danmaku(cid: int, cookie: str | None = None, limit: int = 0) -> dict:
    """XML 路线。返回按时间排序的弹幕列表。"""
    url = f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}"
    st, raw, hd = http_get(url, cookie=cookie)
    if st != 200:
        return {"ok": False, "status": st, "raw": raw[:200].decode("utf-8", "replace")}
    text = decode_body(raw, hd.get("Content-Encoding", "")).decode("utf-8", "replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return {"ok": False, "error": f"XML 解析失败：{e}"}

    items = []
    for d in root.findall("d"):
        p = (d.get("p") or "").split(",")
        try:
            t = float(p[0]) if p and p[0] else 0.0
        except ValueError:
            t = 0.0
        items.append({"t": t, "text": (d.text or "").strip()})
    items.sort(key=lambda x: x["t"])
    if limit and len(items) > limit:
        items = items[:limit]
    return {"ok": True, "count": len(items), "items": items}


# ---------------------------------------------------------------- L2 评论

def fetch_comments(aid: int, cookie: str | None = None, limit: int = 50,
                   sort: int = 2) -> dict:
    """必须用 /main 端点：x/v2/reply 免登录静默只返回 3 条。"""
    out, pn = [], 1
    while len(out) < limit:
        ps = min(20, limit - len(out))
        url = (f"https://api.bilibili.com/x/v2/reply/main?type=1&oid={aid}"
               f"&sort={sort}&ps={ps}&pn={pn}")
        j = get_json(url, cookie=cookie)
        if j.get("code") != 0:
            if not out:
                return {"ok": False, "code": j.get("code"), "message": j.get("message")}
            break
        data = j.get("data") or {}
        replies = data.get("replies") or []
        if not replies:
            break
        for r in replies:
            out.append({
                "like": r.get("like"),
                "ctime": r.get("ctime"),
                "uname": (r.get("member") or {}).get("uname"),
                "message": (r.get("content") or {}).get("message", ""),
            })
        # /main 端点不返回 page.count（实测为 0），不能用它判定是否到底。
        # 改为：本页返回数少于请求数 → 已无更多，停止。
        if len(replies) < ps:
            break
        if len(out) >= limit:
            break
        pn += 1
        time.sleep(0.3)  # 轻量限速
    return {"ok": True, "count": len(out), "items": out[:limit]}


# ---------------------------------------------------------------- L3 AI 总结

def fetch_ai_conclusion(bvid: str, cid: int, cookie: str | None = None) -> dict:
    """免登录恒为 -403，属常态。静默跳过，不重试。"""
    url = (f"https://api.bilibili.com/x/web-interface/view/conclusion/get"
           f"?bvid={bvid}&cid={cid}&up_mid=0")
    j = get_json(url, cookie=cookie)
    if j.get("code") != 0:
        return {"ok": False, "code": j.get("code"), "message": j.get("message")}
    return {"ok": True, "data": j.get("data")}


# ---------------------------------------------------------------- L4 字幕

def fetch_subtitle(aid: int, cid: int, cookie: str | None = None) -> dict:
    """需 SESSDATA。无 Cookie 时直接跳过，不浪费一次请求。"""
    if not cookie:
        return {"ok": False, "skipped": True, "reason": "未提供 SESSDATA，跳过字幕层"}
    j = signed_get_json("https://api.bilibili.com/x/player/wbi/v2",
                        {"aid": aid, "cid": cid}, cookie=cookie)
    if j.get("code") != 0:
        return {"ok": False, "code": j.get("code"), "message": j.get("message")}
    d = j.get("data") or {}
    sub = d.get("subtitle") or {}
    subs = sub.get("subtitles") or []
    if not subs:
        return {"ok": False, "skipped": True,
                "reason": "字幕列表为空（need_login_subtitle=%s）" % d.get("need_login_subtitle")}

    # 取第一条字幕内容
    u = subs[0].get("subtitle_url") or ""
    if u.startswith("//"):
        u = "https:" + u
    st, raw, hd = http_get(u, cookie=cookie)
    body = decode_body(raw, hd.get("Content-Encoding", ""))
    try:
        sj = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return {"ok": False, "error": "字幕内容解析失败"}
    items = [{"from": b.get("from"), "to": b.get("to"), "content": b.get("content")}
             for b in (sj.get("body") or [])]
    return {"ok": True, "lan": subs[0].get("lan"), "count": len(items), "items": items}


# ---------------------------------------------------------------- L5 抽帧

def find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")


def fetch_streams(bvid: str, cid: int, cookie: str | None = None) -> dict:
    j = signed_get_json("https://api.bilibili.com/x/player/wbi/playurl",
                        {"bvid": bvid, "cid": cid, "fnval": 16, "fnver": 0, "fourk": 1},
                        cookie=cookie)
    if j.get("code") != 0:
        return {"ok": False, "code": j.get("code"), "message": j.get("message")}
    dash = (j.get("data") or {}).get("dash") or {}
    videos = dash.get("video") or []
    audios = dash.get("audio") or []
    if not videos:
        return {"ok": False, "error": "无可用视频流"}
    # 取最低画质（id 最小）省流量
    v = sorted(videos, key=lambda x: x.get("id", 9999))[0]
    return {"ok": True, "video_url": v.get("baseUrl"), "video_id": v.get("id"),
            "audio_url": (audios[0].get("baseUrl") if audios else None)}


def frame_plan(duration: float, n: int | None = None) -> list[float]:
    """按时长自适应抽帧点数，跳过首尾各 5%。"""
    if n is None:
        if duration <= 300:
            n = 6
        elif duration <= 1200:
            n = 10
        elif duration <= 3600:
            n = 16
        else:
            n = 20
    n = max(1, int(n))
    start, end = duration * 0.05, duration * 0.95
    if n == 1:
        return [duration / 2]
    step = (end - start) / (n - 1)
    return [round(start + step * i, 2) for i in range(n)]


def extract_frames(video_url: str, points: list[float], out_dir: str,
                   ffmpeg: str, timeout: int = 180) -> list[dict]:
    os.makedirs(out_dir, exist_ok=True)
    frames = []
    for sec in points:
        dst = os.path.join(out_dir, f"f{int(sec)}.jpg")
        cmd = [ffmpeg, "-y", "-loglevel", "error",
               "-user_agent", UA,
               "-headers", "Referer: https://www.bilibili.com/\r\n",
               "-ss", str(sec),          # 必须在 -i 前
               "-i", video_url,
               "-frames:v", "1",
               "-vf", "scale=960:-1",
               "-q:v", "4", dst]
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        if p.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
            frames.append({"t": sec, "path": os.path.abspath(dst)})
    return frames


# ---------------------------------------------------------------- 主流程

def run(target: str, out_root: str, frames: int | None, danmaku_limit: int,
        comment_limit: int, sessdata: str | None, no_ai: bool) -> dict:
    bvid = resolve_input(target)
    cookie = f"SESSDATA={sessdata}" if sessdata else None
    out_dir = os.path.join(out_root, bvid)
    os.makedirs(out_dir, exist_ok=True)

    report: dict = {"bvid": bvid, "out_dir": os.path.abspath(out_dir), "layers": {}}

    meta = fetch_meta(bvid, cookie)
    report["layers"]["L0"] = meta
    if not meta.get("ok"):
        # 硬停止：拿不到元信息就没有 aid/cid，后续各层无法进行，不空跑
        report["confidence"] = "none"
        report["stop_reason"] = f"视频元信息获取失败：{meta.get('message')}"
        report["layers"].update({
            "L1": {"ok": False, "reason": "L0 失败，未执行"},
            "L2": {"ok": False, "reason": "L0 失败，未执行"},
            "L3": {"ok": False, "reason": "L0 失败，未执行"},
            "L4": {"ok": False, "reason": "L0 失败，未执行"},
            "L5": {"ok": False, "reason": "L0 失败，未执行"},
        })
        with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return report

    aid, cid, duration = meta["aid"], meta["cid"], meta.get("duration") or 0

    dm = fetch_danmaku(cid, cookie, limit=danmaku_limit)
    report["layers"]["L1"] = {"ok": dm.get("ok"), "count": dm.get("count", 0),
                              "reason": dm.get("reason") or dm.get("error") or dm.get("raw")}
    if dm.get("ok"):
        with open(os.path.join(out_dir, "danmaku.json"), "w", encoding="utf-8") as f:
            json.dump(dm, f, ensure_ascii=False, indent=2)

    cm = fetch_comments(aid, cookie, limit=comment_limit)
    report["layers"]["L2"] = {"ok": cm.get("ok"), "count": cm.get("count", 0),
                              "reason": cm.get("message") if not cm.get("ok") else None}
    if cm.get("ok"):
        with open(os.path.join(out_dir, "comments.json"), "w", encoding="utf-8") as f:
            json.dump(cm, f, ensure_ascii=False, indent=2)

    if no_ai:
        report["layers"]["L3"] = {"ok": False, "skipped": True, "reason": "--no-ai"}
    else:
        ai = fetch_ai_conclusion(bvid, cid, cookie)
        report["layers"]["L3"] = {"ok": ai.get("ok"), "code": ai.get("code"),
                                  "reason": ai.get("message") if not ai.get("ok") else None,
                                  "data": ai.get("data") if ai.get("ok") else None}

    sub = fetch_subtitle(aid, cid, cookie)
    report["layers"]["L4"] = {"ok": sub.get("ok"), "count": sub.get("count", 0),
                              "reason": sub.get("reason") or sub.get("error") or sub.get("message")}
    if sub.get("ok"):
        with open(os.path.join(out_dir, "subtitle.json"), "w", encoding="utf-8") as f:
            json.dump(sub, f, ensure_ascii=False, indent=2)

    # L5 抽帧
    ff = find_ffmpeg()
    if frames == 0:
        report["layers"]["L5"] = {"ok": False, "skipped": True, "reason": "--frames 0"}
    elif not ff:
        report["layers"]["L5"] = {"ok": False, "reason": "本机未检测到 ffmpeg，跳过抽帧"}
    else:
        try:
            st = fetch_streams(bvid, cid, cookie)
            if not st.get("ok"):
                report["layers"]["L5"] = {"ok": False, "reason": f"视频流获取失败：{st.get('message') or st.get('error')}"}
            else:
                pts = frame_plan(duration, None if frames is None else frames)
                fr = extract_frames(st["video_url"], pts, os.path.join(out_dir, "frames"), ff)
                report["layers"]["L5"] = {"ok": bool(fr), "count": len(fr), "frames": fr,
                                          "audio_url": st.get("audio_url")}
        except Exception as e:  # noqa: BLE001
            report["layers"]["L5"] = {"ok": False, "reason": f"{type(e).__name__}: {e}"}

    # 置信度判定
    l0 = report["layers"]["L0"].get("ok")
    l1 = report["layers"]["L1"].get("count", 0)
    l2 = report["layers"]["L2"].get("count", 0)
    l3 = report["layers"]["L3"].get("ok")
    l4 = report["layers"]["L4"].get("ok")
    l5 = report["layers"]["L5"].get("count", 0)

    if l0 and (l4 or l3):
        report["confidence"] = "高"
    elif l0 and (l1 or l2 or l5):
        report["confidence"] = "中"
    elif l0:
        report["confidence"] = "低"
    else:
        report["confidence"] = "none"

    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="B 站视频数据采集器")
    ap.add_argument("target", help="BV号 / av号 / b23短链 / 视频URL")
    ap.add_argument("--out", default="out", help="输出根目录")
    ap.add_argument("--frames", type=int, default=-1, help="抽帧数量，-1=自适应，0=不抽")
    ap.add_argument("--danmaku-limit", type=int, default=0, help="弹幕条数上限，0=全部")
    ap.add_argument("--comment-limit", type=int, default=50, help="评论条数上限")
    ap.add_argument("--sessdata", default=None, help="SESSDATA cookie（用于取字幕）")
    ap.add_argument("--no-ai", action="store_true", help="跳过官方 AI 总结")
    ap.add_argument("--json", action="store_true", help="输出 JSON 摘要")
    args = ap.parse_args()

    frames = None if args.frames == -1 else args.frames
    report = run(args.target, args.out, frames, args.danmaku_limit,
                 args.comment_limit, args.sessdata, args.no_ai)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    m = report["layers"]["L0"]
    if not m.get("ok"):
        print(f"❌ 无法获取视频信息：{m.get('message')}（code={m.get('code')}）")
        print(f"   视频标识：{report['bvid']}")
        print("   视频可能不存在、已失效或需要登录。流程已停止。")
        return 1
    print(f"标题：{m.get('title')}")
    print(f"UP 主：{m.get('owner')}  时长：{m.get('duration')}s")
    print(f"置信度：{report.get('confidence')}")
    print("数据来源：")
    labels = {"L0": "元信息", "L1": "弹幕", "L2": "评论", "L3": "官方AI总结", "L4": "字幕", "L5": "抽帧"}
    for k, label in labels.items():
        layer = report["layers"].get(k, {})
        if layer.get("ok"):
            extra = layer.get("count", "")
            print(f"  ✅ {label} {extra}")
        else:
            print(f"  ❌ {label} — {layer.get('reason') or layer.get('message') or '失败'}")
    print(f"\n产物目录：{report['out_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
