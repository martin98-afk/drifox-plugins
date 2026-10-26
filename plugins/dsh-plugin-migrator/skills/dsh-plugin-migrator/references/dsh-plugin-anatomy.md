# dsh 插件解剖

本文件回答一个问题：给定一个目录，怎么确定它是不是 dsh 插件、它到底提供了什么。所有结论来自本地实检（`~/.dsh/profiles/` 下约 90 个 `@deepseek-ai/*` 包）与官方仓库 `deepseek-ai/deepseek-harness` README。

## 1. dsh 是什么

DeepSeek Harness（命令 `dsh`）是 deepseek-ai 的开源 agent harness，构建在 Cordis 之上，架构口号「一切皆插件」：模型、工具、沙箱、会话存储、UI、甚至 agent loop 本身都是可替换的插件。MIT，开发者预览期，破坏性变更频繁（约 1.7–2.8 天一个 prerelease）。

**它不是 Claude Code 插件。** 迁移时不要套用 `.claude-plugin/` 的心智模型。

## 2. 一个 dsh 插件的最小构成

```
@scope/pkg-name/
├─ package.json          # 含 "dsh" 声明段 —— 识别入口
├─ cordis.patch.yml      # dsh.bundle.patch 指向；id-targeted insert 列表
├─ lib/index.js          # 已编译产物（rollup 打包，通常单文件多 region）
├─ types/ (lib/types/)   # .d.ts
├─ locale/{en,zh}.json   # 面向 UI 的显示名
└─ README.zh.md / README.md / README.i18n.yaml
```

### 2.1 `package.json` 的 `dsh` 段

三种形态，看到哪种就用哪种路径：

| 形态 | 例子 | 含义 |
|---|---|---|
| `dsh.bundle.patch: <string>` | `@deepseek-ai/dsh-base` | bundle 根插件，patch 文件声明 downstream 插件行 |
| `dsh.bundle.patch: [<string>...]` | `@deepseek-ai/dsh-web-app` | bundle + 多个 preset patch（standard/ptc/minimal/cordis） |
| `dsh.client.inject: [...]`, `dsh.client.platform: "web"` | `@deepseek-ai/dsh-client-ui-skill` | Client 侧插件（React UI），声明注入到哪些 client 服务 |
| `dsh: "lib/bin.js"` | `@deepseek-ai/dsh` | CLI 入口，不是插件，跳过 |

**识别规则**：`package.json` 里没有 `dsh` 段 → 不是可直接迁移的 dsh 插件（可能是内部 leaf 包或普通 npm 依赖）。

实测偏差要记住：`~/.dsh/profiles/node_modules/@deepseek-ai/` 下约 90 个包里，**带 `dsh` 声明段的只有 43 个，且其中 3 个是 bundle、其余全是 `dsh.client.*` 的 Client UI**。也就是说官方发行包几乎全是 host/client 内部 leaf（`dsh-skill`、`dsh-command-compact`、`dsh-tool-web` 都没有 `dsh` 段）。真正可迁移的第三方 dsh 插件不在 `~/.dsh/profiles` 里，要从 npm / GitHub（`topic:dsh-plugin`）/ 用户自己装的 profile 拿。

### 2.1.1 第三方插件带的额外元数据

真实第三方包（如 `dsh-plugin-guide`）除 `dsh.bundle.patch` 外还有两段，都是判据：

- `engines.dsh` —— 面向的 harness 版本范围。缺失则无法判断源包面向哪个版本。
- `dshWorkshop` —— 元数据块：`schema`、`type: plugin`、`permissions`（如 `filesystem:read`）、`compatibility.dshVersions`、`capability.{id,kind,invocation,expected}`、`lifecycle`。`capability.invocation` 常直接写明能力怎么被解析（例如 `ctx.skills.get('<id>')`），这是判定能力落点的一手证据；`permissions` 是 DriFox 侧 `agents/*.md` 权限声明的直接依据。

包根 `SKILL.md` 也是常见形态（`files` 里列 `SKILL.md`），不一定在 `skills/<name>/` 下。

### 2.2 `cordis.patch.yml` 的结构

顶层是 YAML 数组，元素为 patch entry。最常见的 `- insert:` 携带一个插件行列表：

```yaml
- insert:
    - id: tool-bash
      name: '@deepseek-ai/dsh-tool-bash'
      disabled: !!js process.platform === 'win32'
      config:
        maxBytes: 65536
```

行长这样读：

- `id`：patch 层内的唯一标识。上层 patch 用同 `id` 覆盖下层同 `id` 行的 `config`（整行替换，不是深合并）。
- `name`：cordis 插件名。约定：
  - `@scope/pkg` → 普通包
  - `@scope/pkg/tools` → 包内的**具名导出**，通常是 tools 子集（例：`@deepseek-ai/dsh-plugin-manager/tools`）
  - `cordis:group` → 分组容器，子元素在 `config:` 下，配 `group: true` 与 `isolate:` 隔离服务名
- `disabled`：布尔或 `!!js <表达式>`。**求值需要 JS 运行时**，静态解析时把 `!!js` 值原样留为人类可读字符串并标记不可判定，不要猜它在当前平台的值。
- `config`：行配置。对 `cordis:group`，`config` 是子行列表（递归同构）。

### 2.3 patch 的层级与覆盖

组合顺序：`dsh.profile.bundles`（package.json）→ 各 bundle 的 patch → 用户 profile 的 `cordis.patch.yml` → `--patch` overlay。同一 `id` 后写覆盖先写（整行替换）。

