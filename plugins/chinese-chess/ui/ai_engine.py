# -*- coding: utf-8 -*-
"""中国象棋 AI 引擎 — 单轮 LLM 请求 + JSON 走法解析

EP3→EP4 重构：仿 prompt_enhancer 的 _EnhanceTask 范式，把原
EngineSession/executor/QThread/done_ev 流式链路替换为
单次 chat.completions.create() 调用：

1. ChessCard 经 ctx 拿到 main_widget，调 _get_llm_config()
2. _AIMoveTask.run() 调 _one_shot_ask() 拿响应
3. parse_move() 拆 JSON 走法；_is_legal() 校验
4. 非法或异常 → 兜底 random_legal_move()
5. 信号 done(move, source) 回到主线程落子

走子语义不变（解析失败/非法/无候选 → 随机兜底），但运行栈从 7 层压到 2 层。
"""

import random
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from .game_logic import (
    BLACK,
    RED,
    ROWS,
    COLS,
    board_to_ascii,
    gen_legal_moves,
    side_of,
)


# ── Prompt 构造 ──

COORD_GUIDE = (
    "坐标说明：列用 0..8（从左到右），行用 0..9（红方在底部 row 大，"
    "黑方在顶部 row 小）。红帅初始 (4,9)，黑将初始 (4,0)。"
)

SYSTEM_PROMPT = (
    "你是中国象棋高手。请根据局面选择最佳走法。\n"
    "严格要求：\n"
    '1. 仅输出 1 行 JSON，格式 {"from":[c1,r1],"to":[c2,r2]}，c 与 r 为整数\n'
    "2. 不要 markdown 代码块、不要多余文字、不要解释"
)


def build_user_prompt(board, side: str, history: List[str]) -> str:
    """构造用户提示：含坐标说明 + 历史 + ASCII 局面"""
    side_cn = "红方" if side == RED else "黑方"
    last = history[-1] if history else "（首步，无历史）"
    return (
        f"{COORD_GUIDE}\n\n"
        f"你是 {side_cn}，现在轮到你走。\n"
        f"上一步：{last}\n\n"
        f"当前局面（红方在底部，· 表示空格）：\n"
        f"{board_to_ascii(board)}\n\n"
        "请输出你的走法（仅 1 行 JSON）。"
    )


# ── 走法解析 ──

_MOVE_RE = re.compile(
    r'\{\s*"from"\s*:\s*\[?\s*(\d+)\s*,\s*(\d+)\s*\]?'
    r'\s*,\s*"to"\s*:\s*\[?\s*(\d+)\s*,\s*(\d+)\s*\]?\s*\}',
    re.IGNORECASE,
)


def parse_move(text: str) -> Optional[Tuple[int, int, int, int]]:
    """从 LLM 文本中提取走法。返回 (c1,r1,c2,r2) 或 None。"""
    if not text:
        return None
    # 思考型模型会把 <think>...</think> 混在 content 里：
    # - 已闭合：只取 </think> 之后的正文，避免思考中的试探性 JSON 被误匹配
    # - 未闭合：说明输出被截断，正文还没生成，直接判失败
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    elif "<think>" in text:
        return None
    m = _MOVE_RE.search(text)
    if not m:
        return None
    try:
        c1, r1, c2, r2 = (int(x) for x in m.groups())
    except ValueError:
        return None
    if not (0 <= c1 < COLS and 0 <= r1 < ROWS and 0 <= c2 < COLS and 0 <= r2 < ROWS):
        return None
    return c1, r1, c2, r2


def random_legal_move(board, side: str) -> Optional[Tuple[int, int, int, int]]:
    moves = gen_legal_moves(board, side)
    if not moves:
        return None
    return random.choice(moves)


def _strip_thinking(text: str) -> str:
    """剥离 <think>…</think> 段落（防御 reasoning 模型漏出思考）"""
    if not text:
        return text
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# ── 模型配置 ──


