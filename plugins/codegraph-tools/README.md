# CodeGraph Tools - DriFox 插件

CodeGraph 语义级代码智能工具（`codegraph_explore`），从 DriFox 主程序迁出（工具插件化）。

## 功能

| 模式 | 说明 |
|------|------|
| `status` | 查看索引状态（文件/符号/关系/待同步变更） |
| `search` | 搜索符号，按 kind / visibility / 大小写过滤 |
| `callers` / `callees` | 调用链分析（谁调用了它 / 它调用了谁） |
| `explore` | 综合探索（默认）— 搜索 + 源码位置 + 调用摘要 |
| `impact` | 变更影响分析 — 改一个符号会波及哪些代码 |
| `sync` | 同步索引与文件系统 |
| `files` | 列出已索引文件 |

## 安装

### 方式一：从插件市场安装

```bash
/plugin --install codegraph-tools
```

### 方式二：复制到插件目录

```bash
cp -r plugins/codegraph-tools ~/.drifox/plugins/
# 或 Windows
xcopy /E /I plugins\codegraph-tools %USERPROFILE%\.drifox\plugins\codegraph-tools
```

DriFox 启动时自动发现并加载。

## 使用方式

工具注册为 `codegraph_explore`，由 LLM 通过 `mode` 参数切换能力：

```text
codegraph_explore(mode='status')                    # 看索引状态
codegraph_explore('ChatBackend')                    # 探索 ChatBackend（默认 explore）
codegraph_explore('Manager', mode='search', kind='class')   # 搜所有 Manager 类
codegraph_explore('send_message', mode='callers')   # 找调用者
codegraph_explore('on_click', mode='impact')        # 影响分析
```

也可用别名 `/codegraph` 或直接输入 `codegraph` 触发。

## 依赖

`codegraph-py` 库（未安装时工具返回安装提示，不影响其他工具）：

```bash
pip install codegraph-py[all]
```

## 架构

- 引擎封装（CodeGraphTools）整体从 `app/tools/codegraph_tools.py` 迁入
- 进程级引擎单例，workdir 变更自动重新初始化索引（多窗口安全）
- impl 通过 `tool_ctx["workdir"]` 驱动，不依赖主程序 services
- 带 cooldown 保护：查询前自动快速 sync，避免高频调用全目录扫描
