# OMML 元素参考（Office Math Markup Language）

> 命名空间：`http://schemas.openxmlformats.org/officeDocument/2006/math`（前缀 `m`）
> 权威定义：ISO/IEC 29500-1 §22（shared-math.xsd）
> 本文档给出可直接复制使用的 XML 片段。所有 `<m:t>` 都应带 `xml:space="preserve"`。

## 1. 公式容器

### 行内公式（inline）
```xml
<w:p>
  <w:r><w:t>文本</w:t></w:r>
  <m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>   <!-- 与 w:r 平级！ -->
  <w:r><w:t>文本</w:t></w:r>
</w:p>
```
- `m:oMath` 是 `w:p` 的直接子元素（`w:r`、`m:oMath` 可以任意交替）。
- **禁止**把 `m:oMath` 放进 `w:r` 内部。

### 独立公式（display，独占一行）
```xml
<w:p>
  <w:pPr><w:jc w:val="center"/></w:pPr>
  <m:oMathPara><m:oMath>…</m:oMath></m:oMathPara>
</w:p>
```

## 2. 基础 run

| 元素 | XML | 说明 |
|------|-----|------|
| 正体 run | `<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t xml:space="preserve">x</m:t></m:r>` | 默认正体 |
| 斜体 run | `<m:r><m:rPr><m:sty m:val="i"/><m:i m:val="1"/></m:rPr><m:t>…</m:t></m:r>` | 变量惯例 |

## 3. 结构元素

### 下标 sSub
```xml
<m:sSub><m:e>基</m:e><m:sub>下标</m:sub></m:sSub>   <!-- x_t -->
```

### 上标 sSup
```xml
<m:sSup><m:e>基</m:e><m:sup>上标</m:sup></m:sSup>   <!-- a^(k) -->
```

### 上下标同时 sSubSup
```xml
<m:sSubSup><m:e>基</m:e><m:sub>下</m:sub><m:sup>上</m:sup></m:sSubSup>  <!-- x_t^max -->
```

### 分数 frac
```xml
<m:frac><m:num>分子</m:num><m:den>分母</m:den></m:frac>  <!-- ∂x/∂t -->
```
- 分数内部可以嵌套任意表达式（m:frac 的 num/den 里再放 m:frac）。

### 括号（定界符）d
```xml
<m:d>
  <m:dPr><m:begChr m:val="("/><m:endChr m:val=")"/></m:dPr>
  <m:e>内容</m:e>
</m:d>
```
- 常用开闭符：`(` `)`、`[` `]`、`{` `}`、`|`、`‖`（范数）、`⌈⌉`、`⌊⌋`。
- 内容为空或单个元素时 `<m:e>` 直接包；多元素并列就多个 run 拼在 `<m:e>` 里。

### n-ary 算子（求和/积分/连乘）nary
```xml
<m:nary>
  <m:naryPr>
    <m:chr m:val="∑"/>
    <m:limLoc m:val="undOvr"/>   <!-- undOvr=上下限在算子上下；subSup=右下右上 -->
  </m:naryPr>
  <m:sub>m=1</m:sub>
  <m:sup>K</m:sup>
  <m:e>ω_m·J_m</m:e>
</m:nary>
```
- 常用 chr：`∑`（求和）、`∫`（积分）、`∏`（连乘）、`⋃`（并集）。
- 积分无上下限时 `<m:sub/>` `<m:sup/>` 留空。

### 重音（hat / bar / tilde）acc
```xml
<m:acc>
  <m:accPr><m:chr m:val="̂"/></m:accPr>   <!-- U+0302 COMBINING CIRCUMFLEX -->
  <m:e>基</m:e>
</m:acc>
```
- hat 的 chr 是**组合字符** U+0302（跟在基后面渲染成帽子）。
- bar（均值）：chr `‾`（U+203E OVERLINE）；tilde：`̃`（U+0303）。

### 根式 rad
```xml
<m:rad>
  <m:radPr><m:degHide m:val="1"/></m:radPr>   <!-- degHide=1 表示平方根（无次数） -->
  <m:deg/>
  <m:e>被开方数</m:e>
</m:rad>
```
- 三次根号：`<m:degHide m:val="0"/>` + `<m:deg>3</m:deg>`。

### 上下边界（bar）— 矩阵/行列式竖线
```xml
<m:bar>
  <m:barPr><m:pos m:val="top"/><m:chr m:val="¯"/></m:barPr>  <!-- top/bot 边界 -->
  <m:e>内容</m:e>
</m:bar>
```

### 函数名 f（正体函数字）
```xml
<m:f><m:fPr><m:type m:val="func"/></m:fPr><m:e>sin</m:e></m:f>
```
- 用于 sin/cos/tan/log 等函数名正体显示（可选，直接 mtext("sin") 也常见）。

## 4. 指示函数与特殊记号（专利场景常用）

```xml
<!-- 指示函数：粗体 I，条件用方括号定界 -->
<m:r><m:rPr><m:sty m:val="p"/><m:b m:val="1"/></m:rPr><m:t>I</m:t></m:r>
<m:d><m:dPr><m:begChr m:val="["/><m:endChr m:val="]"/></m:dPr><m:e>Viol=0</m:e></m:d>

<!-- 范数：双竖线包住表达式 -->
<m:t>‖</m:t>…<m:t>‖</m:t>
```

## 5. 文本拼接规则

- 表达式 = 多个 run/结构元素**直接字符串拼接**（中间无空格）。
- 需要显示空格时，在 `m:t` 里写空格（必须 `xml:space="preserve"`），或显式 `mtext(" ")`。
- `=`、`+`、`−`、`·`、`≤`、`≥`、`∈`、`×` 等运算符用 `mtext` 包。

## 6. 与 Word 实际渲染的对应

| OMML | Word 显示 |
|------|-----------|
| `m:sSub` | x_t（下标） |
| `m:sSup` | x²（上标） |
| `m:frac` | 竖式分数 |
| `m:nary` | ∑ 带上下限（随算子缩放） |
| `m:d` | 可伸缩括号 |
| `m:acc` | x̂（hat） |
| `m:rad` | √x |
| `m:oMathPara` | 独立公式行（居中） |

## 7. 快速参考（辅助函数 → OMML 元素映射）

| 辅助函数 | 产出元素 |
|----------|---------|
| `msub/mtext/mit` | `m:sSub` / `m:r` |
| `msup` | `m:sSup` |
| `msub_sup` | `m:sSubSup` |
| `mfrac` | `m:frac` |
| `mdelim` | `m:d` |
| `mnary` | `m:nary` |
| `mhat` | `m:acc` |
| `math_inline` | `m:oMath` |
| `math_display` | `m:oMathPara` |
