---
name: frontend-pro
description: 前端开发最佳实践技能 — 涵盖 React/Vue/Angular、组件设计、CSS 方法论、无障碍(A11Y)规范、Web 性能优化、Web Components。触发关键词：前端、frontend、React、Vue、Angular、组件设计、CSS、性能优化、无障碍、a11y、WCAG、Web 标准、Web Vitals。
---

# frontend-pro 技能 — 前端开发最佳实践

本技能为 DriFox 提供前端开发的领域知识。当 AI 处理前端相关任务时，自动注入以下最佳实践。

## 1. 组件设计原则

### 单一职责原则 (SRP)

每个组件只做一件事。当组件变得复杂时，拆分为更小的子组件：

```
✅ 好：<UserCard>、<UserAvatar>、<UserBio> 分离
❌ 坏：<UserProfileCardWithAvatarAndBioAndStats> 大一统组件
```

### Props 设计

- **必选 props 使用 TypeScript 非可选类型**：`name: string`
- **可选 props 提供默认值**：`disabled?: boolean = false`
- **避免 prop drilling**：超过 3 层传值使用 Context / Store
- **不要传递不必要的 props**：只传递组件真正需要的

### 组件组合模式

```tsx
// 组合优于继承
function Dialog({ children, title }) {
  return (
    <div role="dialog" aria-modal="true">
      <header>{title}</header>
      <main>{children}</main>
    </div>
  );
}

// 使用 slot/children 保持灵活性
<Dialog title="确认">
  <p>确定要删除吗？</p>
  <button>取消</button>
  <button>确定</button>
</Dialog>
```

### 状态管理原则

| 状态类型 | 存放位置 | 举例 |
|---------|---------|------|
| 组件内部状态 | `useState` / `ref` | 弹窗开关、输入值 |
| 共享 UI 状态 | Context / Store | 主题、侧边栏 |
| 服务端状态 | React Query / SWR | 用户数据、列表 |
| URL 状态 | 路由参数 / URLSearchParams | 分页、筛选 |

## 2. 无障碍 (A11Y) 规范要点

### WAI-ARIA 使用规则

> **第一条规则**：如果能用原生 HTML 元素或属性实现，不要用 ARIA。

```tsx
// ✅ 正确：使用原生 button
<button onClick={handleClick}>提交</button>

// ❌ 错误：使用 div 模拟 button
<div onClick={handleClick} role="button">提交</div>
```

### 常用 ARIA 属性

| 属性 | 用途 | 示例 |
|------|------|------|
| `aria-label` | 为元素提供可访问名称 | `<button aria-label="关闭菜单">✕</button>` |
| `aria-describedby` | 关联描述文本 | `<input aria-describedby="hint-email">` |
| `aria-expanded` | 指示展开/折叠状态 | `<button aria-expanded={isOpen}>` |
| `aria-hidden` | 从可访问性树移除 | `<span aria-hidden="true">图标</span>` |
| `aria-live` | 通知动态内容变化 | `<div aria-live="polite">新消息</div>` |
| `role` | 定义元素语义角色 | `<div role="alert">错误</div>` |

### 键盘导航要求

- 所有交互元素可通过 Tab 聚焦
- 使用 `Enter` / `Space` 激活按钮
- 使用 `Escape` 关闭模态框/下拉菜单
- 使用 `Arrow` 键在菜单/选项卡中导航
- 模态框打开时焦点 trap，关闭后焦点返回触发元素

### 颜色对比度

| 文本类型 | WCAG AA (最低) | WCAG AAA (推荐) |
|---------|---------------|----------------|
| 普通文本 | 4.5:1 | 7:1 |
| 大文本 (≥18pt) | 3:1 | 4.5:1 |
| UI 组件/图形 | 3:1 | 不要求 |

### 表单无障碍

```tsx
// ✅ 正确：label 关联
<label htmlFor="email">邮箱</label>
<input id="email" type="email" />

// ❌ 错误：placeholder 作为 label
<input placeholder="邮箱" />

// ✅ 错误提示
<input
  aria-invalid={hasError}
  aria-describedby={hasError ? 'email-error' : undefined}
/>
{hasError && <span id="email-error">请输入有效邮箱</span>}
```

## 3. 性能最佳实践

### 代码分割与懒加载

```tsx
// React: 路由级代码分割
const Dashboard = lazy(() => import('./pages/Dashboard'));

// React: 组件级懒加载
const HeavyChart = lazy(() => import('./components/HeavyChart'));

// Vue: 异步组件
const AsyncComponent = defineAsyncComponent(() => import('./Component.vue'));
```

### 图片优化

