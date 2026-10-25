# -*- coding: utf-8 -*-
"""加载期登记测试：装完插件不点任何按钮，打开 magpie 也该认得 DriFox。

跑法（项目 venv）：
    python plugins/magpie/tests/smoke_startup_link.py

覆盖：
- 已装 magpie（PATH 有可执行 or 配置目录存在）→ register_ui 后自动登记
- 没装 magpie（两者都不成立）→ **不**创建 ~/.config/magpie，不凭空造目录
- 已登记 → 不重复写（幂等）
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class _Logger:
    def debug(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def exception(self, *a, **k):
        pass


sys.modules.setdefault("loguru", types.SimpleNamespace(logger=_Logger()))


class _Reg:
    """只记录注册调用的最小 registry 桩。"""

    def __init__(self):
        self.calls = []

    def register_floating_card(self, **kw):
        self.calls.append(("card", kw))

    def register_sidebar_item(self, **kw):
        self.calls.append(("sidebar", kw))

    def _resolve_global_host(self):
        return None

    def toggle_floating_card(self, cid):
        pass


tmp = Path(tempfile.mkdtemp(prefix="magpie-startup-"))
old_xdg = os.environ.get("XDG_CONFIG_HOME")
os.environ["XDG_CONFIG_HOME"] = str(tmp)

# PATH 上有没有真 magpie 会影响结果：agent_link 用模块级 shutil.which，
# 所以直接把它模块对象里的 shutil.which 换掉（在加载后做）。
_magpie_on_path = {"v": False}
_real_which = shutil.which


def _fake_which(name, *a, **k):
    if name == "magpie":
        return "C:/fake/magpie.exe" if _magpie_on_path["v"] else None
    return _real_which(name, *a, **k)


def _load_ui():
    """以包形态重新加载 ui 包（模拟热重载），返回 (ui 模块, agent_link 模块)。

    ui/__init__ 内部 `from . import agent_link` 取的是 sys.modules 里那份，
    所以先把我们的实例塞进去，保证断言操作的是同一个对象。
    """
    for k in [k for k in sys.modules if k == "magpie_ui" or k.startswith("magpie_ui.")]:
        del sys.modules[k]

    pkg = types.ModuleType("magpie_ui")
    pkg.__path__ = [str(ROOT / "ui")]
    sys.modules["magpie_ui"] = pkg

    al_spec = importlib.util.spec_from_file_location("magpie_ui.agent_link", ROOT / "ui" / "agent_link.py")
    agent_link = importlib.util.module_from_spec(al_spec)
    sys.modules["magpie_ui.agent_link"] = agent_link
    al_spec.loader.exec_module(agent_link)
    agent_link.shutil.which = _fake_which  # 只影响本模块，不污染全局

    ui_spec = importlib.util.spec_from_file_location("magpie_ui.__init__", ROOT / "ui" / "__init__.py")
    ui = importlib.util.module_from_spec(ui_spec)
    sys.modules["magpie_ui.__init__"] = ui
    ui_spec.loader.exec_module(ui)
    return ui, agent_link


def _wait_registered(agent_link, timeout=5.0):
    """加载期登记在后台线程，等它落地。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if agent_link.is_registered():
            return True
        time.sleep(0.02)
    return False


try:
    cfg_dir = tmp / "magpie"

    # ── 场景 1：没装 magpie，目录不存在 → 不该凭空造目录 ──
    assert not cfg_dir.exists(), cfg_dir
    _magpie_on_path["v"] = False
    ui, agent_link = _load_ui()
    assert agent_link.magpie_in_use() is False, "无 magpie 时应判定为未使用"
    ui.register_ui(_Reg())
    time.sleep(0.4)  # 给后台线程启动的机会
    assert not cfg_dir.exists(), f"未装 magpie 时不应创建配置目录：{cfg_dir}"

    # ── 场景 2：配置目录存在（用户开过 magpie）→ 自动登记 ──
    cfg_dir.mkdir(parents=True, exist_ok=True)
    assert agent_link.magpie_in_use() is True
    assert agent_link.is_registered() is False

    ui, agent_link = _load_ui()
    ui.register_ui(_Reg())
    assert _wait_registered(agent_link), "加载后应自动登记"
    reg = json.loads((cfg_dir / "plugins.json").read_text(encoding="utf-8"))
    assert len(reg["plugins"]) == 1, reg
    assert Path(reg["plugins"][0]["spec"]) == agent_link.agent_plugin_dir()

    # ── 场景 3：再加载一次（热重载）→ 不重复写 ──
    ui, agent_link = _load_ui()
    ui.register_ui(_Reg())
    time.sleep(0.4)
    reg2 = json.loads((cfg_dir / "plugins.json").read_text(encoding="utf-8"))
    assert len(reg2["plugins"]) == 1, f"热重载不应重复登记：{reg2}"

    # ── 场景 4：PATH 上有 magpie 但配置目录不存在 → 也算用过，该登记 ──
    shutil.rmtree(cfg_dir, ignore_errors=True)
    _magpie_on_path["v"] = True
    ui, agent_link = _load_ui()
    assert agent_link.magpie_in_use() is True, "PATH 有 magpie 应判定为已使用"
    ui.register_ui(_Reg())
    assert _wait_registered(agent_link), "PATH 有 magpie 时加载后应自动登记"

    print("startup link ok: 无 magpie 不造目录 / 有 magpie 自动登记 / 热重载幂等 / PATH 判据")
finally:
    if old_xdg is None:
        os.environ.pop("XDG_CONFIG_HOME", None)
    else:
        os.environ["XDG_CONFIG_HOME"] = old_xdg
    shutil.rmtree(tmp, ignore_errors=True)
