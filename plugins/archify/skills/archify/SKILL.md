---
name: archify
description: 把代码库 / 系统描述 / 纯语言需求 / Mermaid 转成自包含交互式架构图 HTML（architecture/workflow/sequence/dataflow/lifecycle）。产物含主题切换、缩放、关系追踪、PNG/SVG/WebP/WebM 导出。当用户要可视化系统架构、云/安全/网络拓扑、技术工作流、API 调用序列、请求生命周期、数据管道 ETL/ELT、数据血缘、状态机/生命周期，或转换/美化 Mermaid 时使用。通过 archify 工具调用内置 tt-a1i/archify 运行时，开箱即用。
license: MIT
metadata:
  version: "1.0.0"
  author: 马丁
  based_on: tt-a1i/archify (MIT, v2.16)
---

# Archify（DriFox 适配版）

用 `archify` 工具（DriFox 插件，内置 tt-a1i/archify 运行时）把一段小的「typed JSON 规范」渲染成自包含、可交互的 HTML 架构图。默认输出静态图；仅在用户要求 demo/演示时启用动效。

本插件已 vendored archify 运行时，**无需用户安装 Node 依赖**（渲染器为纯 Node 标准库，本机 Node >=18 即可）。不要指示用户去 `npm install` 或 clone archify 仓库——直接调 `archify` 工具。

## 快速创作路径

1. 从下表的 5 类图里选一种。
2. 读取对应 schema 与示例了解字段形状（按需用 glob 搜索 `**/archify_runtime/schemas/<type>.schema.json` 与 `**/archify_runtime/examples/<type>*.json`）。只读本类型相关文件；新创作意味着新的稳定 ID、领域化措辞与布局，用示例学字段形态而非事实。当真实产品身份重要时，调 `archify` 工具 `action=brands` 查询品牌；未知品牌且用户提供 URL 时再读 `archify_runtime/references/brand-marks.md`。
3. **产物优先**：下一步动作必须是写出候选 JSON。先用一条清晰主线、短侧支、稀疏标签，主节点至多 12 个。除非用户显式要求 dense `standard` 地图，否则置 `meta.quality_profile` 为 `"showcase"`。先用自动路由与标签；诊断要求前不要加 `via`/`channelX`/`channelY`/`labelAt`；每次修复至多应用一个诊断出的几何控制。
4. 每次编辑候选后、交付前立即校验：

   ```
   archify 工具 action=validate, diagram_type=<type>, input_json=<候选JSON>, quality=showcase
   ```

   仅 4 项 artifact 检查的收据是基础校验，绝不算 showcase 验收。showcase 通过须报告全部 9 项 artifact 检查、0 组合错误、0 警告。若候选遗漏或拼错 `meta.quality_profile` 字段，先在几何前修正。校验通过即冻结候选，之后不再编辑。
5. 交付 HTML 的最终验收命令：

   ```
   archify 工具 action=render, diagram_type=<type>, input_json=<候选JSON>, quality=showcase, open=<true|false>
   ```

   工具内部走 `deliver` 验收并写入 HTML 文件，返回绝对路径。非零退出绝不能算成功。若校验失败，只改被诊断的 `subject`、核实 `evidence`、从 `supportedFixes` 中选，然后重跑；持续聚焦修正直到目标错误数达新低。若连续两轮无改善，停止并如实报告未解决的 diagnostics。

不要在首次候选前读 `renderers/shared/geometry.mjs`、渲染器源码、校验器源码、测试或基准。仅在遇到不支持的内部诊断、或两次聚焦修复都失败时再查实现。

## 类型路由

| 类型 | 用于 |
|---|---|
| `architecture` | 组件、服务、云/安全边界、基础设施 |
| `workflow` | 流程、审批门、工具调用、runbook、CI/CD |
| `sequence` | API 调用链、请求生命周期、异步链路、返回 |
| `dataflow` | 管道、ETL/ELT、血缘、治理、消费者 |
| `lifecycle` | 状态/状态转换、重试、等待与终态 |

