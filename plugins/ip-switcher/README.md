# ip-switcher — IP 切换监控

免费模型 API 常按出口 IP 绑定免费额度。本插件在检测到限流（HTTP 429）时自动切换本地代理池出口 IP 并重试请求。

## 功能
- 🧩 monkey patch openai SDK：白名单模型请求走本地代理池
- 🔄 429 自动换 IP + 自动重试（默认 3 次，2s 退避）
- 📊 仪表盘浮动卡片：当前出口 IP、换绑历史、统计
- 🖱 手动换 IP 按钮
- ⚙️ 配置存 user-custom 插件（随云端备份恢复）

## 使用
1. 安装插件后输入 `/ip-switcher` 打开仪表盘
2. 在卡片「设置」中配置白名单模型（如 `free-gpt4o`）
3. 插件自动拉起本地代理池（shadow1ng/ProxyPool），首次需等待抓取+检测代理
4. 白名单模型请求触发 429 时自动换 IP

## 配置项（.drifox/plugins/user-custom/ip-switcher/ip-switcher.json）
- `whitelist_models`: 白名单模型名列表
- `whitelist_base_urls`: 白名单 API 地址列表
- `proxy_pool_port`: 代理池代理端口（默认 8082）
- `retry_limit`: 429 后重试次数（默认 3）
- `retry_backoff_seconds`: 重试间隔秒（默认 2）
