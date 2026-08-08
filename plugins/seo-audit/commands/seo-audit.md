---
description: 对 URL 或本地 HTML 跑五优先级 SEO 审查（P0 阻塞 / P1 严重 / P2 重要 / P3 优化 / P4 加分）
type: prompt
parameters:
  - name: "<url-or-file>"
    description: "目标 URL (https://...) 或本地 HTML 文件路径"
    param_type: positional
  - name: "--json"
    description: "输出 JSON 格式报告"
    param_type: flag
  - name: "--competitor="
    description: "竞品 URL，用于对比维度"
    param_type: value
allowed-tools:
  - read
  - webfetch
  - grep
  - glob
hidden: false
---

# /seo-audit 命令 — 五优先级 SEO 审查

你正在处理 `/seo-audit` 命令。本命令对指定 URL 或本地 HTML 跑**结构化 SEO 审查**，按五个优先级输出问题清单与修复建议。

## 📋 执行规则

1. **解析参数**：
   - `<url-or-file>`：URL 用 `webfetch` 抓取，本地文件用 `read` 读取
   - `--json`：输出结构化 JSON
   - `--competitor=`：可选竞品 URL，作对比基线

2. **抓取页面**：

   **URL**：
   ```
   webfetch(url="<url>", format="html")
   ```
   关注返回 HTML（不要 markdown）。

   **本地**：直接 `read` HTML 文件。

3. **五优先级审查**（按顺序）：

   ### 🔴 P0 阻塞级（必须修复，否则搜索引擎无法收录）

   - `robots.txt` 是否存在且允许核心页面
   - `sitemap.xml` 是否存在且包含所有重要页面
   - 是否被 `noindex` 误伤
   - HTTPS 是否正确配置
   - 服务器 5xx 错误

   ### 🟠 P1 严重级（影响排名核心信号）

   - **TDK**：每个页面是否有唯一的 `<title>`、`<meta description>`、`<h1>`
   - **H1 唯一性**：是否只有一个 H1
   - **canonical**：是否设置 canonical 避免重复内容
   - **404/5xx**：内部链接是否指向失效页
   - **移动端 viewport**：`<meta name="viewport">` 是否存在

   ### 🟡 P2 重要级（影响内容质量与可访问性）

   - 图片 `alt` 是否完整（特别是信息图）
   - 内部链接结构（首页 → 分类 → 详情 三层是否清晰）
   - 标题层级（h1→h2→h3 是否跳跃）
   - 字体大小、行高、对比度（移动端可读性）
   - 跳转链接（重定向链）

   ### 🟢 P3 优化级（影响深度与可读性）

   - 内容长度（如 < 300 字考虑扩充）
   - 关键词密度（核心词 1-3%）
   - 段落长度（> 5 行拆段）
   - 列表/表格使用（提升可扫描性）
   - 外部链接（指向权威源）

   ### 🔵 P4 加分级（提升 CTR 与结构化）

   - **Open Graph** og:title / og:description / og:image
   - **Twitter Card** twitter:card / twitter:title
   - **结构化数据** JSON-LD（Article / Product / FAQ）
   - **面包屑** BreadcrumbList
   - **多语言切换** hreflang

4. **每条问题输出格式**：
   ```
   [P? 等级] <问题点>
   位置：<元素/行号/URL>
   现状：<当前状态>
   建议：<具体修复方法>
   影响：<对 SEO/排名/CTR 的影响>
   ```

5. **底部输出汇总**：
   - P0/P1/P2/P3/P4 数量
   - 修复优先级路线图
   - 竞品对比（如有）

## 子行为

<!-- section:json -->
### `--json` JSON 输出

```json
{
  "url": "...",
  "audit_time": "2026-08-08T14:32:00Z",
  "issues": {
    "P0": [{"issue": "...", "fix": "...", "impact": "..."}],
    "P1": [...],
    "P2": [...],
    "P3": [...],
    "P4": [...]
  },
  "summary": {
    "P0_count": 0,
    "P1_count": 2,
    "P2_count": 5,
    "P3_count": 8,
    "P4_count": 1
  },
  "score": 72
}
```
<!-- end -->

<!-- section:competitor -->
### `--competitor=<url>` 竞品对比

拉取竞品页面后，对比以下维度：
- 内容长度
- 关键词使用
- 结构化数据
- 移动端友好度
- 反链数量（可用 `link:<url>` 提示词估算）
<!-- end -->

## 模板变量

- `$ARGUMENTS`：用户输入的完整参数
- `$PLUGIN_NAME`：当前插件名（seo-audit）

## 提示

- 审查前先确认 `webfetch` 能访问目标 URL
- 大型站点推荐先跑 `--competitor` 拿到基线
- 配合 `beautiful-article-skills` 修复内容质量
- 配合 `frontend-pro` 修复前端 SEO 问题
