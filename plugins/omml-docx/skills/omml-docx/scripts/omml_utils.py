#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OMML 辅助函数库 — 用 Python 生成规范的 Word (OMML) 数学公式并嵌入 docx。

从《一种大小模型协同的垂域大模型工艺参数精准控制优化方法》专利交底书
生成脚本 build_jiaodishu(1).py 提炼、通用化而成。

核心事实
--------
* OMML = Office Math Markup Language，命名空间:
  ``http://schemas.openxmlformats.org/officeDocument/2006/math``（前缀 m）
* 行内公式 ``<m:oMath>`` 是 ``<w:p>`` 的**直接子元素**，与 ``<w:r>`` 平级——
  绝不能把 oMath 塞进 w:r 内部，否则 Word 打不开或公式不渲染。
* 独立公式用 ``<m:oMathPara>`` 包裹 ``<m:oMath>``，整段居中显示。
* **兼容性铁律（2026-07 专利交底书实测）**：
  - 行内 ``<m:oMath>``（与 ``<w:r>`` 平级）渲染最稳；**独立公式也用「行内 oMath + 居中段落」**（``math_display`` 默认即此）。
  - ``<m:oMathPara>`` 块级公式在**表格单元格**中会渲染中断——症状：公式只显示前半段（"只剩一半"），从 ``<m:frac>/<m:nary>`` 处丢失。
  - ``<m:frac>``（分数）、``<m:nary>``（求和/积分）兼容性差：稳妥方案是「/ 斜线文本」与「文本 Σ + 上下标」。
  - ``m:rPr`` 中**没有** ``<m:b>`` 元素——加粗必须用 ``<m:sty m:val="b"/>``（``<m:b>`` 会导致该数学 run 渲染中断）。
  - 数学 run（``m:r``）内嵌 ``<w:rPr><w:rFonts w:ascii="Cambria Math" .../>`` 与 Word 原生公式一致。
* docx 就是 zip 包：改 ``word/document.xml`` 后重新 zip 即可。

典型用法
--------
>>> from omml_utils import mixed_para, msub, mtext, math_display, para_text, build_docx
>>> body = []
>>> body.append(para_text('混合文本示例：'))
>>> body.append(mixed_para([('text', '当前状态向量 '), ('math', msub(mtext('x'), mtext('t'))), ('text', ' 已更新。')]))
>>> body.append(math_display(msub(mtext('Σ'), mtext('m')) + mtext(' ω') + msub(mtext('m'), mtext(''))) )  # 独立公式
>>> build_docx(''.join(body), out_path='out.docx')
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 命名空间常量
# ---------------------------------------------------------------------------
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"

# ---------------------------------------------------------------------------
# XML 转义
# ---------------------------------------------------------------------------
def esc(s: str) -> str:
    """XML 文本转义（& < >；引号仅在属性里需要，文本节点不必转）。"""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


#: 数学 run 的字体声明（Word 原生公式写法：m:r 内嵌 w:rPr 指定 Cambria Math）
MATH_FONT = '<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/></w:rPr>'


