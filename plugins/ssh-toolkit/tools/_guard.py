# ssh-toolkit/tools/_guard.py
# -*- coding: utf-8 -*-
"""本地路径边界：SFTP 上传源 / 下载目标的准入判定。

宿主沙箱（app/tools/sandbox.py）只按「文件写入/读取」分组 + path/file_path
字段路由，本插件参数叫 local_path，一条都匹配不上 → 判定恒为 allow。等于
ssh_upload 可以把 ~/.ssh/id_rsa、.env、sessions.db 传到任意远端，ssh_download
可以把远端内容落到启动目录。此模块补上这层边界，全部在插件内完成。

三层规则（任一命中即拒）：
1. 硬黑名单目录/文件名：凭据、浏览器 profile、应用数据。
2. workdir 边界：local_path 必须落在 tool_ctx["workdir"] 内（或 allow_paths 显式补充）。
3. realpath 解析后再判，符号链接不能绕过。
"""
import os

# 目录级黑名单（realpath 归一后比较，含子目录）
_BLOCK_DIRS = (
    "~/.ssh",
    "~/.gnupg",
    "~/.aws",
    "~/.azure",
    "~/.kube",
    "~/.docker",
    "~/.drifox",
    "~/.config",
    "~/appdata/roaming/microsoft/credentials",
    "~/appdata/roaming/microsoft/protect",
    "~/appdata/locallow/google/chrome/user data",
    "~/appdata/roaming/mozilla/firefox/profiles",
    "~/appdata/local/google/chrome/user data",
    "~/library/application support/google/chrome",
    "~/library/keychains",
)

# 文件名模式（小写比较，支持 * 通配）
_BLOCK_NAMES = (
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "*.kdbx",
    ".env",
    ".env.*",
    ".netrc",
    ".pgpass",
    "credentials",
    "sessions.db",
)

# 下载落点黑名单：这些位置写入即等价于本地代码执行
_BLOCK_TARGET_DIRS = (
    "~/appdata/roaming/microsoft/windows/start menu/programs/startup",
    "~/appdata/roaming/microsoft/windows/start menu/programs/startup/approved",
    "~/.config/autostart",
)


def _norm(p):
    """展开变量/用户目录 + realpath（解符号链接，防绕过）"""
    return os.path.realpath(os.path.expanduser(os.path.expandvars(str(p))))


def _under(path, root):
    path = path.rstrip("/\\").lower()
    root = root.rstrip("/\\").lower()
    return path == root or path.startswith(root + os.sep) or path.startswith(root + "/")


def _name_blocked(name):
    name = (name or "").lower()
    for pattern in _BLOCK_NAMES:
        if "*" in pattern:
            head, tail = pattern.split("*", 1)
            if name.startswith(head) and name.endswith(tail):
                return True
        elif name == pattern:
            return True
    return False


def _dir_blocked(norm_path):
    for item in _BLOCK_DIRS:
        if _under(norm_path, _norm(item)):
            return item
    return None


def _target_dir_blocked(norm_path):
    parent = os.path.dirname(norm_path)
    for item in _BLOCK_TARGET_DIRS:
        root = _norm(item)
        if _under(parent, root):
            return item
    return None


def _allowed_roots(tool_ctx, allow_paths=None):
    """允许的本地根目录集合：workdir + allow_paths（均 realpath 归一）

    allow_paths 来自工具调用参数（用户/模型显式声明的额外根目录），
    不是 tool_ctx 的字段 —— 宿主 ctx 由主程序构造，插件无从写入。
    """
    roots = []
    ctx = tool_ctx if isinstance(tool_ctx, dict) else {}
    wd = ctx.get("workdir")
    if wd:
        roots.append(_norm(wd))
    items = allow_paths or []
    if isinstance(items, str):
        items = [items]
    for item in items:
        if item:
            roots.append(_norm(item))
    if not roots:
        # 未设置工作目录时回退用户主目录（仍叠加黑名单与自启动目录拦截）
        roots.append(_norm("~"))
    return roots


def check_local_read(path, tool_ctx, allow_paths=None):
    """上传源文件准入。返回 (ok, reason)。"""
    if not path:
        return False, "缺少 local_path"
    norm = _norm(path)
    hit = _dir_blocked(norm)
    if hit:
        return False, f"拒绝访问受保护目录（{hit}）：{path}"
    if _name_blocked(os.path.basename(norm)):
        return False, f"拒绝外传凭据类文件：{path}（如确需上传，请复制到工作目录后改用新路径）"
    roots = _allowed_roots(tool_ctx, allow_paths)
    if not any(_under(norm, r) for r in roots):
        return False, (
            f"local_path 超出允许范围：{path}。允许的根目录：{', '.join(roots)}；"
            "确需越过边界时，在工作目录内复制副本后再上传"
        )
    return True, ""


def check_local_write(path, tool_ctx, allow_paths=None):
    """下载目标准入。返回 (ok, reason)。"""
    if not path:
        return False, "缺少 local_path"
    norm = _norm(path)
    hit = _dir_blocked(norm)
    if hit:
        return False, f"拒绝写入受保护目录（{hit}）：{path}"
    if _name_blocked(os.path.basename(norm)):
        return False, f"拒绝覆盖凭据类文件：{path}"
    hit = _target_dir_blocked(norm)
    if hit:
        return False, f"拒绝写入自启动/登录项目录（{hit}）：{path}"
    roots = _allowed_roots(tool_ctx, allow_paths)
    if not any(_under(norm, r) for r in roots):
        return False, (
            f"local_path 超出允许范围：{path}。允许的根目录：{', '.join(roots)}；"
            "确需越过边界时，先下载到工作目录再由用户手动移动"
        )
    return True, ""


def check_bind_addr(addr, allow_public=False):
    """端口转发绑定地址准入：默认只允许回环，公网绑定需显式开启。"""
    raw = (addr or "").strip()
    if raw in ("", "127.0.0.1", "::1", "localhost"):
        return True, ""
    if allow_public:
        return True, ""
    return False, (
        f"bind_addr={raw} 会把端口暴露给其它主机。默认只允许回环地址；"
        "确需对外暴露请显式传 allow_public=true（该操作会在审批卡中体现）"
    )
