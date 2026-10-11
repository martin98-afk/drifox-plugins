# Solitaire 经典接龙

在 DriFox 中直接玩的经典接龙纸牌游戏（Klondike · 翻一张 · 可无限重翻牌堆）。

## 玩法

- 输入 `/solitaire` 打开浮动卡片
- 按住明牌拖动，同顺序序列整体跟拖；非法落点自动弹回
- 双击单张明牌自动送上收牌堆
- 点击左上牌堆翻牌；牌堆空后点击将废牌堆重置回牌堆
- 红黑交替降序叠放，空列只收 K；四堆按花色 A→K 收齐即通关

## 结构

```
solitaire/
├── .drifox-plugin/plugin.json   # manifest
├── ui/
│   ├── __init__.py              # register_ui，浮动卡注册
│   ├── game_logic.py            # 纯 Python 规则引擎（无 Qt 依赖，可单测）
│   ├── widgets.py               # CardWidget / DropZone 自绘牌面
│   └── solitaire_card.py        # 浮动卡片 + 拖拽控制器
└── tests/test_game_logic.py     # 规则引擎单元测试
```
