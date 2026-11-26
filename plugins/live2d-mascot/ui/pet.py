# -*- coding: utf-8 -*-
"""桌面看板窗口 —— Qt 原生 OpenGL 渲染 Live2D

为什么不用欢迎卡片的 WebView：宿主 WebEngine 没有 WebGL（实测
getContext('webgl') 返回 null，启动参数带 --disable-gpu-compositing），
pixi/Cubism Web SDK 那条路跑不起来。走 Qt 原生后是真的连续形变：
呼吸、眨眼、视线跟随、点击换表情都由 Cubism Native SDK 实时计算。

关键约束：
- live2d-py 固定 1.0.0：1.1.1 在本机 macOS 26 / Apple Silicon 上 glInit 段错误。
- 必须用兼容上下文（OpenGL 2.1 / GLSL 120）；Core Profile 3.3 下 shader 编译失败。
- 模型中心锚定在视口右上角，缩放围绕该点；适配参数靠首帧测包围盒自动标定，
  换模型不需要改常量。
"""

import json
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_PLATFORM_DIR = {"darwin": "darwin", "win32": "win32"}.get(sys.platform, "linux")
_DEPS = _PLUGIN_DIR / "deps" / _PLATFORM_DIR
if _DEPS.is_dir() and str(_DEPS) not in sys.path:
    sys.path.insert(0, str(_DEPS))

from PyQt5.QtCore import QPoint, QRect, QSettings, Qt, QTimer
from PyQt5.QtGui import QCursor, QImage, QOpenGLWindow, QSurfaceFormat
from PyQt5.QtWidgets import QApplication, QMenu, QAction

# live2d 包在 import 时往 stdout 打 banner；GUI 宿主里 sys.stdout 可能是 None，
# print 会抛 AttributeError 直接把整个 ui 组件带崩，先兜住
import os
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import live2d

MODEL_ROOT = _PLUGIN_DIR / "web" / "model"
_REF_SCALE = 0.2
_FILL_RATIO = 0.92
_MIN_SIZE = 200
_MAX_SIZE = 640
_SNAP_PX = 24
_inited = False
_windows = []


def _settings():
    """持久化到 QSettings（macOS 上是 ~/Library/Preferences 下的 plist）"""
    return QSettings("DriFoxPlugins", "live2d-mascot")


def ensure_live2d():
    """live2d.init() 全局只需一次（加载 shader 目录）"""
    global _inited
    if _inited:
        return
    live2d.init()
    _inited = True


_LOG_PATH = Path.home() / "Library" / "Application Support" / "Drifox" / ".drifox" / "plugin_data" / "live2d-mascot" / "pet.log"


def log(msg):
    """写一行诊断日志（宿主日志抓不到 Python 侧异常，自留一份）"""
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        import datetime
        import os
        with open(_LOG_PATH, "a", encoding="utf-8") as fp:
            fp.write(f"{datetime.datetime.now():%H:%M:%S} [pid {os.getpid()}] {msg}\n")
    except Exception:
        pass


def list_models():
    """枚举 web/model/<name>/<name>.model3.json，返回目录名列表"""
    if not MODEL_ROOT.is_dir():
        return []
    return sorted(p.name for p in MODEL_ROOT.iterdir()
                  if p.is_dir() and (p / (p.name + ".model3.json")).is_file())


def model_path(name):
    """模型入口文件的绝对路径"""
    return str(MODEL_ROOT / name / (name + ".model3.json"))


