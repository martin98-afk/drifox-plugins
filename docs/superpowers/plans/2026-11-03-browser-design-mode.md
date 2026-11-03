# 内置浏览器 Design Mode 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 DriFox 内置浏览器里实现 Cursor 式 Design Mode：点页面元素，把 HTML、计算样式、元素截图追加到对话输入框。

**Architecture:** 三层分离。事件层用 Python eventFilter 挂在 `view.focusProxy()` 上，拦截鼠标；查询层用 `page.runJavaScript` 按坐标取元素数据；渲染层用 Python 侧透明 QWidget 画高亮框，不进入页面 DOM。回填走能力池 `caps_for("input.write")`。

**Tech Stack:** Python 3.14、PyQt5、Qt WebEngine（Chromium）、pytest

**Spec:** `docs/superpowers/specs/2026-11-03-browser-design-mode-design.md`

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `plugins/browser/ui/design_mode_core.py` | 新增。纯函数（rect 裁剪、样式过滤、prompt 组装）与 JS 片段。零 Qt 依赖，能独立单测 |
| `plugins/browser/ui/design_mode.py` | 新增。`DesignMode` 控制器与 `_Highlight` 覆盖层，依赖 PyQt5 |
| `plugins/browser/ui/browser_window.py` | 改。工具栏按钮、持有 `_design_mode`、退出时聚焦输入框 |
| `plugins/browser/ui/shortcuts.py` | 改。`Ctrl+Shift+C` 进入，`Esc` 优先退出模式 |
| `plugins/browser/ui/_page_factory.py` | 改。右键菜单追加「选取此元素」 |
| `plugins/browser/.drifox-plugin/plugin.json` | 改。`capabilities` 加 `input.write`，版本 1.4.4 → 1.5.0 |
| `tests/test_browser_design_mode.py` | 新增。纯函数单测 |
| `plugins/browser/README.md` | 改。功能与快捷键 |

拆分理由：`plugins/` 没有 `__init__.py`，不能当包导入；纯函数单独成 `design_mode_core.py` 后测试可用 importlib 按路径加载，不需要 PyQt5 环境。控制器单独成文件，只做状态与信号编排。

---

## Task 1: manifest 声明 input.write

**Files:**
- Modify: `plugins/browser/.drifox-plugin/plugin.json`

- [ ] **Step 1: 读取当前 manifest**

```bash
python -c "import json,io;d=json.load(io.open('plugins/browser/.drifox-plugin/plugin.json',encoding='utf-8'));print(d['version'],d['capabilities'])"
```

Expected: `1.4.4 ['tool.read', 'ui.notify', 'ui.card.show']`

- [ ] **Step 2: 追加能力并升版本**

把 `capabilities` 改成 `["tool.read", "ui.notify", "ui.card.show", "input.write"]`，`version` 改成 `"1.5.0"`。

```json
"version": "1.5.0",
"capabilities": ["tool.read", "ui.notify", "ui.card.show", "input.write"]
```

- [ ] **Step 3: 校验 schema**

```bash
python tools/validate_plugins.py
```

Expected: 无 FAIL，browser 出现在通过列表。

- [ ] **Step 4: 提交**

```bash
git add plugins/browser/.drifox-plugin/plugin.json
git commit -m "feat(browser): 声明 input.write 能力并升版本到 1.5.0"
```

---

## Task 2: 纯函数与单测

