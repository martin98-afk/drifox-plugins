#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const input = process.argv[2];
const outputArg = process.argv[3];

if (!input) {
  console.error("Usage: node scripts/build-rednote-visual-pack.mjs <output.md> [output-dir]");
  process.exit(2);
}

const inputPath = path.resolve(input);
if (!fs.existsSync(inputPath)) {
  console.error(`Output markdown not found: ${inputPath}`);
  process.exit(2);
}

const outputDir = path.resolve(outputArg || path.join(process.cwd(), "rednote-visual-pack"));
const cardsDir = path.join(outputDir, "cards");
fs.mkdirSync(cardsDir, { recursive: true });

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
  return value
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[#>*_|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function escapeXml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function wrapText(value, maxChars = 15, maxLines = 4) {
  const explicitLines = String(value)
    .split(/\r?\n/)
    .map((line) => cleanMarkdown(line))
    .filter(Boolean);
  if (explicitLines.length > 1) return explicitLines.slice(0, maxLines);

  const cleaned = cleanMarkdown(value);
  const chunks = [];
  let current = "";
  for (const char of cleaned) {
    current += char;
    if (current.length >= maxChars || /[，。！？；:：]/.test(char)) {
      chunks.push(current.trim());
      current = "";
    }
    if (chunks.length >= maxLines) break;
  }
  if (current.trim() && chunks.length < maxLines) chunks.push(current.trim());
  return chunks.slice(0, maxLines);
}

function extractCoverLines() {
  const cover = section("封面字", ["图文页脚本"]);
  const lines = cover
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !/^##|^方案|^\d+[.、]/.test(line));
  const picked = lines.slice(0, 2);
  return picked.length ? picked : ["这篇和你有关", "先看真实素材"];
}

