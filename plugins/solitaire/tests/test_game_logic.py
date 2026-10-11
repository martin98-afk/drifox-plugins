"""接龙规则引擎测试"""
import random
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ui.game_logic import Board, Card, SUITS


def make_board(seed: int = 42) -> Board:
    board = Board(random.Random(seed))
    board.new_game()
    return board


def card(suit: str, rank: int) -> Card:
    return Card(suit, rank)


# ── 初始化 ──

def test_new_game_deal():
    """7 列张数 1..7，总 28 张，stock 24，waste 0"""
    board = make_board()
    counts = [len(board.tableau_col(c)) for c in range(7)]
    assert counts == [1, 2, 3, 4, 5, 6, 7]
    assert board.stock_count() == 24
    assert board.waste_top() is None
    total = sum(counts)
    assert total == 28


def test_new_game_face_up():
    """每列只有末张明牌"""
    board = make_board()
    for col in range(7):
        pile = board.tableau_col(col)
        for i, tc in enumerate(pile):
            assert tc.face_up == (i == len(pile) - 1)


def test_new_game_full_deck():
    """52 张牌不重不漏"""
    board = make_board()
    seen = set()
    for col in range(7):
        for tc in board.tableau_col(col):
            seen.add((tc.card.suit, tc.card.rank))
    for c in board.stock_cards():
        seen.add((c.suit, c.rank))
    assert board.waste_top() is None
    full = {(s, r) for s in SUITS for r in range(1, 14)}
    assert seen == full


# ── 翻牌与重置 ──

def test_draw_and_recycle():
    """翻 24 次耗尽 stock，recycle 后 stock 恢复 24，可无限重翻"""
    board = make_board()
    for _ in range(24):
        assert board.draw() == "draw"
    assert board.stock_count() == 0
    assert board.waste_top() is not None
    assert board.draw() == "recycle"
    assert board.stock_count() == 24
    assert board.draw() == "draw"
    assert board.stock_count() == 23


def test_recycle_preserves_order():
    """重置后翻牌顺序与首轮一致"""
    board = make_board()
    first_round = []
    for _ in range(24):
        board.draw()
        first_round.append(board.waste_top())
    board.draw()  # recycle
    for i in range(24):
        board.draw()
        assert board.waste_top() == first_round[i]


# ── tableau 落点校验 ──

def test_can_drop_tableau_empty_col_king_only():
    board = make_board()
    board._tableau[0] = []  # 清空列 0
    assert board.can_drop_tableau([card("spades", 13)], 0)
    assert not board.can_drop_tableau([card("spades", 12)], 0)


def test_can_drop_tableau_alternating_colors():
    board = make_board()
    # 6♥ 上可放 5♠ / 5♣，不可放 5♦ / 5♥ / 7♠
    board._tableau[0] = []
    from ui.game_logic import TableauCard
    board._tableau[0].append(TableauCard(card("hearts", 6), True))
    assert board.can_drop_tableau([card("spades", 5)], 0)
    assert board.can_drop_tableau([card("clubs", 5)], 0)
    assert not board.can_drop_tableau([card("diamonds", 5)], 0)
    assert not board.can_drop_tableau([card("hearts", 5)], 0)
    assert not board.can_drop_tableau([card("spades", 7)], 0)


def test_peek_source_blocked_by_face_down():
    """暗牌之后的牌不可拖"""
    board = make_board()
    from ui.game_logic import TableauCard
    board._tableau[0] = [
        TableauCard(card("hearts", 6), False),
        TableauCard(card("spades", 5), True),
    ]
    assert board.peek_source(("tableau", 0, 0)) == []
    assert board.peek_source(("tableau", 0, 1)) == [card("spades", 5)]


# ── tableau 移动执行 ──

def test_move_to_tableau_from_tableau_flips():
    """列间移动 + 源列翻牌 + 计步"""
    board = make_board()
    from ui.game_logic import TableauCard
    board._tableau[0] = [TableauCard(card("hearts", 10), False),
                         TableauCard(card("spades", 9), True)]
    board._tableau[1] = [TableauCard(card("diamonds", 10), True)]
    result = board.move_to_tableau(("tableau", 0, 1), 1)
    assert result["ok"] and result["flipped"]
    assert board.moves == 1
    # 9♠ 叠到 10♦ 下
    pile1 = board.tableau_col(1)
    assert [tc.card for tc in pile1] == [card("diamonds", 10), card("spades", 9)]
    # 源列 10♥ 翻开
    assert board.tableau_col(0)[0].face_up


def test_move_sequence_together():
    """明牌序列整体拖动"""
    board = make_board()
    from ui.game_logic import TableauCard
    board._tableau[0] = [
        TableauCard(card("spades", 12), True),
        TableauCard(card("hearts", 11), True),
        TableauCard(card("clubs", 10), True),
    ]
    board._tableau[1] = [TableauCard(card("clubs", 12), True)]
    result = board.move_to_tableau(("tableau", 0, 1), 1)
    assert result["ok"]
    pile = board.tableau_col(1)
    assert [tc.card.rank for tc in pile] == [12, 11, 10]


def test_move_to_tableau_rejects_illegal():
    board = make_board()
    from ui.game_logic import TableauCard
    board._tableau[0] = [TableauCard(card("hearts", 6), True)]
    # 6♥ 不能放到暗牌列顶（顶牌非明牌）
    board._tableau[1] = [TableauCard(card("clubs", 7), False)]
    result = board.move_to_tableau(("tableau", 0, 0), 1)
    assert not result["ok"]
    assert board.moves == 0
    # 原牌未动
    assert board.tableau_col(0)[0].card == card("hearts", 6)


def test_move_to_empty_col_requires_king():
    board = make_board()
    from ui.game_logic import TableauCard
    board._tableau[0] = [TableauCard(card("hearts", 6), True)]
    board._tableau[2] = []  # 清空列 2，非 K 不可进
    result = board.move_to_tableau(("tableau", 0, 0), 2)
    assert not result["ok"]


# ── 收牌堆 ──

def test_foundation_ace_first_and_ascending():
    board = make_board()
    board._waste = [card("spades", 1)]
    assert board.move_to_foundation(("waste",))["ok"]
    board._waste = [card("spades", 2)]
    assert board.move_to_foundation(("waste",))["ok"]
    assert not board.can_drop_foundation(card("spades", 4))
    assert not board.can_drop_foundation(card("hearts", 3))  # hearts 堆还是空的
    assert not board.can_drop_foundation(card("hearts", 2))
    assert board.can_drop_foundation(card("hearts", 1))


def test_foundation_from_tableau_top_only():
    """tableau 上收牌堆只允许列末张"""
    board = make_board()
    from ui.game_logic import TableauCard
    board._tableau[0] = [
        TableauCard(card("spades", 2), True),
        TableauCard(card("spades", 1), True),
    ]
    assert not board.move_to_foundation(("tableau", 0, 0))["ok"]
    result = board.move_to_foundation(("tableau", 0, 1))
    assert result["ok"]
    assert board.foundation_count("spades") == 1
    assert board.tableau_col(0)[0].face_up  # 2♠ 自动翻开


def test_foundation_no_move():
    """空废牌堆上堆失败且不炸"""
    board = make_board()
    assert not board.move_to_foundation(("waste",))["ok"]


# ── 胜利判断 ──

def test_win_detection():
    board = make_board()
    assert not board.is_won
    for s in SUITS:
        for r in range(1, 14):
            board._foundations[s].append(card(s, r))
    assert board.is_won
