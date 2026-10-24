# jimeng 即梦插件设计文档

> 日期：2026-10-24
> 状态：待用户评审
> 关联：`plugins/jimeng/`、官方 CLI v1.4.21、`plugins/openhanako-adapter/tools/jimeng.py`（存量参考实现）

---

## 1. 背景

即梦（Dreamina，字节旗下）**没有官方 MCP server**。官方给 Agent 的接入方式是 CLI + Skill：

- 安装入口 `https://jimeng.jianying.com/ai-tool/install`
- 命令 `curl -s https://jimeng.jianying.com/cli | bash`
- 官方 SKILL.md 落到 `~/.dreamina_cli/dreamina/SKILL.md`（7045 字节，`name: dreamina-cli`）

火山引擎侧同样不给现成 MCP：官方仓库 `volcengine/mcp-server` 全量 84 个 server 目录无即梦/图像生成项（图像相关只有 veImageX，那是图片处理/CDN 助理，不生图）。

存量 `plugins/openhanako-adapter/tools/jimeng.py` 已包了 CLI，但只覆盖 4 个 mode（text2image / image2image / text2video / image2video），漏掉官方一半命令面，且没有 SKILL.md。

### 实测 CLI 命令面（v1.4.21，commit 89c7256）

生成命令 8 个：

| 命令 | 必填参数 | 模型 |
|---|---|---|
| `text2image` | `--prompt` `--resolution_type` | 3.0/3.1/4.0/4.1/4.5/4.6/4.7/5.0/5.0Pro |
| `image2image` | `--images`(1-10) `--prompt` `--resolution_type` | 4.0 起 |
| `image_upscale` | `--image` `--resolution_type`(2k/4k/8k) | 无模型选择 |
| `text2video` | `--prompt` `--video_resolution` | seedance2.0 族 / 2.5 |
| `image2video` | `--image` `--prompt` `--video_resolution` | seedance1.0fast 起 |
| `frames2video` | `--first` `--last` `--video_resolution` | seedance1.5pro 起 |
| `multiframe2video` | `--images`(2-20) `--video_resolution` | 固定模型，不可选 |
| `multimodal2video` | `--video_resolution` | seedance2.0 族 / 2.5（原 ref2video） |

管理命令 8 个：`query_result`、`list_task`、`session {create,list,search,rename,delete}`、`user_credit`、`login [--headless]` + `login checklogin`、`relogin`、`logout`、`version`。

异步语义（官方 SKILL.md 明令）：`submit_id` + `gen_status=querying` 只代表提交成功，`success` 才算完成，`fail` 要念 `fail_reason`。

### 平台约束

- 安装脚本是 bash，只有 `MINGW*|MSYS*|CYGWIN*` 走 windows 分支。原生 PowerShell/cmd 跑不了
- Windows 二进制可直连：`dreamina_cli_windows_amd64.exe`，31.6MB，落 `$HOME/bin/dreamina.exe`
- 未登录时任何命令返回「未检测到有效登录态，请先执行 dreamina login」，非 0 退出码，错误在 stderr
- 首次 `-h` 会在 `~/.dreamina_cli/` 建 `version.json` 与 `logs/`

---

## 2. 需求澄清结论（用户已确认）

| 问题 | 决定 |
|------|------|
| 载体 | 新建独立插件 `jimeng`，skill + tool 全套（不动 openhanako-adapter） |
| 工具粒度 | **1 个工具** `jimeng`，`action` 分派全命令 |
| 登录 | 工具内完成，headless 两段式 |
| 成果交付 | 落盘 + 回传 `artifacts` 字段给主程序成果栏（主程序侧另立设计） |
| 落地顺序 | 先插件，后主程序 |

---

## 3. 目录结构

```
plugins/jimeng/
├── .drifox-plugin/plugin.json    components: {skills: true, tools: true}
├── skills/jimeng/SKILL.md        官方 SKILL.md 本地化
├── tools/jimeng.py               单工具 action 分派
├── tools/icons/jimeng.svg        深色
├── tools/icons_light/jimeng.svg  浅色
├── icon.svg / icon_dark.svg      插件列表图标
└── README.md
```

manifest：

