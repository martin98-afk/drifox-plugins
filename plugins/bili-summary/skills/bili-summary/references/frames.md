# 抽帧识别契约

> 抽帧是**可靠底座**而非兜底：实测未登录可直连 dash 流，ffmpeg 端到端抽帧成功（960x540 有效 JPEG）。
> 当弹幕/评论/AI 总结都拿不到有效内容时，必须走这一步。

## 前置

- 本机有 `ffmpeg`（实测 `D:\ffmpeg\bin\ffmpeg.exe` 可用）。缺了就停，照 `fallback.md` 降级。
- 已通过 `api.md` §L5 拿到 `dash.video[].baseUrl`。

## 抽帧命令（直连远端 URL，不落地整段视频）

```python
cmd = [
    "ffmpeg", "-y", "-loglevel", "error",
    "-user_agent", UA,
    "-headers", "Referer: https://www.bilibili.com/\r\n",
    "-ss", str(sec),              # 关键：-ss 放在 -i 之前，快几十倍
    "-i", video_url,
    "-frames:v", "1",
    "-vf", "scale=960:-1",        # 降分辨率省 token
    "-q:v", "4",
    dst_path,
]
```

⚠ **`-ss` 必须在 `-i` 之前**。放后面会先解码整段再 seek，长视频慢到不可用。
⚠ `-user_agent` 与 `-headers` 缺一不可，否则 412。

## 抽帧策略

按时长决定帧数（不是固定值，短视频抽多了浪费、长视频抽少了漏内容）：

| 时长 | 帧数 | 间隔 |
|------|------|------|
| ≤ 5 min | 6 | duration/6 |
| 5–20 min | 10 | duration/10 |
| 20–60 min | 16 | duration/16 |
| > 60 min | 20 | duration/20 |

抽帧点：跳过片头片尾各 5%（`start = duration*0.05`，`end = duration*0.95`），中间均匀取点。

## 识别路线

抽出的帧用宿主的视觉能力识别（`read` 图片路径 / 视觉模型）。

**优先级**：

1. **宿主原生视觉能力**（推荐）—— 直接 `read` 图片文件。
2. 无视觉能力时 → 照 `fallback.md` 降级，**禁止用标题脑补画面**。

## 输出

每帧产出一条记录，供最终报告引用：

```json
{"t": 90, "path": ".test/bili_frames/f90.jpg", "desc": "画面描述"}
```

最终报告里时间点标注格式为 `[画面@01:30]`。

## 清理

抽帧文件是临时产物，报告出完即可清理。不要留在插件目录里。
