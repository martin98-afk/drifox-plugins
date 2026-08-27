# -*- coding: utf-8 -*-
"""cron-tasks 插件 — 定时任务中心（参考 openhanako desk cron 设计移植）

可视化配置 UI 定时任务（单次/间隔/Cron 表达式），到期后经主程序
EngineSession（services["create_engine_session"]）驱动对话执行 prompt，
运行历史落盘 runs/<jobId>.jsonl。UI 组件模式参考 autoloop 插件。
"""
