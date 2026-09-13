# 样片帧

本目录的 `.jpg` 文件不进仓库。`SKILL.md` 与 `examples/rag/README.md` 中提到的「先看 `examples/rag/frames/overview_*.jpg` 建立视觉标尺」与 QC 报告里的反例帧，可在本地从源仓库同步：

```bash
# 临时拉源仓库并拷贝 frames
git clone --depth 1 --filter=blob:none --sparse https://github.com/Vincentwei1021/anything2explainer
cd anything2explainer
git sparse-checkout set examples/rag/frames
cp -r examples/rag/frames/* ../../plugins/anything2explainer/skills/anything2explainer/examples/rag/frames/
```

源仓库样片帧均为 1280×720 JPEG，每张约 50–400 KB；本目录已配置 `.gitignore` 排除这些二进制，仅保留本 README 与 .gitignore 入仓。

样片视频（中英文版）请直接看源仓库 README：

- English cut *RAG & Knowledge Bases* (5′02″)：<https://github.com/user-attachments/assets/e2771c68-a28c-4459-ac5a-a5b685181eeb>
- Chinese cut *RAG 与知识库* v2 (4′54″)：<https://github.com/user-attachments/assets/5c213990-cbba-439e-8371-fbb3aa348e05>