function extractTags() {
  const tagText = section("标签建议", ["最终成品自检"]);
  return tagText.match(/#[\p{L}\p{N}_-]+/gu) || [];
}

function extractBody() {
  const body = section("正文草稿", ["评论与私信承接"]);
  return body.replace(/^## 正文草稿/m, "").trim();
}

function extractShortLine(block, label) {
  const match = block.match(new RegExp(`${label}[：:]\\s*([^\\n]+)`));
  return match ? match[1].trim() : "";
}

function extractPages() {
  const script = section("图文页脚本", ["视觉类型判断"]);
  const parts = script.split(/(?:^|\n)第\s*(\d+)\s*页[^\n]*\n/g);
  const pages = [];
  for (let i = 1; i < parts.length; i += 2) {
    const pageNo = Number(parts[i]);
    const block = parts[i + 1] || "";
    const title = extractShortLine(block, "页标题") || `第 ${pageNo} 页`;
    const body = extractShortLine(block, "正文短句") || cleanMarkdown(block).slice(0, 60);
    const visual = extractShortLine(block, "画面建议") || "按视觉类型判断生成真实感内页";
    const material = extractShortLine(block, "素材需求") || "待补素材";
    pages.push({ pageNo, title, body, visual, material });
  }
  return pages;
}

function extractMaterialGaps() {
  const source = [
    section("真人细节补位", ["选题角度"]),
    section("视觉类型判断", ["图片生成与配图提示词"]),
    section("最终成品自检", []),
  ].join("\n");
  return source
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => /待补|素材|场景|物件|截图|人物|真实感/.test(line))
    .slice(0, 20)
    .map(cleanMarkdown);
}

function svgCard({ kind, pageNo, title, subtitle, footnote, accent = "#d9486e", theme = "knowledge" }) {
  const isPlog = theme === "plog";
  const titleLines = wrapText(title, kind === "cover" ? 10 : 14, kind === "cover" ? 4 : 3);
  const subLines = wrapText(subtitle, 17, 5);
  const footLines = wrapText(footnote, 19, 3);
  const titleY = isPlog && kind === "cover" ? 760 : kind === "cover" ? 360 : 300;
  const titleSize = kind === "cover" ? (isPlog ? 68 : 80) : 70;
  const bg = isPlog ? "#f5efe6" : kind === "cover" ? "#f9f3ed" : "#fffaf4";
  const ink = isPlog ? "#2f261f" : "#27211d";
  const panelFill = isPlog ? "#fff9f0" : "#ffffff";
  const softBlock = isPlog ? "#e8d7c6" : "#f4e7dc";
  const label = isPlog ? (kind === "cover" ? "PLOG / 小红书图文包" : `PLOG ${String(pageNo).padStart(2, "0")}`) : kind === "cover" ? "COVER / 小红书图文包" : `P${String(pageNo).padStart(2, "0")} / 小红书图文包`;

  const textNodes = [];
  titleLines.forEach((line, index) => {
    textNodes.push(`<text x="92" y="${titleY + index * (titleSize + 16)}" font-size="${titleSize}" font-weight="800" fill="${ink}">${escapeXml(line)}</text>`);
  });
  const subStartY = isPlog && kind === "cover" ? 965 : 780;
  subLines.forEach((line, index) => {
    textNodes.push(`<text x="98" y="${subStartY + index * 54}" font-size="38" fill="#4e4540">${escapeXml(line)}</text>`);
  });
  footLines.forEach((line, index) => {
    textNodes.push(`<text x="98" y="${1240 + index * 40}" font-size="28" fill="#7b716a">${escapeXml(line)}</text>`);
  });

  const visualBlock = isPlog
    ? `<rect x="88" y="180" width="904" height="${kind === "cover" ? 470 : 300}" rx="38" fill="${softBlock}"/>
  <rect x="132" y="${kind === "cover" ? 500 : 390}" width="760" height="26" rx="13" fill="#7a6654" opacity="0.32"/>
  <rect x="190" y="${kind === "cover" ? 290 : 250}" width="180" height="190" rx="16" fill="#c7b49f"/>
  <rect x="405" y="${kind === "cover" ? 260 : 230}" width="240" height="44" rx="10" fill="#ab8d72"/>
  <rect x="405" y="${kind === "cover" ? 326 : 296}" width="210" height="44" rx="10" fill="#d6c3af"/>
  <circle cx="785" cy="${kind === "cover" ? 340 : 290}" r="58" fill="#f7efe6"/>
  <path d="M720 ${kind === "cover" ? 510 : 410} C770 ${kind === "cover" ? 455 : 365}, 830 ${kind === "cover" ? 455 : 365}, 878 ${kind === "cover" ? 510 : 410}" fill="none" stroke="#8e725b" stroke-width="12" stroke-linecap="round" opacity="0.42"/>`
    : `<circle cx="930" cy="220" r="102" fill="${accent}" opacity="0.16"/>
  <circle cx="870" cy="275" r="44" fill="#f2b8a8" opacity="0.35"/>`;

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">
  <rect width="1080" height="1440" fill="${bg}"/>
  <rect x="38" y="38" width="1004" height="1364" rx="42" fill="${panelFill}" opacity="${isPlog ? "0.72" : "0.62"}"/>
  <rect x="74" y="82" width="932" height="10" fill="${accent}"/>
  ${visualBlock}
  <rect x="86" y="1010" width="904" height="150" rx="26" fill="${softBlock}"/>
  <text x="92" y="190" font-size="30" font-weight="700" fill="${accent}" letter-spacing="2">${label}</text>
  ${textNodes.join("\n  ")}
  <text x="92" y="1360" font-size="25" fill="#978b83">3:4 vertical · preview card · replace with real photos when available</text>
</svg>`;
}

function writeCard(name, content) {
  const file = path.join(cardsDir, name);
  fs.writeFileSync(file, content, "utf8");
  return file;
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
      // Try bundled runtime locations below.
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

async function rasterize(svgFiles) {
  const playwright = await loadPlaywright();
  if (!playwright) return [];
  const executablePath = findBrowser();
  const browser = await playwright.chromium.launch(executablePath ? { executablePath } : {});
  const page = await browser.newPage({ viewport: { width: 1080, height: 1440 }, deviceScaleFactor: 1 });
  const pngFiles = [];
  try {
    for (const svgFile of svgFiles) {
      const svg = fs.readFileSync(svgFile, "utf8");
      await page.setContent(
        `<html><head><style>html,body{margin:0;width:1080px;height:1440px;overflow:hidden;background:#fff;}svg{display:block;width:1080px;height:1440px;}</style></head><body>${svg}</body></html>`,
        { waitUntil: "load" },
      );
      const pngFile = svgFile.replace(/\.svg$/i, ".png");
      await page.screenshot({
        path: pngFile,
        fullPage: false,
        clip: { x: 0, y: 0, width: 1080, height: 1440 },
        animations: "disabled",
        timeout: 10000,
      });
      pngFiles.push(pngFile);
    }
  } finally {
    await browser.close();
  }
  return pngFiles;
}

const coverLines = extractCoverLines();
const pages = extractPages();
const tags = extractTags();
const body = extractBody();
const materialGaps = extractMaterialGaps();
const visualText = section("视觉类型判断", ["图片生成与配图提示词"]);
const theme = /Plog|生活方式|出租屋|租房|书桌|桌搭/.test(visualText + text) ? "plog" : "knowledge";
const coverAccent = theme === "plog" ? "#8a6f55" : "#d9486e";

