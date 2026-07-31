# -*- coding: utf-8 -*-
"""git-panel Git 操作封装层 — GitRepo / GitResult

统一封装所有 git 命令调用，卡片代码只面向 GitRepo 编程，
不再散落 subprocess 调用。

设计约束（闭包）：
- 仅依赖 stdlib（subprocess / re / dataclasses / logging），不导入 cards.py
- 单向依赖：cards.py → git_core.py
- 执行类方法返回 GitResult（ok/stdout/stderr/code）
- 查询类方法返回解析后的结构化数据（list / dict / str）
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple

_log = logging.getLogger("git-panel")

GIT_TIMEOUT = 15      # 本地操作超时（秒）
NETWORK_TIMEOUT = 60  # 网络操作（push/pull/fetch）超时（秒）


# ========================================================================
# git 命令执行（唯一 subprocess 入口）
# ========================================================================


def _run_git(cwd: str, *args: str, strip: bool = True, timeout: int = GIT_TIMEOUT) -> Tuple[str, str, int]:
    """执行 git 命令，返回 (stdout, stderr, returncode)

    strip=True 时去除输出首尾空白（默认，适合绝大多数命令）；
    porcelain 等需要保留前导空格的场景传 strip=False。
    """
    try:
        r = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out, err = r.stdout, r.stderr
        if strip:
            out, err = out.strip(), err.strip()
        return out, err, r.returncode
    except subprocess.TimeoutExpired:
        return "", f"timeout ({timeout}s)", -1
    except FileNotFoundError:
        return "", "git not found", -1
    except Exception as e:
        return "", str(e), -1


# ========================================================================
# 查询辅助（GitRepo 各方法复用）
# ========================================================================


def _is_git_repo(cwd: str) -> bool:
    if not cwd:
        return False
    _, _, code = _run_git(cwd, "rev-parse", "--is-inside-work-tree")
    return code == 0


def _get_branch(cwd: str) -> str:
    stdout, _, code = _run_git(cwd, "branch", "--show-current")
    if code == 0 and stdout:
        return stdout
    stdout, _, _ = _run_git(cwd, "rev-parse", "--short", "HEAD")
    if stdout:
        return f"(detached @ {stdout})"
    return ""


def _get_ahead_behind(cwd: str) -> Tuple[int, int]:
    stdout, _, _ = _run_git(cwd, "rev-list", "--left-right", "--count", "HEAD...@{u}")
    if stdout:
        parts = stdout.split()
        if len(parts) == 2:
            try:
                return int(parts[0]), int(parts[1])
            except ValueError:
                pass
    return 0, 0


def _get_diff(cwd: str, path: str, staged: bool = False) -> str:
    """获取单个文件的 diff"""
    args = ["diff", "--cached", "--"] if staged else ["diff", "--"]
    stdout, _, _ = _run_git(cwd, *args, path)
    return stdout


def _get_stashes(cwd: str) -> List[dict]:
    """获取 stash 列表 [{"ref", "message", "index"}]"""
    stdout, _, code = _run_git(cwd, "stash", "list")
    if code != 0 or not stdout:
        return []
    result = []
    for line in stdout.splitlines():
        parts = line.split(": ", 1)
        ref = parts[0] if len(parts) > 0 else ""
        msg = parts[1] if len(parts) > 1 else ""
        idx = 0
        m = re.search(r"stash@\{(\d+)\}", ref)
        if m:
            idx = int(m.group(1))
        result.append({"ref": ref, "message": msg, "index": idx})
    return result


def _get_branches(cwd: str) -> List[dict]:
    """获取分支列表 [{"name", "current"}]"""
    stdout, _, code = _run_git(cwd, "branch")
    if code != 0 or not stdout:
        return []
    current_branch = _get_branch(cwd)
    result = []
    for line in stdout.splitlines():
        is_current = line.startswith("*")
        name = line[2:].strip()
        result.append({"name": name, "current": is_current})
    return result


# ========================================================================
# GitResult / GitRepo
# ========================================================================


@dataclass
class GitResult:
    """git 命令执行结果"""

    ok: bool
    stdout: str = ""
    stderr: str = ""
    code: int = -1

    @staticmethod
    def from_run(stdout: str, stderr: str, code: int) -> "GitResult":
        return GitResult(ok=code == 0, stdout=stdout, stderr=stderr, code=code)

    @property
    def error_message(self) -> str:
        """适合展示给用户的错误摘要（固定回退，不回退 stdout）"""
        return self.stderr or "未知错误（stderr 为空）"


class GitRepo:
    """面向一个仓库目录的 git 命令封装"""

    def __init__(self, cwd: str):
        self.cwd = cwd

    # ── 底层 ──

    def _run(self, *args: str, strip: bool = True, timeout: int = GIT_TIMEOUT) -> GitResult:
        stdout, stderr, code = _run_git(self.cwd, *args, strip=strip, timeout=timeout)
        return GitResult.from_run(stdout, stderr, code)

    # ── 状态 ──

    def is_git_repo(self) -> bool:
        return _is_git_repo(self.cwd)

    def branch(self) -> str:
        """当前分支名（detached 时返回短 hash）"""
        return _get_branch(self.cwd)

    def ahead_behind(self) -> Tuple[int, int]:
        """与 upstream 的 (ahead, behind)"""
        return _get_ahead_behind(self.cwd)

    def status(self) -> List[Tuple[str, str]]:
        """文件变更列表 [(path, xy_code)]，xy 为 porcelain 两位状态码"""
        # strip=False：porcelain 输出以空格表示工作区列，必须保留前导空格；
        # --no-optional-locks：只读刷新不写 index，避免与暂存等写操作并发抢锁
        res = self._run("--no-optional-locks", "status", "--porcelain", "-u", strip=False)
        if not res.ok or not res.stdout:
            return []
        result = []
        for line in res.stdout.splitlines():
            if not line.strip():
                continue
            x, y = line[0], line[1]
            path = line[3:].strip()
            result.append((path, f"{x}{y}"))
        return result

    def status_items(self) -> List[dict]:
        """文件变更列表 [{"path", "status", "staged"}]（UI 渲染用）

        冲突文件（XY 为 UU/AA/DD/DU/UD/AU/UA）合并为单个条目，
        status 为两位组合码，便于 UI 识别冲突状态。
        """
        CONFLICT_CODES = {"UU", "AA", "DD", "DU", "UD", "AU", "UA"}
        items: List[dict] = []
        for path, xy in self.status():
            x, y = xy[0], xy[1]
            # 未跟踪文件（??）优先处理，避免重复
            if x == "?" and y == "?":
                items.append({"path": path, "status": "??", "staged": False})
                continue
            # 冲突状态：合并为单个条目（两位组合码）
            if xy in CONFLICT_CODES:
                items.append({"path": path, "status": xy, "staged": False})
                continue
            # 暂存区变更（X != ' '）
            if x != " ":
                items.append({"path": path, "status": x, "staged": True})
            # 工作区变更（Y != ' '）
            if y != " ":
                items.append({"path": path, "status": y, "staged": False})
        return items

    # ── 暂存 / 放弃 ──

    def add(self, paths: List[str]) -> GitResult:
        """暂存指定路径（paths 可为 ["-A"] 表示全部）"""
        return self._run("add", *paths)

    def restore_staged(self, paths: List[str]) -> GitResult:
        """取消暂存（paths 可为 ["."] 表示全部）"""
        return self._run("restore", "--staged", *paths)

    def checkout_discard(self, paths: List[str]) -> GitResult:
        """放弃已跟踪文件的工作区修改"""
        return self._run("checkout", "--", *paths)

    def clean_untracked(self, paths: List[str]) -> GitResult:
        """删除未跟踪文件"""
        return self._run("clean", "-f", "--", *paths)

    # ── 提交 ──

    def commit(self, message: str = "", amend: bool = False) -> GitResult:
        """提交；amend=True 且 message 为空时使用 --no-edit"""
        if amend:
            if message:
                return self._run("commit", "--amend", "-m", message)
            return self._run("commit", "--amend", "--no-edit")
        return self._run("commit", "-m", message)

    # ── Stash ──

    def stash_push(self, msg: str = "WIP") -> GitResult:
        return self._run("stash", "push", "-m", msg)

    def stash_list(self) -> List[dict]:
        """[{"ref", "message", "index"}]"""
        return _get_stashes(self.cwd)

    def stash_apply(self, idx: int = 0) -> GitResult:
        return self._run("stash", "apply", f"stash@{{{idx}}}")

    def stash_pop(self, idx: int = 0) -> GitResult:
        return self._run("stash", "pop", f"stash@{{{idx}}}")

    def stash_drop(self, idx: int = 0) -> GitResult:
        return self._run("stash", "drop", f"stash@{{{idx}}}")

    # ── 分支 ──

    def branch_list(self) -> List[dict]:
        """[{"name", "current"}]"""
        return _get_branches(self.cwd)

    def branch_checkout(self, name: str) -> GitResult:
        return self._run("checkout", name)

    def branch_create(self, name: str) -> GitResult:
        """创建并切换到新分支"""
        return self._run("checkout", "-b", name)

    def branch_delete(self, name: str) -> GitResult:
        return self._run("branch", "-d", name)

    # ── 同步（push / pull / fetch，网络超时 60s） ──

    def push(self) -> GitResult:
        """推送；仅当无 upstream 时自动重试 git push --set-upstream origin HEAD"""
        res = self._run("push", timeout=NETWORK_TIMEOUT)
        if res.ok:
            return res
        err = res.stderr.lower()
        if any(k in err for k in ("no upstream", "set-upstream",
                                  "has no upstream", "current branch")):
            retry = self._run("push", "--set-upstream", "origin", "HEAD",
                              timeout=NETWORK_TIMEOUT)
            if retry.ok:
                return retry
        return res

    def pull_rebase(self) -> GitResult:
        """pull --rebase --autostash。

        - rebase 冲突：返回原错误（不静默回退），提示用户 git rebase --continue
        - 其他失败（网络/认证等）：回退普通 git pull
        """
        res = self._run("pull", "--rebase", "--autostash", timeout=NETWORK_TIMEOUT)
        if res.ok:
            return res
        err = res.stderr.lower()
        if any(k in err for k in ("conflict", "could not apply", "rebase in progress")):
            return res
        _log.warning("[git-panel] pull --rebase 失败（%s），回退普通 pull", res.error_message)
        fallback = self._run("pull", timeout=NETWORK_TIMEOUT)
        if fallback.ok:
            return fallback
        _log.warning("[git-panel] 普通 pull 也失败（%s）", fallback.error_message)
        return fallback

    def fetch(self) -> GitResult:
        return self._run("fetch", "--all", "--prune", timeout=NETWORK_TIMEOUT)

    # ── 日志 ──

    def log(self, n: int = 30, graph: bool = False) -> List[dict]:
        """提交历史 [{"hash", "author", "date", "subject", "refs", "graph"}]"""
        fmt = "--format=%h%x1f%an%x1f%ai%x1f%s%x1f%D"
        args = ["log", f"-n{n}", fmt, "--all"]
        if graph:
            args.insert(1, "--graph")
        res = self._run(*args)
        if not res.ok or not res.stdout:
            return []
        result = []
        for line in res.stdout.splitlines():
            item = self._parse_log_line(line, graph)
            if item:
                result.append(item)
        return result

    @staticmethod
    def _parse_log_line(line: str, graph: bool) -> Optional[dict]:
        graph_prefix = ""
        rest = line
        if graph:
            # 剥离行首图形前缀（* | / \ 及空格），如 "* "、"| * "
            m = re.match(r"^([|*/\\\s]*?)(?=[0-9a-f]{4,40}\x1f)", line)
            if m:
                graph_prefix = m.group(0).rstrip()
                rest = line[len(m.group(0)):]
        parts = rest.split("\x1f")
        if len(parts) < 4:
            return None
        hash_, author, date_raw, subject = parts[0], parts[1], parts[2], parts[3]
        refs = parts[4] if len(parts) > 4 else ""
        date = date_raw[:10] if date_raw and len(date_raw) >= 10 else date_raw
        return {
            "hash": hash_,
            "author": author,
            "date": date,
            "subject": subject,
            "refs": refs,
            "graph": graph_prefix,
        }

    # ── Diff ──

    def diff(self, path: str, staged: bool = False) -> str:
        return _get_diff(self.cwd, path, staged)

    def show_commit(self, hash_: str) -> GitResult:
        """查看单个 commit 的完整信息与 diff（git show --format=fuller）"""
        return self._run("show", "--format=fuller", hash_)

    # ── 冲突解决 ──

    def checkout_ours(self, path: str) -> GitResult:
        """冲突解决：采用当前分支（ours）版本"""
        return self._run("checkout", "--ours", "--", path)

    def checkout_theirs(self, path: str) -> GitResult:
        """冲突解决：采用合并来源（theirs）版本"""
        return self._run("checkout", "--theirs", "--", path)
