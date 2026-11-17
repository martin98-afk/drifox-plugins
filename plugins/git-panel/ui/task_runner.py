"""串行后台任务：主线程分发回调，运行中保活，销毁不阻塞。"""
import logging
from collections import deque

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot

_ACTIVE = set()
_log = logging.getLogger("git-panel")


class _Signals(QObject):
    done = pyqtSignal(object)


class _Task(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self):
        try:
            result = (True, self.fn())
        except Exception as error:
            result = (False, f"{type(error).__name__}: {error}")
        self.signals.done.emit(result)


class TaskRunner(QObject):
    """每个面板一个队列；后台任务只捕获不可变输入和 GitRepo。"""
    idle = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._pending = deque()
        self._active = None
        self._disposed = False

    @property
    def busy(self):
        return self._active is not None or bool(self._pending)

    def submit(self, fn, on_done, on_error=None, key=None):
        if self._disposed:
            return
        job = (fn, on_done, on_error, key)
        if key is not None:
            for i, pending in enumerate(self._pending):
                if pending[3] == key:
                    self._pending[i] = job
                    return
        self._pending.append(job)
        self._start_next()

    def _start_next(self):
        if self._active is not None or self._disposed:
            return
        if not self._pending:
            self.idle.emit()
            return
        job = self._pending.popleft()
        task = _Task(job[0])
        task.signals.done.connect(self._complete)
        self._active = (task, job)
        _ACTIVE.add(self)
        QThreadPool.globalInstance().start(task)

    @pyqtSlot(object)
    def _complete(self, result):
        _, job = self._active
        self._active = None
        if not self._disposed:
            ok, value = result
            callback = job[1] if ok else job[2]
            try:
                if callback:
                    callback(value)
                elif not ok:
                    _log.error("后台任务失败: %s", value)
            except Exception:
                _log.exception("后台任务回调异常")
        if not self._active:
            _ACTIVE.discard(self)
            self._start_next()

    def dispose(self):
        """忽略结果并清空等待任务；运行任务由 _ACTIVE 保活至 done。"""
        self._disposed = True
        self._pending.clear()
        if self._active:
            task, job = self._active
            self._active = (task, (job[0], None, None, job[3]))
