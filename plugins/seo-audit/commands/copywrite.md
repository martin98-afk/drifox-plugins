---
description: 撰写主页/落地页/定价页高转化文案（基于 Corey Haines 框架）
type: prompt
parameters:
  - name: "<page>"
    description: "页面类型：home / landing / pricing / about / features"
    param_type: positional
  - name: "--tone="
    description: "语气：professional / friendly / bold / playful / technical"
    param_type: value
  - name: "--audience="
    description: "目标受众：developer / founder / marketing / enterprise"
    param_type: value
  - name: "--ref="
    description: "参考 URL（参考竞品文案）"
    param_type: value
allowed-tools:
  - read
  - webfetch
  - grep
hidden: false
---

# /copywrite 命令 — 高转化落地页文案

你正在处理 `/copywrite` 命令。本命令基于 Corey Haines 的市场文案框架，撰写**高转化页面文案**。

## 📋 执行规则

1. **解析参数**：
   - `<page>`：home | landing | pricing | about | features
   - `--tone=`：professional | friendly | bold | playful | technical
   - `--audience=`：developer | founder | marketing | enterprise
   - `--ref=`：参考 URL（可选）

2. **文案结构**（按页面类型）：

   ### 🏠 home（主页）

   ```
   1. Hero
      - Headline（≤ 8 字，传达核心价值）
      - Subheadline（≤ 30 字，解释怎么做到）
      - CTA 主按钮 + 次按钮

   2. Social Proof
      - 客户 logo（5-8 个）
      - 1-2 句真实用户证言

   3. 核心价值（3-4 个 benefit）
      - 每个 benefit：图标 + 标题 + 50 字说明

   4. 工作流/流程（3-4 步）
      - 用编号步骤展示"怎么用"

   5. 详细功能（features grid）
      - 6-8 个 feature，每个截图 + 标题 + 100 字描述

   6. 案例研究
      - 1-2 个真实案例，含数据

   7. 定价简述
      - 3 个套餐卡片（只显示名字 + 价格 + 3 条核心特性）

   8. FAQ（5-8 个最常见问题）

   9. 终极 CTA
      - 重复主 CTA + 风险反转（"30 天试用，无需信用卡"）
   ```

   ### 🚀 landing（落地页 / 活动页）

   ```
   1. Hero（强 attention）
      - Hook（1 句抓眼球）
      - 大标题（≤ 12 字）
      - 副标题（痛点共鸣）
      - CTA

   2. 痛点放大（3-5 条）
      - 描述用户当前困境

   3. 解决方案
      - 我们的产品怎么解决

   4. How it works（3 步）

   5. 社会证明（强烈，含数据）

   6. 反对意见解答（3-5 条）

   7. 终极 CTA + 风险反转
   ```

   ### 💰 pricing（定价页）

   ```
   1. 价值主张（≤ 30 字说明为什么值得）

   2. 3 个套餐（Free / Pro / Enterprise）
      - 每个套餐：
        * 名称 + 价格
        * 5-7 条核心特性
        * 1 个 CTA 按钮
        * "最适合谁" 描述

   3. 对比表（详细功能横向对比）

   4. FAQ（5-8 条：能取消吗？支持哪些支付？发票？）

   5. 信任元素（数据/认证/客户）

   6. 终极 CTA
   ```

3. **文案风格规则**：

   **Corey Haines 原则**：
   - **清晰优于聪明**：用日常语言，不绕弯
   - **具体优于抽象**：用数字、例子、可感知的描述
   - **短句优于长句**：每句 ≤ 20 字
   - **动词优于名词**：start / build / ship / save
   - **第二人称**：直接对用户说话

   **避免**：
   - ❌ "revolutionize" / "synergy" / "leverage" / "cutting-edge"
   - ❌ "我们致力于..." / "我们努力成为..."
   - ❌ 堆砌形容词（"强大、灵活、可扩展的解决方案"）
   - ❌ 否定表述（"你不必担心..."）

4. **底部输出**：
   - 完整文案（Markdown 格式）
   - 关键文案决策说明（为什么这样写）
   - A/B 测试建议（哪些元素可以测试）

## 子行为

<!-- section:tone -->
### `--tone=<style>` 语气指南

| 风格 | 适用场景 | 关键词 |
|------|---------|--------|
| professional | B2B SaaS、咨询、法律 | proven、trusted、standard |
| friendly | 消费级 App、社交产品 | simple、enjoy、easy |
| bold | 颠覆性产品、技术营销 | transform、break、first |
| playful | 创作者工具、游戏 | fun、play、build |
| technical | 开发者工具、API | performant、typed、observable |
<!-- end -->

<!-- section:audience -->
### `--audience=<user>` 受众适配

| 受众 | 关注点 | 强调 |
|------|--------|------|
| developer | 性能、API、DX | 代码示例、benchmark |
| founder | 增长、ROI、效率 | 案例数据、ROI 证明 |
| marketing | 转化、品牌、流量 | A/B 测试、品牌故事 |
| enterprise | 安全、合规、SLA | SSO、SOC2、99.99% |
<!-- end -->

<!-- section:ref -->
### `--ref=<url>` 竞品参考

```
webfetch(ref_url)
```

提取：标题、副标题、CTA 文案、定价策略、语言风格，随后基于此生成差异化文案。
<!-- end -->

## 模板变量

- `$ARGUMENTS`：用户输入的完整参数
- `$PLUGIN_NAME`：当前插件名（seo-audit）

## 提示

- 配合 `seo-audit` 命令先审查现有页面
- 配合 `frontend-pro` 应用 UI 渲染
- 配合 `beautiful-article-skills` 生成 HTML 长文
- 写完后用 `/seo-audit` 验证新页面的 SEO 质量
