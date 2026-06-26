---
description: 为指定文件或函数自动生成测试用例骨架，支持多种测试框架和风格
type: prompt
parameters:
  - name: "--file="
    description: "目标文件路径（如 src/utils.py）"
    param_type: value
  - name: "--function="
    description: "指定函数名（可选，默认分析整个文件）"
    param_type: value
  - name: "--framework="
    description: "测试框架（pytest/jest/vitest/unittest）"
    param_type: value
  - name: "--style="
    description: "测试风格（unit/integration/e2e）"
    param_type: value
mutex_groups:
  scope: ["--function"]
---

# /test-scaffold:generate 命令 — 测试脚手架生成

你正在处理 `/test-scaffold:generate` 命令。根据用户指定的参数，自动生成测试用例骨架。

## 执行规则

1. **解析参数**：
   - `--file`（必填）：目标源文件路径
   - `--function`（可选）：指定函数名，默认为空则分析整个文件
   - `--framework`（默认 pytest）：测试框架
   - `--style`（默认 unit）：测试风格

2. **读取目标文件**，分析：
   - 函数签名和参数类型
   - 异常处理逻辑
   - 边界条件
   - 依赖的外部服务

3. **生成测试骨架**，遵循：
   - **unit 风格**：AAA 模式（Arrange-Act-Assert）
   - **integration 风格**：Given-When-Then 模式
   - **e2e 风格**：场景化测试，模拟用户操作

4. **输出位置**：在目标文件同目录下创建 `tests/` 目录，生成对应测试文件

## 测试框架映射

| 框架 | 文件后缀 | 导入语句 | 断言方式 |
|------|----------|----------|----------|
| pytest | `test_*.py` | `import pytest` | `assert` |
| unittest | `*_test.py` | `import unittest` | `self.assert*` |
| jest | `*.test.js` | `import { describe, it }` | `expect` |
| vitest | `*.test.js` | `import { describe, it } from 'vitest'` | `expect` |

## 单元测试骨架模板（pytest）

```python
import pytest
from pathlib import Path

# 导入待测试模块
# from src.utils import func_name


class TestClassName:
    """测试类：描述测试目标"""

    def setup_method(self):
        """每个测试前的准备工作"""
        pass

    def teardown_method(self):
        """每个测试后的清理工作"""
        pass

    def test_function_name_normal_case(self):
        """测试正常输入场景"""
        # Arrange
        input_data = ...

        # Act
        result = ...

        # Assert
        assert result == expected
```

## 集成测试骨架模板（pytest）

```python
import pytest

class TestFeatureName:
    """集成测试：验证多个组件协作"""

    def test_given_precondition_when_action_then_expectation(self):
        """场景描述：给定前提条件，当执行操作时期望结果"""
        # Given - 准备测试数据
        ...

        # When - 执行操作
        ...

        # Then - 验证结果
        ...
```

## 边界测试场景清单

生成测试时必须包含以下边界场景：

| 边界类型 | 测试内容 |
|----------|----------|
| 空值 | `None`、空字符串 `""`、空列表 `[]` |
| 零值 | `0`、空字典 `{}` |
| 边界数值 | 最大值、最小值、临界值 |
| 类型错误 | 传入错误类型参数 |
| 异常 | 模拟依赖服务失败 |
| 特殊字符 | Unicode、空白字符、SQL 注入尝试 |
| 并发 | 多线程/多进程同时调用 |
| 性能 | 大数据量输入、长运行时间 |

## 输出格式

生成完成后，输出：
1. 创建的测试文件路径
2. 包含的测试函数列表
3. 建议补充的边界测试场景
4. 下一步操作建议