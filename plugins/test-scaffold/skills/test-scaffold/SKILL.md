---
name: test-scaffold
description: 测试脚手架与覆盖率分析技能 — 生成测试用例骨架、分析覆盖率缺口、设计边界测试场景、TDD 流程指导、pytest/unittest 最佳实践。触发关键词：生成测试、测试骨架、覆盖率分析、TDD、边界测试、pytest、unittest、单元测试、集成测试。
---

# 测试脚手架技能

本技能为 DriFox 提供测试开发的专业知识支持。当用户需要编写测试、分析覆盖率、或实践 TDD 时，注入本技能。

## 核心原则

### 测试设计原则（F.I.R.S.T）

| 原则 | 说明 |
|------|------|
| **Fast** | 测试应快速执行，避免不必要的 I/O |
| **Independent** | 测试之间相互独立，无执行顺序依赖 |
| **Repeatable** | 每次运行结果一致，不受外部环境影响 |
| **Self-Validating** | 测试自动判断通过/失败，无需人工介入 |
| **Timely** | 测试应及时编写，最好在生产代码之前（TDD） |

### 测试分层模型

```
┌─────────────────────────────────────┐
│         E2E 测试（少量）              │  ← 用户场景，端到端验证
├─────────────────────────────────────┤
│       集成测试（适量）                │  ← 模块间协作，数据流验证
├─────────────────────────────────────┤
│       单元测试（大量）                │  ← 最小单元功能验证
└─────────────────────────────────────┘
```

## 测试模式

### AAA 模式（单元测试）

```python
def test_addition():
    # Arrange - 准备测试数据
    a = 1
    b = 2

    # Act - 执行被测操作
    result = add(a, b)

    # Assert - 验证结果
    assert result == 3
```

### Given-When-Then 模式（集成测试）

```python
def test_user_registration():
    # Given - 前提条件
    user_data = {"name": "test", "email": "test@example.com"}

    # When - 执行操作
    response = register_user(user_data)

    # Then - 验证结果
    assert response.status_code == 201
    assert response.json()["email"] == user_data["email"]
```

### Arrange-Act-Assert with Mocks

```python
def test_fetch_user_data(mocker):
    # Arrange
    mock_db = mocker.patch("app.database.get_connection")
    mock_db.return_value.fetch_one.return_value = {"id": 1, "name": "Test"}

    # Act
    user = get_user(1)

    # Assert
    assert user["name"] == "Test"
    mock_db.assert_called_once()
```

## 边界测试场景清单

### 1. 输入值边界

| 场景 | 示例 |
|------|------|
| 空值 | `None`, `""`, `[]`, `{}` |
| 零值 | `0`, `-0`, `0.0` |
| 极大值 | `sys.maxsize`, `float('inf')` |
| 极小值 | `-sys.maxsize`, `float('-inf')` |
| 边界值 | 数组索引边界、整型溢出边界 |

### 2. 类型边界

| 场景 | 示例 |
|------|------|
| 类型错误 | 传入 `str` 期望 `int` |
| 类型边界 | 空字符串 vs 空列表 |
| 强制类型转换 | 浮点数截断 |

### 3. 业务逻辑边界

| 场景 | 示例 |
|------|------|
| 条件分支 | if/else 所有分支 |
| 循环边界 | 0次、1次、N次、最大次数 |
| 状态转换 | 状态机所有转换路径 |
| 并发边界 | 竞态条件、锁竞争 |

### 4. 异常边界

| 场景 | 示例 |
|------|------|
| 正常异常 | 抛出预期异常 |
| 异常类型 | 错误的异常类型 |
| 异常消息 | 异常消息内容验证 |
| 异常链 | 原始异常传递 |

### 5. 外部依赖边界

| 场景 | 示例 |
|------|------|
| 网络超时 | 设置短超时 |
| 服务不可用 | Mock 外部服务 |
| 数据库连接失败 | 模拟连接错误 |
| 文件系统错误 | 权限不足、磁盘满 |

## 覆盖率策略

