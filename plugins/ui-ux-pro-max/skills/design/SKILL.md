---
name: design
description: "综合设计技能：品牌识别、设计 token、UI 样式、logo 生成（55 种风格，Gemini / Atlas Cloud / MuAPI / UberLLM）、企业识别系统 CIP（50 项交付物与 mockup）、HTML 演示（Chart.js）、横幅（22 种风格，社交/广告/网页/印刷）、图标设计（15 种风格，SVG）、社交配图（HTML→截图，多平台）。动作：设计 logo、做 CIP、生成 mockup、做幻灯片、设计横幅、生成图标、做社交配图、品牌识别、设计体系。平台：Facebook、Twitter、LinkedIn、YouTube、Instagram、Pinterest、TikTok、Threads、Google Ads。"
argument-hint: "[设计类型] [上下文]"
version: 2.1.0
license: MIT
metadata:
  author: claudekit
  upstream: nextlevelbuilder/ui-ux-pro-max-skill
  localized: zh-CN
---

# Design

统一的设计技能：品牌、token、UI、logo、CIP、幻灯片、横幅、社交配图、图标。

## 什么时候用

- 品牌识别、语气与素材
- 设计体系 token 与规格
- shadcn/ui + Tailwind 的 UI 样式
- logo 设计与 AI 生成
- 企业识别系统（CIP）交付物
- 演示稿与路演稿
- 社交、广告、网页、印刷的横幅
- Instagram、Facebook、LinkedIn、Twitter、Pinterest、TikTok 的社交配图

## 子技能路由

| 任务 | 子技能 | 说明 |
|------|--------|------|
| 品牌识别、语气、素材 | `brand` | 随包同级技能 |
| Token、规格、CSS 变量 | `design-system` | 随包同级技能 |
| shadcn/ui、Tailwind、代码 | `ui-styling` | 随包同级技能 |
| Logo 创作与 AI 生成 | Logo（内置） | `references/logo-design.md` |
| CIP mockup 与交付物 | CIP（内置） | `references/cip-design.md` |
| 演示稿、路演稿 | Slides（内置） | `references/slides.md` |
| 横幅、封面、页头 | Banner（内置） | `references/banner-sizes-and-styles.md` |
| 社交图与配图 | Social Photos（内置） | `references/social-photos-design.md` |
| SVG 图标与图标集 | Icon（内置） | `references/icon-design.md` |

## 脚本路径

本技能与其 `references/` 里的脚本路径，相对于本 SKILL.md 所在目录，不是项目目录：`scripts/<file>` 是本技能自己的 `scripts/`，`../<skill>/scripts/<file>` 是同级子技能的。用这个目录拼出完整路径，工作目录保持在项目根：脚本按项目根读写 `docs/brand-guidelines.md`、`assets/design-tokens.json`、`src/` 这些文件。

## Logo 设计（内置）

55+ 种风格、30 套配色、25 个行业指南。出图引擎：Gemini Nano Banana、Atlas Cloud、MuAPI、UberLLM。

### 生成设计 brief

```bash
python3 scripts/logo/search.py "tech startup modern" --design-brief -p "BrandName"
```

### 搜风格/配色/行业

```bash
python3 scripts/logo/search.py "minimalist clean" --domain style
python3 scripts/logo/search.py "tech professional" --domain color
python3 scripts/logo/search.py "healthcare medical" --domain industry
```

### 用 AI 出图

**始终**用白色背景出图。

```bash
python3 scripts/logo/generate.py --brand "TechFlow" --style minimalist --industry tech
python3 scripts/logo/generate.py --prompt "coffee shop vintage badge" --style vintage
python3 scripts/logo/generate.py --brand "TechFlow" --provider atlas
python3 scripts/logo/generate.py --brand "TechFlow" --provider muapi
python3 scripts/logo/generate.py --brand "TechFlow" --provider muapi --muapi-model nano-banana-pro
python3 scripts/logo/generate.py --brand "TechFlow" --provider uberllm
```

**重要**：脚本失败时直接去修它，不要绕过。

出图后**总是**问用户要不要 HTML 预览；要的话用随包的 `ui-ux-pro-max` 技能搭画册。

## CIP 设计（内置）

50+ 项交付物、20 种风格、20 个行业。出图引擎：Gemini Nano Banana（Flash/Pro）。

### 生成 brief

```bash
python3 scripts/cip/search.py "tech startup" --cip-brief -b "BrandName"
```

### 搜领域

```bash
python3 scripts/cip/search.py "business card letterhead" --domain deliverable
python3 scripts/cip/search.py "luxury premium elegant" --domain style
python3 scripts/cip/search.py "hospitality hotel" --domain industry
python3 scripts/cip/search.py "office reception" --domain mockup
```

### 生成 mockup

```bash
# 带 logo（推荐）
python3 scripts/cip/generate.py --brand "TopGroup" --logo /path/to/logo.png --deliverable "business card" --industry "consulting"
# 整套 CIP
python3 scripts/cip/generate.py --brand "TopGroup" --logo /path/to/logo.png --industry "consulting" --set
# Pro 模型（4K 文字）
python3 scripts/cip/generate.py --brand "TopGroup" --logo logo.png --deliverable "business card" --model pro
# 不带 logo
python3 scripts/cip/generate.py --brand "TechFlow" --deliverable "business card" --no-logo-prompt
```

