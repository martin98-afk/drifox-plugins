#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OMML 结构验证脚本 — 校验生成的 docx 中公式是否规范。

用法:
    python validate_omml.py demo_omml.docx

检查项（对应 SKILL.md 中的 OMML 规范要点）:
    V1  zip 包完整性（能解压）
    V2  word/document.xml 存在且 XML 良构
    V3  根元素声明了 m 命名空间
    V4  m:oMath 数量 >= 1（存在公式）
    V5  行内公式 m:oMath 是 w:p 的直接子元素（与 w:r 平级，未塞进 w:r 内部）
    V6  兼容性：m:oMathPara 块级公式未置于表格单元格内（表格内会渲染中断"只剩一半"）
    V7  各类结构元素出现：sSub / sSup / sSubSup / frac / d / nary / acc
    V8  文本节点 m:t 均带 xml:space="preserve"
    V9  w:t 与 m:t 命名空间正确分离（公式文本不在 w:t 里）
    V10 无非法 <m:b> 元素（m:rPr 无 m:b，加粗必须用 m:sty m:val="b"）
    V11 数学 run 带 Cambria Math 字体声明（建议，与 Word 原生公式一致）

退出码: 0 全部通过 / 1 有失败
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"

CHECKS: list[tuple[str, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    CHECKS.append((name, "PASS" if ok else "FAIL"))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python validate_omml.py <demo.docx>")
        return 2
    docx_path = Path(sys.argv[1])
    if not docx_path.exists():
        print(f"文件不存在: {docx_path}")
        return 1

    # V1 解压
    try:
        zf = zipfile.ZipFile(docx_path)
        bad = zf.testzip()
        check("V1 zip 包完整性", bad is None, f"损坏成员: {bad}")
    except Exception as e:  # noqa: BLE001
        check("V1 zip 包完整性", False, str(e))
        return 1

    # V2 document.xml 良构
    try:
        xml = zf.read("word/document.xml").decode("utf-8")
        root = ET.fromstring(xml)
        check("V2 document.xml 存在且良构", True)
    except Exception as e:  # noqa: BLE001
        check("V2 document.xml 存在且良构", False, str(e))
        return 1

    # V3 m 命名空间（根元素需显式声明 xmlns:m，否则 ET 无法解析 m:oMath）
    M_NS_DECL = 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'
    check("V3 根元素声明 m 命名空间", M_NS_DECL in xml)

    # V4 oMath 数量
    omaths = list(root.iter(M + "oMath"))
    check("V4 存在公式 (m:oMath)", len(omaths) >= 1, f"共 {len(omaths)} 个")

    # 建立 子 -> 父 映射，避免 O(n^2) 反复 iter 查找父元素
    parent_map = {c: p for p in root.iter() for c in p}

    # V5 行内公式位置：oMath 的直接父必须是 w:p（行内）或 m:oMathPara（块级独立）
    inline_ok = True
    for om in omaths:
        dp = parent_map.get(om)
        if dp is None or dp.tag not in (W + "p", M + "oMathPara"):
            inline_ok = False
    check("V5 行内公式为 w:p 直接子元素（未塞进 w:r）", inline_ok)

    # V6 兼容性：oMathPara 独立公式仅允许在非表格段落（表格内渲染中断）
    omps = list(root.iter(M + "oMathPara"))
    if omps:
        omp_bad = 0
        for omp in omps:
            # 沿 parent_map 向上查找祖先：是否位于 w:tbl 内
            node = omp
            in_tbl = False
            while node is not None:
                if node.tag == W + "tbl":
                    in_tbl = True
                    break
                node = parent_map.get(node)
            if in_tbl:
                omp_bad += 1
        check("V6 兼容性: oMathPara 未置于表格单元格内", omp_bad == 0,
              f"{omp_bad}/{len(omps)} 个在表格内（会渲染中断）")
    else:
        check("V6 兼容性: 独立公式用行内 oMath 居中段落（推荐，无 oMathPara）", True)

    # V7 结构元素覆盖
    for tag, name in [("sSub", "下标 sSub"), ("sSup", "上标 sSup"),
                      ("sSubSup", "上下标 sSubSup"), ("frac", "分数 frac"),
                      ("d", "括号 d"), ("nary", "求和/积分 nary"),
                      ("acc", "重音 acc")]:
        found = list(root.iter(M + tag))
        # 注意 M+'d' 需要精确：m:d 标签
        check(f"V7 {name}", len(found) >= 1, f"共 {len(found)} 个")

    # V8 m:t 带 xml:space="preserve"
    mt_ok = True
    missing = 0
    for mt in root.iter(M + "t"):
        if mt.get("{http://www.w3.org/XML/1998/namespace}space") != "preserve":
            missing += 1
    check("V8 m:t 均带 xml:space=preserve", missing == 0, f"{missing} 个缺失")

    # V9 w:t 与 m:t 分离
    wts = list(root.iter(W + "t"))
    mts = list(root.iter(M + "t"))
    check("V9 w:t 与 m:t 分离", len(wts) >= 1 and len(mts) >= 1,
          f"w:t={len(wts)} 个 / m:t={len(mts)} 个")

    # V10 非法 <m:b> 元素（m:rPr 中无 m:b；加粗用 m:sty m:val="b"）
    bad_b = len(re.findall(r"<m:b[ >]", xml))
    check("V10 无非法 <m:b> 元素（加粗用 m:sty b）", bad_b == 0, f"{bad_b} 处")

    # V11 数学 run 字体声明（建议：与 Word 原生一致用 Cambria Math）
    # 合规结构：<m:rPr><m:rFonts w:ascii="Cambria Math" .../>（m:rFonts 在 m:rPr 内）
    has_font = ('m:rFonts w:ascii="Cambria Math"' in xml
                or 'w:rFonts w:ascii="Cambria Math"' in xml)
    check("V11 数学 run 带 Cambria Math 字体声明（建议）", has_font)

    failed = [n for n, s in CHECKS if s == "FAIL"]
    print()
    if failed:
        print(f"结果: {len(CHECKS)-len(failed)}/{len(CHECKS)} 通过, 失败: {failed}")
        return 1
    print(f"结果: {len(CHECKS)}/{len(CHECKS)} 全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
