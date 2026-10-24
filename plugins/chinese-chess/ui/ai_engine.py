# -*- coding: utf-8 -*-
"""中国象棋 AI 引擎 — 单轮 LLM 请求 + JSON 走法解析

EP3 迁移：LLM 调用经宿主 create_engine_session（EngineSession 契约）驱动，
不再自建 openai client 直发（非流式直发会被只支持流式的服务商 400 拒绝，
且绕过 Transport 层丢失伪装头/协议适配/max_tokens 钳制/智能重试）：

1. ChessCard 经 ctx 拿 main_widget + services
2. _resolve_side_config() 按红/黑方选择解析模型配置（关思考 + 低温度）
3. _AIMoveTask.run() 调 _one_shot_ask() → session.turn() 拿响应
4. parse_move() 拆 JSON 走法；_is_legal() 校验
5. 非法或异常 → 兜底 fallback_legal_move()
6. 信号 done(move, source) 回到主线程落子

走子语义不变（解析失败/非法/无候选 → 兜底），协议适配全部交宿主。
"""

import re
import threading
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

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
    "你是中国象棋高手。请根据局面从【合法走法清单】中选择最佳一步。\n"
    "决策优先级：\n"
    "1. 能将死对方的走法 > 吃子（车>炮>马>兵）且吃后不被反吃 > 解除将军 > 出子/护帅\n"
    "2. 严禁将/帅裸奔：走后不能让对方炮/车直接照面将军\n"
    "3. 禁止同一点对来回移动（重复走法浪费步数且长打判负）\n"
    "4. 优先保持车马炮灵活性，不要过早挪动九宫内士象\n"
    "严格要求：\n"
    '1. 仅输出 1 行 JSON，格式 {"from":[c1,r1],"to":[c2,r2]}，c 与 r 为整数\n'
    "2. from/to 必须逐字取自清单中某一条的起点与终点，禁止自创坐标\n"
    "3. 不要 markdown 代码块、不要多余文字、不要解释\n"
    "4. 不要输出 <think> 等思考过程内容，仅输出最终走法 JSON"  # 对齐 prompt-enhancer：显式禁止 thinking 块
)

# 棋子中文名（红大写/黑小写，board 存红大写）
_PIECE_CN_RED = {"K": "帅", "A": "仕", "B": "相", "N": "马", "R": "车", "C": "炮", "P": "兵"}
_PIECE_CN_BLACK = {"k": "将", "a": "士", "b": "象", "n": "马", "r": "车", "c": "炮", "p": "卒"}


def _legal_moves_section(board, side: str) -> str:
    """把 gen_legal_moves 结果渲染成提示词清单（棋子名 + 坐标）。"""
    cn = _PIECE_CN_RED if side == RED else _PIECE_CN_BLACK
    moves = gen_legal_moves(board, side)
    lines = []
    for c1, r1, c2, r2 in moves:
        name = cn.get(board[r1][c1], "?")
        cap = "吃" if board[r2][c2] != "." else ""
        lines.append(f"({c1},{r1})->({c2},{r2}) {name}{cap}")
    return "\n".join(lines)


def build_user_prompt(board, side: str, history: List[str]) -> str:
    """构造用户提示：坐标说明 + 近期历史（防重复）+ ASCII 局面 + 合法走法清单。

    附清单是走法质量的关键：弱模型自由生成坐标的非法率高（实测 glm-flash
    系三连非法触发兜底）；附近期历史防同子往返（实测将 (4,0)↔(4,1) 来回走）。
    """
    side_cn = "红方" if side == RED else "黑方"
    recent = history[-8:]
    last = recent[-1] if recent else "（首步，无历史）"
    hist_block = ""
    if recent:
        hist_block = (
            "【本局走法序列】（你方走法不得与序列中任一走法完全相同，避免往返）：\n"
            + "\n".join(f"{i + 1}. {m}" for i, m in enumerate(recent))
            + "\n\n"
        )
    return (
        f"{COORD_GUIDE}\n\n"
        f"你是 {side_cn}，现在轮到你走。\n"
        f"上一步：{last}\n\n"
        + hist_block
        + f"当前局面（红方在底部，· 表示空格）：\n"
        f"{board_to_ascii(board)}\n\n"
        f"【合法走法清单】（只能从中选一条）：\n"
        f"{_legal_moves_section(board, side)}\n\n"
        "请从清单中选择你的最佳走法（仅 1 行 JSON）。"
    )


