#!/usr/bin/env python3
"""Hookify native hook evaluator — DriFox in-process Python hook.

Called by HookManager via type: "python" hooks.json registration.
Resolves hook rules from plugin's rules/ directory and evaluates them.

Function signature: function(event: str, context: dict) -> str
Return "" for no match, warning message for warn, or dict for block.
"""

import json
import os
import sys

# 插件根目录 = 本文件所在目录的父目录
_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from core.config_loader import load_rules
from core.rule_engine import RuleEngine

# 规则引擎实例（复用，避免每次重新创建）
_engine = RuleEngine()


def _get_event(tool_name: str) -> str:
    """从工具名推断 hook event"""
    if tool_name == 'Bash':
        return 'bash'
    elif tool_name in ('Edit', 'Write', 'MultiEdit'):
        return 'file'
    return 'all'


def _evaluate(event: str, context: dict) -> str:
    """加载规则并评估，返回匹配结果

    load_rules() 自动从以下位置搜索规则：
    1. 插件自身的 rules/ 目录
    2. 项目根目录的 .claude/ 目录（向后兼容）
    """
    event_type = _get_event(context.get('tool_name', ''))
    rules = load_rules(event=event_type)
    if not rules:
        return ""
    result = _engine.evaluate_rules(rules, context)
    if not result:
        return ""
    if result.get("decision") == "block":
        return json.dumps(result, ensure_ascii=False)
    return result.get("message", "")


def eval_pretooluse(event: str, context: dict) -> str:
    """PreToolUse hook 评估函数"""
    return _evaluate(event, context)


def eval_posttooluse(event: str, context: dict) -> str:
    """PostToolUse hook 评估函数"""
    return _evaluate(event, context)


def eval_stop(event: str, context: dict) -> str:
    """Stop hook 评估函数"""
    return _evaluate(event, context)


def eval_userprompt(event: str, context: dict) -> str:
    """UserPromptSubmit hook 评估函数"""
    return _evaluate(event, context)
