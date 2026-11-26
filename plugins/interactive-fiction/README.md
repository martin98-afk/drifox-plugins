# 互动小说

你选，它写。装完就能开一局。

迁移自 [Treasure-hub-agent/interactive-fiction-skill](https://github.com/Treasure-hub-agent/interactive-fiction-skill)（MIT，v10.3.0），正文为上游中文原文。

## 它管什么

选项驱动的互动小说创作规范：开局方式、视角一致性、每回合字数区间、选项机制、存档系统、角色卡体系。不是「让模型随便讲故事」，而是有一套约束让长篇不崩。

| 部分 | 内容 |
|---|---|
| 三种叙事模式 | `shuangwen`（爽文）、`mainline`（主线）、`immersion`（沉浸） |
| 十一个扩展模块 | 角色卡、创世、深度角色塑造、蒸馏、事件行为、路线系统、配角、存储运行时、子代理模式、酒馆导入、标题蒸馏 |
| 参考手册 | 写作指南、亲密角色语气、原始角色数据、委托上下文、切换规则、外观、选项速查、部署、情绪升级母题、角色卡用法、使用指南、命令导航 |

## 四种开局

穿越、自创角色、创世、随机开局。

## 用法

- `开个互动小说`
- `加载小说包 <路径>`
- `玩个选项小说，题材是…`
- `把这段设定做成互动故事`

## 与上游的差异

- 裁掉 `docs/`（推广页）、`dev/`、`tests/`、`social-preview.png` 与英文 README：都是开发与宣传物料。
- 保留 `scripts/`（`novel.py` 等存读档工具）与 `extended/`（十一个扩展模块）。
- 未改任何正文。

## 图标

图标符号取自 [Lucide](https://lucide.dev) 的 `book-open`，ISC 许可，见 `LICENSE-lucide.txt`。

## 许可

MIT，见 `LICENSE`。上游另有 `DISCLAIMER.en.md`（内容免责说明），随包未收，需要时从上游取。