---
name: python-pro
description: Python 开发最佳实践技能 — 当涉及 PEP 8 规范、类型标注（type hints）、async/await 异步编程、ruff/mypy lint 配置、虚拟环境管理、依赖管理（pip/poetry/uv）等话题时触发。
---

# python-pro 技能 — Python 开发最佳实践

本技能为 AI 提供 Python 开发的权威规范与最佳实践参考，确保生成的代码符合 Python 社区标准。

## PEP 8 代码风格要点

### 布局与缩进

- **缩进**：4 空格（不用 Tab）
- **行宽**：最大 79 字符（单行）
- **空行**：顶级定义（函数/类）之间 2 空行，方法之间 1 空行
- **import 顺序**：标准库 → 第三方 → 本地，相邻分组之间不留空行

```python
# ✅ 正确
import os
import sys

import third_party_lib
from mypackage import MyClass

# ❌ 错误
import sys, os
from mypackage import *
```

### 命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| 变量/函数 | snake_case | `def get_user_name()` |
| 类 | PascalCase | `class UserProfile:` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT = 3` |
| 私有属性 | `_leading_underscore` | `self._cache = {}` |

### 字符串与表达式

- 单引号和双引号等价，团队内保持一致即可
- 在 docstring 中使用 `"""三引号"""`，避免无意义 docstring
- 不要在字符串中使用不必要的 `{}.format()`，优先用 f-string（Python 3.6+）

## 类型标注（Type Hints）规范

### 基本用法

```python
# ✅ 推荐：完整标注
def greet(name: str, times: int = 1) -> str:
    return f"Hello, {name}!" * times

# ✅ 可选类型
from typing import Optional, List, Dict

def find_user(user_id: int) -> Optional[str]:
    ...

def process_items(items: List[int]) -> Dict[str, int]:
    ...
```

### 现代写法（Python 3.10+）

```python
# ✅ 使用内置容器类型（无需 from typing 导入）
def process_items(items: list[int]) -> dict[str, int]:
    ...

# ✅ 联合类型用 | 代替 Union / Optional
def parse(value: str | int | float) -> str | None:
    ...
```

### 类型别名的推荐做法

```python
# ✅ 使用 TypeAlias（Python 3.10+）
from typing import TypeAlias

UserId: TypeAlias = int
Result: TypeAlias = dict[str, Any]
```

### mypy 配置建议

在 `pyproject.toml` 中配置：

```toml
[tool.mypy]
python_version = "3.10"
strict = true           # 开启严格模式
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

## async / await 异步编程最佳实践

### 基础原则

```python
# ✅ 正确：使用 async def 定义协程
async def fetch_data(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.read()

# ❌ 错误：混用同步和异步
def fetch_data(url: str) -> bytes:
    response = requests.get(url)  # 同步调用在 async 函数中
    return response.content
```

### 异步上下文管理

```python
# ✅ 正确
async with asyncio.Lock() as lock:
    async with db.connection() as conn:
        ...

# ❌ 错误：不要在 async with 外部使用 await
lock = asyncio.Lock()
await lock.acquire()   # 不要这样做
```

### 常见陷阱

1. **不要在同步函数中调用 async 函数**：会导致死锁
2. **避免顺序 await**：改用 `asyncio.gather()` 并发执行
3. **妥善关闭资源**：使用 `async with` 或 `try/finally` 确保清理
4. **不要吞掉异常**：异步函数中的异常需要正确传播

```python
# ✅ 并发执行
import asyncio

async def main():
    results = await asyncio.gather(
        fetch_data(url1),
        fetch_data(url2),
        fetch_data(url3),
    )
    return results
```

## ruff / lint 配置建议

ruff 是目前最快的 Python linter，推荐使用。在 `pyproject.toml` 中配置：

```toml
[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]
ignore = [
    "E501",  # 行太长（由 formatter 处理）
]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]  # __init__ 中允许未使用导入
```

## 常见 Python 反模式

| 反模式 | 问题 | 正确做法 |
|--------|------|----------|
| `from module import *` | 命名空间污染 | 显式导入具体名称 |
| 空 `except:` 子句 | 吞掉所有异常 | `except SomeError as e:` |
| 使用可变默认参数 | 闭包陷阱 | `def f(x=None): if x is None: x = []` |
| `==` 比较 True | 类型不安全 | `if x is True:` 或 `if x:` |
| 列表拼接字符串 | O(n²) 复杂度 | 用 `str.join()` 或 f-string |
| 忽略下划线变量 | 代码可读性差 | 用 `_` 表示废弃值 |

## 依赖管理

### pip（标准方式）

```bash
# 安装依赖
pip install requests

# 冻结依赖
pip freeze > requirements.txt

# 从文件安装
pip install -r requirements.txt
```

### uv（推荐，跨平台）

```bash
# 安装 uv（如果未安装）
pip install uv

# 创建虚拟环境并安装依赖
uv venv .venv
uv pip install -r requirements.txt

# 快速添加依赖
uv add requests
uv add --dev pytest
```

### poetry（项目级管理）

```bash
# 初始化项目
poetry init

# 添加依赖
poetry add requests
poetry add --group dev pytest

# 安装（读取 pyproject.toml）
poetry install

# 锁定并安装
poetry lock && poetry install
```

### 虚拟环境隔离原则

- **每个项目独立虚拟环境**，不要混用
- `.gitignore` 中添加 `.venv/`、`__pycache__/`、`.pytest_cache/`
- 不提交 `requirements.txt`（改用 `requirements-dev.txt` 分环境管理）

## 快速参考

生成 Python 代码时的检查清单：

- [ ] 遵循 PEP 8 命名约定（函数 snake_case、类 PascalCase）
- [ ] 函数有类型标注（参数 + 返回值）
- [ ] 异步函数正确使用 async/await，不混用同步调用
- [ ] 使用 ruff 进行 lint 检查，配置合理的 ignore 规则
- [ ] 依赖放入虚拟环境，不污染全局 Python
- [ ] 避免常见反模式（空 except、可变默认参数等）