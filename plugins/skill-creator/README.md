# Skill Creator

> 原插件：Anthropic 官方 [skill-creator](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator)（MIT）

**Skill Creator** 是一套创建、优化、评测 AI 技能（skill）的完整方法论。当需要从零写一个技能、改进既有技能、或评估技能性能时自动激活。

## 能力

- **创建技能**：从目标出发，起草 → 迭代 → 验证的完整流程
- **改进技能**：分析现有技能短板，优化触发描述与内容结构
- **评测性能**：内置 `scripts/run_eval.py` 等评测脚本，做基准测试（benchmark）
- **描述优化**：`scripts/improve_description.py` 优化触发准确率
- **打包校验**：`scripts/package_skill.py`、`scripts/quick_validate.py`

## 目录结构

```
skills/skill-creator/
├── SKILL.md              # 主技能（触发入口）
├── agents/                # analyzer / comparator / grader 子智能体
├── scripts/               # 评测与基准脚本
├── references/schemas.md  # 技能架构参考
├── assets/ + eval-viewer/ # 评测报告可视化
```

## 适配说明

与上游一致，零改动。技能格式遵循 DriFox `skills/<name>/SKILL.md` 约定。

## 许可证

MIT（与上游一致）。