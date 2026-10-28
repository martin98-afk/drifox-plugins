# -*- coding: utf-8 -*-
"""ssh-toolkit 设置卡 — 「SSH 远程连接」：审查 + 删除 AI 保存的连接

与 AI 工具（ssh_add_connection 等）共享 ~/.drifox/cache/ssh/connections.json，
设置页只做审查与删除，新增/编辑交给 AI 工具完成。
每行前置状态点：绿 = 连接池内仍有活跃连接（后台保持连接），红 = 展开时
TCP 探测不可达，灰 = 未保持连接/检测中。探测只做 TCP 层可达性检查，
不做 SSH 认证，避免为展示状态触发登录副作用。
删除时联动关闭该连接名下的活跃连接（tools/_pool.close_by_name）：
池内残留 client 不关会一直持有 socket，且 ensure_client 的懒连接会让已删配置复活。
"""

import json
import socket
import sys
from pathlib import Path

from loguru import logger

try:  # qfluentwidgets 由 DriFox 运行时提供
    from qfluentwidgets import ExpandSettingCard
except Exception:  # noqa: BLE001
    ExpandSettingCard = None  # type: ignore

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtProperty, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# tools/ 目录注入 sys.path：与 conn_mgmt.py 使用同一套顶层模块名（_store/_pool），
# 工具已加载时命中 sys.modules 同一实例，POOL 才是同一个，断连才有效。
_TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

try:
    import _pool  # noqa: E402  tools 连接池（删除联动断连）
    import _store  # noqa: E402  连接配置读写
except Exception as e:  # noqa: BLE001
    _pool = None
    _store = None
    logger.warning(f"[ssh-toolkit] 设置卡加载 tools 模块失败，删除不联动断连: {e}")

PLUGIN_NAME = "ssh-toolkit"
_CARD_BASE = ExpandSettingCard if ExpandSettingCard is not None else object  # type: ignore

# ── 轻量 UI 组件（同构宿主 app/widgets，插件自包含内联，不 import app/） ──

_DOT_CONNECTED = "#22c55e"  # 绿：后台保持连接
_DOT_UNREACHABLE = "#e5484d"  # 红：无法连接
_DOT_IDLE = "#6b7280"  # 灰：未连接 / 检测中

# 状态字 → (圆点颜色, tooltip)
_DOT_STATES = {
    "connected": (_DOT_CONNECTED, "后台保持连接中"),
    "unreachable": (_DOT_UNREACHABLE, "无法连接（TCP 探测失败）"),
    "reachable": (_DOT_IDLE, "可达 · 未保持连接（AI 调用时自动建连）"),
    "probing": (_DOT_IDLE, "正在检测可达性…"),
    "unknown": (_DOT_IDLE, "未连接"),
}

try:  # 跟随用户统一字体设置（宿主可选增强，失败回退应用字体）
    from app.utils.utils import get_unified_font as _host_font
except Exception:  # noqa: BLE001
    _host_font = None


def _ui_font(size=11, bold=False):
    """宿主统一字体；宿主不可达时回退应用字体派生。"""
    if _host_font is not None:
        try:
            return _host_font(size, bold)
        except Exception:  # noqa: BLE001
            pass
    f = QFont(QApplication.font())
    f.setPointSize(size)
    f.setBold(bold)
    return f


class _CardHeightDriver(QObject):
    """把动画值写成卡片 fixedHeight（QPropertyAnimation 不能直接驱动 setFixedHeight）。"""

    def __init__(self, card):
        super().__init__(card)
        self._card = card
        self._value = 0

    def _get_value(self) -> int:
        return self._value

    def _set_value(self, value) -> None:
        self._value = int(value)
        try:
            self._card.setFixedHeight(self._value)
        except RuntimeError:  # 卡片已销毁（设置面板关闭）
            pass

    value = pyqtProperty(int, _get_value, _set_value)