def _get_llm_config(main_widget) -> Optional[Dict[str, Any]]:
    """复用主程序当前会话模型配置（沿用 prompt_enhancer 思路）。

    main_widget._valid_configs 是私有状态；用户已接受 prompt_enhancer 同方式读取。
    """
    valid = getattr(main_widget, "_valid_configs", None)
    if not isinstance(valid, dict) or not valid:
        return None
    name = getattr(main_widget, "_current_provider_name", None) or "系统默认配置"
    return valid.get(name)


def _resolve_main_widget(card) -> Optional[Any]:
    """从 ChessCard 实例尽量找到 main_widget（多级兜底）。

    优先级：ctx["main_widget"] → card.parent() 链遍历找拥有
    _valid_configs 属性的祖先 → None
    """
    # 1) 上下文 provider
    provider = getattr(card, "_context_provider", None)
    if callable(provider):
        try:
            ctx = provider() or {}
            mw = ctx.get("main_widget")
            if mw is not None:
                return mw
        except Exception:
            pass

    # 2) 父链兜底：找带 _valid_configs 的祖先 QWidget
    cur = getattr(card, "parent", lambda: None)()
    for _ in range(15):  # 限深防止死循环
        if cur is None:
            break
        if hasattr(cur, "_valid_configs"):
            return cur
        cur = cur.parent() if hasattr(cur, "parent") else None
    return None


# ── 后台任务 ──


class _AISignals(QObject):
    """AI 走子信号（卡片线程 → 主线程）

    done(move, source) — move: (c1,r1,c2,r2) 或 None；
                          source: 'llm' / 'fallback' / 'error'
    error(reason)     — 严重错误（如对话服务未注入）
    """

    done = pyqtSignal(object, str)
    error = pyqtSignal(str)


