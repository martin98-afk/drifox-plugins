---
name: docx-paper
description: "按中文学术规范产出与编辑 Word 文档：Markdown 转 docx、LaTeX 公式转 Word 原生公式、三线表、标题与图表自动编号、GB/T 7714 参考文献、页脚页码、A4 学位论文样式。用户提到中文论文、课程论文、毕业设计、数模论文、.docx 排版、把 Markdown 转 Word 时使用。"
version: 1.0.0
license: MIT
metadata:
  author: Gostyan
  upstream: Gostyan/docx-skill-4-cn-paper
  localized: zh-CN
---

# 中文论文 Word 排版

把 Markdown 草稿或既有内容排成符合中文学术规范的 `.docx`：A4、2.5cm 页边距、宋体小四正文、黑体三级标题、三线表、Word 原生公式、标题与图表自动编号、GB/T 7714-2015 参考文献、页脚居中页码。

`.docx` 本质是装着 XML 的 ZIP。本技能给出三条路径：新建、从 Markdown 转、改已有文档。

**详细信息在上游原文**：完整的实现细节、XML 片段、8 个已知坑的逐条解法在 `REFERENCE.en.md`（1054 行，英文，保真未译）。本文件是中文操作入口，遇到本文没覆盖的细节就去读它。

## 环境依赖

```bash
npm install docx temml fast-xml-parser   # 在 skills/docx-paper/ 目录下执行一次
```

- `docx`：生成 OOXML 的 JS 库
- `temml`：LaTeX → MathML，供 Word 原生公式使用
- `fast-xml-parser`：XML 解析

另外按需：`pandoc`（读 docx 内容）、LibreOffice 的 `soffice`（.doc 转 .docx、转 PDF）、`pdftoppm`（PDF 转图）。`scripts/office/validate.py` 需要 `lxml` 与 `defusedxml`，按需自行安装：

```bash
pip install lxml defusedxml
```

其余 Python 脚本只用标准库（`xml.etree`、`zipfile`）。

本插件不自动装 npm 依赖，首次使用前必须手动跑上面的命令；没装时会报 `Cannot find module 'docx'`。

## 快速参考

| 任务 | 做法 |
|------|------|
| 从 Markdown 生成论文 | `node scripts/new_doc.js input.md output.docx` |
| 不改 md、直接用内置模板 | 改 `scripts/new_doc.js` 的 CONTENT 段后 `node scripts/new_doc.js` |
| 生成了文件要校验 | `python scripts/office/validate.py doc.docx` |
| 插入三线表（改 XML 场景） | `python scripts/table.py unpacked/ "1-1" "标题" --headers "…" --rows '[[…]]'` |
| 插入块公式（改 XML 场景） | `python scripts/formula.py unpacked/ "LaTeX" 1 --anchor "锚文本"` |
| 读 docx 正文 | `pandoc --track-changes=all a.docx -o a.md` |
| 拆开看 XML | `python scripts/office/unpack.py a.docx unpacked/` |
| 改完重新打包 | `python scripts/office/pack.py unpacked/ out.docx` |
| .doc 转 .docx | `python scripts/office/soffice.py --headless --convert-to docx a.doc` |
| 转 PDF 再转图 | `python scripts/office/soffice.py --headless --convert-to pdf a.docx` 然后 `pdftoppm -jpeg -r 150 a.pdf page` |

`scripts/convert_paper.js` 是上游作者转换其本人某篇论文的一次性脚本（无参数、内容写死），**不要当通用转换器用**。

## 中文排版规范

### 页面与正文

- A4：`11906 × 16838` DXA；四边页边距 2.5cm（`1418` DXA）；版心宽 `9070` DXA。
- 中文宋体，英文/数学/代码用 Cambria Math，英文正文可用 Times New Roman。
- 正文 12pt（小四）→ docx-js 里 `size: 24`（半磅）。
- 首行缩进 2 字符（`firstLine: 480` DXA）；行距默认单倍（`line: 240, lineRule: AUTO`），也可固定 20pt（`line: 400, EXACT`）或 1.5 倍（`line: 360, AUTO`）；段前段后 0。

### 三级标题

| 级别 | 字体 | 字号 | 对齐 | 行距 | 编号 |
|------|------|------|------|------|------|
| 一级 | 黑体 | 三号 16pt（`size: 32`） | 居中 | 1.2 倍（`line: 288`） | 正文写「一、二、」 |
| 二级 | 黑体 | 四号 14pt（`size: 28`） | 左对齐 | 1.5 倍（`line: 360`） | `1.1`、`2.1` |
| 三级 | 黑体 | 小四 12pt（`size: 24`） | 左对齐 | 1.1 倍（`line: 264`） | `1.1.1` |

**编号规则**：三级标题统一用「全阿拉伯数字的多级编号配置」，这是唯一能让 H2/H3 跨章正确跟踪（1.1、2.1、2.4）且保持纯阿拉伯数字的做法。若给一级用 `CHINESE_COUNTING`，二级会渲染成 `二.4` 而不是 `2.4`，这是已知的 OOXML 渲染问题。标题文本里不要手写编号，交给 Word。

### 图表与公式

