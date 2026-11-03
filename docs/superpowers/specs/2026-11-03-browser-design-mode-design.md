# 内置浏览器 Design Mode 设计文档

> 日期：2026-11-03
> 状态：待用户评审
> 关联：`plugins/browser/`，对照 Cursor Agents Window 的 Design Mode

---

## 1. 背景与目标

Cursor 的 Design Mode 允许用户直接点浏览器里的元素，把它的 HTML、CSS 和截图送进 Agent 的 prompt。本设计在 DriFox 内置浏览器（`plugins/browser`，Qt WebEngine）里实现同等能力，不修改主程序。

目标交互：

1. `Ctrl+Shift+C`（或工具栏按钮、右键菜单）进入拾取模式
2. 鼠标移动时元素被高亮
3. 点击后，元素截图 + HTML + 计算样式 + 选择器路径 + 页面地址被追加到对话输入框
4. 可以连续点多个元素，每点一次追加一段
5. `Esc` 或再点一次按钮退出

---

## 2. 需求澄清结论（用户已确认）

| 问题 | 决定 |
|---|---|
| 入口 | 工具栏按钮 + `Ctrl+Shift+C` + 右键菜单「选取此元素」，三条路径 |
| 收尾方式 | 常驻模式，边选边追加，`Esc` 或再点按钮退出 |
| 截图范围 | 元素矩形外扩 40px，裁剪到视口内 |
| 回填通道 | 能力池 `input.write`，不直接访问 `main_widget.input_area` |

---

## 3. 架构

```
browser_window.py    入口与状态：按钮/快捷键/右键菜单，持有 _design_mode 实例
design_mode.py       新增：事件过滤、高亮覆盖层、截图裁剪、prompt 组装
_page_factory.py     右键菜单追加「选取此元素」
```

三段职责分离：

| 层 | 位置 | 职责 |
|---|---|---|
| 事件层 | Python，`view.focusProxy()` | 拦截鼠标与键盘，掌控模式开关 |
| 查询层 | 页面 JS，`page.runJavaScript` | 两个无状态函数，按坐标返回元素数据 |
| 渲染层 | Python，透明覆盖 `QWidget` | 画高亮框，不进入页面 DOM |

---

## 4. 关键设计决定

### 4.1 高亮框画在 Python 侧，不注入页面 DOM

页面内 overlay 的 `z-index` 会被页面自身样式压过，且会被页面的 capture 监听干扰，导航后还要重新注入。Python 侧用一个 `WA_TransparentForMouseEvents` 的覆盖 widget：不受页面样式影响、不改 DOM、退出时 `deleteLater()` 即消失。

### 4.2 鼠标事件挂在 `focusProxy()` 上

Qt WebEngine 的实际渲染控件是 `view.focusProxy()`，事件装在 `QWebEngineView` 本身收不到。过滤器内统一换算：

```python
pos = proxy.mapTo(view, event.pos())   # 相对 view 的逻辑坐标
css_x, css_y = pos.x(), pos.y()        # zoomFactor==1 时等于 CSS px
```

当前插件未实现页面缩放（全仓无 `zoomFactor` 调用），因此换算到此为止。若将来加缩放，必须改成 `pos.x() / page.zoomFactor()`，这一行会写在代码注释里。

### 4.3 事件流

| 事件 | 处理 |
|---|---|
| `MouseMove` | 节流 60ms，用一个 in-flight 标志防止查询堆积 |
| `MouseButtonPress` / `Release` / `DblClick` | 一律吞掉，press 与 release 必须成对，否则页面会残留按下状态 |
| `KeyPress` Esc | 退出模式 |
| 标签切换 / 页面导航 | 自动退出（过滤器绑定在具体 view 上） |

### 4.4 两个无状态 JS 函数

通过 `runJavaScript` 按需调用，不做常驻监听、不用 `QWebChannel`：

```js
__dfxHit(x, y)   // → {tag, id, cls, rect}          悬停高亮用，轻量
__dfxPick(x, y)  // → {selector, html, styles, rect, text}  点击时用
```

`__dfxPick` 的取元素方式用 `document.elementFromPoint(x, y)`，而不是事件 target。

选择器生成：从目标节点向上回溯，每层拼 `tag#id.class:nth-of-type(n)`，遇到带 id 的祖先或 `body` 停止，最终拼接成唯一路径。

样式过滤走白名单，只保留视觉相关项：

```
display position top/right/bottom/left z-index float clear overflow
width height min/max-width min/max-height
margin* padding* border* border-radius box-shadow
background* color opacity
font-family font-size font-weight font-style line-height letter-spacing text-align
flex* grid* gap align-* justify-* transform transition
```

`outerHTML` 截断到 4000 字符，超出加 `<!-- truncated -->`。

### 4.5 截图

```python
pixmap = view.grab()                     # 必须是可见状态
dpr = view.devicePixelRatioF()
rect = 元素矩形外扩 40px，再 clamp 到 [0, viewport_w] × [0, viewport_h]
cropped = pixmap.copy(round(x*dpr), round(y*dpr), round(w*dpr), round(h*dpr))
```

