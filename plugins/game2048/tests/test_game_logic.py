"""2048 核心逻辑测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ui.game_logic import Game2048, Direction


def test_init():
    """测试游戏初始化"""
    game = Game2048()
    game.init()
    grid = game.get_grid()
    assert len(grid) == 4
    assert len(grid[0]) == 4
    # 初始应该有2个非零数字
    total = sum(sum(row) for row in grid)
    assert total > 0


def test_init_has_two_tiles():
    """测试初始有两个数字"""
    game = Game2048()
    game.init()
    grid = game.get_grid()
    count = sum(1 for row in grid for val in row if val != 0)
    assert count == 2, f"Expected 2 tiles, got {count}"


def test_move_left():
    """测试向左移动"""
    game = Game2048()
    game.init()
    # 设置一个可预测的场景
    game._grid = [
        [2, 2, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    result = game.move(Direction.LEFT)
    assert result["moved"] is True
    assert game.get_grid()[0][0] == 4


def test_move_left_no_merge():
    """测试向左移动但无合并"""
    game = Game2048()
    game._grid = [
        [0, 2, 4, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    result = game.move(Direction.LEFT)
    assert result["moved"] is True
    assert game.get_grid()[0][0] == 2
    assert game.get_grid()[0][1] == 4


def test_move_right():
    """测试向右移动"""
    game = Game2048()
    game._grid = [
        [2, 2, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    result = game.move(Direction.RIGHT)
    assert result["moved"] is True
    assert game.get_grid()[0][3] == 4


def test_move_up():
    """测试向上移动"""
    game = Game2048()
    game._grid = [
        [2, 0, 0, 0],
        [2, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    result = game.move(Direction.UP)
    assert result["moved"] is True
    assert game.get_grid()[0][0] == 4


def test_move_down():
    """测试向下移动"""
    game = Game2048()
    game._grid = [
        [2, 0, 0, 0],
        [2, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    result = game.move(Direction.DOWN)
    assert result["moved"] is True
    assert game.get_grid()[3][0] == 4


def test_score_increase():
    """测试分数增加"""
    game = Game2048()
    game._grid = [
        [2, 2, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    game.move(Direction.LEFT)
    assert game.score == 4


def test_best_score():
    """测试最高分更新"""
    game = Game2048()
    game._grid = [
        [2, 2, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    game.move(Direction.LEFT)
    assert game.best_score == 4
    
    # 再做一次移动
    game._grid = [
        [4, 4, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    game.move(Direction.LEFT)
    assert game.best_score == 12  # 2048 分数是累加的：4 + 8 = 12


def test_win_condition():
    """测试胜利条件（达到2048）"""
    game = Game2048()
    game._grid = [
        [1024, 1024, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    result = game.move(Direction.LEFT)
    assert result["won"] is True
    assert game.won is True


def test_game_over_no_moves():
    """测试无移动时的游戏结束"""
    game = Game2048()
    game._grid = [
        [2, 4, 2, 4],
        [4, 2, 4, 2],
        [2, 4, 2, 4],
        [4, 2, 4, 2],
    ]
    result = game.move(Direction.LEFT)
    assert result["game_over"] is True
    assert game.game_over is True


def test_game_not_over_with_empty():
    """有空位时游戏不结束"""
    game = Game2048()
    game._grid = [
        [2, 4, 2, 4],
        [4, 2, 4, 2],
        [2, 4, 2, 4],
        [4, 2, 0, 2],
    ]
    result = game.move(Direction.LEFT)
    assert result["game_over"] is False
    assert game.game_over is False


def test_no_move_when_same():
    """没有变化时不移动"""
    game = Game2048()
    game._grid = [
        [2, 4, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    result = game.move(Direction.LEFT)
    assert result["moved"] is False  # 2≠4且已靠左，无变化


def test_chain_merge():
    """测试链式合并（同一个方向只能合并一次）"""
    game = Game2048()
    game._grid = [
        [2, 2, 2, 2],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    result = game.move(Direction.LEFT)
    # [2,2,2,2] -> [4,4,0,0] 而不是 [8,0,0,0]
    assert game.get_grid()[0][0] == 4
    assert game.get_grid()[0][1] == 4


def test_reset():
    """测试重置"""
    game = Game2048()
    game._grid = [
        [2048, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    game._score = 2048
    game._won = True
    
    game.init()
    assert game.score == 0
    assert game.won is False
    assert game.game_over is False


if __name__ == "__main__":
    test_init()
    print("✅ test_init")
    test_init_has_two_tiles()
    print("✅ test_init_has_two_tiles")
    test_move_left()
    print("✅ test_move_left")
    test_move_left_no_merge()
    print("✅ test_move_left_no_merge")
    test_move_right()
    print("✅ test_move_right")
    test_move_up()
    print("✅ test_move_up")
    test_move_down()
    print("✅ test_move_down")
    test_score_increase()
    print("✅ test_score_increase")
    test_best_score()
    print("✅ test_best_score")
    test_win_condition()
    print("✅ test_win_condition")
    test_game_over_no_moves()
    print("✅ test_game_over_no_moves")
    test_game_not_over_with_empty()
    print("✅ test_game_not_over_with_empty")
    test_chain_merge()
    print("✅ test_chain_merge")
    test_reset()
    print("✅ test_reset")
    print("\n🎉 All tests passed!")