# -*- coding: utf-8 -*-
"""扫雷核心逻辑——纯 Python，无 Qt 依赖

MinesweeperGame: 管理棋盘状态、地雷布置、翻开设问、胜利判断。
可独立单元测试。
"""

import random
from collections import deque
from enum import Enum
from typing import List, Optional, Tuple


class CellState(Enum):
    """格子显示状态"""
    HIDDEN = "hidden"
    REVEALED = "revealed"
    FLAGGED = "flagged"


class GameState(Enum):
    """游戏状态"""
    READY = "ready"       # 等待首次点击
    PLAYING = "playing"   # 游戏中
    WON = "won"           # 胜利
    LOST = "lost"         # 失败


# 相邻格子偏移（8 方向）
NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1),
             (0, -1),           (0, 1),
             (1, -1),  (1, 0),  (1, 1)]


class MinesweeperGame:
    """扫雷游戏引擎

    职责：
    - 布置地雷（首次点击后延迟布局，保证首次安全）
    - 翻开格子（含空白连锁展开）
    - 切换旗帜标记
    - 检查胜利/失败条件
    - 提供棋盘查询接口

    Usage:
        game = MinesweeperGame(9, 9, 10)
        game.init_board(first_x=4, first_y=4)
        result = game.reveal(4, 4)  # 翻开格子
    """

    def __init__(self, width: int, height: int, mine_count: int):
        """初始化游戏

        Args:
            width: 棋盘宽度（列数）
            height: 棋盘高度（行数）
            mine_count: 地雷数量
        """
        if width <= 0 or height <= 0:
            raise ValueError(f"棋盘尺寸必须为正: {width}x{height}")
        if mine_count <= 0:
            raise ValueError(f"地雷数量必须为正: {mine_count}")
        if mine_count >= width * height:
            raise ValueError(f"地雷数量({mine_count})不能等于或超过格子总数({width*height})")

        self.width = width
        self.height = height
        self.mine_count = mine_count

        # 棋盘数据
        # _board[x][y] = -1 表示地雷，0-8 表示相邻地雷数
        self._board: List[List[int]] = [[0] * height for _ in range(width)]
        # 格子状态
        self._states: List[List[CellState]] = [[CellState.HIDDEN] * height for _ in range(width)]
        # 游戏状态
        self.state: GameState = GameState.READY
        # 是否已初始化（布过雷了）
        self._initialized: bool = False
        # 已翻开的格子数（用于胜利判断）
        self._revealed_count: int = 0

    def init_board(self, first_x: int, first_y: int) -> None:
        """首次点击后布置地雷

        保证 (first_x, first_y) 及其周围一圈都不是地雷。

        Args:
            first_x: 首次点击的 x 坐标
            first_y: 首次点击的 y 坐标
        """
        if self._initialized:
            return

        if not (0 <= first_x < self.width and 0 <= first_y < self.height):
            raise ValueError(f"坐标越界: ({first_x}, {first_y})")

        # 安全区域：首次点击位置 + 周围 8 格
        safe_positions = {(first_x, first_y)}
        for dx, dy in NEIGHBORS:
            nx, ny = first_x + dx, first_y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                safe_positions.add((nx, ny))

        # 生成所有可能的位置
        all_positions = [(x, y) for x in range(self.width) for y in range(self.height)
                         if (x, y) not in safe_positions]

        # 随机选择 mine_count 个位置布雷
        random.shuffle(all_positions)
        mine_positions = all_positions[:self.mine_count]

        # 如果可用位置不足，从安全区补充（但保留 first_click 位置）
        if len(mine_positions) < self.mine_count:
            extra_needed = self.mine_count - len(mine_positions)
            extra_positions = [(x, y) for x in range(self.width) for y in range(self.height)
                               if (x, y) in safe_positions and (x, y) != (first_x, first_y)]
            random.shuffle(extra_positions)
            mine_positions.extend(extra_positions[:extra_needed])

        # 放置地雷
        for mx, my in mine_positions:
            self._board[mx][my] = -1

        # 计算数字
        for mx, my in mine_positions:
            for dx, dy in NEIGHBORS:
                nx, ny = mx + dx, my + dy
                if 0 <= nx < self.width and 0 <= ny < self.height and self._board[nx][ny] != -1:
                    self._board[nx][ny] += 1

        self._initialized = True
        self.state = GameState.PLAYING

    def reveal(self, x: int, y: int) -> dict:
        """翻开指定格子

        Args:
            x: x 坐标
            y: y 坐标

        Returns:
            dict: {
                "changed": [(x, y, cell_value, is_mine), ...],
                "game_over": bool,
                "won": bool,
                "state": GameState,
            }
        """
        if self.state == GameState.WON or self.state == GameState.LOST:
            return {"changed": [], "game_over": True, "won": self.state == GameState.WON,
                    "state": self.state}

        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(f"坐标越界: ({x}, {y})")

        if self._states[x][y] != CellState.HIDDEN:
            return {"changed": [], "game_over": False, "won": False, "state": self.state}

        # 首次点击触发布局
        if not self._initialized:
            self.init_board(x, y)

        # 踩到地雷
        if self._board[x][y] == -1:
            self._states[x][y] = CellState.REVEALED
            self.state = GameState.LOST
            changed = [(x, y, -1, True)]
            # 显示所有地雷
            for mx in range(self.width):
                for my in range(self.height):
                    if self._board[mx][my] == -1 and self._states[mx][my] != CellState.REVEALED:
                        self._states[mx][my] = CellState.REVEALED
                        changed.append((mx, my, -1, True))
            return {"changed": changed, "game_over": True, "won": False, "state": self.state}

        # 翻开设问（连锁展开）
        changed = self._reveal_flood_fill(x, y)
        self._revealed_count += len(changed)

        # 检查胜利：所有非地雷格子都已翻开
        safe_count = self.width * self.height - self.mine_count
        if self._revealed_count >= safe_count:
            self.state = GameState.WON
            return {"changed": changed, "game_over": True, "won": True, "state": self.state}

        return {"changed": changed, "game_over": False, "won": False, "state": self.state}

    def _reveal_flood_fill(self, x: int, y: int) -> List[tuple]:
        """翻开格子（含空白连锁展开）

        使用 BFS 展开空白区域。
        """
        changed = []
        queue = deque()
        queue.append((x, y))
        visited = set()

        while queue:
            cx, cy = queue.popleft()
            if (cx, cy) in visited:
                continue
            visited.add((cx, cy))

            if self._states[cx][cy] != CellState.HIDDEN:
                continue

            # 翻开当前格子
            self._states[cx][cy] = CellState.REVEALED
            value = self._board[cx][cy]
            changed.append((cx, cy, value, False))

            # 如果是空白格（周围无雷），加入相邻格子
            if value == 0:
                for dx, dy in NEIGHBORS:
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                        if (nx, ny) not in visited and self._states[nx][ny] == CellState.HIDDEN:
                            queue.append((nx, ny))

        return changed

    def toggle_flag(self, x: int, y: int) -> dict:
        """切换旗帜标记

        Args:
            x: x 坐标
            y: y 坐标

        Returns:
            dict: {"flagged": bool, "flag_count": int}
        """
        if self.state != GameState.PLAYING and self.state != GameState.READY:
            return {"flagged": False, "flag_count": self.flag_count}

        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(f"坐标越界: ({x}, {y})")

        if self._states[x][y] == CellState.REVEALED:
            return {"flagged": False, "flag_count": self.flag_count}

        if self._states[x][y] == CellState.FLAGGED:
            self._states[x][y] = CellState.HIDDEN
        else:
            self._states[x][y] = CellState.FLAGGED

        return {"flagged": self._states[x][y] == CellState.FLAGGED,
                "flag_count": self.flag_count}

    @property
    def flag_count(self) -> int:
        """当前旗帜数量"""
        count = 0
        for x in range(self.width):
            for y in range(self.height):
                if self._states[x][y] == CellState.FLAGGED:
                    count += 1
        return count

    def get_cell(self, x: int, y: int) -> dict:
        """获取格子信息

        Returns:
            dict: {"state": CellState, "value": int, "is_mine": bool}
        """
        return {
            "state": self._states[x][y],
            "value": self._board[x][y],
            "is_mine": self._board[x][y] == -1,
        }

    def reset(self, width: Optional[int] = None, height: Optional[int] = None,
              mine_count: Optional[int] = None) -> None:
        """重置游戏

        Args:
            width: 新棋盘宽度（None 保持原值）
            height: 新棋盘高度（None 保持原值）
            mine_count: 新地雷数（None 保持原值）
        """
        if width is not None:
            self.width = width
        if height is not None:
            self.height = height
        if mine_count is not None:
            self.mine_count = mine_count

        self._board = [[0] * self.height for _ in range(self.width)]
        self._states = [[CellState.HIDDEN] * self.height for _ in range(self.width)]
        self.state = GameState.READY
        self._initialized = False
        self._revealed_count = 0
