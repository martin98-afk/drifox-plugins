---
name: hana-html-beautify
description: "Hana HTML 美学纪律（移植自 openhanako beautify 插件）。生成独立整页 HTML（网页/排版页/报告页/落地页）前必读：暖纸底色、唯一青灰蓝强调色、衬线字重克制、发丝线分层、安静动效、避开廉价 AI 感。用户未指定风格时按本纪律生成；用户明确指定则让位仅兜底可读性。"
---

## 章节：router

Hana HTML 美学纪律。生成整页 HTML 前，先读下列章节再动笔；不要凭这段路由文字直接生成。本纪律只服务独立整页 HTML（网页 / 排版页 / 报告页 / 落地页），与聊天内嵌互动卡片无关。

适用条件：用户明确指定了风格 → 听用户的，本纪律让位（仅兜底可读性）。用户没指定 → 按本纪律。

气质：文艺、精致、沉静——像一页装帧考究的私人手账。意象：纸本文稿、宋体字、水墨、宣纸质感、书面感。

五原则：
1. 纸上得来：间距像版面留白，色彩像墨色浓淡。
2. 克制即品质：能用一条线就不用一个框，能用透明度分层就不用实色堆叠。
3. 安静的反馈：hover 是轻微呼吸，切换是柔和淡入；不弹跳、不闪烁。
4. 层级即秩序：用字号 / 字重 / 明度 / 容器建层级。阅读型纯版式，结构型卡片分组。
5. 一致即信任：同类元素全页保持一致尺寸 / 间距 / 行为。

章节索引（在 DriFox 中：全部章节已内联于本技能下方，无需工具调用，直接阅读）：
- color：必读
- typography：必读
- layout：整页 / 多区块 / 复杂版式时必读
- components：用到卡片 / 表格 / 按钮 / 徽章 / 链接等组件时（页面含 <a> 即应读）
- imagery：含图标 / 图片时
- motion：交互页 / 有动效时
- anti-patterns：强烈建议——避开廉价 AI 感

## 章节：color

Hana HTML 美学 · color

**唯一强调色**：`#537D96`（青灰蓝），hover `#456A80`，浅垫 `rgba(83,125,150,.08)`。通篇只此一种彩色强调，不引入第二种主色；强调色视觉占比 ≤ 5%，点睛而非铺陈。

**底色（绝不纯白）**：页面底 `#F8F4ED`（暖纸），卡片 / 抬升面 `#FCFAF5`。整体低对比。

**文字（暖中性，不用冷蓝灰）**：主文 `#3B3D3F`，次级 `#6B6F73`，弱化 / metadata `#8E9196`。绝不用纯黑 `#000`。

**线与边框**：发丝细线、暖调 `rgba(122,96,88,.18)`。优先用线 + 留白分区，而非实色块。

**叠层（透明度分层，非实色叠加）**：`rgba(0,0,0,.03 / .05 / .08 / .15)` 四档。

**语义色（低饱和、克制）**：成功 `#7BAE7F`，危险 `#8B3A3A`，珊瑚强调 `#EC8F8D`（少用）。仅必要时出现。

**硬规则**：灰必须暖调（带黄褐底），禁止冷蓝灰；不用纯白大底 / 纯黑文字；不用渐变铺底、高饱和、霓虹。

本规范只定义暖纸一套配色。用户明确要求深色或其它风格时，走用户明示通道（本规范让位，仅兜底可读性与对比）。

## 章节：typography

Hana HTML 美学 · typography

**衬线（主力，承载标题与正文层级）**：`'EB Garamond','Noto Serif SC','Source Han Serif SC','Songti SC','STSong','SimSun',serif`

字体栈中的系统回退（`Songti SC` / `SimSun` / serif 等）保留为兜底：前列字体未覆盖的字符落系统衬线，不裂版。

**UI / 功能性文字（按钮、标签、表单、导航）**：`system-ui,-apple-system,'PingFang SC',sans-serif`

**代码 / 数字 metric**：`'JetBrains Mono',ui-monospace,monospace`；数字对齐加 `font-variant-numeric:tabular-nums`。

**字重**：仅 400 / 500。不用 600+、不用合成粗体；层级靠字号 + 明度 + 字距，不靠加粗硬堆。

**字号层级**：

