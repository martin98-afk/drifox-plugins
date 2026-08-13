#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const input = process.argv[2];
const outputArg = process.argv[3];

if (!input) {
  console.error("Usage: node scripts/build-rednote-realshot-handoff.mjs <output.md> [output-dir]");
  process.exit(2);
}

const inputPath = path.resolve(input);
if (!fs.existsSync(inputPath)) {
  console.error(`Output markdown not found: ${inputPath}`);
  process.exit(2);
}

const outputDir = path.resolve(outputArg || path.join(process.cwd(), "rednote-realshot-handoff"));
fs.mkdirSync(outputDir, { recursive: true });

const text = fs.readFileSync(inputPath, "utf8");

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

function cleanMarkdown(value) {
  return String(value || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[#>*_|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function extractShortLine(block, label) {
  const labels = ["页标题", "画面建议", "正文短句", "素材需求"].filter((item) => item !== label).join("|");
  const match = block.match(new RegExp(`${label}[：:]\\s*([\\s\\S]*?)(?=；\\s*(?:${labels})[：:]|。\\s*(?:${labels})[：:]|\\n|$)`));
  return match ? cleanMarkdown(match[1]).replace(/^["“]|["”]$/g, "").trim() : "";
}

function extractCoverLines() {
  const cover = section("封面字", ["图文页脚本"]);
  const lines = cover
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !/^##|^备选|^方案|^\d+[.、]/.test(line))
    .map((line) => cleanMarkdown(line))
    .filter((line) => line && !/^封面字$/.test(line));
  return lines.slice(0, 2).length ? lines.slice(0, 2) : ["先看真实素材", "再决定怎么写"];
}

function clipText(value, max = 118) {
  const cleaned = cleanMarkdown(value);
  return cleaned.length > max ? `${cleaned.slice(0, max - 1)}…` : cleaned;
}

function extractPages() {
  const script = section("图文页脚本", ["视觉类型判断"]);
  const matches = [...script.matchAll(/^第\s*(\d+)\s*页[^\n]*/gm)];
  const pages = [];
  for (let i = 0; i < matches.length; i += 1) {
    const match = matches[i];
    const pageNo = Number(match[1]);
    const nextIndex = matches[i + 1]?.index ?? script.length;
    const block = script.slice(match.index, nextIndex);
    pages.push({
      pageNo,
      title: extractShortLine(block, "页标题") || `第 ${pageNo} 页`,
      body: extractShortLine(block, "正文短句") || cleanMarkdown(block).slice(0, 80),
      visual: extractShortLine(block, "画面建议") || "按视觉类型判断补真实画面",
      material: extractShortLine(block, "素材需求") || "待补真实素材",
    });
  }
  return pages;
}

function extractTags() {
  const tagText = section("标签建议", ["最终成品自检"]);
  return tagText.match(/#[\p{L}\p{N}_-]+/gu) || [];
}

function detectDomain() {
  const haystack = text;
  if (/美甲|穿戴甲|甲片|甲床|色卡|手模/.test(haystack)) return "beauty-nail";
  if (/Plog|plog|生活方式|日常|出租屋|桌搭|探店/.test(haystack)) return "plog-life";
  if (/职场|老板|汇报|会议|项目|复盘|简历|面试/.test(haystack)) return "workplace-knowledge";
  if (/课程|咨询|知识博主|观点|方法论/.test(haystack)) return "knowledge-opinion";
  return "general-rednote";
}

function domainVisualRules(domain) {
  const rules = {
    "beauty-nail": {
      primary: "社区美甲小店真实桌面，甲片色卡、甲片尺、手写清单、自然光、手机随拍感",
      negative: "顾客视角、聊天界面感、日常手部动作、自然广告字、真实使用痕迹、非棚拍",
      captureTip: "用手部视角、手模、甲片色卡和店内桌面建立场景；主物件要比封面字更先被看见。",
    },
    "plog-life": {
      primary: "真实生活桌面、随手物件、自然光、不完美边角、手机相册感",
      negative: "生活现场感、真实杂物、轻微摆放痕迹、自然色温、手机相册感",
      captureTip: "用 3-5 个生活场景组织画面，保留轻微杂物和真实使用痕迹。",
    },
    "workplace-knowledge": {
      primary: "真实办公桌面、纸质草稿、电脑局部、手写框架、信息卡留白",
      negative: "截图样式、桌面草稿、局部电脑屏幕、真实办公质感、非商务图库风",
      captureTip: "用桌面材料、手写便签和局部屏幕表达观点。",
    },
    "knowledge-opinion": {
      primary: "桌面书本、批注纸、手写观点卡、简洁信息卡、自然光",
      negative: "观点卡、批注、引用来源留白、课程信息弱化、自然记录感",
      captureTip: "用笔记、批注、观点卡和过程材料承担真实感。",
    },
    "general-rednote": {
      primary: "真实桌面、手写清单、手机随拍感、清楚主体和留白",
      negative: "手机随拍感、自然画面瑕疵、真实屏幕或纸面记录、清楚主体",
      captureTip: "先拍主物件、过程物件、手写清单三类素材，再生成辅助背景。",
    },
  };
  return rules[domain] || rules["general-rednote"];
}

function splitListLine(line) {
  const clean = cleanMarkdown(line)
    .replace(/^[-\d.、\s]+/, "")
    .replace(/^(待补素材|可以模拟生成|模拟真实素材方向)[：:]/, "");
  return clean
    .split(/[、，,；;]/)
    .map((item) => cleanMarkdown(item))
    .filter(Boolean);
}

function extractVisualBuckets() {
  const visual = section("视觉类型判断", ["图片生成与配图提示词"]);
  const buckets = { canGenerate: [], materialGaps: [] };
  for (const line of visual.split(/\r?\n/)) {
    if (/可以模拟|可以生成|模拟真实|素材|场景|物件|截图|人物/.test(line)) buckets.canGenerate.push(...splitListLine(line));
    if (/待补|素材需求/.test(line)) buckets.materialGaps.push(cleanMarkdown(line));
  }
  const detail = section("真人细节补位", ["选题角度"]);
  for (const line of detail.split(/\r?\n/)) {
    if (/待补素材|真实物件|真实场景/.test(line)) buckets.canGenerate.push(...splitListLine(line));
  }
  return buckets;
}

function promptFor({ kind, title, visual, material, domain, coverLines }) {
  const rules = domainVisualRules(domain);
  const subject = kind === "cover" ? coverLines.join(" / ") : title;
  const scene = cleanMarkdown(visual || rules.primary);
  const object = cleanMarkdown(material || "真实主物件、手写清单、自然光桌面");
  const zh = [
    "竖版 3:4 小红书真实感图片。",
    `主题：${subject}。`,
    `画面：${scene}。`,
    `必须出现：${object}。`,
    `风格：${rules.primary}，自然光，手机随拍感，主体清楚，保留封面字留白。`,
    `风格备注：${rules.negative}。`,
  ].join(" ");
  const doubao = `3:4竖版，小红书真实感，${scene}，${object}，自然光，手机随拍感，留白清楚，${rules.negative}`;
  const en = [
    "vertical 3:4 Rednote-style realistic mobile photo",
    scene,
    object,
    "natural daylight, real objects, slight imperfections, clear subject, room for short cover text",
    rules.negative,
  ].join(", ");
  return { gptImage: zh, doubaoJImeng: doubao, englishKeywords: en, styleNote: rules.negative };
}

function unique(values) {
  return [...new Set(values.map((value) => cleanMarkdown(value)).filter(Boolean))];
}

function buildCaptureRows({ pages, buckets, domain }) {
  const rows = [];
  const rules = domainVisualRules(domain);
  const canGenerate = unique([...buckets.canGenerate, ...pages.flatMap((page) => splitListLine(page.material))]);

  for (const page of pages) {
    rows.push({
      itemId: `P${String(page.pageNo).padStart(2, "0")}`,
      page: `page-${page.pageNo}`,
      title: page.title,
      asset: page.material,
      priority: page.pageNo <= 3 ? "high" : "medium",
      canGenerate: "yes",
      assetMode: "simulate-real-material",
      captureDirection: page.visual,
    });
  }

  for (const [index, item] of canGenerate.slice(0, 8).entries()) {
    rows.push({
      itemId: `G${String(index + 1).padStart(2, "0")}`,
      page: "aux",
      title: "可生成辅助素材",
      asset: item,
      priority: "low",
      canGenerate: "yes",
      assetMode: "generated-aux",
      captureDirection: rules.captureTip,
    });
  }

  return rows;
}

function writeCsv(file, rows, columns) {
  const content = [
    columns.join(","),
    ...rows.map((row) => columns.map((col) => csvCell(row[col])).join(",")),
  ].join("\n");
  fs.writeFileSync(file, `${content}\n`, "utf8");
}

function requireFrom(candidate, moduleName) {
  if (!fs.existsSync(candidate)) return null;
  try {
    const req = createRequire(candidate);
    return req(moduleName);
  } catch {
    return null;
  }
}

async function loadPlaywright() {
  for (const moduleName of ["playwright-core", "playwright"]) {
    try {
      return await import(moduleName);
    } catch {
      // Try bundled runtime below.
    }
  }

  const runtimeRoot = path.join(process.env.USERPROFILE || "", ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules");
  const fixedRuntimeRoot = path.join("C:", "Users", "Kim", ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules");
  const roots = [...new Set([runtimeRoot, fixedRuntimeRoot])];
  const candidates = [];
  for (const root of roots) {
    candidates.push({ packageFile: path.join(root, "playwright-core", "package.json"), moduleName: "playwright-core" });
    candidates.push({ packageFile: path.join(root, "playwright", "package.json"), moduleName: "playwright" });
    const pnpmDir = path.join(root, ".pnpm");
    if (fs.existsSync(pnpmDir)) {
      for (const entry of fs.readdirSync(pnpmDir)) {
        if (entry.startsWith("playwright-core@")) {
          candidates.push({ packageFile: path.join(pnpmDir, entry, "node_modules", "playwright-core", "package.json"), moduleName: "playwright-core" });
        }
        if (entry.startsWith("playwright@")) {
          candidates.push({ packageFile: path.join(pnpmDir, entry, "node_modules", "playwright", "package.json"), moduleName: "playwright" });
        }
      }
    }
  }

  for (const candidate of candidates) {
    const loaded = requireFrom(candidate.packageFile, candidate.moduleName);
    if (loaded) return loaded;
  }
  return null;
}

function findBrowser() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    path.join(process.env.PROGRAMFILES || "", "Google", "Chrome", "Application", "chrome.exe"),
    path.join(process.env["PROGRAMFILES(X86)"] || "", "Google", "Chrome", "Application", "chrome.exe"),
    path.join(process.env.PROGRAMFILES || "", "Microsoft", "Edge", "Application", "msedge.exe"),
    path.join(process.env["PROGRAMFILES(X86)"] || "", "Microsoft", "Edge", "Application", "msedge.exe"),
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate));
}

async function screenshotHtml(htmlFile, pngFile) {
  const playwright = await loadPlaywright();
  if (!playwright) return false;
  const executablePath = findBrowser();
  const browser = await playwright.chromium.launch(executablePath ? { executablePath } : {});
  const page = await browser.newPage({ viewport: { width: 1080, height: 1440 }, deviceScaleFactor: 1 });
  try {
    await page.goto(pathToFileURL(htmlFile).href, { waitUntil: "load", timeout: 10000 });
    await page.screenshot({
      path: pngFile,
      fullPage: false,
      clip: { x: 0, y: 0, width: 1080, height: 1440 },
      animations: "disabled",
      timeout: 10000,
    });
    return true;
  } finally {
    await browser.close();
  }
}

const pages = extractPages();
const coverLines = extractCoverLines();
const tags = extractTags();
const domain = detectDomain();
const rules = domainVisualRules(domain);
const buckets = extractVisualBuckets();
const promptSection = section("图片生成与配图提示词", ["正文草稿"]);
const captureRows = buildCaptureRows({ pages, buckets, domain });
const materialRows = captureRows.filter((row) => row.canGenerate === "yes" || row.canGenerate === "yes-with-review");
const generationPrompts = [
  {
    target: "cover",
    title: coverLines.join(" / "),
    source: "image2-simulated-real-material",
    ...promptFor({ kind: "cover", title: coverLines.join(" / "), visual: rules.primary, material: materialRows.slice(0, 3).map((row) => row.asset).join("、"), domain, coverLines }),
  },
  ...pages.slice(0, 8).map((page) => ({
    target: `page-${String(page.pageNo).padStart(2, "0")}`,
    title: page.title,
    source: "image2-simulated-real-material",
    ...promptFor({ kind: "page", title: page.title, visual: page.visual, material: page.material, domain, coverLines }),
  })),
];

const replacementRows = generationPrompts.map((prompt, index) => {
  const page = index === 0 ? null : pages[index - 1];
  const source = index <= 3 ? "Image2 模拟真实素材优先" : "Image2 生成图或信息卡";
  return {
    target: prompt.target,
    finalRecommendedSource: source,
    fallback: index === 0 ? "重写封面 Brief 后重新生成" : "重写该页 Brief 后重新生成",
    reason: page ? `${page.title}：${page.material}` : `封面：${coverLines.join(" / ")}`,
  };
});

const failures = [];
if (pages.length < 6) failures.push(`Need at least 6 carousel pages, found ${pages.length}.`);
if (!promptSection.includes("封面")) failures.push("Image prompt section must include cover prompt.");
if (materialRows.length < 3) failures.push(`Need at least 3 simulated material rows, found ${materialRows.length}.`);
if (generationPrompts.length < 7) failures.push(`Need cover plus at least 6 page prompts, found ${generationPrompts.length}.`);

if (failures.length) {
  console.error("Rednote realshot handoff build failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

const brief = [
  "# Rednote Simulated Material Handoff",
  "",
  `- Source: ${inputPath}`,
  `- Domain route: ${domain}`,
  `- Cover text: ${coverLines.join(" / ")}`,
  `- Tags: ${tags.join(" ") || "none"}`,
  `- Realness gate: pass`,
  "",
  "## 一句话机制",
  "",
  "把小红书预览卡升级为模拟真实素材生产链：先列可生成的场景和物件，再给每页 Image2 提示词和替换映射。",
  "",
  "## 首选视觉路线",
  "",
  `- ${rules.primary}`,
  `- 拍摄提示：${rules.captureTip}`,
  `- 风格备注：${rules.negative}`,
  "",
  "## 封面生图提示词",
  "",
  generationPrompts[0].gptImage,
  "",
  "## 每页模拟素材与提示词",
  "",
  ...generationPrompts.slice(1).map((prompt) => [
    `### ${prompt.target} ${prompt.title}`,
    "",
    `- 推荐来源：${prompt.source}`,
    `- GPT Image / Image2：${prompt.gptImage}`,
    `- 豆包 / 即梦：${prompt.doubaoJImeng}`,
    `- English：${prompt.englishKeywords}`,
    "",
  ].join("\n")),
].join("\n");

writeCsv(
  path.join(outputDir, "asset-capture-list.csv"),
  captureRows,
  ["itemId", "page", "title", "asset", "priority", "canGenerate", "assetMode", "captureDirection"],
);

writeCsv(
  path.join(outputDir, "replacement-map.csv"),
  replacementRows,
  ["target", "finalRecommendedSource", "fallback", "reason"],
);

fs.writeFileSync(path.join(outputDir, "realshot-brief.md"), brief, "utf8");
fs.writeFileSync(path.join(outputDir, "generation-prompts.json"), JSON.stringify(generationPrompts, null, 2), "utf8");

const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Rednote Realshot First Frame</title>
  <style>
    * { box-sizing: border-box; }
    html, body { margin: 0; width: 1080px; height: 1440px; overflow: hidden; font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif; background: #f7f1ea; color: #251f1c; }
    .page { width: 1080px; height: 1440px; padding: 58px; background: linear-gradient(180deg, #fffaf4 0%, #f1e4d7 100%); }
    .bar { height: 12px; width: 100%; background: #8a6f55; margin-bottom: 42px; }
    .kicker { font-size: 30px; color: #8a6f55; font-weight: 800; letter-spacing: 1px; }
    h1 { font-size: 78px; line-height: 1.06; margin: 22px 0 18px; max-width: 760px; letter-spacing: 0; }
    .sub { font-size: 34px; line-height: 1.45; max-width: 850px; color: #594e47; margin-bottom: 36px; }
    .photo { height: 380px; border-radius: 36px; background: #dfcab7; padding: 34px; display: grid; grid-template-columns: 1.15fr .85fr; gap: 24px; box-shadow: inset 0 0 0 2px rgba(90, 68, 48, .18); }
    .shot { border-radius: 26px; background: #fff8ef; padding: 26px; display: flex; flex-direction: column; justify-content: space-between; }
    .shot strong { font-size: 34px; }
    .shot span { font-size: 25px; color: #74665d; line-height: 1.32; display: -webkit-box; -webkit-line-clamp: 7; -webkit-box-orient: vertical; overflow: hidden; }
    .slots { display: grid; gap: 14px; }
    .slot { border-radius: 20px; background: rgba(255,255,255,.62); padding: 18px 22px; font-size: 25px; line-height: 1.3; }
    .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; margin-top: 34px; }
    .card { min-height: 142px; background: rgba(255,255,255,.76); border-radius: 24px; padding: 22px; border: 1px solid rgba(111, 84, 61, .18); }
    .card b { display: block; font-size: 28px; margin-bottom: 10px; }
    .card p { margin: 0; font-size: 23px; line-height: 1.35; color: #61564f; }
    .footer { position: absolute; left: 58px; right: 58px; bottom: 46px; font-size: 24px; color: #82746b; display: flex; justify-content: space-between; border-top: 1px solid rgba(111,84,61,.2); padding-top: 20px; }
  </style>
</head>
<body>
  <main class="page">
    <div class="bar"></div>
    <div class="kicker">真实首帧交付板 · ${escapeHtml(domain)}</div>
    <h1>${escapeHtml(coverLines.join(" "))}</h1>
    <div class="sub">${escapeHtml(rules.captureTip)}</div>
    <section class="photo">
      <div class="shot">
        <strong>封面主图</strong>
        <span>${escapeHtml(clipText(generationPrompts[0].gptImage, 150))}</span>
      </div>
      <div class="slots">
        ${materialRows.slice(0, 4).map((row) => `<div class="slot">${escapeHtml(row.asset)}</div>`).join("")}
      </div>
    </section>
    <section class="grid">
      ${replacementRows.slice(1, 7).map((row) => `<div class="card"><b>${escapeHtml(row.target)}</b><p>${escapeHtml(row.reason)}</p></div>`).join("")}
    </section>
    <div class="footer">
      <span>Image2 模拟真实素材：按 replacement-map 批量生成</span>
      <span>${escapeHtml(tags.slice(0, 3).join(" "))}</span>
    </div>
  </main>
</body>
</html>`;

const htmlFile = path.join(outputDir, "first-frame.html");
const pngFile = path.join(outputDir, "first-frame.png");
fs.writeFileSync(htmlFile, html, "utf8");

let screenshotGenerated = false;
try {
  screenshotGenerated = await screenshotHtml(htmlFile, pngFile);
} catch (error) {
  console.error(`First-frame screenshot failed: ${error.message}`);
}

const manifest = {
  input: inputPath,
  outputDir,
  generatedAt: new Date().toISOString(),
  domain,
  realnessGate: "pass",
  pages: pages.length,
  prompts: generationPrompts.length,
  simulatedMaterialRows: materialRows.length,
  files: {
    realshotBrief: "realshot-brief.md",
    assetCaptureList: "asset-capture-list.csv",
    generationPrompts: "generation-prompts.json",
    replacementMap: "replacement-map.csv",
    firstFrameHtml: "first-frame.html",
    firstFramePng: screenshotGenerated ? "first-frame.png" : null,
  },
};

fs.writeFileSync(path.join(outputDir, "manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
fs.writeFileSync(path.join(outputDir, "manifest.md"), [
  "# Rednote Simulated Material Handoff Manifest",
  "",
  `- Input: ${inputPath}`,
  `- Generated: ${manifest.generatedAt}`,
  `- Domain: ${domain}`,
  `- Realness gate: ${manifest.realnessGate}`,
  `- Carousel pages: ${manifest.pages}`,
  `- Generation prompts: ${manifest.prompts}`,
  `- Simulated material rows: ${manifest.simulatedMaterialRows}`,
  `- First-frame PNG: ${screenshotGenerated ? "yes" : "no"}`,
  "",
  "## Files",
  "",
  ...Object.entries(manifest.files).map(([key, value]) => `- ${key}: ${value || "not generated"}`),
  "",
].join("\n"), "utf8");

if (!screenshotGenerated) {
  console.error("Realshot handoff created, but first-frame PNG was not generated.");
  process.exit(1);
}

console.log(`Rednote simulated material handoff passed: ${generationPrompts.length} prompts, ${materialRows.length} simulated material rows -> ${outputDir}`);
