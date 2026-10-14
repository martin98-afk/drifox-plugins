# codebuddy-intl — 腾讯 CodeBuddy 国际版服务商

伪装 CodeBuddy VSCode 插件客户端接入国际版网关 `www.codebuddy.ai`，
动态路由：模型列表只暴露 craft 路由槽位，网关按账号档位与任务自动分配实际模型。

## 特性

- **OAuth 登录**：服务商编辑卡点「自动登录」弹浏览器授权，长效 refresh_token
  回填 API Key 字段；聊天时自动换取短效 access_token（临期自动刷新）
- **动态路由**：模型列表 = 路由槽位（`default-model` / `fast-model` /
  `balanced-model` / `primary-model`）+ 详情表里的真实模型 ID
  （`gpt-6-luna` / `claude` 系等）；槽位让网关按账号档位自动分配，真实 ID
  可精确指定。claude 系可能被账号档位门控（11102），报错时自行剔除
- **思考可控**：四槽位支持思考强度调节（low / medium / high / xhigh），
  模型配置卡可调「思考等级」
- **多模态**：四槽位支持图像输入
- **模型发现**：登录后拉 `/v3/config`，槽位真源 = craft 智能体模型目录，
  限额/多模态随刷新动态回写
- **多账号**：一条服务商配置 = 一个号；API Key 各存各的 refresh_token，
  余额各显，切换配置即切号
- **自动签到**：每日签到（幂等，活动关闭不领取）
- 与国内版插件（system-providers 内 CodeBuddy）互不干扰，凭据缓存分流

## 使用

1. 设置 → 服务商 → 新增「CodeBuddy International」
2. 点「自动登录」，浏览器完成授权后 API Key 自动回填，保存
3. 模型列表点「获取」拉取账号可用模型（默认 `default-model` 由网关自动选型；
   `fast-model` 响应快、`balanced-model` 均衡、`primary-model` 高质量；
   也可直接选真实模型 ID）

## 与国内版差异

| 项 | 国内版（system-providers） | 本插件（国际版） |
|---|---|---|
| 网关 | copilot.tencent.com | www.codebuddy.ai |
| 伪装形态 | CodeBuddyIDE 独立版 | VSCode 插件（craft） |
| 账号 | 国内账号体系 | 国际账号体系（不互通） |
| 自动签到 | 有 | 有（每日，幂等） |

## 风险提示

非官方客户端协议实现，存在违反服务条款与封号风险，自行评估。

## 测试

```bash
uv run pytest ~/.drifox/plugins/codebuddy-intl/tests -v
```
