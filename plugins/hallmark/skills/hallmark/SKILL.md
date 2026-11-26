---
name: hallmark
description: "网页与新页面的设计技能，让界面看起来是「做出来的」而不是「生成的」。用户要求新建或设计页面、落地页、定价页、组件、应用界面时使用，或用户点名 Hallmark。不要用于已有设计的改动，除非用户点名，例如 /hallmark redesign <path>。"
argument-hint: "<prompt> | redesign <path> | audit <path>"
version: 2.0.0
license: MIT
metadata:
  author: Nutlope
  upstream: Nutlope/hallmark
  upstream_commit: 04977e15f3dfd6ee4b74c887dac3eb52665d6c92
  localized: zh-CN
---

# Hallmark

让编码助手生成的界面看起来是有人做的，而不是模型吐的：一条不可协商的底线，压住所有模型都被训练进去的默认样式；一次发牌式的方向抽取，避免连续几次构建收敛成同一个样子；一个屏幕只讲一件事。底线之上归你：你是一个有判断力的设计师。

**路径约定**：下文命令里的 `<skill-dir>` 指本 SKILL.md 所在目录（即 `skills/hallmark/`）。执行前先定位它，例如按插件安装目录拼出绝对路径，再替换进去；`references/` 与 `scripts/` 都相对这个目录。

## 底线（The Floor）

它对每一次输出生效，任何场景都不豁免，即使你没读本文件后面的任何内容。

1. 每一种颜色、每一种字体，都必须走 `:root` 里声明的 token（或声明的主题块）。token 块之外不许出现字面颜色值或 `font-family`。(48)
2. 永不用 `transition: all`。永不给 `width`、`height`、`top`、`left` 做动画。(10a)
3. 罗马正体标题里不许夹一个斜体词。(38i)
4. `html` 与 `body` 都要写 `overflow-x: clip`。不许用 `hidden`，不许用 `100vw`。(34)
5. 承载图片的网格轨道用 `minmax(0, 1fr)`；展示型标题带 `overflow-wrap: break-word; min-width: 0`。(50)
6. 每个可交互元素都要有 `:focus-visible`，且即时出现。(26a, 15)
7. 每段动画都要有 `prefers-reduced-motion: reduce` 的降级，关掉脚本后内容仍然可见。(27, 62)
8. 永不编造指标、证言、logo 墙或案例数量。(46a)
9. 永不用 eyebrow 小标签，永不用加大字距的大写或小型大写：标签、图注、表头、tag、导航链接都用正文字体（或主题的标签字体），小一号，句首大写或全小写，不加字距。(54, 67)
10. 永不用中点拼接的 meta 串、紧贴链接文字的箭头、装饰性状态圆点。(63)
11. 永不用紫到蓝的渐变、卡里套卡、拿 emoji 当图标、手绘的浏览器或系统窗口。(2a, 4, 30a, 47a)
12. hero 的标题、一句话说明、主操作，在 1280 x 800 下不滚动就能全部看见。(44b)
13. 任一屏幕约 80 词；hero 的文字就是标题、一句话、以及它的操作项。(58)
14. 容器有上限并居中：1920 宽时增长的是边距，版心与网格不变。(44d)
15. CSS 源码的第一条非空行是 Hallmark 印记，第二行是评审行，之后是豁免声明。(20)
16. 如果环境里有 Node，交付前跑 `node <skill-dir>/scripts/sloplint.mjs <输出文件> --render`。每一条 `FAIL` 都要修；每一条 `REFLEX` 要么修，要么在记录里豁免。

底线之上还有两类闸门：**Reflex** 是模型容易滑进去的默认做法，可以带上真实理由、记录在案后豁免；**Finish** 是手艺细节，必须回答，但不阻断交付（见 `references/gates.md` § 1 与 § 2）。

## 流程（Flow）

