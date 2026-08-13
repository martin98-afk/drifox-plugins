import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const root = resolve(import.meta.dirname, "..");
const read = (relativePath) => readFileSync(resolve(root, relativePath), "utf8");

// Kim_Service deliberately publishes the flat compatibility package and
// excludes repository-level runtime projections. Runtime-specific behavior
// remains documented and tested in the canonical files below.
const skillPaths = ["SKILL.md"];
const readmePaths = ["README.md"];

test("runtime skill packages stay synchronized with the compatibility entrypoint", () => {
  const canonical = read(skillPaths[0]);
  for (const path of skillPaths.slice(1)) assert.equal(read(path), canonical, `${path} drifted`);
  assert.match(canonical, /version:\s*"4\.8\.0"/);
});

test("capability discovery stops on an existing provider instead of forcing fallback", () => {
  const skill = read("SKILL.md");
  assert.match(skill, /能力解析链（命中即停止/);
  assert.match(skill, /已有专业 provider 覆盖子任务，就绑定该 provider 并停止搜索/);
  assert.match(skill, /只有本地所有相关 provider 都无法覆盖/);
  assert.doesNotMatch(skill, /Skill完整回退链/);
  assert.doesNotMatch(skill, /这3步必须全部执行完/);
  assert.doesNotMatch(skill, /不允许跳过find-skills搜索/);
  assert.doesNotMatch(skill, /Skill 回退链/);
  assert.doesNotMatch(skill, /不超过5个/);
});

test("Codex uses only the current top-level native spawn contract", () => {
  const skill = read("SKILL.md");
  assert.match(skill, /spawn_agent\(task_name, message, fork_turns\)/);
  assert.match(skill, /不要传 `agent_type` \/ `fork_context`/);
  assert.match(skill, /不要回退到旧的 namespaced spawn API/);
  assert.doesNotMatch(skill, /multi_agent_v1\.spawn_agent/);
});

test("Claude Code keeps its own Agent Task and optional team surfaces", () => {
  const skill = read("SKILL.md");
  assert.match(skill, /Claude Code 使用宿主当前暴露的 `Agent` \/ `Task`/);
  assert.match(skill, /至少携带必填 `prompt`/);
  assert.match(skill, /`TeamCreate` \/ `SendMessage` 时才承诺共享团队语义/);
  assert.match(skill, /不要把 Codex 参数复制到 Claude Code/);
  assert.match(skill, /不要为了获得 Skill 工具而把已有专业 owner 换成 `general-purpose`/u);
});

test("published runtime READMEs stay synchronized and document both primary runtimes", () => {
  const canonical = read(readmePaths[0]);
  for (const path of readmePaths.slice(1)) assert.equal(read(path), canonical, `${path} drifted`);
  assert.match(canonical, /Claude Code \| 原生/);
  assert.match(canonical, /Codex \| 原生适配/);
  assert.match(canonical, /spawn_agent\(task_name, message, fork_turns\)/);
});

test("installer uses the flat monorepo package and runtime-native destinations", () => {
  const installer = read("scripts/install.sh");
  assert.match(installer, /VERSION="V4\.8\.0"/);
  assert.match(installer, /GITHUB_REPO="KimYx0207\/Kim_Service"/);
  assert.match(installer, /GITHUB_COMPONENT_PATH="skills\/agent-teams-playbook"/);
  assert.match(installer, /claude\) echo "\$\{CLAUDE_SKILLS_DIR\}\/\$\{SKILL_NAME\}"/);
  assert.match(installer, /codex\) echo "\$\{CODEX_SKILLS_DIR\}\/\$\{SKILL_NAME\}"/);
  assert.match(installer, /local source_dir="\$\{repo_dir\}"/);
});
