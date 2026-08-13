#!/usr/bin/env node

import fs from "node:fs";

const file = process.argv[2];

if (!file) {
  console.error("Usage: node check-rednote-note.mjs <output.md>");
  process.exit(2);
}

const text = fs.readFileSync(file, "utf8");

const requiredHeadings = [
  "## 策略补全与决策提醒",
  "## 任务判断",
  "## 真人细节补位",
  "## 选题角度",
  "## 封面字",
  "## 图文页脚本",
  "## 视觉类型判断",
  "## 图片生成与配图提示词",
  "## 封面视觉验证",
  "## 批量图片生产",
  "## 标题",
  "## 正文草稿",
  "## 评论与私信承接",
  "## 标签建议",
  "## 最终成品自检",
];

const banned = [
  "必爆",
  "保证涨粉",
  "保证成交",
  "轻松月入",
  "躺赚",
  "闭眼入",
  "全网最",
  "无脑",
  "姐妹们冲",
  "狠狠拿捏",
  "绝绝子",
  "保姆级",
  "不看后悔",
];

const warnings = [];
const failures = [];

const lightweightHeadings = [
  "## 策略判断",
  "## 标题备选",
  "## 图片提示词",
  "## 发布前避坑",
  "## 笔记任务判断",
  "## 3 个内容角度",
  "## 标题与封面字",
  "## 标签与评论引导",
  "## 发布前检查",
  "## 下一步补素材建议",
];

const previousArtifactReusePattern =
  /本地(?:其实|已经)?有一套|已有一套同题|历史输出|旧输出|旧图|旧包|复用旧|复用历史|以前生成|上次生成/i;
const explicitReusePermissionPattern =
  /用户明确要求复用|明确要求复用|explicit_reuse_permission|reuse_requested|按用户要求复用/i;

function section(name, nextNames = []) {
  const start = text.indexOf(`## ${name}`);
  if (start === -1) return "";
  let end = text.length;
  for (const nextName of nextNames) {
    const idx = text.indexOf(`## ${nextName}`, start + 1);
    if (idx !== -1 && idx < end) end = idx;
  }
  return text.slice(start, end).trim();
}

function requireOrder(first, second) {
  const firstIndex = text.indexOf(first);
  const secondIndex = text.indexOf(second);
  if (firstIndex !== -1 && secondIndex !== -1 && firstIndex > secondIndex) {
    failures.push(`${first} must appear before ${second}`);
  }
}

function countNumberedLines(sectionText) {
  return sectionText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => /^\d+[\.\u3001]/.test(line)).length;
}

function plainSectionText(sectionText, heading) {
  return sectionText.replace(new RegExp(`^##\\s*${heading}\\s*`), "").trim();
}

