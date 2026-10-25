# magpie-agent-drifox

让 magpie 认得 DriFox：Agents 页出现 DriFox 一行，Usage / Requests 把这些
调用记在 `DriFox` 名下并带上 DriFox 的会话 id。

这是 magpie 侧的插件包，不是 DriFox 插件。DriFox 的 magpie 插件会调
`magpie plugin add <本目录>` 把它登记进去，通常不需要手动装。

## 它做什么

一个 magpie agent 插件（`"magpie": { "agent": ... }`），只声明身份：

| 字段 | 作用 |
|------|------|
| `id` / `name` | Agents 页那行的 id 与显示名 |
| `icon` | 内联 64px PNG（magpie 的 agent 图标只认图标名 / https URL / data URL） |
| `ua` | 无网关 key 时 magpie 按 User-Agent 首词归属，这里兜住那种情形 |
| `config` | 写入目标，指向 `~/.drifox/plugin_data/magpie/agent-link.json` |
| `connect` | 把网关地址与专属 key 写进上面那个文件（见下） |

### connect 必须返回内容

magpie 的 agent 插件有两级校验：加载期只要求 `config` 存在、`model` 与
`connect` 至少有一个；但**在 UI 里点「连接」时会调 `connect()`，返回空对象会被
拒**，报 `connect returned no keys to write`。所以 `connect` 返回两个键：

```js
export function connect({ gateway }) {
  return { "drifoxGateway.url": gateway.v1, "drifoxGateway.key": gateway.key }
}
```

实际写出的内容（实测）：

```json
{ "drifoxGateway": { "url": "http://127.0.0.1:3425/v1", "key": "magpie-drifox" } }
```

key 是 magpie 给 DriFox 这一行的专属网关 key（形如 `magpie-<id>`）。
**DriFox 当前不读这个文件**（它的插件配置只认 `plugin_data/magpie/config.json`），
写它只是为了满足 magpie 的连接校验，同时把网关地址留个痕迹。
它不会影响 DriFox 的行为，也不会碰 `app.config`。

## 它不做什么

**不在 magpie 里给 DriFox 选模型。** 三个硬原因：

1. DriFox 的模型名在 `app.config` 的 `LLM.SavedProviders[config_id].模型名称`，
   `config_id` 是 `(API_URL, API_KEY)` 的 sha256 前 8 位，随 Key 变化；magpie 的
   `connect` 只能返回固定的 dotted key path，算不出这个 hash。
2. 该文件里的 `API_KEY` 是 `enc:v2` 密文，外部重写 JSON 有损坏风险。
3. DriFox 运行时把配置缓存在内存，保存时整文件覆盖，外部改动会被写回。

模型继续在 DriFox 自己的设置里选。

**也不负责让 DriFox 会话出现在 magpie 的 Sessions 页。** 那一页靠 magpie
内置的 reader 扫描各 agent 自己的会话文件（`.claude/`、`.codex/`、`opencode.db`
等），新增来源只能给 magpie 源码提 PR，插件没有运行时注册路径；而 magpie 的
page 插件虽有 `replaces: "sessions"` 能顶替页面，却只能读 `usage:summary` 与
`providers:list`，且沙箱 CSP 为 `connect-src 'none'` 发不出任何请求。
要看 DriFox 会话的消耗，用 Usage / Requests 页筛 `DriFox`。

## 环境要求

不需要 Bun。magpie 的 agent 插件跑在它自带的 moejs 引擎里，只有 OpenCode 风格的
provider 插件才需要 Bun。

## 手动安装

```sh
magpie plugin add <此目录绝对路径>
```

magpie 对本地路径是**原地引用**（不拷贝）：这个目录不能删、不能改名，否则
agent 行会消失。重复 `add` 同一个路径是幂等的。

卸载：

```sh
magpie plugin rm <此目录绝对路径>
```

## 许可

GPL-3.0-or-later
