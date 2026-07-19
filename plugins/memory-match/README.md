# 🧠 Memory Match - DriFox 记忆翻牌插件

在 DriFox 聊天界面中直接玩经典记忆翻牌游戏！

## 使用

输入 `/memory-match` 打开记忆翻牌卡片。

## 功能

- **三种难度**：
  - 初级 4×4（8 对）
  - 中级 4×6（12 对）
  - 高级 5×6（15 对）
- **Emoji 图案**：32 种不同 emoji，每种两张
- **翻牌动画**：流畅的翻转效果
- **步数计时**：记录翻牌次数和游戏时间
- **配对动画**：配对成功时脉冲高亮
- **智能翻回**：配对失败 1 秒后自动翻回
- **跟随 DriFox 主题色**

## 架构

```
memory-match/
├── .drifox-plugin/
│   └── plugin.json       # 插件元数据
├── ui/
│   ├── __init__.py       # UI 注册入口
│   ├── game_logic.py     # 核心逻辑（纯 Python）
│   ├── memory_card.py    # 主卡片组件
│   └── widgets.py        # 自定义组件
├── tests/
│   └── test_game_logic.py # 单元测试
├── icon.svg              # 浅色主题图标
├── icon_dark.svg         # 深色主题图标
└── README.md
```

## 设计原则

- **纯逻辑分离**：`game_logic.py` 不依赖 Qt，可独立测试
- **无 app.core 依赖**：不导入 DriFox 内部核心模块
- **主题适配**：自动跟随 DriFox 主题色