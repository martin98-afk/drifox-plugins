# tool-locator

开发期工具插件：查找可热重载工具插件的实现文件路径。

## 解决的问题

DriFox 的工具都是可热重载的插件（`~/.drifox/plugins/<name>/tools/*.py`）。
当需要修改某个工具的实现时，先要知道它在哪个文件。本插件提供一个工具
`find_tool_path`，输入工具名即返回其实现文件的绝对路径。

拿到路径后：

- 直接用 `read` / `edit` / `write` 修改该文件；
- 保存后 DriFox 自动热重载生效，无需重启；
- 若现有工具不足以满足需求，可加载 `plugin-creator` 技能自行开发新工具。

## 工具

| 工具名 | 说明 |
|--------|------|
| `find_tool_path` | 查工具插件的实现文件路径。参数 `tool_name`（工具名）；设 `list_all=true` 可列出全部已发现工具及其路径。 |

## 使用

```
/plugin-marketplace 安装本插件
# 或把本目录复制到 ~/.drifox/plugins/tool-locator/
```

然后在对话中让大模型调用 `find_tool_path`，例如：「example_repeat 这个工具的实现文件在哪？」
