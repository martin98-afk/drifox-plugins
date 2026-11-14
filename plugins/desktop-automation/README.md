# Desktop Automation — DriFox 插件

桌面自动化工具（`ui_tree` / `mouse` / `keyboard` / `screenshot`），从 DriFox 主程序迁出（工具插件化）。

## 功能

| 工具 | 说明 |
|------|------|
| `ui_tree` | 读取窗口的无障碍元素树（按钮/输入框/列表项，带序号与坐标）。零第三方依赖，走 Windows 自带的 UIA。 |
| `screenshot` | 截屏并保存为 PNG（支持全屏或指定区域）。结果自动注入视觉上下文。 |
| `mouse` | 桌面鼠标操作：移动 / 单击 / 双击 / 右键 / 滚动 / 拖拽 / 查坐标。支持按元素序号操作。 |
| `keyboard` | 桌面键盘操作：输入文本 / 按单键 / 组合热键 / 直接向元素写值。 |

## 为什么要有 `ui_tree`

只靠截图 + 坐标点击，模型得先"看"出按钮在哪，再猜一个坐标。窗口挪一格、分辨率变一次、
系统缩放不是 100%，坐标全废，而且每次都失败得莫名其妙。

`ui_tree` 把界面结构直接给模型：每个可交互控件有角色、名字、坐标、稳定标识。
模型的操作从"点像素"变成"点这个按钮"，也就能在动作后验证结果。

## 安装

### 方式一：从插件市场安装

```bash
/plugin --install desktop-automation
```

### 方式二：复制到插件目录

```bash
cp -r plugins/desktop-automation ~/.drifox/plugins/
# 或 Windows
xcopy /E /I plugins\desktop-automation %USERPROFILE%\.drifox\plugins\desktop-automation
```

DriFox 启动时自动发现并加载。

## 桌面自动化开关

四个工具都需要在「设置 → 桌面自动化」中开启才能执行；未开启时返回错误提示。

`ui_tree` 与 `mouse`/`keyboard` 都标记为危险工具，默认需要用户在权限卡片中显式开启。
`ui_tree` 虽然只读，但读到的内容是整屏界面，与截图同级的敏感性。

## 使用示例

### 元素定位（推荐）

```text
ui_tree()                                          # 列出所有可交互窗口
ui_tree(app='记事本')                               # 读某个窗口的元素树
ui_tree(pid=12345, max_elements=100)               # 按进程 ID 精确定位
```

返回示例：

```json
{
  "snapshot_id": "a1b2c3d4e5f6",
  "window": {"title": "无标题 - 记事本", "pid": 12345, "rect": [100, 100, 1200, 800]},
  "elements": [
    {"i": 0, "role": "Edit", "name": "", "rect": [120, 140, 1160, 700]},
    {"i": 1, "role": "Button", "name": "发送", "rect": [1000, 760, 90, 32]}
  ]
}
```

拿到序号后：

```text
mouse(action='click', snapshot_id='a1b2c3d4e5f6', element=1)
keyboard(action='set_value', snapshot_id='a1b2c3d4e5f6', element=0, text='你好')
```

`mouse(element=...)` 优先走无障碍动作（不移动光标、不需要窗口在前台）；目标不支持时才退回坐标点击。
`keyboard(set_value=...)` 优先走 ValuePattern 直接写值；不支持时退回"点中 → 全选 → 键入"。

### 传统坐标操作

```text
screenshot()                                       # 全屏截图，保存到 ~/.drifox/screenshots/
screenshot(path='D:/tmp/win.png')                  # 自定义输出路径
screenshot(region=[100, 100, 800, 600])            # 区域截图

mouse(action='click', x=500, y=300)                # 单击
mouse(action='double_click', x=500, y=300)         # 双击
mouse(action='right_click', x=500, y=300)          # 右键
mouse(action='move', x=800, y=200, duration=0.5)   # 0.5s 过渡移动
mouse(action='scroll', dx=0, dy=-3)                # 向上滚动 3 格
mouse(action='drag', x=100, y=100, dx=200, dy=0)   # 拖拽 (100,100) → (300,100)
mouse(action='position')                           # 查询鼠标位置 + 屏幕尺寸

keyboard(action='type', text='Hello World')        # 输入文本
keyboard(action='press', key='enter')              # 按 Enter
keyboard(action='hotkey', keys='ctrl+c')           # 复制
keyboard(action='hotkey', keys='ctrl+shift+n')     # 新窗口（Chrome）
```

## 视觉注入

`screenshot` 工具返回的图片路径会被 chat_worker 识别并自动注入视觉上下文（协议 A）。
LLM 在结果返回后即可看到屏幕内容，无需再调用第二次截图。