const failures = [];
if (pages.length < 6) failures.push(`Need at least 6 visual pages, found ${pages.length}.`);
if (!section("视觉类型判断", ["图片生成与配图提示词"]).includes("3:4")) failures.push("Visual strategy must mention 3:4.");
if (!section("图片生成与配图提示词", ["正文草稿"]).includes("封面")) failures.push("Image prompt section must include cover prompt.");
if (tags.length < 3) failures.push("Need at least 3 tags.");
if (!body) failures.push("Missing body draft.");

if (failures.length) {
  console.error("Rednote visual pack build failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

const svgFiles = [];
svgFiles.push(writeCard("cover.svg", svgCard({
  kind: "cover",
  title: coverLines.slice(0, 2).join("\n"),
  subtitle: "发布前替换为实拍或已确认图片。",
  footnote: tags.slice(0, 3).join(" "),
  accent: coverAccent,
  theme,
})));

for (const item of pages.slice(0, 8)) {
  svgFiles.push(writeCard(`page-${String(item.pageNo).padStart(2, "0")}.svg`, svgCard({
    kind: "page",
    pageNo: item.pageNo,
    title: item.title,
    subtitle: item.body,
    footnote: item.visual,
    accent: theme === "plog" ? (item.pageNo % 2 === 0 ? "#6f8a63" : "#8a6f55") : item.pageNo % 2 === 0 ? "#4f8f78" : "#d9486e",
    theme,
  })));
}

let pngFiles = [];
try {
  pngFiles = await rasterize(svgFiles);
} catch (error) {
  console.error(`PNG rasterization failed: ${error.message}`);
}

const publishBrief = [
  "# Rednote Publish Brief",
  "",
  `- Source: ${inputPath}`,
  `- Cards: ${svgFiles.length} SVG, ${pngFiles.length} PNG`,
  "- Aspect ratio: 3:4",
  `- Tags: ${tags.join(" ")}`,
  "",
  "## Cover Lines",
  "",
  ...coverLines.map((line) => `- ${line}`),
  "",
  "## Carousel Pages",
  "",
  ...pages.map((item) => `- P${String(item.pageNo).padStart(2, "0")}: ${item.title} -> ${item.body}`),
  "",
  "## Material Gaps",
  "",
  ...(materialGaps.length ? materialGaps.map((line) => `- ${line}`) : ["- No explicit material gaps detected."]),
  "",
  "## Body Draft",
  "",
  body,
  "",
].join("\n");

fs.writeFileSync(path.join(outputDir, "publish-brief.md"), publishBrief, "utf8");

const manifest = {
  input: inputPath,
  outputDir,
  generatedAt: new Date().toISOString(),
  aspectRatio: "3:4",
  theme,
  cardCount: svgFiles.length,
  svgFiles: svgFiles.map((file) => path.relative(outputDir, file)),
  pngFiles: pngFiles.map((file) => path.relative(outputDir, file)),
  tags,
  materialGaps,
};

fs.writeFileSync(path.join(outputDir, "manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
fs.writeFileSync(path.join(outputDir, "manifest.md"), [
  "# Rednote Visual Pack Manifest",
  "",
  `- Input: ${inputPath}`,
  `- Generated: ${manifest.generatedAt}`,
  `- Aspect ratio: ${manifest.aspectRatio}`,
  `- Theme: ${manifest.theme}`,
  `- SVG cards: ${svgFiles.length}`,
  `- PNG cards: ${pngFiles.length}`,
  `- Tags: ${tags.join(" ")}`,
  "",
  "## SVG Files",
  "",
  ...manifest.svgFiles.map((file) => `- ${file}`),
  "",
  "## PNG Files",
  "",
  ...(manifest.pngFiles.length ? manifest.pngFiles.map((file) => `- ${file}`) : ["- PNG rasterization unavailable in this environment."]),
  "",
  "## Material Gaps",
  "",
  ...(materialGaps.length ? materialGaps.map((line) => `- ${line}`) : ["- No explicit material gaps detected."]),
  "",
].join("\n"), "utf8");

if (pngFiles.length !== svgFiles.length) {
  console.error(`Visual pack created, but only ${pngFiles.length}/${svgFiles.length} PNG cards were generated.`);
  process.exit(1);
}

console.log(`Rednote visual pack passed: ${svgFiles.length} SVG cards, ${pngFiles.length} PNG cards -> ${outputDir}`);
