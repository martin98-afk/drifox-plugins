---
name: code-reviewer
description: 代码审查最佳实践 — 处理代码审查、PR review、质量检查、安全审计、审查 checklist 相关问题。触发关键词：代码审查、PR 审查、code review、PR review、质量检查、安全审计、审查 checklist、代码质量评分、审查报告。
---

# Code Reviewer 技能

本技能为 DriFox 提供 **代码审查最佳实践** 的领域知识。当用户请求代码审查、PR 审查、质量检查或安全审计时，注入本技能。

## 审查维度

代码审查应覆盖以下维度，按优先级排列：

### 1. 安全性（Critical）

| 检查项 | 说明 |
|--------|------|
| SQL 注入 | 拼接 SQL、参数化查询 |
| XSS | 未转义的用户输入渲染 |
| 命令注入 | `eval`、`exec`、shell 拼接 |
| 敏感信息泄露 | 硬编码密钥、Token、密码 |
| 权限绕过 | 未授权访问、越权操作 |
| 依赖漏洞 | 使用已知漏洞的库版本 |

### 2. 正确性（High）

| 检查项 | 说明 |
|--------|------|
| 逻辑错误 | 边界条件、null 处理 |
| 并发安全 | 竞态条件、死锁 |
| 错误处理 | 异常吞掉、错误传播 |
| 边界条件 | 空数组、零除、超大输入 |

### 3. 性能（High）

| 检查项 | 说明 |
|--------|------|
| N+1 查询 | 循环内数据库查询 |
| 重复计算 | 相同计算重复执行 |
| 大数据加载 | 全量加载到内存 |
| 阻塞操作 | 同步 I/O 在主线程 |

### 4. 可维护性（Medium）

| 检查项 | 说明 |
|--------|------|
| 代码重复 | 可抽象的重复代码 |
| 函数过长 | 单函数超过 50 行 |
| 命名不清 | 变量/函数命名无意义 |
| 耦合度高 | 模块间强依赖 |
| 注释缺失 | 复杂逻辑无解释 |

### 5. 风格一致性（Low）

| 检查项 | 说明 |
|--------|------|
| 格式化 | 缩进、空格、空行 |
| 命名风格 | camelCase vs snake_case |
| 导入顺序 | 标准库/第三方/本地 |

### 6. 测试覆盖（Medium）

| 检查项 | 说明 |
|--------|------|
| 测试缺失 | 核心逻辑无测试 |
| 测试质量 | 边界条件覆盖 |
| 集成测试 | 关键路径测试 |

## 常见代码问题模式

### 安全性反模式

```python
# ❌ 命令注入
os.system(f"git commit -m '{message}'")

# ✅ 安全写法
subprocess.run(["git", "commit", "-m", message], check=True)
```

```python
# ❌ SQL 注入
cursor.execute(f"SELECT * FROM users WHERE id={user_id}")

# ✅ 安全写法
cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
```

```python
# ❌ 敏感信息硬编码
API_KEY = "sk-xxxxxx"

# ✅ 环境变量
API_KEY = os.environ.get("API_KEY")
```

### 正确性反模式

```python
# ❌ 裸 except 吞异常
try:
    do_something()
except:
    pass

# ✅ 明确异常类型
try:
    do_something()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
```

```python
# ❌ 共享可变状态
counter = 0
def increment():
    global counter
    counter += 1

# ✅ 无状态或显式状态管理
def increment(counter: int) -> int:
    return counter + 1
```

### 性能反模式

```python
# ❌ N+1 查询
for user in users:
    posts = db.query(f"SELECT * FROM posts WHERE user_id={user.id}")

# ✅ 批量查询
user_ids = [u.id for u in users]
posts = db.query(f"SELECT * FROM posts WHERE user_id IN ({user_ids})")
```

## 审查优先级

### 紧急（必须修复）

- 安全漏洞
- 数据丢失风险
- 服务崩溃风险

### 高优先级（应修复）

- 逻辑错误
- 严重性能问题
- 缺失关键测试

### 中优先级（建议修复）

- 代码重复
- 命名不规范
- 注释不足

### 低优先级（可选优化）

- 代码风格
- 格式化细节

## 审查报告格式

```markdown
## 审查报告

**项目**: <项目名>
**分支**: <分支名>
**审查范围**: <文件/目录>
**审查时间**: <时间>
**审查人**: @reviewer

### 摘要
- 🔴 严重问题: N
- 🟡 中等问题: N
- 🟢 建议优化: N

### 详细发现

#### 🔴 [严重] <标题>
- **文件**: <path>
- **位置**: 第 N 行
- **问题**: <描述>
- **影响**: <风险描述>
- **建议**: <修复方案>

#### 🟡 [中等] <标题>
...
```

## 审查 checklist

### 开审前

- [ ] 了解需求背景和设计意图
- [ ] 确认测试覆盖情况
- [ ] 检查 CI 是否通过

### 安全性检查

- [ ] 无硬编码敏感信息
- [ ] 输入验证充分
- [ ] 权限检查正确
- [ ] 无危险函数调用

### 正确性检查

- [ ] 逻辑符合需求
- [ ] 错误处理完善
- [ ] 边界条件覆盖
- [ ] 并发场景考虑

### 性能检查

- [ ] 无明显性能问题
- [ ] 资源使用合理
- [ ] 无内存泄漏

### 代码质量检查

- [ ] 命名清晰
- [ ] 注释充分
- [ ] 无重复代码
- [ ] 符合项目风格

## 反模式提醒

- ❌ 不要在审查中过度挑剔格式问题（留给 linter）
- ❌ 不要提出"我觉得这样更好"的纯主观建议
- ❌ 不要遗漏安全相关的审查
- ✅ 要提供具体的修复建议
- ✅ 要解释问题的风险和影响
- ✅ 要区分问题的优先级