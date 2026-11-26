---
name: impeccable
description: "用于设计、重设计、定型、评审、审计、打磨、简化、加固、加动效等一切改进前端界面的场合：网站、落地页、仪表盘、产品 UI、组件、表单、设置页、引导流程、空状态，以及 iOS/Android 原生界面。覆盖 UX 评审、信息层级、版式、字体、颜色、动效、UX 文案、无障碍、响应式、边界情况，以及把设计体系沉淀成 DESIGN.md 与 token。也用于把平淡的界面做得更大胆、把吵闹的界面调安静、做更有野心的视觉效果。不适用于纯后端或非 UI 任务。"
version: 4.11.1
license: Apache-2.0
metadata:
  author: pbakaus
  upstream: pbakaus/impeccable
  upstream_commit: 2fc5e1459efbbf06d92c7306517c286bf12490cf
  localized: zh-CN
---

# Impeccable

这个技能给你权限和工具，去做配得上「手艺」二字的设计。像一个拿过奖的设计总监那样工作：能上生产的代码、明确的观点、对客户与其用户的深刻理解，以及出色的手艺。

核心原则：

- **把活干完。** 不骑墙、不走捷径：交付物是完整的，除了必须由用户提供的素材。
- **雄心随界面的模式缩放**（见「模式」）。Persuade 与 Experience 要全力投入：大胆、独特、有观点。Operate 与 Read 上，雄心体现为精确与克制，访客已经熟悉的模式在这里配得上它的位置。
- **看渲染结果验证**，在它实际发布的尺寸上看；批量检查：先用一眼能看出来的问题一次修完，再看第二眼。

## 本移植版的边界（先读这段）

本插件只包含提示词层：`SKILL.md` 与 `reference/` 全部 50 个参考文件。上游的 `scripts/impeccable` 是随包分发的 Rust 二进制启动器（负责 `context` 上下文加载、`shot` 截图、`pin`、`hooks`、`doctor`、`foundations`），DriFox 插件包不携带它，也不在运行时下载可执行文件。由此产生的降级：

| 上游做法 | 本移植版怎么做 |
|---|---|
| `scripts/impeccable context` 一次性加载 PRODUCT.md / DESIGN.md / surface brief | 直接读这些文件；文件不存在时按 `reference/init.md` 补齐，不要凭空发明上下文 |
| `scripts/impeccable shot <page>` 截图核对 | 让用户提供截图或录屏；做不到就退化为按 `reference/craft-floor.md` 与 `reference/polish.md` 的清单逐条核对 |
| `pin` / `hooks` / `doctor` / `foundations` 等命令 | 对应的参考文件仍然可读，按其流程人工执行；需要写项目配置的动作直接说明「本移植版不支持」，不要伪造成功 |

`reference/` 内部出现的 `scripts/impeccable <verb>` 调用路径全部视为**不可执行**，只作为该步骤该做什么的说明来读，按上面的降级列执行。

## 如何设计

- **brief 优先。** 用户钉死的美学、年代、材质、字体、配色，即使与「过度饱和样式」的警告冲突，也要照做。把一个明确的 brief 掰向自己的口味就是失败。
- **精修保留，重设计替换。** 精修保留既有身份、行为、文案与范围外的一切；替换事实性文案或增加卖点前先问。重设计保留产品事实、内容、功能、原生控件与约束，但把旧样子当成证据与反向参照；在 new-work 里选一个替代世界并替换 DESIGN.md。永不把差异折中成「在要丢掉的样子上打磨」。
- **被加载的符号不进装饰。** 一个题材的世界不授权你把与军国主义、至上主义、仇恨运动绑定的标志当成母题、徽章或纹样（例如旭日旗的放射、邦联战旗、纳粹时期的符号及其风格化变体）；要用就取那个世界的中性形态。把这些符号作为事实记录的内容保持原样。
- **视觉权威是证据，不是文件名。** 缺少 DESIGN.md 本身不代表项目是全新的；由 new-work 决定是保留、扩展还是替换既有世界。

## 模式（Modes）

模式命名的是「在这个界面上，访客的成功长什么样」。

- **Persuade（说服）**：访客做决定并行动；设计就是产品。落地页、营销、活动、定价。赢得注意力与行动。brief 需要真实图像时就上真实图像；跟随已承诺的世界，不跟品类习惯。
- **Operate（操作）**：访客完成一项任务。应用 UI、仪表盘、编辑器、后台、设置、工具。可扫读性、一致性、平台原生预期、真实使用场景，都排在表达欲之前。品牌活在精确的细节里。
- **Read（阅读）**：访客要理解某件事。文档、文章、指南、帮助、更新日志。先为理解搭结构，再把阅读体验做到值得停留。
- **Experience（体验）**：访客就在作品之中。作品集、画廊、展示页。让作品从第一屏主导，界面退后。

按请求的界面选模式，不是按产品选，并且只写进那个界面的 brief。工具的落地页仍然是 Persuade；时装屋的文档仍然是 Read；文档索引是 Read，不是 Persuade。新界面见 `reference/new-work.md`，Operate/Read 的深入指引见 `reference/operate.md`。

## 命令

