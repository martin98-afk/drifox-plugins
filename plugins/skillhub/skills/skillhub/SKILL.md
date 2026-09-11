---
name: skillhub
description: SkillHub 内网技能注册中心工作流 — 发布/上传技能、批量发布、搜索技能、安装技能。触发关键词：SkillHub、上传技能、发布技能、publish skill、技能市场、安装 skill、搜索技能、skill registry、168.168.10.49。
---

# SkillHub 工作流

处理内网 SkillHub（registry）的技能发布、搜索、安装。所有操作依赖本机 `skillhub` CLI（npm 包 `@astron-team/skillhub`）。

## 第一动作：环境检查（所有任务前置）

按顺序执行，失败即走对应修复路线：

1. `skillhub --version`（PowerShell 用 `Get-Command skillhub`，bash 用 `command -v`）
   - 不存在 → `npm i -g @astron-team/skillhub`，仍失败 → 硬停止（需 Node.js ≥ 18）
2. `skillhub whoami`
   - 提示 not logged in 且 registry 不是目标地址 → 向用户要 API Token，执行
     `skillhub login --token <token> --registry http://168.168.10.49`
   - 连接超时/不可达 → 硬停止（需连接 work 网）
3. 默认 registry 是 `https://skill.xfyun.cn`，内网部署必须显式带 `--registry http://168.168.10.49`

Token 只在用户消息或屏幕上出现时读取，不写进任何文件与 commit。

## 任务路由

### 发布单个技能

1. 确认路径是**技能目录**（含 `SKILL.md` 的目录，如 `plugins/<plugin>/skills/<name>/`），禁止传插件根目录
2. `skillhub publish <技能目录> --dry-run` 看校验结果；`resolvedSlug`/`resolvedVersion` 出现即格式通过
3. 失败项对照 `references/registry-notes.md` 的失败分类处理，处理后重跑 dry-run
4. dry-run 通过 → 去掉 `--dry-run` 正式发布 → 报告结果并提醒：需管理员审核后才能被其他用户搜到

### 批量发布（仓库级）

用 `scripts/batch_publish.py`，不要手工循环（限流必翻车）：

```bash
python scripts/batch_publish.py <仓库根目录> [数量上限]   # 0 或省略 = 全量
```

内置：发布间隔、限流退避重试、`results.jsonl` 断点续传。参数含义与失败处理见 `references/registry-notes.md`。

### 搜索

`skillhub search <关键词> --registry http://168.168.10.49`（未登录过内网 registry 时才需要 --registry）。结果为空先问用户是否知道确切名称；仍无则建议走管理员审核确认。

### 安装

`skillhub install <coordinate> --registry http://168.168.10.49`。安装后提示用户重启 Agent 客户端生效。coordinate 不确定时先 search。

## 硬停止

- CLI 装不上（无 Node.js/npm）
- registry 不可达（未连 work 网），向用户说明后停止，不重试超过 2 次
- 用户无法提供 Token
- 批量发布中限流重试 4 次仍失败：跳过该技能继续，最后汇总失败清单，不整体中断

## 边界

- **非目标**：不修改技能内容本身；发现疑似密钥/超大文件只报告定位信息，由用户决定删改（涉及上游迁移内容时尤其如此）
- **副作用**：publish 直接写入内网 registry；dry-run 无副作用，正式发布前必须先 dry-run
- **事实来源**：registry 地址、Token、审核人名单以团队最新指南为准，`references/registry-notes.md` 是 2026-09 快照，冲突时问用户

## 验证

- 单技能发布成功标准：publish 返回 JSON `"ok":true`，页面/搜索可见（审核后）
- 批量发布成功标准：`results.jsonl` 中失败项均有明确分类（内容问题 vs 限流未恢复），无未知失败
- 触发自检：用户说「上传/发布技能到 SkillHub」「搜技能」「装技能」必须命中本技能；用户只说「创建技能」不命中（那是 skill-creator 的事）
