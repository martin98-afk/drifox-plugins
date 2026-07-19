# -*- coding: utf-8 -*-
"""俄罗斯方块核心逻辑——纯 Python，无 Qt 依赖

TetrisGame: 管理棋盘状态、方块生成/下落/旋转/碰撞、行消除、计分。
可独立单元测试。
"""

from enum import Enum
from typing import List, Optional, Tuple
import random


# ── 7 种标准方块定义 ──
# 每个方块用 4 个 (x, y) 相对坐标表示，中心为 (0,0)
# 顺序：[原始形态, 旋转90°, 旋转180°, 旋转270°]
TETROMINOES = {
    "I": {
        "color": "#00BCD4",
        "shapes": [
            [(0, 0), (1, 0), (2, 0), (3, 0)],
            [(1, 0), (1, 1), (1, 2), (1, 3)],
            [(0, 1), (1, 1), (2, 1), (3, 1)],
            [(2, 0), (2, 1), (2, 2), (2, 3)],
        ],
    },
    "O": {
        "color": "#FFEB3B",
        "shapes": [
            [(1, 0), (2, 0), (1, 1), (2, 1)],
            [(1, 0), (2, 0), (1, 1), (2, 1)],
            [(1, 0), (2, 0), (1, 1), (2, 1)],
            [(1, 0), (2, 0), (1, 1), (2, 1)],
        ],
    },
    "T": {
        "color": "#9C27B0",
        "shapes": [
            [(1, 0), (0, 1), (1, 1), (2, 1)],
            [(1, 0), (1, 1), (2, 1), (1, 2)],
            [(0, 1), (1, 1), (2, 1), (1, 2)],
            [(1, 0), (0, 1), (1, 1), (1, 2)],
        ],
    },
    "S": {
        "color": "#4CAF50",
        "shapes": [
            [(1, 0), (2, 0), (0, 1), (1, 1)],
            [(1, 0), (1, 1), (2, 1), (2, 2)],
            [(1, 1), (2, 1), (0, 2), (1, 2)],
            [(0, 0), (0, 1), (1, 1), (1, 2)],
        ],
    },
    "Z": {
        "color": "#F44336",
        "shapes": [
            [(0, 0), (1, 0), (1, 1), (2, 1)],
            [(2, 0), (1, 1), (2, 1), (1, 2)],
            [(0, 1), (1, 1), (1, 2), (2, 2)],
            [(1, 0), (0, 1), (1, 1), (0, 2)],
        ],
    },
    "L": {
        "color": "#FF9800",
        "shapes": [
            [(1, 0), (1, 1), (1, 2), (2, 2)],
            [(0, 1), (1, 1), (2, 1), (2, 2)],
            [(0, 0), (1, 0), (1, 1), (1, 2)],
            [(0, 0), (0, 1), (1, 1), (2, 1)],
        ],
    },
    "J": {
        "color": "#3F51B5",
        "shapes": [
            [(2, 0), (2, 1), (1, 2), (2, 2)],
            [(0, 0), (0, 1), (1, 1), (2, 1)],
            [(0, 0), (1, 0), (0, 1), (0, 2)],
            [(0, 1), (1, 1), (2, 1), (2, 2)],
        ],
    },
}

TETROMINO_NAMES = list(TETROMINOES.keys())


class GameState(Enum):
    """游戏状态"""
    READY = "ready"
    PLAYING = "playing"
    PAUSED = "paused"
    GAME_OVER = "game_over"


