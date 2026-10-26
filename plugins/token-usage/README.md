# token-usage 插件 — Token 用量页签

欢迎卡片新增「🔢 用量」tab：**30 天四指标 + GitHub 风格一年活动热力图**，数据取自会话里的**真实 API usage**（不是本地估算）。

## 功能

| 功能 | 说明 |
|------|------|
| 🔢 **欢迎卡片 tab** | 与会话 / 用量 / 项目看板 tab 并列 |
| 📊 **30 天四指标** | 总 Token / 输入 Token / 输出 Token / 请求次数 |
| 🔲 **年度活动热力图** | 365 天 GitHub 贡献图式色阶（纯 HTML 网格，非 echarts） |
| 🔄 **手动刷新** | 右上「刷新用量」强制丢弃缓存重采 |
| ⚡ **异步采集** | 全库解压扫描放 QThread，主线程不卡 |
| 🌓 **明暗适配** | 配色读 `ctx["is_dark"]`，跟随 Qt 主题 |

## 统计口径

全量求和口径（2026-10-21 确认，取代 2026-10-14 的净占用口径）：

| 指标 | 口径 |
|------|------|
| 输入 Token | 每轮 `usage.input` **原样累加**（与 API 计费口径一致） |
| 输出 Token | 每轮 `usage.output` 之和 |
| 总 Token | 输入 + 输出 |
| 请求次数 | 窗口内全部 `token_usage` 记录条数（每次 API 调用算一次） |
| 热力图色阶 | 按当日总 Token 分位（5 档，抗单日尖峰） |

为什么不做会话内去重：DriFox 每轮请求都把整个上下文重发一遍，去重看着更「干净」，
但服务商就是按全量计费的。实测（开发库 590 会话 / 43145 次请求）：prompt 中位数
93K、p90 227K、单会话中位 43 轮，全量口径是增量口径的 **93.5 倍**。
按增量口径统计出来的数字比真实账单小两个数量级，没有参考价值。

已知失真：API 不返回 usage 时宿主会回退本地估算并打 `estimated: True` 标记
（实测约 5000 条），这些记录也计入统计。

## 数据源

- `.drifox/sessions.db` → `sessions.messages`
- 该字段是 **zstd 压缩 blob**（4 字节 magic `ZSTD` + 1 字节版本 + frame，
  见主程序 `app/core/store/serde.py`），旧数据为裸 JSON，本插件两种都兼容
- 库路径优先问宿主 `app.utils.utils.get_app_data_dir()`（覆盖
  `DRIFOX_DATA_DIR` / 开发态 / 打包态 / macOS 四条分支），
  再退回 `.drifox/sessions.db`、`~/.drifox/sessions.db`
- 排除 `project LIKE '__archived__%'`

## 目录结构

```
plugins/token-usage/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.ui=true）
├── __init__.py              # Python 包标记
├── ui/
│   ├── __init__.py          # register_ui → welcome tab + 刷新动作
│   ├── collector.py         # QThread 异步采集 + 缓存 + 卡片重渲染
│   ├── data.py              # zstd 解压 + 每日 usage 聚合
│   └── render.py            # HTML 片段生成（指标 + 热力图）
├── icon.svg / icon_dark.svg # 插件图标（热力图网格）
└── README.md                # 本文件
```

## 渲染链路

`render_func` 返回 HTML 片段（**不是 markdown**），拼进欢迎卡片 body：

```
render_tab(ctx)
├─ 缓存命中 → render_html：标题行 + 30 天指标 + 年度热力图 + <style>
└─ 缓存未中 → 启动 QThread 采集 + 返回「加载中」占位
                    ↓ 采集完成
       UIEventBus.publish(EV_WELCOME_TAB_REFRESHED, mode_key="token-usage")
                    ↓
       主程序对当前显示本页签的卡片调 set_welcome_mode → 重新走 render_tab
```

「刷新用量」按钮挂 `.context-tag[data-type="tu-refresh"]`，
主程序 `handle_recommended_question` 未识别该 action 时转
`dispatch_welcome_action` 派发回本插件。

## 渲染约束（宿主 QWebEngine = Chromium 83）

Qt 5.15.2 的 WebEngine 是 Chromium 83，下列特性**不可用**：

