#!/usr/bin/env node

import fs from "node:fs";

const file = process.argv[2];

if (!file) {
  console.error("Usage: node check-rednote-chat-output.mjs <final-chat-output.md>");
  process.exit(2);
}

const text = fs.readFileSync(file, "utf8");

const failures = [];
const warnings = [];

const workbenchHeadings = [
  "策略补全与决策提醒",
  "任务判断",
  "真人细节补位",
  "选题角度",
  "封面字",
  "图文页脚本",
  "视觉类型判断",
  "图片生成与配图提示词",
  "封面视觉验证",
  "批量图片生产",
  "标题",
  "正文草稿",
  "评论与私信承接",
  "标签建议",
  "最终成品自检",
];

const visibleWorkbenchCount = workbenchHeadings.filter((heading) =>
  new RegExp(`(^|\\n)\\*\\*?\\s*\\d*\\.?\\s*${heading}|(^|\\n)##\\s*${heading}`, "m").test(text),
).length;

if (visibleWorkbenchCount >= 6 && !/用户明确要求完整工作台|按用户要求展示完整工作台|allow_workbench_dump/i.test(text)) {
  failures.push("最终聊天输出倾倒了完整工作台；默认应展示发布版摘要，不展示 15 段过程");
}

if (
  /这次要做到哪一步|做到哪一步|是否只要文案|要不要先停在脚本/.test(text) &&
  !/用户明确只要文案|用户明确先不生成图片|explicit_text_only_request|text_only_requested|用户主动表达不确定/.test(text)
) {
  failures.push("生成类请求的前置决策完成后不得再问“这次要做到哪一步”；应继续生成封面，批量确认后生成整套图");
}

if (
  /文案\s*\+\s*脚本[\s\S]{0,40}推荐[\s\S]{0,80}不生成图片|推荐[\s\S]{0,40}文案\s*\+\s*脚本[\s\S]{0,80}不生成图片/.test(text) &&
  !/用户明确只要文案|用户明确先不生成图片|explicit_text_only_request|text_only_requested/.test(text)
) {
  failures.push("生成类请求不得把“文案+脚本、不生成图片”设为推荐路线，前置决策完成后应继续生成封面和整套图");
}

if (
  /不需要制作图片|只输出可(?:直接)?发布.*文案|只输出文案|不生成图片/.test(text) &&
  !/用户明确只要文案|用户明确先不生成图片|explicit_text_only_request|text_only_requested|blocked|partial|阻塞|未生成实图/.test(text)
) {
  failures.push("不得把非用户原话的“不需要制作图片/只输出文案”当成执行边界；原始生成类输入应继续走图片路线");
}

const previousArtifactReusePattern =
  /本地(?:其实|已经)?有一套|已有一套同题|历史输出|旧输出|旧图|旧包|复用旧|复用历史|以前生成|上次生成/i;
const explicitReusePermissionPattern =
  /用户明确要求复用|明确要求复用|explicit_reuse_permission|reuse_requested|按用户要求复用/i;

if (
  previousArtifactReusePattern.test(text) &&
  /(已生成|完整包|直接交付|图片包也在本地|批量生成了|生成封面)/.test(text) &&
  !explicitReusePermissionPattern.test(text)
) {
  failures.push("最终聊天把历史 outputs/旧图当成本轮生成；必须重新生成或写明旧产物仅作参考");
}

if (
  /(真实授权素材|最好用真实素材|最好用实拍|真实素材).{0,80}(本轮没有生成最终图片|没有生成最终图片|未生成最终图片|不生成最终图片)|本轮没有生成最终图片.{0,80}(真实授权素材|最好用真实素材|最好用实拍|真实素材)/s.test(
    text,
  ) &&
  !/用户明确先不生成图片|用户明确只要文案|host_refusal|宿主拒绝|工具失败|image_generation_failed|blocked_by_host/.test(text)
) {
  failures.push("真实素材/实拍素材不能作为不生成图片的理由；生成类请求应先走 Image2/宿主原生图像，失败才阻塞");
}

if (
  /(文字信息卡|图片上文字说明是主体|大字封面).{0,120}(本地排版|PowerShell|HTML|SVG|静态结构|PNG 文案卡|本地文字卡)/s.test(
    text,
  ) &&
  !/(imageGeneration|image_gen|generated_images|Image2|GPT Image|宿主原生).{0,120}(失败|错字|不可读|排版失败|fallback|降级|用户要求可编辑)/s.test(
    text,
  )
) {
  failures.push("文字信息卡不能绕过 Image2/宿主原生图像；只有图像文字失败或用户要求可编辑时才可本地排版 fallback");
}

const hasLiveImageEvidence =
  /imageGeneration|image_gen|generated_images|本轮新生成|新生成图片|宿主可见图片结果|!\[[^\]]*\]\([^)]+\.(?:png|jpg|jpeg)\)|已生成图像\s*\d|已生成图片\s*\d/i.test(
    text,
  );
const claimsGeneratedImages = /(已生成图像|已生成图片|批量生成了|封面预览|图片清单|完整.*图片|整套图)/.test(text);

if (claimsGeneratedImages && !hasLiveImageEvidence && !/blocked|partial|阻塞|未生成实图|缺实图证据/.test(text)) {
  failures.push("最终聊天声称已生成图片，但缺少本轮图片证据或诚实阻塞状态");
}

for (const required of ["标题", "正文", "标签"]) {
  if (!text.includes(required)) {
    warnings.push(`建议最终聊天包含${required}`);
  }
}

if (!/承接|评论|私信|互动边界|公开区/.test(text)) {
  warnings.push("建议最终聊天包含承接方式或互动边界");
}

if (failures.length) {
  console.error("Rednote chat output validation failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  if (warnings.length) {
    console.error("Warnings:");
    for (const warning of warnings) console.error(`- ${warning}`);
  }
  process.exit(1);
}

console.log(`Rednote chat output validation passed: ${visibleWorkbenchCount} visible workbench headings.`);
if (warnings.length) {
  console.log("Warnings:");
  for (const warning of warnings) console.log(`- ${warning}`);
}