**Files:**
- Create: `plugins/browser/ui/design_mode_core.py`
- Test: `tests/test_browser_design_mode.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_browser_design_mode.py
# -*- coding: utf-8 -*-
"""design_mode_core 纯函数单测。plugins/ 无 __init__.py，走 importlib 按路径加载。"""

import importlib.util
from pathlib import Path

_CORE = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "browser" / "ui" / "design_mode_core.py"
)


def _load_core():
    spec = importlib.util.spec_from_file_location("browser_design_core", _CORE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_core()


def test_clamp_rect_expands_by_padding():
    assert core.clamp_rect(100, 100, 50, 40, 800, 600, pad=40) == (60, 60, 130, 120)


def test_clamp_rect_clips_at_viewport_edges():
    assert core.clamp_rect(0, 0, 20, 20, 800, 600, pad=40) == (0, 0, 60, 60)
    assert core.clamp_rect(780, 580, 20, 20, 800, 600, pad=40) == (740, 540, 60, 60)


def test_clamp_rect_returns_none_for_degenerate_input():
    assert core.clamp_rect(10, 10, 0, 0, 800, 600, pad=0) is None
    assert core.clamp_rect(900, 900, 10, 10, 800, 600, pad=0) is None


def test_filter_styles_keeps_whitelist_only():
    raw = {
        "display": "flex",
        "color": "rgb(0, 0, 0)",
        "cursor": "pointer",
    }
    out = dict(core.filter_styles(raw))
    assert out["display"] == "flex"
    assert out["color"] == "rgb(0, 0, 0)"
    assert "cursor" not in out


def test_filter_styles_drops_noise_values():
    raw = {"margin-top": "0px", "background-image": "none", "font-size": "16px"}
    out = dict(core.filter_styles(raw))
    assert "margin-top" not in out
    assert "background-image" not in out
    assert out["font-size"] == "16px"


def test_style_keys_has_no_duplicates():
    assert len(core.STYLE_KEYS) == len(set(core.STYLE_KEYS))


def test_build_prompt_contains_all_sections():
    text = core.build_prompt(
        index=2,
        url="https://example.com/a",
        title="示例",
        selector="div.card > h2.title",
        html='<h2 class="title">示例</h2>',
        styles=[("display", "block"), ("font-size", "20px")],
        shot_path="C:/tmp/pick_2.png",
    )
    assert "<!-- drifox-pick 2 -->" in text
    assert "https://example.com/a" in text
    assert "div.card > h2.title" in text
    assert "C:/tmp/pick_2.png" in text
    assert "<h2 class=\"title\">示例</h2>" in text
    assert "display: block" in text
    assert "font-size: 20px" in text


def test_build_prompt_omits_missing_shot():
    text = core.build_prompt(
        index=1,
        url="https://example.com",
        title="",
        selector="body",
        html="<body></body>",
        styles=[],
        shot_path=None,
    )
    assert "截图：" not in text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run python -m pytest tests/test_browser_design_mode.py -v`
Expected: FAIL，`ImportError: cannot import name` 或文件不存在

- [ ] **Step 3: 实现纯函数**

```python
# plugins/browser/ui/design_mode_core.py
# -*- coding: utf-8 -*-
"""Design Mode — 点页面元素，把 HTML/CSS/截图追加到对话输入框。

三层：
- 事件层：Python eventFilter 挂在 view.focusProxy() 上
- 查询层：page.runJavaScript 按坐标取元素数据
- 渲染层：Python 侧透明 QWidget 画高亮，不进入页面 DOM
"""

STYLE_KEYS = (
    "display", "position", "top", "right", "bottom", "left", "z-index",
    "float", "clear", "overflow", "overflow-x", "overflow-y",
    "width", "height", "min-width", "min-height", "max-width", "max-height",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "border-top", "border-right", "border-bottom", "border-left",
    "border-radius", "box-shadow", "box-sizing",
    "background-color", "background-image", "background-size", "background-position",
    "color", "opacity", "visibility",
    "font-family", "font-size", "font-weight", "font-style",
    "line-height", "letter-spacing", "text-align", "text-decoration", "white-space",
    "flex-direction", "flex-wrap", "justify-content", "align-items", "align-self",
    "gap", "row-gap", "column-gap",
    "grid-template-columns", "grid-template-rows",
    "transform", "transition", "cursor",
)

_NOISE_VALUES = frozenset({"none", "normal", "auto", "0px", "0", "rgba(0, 0, 0, 0)"})


def clamp_rect(x, y, w, h, vw, vh, pad=40):
    """元素矩形外扩 pad 并裁剪到视口内；退化输入返回 None。"""
    left = max(0, int(x) - pad)
    top = max(0, int(y) - pad)
    right = min(int(vw), int(x + w) + pad)
    bottom = min(int(vh), int(y + h) + pad)
    if right <= left or bottom <= top:
        return None
    return left, top, right - left, bottom - top


def filter_styles(raw):
    """按白名单过滤计算样式，剔除空值与我行我素的默认值。返回 [(key, value)]。"""
    out = []
    for key in STYLE_KEYS:
        value = raw.get(key)
        if not value:
            continue
        if value.strip().lower() in _NOISE_VALUES:
            continue
        out.append((key, value))
    return out


def build_prompt(*, index, url, title, selector, html, styles, shot_path):
    """把一次拾取组装成可读的 Markdown 片段。"""
    parts = [f"<!-- drifox-pick {index} -->", f"页面：{url}"]
    if title:
        parts.append(f"标题：{title}")
    parts.append(f"元素：{selector}")
    if shot_path:
        parts.append(f"截图：{shot_path}")
    parts.extend(["", "```html", html or "", "```", "", "```css"])
    parts.append("; ".join(f"{k}: {v}" for k, v in styles))
    parts.extend(["```"])
    return "\n".join(parts)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run python -m pytest tests/test_browser_design_mode.py -v`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add plugins/browser/ui/design_mode.py tests/test_browser_design_mode.py
git commit -m "feat(browser): design_mode 纯函数与单测"
```