0. 预检：先读项目，再开口问。
1. 只问一次：素材、受众、用途、调性。
2. 定型：先把页面设计出来，再给它命名。
3. 定方向：发一个主题，或用户要求定制时自由设计。
4. 加载 layout、imagery、craft、genre、theme 与 `gates.md` § 1 至 § 4。
5. 输出 Picks 块，只输出一次。
6. 构建：先 hero，再整页；印记、`tokens.css`、日志。
7. 清扫：`sloplint --render` 跑干净，过判定闸门，做完成评审，最后给出素材清单。

**动词（Verbs）**：仅当用户点名 Hallmark 时可用：`redesign <target>`（保留内容与接线的整体重设计）、`audit <target>`（出一份报告）；先读 `references/redesign.md`。对已有设计的其他修改不算一次 Hallmark 运行：按用户要求在该项目自己的体系里改。

## 0. 预检（Pre-flight）

按顺序找信号：根目录的 `design.md` 或 `DESIGN.md`（已锁定的体系，它的优先级高于本文件的一切，多个页面共享它）；`.hallmark/brand-spec.md`，或 prompt 里点名了真实品牌（读 `references/brand-truth.md`，永不凭记忆给真实品牌套主题）；项目自己的字体、配色、间距、动效库与框架（`package.json`、Tailwind 配置、`:root`、tokens、字体链接）；**产品本身**：一个 URL、一个跑着的 dev server、一条命令就能起来的项目、机器上已装的 app，用 `scripts/capture.mjs` 抓取（`imagery.md` § 4）；一个 Inspo MCP server（`mcp__inspo__*` 工具，信号 8，见 `flow.md` § Signal 8；`/hallmark` 形式的 prompt、点名 Hallmark 或要求定制，都压过它）；设了 `TOGETHER_API_KEY`（信号 9，构图步骤）。

输出一个块（file:line 引用、保留了什么、引入了什么），缓存到 `.hallmark/preflight.json`（`flow.md` § Pre-flight）。

## 1. 只问一次（Ask once）

即使 prompt 只有五个词，也只发一条消息：

> *开工前四件事。1. **素材**，最关键的一项：这个页面能展示什么？截图或录屏（或者把 app、URL、目录给我，我自己跑起来截），你的照片，真实数字（客户数、可用率、价格），带署名的引述，你有权使用的 logo。贴上来或给路径都行；没有照片时我先用 Hallmark 图库里的占位图，之后你用真实的替换，我绝不编造数字、引述或 logo。2. **受众**：谁在用，他们关心什么？3. **用途**：这个页面要推动的唯一动作是什么？4. **调性**：选一个极端（editorial、brutalist、soft、utilitarian、luxury、playful、technical、austere）；「干净现代」不算调性。再加 4 到 8 个词的氛围描述，有色锚就一起给。或者说一句 **你直接来**，我自己推断并告诉你我选了什么。*

用户跳过的项视为放弃回答：自己推断，在回复开头用一行说明推断了什么，并写进印记；不再追问。事实类信息永不许推断：没给的数字、引述、logo 就是不存在的；没给的图片就是槽位里的占位图。当 prompt 已经回答了这四项，或根本没人能回答（无人值守运行、批量任务），不要发这条消息。

**Genre（品类）**，在后台判断：*AI 工具、生成式、音乐、视频、语音、暗色、氛围* → **atmospheric**；*SaaS、企业、API、平台、开发者工具、基础设施、B2B* → **modern-minimal**；*活泼、有趣、友好、柔软、儿童、游戏、社区* → **playful**；其余归 **editorial**，多数消费类与家庭场景都在这里。主题一旦发出，它的 genre 优先（genre 文件、印记、`--genre`）。两个非默认 genre 同时命中时，在那条消息里加一个二选一，或直接选一个并说明。

**Scope（范围）**：prompt 只点名一个元素（按钮、输入框、卡片、弹窗、导航、页脚、标签条、chip），或说「只要那个 X」，就是一个组件（`flow.md` § Component scope）。有人真的在里面干活的界面（仪表盘、后台、设置、工具）是应用界面（`flow.md` § App screens）。

## 2. 定型（Shape）

