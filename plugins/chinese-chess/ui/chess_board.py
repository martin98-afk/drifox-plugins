# -*- coding: utf-8 -*-
"""中国象棋浮动卡片 — 在 DriFox 中对弈大模型

游戏循环：
1. 玩家执红（先手），点击棋子选中 → 点击目标落子
2. 检查胜负（将死/困毙）→ 未结束则轮到 AI
3. AI 执黑：ai_engine.start_ai_move() 单轮调大模型 → 拿到走法后走子
4. 循环直到分出胜负

设计约束：
- 不导入 app.core 内部模块
- 游戏逻辑通过 ui/game_logic 模块（纯 Python）
- AI 调用通过 ui/ai_engine（读 main_widget._valid_configs 拿模型配置）
"""

from typing import Any, Callable, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from .game_logic import (
    BLACK,
    RED,
    ROWS,
    COLS,
    coord_to_str,
    gen_legal_moves,
    initial_board,
    make_move,
    side_of,
)
from .ai_engine import start_ai_move
from .widgets import ChessBoardView

# ── #7 扩展：右侧 AI 思考记录面板 ──
try:
    from .thought_panel import AIThoughtPanel  # type: ignore
except Exception:  # noqa: BLE001
    AIThoughtPanel = None  # type: ignore

# ── 模块级 try/except：qfluentwidgets 容错（参考 prompt-enhancer 行 92）──
try:
    from qfluentwidgets import InfoBar, InfoBarPosition  # type: ignore
except Exception:  # noqa: BLE001
    InfoBar = None  # type: ignore
    InfoBarPosition = None  # type: ignore

# ── 模块级 try/except：PluginConfigStore 容错（主程序未注入时不崩）──
try:
    from app.plugins.managers.plugin_config_store import (  # type: ignore
        PluginConfigStore,
    )
except Exception:  # noqa: BLE001
    PluginConfigStore = None  # type: ignore


# 默认值：与 plugin.json config_schema 一致；老配置缺字段时回退
DEFAULT_RED_CONTROL = "manual"   # 'manual' or 'ai'
DEFAULT_RED_MODEL = ""           # 留空 = 沿用主程序当前模型
DEFAULT_BLACK_MODEL = ""

# ── 模块级 try/except：theme 容错导入 ──
try:
    from . import theme as _theme  # type: ignore
except Exception:  # noqa: BLE001
    _theme = None  # type: ignore


def _load_config_defaults() -> dict:
    """从 PluginConfigStore 读取本插件配置；缺字段用默认值；主程序未注入时返回全默认。

    老配置无 red_control / red_model / black_model 字段时全用默认 → 向后兼容。
    """
    defaults = {
        "red_control": DEFAULT_RED_CONTROL,
        "red_model": DEFAULT_RED_MODEL,
        "black_model": DEFAULT_BLACK_MODEL,
    }
    if PluginConfigStore is None:
        return defaults
    try:
        store = PluginConfigStore()
        for k in defaults:
            v = store.get("chinese-chess", k)
            if v is None or v == "":
                continue
            if k == "red_control" and v in ("manual", "ai"):
                defaults[k] = v
            elif k in ("red_model", "black_model"):
                defaults[k] = "" if v == "__default__" else str(v)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[chinese-chess] 配置加载失败，使用默认: {e}")
    return defaults


