# ♟ 中国象棋 — DriFox 与大模型对弈

在 DriFox 中直接与中国象棋 AI（**大模型驱动**）对弈。

## 使用

在 DriFox 聊天框输入：

```
/chinese-chess
```

即可打开底部中国象棋浮动卡片。

## 玩法

- 你执**红方**（先手），大模型执**黑方**
- 点击己方棋子选中（黄色高亮 + 绿点提示合法落点）→ 点击目标格落子
- 走子后轮到 AI 思考（右下角状态栏显示"🤖 大模型思考中…"）
- AI 输出非法走法时会自动重试，仍失败则从合法走法中随机兜底

## 规则

完整中国象棋规则：
- 7 种棋子（帅/仕/相/马/车/炮/兵）
- 九宫、河界限制
- 将军、蹩马腿、塞象眼、炮架
- 送将过滤（不能送将）
- 将死与困毙判负

## 大模型配置

插件**自动读取 DriFox 当前激活的 LLM provider 配置**（设置 → 模型服务商）：

- `Settings.get_instance().llm_selected_model.value` = 当前 config_id
- `Settings.get_instance().llm_saved_providers.value` = 所有 provider 配置

只要 DriFox 已配置至少一个 OpenAI 兼容 API（绝大多数国产模型都支持：DeepSeek/Qwen/GLM/Doubao/SiliconFlow/Minimax 等），插件就能直接调用，无需重复填 key。

**走法协议**：插件要求 LLM 输出 JSON：

```json
{"from":[c1,r1],"to":[c2,r2]}
```

坐标系：列 `c ∈ 0..8`（左→右），行 `r ∈ 0..9`（红方在底部 row 大，黑方在顶部 row 小）。例：红帅初始 `(4, 9)`，黑将 `(4, 0)`。

## 按钮

- **新对局**：重置到初始局面
- 状态栏：实时显示当前轮次 + 上一步 AI 走法来源（LLM / 兜底 / 出错）

## 版本

v0.1.0 — 完整规则引擎 + LLM 驱动 AI + 自动兜底

v0.2.2 — 修复配置读取链路：适配 PluginConfigStore.get 两参签名；设置卡回显初始化顺序（_on_change_external 前置）；schema select 空 options 哨兵占位；热重载子模块清理前缀笔误