---

## Task 3: JS 查询片段

**Files:**
- Modify: `plugins/browser/ui/design_mode_core.py`
- Test: `tests/test_browser_design_mode.py`

- [ ] **Step 1: 写失败测试**

```python
def test_js_pick_uses_element_from_point():
    script = core.js_pick(120, 340)
    assert "document.elementFromPoint(120, 340)" in script
    assert "(function(x, y)" in script


def test_js_hit_returns_rect_only():
    script = core.js_hit(10, 20)
    assert "document.elementFromPoint(10, 20)" in script
    assert "outerHTML" not in script


def test_js_pick_embeds_style_keys():
    assert "'display'" in core.js_pick(0, 0)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run python -m pytest tests/test_browser_design_mode.py -v -k js_`
Expected: FAIL，`AttributeError: module has no attribute 'js_pick'`

- [ ] **Step 3: 实现 JS 片段**

在 `design_mode_core.py` 顶部补 `import json`，并在 `build_prompt` 之后追加：

_JS_PICK_TMPL = r"""
(function(x, y) {
  var el = document.elementFromPoint(x, y);
  if (!el) return null;
  var path = [];
  var cur = el;
  while (cur && cur.nodeType === 1 && cur !== document.body) {
    var seg = cur.tagName.toLowerCase();
    if (cur.id) { seg += '#' + cur.id; path.unshift(seg); break; }
    if (typeof cur.className === 'string' && cur.className.trim()) {
      seg += '.' + cur.className.trim().split(/\s+/).slice(0, 2).join('.');
    }
    var p = cur.parentElement;
    if (p) {
      var same = Array.prototype.filter.call(p.children, function(c) {
        return c.tagName === cur.tagName;
      });
      if (same.length > 1) seg += ':nth-of-type(' + (same.indexOf(cur) + 1) + ')';
    }
    path.unshift(seg);
    cur = cur.parentElement;
  }
  var cs = getComputedStyle(el);
  var keys = __KEYS__;
  var styles = {};
  for (var i = 0; i < keys.length; i++) {
    var v = cs.getPropertyValue(keys[i]);
    if (v) styles[keys[i]] = v;
  }
  var r = el.getBoundingClientRect();
  return {
    selector: path.join(' > ') || el.tagName.toLowerCase(),
    html: (el.outerHTML || '').slice(0, 4000),
    styles: styles,
    rect: {x: r.left, y: r.top, w: r.width, h: r.height},
    text: (el.innerText || '').slice(0, 200)
  };
})(__X__, __Y__)
"""

_JS_HIT_TMPL = r"""
(function(x, y) {
  var el = document.elementFromPoint(x, y);
  if (!el) return null;
  var r = el.getBoundingClientRect();
  return {
    rect: {x: r.left, y: r.top, w: r.width, h: r.height},
    tag: el.tagName.toLowerCase()
  };
})(__X__, __Y__)
"""


def _fill(tmpl, x, y, **extra):
    out = tmpl.replace("__X__", str(int(x))).replace("__Y__", str(int(y)))
    for key, value in extra.items():
        out = out.replace(f"__{key}__", value)
    return out.strip()


