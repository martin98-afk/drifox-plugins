---
description: 根据描述生成符合最佳实践的前端组件骨架，支持 React/Vue/Svelte/Vanilla 等主流框架
type: prompt
parameters:
  - name: "--framework="
    description: "目标框架：react / vue / svelte / vanilla（默认 react）"
    param_type: value
  - name: "--style="
    description: "组件风格：functional / class / hooks（默认 functional）"
    param_type: value
  - name: "<description>"
    description: "组件功能描述（如：用户头像卡片、可复用按钮、日历选择器）"
    param_type: positional
mutex_groups:
  framework: ["react", "vue", "svelte", "vanilla"]

### 参数说明

- `--framework`：目标框架，决定生成的代码模板
- `--style`：React 组件风格，仅对 React 生效（默认 functional）
  - `functional`：函数组件（推荐）
  - `hooks`：使用自定义 Hook 分离逻辑
  - `class`：Class 组件（遗留代码迁移场景）
prompt_sections:
  react: "react"
  vue: "vue"
  svelte: "svelte"
  vanilla: "vanilla"
allowed-tools:
  - read
  - write
  - edit
  - glob
hidden: false
---

# /frontend-pro component 命令 — 前端组件生成

你正在处理 `/frontend-pro component` 命令。根据用户提供的组件描述，生成符合最佳实践的前端组件代码。

## 📋 执行规则

1. **解析参数**：识别 `--framework`、`--style` 和 `<description>`
2. **确定框架**：默认 React functional 组件
3. **生成组件**：遵循该框架的最佳实践
4. **包含完整要素**：Props 类型定义、样式（如适用）、导出语句

## 组件设计原则

无论选择哪个框架，生成的组件必须遵循以下原则：

- **单一职责**：组件只做一件事
- **可复用性**：Props 设计支持不同场景
- **可访问性**：内置 A11Y 考虑（role、aria-*、keyboard 交互）
- **可测试性**：逻辑与 UI 分离

## React 组件生成

<!-- section:react -->

### 函数组件（默认）

使用函数组件 + TypeScript + Tailwind CSS 模式：

```tsx
// Button.tsx
import React from 'react';

interface ButtonProps {
  /** 按钮文案 */
  label: string;
  /** 点击事件处理 */
  onClick?: () => void;
  /** 按钮变体 */
  variant?: 'primary' | 'secondary' | 'ghost';
  /** 是否禁用 */
  disabled?: boolean;
  /** 额外类名 */
  className?: string;
}

/**
 * 通用按钮组件
 * @example
 * <Button label="提交" variant="primary" onClick={handleSubmit} />
 */
export const Button: React.FC<ButtonProps> = ({
  label,
  onClick,
  variant = 'primary',
  disabled = false,
  className = '',
}) => {
  const baseStyles = 'px-4 py-2 rounded-lg font-medium transition-colors';
  const variantStyles = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700',
    secondary: 'bg-gray-200 text-gray-800 hover:bg-gray-300',
    ghost: 'bg-transparent text-gray-600 hover:bg-gray-100',
  };

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`${baseStyles} ${variantStyles[variant]} ${className}`}
      aria-disabled={disabled}
    >
      {label}
    </button>
  );
};
```

### Hooks 模式（--style=hooks）

如果用户指定 `--style=hooks`，生成使用自定义 Hook 的版本：
- 抽离业务逻辑到 `useXXX` Hook
- 组件只负责渲染
- 支持 `useState`、`useEffect`、`useCallback` 等

### Class 组件模式（--style=class）

如果用户指定 `--style=class`，生成 Class 组件 + TypeScript：

```tsx
import React, { Component } from 'react';

interface CounterProps {
  initialCount?: number;
  onChange?: (count: number) => void;
}

interface CounterState {
  count: number;
}

export class Counter extends Component<CounterProps, CounterState> {
  constructor(props: CounterProps) {
    super(props);
    this.state = {
      count: props.initialCount ?? 0,
    };
  }

  private increment = () => {
    this.setState(
      (prev) => ({ count: prev.count + 1 }),
      () => this.props.onChange?.(this.state.count)
    );
  };

  private decrement = () => {
    this.setState(
      (prev) => ({ count: prev.count - 1 }),
      () => this.props.onChange?.(this.state.count)
    );
  };

  render() {
    return (
      <div className="counter">
        <button onClick={this.decrement} aria-label="减少">−</button>
        <span aria-live="polite">{this.state.count}</span>
        <button onClick={this.increment} aria-label="增加">+</button>
      </div>
    );
  }
}
```

