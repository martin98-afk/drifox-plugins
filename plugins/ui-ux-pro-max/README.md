# UI/UX Pro Max 设计智能

本地可搜索的 UI/UX 知识库。不是让模型凭记忆给设计建议，而是查表：80 种风格、194 套产品配色、74 组字体搭配、141 条 UX 准则、25 类图表、23 个技术栈。

迁移自 [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)（154k★，MIT，v2.0.0），7 个技能的正文译写为中文，`references/`、`data/`、`scripts/` 保留上游原文。

## 七个技能

| 技能 | 管什么 |
|---|---|
| `ui-ux-pro-max` | 主入口：10 类规则的优先级表、查询契约、`--design-system` 一条命令出整套体系、Step 1-4 流程 |
| `design` | 综合入口：logo（55 风格）、CIP（50 交付物）、图标（15 风格）、社交配图、横幅、幻灯片的统一路由 |
| `design-system` | token 三层架构、组件规格、幻灯片决策系统（BM25 搜索 + 8 张决策 CSV） |
| `ui-styling` | shadcn/ui + Tailwind + canvas 三层栈、组件目录、主题、无障碍、10 条最佳实践 |
| `brand` | 品牌声音、视觉识别、信息框架、资产校验、品牌同步到 token |
| `banner-design` | 多格式横幅：9 个平台尺寸、22 种美术方向、安全区与文字占比规则 |
| `slides` | Chart.js 演示稿、版式范式、文案公式 |

## 核心用法

主入口提供一条命令出整套设计体系：

```bash
python "$PLUGIN_DIR/skills/ui-ux-pro-max/scripts/search.py" "beauty spa wellness service" --design-system -p "Serenity Spa"
```

返回模式、风格、配色、字体、效果，以及要避开的反模式。加 `--persist --output-dir <项目根>` 落盘成 `design-system/<slug>/MASTER.md`，后续会话直接读；加 `--tokens css` 导出 CSS 变量；`--variance` / `--motion` / `--density` 三个 1-10 旋钮调风格跨度、动效复杂度与间距密度。

细项查询按 domain 走：

```bash
python "$PLUGIN_DIR/skills/ui-ux-pro-max/scripts/search.py" "keyboard focus modal" --domain ux
python "$PLUGIN_DIR/skills/ui-ux-pro-max/scripts/search.py" "suspense streaming bundle" --stack nextjs
```

## 数据与脚本

```
skills/ui-ux-pro-max/
├── SKILL.md           主入口（中文）
├── data/              23 张 CSV：风格、配色、字体搭配、UX 准则、图表、动效、各栈规范
├── references/        quick-reference.md（141 条 UX 准则）、pro-rules.md（交付前清单）等
└── scripts/           search.py（BM25 检索 + 设计体系生成）、design_system.py、preview.py
```

`search.py` 只用 Python 3 标准库，不需要装任何包。部分可视化脚本用到 Pillow，AI 出图脚本用到 `google-genai`，缺了就跳过对应步骤。

## 与上游的差异

- 上游用 `${CLAUDE_PLUGIN_ROOT}/.claude/skills/...` 定位脚本，本版统一改为 `$PLUGIN_DIR/skills/...`。
- 未收录 54 个 TTF 字体（`ui-styling/canvas-fonts/`，5.5MB）与 805KB 的图标上游数据 `phosphor-icons-upstream.json`：字体用系统字体或项目自带，图标按 `references/` 里的图标规则手写 SVG。
- Logo / CIP / 图标三处的 AI 出图需要 Gemini、Atlas Cloud、MuAPI 或 UberLLM 凭据，缺凭据时给 brief、配色与可直接落地的 SVG/CSS 方案，不伪造出图结果。

## 许可

MIT，见上游仓库。

## 图标

图标符号取自 [Lucide](https://lucide.dev) 的 `layout-grid`（栅格版式，对应设计体系），ISC 许可，见 `LICENSE-lucide.txt`。
