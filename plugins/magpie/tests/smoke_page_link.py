# -*- coding: utf-8 -*-
"""magpie 页识别按钮的接线验证（不建 Qt 窗口，只验方法行为）。

跑法（项目 venv）：
    python plugins/magpie/tests/smoke_page_link.py

覆盖：
- _ensure_agent_link 走 agent_link.ensure_registered，失败不抛
- _sync_agent_link 两级状态文案（已生效 / 已登记未装 magpie / 已登记未加载）
- _ask_ai_to_install 先登记再写提示词，且提示词带上「已登记」说明
- 状态条文案带上登记态
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 宿主依赖桩：loguru 只记日志，PyQt5 只用到常量与信号
_notifies = []
_logs = []


class _Logger:
    def debug(self, m):
        _logs.append(("debug", m))

    def info(self, m):
        _logs.append(("info", m))

    def warning(self, m):
        _logs.append(("warning", m))

    def exception(self, m):
        _logs.append(("exception", m))


sys.modules.setdefault("loguru", types.SimpleNamespace(logger=_Logger()))


class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self, *a):
        for fn in self._slots:
            fn(*a)


qtcore = types.ModuleType("PyQt5.QtCore")
qtcore.QUrl = lambda *a, **k: object()
qtcore.Qt = types.SimpleNamespace(
    AlignCenter=1, RichText=2, TextSelectableByMouse=4, WaitCursor=5
)
qtcore.pyqtSignal = lambda *a, **k: _Signal()
qtcore.QTimer = types.SimpleNamespace(singleShot=lambda *a, **k: None)
pyqt5 = types.ModuleType("PyQt5")
pyqt5.QtCore = qtcore
sys.modules.setdefault("PyQt5", pyqt5)
sys.modules.setdefault("PyQt5.QtCore", qtcore)

qtwidgets = types.ModuleType("PyQt5.QtWidgets")


class _W:
    def __init__(self, *a, **k):
        self._enabled = True

    def setVisible(self, *a):
        pass

    def setEnabled(self, v=True):
        self._enabled = bool(v)

    def isEnabled(self):
        return self._enabled

    def setText(self, *a):
        pass

    def setAlignment(self, *a):
        pass

    def setWordWrap(self, *a):
        pass

    def setTextFormat(self, *a):
        pass

    def setTextInteractionFlags(self, *a):
        pass

    def setContentsMargins(self, *a):
        pass

    def setSpacing(self, *a):
        pass

    def layout(self):
        return None

    def addWidget(self, *a, **k):
        pass

    def addStretch(self, *a):
        pass

    def addLayout(self, *a):
        pass


for name in ("QHBoxLayout", "QVBoxLayout", "QLabel", "QWidget"):
    setattr(qtwidgets, name, type(name, (_W,), {}))


class _App:
    @staticmethod
    def instance():
        return _App()

    @staticmethod
    def setOverrideCursor(*a):
        pass

    @staticmethod
    def restoreOverrideCursor(*a):
        pass


qtwidgets.QApplication = _App
sys.modules.setdefault("PyQt5.QtWidgets", qtwidgets)

qfluent = types.ModuleType("qfluentwidgets")


class _Btn(_W):
    def __init__(self, *a, **k):
        self._clicked = _Signal()
        self.setText = lambda *a: None

    @property
    def clicked(self):
        return self._clicked


qfluent.PushButton = _Btn
qfluent.isDarkTheme = lambda: False
sys.modules.setdefault("qfluentwidgets", qfluent)

# 包形态加载（页面用相对 import 取 agent_link）
pkg = types.ModuleType("magpie_ui")
pkg.__path__ = [str(ROOT / "ui")]
sys.modules["magpie_ui"] = pkg
for mod_name in ("magpie_ui.agent_link", "magpie_ui.magpie_page"):
    sys.modules.pop(mod_name, None)

spec = importlib.util.spec_from_file_location("magpie_ui.agent_link", ROOT / "ui" / "agent_link.py")
agent_link = importlib.util.module_from_spec(spec)
sys.modules["magpie_ui.agent_link"] = agent_link
spec.loader.exec_module(agent_link)

spec = importlib.util.spec_from_file_location("magpie_ui.magpie_page", ROOT / "ui" / "magpie_page.py")
page_mod = importlib.util.module_from_spec(spec)
sys.modules["magpie_ui.magpie_page"] = page_mod
spec.loader.exec_module(page_mod)

tmp = Path(tempfile.mkdtemp(prefix="magpie-page-"))
old_xdg = os.environ.get("XDG_CONFIG_HOME")
os.environ["XDG_CONFIG_HOME"] = str(tmp)

try:
    # 桩掉能力与通知（_notify 是实例方法，得打到类上）
    page_mod._caps = lambda cap_id: None
    page_mod.MagpieWebPage._notify = lambda self, t, c: _notifies.append((t, c))
    page_mod._magpie_installed = lambda: False

    page = page_mod.MagpieWebPage()
    page._status = _W()
    page._guide = _W()
    page._view = None
    page._link_btn = _Btn()

    def _run_sync(p):
        """同步测异步探测：后台线程里 emit 会直接回调（_Signal 是同步桩）。"""
        p._sync_agent_link()
        for _ in range(200):
            if not p._link_btn.isEnabled():
                time.sleep(0.01)
                continue
            break
        # 桩信号是同步 emit，_on_link_probed 已在工作线程里跑完
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if _notifies:
                return
            time.sleep(0.01)

    # 1) 登记成功
    assert page._ensure_agent_link() is True
    assert agent_link.is_registered() is True

    # 2) 幂等
    assert page._ensure_agent_link() is True

    # 3) 未装 magpie → 两级状态文案走「已登记，magpie 未安装」
    #    先桩掉探测，否则真实环境里 magpie 真认得它，测不到这个分支
    agent_link.probe_agent_active = lambda timeout=15.0: (False, "magpie 未安装")
    _notifies.clear()
    _run_sync(page)
    assert _notifies and _notifies[-1][0] == "已登记，magpie 未安装", _notifies

    # 4) 已装但 magpie 不认 → 「已登记但 magpie 未加载」
    page_mod._magpie_installed = lambda: True
    agent_link.probe_agent_active = lambda timeout=15.0: (False, "unknown agent")
    _notifies.clear()
    _run_sync(page)
    assert _notifies[-1][0] == "已登记但 magpie 未加载", _notifies
    assert "unknown agent" in _notifies[-1][1]

    # 5) 已生效
    agent_link.probe_agent_active = lambda timeout=15.0: (True, "DriFox  provider —  ~/.drifox/x.json")
    _notifies.clear()
    _run_sync(page)
    assert _notifies[-1][0] == "magpie 已认得 DriFox", _notifies

    # 6) 写提示词前会先登记：清掉注册表，装成 input.write 可用
    reg = agent_link.registry_path()
    reg.unlink()
    assert agent_link.is_registered() is False
    written = {}
    page_mod._caps = lambda cap_id: (
        (lambda text, append=True, focus=False: written.update(text=text)) if cap_id == "input.write" else None
    )
    _notifies.clear()
    page._ask_ai_to_install()
    assert agent_link.is_registered() is True, "写提示词前必须先登记"
    assert "已在" in written["text"] or "登记" in written["text"], written["text"]
    assert "安装 magpie" in written["text"]

    # 7) 状态条文案带登记态
    assert "已登记" in page._connected_status(3430)
    reg.unlink()
    assert "未登记" in page._connected_status(3430)

    print("page link ok: 登记/幂等/三级状态/提示词前登记/状态条文案")
finally:
    if old_xdg is None:
        os.environ.pop("XDG_CONFIG_HOME", None)
    else:
        os.environ["XDG_CONFIG_HOME"] = old_xdg
    shutil.rmtree(tmp, ignore_errors=True)