```json
{
  "name": "jimeng",
  "description": "即梦（Dreamina）生图/生视频 — 封装官方 dreamina CLI，8 个生成命令 + 会话/额度/登录管理。",
  "version": "1.0.0",
  "type": "user",
  "license": "MIT",
  "author": {"name": "DriFox Contributors"},
  "homepage": "https://github.com/martin98-afk/drifox-plugins",
  "keywords": ["image-generation", "video-generation", "即梦", "dreamina", "jimeng"],
  "components": {"skills": true, "tools": true},
  "min_host_version": "0.5.0"
}
```

---

## 4. 工具设计

### 4.1 action 枚举（16 个）

| 分类 | action | CLI 命令 |
|---|---|---|
| 生成 | `text2image` | `text2image` |
| 生成 | `image2image` | `image2image` |
| 生成 | `upscale` | `image_upscale` |
| 生成 | `text2video` | `text2video` |
| 生成 | `image2video` | `image2video` |
| 生成 | `frames2video` | `frames2video` |
| 生成 | `multiframe2video` | `multiframe2video` |
| 生成 | `multimodal2video` | `multimodal2video` |
| 任务 | `query` | `query_result --download_dir` |
| 任务 | `list_tasks` | `list_task` |
| 账号 | `credit` | `user_credit` |
| 账号 | `session` | `session <session_action>` |
| 登录 | `login` | `login --headless` |
| 登录 | `checklogin` | `login checklogin --device_code` |
| 登录 | `logout` | `logout` |
| 元信息 | `version` | `version` |

### 4.2 schema 参数表

单 schema 承载全部参数，`description` 写清哪个 action 需要哪几个；必填校验在 impl 内按 action 分支做。

| 参数 | 类型 | 用于 |
|---|---|---|
| `action` | string（必填，enum 16 项） | 全 |
| `prompt` | string | 7 个生成命令（upscale 除外） |
| `images` | array[string] | image2image(1-10)、multiframe2video(2-20)、multimodal2video |
| `image` | string | image2video、upscale、multimodal2video |
| `first` / `last` | string | frames2video |
| `videos` / `audios` | array[string] | multimodal2video |
| `transition_prompts` | array[string] | multiframe2video（N 图需 N-1 段） |
| `transition_durations` | array[number] | multiframe2video |
| `model` | string | 6 个生成命令（upscale / multiframe2video 无） |
| `ratio` | string | 8 个生成命令（seedance2.5 的视频命令拒收） |
| `resolution` | string | 图 → `--resolution_type`；视频 → `--video_resolution` |
| `duration` | number | 视频命令 |
| `generate_num` | int | text2image / image2image（1-10） |
| `width` / `height` | int | text2image / image2image（须成对，与 ratio 互斥） |
| `session_id` | int | 生成命令 + session 操作 |
| `submit_id` | string | query、list_tasks 过滤 |
| `download_dir` | string | query（缺省走插件 generated 目录） |
| `poll` | int | 生成命令 |
| `gen_status` / `gen_task_type` / `limit` / `offset` | — | list_tasks |
| `device_code` | string | checklogin |
| `session_action` | string（create/list/search/rename/delete） | session |
| `session_name` | string | session create/rename/search |

参数名映射：`resolution` → 图 `--resolution_type` / 视频 `--video_resolution`；`session_id` → `--session`；`session_action=delete` → `session rm`（CLI 里 delete 是 rm 的别名，两者都可用，统一用 `rm` 更短）。

### 4.3 实现要点

- **CLI 定位**：`DREAMINA_CLI_PATH` → PATH `which` → `DREAMINA_INSTALL_DIR` → `~/bin`、`%LOCALAPPDATA%/Programs/dreamina`。沿用存量 `_resolve_dreamina()` 的查找顺序
- **不传 `--poll`**：提交即返回，轮询交给 `query`。这样工具调用不会阻塞在生成上。`poll` 参数保留但默认 0
- **stdout 解析**：CLI 可能在 JSON 前打印提示文字，用「整体 json.loads 失败则取首尾大括号区间」兜底（存量 `_first_json` 已验证）
- **Windows 静默**：`STARTUPINFO + SW_HIDE + CREATE_NO_WINDOW`，避免每次调用弹黑框
- **超时**：生成提交 180s，query 300s（含下载），管理命令 60s
- **错误透传**：CLI 把「未检测到有效登录态」写 stderr 且退出码非 0。impl 要识别该串，回一个明确的 `ToolResult(False, error=...)` 引导用户走 `action=login`