# ── 走法解析 ──

_MOVE_RE = re.compile(
    r'\{\s*"from"\s*:\s*\[?\s*(\d+)\s*,\s*(\d+)\s*\]?'
    r'\s*,\s*"to"\s*:\s*\[?\s*(\d+)\s*,\s*(\d+)\s*\]?\s*\}',
    re.IGNORECASE,
)


def parse_move(text: str) -> Tuple[Optional[Tuple[int, int, int, int]], str]:
    """从 LLM 文本中提取走法。

    Returns:
        (move, error_msg)
        - move: (c1, r1, c2, r2) 或 None
        - error_msg: 空字符串表示成功；非空时含失败原因，供 UI 提示用
          可取值：empty_response / think_only / truncated / no_json /
                 invalid_int / out_of_range / no_normalized_path
    """
    if not text or not text.strip():
        return None, "empty_response"
    # 思考型模型会把 <think>...</think> 混在 content 里：
    # - 已闭合：只取 </think> 之后的正文，避免思考中的试探性 JSON 被误匹配
    # - 未闭合（说明输出被截断，正文还没生成） → 判失败
    if "<think>" in text:
        if "</think>" in text:
            text = text.split("</think>", 1)[1]
        else:
            return None, "think_only"
    text = text.strip()
    if not text:
        return None, "truncated"
    m = _MOVE_RE.search(text)
    if not m:
        return None, "no_json"
    try:
        c1, r1, c2, r2 = (int(x) for x in m.groups())
    except ValueError:
        return None, "invalid_int"
    if not (0 <= c1 < COLS and 0 <= r1 < ROWS and 0 <= c2 < COLS and 0 <= r2 < ROWS):
        return None, "out_of_range"
    return (c1, r1, c2, r2), ""


def fallback_legal_move(board, side: str) -> Optional[Tuple[int, int, int, int]]:
    """兜底走法（不再用 random 坐标）。

    策略：
    1. 优先选吃子走法（命值最高：先吃车→马→炮→卒→士→相）；多个则取第一个
    2. 无吃子走法时取第一个普通走法（按 gen_legal_moves 顺序，O(n)）
    3. 仍无 → None

    不引 random.seed 显式调用，行为完全确定 → 测试稳定。
    """
    moves = gen_legal_moves(board, side)
    if not moves:
        return None

    # 优先级：吃子价值
    def _capture_value(c2: int, r2: int) -> int:
        p = board[r2][c2]
        if p == ".":
            return 0
        # 红方优先级（值越大越优先吃）；黑方用同样顺序
        return _PIECE_VALUE.get(p.lower(), 0)

    sorted_moves = sorted(
        moves,
        key=lambda m: -_capture_value(m[2], m[3]),
    )
    chosen = sorted_moves[0]
    # 记录：可能不是吃子走法（target == '.'）
    return chosen


# 子力价值（吃子走法优先级排序，与 random 完全无关，可复现）
_PIECE_VALUE = {
    "r": 90,  # 车
    "n": 45,  # 马
    "c": 45,  # 炮
    "p": 10,  # 卒/兵
    "a": 20,  # 士
    "b": 20,  # 相
    "k": 1000,  # 将/帅
}


# 保留旧名以兼容历史调用（AI 引擎范围内仍可引用）
def random_legal_move(board, side: str) -> Optional[Tuple[int, int, int, int]]:
    """DEPRECATED: 旧随机兜底；新逻辑请用 fallback_legal_move()."""
    moves = gen_legal_moves(board, side)
    if not moves:
        return None
    return moves[0]  # 取第一个而非随机，保持可复现


# ── 单轮请求超时（关思考后普通模型 60s 足够）──
_TURN_TIMEOUT = 60.0


def _strip_thinking(text: str) -> str:
    """剥离 <think>…</think> 段落（防御 reasoning 模型漏出思考）"""
    if not text:
        return text
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# ── 模型配置 ──


