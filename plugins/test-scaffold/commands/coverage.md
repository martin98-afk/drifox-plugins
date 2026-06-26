---
description: 分析项目测试覆盖缺口，推荐需要优先补充测试的模块和场景
type: prompt
parameters:
  - name: "--min="
    description: "最低覆盖率阈值（默认 80）"
    param_type: value
  - name: "--format="
    description: "输出格式（table/json/markdown）"
    param_type: value
  - name: "--ignore="
    description: "忽略的目录或文件（逗号分隔）"
    param_type: value
---

# /test-scaffold:coverage 命令 — 覆盖率分析

你正在处理 `/test-scaffold:coverage` 命令。分析项目测试覆盖情况，识别测试缺口。

## 执行规则

1. **扫描项目结构**：
   - 识别源代码目录（`src/`、`lib/`、`app/` 等）
   - 识别现有测试目录（`tests/`、`test/`、`__tests__/` 等）
   - 匹配源文件与对应测试文件

2. **覆盖率分析**：
   - 检查哪些源文件缺少测试文件
   - 检查哪些函数/类缺少测试覆盖
   - 识别低覆盖率模块

3. **风险评估**：
   - 高风险：核心业务逻辑无测试
   - 中风险：辅助功能无测试
   - 低风险：工具类无测试

4. **输出覆盖率报告**

## 覆盖率优先级矩阵

| 优先级 | 模块类型 | 建议覆盖率 | 原因 |
|--------|----------|------------|------|
| P0 | 核心业务逻辑 | ≥90% | 直接影响产品功能 |
| P1 | API/接口层 | ≥80% | 外部依赖稳定性 |
| P2 | 数据处理 | ≥80% | 数据一致性 |
| P3 | 工具函数 | ≥70% | 辅助功能 |
| P4 | UI/展示层 | ≥50% | 变化频繁 |

## 覆盖率报告模板

```markdown
# 测试覆盖率报告

生成时间：{timestamp}
最低阈值：{threshold}%

## 📊 总体统计

| 指标 | 值 |
|------|-----|
| 源文件总数 | X |
| 有测试的文件 | X |
| 覆盖率 | XX% |
| 缺口模块数 | X |

## 📁 模块详情

| 模块 | 覆盖率 | 测试数 | 缺口函数 | 优先级 |
|------|--------|--------|----------|--------|
| src/core/ | 85% | 12 | func_a | P1 |
| src/utils/ | 60% | 3 | func_b, func_c | P3 |

## ⚠️ 高优先级缺口

1. **src/core/engine.py** - 核心引擎无测试
   - 缺失函数：`process()`, `validate()`
   - 建议：优先补充

2. **src/api/routes.py** - API 路由未完全覆盖
   - 缺失端点：`/api/v1/users`
   - 建议：补充集成测试
```

## JSON 输出格式

```json
{
  "timestamp": "2024-01-01T00:00:00Z",
  "threshold": 80,
  "summary": {
    "total_files": 10,
    "tested_files": 7,
    "coverage_percent": 70,
    "gaps": 3
  },
  "modules": [
    {
      "path": "src/core/engine.py",
      "coverage": 0,
      "priority": "P0",
      "missing_functions": ["process", "validate"]
    }
  ]
}
```

## 推荐的测试补充顺序

1. **先核心后边缘**：优先测试核心业务逻辑
2. **先高频后低频**：优先测试常用模块
3. **先简单后复杂**：先补充简单函数的测试
4. **先修复后新增**：先修复已知 bug 的测试，再补充新功能测试

## 下一步建议

分析完成后，提供：
1. 最需要补充测试的模块列表（前 5 个）
2. 每个模块的具体测试建议
3. 快速提升覆盖率的技巧