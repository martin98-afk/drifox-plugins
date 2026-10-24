# -*- coding: utf-8 -*-
"""gateway-feishu 宿主环境自愈三件套测试：CA 兜底 / 日志桥接 / 被动断线重连。

背景（2026-10-16 实机定位）：
1. **CA 兜底**：DriFox 打包环境（PyInstaller）下 ssl 默认 CA 路径解析失效，
   飞书 WS（wss://）在 TLS 握手阶段即失败，报
   ``[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate chain``，
   长连接从未建立、消息静默丢失。且 ``connect()`` 的 ``_connected = True`` 是
   无条件置位（不校验真实结果），日志显示「Connected successfully」是假信号 ——
   进程内实际零外部 TCP 连接。修复走分层兜底：truststore（系统信任库，
   可解企业代理自签 CA）→ certifi cacert.pem（写 SSL_CERT_FILE 全局生效）。
2. **日志桥接**：插件原用 ``logging.getLogger(__name__)``，而宿主日志系统只给
   loguru 配 sink（无 InterceptHandler）→ ``[Feishu]``/``[Lark]`` 输出一条都不
   落盘，连接失败原因不可见，排查只能盲猜（当时误判两轮）。桥接把 lark SDK
   的 ``logging.getLogger("Lark")`` 转发进 loguru。
3. **重连补偿**：lark SDK 的 auto_reconnect 只覆盖自身驱动协程内的重连窗口；
   驱动协程一旦退出 start() 即返回、ws 线程结束、loop 关闭，而 ``_connected``
   仍为 True 无人复位 → 宿主停在「假连接」。补退避重连（上限
   ``_max_reconnect_attempts``）作为双保险。

测试策略：复用 lifecycle 测试的 fake 主程序模块机制，让插件脱离 DriFox 独立跑。
模块级副作用（CA 探测/日志桥接）通过 reload 模块或直接调函数断言。
"""
import importlib.util
import logging
import os
import ssl
import sys
import types
from enum import Enum
from pathlib import Path

import pytest

_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugins" / "gateway-feishu"


# ── fake 主程序模块（feishu.py 的 import 依赖，与 lifecycle 测试同源）──
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


def _load_module(fresh: bool = False):
    """从文件路径加载 feishu.py（fresh=True 时强制重新执行模块级代码）。"""
    _install_fake_app_modules()
    name = "feishu_selfheal_under_test"
    if not fresh and name in sys.modules:
        return sys.modules[name]
    path = _PLUGIN_DIR / "gateways" / "feishu.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ══════════════════════════════════════════════════════════════
# 1. CA 兜底（_ensure_ca_bundle）
# ══════════════════════════════════════════════════════════════
class _EmptyCtx:
    """模拟打包环境：context 加载不出任何 CA。"""

    def get_ca_certs(self, binary_form=False):
        return []


@pytest.fixture
def clean_env(monkeypatch):
    """隔离 SSL_CERT_FILE 污染。

    关键：被测代码直接写 ``os.environ``（不走 monkeypatch），pytest 不会自动
    回滚。故此处手动快照/恢复，否则用例间互相污染（实测表现为后续用例看到
    前一个用例写入的 certifi 路径）。
    """
    saved = os.environ.pop("SSL_CERT_FILE", None)
    m = _load_module()
    monkeypatch.setattr(m, "_TRUSTSTORE_AVAILABLE", False)
    yield m
    os.environ.pop("SSL_CERT_FILE", None)
    if saved is not None:
        os.environ["SSL_CERT_FILE"] = saved


def test_ca_explicit_env_respected(clean_env, monkeypatch):
    """已有显式 SSL_CERT_FILE → 尊重之，不覆盖。"""
    monkeypatch.setenv("SSL_CERT_FILE", "/custom/ca.pem")
    clean_env._ensure_ca_bundle()
    assert os.environ["SSL_CERT_FILE"] == "/custom/ca.pem"