class PetWindow(QOpenGLWindow):
    """无边框透明置顶的 Live2D 看板窗

    用 QOpenGLWindow 而不是 QOpenGLWidget：宿主主窗口里已有 WebEngine 等
    GL 使用者，QOpenGLWidget 走 widget 合成路径会污染宿主的 framebuffer
    （实测召唤后主界面出现残影与文字错乱）。QOpenGLWindow 是独立 QWindow，
    自带 GL 上下文，与主窗口只做窗口级合成。
    """

    def __init__(self, model_name, size=380):
        super().__init__()
        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        fmt.setDepthBufferSize(0)
        fmt.setStencilBufferSize(0)
        fmt.setVersion(2, 1)
        fmt.setProfile(QSurfaceFormat.NoProfile)
        self.setFormat(fmt)
        self.setFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setTitle("看板")
        self._model_name = model_name
        self._timer = 0
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save_state)
        self._restore_state(size)
        self._model = None
        self._frames = 0
        self._scale = _REF_SCALE
        self._offset = (0.0, 0.0)
        self._calibrated = False
        self._calib_stage = 0
        self._measuring = False
        self._drag_from = None
        self._window_from = None
        self._expressions = []
        self._exp_index = -1

    # ---- 状态持久化 / 屏幕定位 ----
    def _restore_state(self, default_size):
        s = _settings()
        size = int(s.value("pet/size", default_size))
        size = max(_MIN_SIZE, min(_MAX_SIZE, size))
        self.resize(size, size)
        on_top = str(s.value("pet/on_top", "true")).lower() in ("true", "1")
        flags = Qt.FramelessWindowHint | Qt.Tool
        if on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setFlags(flags)
        pos = s.value("pet/pos")
        if isinstance(pos, QPoint) and self._pos_on_screen(pos, size):
            self.setPosition(pos)
        else:
            self._place_default(size)

    def _pos_on_screen(self, pos, size):
        """位置是否还落在某块屏幕的可用区域内（拔掉副屏后不能跑到虚空）"""
        for screen in QApplication.screens():
            avail = screen.availableGeometry()
            visible = avail.intersected(QRect(pos.x(), pos.y(), size, size))
            if visible.width() > size * 0.3 and visible.height() > size * 0.3:
                return True
        return False

    def _place_default(self, size):
        """默认落位：主屏右下角，留出 Dock 与边缘间距"""
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        if avail is None:
            self.setPosition(100, 100)
            return
        self.setPosition(avail.right() - size - 32, avail.bottom() - size - 24)

    def _save_state(self):
        s = _settings()
        s.setValue("pet/size", self.width())
        s.setValue("pet/pos", self.position())
        s.setValue("pet/on_top", bool(self.flags() & Qt.WindowStaysOnTopHint))
        s.setValue("pet/click_through", self._click_through())
        s.setValue("pet/model", self._model_name)

    def moveEvent(self, event):
        self._save_timer.start()
        super().moveEvent(event)

    def resizeEvent(self, event):
        self._save_timer.start()
        super().resizeEvent(event)

    def _snap_to_edge(self):
        """松手后吸到最近的屏幕边缘（多屏按窗口中心所在屏算）"""
        center = self.geometry().center()
        screen = QApplication.screenAt(center) or self.screen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        here = self.position()
        x, y, w, h = here.x(), here.y(), self.width(), self.height()
        if abs(x - avail.left()) < _SNAP_PX:
            x = avail.left()
        elif abs(avail.right() - (x + w)) < _SNAP_PX:
            x = avail.right() - w
        if abs(y - avail.top()) < _SNAP_PX:
            y = avail.top()
        elif abs(avail.bottom() - (y + h)) < _SNAP_PX:
            y = avail.bottom() - h
        if (x, y) != (here.x(), here.y()):
            self.setPosition(x, y)

    # ---- 显示 / 性能 ----
    def showEvent(self, event):
        if not self._timer:
            self._timer = self.startTimer(16)
        super().showEvent(event)

    def hideEvent(self, event):
        if self._timer:
            self.killTimer(self._timer)
            self._timer = 0
        super().hideEvent(event)

    # ---- 鼠标穿透 ----
    def _click_through(self):
        return bool(self.flags() & Qt.WindowTransparentForInput)

    def set_click_through(self, on):
        """穿透后窗口不再接收任何鼠标事件（只能从控制页关回来）"""
        flags = self.flags()
        if on:
            flags |= Qt.WindowTransparentForInput
        else:
            flags &= ~Qt.WindowTransparentForInput
        self.setFlags(flags)
        self.show()
        self._save_state()

    def initializeGL(self):
        log("initializeGL enter")
        ensure_live2d()
        live2d.glInit()
        log("glInit ok")
        self._model = live2d.Model()
        self._model.LoadModelJson(model_path(self._model_name))
        self._model.Resize(self.width(), self.height())
        self._model.SetScale(_REF_SCALE)
        self._model.SetOffset(0.0, 0.0)
        log("model loaded " + self._model_name)
        self._expressions = self._read_expressions()
        self._timer = self.startTimer(16)

    def resizeGL(self, w, h):
        if self._model:
            self._model.Resize(w, h)
            self._calibrated = False
            self._frames = 0

    def paintGL(self):
        if self._frames == 0:
            log("first paintGL")
        live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)
        if self._model is None:
            return
        self._model.Update()
        self._model.Draw()
        self._frames += 1
        if self._frames % 120 == 0:
            log("tick frames=%d exposed=%s visible=%s" % (self._frames, self.isExposed(), self.isVisible()))
        if not self._calibrated and not self._measuring and self._frames >= 3:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self._calibrate)

    def timerEvent(self, event):
        self.update()

    def _bbox_from_vertices(self):
        """用 MVP + 顶点算模型在视口中的包围盒

        不走 grabFramebuffer：QOpenGLWindow 在宿主里抓回来是全透明
        （bbox=None，标定直接放弃，模型永远停在画布外看不见）。
        顶点数据由 Cubism 直接给出，与平台/合成无关。
        """
        model = self._model
        if model is None:
            return None
        mvp = model.GetMvp()
        count = len(model.GetDrawableIds())
        w, h = self.width(), self.height()
        xs, ys = [], []
        for index in range(count):
            try:
                verts = model.GetDrawableVertices(index)
            except Exception:
                continue
            if not verts:
                continue
            for i in range(0, len(verts) - 1, 2):
                x, y = verts[i], verts[i + 1]
                xp = mvp[0] * x + mvp[4] * y + mvp[12]
                yp = mvp[1] * x + mvp[5] * y + mvp[13]
                wp = mvp[3] * x + mvp[7] * y + mvp[15]
                if wp:
                    xp /= wp
                    yp /= wp
                xs.append((xp + 1.0) * 0.5 * w)
                ys.append((1.0 - yp) * 0.5 * h)
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys), w, h

    def _calibrate(self):
        """两步标定：先按参考缩放测尺寸算 scale，再按目标 scale 测中心算 offset

        不做「缩放锚点在哪」的假设 —— 不同宿主/上下文下锚点不一样
        （Qt 与 GLFW 实测就不同），用两次实测反推最稳。
        """
        bbox = self._bbox_from_vertices()
        log("calibrate stage=%d bbox=%r size=%sx%s" % (self._calib_stage, bbox, self.width(), self.height()))
        if not bbox:
            self._calibrated = True
            return
        left, top, right, bottom, w, h = bbox
        if self._calib_stage == 0:
            box_h = max(bottom - top, 1)
            k = (_FILL_RATIO * h) / box_h
            self._scale *= k
            self._model.SetScale(self._scale)
            self._model.SetOffset(0.0, 0.0)
            self._calib_stage = 1
            self._frames = 0
            return
        # 第二次：中心偏差换算成 offset（1 单位 = 一个视口宽/高，x 正右、y 正上）
        cx = (left + right) / 2.0
        cy = (top + bottom) / 2.0
        ox = (w / 2.0 - cx) / w
        oy = -(h / 2.0 - cy) / h
        self._offset = (ox, oy)
        self._model.SetOffset(ox, oy)
        self._calibrated = True
        log("calibrated scale=%.4f offset=(%.4f, %.4f)" % (self._scale, ox, oy))

    def _calibrate(self):
        """两步标定：先按参考缩放测尺寸算 scale，再按目标 scale 测中心算 offset

        不做「缩放锚点在哪」的假设 —— 不同宿主/上下文下锚点不一样
        （Qt 与 GLFW 实测就不同），用两次实测反推最稳。
        """
        bbox = self._bbox_from_vertices()
        log("calibrate stage=%d bbox=%r size=%sx%s" % (self._calib_stage, bbox, self.width(), self.height()))
        if not bbox:
            self._calibrated = True
            return
        left, top, right, bottom, w, h = bbox
        if self._calib_stage == 0:
            box_h = max(bottom - top, 1)
            k = (_FILL_RATIO * h) / box_h
            self._scale *= k
            self._model.SetScale(self._scale)
            self._model.SetOffset(0.0, 0.0)
            self._calib_stage = 1
            self._frames = 0
            return
        # 第二次：中心偏差换算成 offset（1 单位 = 一个视口宽/高，x 正右、y 正上）
        cx = (left + right) / 2.0
        cy = (top + bottom) / 2.0
        ox = (w / 2.0 - cx) / w
        oy = -(h / 2.0 - cy) / h
        self._offset = (ox, oy)
        self._model.SetOffset(ox, oy)
        self._calibrated = True
        log("calibrated scale=%.4f offset=(%.4f, %.4f)" % (self._scale, ox, oy))

    def _read_expressions(self):
        """从 model3.json 读表情 id，点击循环切换"""
        try:
            with open(model_path(self._model_name), encoding="utf-8") as fp:
                refs = json.load(fp).get("FileReferences", {})
            return [e.get("Name") for e in (refs.get("Expressions") or []) if e.get("Name")]
        except Exception:
            return []

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_from = event.screenPos()
            self._window_from = self.position()
        elif event.button() == Qt.RightButton:
            self._show_menu(event.screenPos())

    def wheelEvent(self, event):
        step = 24 if event.angleDelta().y() > 0 else -24
        size = max(_MIN_SIZE, min(_MAX_SIZE, self.width() + step))
        if size != self.width():
            self.resize(size, size)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.hide()

    def mouseMoveEvent(self, event):
        if self._model:
            self._model.Drag(event.x(), event.y())
        if self._drag_from is not None:
            self.setPosition(self._window_from + (event.screenPos() - self._drag_from).toPoint())

    def mouseReleaseEvent(self, event):
        if self._drag_from is not None:
            moved = (event.screenPos() - self._drag_from).manhattanLength()
            self._drag_from = None
            if moved < 4 and event.button() == Qt.LeftButton:
                self._next_expression()
            else:
                self._snap_to_edge()

    def _next_expression(self):
        if not self._expressions or not self._model:
            return
        self._exp_index = (self._exp_index + 1) % len(self._expressions)
        try:
            self._model.SetExpression(self._expressions[self._exp_index])
        except Exception:
            pass

    def _show_menu(self, pos):
        menu = QMenu()
        act_top = QAction("窗口置顶", menu)
        act_top.setCheckable(True)
        act_top.setChecked(bool(self.flags() & Qt.WindowStaysOnTopHint))
        act_top.triggered.connect(self._toggle_top)
        menu.addAction(act_top)
        act_through = QAction("鼠标穿透", menu)
        act_through.setCheckable(True)
        act_through.setChecked(self._click_through())
        act_through.triggered.connect(self.set_click_through)
        menu.addAction(act_through)
        menu.addSeparator()
        act_hide = QAction("收起看板", menu)
        act_hide.triggered.connect(self.hide)
        menu.addAction(act_hide)
        menu.exec_(QCursor.pos())

    def set_on_top(self, on):
        """切换置顶（setWindowFlags 后必须 show 才生效）"""
        flags = self.flags()
        if on:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setFlags(flags)
        self.show()
        self._save_state()

    def _toggle_top(self, checked):
        self.set_on_top(checked)

    def closeEvent(self, event):
        """收集起，不销毁

        live2d 的 GlState 绑在首次 glInit 的上下文上；窗口销毁后再建新窗口
        会再次 glInit，渲染不再落到新窗口（表现为「隐藏后再也出不来」）。
        这里把关闭一律降级为隐藏，整个进程只保留一个 GL 上下文。
        """
        event.ignore()
        self._save_state()
        self.hide()


def summon(model_name="", size=0):
    """召唤看板（同模型已开则前置）；返回窗口实例或 None"""
    log("summon called, model_root=" + str(MODEL_ROOT))
    models = list_models()
    log("models=" + repr(models))
    if not models:
        return None
    saved = str(_settings().value("pet/model", ""))
    preferred = model_name or saved
    name = preferred if preferred in models else models[0]
    for win in _windows:
        if win._model_name == name:
            win.show()
            win.raise_()
            win.requestActivate()   # QWindow 没有 activateWindow
            return win
    try:
        win = PetWindow(name, size or 380)
    except Exception as exc:
        log("PetWindow ctor failed: " + repr(exc))
        raise
    _windows.append(win)
    win.show()
    win.raise_()
    log("shown visible=%s exposed=%s geometry=%r flags=%r" % (
        win.isVisible(), win.isExposed(), win.geometry(), int(win.flags())))
    return win


def dismiss():
    """收起全部看板窗（只隐藏，保上下文）"""
    for win in list(_windows):
        win._save_state()
        win.hide()
