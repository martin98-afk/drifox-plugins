# -*- coding: utf-8 -*-
"""接龙（Klondike）核心规则引擎 —— 纯 Python，无 Qt 依赖

Board: 管理 52 张牌的发牌、翻牌、移动校验与执行、胜利判断。
可独立单元测试。

规则（经典 Klondike · 翻一张 · 可无限重翻）：
- 7 列 tableau，第 i 列 i 张牌，末张明牌，余 24 张进牌堆
- 点牌堆翻 1 张到废牌堆；牌堆空后点击把废牌堆逆序重置回牌堆（无限次）
- tableau 红黑交替降序；空列只收 K（或以 K 开头的序列）
- 收牌堆按花色 A→K；已上收牌堆的牌不撤回
- 4 堆全部到 K 即胜利
"""

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

SUITS = ("spades", "hearts", "diamonds", "clubs")
RED_SUITS = frozenset({"hearts", "diamonds"})
RANK_A = 1
RANK_K = 13

# 移动源：("tableau", col, index) 或 ("waste",)
# tableau 的 index 为拖拽序列首张在该列中的位置
Source = tuple


@dataclass(frozen=True)
class Card:
    """一张扑克牌，rank: 1=A ... 11=J, 12=Q, 13=K"""

    suit: str
    rank: int

    @property
    def is_red(self) -> bool:
        return self.suit in RED_SUITS


@dataclass
class TableauCard:
    """牌桌上的牌（带明暗状态）"""

    card: Card
    face_up: bool


