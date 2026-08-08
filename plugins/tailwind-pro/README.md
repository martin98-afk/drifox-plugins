# tailwind-pro

> Tailwind CSS v4 完整支持 — 类型 / 类名 / 任意值 / 设计系统 / 主题映射。

源自 [hairyf/skills](https://github.com/hairyf/skills)，helloianneo/awesome-claude-code-skills **必装 Top 10** 第 9 名。

## 三大能力

1. **LSP 实时校验** — 自动注册 `@tailwindcss/language-server`，类名补全 / hover 文档 / 颜色预览
2. **设计系统方法论** — 设计 token 映射、OKLCH 色彩、间距阶梯
3. **v4 迁移指南** — 从 v3 迁移到 v4 的所有差异

## 安装

```bash
/plugin marketplace add martin98-afk/drifox-plugins
/plugin install tailwind-pro@drifox-official
```

LSP 自动拉取 `npx @tailwindcss/language-server`，无需手动安装。

## 命令

| 命令 | 用途 |
|------|------|
| `/tailwind-init` | 在项目里初始化 Tailwind v4 |
| `/tailwind-migrate` | 从 v3 迁移到 v4 |
| `/tailwind-tokens` | 生成设计 token 配置 |

## 技能

- `tailwind-pro` — Tailwind v4 类名 / 任意值 / 主题映射方法论

## 典型用法

启用后，AI 撰写 HTML/CSS 时自动注入 v4 知识：

```html
<!-- v4 支持的任意值语法 -->
<div class="grid grid-cols-[200px_1fr_200px] bg-[oklch(0.5_0.2_240)]">
  <aside class="p-[clamp(1rem,4vw,2rem)]">Sidebar</aside>
  <main class="text-[length:var(--text-base)]">Main</main>
  <aside class="p-[clamp(1rem,4vw,2rem)]">Sidebar</aside>
</div>
```

## 许可

MIT（hairyf/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