## Vue 组件生成

<!-- section:vue -->

### 组合式 API（默认）

```vue
<!-- UserCard.vue -->
<template>
  <div class="user-card" :class="{ 'user-card--compact': compact }">
    <img
      :src="avatar"
      :alt="`${name}的头像`"
      class="user-card__avatar"
    />
    <div class="user-card__info">
      <h3 class="user-card__name">{{ name }}</h3>
      <p class="user-card__bio">{{ bio }}</p>
    </div>
    <slot name="actions" />
  </div>
</template>

<script setup lang="ts">
interface Props {
  name: string;
  avatar: string;
  bio?: string;
  compact?: boolean;
}

withDefaults(defineProps<Props>(), {
  bio: '',
  compact: false,
});
</script>

<style scoped>
.user-card {
  display: flex;
  gap: 1rem;
  padding: 1rem;
  border-radius: 0.75rem;
  background: white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.user-card__avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  object-fit: cover;
}

.user-card__name {
  font-weight: 600;
  color: #1a1a1a;
  margin: 0;
}

.user-card__bio {
  color: #6b7280;
  margin: 0.25rem 0 0;
}
</style>
```

## Svelte 组件生成

<!-- section:svelte -->

```svelte
<!-- Toggle.svelte -->
<script lang="ts">
  export let checked = false;
  export let label = '';
  export let disabled = false;

  function toggle() {
    if (!disabled) {
      checked = !checked;
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      toggle();
    }
  }
</script>

<button
  type="button"
  role="switch"
  aria-checked={checked}
  aria-label={label}
  {disabled}
  class="toggle"
  class:toggle--checked={checked}
  class:toggle--disabled={disabled}
  on:click={toggle}
  on:keydown={handleKeydown}
>
  <span class="toggle__thumb" />
</button>

<style>
  .toggle {
    position: relative;
    width: 48px;
    height: 24px;
    border-radius: 12px;
    background: #d1d5db;
    border: none;
    cursor: pointer;
    transition: background 0.2s;
  }

  .toggle--checked {
    background: #3b82f6;
  }

  .toggle--disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .toggle__thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: white;
    transition: transform 0.2s;
  }

  .toggle--checked .toggle__thumb {
    transform: translateX(24px);
  }
</style>
```

## Vanilla JS 组件生成

<!-- section:vanilla -->

```js
// Counter.js
/**
 * 无框架依赖的计数器组件
 * @param {HTMLElement} container 挂载容器
 * @param {Object} options 配置选项
 */
export function createCounter(container, options = {}) {
  const { initial = 0, step = 1, label = '计数' } = options;

  let count = initial;

  const template = `
    <div class="counter">
      <span class="counter__label">${label}: <strong>${count}</strong></span>
      <div class="counter__buttons">
        <button type="button" class="counter__btn counter__btn--minus" aria-label="减少">
          −
        </button>
        <button type="button" class="counter__btn counter__btn--plus" aria-label="增加">
          +
        </button>
      </div>
    </div>
  `;

  container.innerHTML = template;
  const minusBtn = container.querySelector('.counter__btn--minus');
  const plusBtn = container.querySelector('.counter__btn--plus');
  const display = container.querySelector('strong');

  minusBtn.addEventListener('click', () => {
    count -= step;
    display.textContent = count;
    container.dispatchEvent(new CustomEvent('change', { detail: { count } }));
  });

  plusBtn.addEventListener('click', () => {
    count += step;
    display.textContent = count;
    container.dispatchEvent(new CustomEvent('change', { detail: { count } }));
  });

  return {
    getCount: () => count,
    setCount: (value) => {
      count = value;
      display.textContent = count;
    },
    destroy: () => {
      minusBtn.removeEventListener('click', () => {});
      plusBtn.removeEventListener('click', () => {});
    },
  };
}
```

## 输出要求

1. **先分析需求**：理解用户描述的组件功能，确定需要的 Props
2. **选择合适框架**：根据 `--framework` 参数选择输出格式
3. **包含类型定义**：TypeScript 接口或 JSDoc 注释
4. **添加使用示例**：在注释中提供 `<ComponentName> ...` 用法
5. **考虑 A11Y**：确保语义化标签、ARIA 属性、键盘导航