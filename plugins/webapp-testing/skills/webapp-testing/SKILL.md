---
name: webapp-testing
description: Web 应用 E2E 测试助手 — 浏览器自动化 + Playwright + Chrome DevTools MCP + 测试策略 + 截图验证 + 调试技巧。编写/测试/调试 web 应用时自动触发。触发关键词：e2e 测试、playwright、自动化测试、浏览器自动化、cypress、页面测试、浏览器测试、回归测试、视觉回归、webapp testing、browser automation。
---

# Webapp Testing 技能 — 浏览器自动化 E2E 测试

源自 [anthropics/skills/webapp-testing](https://github.com/anthropics/skills/tree/main/skills/webapp-testing)。本技能为 AI 提供浏览器自动化测试能力。

## 何时触发

- AI 写完 web 应用后自动验证
- 跑回归测试
- 调试前端 bug
- 跨浏览器兼容性测试

## 2 大核心工具

### 1. Chrome DevTools MCP（AI 首选）

`@modelcontextprotocol/server-chrome-devtools` — 通过 MCP 协议控制 Chrome。

提供 12+ 工具：

| 工具 | 用途 |
|------|------|
| `browser_navigate` | 导航到 URL |
| `browser_click` | 点击元素 |
| `browser_type` | 输入文本 |
| `browser_screenshot` | 截图 |
| `browser_console` | 读取 console |
| `browser_network` | 读取网络请求 |
| `browser_evaluate` | 执行 JS |
| `browser_hover` | 悬浮 |
| `browser_drag` | 拖动 |
| `browser_select` | 选择下拉 |
| `browser_pdf` | 导出 PDF |
| `browser_close` | 关闭 |

### 2. Playwright（生产测试套件）

```bash
npm install -D @playwright/test
npx playwright install
```

## 5 步 AI 测试工作流

### Step 1：启动浏览器

```bash
# Chrome DevTools MCP
npx @modelcontextprotocol/server-chrome-devtools

# Playwright
npx playwright codegen
```

### Step 2：导航 + 截图

```python
mcp__chrome__browser_navigate(url="http://localhost:3000")
mcp__chrome__browser_screenshot()
```

### Step 3：交互

```python
mcp__chrome__browser_click(element="Login button", ref="button[type=submit]")
mcp__chrome__browser_type(element="email input", ref="input[name=email]", text="user@example.com")
mcp__chrome__browser_hover(element="Menu", ref="nav a")
```

### Step 4：验证

```python
mcp__chrome__browser_evaluate(expression="() => document.title")
mcp__chrome__browser_console()  # 检查 console 错误
mcp__chrome__browser_network()  # 检查 4xx/5xx
```

### Step 5：断言

```python
result = mcp__chrome__browser_evaluate(expression="() => window.location.pathname")
assert result == "/dashboard"
```

## 5 大实战场景

### 1. 表单测试

```python
mcp__chrome__browser_navigate(url="http://localhost:3000/signup")
mcp__chrome__browser_type(element="email", ref="input[name=email]", text="user@example.com")
mcp__chrome__browser_type(element="password", ref="input[name=password]", text="secret123")
mcp__chrome__browser_click(element="submit", ref="button[type=submit]")
mcp__chrome__browser_wait_for(text="Welcome")
mcp__chrome__browser_screenshot()
```

### 2. 调试 bug

```python
# 重现 bug
mcp__chrome__browser_navigate(url="http://localhost:3000/problem")
mcp__chrome__browser_console()  # 查 error
mcp__chrome__browser_network()  # 查 500
mcp__chrome__browser_evaluate(expression="() => { const err = window.__lastError; return err }")
```

### 3. 视觉回归

```typescript
import { test, expect } from '@playwright/test'

test('homepage looks correct', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveScreenshot('homepage.png', {
    maxDiffPixels: 100
  })
})
```

### 4. 跨浏览器

```typescript
// playwright.config.ts
export default {
  projects: [
    { name: 'chromium', use: devices['Desktop Chrome'] },
    { name: 'firefox', use: devices['Desktop Firefox'] },
    { name: 'webkit', use: devices['Desktop Safari'] },
  ]
}
```

### 5. 性能分析

```python
mcp__chrome__browser_evaluate(expression="""() => {
  const t = performance.timing
  return {
    loadTime: t.loadEventEnd - t.navigationStart,
    domTime: t.domComplete - t.domInteractive,
    renderTime: t.domContentLoadedEventEnd - t.navigationStart
  }
}""")
```

## 6 个反模式

- ❌ **sleep(1000)** — 用 `wait_for_selector` 替代
- ❌ **CSS 长链选择器** — 维护性差
- ❌ **每个测试独立登录** — 用 fixture
- ❌ **没清理** — 留下脏数据
- ❌ **没断言** — 跑完没失败
- ❌ **跑生产环境** — 永远用 staging

## 7 个最佳实践

1. **定位优先**：test-id > accessibility > CSS
2. **等待元素**：用 `wait_for_selector` 替代 sleep
3. **隔离测试**：每个测试独立数据
4. **失败有价值**：截图 + console + 网络
5. **CI 友好**：headless 模式 + 重试
6. **跨浏览器**：浏览器矩阵覆盖
7. **性能预算**：Lighthouse 集成

## 配合

- 配合 `browser` 插件（drifox 内置）
- 配合 `frontend-pro` 验证 UI 细节
- 配合 `python-pro` 写 pytest
- 配合 `react-pro` 走 React 性能规则

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
