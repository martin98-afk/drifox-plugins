#!/usr/bin/env python3
"""环境自检 — 报告 ffmpeg / B 站连通性 / SESSDATA 三件事。

用法:
    python check_env.py [--json]
"""
from __future__ import annotations

import json
import os
import shutil
import sys

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate",
}
PROBE_BVID = "BV1GJ411x7h7"


def check_ffmpeg() -> dict:
    path = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not path:
        return {"ok": False, "path": None,
                "hint": "未检测到 ffmpeg。抽帧层不可用，照 fallback.md 降级；"
                        "Windows 可去 gyan.dev 下载并加进 PATH。"}
    ver = ""
    try:
        import subprocess
        p = subprocess.run([path, "-version"], capture_output=True, timeout=15)
        ver = p.stdout.decode("utf-8", "replace").splitlines()[0] if p.stdout else ""
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "path": path, "version": ver}


def check_connectivity() -> dict:
    import gzip
    import json as _json
    import urllib.request
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={PROBE_BVID}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            if "gzip" in (resp.headers.get("Content-Encoding") or "").lower():
                raw = gzip.decompress(raw)
            j = _json.loads(raw.decode("utf-8", "replace"))
            return {"ok": j.get("code") == 0, "code": j.get("code"),
                    "message": j.get("message"),
                    "probe_bvid": PROBE_BVID,
                    "probe_title": (j.get("data") or {}).get("title")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "probe_bvid": PROBE_BVID}


def check_sessdata() -> dict:
    val = os.environ.get("BILI_SESSDATA") or os.environ.get("SESSDATA")
    if val:
        return {"ok": True, "source": "env", "note": "可尝试字幕层"}
    return {"ok": False, "source": None,
            "note": "未提供 SESSDATA：字幕层（L4）将跳过，官方 AI 总结（L3）预期 -403"}


def main() -> int:
    as_json = "--json" in sys.argv
    result = {
        "ffmpeg": check_ffmpeg(),
        "connectivity": check_connectivity(),
        "sessdata": check_sessdata(),
    }

    if not result["ffmpeg"]["ok"]:
        result["warning"] = "ffmpeg 缺失 → 抽帧层不可用，必须降级并在报告中标注"
    if not result["connectivity"]["ok"]:
        result["warning"] = "无法连通 B 站 → 整个流程无法进行"

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["connectivity"]["ok"] else 1

    ff = result["ffmpeg"]
    print(f"ffmpeg    : {'✅ ' + ff['path'] if ff['ok'] else '❌ 未检测到'}")
    if ff["ok"] and ff.get("version"):
        print(f"            {ff['version']}")
    co = result["connectivity"]
    print(f"连通性    : {'✅ 正常' if co['ok'] else '❌ ' + str(co.get('error') or co.get('message'))}")
    if co["ok"]:
        print(f"            探针 {co['probe_bvid']} = {co.get('probe_title')}")
    sd = result["sessdata"]
    print(f"SESSDATA  : {'✅ 已提供' if sd['ok'] else '⚠  未提供'} — {sd['note']}")
    if result.get("warning"):
        print(f"\n⚠  {result['warning']}")
    return 0 if result["connectivity"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
