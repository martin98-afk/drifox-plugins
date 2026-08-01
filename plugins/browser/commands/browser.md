---
description: 打开内置浏览器（可选传入网址直接导航）
type: function
parameters:
  - name: "<url>"
    description: "要打开的网址（可选，如 localhost:8080 / example.com）"
    param_type: positional
shortcut: Ctrl+Shift+B
---

# /browser — 打开 DriFox 内置浏览器

打开内置浏览器浮动卡片。可传入 URL 直接导航：

- `/browser` — 打开浏览器（若已打开则聚焦）
- `/browser localhost:8080` — 打开并导航到 http://localhost:8080
- `/browser example.com` — 打开并导航到 https://example.com
- `/browser 搜索词` — 打开并搜索该词

## 功能

- Chrome 风格多标签浏览（Ctrl+T 新建 / Ctrl+W 关闭 / Ctrl+Tab 切换）
- 地址栏（Ctrl+L 聚焦），历史/收藏自动补全
- 收藏（Ctrl+D）、历史（Ctrl+H）、下载管理
- **外部链接接管**：主程序（DriFox）中所有 http/https 外链（AI 消息链接、OAuth 授权、API 文档、设置页外链等）默认在插件浏览器新标签页打开；浏览器插件不可用时自动回退系统浏览器。本地文件（file://）仍走系统默认。
- **bash start 拦截**：大模型通过 bash 执行 `start <url>` / `cmd /c start <url>` / `explorer <url>` 打开网页时，同样转交插件浏览器；`start notepad.exe` 等非 URL 命令照常执行。
- **AI 智能体浏览（MCP）**：插件注册 `browser` MCP 服务器（15 个工具），AI 可自主控制插件浏览器——`browser_navigate`（导航）、`browser_read`（读页面）、`browser_execute_js`（点击/输入/滚动/任意 JS）、`browser_screenshot`（截图反馈视觉模型）、`browser_tabs`（标签管理）等，实现 Codex 式浏览闭环。

> 这是 `type: function` 命令：由 Python 处理器直接执行，不经过 AI。
