# -*- coding: utf-8 -*-
"""把 DriFox 登记进 magpie 的插件表（agent 条目），让 magpie 认得 DriFox。

magpie 的 agent 插件跑在它自带的 moejs 引擎里，**不需要 Bun**；只有 OpenCode
风格的 provider 插件才需要。所以这里直接写 magpie 的注册表文件
（``<config>/magpie/plugins.json``），不走 ``magpie plugin add``——后者在无 Bun
的环境会去 GitHub 下载 Bun 并长时间卡住（实测 180s 无返回），是不可接受的启动
路径。

注册表形态（实测 magpie v0.1.1418）：

    {"plugins": [{"spec": "<插件目录绝对路径>"}, ...]}

本地路径是**原地引用**，不拷贝：插件目录不能删、不能改名，否则 agent 行消失。

登记与生效是两件事：
- 已登记 = plugins.json 里有这条 spec
- 已生效 = ``magpie <agent-id>`` 退出码 0（magpie 每次都现读注册表，所以写完
  立即生效，不需要重启；这点与「运行中的网关进程是否 reload」无关，因为 CLI
  是独立进程）
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple

from loguru import logger

PLUGIN = "magpie"
# 与 agent_plugin/drifox.agent.js 里的 agent.id 必须一致
AGENT_ID = "drifox"
AGENT_DIR_NAME = "agent_plugin"


def agent_plugin_dir() -> Path:
    """agent 插件包的绝对路径（随 DriFox 插件一起分发）。"""
    return Path(__file__).resolve().parent.parent / AGENT_DIR_NAME


def magpie_config_dir() -> Path:
    """magpie 的配置目录。

    magpie 一律用 ``$XDG_CONFIG_HOME/magpie``，未设时落 ``~/.config/magpie``
    （Windows 上同样如此，实测 ``C:\\Users\\<user>\\.config\\magpie``）。
    """
    xdg = str(os.environ.get("XDG_CONFIG_HOME") or "").strip()
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "magpie"


def registry_path() -> Path:
    return magpie_config_dir() / "plugins.json"


def _read_registry(path: Path) -> list:
    """读现有注册表条目；文件不存在/损坏都当空表（损坏不覆盖，交由写入方决定）。"""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — 损坏时不猜，抛给调用方提示
        raise RuntimeError(f"magpie 插件注册表读取失败（{path}）：{e}") from e
    items = data.get("plugins") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def _same_spec(entry, target: str) -> bool:
    """判断已有条目是否指向目标目录（大小写与分隔符不敏感，Windows 友好）。"""
    spec = entry.get("spec") if isinstance(entry, dict) else entry
    if not isinstance(spec, str) or not spec.strip():
        return False
    try:
        return Path(spec).resolve() == Path(target).resolve()
    except Exception:
        return os.path.normcase(spec.strip()) == os.path.normcase(target)


def is_registered() -> bool:
    """插件目录是否已在 magpie 的注册表里（不代表已生效）。"""
    target = str(agent_plugin_dir())
    try:
        return any(_same_spec(e, target) for e in _read_registry(registry_path()))
    except Exception:
        return False


def magpie_in_use() -> bool:
    """用户是否用过 magpie（决定加载期是否值得静默登记）。

    判据取最保守的一组「用户确实装了/开过 magpie」的证据，任一成立即可：

    - PATH 上有 ``magpie`` 可执行文件
    - magpie 的配置目录已存在（``~/.config/magpie``）

    刻意不把「注册表文件存在」当唯一判据：全新机器上两者都不成立时，
    加载期就不该凭空造 ``~/.config/magpie`` 目录。
    """
    if shutil.which("magpie"):
        return True
    return magpie_config_dir().is_dir()


def ensure_registered() -> Tuple[str, str]:
    """幂等登记；返回 (状态, 说明)。状态 ∈ already / registered / error。

    只追加一条 spec，保留用户已有的其它插件条目与本条目的其它字段。
    """
    target = str(agent_plugin_dir())
    if not agent_plugin_dir().is_dir():
        return "error", f"agent 插件包缺失：{target}"

    path = registry_path()
    try:
        entries = _read_registry(path)
    except Exception as e:  # noqa: BLE001
        return "error", str(e)

    if any(_same_spec(e, target) for e in entries):
        return "already", target

    entries.append({"spec": target})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 先写临时文件再替换：magpie 可能同时在读写这个文件，避免半截 JSON
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"plugins": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001
        return "error", f"写入 magpie 插件注册表失败（{path}）：{e}"

    logger.info(f"[magpie] 已把 DriFox agent 条目登记进 {path}")
    return "registered", target


def probe_agent_active(timeout: float = 15.0) -> Tuple[bool, str]:
    """``magpie <agent-id>`` 退出码 0 = magpie 确实认得这个 agent。

    会现读注册表（CLI 是独立进程），成功输出形如
    ``DriFox  provider —  ~\\.drifox\\plugin_data\\magpie\\agent-link.json``。
    这是「已登记」与「已生效」的唯一判据：文件写对了但 magpie 加载失败时，
    这条命令会返回非 0。
    """
    exe = "magpie.exe" if sys.platform == "win32" else "magpie"
    exe = "magpie.exe" if sys.platform == "win32" else "magpie"
    found = shutil.which("magpie") or exe
    try:
        proc = subprocess.run(
            [found, AGENT_ID],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
        )
    except FileNotFoundError:
        return False, "PATH 上没有 magpie 可执行文件"
    except subprocess.TimeoutExpired:
        return False, f"magpie {AGENT_ID} 超时（{timeout:.0f}s）"
    except Exception as e:  # noqa: BLE001
        return False, str(e)

    if proc.returncode == 0:
        line = (proc.stdout or "").strip().splitlines()
        return True, line[0].strip() if line else f"magpie 已认得 {AGENT_ID}"
    msg = (proc.stdout or "").strip() or (proc.stderr or "").strip() or f"退出码 {proc.returncode}"
    return False, msg
