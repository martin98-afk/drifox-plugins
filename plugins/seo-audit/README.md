# seo-audit

> 五优先级 SEO 审查框架 + 落地页高转化文案撰写方法论。

源自 [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills)，helloianneo/awesome-claude-code-skills **强推**。

## 包含技能

| 技能 | 用途 |
|------|------|
| `seo-audit` | 五优先级 SEO 审查（基础设施 → 内容 → 关键词 → 技术 → 外链） |
| `copywriting` | 主页/落地页/定价页高转化文案撰写 |
| `product-marketing-context` | 产品定位、目标人群、竞品、品牌声音 |
| `pricing-strategy` | SaaS 定价设计与竞品对比框架 |

## 命令

| 命令 | 用途 |
|------|------|
| `/seo-audit [url]` | 对 URL 或本地 HTML 跑五优先级 SEO 审查 |
| `/copywrite <page>` | 撰写主页/落地页/定价页文案 |

## 典型用法

### 审查我的站点

```
/seo-audit https://myapp.com
```

输出五优先级问题清单：
- 🔴 P0 阻塞：缺 sitemap.xml、robots.txt 错误
- 🟠 P1 严重：TDK 缺失、H1 重复
- 🟡 P2 重要：图片 alt 缺失、移动端布局问题
- 🟢 P3 优化：内容深度、可读性
- 🔵 P4 加分：结构化数据、内链

### 写落地页文案

```
/copywrite landing --page=pricing
```

输出定价页完整文案：标题、副标题、价值主张、定价表、FAQ、CTA。

## 安装

```bash
/plugin marketplace add martin98-afk/drifox-plugins
/plugin install seo-audit@drifox-official
```

## 许可

MIT（marketingskills 本身）+ GPL-3.0-or-later（DriFox 适配层）
