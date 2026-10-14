# 智谱 开源仓库阅读

阅读 GitHub 开源仓库的文档、结构与代码。安装后填入智谱 API Key。

> 由 HanaAgent 官方市场连接器迁移而来。指向服务方自营的远程 MCP 服务器，
> 本插件不含服务端代码，也不托管任何凭据。

## 启用

设置 → MCP 连接器 → 找到本插件 → 启用。工具名前缀 `mcp__zhipu-zread__`。

## 认证

本连接器需要服务方颁发的 API Key。在 DriFox 里直接填，不必配环境变量：

1. 设置 → MCP 连接器 → 找到本连接器
2. 点「获取 Key」跳到申请页，拿到后粘贴进输入框
3. 点「保存」，随后打开开关即自动连接

申请地址：https://bigmodel.cn/usercenter/proj-mgmt/apikeys

## 上游

- 服务方端点: `https://open.bigmodel.cn/api/mcp/zread/mcp`
- 来源: HanaAgent 官方市场（official-global）
- 上游仓库: https://github.com/liliMozi/hana-connectors
