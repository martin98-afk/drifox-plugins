# Audio 语音合成与播放集成

> ⭐ 新增能力，基于 MiniMax TTS 为每页生成语音讲解并集成到 HTML 翻页自动播放。

---

## 一、整体架构

```
演讲稿.md → generate_tts.py (MiniMax TTS API) → audio/p01.mp3 ~ p30.mp3 → index.html 翻页自动播放
```

## 二、演讲稿格式要求

TTS 脚本按 `## P\d+` 分页，提取 `**演讲词**` 标记后的文本。标准格式：

```markdown
## P01 · 页面标题

**演讲词**（约 X 分钟，风格提示）：
> 演讲稿正文...
```

## 三、TTS 脚本用法

```bash
# 设置 API Key（必须！绝不硬编码）
set MINIMAX_API_KEY=your_key_here

# 生成全部
python scripts/generate_tts.py --input ppt/演讲稿.md --output-dir ppt/audio

# 指定音色
python scripts/generate_tts.py --input ppt/演讲稿.md --output-dir ppt/audio --voice female-shaonv

# Dry-run 预览
python scripts/generate_tts.py --input ppt/演讲稿.md --output-dir ppt/audio --dry-run
```

### 推荐音色

| 音色 ID | 类型 | 适合场景 |
|---------|------|---------|
| `male-qn-qingse` | 男声清晰 | 技术讲座、培训（默认推荐） |
| `audiobook_male_1` | 男声播音 | 正式汇报、产品发布 |
| `female-shaonv` | 女声柔和 | 科普、教育 |
| `female-zhiling` | 女声知性 | 管理层汇报 |

## 四、HTML 集成

### 4.1 控制条 HTML

放在 `<div id="nav"></div>` 后面：

```html
<div id="audio-control">
  <button id="audio-play-btn" aria-label="播放/暂停语音讲解">▶</button>
  <span id="audio-status">语音讲解</span>
  <div id="audio-progress"><div id="audio-progress-bar"></div></div>
</div>
```

### 4.2 CSS

放在 `<style>` 的 `#nav` 样式附近，适配亮色/暗色主题：

```css
#audio-control{position:fixed;left:50%;bottom:5.5vh;transform:translateX(-50%);z-index:31;display:flex;align-items:center;gap:10px;padding:5px 14px;background:rgba(0,0,0,.06);backdrop-filter:blur(8px);border-radius:20px;font-family:var(--sans-zh),var(--sans);font-size:12px;color:var(--text-secondary);transition:opacity .3s;cursor:default;user-select:none}
body.dark-bg #audio-control{background:rgba(255,255,255,.08);color:var(--paper)}
#audio-play-btn{background:none;border:0;cursor:pointer;font-size:16px;color:var(--ink);opacity:.7}
body.dark-bg #audio-play-btn{color:var(--paper)}
#audio-progress{width:40px;height:3px;background:rgba(0,0,0,.12);border-radius:2px;overflow:hidden}
body.dark-bg #audio-progress{background:rgba(255,255,255,.15)}
#audio-progress-bar{height:100%;width:0%;background:var(--accent);transition:width .3s linear}
```

### 4.3 JS 音频管理

在 `go()` 函数末尾添加音频触发（在 `lock=true;setTimeout(()=>lock=false,700);` 之前）：

```javascript
setTimeout(()=>playAudioForSlide(idx), 300);
```

然后在 `go()` 函数和 ESC 索引视图之间插入完整的音频管理代码（见 Step 7.5 ④）。

### 4.4 集成验证清单

- [ ] 音频控制条显示在底部导航点上方
- [ ] 首次打开显示"▶ 点击播放讲解"（浏览器自动播放策略）
- [ ] 点击 ▶ 开始播放，按钮变为 ⏸
- [ ] 翻页自动加载并播放对应音频
- [ ] 进度条随播放推进
- [ ] 音频播完自动翻至下一页
- [ ] 暗色页面下控制条自动反色
- [ ] 按 B 键低功耗模式暂停音频
- [ ] 音频文件路径 `./audio/pXX.mp3` 正确

## 五、常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 音频不自动播放 | 浏览器自动播放策略 | 用户首次手动点击 ▶ 后即可启用 |
| 音频加载失败 | 文件路径不对或文件缺失 | 检查 `./audio/pXX.mp3` 是否存在 |
| API 返回 401 | API Key 无效或未设置 | 检查 `MINIMAX_API_KEY` 环境变量 |
| 合成文本超长 | 单段 > 10,000 字符 | 拆分演讲词或缩短文案 |
