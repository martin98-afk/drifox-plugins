#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = path.resolve(scriptDir, "..");
const validator = path.join(scriptDir, "check-rednote-note.mjs");
const positiveFixture = path.join(skillRoot, "examples", "example-output.md");
const goalFixture = path.join(skillRoot, "examples", "page-direction-regression.md");

function runValidator(file) {
  return spawnSync(process.execPath, [validator, file], {
    cwd: skillRoot,
    encoding: "utf8",
  });
}

function replaceSection(source, heading, nextHeading, replacement) {
  const pattern = new RegExp(`(^## ${heading}\\s*$)[\\s\\S]*?(?=^## ${nextHeading}\\s*$)`, "m");
  if (!pattern.test(source)) throw new Error(`fixture section not found: ${heading}`);
  return source.replace(pattern, `## ${heading}\n${replacement}\n\n`);
}

function sectionBody(source, heading, nextHeading) {
  const pattern = new RegExp(
    "^## " + heading + "\\s*$\\n([\\s\\S]*?)(?=^## " + nextHeading + "\\s*$)",
    "m",
  );
  const match = source.match(pattern);
  if (!match) throw new Error("fixture section not found: " + heading);
  return match[1].trim();
}

function parseGoalVariants(markdown) {
  const rows = markdown
    .split(/\r?\n/)
    .filter((line) => /^\|[^-].*\|$/.test(line.trim()))
    .map((line) => line.split("|").slice(1, -1).map((cell) => cell.trim()))
    .filter((cells) => cells[0] !== "主目标");
  return rows;
}

function normalizeCreativeCell(value) {
  return value
    .replace(/[“”"'\x60]/g, "")
    .replace(/[，。；;、\s]+/g, " ")
    .trim()
    .toLowerCase();
}

function goalVariantsAreDistinct(rows) {
  if (rows.length < 3) return false;
  if (rows.some((row) => row.length !== 6 || row.some((cell) => !normalizeCreativeCell(cell)))) {
    return false;
  }
  const goals = new Set(rows.map((row) => row[0]));
  if (goals.size !== rows.length) return false;
  for (let left = 0; left < rows.length; left += 1) {
    for (let right = left + 1; right < rows.length; right += 1) {
      let changedDimensions = 0;
      for (let column = 1; column < 6; column += 1) {
        if (normalizeCreativeCell(rows[left][column]) !== normalizeCreativeCell(rows[right][column])) {
          changedDimensions += 1;
        }
      }
      if (changedDimensions < 3) return false;
    }
  }
  return true;
}

const failures = [];
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "rednote-direction-"));

