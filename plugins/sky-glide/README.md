# 🐦 滑翔鸟

欢迎卡片里的横屏过关小游戏：一只鸟不停下坠，按空格扇翅膀，从管道缝里挤过去。

## 用法

新建会话停留在欢迎页 → 顶部 tab 切到「🐦 滑翔」→ 点一下画面（让 iframe 拿到键盘焦点）→ 空格起飞。

| 操作 | 输入 |
|------|------|
| 扇翅膀 / 开始 / 死后重来 | `空格`、`↑`、`W`、鼠标点击、触屏点按 |
| 躲开 | 管道、地面、天花板 |

无限刷分制：过一根管道 +1，撞到即结束，最高分存在本地。

## 实现要点

欢迎卡片正文走 markdown → `CodeWebViewer`（QWebEngineView）的 `innerHTML` 注入，
按 HTML 规范注入的 `<script>` **不会执行**。所以游戏不是拼 DOM，而是整份单文件 HTML
塞进 `<iframe srcdoc="...">`：iframe 是独立文档，脚本、canvas、`keydown` 都跑在自己的
window 里，等于把一个浏览器小游戏原样搬进卡片。

- `ui/game_html.py`：游戏本体（canvas + 固定步长主循环），零外部资源，断网可玩
- `ui/__init__.py`：`register_welcome_tab` 注册 tab，`html.escape(quote=True)` 转义后写入 `srcdoc`
- 16:9 用 `padding-top: 56.25%` 撑，不用 `aspect-ratio`（WebEngine 内核 Chromium 83 不支持）
- 配色跟 `ctx["is_dark"]`（主程序 Qt 主题）走两套调色板

## 调手感

全部参数在 `ui/game_html.py` 顶部常量区：`GAP`（缝隙）、`SPACING`（管道间距）、
`VX`（横向速度）、`G`（重力）、`FLAP`（拍翼力度）。

## 许可

代码 MIT。图标取自 [Lucide](https://lucide.dev) 的 `bird`，ISC License，© Lucide Contributors。