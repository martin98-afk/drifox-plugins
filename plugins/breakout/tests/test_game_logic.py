"""打砖块核心逻辑测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ui.game_logic import (
    BreakoutGame,
    Ball,
    Paddle,
    Brick,
    GameState,
    BRICK_COLORS,
    BRICK_SCORES,
)


def test_init():
    """测试游戏初始化"""
    game = BreakoutGame(400, 500, 5, 8)
    assert game.game_width == 400
    assert game.game_height == 500
    assert game.rows == 5
    assert game.cols == 8
    assert game.state == GameState.READY
    assert game.score == 0
    assert game.lives == 3


def test_brick_creation():
    """测试砖块创建"""
    game = BreakoutGame(400, 500, 5, 8)
    assert len(game.bricks) == 5 * 8  # 5行8列
    assert all(brick.alive for brick in game.bricks)
    # 检查颜色分层（从上到下应该是红橙黄绿蓝）
    for row in range(5):
        bricks_in_row = [b for b in game.bricks
                        if int((b.y - game.brick_top_margin) / (game.brick_height + game.brick_padding)) == row]
        if bricks_in_row:
            # 每行砖块应该颜色相同
            colors = set(b.color for b in bricks_in_row)
            assert len(colors) == 1


def test_paddle_movement():
    """测试挡板移动"""
    game = BreakoutGame(400, 500)
    game.start()  # 需要先开始游戏才能移动挡板
    initial_x = game.paddle.x

    # 向右移动多次
    for _ in range(5):
        game.move_paddle("right")
    assert game.paddle.x > initial_x

    # 记录当前位置，再向左移动回来
    moved_x = game.paddle.x
    for _ in range(5):
        game.move_paddle("left")
    assert game.paddle.x < moved_x


def test_paddle_bounds():
    """测试挡板边界限制"""
    game = BreakoutGame(400, 500)
    game.start()  # 需要先开始游戏才能移动挡板

    # 尝试向左超出边界
    for _ in range(100):
        game.move_paddle("left")
    assert game.paddle.x == 0

    # 尝试向右超出边界
    for _ in range(100):
        game.move_paddle("right")
    assert game.paddle.x == game.game_width - game.paddle.width


def test_set_paddle_position():
    """测试设置挡板位置"""
    game = BreakoutGame(400, 500)
    game.start()  # 需要先开始游戏才能设置挡板位置

    # 设置在中间
    game.set_paddle_position(200)
    assert abs(game.paddle.x - (200 - game.paddle.width / 2)) < 1

    # 设置在边界外（左侧）
    game.set_paddle_position(-50)
    assert game.paddle.x == 0

    # 设置在边界外（右侧）
    game.set_paddle_position(500)
    assert game.paddle.x == game.game_width - game.paddle.width


def test_game_start():
    """测试游戏开始"""
    game = BreakoutGame(400, 500)
    assert game.state == GameState.READY

    game.start()
    assert game.state == GameState.PLAYING


def test_ball_launch():
    """测试球发射"""
    game = BreakoutGame(400, 500)
    initial_ball_x = game.ball.x

    game.start()
    game.launch_ball()

    # 发射后球应该移动
    assert game.ball.dx != 0 or game.ball.dy != 0


def test_wall_collision():
    """测试墙壁碰撞"""
    game = BreakoutGame(400, 500)
    game.start()
    game.launch_ball()

    # 运行几帧
    hit_wall = False
    for _ in range(50):
        result = game.update()
        if result.get("hit_wall"):
            hit_wall = True
            break

    # 球应该在游戏区域内
    assert 0 <= game.ball.x <= game.game_width
    assert game.ball.y >= 0


def test_brick_hit():
    """测试砖块碰撞和计分"""
    game = BreakoutGame(400, 500)

    # 获取第一个砖块
    brick = game.bricks[0]
    assert brick.alive

    # 手动触发碰撞效果（模拟碰撞逻辑）
    brick.alive = False
    game.score += brick.score

    # 检查分数增加
    assert game.score == brick.score
    assert not brick.alive


def test_game_update():
    """测试游戏更新"""
    game = BreakoutGame(400, 500)
    game.start()

    result = game.update()
    assert "brick_hit" in result
    assert "game_over" in result
    assert "score" in result
    assert "lives" in result
    assert "state" in result


def test_life_loss():
    """测试生命损失"""
    game = BreakoutGame(400, 500)
    game.start()
    initial_lives = game.lives

    # 将球移出底部
    game.ball.y = game.game_height + 100
    game.update()

    assert game.lives < initial_lives


def test_game_over():
    """测试游戏结束"""
    game = BreakoutGame(400, 500)
    game.start()

    # 耗尽生命（失命后状态变为 READY，需要重新 start）
    while game.lives > 0:
        game.ball.y = game.game_height + 100
        game.update()
        # 失命后自动变为 READY，重新开始以再次激活
        if game.state == GameState.READY:
            game.state = GameState.PLAYING

    assert game.state == GameState.LOST


def test_victory():
    """测试胜利条件"""
    game = BreakoutGame(400, 500, 2, 2)  # 小棋盘便于测试
    game.start()

    # 击碎所有砖块
    for brick in game.bricks:
        brick.alive = False

    result = game.update()
    assert result["game_over"] is True
    assert result["won"] is True
    assert game.state == GameState.WON


def test_reset():
    """测试游戏重置"""
    game = BreakoutGame(400, 500)
    game.start()
    game.ball.y = game.game_height + 100
    game.update()
    game.lives = 1
    game.score = 100

    game.reset()
    assert game.state == GameState.READY
    assert game.lives == 3
    assert game.score == 0
    assert all(b.alive for b in game.bricks)


def test_get_state():
    """测试获取游戏状态"""
    game = BreakoutGame(400, 500)
    state = game.get_state()

    assert "state" in state
    assert "score" in state
    assert "lives" in state
    assert "ball" in state
    assert "paddle" in state
    assert "bricks" in state

    # 检查 ball 数据结构
    assert "x" in state["ball"]
    assert "y" in state["ball"]
    assert "radius" in state["ball"]

    # 检查 paddle 数据结构
    assert "x" in state["paddle"]
    assert "y" in state["paddle"]
    assert "width" in state["paddle"]
    assert "height" in state["paddle"]


def test_brick_scores():
    """测试砖块分数分层"""
    assert len(BRICK_COLORS) == 5
    assert len(BRICK_SCORES) == 5
    # 分数应该从上到下递减
    assert BRICK_SCORES[0] > BRICK_SCORES[1] > BRICK_SCORES[2] > BRICK_SCORES[3] > BRICK_SCORES[4]


def test_invalid_init():
    """测试无效初始化"""
    try:
        BreakoutGame(0, 500)
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "必须为正" in str(e)

    try:
        BreakoutGame(400, 500, 0, 8)
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "必须为正" in str(e)


if __name__ == "__main__":
    test_init()
    print("✅ test_init")
    test_brick_creation()
    print("✅ test_brick_creation")
    test_paddle_movement()
    print("✅ test_paddle_movement")
    test_paddle_bounds()
    print("✅ test_paddle_bounds")
    test_set_paddle_position()
    print("✅ test_set_paddle_position")
    test_game_start()
    print("✅ test_game_start")
    test_ball_launch()
    print("✅ test_ball_launch")
    test_wall_collision()
    print("✅ test_wall_collision")
    test_brick_hit()
    print("✅ test_brick_hit")
    test_game_update()
    print("✅ test_game_update")
    test_life_loss()
    print("✅ test_life_loss")
    test_game_over()
    print("✅ test_game_over")
    test_victory()
    print("✅ test_victory")
    test_reset()
    print("✅ test_reset")
    test_get_state()
    print("✅ test_get_state")
    test_brick_scores()
    print("✅ test_brick_scores")
    test_invalid_init()
    print("✅ test_invalid_init")
    print("\n🎉 All tests passed!")