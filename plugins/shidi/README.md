# shidi

科研与工作中的「师弟」。用户给想法和方向，它负责拆解、执行、交付：文献调研（多角度检索 + 评分标注 + 报告）、设计实验方案（含文献支撑）、科研作图、精读论文、数据整理。

## 迁移来源

- 上游包：`shidi-dsh-plugin`（npm）
- 上游 license：MIT

## 两种模式

| 模式 | 触发 | 特点 |
|---|---|---|
| Pro（默认） | 「详细调研」「pro 模式」或不指定 | 完整检索框架、交互确认、结构化深度交付 |
| Flash | 「快速调研」「flash 模式」 | 少确认，快速形成小范围方案并启动检索 |

入口技能 `skills/shidi/SKILL.md` 只做模式路由，真正的流程在 `modes/pro/` 与 `modes/flash/` 下，两套各自带 references 与 scripts。

## 脚本

`modes/*/scripts/` 下 5 个脚本（`fetch_pdfs.py` / `extract_pdfs.py` / `score_papers.py` / `verify_refs.py` / `render_report.py`）纯标准库实现，无第三方依赖：

- 抓取与解析走 `urllib` + 正则，不依赖 requests
- PDF 抽取需要外部 `pdftotext` 或 PyMuPDF（脚本内会探测，缺失时给提示）

## 与 dsh 原包的差异

- `index.mjs` / `skills.mjs` 只做一件事：把 `skills/` 挂到 dsh 的 skills 注册表。DriFox 目录即技能，这层不需要，未迁移。
- `modes/pro/SKILL.md` 与 `modes/flash/SKILL.md` 的 frontmatter 都写着 `name: shidi`（上游用同一名做模式切换）。DriFox 只把 `skills/shidi/` 识别为技能目录，modes 下的两份作为被引用的流程文件存在，不受 name 一致性校验影响。
- `cordis.patch.yml` 的 group 挂载逻辑未迁移（DriFox 无 cordis 运行时）。
