# -*- coding: utf-8 -*-
"""
evolution_publish — 自进化工具 6：发布插件到官方市场仓库（drifox-plugins）。

流程（与官方发布手册一致，全自动）：
  1. 定位市场仓库（显式 repo_path 优先，否则探测常见路径）
  2. user 根插件 → 仓库 plugins/<name>（排除 __pycache__，删旧后全量同步）
  3. 运行 tools/generate_marketplace.py 更新 marketplace.json
  4. 运行 tools/validate_plugins.py 校验目标插件（准入）
  5. git commit（conventional message）+ 可选 git push（push=true，先 rebase 拉齐远端）

版本纪律：发布前对比 plugin.json 与 marketplace.json 已收录版本，
相同则警告提醒 bump（不阻断）。
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from app.tools.result import ToolResult

_CANDIDATE_REPOS = (
    r"D:\work\drifox-plugins2",
    r"D:\work\drifox-plugins",
    "~/drifox-plugins",
)
_COMMIT_TYPES = ("feat", "fix", "docs", "chore", "refactor", "test")


def _user_root(tool_ctx) -> Path:
    env = tool_ctx.get("env") or {}
    app_data = env.get("app_data_dir")
    if app_data:
        root = Path(app_data) / "plugins"
        if root.is_dir():
            return root
    return Path.home() / ".drifox" / "plugins"


def _find_repo(repo_path: str | None) -> Path | None:
    """定位市场仓库：需同时含 plugins/ 与 tools/generate_marketplace.py"""
    if repo_path:
        p = Path(repo_path).expanduser()
        return p if (p / "tools" / "generate_marketplace.py").exists() else None
    for c in _CANDIDATE_REPOS:
        p = Path(c).expanduser()
        if (p / "tools" / "generate_marketplace.py").exists():
            return p
    return None


def _run(cmd: list, cwd: Path) -> tuple[int, str]:
    r = subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out.strip()


def _upstream_owner(repo: Path) -> str:
    """从 origin remote URL 提取官方仓库 owner（fork 模式拼 PR 链接用）"""
    code, out = _run(["git", "remote", "get-url", "origin"], repo)
    if code != 0:
        return "martin98-afk"
    url = out.strip()
    # https://github.com/<owner>/<repo>.git 或 git@github.com:<owner>/<repo>.git
    if url.startswith("git@github.com:"):
        return url.split(":")[1].split("/")[0]
    if "github.com" in url:
        return url.rstrip("/").split("/")[-2]
    return "martin98-afk"


def _marketplace_version(repo: Path, plugin_name: str) -> str | None:
    try:
        m = json.loads((repo / "marketplace.json").read_text(encoding="utf-8"))
        for p in m.get("plugins", []):
            if p.get("name") == plugin_name:
                return p.get("version")
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _impl(tool_ctx, **kwargs):
    try:
        plugin_name = (kwargs.get("plugin_name") or "").strip()
        if not plugin_name:
            return ToolResult(False, error="必须提供 plugin_name")
        mode = (kwargs.get("mode") or "local").strip()
        if mode not in ("local", "direct", "fork"):
            return ToolResult(False, error="mode 需为 local（仅本地 commit）/ direct（直推 origin）/ fork（推 fork+PR）")
        if kwargs.get("push") and mode == "local":
            mode = "direct"  # 向后兼容 push=true
        fork_remote = (kwargs.get("fork_remote") or "").strip()
        if mode == "fork" and not fork_remote:
            return ToolResult(
                False,
                error="fork 模式需提供 fork_remote（你 fork 的仓库地址，"
                      "如 https://github.com/<你的账号>/drifox-plugins.git）。"
                      "fork：github.com/martin98-afk/drifox-plugins 右上角 Fork。",
            )
        commit_type = (kwargs.get("commit_type") or "feat").strip()
        if commit_type not in _COMMIT_TYPES:
            return ToolResult(False, error=f"commit_type 需为 {list(_COMMIT_TYPES)}")
        message = (kwargs.get("message") or "").strip()
        repo_path = (kwargs.get("repo_path") or "").strip() or None

        # ① 定位仓库与插件源
        repo = _find_repo(repo_path)
        if repo is None:
            return ToolResult(
                False,
                error="未找到市场仓库（含 tools/generate_marketplace.py）。"
                      "请提供 repo_path 参数指向 drifox-plugins 检出目录。",
            )
        src = _user_root(tool_ctx) / plugin_name
        if not src.is_dir():
            return ToolResult(False, error=f"user 根未找到插件 {plugin_name}（{src}）")

        steps = []

        # ② 版本纪律检查（同版本发布 → 警告不阻断）
        manifest = json.loads((src / ".drifox-plugin" / "plugin.json").read_text(encoding="utf-8"))
        new_ver = manifest.get("version", "?")
        old_ver = _marketplace_version(repo, plugin_name)
        version_note = ""
        if old_ver == new_ver:
            version_note = f"⚠ 版本未变（{new_ver}），建议 bump 后再发布\n"

        # ③ 同步到仓库（删旧 + copytree 排除 pycache）
        dst = repo / "plugins" / plugin_name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        steps.append(f"✓ 同步 {plugin_name} → {dst}")

        # ④ generate marketplace
        code, out = _run([sys.executable, "tools/generate_marketplace.py"], repo)
        if code != 0:
            return ToolResult(False, error=f"generate_marketplace 失败：\n{out}\n（已同步文件，未提交）")
        steps.append("✓ marketplace.json 已更新")

        # ⑤ validate（只看目标插件结果）
        code, out = _run([sys.executable, "tools/validate_plugins.py", f"plugins/{plugin_name}"], repo)
        if code != 0 or f"OK   {plugin_name}" not in out:
            detail = "\n".join(l for l in out.splitlines() if plugin_name in l or "err" in l)
            return ToolResult(
                False,
                error=f"validate 未通过：\n{detail or out}\n（已同步文件与 marketplace，未提交——修复后重跑）",
            )
        steps.append(f"✓ validate 通过：{plugin_name}")

        # ⑥ git add + commit
        _run(["git", "add", f"plugins/{plugin_name}", "marketplace.json"], repo)
        if not message:
            message = f"{commit_type}({plugin_name}): 发布 v{new_ver}（evolution_publish）"
        code, out = _run(["git", "commit", "-m", message], repo)
        if code != 0:
            if "nothing to commit" in out or "no changes added" in out:
                steps.append("• 无变更，跳过 commit")
            else:
                return ToolResult(False, error=f"git commit 失败：\n{out}")
        else:
            steps.append(f"✓ commit：{message}")

        # ⑦ 推送（按模式）
        pr_url = ""
        if mode == "direct":
            code, out = _run(["git", "pull", "--rebase", "origin", "main"], repo)
            if code != 0:
                return ToolResult(False, error=f"git pull --rebase 失败（本地 commit 已保留）：\n{out}")
            code, out = _run(["git", "push", "origin", "main"], repo)
            if code != 0:
                return ToolResult(False, error=f"git push 失败（本地 commit 已保留）：\n{out}")
            steps.append("✓ 已直推 origin/main（需官方仓库写权限）")
        elif mode == "fork":
            branch = f"feat/{plugin_name}"
            _run(["git", "checkout", "-B", branch], repo)
            code, out = _run(
                ["git", "push", fork_remote, f"{branch}:{branch}"], repo
            )
            if code != 0:
                _run(["git", "checkout", "main"], repo)
                return ToolResult(False, error=f"推送到 fork 失败（本地分支已保留）：\n{out}")
            steps.append(f"✓ 已推送到 fork 分支 {branch}")
            owner = _upstream_owner(repo)
            fork_owner = fork_remote.rstrip("/").rstrip(".git").split("/")[-2] \
                if "/" in fork_remote else "<你的账号>"
            pr_url = (
                f"https://github.com/{owner}/drifox-plugins/compare"
                f"/main...{fork_owner}:drifox-plugins:{branch}?expand=1"
            )
            steps.append(f"下一步：打开 PR 页面提交审核：\n  {pr_url}")
            _run(["git", "checkout", "main"], repo)  # 切回 main

        mode_label = {"local": "（本地）", "direct": "完成（已直推）", "fork": "到 fork（待提 PR）"}[mode]
        content = (
            f"插件 {plugin_name} 发布{mode_label}\n"
            f"仓库：{repo}\n"
            f"版本：{old_ver or '（新收录）'} → {new_ver}\n"
            f"{version_note}"
            + "\n".join(steps)
        )
        if mode == "local":
            content += "\n\n下一步：确认无误后 mode=direct（有官方仓库权限）或 mode=fork + fork_remote=<你的fork>（社区贡献）"
        return ToolResult(True, content=content)
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"evolution_publish 内部异常：{type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "evolution_publish",
        "description": (
            "自进化：发布插件到官方市场仓库（drifox-plugins）。"
            "自动完成：同步 user 根插件 → 更新 marketplace.json → validate 校验 → "
            "git commit →（push=true 时）rebase 拉齐远端并推送。"
            "发布前自动对比版本，未 bump 会警告。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "要发布的插件名（user 根 ~/.drifox/plugins/<name>）",
                },
                "repo_path": {
                    "type": "string",
                    "description": "市场仓库路径（含 tools/generate_marketplace.py）；不填自动探测常见路径",
                },
                "mode": {
                    "type": "string",
                    "enum": ["local", "direct", "fork"],
                    "description": (
                        "发布模式：local=仅本地 commit（默认）；direct=直推 origin/main"
                        "（需官方仓库写权限）；fork=推到你的 fork 并生成 PR 链接（社区贡献标准流程）"
                    ),
                    "default": "local",
                },
                "fork_remote": {
                    "type": "string",
                    "description": "fork 模式必填：你 fork 的仓库地址（github.com/martin98-afk/drifox-plugins 右上角 Fork 后得到）",
                },
                "push": {
                    "type": "boolean",
                    "description": "向后兼容：true 等价 mode=direct，默认 false",
                    "default": False,
                },
                "commit_type": {
                    "type": "string",
                    "enum": list(_COMMIT_TYPES),
                    "description": "conventional commit 类型，默认 feat",
                },
                "message": {
                    "type": "string",
                    "description": "commit message；不填自动生成 <type>(<name>): 发布 vX.Y.Z",
                },
            },
            "required": ["plugin_name"],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "evolution_publish", _SCHEMA, impl=_impl,
        danger="dangerous", icon="evolution_publish", cn_name="发布插件",
        group="自进化", description="发布插件到市场仓库（同步+marketplace+校验+commit，push 可选）",
        metadata={"permission_arg": "plugin_name"},
    )
