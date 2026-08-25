---
name: omml-docx
description: "用 Python 脚本生成规范的 Word 数学公式（OMML / Office Math）并嵌入 .docx 文档。当用户需要在 Word 文档中插入数学公式时务必使用本技能——典型场景：专利技术交底书（权利要求公式、Pareto 评分、残差公式）、学术论文、技术报告、教材、任何含下标/上标/分数/求和/积分/矩阵公式的 docx 生成任务；当用户问'怎么用 Python 写 Word 公式'、'如何在 docx 里插入数学公式'、'OMML'、'docx 公式生成'、'批量生成带公式的文档'时使用。本技能提供直接可用的辅助函数库（scripts/omml_utils.py）与结构验证脚本（scripts/validate_omml.py），无需安装第三方库（仅标准库）。"
---

# OMML 公式 docx 生成

> 从专利交底书生成器 `build_jiaodishu(1).py` 提炼的通用能力：**用 Python 生成规范 OMML（Office Math Markup Language）公式并嵌入 .docx**。

## 核心原理（必须先理解，5 条铁律）

1. **docx 就是 zip 包**：`word/document.xml` 是正文。生成公式 = 往 document.xml 里写 `<m:oMath>`，再重新 zip。
2. **命名空间**：公式用 `m` 前缀，命名空间 `http://schemas.openxmlformats.org/officeDocument/2006/math`。`w:document` 根元素**必须声明** `xmlns:m`，否则公式无法解析。
3. **行内公式是 `<w:p>` 的直接子元素**：`<m:oMath>…</m:oMath>` 与 `<w:r>` 平级排列在 `<w:p>` 内。**绝不能把 `oMath` 塞进 `<w:r>` 内部**——Word 会打不开或公式不渲染。
4. **独立公式**（独占一行、默认居中）：**优先用行内公式** `<w:p><w:jc w:val="center"/><m:oMath>…</m:oMath></w:p>`。`<m:oMathPara>` 块级公式**在表格单元格中会渲染中断**——症状：公式只显示前半段（"只剩一半"），从 `<m:frac>`/`<m:nary>` 处丢失（2026-07 实测）。仅在**正文非表格段落**且已确认渲染正常时才用 `oMathPara`。
5. **兼容性三戒**（Word/WPS 实测）：① `<m:frac>` 分数、`<m:nary>` 求和/积分兼容性差——稳妥用「/ 斜线文本」「文本 Σ + 上下标」（`mnary_safe`）；② `m:rPr` 中**没有** `<m:b>` 元素，加粗必须用 `<m:sty m:val="b"/>`；③ 数学 run 的 `m:rPr` 内应内嵌 `<m:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/>`（注意是 m:rFonts 而非 w:rFonts；后者直接放在 `<m:r>` 内非法，Word 会忽略导致字体声明不生效）。
6. **文本节点分两套**：普通文本在 `<w:t>`（w 命名空间），公式文本在 `<m:t>`（m 命名空间），且 `<m:t>` 要带 `xml:space="preserve"` 保留空格。

## 快速开始

```bash
# 1. 直接跑示例（生成含 9 类公式的 demo_omml.docx + 结构验证）
python scripts/demo_build_docx.py
python scripts/validate_omml.py demo_omml.docx

# 2. 在自己脚本里使用辅助函数库
python -c "import sys; sys.path.insert(0, 'scripts'); import omml_utils"
```

### 方式 A：从零生成最小 docx（推荐先跑通）

```python
from omml_utils import para_text, mixed_para, sub_math, math_display, mfrac, mtext, build_docx

body = []
body.append(para_text("示例：状态向量", bold=True, sz=24))
# 行内公式（文本+公式混排）
body.append(mixed_para([
    ("text", "当前状态 "),
    ("math", sub_math("x", "t")),
    ("text", " 的预测值 "),
    ("math", sub_math("x", "t+1")),   # 注意：下标用 mtext 包字符串，下标内容为 t+1
    ("text", "。"),
]))
# 独立公式（独占一行居中）
body.append(math_display(mfrac(mtext("∂x"), mtext("∂t")) + mtext(" = 0")))
build_docx("".join(body), "out.docx")
```

### 方式 B：复用现有 docx 作为母版（保留样式/图片/页眉）

```python
build_docx(body_xml, "out.docx", template_docx="母版.docx")
# 内部逻辑：解压母版 → 仅替换 word/document.xml → 重新打包
```