class ChessCard(QWidget):
    """中国象棋浮动卡片"""

    closed = pyqtSignal()

    # 文本回退色（无主题上下文时使用）
    _FG = "rgba(0,0,0,0.85)"
    _FG_DIM = "rgba(0,0,0,0.5)"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        # ObjectName 让 theme.py QSS（#chessCardPanel 等）命中
        self.setObjectName("chessCard")
        self._context_provider: Optional[Callable[[], dict]] = None

        # ── 配置（从 PluginConfigStore 读取，向后兼容老配置无字段）──
        cfg = _load_config_defaults()
        self._red_control = cfg["red_control"]
        self._red_model = cfg["red_model"]
        self._black_model = cfg["black_model"]

        # 游戏状态
        self._board = initial_board()
        self._side_to_move = RED
        self._selected: Optional[tuple] = None
        self._game_over = False
        self._winner: Optional[str] = None  # RED / BLACK
        self._last_move: Optional[tuple] = None
        self._history: list = []  # [(move, side), ...]
        self._ai_task: Optional[Any] = None  # QRunnable 占位（新对局时用以丢弃结果）

        # 红条状态：追踪当前打开的解析失败 InfoBar
        self._error_bar = None

        # #7 扩展：AI 思考面板 + 步数计数器
        self._thought_panel: Any = None  # 由 _setup_ui 注入
        self._step_counter: int = 0       # 当前对局已记录步数
        self._gen_id = 0  # 对局代际计数器（新对局自增，用于丢弃旧 AI 任务结果）

        # 配置保存回调（外部配置卡注册时注入）
        self._config_change_callback: Optional[Callable[[dict], None]] = None

        self._setup_ui()
        self._refresh_status()
        self._board_view.set_pieces(self._board)
        self._board_view.clicked.connect(self._on_board_click)

        # 应用视觉主题（#5 视觉升级）
        self._apply_theme()

        # 绑定配置变更回调：从 ui 插件注册表查找已注册的设置卡实例
        try:
            from app.plugins.registries.ui_plugin_registry import UIPluginRegistry  # type: ignore

            reg = UIPluginRegistry.get_instance()
            for card in getattr(reg, "_settings_cards", {}).values() if hasattr(reg, "_settings_cards") else []:
                if hasattr(card, "register_change_callback"):
                    card.register_change_callback(self.update_config)
                    break
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[chinese-chess] 设置卡绑定跳过: {e}")

    # ── 上下文注入（FloatingCard 协议） ──

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider

    def show_card(self):
        """卡片显示时拉取主题（暂未自定义样式）"""
        self.setVisible(True)

    # ── 主题应用（#5 视觉升级） ──

    def _apply_theme(self) -> None:
        """应用 theme.py 的 QSS；失败时降级（不影响功能）。"""
        if _theme is None:
            return
        try:
            # 1) 主体容器
            full_qss = _theme.get_full_qss()
            if full_qss:
                self.setStyleSheet(full_qss)

            # 2) 棋盘容器用 QSS + 外发光
            from PyQt5.QtWidgets import QGraphicsDropShadowEffect
            from PyQt5.QtGui import QColor

            board_container = self._board_view.parent()  # wrap 容器（QHBoxLayout 内的 spacer 之间）
            if board_container is not None and board_container.objectName() != "chessBoardPanel":
                # 不动 wrap，让 ChessBoardView 自己 paintEvent 画木纹
                pass

            # 3) 给 ChessBoardView 自身设外发光（让棋盘从卡片中"凸出"）
            shadow = QGraphicsDropShadowEffect(self._board_view)
            shadow.setBlurRadius(20)
            shadow.setOffset(0, 4)
            shadow.setColor(QColor(0, 0, 0, 76))  # 30% 黑
            self._board_view.setGraphicsEffect(shadow)

            # 4) 状态标签/主操作按钮的 objectName 让 QSS 命中（如未设置）
            for w in self.findChildren(QLabel):
                if w.objectName() in ("", None):
                    if w is getattr(self, "_status_label", None):
                        w.setObjectName("chessStatusLabel")
                    elif w is getattr(self, "_hint_label", None):
                        w.setObjectName("chessHintLabel")
                    elif w is getattr(self, "_new_game_btn_ref", None):
                        w.setObjectName("chessPrimaryBtn")
            if hasattr(self, "_new_game_btn") and self._new_game_btn.objectName() in ("", None):
                # 「新对局」按钮当主操作按钮
                self._new_game_btn.setObjectName("chessPrimaryBtn")
                self._new_game_btn.setStyleSheet(_theme.get_full_qss())  # 让按钮 QSS 立即生效
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[chinese-chess] 应用主题失败（降级原样式）: {e}")

    # ── 配置热更新（外部设置卡保存时回调） ──

    def register_config_change_callback(self, cb: Callable[[dict], None]):
        """外部（config_card.py）注册配置变更回调；config_card 保存时通知。"""
        self._config_change_callback = cb

    def update_config(self, new_cfg: dict) -> None:
        """实时更新控制模式 / 模型选择，立即生效（无需重启插件）。

        new_cfg 字段（容错，缺字段用原值）：
            red_control: 'manual' or 'ai'
            red_model: 'Provider:Model' 或 ''
            black_model: 'Provider:Model' 或 ''
        """
        if "red_control" in new_cfg and new_cfg["red_control"] in ("manual", "ai"):
            old = self._red_control
            self._red_control = new_cfg["red_control"]
            if old != self._red_control:
                logger.info(f"[chinese-chess] 红方控制方式切换: {old} → {self._red_control}")
                self._refresh_status()
        if "red_model" in new_cfg:
            self._red_model = str(new_cfg["red_model"] or "")
        if "black_model" in new_cfg:
            self._black_model = str(new_cfg["black_model"] or "")
        logger.debug(
            f"[chinese-chess] 配置更新: red_control={self._red_control}, "
            f"red_model={self._red_model}, black_model={self._black_model}"
        )

    # ── UI 搭建 ──

    def _setup_ui(self):
        self.setMinimumWidth(820)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # 顶部状态栏（全局横跨，保留）
        top = QHBoxLayout()
        self._status_label = QLabel("轮到：红方（你）")
        f = QFont("Microsoft YaHei", 12)
        f.setBold(True)
        self._status_label.setFont(f)
        top.addWidget(self._status_label)
        top.addStretch(1)
        self._new_game_btn = QPushButton("新对局")
        self._new_game_btn.clicked.connect(self._new_game)
        self._new_game_btn.setFixedHeight(28)
        top.addWidget(self._new_game_btn)
        root.addLayout(top)

        # ── #7：水平 QSplitter（左侧棋盘 + 右侧 AI 思考面板） ──
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ── 左：原棋盘 + 提示 ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(8)

        self._board_view = ChessBoardView(cell=52, parent=left)
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(self._board_view)
        wrap.addStretch(1)
        # 转成 widget 容器
        wrap_w = QWidget()
        wrap_w.setLayout(wrap)
        left_layout.addWidget(wrap_w, 1)

        self._hint_label = QLabel("点击己方棋子选中 → 点击目标格落子")
        self._hint_label.setAlignment(Qt.AlignCenter)
        self._hint_label.setStyleSheet(f"color: {self._FG_DIM}; font-size: 11px;")
        left_layout.addWidget(self._hint_label)

        splitter.addWidget(left)

        # ── 右：AI 思考记录面板（容错） ──
        self._thought_panel = None
        if AIThoughtPanel is not None:
            try:
                self._thought_panel = AIThoughtPanel()
                splitter.addWidget(self._thought_panel)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[chinese-chess] AIThoughtPanel 创建失败: {e}")
                # fallback：用一个占位 QLabel 让布局不崩
                ph = QLabel("（AI 思考面板不可用）")
                ph.setAlignment(Qt.AlignCenter)
                splitter.addWidget(ph)
        else:
            ph = QLabel("（thought_panel 模块未加载）")
            ph.setAlignment(Qt.AlignCenter)
            splitter.addWidget(ph)

        # 默认宽度：左侧 800, 右侧 320（用户可拖拽）
        splitter.setSizes([800, 320])
        splitter.setStretchFactor(0, 1)   # 棋盘区域可拉伸
        splitter.setStretchFactor(1, 0)   # 面板固定大小

        root.addWidget(splitter, 1)

    # ── 状态显示 ──

    def _refresh_status(self):
        if self._game_over:
            if self._winner == RED:
                self._status_label.setText("🏆 红方胜利！点击「新对局」重开")
            elif self._winner == BLACK:
                self._status_label.setText("🏆 黑方胜利！点击「新对局」重开")
            else:
                self._status_label.setText("对局结束")
        else:
            side_cn = "红方（你）" if self._side_to_move == RED else "黑方（大模型）"
            self._status_label.setText(f"轮到：{side_cn}")

    # ── 新对局 ──

    def _stop_ai_worker(self):
        """停止 AI 任务（新对局 / 关闭卡片时）

        QRunnable 无法中途 kill HTTP，仅置 None 占位；后台任务返回时
        通过 _on_ai_done 检查 self._game_over / self._side_to_move 决定是否落子。
        """
        self._ai_task = None

    def _new_game(self):
        self._stop_ai_worker()
        self._gen_id += 1  # 代际自增：丢弃上一局遗留的 AI 任务结果
        self._board = initial_board()
        self._side_to_move = RED
        self._selected = None
        self._game_over = False
        self._winner = None
        self._last_move = None
        self._history = []
        self._board_view.set_pieces(self._board)
        self._board_view.set_selected(None)
        self._board_view.set_legal_targets([])
        self._board_view.set_last_move(None)
        self._hint_label.setText("点击己方棋子选中 → 点击目标格落子")
        self._close_error_bar()  # 新对局清空旧红条残留
        self._refresh_status()

    # ── 点击处理 ──

    def _on_board_click(self, c: int, r: int):
        # 对局已结束 → 拒绝任何点击
        if self._game_over:
            return
        # 走子动效期间（#6）→ 拒绝任何点击（状态机保护）
        if getattr(self._board_view, "_animating", False):
            return
        # 红方走子阶段：
        #   - manual：允许点击（玩家操作）
        #   - ai：拒绝点击（AI 在思考）
        # 黑方走子阶段：AI 思考中，一律拒绝（与原逻辑一致）
        if self._side_to_move == RED and self._red_control == "manual":
            pass  # fallthrough，允许红方手动点击
        elif self._side_to_move != RED:
            return
        else:  # RED + AI
            return

        piece = self._board[r][c]
        if self._selected is None:
            if piece != "." and side_of(piece) == RED:
                self._select_piece(c, r)
            return
        c1, r1 = self._selected
        if (c, r) == (c1, r1):
            self._select_piece(None)
            return
        legal = gen_legal_moves(self._board, RED)
        move = (c1, r1, c, r)
        if move in legal:
            # 手动走子：不传 source，跳过 AI 兜底校验分支
            self._apply_move(move)
        elif piece != "." and side_of(piece) == RED:
            # 切换选中
            self._select_piece(c, r)
        else:
            self._select_piece(None)

    def _select_piece(self, c=None, r=None):
        """选中 (c, r) 处的棋子；传 None 表示取消选中。"""
        pos = None if c is None else (c, r)
        self._selected = pos
        if pos is None:
            self._board_view.set_selected(None)
            self._board_view.set_legal_targets([])
            return
        self._board_view.set_selected(pos)
        targets = [(nc, nr) for (fc, fr, nc, nr) in gen_legal_moves(self._board, RED) if (fc, fr) == (c, r)]
        self._board_view.set_legal_targets(targets)

    # ── 走子 ──

    def _apply_move(self, move, source: Optional[str] = None):
        from .game_logic import is_checkmate, is_stalemate

        # 状态机保护：动效期间拒绝新走子（#6）
        if getattr(self._board_view, "_animating", False):
            logger.debug("[chinese-chess] 动效进行中，跳过 _apply_move")
            return

        # Blocker #1 兜底守卫：AI 来源的走法需校验当前局面合法性，
        # 防止旧代际 / 非法 AI 走法污染新棋局
        if source in ("llm", "fallback") and move not in gen_legal_moves(
            self._board, self._side_to_move
        ):
            logger.warning(
                "[chinese-chess] 旧/非法 AI 走法被拦截: %s (source=%s)", move, source
            )
            return

        side = self._side_to_move
        c1, r1, c2, r2 = move
        # 走子前快照 + 检查被吃
        piece_type = self._board[r1][c1]  # 移动的棋子字符
        captured_char = self._board[r2][c2]
        captured_info = None
        if captured_char and captured_char != ".":
            captured_info = (captured_char, c2, r2)

        # 给动效用快照
        self._board_view.set_board_snapshot(self._board)

        self._board = make_move(self._board, move)
        self._last_move = move
        self._history.append((move, side))
        self._board_view.set_pieces(self._board)
        self._board_view.set_last_move(move)
        self._selected = None
        self._board_view.set_selected(None)
        self._board_view.set_legal_targets([])

        # 触发动效（#6：起点蓝脉冲 + 终点金脉冲 + 路径箭头 + 被吃棋子淡出）
        try:
            self._board_view.animate_last_move(
                from_pos=(c1, r1),
                to_pos=(c2, r2),
                piece_type=piece_type,
                captured_piece=captured_info,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[chinese-chess] 走子动效触发失败: {e}")

        next_side = BLACK if side == RED else RED
        self._side_to_move = next_side

        # 检查胜负（对 next_side）
        if is_checkmate(self._board, next_side) or is_stalemate(self._board, next_side):
            self._game_over = True
            self._winner = side  # 刚走子的一方胜
            self._refresh_status()
            self._hint_label.setText("对局结束。点击「新对局」重开。")
            return

        self._refresh_status()

        # ── 控制模式分支 ──
        # 红方走子（我方）：
        #   - red_control=manual → 走子后切到黑方，黑方走子由 AI 接管
        #   - red_control=ai → 走子后仍轮到红方（继续 AI）
        # 黑方走子（对方）：始终由 AI 接管
        if self._side_to_move == RED and self._red_control == "ai":
            self._start_ai_move(side_label="red")
        elif self._side_to_move == BLACK:
            self._start_ai_move(side_label="black")

    # ── AI ──

    def _start_ai_move(self, side_label: Optional[str] = None):
        """启动 AI 任务。side_label: 'red' (我方) / 'black' (对方) / None (自动)"""
        side_cn = "红方（我方 AI）" if side_label == "red" else "黑方（对方）"
        self._status_label.setText(f"轮到：{side_cn} — 思考中…")
        self._hint_label.setText(f"🤖 {side_cn} 思考中…")
        ok = start_ai_move(self)
        if not ok:
            self._hint_label.setText("⚠️ 模型配置或上下文不可用，无法调用大模型")
            self._game_over = True
            self._winner = RED if side_label == "black" else BLACK
            self._refresh_status()

    def _on_ai_done(self, move, source, reason: str = "", gen_id: Optional[int] = None):
        self._ai_task = None
        # 代际守卫（Blocker #1）：旧对局遗留的 AI 任务结果直接丢弃
        if gen_id is not None and gen_id != self._gen_id:
            logger.debug("[chinese-chess] 旧代际 AI 结果被丢弃 gen_id=%s", gen_id)
            return
        # 用户已开新对局/关闭卡片 → 丢弃本次 AI 结果
        if self._game_over:
            return

        # ── source == error 或 fallback：弹红条 ──
        if source == "fallback":
            # 兜底走法 — 显示警告条 + 给出重试按钮（用户主动再发请求）
            self._show_parse_warning_bar(reason)
            # 兜底也算走子（不判负，让玩家继续），但 hint 文本明示
            if move is not None:
                c1, r1, c2, r2 = move
                src_cn = {"llm": "LLM", "fallback": "兜底", "error": "出错"}.get(source, source)
                self._hint_label.setText(
                    f"⚠️ AI 解析失败，已使用兜底走法 {coord_to_str(c1, r1)} → {coord_to_str(c2, r2)}（{src_cn}）"
                )
        elif source == "error" or move is None:
            # 致命错误：弹红条，让玩家决定重试还是开新局
            self._show_parse_error_bar(reason or "AI 未返回有效走法")
            self._hint_label.setText("AI 未能走子（见顶部红条），可点「重试」或「新对局」")
            return  # 不落子，等用户决定

        # 校验：被新对局打断 / 执子方已切换
        if self._side_to_move not in (RED, BLACK):
            return
        if self._side_to_move == RED and self._red_control == "manual":
            # 手动模式通常不会走这一步（黑方走完才是 AI），留作守卫
            pass

        if move is not None:
            c1, r1, c2, r2 = move
            if source == "llm":
                self._hint_label.setText(
                    f"AI 走法：{coord_to_str(c1, r1)} → {coord_to_str(c2, r2)}（LLM）"
                )
            # AI 走法：传 source 触发 _apply_move 合法性兜底校验
            self._apply_move(move, source=source)

    def _on_ai_failed(self, reason: str):
        # 仅记录，不覆盖 done 的 UI 行为
        logger.warning(f"[chinese-chess] AI failed: {reason}")

    # ── 红条 + 重试 ──

    def _show_parse_error_bar(self, reason: str) -> None:
        """AI 解析失败错误红条（带重试按钮）。"""
        self._close_error_bar()
        if InfoBar is None:
            # qfluentwidgets 不可用：只更新 hint_label
            self._hint_label.setText(f"⚠️ AI 解析失败：{reason[:200]}")
            return

        try:
            from qfluentwidgets import PushButton  # type: ignore

            content = f"AI 解析/调用失败。原因：{reason[:200]}"
            bar = InfoBar.error(
                title="❌ AI 解析失败",
                content=content,
                parent=self,
                duration=0,  # 常驻
                isClosable=True,
                position=InfoBarPosition.TOP,
            )
            # 附加重试按钮
            try:
                retry_btn = PushButton("🔄 重试", bar)
                retry_btn.clicked.connect(self.force_retry)
                bar.addWidget(retry_btn)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[chinese-chess] 重试按钮挂载失败: {e}")
            self._error_bar = bar
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[chinese-chess] InfoBar 创建失败: {e}")
            self._hint_label.setText(f"⚠️ AI 解析失败：{reason[:200]}")

    def _show_parse_warning_bar(self, reason: str) -> None:
        """AI 兜底走法警告条（不阻塞游戏，仅提示）。"""
        self._close_error_bar()
        if InfoBar is None:
            return
        try:
            content = f"原因：{reason[:200]}"
            bar = InfoBar.warning(
                title="⚠️ AI 解析失败，已使用兜底走法",
                content=content,
                parent=self,
                duration=5000,  # 5s 自动消失
                isClosable=True,
                position=InfoBarPosition.TOP,
            )
            self._error_bar = bar
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[chinese-chess] 警告条创建失败: {e}")

    def _close_error_bar(self) -> None:
        """关闭当前红条（如有）。"""
        bar = getattr(self, "_error_bar", None)
        if bar is not None:
            try:
                bar.close()
            except RuntimeError:
                pass  # 已销毁
            self._error_bar = None

    def force_retry(self) -> None:
        """用户主动重新请求当前局面 AI 走子。

        仅在：未结束 / 当前执子方为 AI 阵营 时启用。
        """
        if self._game_over:
            return
        # 红方 manual：当前是 RED+manual，玩家不应主动重试 AI
        if self._side_to_move == RED and self._red_control == "manual":
            return
        self._close_error_bar()
        # 停掉旧任务占位
        self._stop_ai_worker()
        if self._side_to_move == RED:
            self._start_ai_move(side_label="red")
        elif self._side_to_move == BLACK:
            self._start_ai_move(side_label="black")

    # ── AI 思考面板接入（#7） ──

    def _on_thought_received(self, side_cn: str, model_name: str, raw_text: str) -> None:
        """AI 后台任务 emit thought_received → 转给右侧面板。

        Args:
            side_cn: 执子方中文（'红' / '黑'）
            model_name: 模型显示名
            raw_text: LLM 原始响应（已剥离 <think>）
        """
        if self._thought_panel is None:
            return
        try:
            self._thought_panel.add_thought(side_cn, model_name, raw_text)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[chinese-chess] 思考面板 add_thought 失败: {e}")

    # ── 关闭清理 ──

    def _on_close(self):
        self._stop_ai_worker()
        self._close_error_bar()  # 关闭时清理常驻红条
        self.setVisible(False)
        self.closed.emit()
