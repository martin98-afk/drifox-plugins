---
description: 对当前 git diff 或指定文件执行代码审查，输出质量评分和改进建议
type: prompt
parameters:
  - name: "--file="
    description: "指定要审查的文件路径（相对于项目根目录）"
    param_type: value
  - name: "--staged"
    description: "仅审查暂存区的变更（git diff --cached）"
    param_type: flag
  - name: "--full"
    description: "全项目审查（审查所有已跟踪文件）"
    param_type: flag
mutex_groups:
  scope: ["--file", "--staged", "--full"]
prompt_sections:
  --file: "file_review"
  --staged: "staged_review"
  --full: "full_review"
---

# /review 命令 — 代码审查

你正在处理 `/review` 命令。用户输入的参数（`$ARGUMENTS`）包含审查范围和选项。

## 执行规则

1. **确定审查范围**：根据参数决定审查范围
2. **获取代码变更**：使用 `git diff` 或 `read` 获取代码
3. **系统性审查**：按维度逐项分析
4. **生成报告**：输出结构化审查报告

## 审查维度（按优先级）

| 优先级 | 维度 | 检查重点 |
|--------|------|----------|
| 🔴 Critical | 安全性 | SQL 注入、XSS、命令注入、敏感信息 |
| 🟠 High | 正确性 | 逻辑错误、错误处理、边界条件 |
| 🟠 High | 性能 | N+1 查询、重复计算、阻塞操作 |
| 🟡 Medium | 可维护性 | 代码重复、函数过长、命名不清 |
| 🟢 Low | 风格 | 格式化、命名风格 |
| 🟡 Medium | 测试 | 测试覆盖、测试质量 |

<!-- section:file_review -->

## --file 模式：指定文件审查

当指定了 `--file=<path>` 时：

1. 读取指定文件的完整内容
2. 如果是新增文件，直接审查内容
3. 如果是已存在文件，使用 `git diff HEAD -- <path>` 查看变更
4. 如果文件不存在，提示用户检查路径

<!-- section:staged_review -->

## --staged 模式：暂存区审查

当指定了 `--staged` 时：

1. 执行 `git diff --cached` 获取暂存区变更
2. 如果没有暂存内容，提示用户
3. 审查所有暂存的文件变更

<!-- section:full_review -->

## --full 模式：全项目审查

当指定了 `--full` 时：

1. 使用 `glob` 获取项目中的代码文件
2. 优先审查以下类型的文件：
   - 核心业务逻辑（src/、lib/、core/）
   - 配置文件（config/、settings/）
   - 测试文件（test/、spec/）
3. 排除以下目录：
   - node_modules/、vendor/、dist/
   - .git/、__pycache__/
   - 第三方依赖

## 默认行为

如果用户未指定任何参数，默认执行：

1. 尝试 `git diff` 获取未提交变更
2. 如果没有变更，提示用户使用 `--full`
3. 如果有变更，审查变更内容

## 审查报告格式

输出结构化报告：

```
## 审查报告

**审查范围**: <文件/目录>
**变更行数**: +N/-N
**审查时间**: <时间>

### 摘要
| 严重程度 | 数量 |
|---------|------|
| 🔴 严重 | N |
| 🟡 中等 | N |
| 🟢 建议 | N |

### 详细发现

#### 🔴 [P0] <问题标题>
- **文件**: `<path>`
- **问题**: <描述>
- **影响**: <风险>
- **建议**: <修复方案>

...

### 总结
<总体评价>
```