def test_ca_default_ok_no_intervention(clean_env, monkeypatch):
    """默认 CA 可用（开发机）→ 不写环境变量。"""
    ctx = ssl.create_default_context()
    if not ctx.get_ca_certs():
        pytest.skip("本机默认 CA 不可用，此分支不适用")
    clean_env._ensure_ca_bundle()
    assert "SSL_CERT_FILE" not in os.environ


def test_ca_falls_back_to_certifi(clean_env, monkeypatch):
    """打包环境 CA 失效 → 回退 certifi，路径真实可用。"""
    real_ctx = ssl.create_default_context
    monkeypatch.setattr(ssl, "create_default_context", lambda *a, **kw: _EmptyCtx())
    clean_env._ensure_ca_bundle()
    ca = os.environ.get("SSL_CERT_FILE")
    assert ca and os.path.exists(ca), "必须回退出可用的 CA 文件"
    assert "cacert.pem" in ca
    # 用真实 context 验证该 bundle 确实能加载证书
    assert real_ctx(cafile=ca).get_ca_certs()


def test_ca_truststore_preferred_over_certifi(clean_env, monkeypatch):
    """truststore 可用时优先系统信任库，不写 SSL_CERT_FILE（避免覆盖其行为）。

    注意：_ensure_ca_bundle 内部会重新探测 truststore 并覆盖模块级标志，
    故必须同时让 import truststore 成功（fake 一个模块）才能测到这个分支。
    """
    fake_truststore = types.ModuleType("truststore")
    fake_truststore.SSLContext = lambda *a, **kw: object()
    monkeypatch.setitem(sys.modules, "truststore", fake_truststore)
    monkeypatch.setattr(ssl, "create_default_context", lambda *a, **kw: _EmptyCtx())

    clean_env._ensure_ca_bundle()

    assert "SSL_CERT_FILE" not in os.environ, "truststore 可用时不应写 SSL_CERT_FILE"


# ══════════════════════════════════════════════════════════════
# 2. lark 日志桥接（_bridge_lark_logging）
# ══════════════════════════════════════════════════════════════
@pytest.fixture
def captured(monkeypatch):
    """捕获经 loguru 转发的记录（不依赖真实文件 sink）。"""
    m = _load_module()
    from loguru import logger as lz

    records: list[tuple[str, str]] = []
    sink_id = lz.add(
        lambda msg: records.append((msg.record["level"].name, msg.record["message"])),
        level="TRACE",
    )
    try:
        yield records
    finally:
        lz.remove(sink_id)


def test_bridge_forwards_lark_error(captured):
    """核心：lark SDK 的 ERROR 必须能落进 loguru（排查盲区根治）。"""
    m = _load_module()
    m._bridge_lark_logging()
    logging.getLogger("Lark").error("connect failed, err: [SSL: CERTIFICATE_VERIFY_FAILED]")
    assert any("connect failed" in msg for _, msg in captured)


def test_bridge_preserves_level(captured):
    """级别语义保留：ERROR/WARNING/DEBUG 各归其位。"""
    m = _load_module()
    m._bridge_lark_logging()
    lg = logging.getLogger("Lark")
    lg.warning("w-msg")
    lg.error("e-msg")
    # 桥接给消息加了 "[Lark] " 前缀，按键做包含匹配
    by_level = {msg: lv for lv, msg in captured}
    w = next((lv for msg, lv in by_level.items() if "w-msg" in msg), None)
    e = next((lv for msg, lv in by_level.items() if "e-msg" in msg), None)
    assert w == "WARNING"
    assert e == "ERROR"


def test_bridge_ignores_non_lark(tmp_path):
    """只转发 Lark 一族：其他第三方库（噪音大户）不进插件日志通道。"""
    m = _load_module()
    m._bridge_lark_logging()
    from loguru import logger as lz

    records: list[str] = []
    sink_id = lz.add(lambda msg: records.append(msg.record["message"]), level="TRACE")
    try:
        logging.getLogger("urllib3.connectionpool").error("noise-should-not-forward")
        assert not any("noise-should-not-forward" in r for r in records)
    finally:
        lz.remove(sink_id)


