# webapp-testing

> Web 应用 E2E 测试助手 — 浏览器自动化 + Playwright + Chrome DevTools MCP + 测试策略 + 截图验证 + 调试技巧。

源自 [anthropics/skills/webapp-testing](https://github.com/anthropics/skills/tree/main/skills/webapp-testing)。本插件帮 AI 用浏览器自动化测试 Web 应用。

## 何时使用

- AI 写完 web 应用后，需要自动截图验证
- 跑回归测试
- 调试前端 bug
- 跨浏览器兼容性测试

## 核心工具

### 1. Chrome DevTools MCP（首选）

`@modelcontextprotocol/server-chrome-devtools` MCP server。

提供 12 大类工具：
- `browser_navigate` — 导航到 URL
- `browser_click` — 点击元素
- `browser_type` — 输入文本
- `browser_screenshot` — 截图
- `browser_console` — 读取 console
- `browser_network` — 读取网络请求
- `browser_evaluate` — 执行 JS
- `browser_hover` / `browser_drag` / `browser_select` — 交互
- `browser_pdf` / `browser_print` — 保存
- `browser_close` — 关闭

### 2. Playwright

```bash
npm install -D @playwright/test
npx playwright install
```

### 3. Cypress

```bash
npm install -D cypress
npx cypress open
```

## 适用场景

| 场景 | 推荐工具 |
|------|---------|
| AI 自动验证页面 | Chrome DevTools MCP |
| 跑 E2E 测试套件 | Playwright |
| 组件测试 | Storybook + Playwright |
| 视觉回归 | Playwright + pixelmatch |
| 性能测试 | Lighthouse + Puppeteer |
| 跨浏览器 | Playwright 多浏览器 |

## 工作流

### 1. 启动浏览器

```bash
# Chrome DevTools MCP
npx @modelcontextprotocol/server-chrome-devtools

# 或 Playwright
npx playwright codegen
```

### 2. 自动化测试用例

```typescript
import { test, expect } from '@playwright/test'

test('user can login', async ({ page }) => {
  await page.goto('/login')
  await page.fill('input[name="email"]', 'user@example.com')
  await page.fill('input[name="password"]', 'secret')
  await page.click('button[type="submit"]')
  await expect(page).toHaveURL('/dashboard')
  await expect(page.locator('h1')).toContainText('Welcome')
})
```

### 3. 视觉回归

```typescript
test('homepage looks correct', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveScreenshot('homepage.png', {
    maxDiffPixels: 100
  })
})
```

### 4. AI 验证

```python
# AI 任务：写一个登录页
# 验证流程：
mcp__chrome__browser_navigate(url="http://localhost:3000/login")
mcp__chrome__browser_screenshot()  # 截图
mcp__chrome__browser_evaluate(expression="() => document.title")  # 验证标题
mcp__chrome__browser_console()  # 检查 console 错误
```

## 实战模式

### 1. 表单测试

```python
mcp__chrome__browser_navigate(url="http://localhost:3000/signup")
mcp__chrome__browser_type(element="email input", ref="input[name=email]", text="user@example.com")
mcp__chrome__browser_type(element="password input", ref="input[name=password]", text="secret123")
mcp__chrome__browser_click(element="Submit button", ref="button[type=submit]")
mcp__chrome__browser_wait_for(text="Dashboard")
mcp__chrome__browser_screenshot()
```

### 2. 调试

```python
# 重现 bug
mcp__chrome__browser_navigate(url="http://localhost:3000/problem")
mcp__chrome__browser_console()  # 查 console
mcp__chrome__browser_network()  # 查网络
mcp__chrome__browser_evaluate(expression="() => { debugger; return state }")
```

### 3. 性能分析

```python
mcp__chrome__browser_navigate(url="http://localhost:3000")
mcp__chrome__browser_evaluate(expression="async () => { const t = performance.timing; return t.loadEventEnd - t.navigationStart }")
```

## 反模式

- ❌ **sleep(1000)** — 用 `wait_for_selector` 替代
- ❌ **CSS selector 长链** — 维护性差
- ❌ **每个测试独立登录** — 用 fixture
- ❌ **没清理** — 留下脏数据
- ❌ **没断言** — 跑完没失败
- ❌ **跑生产环境** — 永远用 staging

## 配合

- 配合 `browser` 插件（drifox 内置）
- 配合 `frontend-pro` 验证 UI 细节
- 配合 `python-pro` 写 pytest 测试

## 许可

MIT（anthropics/skills 本身）+ GPL-3.0-or-later（DriFox 适配层）
