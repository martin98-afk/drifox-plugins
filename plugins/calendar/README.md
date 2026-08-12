# calendar 插件 — DriFox 官方插件

在 DriFox 欢迎卡片中注入「日历」tab，月视图展示，支持上/下月切换与今天高亮，
右侧附带圆形时钟实时显示系统时间。

## 功能

- 📅 欢迎卡片新增「📅 日历」tab（mode_key=`calendar`）
- 🔄 上/下月切换（‹ › 按钮）
- ⭐ 今天高亮（蓝色圆角底色）
- 🕐 右侧圆形时钟（时/分/秒针，CSS 动画实时走动，秒针每秒跳格）
- 🌓 明暗配色自动跟随系统（`prefers-color-scheme`）
- 📆 周一起始、前后月补位日期灰显

## 安装

插件位于 `plugins/calendar/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\calendar %USERPROFILE%\.drifox\plugins\calendar /E /I /Y

# Linux / macOS
cp -r plugins/calendar ~/.drifox/plugins/
```

启动 DriFox，打开欢迎卡片，点击「📅 日历」tab 即可。

## 目录结构

```
plugins/calendar/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.ui=true）
├── __init__.py              # Python 包标记
├── ui/
│   └── __init__.py          # register_ui(registry) 入口 + 日历渲染
└── README.md                # 本文件
```

## UI 注册接口

UI 插件通过 `ui/__init__.py` 暴露 `register_ui(registry)` 函数，DriFox 启动时由 `UIPluginRegistry.load_plugin` 调用。

```python
def register_ui(registry: UIPluginRegistry) -> None:
    registry.register_welcome_tab(
        plugin_name="calendar",
        mode_key="calendar",
        label="📅 日历",
        render_func=lambda ctx: _render_calendar_html(),
    )
```

## 渲染约束

欢迎卡片骨架用 `innerHTML` 注入内容，因此：

- `<script>` 标签不会执行 → 日期网格与时钟刻度由 Python 预渲染
- 上/下月切换走 `onclick` 内联 JS（`_CAL_SHIFT_JS`，DOM API 构建格子）
- 时钟指针走纯 CSS 动画（`@keyframes cal-spin`），用负 `animation-delay`
  对齐渲染时刻的系统时间，无需 JS 定时器
- `<style>` 注入后生效 → 样式全部内联

## 参考

- DriFox UI 插件注册表：`DriFox/app/core/ui_plugin_registry.py`
- 欢迎卡片骨架：`DriFox/app/widgets/welcome_card.py`（如有）
