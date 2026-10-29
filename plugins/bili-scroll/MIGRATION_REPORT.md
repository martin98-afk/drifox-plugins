# -*- coding: utf-8 -*-
"""bili-scroll 迁移报告（dsh-bili-scroll v2.3.0 → DriFox 插件）。

## 迁移决策
- 值班章程 prompts/duty.md → skills/bili-scroll-duty/SKILL.md（port，改写点：
  headless 会话→引擎会话轮、AGENTS.md 内联→persona 设置注入、duty_* 工具名→bili_*、
  dsh 桌宠梗删除、全部实测教训保留）
- vendor/bilibili-mcp 工具函数 → 宿主进程内注册为 DriFox tools（tools/bili_tools.py，
  遍历 FastMCP 工具表动态注册，asyncio.run 包装；26 个工具，上游逻辑零改动）
- deps/ + deps/win32/ 随插件自带依赖（deps_loader 规范；宿主已有的 41 包不 vendor 防遮蔽）
- vendor patch ⑦：CRED_FILE 支持 BILI_CRED_FILE env（凭证落 plugin_data）
- 峰谷调度 → biliscroll_core/scheduler.py（QTimer 5min tick，窗口内每天一轮，先记账再跑）
- 判重/日报/归档 → biliscroll_core/store.py（seen.tsv / out/ / digest/，plugin_data 落盘）
- UI：设置四页签+卡片墙 → 浮动卡 full（状态/跑一轮/日报预览/最近判重）+ config_schema 自动卡

## 未映射（不迁移）
- 专用 profile 沙箱（dsh 固有）：DriFox 无 per-session 工具白名单；等效闸门=值班轮
  turn(tools=) 子集 + 窄口工具固定路径 + bili_reply 需配置开启
- 本地转写三工具（asr.py 依赖 Whisper 模型 538MB）：v1 未启用，章程已声明跳过口径
- headless 专用 profile / Web UI 设置页（React）/ qrcode 设置页内嵌（对话内出码）

## MIGRATION_TODO
- 无未处理项。转写三件套属显式 v1 边界（报告+README+章程三处声明）。

## 验证证据（runtime）
- py_compile 全部通过；validate_plugins.py 结构 OK（marketplace 未收录属发布前规则）
- deps 注入 + import mcp_server + FastMCP 工具表 = 26 工具
- bili_video_zones 实调返回真实分区数据（免登录）
- 待人工：扫码登录 → bili_duty_run 真跑一轮 → 日报落盘检查

## 写回决策
- proposal：宿主 .mcp.json 无宿主解释器占位符，stdio MCP 无法与 vendored 二进制
  ABI 匹配（py -3 版本不可控）——若未来要支持重依赖 MCP 插件，可提 ${DRIFOX_PYTHON}
  占位符；本次以宿主进程内 tools 通道绕开
"""
