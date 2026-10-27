# dsh 热门插件集成 — 迁移报告

日期：2026-10-27
源：DeepSeek Harness（dsh）npm 生态，按 `awesome-dsh-plugin.com` 索引的 npm 30 天下载量排序
判定依据：`dsh-plugin-migrator` 技能的 `references/mapping-rules.md`

---

## 1. 数据来源与可信度

| 信号 | 状态 | 说明 |
|---|---|---|
| npm 官方 `downloads/point` API | 不可用 | 返回 2026-06-25~07-01 陈旧窗口，全部为 0 |
| `awesome-dsh-plugin.com/plugins.json` | 可用 | 7211 条，含 npm 30 天下载量（窗口 2026-09-26~10-25） |
| GitHub `topic:dsh-plugin` | 有噪声 | 23295 个仓库，大量非插件项目蹭标签 |
| 索引 `icon` 字段 | 覆盖率 2% | 下载 top50 中 0 个带 icon，无法作为图标来源 |
| 索引 `stars` 字段 | 有噪声 | 聚合仓库子包继承父仓库 star（`dsh-web` 6 个包均为 9.5k） |

下载量可信度判据：`downloads / stars` 比值，正常区间 10–80。超过 200 视为可疑（高频发版自灌）。

---

## 2. 候选评估

工具 / 技能 / 视觉 / 浏览器四类，下载量 ≥ 5000 的共 43 个。逐个判定可迁移性：

| 包 | 30 天下载 | 形态 | 判定 | 理由 |
|---|---|---|---|---|
| `@liustack/modlens` | 84,660 | `skills/modlens/` + dist | **port** | 有完整可读技能目录，CLI 通过 `scripts/run.ps1` 自包含 |
| `@liustack/modsearch` | 37,236 | `skills/modsearch/` + dist | **port** | 同上 |
| `@roarpeng/graphflow` | 21,367 | `skills/graphflow/` + dist + `mcp.json` | **port** | 技能正文完整；MCP 服务端未迁移（见 §4） |
| `lunheng-article-pipeline` | 36,636 | `skills/` 两个子技能 + lib | **port** | 技能正文完整，175 个 reference 文件齐全 |
| `dsh-mattpocock-skills-deck` | 12,447 | `bundled-skills-zh/` 27 个 | **port（部分）** | 只有 11 个可被 AI 调用，其余 16 个 `disable-model-invocation: true` 已排除 |
| `dsh-free-search` | 48,147 | `lib/` 编译产物 + patch | **skip** | 无 skills 目录，纯 JS 实现，只能产 stub |
| `dsh-mnemon` | 46,705 | `lib/` 编译产物 + patch | **skip** | 同上 |
| `@michengai/dsh-agency-agents` | 36,730 | `lib/` + assets（332 个 md 资料） | **skip** | 智能体资料是 321 个独立 md，但加载逻辑在编译后的 `lib/client.js`（707KB），无法复现调度语义 |
| `dsh-vision-router` | 29,351 | `lib/` + presets | **skip** | 纯 JS，无技能目录 |
| `@anionex/dsh-vision-toolkit` | 10,773 | `lib/` + runtime | **skip** | 依赖作者自建远程服务，无本地可迁移逻辑 |
| `dsh-skill-hub` | 6,182 | `lib/` + src | **skip** | 技能管理 UI，属宿主内部能力，DriFox 已有等价设置卡 |
| `dsh-ops` | 31,257 | Rust 二进制 + patch | **skip** | 原生二进制，跨范式无法搬运 |
| `dsh-browser-cdp` | 18,387 | `lib/` + CDP | **skip** | DriFox 已有 `browser` 插件（v1.4.4） |
| `dsh-mcp-connector` | 20,672 | `lib/` + 目录数据 | **skip** | DriFox 已有 MCP 设置面板 |
| `dsh-computer-use-win` | 8,305 | 原生 + lib | **skip** | DriFox 已有 `desktop-automation` 插件 |

**结论**：43 个候选里只有 5 个具备可读的声明式材料，其余均为编译后 JS / 原生二进制 / 依赖远程服务。

---

## 3. 已产出插件

