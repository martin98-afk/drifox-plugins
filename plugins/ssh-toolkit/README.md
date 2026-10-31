# ssh-toolkit

SSH 远程工具包插件（AI 工具 + 系统设置页连接管理）。基于 paramiko，提供连接管理、命令执行、SFTP 文件传输、目录浏览、端口转发。

## 工具
- `ssh_connect` 建立连接入池，返回 handle；**连一次就自动保存**（无名直连按 `user@host` 命名，同名只刷新最后连接时间与次数）
- `ssh_exec` 执行命令（stdout/stderr/exit code）
- `ssh_list_connections` 列出已保存连接（密码掩码，含最后连接时间）
- `ssh_remove_connection` 删除连接
- `ssh_upload` SFTP 上传
- `ssh_download` SFTP 下载
- `ssh_list_dir` 远程目录浏览
- `ssh_forward` 端口转发（后台）
- `ssh_disconnect` 关闭连接/转发

> 没有单独的「保存连接」工具：保存是 `ssh_connect` 成功的副作用，不再要求先建档再连接。

## tmux 长期会话

参数服务器上跑长任务，直接 `ssh_exec("make")` 不行：`_read_streams` 会同步轮询到进程退出，
超时后关通道，任务随 SSH channel 一起死。tmux 解决这个问题靠的是解耦：tmux server 是远端
独立 daemon，跟 SSH 通道无关，通道断了 server 照样跑，下次连上去接着看。

插件无需任何改造，四条命令覆盖全套（下面用 `work` 作会话名）：

```bash
# 建或复用会话（-d 分离启动，不 attach）
tmux has-session -t work 2>/dev/null || tmux new-session -d -s work -c /srv/app

# 投喂命令（注意 Enter 要单独作为一个参数）
tmux send-keys -t work 'make -j8' Enter

# 抓输出（-p 打到 stdout，-S -300 回看最近 300 行）
tmux capture-pane -pt work -S -300

# 看存活与当前前台命令
tmux list-panes -t work -F '#{pane_pid} #{pane_current_command} #{pane_dead}'
```

拿退出码：`tmux send-keys -t work 'make -j8; echo __RC=$?' Enter`，再从 `capture-pane`
里 grep `__RC=`。

四个必须知道的限制：

- **不能 `tmux attach`**：会一直不返回，`ssh_exec` 吃满 `timeout` 后关通道。只用 `-d` 分离模式。
- **PATH 可能不全**：`exec_command` 走非 login shell，`/usr/local/bin` 或 brew 装的 tmux 可能
  找不到。包一层 `bash -lc '...'`，或写容器内绝对路径。
- **没有 cwd/env 参数**：目录用 `new-session -c` 指定，环境变量在命令里自己 `export`。
- **插件不记会话名**：哪个连接对应哪个 tmux 会话靠命名约定，自己定规则（如「连接名-用途」）。

## 设置页（设置 → SSH 远程连接）

展开即刷新，每条连接显示：状态点（绿=池内活跃 / 红=TCP 不可达 / 灰=未保持）、
名称、`user@host:port`、认证方式与密钥路径、最后连接时间、累计连接次数、备注；
行尾「删除」会二次确认，并同时断开该名字下的活跃连接与端口转发。

空态提示「直接对 AI 说『连到 root@1.2.3.4』，连上后会自动出现在这里」。

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