## 辅助函数 API 速查（scripts/omml_utils.py）

### 文本层（w: 命名空间）
| 函数 | 说明 |
|------|------|
| `run(text, bold=, sz=, font=, italic=)` | 构造 `<w:r>`，支持 `\n` 换行 |
| `para(content_xml, align=, ind_first=, style=)` | 构造 `<w:p>`，包任意内部 XML |
| `para_text(text, **kw)` | 纯文本段落（无公式） |

### 公式层（m: 命名空间）
| 函数 | 生成结构 | 示例 |
|------|---------|------|
| `mtext(s)` | 普通数学 run | `mtext("x")` |
| `mit(s)` | 斜体数学 run（变量惯例） | `mit("x")` |
| `msub(base, sub)` | 下标 `<m:sSub>` | `msub(mtext("x"), mtext("t"))` → x_t |
| `msup(base, sup)` | 上标 `<m:sSup>` | `msup(mtext("a"), mtext("(k)"))` → a⁽ᵏ⁾ |
| `msub_sup(base, sub, sup)` | 上下标 `<m:sSubSup>` | x_t^max |
| `mfrac(num, den)` | 分数 `<m:frac>` | ∂x/∂t（**兼容性差，优先用 `mtext("A")+mtext(" / ")+mtext("B")`**） |
| `mdelim(open, content, close)` | 括号 `<m:d>` | `mdelim("(", a_k, ")")` |
| `mnary(op, sub, sup, content, lim_loc=)` | 求和/积分 `<m:nary>` | Σ、∫、Π（**兼容性差：算子字符可能丢失，优先用 `mnary_safe`**） |
| `mnary_safe(op, sub, sup, content)` | 文本算子+上下标（兼容版） | `msub_sup(mtext("Σ"), mtext("j=1"), mtext("N_a")) + …` |
| `mhat(var)` | 重音/顶帽 `<m:acc>` | x̂ |
| `mnorm_par(var)` | 双竖线范数 | ‖r_t‖ |
| `I_chr()` | 指示函数粗体 I（用 `m:sty b`，**不用非法的 `m:b`**） | I[条件] |

### 便捷组合器
| 函数 | 说明 |
|------|------|
| `sub_math(var, sub)` | `var_sub` 行内公式（var 自动正体） |
| `sup_math(var, sup)` | `var^sup` |
| `sub_sup_math(var, sub, sup)` | 上下标 |
| `sub_hat_math(var, sub)` | `x̂_sub`（hat + 下标） |

### 公式容器
| 函数 | 说明 |
|------|------|
| `math_inline(math_xml)` | `<m:oMath>`（**与 w:r 平级**，用于 mixed_para） |
| `math_display(math_xml, block=False)` | 独立公式段落，**默认行内 oMath 居中**（最稳）；`block=True` 才用 `<m:oMathPara>`（仅正文非表格） |
| `mixed_para([('text',…),('math',…)])` | 文本+公式混合段落（最常用） |

### 常用公式模板（借鉴专利交底书案例）
| 函数 | 公式 |
|------|------|
| `formula_pareto_score()` | A_pareto(a⁽ᵏ⁾) = Σ_{m∈{q,e,p,s}} ω_m·J_m(a⁽ᵏ⁾), Σω_m=1, ω_m≥0 |
| `formula_indicator_pass()` | I_pass(a⁽ᵏ⁾) = I[Viol_hard=0]·I[Viol_soft≤τ_soft]·I[A_pareto≥A_min] |
| `formula_multi_target()` | L_gen = λ_q·J_q + λ_e·J_e + λ_p·J_p + λ_s·J_s |
| `formula_skill_match()` | Match(h_t, SKILL_j) = cosine_sim(h_t, C_j)·I[‖h_t−C_j‖≤r_j]·S_j |

### 打包
| 函数 | 说明 |
|------|------|
| `build_docx(body_xml, out_path, template_docx=None, document_xml=None)` | body 内容 → .docx 文件。`template_docx` 复用母版；`document_xml` 自定义完整骨架 |

## 完整生成流程（推荐步骤）

1. **规划段落**：收集所有段落，区分「纯文本段」和「含公式混合段」。
2. **构造 body**：按文档顺序 `body.append(...)` 拼接 `<w:p>`。
   - 纯文本：`para_text(...)`
   - 混合：`mixed_para([('text', …), ('math', …), …])`
   - 独立公式：`math_display(...)`
