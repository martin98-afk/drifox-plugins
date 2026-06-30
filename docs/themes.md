# themes 组件

themes 是 DriFox 的视觉主题方案。每个主题是 `themes/<theme-name>/<theme-name>.yaml`，定义窗口、背景、卡片、文本等颜色 token。

## 文件位置

```
<plugin-name>/
└── themes/
    ├── amber/
    │   └── amber.yaml
    ├── ocean/
    │   └── ocean.yaml
    └── sakura/
        └── sakura.yaml
```

> 一个主题 = 一个子目录 + 一个 yaml。目录名 = 主题 id = yaml 文件 stem。

## 最小示例

```yaml
name: 琥珀日落
id: amber
window:
  gradient_start: rgba(20, 16, 8, 255)
  gradient_end: rgba(45, 31, 13, 255)
background:
  chat_list:
    image: :/icons/fox_bg.png
    opacity: 0.1
    enabled: true
colors:
  card_bg: rgba(55, 38, 18, 232)
  card_bg_solid: rgba(55, 38, 18, 250)
  content_bg: '#3d2912'
  border: '#6a4e30'
  border_accent: '#f0b34b'
  text_primary: '#f5edd8'
  text_secondary: rgba(245, 237, 216, 0.72)
  text_muted: '#b89868'
  accent: '#d4893b'
  accent_warm: '#7fc7ff'
  hover_bg: rgba(212, 137, 59, 0.15)
  selected_bg: rgba(212, 137, 59, 0.34)
  capsule_bg: rgba(48, 32, 14, 185)
  capsule_border: rgba(95, 72, 45, 205)
```

## 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 主题显示名（可中文） |
| `id` | string | ✅ | 主题标识符（与目录名一致） |
| `window` | object | ❌ | 窗口外观 |
| `background` | object | ❌ | 背景图配置 |
| `colors` | object | ✅ | 颜色 token 集 |

## window

```yaml
window:
  gradient_start: rgba(R, G, B, A)
  gradient_end: rgba(R, G, B, A)
  blur: 12                  # 背景模糊度（可选）
  radius: 16                 # 窗口圆角（可选）
```

## background

```yaml
background:
  chat_list:
    image: :/icons/fox_bg.png   # qrc 路径或绝对路径
    opacity: 0.1                # 0.0 - 1.0
    enabled: true
  chat_detail:
    image: :/icons/bg2.png
    opacity: 0.05
    enabled: true
```

支持 `chat_list` / `chat_detail` / `sidebar` 等区域，按 DriFox 实际渲染器决定。

## colors 颜色 token

> 这是主题的核心。token 名是 DriFox 渲染器约定的，缺失 token 会用默认色。

### 必备 token

```yaml
colors:
  card_bg: rgba(...)         # 卡片背景
  card_bg_solid: rgba(...)   # 卡片纯色背景（用于截图/导出）
  content_bg: '#hex'         # 内容区背景
  border: '#hex'             # 边框
  border_accent: '#hex'      # 强调边框
  text_primary: '#hex'       # 主文本
  text_secondary: rgba(...)  # 次文本
  text_muted: '#hex'         # 弱化文本
  accent: '#hex'             # 主色调
  accent_warm: '#hex'        # 互补色
  hover_bg: rgba(...)        # hover 背景
  selected_bg: rgba(...)     # 选中背景
```

### 扩展 token（input_glow_preset 联动）

```yaml
colors:
  input_glow_preset: subtle   # subtle / breath / platinum / ember
  input_glow_color: '#hex'
  toolbar_bg: rgba(...)
  divider_color: rgba(...)
  hover_bg_strong: rgba(...)
  # ...
```

`input_glow_preset` 是 `/theme` 命令的「一键切换输入框聚焦发光风格」开关。

## 颜色格式

支持三种格式：

| 格式 | 示例 | 适用 |
|------|------|------|
| hex | `#f5edd8`、`#fff` | 不透明色 |
| rgba | `rgba(245, 237, 216, 0.72)` | 含 alpha |
| 命名 | （不推荐） | — |

> 不支持 `rgb()`（必须带 alpha）。DriFox 渲染层要求统一 alpha。

## 使用

```bash
/theme amber
/theme ocean
```

在 `~/.drifox/config.json` 中设置默认主题：

```json
{
  "ui": {
    "theme": "ocean"
  }
}
```

## 创建新主题

最快方式：复制 `plugins/example-plugin/themes/`（本仓库内有完整示例），改 `name` / `id` / 颜色 token。

## 校验

- 主题目录名必须 `^[a-z][a-z0-9-]+$`
- 必须有至少一个 `*.yaml` 文件
- 顶层必须有 `id` 字段
- yaml 文件可被读取（lint 阶段不强制解析 yaml 字段，由 DriFox 渲染层负责）

## 参考

完整示例见 `plugins/example-plugin/themes/`（amber、ocean、bordeaux、sunset、forest、aurora、midnight、crimson、amber-night、twilight、amber-light）。
