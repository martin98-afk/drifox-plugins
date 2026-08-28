---
description: 会话转技能 — 把刚做完的这件事提炼成可复用技能并安装（移植自 openhanako /xing）
type: prompt
allowed-tools:
  - "*"
hidden: false
---

# /xing — 把这次会话沉淀成技能

用户刚教完你一件事，现在要把这个流程提炼成可复用技能。与 openhanako /xing 同构：命令给你提炼任务，安装动作你自己做。

## 步骤

1. **提素材**：
   - 优先直接使用**当前会话上下文**（你就在这个对话里，素材天然在手）
   - 需要回看其他会话时：用 `powershell`/python 只读查 `<app_data_dir>/sessions.db` 的 `sessions` 表（messages 为 JSON），或让用户指定 session
2. **提炼**：
   - 抽出「用户想做成什么 → 实际怎么做的 → 关键步骤 / 坑」
   - 写成**可复现的操作指南**，不是对话回放
   - `description` 必须写清触发场景（什么时候该用），这是技能被正确启用的关键
   - 正文给流程、给判断标准、给坑，不给口号

   SKILL.md 模板：
   ```markdown
   ---
   name: <kebab-case 名>
   description: "<做什么>。<什么时候用：触发场景、关键词>。<什么时候不要用>"
   ---

   # <技能名>

   ## 适用场景
   - ...

   ## 工作流
   1. <步骤 + 验证方式>
   2. ...

   ## 关键细节 / 坑
   - ...
   ```
3. **确认**：把拟定的技能名（kebab-case）和 SKILL.md 内容概要给用户过目，确认后再装
4. **安装**：`write` 写入本插件技能目录 `~/.drifox/plugins/openhanako-adapter/skills/<name>/SKILL.md`（frontmatter `---` 开头，含 name/description；目录不存在则创建；插件热重载自动生效）。`~` 由系统自动展开为当前用户主目录，不要硬编码 `C:/Users/<name>/` 这类绝对路径——同一插件要给不同用户共用。
5. 告知用户：以后对话中说「使用 `<技能名>` 技能」即可调用

## 判断值不值得沉淀

值得：多步骤流程、试错后找到正解、含"踩过才知道"的坑
不值得：单步问答、纯闲聊——此时向用户说明并建议放弃
