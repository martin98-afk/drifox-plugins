# ppt-deck

一句话或一篇 Markdown 文档 → 完整演示文稿：**独立 HTML 网页放映 + 可编辑 PPTX + deck manifest**。本插件只做路由与纪律，生成逻辑在随包的 Node 脚本里。

## 迁移来源

- 上游 npm 包：`dsh-ppt`（v0.19.0，技能脚本 v0.16.0）
- 上游 license：MIT

## 内容

| 通道 | 产物 | 说明 |
|---|---|---|
| skills | `skills/ppt-deck/SKILL.md` | 路由与纪律：叙事骨架、数据溯源、交付验收 |
| skills | `skills/ppt-deck/references/` | 6 份按需加载的细则：文案、主题、语法、进阶、数据、排障 |
| skills | `skills/ppt-deck/scripts/` | 10 个 `.mjs` 生成器（约 250KB），原样保留 |
| tools | `tools/ppt_deck.py` | 单入口工具，`action` 分流到 `node build-deck.mjs` |

生成逻辑没有重写：工具层只做参数翻译、Node 版本检查与子进程调用。

## 运行时依赖

- **Node ^22.19.0 或 >=24.0.0**（必需，脚本是 ESM）
- 首次使用前在 `skills/ppt-deck/` 下跑 `npm install --ignore-scripts`：
  - `@office-kit/pptx@0.21.0` — 图片、图表、品牌导出与 PPTX 生成
  - `csv-parse@6.1.0` / `jsep@1.4.0` — 结构化数据模型与公式解析
- 可选：`@deepseek-ai/libreoffice-kit@0.1.5` — 逐页 PNG/PDF 渲染

纯文本放映（不插图不插表）不需要 Office Kit。缺依赖时工具会直接报出缺哪个包。

## 用法

```
ppt_deck(title='产品发布', content='# 一、市场\n要点…', theme='data', lang='zh', out='dist')
ppt_deck(action='list_themes')
ppt_deck(action='check', deck='dist/产品发布.json')
ppt_deck(action='render', deck_file='dist/产品发布.pptx', format='png')
```

输出三件套：`<file>.html`（无外链，双击即放）、`<file>.pptx`（16:9 可编辑）、`<file>.json`（deck manifest）。文件名前缀默认 `deck`，要指定就用 `file` 参数（中文标题不会自动转成文件名）。

## 与 dsh 原包的差异

- 上游注册了 8 个工具（`ppt_create` / `ppt_themes` / `ppt_templates` / `ppt_edit` / `ppt_data` / `ppt_undo` / `ppt_check` / `ppt_render`），实现都在 `lib/*.js` 且只是对 `scripts/*.mjs` 的薄封装。本插件合并为单入口 `ppt_deck`，用 `action` 分流；编辑/撤销/数据预览这几个动作通过 `extra_args` 透传给脚本（脚本本身支持 `--edit` / `--undo` / `--data-model`）。
- `lib/client.js`（dsh Web 的设置页与预览面板）未迁移：DriFox 无对应 UI 载体。
- `lib/coaching.js` / `visual.js` / `workbench.js` 是 dsh 侧的引导与工作台逻辑，未迁移；技能正文里的流程约束已覆盖同类要求。
- 上游 skill frontmatter 的 `compatibility` / `allowed-tools` 键已剔除，内容并入正文顶部的运行环境注释。
- `cordis.patch.yml` 的挂载逻辑未迁移（DriFox 无 cordis 运行时）。
