# -*- coding: utf-8 -*-
"""打砖块核心逻辑——纯 Python，无 Qt 依赖

BreakoutGame: 管理球、挡板、砖块、碰撞检测、计分、生命值。
可独立单元测试。
"""

import random
from enum import Enum
from typing import List, Optional, Tuple


class GameState(Enum):
    """游戏状态"""
    READY = "ready"       # 等待开始
    PLAYING = "playing"   # 游戏中
    WON = "won"           # 胜利（所有砖块被击碎）
    LOST = "lost"         # 失败（生命值耗尽）
    PAUSED = "paused"     # 暂停


# 砖块颜色分层配置
BRICK_COLORS = [
    "#E94560",  # 红色   - 顶层，最高分
    "#FF7043",  # 橙色
    "#FFCA28",  # 黄色
    "#66BB6A",  # 绿色
    "#42A5F5",  # 蓝色   - 底层，最低分
]

# 各颜色层对应分数
BRICK_SCORES = [50, 40, 30, 20, 10]


class Brick:
    """砖块"""

    def __init__(self, x: float, y: float, width: float, height: float,
                 color: str, score: int):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = color
        self.score = score
        self.alive = True

    @property
    def rect(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.width, self.height)


class Ball:
    """小球"""

    def __init__(self, x: float, y: float, radius: float = 8):
        self.x = x
        self.y = y
        self.radius = radius
        # 初始速度向量（角度）
        self.angle = -45  # 向左上方向
        self.speed = 5
        self.dx = 0
        self.dy = 0
        self._update_velocity()

    def _update_velocity(self):
        """根据角度和速度计算 dx, dy"""
        import math
        rad = math.radians(self.angle)
        self.dx = self.speed * math.cos(rad)
        self.dy = self.speed * math.sin(rad)

    def set_speed(self, speed: float):
        """设置速度大小"""
        self.speed = speed
        self._update_velocity()

    def set_angle(self, angle: float):
        """设置飞行角度"""
        self.angle = angle
        self._update_velocity()

    def move(self):
        """移动小球"""
        self.x += self.dx
        self.y += self.dy


class Paddle:
    """挡板"""

    def __init__(self, x: float, y: float, width: float = 100, height: float = 12):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.speed = 8
        self.min_x = 0
        self.max_x = 0  # 游戏区域宽度限制

    def move_left(self):
        """向左移动"""
        self.x = max(self.min_x, self.x - self.speed)

    def move_right(self):
        """向右移动"""
        self.x = min(self.max_x - self.width, self.x + self.speed)

    def set_bounds(self, min_x: float, max_x: float):
        """设置移动边界"""
        self.min_x = min_x
        self.max_x = max_x


