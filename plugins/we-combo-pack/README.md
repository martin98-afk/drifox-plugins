# we-combo-pack — 搭配实验 5 套

Wallpaper Engine 壁纸转制的**搭配样板集**，每套演示一种「载体组合」，用来验证 DriFox 主题背景系统的各种搭配能力。素材版权归原作者，仅限本地个人使用。

## 五套搭配

| theme-id | 明暗 | 载体组合 | 演示的缺口 |
|---|---|---|---|
| `combo-hanabi-chat` | dark | `window.image` + `chat.animation` | 对话区独立动画（G1） |
| `combo-healing-light` | light | `window.image` 淡化 + `chat.animation` | 浅色雾感 + 对话动画（G3） |
| `combo-ocean-sidebar` | dark | `window.image` + `sidebar.image` | 侧栏静态分景（G5） |
| `combo-somi-foreground` | dark | `window.animation` + `scene.foreground` | 透明前景层叠加（G6） |
| `combo-campfire-sidebar` | dark | `window.animation` + `sidebar.animation`（**同一 src，双 `canvas: shared`**） | **侧栏动画 + 多区共享画布（全仓首例）** |

## combo-campfire-sidebar 的技术要点

这是全仓第一个用上 `sidebar.animation` 的主题，也是第一个 `canvas: shared` 跨区共享。

```yaml
backgrounds:
  window:
    animation: {src: ../../assets/combo-campfire-sidebar/chat.webp,
                canvas: shared, fps: 10, fit: cover, position: center}
  sidebar:
    animation: {src: <同一个文件>, canvas: shared, fps: 10, fit: cover, position: center}
    color: rgba(10, 8, 6, 172)     # 半透明罩保侧栏文字可读
  scene: {color: rgba(0, 0, 0, 0)}  # 纯透明，透出整窗动画
```

`canvas: shared` 的两层语义：
1. **共享解码**：同一绝对路径只建一个 `AnimationSource`，不重复解码（省 CPU）
2. **共享画布**：各区域取「整图属于自己的那一段」，窗口与侧栏的接缝图案连续，看起来是一整张画

**硬约束**：两个 region 的 `fps` / `fit` / `position` 必须完全一致，否则两区缩放比例不同会错位。

**已知限制**：`window` 与 `sidebar` 都不读 `blur` / `dim` 字段（`_apply_area_bg` 不处理），要压暗只能用半透明 `color` 罩或素材自带暗调。`blend` 是死字段，别写。

## 素材规格

| theme-id | 素材 | 规格 |
|---|---|---|
| `combo-campfire-sidebar` | `assets/combo-campfire-sidebar/chat.webp` | 1600×900 / 381 帧 / 2.32 MB / 实测 10.68fps，yaml 标 10 |

## 制作工具链

素材转换与校验用 `D:\work\drifox-plugins2\.theme-template\`（不在 `plugins/` 下，不进市场）：

```powershell
$P = "D:\work\DriFox\.venv\Scripts\python.exe"
# 生成骨架
& $P .theme-template\new_theme.py --src "<壁纸目录>" --out plugins\<插件> --theme-id <id> --name "<名>" --mode dark
# 校验
& $P .theme-template\tools\verify_theme.py plugins\<插件> <theme-id>
# fps 判定（必须 PySide6 环境）
& 'D:\work\.venv-pyside6\Scripts\python.exe' .theme-template\tools\fps_verdict.py <yaml> <webp>
```

## 版权

各套素材来自 Wallpaper Engine 创意工坊，版权归原作者。本插件仅供本地个人学习与欣赏，公开发布前必须替换为自有或可商用素材。