class _AIMoveTask(QRunnable):
    """单轮 LLM 决策任务（仿 _EnhanceTask）。

    执行流程：
      _one_shot_ask() → 取文本 → parse_move() + _is_legal() → 合法即走法
      ├─ 非法：emit done(None, "fallback") 走 random_legal_move（若仍空 → done(None, "error")）
      └─ 异常：emit error(reason)
    """

    def __init__(
        self,
        board,
        side: str,
        history: List[str],
        llm_config: Dict[str, Any],
        signals: _AISignals,
        max_retries: int = 1,
    ):
        super().__init__()
        # 深拷贝棋盘，避免主线程修改影响后台任务
        self.board = [row[:] for row in board]
        self.side = side
        self.history = list(history or [])
        self.llm_config = llm_config
        self.signals = signals
        self.max_retries = max_retries
        self._lock = threading.Lock()  # 单实例自旋字段保留位（未来可扩展）
        self.setAutoDelete(True)

    # ================================================================
    #  主流程
    # ================================================================

    def run(self):
        try:
            user_prompt = build_user_prompt(self.board, self.side, self.history)
            text = self._one_shot_ask(user_prompt)
            move = parse_move(text) if text else None
            if move and self._is_legal(move):
                logger.info(f"[chinese-chess] LLM 走法: {move}")
                self.signals.done.emit(move, "llm")
                return
            # 诊断：把响应与模型配置暴露到日志，方便排障
            logger.warning(
                f"[chinese-chess] 解析失败/非法走法 (尝试上限 {self.max_retries + 1})→ 兜底: text={(text or '')[:200]!r}"
            )
            logger.warning(
                f"[chinese-chess] 模型配置: api_key={bool(self.llm_config.get('API_KEY'))}, "
                f"base_url={self.llm_config.get('API_URL')}, model={self.llm_config.get('模型名称')}"
            )
            fb = random_legal_move(self.board, self.side)
            if fb:
                logger.info(f"[chinese-chess] 兜底走法: {fb}")
                self.signals.done.emit(fb, "fallback")
            else:
                self.signals.error.emit("无合法走法可用（已被将死或困毙）")
                self.signals.done.emit(None, "error")
        except Exception as e:
            logger.exception(f"[chinese-chess] LLM 调用异常: {e}")
            self.signals.error.emit(f"LLM 调用异常: {e}")
            try:
                fb = random_legal_move(self.board, self.side)
                if fb:
                    self.signals.done.emit(fb, "fallback")
                else:
                    self.signals.done.emit(None, "error")
            except Exception:
                self.signals.done.emit(None, "error")

    # ================================================================
    #  单轮 ask
    # ================================================================

    def _one_shot_ask(self, user_prompt: str) -> Optional[str]:
        """单轮 chat.completions.create() + 至多 max_retries 次重试。

        每次返回剥离 <think> 段落后的 text；全失败返回 None。
        """
        from app.utils.http_client import build_openai_client

        api_key = self.llm_config.get("API_KEY", "")
        base_url = self.llm_config.get("API_URL")
        model = self.llm_config.get("模型名称", "gpt-4o")

        last_err: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            prompt = user_prompt
            if last_err:
                prompt += (
                    f"\n\n⚠️ 你上一次的回答不合法（{last_err}）。请重新仔细核对棋盘上棋子的位置，只输出 1 行 JSON。"
                )
            try:
                client = build_openai_client(api_key=api_key, base_url=base_url)
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=500,  # 给 reasoning 模型留缓冲；JSON 本身极短
                )
                msg = resp.choices[0].message
                # 记录 finish_reason + content 详情，帮助诊断「响应为空」
                fr = getattr(resp.choices[0], "finish_reason", None)
                logger.debug(
                    f"[chinese-chess] LLM 响应: model={model}, finish_reason={fr}, "
                    f"content_len={len(msg.content or '')}, usage={getattr(resp, 'usage', None)}"
                )
                text = (msg.content or "").strip()
                return _strip_thinking(text)
            except Exception as e:
                last_err = f"LLM 调用失败: {type(e).__name__}: {e}"
                logger.warning(f"[chinese-chess] LLM 尝试 {attempt + 1} 失败: {last_err}")
        return None

    # ================================================================
    #  校验
    # ================================================================

    def _is_legal(self, move: Tuple[int, int, int, int]) -> bool:
        """校验走法是否合法（由 side 方走且不送将）"""
        c1, r1, _c2, _r2 = move
        p = self.board[r1][c1]
        if p == "." or side_of(p) != self.side:
            return False
        return move in gen_legal_moves(self.board, self.side)


# ── 暴露入口（供 chess_board 调用） ──


def start_ai_move(card):
    """从 ChessCard 启动一次 AI 决策任务并连接信号。

    返回 True = 任务已派发；False = 缺少上下文/模型配置。
    """
    main_widget = _resolve_main_widget(card)
    if main_widget is None:
        logger.warning("[chinese-chess] 未找到 main_widget，LLM 不可用")
        return False

    llm_config = _get_llm_config(main_widget)
    if not llm_config:
        logger.warning("[chinese-chess] 未找到模型配置，LLM 不可用")
        return False

    signals = _AISignals()
    signals.done.connect(card._on_ai_done)
    signals.error.connect(card._on_ai_failed)

    # 历史构造（与原 _start_ai_move 同格式）
    history: List[str] = []
    for mv, sd in getattr(card, "_history", []):
        c1, r1, c2, r2 = mv
        side_cn = "红" if sd == RED else "黑"
        from .game_logic import coord_to_str  # 局部导入避免循环

        history.append(f"{side_cn}方 {coord_to_str(c1, r1)}-{coord_to_str(c2, r2)}")

    task = _AIMoveTask(
        board=card._board,
        side=card._side_to_move,
        history=history,
        llm_config=llm_config,
        signals=signals,
        max_retries=1,
    )

    pool = getattr(main_widget, "_gen_thread_pool", None) or QThreadPool.globalInstance()
    pool.start(task)
    card._ai_task = task
    return True