| 层级 | rem | 用途 |
|---|---|---|
| display | 2 – 2.4 | 页面主标题 / hero |
| h1 | 1.6 | 章节大标题 |
| h2 | 1.25 | 小节标题（可配左竖线 `border-left:2px solid #537D96;padding-left:8px;border-radius:0`） |
| h3 | 1.05 | 子标题 |
| body | 1（16px） | 正文，`line-height:1.7` |
| small | 0.85 | 辅助 / caption |

**中英混排**：中文衬线行高略高（1.7 – 1.8）；CJK 标题可加 `letter-spacing:.01em`。

## 章节：layout

Hana HTML 美学 · layout

**间距节奏**：`4 / 8 / 16 / 24 / 40`。不用区间外魔法值。

**内容宽度**：阅读型正文 `max-width:60–72ch`（约 680–760px）居中；落地型可更宽，但每个文本分区内仍守可读行宽。

**留白**：区块之间 40，区块内 16 – 24。留白是层级工具，不是浪费。

**响应式**：移动端单列、加大行距、控件触达 ≥ 44px；窄屏断点 ~880 / ~480。

**版式模式（按内容类型选其一）**：

| 类型 | 取向 | 手段 |
|---|---|---|
| 阅读 / 编辑型 | 纯版式分层 | 留白 + 字号层级，不套卡片；正文居中守行宽 |
| 结构 / 仪表型 | 卡片 / 分组 | 卡片 `#FCFAF5` + 发丝边；分组标题 |
| 落地 / 展示型 | 编辑式 hero + 分区 | 大标题 + 克制配图 + 单强调色点睛；不堆营销装饰 |
| 交互型 | 内容居中、控件克制 | 安静动效、状态清晰 |

阅读连续内容用纯版式保流畅；密集功能场景用卡片强区块感。二选一，别两者都上。

## 章节：components

Hana HTML 美学 · components

底色变量沿用 color 章节。以下为默认形态。

```css
/* 区块标题 */
h2 { font-family: serif; font-size: 1.25rem; font-weight: 500; color: #3B3D3F;
     border-left: 2px solid #537D96; padding-left: 8px; border-radius: 0; margin: 1.6em 0 .6em; }

/* 卡片 / 面板（仅结构型场景用） */
.card { background: #FCFAF5; border: 1px solid rgba(122,96,88,.18); border-radius: 4px;
        padding: 1rem 1.25rem; }

/* 分隔线 */
hr { border: none; border-top: 1px solid rgba(122,96,88,.18); margin: 1.5rem 0; }

/* 表格：细线、紧凑、左对齐表头 */
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th { text-align: left; font-weight: 500; color: #6B6F73; padding: 6px 8px;
     border-bottom: 1px solid rgba(122,96,88,.18); }
td { padding: 5px 8px; border-bottom: 1px solid rgba(0,0,0,.05); color: #3B3D3F; }
tr:last-child td { border-bottom: none; }

/* 列表 */
ul, ol { padding-left: 18px; }
li { margin: .2em 0; }
li::marker { color: #537D96; }

/* 引用 */
blockquote { border-left: 2px solid #537D96; padding: 4px 0 4px 12px;
             color: #6B6F73; font-style: italic; border-radius: 0; }

/* 代码 */
pre { background: #F8F4ED; border: 1px solid rgba(122,96,88,.18); border-radius: 4px;
      padding: 8px 12px; overflow-x: auto; }
code { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: .85rem; color: #3B3D3F; }

/* 按钮：方角、描边优先、hover 微底色，无 :active 缩放 */
.btn { font-family: sans-serif; border: 1px solid rgba(122,96,88,.18); border-radius: 4px;
       background: transparent; color: #537D96; padding: 6px 14px; cursor: pointer;
       transition: background .15s cubic-bezier(.16,1,.3,1); }
.btn:hover { background: rgba(83,125,150,.08); }
/* 主行动按钮可用 background:#537D96;color:#FCFAF5 实色，但每屏 ≤ 1 个 */

/* 徽章 / 标签 */
.tag { display: inline-flex; padding: 2px 8px; font-size: .75rem; font-weight: 500;
       border-radius: 4px; background: rgba(83,125,150,.08); color: #456A80; }

/* 链接：accent 色 + 细下划线，hover 加深；不按钮化、不去下划线 */
a { color: #537D96; text-decoration: underline; text-decoration-thickness: 1px;
    text-underline-offset: 2px; text-decoration-color: rgba(83,125,150,.4);
    transition: color .15s cubic-bezier(.16,1,.3,1), text-decoration-color .15s cubic-bezier(.16,1,.3,1); }
a:hover { color: #456A80; text-decoration-color: currentColor; }

/* focus：可见但克制（motion 章节原则的具体值） */
:focus-visible { outline: 1px solid #537D96; outline-offset: 2px; }
```

