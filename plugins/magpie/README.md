# magpie

把 [magpie](https://github.com/yetone/magpie) 的本地网关接成 DriFox 的一个服务商。

magpie 是一个聚合网关：它把你所有 agent 各自的模型配置、订阅账号（Claude / ChatGPT /
Copilot / Gemini / Grok）、API Key、本地模型收进一个地方，对外只暴露一个
`http://127.0.0.1:3425/v1` 端点，并用 `provider/model` 形式的 id 命名每个模型。
接入 DriFox 后，一份服务商配置即可用上 magpie 里的全部模型，配额耗尽时由 magpie
自己换到下个账号，DriFox 侧无感知。

## 前提

1. 安装 magpie（桌面 App、菜单栏图标、`magpie serve` 或 `magpie web` 任一形态，
   只要网关在跑）。没在跑？插件能直接帮你拉起（见下）。
2. 在 magpie 里添加服务商 / 登录订阅，并给要用的 agent 选中模型。

没在跑时，magpie 页里点「启动 magpie web」即可：插件经宿主的 `process.start`
能力后台拉起，不需要终端。

## 使用

1. 设置 → 服务商 → 添加 → 选「magpie」。
2. API URL 保持默认 `http://127.0.0.1:3425/v1`。端口改过（`MAGPIE_ADDR` 或 magpie
   的 `settings.json`）就改成对应端口。
3. API Key 可留空。留空时本插件默认发 `Bearer magpie-drifox`，让这些调用在 magpie
   的 Usage / Requests 页归到 `drifox` 名下。
4. 点「获取模型列表」：插件先请求 `/api/hello` 确认对端确实是 magpie，再拉
   `/v1/models`，把 magpie 当前可见的全部模型填进下拉框。
5. 选一个模型开始对话。

模型 id 形如 `deepseek/deepseek-v4-pro`、`anthropic/claude-sonnet-5`、
`group/opus-anywhere`。路由组也照原样选，配额耗尽后的回退由 magpie 内部完成。

## 内嵌 magpie 网页界面

插件带一个全屏工作页（侧边栏「自定义插件」分组的 magpie 项，或命令
`/magpie:web`），
里面直接内嵌 magpie 自己的网页界面：切模型、加服务商、看配额与用量、改路由
组，跟开浏览器里那个页面是同一套。

**它连的是 `127.0.0.1:3430`，不是网关的 3425。** 这两个是不同的东西：

| 端口 | 用途 | 由谁开启 |
|------|------|----------|
| 3425 | LLM 网关（DriFox 聊天走这里） | App / `magpie serve` / 桌面版任一形态 |
| 3430 | 网页界面（本页走这里） | **只有** `magpie web` / `magpie serve --web` / `magpie daemon install --web` |

所以只装了桌面 App 时，工作页会引导你启动网页服务。要内嵌使用，得从终端
启动网页服务：

```sh
magpie web --no-open          # 默认 3430
```

页面会自动判断本地状态并给出对应引导：

| 状态 | 引导 |
|------|------|
| 端口无响应 + PATH 有 `magpie` | 显示「启动 magpie web」按钮（一键拉起，自动固定 key）+ 可复制的命令 | 
| 端口无响应 + PATH 无 `magpie` | 提示未安装 + 「让 AI 帮我装」按钮 |
| 端口有响应但页面拒绝 | 提示 key 不匹配 + 「启动 magpie web」用固定 key 重启对齐 |

「让 AI 帮我装」不自己下载安装——它会把安装指令写进输入框，由对话里的模型
按你的系统环境处理（Windows / macOS / Linux 装法不同，插件硬编码反而容易错）。
插件只用 `input.write` / `ui.notify` / `process.start` 三个能力；启动 magpie
经宿主能力完成，插件代码不碰 `subprocess`。

### 启动与 key：插件自动管理

「启动 magpie web」按钮做的事：

1. 插件配置里没有 Web Key 时，生成一个稳定随机值存进插件配置（首次启动后
   固定不变）；
2. 以环境变量 `MAGPIE_WEB_KEY=<key>` 后台启动 `magpie web --no-open`（改过
   端口则带 `--addr`）；
3. 轮询等端口就绪，加载页面（URL 自带 `?k=<key>`）。

之后无论重启 magpie 还是重启电脑再点启动，都是同一个 key，URL 永远有效，
不再需要手动设环境变量。想换 key：改插件设置里的「Web Key」，重启一次
magpie web 即可。

或者装成后台服务，开机自动带网页：

```sh
magpie daemon install --web
```

### Web Key

`magpie web` 每次启动会生成一个新的随机 key，URL 必须带 `?k=<key>` 才能进。
用「启动 magpie web」按钮拉起时插件自动固定 key（见上），无需手动设。要从
终端自己启动并固定，先设环境变量再启动：

```sh
MAGPIE_WEB_KEY=mykey magpie web --no-open
```

然后把 `mykey` 填进插件的设置卡（设置 → 插件 → magpie 网页界面 → Web Key）。
设置里还有「网页端口」，改了 3430 就同步改这里。

key 留空时页面仍会尝试加载，被拒绝时页面顶部会提示 key 不匹配（此时点
「启动 magpie web」让插件用固定 key 重新拉起即可）。

## 已知限制

这些是「聚合网关」形态的固有代价，不是插件缺陷：

- **能力表按最宽声明。** magpie 背后横跨几十家厂商，一张表无法同时准确描述全部 id。
  本插件按 `context_limit=200000`、`supports_thinking=True`、
  `thinking_param=reasoning_effort` 声明，选到窗口更小或不吃思考参数的模型时，
  超限由厂商返回 400。
- **采样参数原样透传。** 选到不接受采样参数的模型（o1/o3 类）时，需在模型配置卡
  手动关掉温度等参数。
- **未接原生配额面板。** `GET /v1/magpie/quotas` 的响应结构未经实测，插件不做
  猜测式解析。看配额请用内嵌的 magpie 网页界面（Quotas / Usage 页），或在
  Claude Code 状态栏用 `magpie statusline`。
- **不管理 magpie 配置。** magpie 的文档明确「读 settings.json，不要写」。改模型、
  加服务商请用 magpie 自己的界面或 CLI。
- **只走 OpenAI 兼容协议。** magpie 也提供 Anthropic Messages 与 Gemini 端点，
  DriFox 侧走 OpenAI `/chat/completions`，协议转换由 magpie 完成。
- **模型 id 前缀会命中主程序内置判定器。** magpie 的 id 带厂商前缀
  （`deepseek/deepseek-v4-pro`、`google/gemini-3.1-pro`），主程序的
  `system-model-adapters` 会按模型名子串判定：`deepseek/...` 命中
  「thinking 模式需回传 reasoning_content」，含 `gemini` 的命中 Gemini
  thought_signature 分支。协议适配由 magpie 负责，这两条判定对 magpie
  通常是多余而非有害；若实测出现 400，可另加 model_adapters 组件按
  `family == "magpie"` 覆盖这两个开关。
- **默认模型为空是刻意的。** magpie 有哪些模型取决于你在 magpie 里加了多少
  服务商，插件不内置任何模型名。保存时主程序会自动把「模型列表」首项设为
  「模型名称」，所以第一次必须先点「获取模型列表」再保存；不点则模型列表为空、
  模型名称为空，聊天时会提示先配置模型。

## 排障

「获取模型列表」报错时的对应关系：

| 报错 | 原因 | 处理 |
|------|------|------|
| 连不上 magpie 网关 `http://...` | 网关没跑，或端口不对 | magpie 页点「启动 magpie web」，或核对端口 |
| `... 不是 magpie 网关：/api/hello 返回 ...` | 该端口被别的服务占用 | 换端口，或停掉占用方 |
| 读取 magpie 模型列表失败 | 网关在跑但 `/v1/models` 异常 | 在浏览器打开 `/v1/models` 看返回 |
| magpie 返回的模型列表为空 | magpie 里还没加服务商，或模型对 agents 不可见 | 在 magpie 里添加服务商 |
| 页面显示「启动失败」 | 找不到 magpie，或宿主缺 `process.start` 能力 | 按提示安装 magpie，或升级 DriFox ≥ 0.6.11 |
| 页面显示「页面加载失败（多为 web key 不匹配）」 | 端口上的实例用的是另一次启动的随机 key | 退出现有 magpie 进程后点「启动 magpie web」对齐 key |

## 许可

GPL-3.0-or-later
