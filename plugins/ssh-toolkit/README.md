# ssh-toolkit

SSH 远程工具包插件（AI 工具 + 系统设置页连接管理）。基于 paramiko，提供连接管理、命令执行、SFTP 文件传输、目录浏览、端口转发。

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

## 安全边界

### 加密后端仲裁（cryptography 来源）
cx_Freeze 打包版宿主内嵌了自己版本的 cryptography，其 `FrozenImporter` 挂在
`sys.meta_path`，优先级高于 sys.path —— 插件 deps 的 cryptography 会被截胡，
paramiko 因此被绑到宿主副本上。实测该副本 AES-CTR 不可用，连接协商到
`aes-*-ctr` 时报 `cipher AES in CTR mode is not supported`。

插件在 import paramiko 前做来源仲裁（`tools/_auth.py`）：meta_path 钩子把
`cryptography*` 的 import 强制指向插件 deps 目录，加载后先跑 AES-CTR 自检，
通过才保留；任何失败（deps 缺失/自检不过）都会回滚到宿主原状，保证插件可加载。

### 主机身份（host_key_policy）
默认 `tofu`（Trust On First Use）：首次连接把主机密钥指纹写入
`~/.drifox/cache/ssh/known_hosts`，并在 `ssh_connect` 返回内容里回显 `SHA256:` 指纹；
之后同一主机的密钥若变化，paramiko 直接抛 `BadHostKeyException` 拒绝连接。

- `strict`：未知主机一律拒绝，只认已登记条目。
- `off`：不校验（等价旧版 AutoAddPolicy），仅在明确知情时使用。

系统 `~/.ssh/known_hosts` 已登记的主机自动可信，不会重复记录。

### 本地路径边界（ssh_upload / ssh_download）
宿主沙箱按「文件写入/读取」分组 + `path` 字段路由，插件参数叫 `local_path`，两者匹配不上，
所以这套工具自带边界（`tools/_guard.py`）：

- 本地路径必须落在当前工作目录内；可用 `allow_paths` 显式追加允许的根目录。
- 硬黑名单不受 `allow_paths` 影响：`~/.ssh`、`~/.gnupg`、`~/.aws`、`~/.kube`、`~/.drifox`、
  浏览器 profile、`id_rsa` / `*.pem` / `.env` / `sessions.db` 等凭据文件一律拒绝。
- 下载落点额外禁止自启动/登录项目录（Startup、`.config/autostart`）。
- 路径先 realpath 解析，符号链接无法绕过。

### 命令输出上限
`ssh_exec` 单路输出上限 256KB，超出即截断并关闭通道。`timeout` 现在是**总时长**约束，
不再是参数名意义上的单次 recv 超时；远端 `yes` / `cat /dev/urandom` 不会撑爆宿主内存。
stdout/stderr 同轮询消费，避免一路写满 SSH 窗口把另一路锁死。

### 端口转发
`bind_addr` 默认只允许回环（`127.0.0.1` / `::1` / `localhost`）。绑定 `0.0.0.0` 等对外地址需显式传
`allow_public=true`。`bind_port=0` 时返回真实分配端口。当前仅实现 local 转发（`-L`）。

## 依赖
paramiko 及其依赖已 vendoring 于 `deps/`，运行时由插件加载器自动加入 `sys.path`，无需额外安装。

## 已知限制
连接配置（含密码/私钥口令）**明文**存于 `~/.drifox/cache/ssh/connections.json`，文件权限 600。
Windows 上 chmod 只影响只读位，不改变 ACL，因此该文件对同用户进程与备份/云同步均可见。
生产环境建议使用 `publickey` + `ssh-agent`，避免在配置里存密码。