# ---------------------------------------------------------------------------
# 文本段落辅助（w:r / w:p）
# ---------------------------------------------------------------------------
def run(text: str, *, bold: bool = False, sz: int | None = None,
        font: str = "宋体", italic: bool = False) -> str:
    """构造一个 <w:r> 文本 run。支持 \\n 换行（拆成多个 run + w:br）。"""
    rpr_parts = [
        f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:eastAsia="{font}"/>',
        f'<w:b w:val="1"/>' if bold else '<w:b w:val="0"/>',
    ]
    if italic:
        rpr_parts.append('<w:i w:val="1"/>')
    if sz is not None:
        rpr_parts.append(f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>')
    rpr = "<w:rPr>" + "".join(rpr_parts) + "</w:rPr>"
    runs = []
    for k, seg in enumerate(text.split("\n")):
        if k > 0:
            runs.append("<w:r><w:br/></w:r>")
        if seg:
            runs.append(f'<w:r>{rpr}<w:t xml:space="preserve">{esc(seg)}</w:t></w:r>')
    return "".join(runs)


def para(content_xml: str, *, align: str | None = None,
         ind_first: int | None = None, style: str | None = None) -> str:
    """构造 <w:p> 段落，包裹一段内部 XML（run / oMath 均可）。"""
    ppr = []
    if style:
        ppr.append(f'<w:pStyle w:val="{style}"/>')
    if align:
        ppr.append(f'<w:jc w:val="{align}"/>')
    if ind_first is not None:
        ppr.append(f'<w:ind w:firstLine="{ind_first}"/>')
    ppr_xml = ("<w:pPr>" + "".join(ppr) + "</w:pPr>") if ppr else ""
    return f"<w:p>{ppr_xml}{content_xml}</w:p>"


def para_text(text: str, **kw) -> str:
    """纯文本段落（无公式）。kw 透传给 run()/para()。"""
    bold = kw.pop("bold", False)
    sz = kw.pop("sz", 21)
    font = kw.pop("font", "宋体")
    italic = kw.pop("italic", False)
    return para(run(text, bold=bold, sz=sz, font=font, italic=italic), **kw)


# ---------------------------------------------------------------------------
# OMML 基础元素
# ---------------------------------------------------------------------------
def mtext(s: str) -> str:
    """数学 run（普通正体）：<m:r><m:rPr><m:sty m:val='p'/>…</m:rPr><m:t>…</m:t></m:r>"""
    return (f'<m:r><m:rPr><m:sty m:val="p"/></m:rPr>{MATH_FONT}'
            f'<m:t xml:space="preserve">{esc(s)}</m:t></m:r>')


def mit(s: str) -> str:
    """数学 run（斜体，变量惯例）：<m:r><m:rPr><m:sty m:val='i'/><m:i m:val='1'/></m:rPr>…</m:r>"""
    return (f'<m:r><m:rPr><m:sty m:val="i"/><m:i m:val="1"/></m:rPr>{MATH_FONT}'
            f'<m:t xml:space="preserve">{esc(s)}</m:t></m:r>')


def msub(base: str, sub: str) -> str:
    """下标：<m:sSub><m:e>基</m:e><m:sub>下标</m:sub></m:sSub>"""
    return f"<m:sSub><m:e>{base}</m:e><m:sub>{sub}</m:sub></m:sSub>"


def msup(base: str, sup: str) -> str:
    """上标：<m:sSup><m:e>基</m:e><m:sup>上标</m:sup></m:sSup>"""
    return f"<m:sSup><m:e>{base}</m:e><m:sup>{sup}</m:sup></m:sSup>"


def msub_sup(base: str, sub: str, sup: str) -> str:
    """上下标同时：<m:sSubSup><m:e>基</m:e><m:sub>下</m:sub><m:sup>上</m:sup></m:sSubSup>"""
    return (f"<m:sSubSup><m:e>{base}</m:e>"
            f"<m:sub>{sub}</m:sub><m:sup>{sup}</m:sup></m:sSubSup>")


def mfrac(num: str, den: str) -> str:
    """分数：<m:frac><m:num>分子</m:num><m:den>分母</m:den></m:frac>

    兼容性注意（2026-07 实测）：<m:frac> 在部分 Word/WPS 环境中内容可能不渲染
    （尤其位于 <m:oMathPara> 块级公式中时）。**稳妥方案**：用斜线文本替代——
    ``mtext("|A|") + mtext(" / ") + mtext("|B|")``。
    在行内 <m:oMath> 中可渲染，但交付前务必用 Word/WPS 复核。
    """
    return f"<m:frac><m:num>{num}</m:num><m:den>{den}</m:den></m:frac>"


def mdelim(open_: str, content: str, close: str) -> str:
    """带定界符的括号结构：<m:d><m:dPr><m:begChr/><m:endChr/></m:dPr><m:e>内容</m:e></m:d>"""
    return (f'<m:d><m:dPr><m:begChr m:val="{esc(open_)}"/>'
            f'<m:endChr m:val="{esc(close)}"/></m:dPr>'
            f"<m:e>{content}</m:e></m:d>")


def mnary(operator: str, sub: str | None, sup: str | None, content: str,
          lim_loc: str = "undOvr") -> str:
    """n-ary 算子（求和 Σ / 积分 ∫ / 连乘 Π）。

    <m:nary>
      <m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="undOvr"/></m:naryPr>
      <m:sub>…</m:sub><m:sup>…</m:sup><m:e>…</m:e>
    </m:nary>
    lim_loc: undOvr（上下限在算子上下）/ subSup（右下右上）
    """
    pr = f'<m:naryPr><m:chr m:val="{esc(operator)}"/><m:limLoc m:val="{lim_loc}"/></m:naryPr>'
    sub_x = f"<m:sub>{sub}</m:sub>" if sub else "<m:sub/>"
    sup_x = f"<m:sup>{sup}</m:sup>" if sup else "<m:sup/>"
    return f"<m:nary>{pr}{sub_x}{sup_x}<m:e>{content}</m:e></m:nary>"


def mnary_safe(operator: str, sub: str, sup: str, content: str) -> str:
    """兼容版求和/积分：文本算子 + 上下标（替代 <m:nary>）。

    适用场景：目标环境对 <m:nary> 渲染不佳（算子字符丢失、只剩上下标）时使用。
    例：Σ_{j=1}^{N_a} → msub_sup(mtext("Σ"), mtext("j=1"), mtext("N_a")) + content
    """
    return msub_sup(mtext(operator), mtext(sub), mtext(sup)) + content


def mhat(var: str) -> str:
    """重音（hat / 顶帽）：<m:acc><m:accPr><m:chr m:val='̂'/></m:accPr><m:e>基</m:e></m:acc>

    m:chr 的 val 是 U+0302 COMBINING CIRCUMFLEX ACCENT，表示帽子加在基之上。
    """
    return ('<m:acc><m:accPr><m:chr m:val="\u0302"/></m:accPr>'
            f"<m:e>{var}</m:e></m:acc>")


def mnorm_par(var: str) -> str:
    """双竖线范数：‖var‖"""
    return mtext("‖") + var + mtext("‖")


def I_chr() -> str:
    """指示函数记号：粗体 I。

    注意：OMML 的 m:rPr 中**没有** <m:b> 元素——加粗必须用
    <m:sty m:val="b"/>（<m:b> 在部分 Word/WPS 中会导致该数学 run 渲染中断）。
    """
    return (f'<m:r><m:rPr><m:sty m:val="b"/></m:rPr>{MATH_FONT}'
            '<m:t xml:space="preserve">I</m:t></m:r>')


# ---------------------------------------------------------------------------
# 公式容器：行内 / 独立
# ---------------------------------------------------------------------------
def math_inline(math_xml: str) -> str:
    """行内公式：<m:oMath>…</m:oMath>（作为 w:p 直接子元素，与 w:r 平级）"""
    return f"<m:oMath>{math_xml}</m:oMath>"


def math_display(math_xml: str, *, align: str = "center", block: bool = False) -> str:
    """独立公式段落（独占一行，默认居中）。

    兼容性铁律：**默认（block=False）用行内 <m:oMath> + 居中段落**——
    <m:oMathPara> 块级公式在**表格单元格**中会渲染中断（症状：公式只显示
    前半段"只剩一半"，从 <m:frac>/<m:nary> 处丢失）。行内 oMath 渲染最稳。

    block=True 时生成 <m:oMathPara>（仅当公式位于**正文非表格段落**且
    已在目标 Word/WPS 确认渲染正常时使用）。
    """
    if block:
        body = f"<m:oMathPara><m:oMath>{math_xml}</m:oMath></m:oMathPara>"
        return para(body, align=align)
    return para(f"<m:oMath>{math_xml}</m:oMath>", align=align)


def mixed_para(segments: list, **kw) -> str:
    """文本 + 行内公式混合段落。

    segments: [('text', str) | ('math', omml_xml) | ('math', ('key', …)), ...]
    其中 ('math', …) 的第二个元素可以是 OMML XML 字符串，或可调用对象/预置键。

    示例:
        mixed_para([('text', '状态向量 '),
                    ('math', msub(mtext('x'), mtext('t'))),
                    ('text', ' 的预测值为 '),
                    ('math', mhat(msub(mtext('x'), mtext('t+1'))))])
    """
    xml_parts = []
    for seg_type, content in segments:
        if seg_type == "text":
            xml_parts.append(run(content, **kw))
        elif seg_type == "math":
            xml_parts.append(math_inline(content))
        else:
            raise ValueError(f"未知段类型: {seg_type!r}")
    return para("".join(xml_parts), **kw)


# ---------------------------------------------------------------------------
# 便捷组合器：常用变量（下标/上标/重音）快速构造
# ---------------------------------------------------------------------------
def sub_math(var: str, sub: str) -> str:
    """var_sub 行内公式"""
    return msub(mtext(var), mtext(sub))


def sup_math(var: str, sup: str) -> str:
    """var^sup 行内公式"""
    return msup(mtext(var), mtext(sup))


def sub_sup_math(var: str, sub: str, sup: str) -> str:
    return msub_sup(mtext(var), mtext(sub), mtext(sup))


def sub_hat_math(var: str, sub: str) -> str:
    """x̂_sub（带 hat 的下标变量）"""
    return msub(mhat(mtext(var)), mtext(sub))


# ---------------------------------------------------------------------------
# docx 打包：把 document.xml 组装成 .docx
# ---------------------------------------------------------------------------
#: 标准 document.xml 骨架（含 m 命名空间；有模板时用模板的，勿用此默认）
DOCUMENT_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:r="{r}" xmlns:m="{m}" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" mc:Ignorable="w14 w15 wp14">
<w:body>
{body}
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="851" w:footer="992" w:gutter="0"/><w:cols w:space="425"/><w:docGrid w:type="lines" w:linePitch="312"/></w:sectPr>
</w:body>
</w:document>"""

MINIMAL_DOCX_PARTS = {
    "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>""",
    "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
    "word/_rels/document.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
    "word/styles.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:rPr><w:rFonts w:ascii="宋体" w:hAnsi="宋体" w:eastAsia="宋体"/><w:sz w:val="21"/></w:rPr></w:style>
</w:styles>""",
}


def build_docx(body_xml: str, out_path: str,
               template_docx: str | None = None,
               document_xml: str | None = None) -> str:
    """把 body 内容组装成 .docx 文件。

    body_xml: 若干 <w:p> / <w:tbl> 拼接的字符串。
    out_path: 输出 .docx 路径。
    template_docx: 可选——复用现有 docx 作为母版（保留 styles/theme/图片等）。
                   传入后仅替换其中的 word/document.xml 为新的（body 外包骨架）。
    document_xml: 可选——完整 document.xml（含 w:document 根 + sectPr）。
                  不传则用 DOCUMENT_XML_TEMPLATE 骨架包裹 body_xml。
    """
    import os
    import shutil
    import tempfile
    import zipfile
    from pathlib import Path

    if document_xml is None:
        document_xml = DOCUMENT_XML_TEMPLATE.format(
            body=body_xml, r=R, m=M)

    out_path = str(out_path)
    if template_docx and os.path.exists(template_docx):
        # 复用母版：解压 → 换 document.xml → 重打包
        work = Path(tempfile.mkdtemp(prefix="omml_build_"))
        try:
            with zipfile.ZipFile(template_docx) as zf:
                zf.extractall(work)
            (work / "word" / "document.xml").write_text(document_xml, encoding="utf-8")
            if os.path.exists(out_path):
                os.remove(out_path)
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _dirs, files in os.walk(work):
                    for f in files:
                        full = Path(root) / f
                        zf.write(full, str(full.relative_to(work)).replace("\\", "/"))
        finally:
            shutil.rmtree(work, ignore_errors=True)
    else:
        # 从零构建最小 docx
        parts = dict(MINIMAL_DOCX_PARTS)
        parts["word/document.xml"] = document_xml
        if os.path.exists(out_path):
            os.remove(out_path)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in parts.items():
                zf.writestr(name, content)
    return out_path


# ---------------------------------------------------------------------------
# 常用公式模板（借鉴专利交底书案例，可扩展）
# ---------------------------------------------------------------------------
def formula_pareto_score(base: str = "A", sub: str = "pareto",
                         index_set: str = "m∈{q,e,p,s}",
                         target: str = "J") -> str:
    """A_pareto(a^(k)) = Σ_{m∈{q,e,p,s}} ω_m · J_m(a^(k))

    专利案例：多目标加权评分公式。
    """
    a_k = msup(mtext("a"), mtext("(k)"))
    omega_m = msub(mtext("ω"), mtext("m"))
    J_m = msub(mtext(target), mtext("m"))
    return (msub(mtext(base), mtext(sub)) + mdelim("(", a_k, ")") + mtext(" = ") +
            mnary("∑", mtext(index_set), None, omega_m + mtext("·") + J_m + mdelim("(", a_k, ")")) +
            mtext(",  ") + msub(mtext("Σ"), mtext("m")) + omega_m + mtext(" = 1, ") +
            omega_m + mtext(" ≥ 0"))


def formula_indicator_pass() -> str:
    """I_pass(a^(k)) = I[Viol_hard=0]·I[Viol_soft≤τ_soft]·I[A_pareto≥A_min]

    专利案例：三层预验证通过判据。
    """
    a_k = msup(mtext("a"), mtext("(k)"))
    I = I_chr()  # noqa: E741
    return (msub(mtext("I"), mtext("pass")) + mdelim("(", a_k, ")") + mtext(" = ") +
            I + mdelim("[", msub(mtext("Viol"), mtext("hard")) + mtext(" = 0"), "]") + mtext("·") +
            I + mdelim("[", msub(mtext("Viol"), mtext("soft")) + mtext(" ≤ ") + msub(mtext("τ"), mtext("soft")), "]") + mtext("·") +
            I + mdelim("[", msub(mtext("A"), mtext("pareto")) + mtext(" ≥ ") + msub(mtext("A"), mtext("min")), "]"))


def formula_multi_target() -> str:
    """L_gen = λ_q·J_q + λ_e·J_e + λ_p·J_p + λ_s·J_s

    专利案例：综合生成目标函数。
    """
    parts = []
    for i, (lam, J) in enumerate([("q", "q"), ("e", "e"), ("p", "p"), ("s", "s")]):
        if i:
            parts.append(mtext(" + "))
        parts.append(msub(mtext("λ"), mtext(lam)) + mtext("·") + msub(mtext(J), mtext(lam)))
    return msub(mtext("L"), mtext("gen")) + mtext(" = ") + "".join(parts)


def formula_skill_match() -> str:
    """Match(h_t, SKILL_j) = cosine_sim(h_t, C_j)·I[‖h_t−C_j‖≤r_j]·S_j

    专利案例：技能匹配度函数。
    """
    h_t = msub(mtext("h"), mtext("t"))
    C_j = msub(mtext("C"), mtext("j"))
    r_j = msub(mtext("r"), mtext("j"))
    S_j = msub(mtext("S"), mtext("j"))
    I = I_chr()  # noqa: E741
    return (mtext("Match") + mdelim("(", h_t + mtext(", ") + msub(mtext("SKILL"), mtext("j")), ")") + mtext(" = ") +
            mtext("cosine_sim") + mdelim("(", h_t + mtext(", ") + C_j, ")") + mtext("·") +
            I + mdelim("[", mnorm_par(h_t + mtext(" − ") + C_j) + mtext(" ≤ ") + r_j, "]") + mtext("·") +
            S_j)


if __name__ == "__main__":
    # 快速自检：生成一个含各类公式的最小 docx
    body = []
    body.append(para_text("OMML 示例文档", bold=True, sz=32, align="center"))
    body.append(para_text("1. 行内公式示例：状态向量 x_t 的预测值 x̂_{t+1}。", sz=21))
    body.append(mixed_para([
        ("text", "1. 行内公式示例：状态向量 "),
        ("math", sub_math("x", "t")),
        ("text", " 的预测值 "),
        ("math", sub_hat_math("x", "t+1")),
        ("text", "。"),
    ]))
    body.append(para_text("2. 独立公式（多目标加权评分）：", sz=21))
    body.append(math_display(formula_pareto_score()))
    body.append(para_text("3. 分数公式：", sz=21))
    body.append(math_display(mfrac(mtext("∂x"), mtext("∂t")) + mtext(" = ") +
                             mfrac(mtext("F"), msub(mtext("M"), mtext("s")))))
    body.append(para_text("4. 求和与积分：", sz=21))
    body.append(math_display(mnary("∑", msub(mtext("m"), mtext("")) + mtext("=1"), mtext("K"),
                                   msub(mtext("ω"), mtext("m")))))
    body.append(math_display(mnary("∫", mtext("0"), mtext("1"), mtext("f(t) dt"))))
    out = build_docx("".join(body), "demo_omml.docx")
    print("生成:", out)
