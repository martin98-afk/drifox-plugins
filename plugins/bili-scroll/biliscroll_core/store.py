# -*- coding: utf-8 -*-
"""值班数据落盘：判重表（seen.tsv）、日报（out/）、月度归档（digest/）。

契约（与值班章程对齐）：
- 日报每段以 `### <BV号>` 开头，配额计数数的就是这些标题行
- 判重表一行一条：ts \t bvid \t title \t up \t status \t rpid \t root
  （status ∈ 挑了/跳过/评论；rpid/root 发评论后回填，供宿主复核）
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .paths import plugin_data_root

_TODAY = lambda: _dt.date.today().isoformat()  # noqa: E731


def _require_root(root: Path | None) -> Path:
    base = root or plugin_data_root()
    if not base:
        raise RuntimeError("数据目录不可用（storage.data_dir 能力未就绪）")
    return Path(base)


class DutyStore:
    def __init__(self, root: Path | None = None):
        self.root = _require_root(root)
        self.out_dir = self.root / "out"
        self.digest_dir = self.root / "digest"
        self.seen_path = self.root / "seen.tsv"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.digest_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- 日报 ----------------

    def report_path(self, day: str | None = None) -> Path:
        return self.out_dir / f"{day or _TODAY()}.md"

    def report_append(self, text: str) -> str:
        """追加日报并返回路径。值班轮契约：保底至少一行，绝不留空文件。"""
        path = self.report_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
        return str(path)

    def count_picked_today(self) -> int:
        """今天已挑条数 = 日报里 `### ` 标题行数（配额契约）。"""
        path = self.report_path()
        if not path.is_file():
            return 0
        with open(path, encoding="utf-8") as f:
            return sum(1 for line in f if line.startswith("### "))

    # ---------------- 判重表 ----------------

    def seen_append(self, bvid: str, title: str, up: str, status: str,
                    rpid: str = "", root: str = "") -> None:
        row = [_TODAY(), bvid, title.replace("\t", " "), up.replace("\t", " "),
               status, str(rpid), str(root)]
        with open(self.seen_path, "a", encoding="utf-8") as f:
            f.write("\t".join(row) + "\n")

    def seen_seen(self, bvid: str) -> bool:
        return any(r.get("bvid") == bvid for r in self.seen_recent(limit=100000))

    def seen_recent(self, limit: int = 40, bvid: str = "") -> list[dict]:
        """最近 limit 条（新→旧）；给 bvid 则只查该条。"""
        if not self.seen_path.is_file():
            return []
        rows: list[dict] = []
        with open(self.seen_path, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 5:
                    continue
                row = {
                    "date": parts[0], "bvid": parts[1], "title": parts[2],
                    "up": parts[3], "status": parts[4],
                    "rpid": parts[5] if len(parts) > 5 else "",
                    "root": parts[6] if len(parts) > 6 else "",
                }
                if bvid and row["bvid"] != bvid:
                    continue
                rows.append(row)
        rows.reverse()
        return rows[:limit] if limit else rows

    def my_recent_comments(self, days: int = 7) -> list[dict]:
        """最近 N 天自己发过评论的记录（回复评论前先查，别漏人）。"""
        cutoff = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
        return [r for r in self.seen_recent(limit=100000)
                if r["status"] == "评论" and r["rpid"] and r["date"] >= cutoff]

    # ---------------- 归档 ----------------

    def digest_path(self) -> Path:
        return self.digest_dir / f"{_dt.date.today().strftime('%Y-%m')}.md"

    def digest_append(self, text: str) -> str:
        path = self.digest_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
        return str(path)
