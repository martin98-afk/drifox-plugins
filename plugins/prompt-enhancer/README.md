# prompt-enhancer 插件 — DriFox 官方插件

输入框一键「优化提示词」：复用主程序当前会话模型配置，把输入框原文用 LLM 优化为
更清晰、结构化、高信息密度的提示词，并自动注回输入框。

## 功能

- ✨ 输入区新增「优化提示词」按钮，一键 LLM 增强当前输入框内容
- 🔄 优化中按钮图标转圈动画（QPainter 自绘圆环，浅色/深色主题自适应），完成/失败后恢复
- ⚙️ 增强指令在系统配置「提示词增强」卡片中**多行编辑**，即时保存 + 恢复默认
- 🛡️ 防任务积压：同一窗口同时只允许一个优化任务，运行中重复点击给出提示
- 📊 进度可感知：优化中常驻提示条，完成/失败后自动关闭并给出结果提示
- 🔌 复用主程序模型配置与 HTTP 客户端，闭包实现（不修改主程序）
- 🧩 可选指定「提示词增强模型」覆盖主程序当前模型（`Provider:Model` 格式，关闭再打开保留）
- 📜 增强模型下拉最大可见 8 项，超出滚动查看（对齐主程序子智能体模板下拉）

## 安装

插件位于 `plugins/prompt-enhancer/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\prompt-enhancer %USERPROFILE%\.drifox\plugins\prompt-enhancer /E /I /Y

# Linux / macOS
cp -r plugins/prompt-enhancer ~/.drifox/plugins/
```

## 使用

1. 在输入框输入粗略想法
2. 点击输入区「✨ 优化提示词」按钮
3. 优化结果自动填入输入框，可继续编辑后发送

## 配置

系统设置 → 插件分区 →「提示词增强」卡片：

- **增强指令**：作为 system prompt 的优化指令（多行编辑，留空回默认）
- **提示词增强模型**：可选指定 `Provider:Model`（留空沿用调用方当前模型），关闭配置卡再打开选择会保留
- **恢复默认**：一键还原内置增强指令

## 目录结构

```
prompt-enhancer/
├── .drifox-plugin/
│   └── plugin.json      # 插件清单 + 声明式配置 schema
├── ui/
│   ├── __init__.py      # 输入按钮注册 + 优化任务（QRunnable）
│   └── icons/enhance.svg
├── icon.svg             # 明色主题图标
├── icon_dark.svg        # 暗色主题图标
└── README.md
```

## 密钥获取（重要）
插件需要「切到指定服务商跑一次 LLM 调用」时，**必须**经宿主公开服务取配置：
```python
cfg = ctx["services"]["get_provider_config"]("MiniMax", "MiniMax-M2.7")
# → {"API_KEY": "sk-…已解密明文", "API_URL": "…", "模型名称": …}
```
**不要**自行 `json.load(~/.drifox/app.config)` 取 `LLM.SavedProviders[*].API_KEY`：
主程序 `SecretMode` 非 `none` 时，该字段是密文（`password` 模式 `enc:v2:…`）
或空串（`keyring` 模式密钥已入系统凭证库），拿去发请求会得到
`401 log in fail: Please carry the API secret key`。只有主程序内存态持有明文。

磁盘文件仍可读**非密钥字段**（`provider_name` / `模型列表` 等），用于渲染
「服务商:模型名」下拉选项；密钥字段一律走服务。旧版主程序无该服务时，
回退遍历 `main_widget._valid_configs`（同为内存态，同样不碰磁盘）。
