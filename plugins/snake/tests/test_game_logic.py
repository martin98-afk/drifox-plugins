"""贪吃蛇核心逻辑测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ui.game_logic import SnakeGame, Direction, GameState, CollisionType


def test_init():
    """测试初始化"""
    game = SnakeGame(15, 15)
    assert game.width == 15
    assert game.height == 15
    assert game.state == GameState.READY
    assert game.score == 0
    assert game.direction == Direction.RIGHT


def test_invalid_size():
    """测试无效尺寸"""
    try:
        game = SnakeGame(1, 15)
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "网格尺寸必须大于 2x2" in str(e)


def test_start():
    """测试游戏开始"""
    game = SnakeGame(15, 15)
    result = game.start()

    assert game.state == GameState.PLAYING
    assert len(game.snake) == 3  # 初始长度 3
    assert game.food[0] >= 0  # 食物已生成
    assert game.food[1] >= 0


def test_direction_change():
    """测试方向改变"""
    game = SnakeGame(15, 15)
    game.start()

    # 游戏开始时方向是 RIGHT
    assert game._direction == Direction.RIGHT

    # 正常改变方向为向上（不是掉头）
    result = game.set_direction(Direction.UP)
    assert result["success"] is True
    assert game._next_direction == Direction.UP

    # 向左不是掉头（当前方向是 RIGHT）
    result = game.set_direction(Direction.LEFT)
    assert result["success"] is True

    # 尝试掉头（向左之后，尝试向右）
    result = game.set_direction(Direction.RIGHT)
    assert result["success"] is False


def test_movement():
    """测试移动"""
    game = SnakeGame(10, 10)
    game.start()

    initial_head = game.snake[0]
    game.tick()

    # 蛇应该向右移动
    new_head = game.snake[0]
    assert new_head[0] == initial_head[0] + 1
    assert new_head[1] == initial_head[1]


def test_food_collision():
    """测试吃食物"""
    game = SnakeGame(10, 10)
    game.start()

    # 将食物放到蛇头前方一格
    game._food = (game.snake[0][0] + 1, game.snake[0][1])
    game.tick()

    # 应该吃到了食物
    assert game.score == 10
    assert len(game.snake) == 4  # 长度 +1


def test_wall_collision():
    """测试撞墙"""
    game = SnakeGame(5, 5)
    game.start()

    # 将蛇移到边缘
    game._snake = [(4, 2), (3, 2), (2, 2)]
    game._food = (10, 10)  # 远离食物

    # 向右移动会撞墙
    game.tick()

    assert game.state == GameState.LOST


def test_self_collision():
    """测试撞自身"""
    game = SnakeGame(10, 10)
    game.start()

    # 创建一个会撞到自己的情况：蛇头在(2,2)，身体包含(2,2)
    # 蛇向左走会撞到自己的身体
    game._snake = [(3, 3), (2, 3), (1, 3), (1, 2)]
    game._direction = Direction.LEFT
    game._next_direction = Direction.LEFT
    game._food = (10, 10)  # 远离食物

    # 向左移动一格，蛇头会到(2,3)，而身体包含(2,3)，应该撞到自己
    game.tick()

    assert game.state == GameState.LOST


def test_pause():
    """测试暂停"""
    game = SnakeGame(10, 10)
    game.start()

    # 暂停
    result = game.pause()
    assert result["state"] == GameState.PAUSED
    assert result["paused"] is True

    # 继续
    result = game.pause()
    assert result["state"] == GameState.PLAYING
    assert result["paused"] is False


def test_speed_increase():
    """测试速度递增"""
    game = SnakeGame(15, 15)
    game.start()

    initial_interval = game.interval

    # 吃几个食物
    for i in range(5):
        # 将食物放到蛇头前方
        head = game.snake[0]
        game._food = (head[0] + 1, head[1])
        game.tick()

    # 速度应该提升（间隔减少）
    assert game.interval < initial_interval


def test_reset():
    """测试重置"""
    game = SnakeGame(15, 15)
    game.start()

    # 移动几步
    game.tick()
    game.tick()

    # 重置
    game.reset()

    assert game.state == GameState.READY
    assert game.score == 0
    assert len(game.snake) == 0


def test_180_degree_turn_prevented():
    """测试防止 180 度掉头"""
    game = SnakeGame(10, 10)
    game.start()

    # 向右走
    game.set_direction(Direction.RIGHT)

    # 试图向左（掉头）
    result = game.set_direction(Direction.LEFT)
    assert result["success"] is False


def test_food_not_on_snake():
    """测试食物不会生成在蛇身上"""
    game = SnakeGame(10, 10)
    game.start()

    # 确保食物不在蛇身上
    for pos in game.snake:
        assert game.food != pos


if __name__ == "__main__":
    test_init()
    print("✅ test_init")
    test_invalid_size()
    print("✅ test_invalid_size")
    test_start()
    print("✅ test_start")
    test_direction_change()
    print("✅ test_direction_change")
    test_movement()
    print("✅ test_movement")
    test_food_collision()
    print("✅ test_food_collision")
    test_wall_collision()
    print("✅ test_wall_collision")
    test_self_collision()
    print("✅ test_self_collision")
    test_pause()
    print("✅ test_pause")
    test_speed_increase()
    print("✅ test_speed_increase")
    test_reset()
    print("✅ test_reset")
    test_180_degree_turn_prevented()
    print("✅ test_180_degree_turn_prevented")
    test_food_not_on_snake()
    print("✅ test_food_not_on_snake")
    print("\n🎉 All tests passed!")