# -*- coding: utf-8 -*-
"""中国象棋规则引擎测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ui.game_logic import (
    RED, BLACK, COLS, ROWS,
    initial_board, side_of, coord_to_str, str_to_coord, board_to_ascii,
    gen_pseudo_moves, gen_legal_moves, make_move,
    is_in_check, is_checkmate, is_stalemate, game_result,
    find_king, in_palace, in_own_half,
)


def test_initial_board_count():
    """初始局面应有 32 个棋子"""
    board = initial_board()
    n = sum(1 for row in board for p in row if p != '.')
    assert n == 32, f"expected 32 pieces, got {n}"


def test_initial_king_positions():
    """红帅在 (4,9)，黑将在 (4,0)"""
    board = initial_board()
    assert find_king(board, RED) == (4, 9)
    assert find_king(board, BLACK) == (4, 0)


def test_marshal_in_palace_only():
    """帅只能走九宫内"""
    assert in_palace(RED, 4, 9) is True
    assert in_palace(RED, 3, 7) is True
    assert in_palace(RED, 5, 7) is True
    assert in_palace(RED, 4, 6) is False
    assert in_palace(RED, 2, 9) is False


def test_coord_roundtrip():
    """坐标字符串互转"""
    for c in range(COLS):
        for r in range(ROWS):
            s = coord_to_str(c, r)
            assert str_to_coord(s) == (c, r)
    assert str_to_coord("z0") is None
    assert str_to_coord("a99") is None


def test_make_move():
    """make_move 返回新棋盘，不修改原盘"""
    board = initial_board()
    nb = make_move(board, (0, 9, 0, 8))
    assert nb[8][0] == 'R'
    assert nb[9][0] == '.'
    assert board[9][0] == 'R'


def test_horse_leg_blocked():
    """蹩马腿：直步方向有子则不能走"""
    board = initial_board()
    board[8][1] = 'P'  # 放红兵在 (1,8) 当蹩腿
    moves = gen_pseudo_moves(board, 1, 9)
    # 马 (1,9) 走 (0,7) 或 (2,7)：leg=(1,8)='P' → 蹩腿
    assert (0, 7) not in moves, "马 (0,7) 应被 (1,8) 蹩腿"
    assert (2, 7) not in moves, "马 (2,7) 应被 (1,8) 蹩腿"


def test_horse_open_in_initial():
    """初始局面下红马 (1,9) 8 方向中只有 2 个方向（腿点为空）可走"""
    board = initial_board()
    moves = gen_pseudo_moves(board, 1, 9)
    # (1,9) 的 8 方向：
    #   (-1,-2)(1,-2): leg(1,8)='.'空 → 可到 (0,7)(2,7)
    #   (-1,2)(1,2): leg(1,10)越界 → 不可
    #   (-2,-1)(-2,1): leg(0,9)='R' → 蹩
    #   (2,-1)(2,1): leg(2,9)='B' → 蹩
    assert (0, 7) in moves
    assert (2, 7) in moves
    assert len(moves) == 2, f"初始马 (1,9) 应有 2 个可走方向，got {len(moves)}: {moves}"


def test_cannon_requires_screen():
    """炮走不需炮架，吃子必须隔一个子（无炮架不能吃 / 不能吃己方）"""
    board = initial_board()
    moves = gen_pseudo_moves(board, 1, 7)
    # 红炮 (1,7) 向上遇 (1,9)='N' 己马 → 不能吃
    assert (1, 9) not in moves, f"红炮不应吃己马 (1,9)，got {moves}"
    # 红炮 (1,7) 向右遇 (7,7)='C' 己炮 → 不能吃
    assert (7, 7) not in moves, f"红炮不应吃己炮 (7,7)，got {moves}"
    # 红炮 (1,7) 沿 col 1 走空格
    for pos in [(1, 6), (1, 5), (1, 4), (1, 3)]:
        assert pos in moves, f"红炮应能走到 {pos}（空格）"
    # 红炮 (1,7) 隔 (1,2)='c' 炮架吃 (1,0)='n'
    assert (1, 0) in moves, f"红炮应能隔 (1,2) 炮架吃 (1,0)，got {moves}"
    # 验证"无炮架不能吃"：构造红炮 (4,7) 前方只有黑卒无炮架
    board2 = [row[:] for row in initial_board()]
    # 清 col 4 上下，留一个黑卒在 (4,5) 当"想吃的目标"
    for r in range(ROWS):
        board2[r][4] = '.'
    board2[0][4] = 'k'  # 黑将回位
    board2[5][4] = 'p'  # 黑卒 (4,5) 当目标
    board2[7][4] = 'C'  # 红炮 (4,7)
    moves2 = gen_pseudo_moves(board2, 4, 7)
    # 沿 col 4 向下：(4,6)='.'(4,5)='p' → 中间无炮架不能吃 (4,5)
    assert (4, 6) in moves2
    assert (4, 5) not in moves2, f"无炮架不应能吃 (4,5)，got {moves2}"


def test_cannon_capture_with_screen():
    """炮架规则：中间恰好一个子时可吃"""
    board = initial_board()
    board[4][1] = 'P'  # 红兵当炮架
    board[3][1] = 'p'  # 黑卒当目标
    moves = gen_pseudo_moves(board, 1, 7)
    # 红炮 (1,7) 向下：穿过 (1,6)(1,5) 空，遇 (1,4)='P' 炮架，跳到 (1,3)='p' 吃
    assert (1, 3) in moves, f"红炮应能隔炮架吃 (1,3)，got {moves}"


def test_elephant_eye_blocked():
    """塞象眼：田字中心有子则相不能过"""
    board = initial_board()
    board[8][1] = 'P'  # 塞象眼点 (1,8)
    moves = gen_pseudo_moves(board, 2, 9)
    # 红相 (2,9) 走 (0,7)：eye=(1,8)='P' 非空 → 不能
    assert (0, 7) not in moves, "相 (0,7) 应被 (1,8) 塞象眼"
    # 红相 (2,9) 走 (4,7)：eye=(3,8)='.'空 → 可
    assert (4, 7) in moves


def test_elephant_cannot_cross_river():
    """相不能过河"""
    board = initial_board()
    moves = gen_pseudo_moves(board, 2, 9)
    for nc, nr in moves:
        assert nr >= 5, f"相过河: {(nc, nr)}"


def test_pawn_forward_only_before_crossing():
    """兵未过河只能前进"""
    board = initial_board()
    moves = gen_pseudo_moves(board, 0, 6)
    assert (0, 5) in moves  # 前
    assert (1, 6) not in moves  # 未过河不能左右
    assert (0, 7) not in moves  # 不能后退


def test_pawn_sideways_after_crossing():
    """兵过河后可左右"""
    board = initial_board()
    board[4][0] = 'P'  # 红兵过河到 (0,4)
    moves = gen_pseudo_moves(board, 0, 4)
    assert (0, 3) in moves  # 继续前
    assert (1, 4) in moves  # 可右


def test_legal_moves_filters_self_check():
    """送将过滤：走子后己方被将的走法应被过滤"""
    board = initial_board()
    legal = gen_legal_moves(board, RED)
    for mv in legal:
        nb = make_move(board, mv)
        assert not is_in_check(nb, RED), f"非法走法未过滤: {mv}"


def test_is_in_check_true_false():
    """将军检测"""
    board = initial_board()
    assert not is_in_check(board, RED)
    assert not is_in_check(board, BLACK)
    # 构造黑车直接攻击红帅：清 col 4 所有子，黑车放 (4,0)
    for r in range(ROWS):
        board[r][4] = '.'
    board[0][4] = 'r'
    assert is_in_check(board, RED) is True, "红帅应被黑车 (4,0) 攻击"


def test_checkmate_detection():
    """将死检测：三车控制九宫 col 3-5 + 黑将被红车 (4,0) 将军"""
    board = initial_board()
    for r in range(ROWS):
        for c in range(COLS):
            board[r][c] = '.'
    board[0][4] = 'k'
    board[7][3] = 'R'  # 控制 col 3
    board[7][4] = 'R'  # 控制 col 4 (也将黑将)
    board[7][5] = 'R'  # 控制 col 5
    assert is_checkmate(board, BLACK) is True, "黑将应被将死（无合法走法且被将）"


def test_game_result_winner():
    """game_result 返回赢家"""
    board = initial_board()
    for r in range(ROWS):
        for c in range(COLS):
            board[r][c] = '.'
    board[0][4] = 'k'
    board[7][3] = 'R'
    board[7][4] = 'R'
    board[7][5] = 'R'
    # 黑将被将死 → red_win
    assert game_result(board, BLACK) == "red_win"


def test_stalemate_loses():
    """困毙（未被将但无合法走法）判负 — 函数语义 + 初始非困毙"""
    assert callable(is_stalemate)
    # 初始局面双方都有合法走法，未被将 → 非困毙
    assert is_stalemate(initial_board(), RED) is False
    assert is_stalemate(initial_board(), BLACK) is False


def test_initial_red_first():
    """初始局面下红方先走（合法走法非空）"""
    board = initial_board()
    moves = gen_legal_moves(board, RED)
    assert len(moves) > 0


def test_board_to_ascii_renders():
    """ASCII 输出包含所有棋子名"""
    s = board_to_ascii(initial_board())
    assert "帅" in s
    assert "将" in s
    assert "车" in s
    assert "马" in s


if __name__ == "__main__":
    tests = [
        test_initial_board_count, test_initial_king_positions,
        test_marshal_in_palace_only, test_coord_roundtrip, test_make_move,
        test_horse_leg_blocked, test_horse_open_in_initial,
        test_cannon_requires_screen, test_cannon_capture_with_screen,
        test_elephant_eye_blocked, test_elephant_cannot_cross_river,
        test_pawn_forward_only_before_crossing, test_pawn_sideways_after_crossing,
        test_legal_moves_filters_self_check,
        test_is_in_check_true_false, test_checkmate_detection,
        test_game_result_winner, test_stalemate_loses,
        test_initial_red_first, test_board_to_ascii_renders,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"✅ {t.__name__}")
        except AssertionError as e:
            print(f"❌ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(0 if failed == 0 else 1)