模型：`flash`（默认，`gemini-2.5-flash-image`）、`pro`（`gemini-3-pro-image`）。可用 `GEMINI_FLASH_IMAGE_MODEL` / `GEMINI_PRO_IMAGE_MODEL` 覆盖 model id。

### 渲染 HTML 展示页

```bash
python3 scripts/cip/render-html.py --brand "TopGroup" --industry "consulting" --images /path/to/cip-output
```

**提示**：还没有 logo 时，先走上面的 Logo 设计。

## 幻灯片（内置）

带 Chart.js、设计 token、文案公式的策略型 HTML 演示。创建流程读 `references/slides-create.md`。

| 主题 | 文件 |
|------|------|
| 创建指南 | `references/slides-create.md` |
| 版式范式 | `references/slides-layout-patterns.md` |
| HTML 模板 | `references/slides-html-template.md` |
| 文案公式 | `references/slides-copywriting-formulas.md` |
| 策略 | `references/slides-strategies.md` |

## 横幅设计（内置）

22 种美术方向，覆盖社交、广告、网页、印刷。本流程不依赖包外资源：尺寸与风格看 `references/banner-sizes-and-styles.md`，配色与风格建议用随包的 `ui-ux-pro-max` 技能。浏览器调研、图片生成、截图都是可选能力，没有时用用户素材、CSS 构建的视觉与运行环境自带的预览/截图流程。

步骤：

1. **收集需求**：用途、平台、内容、品牌、风格、数量
2. **调研**：读尺寸与风格参考，用 `ui-ux-pro-max` 查风格与配色；浏览器调研可用时收 3 到 5 个参考
3. **设计**：按精确平台尺寸做 HTML/CSS；用用户素材、CSS 视觉，或运行环境授权的出图能力
4. **导出**：用运行环境的浏览器或截图能力按精确尺寸截 PNG；不可用就交付 HTML/CSS 源码并标注导出未完成
5. **展示**：并排给出所有方案，按反馈迭代

尺寸速查：

| 平台 | 类型 | 尺寸（px） |
|------|------|-----------|
| Facebook | 封面 | 820 x 312 |
| Twitter/X | 页头 | 1500 x 500 |
| LinkedIn | 个人页 | 1584 x 396 |
| YouTube | 频道封面 | 2560 x 1440 |
| Instagram | 快拍 | 1080 x 1920 |
| Instagram | 帖图 | 1080 x 1080 |
| Google Ads | 中等矩形 | 300 x 250 |
| 网站 | Hero | 1920 x 600-1080 |

设计规则：关键内容放中间 70% 到 80%；每条横幅一个 CTA，右下角，高至少 44px；最多 2 种字体，正文至少 16px，标题至少 32px；广告的文字占比低于 20%；印刷用 300 DPI、CMYK、3 到 5mm 出血。

## 图标设计（内置）

15 种风格、12 个类别。Gemini 3.1 Pro Preview 直接输出 SVG 文本。

```bash
python3 scripts/icon/generate.py --prompt "settings gear" --style outlined
python3 scripts/icon/generate.py --prompt "shopping cart" --style filled --color "#6366F1"
python3 scripts/icon/generate.py --name "dashboard" --category navigation --style duotone
# 批量变体
python3 scripts/icon/generate.py --prompt "cloud upload" --batch 4 --output-dir ./icons
# 多尺寸导出
python3 scripts/icon/generate.py --prompt "user profile" --sizes "16,24,32,48" --output-dir ./icons
```

常用风格：`outlined`（界面、web 应用）、`filled`（移动端、导航栏）、`duotone`（营销、落地页）、`rounded`（友好型应用、健康）、`sharp`（科技、金融、企业）、`flat`（Material 风格）、`gradient`（现代品牌、SaaS）。

模型 `gemini-3.1-pro-preview` 只出文本（SVG 就是 XML 文本），不需要图像生成 API。

## 社交配图（内置）

多平台社交图设计：HTML/CSS → 截图导出。用到随包的 `ui-ux-pro-max`、`brand`、`design-system` 三个技能；截图走 Chrome headless、Playwright 或 Puppeteer。

尺寸、模板与最佳实践读 `references/social-photos-design.md`。

步骤：

1. **编排**：用运行环境的任务列表跟踪下面各步；独立工作可并行
2. **解析**：提取主题、平台、风格、品牌上下文、内容元素
3. **出概念**：3 到 5 个方案，问用户选
4. **设计**：按 `brand` → `design-system` → `ui-ux-pro-max` 的顺序，每个方案 × 每个尺寸出 HTML
5. **导出**：Chrome headless / Playwright / Puppeteer 按精确像素截图（工具支持时用 2x 设备像素比）
6. **核对**：在浏览器或看图器里打开导出的 PNG 逐张检查，修布局与样式问题后重导
7. **报告**：把设计与决策写进 `plans/reports/`

## 本地化说明

本文件由英文原文译写为中文。`.py` 脚本需要 Python 3；Logo、CIP、图标三处的 AI 出图分别需要 Gemini、Atlas Cloud、MuAPI 或 UberLLM 的凭据，缺凭据时不要伪造出图结果，改为给出 brief、配色、风格与可直接落地的 SVG/CSS 方案。上游随包的 54 个 TTF 字体未收录，canvas 类视觉用系统字体或项目自带字体。