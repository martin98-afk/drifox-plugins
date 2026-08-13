# -*- coding: utf-8 -*-
"""
UserPromptSubmit Hook — 提示词自动优化（HookPrompt 的 DriFox Python 移植版）

原项目：https://github.com/KimYx0207/HookPrompt（MIT License）
行为对齐 Node 原版：
1. 用户输入进入模型前，先判断是否需要优化
2. 需要 → 注入「强制三段式格式说明 + 优化元模板 + 用户原文」，
   模型首条回复展示：📝 原始输入 → 🔄 优化后的理解 → ✅ 优化后的完整提示词
3. 无需优化（纯确认/斜杠命令/系统标签/过短无意图）→ 返回空串跳过

过滤逻辑与注入格式为原版 shouldFilter / buildFullTemplateInstruction 的直接移植，
仅把 stdin JSON 协议替换为 DriFox 的 context["message"]。
"""

import os
import re

_TEMPLATE_NAME = "prompt_optimizer_meta.md"

# ---- 过滤规则（移植自原版 shouldFilter） ----

# Claude Code 内部系统消息标签（精确匹配，避免误杀用户 HTML/JSX）
_SYSTEM_TAG_PATTERN = re.compile(
    r"^<(task-notification|system-reminder|tool-result|tool-use|agent-response|claude-internal)[\s>]"
)

# 简单交互式回复 - 不需要优化
_SIMPLE_RESPONSES = {
    "好的",
    "是的",
    "继续",
    "谢谢",
    "ok",
    "OK",
    "yes",
    "YES",
    "no",
    "NO",
    "确认",
    "取消",
    "好",
    "行",
    "可以",
    "不",
    "嗯",
    "y",
    "n",
    "Y",
    "N",
}

# 短诊断/修复/优化意图（去空白后匹配）
_DIAGNOSTIC_PATTERNS = [
    re.compile(
        r"^(这个|这|这里|刚才|上面)?(不行|不对|有问题|报错了?|失败了?|错了|坏了|乱了|太乱了?|不好看|卡住了?|跑不通|看不懂)$",
        re.I,
    ),
    re.compile(
        r"^(帮我)?(看看|看下|检查|排查|修复|修一下|改一下|优化一下|整理一下)$", re.I
    ),
    re.compile(r"^(this|it|that)?(doesnot|doesnt|isnot|isnt)?(work|working)$", re.I),
    re.compile(
        r"^(error|failed|failure|broken|bug|pleasecheck|checkthis|fixthis)$", re.I
    ),
]


def _has_short_task_intent(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return any(p.match(compact) for p in _DIAGNOSTIC_PATTERNS)


def should_filter(message: str) -> bool:
    """判断输入是否应跳过优化。True=跳过，False=需要优化。"""
    text = (message or "").strip()
    if not text:
        return True
    # 斜杠命令不优化（保留：DriFox 内置命令）
    if text.startswith("/"):
        return True
    # 系统消息标签不优化
    if _SYSTEM_TAG_PATTERN.match(text):
        return True
    # 简单回复不优化
    if text in _SIMPLE_RESPONSES:
        return True
    # 短诊断输入仍要优化
    if _has_short_task_intent(text):
        return False
    # 过短且无可执行意图
    if len(text) < 10:
        return True
    return False


# ---- 注入文本构建（移植自原版 buildFullTemplateInstruction + fencedBlock） ----


def _fenced_block(content: str, lang: str = "text") -> str:
    """构造安全 fenced code block：内容含反引号时自动加长围栏。"""
    text = str(content or "")
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{lang}\n{text}\n{fence}"


def _read_template() -> str:
    """读取优化元模板（优先插件目录，兜底当前目录）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(here, _TEMPLATE_NAME)]
    for fp in candidates:
        if os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as f:
                return f.read()
    return ""


def build_instruction(message: str, template: str = "") -> str:
    """构建注入文本：强制格式说明 + 优化元模板 + 用户原文。"""
    if not template:
        template = _read_template()
    user_block = _fenced_block(message, "text")
    raw_example = _fenced_block("[用户的原话，逐字保留]", "text")
    prompt_example = _fenced_block("[优化后的结构化提示词]", "markdown")
    return f"""<MANDATORY_FORMAT_INSTRUCTION>
【回复格式说明】

本次用户请求的第一条面向用户的 assistant 回复必须严格按以下顺序输出，不得跳过任何部分。

重要：这是单次首条回复格式，不是每条消息的全局格式。只允许在本轮第一条面向用户的 assistant 消息开头展示一次；完成这组优化展示后，后续 commentary/progress/final/review/verification 消息必须直接继续任务，不得再次重复"原始输入 / 优化后的理解 / 优化后的完整提示词"三段。

1. 第一行必须是：📝 **原始输入**：

2. 然后必须立刻输出一个 fenced code block，逐字放入用户原始输入。禁止把原始输入裸贴在 Markdown 正文里，避免其中的 #、##、列表、图片路径或代码片段被渲染成标题或格式。

示例：

{raw_example}

3. 然后是：
🔄 **优化后的理解**：
- **Context（上下文）**：[推断的场景、身份、目标]
- **Task（任务）**：[明确的动作 + 要求]
- **Format（格式）**：[期望的输出形式]

4. 然后是：
✅ **优化后的完整提示词**：

优化后的完整提示词正文必须放入 fenced code block。禁止把完整提示词正文裸贴在 Markdown 正文里，避免被渲染成大标题。

示例：

{prompt_example}

5. 最后是分隔线 --- 后执行任务内容

请只在本轮第一条回复开头展示对用户输入的理解（原始输入 + 优化后的结构化版本），然后再执行任务。
</MANDATORY_FORMAT_INSTRUCTION>

---

{template}

---

## 用户原始输入（已安全包裹，请从代码块中读取原文）

{user_block}"""


def hook(event: str, context: dict) -> str:
    """UserPromptSubmit 事件入口。返回注入文本；无需优化时返回空串。"""
    message = (context or {}).get("message", "")
    if should_filter(message):
        return ""
    return build_instruction(message)
