# anything2explainer

> DriFox 插件：把任意主题做成一条黑底 MG 风格、有配音字幕与章节进度条的科普讲解视频（中文或英文，Remotion 代码动画）。
>
> 本插件由 [`Vincentwei1021/anything2explainer`](https://github.com/Vincentwei1021/anything2explainer) 整体迁移而来，作为「外部 Skill 入仓」的参考实现。**视觉体系、内容规范、模板与样片均完整保留**，差异仅在仓库组织与协议（详见文末）。

## 一句话能力

给一个主题（"讲一下 RAG"、"讲一下向量数据库"），产出一条 2–8 分钟、代码绘制（Remotion）+ TTS 配音 + 字幕 + 章节进度条的黑底科普视频。

| | |
|---|---|
| 帧规格 | 1280×720 @ 30fps，H.264 MP4 |
| 语言 | 中文（默认）/ 英文 |
| 风格 | 黑底幕底（星点雾底或点阵波二选一）、白线条 + 紫色重点、超粗黑体 |
| 持续图层 | 44px 白字黑边字幕、底部章节进度条、顶部胶囊 HUD、可选 pipeline rail |
| 配音 | 中文 `edge-tts zh-CN-YunxiNeural`；英文 `kokoro-82m am_liam`；可自带成品 wav |
| 时长 | 用户定；2–3 分 ≈1h、3–5 分（样片档）≈2h、5–8 分 ≈2–3h |

## 何时触发

- 用户说"讲一下 X"、"做一个讲解视频"、"把这份文档改成视频"
- 不适用：复刻现有视频（用 video-replica）、真人主播、需要实拍

加载本技能后，请按 `SKILL.md` 的「四个确认点 + 五个阶段」推进。

## 仓库组织

```
plugins/anything2explainer/
├── .drifox-plugin/plugin.json      # manifest
├── README.md                       # 本文件（迁移说明，中文）
├── README.zh-CN.md                 # 原 README_ZH 副本
├── LICENSE                         # 原 PolyForm Noncommercial 协议副本
├── CITATION.cff                    # 原 CITATION.cff
├── __init__.py
├── icon.svg / icon_dark.svg
└── skills/anything2explainer/      # 核心技能包
    ├── SKILL.md                    # 入口（打开即看）
    ├── reference/                  # 风格指南 / 分镜 / 调研 / QC 规范
    ├── template/                   # 可编译 Remotion 模板
    │   ├── scripts/                # new_project.sh / tts_build.py / motion_check.py / selfcheck.py
    │   ├── src/                    # Remotion 源码
    │   └── public/                 # 资产（含 NotoSansSC.ttf 16.9MB 等）
    └── examples/                   # 完整样片《RAG 与知识库》全套材料
        ├── rag/                    # 调研 / 解说词 / 分镜 / 镜头源码 / QC 报告
        ├── rag/frames/             # 样片帧（*.jpg 二进制不入仓，见 frames/README.md）
        └── contrast/               # 6 组反例/正例帧对照
```

### 与原仓库的差异

| 项目 | 原仓库 | 本插件 | 说明 |
|---|---|---|---|
| 根路径 | `/` 直放 | `plugins/anything2explainer/` | DriFox 插件组织约定 |
| SKILL.md | 仓库根 | `skills/anything2explainer/SKILL.md` | DriFox 技能发现约定 |
| `reference/` `template/` `examples/` | 仓库根平级 | `skills/anything2explainer/` 下 | 作为 SKILL.md 的同包资源 |
| 协议声明 | PolyForm Noncommercial | **MIT**（plugin.json）；LICENSE 文件保留原 PolyForm 副本 | 用户授权迁移时改 MIT |
| 样片帧 `.jpg` | 入仓（约 4 MB） | **不入仓**（`.gitignore` 排除；frames/README.md 给下载命令） | 控本仓库体积 |
| 字体 `NotoSansSC.ttf` | 16.9 MB 入仓 | 16.9 MB 入仓 | 中文渲染必需，保留 |

### 协议与署名

- 本插件 `plugin.json` 标 **MIT**（迁移到 drifox-plugins2 仓库时统一约定）
- `LICENSE` 文件保留原作者的 **PolyForm Noncommercial 5.0** 副本作为历史参考
- 顶部作者署名：`Vincentwei1021`，上游仓库 <https://github.com/Vincentwei1021/anything2explainer>
- 所有视觉风格与方法的著作权与荣誉归属原作者

## 使用流程（速查）

主会话按 SKILL.md 走 5 个阶段 + 4 个确认点：

```
阶段 0 建项目（5 分）  template/scripts/new_project.sh <工作目录>
阶段 1 调研（20 分）    reference/research-brief.md 派单 → research/调研.md
阶段 2 解说词与配音（20 分）  → 确认点 2、3 → tts_build.py
阶段 3 分镜（30 分）    reference/narration-storyboard.md
阶段 4 并行构建镜头（40–60 分）  reference/build-protocol.md + rag/AGENT_RAG_BUILD_RULES.md
阶段 5 QC（30 分）      reference/qc-criteria.md + rag/AGENT_RAG_QC_RULES.md
阶段 5a 前 30 秒样片    scripts/preview.sh 30  → 确认点 4
阶段 6 整片渲染与交付
```

完整 4 个确认点、6 条硬性原则、风格/动效细则、QC 判据、风格致敬均见 `SKILL.md`。

## 视觉标尺（先看）

未下载 frames 之前，先看 README 顶部的两条样片视频：

- English cut *RAG & Knowledge Bases* (5′02″) — <https://github.com/user-attachments/assets/e2771c68-a28c-4459-ac5a-a5b685181eeb>
- Chinese cut *RAG 与知识库* v2 (4′54″) — <https://github.com/user-attachments/assets/5c213990-cbba-439e-8371-fbb3aa348e05>

若需对照本地帧（建立 QC 标尺），按 `skills/anything2explainer/examples/rag/frames/README.md` 一节命令拉源仓库的 frames。

## 致谢与原作者

- 原作者：**Vincentwei1021** — <https://github.com/Vincentwei1021/anything2explainer>
- 视觉风格灵感：抖音 @图灵宇宙（写交付说明时照实标注「风格致敬、画面自绘」）
- 渲染框架：[Remotion](https://remotion.dev)（其商用许可见 remotion.dev/license）
- 协议来源：源仓库 LICENSE（PolyForm Noncommercial 5.0）

> 本插件迁移自上游仓库 v1.0+。后续上游若有更新，请按 [上游 commit 历史](https://github.com/Vincentwei1021/anything2explainer/commits/main) 同步；插件同步策略见 `CHANGELOG.md`。