**素材先行。** 先清点，一行写完：*real*（prompt 与项目提供的一切具体事实：名称、主张、数字、地点、日期、图片）、*pictures*（页面展示什么图，每张从哪来：用户给的、真实产品的截图、真实构建出来再截、图库）、*absent*（它一定不会有的证据：没人给过的 logo、引述、指标）。形态跟着素材走：有图的页面以图开篇（`imagery.md` § 1）；以文字为主的页面承载的是字体与事实（长文档、信件、索引优先、宣言）。

**任务。** 说清访客来这里做什么（订阅、预约、到访、参会、购买、试用、注册、招聘、加入、收听），再在 `references/anatomy.md` 里读这一类真实站点怎么放动作、围绕哪些区块组织（菜单、阵容、期号、唱片）、怎么收尾。页面从这个解剖结构长出来，永不套用默认的「数字 + 三步 + 邮箱表单」。(85)

然后设计页面：整体形态、开篇方式、每个区块的内容与构图、导航、页脚、hero 由什么承载。起点：`references/macrostructures.md` 里的 21 种形态（只读你选中的那一个文件）；构图、导航、页脚见 `layout.md`。

**发牌（The draw）。** 走主题路线时，第 3 步选定主题后运行：

```
node <skill-dir>/scripts/theme.mjs draw --material photo|product|words --job <job> --theme <slug> [--log .hallmark/log.json]
```

它会避开日志里用过的与主题自己的图，发给你：一种形态、hero 姿态、导航、页脚、第一个区块、动作位置、两个应弃用的构图、hero 主打什么。除非素材确实不允许，否则照它做；任何替换都要在 Picks 块里点名。「同一个 prompt、同一个主题，做两次得两个页面」才算过。**镜像测试**：同品类的相邻 prompt 会不会得到完全同一套组合？会，就改掉一个决策并说明改了什么。

**签名（Signature）。** 访客唯一会记住的东西：这个 prompt 里最强的真实之物，以最好看的方式展示（那张就是这个地点的照片、产品干它唯一那件事、因为它是卖点所以放得极大的价格、一个可以上手的控件）。用主题的材质呈现（定制路线用它自己的语言），放在首屏，在 Picks 块与印记里点名。把一个数字画成计数符号是装置，不是签名。(82)

这些全部先在心里定住，到第 5 步才一次性说出来。

## 3. 定方向（Direction）

按顺序，先命中先用。

1. **用户点明了主题** → 照它建（印记写 `theme: <name> (by request)`）。
2. **用户要求定制**（custom、重新推演、量身定做、不要主题、要一个自己的世界）→ 读 `references/direction.md`：设计由你做主。它接管发牌、形态、`layout.md`、genre 文件以及第 6 步的构图与首屏规则；底线、闸门、清扫仍然生效。用户没表态时永不走这条路。
3. **其余情况，发一个主题：**

```
node <skill-dir>/scripts/theme.mjs deal --genre <genre> --prompt "<the prompt>" [--log .hallmark/log.json]
```

它发出三个贴合 prompt 且避开了日志的主题。看这三张图，选素材能承载 prompt 的那个（动效、照片、代码），说明选了哪个、为什么，然后只加载 `references/themes/<slug>.md`。只在用户要求时重发（`--reroll 1`）。没有 Node：手工从 `references/themes/index.json` 里挑，印记写 `deal: manual`。

主题是材质，不是方案：它从不决定页面装什么、按什么顺序装。当它与形态、genre 或手艺文件在素材、控件、动效上冲突时，主题优先；底线与用户自己的话压过两者。

## 4. 加载（Load）

页面构建只读这些：`references/layout.md`、`references/anatomy.md`（与任务对应的部分）、`references/imagery.md`、`references/craft.md`、`references/genres/<genre>.md`、`references/themes/<slug>.md` 及它发牌时已经看过的那张图（用户点名主题时，现在就去看 `<slug>.jpg`）。从主题里取配色比例、字体语气、表面处理与它的 Range（不依赖照片也能撑起的区块），永不取它的版式；`references/gates.md` § 1 至 § 4。定制路线用 `direction.md` 替代 layout、genre、theme 三个文件。

