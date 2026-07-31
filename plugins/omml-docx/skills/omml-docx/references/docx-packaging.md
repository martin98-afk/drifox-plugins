# docx 打包流水线详解

> docx = ZIP 容器 + OOXML。本文档说明如何用纯标准库把 document.xml 组装成合法 docx。

## 1. ZIP 结构（最小必需）

```
out.docx
├── [Content_Types].xml          ← 必填：声明包内文件类型
├── _rels/.rels                  ← 必填：包级关系（指向 word/document.xml）
└── word/
    ├── document.xml             ← 正文（含公式）
    ├── _rels/document.xml.rels  ← 文档级关系（styles/theme/图片）
    ├── styles.xml               ← 样式（可最小化）
    └── media/                   ← 图片（可选）
```

## 2. 三种构建策略

### 策略 A：从零最小 docx（`build_docx(body, out)`，template 为 None）
- 用库内 `MINIMAL_DOCX_PARTS`（Content_Types + 两级 rels + 最小 styles）。
- 适合快速原型、无样式要求的场景。
- **注意**：最小包没有 theme/settings，Word 打开正常但样式能力弱。

### 策略 B：复用母版（`build_docx(body, out, template_docx=母版)`）【推荐】
- 逻辑：解压母版 → 用新 `document.xml` 覆盖 `word/document.xml` → 重新 zip。
- 母版的 styles/theme/fontTable/media/页眉页脚全部保留。
- 适用：专利交底书、论文（需要模板样式、页眉页脚、图片）。

### 策略 C：直接改现有 docx 的局部 XML
- 仅当改动极小（如只插一个公式段）且公式结构简单时。
- **不推荐**：字符串替换容易破坏既有公式/结构；优先策略 B。

## 3. document.xml 骨架要求

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
  xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"   <!-- 必须！ -->
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  …其余 wpc/mc/o/v/wp/w14/w15/wpg/wps 命名空间…>
  <w:body>
    …段落/表格…
    <w:sectPr>…页面设置…</w:sectPr>   <!-- body 末尾必须保留 -->
  </w:body>
</w:document>
```

## 4. 图片嵌入（需要插图时）

```xml
<!-- 1) word/media/image1.png 放入包 -->
<!-- 2) word/_rels/document.xml.rels 注册 -->
<Relationship Id="rId9"
  Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
  Target="media/image1.png"/>

<!-- 3) document.xml 中引用 -->
<w:p>
  <w:r>
    <w:drawing>
      <wp:inline distT="0" distB="0" distL="0" distR="0">
        <wp:extent cx="4680000" cy="4680000"/>
        <wp:docPr id="1" name="图1"/>
        <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
            <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
              <pic:nvPicPr>
                <pic:cNvPr id="1" name="图1"/><pic:cNvPicPr/>
              </pic:nvPicPr>
              <pic:blipFill>
                <a:blip r:embed="rId9"/>
                <a:stretch><a:fillRect/></a:stretch>
              </pic:blipFill>
              <pic:spPr>
                <a:xfrm><a:off x="0" y="0"/><a:ext cx="4680000" cy="4680000"/></a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
              </pic:spPr>
            </pic:pic>
          </a:graphicData>
        </a:graphic>
      </wp:inline>
    </w:drawing>
  </w:r>
</w:p>
```

## 5. 表格（w:tbl）与公式混合

- 公式可以出现在表格单元格里（`w:tc` 内的 `w:p` 中），OMML 结构不变。
- 单元格段落同样遵守"oMath 与 w:r 平级"规则。

## 6. 打包与验证

```bash
# 打包（库内 build_docx 自动完成；也可手写 zipfile）
python - <<'PY'
import zipfile
with zipfile.ZipFile('out.docx', 'w', zipfile.ZIP_DEFLATED) as zf:
    for name, content in parts.items():
        zf.writestr(name, content)
PY

# 验证
python scripts/validate_omml.py out.docx     # 结构 15 项
# 打开确认（Word/WPS/LibreOffice）
```

## 7. 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| Word 提示"文件损坏，是否修复" | document.xml 结构错误（缺 sectPr / 命名空间缺失 / oMath 位置错） | 跑 validate_omml.py，逐项排查 |
| 图片不显示 | rels 未注册或 r:embed 的 rId 不匹配 | 检查 document.xml.rels 的 rId 与 drawing 中 r:embed 一致 |
| 公式不渲染但文本在 | 命名空间缺失或 oMath 放错位置 | 确认 xmlns:m 声明 + oMath 为 w:p 直接子元素 |
| 打开后公式变成"域代码" | OMML 被当作 field | 确认用的是 m:oMath 而非 w:fldSimple |