| 插件 id | 技能数 | 上游 | license | 30 天下载 |
|---|---|---|---|---|
| `modlens` | 1 | liustack/modlens | MIT | 84,660 |
| `modsearch` | 1 | liustack/modsearch | MIT | 37,236 |
| `graphflow` | 1 | Roarpeng/GraphFlow | Apache-2.0 | 21,367 |
| `lunheng-article-pipeline` | 2 | zuoyunlai/lunheng-article-pipeline-dsh | MIT | 36,636 |
| `mattpocock-skills` | 11 | FeatherHunter/dsh-mattpocock-skills-deck | MIT | 12,447 |

合计 16 个技能。

### 图标

五个源包中只有 `lunheng-article-pipeline` 自带 `icon.svg`（CorelDRAW 绘制的“论衡”徽标，小麦色圆底），直接沿用。
其余四个源包及索引均无图标，按插件语义新绘 SVG（`icon.svg` + `icon_dark.svg` 双主题）：

- `modlens`：取景框 + 山景 + 第二视角轮廓（视觉桥）
- `modsearch`：放大镜 + 结果行（搜索桥）
- `graphflow`：五节点代码图谱（AST 索引）
- `mattpocock-skills`：圆角徽章内代码尖括号与斜杠（工程技能集）

---

## 4. 未映射能力

按 `mapping-rules.md` 的兜底纪律，以下内容没有对应通道，显式记录而非静默丢弃：

1. **`cordis.patch.yml` 挂载逻辑**（5 个包全部）—— DriFox 无 cordis 运行时。5 个包的 patch 内容都只是「挂载自己」，不含独立能力单元，因此不构成信息损失。
2. **`graphflow` 的 MCP 服务端**（`mcp.json` + `dist/`）—— 技能的四个 `gf_*` 工具依赖本包 MCP 服务。技能正文已迁移，但 MCP 服务需用户自行安装上游 npm 包并配置。**这是 `MIGRATION_TODO`。**
3. **`lunheng-commands` 的 5 个 `.mjs` 脚本**（`route-command.mjs` 等）—— 依赖 dsh 的命令路由运行时。技能正文中的命令语义已迁移，脚本执行路径未迁。
4. **`modlens` / `modsearch` 的 `dist/`** —— 上游 CLI 本体，技能内 `scripts/run.ps1` 会在需要时通过 `npx` 拉取，不随包分发。
5. **`@michengai/dsh-agency-agents` 的 321 个智能体资料** —— 资料本身是纯 markdown 可读，但调度逻辑（何时召唤哪个智能体、如何注入）写在 `lib/client.js`。只搬资料而不搬调度，产出的是 321 个死文件。**判定 skip，理由记录在此。**

---

## 5. 被排除的技能

`mattpocock-skills` 源包 27 个技能中，16 个带 `disable-model-invocation: true`：

```
ask-matt, grill-me, grill-with-docs, handoff, implement, implement-spec,
improve-codebase-architecture, retro, setup-matt-pocock-skills, teach,
to-questionnaire, to-spec, to-tickets, triage, wait-what, wayfinder
```

该字段语义是「模型不得主动调用，只能用户显式触发」。DriFox 无对应机制，搬入后会变成模型可随意调用，语义反转。已移出至 `.dsh-migration/parked-user-only/`，未进插件。

`agents/openai.yaml` 是 OpenAI 平台专用配置，中文版本身也未包含，与 DriFox 无关。

---

## 6. UI 类迁移评估

按用户要求，UI 类只做评估不实现。

**榜单事实**：UI 增强类以 157.6 万下载占（剔除 `billion-context` 后）17.7%，是第一大类。头部为 `DSH-better-sidebar`（18.2 万）、`dsh-codex-ui`（11.1 万）、`dsh-task-board`（10.1 万）。

**迁移可行性判定：低。** 三条硬障碍：

| 障碍 | 事实 | 后果 |
|---|---|---|
| React 组件本体不在包里 | 32 个 `dsh-client-ui-*` 包中 31 个没有 `register` 调用，浏览器侧通过 `package.json` 的 `dsh.client` 声明单独分发 | 包内无 UI 结构可提取 |
| 扩展点无等价物 | 这些包依赖 dsh 的 `client-ui-sidebar` / `client-ui-conversation` / `client-ui-settings` 等注入点 | DriFox 的 UI 扩展点是 Qt widget 注册（`UIPluginRegistry`），扩展点模型不同 |
| 渲染栈不同 | dsh 是 Web（React + DOM），DriFox 是 Qt | 无法机械翻译，只能按功能重新设计 |

