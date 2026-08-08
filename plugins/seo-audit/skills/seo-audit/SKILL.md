---
name: seo-audit
description: 当用户请求审查 / 分析 / 优化网站 SEO 时，触发本技能。按五优先级（P0 阻塞 / P1 严重 / P2 重要 / P3 优化 / P4 加分）输出结构化问题清单与修复建议。触发关键词：SEO 审计、SEO 检查、SEO 优化、SEO 审查、SEO 分析、SEO 评分、TDK 优化、sitemap、robots、SEO audit、SEO review。
---

# SEO 审计技能 — 五优先级审查框架

本技能为 AI 提供结构化 SEO 审查能力，按可操作性递增的五个优先级输出问题清单。

## 何时触发

- 用户："审查 X 的 SEO"、"X 站 SEO 怎么样"、"X 站 SEO 跑分"
- 用户："为什么 X 排名上不去"、"X 关键词没收录"
- 用户："优化标题 / meta description / h1"
- 用户："sitemap / robots / canonical 怎么写"

## 五优先级框架

### 🔴 P0 — 阻塞级（必须修复，否则搜索引擎无法收录）

| 检查项 | 工具 | 修复 |
|--------|------|------|
| `robots.txt` 存在 + 允许核心 | `curl /robots.txt` | 添加 `User-agent: * Allow: /` |
| `sitemap.xml` 存在 + 含重要 URL | `curl /sitemap.xml` | 生成 sitemap（含 lastmod） |
| 页面未误 `noindex` | 检 HTML 头 | 移除 `<meta name="robots" content="noindex">` |
| HTTPS 配置正确 | 浏览器检查 | 强制 HTTPS + HSTS |
| 无 5xx 服务器错误 | 监控 | 修复服务器 |

### 🟠 P1 — 严重级（影响排名核心信号）

| 检查项 | 说明 |
|--------|------|
| 每个页面唯一 `<title>` (50-60 字) | 重复 title 是降权大忌 |
| 每个页面唯一 `<meta description>` (150-160 字) | 影响 CTR |
| 一个 H1（且包含核心关键词） | 多个 H1 会分散权重 |
| `<link rel="canonical">` | 避免重复内容 |
| 内部链接无 404 | 死链降低爬虫效率 |
| `<meta name="viewport">` | 移动端必备 |

### 🟡 P2 — 重要级（影响内容质量与可访问性）

- 图片 `alt` 完整（信息图、对装饰图 `alt=""`）
- 内部链接结构清晰（首页→分类→详情 三层）
- 标题层级连贯（h1→h2→h3）
- 移动端可读性（字体 ≥ 16px、行高 ≥ 1.5）
- 跳转链接（href 锚点）
- 重定向链（301 → 301 跳过）

### 🟢 P3 — 优化级（影响深度与可读性）

- 内容长度（薄内容 < 300 字考虑扩充）
- 关键词密度（核心词 1-3%）
- 段落长度（> 5 行拆段）
- 列表/表格使用（提升可扫描性）
- 外部链接（指向权威源）

### 🔵 P4 — 加分级（提升 CTR 与结构化）

- Open Graph（og:title / og:description / og:image）
- Twitter Card（twitter:card / twitter:title）
- 结构化数据 JSON-LD（Article / Product / FAQ / BreadcrumbList）
- 多语言 hreflang

## 输出格式

每条问题按以下模板输出：

```markdown
### [P0] sitemap.xml 缺失
**位置**：site.com
**现状**：curl /sitemap.xml 返回 404
**建议**：用以下工具生成 sitemap：
- Next.js: `next-sitemap`
- 通用: `https://www.xml-sitemaps.com/`
**影响**：搜索引擎无法发现所有页面，收录率 < 30%
```

## 评分公式

```
总分 = 100 - P0×15 - P1×8 - P2×3 - P3×1 - P4×0.5
```

- 90+：优秀
- 70-89：良好
- 50-69：需改进
- < 50：紧急

## 流程

1. **抓取**：用 `webfetch` 抓 HTML
2. **抓 metadata**：用 `curl` 抓 robots.txt / sitemap.xml
3. **逐项检查**：按 P0→P1→P2→P3→P4 顺序
4. **汇总**：每优先级计数 + 评分 + 路线图
5. **可选对比**：抓竞品 URL 对比

## 提示

- 审查深度胜过宽度
- 修复 P0 后再做 P1，避免浪费时间
- 配合 `frontend-pro` 修复前端 SEO
- 配合 `seo-audit` 命令触发完整审查
