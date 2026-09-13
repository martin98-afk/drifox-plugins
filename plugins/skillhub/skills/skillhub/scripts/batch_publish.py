# -*- coding: utf-8 -*-
"""批量发布仓库技能到 SkillHub。

用法:
    python batch_publish.py <仓库根目录> [数量上限]

行为:
    - 扫描 <仓库根>/plugins/**/skills/*/SKILL.md，逐个 skillhub publish
    - 发布间隔 2 秒；命中限流按 30/60/90/120 秒退避重试，最多 4 次
    - 结果追加写入 <仓库根>/skillhub_results.jsonl，重跑自动跳过已成功项（断点续传）
    - 退出码: 0=全部处理完成（含内容性失败），2=CLI 不存在
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time

GAP = 2        # 相邻 publish 间隔秒数
RETRIES = 4    # 限流重试次数
BACKOFF = 30   # 限流基础等待秒数

def find_cli():
    return shutil.which("skillhub") or shutil.which("skillhub.cmd")

def load_done(out_path):
    done = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("ok"):
                    done.add(r["path"])
    return done

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    repo = os.path.abspath(sys.argv[1])
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    cli = find_cli()
    if not cli:
        print("[FATAL] 未找到 skillhub CLI，先执行: npm i -g @astron-team/skillhub")
        return 2

    out_path = os.path.join(repo, "skillhub_results.jsonl")
    dirs = sorted({os.path.dirname(p) for p in glob.glob(
        os.path.join(repo, "plugins", "**", "skills", "*", "SKILL.md"), recursive=True)})
    done = load_done(out_path)
    print(f"total={len(dirs)} done_skip={len(done)}", flush=True)

    count = 0
    for d in dirs:
        if d in done:
            continue
        if limit and count >= limit:
            break
        count += 1
        t0 = time.time()
        data = None
        for attempt in range(1, RETRIES + 1):
            try:
                p = subprocess.run(
                    [cli, "publish", d, "--json"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=120,
                )
                out = (p.stdout or "").strip()
                try:
                    data = json.loads(out)
                except Exception:
                    data = {"ok": False,
                            "message": (out[-500:] or (p.stderr or "")[-500:]),
                            "exitCode": p.returncode}
            except subprocess.TimeoutExpired:
                data = {"ok": False, "message": "timeout", "exitCode": -1}
            if data.get("ok") or "rate limit" not in (data.get("message") or "").lower():
                break
            wait = BACKOFF * attempt
            print(f"[WAIT] 限流 {os.path.basename(d)}，等待 {wait}s（{attempt}/{RETRIES}）", flush=True)
            time.sleep(wait)

        rec = {"path": d, "ok": bool(data.get("ok")),
               "slug": data.get("slug") or os.path.basename(d),
               "msg": (data.get("message") or "")[:300],
               "sec": round(time.time() - t0, 1)}
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        mark = "OK  " if rec["ok"] else "FAIL"
        print(f"[{mark}] {rec['slug']} ({rec['sec']}s) {rec['msg'][:120]}", flush=True)
        time.sleep(GAP)
    print("ALL_DONE", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