try {
  const positive = runValidator(positiveFixture);
  if (positive.status !== 0) {
    failures.push(`positive fixture should pass:\n${positive.stderr || positive.stdout}`);
  }

  const source = fs.readFileSync(positiveFixture, "utf8");
  const weakStrategy = replaceSection(
    source,
    "策略补全与决策提醒",
    "任务判断",
    [
      "用户已确认；原生确认证据：request_user_input returned。",
      "人类决策记录：策略路线 human_confirmed；标题与封面字 human_confirmed；视觉方案 human_confirmed；模板路由 human_confirmed；封面候选图 human_confirmed；批量生产许可 human_confirmed；继续执行许可 human_confirmed。",
      "1. 真实感路线（推荐）。",
      "2. 信息卡路线。",
    ].join("\n"),
  );
  const weakStrategyFile = path.join(tempRoot, "weak-strategy.md");
  fs.writeFileSync(weakStrategyFile, weakStrategy, "utf8");
  const weakStrategyResult = runValidator(weakStrategyFile);
  const weakStrategyOutput = `${weakStrategyResult.stdout}\n${weakStrategyResult.stderr}`;
  if (weakStrategyResult.status === 0 || !/机会研究与营销决策/.test(weakStrategyOutput)) {
    failures.push("R07 weak strategy fixture was not rejected by the marketing-decision gate");
  }

  const weakPages = replaceSection(
    source,
    "图文页脚本",
    "视觉类型判断",
    Array.from({ length: 6 }, (_, index) =>
      `第 ${index + 1} 页：画一张好看的学习桌面图，放一句标题。`,
    ).join("\n"),
  );
  const weakPagesFile = path.join(tempRoot, "weak-pages.md");
  fs.writeFileSync(weakPagesFile, weakPages, "utf8");
  const weakPagesResult = runValidator(weakPagesFile);
  const weakPagesOutput = `${weakPagesResult.stdout}\n${weakPagesResult.stderr}`;
  if (weakPagesResult.status === 0 || !/逐页视觉导演表|视觉导演表缺少字段/.test(weakPagesOutput)) {
    failures.push("R07 weak page fixture was not rejected by the per-page direction gate");
  }

  const originalPageBody = sectionBody(source, "图文页脚本", "视觉类型判断");
  const pageFieldLine =
    /^((?:页面角色|读者在本页完成的认知动作|本页唯一信息承诺|画面主体与真实感锚点|构图版式|选择理由|主体区|主标题区 \/ 精确文字|副标题或证据区 \/ 精确文字|文字层级与位置|不能遮挡或不能出现|与前后页连续的元素|本页 Image2 结构化提示词|验收)[：:]).*$/gm;
  const emptyPageFields = replaceSection(
    source,
    "图文页脚本",
    "视觉类型判断",
    originalPageBody.replace(pageFieldLine, "$1"),
  );
  const emptyPageFile = path.join(tempRoot, "empty-page-fields.md");
  fs.writeFileSync(emptyPageFile, emptyPageFields, "utf8");
  const emptyPageResult = runValidator(emptyPageFile);
  const emptyPageOutput = (emptyPageResult.stdout || "") + "\n" + (emptyPageResult.stderr || "");
  if (emptyPageResult.status === 0 || !/字段值为空或无信息量/.test(emptyPageOutput)) {
    failures.push("R07 empty page-direction values were not rejected");
  }

  const repeatedPageBody = originalPageBody
    .replace(/^读者在本页完成的认知动作[：:].*$/gm, "读者在本页完成的认知动作：让读者理解同一个核心重点。")
    .replace(/^本页唯一信息承诺[：:].*$/gm, "本页唯一信息承诺：这一页解释同一个核心重点。")
    .replace(/^画面主体与真实感锚点[：:].*$/gm, "画面主体与真实感锚点：同一组桌面物件与自然光。")
    .replace(/^本页 Image2 结构化提示词[：:].*$/gm, "本页 Image2 结构化提示词：生成同一张桌面图并放置同一句标题。");
  const repeatedPageFields = replaceSection(
    source,
    "图文页脚本",
    "视觉类型判断",
    repeatedPageBody,
  );
  const repeatedPageFile = path.join(tempRoot, "repeated-page-fields.md");
  fs.writeFileSync(repeatedPageFile, repeatedPageFields, "utf8");
  const repeatedPageResult = runValidator(repeatedPageFile);
  const repeatedPageOutput = (repeatedPageResult.stdout || "") + "\n" + (repeatedPageResult.stderr || "");
  if (repeatedPageResult.status === 0 || !/重复、没有形成有效变化/.test(repeatedPageOutput)) {
    failures.push("R07 repeated generic page-direction values were not rejected");
  }

  const emptyMarketing = source.replace(
    /^- 产品角色[：:].*$/m,
    "- 产品角色：来源：AI 假设。",
  );
  const emptyMarketingFile = path.join(tempRoot, "empty-marketing-field.md");
  fs.writeFileSync(emptyMarketingFile, emptyMarketing, "utf8");
  const emptyMarketingResult = runValidator(emptyMarketingFile);
  const emptyMarketingOutput = (emptyMarketingResult.stdout || "") + "\n" + (emptyMarketingResult.stderr || "");
  if (emptyMarketingResult.status === 0 || !/字段值为空或无信息量：产品角色/.test(emptyMarketingOutput)) {
    failures.push("R07 empty marketing-decision value was not rejected");
  }

  const missingProvenance = source.replace(
    /(^- 产品角色[：:][^\n]*?)[。；;，,\s]*(?:来源|证据来源)[：:]\s*(?:用户提供|研究证据|AI 假设)[。；;，,\s]*$/m,
    "$1",
  );
  const missingProvenanceFile = path.join(tempRoot, "missing-marketing-source.md");
  fs.writeFileSync(missingProvenanceFile, missingProvenance, "utf8");
  const missingProvenanceResult = runValidator(missingProvenanceFile);
  const missingProvenanceOutput =
    (missingProvenanceResult.stdout || "") + "\n" + (missingProvenanceResult.stderr || "");
  if (missingProvenanceResult.status === 0 || !/字段缺少逐条来源：产品角色/.test(missingProvenanceOutput)) {
    failures.push("R07 marketing-decision field without bound provenance was not rejected");
  }

  const goalRows = parseGoalVariants(fs.readFileSync(goalFixture, "utf8"));
  if (!goalVariantsAreDistinct(goalRows)) {
    failures.push("R06 positive goal variants must change creative signatures across at least three goals");
  }
  const collapsedRows = goalRows.map((row) => [row[0], ...goalRows[0].slice(1)]);
  if (goalVariantsAreDistinct(collapsedRows)) {
    failures.push("R06 collapsed goal variants should fail when title, cover, page roles and product expression are identical");
  }
  const titleOnlyRows = goalRows.map((row, index) => [
    row[0],
    "只换标题 " + (index + 1),
    ...goalRows[0].slice(2),
  ]);
  if (goalVariantsAreDistinct(titleOnlyRows)) {
    failures.push("R06 title-only variants should fail when fewer than three creative dimensions change");
  }
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true });
}

if (failures.length) {
  console.error("Page-direction fixture validation failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Page-direction fixture validation passed.");
console.log("R06 distinct-goal regression: positive, collapsed-negative, and title-only-negative cases passed.");
console.log("R07 marketing/page direction: positive, empty-value, missing-source, repeated-value, and weak-negative cases passed.");
