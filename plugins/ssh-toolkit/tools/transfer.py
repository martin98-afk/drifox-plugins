# ssh-toolkit/tools/transfer.py
# -*- coding: utf-8 -*-
"""SFTP 文件传输与目录浏览（upload/download/list_dir）。"""
import os
import sys
from pathlib import Path

# PluginToolLoader 用 importlib 加载本模块，注入 tools/ 目录到 sys.path 以便绝对导入
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from app.tools.result import ToolResult  # noqa: E402

import _pool as pool  # noqa: E402


def _client(ref):
    client, err = pool.ensure_client(ref) if ref else (None, None)
    if client is None:
        raise RuntimeError(err or f"未找到活跃连接：{ref}（先 ssh_connect）")
    return client


def _norm_remote(path, home):
    if not path:
        return "."
    if path.startswith("~"):
        path = os.path.join(home, path[1:].lstrip("/"))
    elif not os.path.isabs(path):
        path = os.path.join(home, path)
    return path


def _home(client):
    return client.exec_command("echo $HOME")[1].read().decode("utf-8", "replace").strip() or "~"


def _upload_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name")
    local = kwargs.get("local_path")
    remote = kwargs.get("remote_path")
    text_mode = bool(kwargs.get("text_mode", False))
    executable = bool(kwargs.get("executable", False))
    if not local or not remote:
        return ToolResult(False, error="需要 local_path 与 remote_path")
    try:
        client = _client(ref)
        remote = _norm_remote(remote, _home(client))
        sftp = client.open_sftp()
        if text_mode:
            with open(local, "rb") as f:
                data = f.read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            with sftp.open(remote, "wb") as rf:
                rf.write(data)
            extra = f"，text_mode 已 CRLF→LF（{len(data)}B）"
        else:
            sftp.put(local, remote)
            extra = ""
        if executable:
            sftp.chmod(remote, 0o755)
            extra += "，已 chmod 755"
        sftp.close()
    except Exception as e:
        return ToolResult(False, error=f"上传失败：{e}")
    return ToolResult(True, content=f"已上传 {local} → {remote} @ {ref}{extra}")


def _download_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name")
    remote = kwargs.get("remote_path")
    local = kwargs.get("local_path")
    if not local or not remote:
        return ToolResult(False, error="需要 remote_path 与 local_path")
    try:
        client = _client(ref)
        remote = _norm_remote(remote, _home(client))
        os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
        sftp = client.open_sftp()
        sftp.get(remote, local)
        sftp.close()
    except Exception as e:
        return ToolResult(False, error=f"下载失败：{e}")
    return ToolResult(True, content=f"已下载 {remote} → {local} @ {ref}")


def _list_dir_impl(tool_ctx, **kwargs):
    ref = kwargs.get("handle") or kwargs.get("name")
    remote = kwargs.get("remote_path", ".")
    try:
        client = _client(ref)
        remote = _norm_remote(remote, _home(client))
        sftp = client.open_sftp()
        items = sftp.listdir_attr(remote)
        lines = []
        for a in items:
            kind = "d" if (a.st_mode & 0o170000) == 0o040000 else "f"
            lines.append(f"{kind} {a.st_size:>10} {a.st_mtime:.0f}  {a.filename}")
        sftp.close()
    except Exception as e:
        return ToolResult(False, error=f"浏览失败：{e}")
    return ToolResult(True, content="\n".join(lines) or "（空目录）")


def register(registry):
    registry.register(
        "ssh_upload",
        {"type": "function", "function": {
            "name": "ssh_upload",
            "description": "通过 SFTP 上传本地文件到远程主机",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "连接 handle 或连接名"},
                "name": {"type": "string", "description": "连接名"},
                "local_path": {"type": "string", "description": "本地文件路径"},
                "remote_path": {"type": "string", "description": "远程目标路径"},
                "text_mode": {"type": "boolean", "description": "文本模式：上传前自动将 CRLF 转为 LF（默认 false，向后兼容）"},
                "executable": {"type": "boolean", "description": "是否上传后自动 chmod 0o755（默认 false）"},
            }, "required": ["local_path", "remote_path"]},
        }},
        impl=_upload_impl, danger="dangerous", icon="ssh_upload", cn_name="SSH 上传文件", group="SSH 远程",
        description="SFTP 上传文件",
    )
    registry.register(
        "ssh_download",
        {"type": "function", "function": {
            "name": "ssh_download",
            "description": "通过 SFTP 从远程主机下载文件到本地",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "连接 handle 或连接名"},
                "name": {"type": "string", "description": "连接名"},
                "remote_path": {"type": "string", "description": "远程文件路径"},
                "local_path": {"type": "string", "description": "本地目标路径"},
            }, "required": ["remote_path", "local_path"]},
        }},
        impl=_download_impl, danger="dangerous", icon="ssh_download", cn_name="SSH 下载文件", group="SSH 远程",
        description="SFTP 下载文件",
    )
    registry.register(
        "ssh_list_dir",
        {"type": "function", "function": {
            "name": "ssh_list_dir",
            "description": "浏览远程目录文件列表（权限/大小/mtime）",
            "parameters": {"type": "object", "properties": {
                "handle": {"type": "string", "description": "连接 handle 或连接名"},
                "name": {"type": "string", "description": "连接名"},
                "remote_path": {"type": "string", "description": "远程目录路径，默认当前目录"},
                "recursive": {"type": "boolean", "description": "是否递归"},
            }, "required": []},
        }},
        impl=_list_dir_impl, danger="safe", icon="ssh", cn_name="SSH 浏览目录", group="SSH 远程",
        description="浏览远程目录",
    )
