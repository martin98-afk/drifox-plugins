---
name: office-docs
description: Office 文档处理 — docx / pdf / pptx / xlsx 4 类文档的读、写、转换、生成、批量处理。触发关键词：word、docx、excel、xlsx、powerpoint、pptx、pdf、文档处理、表格、演示、office、文档生成、文档转换、批量文档、合同生成、报告生成。
---

# Office Docs 技能 — 4 类文档处理

源自 [anthropics/skills](https://github.com/anthropics/skills) 4 个文档 skill（docx / pdf / pptx / xlsx）整合。

## 何时触发

- 读 / 写 / 编辑 Word 文档
- 读 / 转换 / 合并 PDF
- 生成 PPT 演示
- 处理 Excel 表格数据
- 批量生成合同 / 报告 / 演示

## 4 类文档速查

### 1. docx（Word）

```python
from docx import Document

# 读
doc = Document('input.docx')
for p in doc.paragraphs:
    print(p.text)

# 写
doc = Document()
doc.add_heading('Title', level=0)
doc.add_paragraph('Hello world')
doc.save('output.docx')

# 读表格
for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            print(cell.text)

# 编辑
doc = Document('input.docx')
doc.paragraphs[0].text = 'New Title'
doc.save('output.docx')
```

### 2. pdf

```python
import pdfplumber
from pypdf import PdfReader, PdfWriter, PdfMerger

# 读
with pdfplumber.open('input.pdf') as pdf:
    for page in pdf.pages:
        print(page.extract_text())

# 合并
merger = PdfMerger()
for pdf in ['a.pdf', 'b.pdf']:
    merger.append(pdf)
merger.write('merged.pdf')

# 拆分
reader = PdfReader('input.pdf')
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f'page-{i}.pdf', 'wb') as f:
        writer.write(f)

# 提取图片
import fitz  # PyMuPDF
doc = fitz.open('input.pdf')
for page in doc:
    for img in page.get_images():
        xref = img[0]
        base = doc.extract_image(xref)
        with open(f'img-{xref}.png', 'wb') as f:
            f.write(base['image'])
```

### 3. pptx（PowerPoint）

```python
from pptx import Presentation
from pptx.util import Inches, Pt

# 读
prs = Presentation('input.pptx')
for slide in prs.slides:
    for shape in slide.shapes:
        if shape.has_text_frame:
            print(shape.text_frame.text)

# 创建
prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[1])  # Title + Content
slide.shapes.title.text = 'Title'
slide.placeholders[1].text = 'Subtitle'
prs.save('output.pptx')

# 加图片
slide = prs.slides.add_slide(prs.slide_layouts[5])
slide.shapes.title.text = 'Chart'
slide.shapes.add_picture('chart.png', Inches(1), Inches(2))
```

### 4. xlsx（Excel）

```python
import openpyxl

# 读
wb = openpyxl.load_workbook('input.xlsx', read_only=True)
ws = wb.active
for row in ws.iter_rows(values_only=True):
    print(row)

# 写
wb = openpyxl.Workbook()
ws = wb.active
ws['A1'] = 'Name'
ws['B1'] = 'Age'
ws.append(['Alice', 30])
ws.append(['Bob', 25])
wb.save('output.xlsx')

# 公式
ws['C1'] = '=SUM(B1:B100)'

# 格式
from openpyxl.styles import Font, PatternFill
ws['A1'].font = Font(bold=True, color='FFFFFF')
ws['A1'].fill = PatternFill('solid', fgColor='0066FF')
```

## 5 大实战场景

### 1. 批量合同生成

```python
from docx import Document

template = Document('contract-template.docx')

for customer in customers:
    doc = Document('contract-template.docx')
    for p in doc.paragraphs:
        for key, val in customer.items():
            if f'{{{{{key}}}}}' in p.text:
                p.text = p.text.replace(f'{{{{{key}}}}}', str(val))
    doc.save(f'contracts/{customer["name"]}.docx')
```

### 2. PDF 转 docx

```python
import pdfplumber
from docx import Document

doc = Document()
with pdfplumber.open('input.pdf') as pdf:
    for page in pdf.pages:
        if page.extract_text():
            doc.add_paragraph(page.extract_text())
doc.save('output.docx')
```

### 3. Excel 数据透视

```python
import openpyxl
from collections import defaultdict

wb = openpyxl.load_workbook('sales.xlsx')
ws = wb.active

totals = defaultdict(float)
for row in ws.iter_rows(min_row=2, values_only=True):
    product, amount = row[1], row[2]
    if product:
        totals[product] += amount

# 输出
for product, total in sorted(totals.items(), key=lambda x: -x[1]):
    print(f'{product}: ${total:.2f}')
```

### 4. PPT 自动生成

```python
from pptx import Presentation

prs = Presentation()
for slide_data in slides:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = slide_data['title']
    body = slide.placeholders[1].text_frame
    body.text = slide_data['bullets'][0]
    for bullet in slide_data['bullets'][1:]:
        body.add_paragraph().text = bullet
prs.save('output.pptx')
```

### 5. PDF 加水印

```python
from pypdf import PdfReader, PdfWriter

stamp = PdfReader('watermark.pdf').pages[0]
reader = PdfReader('input.pdf')
writer = PdfWriter()

for page in reader.pages:
    page.merge_page(stamp)
    writer.add_page(page)

with open('watermarked.pdf', 'wb') as f:
    writer.write(f)
```

## 5 个反模式

- ❌ **用 Word 模板做 OCR** — 用专业 OCR 工具
- ❌ **生成 PDF 后再编辑** — 应当源端编辑
- ❌ **忽略格式** — 大小/边距/字体
- ❌ **xlsx 大文件无流式** — 用 `read_only=True`
- ❌ **xlsx 公式硬编码** — 用 `=` 公式

## 配套库

| 用途 | 库 |
|------|------|
| docx | python-docx, docx2pdf |
| pdf | pypdf, pdfplumber, PyMuPDF |
| pptx | python-pptx |
| xlsx | openpyxl, xlrd, xlsxwriter |
| OCR | pytesseract, easyocr |
| 转换 | LibreOffice headless |

## 配合

- 配合 `python-pro` 写 Python 脚本
- 配合 `beautiful-article-skills` 写文章
- 配合 `omml-docx` 走 Office 数学公式

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
