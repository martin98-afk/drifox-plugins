# -*- coding: utf-8 -*-
"""gateway-feishu 适配器生命周期回归测试

背景（2026-08-20 连接泄漏 bug）：
- lark_oapi ws Client 无 stop()/close()/_running，start() 永久阻塞于
  run_until_complete(_select())，ping/receive 均为 while True，auto_reconnect
  默认无限重连
- 旧 disconnect() 靠 hasattr 探测 stop/close/_running 三分支全部落空 →
  连接/线程/loop 永生，每次 stop/热重载泄漏一条长连接 + "Event loop is
  closed" / "attached to a different loop" / 文件占用无法卸载

本测试绕过 connect() 的网络部分，直接布置"运行中"状态，验证 disconnect()
真正关闭：ws 线程退出、ws loop 停止、handler loop 停止、幂等可重入。
"""

import asyncio
import importlib.util
import sys
import threading
import time
import types
from enum import Enum
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugins" / "gateway-feishu"


# ── fake 主程序 app.gateway.base / app.gateway.config（feishu.py 的 import 依赖）──
def _install_fake_app_modules() -> None:
    if "app.gateway.base" in sys.modules:
        return

    app = types.ModuleType("app")
    gateway = types.ModuleType("app.gateway")

    base = types.ModuleType("app.gateway.base")

    class Platform(str, Enum):
        FEISHU = "feishu"

    class MessageType:  # noqa: N801
        TEXT = 1
        FILE = 2

    class PlatformConfig:
        def __init__(self, enabled: bool = True, extra: dict | None = None):
            self.enabled = enabled
            self.extra = extra or {}

    class SendResult:  # noqa: N801
        pass

    class MessageEvent:  # noqa: N801
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class BasePlatformAdapter:
        def __init__(self, config, platform):
            self.config = config
            self.platform = platform
            self.name = "test"
            self._running = False
            self._connected = False
            self._last_error = None

        @property
        def is_connected(self):
            return self._connected

        async def start(self) -> bool:
            if self._running:
                return True
            self._running = True
            self._connected = True
            return True

        async def stop(self) -> None:
            self._running = False
            await self.disconnect()
            self._connected = False

        async def connect(self) -> bool:
            return True

        async def disconnect(self) -> None:
            pass

    base.Platform = Platform
    base.MessageType = MessageType
    base.PlatformConfig = PlatformConfig
    base.SendResult = SendResult
    base.MessageEvent = MessageEvent
    base.BasePlatformAdapter = BasePlatformAdapter

    app.gateway = gateway
    gateway.base = base
    sys.modules.setdefault("app", app)
    sys.modules.setdefault("app.gateway", gateway)
    sys.modules["app.gateway.base"] = base


# ── 从文件路径加载 feishu.py（与 conftest 的 ip-switcher 模式一致）──
def _load_feishu_module():
    _install_fake_app_modules()
    name = "feishu_gateway_adapter_under_test"
    if name in sys.modules:
        return sys.modules[name]
    path = _PLUGIN_DIR / "gateways" / "feishu.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


feishu_gw = _load_feishu_module()


class FakeWSClient:
    """模拟 lark_oapi ws Client 的可观察行为面：start() 永久阻塞 + _disconnect 协程"""

    def __init__(self):
        self._auto_reconnect = True
        self._disconnected = False
        self.start_entered = threading.Event()

    def start(self) -> None:
        # 模拟 SDK：run_until_complete(_select()) 永久阻塞
        self.start_entered.set()

        async def _select():
            while True:
                await asyncio.sleep(3600)

        asyncio.get_event_loop().run_until_complete(_select())

    async def _disconnect(self) -> None:
        self._disconnected = True


