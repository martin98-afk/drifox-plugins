# -*- coding: utf-8 -*-
"""中国象棋规则引擎 — 纯 Python，可独立单测

棋盘坐标系：
- 列 col: 0..8（从左到右）
- 行 row: 0..9（0=黑方底线/顶部，9=红方底线/底部）
- 红方在底部（row 大），黑方在顶部（row 小）

棋子字符：
- 红（大写）：K=帅 A=仕 B=相 N=马 R=车 C=炮 P=兵
- 黑（小写）：k=将 a=士 b=象 n=马 r=车 c=炮 p=卒
"""

from typing import List, Optional, Tuple

COLS = 9
ROWS = 10

RED = "red"
BLACK = "black"

# 初始局面（row 0 在顶 = 黑底线）
INITIAL_BOARD: List[List[str]] = [
    list("rnbakabnr"),  # row 0 黑底线
    list("........."),  # row 1
    list(".c.....c."),  # row 2 黑炮
    list("p.p.p.p.p"),  # row 3 黑卒
    list("........."),  # row 4
    list("........."),  # row 5
    list("P.P.P.P.P"),  # row 6 红兵
    list(".C.....C."),  # row 7 红炮
    list("........."),  # row 8
    list("RNBAKABNR"),  # row 9 红底线
]

# 中文显示名
PIECE_CN = {
    "K": "帅", "k": "将",
    "A": "仕", "a": "士",
    "B": "相", "b": "象",
    "N": "马", "n": "马",
    "R": "车", "r": "车",
    "C": "炮", "c": "炮",
    "P": "兵", "p": "卒",
}


def initial_board() -> List[List[str]]:
    return [row[:] for row in INITIAL_BOARD]


def in_board(c: int, r: int) -> bool:
    return 0 <= c < COLS and 0 <= r < ROWS


def side_of(piece: str) -> Optional[str]:
    if piece == "." or not piece:
        return None
    return RED if piece.isupper() else BLACK


def opposite(side: str) -> str:
    return BLACK if side == RED else RED


def in_palace(side: str, c: int, r: int) -> bool:
    if not (3 <= c <= 5):
        return False
    if side == RED:
        return 7 <= r <= 9
    return 0 <= r <= 2


def in_own_half(side: str, r: int) -> bool:
    if side == RED:
        return r >= 5
    return r <= 4


def forward(side: str) -> int:
    """己方前进方向：红向上 row 减小 = -1；黑向下 row 增大 = +1"""
    return -1 if side == RED else 1


def gen_pseudo_moves(board: List[List[str]], c: int, r: int) -> List[Tuple[int, int]]:
    """生成 (c,r) 处棋子的所有 pseudo-legal 走法（不考虑送将）。

    返回目标格列表 [(nc, nr), ...]，供 gen_legal_moves 与攻击检测复用。
    """
    piece = board[r][c]
    if piece == ".":
        return []
    side = side_of(piece)
    p = piece.upper()
    moves: List[Tuple[int, int]] = []

    if p == "K":  # 帅/将：九宫内四向 + 飞将吃对面将
        for dc, dr in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nc, nr = c + dc, r + dr
            if in_board(nc, nr) and in_palace(side, nc, nr):
                t = board[nr][nc]
                if t == "." or side_of(t) != side:
                    moves.append((nc, nr))
        # 飞将：与对面将帅同列且中间无子，可吃
        dr_opp = -forward(side)
        nr = r + dr_opp
        while in_board(c, nr):
            t = board[nr][c]
            if t != ".":
                if side_of(t) == opposite(side) and t.upper() == "K":
                    moves.append((c, nr))
                break
            nr += dr_opp

    elif p == "A":  # 仕/士：九宫内四斜
        for dc, dr in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            nc, nr = c + dc, r + dr
            if in_board(nc, nr) and in_palace(side, nc, nr):
                t = board[nr][nc]
                if t == "." or side_of(t) != side:
                    moves.append((nc, nr))

    elif p == "B":  # 相/象：田字 + 塞象眼
        for dc, dr in ((-2, -2), (2, -2), (-2, 2), (2, 2)):
            nc, nr = c + dc, r + dr
            ec, er = c + dc // 2, r + dr // 2
            if in_board(nc, nr) and in_own_half(side, nr) and board[er][ec] == ".":
                t = board[nr][nc]
                if t == "." or side_of(t) != side:
                    moves.append((nc, nr))

    elif p == "N":  # 马：日字 + 蹩马腿
        # (dc,dr,leg_dc,leg_dr) 马走的方向与蹩腿点
        legs = (
            (-1, -2, 0, -1), (1, -2, 0, -1),
            (-1, 2, 0, 1), (1, 2, 0, 1),
            (-2, -1, -1, 0), (-2, 1, -1, 0),
            (2, -1, 1, 0), (2, 1, 1, 0),
        )
        for dc, dr, lc, lr in legs:
            nc, nr = c + dc, r + dr
            if in_board(nc, nr) and board[r + lr][c + lc] == ".":
                t = board[nr][nc]
                if t == "." or side_of(t) != side:
                    moves.append((nc, nr))

    elif p == "R":  # 车：直线
        for dc, dr in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nc, nr = c + dc, r + dr
            while in_board(nc, nr):
                t = board[nr][nc]
                if t == ".":
                    moves.append((nc, nr))
                else:
                    if side_of(t) != side:
                        moves.append((nc, nr))
                    break
                nc += dc
                nr += dr

    elif p == "C":  # 炮：走=车；吃需炮架
        for dc, dr in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nc, nr = c + dc, r + dr
            # 走：遇子前可继续
            while in_board(nc, nr) and board[nr][nc] == ".":
                moves.append((nc, nr))
                nc += dc
                nr += dr
            # 跳过该子，看其后是否还有敌方子（炮架规则）
            if in_board(nc, nr):
                nc += dc
                nr += dr
                while in_board(nc, nr):
                    t = board[nr][nc]
                    if t != ".":
                        if side_of(t) != side:
                            moves.append((nc, nr))
                        break
                    nc += dc
                    nr += dr

    elif p == "P":  # 兵/卒：前 + 过河后左右
        fr = forward(side)
        nc, nr = c, r + fr
        if in_board(nc, nr):
            t = board[nr][nc]
            if t == "." or side_of(t) != side:
                moves.append((nc, nr))
        crossed = (side == RED and r <= 4) or (side == BLACK and r >= 5)
        if crossed:
            for dc in (-1, 1):
                nc2 = c + dc
                if in_board(nc2, r):
                    t = board[r][nc2]
                    if t == "." or side_of(t) != side:
                        moves.append((nc2, r))

    return moves