- 图标题：宋体 11pt（`size: 22`），居中，加粗，图下方；段前 0.5 行（`before: 120`）、段后 3pt（`after: 60`）；格式「图 章-序」。
- 表标题：宋体 11pt，居中，无首行缩进（`firstLine: 0`），加粗，表上方；格式「表 章-序」。
- 表体必须是**三线表**：顶线与底线 1.5pt（`size: 12`），表头下细线 0.75pt（`size: 6`），其余边框全部 `BorderStyle.NONE`，表头不加底纹。
- 块公式用**三列无边框表**：[567 DXA 间隔 | 7936 DXA 公式居中 | 567 DXA 编号右对齐]；最终 docx 里不要留 `$$` 裸 LaTeX。
- 图/表标题不要手写编号，用 SEQ 域自动生成「图 章-序」。

### 参考文献（GB/T 7714-2015）

| 类型 | 标识 | 格式 |
|------|------|------|
| 期刊论文 | [J] | 作者. 题名[J]. 刊名, 年, 卷(期): 起止页. |
| 专著 | [M] | 作者. 书名[M]. 出版地: 出版者, 出版年: 起止页. |
| 学位论文 | [D] | 作者. 题名[D]. 保存地: 保存单位, 年份. |
| 会议论文 | [C] | 作者. 题名[C]//会议名. 出版地: 出版者, 年: 起止页. |
| 网络资源 | [EB/OL] | 作者. 题名[EB/OL]. (发布日期)[引用日期]. URL. |

条目样式：悬挂缩进 480 DXA，每条一个 Paragraph，走 `references` 编号引用。正文引用用上标 `[1][2]`。

### 页脚

居中页码，走 `Footer` + `PageNumber`。

## 新建文档

```bash
# 有 Markdown 时（推荐）：第一个参数是 md，第二个是输出
node scripts/new_doc.js 论文.md output.docx

# 没有 md 时：改 new_doc.js 里的 CONTENT 段，然后
node scripts/new_doc.js
```

`new_doc.js` 顶部集中定义了 STYLES / NUMBERING / 页面常量，是全套规范的权威实现；提供现成 helper：`h1/h2/h3(text)`、`body(text)`、`tableCaption/figCaption(label)`、`threeLineTable(headers, rows, colWidths)`、`ref(text)`、`blank()`。表格列宽必须相加等于 9070。

生成后用 `python scripts/office/validate.py output.docx` 校验；失败就 unpack、改 XML、repack。

## docx-js 硬规则

- 页面尺寸显式写 A4；横向时传竖向尺寸再设 `orientation: PageOrientation.LANDSCAPE`（docx-js 内部会交换宽高）。
- 不要用 `\n` 换行，用独立 `Paragraph`。
- 不要手打 unicode 项目符号，用 `LevelFormat.BULLET` 编号配置；同一个 reference 连续编号，不同 reference 各自从 1 开始。
- `PageBreak` 必须放在 `Paragraph` 里，独立使用会生成非法 XML。
- `ImageRun` 必须给 `type`（png/jpg 等）。
- 表格宽度用 DXA，不用 `WidthType.PERCENTAGE`（Google Docs 会坏）；`columnWidths` 与每个 cell 的 `width` 都要给且一致。
- 表格加 cell 边距（`margins: { top: 80, bottom: 80, left: 120, right: 120 }`）；底纹用 `ShadingType.CLEAR`，不用 SOLID。
- 覆盖内置样式时用准确 ID（`Heading1`/`Heading2`），字体要写对象形式 `{ ascii, eastAsia, hAnsi }`：写字符串只设置 ASCII 槽，中文会掉回正文宋体。
- 需要目录识别时，标题段落带 `outlineLevel`（H1 为 0，H2 为 1）。

## 编辑已有文档

三步，顺序不能变：

```bash
# 1. 拆包：抽出 XML、格式化、合并相邻 run、把弯引号转成 XML 实体
python scripts/office/unpack.py document.docx unpacked/

# 2. 改 unpacked/word/ 下的 XML（三线表/公式优先用 table.py、formula.py 生成）

# 3. 打包
python scripts/office/pack.py unpacked/ output.docx
```

改 XML 前先读 `REFERENCE.en.md` 的 XML Reference 一节（schema 合规、修订痕迹、批注、图片的完整片段）。

## 已知坑

上游在真实论文转换中踩过 8 个坑，逐条解法写在 `REFERENCE.en.md` 的「Critical Issues & Solutions」：

1. 三线表中间横线透出来 → 表体所有边框设 NONE，只留表头顶线/底线与末行底线。
2. 公式三列表出现边框 → 连 `insideHorizontal`、`insideVertical` 一起设 NONE。
3. 其余 6 条（标题编号跳号、公式编号错位、上标引用丢失、Markdown 残留编号、图片尺寸、表格列宽不齐）见原文。

遇到本文没写的症状，先查这 8 条，再 unpack 看实际 XML。

## 本地化说明

- 本文件是中文操作入口，由上游 `docx-editor-cn/SKILL.md`（1054 行，英文）提炼译写；**上游原文完整保留为 `REFERENCE.en.md`**，XML 结构与实现细节以它为准。
- 上游 SKILL.md 的 frontmatter 写 `license: Proprietary`，但随包 `LICENSE.txt` 实际是 MIT（Copyright 2025-2026 Gostyan），两者矛盾。本插件按 `LICENSE.txt` 的 MIT 条款分发并保留版权声明，`LICENSE.txt` 随技能目录一起保留。
- npm 依赖不随包分发，首次使用按上面「环境依赖」手动安装。