def _wait_until(predicate, timeout: float = 15.0) -> bool:
    # 首次 import deps/lark_oapi（protobuf 链）可能耗时数秒，窗口需充足
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_disconnect_stops_ws_thread_and_loops():
    """disconnect() 必须真正停掉 ws 线程/loop/handler loop（回归：旧实现全泄漏）"""
    adapter = feishu_gw.FeishuAdapter(feishu_gw.PlatformConfig(extra={}))
    fake = FakeWSClient()
    adapter._ws_client = fake
    adapter._running = True
    adapter._connected = True
    adapter._start_handler_loop()
    adapter._feishu_thread = threading.Thread(
        target=adapter._run_feishu_client, daemon=True
    )
    adapter._feishu_thread.start()

    # 等 ws 线程进入运行（loop 已建并跑起来）
    assert _wait_until(
        lambda: adapter._ws_loop is not None and adapter._ws_loop.is_running()
    ), "ws loop 未启动"
    assert fake.start_entered.wait(3), "FakeWSClient.start 未执行"
    ws_thread = adapter._feishu_thread
    handler_loop = adapter._handler_loop
    handler_thread = adapter._handler_loop_thread

    asyncio.run(adapter.disconnect())

    # 断连协议：禁自动重连 + 真正调用了 _disconnect
    assert fake._auto_reconnect is False, "必须禁用 SDK 自动重连"
    assert fake._disconnected is True, "必须经 ws loop 真正关闭连接"
    # ws 线程退出 + 引用清空
    assert not ws_thread.is_alive(), "ws 线程必须退出（旧实现泄漏点）"
    assert adapter._ws_client is None
    assert adapter._ws_loop is None
    # handler loop 停止 + 线程退出 + 引用清空
    assert not handler_loop.is_running(), "handler loop 必须停止"
    assert not handler_thread.is_alive(), "handler 线程必须退出"
    assert adapter._handler_loop is None
    assert adapter._handler_loop_thread is None
    # 状态复位
    assert adapter._running is False and adapter._connected is False


def test_disconnect_is_idempotent():
    """disconnect 可重入（二次调用不抛异常、不残留）"""
    adapter = feishu_gw.FeishuAdapter(feishu_gw.PlatformConfig(extra={}))
    fake = FakeWSClient()
    adapter._ws_client = fake
    adapter._running = True
    adapter._connected = True
    adapter._start_handler_loop()
    adapter._feishu_thread = threading.Thread(
        target=adapter._run_feishu_client, daemon=True
    )
    adapter._feishu_thread.start()
    assert _wait_until(
        lambda: adapter._ws_loop is not None and adapter._ws_loop.is_running()
    )

    asyncio.run(adapter.disconnect())
    # 二次 disconnect：全空状态，静默通过
    asyncio.run(adapter.disconnect())
    assert adapter._feishu_thread is None


def test_connect_defensive_cleanup_when_thread_alive(monkeypatch):
    """connect() 重入防御：上一轮线程仍存活时先彻底断开再重连（防连接叠加）"""
    adapter = feishu_gw.FeishuAdapter(feishu_gw.PlatformConfig(extra={}))
    fake = FakeWSClient()
    adapter._ws_client = fake
    adapter._running = True
    adapter._connected = True
    adapter._start_handler_loop()
    stale_thread = threading.Thread(target=adapter._run_feishu_client, daemon=True)
    adapter._feishu_thread = stale_thread
    stale_thread.start()
    assert _wait_until(
        lambda: adapter._ws_loop is not None and adapter._ws_loop.is_running()
    )

    # 依赖检查置 False（直接替函数，避免 LARK_AVAILABLE 被 check 内部 import 回写），
    # 使 connect 在防御清理后走 early-return，不触网络
    monkeypatch.setattr(feishu_gw, "check_feishu_requirements", lambda: False)
    ok = asyncio.run(adapter.connect())
    assert ok is False
    # 关键断言：活线程已被 connect 开头的防御性 disconnect 清理
    assert not stale_thread.is_alive(), "connect 防御清理未生效（旧线程泄漏）"
    assert adapter._feishu_thread is None
