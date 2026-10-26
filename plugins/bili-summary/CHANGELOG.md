# 更新日志

本文件记录 bili-summary 插件的变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-10-27

### 新增

- 首个版本：B 站视频总结技能（纯 skill 形态，无自研工具注册）。
- 采集阶梯：元信息（L0）、弹幕（L1）、评论（L2）、官方 AI 总结（L3）、字幕（L4）、抽帧（L5）。
- `scripts/bili_fetch.py`：标准库实现的采集器，支持 BV 号 / av 号 / b23 短链 / 完整 URL 输入。
- `scripts/check_env.py`：环境自检（ffmpeg / 连通性 / SESSDATA）。
- `scripts/check_package.py`：包结构自检。
- `references/api.md`：接口契约，全部经 2026-10-27 本机实测。
- `references/frames.md`：抽帧策略与命令（`--ss` 前置、Referer 要求）。
- `references/fallback.md`：逐层降级表与反模式。
- `assets/summary-template.md`：总结输出模板与证据来源标注规范。
- `evals/trigger-eval.json`：触发评测（5 正 / 5 负 / 3 near-miss / 3 ambiguous）。
- 输入归一化：av 号 → BV 号转换（官方 base58 + 异或置换算法）、多 P 分页 cid 定位。

### 说明

- 字幕层（L4）因 B 站对未登录用户不返回字幕而默认跳过，需提供 SESSDATA 才尝试。
- 抽帧层（L5）依赖本机 ffmpeg，缺失时降级并在报告中标注。
