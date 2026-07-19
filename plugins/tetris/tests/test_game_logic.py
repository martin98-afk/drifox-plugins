"""俄罗斯方块核心逻辑测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ui.game_logic import TetrisGame, GameState, TETROMINOES, TETROMINO_NAMES


def test_init():
    game = TetrisGame(10, 20)
    assert game.width == 10
    assert game.height == 20
    assert game.state == GameState.READY
    assert game.score == 0
    assert game.level == 1
    assert game.lines_cleared == 0


def test_tetrominoes_defined():
    """所有 7 种方块都正确定义"""
    assert set(TETROMINO_NAMES) == {"I", "O", "T", "S", "Z", "L", "J"}
    for name in TETROMINO_NAMES:
        t = TETROMINOES[name]
        assert "color" in t
        assert "shapes" in t
        assert len(t["shapes"]) == 4
        for shape in t["shapes"]:
            assert len(shape) == 4


def test_start_game():
    game = TetrisGame(10, 20)
    game.start()
    assert game.state == GameState.PLAYING
    assert game._current is not None
    assert game._next is not None


def test_move_left_right():
    game = TetrisGame(10, 20)
    game.start()
    init_x = game._current["x"]
    game.move_left()
    assert game._current["x"] == init_x - 1
    game.move_right()
    assert game._current["x"] == init_x


def test_rotate():
    game = TetrisGame(10, 20)
    game.start()
    init_rot = game._current["rotation"]
    result = game.rotate()
    assert result is True
    assert game._current["rotation"] == (init_rot + 1) % 4


def test_soft_drop():
    game = TetrisGame(10, 20)
    game.start()
    init_y = game._current["y"]
    init_score = game.score
    game.soft_drop()
    assert game._current["y"] == init_y + 1
    assert game.score == init_score + 1


def test_hard_drop():
    game = TetrisGame(10, 20)
    game.start()
    game.hard_drop()
    # 锁定后 current 变为 None
    assert game._current is None


def test_line_clear():
    """手动填充一行后应消除"""
    game = TetrisGame(10, 20)
    game.start()
    # 填充第一行
    for x in range(10):
        game._board[x][0] = "#aaa"
    game._clear_lines()
    assert game.lines_cleared == 1
    assert game.score == 100  # 1行=100分
    # 验证第一行已被清空
    assert all(game._board[x][0] is None for x in range(10))


def test_double_line_clear():
    """双行消除计分"""
    game = TetrisGame(10, 20)
    game.start()
    for x in range(10):
        game._board[x][0] = "#aaa"
        game._board[x][1] = "#bbb"
    game._clear_lines()
    assert game.lines_cleared == 2
    assert game.score == 300  # 2行=300分
    # ★ 验证行0和行1都已被清空（修复重删索引偏移 bug）
    assert all(game._board[x][0] is None for x in range(10))
    assert all(game._board[x][1] is None for x in range(10))


def test_triple_line_clear():
    """三行同时消除"""
    game = TetrisGame(10, 20)
    game.start()
    for x in range(10):
        for y in range(3):
            game._board[x][y] = "#aaa"
    game._clear_lines()
    assert game.lines_cleared == 3
    assert game.score == 500  # 3行=500分
    # 验证前三行全部清空
    for y in range(3):
        assert all(game._board[x][y] is None for x in range(10))


def test_non_consecutive_rows():
    """非连续行消除"""
    game = TetrisGame(10, 20)
    game.start()
    # 填充行0和行2（跳行1）
    for x in range(10):
        game._board[x][0] = "#aaa"
    for x in range(10):
        game._board[x][2] = "#ccc"
    # 行1保持None
    result = game._clear_lines()
    assert len(result) == 2
    assert game.lines_cleared == 2
    # 验证行0和行2被清空，且保留了1个空行在顶部
    assert all(game._board[x][0] is None for x in range(10))
    assert all(game._board[x][1] is None for x in range(10))
    assert all(game._board[x][2] is None for x in range(10))


def test_tetris_four_lines():
    """一次消除4行（Tetris）"""
    game = TetrisGame(10, 20)
    game.start()
    for x in range(10):
        for y in range(4):
            game._board[x][y] = "#ccc"
    game._clear_lines()
    assert game.lines_cleared == 4
    assert game.score == 800  # 4行=800分
    # 验证前4行都被清空
    for y in range(4):
        assert all(game._board[x][y] is None for x in range(10))


def test_level_up():
    """消除10行应升级"""
    game = TetrisGame(10, 20)
    game.start()
    for x in range(10):
        for row in range(10):
            game._board[x][row] = "#fff"
    game._clear_lines()
    assert game.level == 2


def test_get_drop_interval():
    """速度随等级变化"""
    game = TetrisGame(10, 20)
    game.start()
    assert game.get_drop_interval() == 800  # level 1
    game.level = 5
    assert game.get_drop_interval() == 400  # level 5


def test_pause():
    game = TetrisGame(10, 20)
    game.start()
    assert game.state == GameState.PLAYING
    game.pause()
    assert game.state == GameState.PAUSED
    game.pause()
    assert game.state == GameState.PLAYING


def test_reset():
    game = TetrisGame(10, 20)
    game.start()
    game.hard_drop()
    game.reset()
    assert game.state == GameState.READY
    assert game.score == 0
    assert game.level == 1
    assert game.lines_cleared == 0
    assert game._current is None


def test_game_over_on_spawn_collision():
    """棋盘堆满时游戏结束"""
    game = TetrisGame(10, 4)
    game.start()
    # 填满棋盘（除了顶部生成位置）
    for x in range(10):
        for y in range(2):
            game._board[x][y] = "#aaa"
    # 重置并重新开始，应该触发游戏结束
    game.reset()
    game._next = game._pop_from_bag()
    # 手动填充所有空间
    for x in range(10):
        for y in range(4):
            game._board[x][y] = "#aaa"
    # 尝试生成会碰撞
    result = game._spawn()
    assert result is False
    assert game.state == GameState.GAME_OVER


def test_get_next_piece():
    """下一块预览"""
    game = TetrisGame(10, 20)
    game.start()
    next_piece = game._next
    assert next_piece in TETROMINO_NAMES


def test_wall_kick():
    """墙边旋转不应卡死"""
    game = TetrisGame(4, 10)
    game.start()
    # 把方块移到最左边
    while game._current["x"] > 0:
        game.move_left()
    init_rot = game._current["rotation"]
    # 旋转（应该触发 wall kick）
    game.rotate()
    # 应该成功旋转
    assert game._current["rotation"] == (init_rot + 1) % 4


if __name__ == "__main__":
    test_init()
    print("✅ test_init")
    test_tetrominoes_defined()
    print("✅ test_tetrominoes_defined")
    test_start_game()
    print("✅ test_start_game")
    test_move_left_right()
    print("✅ test_move_left_right")
    test_rotate()
    print("✅ test_rotate")
    test_soft_drop()
    print("✅ test_soft_drop")
    test_hard_drop()
    print("✅ test_hard_drop")
    test_line_clear()
    print("✅ test_line_clear")
    test_double_line_clear()
    print("✅ test_double_line_clear")
    test_tetris_four_lines()
    print("✅ test_tetris_four_lines")
    test_level_up()
    print("✅ test_level_up")
    test_get_drop_interval()
    print("✅ test_get_drop_interval")
    test_pause()
    print("✅ test_pause")
    test_reset()
    print("✅ test_reset")
    test_game_over_on_spawn_collision()
    print("✅ test_game_over_on_spawn_collision")
    test_get_next_piece()
    print("✅ test_get_next_piece")
    test_wall_kick()
    print("✅ test_wall_kick")
    print("\n🎉 All tests passed!")