def _animate_card_height(card, target: int, duration: int = 180) -> None:
    """展开/折叠高度动画：逐帧写 fixedHeight，避免高度瞬移。"""
    from PyQt5.QtCore import QEasingCurve, QPropertyAnimation

    ani = getattr(card, "_expand_height_ani", None)
    if ani is None:
        driver = _CardHeightDriver(card)
        ani = QPropertyAnimation(driver, b"value", card)
        ani.setDuration(duration)
        ani.setEasingCurve(QEasingCurve.OutCubic)
        card._expand_height_driver = driver
        card._expand_height_ani = ani
    ani.stop()
    ani.setStartValue(int(card.height()))
    ani.setEndValue(max(0, int(target)))
    ani.start()


class _StatusDot(QLabel):
    """CSS 圆点状态灯（QSS border-radius 矢量圆，缩放不发虚不裁切）。"""

    def __init__(self, diameter=10, color=_DOT_IDLE, parent=None):
        super().__init__(parent)
        self._d = max(4, int(diameter))
        self._color = color
        self.setFixedSize(self._d, self._d)
        self._apply()

    def set_color(self, color):
        if color != self._color:
            self._color = color
            self._apply()

    def _apply(self):
        r = self._d // 2
        self.setStyleSheet(
            f"background-color: {self._color}; border: none;"
            f" border-radius: {r}px; padding: 0;"
        )


class _ElidedLabel(QLabel):
    """宽度不足时中段自动省略（…），tooltip 保留全文。"""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = text
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setToolTip(text)
        super().setText(text)

    def setText(self, text):
        self._full = text
        self.setToolTip(text)
        self._update_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elide()

    def _update_elide(self):
        w = self.width()
        if w <= 0:
            super().setText(self._full)
            return
        super().setText(self.fontMetrics().elidedText(self._full, Qt.ElideMiddle, w))


def _hint_label(text, color="gray"):
    """空态/错误态提示：一行灰字或红字，自动换行，不弹窗。"""
    lb = QLabel(text)
    lb.setFont(_ui_font(10))
    lb.setWordWrap(True)
    lb.setStyleSheet(f"color: {color};")
    return lb


def _humanize_since(iso):
    """ISO 时间戳 → 「刚刚 / 3 分钟前 / 2 小时前 / 昨天 / 5 天前 / 2026-01-02」。"""
    import datetime

    if not iso:
        return "未知"
    try:
        ts = datetime.datetime.fromisoformat(str(iso))
    except ValueError:
        return str(iso)
    secs = int((datetime.datetime.now() - ts).total_seconds())
    if secs < 0:
        return ts.strftime("%Y-%m-%d %H:%M")
    if secs < 60:
        return "刚刚"
    if secs < 3600:
        return f"{secs // 60} 分钟前"
    if secs < 86400:
        return f"{secs // 3600} 小时前"
    if secs < 86400 * 2:
        return "昨天"
    if secs < 86400 * 30:
        return f"{secs // 86400} 天前"
    return ts.strftime("%Y-%m-%d")


# ── 可达性探测（展开设置卡时对未保持连接的条目后台 TCP 探测） ────────


class _ProbeSignals(QObject):
    """探测结果桥：出生在主线程（模块首次导入必在主线程），worker 线程 emit
    经 queued 连接投递回 UI 线程；接收方卡片销毁后事件由 Qt 自动丢弃。"""

    done = pyqtSignal(str, bool)  # (name, reachable)


_probe_signals_instance = None


def _probe_signals():
    global _probe_signals_instance
    if _probe_signals_instance is None:
        _probe_signals_instance = _ProbeSignals()
    return _probe_signals_instance


def _tcp_reachable(host, port, timeout=3.0):
    """TCP 层可达性：只建连接不认证，状态展示不应触发登录副作用。"""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


class _ProbeRunnable(QRunnable):
    """短命任务跑在线程池，结果经主线程出生的信号桥投递，无线程对象析构问题。"""

    def __init__(self, name, host, port):
        super().__init__()
        self._name, self._host, self._port = name, host, port

    def run(self):
        ok = _tcp_reachable(self._host, self._port)
        try:
            _probe_signals().done.emit(self._name, ok)
        except RuntimeError:  # 桥对象已随热重载销毁，丢弃即可
            pass


