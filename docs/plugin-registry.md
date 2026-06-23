# 插件发现与加载

本文说明 DriFox 启动时如何发现、加载、激活一个插件。

## 插件目录

DriFox 在以下位置查找插件（按优先级）：

1. **项目级**：`./.drifox/plugins/`
2. **用户级**：`~/.drifox/plugins/`（Windows: `%USERPROFILE%\.drifox\plugins\`）
3. **系统级**：`/etc/drifox/plugins/`（仅 Linux/macOS）

每个位置下的每个子目录都被视为一个候选插件。

## 加载流程

```
[启动]
  │
  ▼
遍历各 PLUGIN_DIR 下所有直接子目录
  │
  ▼
对每个子目录，读取 <name>/.drifox-plugin/plugin.json
  │
  │ 校验失败 ──► 跳过，记录 warning 日志
  │
  ▼
通过 JSON Schema 校验
  │
  ▼
检查 type 字段
  │
  │ type=system ──► 必须签名验证（受信任）
  │ type=user   ──► 信任用户态
  │
  ▼
读取 plugin.json.components
  │
  ├── components.commands = true
  │     遍历 commands/*.md，注册为 /<name>:<cmd>
  │
  ├── components.hooks = true
  │     读取 hooks/hooks.json，按 event 索引
  │     在对应事件触发时调用 <name>_hook.py 中的函数
  │
  └── components.skills = true
        遍历 skills/*/SKILL.md，注册到 AI 技能索引
```

## 命名规则

- 插件目录名 = `plugin.json` 中的 `name` 字段
- 命令注册为 `/<plugin-name>:<command-file-stem>`
  - 例如 `plugins/evolver/commands/status.md` → `/evolver:status`
- 钩子入口函数命名规范：`hook_<event_snake_case>`

## 冲突处理

| 冲突类型 | 处理 |
|---------|------|
| 同名插件 | 后加载的覆盖前者，输出 warning |
| 同名命令 | 后加载的覆盖前者，输出 warning |
| 同一事件多个钩子 | 按 `hooks.json` 中数组顺序串行执行，单个失败不影响后续 |
| 钩子超时 | 强杀进程，记录到 `~/.drifox/logs/hooks.log` |

## 禁用插件

在 `~/.drifox/config.json` 中：

```json
{
  "plugins": {
    "disabled": ["evolver"]
  }
}
```

被禁用的插件会被扫描到但完全不加载。

## 热重载（实验性）

DriFox 0.5+ 支持 `drifox reload` 命令，对已修改的插件自动重新加载：

```bash
drifox reload evolver
```

重载期间该插件的钩子会短暂停止接收事件。

## 卸载

直接删除插件目录即可：

```bash
rm -rf ~/.drifox/plugins/evolver
```

下次启动 DriFox 时该插件不再被发现。
