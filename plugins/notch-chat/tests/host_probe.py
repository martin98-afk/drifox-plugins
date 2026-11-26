"""在真 DriFox 内验证 EngineSession；报告不含模型回复和凭据。"""

from threading import Event
from time import monotonic


def probe_engine(session, report):
    """在后台线程执行；会话由宿主界面线程创建。"""
    delta = Event()
    first_delta = []

    def mark_delta(piece):
        if isinstance(piece, str) and piece.strip() and not delta.is_set():
            first_delta.append(monotonic())
            delta.set()

    try:
        first = session.turn(
            user="记住本次校验词是蓝松塔。请用两段短文介绍雨天读书。",
            tools=[], callbacks={"content_received": mark_delta}, timeout=90,
            auto_history=True,
        )
        returned = monotonic()
        if not first.ok or not first.text.strip():
            raise RuntimeError("首轮没有有效回复；检查宿主模型配置或服务端连接")
        if not delta.is_set() or first_delta[0] >= returned:
            raise RuntimeError("首轮返回前未收到正文增量")
        report("通过：真实正文增量早于首轮返回")

        second = session.turn(
            user="刚才的校验词是什么？只回答校验词。",
            tools=[], timeout=90, auto_history=True,
        )
        if not second.ok or "蓝松塔" not in second.text:
            raise RuntimeError("追问未得到首轮的校验词")
        report("通过：同一独立会话可追问")
    finally:
        session.cleanup()