歧义时调 `archify` 工具 `action=guide, scenario="<场景>"` 获取引导。场景样例仅作结构参考，不是照搬的事实。

## Mermaid 输入

读 Mermaid 取拓扑与语义，再创作全新的 Archify JSON；不要机械渲染 Mermaid 样式。
- `flowchart` / `graph` → `workflow`，或组件图用 `architecture`
- `sequenceDiagram` → `sequence`；participants 变语义参与者，arrows 变 messages
- `stateDiagram` → `lifecycle`；states/transitions 保留语义而非 Mermaid 风格

## 创作不变量

- 一条明显主线；侧支离开最近的主线节点。加路由控制前先删低价值边。
- 默认省略 `meta.visual_preset`，让图以 `classic` 打开；仅当用户显式要求 `signal-flow`/`blueprint`/`editorial` 时才设。颜色模式与视觉预设独立：切换浅/深必须保留当前预设。
- 默认省略 `meta.subtitle`；绝不复述标题/节点/卡片的副标题；仅当用户明确要求时才加一行支撑语。
- 把独立桌面查看器当作首屏产物（而非浅条带）：为笔记本与外显生成一份响应式产物，绝不做设备专属 HTML 或改拓扑。在 1440×900、1600×1000、1920×1080 打开真实 HTML，大屏桌面还要查 2048×1320；要求每个尺寸下 `scrollWidth <= innerWidth` 且 `scrollHeight <= innerHeight`，同时目测图在最大视口下仍舒适可读、垂直均衡。用删冗余内容或压缩间距修溢出，最后才缩节点/标签/主面板。最大视口仍有明显下部空白时，重分布 Y 位置并等比增高 viewBox，不要塞填充文案或装饰卡片。绝不用 `overflow:hidden`、裁切、内部图滚动条、拉伸 SVG 高度或更小字号伪造通过。窄/移动布局在 containment 需要时可纵向滚动。
- 默认省略 `meta.legend` 走诚实的 `auto`：只列 typed IR 中存在的语义种类。需要时用 `mode: auto|all|hidden` 与渲染器支持的 `entries.<kind>.label|visible`；label 不改语义。
- 选一种主要创作语言：用户显式选择优先，否则遵循请求或对话主导语言。`meta.locale` 只控渲染器自有 Viewer UI：用 `"en"` 或 `"zh-CN"`。其他语言省略 `meta.locale` 并如实说明固定 Viewer UI 与 `<html lang>` 回退英文。渲染器从不翻译创作内容。
- 保留确切产品名、代码标识符、命令、协议、API 路径、环境名；它们可留在英文，但周围解释性文案须用所选语言。
- lifecycle：phase 列 `0..4` 在主轨；event/outcome 列 `0..2` 对齐后续 phase。可恢复状态用 `type:"failure"` 加一条回到 active 状态的真实转换。

## 可选 Viewer 能力

生成的 HTML 已自带主题切换、pan/zoom、搜索、聚焦、关系追踪、语义视图、演示与诚实导出。这些是读者能力，不是额外创作工作。`meta.animation:"trace"` 为 opt-in；`meta.views` 可选，至多 5 个精选章节。仅当用户显式要求分享卡 / 路由可达卡 / 动效 / 引导故事 / 深链 / 演示 / 搜索聚焦 / 其他 Viewer Runtime 特性时，才读 `archify_runtime/references/viewer-runtime.md`。

## 设置与兜底

本插件内置运行时，无需安装。可用 `archify` 工具 `action=doctor` 自检；若用户想看全部示例可 `action=examples`。当 shell 不可用时（本插件不依赖 shell，正常调工具即可），不要尝试手动跑 node。

## 输出

返回生成的 HTML 绝对路径、图类型、校验摘要与诚实的视觉审阅状态。非零命令绝不能声称成功，也不要声称你做了未做的视觉检查（本环境无法看图，只能给路径）。
