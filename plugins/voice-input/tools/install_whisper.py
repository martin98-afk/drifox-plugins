# -*- coding: utf-8 -*-
"""一键把 faster-whisper 及其编译依赖安装进插件自带 deps/ 目录。

为什么需要：voice-input 的高精度识别后端 faster-whisper 依赖多个编译轮子
（ctranslate2 / av / tokenizers 等），不能像纯 Python 包那样直接随插件分发。
按 desktop-automation 的惯例，用「插件自带 deps/ + sys.path 注入」实现自包含。

用法（必须用 DriFox 宿主同一个 Python 解释器执行）：

    # Windows（找到 DriFox 内置 Python 后）：
    <DriFox-python> plugins\\voice-input\\tools\\install_whisper.py

    # 或在插件目录内直接：
    python tools/install_whisper.py

脚本行为：
1. 解析插件根目录，目标目录 = <插件根>/deps；
2. 用当前解释器执行 pip install --target deps faster-whisper
   （pip 会按当前解释器版本自动挑选匹配的编译轮子，如 cp314/abi3）；
3. 子进程隔离验证：把 deps 加入 PYTHONPATH 后 import faster_whisper 确认可用；
4. 打印体积与卸载方式。

卸载：删除 deps/ 目录即可（插件自动回退 SAPI5）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# 依赖名即 pip 包名；版本留空表示取当前最新
_PACKAGES = ["faster-whisper"]


def plugin_root() -> Path:
    """tools/ 的上一级即插件根目录。"""
    return Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> int:
    print(">>", " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    root = plugin_root()
    deps = root / "deps"
    python = sys.executable

    print(f"目标 Python : {python}")
    print(f"插件根目录  : {root}")
    print(f"依赖安装到  : {deps}\n")

    if not deps.is_dir():
        deps.mkdir(parents=True)
        print(f"已创建 {deps}\n")

    # 1) pip 安装到 deps/（--target 语义：按当前解释器解析平台/ABI 轮子）
    cmd = [python, "-m", "pip", "install", "--target", str(deps), "--upgrade", *_PACKAGES]
    rc = _run(cmd)
    if rc != 0:
        print(
            "\n[pip 安装失败] 请确认：\n"
            "  1) 当前解释器确实带 pip（缺失时先 `python -m ensurepip`）；\n"
            "  2) 网络可达 PyPI（国内可加 -i https://pypi.tuna.tsinghua.edu.cn/simple）。\n",
            file=sys.stderr,
        )
        return rc

    # 2) 隔离验证：仅靠 deps/ 能否 import faster_whisper（排除宿主环境干扰）
    env = dict(os.environ)
    env["PYTHONPATH"] = str(deps) + os.pathsep + env.get("PYTHONPATH", "")
    check = subprocess.run(
        [python, "-c", "import faster_whisper; print('faster_whisper', faster_whisper.__version__)"],
        capture_output=True,
        text=True,
        env=env,
    )
    if check.returncode != 0:
        print(
            "\n[验证失败] deps/ 中 import faster_whisper 出错：\n"
            f"{check.stderr.strip()}\n"
            "提示：deps/ 的编译轮子必须与宿主 Python 版本匹配，请务必用宿主解释器重跑本脚本。",
            file=sys.stderr,
        )
        return check.returncode

    size_mb = sum(
        p.stat().st_size
        for p in deps.rglob("*")
        if p.is_file() and ".libs" not in p.parts
    ) / (1024 * 1024)
    print(
        f"\n[完成] faster_whisper {check.stdout.strip()} 已装进 deps/（约 {size_mb:.0f}MB）。\n"
        "首次点麦克风识别时会自动下载中文模型（默认 small ≈460MB，可设环境变量\n"
        "DRIFOX_VOICE_MODEL=tiny/base/medium 调整档位），之后即走 Whisper 高精度识别；\n"
        "未安装时插件自动回退 Windows 系统识别，不影响使用。\n"
        f"\n卸载：删除 {deps} 目录即可。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