**层次与阴影**：优先发丝线 + 留白 + 底色微差建立层级；需要抬升时用极淡阴影 `box-shadow: 0 1px 4px rgba(59,61,63,.09)`。禁止重投影、glow、多层 drop-shadow。

## 章节：imagery

Hana HTML 美学 · imagery

- **图标**：纯 inline SVG，stroke 线性（feather 风），`stroke="currentColor" stroke-width="1.5" fill="none"`。**不用 emoji**，不用实心 fill 图标。
- **装饰**：不堆漂浮符号 / 星星 / 气泡等廉价 AI 点缀；微光隐喻（柔和、非炫目）可少量点睛。
- **图像比例**：hero 16:9，编辑插图 4:3，网格缩略 3:2；`object-fit:cover` + 合理 `object-position`，不拉伸。
- **圆角**：图像 / 卡片 4px 小圆角（方角倾向），不用大圆角胶囊。
- **无真实图片资源时**：**禁止热链外部图床**（unsplash / picsum 等——隐私暴露、离线即裂图）。占位用纯色块（`#FCFAF5` + 发丝边）或自绘内联 SVG（线性、低饱和、符合 color 章节），宁可留白也不外链。用户提供的本地 / 已有资源不受此限。

## 章节：motion

Hana HTML 美学 · motion

- **安静**：过渡柔和短促。duration 用 `0.1 / 0.15 / 0.25` 三档；easing 入场 `cubic-bezier(.16,1,.3,1)`、退场 `cubic-bezier(.7,0,.84,0)`。
- **hover 是轻微呼吸**（色 / 透明度微变），不放大、不弹跳。
- **禁止**：`:active` 缩放弹跳、闪烁、旋转炫技、自动轮播抢注意。
- **状态清晰可预期**：focus 给可见但克制的指示（具体值见 components 章节的 :focus-visible）；禁用态降透明度。
- 尊重 `prefers-reduced-motion: reduce`，关掉非必要动效。

## 章节：anti-patterns

Hana HTML 美学 · anti-patterns

| ❌ 不要 | ✅ 改用 |
|---|---|
| Material Design 感 / 涟漪 | 纸本手账的克制 |
| glassmorphism 毛玻璃、模糊炫技 | 实底 + 发丝线 |
| 纯白 `#fff` 大面积底 | 暖纸 `#F8F4ED` |
| 纯黑 `#000` 文字 | 暖墨 `#3B3D3F` |
| 冷蓝灰中性色 | 暖调灰 |
| 第二种主色 / 多彩堆砌 | 单一 accent `#537D96` |
| 霓虹、高饱和、渐变铺底 | 低饱和、低对比 |
| 重投影 / 发光 glow | 极淡阴影或仅发丝线 |
| 大圆角胶囊感 | 方角 / 4px 小圆角 |
| emoji 当图标 / 装饰 | SVG stroke 图标 |
| 600+ 粗体堆层级 | 字号 + 明度 + 400/500 |
| 弹跳 / 缩放 / 旋转动效 | 柔和淡入、呼吸 |
| 漂浮装饰符号堆砌 | 留白 + 克制微光 |

## 附：Markdown Cover 风格说明

Hana Markdown cover 的默认审美规范：

1. 画风：现代 Anime / 动画电影 key visual，不使用传统东方刻板符号作为默认风格。
2. 材质：强纸张质感、印刷纹理、细腻颗粒、温润材料感；像被装帧进纸本里的画面。
3. 叙事：有电影感、有故事感、有文学气息；优先通过真实场景、人物动作、光线、道具关系、环境痕迹表达主题。
4. 内容：阅读文章后提炼意象主题，做文章气质的视觉化，不要把文章摘要逐字画出来。
5. 幻想感：星空、幻想、文学意象可以出现，但必须由场景自然承载，有现实重量和情感理由。
6. 克制：避免廉价 AI 感的漂浮符号堆砌；超现实元素只有在叙事上有必要时才出现。
7. 主题：浅色主题使用柔和暖光、低对比、干净留白、纸面纤维清晰；深色主题使用低照度、克制高光、暗部保留材料层次。
8. 输出：默认让生图工具按横向 3:2 生成；如果供应商不支持，允许接近的横向比例，但不能拉伸图片。
