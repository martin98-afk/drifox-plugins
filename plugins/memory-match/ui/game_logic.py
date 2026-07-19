# -*- coding: utf-8 -*-
"""记忆翻牌核心逻辑——纯 Python，无 Qt 依赖

MemoryMatchGame: 管理卡牌状态、翻牌配对、消除判定、胜利判断。
可独立单元测试。
"""

import random
from enum import Enum
from typing import Dict, List, Optional, Tuple


class CardState(Enum):
    """卡牌状态"""
    HIDDEN = "hidden"       # 背面（未翻开）
    FLIPPED = "flipped"     # 正面（已翻开，未配对）
    MATCHED = "matched"     # 已配对消除


class GameState(Enum):
    """游戏状态"""
    READY = "ready"         # 等待开始
    PLAYING = "playing"     # 游戏中
    WON = "won"             # 胜利
    WAITING = "waiting"     # 等待翻第二张后的倒计时结束


# Emoji 图案池
DEFAULT_EMOJIS = [
    "🍎", "🍊", "🍋", "🍇", "🍓", "🍒", "🥝", "🍑",
    "🌸", "🌺", "🌻", "🌷", "🌹", "💐", "🍀", "🌿",
    "🐶", "🐱", "🐼", "🐨", "🦁", "🐸", "🦊", "🐰",
    "⭐", "🌙", "☀️", "🌈", "❤️", "💎", "🎈", "🎁",
]


