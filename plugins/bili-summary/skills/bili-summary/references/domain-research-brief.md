# Domain Research Brief — B 站视频总结

- Raw user intent: 通过评论、弹幕、字幕、抽帧识别等方法概括一个视频要讲的内容。
- Suspected domain(s): B 站（bilibili）Web 端公开接口；视频内容理解；ASR/OCR。
- Research intensity: `minimum-sweep`（核心接口已在本机实测，非猜测）
- Decision at stake: 阶梯式降级路线是否成立（字幕是否可无登录获取，决定第 1 级是否可用）
- Freshness / date boundary: 2026-10-27 本机实跑

## 实测证据卡（全部来自本机真实请求，非文档转述）

| # | 事实 | 证据 |
|---|---|---|
| E1 | `x/web-interface/view?bvid=` 免登录可用，返回 aid/cid/title/desc/duration/pages/stat | probe1: code 0，title/duration=213/pages/stat 全字段 |
| E2 | `x/v1/dm/list.so?oid=cid` 免登录返回 XML，Content-Encoding 为 **deflate** | probe1 原始字节乱码 + probe2 解压后 XML 正常；probe2 head_hex=b4fde972（zlib 裸流） |
| E3 | `x/v2/dm/web/seg.so` 返回 **protobuf 二进制**（非 XML），需解 pb | probe5: len=163777, hex=0a6d08...；且 probe3 用 JSON 解析直接抛 JSONDecodeError |
| E4 | `x/v2/reply?...&sort=2` 免登录可用，但只返回 **3 条**（被裁剪） | probe1/probe3: ps=5 实得 3 |
| E5 | `x/v2/reply/**main**?...` 免登录返回 **完整 ps 条**（sort=0 时间序也返回 5 条） | probe5: reply_time_main n=5（v2 端点同参数 n=0） |
| E6 | `x/v2/reply/wbi/main` 无签名 → code **-403 访问权限不足** | probe3 |
| E7 | `x/web-interface/view/conclusion/get`（官方 AI 总结）→ code **-403** | probe1 |
| E8 | WBI 签名算法正确：img/sub key 取 nav 的 wbi_img 文件名，mixin_key=`ea1db124af3c7062474693fa704f4ff8`，与官方示例逐字符一致 | probe3 输出对照 wbi.md 官方示例 |
| E9 | 签名后 `x/player/wbi/v2` 返回 code 0，但**字幕列表恒空**，`need_login_subtitle=true` | probe3/probe4/probe5 |
| E10 | 扫 10 个热门视频，带字幕者 **0 个** | probe4 found_with_subtitle=[] |
| E11 | `x/v2/subtitle/web/view` → code -400 请求错误 | probe6 |
| E12 | 未登录可直连 dash 视频流，200 / 33MB | probe4 stream_probe |
| E13 | ffmpeg 带 Referer+UA 直连远端 URL 抽帧成功，三帧均 960x540 有效 JPEG | probe6 + ffprobe 确认 |

## Key findings

1. **字幕在无 Cookie 环境下拿不到**（E9/E10/E11）。不是签名问题，是 B 站对未登录用户不返回字幕。这意味着"字幕优先"的阶梯第 1 级对未登录用户永远落空。
2. **弹幕有两条路**：XML（`x/v1/dm/list.so`，deflate 解压即 XML，最省事）和 protobuf（`x/v2/dm/web/seg.so`，能拿全量弹幕但需解 pb）。MVP 走 XML。
3. **评论必须用 `/main` 端点**，`x/v2/reply` 会被静默裁剪到 3 条（E4），这种"不报错但少给数据"最容易让总结质量无声劣化。
4. **视频流与抽帧完全可用**（E12/E13），所以"抽帧看图"是真正可靠的底座，而非兜底。

## Decision impact

阶梯顺序调整为：**元信息 → 弹幕(XML) → 评论(/main) → 官方 AI 总结 → 抽帧**。
字幕降级为"仅当用户提供 Cookie（SESSDATA）时尝试"，不作为默认第 1 级，否则未登录用户每次都白跑一级。

## Stop rule

- 未提供 SESSDATA 时不尝试字幕接口，直接跳过并在报告标注。
- 抽帧依赖本机 ffmpeg；缺失则停止并明确告知，不用"猜内容"填补。

## Decision

`make` — 可重复工作流、有稳定输入输出、需要 bundled 脚本与模板。
