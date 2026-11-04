# -*- coding: utf-8 -*-
"""speak-up 运行时 — 定时器 + 掷骰 + 真发。

线程与宿主约束（读主程序源码得到，不是假设）：

1. `session.send` 是能力池里 `_send_with_mode` 的闭包，内部只做 `action_queue.enqueue`。
   `main_widget` 有 enqueue observer，空闲期入队会立刻 drain（注释在
   `app/main_widget.py:1018`：正是为「定时器 session.send」加的这条桥）。
   所以本插件可以放心在**后台线程**调 send，不需要自己碰 Qt。

2. 冷却口径抄上游 0.2.9（issue #8）：投递成功不等于「她真的说了话」。
   上游踩过：投递成功、这一轮 1 秒结束、一个字没发，却照样吃掉了整个冷却。
   这里改判据为「投递后，会话里出现新的 assistant 消息且有正文」。

3. 「距上次用户说话」：DriFox 没有 `sessionController.inspect`，
   走 `session.read()` 拿当前会话消息列表，从后往前找最后一条 role=user。
   ⚠ read() 只给**当前会话**——多会话场景下拿不到其它会话的时间，
   此时按「时间不明」处理（时机因子 1），这是能力边界不是 bug。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from . import dice
from .config import SpeakUpConfig

LOG_LIMIT = 60
SOURCE_TAG = "speak-up"


@dataclass
class LogEntry:
    at: str
    text: str


@dataclass
class RuntimeState:
    misses: int = 0  # 连着几次没掷中（只在内存，重启归零）
    last_self_spoke: float = 0.0  # 自己上次**真的说出话**的时刻（time.time()）
    last_user_at: float = 0.0  # 观测到的最后一条用户消息时刻
    entries: List[LogEntry] = field(default_factory=list)


class SpeakUpRunner:
    """调度与执行。所有公开方法都可从后台线程调用。"""

    def __init__(self, get_caps: Callable[[str], Any], get_config: Callable[[], SpeakUpConfig]):
        self._get_caps = get_caps
        self._get_config = get_config
        self._state = RuntimeState()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._interval_seconds = 0

    # ── 生命周期 ────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="speak-up-timer")
            self._thread.start()
            logger.info("[speak-up] 定时器已启动")

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
        logger.info("[speak-up] 定时器已停止")

    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    # ── 记账 ────────────────────────────────────────────

    def _record(self, text: str) -> LogEntry:
        entry = LogEntry(at=datetime.now().strftime("%m-%d %H:%M:%S"), text=str(text))
        with self._lock:
            self._state.entries.append(entry)
            if len(self._state.entries) > LOG_LIMIT:
                del self._state.entries[: len(self._state.entries) - LOG_LIMIT]
        try:
            logger.info(f"[speak-up] {entry.text}")
        except Exception:  # noqa: BLE001 - 记账失败不影响主流程
            pass
        return entry

    def recent_entries(self) -> List[LogEntry]:
        with self._lock:
            return list(self._state.entries)

    def state_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "misses": self._state.misses,
                "last_self_spoke": self._state.last_self_spoke,
                "running": self.is_running(),
                "interval_seconds": self._interval_seconds,
            }

    # ── 会话观测 ────────────────────────────────────────

    def _read_session(self) -> Dict[str, Any]:
        read = self._get_caps("session.read")
        if not callable(read):
            return {}
        try:
            return read() or {}
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[speak-up] 读会话失败: {e}")
            return {}

    def _minutes_since_user(self) -> Optional[float]:
        """距最后一条用户消息多少分钟。取不到返回 None（时机因子按 1 算）。

        优先用运行时观测到的时间（hook 记录，毫秒级准确）；
        没有就翻会话消息，按 `ts_ms` 或 `timestamp` 字段解析。
        """
        with self._lock:
            observed = self._state.last_user_at
        if observed > 0:
            return (time.time() - observed) / 60.0

        session = self._read_session()
        messages = session.get("messages") or []
        for msg in reversed(messages):
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            ts_ms = msg.get("ts_ms")
            if isinstance(ts_ms, (int, float)) and ts_ms > 0:
                return (time.time() - float(ts_ms) / 1000.0) / 60.0
            stamp = msg.get("timestamp")
            if isinstance(stamp, str) and stamp:
                try:
                    dt = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                return (time.time() - dt.timestamp()) / 60.0
        return None

    def note_user_activity(self) -> None:
        """hook 在用户发消息时调用，记下精确时刻。"""
        with self._lock:
            self._state.last_user_at = time.time()

    def _session_is_busy(self) -> bool:
        """当前会话是否在流式中。读不到按不忙处理（安全默认，与宿主同口径）。"""
        try:
            from app.plugins.capabilities.providers.ui_core import _engine_busy  # type: ignore

            from app.plugins.capabilities.resolve import active_main_widget

            host = active_main_widget()
            backend = getattr(host, "backend", None)
            return bool(_engine_busy(backend))
        except Exception:  # noqa: BLE001 - 判忙是优化不是必需，读不到就当空闲
            pass
        # 退路：会话消息最后一条是 assistant 且有内容，且没有活跃流 → 认为不忙
        return False

    # ── 执行 ────────────────────────────────────────────

    def _loop(self) -> None:
        # 首轮先睡一个间隔再掷：刚启动时用户可能正在用，别立刻插话
        while not self._stop.is_set():
            config = self._get_config()
            interval = max(1, int(config.interval_minutes)) * 60
            self._interval_seconds = interval
            if self._stop.wait(interval):
                return
            try:
                self.roll(source="定时", mode="自动")
            except Exception as e:  # noqa: BLE001 - 定时线程不能死
                logger.exception(f"[speak-up] 定时掷骰异常: {e}")

    def roll(self, source: str = "手动", mode: str = "自动") -> Dict[str, Any]:
        """掷一次骰。mode: 自动 / 演练 / 真发。

        - 自动：定时器走的路，受总开关/安静时段/命中线约束，试运行开着就只记账
        - 演练：跳过安静时段和命中线，**绝不真发**
        - 真发：跳过等待和试运行，真的发出去（用于当场验证）
        """
        config = self._get_config()
        now = datetime.now()
        rehearsal = mode == "演练" or (mode == "自动" and config.dry_run)

        if mode == "自动":
            if not config.enabled:
                return self._result(False, self._record("总开关是关着的，这轮不动"))
            if dice.in_quiet_hours(now.hour, config.quiet_start_hour, config.quiet_end_hour):
                return self._result(
                    False,
                    self._record(
                        f"现在 {now.hour} 点在安静时段（{config.quiet_start_hour}~{config.quiet_end_hour}）里，这轮不掷"
                    ),
                )

        if not config.enabled and mode != "真发":
            return self._result(False, self._record("总开关关着，跳过"))

        # 冷却：只认「真的说出话」，且只约束自动路径
        if mode == "自动" and config.cooldown_minutes > 0:
            with self._lock:
                last = self._state.last_self_spoke
            if last > 0:
                cooled = (time.time() - last) / 60.0
                if cooled < config.cooldown_minutes:
                    return self._result(
                        False,
                        self._record(
                            f"自己刚开过口（{cooled:.1f} 分钟前，冷却 {config.cooldown_minutes} 分钟），这轮不重复"
                        ),
                    )

        if self._session_is_busy():
            return self._result(False, self._record("会话正忙（在流式输出），这轮不搭话"))

        # 掷骰（手动按钮不掷、不动 misses 计数器）
        prefix = ""
        roll_result: Optional[dice.RollResult] = None
        if mode == "自动":
            minutes = self._minutes_since_user()
            with self._lock:
                misses = self._state.misses
            roll_result = dice.roll_once(
                peak_hit=config.peak_hit,
                valley_hit=config.valley_hit,
                near_minutes=config.near_minutes,
                near_factor=config.near_factor,
                far_minutes=config.far_minutes,
                far_factor=config.far_factor,
                miss_bonus=config.miss_bonus,
                bonus_cap=config.bonus_cap,
                misses=misses,
                minutes_since_user=minutes,
                now=now,
            )
            with self._lock:
                self._state.misses = roll_result.misses_after
            prefix = roll_result.message
            if not roll_result.hit:
                return self._result(False, self._record(prefix))
        else:
            prefix = f"【{source}/{mode}】手动触发（不掷骰子、不动没中加成）"

        text = dice.wrap_inner_voice(config.trigger_text, now)
        flat = text.replace("\n", " ")

        if rehearsal:
            return self._result(False, self._record(f"{prefix}｜演练：本来要发「{flat}」"))

        send = self._get_caps("session.send")
        if not callable(send):
            return self._result(False, self._record(f"{prefix}｜session.send 取不到，无法投递"))

        before_count = len((self._read_session().get("messages") or []))
        try:
            ok = send(text)
        except Exception as e:  # noqa: BLE001 - 投递失败不能炸定时线程
            return self._result(False, self._record(f"{prefix}｜投递异常：{e}"))
        if not ok:
            return self._result(False, self._record(f"{prefix}｜入队被拒绝（窗口不匹配或宿主未就绪）"))

        entry = self._record(f"{prefix}｜已送出一句，宿主会照常开一轮：「{flat}」")
        self._watch_spoken(before_count)
        return self._result(True, entry)

    def _watch_spoken(self, before_count: int) -> None:
        """投递后盯一小段时间，真出现新的 assistant 正文才记「自己上次开口」。

        上游踩过的坑：投递成功不等于模型真的说了话。那一轮可能被用户打断、
        可能 1 秒结束一个字没发。用投递时间当冷却起点会让冷却白吃。
        """

        def _watch() -> None:
            deadline = time.time() + 180.0  # 3 分钟够模型跑完一轮短对话
            while time.time() < deadline and not self._stop.is_set():
                time.sleep(3.0)
                messages = self._read_session().get("messages") or []
                if len(messages) <= before_count:
                    continue
                for msg in messages[before_count:]:
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("role") != "assistant":
                        continue
                    content = msg.get("content")
                    if isinstance(content, str) and content.strip():
                        with self._lock:
                            self._state.last_self_spoke = time.time()
                        logger.debug("[speak-up] 已确认它真的说了话，冷却起点更新")
                        return
            logger.debug("[speak-up] 3 分钟内未见 assistant 正文，冷却起点不更新")

        threading.Thread(target=_watch_spoken, daemon=True, name="speak-up-watch").start()

    @staticmethod
    def _result(ok: bool, entry: LogEntry) -> Dict[str, Any]:
        return {"ok": ok, "at": entry.at, "text": entry.text}