class Board:
    """接龙游戏引擎

    Usage:
        board = Board()
        board.new_game()
        board.draw()                        # 翻牌 / 重置牌堆
        board.move_to_tableau(src, col)     # 移动序列到牌桌列
        board.move_to_foundation(src)       # 单张上收牌堆
        board.is_won                        # 是否胜利
    """

    TABLEAU_COLS = 7

    def __init__(self, rng: Optional[random.Random] = None):
        self._rng = rng or random.Random()
        self._stock: List[Card] = []      # 列表尾 = 堆顶
        self._waste: List[Card] = []      # 列表尾 = 堆顶
        self._foundations: Dict[str, List[Card]] = {s: [] for s in SUITS}
        self._tableau: List[List[TableauCard]] = [
            [] for _ in range(self.TABLEAU_COLS)
        ]
        self._moves = 0

    # ── 初始化 ──

    def new_game(self) -> None:
        """洗牌发牌：7 列 tableau（第 i 列 i 张，末张明牌），余 24 张进牌堆"""
        deck = [Card(s, r) for s in SUITS for r in range(1, 14)]
        self._rng.shuffle(deck)
        self._stock = []
        self._waste = []
        self._foundations = {s: [] for s in SUITS}
        self._tableau = [[] for _ in range(self.TABLEAU_COLS)]
        self._moves = 0
        for col in range(self.TABLEAU_COLS):
            for _ in range(col + 1):
                card = deck.pop()
                face_up = len(self._tableau[col]) == col  # 末张明牌
                self._tableau[col].append(TableauCard(card, face_up))
        self._stock = deck  # 剩余 24 张，列表尾 = 堆顶

    # ── 牌堆操作 ──

    def draw(self) -> str:
        """点击牌堆：翻 1 张到废牌堆；牌堆空则把废牌堆逆序重置回牌堆

        Returns:
            "draw"    翻了一张
            "recycle" 废牌堆重置回牌堆
            "empty"   牌堆与废牌堆都空（理论上翻一张规则下不会发生）
        """
        if self._stock:
            self._waste.append(self._stock.pop())
            return "draw"
        if self._waste:
            self._stock = self._waste[::-1]
            self._waste = []
            return "recycle"
        return "empty"

    # ── 状态查询 ──

    def tableau_col(self, col: int) -> Tuple[TableauCard, ...]:
        return tuple(self._tableau[col])

    def waste_top(self) -> Optional[Card]:
        return self._waste[-1] if self._waste else None

    def waste_cards(self) -> Tuple[Card, ...]:
        return tuple(self._waste)

    def stock_count(self) -> int:
        return len(self._stock)

    def stock_cards(self) -> Tuple[Card, ...]:
        """牌堆内全部牌（列表尾 = 堆顶，仅供测试/展示）"""
        return tuple(self._stock)

    def foundation_top(self, suit: str) -> Optional[Card]:
        pile = self._foundations[suit]
        return pile[-1] if pile else None

    def foundation_count(self, suit: str) -> int:
        return len(self._foundations[suit])

    @property
    def moves(self) -> int:
        return self._moves

    @property
    def is_won(self) -> bool:
        return all(len(pile) == 13 for pile in self._foundations.values())

    # ── 拖拽源查询 ──

    def peek_source(self, src: Source) -> List[Card]:
        """查看从源 src 可拖出的牌序列（不摘除）

        tableau: index 起必须全部明牌，序列为 [index .. 列底]
        waste:   只有堆顶单张可拖
        返回空列表表示该源不可拖。
        """
        if src[0] == "tableau":
            _, col, index = src
            pile = self._tableau[col]
            if not (0 <= index < len(pile)):
                return []
            if not all(tc.face_up for tc in pile[index:]):
                return []
            return [tc.card for tc in pile[index:]]
        if src[0] == "waste":
            return [self._waste[-1]] if self._waste else []
        return []

    # ── 落点校验 ──

    def can_drop_tableau(self, cards: List[Card], col: int) -> bool:
        """序列首张能否落到 tableau 第 col 列"""
        if not cards or not (0 <= col < self.TABLEAU_COLS):
            return False
        first = cards[0]
        pile = self._tableau[col]
        if not pile:
            return first.rank == RANK_K
        top = pile[-1]
        return top.face_up and top.card.is_red != first.is_red \
            and top.card.rank == first.rank + 1

    def can_drop_foundation(self, card: Card) -> bool:
        """单张能否按花色上收牌堆（A 起升序）"""
        pile = self._foundations[card.suit]
        if not pile:
            return card.rank == RANK_A
        return pile[-1].rank == card.rank - 1

    # ── 移动执行 ──

    def move_to_tableau(self, src: Source, col: int) -> dict:
        """把 src 可拖序列移动到 tableau 第 col 列

        Returns:
            dict(ok, flipped, won)：flipped 表示源列翻开了新明牌
        """
        cards = self.peek_source(src)
        if not cards or not self.can_drop_tableau(cards, col):
            return {"ok": False, "flipped": False, "won": self.is_won}

        flipped = False
        if src[0] == "tableau":
            _, scol, sidx = src
            # 序列整体摘除
            moved = self._tableau[scol][sidx:]
            del self._tableau[scol][sidx:]
            self._tableau[col].extend(moved)
            # 翻开源列新顶牌
            pile = self._tableau[scol]
            if pile and not pile[-1].face_up:
                pile[-1].face_up = True
                flipped = True
        else:  # waste
            card = self._waste.pop()
            self._tableau[col].append(TableauCard(card, True))

        self._moves += 1
        return {"ok": True, "flipped": flipped, "won": self.is_won}

    def move_to_foundation(self, src: Source) -> dict:
        """把 src 的单张牌送上收牌堆（按花色）

        tableau 源必须是列末张；waste 源是堆顶。

        Returns:
            dict(ok, won)
        """
        cards = self.peek_source(src)
        if len(cards) != 1 or not self.can_drop_foundation(cards[0]):
            return {"ok": False, "won": self.is_won}

        if src[0] == "tableau":
            _, col, index = src
            pile = self._tableau[col]
            if index != len(pile) - 1:  # 只允许列末张
                return {"ok": False, "won": self.is_won}
            tc = pile.pop()
            self._foundations[tc.card.suit].append(tc.card)
            if pile and not pile[-1].face_up:
                pile[-1].face_up = True
        else:  # waste
            card = self._waste.pop()
            self._foundations[card.suit].append(card)

        self._moves += 1
        return {"ok": True, "won": self.is_won}