def js_pick(x, y):
    """返回取完整元素信息的 JS（IIFE，不依赖页面全局函数）。"""
    return _fill(_JS_PICK_TMPL, x, y, KEYS=json.dumps(list(STYLE_KEYS)))


def js_hit(x, y):
    """返回只取矩形的 JS，用于悬停高亮。"""
    return _fill(_JS_HIT_TMPL, x, y)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run python -m pytest tests/test_browser_design_mode.py -v`
Expected: 11 passed

- [ ] **Step 5: 提交**

```bash
git add plugins/browser/ui/design_mode.py tests/test_browser_design_mode.py
git commit -m "feat(browser): design_mode 的 JS 查询片段"
```

---

## Task 4: 高亮覆盖层与事件控制器

**Files:**
- Create: `plugins/browser/ui/design_mode.py`

本 task 无自动化测试，Qt widget 行为靠 Task 8 的手测清单验收。

- [ ] **Step 1: 新建 design_mode.py 并写高亮层**

```python
# plugins/browser/ui/design_mode.py
# -*- coding: utf-8 -*-
"""Design Mode 控制器：事件拦截 + 查询 + 截图 + 回填。"""

from .design_mode_core import build_prompt, clamp_rect, filter_styles, js_hit, js_pick
from PyQt5.QtCore import QEvent, QObject, QPoint, QTimer, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QWidget