class TetrisGame:
    """俄罗斯方块游戏引擎

    棋盘坐标系: x 为列(0~width-1)，y 为行(0~height-1)，y 向下递增
    方块位置: (x, y) 表示方块左上角，参考点为方块 bounding box 的左上角

    职责：
    - 生成新方块（含预览下一块）
    - 左右移动、旋转、软降、硬降
    - 碰撞检测
    - 行满消除
    - 计分、等级、游戏速度递增
    - 游戏结束检测
    """

    BOARD_EMPTY = None  # 棋盘空格标记

    def __init__(self, width: int = 10, height: int = 20):
        if width < 4 or height < 4:
            raise ValueError(f"棋盘尺寸太小: {width}x{height}")

        self.width = width
        self.height = height

        # 棋盘: board[x][y] = None 或 "I"/"O"/... 颜色方块
        self._board: List[List[Optional[str]]] = [
            [self.BOARD_EMPTY] * height for _ in range(width)
        ]

        # 游戏状态
        self.state: GameState = GameState.READY

        # 当前活动方块
        self._current: Optional[dict] = None   # {"type": "I", "rotation": 0, "x": int, "y": int}
        # 下一块
        self._next: Optional[str] = None

        # 计分
        self.score: int = 0
        self.level: int = 1
        self.lines_cleared: int = 0

        # 随机序列（7-bag 随机洗牌）
        self._bag: List[str] = []
        self._refill_bag()

    # ── 方块生成 ──

    def _refill_bag(self):
        """重新填充 7-bag"""
        self._bag = TETROMINO_NAMES[:]
        random.shuffle(self._bag)

    def _pop_from_bag(self) -> str:
        """从 bag 取出一个方块类型"""
        if not self._bag:
            self._refill_bag()
        return self._bag.pop()

    def _preview_next(self) -> str:
        """预览下一个方块（不消耗它）"""
        if not self._bag:
            self._refill_bag()
        return self._bag[-1]

    def _spawn(self) -> bool:
        """生成新方块到棋盘顶部中央

        Returns:
            True 如果生成成功，False 如果生成位置已被占用（游戏结束）
        """
        piece_type = self._next if self._next else self._pop_from_bag()
        self._next = self._pop_from_bag()

        rotation = 0
        shapes = TETROMINOES[piece_type]["shapes"]
        # 计算初始位置：居中，顶部留 2 行可见
        min_x = min(cx for cx, cy in shapes[rotation])
        max_x = max(cx for cx, cy in shapes[rotation])
        spawn_x = (self.width - (max_x - min_x + 1)) // 2 - min_x
        spawn_y = 0

        self._current = {
            "type": piece_type,
            "rotation": rotation,
            "x": spawn_x,
            "y": spawn_y,
        }

        # 检查生成位置是否与已有方块重叠
        if self._check_collision(self._current):
            self.state = GameState.GAME_OVER
            return False
        return True

    # ── 方块坐标计算 ──

    def _get_cells(self, piece: dict) -> List[Tuple[int, int]]:
        """获取方块所有 4 个格子在棋盘上的绝对坐标"""
        shape = TETROMINOES[piece["type"]]["shapes"][piece["rotation"]]
        return [(piece["x"] + cx, piece["y"] + cy) for cx, cy in shape]

    def _get_current_cells(self) -> List[Tuple[int, int]]:
        return self._get_cells(self._current)

    # ── 碰撞检测 ──

    def _check_collision(self, piece: dict) -> bool:
        """检测给定方块是否与边界或已落方块碰撞"""
        for cx, cy in self._get_cells(piece):
            # 越界
            if cx < 0 or cx >= self.width or cy >= self.height:
                return True
            # y < 0 允许（方块刚生成时部分在顶部之上）
            if cy < 0:
                continue
            # 与已有方块重叠
            if self._board[cx][cy] is not None:
                return True
        return False

    def _check_collision_at(self, dx: int, dy: int, rotation: int) -> bool:
        """检测将当前方块移动 (dx, dy) 并旋转到 rotation 是否碰撞"""
        if self._current is None:
            return True
        test_piece = {
            "type": self._current["type"],
            "rotation": rotation,
            "x": self._current["x"] + dx,
            "y": self._current["y"] + dy,
        }
        return self._check_collision(test_piece)

    # ── 方块操作 ──

    def move_left(self) -> bool:
        """左移"""
        if not self._can_act():
            return False
        if not self._check_collision_at(-1, 0, self._current["rotation"]):
            self._current["x"] -= 1
            return True
        return False

    def move_right(self) -> bool:
        """右移"""
        if not self._can_act():
            return False
        if not self._check_collision_at(1, 0, self._current["rotation"]):
            self._current["x"] += 1
            return True
        return False

    def rotate(self) -> bool:
        """顺时针旋转 90°（带 wall kick 补偿）"""
        if not self._can_act():
            return False
        new_rotation = (self._current["rotation"] + 1) % 4

        # 尝试标准位置
        if not self._check_collision_at(0, 0, new_rotation):
            self._current["rotation"] = new_rotation
            return True

        # Wall kick: 尝试左右偏移 1 格
        for kick in [-1, 1]:
            if not self._check_collision_at(kick, 0, new_rotation):
                self._current["rotation"] = new_rotation
                self._current["x"] += kick
                return True

        # Wall kick: 尝试左右偏移 2 格（I 型长条需要）
        for kick in [-2, 2]:
            if not self._check_collision_at(kick, 0, new_rotation):
                self._current["rotation"] = new_rotation
                self._current["x"] += kick
                return True

        return False

    def soft_drop(self) -> bool:
        """软降（加速下落一格）"""
        if not self._can_act():
            return False
        if not self._check_collision_at(0, 1, self._current["rotation"]):
            self._current["y"] += 1
            self.score += 1  # 软降得分
            return True
        else:
            self._lock_piece()
            return False

    def hard_drop(self) -> dict:
        """硬降——直接落到底部

        Returns:
            dict: {"dropped": int, "cleared_rows": list[int]}
        """
        if not self._can_act():
            return {"dropped": 0, "cleared_rows": []}
        dropped = 0
        while not self._check_collision_at(0, 1, self._current["rotation"]):
            self._current["y"] += 1
            dropped += 1
        self.score += dropped * 2  # 硬降得分
        cleared = self._lock_piece()
        return {"dropped": dropped, "cleared_rows": cleared}

    def _lock_piece(self) -> List[int]:
        """锁定当前方块到棋盘，触发行消除

        Returns:
            List[int]: 消除的行号列表
        """
        if self._current is None:
            return []
        color = TETROMINOES[self._current["type"]]["color"]
        for cx, cy in self._get_current_cells():
            if 0 <= cx < self.width and 0 <= cy < self.height:
                self._board[cx][cy] = color

        self._current = None
        return self._clear_lines()

    def _clear_lines(self) -> List[int]:
        """检测并消除已满的行

        Returns:
            List[int]: 被消除的行号列表（用于特效展示）
        """
        full_rows = []
        for y in range(self.height):
            if all(self._board[x][y] is not None for x in range(self.width)):
                full_rows.append(y)

        if not full_rows:
            return []

        # ★ 修复：先全部删除，再统一在头部补充空行
        # 避免 insert(0) 导致后续索引偏移
        for y in sorted(full_rows, reverse=True):
            for x in range(self.width):
                del self._board[x][y]

        for x in range(self.width):
            for _ in full_rows:
                self._board[x].insert(0, self.BOARD_EMPTY)

        # 计分
        n = len(full_rows)
        # 经典计分规则
        line_scores = {1: 100, 2: 300, 3: 500, 4: 800}
        self.score += line_scores.get(n, n * 100)
        self.lines_cleared += n

        # 升级（每 10 行升一级）
        new_level = self.lines_cleared // 10 + 1
        if new_level > self.level:
            self.level = new_level

        return full_rows

    # ── 游戏控制 ──

    def start(self):
        """开始或继续游戏"""
        if self.state == GameState.GAME_OVER:
            return
        if self.state == GameState.READY:
            self._next = self._pop_from_bag()
            self._spawn()
        self.state = GameState.PLAYING

    def pause(self):
        """暂停游戏"""
        if self.state == GameState.PLAYING:
            self.state = GameState.PAUSED
        elif self.state == GameState.PAUSED:
            self.state = GameState.PLAYING

    def reset(self):
        """重置游戏"""
        self._board = [
            [self.BOARD_EMPTY] * self.height for _ in range(self.width)
        ]
        self._current = None
        self._next = None
        self.score = 0
        self.level = 1
        self.lines_cleared = 0
        self.state = GameState.READY
        self._bag = []
        self._refill_bag()

    def _can_act(self) -> bool:
        """是否允许操作"""
        return self.state == GameState.PLAYING and self._current is not None

    # ── 下落步进 ──

    def tick(self) -> dict:
        """游戏主循环步进——下落一格

        Returns:
            dict: {
                "game_over": bool,
                "lines_cleared": int,   # 本步消除行数（0~4）
                "cleared_rows": list[int],  # 消除的行号（用于特效）
                "level_up": bool,
                "state": GameState,
            }
        """
        base = {"game_over": False, "lines_cleared": 0, "cleared_rows": [],
                "level_up": False, "state": self.state}

        if self.state != GameState.PLAYING:
            return {**base, "state": self.state}

        if self._current is None:
            # 生成下一块
            if not self._spawn():
                return {**base, "game_over": True, "state": self.state}
            return base

        # 尝试下落
        if not self._check_collision_at(0, 1, self._current["rotation"]):
            self._current["y"] += 1
            return base
        else:
            # 无法下落，锁定
            old_lines = self.lines_cleared
            old_level = self.level
            cleared_rows = self._lock_piece()

            # 检查是否生成新块后立即游戏结束
            if self.state == GameState.GAME_OVER:
                return {**base, "game_over": True, "state": self.state}

            lines = self.lines_cleared - old_lines
            level_up = self.level > old_level

            # 生成新块
            if not self._spawn():
                return {**base, "game_over": True, "lines_cleared": lines,
                        "cleared_rows": cleared_rows, "level_up": level_up, "state": self.state}
            return {**base, "lines_cleared": lines, "cleared_rows": cleared_rows,
                    "level_up": level_up, "state": self.state}

    # ── 查询接口 ──

    def get_board(self) -> List[List[Optional[str]]]:
        """获取棋盘快照（含活动方块）"""
        # 返回一份副本
        board_copy = [row[:] for row in self._board]
        if self._current is not None and self.state == GameState.PLAYING:
            color = TETROMINOES[self._current["type"]]["color"]
            for cx, cy in self._get_current_cells():
                if 0 <= cx < self.width and 0 <= cy < self.height:
                    board_copy[cx][cy] = color
        return board_copy

    def get_current_piece(self) -> Optional[dict]:
        """获取当前活动方块信息"""
        return self._current

    def get_next_piece(self) -> Optional[str]:
        """获取下一个方块类型"""
        return self._next

    def get_drop_interval(self) -> int:
        """根据等级返回下落间隔（毫秒）

        等级越高，速度越快
        """
        intervals = {
            1: 800, 2: 700, 3: 600, 4: 500, 5: 400,
            6: 300, 7: 250, 8: 200, 9: 150, 10: 100,
        }
        return intervals.get(self.level, max(100, 1000 - self.level * 80))