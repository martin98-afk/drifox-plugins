# frontend-pro — 前端开发增强插件

将前端开发最佳实践、无障碍(A11Y)检查和性能优化能力注入到 DriFox，让 AI 在编写前端代码时自动遵循行业标准。

## 功能

| 功能 | 说明 |
|------|------|
| 🎨 **组件生成** | `/frontend-pro component` 根据描述生成符合最佳实践的前端组件，支持 React/Vue/Svelte/Vanilla |
| ♿ **无障碍检查** | `/frontend-pro a11y` 对 HTML/JSX/Vue 模板进行无障碍检查，列出问题并给出修复方案 |
| 📚 **最佳实践注入** | Skills 系统自动将前端开发规范注入到 AI 上下文，覆盖组件设计、CSS、性能、A11Y |

## 安装

插件位于 `plugins/frontend-pro/`，DriFox 启动时自动发现。无需额外依赖。

## 命令

### `/frontend-pro component`

根据描述生成前端组件骨架：

```bash
# 生成 React 函数组件
/frontend-pro component --framework=react --style=hooks

# 生成 Vue 组合式组件
/frontend-pro component --framework=vue --style=functional

# 生成 Svelte 组件
/frontend-pro component --framework=svelte
```

**支持框架**：react / vue / svelte / vanilla
**支持风格**：functional（默认）/ class（仅 React）/ hooks（仅 React）

### `/frontend-pro a11y`

对指定文件执行无障碍检查：

```bash
# 检查单个文件
/frontend-pro a11y src/components/Button.tsx

# 检查多个文件
/frontend-pro a11y src/**/*.jsx
```

## 工作原理

```
用户调用命令
    │
    ▼
DriFox 加载 frontend-pro 命令 prompt
    │
    ├── /component → 根据 --framework 生成对应框架组件骨架
    │
    └── /a11y → 扫描 HTML/JSX 中的 A11Y 问题
                   │
                   ▼
              输出问题列表 + 修复建议
```

## 技能注入

当 AI 处理前端相关任务时，`frontend-pro` 技能自动注入以下知识：

- **组件设计原则**：单一职责、组合优于继承、Props 接口设计
- **无障碍规范**：WAI-ARIA、键盘导航、颜色对比度
- **性能最佳实践**：代码分割、懒加载、图片优化、Web Vitals
- **CSS 方法论**：BEM、CSS-in-JS、Tailwind 原子化
- **常见反模式**：内联函数作为 Props、N+1 查询、过度抽象

## 技术栈覆盖

| 框架 | 组件模式 | 状态管理 | 样式方案 |
|------|---------|---------|---------|
| React 18+ | Hooks / 函数组件 | Context / Zustand | CSS Modules / Tailwind |
| Vue 3 | 组合式 API | Pinia | Scoped CSS / UnoCSS |
| Svelte | 原生 Svelte 语法 | Svelte Store | Scoped CSS |
| Vanilla JS | ES Modules | — | 现代 CSS |

## 贡献

欢迎提交 Issue 或 PR 来扩展前端框架支持或补充最佳实践。