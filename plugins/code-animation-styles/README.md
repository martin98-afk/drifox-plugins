# code-animation-styles — 代码动画风格提示词库

把内容做成「代码动画」的风格库插件：**341 种**风格提示词，每种一个 `.md`，Opus 5.5 与 DeepSeek 通用。其中 **193 种带静帧**（`.jpg`）。

## 十大类别

| 类别 | 数量 | 是什么 |
|---|---|---|
| A–G 代码样片 | 26 | 字、粒子、线与墨、光与天气、图形与纸、讲解、质感；每种附参考实现代码 |
| M 动态风格 | 40 | 整段视频怎么动、怎么剪、怎么讲 |
| K 卡通画风 | 38 | 角色和画面长什么样 |
| Z 中国风 | 15 | 水墨、工笔、剪纸、皮影、敦煌…… |
| H 现成版式 | 12 | 配色加字体的整套搭配 |
| L Lemo-Opuscar | 59 | 开源项目 Lemo-Opuscar 的风格，每种有完整做法 |
| V mg-styles-15 | 15 | 开源项目 mg-styles-15 的动态风格 |
| X code-video | 31 | 开源项目 code-video 的风格 |
| R 照参考学来的 | 7 | 照参考学着用代码画的赛博朋克 |
| O 奥斯卡 98 部 | 98 | 98 部奥斯卡最佳影片，每部一种画风 |

## 怎么用

**让 AI 挑（推荐）**：直接说需求，例如「用代码动画讲一下 XXX，要有中国风感觉」。AI 读 `skills/code-animation/styles/INDEX.md` 索引筛选风格，再读对应风格 `.md` 取完整提示词。

**自己挑**：双击 `skills/code-animation/styles/风格挑选.html`（Chrome / Edge 打开，不用联网），按类别筛、搜索、看静帧、勾选、导出清单，把清单发给 AI。

**直接用**：打开某个风格的 `.md`，把「风格提示词」一段复制给任意模型，再加上你的内容。提示词里的 `{{ }}` 是要自己填的空。

对 AI 的完整工作流指引见 `skills/code-animation/SKILL.md`，提示词写法范例（详细版 / 一句话版）见同目录 `references/`。

## 目录结构

```
code-animation-styles/
├── .drifox-plugin/plugin.json
├── README.md
└── skills/code-animation/           技能包（自包含）
    ├── SKILL.md                     路由面：触发 / 第一动作 / 渐进加载 / 边界
    ├── references/                  工作流契约 / 提示词分寸 / 详略两派范例
    ├── evals/trigger-eval.json      触发评测（正反例 + 真实/边界任务）
    └── styles/                      风格数据资产
        ├── INDEX.md                 全量风格索引（AI 检索入口）
        ├── 风格提示词/               341 个风格 .md + 193 张静帧 .jpg + _公共函数.js
        ├── 风格挑选.html             离线挑选页（双击即开）
        ├── 说明.md / 许可与来源.md / _统计.json
        └── 第三方许可/               Lemo-Opuscar / mg-styles-15 / code-video 的 LICENSE
```

## 许可与约定

内容源自社区开源整理（含 Lemo-Opuscar、mg-styles-15、code-video 三个 MIT 开源项目），各部分来源与许可见 `skills/code-animation/styles/许可与来源.md` 与 `skills/code-animation/styles/第三方许可/`。

原始作者的约定，在此完整保留：

> 全部免费，不用私信，不用买课。
> 你可以免费用、免费转给别人；转的时候也请免费分享。
> **禁止把这些内容包装成课程、付费 skills 或任何收费的东西拿去卖。**
> 其中来自开源项目的部分，保留它们原来的许可和署名。

本插件为免费打包分发，不附加任何收费。