---
name: web-accessibility
description: Web 无障碍（WCAG 2.2 AA）— 对比度、键盘导航、语义结构、ARIA、屏幕阅读器支持、动效减弱、聚焦管理。触发关键词：a11y、无障碍、accessibility、WCAG、键盘导航、屏幕阅读器、aria、aria-label、对比度、focus、focus-visible、screen reader。
---

# Web Accessibility 技能 — WCAG 2.2 AA 合规

源自 [supercent-io/skills-template](https://github.com/supercent-io/skills-template) 的 web-accessibility，helloianneo/awesome-claude-code-skills **好用**。

本技能为 AI 提供 **WCAG 2.2 AA 级**无障碍检查与修复能力。

## 何时触发

- 用户："检查 a11y"、"a11y 审查"、"无障碍检查"
- 用户："键盘导航"、"屏幕阅读器适配"
- 用户："WCAG 合规"、"a11y 自动化"
- AI 完成 UI 时自动注入

## WCAG 2.2 AA 四大原则（POUR）

### P. Perceivable（可感知）

| 准则 | 检查 | 修复 |
|------|------|------|
| 1.1.1 非文本内容 | 装饰图 `alt=""` / 信息图 `alt="..."` | 加 alt |
| 1.3.1 信息和关系 | 标题层级正确 / `<label>` 关联 | 修语义 |
| 1.4.3 文本对比度 | ≥ 4.5:1（AA）/ 7:1（AAA） | 调色 |
| 1.4.4 文本缩放 | 200% 缩放不丢内容 | 用 rem/em |
| 1.4.10 重排 | 320px 宽不丢内容 | 响应式 |
| 1.4.11 非文本对比度 | UI 元素 ≥ 3:1 | 调色 |
| 1.4.12 文本间距 | 行高 ≥ 1.5 / 段距 ≥ 2 倍 | 修样式 |
| 1.4.13 悬停内容 | 可悬停 + 关闭 | 提供关闭 |

### O. Operable（可操作）

| 准则 | 检查 | 修复 |
|------|------|------|
| 2.1.1 键盘 | 所有功能可用键盘 | 加 handlers |
| 2.1.2 无键盘陷阱 | Tab 可离开 | 修 focus |
| 2.4.1 跳过块 | "跳到主内容" | 加链接 |
| 2.4.2 页面标题 | 每页唯一 title | 改 <title> |
| 2.4.3 焦点顺序 | 顺序与视觉一致 | 修 tabindex |
| 2.4.6 标题与标签 | 清晰描述 | 改文案 |
| 2.4.7 焦点可见 | 始终显示 | 修 outline |
| 2.4.11 焦点不遮挡 | 焦点元素不被 sticky 元素遮 | 改 z-index |
| 2.5.3 标签名 | 与名称一致 | 修 aria-label |
| 2.5.7 拖动替代 | 拖动有替代 | 加按钮 |
| 2.5.8 目标大小 | ≥ 24×24px（含间距） | 调 padding |

### U. Understandable（可理解）

| 准则 | 检查 | 修复 |
|------|------|------|
| 3.1.1 页面语言 | `<html lang="...">` | 加 lang |
| 3.2.1 聚焦不改变上下文 | focus 不触发跳转 | 修 onFocus |
| 3.2.2 输入不改变上下文 | input 不自动提交 | 修 onChange |
| 3.3.1 错误识别 | 错误描述 | 加 aria-errormessage |
| 3.3.2 标签/提示 | 输入框有 label | 加 <label> |

### R. Robust（健壮）

| 准则 | 检查 | 修复 |
|------|------|------|
| 4.1.2 名称/角色/值 | 组件角色正确 | 修 aria |
| 4.1.3 状态消息 | 状态变化通知 | aria-live |

## 实战代码模式

### 1. 按钮 vs 链接

```tsx
// ❌ div + onclick
<div onClick={handleClick}>Click me</div>

// ✅ 按钮
<button type="button" onClick={handleClick}>Click me</button>

// ✅ 跳转用链接
<a href="/about">About</a>
```

### 2. 键盘导航

```tsx
// ✅ 列表项键盘可访问
<div
  role="button"
  tabIndex={0}
  onClick={handleClick}
  onKeyDown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      handleClick()
    }
  }}
>
  Click me
</div>
```

### 3. 焦点管理

```tsx
// ✅ 模态对话框打开时，焦点移到对话框
function Modal({ open, onClose, children }: ModalProps) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (open && ref.current) {
      ref.current.focus()
    }
  }, [open])

  return open ? (
    <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true">
      {children}
      <button onClick={onClose}>Close</button>
    </div>
  ) : null
}
```

### 4. 可见焦点

```css
/* ❌ 删除焦点环 */
*:focus { outline: none; }

/* ✅ 自定义焦点环 */
*:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
```

### 5. 表单标签

```tsx
// ✅ 关联 label 与 input
<label htmlFor="email">Email</label>
<input id="email" type="email" required />

// ✅ aria 描述
<input
  id="email"
  type="email"
  aria-describedby="email-error"
  aria-invalid={!!error}
/>
{error && <span id="email-error">{error}</span>}
```

### 6. 动效减弱

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

### 7. ARIA 模式

```tsx
// ✅ Combobox
<div role="combobox" aria-expanded={open} aria-haspopup="listbox" aria-owns="listbox-id">
  <input aria-autocomplete="list" aria-controls="listbox-id" />
  <ul id="listbox-id" role="listbox">
    {items.map(item => (
      <li role="option" aria-selected={item === selected}>{item.label}</li>
    ))}
  </ul>
</div>
```

### 8. 跳转链接

```tsx
<a href="#main-content" className="sr-only focus:not-sr-only">
  Skip to main content
</a>
<main id="main-content" tabIndex={-1}>
  {/* 内容 */}
</main>
```

## 自动化工具

| 工具 | 作用 | 命令 |
|------|------|------|
| axe-core | 静态扫描 | `npx @axe-core/cli` |
| Lighthouse | Performance + a11y | Chrome DevTools |
| Pa11y | CI 集成 | `npx pa11y-ci` |
| Wave | 可视化审查 | Chrome 扩展 |
| Screen Reader | 真实测试 | NVDA / VoiceOver |

## 反模式

- ❌ `<div onClick>` 替代 `<button>`
- ❌ 删除 `outline: none` 不补
- ❌ 装饰图 `<img>` 无 `alt`
- ❌ 表单缺 `<label>`
- ❌ 自动播放音频/视频
- ❌ 强制键盘焦点
- ❌ 拖动无替代
- ❌ 媒体不带字幕

## 检查清单模板

```markdown
## A11y 审查 — [页面名]

### P. Perceivable
- [ ] 所有图片有 alt 或 alt=""
- [ ] 文本对比度 ≥ 4.5:1
- [ ] 200% 缩放无内容丢失
- [ ] 320px 宽无水平滚动

### O. Operable
- [ ] 所有功能键盘可用
- [ ] 无键盘陷阱
- [ ] 焦点环始终可见
- [ ] 跳转链接存在
- [ ] 标题层级正确
- [ ] 触控目标 ≥ 24×24px

### U. Understandable
- [ ] <html lang="..."> 设置
- [ ] 表单有 label
- [ ] 错误信息清晰

### R. Robust
- [ ] ARIA 角色正确
- [ ] 状态消息 aria-live

### 评分
- 通过：__/20
- 失败：__/20
- 整体：PASS / FAIL
```

## 提示

- 配合 `frontend-pro` 走 12 大类 UI 审查
- 配合 `tailwind-pro` 验证颜色对比度
- 配合 `web-design-guidelines` 审查 UI 细节
- 用 axe-core 自动扫描后再手动复核
