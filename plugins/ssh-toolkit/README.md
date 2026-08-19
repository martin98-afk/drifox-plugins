# ssh-toolkit

SSH 远程工具包插件（纯 AI 工具，无 UI）。基于 paramiko，提供连接管理、命令执行、SFTP 文件传输、目录浏览、端口转发。

## 工具
- `ssh_add_connection` 保存命名连接
- `ssh_list_connections` 列出连接（密码掩码）
- `ssh_remove_connection` 删除连接
- `ssh_connect` 建立连接入池，返回 handle
- `ssh_exec` 执行命令（stdout/stderr/exit code）
- `ssh_upload` SFTP 上传
- `ssh_download` SFTP 下载
- `ssh_list_dir` 远程目录浏览
- `ssh_forward` 端口转发（后台）
- `ssh_disconnect` 关闭连接/转发

## 依赖
paramiko 及其依赖已 vendoring 于 `deps/`，运行时由插件加载器自动加入 `sys.path`，无需额外安装。

## 安全警告
连接配置（含密码/私钥口令）**明文**存于 `~/.drifox/cache/ssh/connections.json`，文件权限 600。
同机有读权限的进程/用户可见。生产环境建议使用 `publickey` + `ssh-agent`，避免存储密码。