function sectionParagraphs(sectionText, heading) {
  return plainSectionText(sectionText, heading)
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

const provenancePattern = /(?:来源|证据来源)[：:]\s*(用户提供|研究证据|AI 假设)/;
const genericFieldValuePattern =
  /^(?:待定|待补|暂无|无|同上|略|按上文|根据内容|按需求|自行设计|占位|好看即可|一张好看的图|放一句标题|TBD|N\/?A)$/i;

function normalizeFieldValue(value) {
  return value
    .replace(/\s*(?:[。；;，,]\s*)?(?:来源|证据来源)[：:]\s*(?:用户提供|研究证据|AI 假设)[。；;，,\s]*$/u, "")
    .replace(/^[\s“”"'【】\[\]（）()]+|[\s“”"'【】\[\]（）()。；;，,]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function isMeaningfulFieldValue(value) {
  const normalized = normalizeFieldValue(value);
  if (!normalized || genericFieldValuePattern.test(normalized)) return false;
  if (/^[A-E]$/i.test(normalized)) return true;
  return [...normalized].length >= 2;
}

function requireFields(scopeLabel, scopeText, fields) {
  const values = new Map();
  for (const [fieldLabel, pattern, options = {}] of fields) {
    const match = scopeText.match(pattern);
    if (!match) {
      failures.push(scopeLabel + "缺少字段：" + fieldLabel);
      continue;
    }
    const rawValue = (match[1] || "").trim();
    if (!isMeaningfulFieldValue(rawValue)) {
      failures.push(scopeLabel + "字段值为空或无信息量：" + fieldLabel);
      continue;
    }
    const source = rawValue.match(provenancePattern)?.[1] || null;
    if (options.provenance && !source) {
      failures.push(scopeLabel + "字段缺少逐条来源：" + fieldLabel);
    }
    values.set(fieldLabel, {
      raw: rawValue,
      value: normalizeFieldValue(rawValue),
      source,
    });
  }
  return values;
}

function rejectRepeatedFieldValues(scopeLabel, fieldMaps, fieldLabels, minimumUnique = 3) {
  for (const fieldLabel of fieldLabels) {
    const values = fieldMaps
      .map((fieldMap) => fieldMap.get(fieldLabel)?.value)
      .filter(Boolean)
      .map((value) => value.toLowerCase());
    if (values.length >= minimumUnique && new Set(values).size < minimumUnique) {
      failures.push(
        scopeLabel +
          "字段在多页重复、没有形成有效变化：" +
          fieldLabel +
          "（至少需要 " +
          minimumUnique +
          " 个不同值）",
      );
    }
  }
}

function extractPageDirectionBlocks(sectionText) {
  const body = plainSectionText(sectionText, "图文页脚本");
  const pageHeader = /(?:^|\n)(?:#{3,6}\s*)?第\s*([1-8])\s*页(?:[：:][^\n]*)?\s*\n/g;
  const matches = [...body.matchAll(pageHeader)];
  return matches.map((match, index) => {
    const start = match.index + match[0].length;
    const end = matches[index + 1]?.index ?? body.length;
    return { page: Number(match[1]), text: body.slice(start, end).trim() };
  });
}

if (text.includes("## AI 参与标识建议")) {
  failures.push("output should not include AI 参与标识建议 as a front-stage section");
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
  !/用户明确只要文案|用户明确先不生成图片|explicit_text_only_request|text_only_requested|阻塞|partial/.test(text)
) {
  failures.push("不得把非用户原话的“不需要制作图片/只输出文案”当成执行边界；原始生成类输入应继续走图片路线");
}

if (
  previousArtifactReusePattern.test(text) &&
  /(已生成|完整包|交付状态：\s*交付级|批量生成了|图片包也在本地|直接交付)/.test(text) &&
  !explicitReusePermissionPattern.test(text)
) {
  failures.push("检测到历史 outputs/旧图被当成本轮生成交付；除非用户明确要求复用，否则旧产物只能作参考");
}

for (const heading of lightweightHeadings) {
  if (text.includes(heading)) {
    failures.push(`uses lightweight draft heading instead of workbench contract: ${heading}`);
  }
}

for (const heading of requiredHeadings) {
  if (!text.includes(heading)) {
    failures.push(`missing heading: ${heading}`);
  }
}

for (const phrase of banned) {
  if (text.includes(phrase)) {
    failures.push(`banned generic phrase: ${phrase}`);
  }
}

requireOrder("## 策略补全与决策提醒", "## 封面字");
requireOrder("## 批量图片生产", "## 标题");
requireOrder("## 标题", "## 正文草稿");
requireOrder("## 正文草稿", "## 评论与私信承接");
for (let i = 0; i < requiredHeadings.length - 1; i += 1) {
  requireOrder(requiredHeadings[i], requiredHeadings[i + 1]);
}

const mustMention = ["待补素材", "私信", "标题兑现", "提示词", "真实感", "生成图片", "最终成品", "Image2", "SVG 兜底"];
for (const item of mustMention) {
  if (!text.includes(item)) {
    warnings.push(`consider adding explicit mention: ${item}`);
  }
}

const pageMatches = text.match(/第\s*[1-8]\s*页/g) || [];
if (pageMatches.length < 6) {
  failures.push("图文页脚本少于 6 页");
}

const strategyDecisionSection = section("策略补全与决策提醒", ["任务判断"]);
const taskDecisionSection = section("任务判断", ["真人细节补位"]);
const angleSection = section("选题角度", ["封面字"]);
const coverTextSection = section("封面字", ["图文页脚本"]);
const pageScriptSection = section("图文页脚本", ["视觉类型判断"]);
const imagePromptSection = section("图片生成与配图提示词", ["封面视觉验证"]);
const visualStrategySection = section("视觉类型判断", ["图片生成与配图提示词"]);
const coverVisualSection = section("封面视觉验证", ["批量图片生产"]);
const batchImageSection = section("批量图片生产", ["标题"]);
const titleSection = section("标题", ["正文草稿"]);
const bodySection = section("正文草稿", ["评论与私信承接"]);
const commentHandoffSection = section("评论与私信承接", ["标签建议"]);
const finalCheckSection = section("最终成品自检", []);
const decisionEvidenceText = [
  strategyDecisionSection,
  visualStrategySection,
  imagePromptSection,
  titleSection,
  coverTextSection,
  coverVisualSection,
  batchImageSection,
  finalCheckSection,
].join("\n");
const humanDecisionText = decisionEvidenceText;
const promptPageMatches = imagePromptSection.match(/第\s*[1-8]\s*页/g) || [];

const opportunityDecisionText = [strategyDecisionSection, taskDecisionSection].join("\n");
if (!/内容机会研究[：:]/.test(opportunityDecisionText)) {
  failures.push("机会研究与营销决策缺少区块：内容机会研究");
}
const marketingDecisionValues = requireFields("机会研究与营销决策", opportunityDecisionText, [
  ["研究日期与能力", /^- 研究日期与能力[：:][ \t]*([^\r\n]*)$/m],
  ["读者搜索/浏览场景", /^- 读者搜索\/浏览场景[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["重复承诺与内容空缺", /^- 重复承诺与内容空缺[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["读者真实问题", /^- 读者真实问题[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["要抢的需求", /^- 要抢的需求[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["研究缺口", /^- 研究缺口[：:][ \t]*([^\r\n]*)$/m],
  ["目标读者与具体场景", /^- 目标读者与具体场景[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["需求阶段", /^- 需求阶段[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["主目标 / 次目标", /^- 主目标\s*\/\s*次目标[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["读者张力", /^- 读者张力[^\n：:]*[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["产品角色", /^- 产品角色[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["证据强度与不可说边界", /^- 证据强度(?:与不可说边界)?[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["表达强度及理由", /^- 表达强度[^\n：:]*[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["信息框架与标题路线", /^- 信息框架与标题路线[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
  ["视觉证据方式", /^- 视觉证据方式[：:][ \t]*([^\r\n]*)$/m, { provenance: true }],
]);
const repeatedMarketingValues = new Map();
for (const { value } of marketingDecisionValues.values()) {
  const normalized = value.toLowerCase();
  repeatedMarketingValues.set(normalized, (repeatedMarketingValues.get(normalized) || 0) + 1);
}
for (const [value, count] of repeatedMarketingValues) {
  if (count >= 3) {
    failures.push("机会研究与营销决策存在重复泛化值（" + count + " 个字段相同）：" + value);
  }
}

const pageDirectionBlocks = extractPageDirectionBlocks(pageScriptSection);
const uniquePageNumbers = new Set(pageDirectionBlocks.map(({ page }) => page));
if (pageDirectionBlocks.length < 6 || pageDirectionBlocks.length > 8 || uniquePageNumbers.size !== pageDirectionBlocks.length) {
  failures.push("逐页视觉导演表必须包含 6-8 个不重复的页面块，并用“### 第 N 页”分隔");
}
const pageDirectionFieldMaps = [];
for (const { page, text: pageText } of pageDirectionBlocks) {
  const fieldMap = requireFields("第 " + page + " 页视觉导演表", pageText, [
    ["页面角色", /^页面角色[：:][ \t]*([^\r\n]*)$/m],
    ["读者认知动作", /^(?:读者在本页完成的)?认知动作[：:][ \t]*([^\r\n]*)$/m],
    ["唯一信息承诺", /^(?:本页)?唯一(?:信息)?承诺[：:][ \t]*([^\r\n]*)$/m],
    ["画面主体与真实感锚点", /^画面主体与真实感锚点[：:][ \t]*([^\r\n]*)$/m],
    ["构图版式", /^构图版式[：:][ \t]*([^\r\n]*)$/m],
    ["构图选择理由", /^(?:选择理由|为什么这样构图)[：:][ \t]*([^\r\n]*)$/m],
    ["主体区", /^主体区[：:][ \t]*([^\r\n]*)$/m],
    ["主标题区与精确文字", /^主标题区(?:\s*\/\s*精确文字)?[：:][ \t]*([^\r\n]*)$/m],
    ["副标题或证据区与精确文字", /^(?:副标题或证据区|副标题区|证据区)(?:\s*\/\s*精确文字)?[：:][ \t]*([^\r\n]*)$/m],
    ["文字层级与位置", /^文字层级与位置[：:][ \t]*([^\r\n]*)$/m],
    ["不能遮挡或不能出现", /^不能遮挡或不能出现[：:][ \t]*([^\r\n]*)$/m],
    ["前后页连续元素", /^与前后页连续的元素[：:][ \t]*([^\r\n]*)$/m],
    ["Image2 结构化提示词", /^(?:本页\s*)?Image2\s*结构化提示词[：:][ \t]*([^\r\n]*)$/m],
    ["验收", /^验收[：:][ \t]*([^\r\n]*)$/m],
  ]);
  pageDirectionFieldMaps.push(fieldMap);
}
rejectRepeatedFieldValues(
  "逐页视觉导演表",
  pageDirectionFieldMaps,
  ["读者认知动作", "唯一信息承诺", "画面主体与真实感锚点", "Image2 结构化提示词"],
);
if (!/待确认决策|用户已确认|默认假设/.test(strategyDecisionSection)) {
  failures.push("策略补全与决策提醒缺少待确认决策/用户已确认/默认假设");
}
if (!/确认状态|用户已明确确认|用户已确认|原生确认|request_user_input|AskUserQuestion|阻塞：缺少原生确认工具/.test(decisionEvidenceText)) {
  failures.push("缺少分步确认证据或阻塞状态，不能用一次性长文替代决策流程");
}
if (/普通聊天卡|聊天决策卡|Markdown\s*选项卡|文字决策卡/.test(decisionEvidenceText) && !/不算确认|阻塞|停止等待/.test(decisionEvidenceText)) {
  failures.push("普通聊天卡/Markdown 选项卡不能冒充原生确认后继续执行");
}
if (!/人类决策记录/.test(humanDecisionText)) {
  failures.push("缺少人类决策记录，不能靠生成后抽卡返工");
}
for (const requiredDecision of ["策略路线", "标题与封面字", "视觉方案", "模板路由", "封面候选图", "批量生产许可", "继续执行许可"]) {
  if (!humanDecisionText.includes(requiredDecision)) {
    failures.push(`人类决策记录缺少字段：${requiredDecision}`);
  }
}
if (!/human_confirmed|explicit_auto_permission|blocked_pending_human_decision|pending_user_review/.test(humanDecisionText)) {
  failures.push("人类决策记录缺少标准状态 human_confirmed / explicit_auto_permission / blocked_pending_human_decision");
}
if (/默认假设/.test(humanDecisionText) && /封面图文件|图片文件|\.png|\.jpg|已用 Image2|Image2 一体化封面生成/.test(coverVisualSection + "\n" + batchImageSection) && !/human_confirmed|explicit_auto_permission|用户已明确确认|用户已确认/.test(humanDecisionText)) {
  failures.push("默认假设不能触发 Image2 出图或批量生产，必须有人类确认或明确自动授权");
}
if (/继续执行许可[：:]\s*yes/.test(humanDecisionText) && /blocked_pending_human_decision|待用户确认|未确认/.test(humanDecisionText)) {
  failures.push("仍有待确认/阻塞项时，继续执行许可不能为 yes");
}
const completeDeliveryIntent = /完整交付|完整视觉交付|能发的成品包|图片也做出来|帮我把图片也做出来|整套图|完整图集/.test(text);
const singleCoverStop =
  /已生成上方那张封面候选图|已生成封面候选\s*1\s*张|已生成封面候选图\s*1\s*张|批量内页图必须等你确认封面|等你确认上方封面|封面确认后才能.*批量|暂不批量生成图片/.test(
    [coverVisualSection, batchImageSection, finalCheckSection].join("\n"),
  );
const nativeChoiceEvidence =
  /原生确认证据[：:][\s\S]{0,80}(request_user_input|AskUserQuestion|已弹出|已返回|returned)|阻塞：缺少原生确认工具/.test(
    decisionEvidenceText + "\n" + coverVisualSection + "\n" + batchImageSection + "\n" + finalCheckSection,
  );
const textOnlyCoverConfirm =
  /下一步只需要你确认|下一步.*确认.*封面|通过的话.*批量|通过.*我再.*批量|确认上方封面|确认封面候选图|等你确认.*封面|待你确认.*封面/.test(
    [coverVisualSection, batchImageSection, finalCheckSection].join("\n"),
  );
if (completeDeliveryIntent && singleCoverStop) {
  failures.push("完整交付请求不能只生成 1 张封面并停在等待封面确认");
}
if (textOnlyCoverConfirm && !nativeChoiceEvidence) {
  failures.push("封面完成后不能只用文字要求确认，必须有 request_user_input / AskUserQuestion 原生弹框证据");
}
if (/pending_user_review|待用户确认/.test(coverVisualSection + "\n" + batchImageSection) && !nativeChoiceEvidence) {
  failures.push("pending_user_review 必须绑定原生弹框证据，不能只是正文里写待确认");
}
if (
  completeDeliveryIntent &&
  /批量生产许可[：:]\s*blocked_pending_human_decision/.test(humanDecisionText + "\n" + batchImageSection) &&
  /封面.*待用户确认|等你确认|封面未确认|待用户确认/.test(coverVisualSection + "\n" + batchImageSection)
) {
  failures.push("完整交付许可下不能用封面待确认二次闸门阻断批量图片生产");
}
if (!/策略选项|推荐/.test(strategyDecisionSection)) {
  failures.push("策略补全与决策提醒缺少策略选项和推荐");
}
if (countNumberedLines(strategyDecisionSection) < 2) {
  failures.push("策略补全与决策提醒少于 2 个策略选项");
}
if (countNumberedLines(angleSection) < 3) {
  failures.push("选题角度少于 3 个角度");
}
if (!/已确认选题角度|主推角度|推荐角度/.test(angleSection)) {
  failures.push("选题角度缺少已确认/主推角度");
}
for (const requiredAngleField of ["适合人群", "素材要求", "风险提醒"]) {
  if (!angleSection.includes(requiredAngleField)) {
    failures.push(`选题角度缺少${requiredAngleField}`);
  }
}
if (!/实拍|信息卡|Plog|产品细节|流程图|纯文字封面|拼图合集|抠图拼贴|前后对比/.test(visualStrategySection)) {
  failures.push("视觉类型判断缺少小红书视觉类型");
}
if (!/真实感来源|生活痕迹|真实物件|手机拍摄感|自然光|不完美细节/.test(visualStrategySection)) {
  failures.push("视觉类型判断缺少真实感来源");
}
if (!/可以模拟生成|可模拟生成|可以生成/.test(visualStrategySection)) {
  failures.push("视觉类型判断缺少可模拟生成边界");
}
if (!/3:4|竖版|1080\s*x\s*1440|1242\s*x\s*1660/.test(visualStrategySection)) {
  failures.push("视觉类型判断缺少小红书图片比例策略");
}
if (!/手机信息流|小图测试|缩略图|缩小后/.test(visualStrategySection + imagePromptSection)) {
  failures.push("缺少手机信息流小图测试");
}
const thumbnailText = [visualStrategySection, imagePromptSection, coverVisualSection].join("\n");
if (!/主标题|标题足够大|先读标题|最大信息层/.test(thumbnailText)) {
  failures.push("缺少主标题在手机信息流中足够大的判断");
}
if (!/视觉重心|上中部|左中部|上重下空|不要贴顶|标题位置/.test(thumbnailText)) {
  failures.push("缺少标题位置和视觉重心判断，不能只检查字号");
}
if (/右下角小贴纸|小贴纸|小角标|小标签|小字说明/.test(thumbnailText) && !/不要|不得|禁止|删除|不依赖|不出现|无意义/.test(thumbnailText)) {
  failures.push("封面不能依赖右下角小贴纸/小角标/小标签补充主题");
}
const visualOptionCount =
  (visualStrategySection.match(/^\s*\d+[\.\u3001]/gm) || []).length +
  (visualStrategySection.match(/视觉方案\s*\d/g) || []).length;
if (visualOptionCount < 2) {
  failures.push("视觉类型判断少于 2 个视觉方案选项");
}
if (!/推荐方案|推荐视觉|首选视觉/.test(visualStrategySection)) {
  failures.push("视觉类型判断缺少推荐视觉方案");
}
if (!/6\s*[-到~—]\s*10\s*字|6\s*[-到~—]\s*10个字|六到十字|封面字.*短/.test(visualStrategySection + imagePromptSection)) {
  warnings.push("建议明确封面字 6-10 字或短字策略");
}
if (!/封面图提示词|封面提示词/.test(imagePromptSection)) {
  failures.push("缺少封面图提示词");
}
if (!/一体化|完整封面|画面.*标题.*排版|标题.*封面字.*排版|integrated cover|一次性生成/.test(imagePromptSection)) {
  failures.push("封面提示词缺少 Image2/GPT Image 一体化生成要求");
}
if (!/Image2\s*一体化封面\s*Brief|结构化封面\s*Brief|封面\s*Brief/.test(imagePromptSection)) {
  failures.push("封面提示词前缺少 Image2 一体化封面 Brief");
}
if (!/绘画提示词模板路由|提示词模板路由|模板路由|模板类型|Prompt Template|Template Route/.test(imagePromptSection)) {
  failures.push("图片生成与配图提示词缺少绘画提示词模板路由");
}
const templateCodes = imagePromptSection.match(/\bT(?:10|[1-9])\b/g) || [];
if (templateCodes.length < 2) {
  failures.push("绘画提示词模板路由少于 2 个模板代码");
}
if (!/\bT1\b|一体化文字封面/.test(imagePromptSection)) {
  failures.push("封面模板路由缺少 T1 一体化文字封面");
}
if (!/\bT9\b|多页系列一致性/.test(imagePromptSection)) {
  warnings.push("建议为 6-8 页内页加入 T9 多页系列一致性模板");
}
const briefFieldChecks = [
  ["模板路由", /模板路由|模板类型|T(?:10|[1-9])/],
  ["视觉任务", /视觉任务/],
  ["已确认文字", /已确认文字|已确认标题/],
  ["一秒先读", /一秒先读|第一眼先读|手机信息流.*先读/],
  ["真实场景锚点", /真实场景锚点|真实场景|场景锚点/],
  ["构图", /构图/],
  ["镜头与光线", /镜头与光线|镜头|光线/],
  ["材质与色彩", /材质与色彩|材质|色彩/],
  ["文字层级", /文字层级|主标题.*最大|最大信息层/],
  ["验收标准", /验收标准|通过标准|手机信息流.*可读/],
  ["fallback 触发", /fallback\s*触发|降级触发|错字|不可读|排版失败/],
];
for (const [fieldName, pattern] of briefFieldChecks) {
  if (!pattern.test(imagePromptSection)) {
    failures.push(`Image2 一体化封面 Brief 缺少字段：${fieldName}`);
  }
}
const coverDirectionText = [imagePromptSection, coverVisualSection].join("\n");
requireFields("封面视觉导演表", coverDirectionText, [
  ["版式", /^(?:封面)?版式[：:][ \t]*([^\r\n]*)$/m],
  ["主体区", /^主体区[：:][ \t]*([^\r\n]*)$/m],
  ["主标题区与精确文字", /^主标题区(?:与精确文字|\s*\/\s*精确文字)?[：:][ \t]*([^\r\n]*)$/m],
  ["副标题区与精确文字", /^副标题区(?:与精确文字|\s*\/\s*精确文字)?[：:][ \t]*([^\r\n]*)$/m],
  ["不能遮挡区", /^不能遮挡区[：:][ \t]*([^\r\n]*)$/m],
  ["缩略图第一眼承诺", /^缩略图第一眼(?:承诺|读到什么)[：:][ \t]*([^\r\n]*)$/m],
  ["构图选择理由", /^(?:(?:构图)?选择理由|为什么选这套构图)[：:][ \t]*([^\r\n]*)$/m],
]);
if (!/GPT Image|Image2|豆包|即梦|Midjourney|通用英文/.test(imagePromptSection)) {
  failures.push("缺少多工具图片生成适配");
}
if (promptPageMatches.length < 6) {
  failures.push("图文页配图提示词少于 6 页");
}
if (!/Image2[\s\S]*其他图片生成|Image2[\s\S]*MCP|其他图片生成[\s\S]*SVG 兜底/.test(batchImageSection)) {
  failures.push("批量图片生产缺少 Image2 -> 其他图片生成 MCP/工具 -> SVG 兜底路线");
}
if (!/Image2 全套成功|全套图成功|不再生成 SVG|停止 SVG/.test(batchImageSection)) {
  failures.push("批量图片生产缺少 Image2 全套成功后停止 SVG/模拟包的规则");
}
const imageRouteText = [imagePromptSection, coverVisualSection, batchImageSection, finalCheckSection].join("\n");
if (!/Image2\s*优先级证据|Image2\s*最高优先级|Image2\s*是最高优先级/.test(imageRouteText)) {
  failures.push("缺少 Image2 优先级证据，必须明确 Image2 是最高优先级且 MCP 只能在 Image2 不可用/失败后降级");
}
const actualMcpGeneration =
  /MCP[^\n]*(已完成|已生成|生成结果|图片路径|封面图文件|integrated cover)|minimax|MiniMax|text_to_image|豆包[^\n]*(已完成|已生成)|即梦[^\n]*(已完成|已生成)|Midjourney[^\n]*(已完成|已生成)|其他图片生成 MCP[^\n]*(已完成|已生成|实际状态)/i.test(
    imageRouteText,
  );
const image2DowngradeProof =
  /Image2\s*优先级证据[：:][^\n]*(已调用并失败|调用失败|不可用|无 Image2 可调用工具|当前宿主无 Image2|用户明确要求不用 Image2)|Image2[^\n]*(不可用|调用失败|生成失败|无可调用工具|当前宿主无)|降级原因[：:][^\n]*Image2/i.test(
    imageRouteText,
  );
if (actualMcpGeneration && !image2DowngradeProof) {
  failures.push("检测到实际使用 MCP/其他图片生成工具，但缺少 Image2 不可用或失败证据；MCP 不得抢在 Image2 前调用");
}
if (!/已确认标题|待用户确认标题|标题/.test(coverVisualSection)) {
  failures.push("封面视觉验证缺少已确认标题/待确认标题");
}
if (!/已确认封面字|待用户确认封面字|封面字/.test(coverVisualSection)) {
  failures.push("封面视觉验证缺少已确认封面字/待确认封面字");
}
if (!/手机信息流|小图测试|缩略图/.test(coverVisualSection)) {
  failures.push("封面视觉验证缺少手机信息流小图测试");
}
if (!/用户确认|待用户确认|已确认/.test(coverVisualSection)) {
  failures.push("封面视觉验证缺少用户确认状态");
}
if (!/封面生成路线|Image2 integrated cover|integrated cover|一体化封面|photo layer \+ editable overlay fallback|可编辑文字叠加 fallback|SVG fallback/.test(coverVisualSection)) {
  failures.push("封面视觉验证缺少封面生成路线，不能混淆一体化生成和叠字 fallback");
}
const mentionsOverlayRoute = /照片层|photo layer|叠加|overlay|可编辑文字/.test(coverVisualSection);
const overlayRouteNegated =
  /没有使用.{0,12}(照片层|叠字|叠加|overlay|可编辑文字)|未使用.{0,12}(照片层|叠字|叠加|overlay|可编辑文字)|不是.{0,12}(照片层|叠字|叠加|overlay|可编辑文字)/.test(
    coverVisualSection,
  );
if (mentionsOverlayRoute && !overlayRouteNegated && !/fallback|降级|错字|不可读|排版失败|文字失败|用户要求可编辑|不算 Image2 一体化成功|不能冒充/.test(coverVisualSection)) {
  failures.push("使用照片层/叠字时必须说明 fallback 原因，不能冒充 Image2 一体化封面");
}
if (!/封面图文件|图片文件|图片路径|封面图路径|宿主可见图片结果|生成结果|实图证据|image2-phone-feed-test|final-cover\.(png|jpg|jpeg)|\.png|\.jpg|阻塞：缺实图证据/.test(coverVisualSection)) {
  failures.push("封面视觉验证缺少图片文件、宿主可见结果或缺实图阻塞状态");
}
const imagePendingText = [coverVisualSection, batchImageSection, finalCheckSection].join("\n");
const imagePending =
  /待\s*(Image2\s*)?生成|待生成|未生成|不能出图|只提供提示词|只给提示词|没有实图|缺实图证据/.test(imagePendingText);
if (imagePending && !/交付状态：\s*(partial|blocked)|阻塞：缺实图证据|不能写成交付级|不判为交付级/.test(imagePendingText)) {
  failures.push("图片未生成或缺实图时，必须标注 partial/blocked，不能暗示完整交付");
}
if (/交付状态：\s*交付级/.test(imagePendingText) && imagePending) {
  failures.push("缺少实图或仍待生成时不能写交付状态：交付级");
}
if (!/交付状态：\s*(交付级|partial|blocked)/.test(batchImageSection + "\n" + finalCheckSection)) {
  failures.push("批量图片生产或最终自检缺少交付状态");
}
const innerPageAssetMatches =
  batchImageSection.match(/(?:final-page-\d{2}|第\s*[1-8]\s*页[^\n]*(?:\.png|\.jpg|\.jpeg|图片路径|生成结果|已生成))/g) || [];
if (/交付状态：\s*交付级/.test(batchImageSection + "\n" + finalCheckSection) && completeDeliveryIntent && innerPageAssetMatches.length < 6) {
  failures.push("完整视觉交付写成交付级时，批量图片生产必须列出至少 6 页内页图证据");
}

if (!/已确认标题|待用户确认标题/.test(titleSection)) {
  failures.push("标题区缺少已确认标题/待用户确认标题");
}
if (!/标题选项|保留备选/.test(titleSection)) {
  failures.push("标题区缺少标题选项/保留备选");
}
if (!/已确认封面字|待用户确认封面字/.test(coverTextSection)) {
  failures.push("封面字区缺少已确认封面字/待用户确认封面字");
}
if (!/封面字选项|保留备选/.test(coverTextSection)) {
  failures.push("封面字区缺少封面字选项/保留备选");
}
if (countNumberedLines(coverTextSection) < 3) {
  failures.push("封面字少于 3 组选项");
}
const titleLines = titleSection
  .split(/\r?\n/)
  .map((line) => line.trim())
  .filter((line) => /^\d+\./.test(line));

if (titleLines.length < 8) {
  failures.push("标题少于 8 个，标题区必须保留多选/备选空间");
}
if (!/多选|保留备选|可作为备选|备选|推荐/.test(titleSection)) {
  failures.push("标题区缺少多选/推荐/保留备选说明，不能只给单一最终标题");
}
if (text.indexOf("## 标题") < text.indexOf("## 批量图片生产")) {
  failures.push("最终标题必须放在批量图片生产后面，方便和图片一起交付");
}
if (text.indexOf("## 正文草稿") < text.indexOf("## 批量图片生产")) {
  failures.push("正文草稿必须放在批量图片生产后面，方便和图片一起交付");
}
if (!bodySection.trim()) {
  failures.push("正文草稿为空");
}
const bodyText = plainSectionText(bodySection, "正文草稿");
const hasConcreteBodyAnchor = /场景|步骤|方法|标准|对比|适合|不适合|过程|证据|问题|行动|清单|条件/.test(bodyText);
if (!hasConcreteBodyAnchor) {
  failures.push("正文缺少可执行的场景、方法、比较、证据或行动锚点");
}
const mainGoalValue = marketingDecisionValues.get("主目标 / 次目标")?.value || "";
const informationFrameValue = marketingDecisionValues.get("信息框架与标题路线")?.value || "";
const primaryGoalValue = mainGoalValue.split(/次目标[为：:]?/)[0];
const narrativeSignal = primaryGoalValue + " " + informationFrameValue;
let narrativeRoute = "unspecified";
if (/信任|种草/.test(narrativeSignal)) narrativeRoute = "trust";
else if (/咨询|转化|比较|准备行动|判断标准|怎么选/.test(narrativeSignal)) narrativeRoute = "comparison";
else if (/收藏|搜索|找方法|清单|教程|答案/.test(narrativeSignal)) narrativeRoute = "search-save";
else if (/评论|讨论|观点|争议/.test(narrativeSignal)) narrativeRoute = "discussion";
else if (/停留|未意识|场景痛点|身份认同/.test(narrativeSignal)) narrativeRoute = "awareness";

if (narrativeRoute === "trust") {
  if (!/以前|后来|过程|尝试|使用|记录|场景|经历/.test(bodyText)) {
    failures.push("信任/种草路线正文缺少真实场景或过程");
  }
  if (!/证据|结果|运行|变化|失败|限制|截图|材料|不适合|不承诺/.test(bodyText)) {
    failures.push("信任/种草路线正文缺少证据、结果或克制边界");
  }
} else if (narrativeRoute === "search-save") {
  if (!/步骤|方法|清单|标准|先|再|怎么做|如何/.test(bodyText)) {
    failures.push("搜索/收藏路线正文缺少可执行方法、步骤或判断标准");
  }
  if (!/易错|条件|注意|验收|适合|不适合|保存|收藏|边界/.test(bodyText)) {
    failures.push("搜索/收藏路线正文缺少易错点、适用条件或可保存结论");
  }
} else if (narrativeRoute === "comparison") {
  if (!/对比|区别|标准|维度|怎么选|适合/.test(bodyText)) {
    failures.push("比较/咨询路线正文缺少选择标准或比较维度");
  }
  if (!/不适合|限制|边界|条件|证据|不能/.test(bodyText)) {
    failures.push("比较/咨询路线正文缺少适用边界或证据");
  }
} else if (narrativeRoute === "discussion") {
  if (!/观点|判断|反常识|为什么|争议/.test(bodyText) || !/例子|场景|反例|边界|讨论|你怎么看/.test(bodyText)) {
    failures.push("观点/讨论路线正文必须同时有明确判断和例子、反例或讨论边界");
  }
} else if (narrativeRoute === "awareness") {
  if (!/场景|痛点|卡住|担心|害怕|问题/.test(bodyText) || !/理解|判断|原因|不是[\s\S]{0,80}而是/.test(bodyText)) {
    failures.push("停留/认知路线正文缺少具体痛点场景或新理解");
  }
} else {
  warnings.push("无法从营销决策识别正文叙事路线；请明确主目标与信息框架");
}

const overtLeadGenPatterns = [
  /私信\s*(我|给我|发我|聊|咨询|了解)/i,
  /你可以发我|发我你|发给我|发我\s*你想做/i,
  /想了解(这门课|课程)|了解[\s\S]{0,12}课程/i,
  /领取|领资料|资料包|体验路线|路线[\s\S]{0,12}私信|私信[\s\S]{0,12}路线/i,
  /加微信|微信|二维码|加群|进群|报名|报课|咨询课程|课程咨询|购买|外链|联系方式|VX|v信/i,
];
const commentLeadGenLines = commentHandoffSection
  .split(/\r?\n/)
  .map((line) => line.trim())
  .filter(Boolean);
const hasOvertLeadGenLine = commentLeadGenLines.some((line) => {
  const isBoundaryLine = /不主动|不得|不写|不索要|不承诺|只回复|公开可核验|站内互动边界|如果有人主动/.test(line);
  return !isBoundaryLine && overtLeadGenPatterns.some((pattern) => pattern.test(line));
});
if (hasOvertLeadGenLine) {
  failures.push("评论与私信承接含明显导流/导私话术，课程类笔记只能保留低风险公开互动和站内互动边界");
}
if (!/不主动引导私信|不主动导私|公开区|站内互动边界|不索要联系方式|公开可核验/.test(commentHandoffSection)) {
  failures.push("评论与私信承接缺少站内互动边界，必须明确不主动导私、不索要联系方式或只给公开可核验信息");
}

for (const line of titleLines) {
  const title = line.replace(/^\d+\.\s*/, "");
  if (/[\[【（(](痛点|反常识|经验|清单|避坑|轻观点)[\]】）)]/.test(title)) {
    failures.push(`title exposes internal type label: ${title}`);
  }
  if (title.length > 34) {
    warnings.push(`title may be too long: ${title}`);
  }
}

const tagSection =
  text.split("## 标签建议")[1]?.split("## 最终成品自检")[0] || "";
const tags = tagSection.match(/#[\p{L}\p{N}_-]+/gu) || [];
if (tags.length < 3) {
  failures.push("标签建议少于 3 个");
}
if (tags.length > 6) {
  warnings.push(`标签建议超过 6 个: ${tags.join(" ")}`);
}

if (failures.length) {
  console.error("Rednote note validation failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  if (warnings.length) {
    console.error("Warnings:");
    for (const warning of warnings) console.error(`- ${warning}`);
  }
  process.exit(1);
}

console.log(
  `Rednote note validation passed: ${requiredHeadings.length} required sections, ${pageMatches.length} page markers, ${titleLines.length} titles, ${tags.length} tags.`,
);

if (warnings.length) {
  console.log("Warnings:");
  for (const warning of warnings) console.log(`- ${warning}`);
}