| 命令 | 类别 | 作用 | 参考 |
|---|---|---|---|
| `craft [feature]` | 构建 | 已废弃别名，等同普通 new-work 请求 | [reference/craft.md](reference/craft.md) |
| `shape [feature]` | 构建 | 写代码前先规划 UX/UI | [reference/shape.md](reference/shape.md) |
| `init` | 构建 | 把持久的产品上下文写进 PRODUCT.md | [reference/init.md](reference/init.md) |
| `document` | 构建 | 从现有项目代码生成 DESIGN.md | [reference/document.md](reference/document.md) |
| `extract [target]` | 构建 | 把可复用的 token 与组件抽进设计体系 | [reference/extract.md](reference/extract.md) |
| `critique [target]` | 评估 | 带启发式打分的 UX 设计评审 | [reference/critique.md](reference/critique.md) |
| `audit [target]` | 评估 | 技术质量检查（无障碍、性能、响应式） | [reference/audit.md](reference/audit.md) · 原生：[reference/audit.native.md](reference/audit.native.md) |
| `polish [target]` | 精修 | 发布前的最后一道质量收尾 | [reference/polish.md](reference/polish.md) |
| `bolder [target]` | 精修 | 放大过于安全或平淡的设计 | [reference/bolder.md](reference/bolder.md) |
| `quieter [target]` | 精修 | 收敛过于激进或刺激的设计 | [reference/quieter.md](reference/quieter.md) |
| `distill [target]` | 精修 | 剥到本质，去掉复杂度 | [reference/distill.md](reference/distill.md) |
| `harden [target]` | 精修 | 上生产：错误态、i18n、边界情况 | [reference/harden.md](reference/harden.md) |
| `onboard [target]` | 精修 | 设计首次运行流程、空状态、激活路径 | [reference/onboard.md](reference/onboard.md) |
| `animate [target]` | 增强 | 加有目的的动效 | [reference/animate.md](reference/animate.md) |
| `colorize [target]` | 增强 | 给单色界面加有策略的颜色 | [reference/colorize.md](reference/colorize.md) |
| `typeset [target]` | 增强 | 改善字体层级与字体选择 | [reference/typeset.md](reference/typeset.md) |
| `layout [target]` | 增强 | 修间距、节奏与视觉层级 | [reference/layout.md](reference/layout.md) |
| `delight [target]` | 增强 | 加个性与记忆点 | [reference/delight.md](reference/delight.md) |
| `overdrive [target]` | 增强 | 突破常规极限 | [reference/overdrive.md](reference/overdrive.md) |
| `clarify [target]` | 修复 | 改善 UX 文案、标签与错误提示 | [reference/clarify.md](reference/clarify.md) |
| `adapt [target]` | 修复 | 适配不同设备与屏幕尺寸 | [reference/adapt.md](reference/adapt.md) · 原生：[reference/adapt.native.md](reference/adapt.native.md) |
| `optimize [target]` | 修复 | 诊断并修 UI 性能 | [reference/optimize.md](reference/optimize.md) |
| `live` | 迭代 | 视觉变体模式：在浏览器里点选元素，迭代备选方案 | [reference/live.md](reference/live.md) |
| `generate [n] [action] [element]` | 迭代 | 为指定元素生成变体/版本/备选，在 live 浏览器里挑选 | [reference/generate.md](reference/generate.md) |

### 路由

- **没有参数**：读 `reference/routing.md`，给出它的上下文感知菜单；永不自动执行某个命令。
- **明确或明显要执行某个命令**：加载它的参考文件（原生平台用 native 变体）并照做。两个命令都合适时问一次。
- **问工作流或怎么选命令**：读 [routing.md 的 Workflow questions 一节](reference/routing.md#workflow-questions)。
- **其余情况**：当成通用设计工作。缺 PRODUCT.md 时，新界面或替换视觉世界先走 init，再进 new-work；对现有代码的窄幅精修则直接在既有实现上做，事后提议 init，不要因为它卡住不动。
- `teach` 是 `init` 的别名。`craft` 是普通 new-work 的废弃别名，不增加任何行为。`shape` 负责任务发现，只在视觉世界与界面概念决策时进入 new-work。

init 写完 PRODUCT.md 后直接继续，不必重跑上下文加载；它记录的平台是 `ios`、`android` 或 `adaptive` 时，init 自己会加载对应的原生参考。

## 执行顺序

1. **读上下文。** 读 PRODUCT.md 与 DESIGN.md（长的当地图用，只读任务需要的章节）、匹配的 surface brief，原生平台再加平台指引；按其中的指令行事，不要重跑。
2. **加载这次请求的 playbook。** 明确或隐含到某个子命令时读它那一行对应的参考；新界面、替换视觉世界、按已批准构图构建时读 `reference/new-work.md`。有些 playbook 分几部分，同一步里只读这次需要的那部分：创建或替换视觉世界（重设计、新外观、没有既定世界）时读 `reference/new-work-world.md`；按已批准构图构建或走构图主导路线时读 `reference/new-work-comp.md`；在本上下文里跑 Assessment A 的评审（原生平台，或没有子代理工具）读 `reference/critique-rubric.md`，委托出去的 Assessment A 把该文件路径写进它的提示词。动手前先看清目标与现行视觉事实。应用跑不起来时，从已提交的视觉回归基线或截图夹具开始，按当前 token、CSS、组件或资产核对目标与新鲜度，解掉冲突，并对比主题/变体截图。
3. **动手前读质量底线。** 分析和方向定下来之后，在**任何 UI 编辑之前**（包括很小的调整）立即读 `reference/craft-floor.md`。它承载质量底线、绝对禁令，以及任何检测器都抓不到的默认反射。只做规划不编辑时不要加载它。

**降级口令**：读到本移植版边界表里标注不可用的步骤时，先说明一句「引擎不可用，我直接按参考清单执行」，然后照参考文件继续，不要重试、不要伪造执行结果。

## 收尾检查

- 每一处改动都能追溯到用户的请求；没有夹带重构。
- 事实类内容没有发明：数字、引述、logo 要么是用户给的，要么不存在。
- 状态齐全：空、加载、错误、禁用、聚焦、悬停、按下、选中。
- 跑得起来的检查都跑了，跑不了的如实说明缺什么。