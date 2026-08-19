# win-powershell

专用 Windows PowerShell 执行工具（DriFox 工具插件）。

## 它解决什么

DriFox 内置的 `bash` 工具在 Windows 下底层也调 PowerShell，但它执行的是**通用 shell 字符串**（cmd / PowerShell 混用、含安全分类与 findstr 修复）。

本插件提供一个**真正的 PowerShell 专用入口**，强制走 PowerShell 原生调用，面向 PS 原生用法：

- cmdlet（`Get-Process`、`Get-ChildItem` …）
- 管道对象（`Get-Process | Where-Object { $_.CPU -gt 10 }`）
- 结构化输出（`... | ConvertTo-Json`、`ConvertTo-Xml`）
- 脚本块（`{ ... }`）

## 编码方案（关键）

- 用 `-EncodedCommand`（UTF-16LE base64）传脚本，彻底规避 Windows 命令行非 ASCII 字符被破坏的问题（直接 `-Command "中文"` 会乱码）。
- 脚本开头强制 `[Console]::OutputEncoding = UTF-8`，使 stdout 可靠为 UTF-8；解码时再兜底 GBK / latin-1（兼容外部 exe 的 GBK 输出）。
- 解释器自动检测：优先 `pwsh`（PowerShell 7，UTF-8 更好），回退 `powershell`（Windows PowerShell 5.1，系统自带）。

## 工具：`powershell`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `script` | string | 是 | 要执行的 PowerShell 脚本/命令/脚本块 |
| `cwd` | string | 否 | 工作目录，默认当前项目目录 |
| `timeout` | integer | 否 | 超时秒数，默认 120（范围 1-3600） |

`danger = dangerous`：可执行任意命令，首次调用会触发权限确认。

## 示例

```powershell
# 取进程并按 CPU 排序，输出 JSON
Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 | ConvertTo-Json
```

```powershell
# 读取并解析 JSON 文件
(Get-Content ./config.json -Raw) | ConvertFrom-Json
```

```powershell
# 运行 .ps1 文件
& ".\scripts\deploy.ps1" -Env prod
```

## 安装

1. 把本插件目录放入 `~/.drifox/plugins/win-powershell/`（或 DriFox 工作树 `plugins/`）。
2. DriFox 会自动热加载（1-3 秒），无需重启。
3. 在 `/plugin-marketplace` 中确认已启用。

## 与 bash 工具怎么选

- 需要 **PowerShell 原生能力**（cmdlet、对象管道、结构化输出）→ 用本工具。
- 跑通用 shell 命令 / Git / npm 等 → 用内置 `bash` 即可。