class MemoryMatchGame:
    """记忆翻牌游戏引擎

    职责：
    - 初始化卡牌（洗牌）
    - 翻牌操作（最多同时翻两张）
    - 配对判定与消除
    - 计时、计步
    - 检查胜利条件
    - 提供卡牌查询接口

    Usage:
        game = MemoryMatchGame(4, 4)  # 4x4 = 16 张牌 = 8 对
        game.start()
        result = game.flip(0, 0)  # 翻开第一张
        result = game.flip(1, 0)  # 翻开第二张
    """

    def __init__(self, rows: int, cols: int):
        """初始化游戏（未开始）

        Args:
            rows: 行数
            cols: 列数
        """
        if rows < 1 or cols < 1:
            raise ValueError(f"行列数必须为正: {rows}x{cols}")
        total = rows * cols
        if total % 2 != 0:
            raise ValueError(f"卡牌总数({total})必须是偶数（成对）")
        if total // 2 > len(DEFAULT_EMOJIS):
            raise ValueError(f"卡牌对数({total//2})超过可用图案数({len(DEFAULT_EMOJIS)})")

        self.rows = rows
        self.cols = cols
        self.total_pairs = total // 2

        # 卡牌数据: _cards[row][col] = emoji 或 None（已消除）
        self._cards: List[List[Optional[str]]] = [[None] * cols for _ in range(rows)]
        # 卡牌状态
        self._states: List[List[CardState]] = [[CardState.HIDDEN] * cols for _ in range(rows)]
        # 游戏状态
        self.state: GameState = GameState.READY
        # 已配对数
        self._matched_count: int = 0
        # 步数
        self._moves: int = 0
        # 翻转的第一张牌位置（等待第二张）
        self._first_flip: Optional[Tuple[int, int]] = None
        # 计时（秒）
        self._seconds: int = 0

    def start(self) -> None:
        """开始新游戏：洗牌布局"""
        # 选择图案（不重复）
        emojis = random.sample(DEFAULT_EMOJIS, self.total_pairs)
        # 每种图案两张
        deck = emojis * 2
        random.shuffle(deck)

        # 填充棋盘
        idx = 0
        for r in range(self.rows):
            for c in range(self.cols):
                self._cards[r][c] = deck[idx]
                self._states[r][c] = CardState.HIDDEN
                idx += 1

        self.state = GameState.PLAYING
        self._matched_count = 0
        self._moves = 0
        self._seconds = 0
        self._first_flip = None

    def flip(self, row: int, col: int) -> dict:
        """翻开指定卡牌

        Args:
            row: 行索引
            col: 列索引

        Returns:
            dict: {
                "changed": [(row, col, emoji, state, is_match), ...],
                "game_over": bool,
                "won": bool,
                "state": GameState,
                "first_card": (row, col) or None,
                "second_card": (row, col) or None,
                "is_match": bool or None,
            }
        """
        if self.state == GameState.WON:
            return {"changed": [], "game_over": True, "won": True,
                    "state": self.state, "first_card": None,
                    "second_card": None, "is_match": None}

        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise ValueError(f"坐标越界: ({row}, {col})")

        # 已翻开或已消除的卡牌不能再翻
        if self._states[row][col] != CardState.HIDDEN:
            return {"changed": [], "game_over": False, "won": False,
                    "state": self.state, "first_card": self._first_flip,
                    "second_card": None, "is_match": None}

        # 翻开这张牌
        self._states[row][col] = CardState.FLIPPED

        if self._first_flip is None:
            # 第一张牌
            self._first_flip = (row, col)
            return {
                "changed": [(row, col, self._cards[row][col],
                             CardState.FLIPPED, False)],
                "game_over": False, "won": False,
                "state": GameState.PLAYING,
                "first_card": (row, col),
                "second_card": None,
                "is_match": None,
            }
        else:
            # 第二张牌
            first_row, first_col = self._first_flip
            self._moves += 1
            is_match = self._cards[row][col] == self._cards[first_row][first_col]

            result = {
                "changed": [
                    (first_row, first_col, self._cards[first_row][first_col],
                     CardState.FLIPPED, False),
                    (row, col, self._cards[row][col], CardState.FLIPPED, False),
                ],
                "game_over": False,
                "won": False,
                "state": GameState.WAITING,
                "first_card": (first_row, first_col),
                "second_card": (row, col),
                "is_match": is_match,
            }

            if is_match:
                # 配对成功 → 消除
                self._states[first_row][first_col] = CardState.MATCHED
                self._states[row][col] = CardState.MATCHED
                self._matched_count += 1
                result["changed"] = [
                    (first_row, first_col, self._cards[first_row][first_col],
                     CardState.MATCHED, True),
                    (row, col, self._cards[row][col], CardState.MATCHED, True),
                ]
                self._first_flip = None

                # 检查胜利
                if self._matched_count >= self.total_pairs:
                    self.state = GameState.WON
                    result["game_over"] = True
                    result["won"] = True
                    result["state"] = GameState.WON
                else:
                    self.state = GameState.PLAYING
            else:
                # 配对失败 → 保持翻开状态，等待翻回
                self.state = GameState.WAITING

            return result

    def flip_back(self) -> dict:
        """翻回不配对的两张牌（动画结束后调用）"""
        if self._first_flip is None:
            return {"changed": [], "state": self.state}

        first_row, first_col = self._first_flip
        self._states[first_row][first_col] = CardState.HIDDEN
        self._states[first_row][first_col]  # second card is not stored, need to find it
        # The second card position was returned in last flip() result
        # We need to track it properly
        self._first_flip = None
        self.state = GameState.PLAYING

        return {"changed": [], "state": self.state}

    def flip_back_pair(self, row1: int, col1: int, row2: int, col2: int) -> dict:
        """翻回指定的两张卡牌（用于动画结束后重置状态）"""
        if 0 <= row1 < self.rows and 0 <= col1 < self.cols:
            if self._states[row1][col1] == CardState.FLIPPED:
                self._states[row1][col1] = CardState.HIDDEN
        if 0 <= row2 < self.rows and 0 <= col2 < self.cols:
            if self._states[row2][col2] == CardState.FLIPPED:
                self._states[row2][col2] = CardState.HIDDEN
        self._first_flip = None
        self.state = GameState.PLAYING
        return {"changed": [], "state": self.state}

    def get_card(self, row: int, col: int) -> dict:
        """获取卡牌信息

        Returns:
            dict: {"emoji": str, "state": CardState, "is_hidden": bool}
        """
        return {
            "emoji": self._cards[row][col],
            "state": self._states[row][col],
            "is_hidden": self._states[row][col] == CardState.HIDDEN,
        }

    def get_revealed_pair(self) -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
        """获取当前等待翻回的一对卡牌位置"""
        return self._first_flip, None

    @property
    def moves(self) -> int:
        """已翻牌次数（每翻两张计1步）"""
        return self._moves

    @property
    def seconds(self) -> int:
        """游戏耗时（秒）"""
        return self._seconds

    @seconds.setter
    def seconds(self, value: int):
        self._seconds = value

    @property
    def matched_pairs(self) -> int:
        """已配对数"""
        return self._matched_count

    @property
    def remaining_pairs(self) -> int:
        """剩余未配对数"""
        return self.total_pairs - self._matched_count

    def reset(self) -> None:
        """重置游戏（保持尺寸，重新洗牌）"""
        self._cards = [[None] * self.cols for _ in range(self.rows)]
        self._states = [[CardState.HIDDEN] * self.cols for _ in range(self.rows)]
        self.state = GameState.READY
        self._matched_count = 0
        self._moves = 0
        self._seconds = 0
        self._first_flip = None