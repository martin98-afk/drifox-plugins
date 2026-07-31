#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Demo：用 omml_utils 生成一个含各类 OMML 公式的 docx（模拟专利交底书场景）。

运行:
    python demo_build_docx.py            # 生成 demo_omml.docx
    python validate_omml.py demo_omml.docx   # 结构验证

本示例覆盖:
    行内公式（x_t、x̂_{t+1}、M_LLM、a^(k)）
    独立公式（Pareto 多目标评分 / 通过判据 / 综合目标 / 技能匹配）
    分数公式、求和 Σ、积分 ∫、括号、指示函数
    混合文本+公式段落
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from omml_utils import (  # noqa: E402
    I_chr, build_docx, formula_indicator_pass, formula_multi_target,
    formula_pareto_score, formula_skill_match, math_display, mdelim, mfrac,
    mhat, mixed_para, mnary, mnorm_par, msub, msub_sup, msup, mtext, msub_sup,
    para_text, sub_hat_math, sub_math, sup_math,
)


def build(out_path: str = "demo_omml.docx") -> str:
    body = []

    # ---- 标题 ----
    body.append(para_text("OMML 公式生成示例文档（专利交底书场景）", bold=True, sz=32, align="center"))
    body.append(para_text(""))

    # ---- 1. 行内公式 + 混合段落 ----
    body.append(para_text("1. 行内公式与混合段落", bold=True, sz=24))
    body.append(mixed_para([
        ("text", "当前工艺状态向量 "),
        ("math", sub_math("x", "t")),
        ("text", " 与工况指纹 "),
        ("math", sub_math("h", "t")),
        ("text", " 输入垂域大模型 "),
        ("math", sub_math("M", "L")),
        ("text", "，生成第 k 条候选策略 "),
        ("math", sup_math("a", "(k)")),
        ("text", "；机理模型预测下一时刻状态 "),
        ("math", sub_hat_math("x", "t+1")),
        ("text", "，残差 "),
        ("math", sub_math("r", "t")),
        ("text", " 的范数 "),
        ("math", mnorm_par(sub_math("r", "t"))),
        ("text", " 超过阈值时触发反思修正。"),
    ]))

    # ---- 2. 独立公式：Pareto 多目标评分 ----
    body.append(para_text("2. 独立公式：Pareto 多目标加权评分", bold=True, sz=24))
    body.append(math_display(formula_pareto_score()))

    # ---- 3. 独立公式：三层预验证通过判据（指示函数）----
    body.append(para_text("3. 三层预验证通过判据", bold=True, sz=24))
    body.append(math_display(formula_indicator_pass()))

    # ---- 4. 分数与导数 ----
    body.append(para_text("4. 分数公式", bold=True, sz=24))
    body.append(math_display(
        mfrac(mtext("∂x"), mtext("∂t")) + mtext(" = ") +
        mfrac(msub(mtext("F"), mtext("b")), msub(mtext("M"), mtext("s")))
    ))

    # ---- 5. 求和 Σ 与积分 ∫（标准 nary 结构）----
    body.append(para_text("5. 求和与积分（m:nary 标准结构）", bold=True, sz=24))
    body.append(math_display(
        mnary("∑", msub(mtext("m"), mtext("")) + mtext("=1"), mtext("K"),
              msub(mtext("ω"), mtext("m")) + mtext("·") + msub(mtext("J"), mtext("m")))
    ))
    body.append(math_display(
        mnary("∫", mtext("0"), mtext("∞"), mtext("f(t)") + mtext(" dt"))
    ))

    # ---- 6. 上下标同时 ----
    body.append(para_text("6. 上下标同时（sSubSup）与括号（d）", bold=True, sz=24))
    body.append(math_display(
        msub_sup(mtext("x"), mtext("t"), mtext("max")) + mtext(" ∈ ") +
        mdelim("[", mtext("0") + mtext(", ") + mtext("1"), "]")
    ))

    # ---- 7. 综合目标函数 ----
    body.append(para_text("7. 综合生成目标函数", bold=True, sz=24))
    body.append(math_display(formula_multi_target()))

    # ---- 8. 技能匹配函数 ----
    body.append(para_text("8. 技能匹配度函数", bold=True, sz=24))
    body.append(math_display(formula_skill_match()))

    # ---- 9. 指示函数说明 ----
    body.append(para_text("9. 指示函数记号", bold=True, sz=24))
    body.append(mixed_para([
        ("text", "指示函数 "),
        ("math", I_chr() + mdelim("[", mtext("条件成立"), "]")),
        ("text", " 在条件成立时取 1、否则取 0；hat 记号 "),
        ("math", mhat(mtext("x"))),
        ("text", " 表示预测值。"),
    ]))

    return build_docx("".join(body), out_path)


if __name__ == "__main__":
    print("生成:", build())
