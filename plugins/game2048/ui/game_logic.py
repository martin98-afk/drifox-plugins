# -*- coding: utf-8 -*-
"""2048 核心逻辑——纯 Python，无 Qt 依赖

Game2048: 管理 4x4 网格、滑动合并、计分、胜利判断。
可独立单元测试。
"""

import random
from enum import Enum
from typing import List, Optional, Tuple


class Direction(Enum):
    """滑动方向"""
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class Game2048:
    """2048 游戏引擎

    职责：
    - 管理 4x4 网格状态
    - 处理四个方向的滑动合并
    - 生成随机数字（2 或 4）
    - 计分与最高分追踪
    - 判断胜利（达到 2048）与失败条件

    Usage:
        game = Game2048()
        game.init()
        result = game.move(Direction.LEFT)
        game.get_grid()
    """

    GRID_SIZE = 4
    WIN_VALUE = 2048

    def __init__(self):
        self._grid: List[List[int]] = [[0] * self.GRID_SIZE for _ in range(self.GRID_SIZE)]
        self._score: int = 0
        self._best_score: int = 0
        self._won: bool = False
        self._game_over: bool = False
        self._moved: bool = False  # 上一步是否有有效移动

    def init(self) -> None:
        """初始化游戏，生成两个初始数字"""
        self._grid = [[0] * self.GRID_SIZE for _ in range(self.GRID_SIZE)]
        self._score = 0
        self._won = False
        self._game_over = False
        self._moved = False
        self._add_random_tile()
        self._add_random_tile()

    def _add_random_tile(self) -> bool:
        """在空位置随机添加 2 或 4

        Returns:
            bool: 是否成功添加（还有空位返回 True）
        """
        empty_cells = self._get_empty_cells()
        if not empty_cells:
            return False
        x, y = random.choice(empty_cells)
        # 90% 概率生成 2，10% 概率生成 4
        self._grid[x][y] = 2 if random.random() < 0.9 else 4
        return True

    def _get_empty_cells(self) -> List[Tuple[int, int]]:
        """获取所有空单元格位置"""
        return [
            (x, y) for x in range(self.GRID_SIZE)
            for y in range(self.GRID_SIZE)
            if self._grid[x][y] == 0
        ]

    def _get_row(self, index: int) -> List[int]:
        """获取指定行"""
        return self._grid[index][:]
    
    def _get_col(self, index: int) -> List[int]:
        """获取指定列"""
        return [self._grid[i][index] for i in range(self.GRID_SIZE)]

    def _set_row(self, index: int, row: List[int]) -> None:
        """设置指定行"""
        self._grid[index] = row[:]

    def _set_col(self, index: int, col: List[int]) -> None:
        """设置指定列"""
        for i in range(self.GRID_SIZE):
            self._grid[i][index] = col[i]

    def move(self, direction: Direction) -> dict:
        """执行滑动操作

        Args:
            direction: 滑动方向

        Returns:
            dict: {
                "moved": bool,        # 是否有有效移动
                "grid": List[List[int]],  # 当前网格状态
                "score": int,         # 当前分数
                "best_score": int,    # 最高分
                "won": bool,          # 是否获胜（达到2048）
                "game_over": bool,    # 游戏是否结束
                "merged_cells": List[Tuple[int, int]],  # 本次合并的单元格位置
            }
        """
        if self._game_over:
            return self._build_result(False)

        self._moved = False
        merged_cells = []

        # 先检查是否游戏已结束
        if not self._get_empty_cells() and self._check_game_over():
            self._game_over = True
            return self._build_result(False)

        if direction == Direction.LEFT:
            merged_cells = self._slide_horizontal(lambda row: self._get_row(row), 
                                                   lambda row, data: self._set_row(row, data))
        elif direction == Direction.RIGHT:
            merged_cells = self._slide_horizontal(lambda row: self._get_row(row)[::-1],
                                                   lambda row, data: self._set_row(row, data[::-1]))
        elif direction == Direction.UP:
            merged_cells = self._slide_vertical(lambda col: self._get_col(col),
                                                lambda col, data: self._set_col(col, data))
        elif direction == Direction.DOWN:
            merged_cells = self._slide_vertical(lambda col: self._get_col(col)[::-1],
                                                lambda col, data: self._set_col(col, data[::-1]))

        if self._moved:
            self._add_random_tile()
            # 更新最高分
            if self._score > self._best_score:
                self._best_score = self._score
            # 检查是否达到 2048
            if not self._won and self._check_win():
                self._won = True
            # 检查是否游戏结束
            if self._check_game_over():
                self._game_over = True

        return self._build_result(self._moved, merged_cells)

    def _slide_horizontal(self, get_line, set_line) -> List[Tuple[int, int]]:
        """水平滑动合并"""
        merged_cells = []
        for i in range(self.GRID_SIZE):
            line = get_line(i)
            new_line, cells = self._merge_line(line)
            # 转换相对位置到网格坐标
            for rel_pos, _ in cells:
                merged_cells.append((i, rel_pos))
            set_line(i, new_line)
        return merged_cells

    def _slide_vertical(self, get_line, set_line) -> List[Tuple[int, int]]:
        """垂直滑动合并"""
        merged_cells = []
        for i in range(self.GRID_SIZE):
            line = get_line(i)
            new_line, cells = self._merge_line(line)
            # 转换相对位置到网格坐标
            for rel_pos, _ in cells:
                merged_cells.append((rel_pos, i))
            set_line(i, new_line)
        return merged_cells

    def _merge_line(self, line: List[int]) -> Tuple[List[int], List[Tuple[int, int]]]:
        """合并一行数字

        Args:
            line: 输入行（已按目标方向对齐为向左滑动）

        Returns:
            Tuple[List[int], List[Tuple]]: 合并后的行和合并位置列表
        """
        # 移除零
        non_zero = [x for x in line if x != 0]
        merged = []
        merged_positions = []
        skip_next = False

        for i in range(len(non_zero)):
            if skip_next:
                skip_next = False
                continue
            if i + 1 < len(non_zero) and non_zero[i] == non_zero[i + 1]:
                # 合并
                merged_value = non_zero[i] * 2
                merged.append(merged_value)
                self._score += merged_value
                # 记录合并位置
                merged_positions.append((len(merged) - 1, 0))
                skip_next = True
            else:
                merged.append(non_zero[i])

        # 填充零到右边
        while len(merged) < self.GRID_SIZE:
            merged.append(0)

        if merged != line:
            self._moved = True

        return merged, merged_positions

    def _check_win(self) -> bool:
        """检查是否达到 2048"""
        for row in self._grid:
            if self.WIN_VALUE in row:
                return True
        return False

    def _check_game_over(self) -> bool:
        """检查是否无有效移动"""
        # 还有空位可以继续
        if self._get_empty_cells():
            return False
        # 检查相邻格子是否可以合并
        for x in range(self.GRID_SIZE):
            for y in range(self.GRID_SIZE):
                val = self._grid[x][y]
                # 检查右边
                if x + 1 < self.GRID_SIZE and self._grid[x + 1][y] == val:
                    return False
                # 检查下边
                if y + 1 < self.GRID_SIZE and self._grid[x][y + 1] == val:
                    return False
        return True

    def _build_result(self, moved: bool, merged_cells: List[Tuple[int, int]] = None) -> dict:
        """构建结果字典"""
        return {
            "moved": moved,
            "grid": [row[:] for row in self._grid],
            "score": self._score,
            "best_score": self._best_score,
            "won": self._won,
            "game_over": self._game_over,
            "merged_cells": merged_cells or [],
        }

    def get_grid(self) -> List[List[int]]:
        """获取当前网格状态"""
        return [row[:] for row in self._grid]

    @property
    def score(self) -> int:
        """当前分数"""
        return self._score

    @property
    def best_score(self) -> int:
        """最高分"""
        return self._best_score

    @property
    def won(self) -> bool:
        """是否获胜"""
        return self._won

    @property
    def game_over(self) -> bool:
        """游戏是否结束"""
        return self._game_over

    @property
    def can_continue(self) -> bool:
        """是否可以继续游戏（在达到2048后）"""
        return self._won and not self._game_over