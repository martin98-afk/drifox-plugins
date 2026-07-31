# omml-docx

用 Python 生成规范的 **Word 数学公式（OMML / Office Math）** 并嵌入 `.docx` 文档。

> 源自《一种大小模型协同的垂域大模型工艺参数精准控制优化方法》专利交底书生成器 `build_jiaodishu(1).py` 的通用化提炼。

## 功能

- **OMML 辅助函数库** `skills/omml-docx/scripts/omml_utils.py`
  - 行内公式（`m:oMath` 与 `w:r` 平级混排）、独立公式（`m:oMathPara` 居中）
  - 下标/上标/上下标同时/分数/括号/求和 Σ/积分 ∫/重音 hat/范数/指示函数
  - 文本+公式混合段落、常用公式模板（Pareto 评分、通过判据、综合目标、技能匹配）
  - docx 打包：从零生成 或 复用母版（保留样式/图片/页眉）
  - **纯标准库，零第三方依赖**
- **结构验证脚本** `skills/omml-docx/scripts/validate_omml.py`
  - 15 项检查：zip 完整性、XML 良构、m 命名空间、公式数量、oMath 位置、各结构元素、xml:space、w:t/m:t 分离
- **参考文档** `skills/omml-docx/references/`
  - `omml-elements.md` — OMML 元素逐项详解（含可复制 XML 片段）
  - `docx-packaging.md` — docx zip 结构与打包流水线（含图片嵌入、表格混合）

## 快速开始

```bash
cd skills/omml-docx/scripts
python demo_build_docx.py              # 生成 demo_omml.docx（9 类公式示例）
python validate_omml.py demo_omml.docx # 15 项结构验证
```

在自己的脚本中使用：

```python
import sys; sys.path.insert(0, "skills/omml-docx/scripts")
from omml_utils import para_text, mixed_para, sub_math, math_display, mfrac, mtext, build_docx

body = [para_text("示例", bold=True)]
body.append(mixed_para([("text", "状态 "), ("math", sub_math("x", "t")), ("text", "。")]))
body.append(math_display(mfrac(mtext("∂x"), mtext("∂t")) + mtext(" = 0")))
build_docx("".join(body), "out.docx")
```

## 目录结构

```
omml-docx/
├── .drifox-plugin/plugin.json     ← 插件 manifest（skills: true）
└── skills/
    └── omml-docx/
        ├── SKILL.md               ← 技能主文档（OMML 铁律 + API + 常见坑）
        ├── scripts/
        │   ├── omml_utils.py      ← OMML 辅助函数库
        │   ├── demo_build_docx.py ← 示例生成脚本
        │   └── validate_omml.py   ← 结构验证（15 项）
        └── references/
            ├── omml-elements.md   ← OMML 元素参考
            └── docx-packaging.md  ← docx 打包流水线
```

## 适用场景

- 专利技术交底书（权利要求公式、Pareto 评分、残差公式、符号表）
- 学术论文 / 技术报告 / 教材中的数学公式
- 批量生成带公式的 Word 文档

## License

MIT