class BreakoutGame:
    """打砖块游戏引擎

    职责：
    - 管理球、挡板、砖块状态
    - 碰撞检测（球与墙壁、挡板、砖块）
    - 计分系统
    - 生命值管理
    - 胜利/失败判断
    - 提供游戏状态查询接口

    Usage:
        game = BreakoutGame(game_width=400, game_height=500)
        game.start()
        # 游戏中每帧:
        result = game.update()
        if result.get("brick_hit"):
            # 更新分数显示
    """

    def __init__(self, game_width: int = 400, game_height: int = 500,
                 rows: int = 5, cols: int = 8):
        """初始化游戏

        Args:
            game_width: 游戏区域宽度
            game_height: 游戏区域高度
            rows: 砖块行数
            cols: 砖块列数
        """
        if game_width <= 0 or game_height <= 0:
            raise ValueError(f"游戏区域尺寸必须为正: {game_width}x{game_height}")
        if rows <= 0 or cols <= 0:
            raise ValueError(f"砖块行列必须为正: {rows}x{cols}")

        self.game_width = game_width
        self.game_height = game_height
        self.rows = rows
        self.cols = cols

        # 游戏状态
        self.state: GameState = GameState.READY

        # 计分
        self.score: int = 0

        # 生命值
        self.lives: int = 3
        self.max_lives: int = 3

        # 游戏对象
        self.ball: Optional[Ball] = None
        self.paddle: Optional[Paddle] = None
        self.bricks: List[Brick] = []

        # 游戏配置
        self.paddle_width = min(120, game_width // 4)
        self.paddle_height = 12
        self.paddle_bottom_margin = 40  # 挡板距底部距离
        self.ball_radius = 8
        self.ball_initial_speed = 5
        self.brick_padding = 4
        self.brick_top_margin = 60  # 砖块区域距顶部
        self.brick_height = 20

        # 碰撞计数（用于返回事件）
        self._brick_hit = False
        self._brick_destroyed = False
        self._hit_paddle = False
        self._hit_wall = False

        # 初始化游戏对象
        self._init_game_objects()

    def _init_game_objects(self):
        """初始化游戏对象"""
        # 初始化挡板
        paddle_x = (self.game_width - self.paddle_width) // 2
        paddle_y = self.game_height - self.paddle_bottom_margin - self.paddle_height
        self.paddle = Paddle(paddle_x, paddle_y, self.paddle_width, self.paddle_height)
        self.paddle.set_bounds(0, self.game_width)

        # 初始化小球
        ball_x = self.game_width // 2
        ball_y = paddle_y - self.ball_radius - 2
        self.ball = Ball(ball_x, ball_y, self.ball_radius)
        self.ball.set_speed(self.ball_initial_speed)

        # 初始化砖块
        self._create_bricks()

    def _create_bricks(self):
        """创建砖块矩阵"""
        self.bricks = []

        # 计算砖块尺寸
        total_padding = self.brick_padding * (self.cols + 1)
        brick_width = (self.game_width - total_padding) // self.cols

        # 计算砖块起始位置（居中）
        total_width = brick_width * self.cols + self.brick_padding * (self.cols - 1)
        start_x = (self.game_width - total_width) // 2

        for row in range(self.rows):
            # 根据行数分配颜色（从顶部开始）
            color_idx = row * (len(BRICK_COLORS) - 1) // max(1, self.rows - 1)
            color = BRICK_COLORS[color_idx]
            score = BRICK_SCORES[color_idx]

            y = self.brick_top_margin + row * (self.brick_height + self.brick_padding)

            for col in range(self.cols):
                x = start_x + col * (brick_width + self.brick_padding)
                brick = Brick(x, y, brick_width, self.brick_height, color, score)
                self.bricks.append(brick)

    def start(self):
        """开始游戏

        - READY: 首次开始或失命后继续，直接设为 PLAYING（已有棋盘状态）
        - LOST: 全部生命耗尽，需要重置所有
        """
        if self.state == GameState.LOST:
            self.reset()
        if self.state in (GameState.READY, GameState.PLAYING):
            self.state = GameState.PLAYING

    def reset(self):
        """重置游戏"""
        self.score = 0
        self.lives = self.max_lives
        self.state = GameState.READY
        self._init_game_objects()

    def move_paddle(self, direction: str):
        """移动挡板

        Args:
            direction: "left" 或 "right"
        """
        if self.state != GameState.PLAYING:
            return
        if direction == "left":
            self.paddle.move_left()
        elif direction == "right":
            self.paddle.move_right()

    def set_paddle_position(self, x: float):
        """设置挡板位置（用于鼠标控制）

        Args:
            x: 挡板中心 x 坐标
        """
        if self.state != GameState.PLAYING:
            return
        # 将中心点转换为左上角坐标
        self.paddle.x = x - self.paddle.width // 2
        # 限制在边界内
        self.paddle.x = max(self.paddle.min_x, min(self.paddle.max_x - self.paddle.width, self.paddle.x))

    def launch_ball(self):
        """发射小球（从挡板释放）"""
        if self.state == GameState.READY:
            # 设置随机发射角度（向上偏移）
            import math
            angle = random.uniform(-135, -45)  # 左上到右上
            self.ball.angle = angle
            self.ball._update_velocity()
            self.state = GameState.PLAYING

    def update(self) -> dict:
        """更新游戏状态（一帧）

        Returns:
            dict: {
                "brick_hit": bool,      # 是否击中砖块
                "brick_destroyed": bool,# 是否击碎砖块
                "hit_paddle": bool,     # 是否击中挡板
                "hit_wall": bool,       # 是否碰到墙壁
                "life_lost": bool,      # 是否失去一条命
                "game_over": bool,      # 游戏是否结束
                "won": bool,            # 是否获胜
                "score": int,           # 当前分数
                "lives": int,           # 剩余生命
                "state": GameState,     # 当前状态
            }
        """
        result = {
            "brick_hit": False,
            "brick_destroyed": False,
            "hit_paddle": False,
            "hit_wall": False,
            "life_lost": False,
            "game_over": False,
            "won": False,
            "score": self.score,
            "lives": self.lives,
            "state": self.state,
        }

        if self.state != GameState.PLAYING:
            return result

        # 重置碰撞标志
        self._brick_hit = False
        self._brick_destroyed = False
        self._hit_paddle = False
        self._hit_wall = False

        # 移动小球
        self.ball.move()

        # 检测碰撞
        self._check_wall_collision()
        self._check_paddle_collision()
        self._check_brick_collision()

        # 检查胜利
        if all(not brick.alive for brick in self.bricks):
            self.state = GameState.WON
            result["game_over"] = True
            result["won"] = True
            return result

        # 检查失败（球落出底部）
        if self.ball.y > self.game_height + self.ball.radius:
            self._lose_life()
            result["life_lost"] = True

        # 更新返回结果
        result["brick_hit"] = self._brick_hit
        result["brick_destroyed"] = self._brick_destroyed
        result["hit_paddle"] = self._hit_paddle
        result["hit_wall"] = self._hit_wall
        result["game_over"] = self.state in (GameState.WON, GameState.LOST)
        result["score"] = self.score
        result["lives"] = self.lives
        result["state"] = self.state

        return result

    def _check_wall_collision(self):
        """检测墙壁碰撞"""
        ball = self.ball

        # 左墙
        if ball.x - ball.radius <= 0:
            ball.x = ball.radius
            ball.dx = abs(ball.dx)
            self._hit_wall = True

        # 右墙
        if ball.x + ball.radius >= self.game_width:
            ball.x = self.game_width - ball.radius
            ball.dx = -abs(ball.dx)
            self._hit_wall = True

        # 顶墙
        if ball.y - ball.radius <= 0:
            ball.y = ball.radius
            ball.dy = abs(ball.dy)
            self._hit_wall = True

        # 底边（在挡板区域外）会在 update 中检测

    def _check_paddle_collision(self):
        """检测挡板碰撞"""
        ball = self.ball
        paddle = self.paddle

        # 简单 AABB 检测
        if (ball.x + ball.radius > paddle.x and
            ball.x - ball.radius < paddle.x + paddle.width and
            ball.y + ball.radius > paddle.y and
            ball.y - ball.radius < paddle.y + paddle.height):

            # 球从上方进入
            if ball.dy > 0:
                ball.y = paddle.y - ball.radius
                self._hit_paddle = True

                # 根据击中挡板的位置改变反弹角度
                # 中心点（0）到边缘（-1 到 1）
                hit_pos = (ball.x - (paddle.x + paddle.width / 2)) / (paddle.width / 2)
                hit_pos = max(-1, min(1, hit_pos))  # 限制范围

                # 角度范围：-150° 到 -30°（确保总是向上）
                angle = -90 + hit_pos * 60
                ball.set_angle(angle)

                # 轻微加速
                ball.set_speed(min(ball.speed + 0.1, 10))

    def _check_brick_collision(self):
        """检测砖块碰撞"""
        ball = self.ball

        for brick in self.bricks:
            if not brick.alive:
                continue

            bx, by, bw, bh = brick.rect

            # AABB 检测
            if (ball.x + ball.radius > bx and
                ball.x - ball.radius < bx + bw and
                ball.y + ball.radius > by and
                ball.y - ball.radius < by + bh):

                # 确定碰撞方向
                overlap_left = ball.x + ball.radius - bx
                overlap_right = bx + bw - (ball.x - ball.radius)
                overlap_top = ball.y + ball.radius - by
                overlap_bottom = by + bh - (ball.y - ball.radius)

                min_overlap_x = min(overlap_left, overlap_right)
                min_overlap_y = min(overlap_top, overlap_bottom)

                if min_overlap_x < min_overlap_y:
                    # 水平碰撞
                    ball.dx = -ball.dx
                else:
                    # 垂直碰撞
                    ball.dy = -ball.dy

                # 击碎砖块
                brick.alive = False
                self.score += brick.score
                self._brick_hit = True
                self._brick_destroyed = True
                return  # 每帧只处理一次砖块碰撞

    def _lose_life(self):
        """失去一条命"""
        self.lives -= 1

        if self.lives <= 0:
            self.state = GameState.LOST
            return

        # 重置球和挡板位置
        ball_x = self.game_width // 2
        ball_y = self.paddle.y - self.ball_radius - 2
        self.ball = Ball(ball_x, ball_y, self.ball_radius)
        self.ball.set_speed(self.ball_initial_speed)

        # 重置挡板位置
        self.paddle.x = (self.game_width - self.paddle_width) // 2

        # 暂停状态，等待再次发射
        self.state = GameState.READY

    @property
    def brick_count(self) -> int:
        """剩余砖块数量"""
        return sum(1 for b in self.bricks if b.alive)

    def get_state(self) -> dict:
        """获取当前游戏状态（用于渲染）"""
        return {
            "state": self.state,
            "score": self.score,
            "lives": self.lives,
            "ball": {
                "x": self.ball.x,
                "y": self.ball.y,
                "radius": self.ball.radius,
                "dx": self.ball.dx,
                "dy": self.ball.dy,
            },
            "paddle": {
                "x": self.paddle.x,
                "y": self.paddle.y,
                "width": self.paddle.width,
                "height": self.paddle.height,
            },
            "bricks": [
                {
                    "x": b.x,
                    "y": b.y,
                    "width": b.width,
                    "height": b.height,
                    "color": b.color,
                    "alive": b.alive,
                }
                for b in self.bricks
            ],
        }