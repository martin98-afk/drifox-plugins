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

## 让 magpie 认得 DriFox

magpie 有自己的 Agents 页与 Usage / Sessions 页。插件随包带一个 magpie 侧的
agent 插件（`agent_plugin/`），登记后：

| 位置 | 效果 |
|------|------|
| Agents 页 | 出现 DriFox 一行（图标 + 名字） |
| Usage / Requests | 调用记在 `DriFox` 名下，带 DriFox 的会话 id |
| Sessions 页 | **不出现 DriFox 会话**（见下方架构限制） |

三条路径都会自动登记（同一个幂等函数，重复调用无副作用）：

1. **插件加载时**（最关键）：只要检测到机器上用过 magpie（PATH 有 `magpie`
   或 `~/.config/magpie` 已存在），就在后台静默登记。装完插件打开 magpie
   就能看到 DriFox，不用点任何按钮；
2. 点「启动 magpie web」时，拉起前先登记；
3. 点「让 AI 帮我装」时，写提示词前先登记（装好第一次启动就认得，开箱即用）；
4. 指引面板的「让 magpie 认得 DriFox」按钮，手动重试 + 探测是否真的生效。

加载期登记刻意加了条件：从未装过 magpie 的机器上**不会**凭空造
`~/.config/magpie` 目录。

登记是往 magpie 的插件注册表（`<config>/magpie/plugins.json`，Windows 上是
`~\.config\magpie\plugins.json`）追加一条 spec，**不依赖 magpie 是否已装，
也不需要 Bun**。手动等价命令：

```sh
magpie plugin add <本插件目录>/agent_plugin
```

状态分两级：**已登记**（注册表里有这条）与**已生效**（`magpie drifox` 退出码 0）。
已登记但 magpie 没加载时，按钮会回显 magpie 的原始报错。

### 不支持「在 magpie 里给 DriFox 选模型」

magpie 的 Agents 页允许为每行选模型，DriFox 这一行刻意没做。三个硬原因：

1. DriFox 的模型名在 `app.config` 的 `LLM.SavedProviders[config_id].模型名称`。
   `config_id` 是 `(API_URL, API_KEY)` 的 sha256 前 8 位，随 Key 变化；magpie 的
   `connect` 只能返回**固定**的 dotted key path，算不出这个 hash。
2. 该文件里的 `API_KEY` 是 `enc:v2` 密文，外部重写 JSON 有损坏风险。
3. DriFox 运行时把配置缓存在内存，保存时整文件覆盖，外部改动会被写回覆盖掉。

所以这一行只是身份标记，模型继续在 DriFox 自己的设置里选。

### Sessions 页不出 DriFox 会话：magpie 的架构限制

magpie 的会话页不是按请求头分组的，而是**扫描每个 agent 自己的会话文件**：
实测本机扫了 611 个（`.workbuddy/` 298、`opencode.db` 276、`.codex/` 15、
`.dsh/` 10、`.claude/` 8、Cursor 的 vscdb 4）。这套 reader 写在 magpie 的
`internal/agent` 里，一个 agent 一个 Go 文件，**只能靠给 magpie 源码提 PR 新增，
没有运行时注册路径**（magpie 的 Integrate 文档明写）。DriFox 的会话存在
`~/.drifox/sessions.db`（SQLite），magpie 没有对应 reader，二进制里连
`drifox` / `.drifox` 字样都没有。

插件侧三条路都堵死，这是实测的：

| 尝试 | 为何不行 |
|------|----------|
| page 插件 `replaces: "sessions"` 顶替会话页 | 能顶替，但页面只能调 `magpie.read(name)`，白名单只有 `usage:summary` 与 `providers:list`，**没有任何读会话的能力** |
| page 自己 fetch DriFox 的本地接口 | page 的沙箱 CSP 是 `default-src 'none'; connect-src 'none'`，**发不出任何网络请求**（连 127.0.0.1 都不行） |
| agent 插件 / middleware 写入会话 | 它们能拿到会话 id（经 `X-Magpie-Session`），但 magpie 只把它写进 usage 记录，不写会话索引 |

能用的替代：**Usage / Requests 页**已经按 `DriFox` + DriFox 会话 id 分组，
要看会话消耗就去那里（筛 `DriFox`）。

要把 DriFox 会话真正列进 Sessions 页，只有 magpie 上游加一个 DriFox adapter
（读 `sessions.db` 的 `sessions` 表：`session_id / title / project / created_at /
updated_at / message_count / first_user_msg / preview`）。magpie 的 README 明确
**不接受外部 PR**，需求要发他们的 Discord 由维护者实现。

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
  加服务商请用 magpie 自己的界面或 CLI。唯一的例外是插件注册表
  （`<config>/magpie/plugins.json`）：那是 magpie 的插件机制入口，不是
  `settings.json`，追加 agent 条目是它的正常用法。
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
| 点「让 magpie 认得 DriFox」提示「已登记但 magpie 未加载」 | 注册表写对了，但 magpie 加载插件失败（多为插件目录被删/改名） | 按回显的 magpie 原始报错处理；本地路径是原地引用，插件目录不能移动 |
| magpie 的 Agents 页没有 DriFox 行 | 注册表未登记，或 magpie 版本太老不认 agent 插件 | 点「让 magpie 认得 DriFox」，并用 `magpie drifox` 核对 |

## 许可

GPL-3.0-or-later
