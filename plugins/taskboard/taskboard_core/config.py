# -*- coding: utf-8 -*-
"""taskboard 配置 — 看板列定义、智能体映射与信号协议"""

# 看板列（有序：todo → inprogress → review → done）
COLUMNS = ["todo", "inprogress", "review", "done"]

# 列元数据：标题 / 绑定智能体 / 强调色（列头圆点与卡片描边）
COLUMN_META = {
    "todo": {
        "title": "待办",
        "agent": "tb_todo",
        "accent": "#8A8F98",
    },
    "inprogress": {
        "title": "进行中",
        "agent": "tb_build",
        "accent": "#3B82F6",
    },
    "review": {
        "title": "审查",
        "agent": "tb_review",
        "accent": "#F59E0B",
    },
    "done": {
        "title": "完成",
        "agent": "tb_done",
        "accent": "#22C55E",
    },
}

# 智能体去留信号（响应末尾输出，worker 解析）
SIGNAL_ADVANCE = "TASK_ADVANCE"  # 推进到下一列
SIGNAL_HOLD = "TASK_HOLD"        # 保留当前列（等待用户再次触发）
SIGNAL_DROP = "TASK_DROP"        # 删除该任务

VALID_SIGNALS = {SIGNAL_ADVANCE, SIGNAL_HOLD, SIGNAL_DROP}

# 看板数据持久化目录（位于当前工作目录下）
BOARD_DIR_NAME = ".taskboard"
BOARD_FILE_NAME = "board.json"
REPORTS_DIR_NAME = "reports"
LOGS_DIR_NAME = "logs"

# 单任务单次处理的超时（秒）：一次 execute 内部含多轮工具循环，
# 此处为兜底上限，超时视为失败保留当前列
TASK_TIMEOUT_SECONDS = 600

# 摘要截断长度（任务卡片显示）
SUMMARY_MAX_CHARS = 120


def next_column(status: str) -> str:
    """返回下一列；done 为终点返回自身"""
    try:
        idx = COLUMNS.index(status)
    except ValueError:
        return status
    return COLUMNS[min(idx + 1, len(COLUMNS) - 1)]


def prev_column(status: str) -> str:
    """返回上一列；todo 为起点返回自身"""
    try:
        idx = COLUMNS.index(status)
    except ValueError:
        return status
    return COLUMNS[max(idx - 1, 0)]
