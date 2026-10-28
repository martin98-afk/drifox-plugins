# gongwen

中文公文全流程处理。按 **GB/T 9704《党政机关公文格式》** 国家标准，对 .docx 做格式检查与自动修复、Word 原生修订式内容优化、模板生成与样式学习、Markdown 转公文，覆盖通知/请示/报告/函/纪要等 25 类公文。

## 迁移来源

- 上游仓库：https://github.com/linhut/gongwen-skill
- 上游 npm 包：`gongwen-skill`（v2.15.0）
- 上游 license：MIT

## 内容

| 通道 | 产物 | 说明 |
|---|---|---|
| skills | `skills/gongwen/SKILL.md` | 2965 行完整操作手册：硬门控、路径决策树、GB/T 9704 格式基准、六维质量评分 |
| skills | `skills/gongwen/{engine,gongwen,rules,prompts,presets}` | 上游 Python 格式引擎与 CLI，原样保留 |
| tools | `tools/gongwen.py` | 单入口工具 `gongwen`，按 `command` 分发到 `python -m gongwen <cmd>` |

引擎没有重写：工具层只做参数翻译与子进程调用，格式规则、修订标注、模板生成全部走上游实现。

## 运行时依赖

Python 侧依赖见 `skills/gongwen/requirements.txt`（核心是 `python-docx`，YAML 规则解析优先用 `pyyaml`，缺失时上游自带兜底解析）。缺依赖时 `gongwen(command='doctor')` 会给出诊断。

## 常用命令

```
gongwen(command='list-types')                                    # 看 25 类公文类型
gongwen(command='check', input='通知.docx', doc_type='notice')     # 只读检查
gongwen(command='optimize', input='通知.docx', output='修复.docx')  # 自动修复格式
gongwen(command='md2docx', input='稿.md', doc_type='report')       # Markdown 转公文
gongwen(command='doctor')                                        # 环境诊断
```

## 与 dsh 原包的差异

- dsh 的 `cordis.patch.yml` 挂载逻辑未迁移（DriFox 无 cordis 运行时）。
- `dsh/index.js` 的 host 端逻辑等价重写为 `tools/gongwen.py`：上游也是 `spawn("python", ["-m", "gongwen", ...])`，语义一致。
- `dsh/client.js` 与 `dsh.client.inject`（dsh 设置页的配置面板）未迁移：DriFox 侧暂无对应 UI 载体。上游配置里的 `default_doc_type` 等默认值改用工具参数传入。
- `wizard` 交互式向导仍可用，但它是终端 TUI，模型调用时建议直接用 `--answers` 非交互模式。
- 上游 skill frontmatter 的 `whenToUse` / `user-invocable` 键已并入正文说明（DriFox 无这两个键）。