def make_move(board: List[List[str]], move: Tuple[int, int, int, int]) -> List[List[str]]:
    """返回新棋盘（不修改原 board）"""
    c1, r1, c2, r2 = move
    nb = [row[:] for row in board]
    nb[r2][c2] = nb[r1][c1]
    nb[r1][c1] = "."
    return nb


def find_king(board: List[List[str]], side: str) -> Optional[Tuple[int, int]]:
    k = "K" if side == RED else "k"
    for r in range(ROWS):
        for c in range(COLS):
            if board[r][c] == k:
                return c, r
    return None


def is_square_attacked(board: List[List[str]], c: int, r: int, by_side: str) -> bool:
    """判断 (c,r) 是否被 by_side 攻击（pseudo-legal）"""
    for rr in range(ROWS):
        for cc in range(COLS):
            p = board[rr][cc]
            if p == "." or side_of(p) != by_side:
                continue
            if (c, r) in gen_pseudo_moves(board, cc, rr):
                return True
    return False


def is_in_check(board: List[List[str]], side: str) -> bool:
    k = find_king(board, side)
    if k is None:
        return True
    return is_square_attacked(board, k[0], k[1], opposite(side))


def gen_legal_moves(board: List[List[str]], side: str) -> List[Tuple[int, int, int, int]]:
    """生成 side 方的所有合法走法（已过滤送将）"""
    result: List[Tuple[int, int, int, int]] = []
    for r in range(ROWS):
        for c in range(COLS):
            p = board[r][c]
            if p == "." or side_of(p) != side:
                continue
            for nc, nr in gen_pseudo_moves(board, c, r):
                nb = make_move(board, (c, r, nc, nr))
                if not is_in_check(nb, side):
                    result.append((c, r, nc, nr))
    return result


def is_checkmate(board: List[List[str]], side: str) -> bool:
    return is_in_check(board, side) and len(gen_legal_moves(board, side)) == 0


def is_stalemate(board: List[List[str]], side: str) -> bool:
    """困毙：未被将但无合法走法（标准规则判负）"""
    return not is_in_check(board, side) and len(gen_legal_moves(board, side)) == 0


def game_result(board: List[List[str]], side_to_move: str) -> str:
    """'red_win' / 'black_win' / 'ongoing'"""
    if is_checkmate(board, side_to_move):
        return "black_win" if side_to_move == RED else "red_win"
    if is_stalemate(board, side_to_move):
        return "black_win" if side_to_move == RED else "red_win"
    return "ongoing"


def coord_to_str(c: int, r: int) -> str:
    """数字坐标 → 'a1'..'i10'（列字母+行号 1-10）"""
    return chr(ord("a") + c) + str(r + 1)


def str_to_coord(s: str) -> Optional[Tuple[int, int]]:
    """'a1'..'i10' → (c, r)；失败返回 None"""
    if not s or len(s) < 2:
        return None
    s = s.strip().lower()
    c = ord(s[0]) - ord("a")
    try:
        r = int(s[1:]) - 1
    except ValueError:
        return None
    if not (0 <= c < COLS and 0 <= r < ROWS):
        return None
    return c, r


def board_to_ascii(board: List[List[str]]) -> str:
    """生成棋盘 ASCII（红方在底部，标准视图）"""
    lines = ["  " + " ".join(str(i) for i in range(COLS))]
    for r in range(ROWS):
        row = board[r]
        cells = []
        for c in range(COLS):
            p = row[c]
            if p == ".":
                cells.append("·")
            else:
                cells.append(PIECE_CN.get(p, p))
        lines.append(f"{r} " + " ".join(cells))
    return "\n".join(lines)
