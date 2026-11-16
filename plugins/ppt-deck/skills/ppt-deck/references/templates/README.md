# 版式参考库（16 套 / 192 页）

从 DSH Desktop（`dataelement/dsh-desktop`，tag `v0.9.2`）的 PPT 运行时迁移而来。每套含：

- `design.md`：配色、字体、栅格、版式语法、12 页结构说明
- `pages/01.jpg … 12.jpg`：1280×720 英文版预览

**这不是 `ppt_deck` 的 theme。** 生成器仍只有 `data / swiss / velvet / soft / bold` 五套主题。本库用于两种情况：

1. 选主题阶段，需要更具体的版式参照（栅格、页序、图表位置）；
2. 用户要求"像咨询报告 / 像杂志 / 像发布会"而现有五套都不贴时，按某套的视觉规则自定义 HTML/CSS。

**只借版式，不借内容。** 示例里的公司名、数字、结论都是虚构素材，必须替换为用户材料。

## 目录

| 分类 | 目录 | 风格 | 适合 |
| --- | --- | --- | --- |
| 教学研究 | `academic/dsh-course-workshop` | 米白 + 墨绿，固定学习目标边栏、概念图、自测 | 培训、课程、工作坊 |
| 教学研究 | `academic/dsh-monochrome` | 黑墨米纸，超细无衬线 + 衬线斜体引文 | 论文汇报、极简研究 |
| 商务 | `business/dsh-blue-professional` | 奶油底 + 单一钴蓝，咨询级克制 | 方案汇报、客户提案 |
| 商务 | `business/dsh-neo-grid-bold` | 12×8 块网格，荧光黄，重海报 | 强势结论、发布会 |
| 咨询 | `consulting/curated-swiss-signal-grid` | 纸白/纯黑/信号红，超大数字、竖排索引 | 管理汇报、指标复盘 |
| 咨询 | `consulting/dsh-cartesian` | 暖石五色，衬线标题，博物馆图录 | 研究简报、战略分析 |
| 咨询 | `consulting/dsh-signal` | 奶油 + 深海军蓝 + 古金，杂志式情报简报 | 决策简报、尽调 |
| 观点叙事 | `editorial/dsh-editorial-notebook` | 双栏论述 + 边注 + 证据条 + 决策矩阵 | 研究、观点、业务叙事 |
| 观点叙事 | `editorial/dsh-soft-editorial` | 暖色杂志跨页，衬线标题 | 品牌故事、长文提炼 |
| 推广 | `promotion/dsh-broadside` | 橙黑宣言，大号粗体 | 活动、宣言、招聘 |
| 推广 | `promotion/dsh-playful` | 杏色底 + 炭黑，手作感 | 创意提案、社群分享 |
| 推广 | `promotion/dsh-sakura-chroma` | 复古彩带，六色主色 + 暖棕 | 文化、消费品、复古主题 |
| 运营 | `work/curated-modular-logistics-system` | 工业白 + 石墨模块 + 安全黄 | 供应链、流程、组织 |
| 运营 | `work/curated-nordic-operating-report` | 暖纸 + 深钢蓝 + 雾蓝 | 年度经营报告、董事会 |
| 运营 | `work/dsh-editorial-forest` | 深林绿 + 粉 + 米，文学季刊 | 品牌手册、可持续主题 |
| 运营 | `work/dsh-engineering-blueprint` | 纸底 + 墨 + 砖红，工程网格 | 架构评审、技术方案 |

## 怎么用

1. 读本表选 1 套，打开它的 `design.md`，看 `Typography` / `Layout grammar` / 12 页结构。
2. 看 2–3 张 `pages/*.jpg`，确认页序与信息密度是否符合材料。
3. 从 12 页里挑结构（例如"三支假设树""贡献瀑布""决策门槛路线图"），用用户内容重建；不要整页当背景，也不要把示例数字带进去。
4. 通用排版规则见同目录 `composition.md`（页序、证据与解读、图表标注、中英文重排）。

## 来源与许可

- 迁移自 `dataelement/dsh-desktop` 的 `packages/ppt-runtime`（tag `v0.9.2`），MIT。
- 10 套改编自 Zara Zhang 的 [`beautiful-html-templates`](https://github.com/zarazhangrui/beautiful-html-templates)（commit `e5e204fb1f3b06290846e7dcd7aceddabeceec8c`），MIT。
- `dsh-engineering-blueprint`、`dsh-course-workshop` 改编自 [`nexu-io/html-anything`](https://github.com/nexu-io/html-anything) 的 `deck-blueprint` / `deck-course-module`（commit `c31204544230578ac814026fecc153c6e36587ae`），Apache-2.0。
- 三套 `curated-*` 为 WorkBuddy / DSH 原创。
- 完整声明与许可证原件在 `_LICENSES/`：`THIRD_PARTY_NOTICES.md`、`LICENSE-dsh-ppt.txt`、`LICENSE-zara.txt`、`LICENSE-html-anything.txt`。
- 不随包分发任何字体文件；`design.md` 只声明字体名与平台回退。
