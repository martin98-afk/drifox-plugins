# 快速开始

## 前置条件

- Python 3.8+
- 一个你有权写入的项目目录
- 自动模式另需 Claude Code、Codex 或两者之一

## 从 Kim Service 安装

从当前公开合集进入包目录：

```bash
git clone https://github.com/KimYx0207/Kim_Service.git
cd Kim_Service/skills/memory-3layer
```

Windows：

```powershell
$ProjectDir = (Resolve-Path "..\你的目标项目").Path
.\install.ps1 -ProjectDir $ProjectDir -Platform auto
```

macOS / Linux：

```bash
chmod +x install.sh
./install.sh --project-dir /你的/目标项目 --platform auto
```

`ProjectDir` / `--project-dir` 必须明确指向要启用记忆的目标项目，不能省略。`auto` 会检测 Claude Code 与 Codex；都不存在时只初始化 manual 核心。也可以显式选择 `claude`、`codex`、`both` 或 `manual`。

## 第一次验证

```bash
python scripts/check_memory_3layer.py
```

然后按平台完成运行验证：

- Claude Code：启动新会话，确认加载事件有输出。
- Codex：先运行 `/hooks`，审查并信任项目 Hooks，再启动新会话确认加载输出。
- 其他平台：按安装器输出的 manual 说明显式加载 `.memory-3layer/`。

## 记住一条事实

对已加载本 Skill 的 Agent 说：

> 记住：这个项目统一使用 pnpm，除非 package.json 明确要求其他工具。

Agent 应显式调用受控入口（也可以人工运行）：

```bash
python scripts/record_memory.py --project-dir /你的/目标项目 --fact "这个项目统一使用 pnpm，除非 package.json 明确要求其他工具" --topic workflow
```

预期结果：Layer 1 新增带 `source`、`timestamp`、`status: active` 的事实，Layer 2 追加当天摘要。普通工具输出不会被自动当作事实；包含秘密或仅为猜测时应拒绝写入。

## 复查与清理

运行 `memory-status` 查看数量与日期范围，运行 `memory-review` 生成重复、冲突和过时建议。未获得确认前，不应删除条目；确认旧事实失效后将其标为 `superseded`。

## 从旧版迁移

发现 `.claude/memory/` 时，不要继续把新内容写回旧目录。运行：

```bash
python scripts/migrate_legacy_memory.py --project-dir /你的/目标项目
```

默认复制到 `.memory-3layer/`，跳过冲突、不覆盖、不删除旧目录。详见 [迁移规则](../references/migration.md)。