**唯一有部分可行性的方向**：`dsh-task-board` 的「多列任务看板 + cron 定时交给真实会话执行」——功能语义清晰，DriFox 已有 `taskboard`（v?）与 `cron-tasks` 插件，需先比对现有能力再决定是否为重复建设。

**建议**：UI 类不做跨范式迁移。若确需某个 UI 功能，按 DriFox 的 Qt 插件规范重写，把上游仅作为功能参考。

---

## 7. 验证证据

### 结构层

```
$ python tools/validate_plugins.py plugins/modlens plugins/modsearch plugins/graphflow \
      plugins/lunheng-article-pipeline plugins/mattpocock-skills
结果：
  OK   modlens
  OK   modsearch
  OK   graphflow
  OK   lunheng-article-pipeline
  OK   mattpocock-skills
✓ 全部 5 个插件通过校验
EXIT=0
```

`marketplace.json` 已同步，211 个插件（原 206 + 新 5）。

### 运行时层 1：技能解析

用宿主真实的 frontmatter 解析路径（`yaml.safe_load` + name/目录名一致性 + description 非空 + 正文长度）逐项检查：

```
16 个技能全部通过，失败 0
EXIT=0
```

### 运行时层 2：manifest 契约

调用宿主真实的 `_load_manifest_file`（含 schema 校验、字段限长、未知能力检测）：

```
ok   modlens                  v1.0.0 icon={'light': 'icon.svg', 'dark': 'icon_dark.svg'}
ok   modsearch                v1.0.0
ok   graphflow                v1.0.0
ok   lunheng-article-pipeline v1.0.0
ok   mattpocock-skills        v1.0.0
失败/告警合计 0
EXIT=0
```

### 三层状态

| 层 | 状态 | 依据 |
|---|---|---|
| `structure_status` | `artifact_consistent` | validate_plugins 退出码 0，marketplace 已同步 |
| `runtime_status` | `verified`（技能与 manifest 两层） | 两个验证脚本退出码 0 |
| `human_status` | `pending` | 待用户确认技能语义与上游一致 |
| `MIGRATION_TODO` | 1 条未闭环 | `graphflow` 的 MCP 服务端需用户自行配置，见 §4 第 2 条 |

---

## 8. 发现的问题

**扫描器 bug（需写回）**：`scan_dsh_plugin.py` 第 360 行

```python
decl_kind = "client" if isinstance(dsh_decl, dict) and "client" in dsh_decl else "bundle"
...
if decl_kind == "bundle":
    raw = (dsh_decl.get("bundle") or {}).get("patch")
```

该逻辑假设 `bundle` 与 `client` 互斥。实测 6 个源包**全部同时声明两者**，于是被判为 `client`，`bundle.patch` 从未被读取，扫描结果 `patch_files=[]`、`row_count=0`，与 `package.json` 明写的 `bundle.patch` 矛盾。

影响：所有同时声明 `bundle` 与 `client` 的第三方 dsh 插件（即绝大多数带 Web UI 的插件）都会漏读 patch，能力清单不完整。

修法：`patch_files` 的提取不该受 `decl_kind` 约束，应独立判断：

```python
patch_files = []
raw = (dsh_decl.get("bundle") or {}).get("patch") if isinstance(dsh_decl, dict) else None
if raw:
    patch_files = [raw] if isinstance(raw, str) else list(raw)
```

`decl_kind` 仅用于描述（是否可以同时是 `bundle+client`），不用于门控。本次未改该脚本（属技能插件目录，不在本仓范围），记入写回决策。

---

## 9. 写回决策

**`proposal`**：`scan_dsh_plugin.py` 的 `decl_kind` 门控 bug 应修，理由与修法见 §8。该脚本位于 `D:\work\DriFox\.drifox\plugins\dsh-plugin-migrator\`，不属本仓库，需用户决定是否改。

**`none-with-reason`**：不向 `mapping-rules.md` 写回新规则。本次没有推翻既有判定规则的新发现——所有 skip 判定都能由现有规则（「需要读 JS 实现才能确定语义 → stub/skip」）直接推出。`decl_kind` 是脚本实现 bug，不是规则缺陷，应改代码而非改规则。