class _Highlight(QWidget):
    """元素高亮框：透明、不接收鼠标、画在 view 之上。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setCursor(Qt.CrossCursor)
        self.hide()
        self._color = QColor(64, 158, 255)

    def set_color(self, color):
        if isinstance(color, QColor):
            self._color = color
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self._color, 2))
        fill = QColor(self._color)
        fill.setAlpha(40)
        painter.setBrush(fill)
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))


class _EscFilter(QObject):
    """Esc 优先退出 Design Mode，其余按键放行。"""

    def __init__(self, mode):
        super().__init__(mode)
        self._mode = mode

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self._mode.stop()
            return True
        return False
```

- [ ] **Step 2: 同一个文件里追加控制器**

在 `_Highlight` 与 `_EscFilter` 之后追加（不要重复写 import）：

```python
class DesignMode(QObject):
    """拾取模式控制器：事件拦截 + 查询 + 截图 + 回填。"""

    HOVER_MS = 60

    def __init__(self, card):
        super().__init__(card)
        self._card = card
        self._view = None
        self._proxy = None
        self._highlight = None
        self._esc_filter = None
        self._active = False
        self._count = 0
        self._pending = False
        self._last_pos = QPoint()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.HOVER_MS)
        self._timer.timeout.connect(self._query_hover)

    def is_active(self):
        return self._active

    def toggle(self):
        if self._active:
            self.stop()
        else:
            self.start()

    def start(self):
        view = self._card._current_view()
        if view is None:
            self._card._set_status("Design Mode：当前标签不可用")
            return
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineSettings

            js_on = view.page().settings().testAttribute(
                QWebEngineSettings.JavascriptEnabled
            )
            if not js_on:
                self._card._set_status("Design Mode：当前页面禁用了 JS，无法拾取")
                return
        except Exception:
            pass
        proxy = view.focusProxy() or view
        self._view = view
        self._proxy = proxy
        self._highlight = _Highlight(view)
        self._highlight.resize(view.size())
        self._highlight.show()
        self._highlight.raise_()
        proxy.installEventFilter(self)
        self._esc_filter = _EscFilter(self)
        view.installEventFilter(self._esc_filter)
        self._active = True
        self._count = 0
        view.setFocus()
        self._card._set_status("Design Mode：点击页面元素，Esc 退出")
        self._sync_button()

    def stop(self):
        if not self._active:
            return
        self._active = False
        self._timer.stop()
        if self._proxy is not None:
            try:
                self._proxy.removeEventFilter(self)
            except RuntimeError:
                pass
        if self._view is not None and self._esc_filter is not None:
            try:
                self._view.removeEventFilter(self._esc_filter)
            except RuntimeError:
                pass
        if self._highlight is not None:
            self._highlight.deleteLater()
            self._highlight = None
        self._esc_filter = None
        self._view = None
        self._proxy = None
        self._sync_button()
        if self._count:
            self._card._set_status(f"Design Mode 已退出，共追加 {self._count} 个元素")
        else:
            self._card._set_status("Design Mode 已退出")

    def _sync_button(self):
        btn = getattr(self._card, "_btn_pick", None)
        if btn is not None:
            btn.setDown(self._active)

    def eventFilter(self, obj, event):
        if not self._active:
            return False
        kind = event.type()
        if kind == QEvent.MouseMove:
            self._last_pos = event.pos()
            if not self._timer.isActive():
                self._timer.start()
            return True
        if kind in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            return True
        if kind == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton:
                self._pick(event.pos())
            return True
        if kind == QEvent.Resize and self._highlight is not None:
            self._highlight.resize(self._view.size())
        return False

    def _to_page(self, pos):
        """focusProxy 坐标 → 页面 CSS 坐标。"""
        if self._proxy is not None and self._view is not None:
            pos = self._proxy.mapTo(self._view, pos)
        zoom = 1.0
        try:
            zoom = self._view.page().zoomFactor() or 1.0
        except Exception:
            pass
        return pos.x() / zoom, pos.y() / zoom

    def _query_hover(self):
        if not self._active or self._pending or self._view is None:
            return
        self._highlight.resize(self._view.size())
        x, y = self._to_page(self._last_pos)
        self._pending = True

        def done(result):
            self._pending = False
            if not self._active or not isinstance(result, dict):
                return
            rect = result.get("rect") or {}
            w = int(rect.get("w") or 0)
            h = int(rect.get("h") or 0)
            if w <= 0 or h <= 0:
                self._highlight.hide()
                return
            self._highlight.setGeometry(int(rect["x"]), int(rect["y"]), w, h)
            self._highlight.show()
            self._highlight.raise_()

        self._view.page().runJavaScript(js_hit(x, y), done)
```

- [ ] **Step 3: 语法校验**

```bash
python -m py_compile plugins/browser/ui/design_mode.py
```

Expected: 无输出（成功）

- [ ] **Step 4: 提交**

```bash
git add plugins/browser/ui/design_mode.py
git commit -m "feat(browser): DesignMode 控制器与高亮覆盖层"
```

---

## Task 5: 截图裁剪

**Files:**
- Modify: `plugins/browser/ui/design_mode.py`

本 task 无自动化测试，截图逻辑靠 Task 8 手测清单第 6、7 条验收。

- [ ] **Step 1: 在 design_mode.py 顶部补 import，类内追加 _capture**

顶部补：

```python
import time
from pathlib import Path


def _picks_dir():
    root = Path.home() / ".drifox" / "plugins" / "browser" / "data" / "picks"
    root.mkdir(parents=True, exist_ok=True)
    return root
```

在 `DesignMode` 类内追加（不要重复写 `class` 行）：

```python
    def _capture(self, rect, index):
        """按元素矩形（外扩 40px）裁剪当前视口截图；失败返回 None。"""
        view = self._view
        if view is None:
            return None
        pixmap = view.grab()
        if pixmap.isNull():
            return None
        dpr = view.devicePixelRatioF() or 1.0
        vw = pixmap.width() / dpr
        vh = pixmap.height() / dpr
        box = clamp_rect(
            rect.get("x", 0), rect.get("y", 0),
            rect.get("w", 0), rect.get("h", 0),
            vw, vh, pad=40,
        )
        if box is None:
            return None
        x, y, w, h = (int(round(v * dpr)) for v in box)
        cropped = pixmap.copy(x, y, w, h)
        if cropped.isNull() or cropped.width() == 0 or cropped.height() == 0:
            return None
        path = _picks_dir() / f"pick_{int(time.time() * 1000)}_{index}.png"
        if not cropped.save(str(path), "PNG"):
            return None
        return path
```

- [ ] **Step 2: 语法校验**

```bash
python -m py_compile plugins/browser/ui/design_mode.py
```

Expected: 无输出

- [ ] **Step 3: 提交**

```bash
git add plugins/browser/ui/design_mode.py
git commit -m "feat(browser): Design Mode 元素截图裁剪"
```

---

## Task 6: 拾取与回填

**Files:**
- Modify: `plugins/browser/ui/design_mode.py`

- [ ] **Step 1: 在 DesignMode 类内追加拾取与回填**

```python
    def _pick(self, pos):
        if self._view is None:
            return
        x, y = self._to_page(pos)
        view = self._view

        def done(result):
            if not self._active or not isinstance(result, dict):
                self._card._set_status("Design Mode：该位置取不到元素")
                return
            self._count += 1
            styles = filter_styles(result.get("styles") or {})
            shot = self._capture(result.get("rect") or {}, self._count)
            text = build_prompt(
                index=self._count,
                url=view.url().toString(),
                title=view.title(),
                selector=result.get("selector") or "unknown",
                html=result.get("html") or "",
                styles=styles,
                shot_path=str(shot) if shot else None,
            )
            ok = self._write(text)
            if ok:
                self._card._set_status(
                    f"Design Mode：已追加第 {self._count} 个元素（Esc 退出）"
                )
            else:
                self._card._set_status("Design Mode：已拾取，但输入框写入失败")

        view.page().runJavaScript(js_pick(x, y), done)

    def _write(self, text):
        """经能力池写入输入框。首次覆盖，后续追加，全程不抢焦点。"""
        try:
            from app.plugins.sdk import caps_for

            write = caps_for("input.write", plugin="browser", surface="ui")
        except Exception:
            write = None
        if write is None:
            return False
        try:
            write(text, append=self._count > 1, focus=False)
            return True
        except Exception:
            return False
```

- [ ] **Step 2: 语法校验**

```bash
python -m py_compile plugins/browser/ui/design_mode.py
```

Expected: 无输出

- [ ] **Step 3: 提交**

```bash
git add plugins/browser/ui/design_mode.py
git commit -m "feat(browser): Design Mode 拾取与 input.write 回填"
```

---

## Task 7: 三处入口接线

**Files:**
- Modify: `plugins/browser/ui/browser_window.py`
- Modify: `plugins/browser/ui/shortcuts.py`
- Modify: `plugins/browser/ui/_page_factory.py`

- [ ] **Step 1: 工具栏按钮**

在 `browser_window.py` 的 `_btn_bookmark` 创建之前插入：

```python
        # Design Mode（拾取页面元素 → 回填输入框）
        self._btn_pick = self._make_tool_btn("⌖", "选取页面元素 (Ctrl+Shift+C)")
        self._btn_pick.clicked.connect(self._toggle_design_mode)
        tly.addWidget(self._btn_pick)
```

- [ ] **Step 2: 卡片持有控制器**

在 `BrowserWindowCard.__init__` 里 `self._loader = AsyncDataLoader(self)` 之后插入：

```python
        self._design_mode = None
```

在类中追加方法：

```python
    def _toggle_design_mode(self):
        from .design_mode import DesignMode

        if self._design_mode is None:
            self._design_mode = DesignMode(self)
        self._design_mode.toggle()

    def _exit_design_mode(self):
        """切标签、导航、关卡片时调用，幂等。"""
        mode = getattr(self, "_design_mode", None)
        if mode is not None:
            mode.stop()

    def _focus_input(self):
        """退出拾取后把焦点交还输入框（input.write 已填好内容）。"""
        try:
            from app.plugins.sdk import caps_for

            write = caps_for("input.write", plugin="browser", surface="ui")
            if write is not None:
                write("", append=True, focus=True)
        except Exception:
            pass
```

- [ ] **Step 3: 切标签与导航退出**

在 `browser_window.py` 的 `_on_load_started(self, view)` 方法体首行插入：

```python
        self._exit_design_mode()
```

在 `_on_tab_changed(self, idx)` 方法体首行插入同一句。方法已存在于 `browser_window.py:420`，不要新建。

- [ ] **Step 4: 快捷键**

在 `shortcuts.py` 的 `install_shortcuts` 末尾追加：

```python
    sc = QShortcut(QKeySequence("Ctrl+Shift+C"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(card._toggle_design_mode)
```

把 Esc 的处理改为优先退出模式：

```python
    def _on_escape():
        if card._design_mode is not None and card._design_mode.is_active():
            card._design_mode.stop()
            card._focus_input()
            return
        card._stop()
        card._menu_panel.setVisible(False)

    sc = QShortcut(QKeySequence("Esc"), card)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(_on_escape)
```

- [ ] **Step 5: 右键菜单**

在 `_page_factory.py` 的 `show_context_menu` 里，找到 `owner = getattr(new_page_callback, "__self__", None)` 那一段之后、`if link_url.isValid() and not link_url.isEmpty():` 之前，插入：

```python
        if owner is not None and hasattr(owner, "_toggle_design_mode"):
            menu.addAction("选取此元素", owner._toggle_design_mode)
            menu.addSeparator()
```

- [ ] **Step 6: 语法校验**

```bash
python -m py_compile plugins/browser/ui/browser_window.py plugins/browser/ui/shortcuts.py plugins/browser/ui/_page_factory.py
```

Expected: 无输出

- [ ] **Step 7: 提交**

```bash
git add plugins/browser/ui/browser_window.py plugins/browser/ui/shortcuts.py plugins/browser/ui/_page_factory.py
git commit -m "feat(browser): Design Mode 三处入口接线"
```

---

## Task 8: 文档与验证

**Files:**
- Modify: `plugins/browser/README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: README 增加功能说明**

在「## 功能」列表末尾追加：

```markdown
- **Design Mode**：`Ctrl+Shift+C` 或工具栏 ⌖ 进入拾取模式，点页面元素把 HTML、计算样式和元素截图追加到对话输入框；可连续点多个，`Esc` 退出。截图存在 `~/.drifox/plugins/browser/data/picks/`
```

在快捷键表追加一行：

```markdown
| `Ctrl+Shift+C` | 进入/退出 Design Mode（选取页面元素） |
```

- [ ] **Step 2: CHANGELOG 记一条**

```markdown
### browser 1.5.0
- ✨ 新增 Design Mode：点页面元素，HTML/CSS/截图直接进对话输入框
- 🎨 刷新/停止按钮移到地址栏右侧
```

- [ ] **Step 3: 跑插件校验**

```bash
python tools/validate_plugins.py
```

Expected: 无 FAIL

- [ ] **Step 4: 重新生成市场索引**

```bash
python tools/generate_marketplace.py
```

Expected: `marketplace.json` / `downloads_cache.json` 更新

- [ ] **Step 5: 跑单测**

```bash
uv run python -m pytest tests/test_browser_design_mode.py -v
```

Expected: 11 passed

- [ ] **Step 6: 手测清单（必须在客户端里跑）**

| # | 场景 | 期望 |
|---|---|---|
| 1 | 打开 `example.com`，`Ctrl+Shift+C`，移动鼠标 | 元素被蓝色框高亮，光标是十字 |
| 2 | 点段落 `<p>` | 输入框出现一段，含 HTML/CSS/截图路径 |
| 3 | 输入框焦点是否被抢走 | 否，仍能继续点页面 |
| 4 | 连点 3 个元素 | 输入框累计 3 段，编号 1/2/3 |
| 5 | 按 `Esc` | 模式退出，光标恢复，焦点回到输入框 |
| 6 | 滚动到视口外元素再点 | 截图正确，不偏移 |
| 7 | Windows 显示缩放 150% | 截图仍与元素对齐 |
| 8 | 切到另一个标签 | 模式自动退出 |

- [ ] **Step 7: 提交**

```bash
git add plugins/browser/README.md CHANGELOG.md marketplace.json downloads_cache.json
git commit -m "docs(browser): Design Mode 说明与 1.5.0 变更记录"
```

---

## 已知风险

| 风险 | 处置 |
|---|---|
| `view.focusProxy()` 返回 None | 代码已回退到 `view` 本身；若高亮不跟随，在 `start()` 里打日志确认 |
| `runJavaScript` 在复杂页面超过 60ms | 把 `HOVER_MS` 调到 100 |
| `grab()` 拿旧帧 | 截图偶发偏差时，在 `_pick` 里改为 `QTimer.singleShot(80, ...)` 再截 |
| 页面禁用 JS | `runJavaScript` 无回调，超时后用户会看到无反应；在 `start()` 里检查 `settings().testAttribute(JavascriptEnabled)` |

---

## 明确不做

- matchedCSSRules / 样式来源定位
- 跨域 iframe 内部元素
- 页面内画框批注
- 长截图拼接