3. **打包**：`build_docx("".join(body), out, template_docx=母版或None)`。
4. **验证**：`python scripts/validate_omml.py out.docx`（17 项结构检查，必须全 PASS）。
5. **人工复核**：用 Word/WPS 打开确认公式渲染正确。

## 常见坑（踩过的）

| 坑 | 现象 | 解决 |
|----|------|------|
| oMath 放进 w:r 内部 | Word 报"无法读取"或公式不渲染 | oMath 必须是 w:p 直接子元素，与 w:r 平级 |
| document.xml 缺 xmlns:m 声明 | 公式解析失败/打开报错 | 根元素加 `xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"` |
| m:t 未带 xml:space="preserve" | 公式内空格被吞（如 "a b" 变 "ab"） | m:t 加 `xml:space="preserve"` |
| 特殊字符未转义（& < >） | XML 解析失败 | 文本一律过 `esc()`（库内已自动处理） |
| 下标内容含运算符 | 显示错乱（如 t+1 整体是下标内容） | `msub(mtext("x"), mtext("t+1"))` —— 下标内容整个放 mtext 里 |
| **oMathPara 放在表格单元格** | **公式只显示前半段（从 frac/nary 处中断，"只剩一半"）** | **独立公式用行内 oMath + 居中段落（math_display 默认）；oMathPara 仅用于正文非表格** |
| **mfrac 内容不渲染** | **分数部分整体消失（尤其 oMathPara 中）** | **用 `mtext("A") + mtext(" / ") + mtext("B")` 斜线文本** |
| **mnary 算子丢失** | **∑/∫ 符号消失，只剩上下标** | **用 `mnary_safe`（文本 Σ + 上下标）** |
| **m:rPr 里写 m:b 加粗** | **该数学 run 渲染中断/异常** | **加粗用 `<m:sty m:val="b"/>`（OMML 无 m:b 元素）** |
| **数学 run 无字体声明** | **部分 Word/WPS 环境公式字体异常** | **m:rPr 内嵌 `<m:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/>`（库内已自动，m:rFonts 在 m:rPr 内，合规）** |
| 求和用下标模拟 Σ | 上下限不随算子缩放（不规范） | 用 `mnary("∑", …)` 标准结构；环境不兼容时用 `mnary_safe` |
| Windows 终端中文乱码 | 只是显示问题 | 脚本本身 UTF-8 正确；PowerShell 里 `chcp 65001` 或重定向到文件查看 |
| 直接改现有 docx 的 XML 字符串 | 极易破坏公式结构 | 走 build_docx（解压→替换→重打包），或从母版复用 |

## 大型文档建议（专利交底书/论文）

- **母版复用**：有样式/页眉/图片需求的，先解压母版 docx 作为模板（`template_docx=`），只重写 document.xml。
- **公式参数说明**：每个独立公式后紧跟"其中：……"参数说明段（变量含义、取值、单位），保证公开充分性——这是专利交底书的硬要求。
- **统一符号表**：文档末尾附"主要符号与参数说明"表，集中定义全部符号。
- **图片嵌入**：需要插图时在 document.xml.rels 注册图片关系（`rId` + `word/media/`），参考 OOXML 规范或复用母版已有关系。
- **分节**：body 最后必须保留 `<w:sectPr>`（页面设置），否则 Word 打开可能异常。

## 参考文件

- `references/omml-elements.md` — OMML 元素逐项详解（sSub/sSup/frac/d/nary/acc/bar/rad 等，含 XML 样例）
- `references/docx-packaging.md` — docx zip 结构与打包流水线详解（含图片嵌入、rels、Content_Types）

## 验证清单（交付前必跑）

- [ ] `python scripts/validate_omml.py <out.docx>` 全部 17 项 PASS（含 V10 非法 m:b 检测、V11 字体声明）
- [ ] Word/WPS 实际打开，公式渲染正确（行内不串行、独立公式居中、上下标/分数/求和显示正常）
- [ ] 含公式的段落中没有把 oMath 放进 w:r
- [ ] 若文档含**表格**：确认表格单元格内**没有 oMathPara**（用行内 oMath）；独立公式在表格内也走行内 oMath
- [ ] 若用了特殊 Unicode（如 ‖、̂、Σ、∫），确认目标字体支持