def _get_llm_config(
    main_widget,
    provider: str = "",
    model: str = "",
    services: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """取模型配置（API_KEY / API_URL / 模型名称）。

    唯一正确通道 services["get_provider_config"]（宿主内存态明文 + 模型
    默认参数）；旧宿主兜底遍历 main_widget._valid_configs。
    绝不读 app.config 磁盘文件——密钥模式下 API_KEY 是密文。

    provider/model 为空时沿用主程序当前会话模型；提供时用指定服务商，
    且显式指名的 provider 失效时不静默串到别的服务商（返 None）。
    """
    if isinstance(services, dict):
        get_cfg = services.get("get_provider_config")
        if callable(get_cfg):
            try:
                cfg = get_cfg(provider, model)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[chinese-chess] get_provider_config 调用失败: {e}")
                cfg = None
            # 判据是「配置非空」非「key 非空」：免鉴权服务商 API_KEY 本就为空
            if isinstance(cfg, dict) and cfg:
                return dict(cfg)
            if provider:
                return None

    valid = getattr(main_widget, "_valid_configs", None)
    if not isinstance(valid, dict) or not valid:
        return None
    if provider:
        # 按 config_id / display_name / provider_name 匹配（与主程序五级解析同序）
        cfg = None
        if provider in valid:
            cfg = dict(valid[provider])
        else:
            for _cid, info in valid.items():
                if isinstance(info, dict) and provider in (
                    info.get("display_name"),
                    info.get("provider_name"),
                    info.get("name"),
                ):
                    cfg = dict(info)
                    break
        if cfg is None:
            return None
    else:
        name = getattr(main_widget, "_current_provider_name", None) or ""
        raw = valid.get(name)
        cfg = dict(raw) if isinstance(raw, dict) else None
        if cfg is None:
            return None
    if model:
        cfg["模型名称"] = model
    return cfg


def _resolve_side_config(
    main_widget,
    services: Optional[Dict[str, Any]],
    side: str,
    card,
) -> Optional[Dict[str, Any]]:
    """红/黑方各自生效的模型配置。

    设置卡红/黑模型格式 "Provider:Model"，空 = 沿用主程序当前会话模型；
    叠加象棋专用参数：关思考（走法无需 reasoning，提速）+ 低温度。
    """
    sel = str(getattr(card, "_red_model" if side == RED else "_black_model", "") or "")
    provider, model = "", ""
    if ":" in sel:
        provider, model = sel.split(":", 1)
    cfg = _get_llm_config(main_widget, provider, model, services)
    if not cfg:
        return None
    return {**cfg, "温度": 0.3, "思考模式": False}


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

    done(move, source, reason) — move: (c1,r1,c2,r2) 或 None；
                                 source: 'llm' / 'fallback' / 'error'
                                 reason: 失败/兜底的详细原因（成功时为空字符串）
    error(reason)             — 致命异常（如对话服务未注入），独立信号保留
    thought_received(side,    — #7 扩展：AI 思考原文（含 JSON / 思考块 / 解释）
                     model,     side: '红' / '黑'（执子方中文）
                     raw_text)  model: 模型显示名
                                raw_text: LLM 原始响应（已剥离 <think>）
    """

    done = Signal(object, str, str)
    error = Signal(str)
    thought_received = Signal(str, str, str)


class _AIMoveTask(QRunnable):
    """单轮 LLM 决策任务（仿 _EnhanceTask）。

    重试策略（修复前 Bug：空响应 / 解析失败 / finish_reason≠stop 不重试）：
      ├─ 空响应 / 仅有思考块 / 解析失败 → 重试，最多 2 次
      ├─ finish_reason="length" 或 "content_filter" → 重试
      ├─ 全部失败 → 走 fallback_legal_move（不再 random）
      └─ 全异常 → emit error(reason) + done(None, "error", reason)
    """

    # 重试上限：初次 + 1 次重试 = 最多 2 次调用（用户要求"重试 1 次"）
    MAX_RETRY_ATTEMPTS = 2

    def __init__(
        self,
        board,
        side: str,
        history: List[str],
        llm_config: Dict[str, Any],
        signals: _AISignals,
        max_retries: Optional[int] = None,
        prompt_suffix: Optional[str] = None,
        side_cn: Optional[str] = None,
        model_name: Optional[str] = None,
        services: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        # 深拷贝棋盘，避免主线程修改影响后台任务
        self.board = [row[:] for row in board]
        self.side = side
        # #7 扩展：执子方中文标签 / 模型显示名（用于 thought_received）
        self.side_cn = side_cn or ("红" if side == RED else "黑")
        self.model_name = model_name or llm_config.get("模型名称", "unknown")
        self.history = list(history or [])
        self.llm_config = llm_config
        self.signals = signals
        self.services = services or {}
        self.max_retries = max_retries if max_retries is not None else self.MAX_RETRY_ATTEMPTS - 1
        self.prompt_suffix = prompt_suffix  # 可选：追加到 system prompt 末尾的额外约束
        self._lock = threading.Lock()
        self.setAutoDelete(True)

    # ================================================================
    #  主流程
    # ================================================================

    def run(self):
        # 收集最后响应，给 UI 红条留 diagnostic
        last_text = ""
        last_finish_reason = None
        last_error = ""
        attempts = 0

        for attempt in range(self.max_retries + 1):
            attempts += 1
            try:
                user_prompt = build_user_prompt(self.board, self.side, self.history)
                text, finish_reason = self._one_shot_ask(user_prompt, retry_hint=last_error or None)
            except Exception as e:
                last_error = f"LLM 调用失败: {type(e).__name__}: {e}"
                last_text = ""
                last_finish_reason = None
                logger.warning(f"[chinese-chess] LLM 尝试 {attempt + 1} 异常: {last_error}")
                continue

            last_text = text or ""
            last_finish_reason = finish_reason

            # 1. 空响应 / 仅有思考块 → 重试
            if not last_text.strip():
                last_error = "empty_response"
                logger.warning(f"[chinese-chess] 尝试 {attempt + 1}: 空响应 → 重试")
                continue

            # 2. finish_reason = length / content_filter → 重试
            if finish_reason in ("length", "content_filter"):
                last_error = f"finish_reason={finish_reason}"
                logger.warning(f"[chinese-chess] 尝试 {attempt + 1}: {last_error} → 重试")
                continue

            # 3. 解析
            move, parse_err = parse_move(last_text)
            if move is None:
                last_error = parse_err or "parse_failed"
                logger.warning(f"[chinese-chess] 尝试 {attempt + 1}: 解析失败 {parse_err} → 重试")
                continue

            # 4. 合法性校验
            if not self._is_legal(move):
                last_error = "illegal_move"
                logger.warning(f"[chinese-chess] 尝试 {attempt + 1}: 非法走法 {move} → 重试")
                continue

            # ── 成功 ──
            logger.info(f"[chinese-chess] LLM 走法成功 (尝试 {attempt + 1}): {move}")
            self.signals.done.emit(move, "llm", "")
            return

        # ── 全部尝试后失败 → 兜底走法（非 random）──
        logger.warning(
            f"[chinese-chess] 全部 {attempts} 次尝试失败，最终兜底: "
            f"text={last_text[:200]!r}, finish_reason={last_finish_reason}, last_err={last_error}"
        )
        logger.warning(
            f"[chinese-chess] 模型配置: api_key={bool(self.llm_config.get('API_KEY'))}, "
            f"base_url={self.llm_config.get('API_URL')}, model={self.llm_config.get('模型名称')}"
        )

        fb = fallback_legal_move(self.board, self.side)
        if fb:
            logger.info(f"[chinese-chess] 兜底走法（非 random）: {fb}")
            # 兜底原因组装：含最后 1 次失败详情 + 最后响应前 500 字
            reason = (
                f"{last_error or 'unknown'} | "
                f"finish_reason={last_finish_reason} | "
                f"text={last_text[:500]!r}"
            )
            self.signals.done.emit(fb, "fallback", reason)
        else:
            err = "无合法走法可用（已被将死或困毙）"
            self.signals.error.emit(err)
            self.signals.done.emit(None, "error", err)

    # ================================================================
    #  单轮 ask
    # ================================================================

    def _one_shot_ask(
        self, user_prompt: str, retry_hint: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """经宿主 EngineSession（EP3）执行单轮 LLM 调用。

        原实现自建 openai client 直发**非流式** chat.completions.create，
        只支持流式的服务商直接 400（11101 Non-stream not supported）；
        且绕过 ModelAdapter/Serializer/Transport 后，伪装头、GPT-5 系
        /v1/responses 协议、max_tokens 钳制、智能重试全部失效。

        Returns:
            (text, finish_reason) — text 已剥离 <think>；宿主 ChatResult
            不暴露 finish_reason，恒为 None（截断场景由解析失败重试兜住）。

        Raises:
            RuntimeError / TimeoutError — 供 run() 计入重试。
        """
        create = (self.services or {}).get("create_engine_session")
        if not callable(create):
            raise RuntimeError(
                "主程序未提供 create_engine_session 服务，请升级 DriFox ≥ 0.5.10"
            )

        # 解析失败重试：prompt 强化追加（明确"仅输出标准 JSON"）
        extra_suffix = self.prompt_suffix or ""
        if retry_hint:
            extra_suffix += (
                f"\n\n⚠️ 你上一次的回答不合法（{retry_hint}）。"
                f"请仅输出标准 JSON，不要包含任何额外文字、注释、代码块或 <think> 段落。"
                f"只输出 1 行：{{\"from\":[c1,r1],\"to\":[c2,r2]}}"
            )

        session = create(
            "chinese-chess",
            model_config_override=self.llm_config,
            # 全局 hook 全跳过：象棋单步决策不吃 BuildSystemPrompt 等注入
            hook_policy_id="none",
        )
        try:
            result = session.turn(
                system=SYSTEM_PROMPT + extra_suffix,
                user=user_prompt,
                tools=[],
                timeout=_TURN_TIMEOUT,
            )
        finally:
            session.cleanup()

        if getattr(result, "timed_out", False):
            raise TimeoutError(f"LLM 响应超时（>{int(_TURN_TIMEOUT)}s）")
        if getattr(result, "cancelled", False):
            raise RuntimeError("已取消")
        err = getattr(result, "error", None)
        if err:
            raise RuntimeError(str(err))

        text = _strip_thinking(getattr(result, "text", "") or "")
        model = self.llm_config.get("模型名称", "unknown")
        logger.debug(f"[chinese-chess] LLM 响应: model={model}, content_len={len(text)}")

        # ── #7 扩展：emit 原始响应给右侧面板（已剥离 <think> 段但保留 JSON） ──
        if text:
            try:
                self.signals.thought_received.emit(
                    getattr(self, "side_cn", "?"),
                    getattr(self, "model_name", model),
                    text,
                )
            except Exception:  # noqa: BLE001
                logger.debug("[chinese-chess] thought_received emit 失败")

        return text, None

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

    # 上下文 services（EP3 契约：get_provider_config / create_engine_session）
    services: Dict[str, Any] = {}
    ctx_provider = getattr(card, "_context_provider", None)
    if callable(ctx_provider):
        try:
            services = (ctx_provider() or {}).get("services") or {}
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[chinese-chess] 读取上下文 services 失败: {e}")

    llm_config = _resolve_side_config(main_widget, services, card._side_to_move, card)
    if not llm_config:
        logger.warning("[chinese-chess] 未找到模型配置，LLM 不可用")
        return False

    signals = _AISignals()
    # Blocker #1：注入当前对局代际 id，旧任务结果在 _on_ai_done 被丢弃
    gen_id = getattr(card, "_gen_id", 0)
    signals.done.connect(
        lambda move, source, reason: card._on_ai_done(move, source, reason, gen_id)
    )
    signals.error.connect(card._on_ai_failed)
    # #7 扩展：连接思考面板信号；面板自身可能不存在（容错）
    try:
        panel = getattr(card, "_thought_panel", None)
        if panel is not None and hasattr(panel, "add_thought"):
            signals.thought_received.connect(
                lambda side_cn, model_name, raw_text: card._on_thought_received(
                    side_cn=side_cn, model_name=model_name, raw_text=raw_text
                )
            )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[chinese-chess] thought_panel 信号连接失败: {e}")

    # 历史构造（与原 _start_ai_move 同格式）
    history: List[str] = []
    for mv, sd in getattr(card, "_history", []):
        c1, r1, c2, r2 = mv
        side_cn = "红" if sd == RED else "黑"
        from .game_logic import coord_to_str  # 局部导入避免循环

        history.append(f"{side_cn}方 {coord_to_str(c1, r1)}-{coord_to_str(c2, r2)}")

    # #7：根据 _side_to_move 决定执子方中文 + 模型展示名
    side_cn_now = "红" if card._side_to_move == RED else "黑"
    model_now = llm_config.get("模型名称", "unknown")

    task = _AIMoveTask(
        board=card._board,
        side=card._side_to_move,
        history=history,
        llm_config=llm_config,
        signals=signals,
        max_retries=1,
        side_cn=side_cn_now,
        model_name=model_now,
        services=services,
    )

    pool = getattr(main_widget, "_gen_thread_pool", None) or QThreadPool.globalInstance()
    pool.start(task)
    card._ai_task = task
    return True
