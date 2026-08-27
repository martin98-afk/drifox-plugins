# ssh-toolkit 工具图标预览（v0.1.2）

> 三类 SVG，深色 + 浅色各一份（共 4 × 2 = 8 文件），由 `plugin_tool_loader` 自动加载。

## 1. 插件主图标（未改动）

| 模式 | 文件 |
|---|---|
| Light | `plugins/ssh-toolkit/icon.svg` |
| Dark  | `plugins/ssh-toolkit/icon_dark.svg` |

视觉：单色链子交错（`#333333` / `#ffffff`）。

## 2. 工具图标：连接类（沿用主插件视觉）

`icon="ssh_conn"` —— 应用于：

- `ssh_add_connection`
- `ssh_list_connections`
- `ssh_remove_connection`
- `ssh_connect`
- `ssh_disconnect`

| 模式 | 文件 | 预览 |
|---|---|---|
| Light (`#1f2937` stroke) | `tools/icons_light/ssh_conn.svg` | 链子符号（与主插件一致的识别点） |
| Dark  (`#ffffff` stroke) | `tools/icons/ssh_conn.svg` | 同上反色 |

## 3. 工具图标：通用 SSH（保持原状，未改动）

`icon="ssh"` —— 应用于：

- `ssh_exec`
- `ssh_list_dir`
- `ssh_forward`

| 模式 | 文件 |
|---|---|
| Light | `tools/icons_light/ssh.svg` |
| Dark  | `tools/icons/ssh.svg` |

视觉：终端框 + `>` + `→`（命令提示符风格）。

## 4. 工具图标：上传（新建）

`icon="ssh_upload"` —— 应用于：

- `ssh_upload`

| 模式 | 文件 | 视觉 |
|---|---|---|
| Light | `tools/icons_light/ssh_upload.svg` | 托盘底 + 上箭头 + 水平地线 |
| Dark  | `tools/icons/ssh_upload.svg` | 同上反色 |

## 5. 工具图标：下载（新建）

`icon="ssh_download"` —— 应用于：

- `ssh_download`

| 模式 | 文件 | 视觉 |
|---|---|---|
| Light | `tools/icons_light/ssh_download.svg` | 托盘底 + 下箭头 + 水平地线 |
| Dark  | `tools/icons/ssh_download.svg` | 同上反色 |

---

## 落地清单

| 文件 | 动作 |
|---|---|
| `tools/icons/ssh_conn.svg` | 新建 |
| `tools/icons_light/ssh_conn.svg` | 新建 |
| `tools/icons/ssh_upload.svg` | 新建 |
| `tools/icons_light/ssh_upload.svg` | 新建 |
| `tools/icons/ssh_download.svg` | 新建 |
| `tools/icons_light/ssh_download.svg` | 新建 |
| `tools/conn_mgmt.py` | `icon="ssh"` ×3 → `icon="ssh_conn"` |
| `tools/exec_tool.py` | `ssh_connect`/`ssh_disconnect` 改 `ssh_conn`，`ssh_exec` 保持 `ssh` |
| `tools/transfer.py` | `ssh_upload`→`ssh_upload`、`ssh_download`→`ssh_download`、`ssh_list_dir` 保持 `ssh` |
| `tools/forward.py` | 无改动（`icon="ssh"` 保持） |

## 验证

```bash
evolution_validate ssh-toolkit
```
