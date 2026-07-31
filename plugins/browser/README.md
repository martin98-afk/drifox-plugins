# DriFox 内置浏览器

一比一还原 Chrome 体验的多标签内置浏览器插件，基于主程序已打包的 Qt WebEngine（Chromium 内核），零额外依赖。

## 快速开始

| 命令 | 说明 |
|------|------|
| `/browser` | 打开浏览器 |
| `/browser <url>` | 打开并导航到指定网址 |
| `/browser-new` | 新建标签页 |
| `/browser-devtools` | 打开 DevTools |
| `/browser-incognito` | 打开隐身窗口 |

## 快捷键（与 Chrome 一致）

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+L` | 聚焦地址栏 |
| `Ctrl+T` / `Ctrl+W` | 新建 / 关闭标签 |
| `Ctrl+Shift+T` | 恢复关闭的标签 |
| `F5` / `Ctrl+R` | 刷新 |
| `Esc` | 停止加载 |
| `F12` / `Ctrl+Shift+I` | DevTools |
| `Ctrl+Shift+N` | 隐身窗口 |
| `Ctrl+H` / `Ctrl+D` | 历史 / 收藏 |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | 切换标签 |
| `Ctrl+1..8` | 跳转标签 |

## 功能

- **右侧浏览器面板**：默认占用主界面右侧区域
- **多标签浏览**：Chrome 风格标签栏，标题/图标同步，拖拽排序；左键在当前页跳转，右键可选择在新标签打开
- **地址栏**：`localhost:8080` 自动补 `http://`，历史+收藏合并补全
- **收藏夹**：`Ctrl+D` 收藏，菜单 → 收藏夹管理（打开/删除）
- **历史记录**：卡片内悬浮面板，自动记录访问，支持搜索与清空
- **下载管理**：downloadRequested 托管，进度条实时显示，可打开所在文件夹
- **DevTools**：F12 打开独立开发者工具窗口
- **隐身模式**：OTR Profile，关闭即焚，与正常浏览完全隔离

## 性能设计

- **后台标签冻结**：超过 6 个标签时，非活跃标签 `setLifecycleState(Frozen)` 释放渲染内存
- **懒创建**：标签页 WebEngineView 延迟到激活时创建
- **80ms 渲染合并**：地址栏进度更新经 QTimer 合并，减少重绘
- **独立 Profile**：`browser-profile` 独立 storage/cache 目录，与主程序完全隔离

## 数据目录

- 数据库：`~/.drifox/plugins/browser/data/browser.db`（收藏/历史/下载）
- Profile：`~/.drifox/plugins/browser/data/profile/`（Cookie/localStorage）
- Cache：`~/.drifox/plugins/browser/data/cache/`

## 架构

```
browser/
├── .drifox-plugin/plugin.json   # manifest（commands + ui）
├── commands/                    # 5 个斜杠命令
└── ui/
    ├── __init__.py              # register_ui 入口
    ├── browser_window.py        # 主窗口（工具栏/标签栏/页面区）
    ├── tab_widget.py            # Chrome 标签栏 + 冻结策略
    ├── url_bar.py               # 地址栏（URL 规范化/补全/加载指示）
    ├── profile_manager.py       # 持久 Profile + OTR Profile
    ├── data.py                  # SQLite + QThread worker
    ├── bookmarks.py             # 收藏管理
    ├── history.py               # 历史管理
    ├── downloads.py             # 下载托管
    ├── devtools.py              # DevTools 集成
    ├── incognito.py             # 隐身窗口
    ├── shortcuts.py             # 快捷键
    └── assets/                  # 图标
```
