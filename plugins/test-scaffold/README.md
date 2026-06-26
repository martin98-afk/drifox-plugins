# test-scaffold — 测试脚手架插件

DriFox 的测试脚手架生成插件，自动为代码生成测试用例骨架、分析覆盖率缺口、推荐边界测试场景，加速测试驱动开发（TDD）流程。

## 功能

| 功能 | 说明 |
|------|------|
| 📝 **测试骨架生成** | `/test-scaffold:generate` 自动为源文件/函数生成测试用例模板 |
| 📊 **覆盖率分析** | `/test-scaffold:coverage` 分析项目测试覆盖缺口，识别高风险模块 |
| 🎯 **边界场景推荐** | 自动识别需要补充的边界测试用例 |
| 🛠️ **多框架支持** | 支持 pytest、unittest、jest、vitest 等主流测试框架 |
| 📐 **多种测试风格** | 支持单元测试、集成测试、端到端测试 |

## 安装

插件位于 `~/.drifox/plugins/test-scaffold/`，DriFox 启动时自动发现并加载。

## 使用方法

### 生成测试骨架

```bash
/test-scaffold:generate --file=src/utils.py --framework=pytest --style=unit
```

参数说明：
- `--file`：目标源文件路径（必填）
- `--function`：指定函数名（可选）
- `--framework`：测试框架（默认 pytest）
- `--style`：测试风格（默认 unit）

### 分析覆盖率

```bash
/test-scaffold:coverage --min=80 --format=table
```

参数说明：
- `--min`：最低覆盖率阈值（默认 80%）
- `--format`：输出格式（table/json/markdown）
- `--ignore`：忽略的目录或文件

## 支持的测试框架

| 框架 | 文件后缀 | 断言方式 |
|------|----------|----------|
| pytest | `test_*.py` | `assert` |
| unittest | `*_test.py` | `self.assert*` |
| jest | `*.test.js` | `expect` |
| vitest | `*.test.js` | `expect` |

## 测试风格

### 单元测试（unit）

使用 AAA 模式（Arrange-Act-Assert），适合独立函数的测试。

### 集成测试（integration）

使用 Given-When-Then 模式，适合验证模块间协作。

### 端到端测试（e2e）

场景化测试，模拟真实用户操作流程。

## 示例

### 生成单元测试

```bash
/test-scaffold:generate --file=src/calculator.py --framework=pytest --style=unit
```

输出：
```python
# tests/test_calculator.py
import pytest
from src.calculator import add, subtract, multiply, divide


class TestCalculator:
    def test_add_normal_case(self):
        # Arrange
        a, b = 1, 2
        # Act
        result = add(a, b)
        # Assert
        assert result == 3
```

### 分析覆盖率

```bash
/test-scaffold:coverage --min=80
```

输出：
```
# 测试覆盖率报告

## 📊 总体统计
| 指标 | 值 |
|------|-----|
| 源文件总数 | 15 |
| 有测试的文件 | 10 |
| 覆盖率 | 67% |
| 缺口模块数 | 5 |

## ⚠️ 高优先级缺口
1. src/core/engine.py - 核心引擎无测试
2. src/api/routes.py - API 路由未完全覆盖
```

## 工作原理

```
源代码
  │  (/test-scaffold:generate)
  ▼
AST 解析 → 分析函数签名、依赖、异常
  │
  ▼
测试骨架生成
  │
  ├─► 单元测试模板（AAA 模式）
  ├─► 集成测试模板（Given-When-Then）
  ├─► 边界场景清单
  └─► 覆盖率分析建议
```

## 相关插件

- [evolver](../evolver/) — Evolver 自进化引擎，可与 test-scaffold 结合实现测试驱动进化
- [example-plugin](../example-plugin/) — 插件开发参考，了解更多插件规范