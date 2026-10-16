# -*- coding: utf-8 -*-
"""ssh-toolkit 设置卡 — 「SSH 远程连接」：审查 + 删除 AI 保存的连接

与 AI 工具（ssh_add_connection 等）共享 ~/.drifox/cache/ssh/connections.json，
设置页只做审查与删除，新增/编辑交给 AI 工具完成。
删除时联动关闭该连接名下的活跃连接（tools/_pool.close_by_name）：
池内残留 client 不关会一直持有 socket，且 ensure_client 的懒连接会让已删配置复活。
"""

import json
import sys
from pathlib import Path

from loguru import logger

# tools/ 目录注入 sys.path：与 conn_mgmt.py 使用同一套顶层模块名（_store/_pool），
# 工具已加载时命中 sys.modules 同一实例，POOL 才是同一个，断连才有效。
_TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

try:  # qfluentwidgets 由 DriFox 运行时提供
    from qfluentwidgets import ExpandSettingCard
except Exception:  # noqa: BLE001
    ExpandSettingCard = None  # type: ignore

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    import _pool  # noqa: E402  tools 连接池（删除联动断连）
    import _store  # noqa: E402  连接配置读写
except Exception as e:  # noqa: BLE001
    _pool = None
    _store = None
    logger.warning(f"[ssh-toolkit] 设置卡加载 tools 模块失败，删除不联动断连: {e}")

PLUGIN_NAME = "ssh-toolkit"
_CARD_BASE = ExpandSettingCard if ExpandSettingCard is not None else object  # type: ignore


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

        self._list_layout = QVBoxLayout()
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self.viewLayout.addLayout(self._list_layout)

        self._reload()

    # ── 数据渲染 ──

    def _reload(self):
        """清空重建列表。展开时调用，保证 AI 增删后打开设置即是最新。"""
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        conns, error = _load_conns()
        if error:
            hint = QLabel(error)
            hint.setStyleSheet("color: #e5484d;")
            self._list_layout.addWidget(hint)
            return
        if not conns:
            hint = QLabel("（暂无已保存连接 — 让 AI 用 ssh_add_connection 添加）")
            hint.setStyleSheet("color: gray;")
            self._list_layout.addWidget(hint)
            return
        for c in conns:
            self._list_layout.addWidget(self._build_row(c))

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
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        text = "{name}   {user}@{host}:{port}   [{detail}]".format(
            name=c.get("name") or "（未命名）",
            user=c.get("user") or "?",
            host=c.get("host") or "?",
            port=c.get("port", 22),
            detail=self._describe(c),
        )
        note = (c.get("note") or "").strip()
        if note:
            text += f"   {note}"
        label = QLabel(text)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(label, 1)

        btn = QPushButton("删除")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("QPushButton:hover { color: #e5484d; }")
        btn.clicked.connect(lambda _=False, n=c.get("name"): self._on_remove(n))
        lay.addWidget(btn, 0, Qt.AlignRight)
        return w

    # ── 删除（联动断开活跃连接） ──

    def _on_remove(self, name):
        if not name:
            return
        box = QMessageBox(self)
        box.setWindowTitle("删除 SSH 连接")
        box.setText(f"确定删除连接「{name}」？\n将同时断开该连接名下的活跃连接与端口转发。")
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
        """内容区应有高度：手工累加，不依赖 viewLayout.sizeHint 汇总。

        展开时列表刚重建，新行 widget 尚未 show，QBoxLayout 汇总会跳过它们
        （viewLayout.sizeHint 只剩 margins 16px），据此锁高会把内容压成一条缝。
        行 widget 自身的 sizeHint 与 show 状态无关，累加可得精确高度。
        """
        m = self.viewLayout.contentsMargins()
        h = m.top() + m.bottom()
        n = self._list_layout.count()
        for i in range(n):
            item = self._list_layout.itemAt(i)
            w = item.widget()
            h += w.sizeHint().height() if w is not None else item.sizeHint().height()
        if n > 1:
            h += self._list_layout.spacing() * (n - 1)
        return h

    def _adjustViewSize(self):
        """spaceWidget 占位归零 + 按手工测量高度直切展开/折叠。

        原版 _adjustViewSize 把 spaceWidget 设为内容等高，展开高度 = 内容 + 等高空白，
        且折叠动画依赖占位高度导致收不回去；归零后牺牲折叠动画换取正确几何。"""
        try:
            self.spaceWidget.setFixedHeight(0)
        except Exception:  # noqa: BLE001
            pass
        if self.isExpand:
            self.setFixedHeight(self.card.height() + self._measure_content_height())
        else:
            self.setFixedHeight(self.card.height())

    def setExpand(self, isExpand: bool):
        """覆写：不用原版滚动动画；展开前先重载数据（AI 改动后即为最新）。"""
        if isExpand:
            self._reload()
        if self.isExpand == isExpand:
            return
        self.isExpand = isExpand
        self.setProperty("isExpand", isExpand)
        self.setStyle(QApplication.style())
        self.card.expandButton.setExpand(isExpand)
        self._adjustViewSize()


def register_connections_card(registry):
    """注册「SSH 远程连接」设置卡到设置面板「插件」分区。"""
    registry.register_settings_card(
        PLUGIN_NAME,
        f"{PLUGIN_NAME}-connections",
        "SSH 远程连接",
        _ConnectionsCard,
        priority=1,
    )