只在需要时读 `references/` 下的：某个 macrostructure 文件；有状态 UI 读 `microinteractions.md`；表单读 `interaction-and-states.md`；非常规版式读 `responsive.md`；主题点名纹理时读 `texture.md`；滚动叙事读 `scroll-choreography.md`；明暗双模式读 `dark-mode.md`；图表读 `data-viz.md`；定制路线读 `fonts.md`；信号 9 时读 `comp.md`（构图、生成静帧）；需要锁定体系时读 `design-md.md`。

`gates.md` § 5 要等到第 7 步，§ 6 属于评审；多读就是最大的可避免成本。

## 5. Picks 块

这是整轮唯一一次复述决策，也是用户改口的机会：

```markdown
**Hallmark · v2.0.0**
- **Shape** · Workbench，来自 draw 7f3a2c · genre modern-minimal · 任务：注册，动作在 hero 与价格旁各一处
- **Theme** · Coral，deal 2/3（暖灰、一处珊瑚信号、General Sans、柔和胶囊）· 在纸带上压过 Cobalt
- **Chrome** · 导航：贴边对齐，一个字标加一个动作 · 页脚：报头，字标压在链接之上
- **Hero** · Stage：标题占 1 到 5 列，图槽占 6 到 12 列、560px，居中
- **Signature** · 在 hero 里实时构建的催款发票列表
- **Sections** · Hero（发票列表）· Pinned（一笔逾期，三段追讨）· Switcher（客户视角与你）· Table（定价）· Footer
- **Material** · real：2 分钟接入、CSV 导入、里斯本 · pictures：hero 里实时构建的发票列表、图库的里斯本工作室照片（降饱和）· absent：logo、引述、指标
- **Sweep** · 构建后运行
```

定制路线的行写在 `direction.md` 里。之后补一行轻描淡写的话，组件范围或已有 `design.md` 时跳过：*要把体系固定下来吗？说「锁住体系」，我生成 `design.md`。* 信号 9 时，`comp.md` 在这一步介入。

## 6. 构建（Build）

- **从脚手架开始。** `node <skill-dir>/scripts/theme.mjs scaffold <slug>`（带上发牌时的 `--dealt`；定制路线用 `--custom`）会在项目样式表旁边写出 `tokens.css`（主题 token 与共享尺度）与 `base.css`（底线已经定下的部分），并打印印记骨架、两行 import、槽位脚本。你只写页面本身。
- **`references/patterns.md` 读一次**：控件的八种状态、一个图槽、一条缺失的事实、一个暂时没有后端的表单、一次揭示、可对比的数字。取它们的形状，永不抄它们的文案。
- **hero 优先。** 先写导航与 hero，下面什么都不写，跑 `node <skill-dir>/scripts/sloplint.mjs <file> --render --stage hero`，再用全新上下文做 hero 评审（`gates.md` § 6）。hero 过关后再建其余区块；图片署名与整页检查等整页完成。
- **一个屏幕一个想法，做大。** Hero：标题不超过七个词（50 字符），一句话不超过十二个词，一到两个动作。六到九个区块，含 hero 与页脚（prompt 很薄时五个），最多 450 个可见词，每块都是这个品类自己的内容，放在有分量的构图里（`layout.md` § 4 与 § 5）。hero 就是第一屏，也只是第一屏，它的姿态由任务决定（`layout.md` § 6）。饱满来自尺度与图片，永不来自更多文字（77 至 79）。
- **展示，不要描述**（`imagery.md`）。页面展示真实的东西：用户的图片、用 `scripts/capture.mjs` 抓的真实产品截图（只要能接触到）、接触不到时才高保真重建产品、或图库照片（`node <skill-dir>/scripts/theme.mjs photos "<subject>" --theme <slug>`），要大，按主题的处理方式呈现，放在用户文件能替换的槽位里，每张图库照片在页脚署名。hero 以下的图片最多占页面三分之一，永不连续两个照片主导的区块，其余由主题的 Range 撑起（83）。永不用图库站点的 URL、手绘插画（80）、空白糊色（81）、一排计数符号（82）或编造的数字。
- **页面不变量**（F15）：一种主按钮样式、一个容器宽度、hero 以下一种列间距、每层嵌套一个圆角半径、居中标题组永不多于左对齐标题组。
- **字体与动效**（`craft.md` § 1 与 § 5）。用主题的字体，最多两个字族（可以第三个做异类角色）；正文 16px 起；标题一种字重一种颜色（38iii）；标签永不用等宽，除非等宽就是材质（64）。每个控件八种状态；只用 `transform` 与 `opacity`；最多一次揭示动效，主题本来就是静的就不做，默认可见。
- **印记。** CSS 第 1 行是脚手架给的印记骨架，每个字段都要填，第 2 行是评审行（`gates.md` § 3），之后是 `waive` 与 `answered` 行，全部落在前 40 行内。
- **已有样式表只许追加**：import 紧跟在最后一个 `@import` 之后，永不放进规则或 `@tailwind` 指令下面；复用项目已有的 token 名（`references/export-formats.md`）。
- **日志。** `node <skill-dir>/scripts/theme.mjs log --entry '<json>'` 把这次构建写到 `.hallmark/log.json` 顶部，字段包括 rotation 要读的那些（`shape`、`theme`、`axes`、`hero`、`nav`、`footer`、`imagery`、`photos`、`entry`、`fingerprint`、`sections`、`signature`、`waived`、`prompt`），漏了什么它会点名。

