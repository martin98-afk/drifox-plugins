# biaoqingbao

养成系表情包插件 — 助手按自己的情绪挑图发表情，越用越懂你。

## 做什么

助手在回复时如果感受到情绪（开心、委屈、心疼、无语、得意…），可以调 `express` 工具，从你的图库里挑一张合适的表情发出来。图库由你喂，助手通过标签、反馈和频率控制慢慢学会什么时候该发、发哪张。

- **情绪驱动**：助手传一个情绪词，插件按标签三档打分选图
- **频率门控**：日常 / 正事两种频率，检测到代码、bug、部署这类词自动降频
- **偏好学习**：喜欢 +10，不喜欢逐次降权，否决 −20 直接出局
- **冷却**：最近 5 张不重复
- **开箱可用**：内置 13 类情绪、39 张 OpenMoji 表情，一键导入
- **纯本地**：图库、标签、偏好都存本机，不上传

## 来源

插件代码移植自 [moononnn/DeepSeek-Harness-biaoqingbao](https://github.com/moononnn/DeepSeek-Harness-biaoqingbao)（MIT）。
原版是 OpenHanako 社区插件 [hanako-biaoqingbao](https://github.com/moononnn/hanako-biaoqingbao) 的 DSH 移植版。
本仓库保留 MIT 许可与原作者署名，算法阈值与上游一致。

内置图库表情来自 [OpenMoji](https://openmoji.org)（CC BY-SA 4.0），与代码许可分开标注。

## 形态

| 项 | 值 |
|---|---|
| 组件 | `tools` |
| 数据目录 | `<app_data>/plugin_data/biaoqingbao/` |
| 依赖 | Python 3.10+，仅标准库 |
| 许可 | MIT |

## 工具

| 工具 | 作用 |
|---|---|
| `biaoqingbao_express` | 按情绪挑一张表情发出来（核心） |
| `biaoqingbao_manage` | 图库管理，`action` 分发：`list` / `search` / `add` / `update_tags` / `feedback` / `import_starter` |

管理能力合并成单一入口：6 个独立工具 schema 共 2368 字符，每轮随 prompt 走太贵；
合并后 1205 字符，加 express 共 1766 字符（约 1100 token），比合并前省 1260 字符。

## 打分规则

标签分三档，与上游一致：

| 字段 | 精确 | 包含 |
|---|---|---|
| `emotion` | +8 | +5 |
| `scene` | +5 | +3 |
| `keywords` | +4 | +2 |
| `description` 含情绪词 | — | +3 |

偏好加减：喜欢 `+10`，否决 `−20`，不喜欢每次 `−5`（最多 −25）。总分 ≤ 0 的图不参与候选。

## 展示位置

表情图由**回复正文的 markdown 图片**承载，工具卡只留一行标题：

- `render_mode="inline"` — 单行卡，无 body（卡片 body 在简洁模式下是 lazy 空壳，见下）
- 不声明 `keep_in_content` — 卡收进「工具与思考」折叠区，正文只留图片
- 工具返回 `![desc](/abs/path)`，宿主 `_resolve_image_src` 把绝对路径转 `file:///` 渲染
- 返回路径指向 **180px 缩略图**（`thumbs/<id>_180.png`，PIL 首次生成并缓存）

为什么不用 render 闭包往工具卡里塞 `<img>`：简洁模式下宿主 `_tool_lazy_body` 为真，
工具块 body 只出空占位，靠「展开工具区」时 JS 经 `tool_body` 通道注入内容；
正文里没有那次展开动作，body 始终为空。正文 markdown 图片是宿主已验证的稳定通道。
缩略图负责控宽：正文图片只有 `max-width:100%`，原图 618px 会撑满整行。

## 数据结构

```
plugin_data/biaoqingbao/
├── stickers.json      # 图库：[{id, file, description, tags{emotion,scene,keywords}, ...}]
├── preferences.json   # 偏好：{users: {default: {mappings: [{context:{emotion}, preferred_ids, vetoed_ids, dislike_counts}]}}}
├── config.json        # 设置：{enabled, freq:{daily,task}, dialect:{...}}
├── thumbs/            # 180px 缩略图缓存（自动生成，可删）
└── stickers/          # 图片文件
```

## 用法

```
用户：今天终于把那个 bug 修好了
助手：（调 biaoqingbao_express，emotion="开心"）
     → 已发送表情包「开心猫咪挥手」（匹配度 13）
     → ![开心猫咪挥手](/…/stk_xxx.png)
```

图库为空时先导入内置图库（推荐）：

```
biaoqingbao_import_starter()
```

也可以自己加图：

```
biaoqingbao_add_sticker(path="/path/to/cat.png", description="开心猫咪", emotion=["开心"], keywords=["猫咪"])
```

## 验证

```bash
python3 plugins/biaoqingbao/tests/test_core.py
python3 tools/validate_plugins.py plugins/biaoqingbao
```

## 路线图

- [x] 内置图库（13 类情绪、39 张 OpenMoji）
- [ ] 设置卡（频率、开关、图库管理面板）
- [ ] 自动配图观察器（hooks + 内容分析模型）
- [ ] AI 识图自动打标（走 DriFox provider）
- [ ] 语义向量检索（可选增强）