def _pool_active(name):
    """池内是否存在该连接名的活跃连接（paramiko transport 仍 alive）。"""
    if _pool is None:
        return False
    try:
        for handle, client in list(_pool.POOL.items()):
            # handle = "<连接名>:<uuid>"，连接名可能自带冒号（user@host:port），
            # 必须从右侧切掉 uuid 才能还原名字
            if handle.rsplit(":", 1)[0] != name:
                continue
            transport = None
            try:
                transport = client.get_transport()
            except Exception:  # noqa: BLE001
                pass
            if transport is not None and transport.is_active():
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _conns_path():
    return Path.home() / ".drifox" / "cache" / "ssh" / "connections.json"


def _load_conns():
    """返回 (conns, error)。文件不存在返回空列表；损坏返回错误信息。"""
    p = _conns_path()
    if not p.exists():
        return [], None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (data.get("connections") or []), None
    except (OSError, ValueError) as e:
        return [], f"连接配置读取失败: {e}"


class _ConnectionsCard(_CARD_BASE):
    """SSH 连接列表卡：每行 name + user@host:port + 认证摘要，右侧删除按钮。

    构造签名 (parent=None) 满足 register_settings_card 的 widget_class 约定。
    密码/口令值永不展示，仅显示认证方式摘要。
    """

    def __init__(self, parent=None):
        from qfluentwidgets import FluentIcon

        # GLOB 在部分 qfluentwidgets 版本不存在（实测本机报 no attribute 'GLOB'），
        # getattr 回退 SETTING，避免枚举名差异炸掉整卡构建
        icon = getattr(FluentIcon, "GLOBE", None) or FluentIcon.SETTING
        super().__init__(
            icon,
            "SSH 远程连接",
            "审查 AI 保存的连接；删除将同时断开其活跃连接与端口转发",
            parent,
        )
        self.viewLayout.setContentsMargins(48, 8, 48, 8)
        self.viewLayout.setSpacing(4)

        self._dots = {}  # name -> _StatusDot（探测回调按名更新）
        self._status = {}  # name -> 状态字（探测缓存，跨展开保留）
        self._probing = set()  # 探测中的连接名，防重复派发
        _probe_signals().done.connect(self._on_probe_done)

        self._list_layout = QVBoxLayout()
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)

        # 顶部摘要：总数 + 活跃数（展开时刷新）
        self._summary = QLabel("")
        self._summary.setFont(_ui_font(10))
        self._summary.setStyleSheet("color: gray;")
        self.viewLayout.addWidget(self._summary)
        self.viewLayout.addLayout(self._list_layout)

        self._reload()

    # ── 数据渲染 ──

    def _reload(self):
        """清空重建列表。展开时调用，保证 AI 增删/新连接后打开设置即是最新。"""
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                # 必须立即 setParent(None)：deleteLater 要等事件循环，期间旧行
                # 仍挂在父级上照常绘制，与新行叠成重影（展开时 _reload 会再跑一次）
                w.setParent(None)
                w.deleteLater()
        self._dots.clear()  # 旧行 dot 随 deleteLater 销毁，引用一并清理

        conns, error = _load_conns()
        if error:
            self._summary.setText("")
            hint = _hint_label(error, "#e5484d")
            self._list_layout.addWidget(hint)
            return
        if not conns:
            self._summary.setText("")
            hint = _hint_label(
                "还没有保存的连接。直接对 AI 说「连到 root@1.2.3.4」，连上后会自动出现在这里。",
                "gray",
            )
            self._list_layout.addWidget(hint)
            return

        active = sum(1 for c in conns if _pool_active(c.get("name") or ""))
        summary = f"共 {len(conns)} 个连接"
        if active:
            summary += f" · {active} 个活跃中"
        self._summary.setText(summary)

        for c in conns:
            self._list_layout.addWidget(self._build_row(c))
        self._refresh_status(conns)

    # ── 连接状态点 ──

    def _refresh_status(self, conns):
        """逐条刷新状态：池内活跃直接绿；其余沿用探测缓存，无缓存则后台探测。"""
        for c in conns:
            name = c.get("name") or ""
            if not name or name not in self._dots:
                continue
            if _pool_active(name):
                self._apply_status(name, "connected")
                continue
            if name in self._probing:
                continue
            cached = self._status.get(name)
            if cached:
                self._apply_status(name, cached)
                continue
            host = (c.get("host") or "").strip()
            if not host:
                self._apply_status(name, "unknown")
                continue
            self._probing.add(name)
            self._apply_status(name, "probing")
            QThreadPool.globalInstance().start(
                _ProbeRunnable(name, host, c.get("port", 22))
            )

    def _apply_status(self, name, state):
        self._status[name] = state
        dot = self._dots.get(name)
        if dot is None:
            return
        color, tip = _DOT_STATES.get(state, _DOT_STATES["unknown"])
        dot.set_color(color)
        dot.setToolTip(tip)

    def _on_probe_done(self, name, reachable):
        """探测结果投递回 UI 线程：更新缓存与状态点（行数不变，无需调高度）。"""
        self._probing.discard(name)
        if name not in self._dots:
            return
        self._apply_status(name, "reachable" if reachable else "unreachable")

    @staticmethod
    def _describe(c):
        auth = c.get("auth_type") or ""
        if auth == "publickey":
            detail = f"密钥 {c.get('key_path') or '~/.ssh/id_rsa'}"
        elif auth == "password":
            detail = "密码认证"
        else:
            detail = auth or "未指定认证"
        return detail

    def _build_row(self, c):
        name = c.get("name") or "（未命名）"
        addr = "{user}@{host}:{port}".format(
            user=c.get("user") or "?",
            host=c.get("host") or "?",
            port=c.get("port", 22),
        )
        last = _humanize_since(c.get("last_connected"))
        count = int(c.get("connect_count") or 0)
        note = (c.get("note") or "").strip()

        w = QWidget()
        w.setObjectName("sshConnRow")
        w.setAttribute(Qt.WA_StyledBackground, True)
        w.setStyleSheet(
            "#sshConnRow { background: rgba(128,128,128,0.07); border-radius: 6px; }"
            "#sshConnRow:hover { background: rgba(128,128,128,0.13); }"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(10)

        # 状态指示灯（CSS 圆点，矢量绘制不发虚不裁切）
        dot = _StatusDot(10, color=_DOT_IDLE)
        dot.setToolTip("未连接")
        self._dots[c.get("name") or ""] = dot
        lay.addWidget(dot, 0, Qt.AlignTop)

        # 两行信息：名称 + 右侧「时间 · 次数」/ 地址（名字已含地址时省略）+ 认证 + 备注
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        name_label = QLabel(name)
        name_label.setFont(_ui_font(11, bold=True))
        name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        title_row.addWidget(name_label, 0)
        title_row.addStretch(1)
        # 右侧一行化：「3 分钟前 · 2 次」，没有次数就只留时间，不占额外行
        brief = " · ".join(x for x in (last, f"{count} 次" if count else "") if x)
        brief_label = QLabel(brief)
        brief_label.setFont(_ui_font(9))
        brief_label.setStyleSheet("color: gray;")
        title_row.addWidget(brief_label, 0)
        text_col.addLayout(title_row)

        parts = []
        if addr != name:  # 名字就是 user@host:port 时不重复平铺
            parts.append(addr)
        parts.append(self._describe(c))
        if note:
            parts.append(note)
        meta = _ElidedLabel(" · ".join(parts))
        meta.setFont(_ui_font(10))
        meta.setStyleSheet("color: gray;")
        meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_col.addWidget(meta)

        lay.addLayout(text_col, 1)

        btn = QPushButton("删除")
        btn.setFont(_ui_font(10))
        btn.setFixedHeight(26)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background: transparent;"
            " border: 1px solid rgba(128,128,128,0.35); border-radius: 4px;"
            " padding: 2px 14px; color: gray; }"
            "QPushButton:hover { border-color: #e5484d; color: #e5484d;"
            " background: rgba(229,72,77,0.08); }"
        )
        btn.clicked.connect(lambda _=False, n=c.get("name"): self._on_remove(n))
        lay.addWidget(btn, 0, Qt.AlignVCenter)

        tips = [f"{name}  {addr}", f"认证：{self._describe(c)}", f"最后连接：{last}"]
        if count:
            tips.append(f"累计连接 {count} 次")
        if note:
            tips.append(f"备注：{note}")
        w.setToolTip("\n".join(tips))
        return w

    # ── 删除（联动断开活跃连接） ──

    def _on_remove(self, name):
        if not name:
            return
        box = QMessageBox(self)
        box.setWindowTitle("删除 SSH 连接")
        box.setText(
            f"确定删除连接「{name}」？\n将同时断开该连接名下的活跃连接与端口转发。"
        )
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        if box.exec_() != QMessageBox.Yes:
            return

        closed = 0
        if _pool is not None:
            try:
                closed = _pool.close_by_name(name)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[ssh-toolkit] 断开活跃连接失败 {name}: {e}")
        try:
            _store.remove_connection(name)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[ssh-toolkit] 删除连接配置失败 {name}: {e}")
            QMessageBox.warning(self, "删除失败", str(e))
            return
        logger.info(f"[ssh-toolkit] 设置页删除连接 {name}（断开 {closed} 条活跃连接）")
        self._reload()
        if self.isExpand:
            self._adjustViewSize()  # 展开态删行后收缩高度，避免留白

    # ── 展开几何（qfluentwidgets ExpandSettingCard 占位坑，同 git-panel 处理） ──

    def _measure_content_height(self):
        """内容区应有高度：递归手工累加，不依赖 viewLayout.sizeHint 汇总。

        展开时列表刚重建，新行 widget 尚未 show，QBoxLayout 汇总会跳过它们
        （viewLayout.sizeHint 会漏算），据此锁高会把内容压扁、文字互相重叠。
        行 widget 自身的 sizeHint 与 show 状态无关，递归累加可得精确高度；
        顶部摘要行与嵌套的 _list_layout 都要算进去。
        """

        def measure(item):
            w = item.widget()
            if w is not None:
                return w.sizeHint().height()
            lay = item.layout()
            if lay is None:
                return 0
            m = lay.contentsMargins()
            n = lay.count()
            h = m.top() + m.bottom()
            for i in range(n):
                h += measure(lay.itemAt(i))
            if n > 1:
                h += lay.spacing() * (n - 1)
            return h

        m = self.viewLayout.contentsMargins()
        n = self.viewLayout.count()
        total = m.top() + m.bottom()
        for i in range(n):
            total += measure(self.viewLayout.itemAt(i))
        if n > 1:
            total += self.viewLayout.spacing() * (n - 1)
        return total

    def _adjustViewSize(self):
        """内容尺寸变化后直接定格（不动画）：删行/重建后用。"""
        try:
            self.spaceWidget.setFixedHeight(0)
        except Exception:  # noqa: BLE001
            pass
        h = self._measure_content_height() if self.isExpand else 0
        self.setFixedHeight(self.card.height() + h)

    def setExpand(self, isExpand: bool):
        """覆写：展开前先重载数据（AI 改动后即为最新），高度走动画。

        列表是动态重建的，目标高度必须用 _measure_content_height 实测
        （viewLayout.sizeHint 会跳过尚未 show 的新行）。
        """
        if isExpand:
            self._reload()
        if self.isExpand == isExpand:
            return
        self.isExpand = isExpand
        self.setProperty("isExpand", isExpand)
        self.setStyle(QApplication.style())
        self.card.expandButton.setExpand(isExpand)
        try:
            self.spaceWidget.setFixedHeight(0)
        except Exception:  # noqa: BLE001
            pass
        target = self.card.height() + (self._measure_content_height() if isExpand else 0)
        _animate_card_height(self, target)


def register_connections_card(registry):
    """注册「SSH 远程连接」设置卡到设置面板「插件」分区。"""
    registry.register_settings_card(
        PLUGIN_NAME,
        f"{PLUGIN_NAME}-connections",
        "SSH 远程连接",
        _ConnectionsCard,
        priority=1,
    )