三条硬约束：

1. `view.grab()` 在 view 隐藏时必然返回空白（`control_server.py:109` 已踩过），进入模式前必须确认可见，不可见时复用 `_ensure_browser()` 的显示逻辑
2. 元素不在视口内时，先 `scrollIntoView({block:'center'})`，等 100ms 重新取矩形，再截图
3. `grab()` 拿的是当前合成帧，滚动后可能滞后一帧，等待期间用一个 `QTimer.singleShot` 串起来

### 4.6 回填内容与焦点

每段追加的文本格式：

```markdown
<!-- drifox-pick 2 -->
页面：https://example.com/path
元素：div.card > h2.title:nth-of-type(1)
截图：C:\Users\...\.drifox\plugins\browser\data\picks\pick_1730_2.png

```html
<h2 class="title">示例</h2>
```

```css
display: block; font-size: 20px; color: rgb(31, 41, 55); ...
```
```

回填调用：

```python
write(text, append=not first, focus=False)
```

`focus=False` 是必须的：焦点一旦跑到输入框，用户就没法继续点页面，整个「边选边追加」的设计会断掉。退出模式时才补一次 `focus=True`，并在 `ui.notify` 里报一句「已追加 N 个元素」。

---

## 5. 边界与降级

| 场景 | 行为 |
|---|---|
| `input.write` 不可用 | `ui.notify` 提示「宿主未提供 input.write」，截图仍落盘并告知路径 |
| 元素在视口外 | 先滚动居中，再取矩形 |
| closed shadow DOM | `elementFromPoint` 只返回 host，提示「该元素在封闭 Shadow DOM 内，只能选到宿主」 |
| 跨域 iframe | 只能选到 iframe 容器本身 |
| 页面禁用 JS | 模式不可启动，提示原因 |
| view 不可见 | 自动显示浏览器卡片后继续 |
| 连续快速点击 | in-flight 标志丢弃并发查询，只处理最后一次 |

---

## 6. 状态机

```
off ──(按钮/快捷键/右键)──> picking
picking ──(Esc/再点按钮)──> off
picking ──(切换标签/导航/卡片关闭)──> off
```

`picking` 期间：工具栏按钮保持按下视觉状态，鼠标光标切到 crosshair（覆盖层设置 `Qt.CrossCursor`）。

---

## 7. 验证方法

**手测清单**（`example.com` + 一个自建的多层布局页面）：

1. 有 id 的元素、无 id 只有 class 的元素、嵌套 5 层以上的元素
2. 视口内的元素、需要滚动才能看到的元素
3. 带 `::before` 装饰的元素
4. iframe 容器
5. 连续点 3 个元素，检查输入框里是否 3 段齐全、焦点是否仍在浏览器
6. Windows 125% / 150% 缩放下截图是否错位

**单测**（按仓库既有约定放根 `tests/`）：

- 选择器生成函数：给定 DOM 树快照，输出稳定路径
- 样式过滤函数：白名单外属性必须被剔除
- 裁剪矩形函数：越界输入必须被 clamp

**验收判据**：把一段回填内容直接发给模型，模型能凭截图路径读到图、凭 CSS 说出该元素的主色与字号。

---

## 8. 不做

- CDP / `matchedCSSRules`（要开 `QTWEBENGINE_REMOTE_DEBUGGING`，进程启动时读环境变量，插件改不了）
- 跨域 iframe 内部元素
- 页面内画框批注、语音输入
- 整页长截图拼接
- 元素样式来源定位（哪个 CSS 文件哪一行）

---

## 9. 文件清单

| 文件 | 改动 |
|---|---|
| `plugins/browser/ui/design_mode.py` | 新增，约 350 行 |
| `plugins/browser/ui/browser_window.py` | 工具栏按钮、快捷键、状态持有、退出聚焦 |
| `plugins/browser/ui/_page_factory.py` | 右键菜单追加一项 |
| `plugins/browser/.drifox-plugin/plugin.json` | `capabilities` 加 `input.write`，版本 1.4.4 → 1.5.0 |
| `plugins/browser/README.md` | 功能说明与快捷键表 |
| `tests/test_browser_design_mode.py` | 新增，纯函数单测 |
| `marketplace.json` / `downloads_cache.json` | 改完 manifest 后跑 `tools/generate_marketplace.py` 重新生成 |

---

## 10. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| `focusProxy()` 在部分 Qt 版本返回 None | 模式无法启动 | 回退到 `view` 本身，启动时探一次并记日志 |
| `runJavaScript` 的 IPC 延迟在复杂页面上超过 100ms | 高亮跟手性差 | 节流上调到 100ms，移动时不查 HTML 只查矩形 |
| 部分页面拦截 `elementFromPoint`（极少见） | 取不到元素 | 降级用 `e.target`，但需要恢复页面事件监听，暂不实现，直接提示失败 |
| 截图在 GPU 合成路径下偶发空白 | 回填缺图 | 检测到全白 pixmap 时重试一次，仍失败则只回填文本 |