### 4.4 登录两段式

```
action=login
  → CLI: dreamina login --headless
  → 解析 stdout 的 verification_uri / user_code / device_code
  → device_code 存 app_data/plugins/jimeng/pending_login.json
  → 返回给用户：verification_uri + user_code + 「完成授权后告诉我」

action=checklogin
  → 读 pending 里的 device_code（无则报错要求先 login）
  → CLI: dreamina login checklogin --device_code=<code> --poll=30
  → 成功则删 pending 文件，返回登录成功
  → 超时保留 pending，提示可再次 checklogin
```

不用 `action=login` 直接阻塞等待：工具调用不能卡在人工操作上。headless 两段式是官方明确支持的模式。

`pending_login.json` 仅存 `device_code` 与创建时间，不含 token。OAuth 登录态由 CLI 自己维护在 `~/.dreamina_cli/`。

### 4.5 成果回传

生成任务 `query` 成功且下载到文件后，除返回文本路径外，同时在 `ToolResult.artifacts` 里回传结构化条目：

```python
{
  "path": "/abs/path/xxx.png",
  "kind": "image",          # image | video | html | text | file
  "mime": "image/png",
  "width": 2048,            # 图片/视频才有
  "height": 2048,
  "name": "xxx.png",
  "size": 1234567,
  "prompt": "原始提示词",
  "submit_id": "3f6eb41f...",
}
```

`kind` 判定按扩展名：`.png/.jpg/.jpeg/.webp/.gif` → image；`.mp4/.mov/.webm` → video；`.html/.htm` → html；`.md/.txt` → text；其余 → file。

主程序若不认识 `artifacts` 字段（未升级），工具同时把路径列表写进 `content` 文本，功能降级但可用。

### 4.6 落盘

`app_data/plugins/jimeng/generated/`（`tool_ctx["env"]["app_data_dir"]` → `plugins/jimeng/generated`）。`query` 传给 CLI `--download_dir`。

按 `session_id` 或日期分子目录不做：官方 `list_task` 已能按任务检索，本地平铺更利于用户直接用文件管理器找。

---

## 5. SKILL.md 本地化

保留官方结构（默认流程、异步判定、登录确认、模型选择规则），改三处：

1. **安装**：补 Windows 原生安装说明（直连下载 exe 到 `%USERPROFILE%\bin`，加 PATH），因为官方脚本在 PowerShell 下跑不了
2. **入口**：优先引导模型调用 `jimeng` 工具而不是自己拼 `dreamina` 命令行（工具已封装参数校验与落盘）。CLI 直接调用降级为排查手段
3. **产物**：说明生成结果会自动出现在消息卡片成果栏，不需要模型自己读图

`name` 用 `jimeng`（与目录一致，校验器要求），不用官方的 `dreamina-cli`。

`description` 精准描述匹配场景，覆盖触发词：即梦、Dreamina、dreamina、生图、生视频、AI 绘图、seedance、文生图、图生视频。

---

## 6. 验证

```bash
python tools/validate_plugins.py && python tools/generate_marketplace.py
```

手工验证清单：

1. 未装 CLI 时任一 action → 明确错误 + 安装指引
2. `action=version` → 正常返回 v1.4.21
3. `action=login` → 返回 verification_uri + user_code，pending 文件写入
4. `action=credit`（未登录）→ 识别「未检测到有效登录态」并引导 login
5. `action=text2image` → 返回 submit_id
6. `action=query` → 轮询到 success 后文件落盘，artifacts 字段正确

真实生成会消耗额度，验证阶段只用 `--poll 0` 提交 + query 观察，不批量刷图。

---

## 7. 非目标

- 不做即梦 MCP server（官方没有，包一层协议壳没收益）
- 不做逆向 API 直连（sessionid 掉线、封号风险）
- 不改 `openhanako-adapter/tools/jimeng.py`（存量工具保留，谁用谁负责；如需统一后续单独提）
- 不做额度自动检查/预警
- 不做多账号切换
