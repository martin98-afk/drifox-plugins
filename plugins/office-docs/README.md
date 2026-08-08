# office-docs

> Office 文档处理 — docx / pdf / pptx / xlsx 4 类文档读、写、转换、生成。

源自 [anthropics/skills](https://github.com/anthropics/skills) 4 个文档 skill（docx / pdf / pptx / xlsx）整合。

## 4 大能力

| 文档 | 库 | 用途 |
|------|------|------|
| **docx** | python-docx | Word 文档读/写/编辑 |
| **pdf** | pypdf / pdfplumber | PDF 读/写/合并/拆分 |
| **pptx** | python-pptx | PPT 演示文稿创建 |
| **xlsx** | openpyxl | Excel 表格读/写 |

## 安装

```bash
/plugin marketplace add martin98-afk/drifox-plugins
/plugin install office-docs@drifox-official
```

依赖：

```bash
pip install python-docx pypdf pdfplumber python-pptx openpyxl
```

## 命令

| 命令 | 用途 |
|------|------|
| `/docx-read <file>` | 读取 Word 文档内容 |
| `/pdf-read <file>` | 读取 PDF 文本 |
| `/pptx-create <topic>` | 创建 PPT 演示 |
| `/xlsx-read <file>` | 读取 Excel 数据 |

## 4 类文档实战

### 1. docx — Word 文档

```python
from docx import Document

doc = Document('input.docx')

# 读段落
for p in doc.paragraphs:
    print(p.text)

# 写新文档
doc = Document()
doc.add_heading('Title', 0)
doc.add_paragraph('Hello world')
doc.save('output.docx')
```

### 2. pdf — PDF 文档

```python
import pdfplumber

with pdfplumber.open('input.pdf') as pdf:
    for page in pdf.pages:
        print(page.extract_text())

# 合并 PDF
from pypdf import PdfMerger
merger = PdfMerger()
for pdf in ['a.pdf', 'b.pdf']:
    merger.append(pdf)
merger.write('merged.pdf')
```

### 3. pptx — PPT 演示

```python
from pptx import Presentation

prs = Presentation()

slide = prs.slides.add_slide(prs.slide_layouts[1])
slide.shapes.title.text = 'Hello'
slide.placeholders[1].text = 'World'

prs.save('output.pptx')
```

### 4. xlsx — Excel 表格

```python
import openpyxl

wb = openpyxl.load_workbook('input.xlsx')
ws = wb.active

for row in ws.iter_rows(values_only=True):
    print(row)

# 写新表
wb = openpyxl.Workbook()
ws = wb.active
ws['A1'] = 'Hello'
ws['B1'] = 'World'
wb.save('output.xlsx')
```

## 5 个常见场景

### 1. 批量生成合同

```python
from docx import Document
from docx.shared import Pt

template = Document('contract-template.docx')
for customer in customers:
    doc = Document('contract-template.docx')
    for p in doc.paragraphs:
        if '{{name}}' in p.text:
            p.text = p.text.replace('{{name}}', customer['name'])
    doc.save(f'contracts/{customer["name"]}.docx')
```

### 2. PDF 转 docx

```python
import pdfplumber
from docx import Document

doc = Document()
with pdfplumber.open('input.pdf') as pdf:
    for page in pdf.pages:
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
    date, product, amount = row
    totals[product] += amount

for product, total in totals.items():
    print(f'{product}: ${total}')
```

### 4. PPT 自动生成

```python
from pptx import Presentation
from pptx.util import Inches

prs = Presentation()
for slide_data in slides:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = slide_data['title']
    body = slide.placeholders[1]
    body.text = '\n'.join(slide_data['bullets'])
prs.save('output.pptx')
```

### 5. PDF 水印

```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader('input.pdf')
writer = PdfWriter()
for page in reader.pages:
    page.merge_page(watermark_page)
    writer.add_page(page)
writer.write('watermarked.pdf')
```

## 4 个反模式

- ❌ **用 Word 模板做 OCR** — 用专业 OCR 工具
- ❌ **生成 PDF 后再编辑** — 应当源端编辑
- ❌ **忽略格式** — 大小/边距/字体
- ❌ **xlsx 大文件无流式** — 用 `read_only=True`

## 配套库

| 用途 | 库 |
|------|------|
| docx | python-docx, docx2pdf |
| pdf | pypdf, pdfplumber, PyMuPDF |
| pptx | python-pptx |
| xlsx | openpyxl, xlrd |
| OCR | pytesseract |
| 转换 | LibreOffice headless |

## 配合

- 配合 `python-pro` 写 Python 脚本
- 配合 `beautiful-article-skills` 写文章
- 配合 `omml-docx` 走 Office 数学公式

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
