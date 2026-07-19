# -*- coding: utf-8 -*-
"""贪吃蛇核心逻辑——纯 Python，无 Qt 依赖

SnakeGame: 管理蛇身移动、食物生成、碰撞检测、计分、速度调整。
可独立单元测试。
"""

import random
from enum import Enum
from typing import List, Optional, Tuple


class Direction(Enum):
    """移动方向"""
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)


class GameState(Enum):
    """游戏状态"""
    READY = "ready"       # 等待开始
    PLAYING = "playing"   # 游戏中
    PAUSED = "paused"     # 已暂停
    WON = "won"           # 胜利（填满整个地图）
    LOST = "lost"         # 失败


class CollisionType(Enum):
    """碰撞类型"""
    NONE = "none"
    WALL = "wall"
    SELF = "self"
    FOOD = "food"


class SnakeGame:
    """贪吃蛇游戏引擎

    职责：
    - 管理蛇身数据（头+身体坐标列表）
    - 食物随机生成
    - 方向控制与移动
    - 碰撞检测（撞墙/撞自身）
    - 计分与速度调整
    - 胜利/失败判断

    Usage:
        game = SnakeGame(15, 15)
        game.set_direction(Direction.RIGHT)
        result = game.tick()  # 驱动一帧
    """

    # 初始速度（毫秒/帧）
    BASE_INTERVAL = 200
    # 每吃一个食物速度提升量（毫秒）
    SPEED_INCREMENT = 5
    # 最小间隔（毫秒）
    MIN_INTERVAL = 50

    def __init__(self, width: int, height: int):
        """初始化游戏

        Args:
            width: 网格宽度（列数）
            height: 网格高度（行数）
        """
        if width <= 2 or height <= 2:
            raise ValueError(f"网格尺寸必须大于 2x2: {width}x{height}")

        self.width = width
        self.height = height

        # 蛇身坐标列表，第一个是蛇头
        self._snake: List[Tuple[int, int]] = []
        # 当前方向
        self._direction: Direction = Direction.RIGHT
        # 下一个方向（防止一帧内连续变向）
        self._next_direction: Direction = Direction.RIGHT
        # 食物坐标
        self._food: Tuple[int, int] = (-1, -1)
        # 游戏状态
        self.state: GameState = GameState.READY
        # 分数
        self.score: int = 0
        # 已吃食物数量
        self._food_eaten: int = 0
        # 当前速度间隔
        self._interval: int = self.BASE_INTERVAL

    def start(self) -> dict:
        """开始新游戏

        Returns:
            dict: 初始状态信息
        """
        if self.state == GameState.PLAYING:
            return {"state": self.state, "error": "Game already started"}

        # 初始化蛇在中间位置，初始长度为 3
        cx, cy = self.width // 2, self.height // 2
        self._snake = [
            (cx, cy),
            (cx - 1, cy),
            (cx - 2, cy),
        ]

        self._direction = Direction.RIGHT
        self._next_direction = Direction.RIGHT
        self.score = 0
        self._food_eaten = 0
        self._interval = self.BASE_INTERVAL
        self.state = GameState.PLAYING

        # 生成第一个食物
        self._spawn_food()

        return self._get_state_info()

    def set_direction(self, direction: Direction) -> dict:
        """设置蛇的移动方向

        禁止 180 度掉头（防止直接撞到自己）

        Args:
            direction: 目标方向

        Returns:
            dict: {"success": bool, "state": GameState}
        """
        if self.state != GameState.PLAYING:
            return {"success": False, "state": self.state}

        # 禁止掉头（检查下一个方向，防止一帧内连续变向导致撞自己）
        opposites = {
            Direction.UP: Direction.DOWN,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
            Direction.RIGHT: Direction.LEFT,
        }

        if direction == opposites.get(self._next_direction):
            return {"success": False, "state": self.state}

        self._next_direction = direction
        return {"success": True, "state": self.state}

    def pause(self) -> dict:
        """暂停游戏"""
        if self.state == GameState.PLAYING:
            self.state = GameState.PAUSED
            return {"state": self.state, "paused": True}
        elif self.state == GameState.PAUSED:
            self.state = GameState.PLAYING
            return {"state": self.state, "paused": False}
        return {"state": self.state, "paused": self.state == GameState.PAUSED}

    def tick(self) -> dict:
        """驱动游戏一帧

        调用此方法推进游戏状态。

        Returns:
            dict: {
                "snake": [(x, y), ...],
                "food": (x, y),
                "collision": CollisionType,
                "game_over": bool,
                "won": bool,
                "state": GameState,
                "score": int,
                "interval": int,
            }
        """
        if self.state != GameState.PLAYING:
            return self._get_state_info()

        # 应用方向
        self._direction = self._next_direction

        # 计算新蛇头位置
        head_x, head_y = self._snake[0]
        dx, dy = self._direction.value
        new_head = (head_x + dx, head_y + dy)

        # 碰撞检测
        collision = self._check_collision(new_head)

        if collision == CollisionType.WALL:
            self.state = GameState.LOST
            return self._get_state_info(collision=collision, game_over=True)

        if collision == CollisionType.SELF:
            self.state = GameState.LOST
            return self._get_state_info(collision=collision, game_over=True)

        # 移动蛇
        self._snake.insert(0, new_head)

        if collision == CollisionType.FOOD:
            # 吃到食物：蛇身增长（不移除尾部）+ 计分
            self._food_eaten += 1
            self.score = self._food_eaten * 10

            # 速度提升
            self._interval = max(
                self.MIN_INTERVAL,
                self.BASE_INTERVAL - self._food_eaten * self.SPEED_INCREMENT
            )

            # 检查胜利（蛇身填满整个地图）
            if len(self._snake) >= self.width * self.height:
                self.state = GameState.WON
                return self._get_state_info(collision=collision, game_over=True, won=True)

            # 生成新食物
            self._spawn_food()
        else:
            # 普通移动：移除尾部
            self._snake.pop()

        return self._get_state_info(collision=collision)

    def _check_collision(self, pos: Tuple[int, int]) -> CollisionType:
        """检查碰撞

        Args:
            pos: 要检查的位置 (x, y)

        Returns:
            CollisionType: 碰撞类型
        """
        x, y = pos

        # 撞墙
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return CollisionType.WALL

        # 撞自身（排除蛇尾，因为移动后蛇尾会移动）
        if pos in self._snake[:-1]:
            return CollisionType.SELF

        # 吃食物
        if pos == self._food:
            return CollisionType.FOOD

        return CollisionType.NONE

    def _spawn_food(self) -> None:
        """在空白位置生成食物"""
        # 计算空白位置
        occupied = set(self._snake)
        empty_positions = [
            (x, y) for x in range(self.width) for y in range(self.height)
            if (x, y) not in occupied
        ]

        if empty_positions:
            self._food = random.choice(empty_positions)
        else:
            # 地图满了
            self._food = (-1, -1)

    def _get_state_info(self, collision: CollisionType = None,
                        game_over: bool = False, won: bool = False) -> dict:
        """获取当前状态信息"""
        return {
            "snake": list(self._snake),
            "food": self._food,
            "collision": collision or CollisionType.NONE,
            "game_over": game_over,
            "won": won,
            "state": self.state,
            "score": self.score,
            "interval": self._interval,
            "length": len(self._snake),
        }

    def get_state(self) -> dict:
        """获取当前状态（不推进游戏）"""
        return self._get_state_info()

    @property
    def snake(self) -> List[Tuple[int, int]]:
        """获取蛇身坐标列表"""
        return list(self._snake)

    @property
    def food(self) -> Tuple[int, int]:
        """获取食物坐标"""
        return self._food

    @property
    def direction(self) -> Direction:
        """获取当前方向"""
        return self._direction

    @property
    def interval(self) -> int:
        """获取当前速度间隔（毫秒）"""
        return self._interval

    def reset(self) -> None:
        """重置游戏（保留网格尺寸）"""
        self._snake = []
        self._direction = Direction.RIGHT
        self._next_direction = Direction.RIGHT
        self._food = (-1, -1)
        self.state = GameState.READY
        self.score = 0
        self._food_eaten = 0
        self._interval = self.BASE_INTERVAL