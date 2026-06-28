# git-status Hook

向 LLM 上下文自动注入当前 Git 仓库状态，让 AI 无需询问即可知道：

- 当前所在分支（detached HEAD / ahead/behind 远程多少提交）
- 工作树里改了哪些文件（已暂存 / 未暂存 / 未跟踪）
- 整体变更规模（行数增删统计）
- 最近 5 条 commit

## 安装

把整个 `git-status/` 目录放到 `.drifox/plugins/` 下，**无需任何依赖**（只用系统已安装的 git 命令）。

重启 DriFox 或在设置 → 插件中点击"重扫"即可发现。

## 注册到 PreUserMessage 事件

在 `plugins/system/hooks/hooks.json` 的 `PreUserMessage` 列表里追加：

```json
{
  "hooks": [
    {
      "type": "python",
      "function": ".git_status:hook",
      "add_output_to_context": true,
      "statusMessage": "正在注入 Git 状态...",
      "id": "git_status_inject"
    }
  ]
}
```

`function` 字段的格式是 `<文件名（不含 .py）>:<函数名>`，DriFox 会从所有已加载的插件目录中查找对应函数。

## 注入示例

```markdown
## Git 仓库状态
**当前分支**: `feature/add-clipboard-tool` ↑2

**工作树状态**:
- 已暂存 (1):
  - [修改] `app/tools/file_tools.py`
- 未暂存 (2):
  - [新增] `app/tools/clipboard_tools.py`
  - [修改] `tests/test_file_tools.py`
- 未跟踪 (1):
  - `docs/clipboard_design.md`

**变更统计**: 2 files changed, 145 insertions(+), 12 deletions(-)

**最近 commits**:
- `a1b2c3d feat: add MCP clipboard bridge`
- `d4e5f6g fix: handle empty input in file reader`
- `h7i8j9k docs: update API reference for tools`
- `l0m1n2o refactor: extract path validation helper`
- `p3q4r5s chore: bump pyttsx3 to 2.90`
```

## 设计取舍

| 选择 | 理由 |
|------|------|
| git 命令用 subprocess 调用 | 无需 Python 依赖，跨平台一致 |
| 单次命令 3s 超时 | git 卡死不能阻塞 AI 对话 |
| 输出限制 2000 字符 | 防止撑爆 token 窗口 |
| 文件清单 30 项后折叠 | 真正重要的状态在前几个文件 |
| porcelain v1 输出 | 可机器解析、跨版本兼容 |
| 无 git 仓库时返回空 | 不打扰用户，DriFox 会跳过注入 |
| 任何异常都吞掉 | hook 永远不能中断主对话流 |

## 关闭 / 卸载

- **临时禁用**：在 DriFox 设置 → 插件 → git-status 中点击禁用
- **彻底删除**：删除 `.drifox/plugins/git-status/` 整个目录
- **单次跳过**：hooks.json 中移除对应条目即可

## 兼容性

- Python 3.10+
- Git 2.x（任意较新版本）
- Windows / macOS / Linux 全平台（git 命令本身跨平台）
