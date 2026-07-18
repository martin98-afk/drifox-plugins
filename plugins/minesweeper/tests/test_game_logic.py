"""扫雷核心逻辑测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ui.game_logic import MinesweeperGame, CellState, GameState


def test_init():
    game = MinesweeperGame(9, 9, 10)
    assert game.width == 9
    assert game.height == 9
    assert game.mine_count == 10
    assert game.state == GameState.READY


def test_init_board_first_click_safe():
    game = MinesweeperGame(9, 9, 10)
    game.init_board(4, 4)
    assert game._initialized
    assert game.state == GameState.PLAYING
    # 首次点击位置必须是安全的
    assert game._board[4][4] != -1
    # 周围 8 格也安全
    for dx, dy in [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1)]:
        nx, ny = 4+dx, 4+dy
        if 0 <= nx < 9 and 0 <= ny < 9:
            assert game._board[nx][ny] != -1, f"({nx},{ny}) has a mine!"


def test_reveal_number():
    game = MinesweeperGame(9, 9, 10)
    game.init_board(4, 4)
    result = game.reveal(4, 4)
    assert len(result["changed"]) > 0  # 应该翻开至少1格
    assert game.state == GameState.PLAYING


def test_flag_toggle():
    game = MinesweeperGame(9, 9, 10)
    game.init_board(4, 4)
    result = game.toggle_flag(0, 0)
    assert result["flagged"] is True
    assert game.get_cell(0, 0)["state"] == CellState.FLAGGED
    result = game.toggle_flag(0, 0)
    assert result["flagged"] is False
    assert game.get_cell(0, 0)["state"] == CellState.HIDDEN


def test_game_over_on_mine():
    game = MinesweeperGame(9, 9, 10)
    game.init_board(4, 4)
    # 找一个地雷位置
    mine_pos = None
    for x in range(9):
        for y in range(9):
            if game._board[x][y] == -1:
                mine_pos = (x, y)
                break
        if mine_pos:
            break
    if mine_pos:
        result = game.reveal(mine_pos[0], mine_pos[1])
        assert result["game_over"] is True
        assert result["won"] is False
        assert game.state == GameState.LOST


def test_reset():
    game = MinesweeperGame(9, 9, 10)
    game.init_board(4, 4)
    game.reveal(4, 4)
    game.reset(16, 16, 40)
    assert game.width == 16
    assert game.height == 16
    assert game.mine_count == 40
    assert game.state == GameState.READY


def test_flag_count():
    game = MinesweeperGame(9, 9, 10)
    game.init_board(4, 4)
    assert game.flag_count == 0
    game.toggle_flag(0, 0)
    assert game.flag_count == 1
    game.toggle_flag(1, 1)
    assert game.flag_count == 2
    game.toggle_flag(0, 0)
    assert game.flag_count == 1


def test_reveal_flagged_cell():
    game = MinesweeperGame(9, 9, 10)
    game.init_board(4, 4)
    game.toggle_flag(2, 2)
    # 插旗的格子不能翻开
    result = game.reveal(2, 2)
    assert len(result["changed"]) == 0


if __name__ == "__main__":
    test_init()
    print("✅ test_init")
    test_init_board_first_click_safe()
    print("✅ test_init_board_first_click_safe")
    test_reveal_number()
    print("✅ test_reveal_number")
    test_flag_toggle()
    print("✅ test_flag_toggle")
    test_game_over_on_mine()
    print("✅ test_game_over_on_mine")
    test_reset()
    print("✅ test_reset")
    test_flag_count()
    print("✅ test_flag_count")
    test_reveal_flagged_cell()
    print("✅ test_reveal_flagged_cell")
    print("\n🎉 All tests passed!")
