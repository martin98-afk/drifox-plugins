# context-stats 欢迎卡片 tab 设计文档

> 日期：2026-08-12
> 状态：已获用户批准（方案 A + 市场仓库部署 + 两个图）

## 1. 需求

参考 `context-usage-stats` 插件（DriFox 运行时内置），开发一个**欢迎卡片类** UI 插件，
在欢迎卡片新增 tab「📊 用量」，输出 **echarts** 图表：

1. 模型上下文（token）用量趋势（近 14 天，面积图）
2. 消息量趋势（近 14 天，柱状图）

## 2. 关键技术约束（已验证）

| 约束 | 结论 |
|------|------|
| 欢迎卡片渲染管线 | body 走 `updateContent()` innerHTML 注入，`<script>` 不执行 |
| welcome viewer 骨架 | light 骨架（`light=True`）→ `cdn_libs=""`，**无 echarts 库** |
| echarts 初始化 | 骨架 JS `if (window.echarts)` 命中才渲染 `.echarts-container` |
| ` ```echarts ` 代码块 | markdown 管线 `_wrap_code_blocks_with_copy_button_web` 转成 echarts-container div（base64 JSON） |
| render_func 签名 | `(ctx: dict) -> str`，返回片段拼进 `welcome_md` 后走 markdown 管线 |
| render_func 线程 | 主线程同步调用，禁网络/大文件读取 |

**结论**：欢迎卡片 tab 用 echarts 需主程序给 welcome 骨架也加载 echarts vendor（方案 A）。

## 3. 主程序改动（D:\work\DriFox\app\widgets\message_card.py）

1. `_load_skeleton`（L3220）：`if self._light_skeleton: cdn_libs = ""` →
   light 骨架也加载 echarts vendor（复用 `_get_vendor_script_tags()`）
2. `_SKELETON_CACHE_VERSION`（L1978）：`8` → `9`（骨架缓存强制失效）
3. `.echarts-container` CSS（L4241）：去掉 light 跳过分支

## 4. 插件结构（D:/work/drifox-plugins2/plugins/context-stats/）

```
context-stats/
├─ .drifox-plugin/plugin.json   # name=context-stats, ui:true, type:user
├─ icon.svg / icon_dark.svg
└─ ui/
   ├─ __init__.py               # register_ui: register_welcome_tab
   ├─ render.py                 # render_func(ctx) -> markdown(含 echarts JSON)
   └─ data.py                   # SQLite 读取 + 模块级缓存
```

- `mode_key="context-stats"`（避开内置 `sessions/projects/changelog`）
- `label="📊 用量"`
- `register_ui` 清理 `ui_plugin_context_stats.` sys.modules 前缀（热重载）

## 5. 渲染链路

```
render_func(ctx) 返回:
  ### 上下文用量趋势
  ```echarts
  {echarts_option_json}
  ```
→ 拼入 welcome_md → set_content → markdown 管线
→ echarts-container div(data-echarts-json=base64)
→ 骨架 JS echarts.init(el, 'dark') → 渲染
```

## 6. echarts option 设计

公共：`backgroundColor: 'transparent'`、`grid`、`tooltip: {trigger:'axis'}`、
`xAxis` 14 天 `MM-DD`、显式 textStyle 颜色（不依赖骨架 dark 主题默认）。

**单图双 Y 轴**（一个 echarts 实例、共享 x 轴，两条曲线同一坐标系）：
- 左轴（yAxis[0]）：token 用量，`type:'line'` 面积图（accent 色系，暗色 #62a0ea / 亮色 #2878dc，渐变 0.3→0）
- 右轴（yAxis[1]）：消息量，`type:'bar'` 柱状图（success 系，暗色 #50e3c2 / 亮色 #00a888，`borderRadius:[4,4,0,0]`）
- 右轴关闭 `splitLine` 避免网格重叠

**数字缩写**（8000000 → 8M / 8000 → 8k）：
- echarts JSON 走 base64 → `JSON.parse`，**无法携带 JS 函数 formatter**
- 方案：Python 侧按各轴数据最大值选单位（`_scale_unit`：≥1e6→M，≥1e3→k），
  数据除以缩放因子，`axisLabel.formatter` 用字符串模板 `"{value}M"` / `"{value}k"` 补后缀
- tooltip formatter 同法拼接（`{c0}M tokens` / `{c1} 条`）
- 概要行 `_fmt_k`：整数去尾 `.0`（`8.0M` → `8M`）

明暗切换：`ctx["is_dark"]` 选择色板；`is_dark is not None` 判断，勿 `bool()` 包裹。

## 7. 数据层（data.py）

复用 context-usage-stats 的查询模式（`sessions` 表）：
- 按日聚合近 14 天：`DATE(created_at)` + `SUM(context_usage)`、`SUM(message_count)`
- token 回退估算：`context_usage` 为 0/空的旧会话用 `messages` 文本快速估算
- 路径兜底：`_PROJECT_ROOT/.drifox/sessions.db` → `~/.drifox/sessions.db`
- **模块级缓存**：key=`(db_mtime, 当天日期)`，db 未变则复用，避免每次切 tab 重复查询
- 主线程同步执行（render_func 限制），查询为轻量聚合

## 8. 验证计划

1. 主程序 message_card.py 语法检查
2. data.py 单元测试（mock SQLite：14 天窗口、空数据、fallback 估算）
3. 启动 DriFox → 欢迎卡片出现「📊 用量」tab → 两个 echarts 图渲染
4. 明暗主题切换图表配色跟随
5. 热重载无异常
6. marketplace.json 条目 + `tools/validate_plugins.py` 通过

## 9. 市场条目

- `plugins/context-stats` 加入 marketplace.json
- `drifox.min_version` 需覆盖含 echarts 骨架改动的主程序版本（TODO：确认主程序当前版本号）
- `tools/generate_marketplace.py` 重新生成
