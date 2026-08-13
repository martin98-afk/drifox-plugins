# 验收运行记录模板

这个模板描述验收目录与其目录外证据锚点；推荐用 `python scripts/prepare_acceptance_run.py` 创建。准备器生成的全部状态必须保持 `pending`，不得预填分数或 PASS。

## 运行类型

- 类型：acceptance / baseline / regression
- 目标技能包：
- 运行 ID：
- 运行日期：
- 执行环境：

## 原始输入

- `input.md`：只放用户原话。
- `prompt-without-skill.txt`：与 `input.md` 完全相同。
- `prompt-with-skill.txt`：与 `input.md` 完全相同；Skill 由宿主加载，不能把验收规则偷偷加进 prompt。

## 真实触发与运行记录

- `trigger-run.json`：按 `assets/trigger-run-record-template.json` 填写。
- without-skill 与 with-skill 必须来自两个不同的干净会话；`session_id` 去首尾空白并忽略大小写后仍必须不同。
- 每条 route 必须有宿主、session ID、起止时间、是否加载 Skill、是否观察到触发、prompt/output SHA-256 和运行记录。
- `runtime-without-skill.log`、`runtime-with-skill.log` 是验收目录内副本，只能证明材料一致，不能证明运行真的发生。
- 宿主必须在 run folder 外导出 `host-event-anchor.json`，再生成绑定 event hash、两条 route、session、prompt/output hash 和能力字段的 `host-attestation.json`。格式见 `assets/host-event-anchor-template.json`、`assets/host-attestation-template.json`。
- 外部 attestation 放在 run folder 的同级 `attestations/`，不得复制回 run folder 冒充外部证据。

## 读取与能力边界

- `evidence-sweep.md`：记录用户材料、本地/Graphify、官方/平台、高信号、反证、时间和具体来源。
- `tool-capability.md`：记录宿主、Python 入口、Skill 调用表面、run 内日志副本、外部 host attestation 和限制；能力字段必须与外部 attestation 一致。
- 明确未读取的无关材料：

## 输出与评分

- `without-skill-output.md`：不编辑的原始输出。
- `with-skill-output.md`：不编辑的原始输出。
- `scoring-rubric.json`：评分前冻结的机器合同；维度 ID 唯一、权重合计 100、每维有可观察标准。
- `scoring-rubric.md`：人读说明，ID 和冻结时间与 JSON 一致。
- `reviewer-notes.md`：Reviewer、Reviewer ID/type、Reviewed at、外部 attestation、rubric hash、重算总分、决定。
- 人工 reviewer 必须在 run folder 外生成 `reviewer-attestation.json`，逐维给两路打分、逐维引用两份输出中实际存在且非空的行号/范围（`#Lx` 或 `#Lx-Ly`），并绑定 rubric/output hash；格式见 `assets/reviewer-attestation-template.json`。AI、A.I.、Artificial Intelligence、Machine Review、model/bot/service、自动化和匿名 reviewer 不能关闭 human gate。

## 校验命令

```bash
python scripts/check_meta_skill_package.py .
python scripts/check_closed_loop.py .
python scripts/test_acceptance_runs.py
python scripts/check_acceptance_runs.py <completed-run-dir>
```

## 三层状态

- `structure_status=artifact_consistent`：必需文件、格式、提示一致性、哈希关系和确定性校验闭合；它不证明任何动作发生过。
- `runtime_status=verified`：两个真实宿主会话、Skill 加载/触发观察和目录外 host event/attestation 闭合。
- `human_status=verified`：已识别的人类 reviewer 按冻结 rubric 逐维审核，目录外 reviewer attestation 闭合。
- `ready_decision=pass`：只有前述三层状态精确成立，且时间线满足 rubric/evidence → run → validation → review → release 时才能为 pass。

任何时间都必须带时区且不得晚于校验时刻。没有目录外锚点时，最多只能报告 `artifact_consistent`，runtime/human 必须是 `unverified` 或 `blocked`，Ready 不能为 pass。

## 失败与回写

- 失败点：
- 应加入的评测：
- 应更新的参考：
- `writeback` / `proposal` / `none-with-reason` / `blocked`：
- `next_run_reuse_key`：