## 架构

```
tools/desktop.py       工具注册与动作编排（UIA 优先，坐标兜底）
scripts/uia.ps1        UIA 桥：PowerShell + 系统自带 .NET UIAutomationClient
```

`uia.ps1` 每次调用起一个进程（约 1~1.5 秒），代价换来零第三方依赖：
不需要 comtypes / pywinauto / uiautomation，插件保持自包含。

## 元素直连定位（推荐用法）

不必先 `ui_tree` 拿整棵树再引序号，`mouse` / `keyboard` 支持直接按「窗口 + 元素名」定位：

```text
mouse(action="click", app="HyperFrames", name="关闭标签页")
keyboard(action="set_value", app="记事本", name="文本编辑器", text="你好")
```

规则：
- 精确名字优先，模糊匹配次之（找「点击」不会先命中「点击折叠/展开」）
- 同名多个直接拒绝并列出候选，不猜
- 实测：Chromium 窗口 154ms 命中

## 性能实测

| 场景 | 耗时 |
|---|---|
| 常驻进程单次空操作 | 0-1ms（对比每次起进程 500ms） |
| Chromium 窗口读树 | 208-777ms |
| Qt 窗口读树（元素多时） | 1.6-6.8s |
| 直连定位（精确名字） | 154-250ms |

进程常驻后，省掉的是每次约 500ms 的 PowerShell 启动 + 程序集加载。剩下的主要是 UIA 遍历本身，
取决于目标应用的 provider 实现和元素数量，省不掉。

## 已知限制与实测踩坑

这些不是理论推测，是开发时实测出来的：

1. **Chromium 系的 UIA 树按需激活。** Electron / Chrome / Edge 首次被查询时只返回窗口框
   （十几个节点），激活后才吐完整树（实测 13 → 513）。`uia.ps1` 在节点数异常少时会等 600ms
   重取一次，并在返回里带 `activated` 标记。

2. **Qt 的元素全都"支持" invoke。** Qt5 的 MSAA→UIA 桥给几乎所有元素（含 QLabel、QImage）
   都报 `IsInvokePatternAvailable=true`，所以 pattern 可用性不能用来判断可点性。裁剪只能靠
   名字 + 角色 + 面积。同理，Qt 滚动区里的元素坐标会返回内容坐标（可能为负、可能超出窗口），
   不能拿中心点判断是否在窗口内，只能算矩形交集。

3. **WinForms 的元素全是 Pane。** Button、TextBox 都被报成 `ControlType.Pane`，且
   `InvokePattern` / `ValuePattern` 全部 unsupported。这类应用只能靠 ClassName 识别
   （`WindowsForms10.BUTTON` / `.EDIT`），动作只能走坐标点击兜底。

4. **不先激活窗口，坐标点击会被吞。** Windows 对后台窗口的第一次点击只用于激活，不传给控件。
   所以坐标路径会先调 `activate`（`SetForegroundWindow`，失败时用 AttachThreadInput 和模拟
   Alt 键绕过前台锁）。

5. **DPI 坐标系不一致。** UIA 桥声明了 per-monitor DPI 感知，返回物理像素；而宿主进程若
   不是 DPI 感知的，鼠标 API 收到的是逻辑坐标。实测 225% 缩放下两者相差 2.25 倍。
   元素坐标会按 `物理宽 / 自身 GetSystemMetrics 宽` 自动换算；用户手填的 x/y 不做换算。

6. **UIA 动作能否执行取决于目标应用。** Qt 应用支持 Invoke/Value（实测可点击、可写值、可读回）；
   WinForms 不支持；WPF 通常支持。失败时自动退化为坐标 + 键盘，不会静默失败。

7. **CacheRequest 在 Qt 上是负优化。** 微软文档推荐的批量属性缓存，实测在 Qt 应用上让遍历
   从 2.7s 变成 27s（provider 要为缓存视图重建整棵树）。已移除，不要重新加上。

8. **自绘 UI 完全读不到。** 实测 ToDesk、UU 加速器这类自绘界面返回 0 个元素，
   游戏全屏窗口同理。这类目标只能用纯坐标点击，元素树对它没有意义。


## 依赖

- `pynput` — 鼠标键盘控制
- `mss` — 跨平台截屏

`ui_tree` 不引入任何新依赖（Windows 自带 .NET UIAutomationClient）。

```bash
pip install pynput mss
```

未安装时 `mouse`/`keyboard`/`screenshot` 返回导入错误，`ui_tree` 不受影响。
非 Windows 平台 `ui_tree` 返回"元素树仅支持 Windows"，其余工具正常。
