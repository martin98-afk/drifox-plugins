# Desktop Automation — DriFox 插件

桌面自动化工具（`mouse` / `keyboard` / `screenshot`），从 DriFox 主程序迁出（工具插件化）。

## 功能

| 工具 | 说明 |
|------|------|
| `screenshot` | 截屏并保存为 PNG（支持全屏或指定区域）。结果自动注入视觉上下文。 |
| `mouse` | 桌面鼠标操作：移动 / 单击 / 双击 / 右键 / 滚动 / 拖拽 / 查坐标。 |
| `keyboard` | 桌面键盘操作：输入文本 / 按单键 / 组合热键（`ctrl+c` 等）。 |

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

三个工具都需要在「设置 → 桌面自动化」中开启才能执行；未开启时返回错误提示。

## 使用示例

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

- 完全自包含：仅依赖 `pynput`（鼠标键盘）+ `mss`（截屏）+ Python 标准库
- 不依赖主程序 services，通过 `tool_ctx["env"]` 读取配置
- 渲染闭包 `_render_screenshot_body` 自带 `_extract_screenshot_image_path` 实现，
  无需主程序 `app.widgets.render_helpers` 内部 API
- 图标自包含：`tools/icons/`（深色主题）+ `tools/icons_light/`（浅色主题）

## 依赖

- `pynput` — 鼠标键盘控制
- `mss` — 跨平台截屏

```bash
pip install pynput mss
```

未安装时三个工具全部返回导入错误，不影响其他工具。