def test_bridge_idempotent():
    """幂等：重复安装不叠加 handler（否则每条日志重复落盘）。"""
    m = _load_module()
    m._bridge_lark_logging()
    root = logging.getLogger()
    first = len(root.handlers)
    m._bridge_lark_logging()
    assert len(root.handlers) == first


# ══════════════════════════════════════════════════════════════
# 3. 被动断线重连补偿（_schedule_ws_reconnect / _spawn_ws_thread）
# ══════════════════════════════════════════════════════════════
def _make_adapter():
    m = _load_module()
    cfg = sys.modules["app.gateway.base"].PlatformConfig(
        enabled=True, extra={"app_id": "cli_test", "app_secret": "secret_test"}
    )
    return m, m.FeishuAdapter(cfg)


def test_reconnect_spawns_new_thread():
    """退避后经 _spawn_ws_thread 拉起新 ws 线程（不是递归自身）。"""
    m, adapter = _make_adapter()
    adapter._running = True

    spawned: list[int] = []
    m_orig = adapter._spawn_ws_thread

    def _fake_spawn():
        spawned.append(1)

    adapter._spawn_ws_thread = _fake_spawn
    # 把退避缩短，避免测试等待
    adapter._stop_event.wait = lambda delay: False  # type: ignore[method-assign]
    try:
        adapter._schedule_ws_reconnect()
    finally:
        adapter._spawn_ws_thread = m_orig

    assert spawned == [1], "必须拉起新线程"
    assert adapter._reconnect_attempts == 1


def test_reconnect_respects_stop_event():
    """等待期内收到停止信号 → 取消重连（用户主动停不该被拉起）。"""
    m, adapter = _make_adapter()
    adapter._running = True
    spawned: list[int] = []

    def _fake_spawn():
        spawned.append(1)

    adapter._spawn_ws_thread = _fake_spawn
    adapter._stop_event.set()  # 模拟 disconnect 已置位
    adapter._schedule_ws_reconnect()
    assert not spawned, "停止中不得重连"


def test_reconnect_gives_up_at_limit():
    """达重连上限 → 置 _running/_connected False（不再假连接）。"""
    m, adapter = _make_adapter()
    adapter._running = True
    adapter._connected = True
    adapter._reconnect_attempts = adapter._max_reconnect_attempts

    adapter._schedule_ws_reconnect()

    assert adapter._running is False
    assert adapter._connected is False, "放弃重连时必须复位连接标志，消除假连接"


def test_connect_resets_reconnect_counter():
    """connect() 是全新一次连接 → 重置 attempts（不继承上轮退避计数）。

    直接验代码语义而非跑完整 connect：读源码 AST 确认 `self._reconnect_attempts = 0`
    出现在 connect 函数体内且早于 `_spawn_ws_thread()` 调用。完整 connect 依赖
    lark SDK 的运行时构造（函数内 import），桩成本高且脆弱。
    """
    import ast

    src = (_PLUGIN_DIR / "gateways" / "feishu.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    connect_fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "connect"
    )
    # 收集 connect 函数体里「重置计数」与「起线程」的行号
    reset_line = None
    spawn_line = None
    for node in ast.walk(connect_fn):
        if isinstance(node, ast.Assign):
            targets = [t.attr for t in node.targets if isinstance(t, ast.Attribute)]
            if "_reconnect_attempts" in targets:
                reset_line = node.lineno
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_spawn_ws_thread"
        ):
            spawn_line = node.lineno

    assert reset_line is not None, "connect 内必须重置 _reconnect_attempts"
    assert spawn_line is not None, "connect 必须经 _spawn_ws_thread 起线程"
    assert reset_line < spawn_line, "重置必须早于起线程（否则新线程继承旧计数）"
