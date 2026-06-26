# 插件安全审查指引

DriFox 插件可以在运行时进程中执行代码（hooks）、注入 AI 上下文（skills/commands）、调用外部服务（mcp/lsp）。本文件描述插件安全模型与审查 checklist，供插件开发者和审查者参考。

## 1. 威胁模型

| 组件 | 风险面 | 严重度 |
|------|--------|--------|
| **hooks** | Python 代码在 DriFox 进程中执行，可访问文件系统、网络、环境变量 | 🔴 高 |
| **mcp** | 注入外部 MCP 服务器，可执行任意命令、访问网络 | 🔴 高 |
| **lsp** | 注入外部 LSP 服务器，可执行命令 | 🟡 中 |
| **commands** | 注入 AI 上下文的 prompt，可引导 AI 执行危险操作 | 🟡 中 |
| **agents** | 预配置角色与权限，可放宽/收紧 AI 工具权限 | 🟡 中 |
| **skills** | 注入 AI 上下文的知识，可误导 AI 决策 | 🟢 低 |
| **themes** | 仅影响视觉呈现，无执行能力 | 🟢 低 |

## 2. hooks 安全 checklist

hooks 是最高风险组件。每个 hook 插件提交时必须通过以下审查：

### 2.1 代码审查

- [ ] **无硬编码密钥**：不包含 API key、token、密码等敏感凭证
- [ ] **无网络外传**：除非插件明确需要，不向外部服务器发送数据
- [ ] **文件操作受限**：仅写入 `memory/` 目录或用户明确指定的路径
- [ ] **无危险 subprocess**：不执行 `rm -rf`、`format`、`del /f` 等破坏性命令
- [ ] **超时可控**：所有 subprocess 调用有 timeout 参数
- [ ] **幂等性**：钩子可被重复触发，不会产生累积副作用
- [ ] **错误隔离**：单个钩子异常不影响其它钩子或主流程
- [ ] **无 eval/exec**：不使用 `eval()`、`exec()` 执行动态代码
- [ ] **无 os.system**：使用 `subprocess.run()` 替代 `os.system()`

### 2.2 权限最小化

```python
# ✅ 好：仅访问必要的上下文字段
project_root = ctx.get("project_root", "")

# ❌ 坏：尝试访问整个 DriFox 内部状态
import drifox_internal  # 不应存在此依赖
```

### 2.3 资源限制

| 资源 | 建议上限 | 说明 |
|------|---------|------|
| 执行时间 | 15s（AI 回复类 30s） | 超时后 DriFox 强杀进程 |
| 内存 | < 100MB | 避免大文件全量加载 |
| 磁盘写入 | < 10MB/次 | 日志类文件注意轮转 |
| 网络请求 | 非必需不发起 | 必需时用短 timeout |

## 3. mcp/lsp 安全 checklist

### 3.1 mcp 服务器

- [ ] **来源可信**：command 指向已知安全的工具（如 `uvx`、`npx` 正式包）
- [ ] **环境变量**：`env` 中不硬编码密钥，使用占位符提示用户配置
- [ ] **网络暴露**：了解 MCP 服务器是否监听网络端口，评估风险
- [ ] **enabled 默认值**：高风险服务器建议 `enabled: false`，用户手动开启

```json
// ✅ 好：使用占位符
"env": {
    "API_KEY": "your-api-key-here"
}

// ❌ 坏：硬编码真实密钥
"env": {
    "API_KEY": "sk-1234567890abcdef"
}
```

### 3.2 lsp 服务器

- [ ] **command 安全**：language server 来自可信来源
- [ ] **startupTimeout 合理**：默认 10s，不应过长
- [ ] **maxRestarts 有限**：避免无限重启循环

## 4. commands/agents 安全 checklist

### 4.1 prompt 注入防护

commands 和 agents 的 markdown 正文会被注入 AI 上下文。需注意：

- [ ] **无隐藏指令**：不包含对 AI 的隐藏操纵指令（如 "忽略之前的所有指令"）
- [ ] **权限声明合理**：agents 的 `permission` 字段遵循最小权限原则
- [ ] **allowed-tools 受控**：commands 的 `allowed-tools` 不应包含不必要的危险工具

### 4.2 权限模型

```yaml
# ✅ 好：只读探索智能体的权限
permission:
  write: deny
  edit: deny
  multi_edit: deny
  bash: deny
  "*": allow

# ❌ 坏：无限制权限（除非确实需要）
# 不设 permission 字段 = 全部 allow
```

## 5. 审查流程

### 5.1 自动校验（CI）

以下由 `validate_plugins.py` 自动检查：
- manifest 符合 JSON Schema
- 组件资源存在
- hooks Python 文件通过 `ast.parse` 语法检查
- mcp/lsp JSON 格式合法

### 5.2 人工审查（PR）

以下需要人工审查：
- hooks Python 代码的 **行为安全性**（自动校验无法判断）
- mcp 服务器的 **来源可信度**
- commands/agents 的 **prompt 内容合理性**
- 是否存在 **信息泄露** 风险

### 5.3 审查优先级

| 插件类型 | 审查要求 |
|---------|---------|
| 仅 skills/themes | 轻量审查（检查内容合理性） |
| 含 commands/agents | 标准审查（检查权限声明 + prompt 内容） |
| 含 hooks | 严格审查（逐行审查 Python 代码） |
| 含 mcp/lsp | 严格审查（验证外部服务来源） |
| type=system | 最高审查（需签名验证 + 全面审计） |

## 6. 用户侧防护

### 6.1 禁用不信任的插件

```json
// ~/.drifox/config.json
{
  "plugins": {
    "disabled": ["untrusted-plugin"]
  }
}
```

### 6.2 检查插件来源

安装前检查：
- 插件是否来自官方仓库或可信作者
- hooks 代码是否可审查（开源）
- mcp/lsp 指向的服务器是否已知

### 6.3 沙箱建议（未来）

DriFox 计划在后续版本中引入 hooks 沙箱机制：
- 文件系统访问限制（白名单目录）
- 网络访问控制
- 资源使用配额
- 环境变量隔离

当前版本（v0.5）hooks 在主进程中执行，用户需自行评估插件信任度。

## 7. 报告安全问题

如发现插件安全漏洞，请**不要**公开提交 Issue。通过以下方式私密报告：

1. GitHub Security Advisory（推荐）
2. 私密联系仓库维护者

修复并发布补丁版本后，再公开披露详情。
