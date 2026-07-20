# guizang-ppt-skill 🎤📊

> 由 [歸藏](https://github.com/op7418) 创建与维护 · [源仓库](https://github.com/op7418/guizang-ppt-skill)

**生成横向翻页网页 PPT + MiniMax TTS 逐页语音配音。**

## 功能

- **两种风格**：电子杂志 × 电子墨水 / 瑞士国际主义
- **30+ 种布局**：封面、幕封、数据大字报、时间线、KPI 塔、对比页等
- **WebGL 动效背景** + Motion One 入场动画
- **ESC 索引视图** + 低功耗模式
- ⭐ **MiniMax TTS 语音配音**：每页独立 MP3，翻页自动播放

## ⭐ 新增：语音配音

```bash
# 1. 设置 API Key
set MINIMAX_API_KEY=your_key_here

# 2. 生成演讲稿对应的 30 页 MP3
python scripts/generate_tts.py --input ppt/演讲稿.md --output-dir ppt/audio

# 3. 打开 ppt/index.html 即可体验翻页自动播放
```

## 快速开始

1. 告诉 AI 你的 PPT 主题
2. AI 按本技能指引完成全部生成
3. 打开 `ppt/index.html` 即可演示

## 键盘快捷键

| 按键 | 功能 |
|------|------|
| ← → / 空格 | 翻页 |
| ESC | 索引视图 |
| B | 低功耗模式 |
| `?slide=N` | URL 跳转 |

## 参考

- [源仓库](https://github.com/op7418/guizang-ppt-skill)
- 赞助方：360 安全龙虾(金牌赞助) · 真格 Token Grant(Grant Supporter)
