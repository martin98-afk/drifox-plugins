# skillhub

SkillHub 技能工作流插件 — 打通内网技能注册中心（registry）的发布、搜索与安装全流程。

## 能力

- **发布**：单技能发布（dry-run 验证 + 正式发布）、仓库级批量发布（限流重试 + 断点续传 + 失败分类）
- **搜索**：按关键词搜索 registry 已发布的技能
- **安装**：CLI 安装指定技能到本地

## 前置条件

1. 能访问内网 registry（`http://168.168.10.49/`，需连接 work 网）
2. 已安装 Node.js；`npm i -g @astron-team/skillhub` 安装 CLI
3. 持有个人 API Token（SkillHub 页面获取），执行 `skillhub login --token <token> --registry http://168.168.10.49`

## 使用

对 AI 说：
- 「把这个技能发布到 SkillHub」/「批量上传仓库技能」
- 「在 SkillHub 搜一下 xxx」
- 「从 SkillHub 安装 xxx 技能」

## 注意

普通用户发布的技能需管理员审核通过后才能在技能市场被其他用户搜索到。