| 不可用 | 替代方案 |
|--------|---------|
| flex `gap` | 一律用 `margin`（`.tu-week { margin-right }`、`.tu-cell { margin-bottom }`） |
| `aspect-ratio`（84+） | 格子固定 px 尺寸（`_fs(10)`） |
| `min()` / `clamp()`（79+ 有 min，80+ 有 clamp，但混用易出问题） | 尺寸全用 px |
| 模板 `<style>` | 本插件样式内联在片段尾部 `<style>` 里（与 calendar 同款） |
| 片段内 `<script>` | 不执行（宿主经 innerHTML 注入，HTML 规范）；交互走内联事件属性 |

热力图几何：53 周列 × (10px 格子 + 2px 间距) ≈ 634px，基准字号下正好落在
欢迎卡片正文宽度内不横向滚动；用户放大字号时 `.tu-heat { overflow-x: auto }` 兜底。

### tooltip 定位（格子悬停提示）

不用原生 `title`（OS 绘制，浅色下黑底大字号，Chromium 83 无 `::-webkit-tooltip`），
也不用 CSS 伪元素 `:hover::after`：伪元素测不到自身宽度，只能靠 `nth-child`
硬编码「边缘列翻转」，而卡片宽度是动态的（`parent_width - 20`），近边缘列
仍会溢出被 `html{overflow:hidden}` 裁掉。

现方案：`data-tip` 存文案 + `.tu-grid` 内联委托事件（`onmouseover` /
`onmouseout`）驱动 JS 自绘的 `#tu-tip`（`position: fixed` 挂 `body`）。
展示时用 `getBoundingClientRect()` 实测格子与 tooltip 尺寸，把左右上下
都钳制进视口（`Math.min/Math.max`），侧边列、底部行都不会溢出。

## 缓存与增量

| 层 | key | 失效 |
|----|-----|------|
| 采集缓存 | `(db mtime_ns, 当天日期)` | db 写入即失效，切回页签自动重采；db 没变则永远复用（无 TTL） |
| error 结果 | 同上 + 60s TTL | 避免临时失败被永久固化 |
| 手动刷新 | 强制 `invalidate()` | 「刷新用量」动作 |
| 会话级增量摘要 | `plugin_data/token-usage/session_stats.json` | 指纹 `(updated_at, message_count)` 未变的会话零解压复用；格式变更由 version 字段整体作废重建 |

增量语义：会话被删除（或归档清理）后摘要保留，历史统计**不随删除蒸发**；
`sessions` 计数因此含已删除但曾产生用量的会话。

数据目录三级取值：功能池 `storage.data_dir`（宿主能力，首选）→ 直接导入
`app.utils.utils.get_app_data_dir`（旧宿主过渡）→ `~/.drifox`（兜底）。

## 依赖

- **DriFox ≥ 0.5.0**：需要 `register_welcome_action`（刷新按钮）与
  `EV_WELCOME_TAB_REFRESHED`（采集完成通知）。旧主程序缺 `register_welcome_action`
  时页签仍可用，只是刷新按钮无响应（有 warning 日志）
- Python 3.14+（`compression.zstd`，PEP 784）。缺该模块时插件降级为
  「跳过压缩会话」，不崩
- 无第三方依赖（orjson 可选，有则用）

## 性能

- 增量采集：未变会话不读 blob（轻量列指纹比对），只解压新增 / 变更会话；
  稳态下每轮只处理个位数脏会话，亚 50ms
- 首次运行（或摘要作废）退化为全量扫描：476 会话 / 85MB ≈ **0.6s**
  （QThread，不阻塞 UI）
- 单次会话 messages 最大 13MB，SQL 层只取所需列，不做全字段展开
- orjson 可选：命中则 JSON 解析走 C 层

## 安装

插件位于 `plugins/token-usage/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\token-usage %USERPROFILE%\.drifox\plugins\token-usage /E /I /Y

# Linux / macOS
cp -r plugins/token-usage ~/.drifox/plugins/
```

启动 DriFox，在欢迎卡片点击「🔢 用量」tab。

## 测试

```bash
pytest tests/test_token_usage.py -q
```

覆盖 zstd 解压、裸 JSON 兼容、全量求和口径、窗口补零、色阶分位、热力图几何。

## 同类插件

- [`context-stats`](../context-stats/)：近 14 天 echarts 趋势图（本地估算口径）
- [`project-dashboard`](../project-dashboard/)：项目 git 看板