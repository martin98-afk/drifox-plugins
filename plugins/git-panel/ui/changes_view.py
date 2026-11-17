"""变更文件的轻量模型/视图：列表与文件树共用交互和状态。"""
import os

from PyQt5.QtCore import QSettings, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPalette, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QAbstractItemView, QStyle, QStyledItemDelegate, QTreeView

FILE_ROLE = Qt.UserRole + 1
KEY_ROLE = Qt.UserRole + 2
CONFLICTS = {"UU", "AA", "DD", "DU", "UD", "AU", "UA"}
GROUPS = (("conflict", "合并更改"), ("staged", "已暂存的更改"), ("changes", "更改"))


class _FileDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(80, max(28, option.fontMetrics.height() + 10))

    def paint(self, painter: QPainter, option, index):
        info = index.data(FILE_ROLE)
        if not info:
            super().paint(painter, option, index)
            return
        opt = self.viewOptions(option)
        opt.text = ""
        style = option.widget.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, option.widget)
        painter.save()
        painter.setFont(option.font)
        rect = option.rect.adjusted(4, 0, -4, 0)
        selected = bool(option.state & QStyle.State_Selected)
        palette = option.palette
        primary = palette.color(QPalette.HighlightedText if selected else QPalette.Text)
        secondary = QColor(primary)
        secondary.setAlphaF(.5)
        hovered = bool(option.state & QStyle.State_MouseOver)
        action_width = 24
        text_rect = rect.adjusted(0, 0, -(26 + action_width), 0)
        name = os.path.basename(info["path"])
        painter.setPen(primary)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                         option.fontMetrics.elidedText(name, Qt.ElideMiddle, text_rect.width()))
        if option.widget.property("changesMode") == "list":
            name_width = option.fontMetrics.horizontalAdvance(name) + 14
            directory = os.path.dirname(info["path"])
            if directory and name_width < text_rect.width() - 24:
                directory_rect = text_rect.adjusted(name_width, 0, 0, 0)
                painter.setPen(secondary)
                available = directory_rect.width()
                painter.drawText(directory_rect, Qt.AlignVCenter | Qt.AlignLeft,
                                 option.fontMetrics.elidedText(directory, Qt.ElideLeft, available))
        status = info["status"]
        letter = "U" if status in CONFLICTS or status == "??" else status[:1]
        color = primary if selected else palette.color(QPalette.Link)
        if status in {"A", "??"} and not selected:
            color = QColor("#16a34a")
        elif (status in CONFLICTS or status == "D") and not selected:
            color = QColor("#e05252")
        painter.setPen(color)
        status_rect = QRect(rect.right() - action_width - 20, rect.top(), 20, rect.height())
        painter.drawText(status_rect, Qt.AlignCenter, letter)
        if hovered:
            painter.setPen(primary)
            painter.drawText(rect.adjusted(rect.width() - 22, 0, 0, 0), Qt.AlignCenter,
                             "!" if status in CONFLICTS else "−" if info["staged"] else "+")
        painter.restore()

    @staticmethod
    def viewOptions(option):
        from PyQt5.QtWidgets import QStyleOptionViewItem
        return QStyleOptionViewItem(option)


class ChangesView(QTreeView):
    diff_requested = pyqtSignal(str, bool, str)
    action_requested = pyqtSignal(str, object)
    context_requested = pyqtSignal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = ()
        self._fingerprint = None
        self._mode = "list"
        self._settings = QSettings("DriFox", "git-panel")
        self._dir_state = {}
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setIndentation(14)
        self.setMouseTracking(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setItemDelegate(_FileDelegate(self))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.expanded.connect(lambda i: self._remember_dir(i, True))
        self.collapsed.connect(lambda i: self._remember_dir(i, False))
        self.set_mode(str(self._settings.value("changes_view", "list")))

    @property
    def mode(self):
        return self._mode

    def set_mode(self, mode):
        mode = "tree" if mode == "tree" else "list"
        if mode == self._mode:
            return
        self._mode = mode
        self.setProperty("changesMode", mode)
        self._settings.setValue("changes_view", mode)
        self._rebuild()

    def set_items(self, items):
        fingerprint = tuple(sorted((i["path"], i["status"], bool(i["staged"])) for i in items))
        if fingerprint == self._fingerprint:
            return False
        self._fingerprint = fingerprint
        self._items = tuple(dict(i) for i in items)
        self._rebuild()
        return True

    def _all_indexes(self, parent=None):
        from PyQt5.QtCore import QModelIndex
        parent = parent if parent is not None else QModelIndex()
        for row in range(self._model.rowCount(parent)):
            index = self._model.index(row, 0, parent)
            yield index
            yield from self._all_indexes(index)

    def file_indexes(self):
        return [index for index in self._all_indexes() if index.data(FILE_ROLE)]

    def _remember_dir(self, index, expanded):
        key = index.data(KEY_ROLE)
        if key and not index.data(FILE_ROLE):
            self._dir_state[key] = expanded

    def _rebuild(self):
        current_key = self.currentIndex().data(KEY_ROLE)
        scroll = self.verticalScrollBar().value()
        self._model.clear()
        groups = {key: [] for key, _ in GROUPS}
        for info in self._items:
            group = "conflict" if info["status"] in CONFLICTS else "staged" if info["staged"] else "changes"
            groups[group].append(info)
        for group, title in GROUPS:
            files = groups[group]
            if not files:
                continue
            root = QStandardItem(f"{title}  {len(files)}")
            root.setData(group, KEY_ROLE)
            font = root.font()
            font.setBold(True)
            root.setFont(font)
            self._model.appendRow(root)
            directories = {"": root}
            for info in sorted(files, key=lambda f: f["path"].casefold()):
                parent = root
                parts = info["path"].split("/")
                if self._mode == "tree":
                    path = ""
                    for part in parts[:-1]:
                        path = f"{path}/{part}" if path else part
                        if path not in directories:
                            item = QStandardItem(part)
                            item.setData(f"{group}/{path}/", KEY_ROLE)
                            parent.appendRow(item)
                            directories[path] = item
                        parent = directories[path]
                item = QStandardItem(parts[-1])
                item.setToolTip(f"{info['path']}\n{'已暂存' if info['staged'] else '工作区'} · {info['status']}")
                item.setData(info, FILE_ROLE)
                item.setData((group, info["path"]), KEY_ROLE)
                parent.appendRow(item)
        self.setProperty("changesMode", self._mode)
        for index in self._all_indexes():
            key = index.data(KEY_ROLE)
            if not index.data(FILE_ROLE):
                self.setExpanded(index, self._dir_state.get(key, True))
            if key == current_key:
                self.setCurrentIndex(index)
        self.verticalScrollBar().setValue(scroll)

    def _open(self, info):
        self.diff_requested.emit(info["path"], info["staged"], info["status"])

    def mouseReleaseEvent(self, event):
        index = self.indexAt(event.pos())
        info = index.data(FILE_ROLE)
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and info:
            rect = self.visualRect(index)
            if event.pos().x() >= rect.right() - 26:
                action = "conflict" if info["status"] in CONFLICTS else "unstage" if info["staged"] else "stage"
                self.action_requested.emit(action, info)
            else:
                self._open(info)

    def keyPressEvent(self, event):
        info = self.currentIndex().data(FILE_ROLE)
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and info:
            self._open(info)
            event.accept()
            return
        super().keyPressEvent(event)

    def _context_menu(self, pos):
        info = self.indexAt(pos).data(FILE_ROLE)
        if info:
            self.context_requested.emit(info, self.viewport().mapToGlobal(pos))
