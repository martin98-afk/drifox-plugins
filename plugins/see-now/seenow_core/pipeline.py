# -*- coding: utf-8 -*-
"""采集线程 — 后台持续抓帧、打分、留帧，攒够就出一个「图+清单」。

线程模型：
- 采集线程（daemon）按 fps 抓帧。mss 任意线程可用，Qt 的 QImage 缩放也只
  碰本进程内的图像对象，不碰 QWidget，安全。
- 工具调用时，从队列里**取走**当前攒的帧并拼图。取是原子的（锁），
  所以一次观察只会被一个调用消费。
- 模型思考期间队列继续攒，不等模型——这是上游「截断在采集侧」的设计。

配置热生效：宿主的 PluginConfigStore / PluginConfigRegistry 都不发变更信号，
所以线程每秒自己比对一次配置指纹，变了就原地换参数（不重启线程、不丢已攒的帧）。

空闲自停：久无人用就退出线程并放掉 mss 句柄，下次工具调用由 loop.get_loop() 重新拉起。

与上游的一处简化：不延迟一帧做切点确认。桌面场景的硬切（切窗口）变化分
一帧就冲到 100+，不需要前后帧对比确认尖峰。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from loguru import logger

from .capture import ScreenGrabber
from .scoring import grid_rgb, score_pair
from .sheet import FrameSelector, KeptFrame, compose_sheet, grid_shape, sheet_size

# 配置指纹比对间隔（秒）。load_config 读一次 json 约 0.1ms，频率再高也没意义。
CONFIG_CHECK_SECONDS = 1.0


@dataclass
class Sheet:
    """一次「看」的结果。"""

    png: bytes
    frames: List[KeptFrame]
    cols: int
    rows: int
    width: int
    height: int
    elapsed: float  # 这批帧覆盖多少秒
    reason: str  # "cut" / "fallback" / "mixed"

    def describe(self) -> str:
        """给模型看的一行清单（角标时间码与图里烧的一致）。"""
        count = len(self.frames)
        kind = {"cut": "画面变化", "fallback": "兜底", "mixed": "混合"}.get(self.reason, self.reason)
        lines = [
            f"{self.elapsed:.1f} 秒里的 {count} 个画面（{self.cols}×{self.rows} 宫格，{kind}）",
        ]
        for idx, frame in enumerate(self.frames, 1):
            lines.append(f"  {idx}. {frame.at:.1f}s  变化分 {frame.score:.1f}  {frame.reason}")
        return "\n".join(lines)


class CaptureLoop:
    """采集线程。start() 后持续运行，直到 stop() 或空闲超时。"""

    def __init__(
        self,
        fps: float = 1.0,
        threshold: float = 12.0,
        fallback_seconds: float = 20.0,
        max_frames: int = 6,
        idle_seconds: float = 180.0,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self._fps = max(0.2, float(fps))
        self._threshold = float(threshold)
        self._fallback = float(fallback_seconds)
        self._max_frames = int(max_frames)
        self._interval = 1.0 / self._fps
        self._idle_seconds = float(idle_seconds)
        self._selector = self._make_selector()
        self._grabber = ScreenGrabber()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._prev_grid: Optional[list] = None
        self._started_at = 0.0
        self._frame_count = 0
        self._error_count = 0
        self._on_error = on_error
        self._last_activity = 0.0
        self._last_cfg_check = 0.0
        self._stopped_by_idle = False
        # 已知配置指纹。由构造参数落定（真实路径上它来自 load_config，两者同源），
        # 之后只有与它不同才换参数——否则每次检查都白重配一遍。
        self._cfg_snapshot = self._config_tuple()

    def _config_tuple(self) -> tuple:
        return (self._fps, self._threshold, self._fallback, self._max_frames)

    def _make_selector(self) -> FrameSelector:
        return FrameSelector(
            threshold=self._threshold,
            fallback_seconds=self._fallback,
            max_frames=self._max_frames,
        )

    # ── 生命周期 ────────────────────────────────────────

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            if not self._grabber.is_available():
                logger.warning("[see-now] 采集不可用（取不到屏幕），不启动")
                return False
            self._stop.clear()
            self._started_at = time.monotonic()
            self._last_activity = time.monotonic()
            self._last_cfg_check = 0.0
            self._stopped_by_idle = False
            self._thread = threading.Thread(target=self._run, daemon=True, name="see-now-capture")
            self._thread.start()
            logger.info(f"[see-now] 采集线程已启动（{self._fps:.1f} fps）")
            return True

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=3.0)
        self._thread = None
        self._grabber.close()
        logger.info("[see-now] 采集线程已停止")

    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    # ── 采集 ────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._should_idle_stop():
                self._stopped_by_idle = True
                logger.info(
                    f"[see-now] {self._idle_seconds:.0f} 秒无人使用，采集线程自停（下次调用重新拉起）"
                )
                break
            now = time.monotonic()
            if now - self._last_cfg_check >= CONFIG_CHECK_SECONDS:
                self._last_cfg_check = now
                self._apply_config_if_changed()
            started = time.monotonic()
            try:
                self._tick()
            except Exception as e:  # noqa: BLE001 - 采集线程不能死
                self._error_count += 1
                logger.warning(f"[see-now] 采集异常（第 {self._error_count} 次）: {e}")
                if self._error_count >= 5 and self._on_error is not None:
                    try:
                        self._on_error(f"连续采集失败：{e}")
                    except Exception:  # noqa: BLE001
                        pass
                    self._error_count = 0
            elapsed = time.monotonic() - started
            wait = self._interval - elapsed
            if wait > 0 and self._stop.wait(wait):
                return
        with self._lock:
            self._thread = None
        self._grabber.close()

    def _should_idle_stop(self) -> bool:
        """久无人用就停。

        已攒的帧不受影响：stop() 只关 mss 句柄，`_selector` 里的帧留着，
        下次 start() 后仍在队列里，工具调用照常能取到。
        """
        with self._lock:
            last = self._last_activity
        return last > 0 and (time.monotonic() - last) >= self._idle_seconds

    def _apply_config_if_changed(self) -> None:
        """比对配置指纹，变了原地换参数。

        宿主不发配置变更信号，只能轮询。换参数不重启线程：重启会丢掉已攒的帧，
        且 mss 重新初始化有几十毫秒成本。
        """
        try:
            from .config import load_config

            config = load_config()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[see-now] 读配置失败，沿用旧参数: {e}")
            return
        new_fps = max(0.2, float(config.fps))
        new_threshold = float(config.threshold)
        new_fallback = float(config.fallback_seconds)
        new_max = int(config.max_frames)
        if (new_fps, new_threshold, new_fallback, new_max) == self._cfg_snapshot:
            return
        self._cfg_snapshot = (new_fps, new_threshold, new_fallback, new_max)
        with self._lock:
            if new_fps != self._fps:
                self._fps = new_fps
                self._interval = 1.0 / new_fps
            if (new_threshold, new_fallback, new_max) != (
                self._threshold,
                self._fallback,
                self._max_frames,
            ):
                self._threshold = new_threshold
                self._fallback = new_fallback
                self._max_frames = new_max
                # 阈值/兜底/帧数都只影响留帧判据，重建选择器即可；
                # 已攒的帧随重建丢弃（改配置是低频操作，不为此做状态迁移）。
                self._selector = self._make_selector()
        logger.info(
            f"[see-now] 配置已生效：{new_fps:g} fps / 阈值 {new_threshold:g} / "
            f"兜底 {new_fallback:g}s / 最多 {new_max} 帧"
        )

    def _tick(self) -> None:
        grabbed = self._grabber.grab_scaled()
        if grabbed is None:
            return
        rgb, width, height = grabbed
        at = time.monotonic()
        grid = grid_rgb(rgb, width, height, bpp=3)
        score = 0.0 if self._prev_grid is None else score_pair(self._prev_grid, grid)
        self._prev_grid = grid
        self._frame_count += 1
        self._selector.push(rgb, width, height, score, at)

    # ── 取图 ────────────────────────────────────────────

    def grab_once(self) -> Optional[Sheet]:
        """立刻抓一帧，不消费已攒的帧（action=once 用）。"""
        self._touch()
        grabbed = self._grabber.grab_scaled()
        if grabbed is None:
            return None
        rgb, width, height = grabbed
        selector = FrameSelector()
        selector.push(rgb, width, height, 0.0, time.monotonic())
        frames = selector.take()
        png = compose_sheet(frames)
        if png is None:
            return None
        cols, rows = grid_shape(len(frames))
        sw, sh = sheet_size(len(frames))
        sheet = Sheet(
            png=png,
            frames=frames,
            cols=cols,
            rows=rows,
            width=sw,
            height=sh,
            elapsed=0.0,
            reason="cut",
        )
        # once 的清单不用说「这几个帧」，一句话足够
        sheet.describe = lambda: "当前屏幕（1 帧，整幅）"  # type: ignore[method-assign]
        return sheet

    def take(self, min_frames: int = 1) -> Optional[Sheet]:
        """取走当前攒的帧并拼图。帧数不足 min_frames 时返回 None（不消费）。"""
        self._touch()
        with self._lock:
            if self._selector.pending() < max(1, int(min_frames)):
                return None
            frames = self._selector.take()
        if not frames:
            return None
        png = compose_sheet(frames)
        if png is None:
            return None
        cols, rows = grid_shape(len(frames))
        width, height = sheet_size(len(frames))
        elapsed = frames[-1].at - frames[0].at if len(frames) > 1 else 0.0
        reasons = {f.reason for f in frames}
        reason = reasons.pop() if len(reasons) == 1 else "mixed"
        return Sheet(
            png=png,
            frames=frames,
            cols=cols,
            rows=rows,
            width=width,
            height=height,
            elapsed=elapsed,
            reason=reason,
        )

    def _touch(self) -> None:
        """标记有人在用（watch 轮询期间也算），防空闲自停。"""
        self._last_activity = time.monotonic()

    def stats(self) -> dict:
        with self._lock:
            return {
                "running": self.is_running(),
                "fps": round(1.0 / self._interval, 2),
                "frames_captured": self._frame_count,
                "pending": self._selector.pending(),
                "uptime": round(time.monotonic() - self._started_at, 1) if self._started_at else 0.0,
                "errors": self._error_count,
            }
