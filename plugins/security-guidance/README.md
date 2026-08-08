# Security Guidance

> 原插件：Anthropic 官方 [security-guidance](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/security-guidance)（MIT，作者 David Dworken）

**Security Guidance** 对 AI 生成的代码做安全审查，覆盖常见 Web 漏洞类：注入攻击、XSS、SSRF、硬编码密钥、IDOR、认证绕过、不安全反序列化、路径穿越等。

## 本适配版实现

DriFox 版聚焦原版的第一层能力，以**静态模式检查**为主，零外部依赖：

- `PostToolUse`（Edit/Write/MultiEdit）触发：基于 25 条正则/子串规则检查写入内容
- 命中规则时，警告注入附加上下文，提醒 AI 修正或明确说明原因
- 规则集与上游 `patterns.py` 完全一致（硬编码密钥、`eval()`、`pickle.load`、`yaml.unsafe_load`、`innerHTML`、`child_process.exec` 等）

## 与原版差异

- 原版的 LLM diff 审查（Stop 阶段）与 SDK 驱动提交审查依赖 Claude API/SDK，**未移植**——DriFox 下 LLM 审查由主循环自然承担，本插件专注零依赖的静态规则层
- hook 已改写为 DriFox 原生 Python 实现（`hooks/security_guidance_hook.py`）

## 许可证

MIT（与上游一致）。