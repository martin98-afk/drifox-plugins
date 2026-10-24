# jimeng — 即梦（Dreamina）生图/生视频

封装即梦官方 `dreamina` CLI，一个工具 16 个动作：8 个生成命令 + 任务/额度/会话/登录管理。

## 为什么是 CLI 不是 MCP

即梦**没有官方 MCP server**。官方给 Agent 的接入方式就是 CLI + Skill：

- 安装：`https://jimeng.jianying.com/ai-tool/install`
- 官方 SKILL 落 `~/.dreamina_cli/dreamina/SKILL.md`

火山引擎侧也不给现成 MCP：官方仓库 `volcengine/mcp-server` 84 个 server 目录里没有即梦/图像生成。社区那些 `jimeng-mcp` 多是逆向调用（sessionid 易掉线、有封号风险）或第三方个人项目。包一层 MCP 协议壳没有收益。

## 安装 CLI

**macOS / Linux**

```bash
curl -s https://jimeng.jianying.com/cli | bash
```

**Windows**

官方安装脚本是 bash，只在 MINGW / MSYS / CYGWIN 下走 windows 分支，原生 PowerShell 跑不了。直接下载：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\bin" | Out-Null
curl.exe -L "https://lf3-static.bytednsdoc.com/obj/eden-cn/psj_hupthlyk/ljhwZthlaukjlkulzlp/dreamina_cli_beta/dreamina_cli_windows_amd64.exe" -o "$env:USERPROFILE\bin\dreamina.exe"
# 把 %USERPROFILE%\bin 加入用户 PATH，然后重开终端
```

查找顺序：`DREAMINA_CLI_PATH` → PATH → `DREAMINA_INSTALL_DIR` → `~/bin`、`%LOCALAPPDATA%/Programs/dreamina`。

## 登录

`action=login` 走 headless 两段式，不阻塞等人工：

1. 返回授权链接与验证码，`device_code` 本地暂存到 `<app_data>/plugins/jimeng/pending_login.json`
2. 用户在浏览器完成授权
3. `action=checklogin` 收尾

登录态由 CLI 自己维护在 `~/.dreamina_cli/`。

## 动作表

| 分类 | action | 说明 |
|---|---|---|
| 生成 | `text2image` | 文生图，`prompt` + `resolution` |
| 生成 | `image2image` | 图生图，`images`(1-10) + `prompt` + `resolution` |
| 生成 | `upscale` | 图片放大，`image` + `resolution`(2k/4k/8k) |
| 生成 | `text2video` | 文生视频，`prompt` + `resolution` |
| 生成 | `image2video` | 图生视频，`image` + `prompt` + `resolution` |
| 生成 | `frames2video` | 首尾帧视频，`first` + `last` + `resolution` |
| 生成 | `multiframe2video` | 多帧故事视频，`images`(2-20) + `resolution` |
| 生成 | `multimodal2video` | 多模态参考视频（原 ref2video） |
| 任务 | `query` | 按 `submit_id` 查状态并下载成品 |
| 任务 | `list_tasks` | 任务列表，可按状态/类型过滤 |
| 账号 | `credit` | 查剩余额度 |
| 账号 | `session` | 会话管理（create/list/search/rename/delete） |
| 登录 | `login` / `checklogin` / `logout` | 两段式登录 / 收尾 / 清除 |
| 元信息 | `version` | CLI 版本与路径 |

## 异步语义

提交即返回 `submit_id`，工具不阻塞。`gen_status=querying` 只代表提交成功，`success` 才算完成，`fail` 要念 `fail_reason`。轮询交给 `action=query`。

## 成品

`query` 成功且下载到文件后：文件落盘到 `<app_data>/plugins/jimeng/generated/`，同时在 `ToolResult.artifacts` 回传结构化条目，由主程序成果栏按类型渲染（图片缩略图 / 视频占位 / 文件卡片）。

宿主未升级（不认识 `artifacts` 字段）时自动降级：路径仍写在 `content` 文本里，功能不失败。

## 验证

```bash
python tools/validate_plugins.py
```

手工：

1. `action=version` → 返回 CLI 版本与路径
2. `action=credit`（未登录）→ 明确提示走 login
3. `action=login` → 返回授权链接 + 验证码
4. `action=text2image prompt=... resolution=2k` → 返回 submit_id
5. `action=query submit_id=...` → 轮询到 success 后文件落盘

真实生成消耗额度，验证阶段只提交不批量刷图。

## 许可

MIT
