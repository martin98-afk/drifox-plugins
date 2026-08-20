# tool-locator

开发期工具插件：查找工具插件的实现文件路径。

## 解决的问题

DriFox 的工具都是插件（`registry.register` 注册）：
- **system 根**：主程序工作树 `plugins/`（read / edit / bash / lsp / websearch 等系统工具所在）；
- **user 根**：`~/.drifox/plugins/`（可热重载的用户插件）。

当需要修改某个工具的实现时，先要知道它在哪个文件。本插件提供一个工具
`find_tool_path`，输入工具名即返回其实现文件的绝对路径，并标注所属根。

拿到路径后：

- user 根文件直接用 `read` / `edit` / `write` 修改，保存后 DriFox 自动热重载生效，无需重启；
- system 根为主程序工作树插件，修改后需同步主程序仓库；
- 若现有工具不足以满足需求，可加载 `plugin-creator` 技能自行开发新工具。

扫描根与主程序 `PluginToolLoader` 保持一致（优先复用其根列表，失败时按同样规则推导）；
同名工具跨根覆盖规则一致：user 覆盖 system。

## 工具

| 工具名 | 说明 |
|--------|------|
| `find_tool_path` | 查工具实现文件路径。参数 `tool_name`（工具名）；设 `list_all=true` 可列出全部已发现工具及其路径。 |

## 使用

```
/plugin-marketplace 安装本插件
# 或把本目录复制到 ~/.drifox/plugins/tool-locator/
```

然后在对话中让大模型调用 `find_tool_path`，例如：「example_repeat 这个工具的实现文件在哪？」
