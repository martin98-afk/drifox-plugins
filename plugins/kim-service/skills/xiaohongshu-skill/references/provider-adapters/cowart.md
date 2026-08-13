# CowArt 视觉工作台适配

本文件把 CowArt 映射到 `visual-workspace-contract.md`。它是具体供应商说明，不是小红书通用控制规则。

## 目标版本与启用条件

- 当前适配目标元数据：CowArt `0.1.20`。
- 版本号只用于说明本适配按哪版合同编写，**不能作为已启用证据**。
- 每次执行先做 capability probe；只有当前会话同时可调用 `render_cowart_canvas_widget`、`get_cowart_selection`、`insert_cowart_image`、`get_cowart_canvas_state`，才启用本适配。
- 插件刚安装或升级但能力不可见时，本轮按“适配器不可用”处理；可以提示用户新开 Codex 对话加载新工具 schema，但不得靠版本号猜测能力存在。

## 询问与启动映射

适配器只在通用合同的 `cover_first_visible_candidate`、`cover_revision_comparison` 或 `failed_page_revision_comparison` 到达后参与；不得因为工具已加载就在 Skill 启动时打开或询问。面向用户的选择文案读取机器映射中的 `offer_policy.user_copy`，只显示“可视化工作台”，不显示 CowArt、MCP、widget、holder 或 shape 等内部术语。

Codex 使用 `request_user_input`；Claude Code 无此适配器时继续 `AskUserQuestion` 与既有流程。无原生选择面时输出同文案 Markdown 卡并停止等待，状态写 `offered_pending`，不得称为弹窗。用户跳过、能力不可用或 `render_cowart_canvas_widget` 启动失败时分别写 `declined`、`unavailable`、`launch_failed`，然后继续封面验收与现有图片路线。

`accepted` 只表示已有启动授权；`explicit_auto_permission` 不能写成 `human_confirmed`。只有插入后 `get_cowart_canvas_state` 回读匹配，状态才提升为 `opened_verified`。同一 `offer_stage + value_fingerprint` 最多询问一次；跨阶段重问必须有新的可比较资产和 hash 绑定的新价值证据。

## 能力映射

- `render_cowart_canvas_widget`（必需）：在 Codex 内打开项目绑定的原生 Widget。正常路径不启动 localhost、本地网页服务或浏览器；旧启动脚本只属于插件开发 fallback，不是本适配路径。
- `get_cowart_selection`（必需）：读取当前选中的 `AI 图片` holder、尺寸、比例和锚点。小红书封面必须验证为 3:4。
- `insert_cowart_image`（必需）：把本轮新位图插入当前页。选中 holder 时默认用 holder 的尺寸与位置替换 holder；批注返修时使用原图作为锚点，把新图放在旁边且保留原图与批注。
- `get_cowart_canvas_state`（必需）：每次插入后立即读回项目画布，核对 shape、asset URL/路径和持久化 snapshot 指纹。插入返回 ID 但没有该读回时，只能写 `attempted`。
- `save_cowart_canvas_state`（可选 fallback）：只有必须更新完整 tldraw snapshot 时使用；正常插图优先 `insert_cowart_image`。
- `save_cowart_reference_image`（按需）：Widget 参考图没有以宿主附件暴露时，把选中参考图保存到当前页资产目录。
- `read_cowart_page_asset`（按需）：需要读取页面本地参考资产时使用，不默认 hydrate 整张画布。

对应技能语义保持不变：

- `cowart-open-canvas` 使用 `render_cowart_canvas_widget` 打开原生 Widget。
- `cowart-image-gen` 先用 `get_cowart_selection` 取得 holder 的 3:4 尺寸合同，再由当前环境内置图片生成流程出图，最后用 `insert_cowart_image` 默认替换 holder。生成证据仍来自内置图片生成调用；CowArt 本身不登记为图片路线第 2 级。
- `cowart-image-edit` 只读取用户或 Widget 明确提交的批注截图作为编辑 Brief，由当前环境内置图片生成流程产出新位图，再用 `insert_cowart_image` 放到原图旁边；不得扫描整张画布猜测编辑意图。

## 项目路径绑定

- 所有四个必需工具的 `projectDir` 必须是当前用户工作区的规范化绝对路径；记录 `resolved_project_dir`。
- 默认且推荐的 `canvasDir` 必须解析为 `<projectDir>/canvas`；记录 `resolved_canvas_dir`。
- 不传自定义 `canvasDir`。只有用户明确授权自定义位置，并完成规范化路径、真实路径与符号链接检查，证明目标仍被已授权 `projectDir` 包含时才允许；否则拒绝该工作台写入并继续原生图片路线。
- 禁止 `..`、不同盘符、UNC 路径或符号链接把 `canvasDir` 逃逸到工作区外。

## 插入与落盘证据

`insert_cowart_image` 返回的 `assetId`、`shapeId`、`assetUrl` 或 `assetFile` 只记为 `insert_attempt`，不能直接声明已放置。随后必须调用 `get_cowart_canvas_state`，并完成：

1. 读回 snapshot 中存在返回的 `shapeId`。
2. 该 shape 关联的 asset 记录与返回的 `assetUrl` / `assetFile` 一致，且路径仍在已解析的 `canvasDir` 内。
3. 对本次读回的持久化 snapshot 计算或取得 SHA-256，并连同读回证据记录。

只有三项都通过，状态才能从 `attempted` 提升为 `persisted_verified`。若保存层返回失败、读回缺 shape、资产不匹配或无 snapshot hash，本页保持 `partial`，不得写入 `accepted_asset`。

静态 `check-visual-workspace-contract.mjs` 通过只证明本适配规则一致，不证明当前宿主工具存在、插入成功或真实画布已落盘。

## 替换分支

- 封面 holder：只有 `get_cowart_selection` 当前读回证明恰好一个选中对象是 `AI 图片` holder，且尺寸比例验证为 3:4，才允许 `replaceAiImageHolder: true`。
- 未验证 holder 或普通图片锚点：必须 `replaceAiImageHolder: false`。
- 批注 / before-after：必须 `replaceAiImageHolder: false`、`placement: "right"`，保留原图和全部批注；读回还要确认原 shape 与批注 shape 仍存在。

## 小红书使用方式

1. 逐页视觉导演和封面 Image2 Brief 完成后，通过原生 Widget 建立或选中 3:4 `AI 图片` holder；不得使用 AI Slides 的 16:9 画布或幻灯片导出路径。
2. 用 selection 返回的 `targetWidth`、`targetHeight` 和 `targetAspectRatio` 约束 Image2；仅在 holder 已验证时通过 `insert_cowart_image` 替换 holder，随后强制状态读回。只有 `persisted_verified` 后才能做移动端检查和候选验收。
3. 检查通过后仍由 Codex `request_user_input` 获取批量许可。CowArt 选中状态、holder id、shape id 或画布保存成功都不算许可。
4. 批注返修时只使用用户提供的对应截图；新图放在原图右侧或附近空白区，保留原图和批注。复查后写入明确的 `accepted_asset`。
5. 批量完成后按页记录资产与 shape 映射，只返修失败页。

## 不可用与失败

- 版本存在但四个必需能力任一不可调用：视为 CowArt 适配器未启用，直接继续宿主原生图片预览与决策流程。
- Image2 / 宿主原生生成失败：按既有图片路线处理；不得启动 CowArt 当作第 2 级生成器或失败救援。
- Claude Code 没有 CowArt：继续 `AskUserQuestion` 和既有图片路线，不新增阻塞。

机器可读映射见 `assets/visual-workspace-adapters/cowart.json`。