```html
<!-- 响应式图片 -->
<img
  srcset="small.jpg 480w, medium.jpg 800w, large.jpg 1200w"
  sizes="(max-width: 600px) 480px, (max-width: 900px) 800px, 1200px"
  src="medium.jpg"
  alt="描述"
  loading="lazy"
/>

<!-- 现代格式 -->
<picture>
  <source srcset="image.avif" type="image/avif" />
  <source srcset="image.webp" type="image/webp" />
  <img src="image.jpg" alt="描述" />
</picture>
```

### Web Vitals 优化

| 指标 | 目标 | 优化方法 |
|------|------|---------|
| LCP (最大内容绘制) | < 2.5s | 预加载关键资源、优化图片 |
| FID (首次输入延迟) | < 100ms | 减少主线程阻塞、代码分割 |
| CLS (累积布局偏移) | < 0.1 | 预留图片尺寸、避免动态插入 |

### React 性能优化

```tsx
// 1. useMemo 缓存计算结果
const sortedList = useMemo(
  () => items.filter(x => x.active).sort(byDate),
  [items]
);

// 2. useCallback 稳定回调引用
const handleClick = useCallback((id) => {
  setItems(prev => prev.map(i => i.id === id ? {...i, active: true} : i));
}, []);

// 3. React.memo 避免不必要的重渲染
const ExpensiveList = memo(({ items }) => {
  return items.map(item => <Item key={item.id} {...item} />);
});
```

## 4. CSS 最佳实践

### CSS 方法论选择

| 方法论 | 适用场景 | 代表框架 |
|--------|---------|---------|
| BEM | 传统多页面应用 | — |
| CSS Modules | React/Vue 组件化 | Next.js, Vite |
| Tailwind/UnoCSS | 快速迭代、原子化 | 现代项目 |
| CSS-in-JS | 动态样式、主题切换 | Styled Components |

### 避免的 CSS 反模式

```css
/* ❌ 避免：ID 选择器（特异性过高） */
#header { background: blue; }

/* ❌ 避免：！important（难以覆盖） */
.button { color: red !important; }

/* ❌ 避免：内联样式（无法复用、无法主题化） */
<div style="margin: 10px; padding: 20px;">

/* ❌ 避免：Magic numbers */
.element { top: 37px; }

/* ✅ 正确：使用 CSS 变量 */
.element { top: var(--header-height); }
```

### 响应式设计

```css
/* 移动优先 */
.container {
  padding: 1rem;
}

@media (min-width: 768px) {
  .container {
    padding: 2rem;
    max-width: 1200px;
  }
}

/* 使用 CSS Grid 布局 */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
}
```

## 5. 常见前端反模式

### React 反模式

| 反模式 | 问题 | 正确做法 |
|--------|------|---------|
| 内联函数作为 props | 每次渲染创建新函数 | 使用 `useCallback` |
| 缺少 `key` | 列表渲染错误 | 使用稳定唯一 ID |
| 同步 setState 后读取 | 读取到旧值 | 使用回调函数或 useEffect |
| 过度使用 `useEffect` | 逻辑分散、难以追踪 | 优先在事件处理中更新 |
| `JSON.stringify` 在依赖中 | 每次渲染触发 | 使用 useRef 或拆分为多个 useEffect |

### Vue 反模式

| 反模式 | 问题 | 正确做法 |
|--------|------|---------|
| 直接修改 props | 违反单向数据流 | 使用 `emit` 或本地 data |
| 在模板中使用复杂计算 | 性能问题 | 使用 computed |
| 在 created 中调用 async | 不处理 Promise | 使用 `asyncData` 或 `setup` 中的 await |
| 滥用 `v-if` 切换大组件 | 重新创建开销大 | 使用 `v-show` |

### CSS 反模式

| 反模式 | 问题 | 正确做法 |
|--------|------|---------|
| 深度选择器 (`>>>` / `:deep()` | 样式泄漏 | 使用 CSS Modules 或 BEM |
| 硬编码颜色值 | 主题不支持 | 使用 CSS 变量 |
| 固定宽度容器 | 不响应式 | 使用 max-width + 百分比 |
| 忽略 z-index 管理 | 层叠冲突 | 使用 z-index 变量表 |

## 6. Web Components 注意事项

```js
// 自定义元素命名：必须包含连字符
class MyButton extends HTMLElement { }

// Shadow DOM 隔离样式
this.attachShadow({ mode: 'open' });

// observedAttributes 触发更新
static get observedAttributes() {
  return ['variant', 'disabled'];
}
```

## 参考资源

- [MDN Web Docs](https://developer.mozilla.org/zh-CN/)
- [React 官方文档](https://react.dev/)
- [Vue 官方文档](https://vuejs.org/)
- [WAI-ARIA 实践模式](https://www.w3.org/WAI/ARIA/apg/)
- [Web.dev 性能指南](https://web.dev/performance/)
- [CSS Triggers](https://csstriggers.com/)