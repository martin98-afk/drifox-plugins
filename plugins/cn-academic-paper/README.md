# 中文论文

中文论文从写到成稿。两个技能分工：一个管「该写什么」，一个管「排成符合学校要求的 Word」。

## 两个技能

| 技能 | 来源 | 管什么 |
|---|---|---|
| `research-writing` | [zLanqing/codex-claude-academic-skills](https://github.com/zLanqing/codex-claude-academic-skills)（6.3k★，MIT）的 `research-writing-skill` | 中文优先的写作原则、七段式章节写法、修改润色规则、审稿回复、交付前自检。20 个参考文件覆盖论证规划、章节修辞、图表规划、编辑视角判断 |
| `docx-paper` | [Gostyan/docx-skill-4-cn-paper](https://github.com/Gostyan/docx-skill-4-cn-paper)（500★，MIT） | 按中文学术规范产出 `.docx`：Markdown 转 Word、LaTeX 公式转 Word 原生公式、三线表、标题与图表自动编号、GB/T 7714-2015 参考文献、页脚页码、A4 学位论文样式；也能编辑既有 docx（unpack → 改 XML → pack） |

`research-writing` 是纯文本，装完即用。`docx-paper` 需要一次 npm 安装。

## 装机后必做：装 npm 依赖

`docx-paper` 的转换脚本依赖三个 npm 包，DriFox 只自动装 pip，装不了 npm。首次使用前在技能目录跑一次：

```bash
cd ~/.drifox/plugins/cn-academic-paper/skills/docx-paper
npm install
```

装的是 `docx@9`、`fast-xml-parser`、`temml`（LaTeX → MathML）。没装时脚本会报 `Cannot find module 'docx'`。

## 用法

**写作**（自动命中 `research-writing`）：

- `帮我写这篇论文的引言，主题是…`
- `把这段实验结果改成论文口吻，别用「显著提升」这种词`
- `审稿人说我相关工作写得太像流水账，怎么改`
- `这篇稿子的摘要按问题/方法/结果/贡献重写`

**排版**（自动命中 `docx-paper`）：

- `把 论文.md 转成符合学校格式的 docx`
- `这个 Word 里的三线表边框不对，改一下`
- `公式要 Word 原生公式，不要图片`
- `参考文献按 GB/T 7714 排`

## 排出来的样子

A4、四边 2.5cm 页边距、宋体小四正文、单倍行距、首行缩进 2 字符；一级标题黑体三号居中（一、二、）、二级黑体四号（1.1）、三级黑体小四（1.1.1）；图题在图下、表题在表上、都用 SEQ 域自动编号；表格强制三线表（顶底 1.5pt、表头下 0.75pt、无竖线）；块公式用三列无边框表（间隔 1cm | 公式居中 | 编号右对齐）；参考文献悬挂缩进、正文上标 `[1][2]`；页脚居中页码。

## 目录

```
plugins/cn-academic-paper/
├── .drifox-plugin/plugin.json
├── skills/
│   ├── research-writing/
│   │   ├── SKILL.md              中文正文：原则、工作流、七段式、自检
│   │   └── references/           20 个写作参考（英文原文，按需读）
│   └── docx-paper/
│       ├── SKILL.md              中文操作入口：规范、命令、硬规则、已知坑
│       ├── REFERENCE.en.md       上游原文 1054 行（XML 细节与 8 个坑的逐条解法）
│       ├── scripts/              new_doc.js（md→docx）、table.py、formula.py、office/（unpack/pack/validate）
│       ├── package.json          npm 依赖声明
│       └── LICENSE.txt           上游 MIT 版权声明
└── LICENSE-zlanqing.txt          写作技能的上游 MIT 版权声明
```

## 与上游的差异

- `docx-paper` 的上游 SKILL.md 是 1054 行英文技术手册，这里改写成中文操作入口（5534 字符），**上游原文完整保留为 `REFERENCE.en.md`**，XML 结构与实现细节以原文为准。
- 上游 SKILL.md 的 frontmatter 标 `license: Proprietary`，但随包 `LICENSE.txt` 是 MIT（Copyright 2025-2026 Gostyan）。两者矛盾，按 `LICENSE.txt` 的 MIT 条款分发并保留版权声明。
- `scripts/convert_paper.js` 是上游作者转其本人某篇论文的一次性脚本（无参数、内容写死），不是通用转换器；通用入口是 `new_doc.js`。
- 未收 `zLanqing` 的 `office-academic-skill`（与 `docx-paper` 重叠）与 `scientific-toolkit-skill`（20 个科学计算子技能，偏 Python 库用法）。

## 许可

两个上游都是 MIT。`LICENSE-zlanqing.txt`（Copyright 2026 zLanqing）与 `skills/docx-paper/LICENSE.txt`（Copyright 2025-2026 Gostyan）随包保留。

## 图标

图标符号取自 [Lucide](https://lucide.dev) 的 `file-text`（文稿），ISC 许可，见 `LICENSE-lucide.txt`。