### 覆盖率指标

| 指标 | 说明 | 建议目标 |
|------|------|----------|
| **行覆盖率** | 执行的代码行数/总行数 | ≥80% |
| **分支覆盖率** | 条件分支覆盖情况 | ≥75% |
| **函数覆盖率** | 调用的函数/总函数 | ≥90% |
| **语句覆盖率** | 执行的语句数 | ≥85% |

### 覆盖率提升优先级

```
P0: 核心业务函数 → 必须 100%
P1: 公共工具函数 → 优先覆盖
P2: 边界情况处理 → 重要
P3: 错误处理逻辑 → 必要
P4: 辅助函数 → 适度覆盖
```

### 覆盖率陷阱

⚠️ **高覆盖率不等于高质量测试**

- 避免「测试通过但不验证结果」的假测试
- 避免「只测试简单路径」的水测试
- 关注**有意义的断言**，而非单纯追求数字

## 测试反模式

### ❌ 过度 Mock

```python
# 反模式：Mock 了所有东西，测试没有意义
def test_foo(mocker):
    mocker.patch("module.A", return_value=1)
    mocker.patch("module.B", return_value=2)
    mocker.patch("module.C", return_value=3)
    result = foo()
    assert result == 6  # 只测试了数学计算
```

### ❌ 测试脆弱

```python
# 反模式：依赖实现细节
def test_internal_state():
    obj = MyClass()
    obj._internal_cache = {"key": "value"}  # 依赖私有属性
    result = obj.get_cached("key")
    assert result == "value"
```

### ❌ 重复测试

```python
# 反模式：多个测试验证同一逻辑
def test_add_positive(): assert add(1, 2) == 3
def test_add_positive2(): assert add(1, 2) == 3  # 重复
def test_add_positive3(): assert add(1, 2) == 3  # 重复
```

### ✅ 好的测试实践

```python
# 正模式：清晰的测试意图
def test_division_by_zero_raises_error():
    """除以零应抛出 ZeroDivisionError"""
    with pytest.raises(ZeroDivisionError):
        divide(1, 0)

# 正模式：参数化测试覆盖多场景
@pytest.mark.parametrize("a,b,expected", [
    (1, 2, 3),
    (0, 0, 0),
    (-1, 1, 0),
])
def test_addition(a, b, expected):
    assert add(a, b) == expected
```

## pytest 最佳实践

### fixtures 使用

```python
@pytest.fixture
def user():
    """创建测试用户"""
    return User(name="test", email="test@example.com")

@pytest.fixture
def authenticated_client(client, user):
    """带认证的客户端"""
    client.force_login(user)
    return client

def test_profile_view(authenticated_client):
    response = authenticated_client.get("/profile/")
    assert response.status_code == 200
```

### 标记（Markers）

```python
@pytest.mark.slow      # 慢速测试
@pytest.mark.integration  # 集成测试
@pytest.mark.unit      # 单元测试
@pytest.mark.skip(reason="功能开发中")
@pytest.mark.xfail(reason="已知问题")
```

### 参数化

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("", ""),
])
def test_uppercase(input, expected):
    assert uppercase(input) == expected
```

## TDD 流程指导

```
1. 🔴 红：写一个会失败的测试
   └── 定义期望的行为

2. 🟢 绿：写最少的代码让测试通过
   └── 不考虑完美实现

3. ♻️ 重构：优化代码，测试保持通过
   └── 保持测试覆盖

重复以上步骤
```

## 常见测试框架对比

| 框架 | 语言 | 特点 | 适用场景 |
|------|------|------|----------|
| pytest | Python | 简洁、强大、插件丰富 | Python 项目 |
| unittest | Python | 标准库，无需安装 | 简单项目 |
| jest | JavaScript | 零配置、内置 Mock | React/Vue 项目 |
| vitest | JavaScript | Vite 原生支持，快 | Vite 项目 |
| go test | Go | 标准库，性能好 | Go 项目 |
| JUnit | Java | 企业级，稳定 | Java 项目 |