## 7. 清扫（Sweep）

1. `node <skill-dir>/scripts/sloplint.mjs <files> --genre <genre> --render`（适用范围写明 `--scope component` 或 `--scope app`；框架项目里用 `--url http://localhost:<port>/<route>` 并保持 dev server 运行）。修掉每一条 FAIL，重跑到干净为止。render 档会生成截图；永不用手去操作浏览器。
2. 读 `references/gates.md` § 5，走 J 与 R/J 闸门。每一条 WARN 都要确认或驳回。底线项发现的问题全修；Reflex 项修或豁免；Finish 项逐条回答。
3. 用全新上下文做完成评审（`gates.md` § 6；评审者读自己的提示词，你永不去打开 `review-*.md`）：按它第一个词行动（`recapture`、`rebuild`、`fix`、`ship`），修完之后自己给分。
4. 收尾时给出素材清单：每个槽位、尺寸、该放什么，然后指出最该补的那一件素材。
5. 更新 Picks 块：构建过程中有变化的行，以及最后一行的结果（`Floor 0 FAIL · Reflex 2 (1 waived: 47b) · finish-review: subagent, 3 resolved`）。伪造通过本身就是 slop。

验证是有预算的：一轮批量检查、一批修复、最多一轮确认；每加一次评审就要加一批修复和一次重拍。

## 分支（Branches）

 `references/flow.md` 一次读一节：组件范围、应用界面、信号 8、先构图后构建、各 harness 的杠杆、预检的边缘情况、**fast 模式**（`--fast`，或 prompt 说快、粗糙、原型）以及编辑时钩子。在已有项目里，先点名你要碰的文件；未经用户批准的文件级方案，永不删路由或组件树。

## 本地化说明

- 本文件由英文原文（`Nutlope/hallmark` @ `04977e1`）译写为中文。`references/` 与 `scripts/` 保留上游英文原文，未作改动；读到中文条款与英文参考冲突时，以英文参考的文件事实为准。
- `scripts/` 只依赖 Node 内置模块，无第三方 npm 依赖。环境里没有 Node 时，发牌与 lint 两步降级为手工：主题从 `references/themes/index.json` 挑（印记写 `deal: manual`），闸门按 `gates.md` 人工走，并在交付说明里注明「未运行 sloplint」。
- 上游的 Together AI 构图步骤（信号 9）需要 `TOGETHER_API_KEY`，没有就跳过，不要伪造构图。