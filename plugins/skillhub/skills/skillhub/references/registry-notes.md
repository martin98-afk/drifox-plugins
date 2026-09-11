# SkillHub Registry 实测笔记

> 快照时间：2026-09-11。来源：团队《苏畅AI后端研发使用指南》PDF + 当日 400+ 技能批量发布实测。与团队最新指南冲突时以指南为准。

## 访问信息

| 项 | 值 |
|---|---|
| SkillHub 页面 | `http://168.168.10.49/`（需连接 work 网） |
| CLI 默认 registry | `https://skill.xfyun.cn`（内网部署必须显式覆盖） |
| CLI 安装 | `npm i -g @astron-team/skillhub` |
| 登录 | `skillhub login --token <token> --registry http://168.168.10.49` |
| Token 获取 | SkillHub 页面按指南操作获取个人 API Token |

## CLI 命令面

```
skillhub login  [--token <t>] [--registry <url>]
skillhub whoami                    # 验证 token 与 registry
skillhub search <query>            # 搜索已发布技能
skillhub install <coordinate>      # 安装技能到本地
skillhub publish <path> [--dry-run] [--json] [--namespace <slug>]
                                   # path 必须是含 SKILL.md 的技能目录
skillhub list / remove / upgrade / sync / doctor
```

- `publish` 版本号自动生成时间戳（如 `20260911.045613`），无需手动指定
- `--json` 输出机器可读结果，脚本场景必加
- 上传/更新需管理员审核（当前审核人：张挺、周妍）后才对其他用户可见

## 发布校验失败分类（实测）

| 类别 | 报错样例 | 处理 |
|---|---|---|
| 文件超限 | `File too large: template/public/fonts/NotoSansSC.ttf (10486022 bytes)` | 单文件上限约 10 MB；删除或替换大文件（字体/模型/数据集），或征得同意后从发布目录剔除 |
| 疑似密钥 | `line NNNN contains a value that looks like a secret or token` | 打开指定文件行号核查：真密钥必须移出并轮换；误报可改成占位符形式重试 |
| 非法扩展名 | `Disallowed file extension: xxx.ttf / xxx.tsx` | registry 白名单外扩展名（实测 .ttf、.tsx 被拒）；剔除或转换后重发 |
| 限流 | `Rate limit exceeded`（含 requestId） | 连续 publish 必触发；脚本内置间隔 + 退避重试可恢复，见下 |

## 批量发布经验（scripts/batch_publish.py）

- **限流**：无间隔连发 3~4 个后必触发限流。脚本内每次发布间隔约 2 秒，命中限流按 30/60/90/120 秒退避重试，最多 4 次，实测可全部恢复
- **断点续传**：结果写入脚本同目录 `results.jsonl`，重跑自动跳过已成功项；失败项（内容问题）也会记录，避免重复撞墙
- **Windows 坑**：npm 全局命令实际是 `skillhub.cmd`，Python `subprocess` 直接传 `"skillhub"` 会 `WinError 2`；必须 `shutil.which("skillhub")` 解析完整路径
- **路径**：publish 只接受技能目录（`plugins/<plugin>/skills/<name>/`）；仓库扫描模式 `plugins/**/skills/*/SKILL.md`，取其父目录
- **干跑**：任何批量动作前先 `--dry-run` 单技能验证 CLI 版本与鉴权没问题
