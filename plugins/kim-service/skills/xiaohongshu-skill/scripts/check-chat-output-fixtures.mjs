#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const skillDir = path.resolve(scriptDir, "..");
const checker = path.join(scriptDir, "check-rednote-chat-output.mjs");
const good = path.join(skillDir, "examples", "chat-output-good.md");
const bad = path.join(skillDir, "examples", "chat-output-bad-workbench-dump.md");
const badTextScript = path.join(skillDir, "examples", "chat-output-bad-text-script-recommendation.md");
const badHookPromptTextOnly = path.join(skillDir, "examples", "chat-output-bad-hookprompt-text-only.md");
const badRealMaterialStop = path.join(skillDir, "examples", "chat-output-bad-real-material-stop.md");
const badLocalTextCard = path.join(skillDir, "examples", "chat-output-bad-local-text-card.md");

function run(file) {
  return spawnSync(process.execPath, [checker, file], {
    cwd: skillDir,
    encoding: "utf8",
  });
}

const goodResult = run(good);
if (goodResult.status !== 0) {
  process.stderr.write(goodResult.stdout || "");
  process.stderr.write(goodResult.stderr || "");
  console.error("Expected good chat output fixture to pass.");
  process.exit(1);
}

const badResult = run(bad);
if (badResult.status === 0) {
  process.stderr.write(badResult.stdout || "");
  process.stderr.write(badResult.stderr || "");
  console.error("Expected bad workbench-dump fixture to fail.");
  process.exit(1);
}

const badOutput = `${badResult.stdout}\n${badResult.stderr}`;
for (const phrase of ["工作台", "历史", "旧图"]) {
  if (!badOutput.includes(phrase)) {
    process.stderr.write(badOutput);
    console.error(`Bad fixture failed for the wrong reason; missing phrase: ${phrase}`);
    process.exit(1);
  }
}

const badTextScriptResult = run(badTextScript);
if (badTextScriptResult.status === 0) {
  process.stderr.write(badTextScriptResult.stdout || "");
  process.stderr.write(badTextScriptResult.stderr || "");
  console.error("Expected bad text/script recommendation fixture to fail.");
  process.exit(1);
}

const badTextScriptOutput = `${badTextScriptResult.stdout}\n${badTextScriptResult.stderr}`;
for (const phrase of ["做到哪一步", "文案+脚本", "整套图"]) {
  if (!badTextScriptOutput.includes(phrase)) {
    process.stderr.write(badTextScriptOutput);
    console.error(`Text/script fixture failed for the wrong reason; missing phrase: ${phrase}`);
    process.exit(1);
  }
}

const badHookPromptTextOnlyResult = run(badHookPromptTextOnly);
if (badHookPromptTextOnlyResult.status === 0) {
  process.stderr.write(badHookPromptTextOnlyResult.stdout || "");
  process.stderr.write(badHookPromptTextOnlyResult.stderr || "");
  console.error("Expected bad HookPrompt text-only fixture to fail.");
  process.exit(1);
}

const badHookPromptTextOnlyOutput = `${badHookPromptTextOnlyResult.stdout}\n${badHookPromptTextOnlyResult.stderr}`;
for (const phrase of ["不需要制作图片", "原始生成类输入"]) {
  if (!badHookPromptTextOnlyOutput.includes(phrase)) {
    process.stderr.write(badHookPromptTextOnlyOutput);
    console.error(`HookPrompt text-only fixture failed for the wrong reason; missing phrase: ${phrase}`);
    process.exit(1);
  }
}

const badRealMaterialStopResult = run(badRealMaterialStop);
if (badRealMaterialStopResult.status === 0) {
  process.stderr.write(badRealMaterialStopResult.stdout || "");
  process.stderr.write(badRealMaterialStopResult.stderr || "");
  console.error("Expected bad real-material stop fixture to fail.");
  process.exit(1);
}

const badRealMaterialStopOutput = `${badRealMaterialStopResult.stdout}\n${badRealMaterialStopResult.stderr}`;
for (const phrase of ["真实素材", "Image2"]) {
  if (!badRealMaterialStopOutput.includes(phrase)) {
    process.stderr.write(badRealMaterialStopOutput);
    console.error(`Real-material stop fixture failed for the wrong reason; missing phrase: ${phrase}`);
    process.exit(1);
  }
}

const badLocalTextCardResult = run(badLocalTextCard);
if (badLocalTextCardResult.status === 0) {
  process.stderr.write(badLocalTextCardResult.stdout || "");
  process.stderr.write(badLocalTextCardResult.stderr || "");
  console.error("Expected bad local text-card fixture to fail.");
  process.exit(1);
}

const badLocalTextCardOutput = `${badLocalTextCardResult.stdout}\n${badLocalTextCardResult.stderr}`;
for (const phrase of ["文字信息卡", "Image2"]) {
  if (!badLocalTextCardOutput.includes(phrase)) {
    process.stderr.write(badLocalTextCardOutput);
    console.error(`Local text-card fixture failed for the wrong reason; missing phrase: ${phrase}`);
    process.exit(1);
  }
}

console.log("Rednote chat output fixture check passed: good passes; workbench dump, old-artifact reuse, text/script downgrade, HookPrompt text-only pollution, real-material stop, and local text-card bypass fail.");