所以一棵 patch 树的实际生效形态要**按层叠完再看**，不能只读最内层。`standard.patch.yml` 里的 `preset-standard` 行就是典型：`presets/standard.patch.yml` 声明 preset 的插件清单，profile 层的用户编辑只覆盖 `config.plugins` 里某个 id。

## 3. 插件提供的能力落在哪

dsh 的「能力」分三类，可迁移性差别很大：

### 3.1 声明式 skill bundle（最易迁移）

由 `dsh-skill-filesystem` 从磁盘发现。格式：

- 目录 bundle：`<root>/<name>/SKILL.md`
- 平铺文件：`<root>/<name>.md`
- **刻意不支持嵌套 `**/SKILL.md`**（深度固定为 1）

frontmatter 必填 `name`（kebab-case）、`description`；可选 `whenToUse`、`metadata`、`disable-model-invocation`、`user-invocable`。

发现根与 rank（数字小的赢）：

| rank | 来源 | 路径 |
|---|---|---|
| 100 | project-dsh | `<projectRoot>/.dsh/skills` |
| 200 | project-agents | `<projectRoot>/.agents/skills` |
| 300 | custom | `Config.customSkillDirs` |
| 400 | user-dsh | `<dshHome>/skills` |
| 500 | user-agents | `<agentsHome>/skills` |

bundle 内可有 `references/`、`scripts/`、`assets/`、`examples/` 子目录。

### 3.2 运行时服务包（难迁移）

包在 `lib/index.js` 里用 cordis 或各子系统 API 注册能力。注册面：

| 注册目标 | 典型包名前缀 | 注册方式 |
|---|---|---|
| `ctx.tools` | `dsh-tool-*` | `defineTool({ name, description, parameters, output, execute })` |
| `ctx.commands` | `dsh-command-*` | `ctx.commands.register({ name, description, input, handler })` |
| `ctx.skills` | `dsh-skill`（注册表）、`dsh-skill-filesystem`、`dsh-tool-skill` | `registerProvider` / `register` |
| `ctx.*` cordis 服务 | `dsh-llm`、`dsh-session`、`dsh-agent`、`dsh-workspace`、`dsh-attachment` | 插件导出 `apply(ctx)` + `inject: [...]` |
| client UI | `dsh-client-ui-*` | React 组件，通过 `dsh.client.inject` 声明注入点 |

**关键差异**：dsh 的 command handler 与 tool 是 **TypeScript 代码**，注册后即时注册即时可见；DriFox 的 `commands/*.md` 是**提示词**（`type: prompt`），`tools/*.py` 是** Python**（必须有 `register(registry)`）。这不是格式转换，是执行模型换了。

### 3.3 agent preset（半可迁移）

`dsh-agent-preset` 行在 patch 里声明一个 preset：`id`、`order`、以及 `plugins:` 子行列表。preset 是一套「系统提示前缀 + 工具白名单 + 能力开关」的组合，本质上是一张配置表。它可以落成 DriFox 的一个 `agents/<name>.md`（persona 文本 + 权限声明），但 preset 的「插件清单」语义在 DriFox 没有对应——DriFox 没有组合层。

## 4. 已经迁过的三个插件（本仓库内的先例）

读它们能省很多摸索成本，但要明白它们都是**人工语义重写**，不构成自动转换的证据：

| 插件 | 源 dsh 材料 | DriFox 产物 | 手法 |
|---|---|---|---|
| `plugins/dsh-router` | dsh-routing-suite 的分类规则 | 4 agents + 2 commands + 3 skills + 1 hook | 关键词正则与 persona 段重写为 markdown，行为带映射到 prompt 文本 |
| `plugins/dsh-super-injector` | 会话审计与插件状态 | 3 tools（`plugin_status.py` 等）+ hooks | TS 工具逻辑用 Python 标准库重写 |
| `plugins/dsh-presets` | `@deepseek-ai/dsh-agent-preset` standard/code/cordis | 3 agents + hook + 2 commands + skill | preset 清单翻译成三个 agent 角色 |

注意 third party 材料只能抽象为原则：**不要复制他人的提示词原文、 personas 措辞、目录命名到新产物里。** 上述三个已经存在的插件是既有事实，新迁移的产物应当自己写 Description 与 persona 文本。

## 5. 常见误判

- 把 `lib/index.js` 当成源码逐读 → 它是 rollup 打包产物，`//#region` 里塞的是**其他包的内联副本**（例如 `dsh-tool-skill/lib/index.js` 里内联了 `partial-json` 与 `brand` 的实现）。要靠 `package.json` 的 `inject` / `peerDependencies` 和 `README` 判断它注册了什么，不要从打包体里数 import。
- 把 `@deepseek-ai/dsh-*` 全当成「官方插件样例」→ 绝大部分是 harness 自己构成用的**内部 leaf 包**（`dsh-base`、`dsh-agent`、`dsh-session`…），它们不属于可执行迁移范围。
- 以为 `disabled: true` 的 patch 行不需要处理 → 它表达的是「默认关闭，需要时开启」的能力分支（常见的是插件市场、工具管理这类可选面），报告中要单列，不要与不可迁移的能力混在一起。
- 以为 `node_modules` 里的所有 `@scope` 都能迁 → 只有带 `dsh` 声明段的是插件，其余（`react`、`zod`、`express`…）是依赖。
