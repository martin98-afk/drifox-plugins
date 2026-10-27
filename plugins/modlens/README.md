# modlens

文本模型的视觉桥。把图片路径/URL 交给 modlens CLI，返回结构化 JSON 证据：逐字转写、版面区块、语义与视觉线索。

## 迁移来源

- 上游仓库：https://github.com/liustack/modlens
- 上游 npm 包：`@liustack/modlens`
- 上游 license：MIT

## 内容

含 1 个技能，位于 `skills/`。技能正文与 references/scripts 原样保留自上游。

## 运行时依赖

技能内的 `scripts/run.ps1` / `scripts/run.sh` 会调用上游 CLI（需 Node 22+ 或预装二进制）。首次使用前按技能正文的配置章节填入服务商 API Key。

## 与 dsh 原包的差异

- dsh 的 `cordis.patch.yml` 挂载逻辑未迁移（DriFox 无 cordis 运行时）。
- dsh 专属 frontmatter 键（`whenToUse` / `compatibility` / `allowed-tools` / `disable-model-invocation`）已剔除。
- 仅作为 CLI 入口的 bin 未迁移。
