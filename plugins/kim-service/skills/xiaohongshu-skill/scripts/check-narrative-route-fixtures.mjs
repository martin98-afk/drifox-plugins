#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = path.resolve(scriptDir, "..");
const validator = path.join(scriptDir, "check-rednote-note.mjs");
const sourceFile = path.join(skillRoot, "examples", "example-output.md");
const source = fs.readFileSync(sourceFile, "utf8");
const failures = [];
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "rednote-narrative-"));

function replaceSection(markdown, heading, nextHeading, body) {
  const pattern = new RegExp(
    "^## " + heading + "\\s*$[\\s\\S]*?(?=^## " + nextHeading + "\\s*$)",
    "m",
  );
  if (!pattern.test(markdown)) throw new Error("fixture section not found: " + heading);
  return markdown.replace(pattern, "## " + heading + "\n" + body.trim() + "\n\n");
}

function buildFixture(mainGoal, informationFrame, body) {
  return replaceSection(
    source
      .replace(
        /^- 主目标\s*\/\s*次目标[：:].*$/m,
        "- 主目标 / 次目标：" + mainGoal + "。来源：AI 假设。",
      )
      .replace(
        /^- 信息框架与标题路线[：:].*$/m,
        "- 信息框架与标题路线：" + informationFrame + "。来源：AI 假设。",
      ),
    "正文草稿",
    "评论与私信承接",
    body,
  );
}

function runCase(name, markdown, shouldPass, expectedFailure) {
  const file = path.join(tempRoot, name + ".md");
  fs.writeFileSync(file, markdown, "utf8");
  const result = spawnSync(process.execPath, [validator, file], {
    cwd: skillRoot,
    encoding: "utf8",
  });
  const output = (result.stdout || "") + "\n" + (result.stderr || "");
  if (shouldPass && result.status !== 0) {
    failures.push(name + " should pass:\n" + output);
  }
  if (!shouldPass && (result.status === 0 || !expectedFailure.test(output))) {
    failures.push(name + " should fail with route-specific evidence:\n" + output);
  }
}

try {
  runCase("trust-positive", source, true, /$^/);

  runCase(
    "search-save-positive",
    buildFixture(
      "主目标为收藏；次目标为搜索发现",
      "搜索答案 + 低风险行动",
      [
        "周报写不出来时，先别急着润色，先把本周材料按“结果、动作、问题”分成三组。",
        "",
        "第一步只找结果：完成了什么、推进到哪里。第二步补动作：你做了哪些判断。第三步再写问题和下一步，不要把流水账当成果。",
        "",
        "最常见的易错点，是先写感想再找事实。验收时检查三件事：每段有具体对象、有可核验动作、有下一步条件。适合材料零散的人；如果本周没有任何记录，先补记录再套方法。",
        "",
        "把这三步存下来，下次写周报时按同一顺序过一遍即可。",
      ].join("\n"),
    ),
    true,
    /$^/,
  );

  runCase(
    "search-save-negative-story-only",
    buildFixture(
      "主目标为收藏；次目标为搜索发现",
      "搜索答案 + 低风险行动",
      "我以前每到周五都会想起很多工作的片段。后来换了一个工具，整个过程让我轻松了不少，也让我重新理解了记录工作的意义。",
    ),
    false,
    /搜索\/收藏路线正文缺少/,
  );

  runCase(
    "comparison-positive",
    buildFixture(
      "主目标为咨询；次目标为信任",
      "判断标准 + 比较选择",
      [
        "选周报工具先看四个标准：材料能否自动归类、结论能否回到原始记录、团队是否能复核、导出后是否还能编辑。",
        "",
        "对比时不要只看模板数量。个人记录适合轻量工具；多人协作更需要权限和来源证据。没有历史记录的人不适合直接追求自动总结，先建立输入习惯。",
        "",
        "限制也要看清：任何工具都不能替你判断业务优先级。先用真实一周材料试跑，再按漏项、误判和修改时间决定是否继续。",
      ].join("\n"),
    ),
    true,
    /$^/,
  );

  runCase(
    "comparison-negative-story-only",
    buildFixture(
      "主目标为咨询；次目标为信任",
      "判断标准 + 比较选择",
      "我以前也不喜欢写周报，后来偶然用了一个新工具。整个过程很顺利，让我觉得工作记录终于没有那么困难。",
    ),
    false,
    /比较\/咨询路线正文缺少/,
  );
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true });
}

if (failures.length) {
  console.error("Narrative-route fixture validation failed:");
  for (const failure of failures) console.error("- " + failure);
  process.exit(1);
}

console.log("Narrative-route fixture validation passed.");
console.log("Trust, search/save, and comparison routes passed positive and route-mismatch negative cases.");
