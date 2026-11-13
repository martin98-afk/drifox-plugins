# 诊断包（diagnostics-pack）

一键把排查所需的事实打包成 zip：最近日志、错误摘要、崩溃堆栈与 minidump、系统信息、插件清单、脱敏后的配置。

## 入口

| 入口 | 用法 |
|---|---|
| 设置卡 | 设置 → 插件 → **诊断包**：选选项 → 立即导出 → 打开导出目录 |
| 命令 | `/diag` 直接导出；`/diag --open` 导出后打开目录 |
| AI 工具 | `export_diagnostics`（参数：`include_crash_dumps` / `max_mb` / `note`） |

产物落在 `<应用数据目录>/diagnostics/drifox-diagnostics-<时间戳>.zip`，按「历史包保留」自动清理旧包。

## 包里有什么

```
README.txt            用途、隐私提醒
metadata.json         选项、条目、体积、脱敏计数、截断与跳过原因
system-info.txt       系统 / Python / Qt / 宿主版本 / 数据目录 / DRIFOX_* 环境变量
plugins.json          已安装用户插件清单（启用状态由 UI 侧提供，未知为 null）
config/app.config     宿主配置（脱敏）
config/plugin_data/   各插件配置（脱敏）
logs/*.log            最近 30 份日志，每份取末尾 1.5 MB
logs/recent-errors.txt  错误行与 Traceback 摘要
crash/*.log           崩溃堆栈（faulthandler / VEH）
crash/dumps/*.dmp     minidump（可关闭）
```

体积按未压缩字节算，默认上限 50 MB；超预算的条目跳过，原因写进 `metadata.json`。

## 脱敏口径

- 命中形态：`Bearer xxx`、`sk-*`、`gh*_*`、`xox?-*`、`AKIA*`、`AIza*`，以及 `api_key/secret/token/password/authorization/cookie` 等键值对。
- 不脱敏：本机路径、用户名、会话片段、minidump 内存内容。
- 所以公开上传前仍需人工检查，README.txt 里也写了这条。

## 选项

| 选项 | 默认 | 说明 |
|---|---|---|
| 包含崩溃 dump | 开 | minidump 体积大且可能含内存片段 |
| 单包体积上限 | 50 MB | 5–1000 |
| 历史包保留 | 5 份 | 只清理本插件生成的包 |

存在 `<应用数据目录>/plugin_data/diagnostics-pack/settings.json`。

## 开发

```
diagnostics-pack/
├── drifox_diag_pack/     核心：collect（采集）/ mask（脱敏）/ pack（打包）/ host_env（宿主适配）
├── tools/export_diagnostics.py   AI 工具
├── ui/                   设置卡 + /diag 命令 + QThread 导出
├── commands/diag.md
└── tests/test_diagnostics_pack.py
```

核心模块零宿主依赖，可直接跑单测：

```bash
python -m pytest plugins/diagnostics-pack/tests -q
```

插件依赖注入（`storage.data_dir` 等）只在 `host_env` / `ui` / `tools` 三处出现，核心不碰。
