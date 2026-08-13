#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const input = process.argv[2];
const outputArg = process.argv[3];

if (!input || !outputArg) {
  console.error("Usage: node scripts/build-rednote-final-replacement-pack.mjs <output.md> <output-dir>");
  process.exit(2);
}

const inputPath = path.resolve(input);
if (!fs.existsSync(inputPath)) {
  console.error(`Output markdown not found: ${inputPath}`);
  process.exit(2);
}

const outputDir = path.resolve(outputArg);
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

function clean(value) {
  return String(value || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[#>*_|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function wrap(value, maxChars = 9, maxLines = 3) {
  const source = clean(value);
  const lines = [];
  let current = "";
  for (const char of source) {
    current += char;
    if (current.length >= maxChars || /[，。！？；:：]/.test(char)) {
      lines.push(current.trim());
      current = "";
    }
    if (lines.length >= maxLines) break;
  }
  if (current.trim() && lines.length < maxLines) lines.push(current.trim());
  return lines;
}

function extractCoverLines() {
  const cover = section("封面字", ["图文页脚本"]);
  const lines = cover
    .split(/\r?\n/)
    .map((line) => clean(line.replace(/^[-\d.、\s]+/, "")))
    .filter(Boolean)
    .filter((line) => !/^封面字|^方案|^备选|^##/.test(line));
  return lines.slice(0, 2).length ? lines.slice(0, 2) : ["真实素材先补齐", "再决定怎么发"];
}

function extractShortLine(block, label) {
  const match = block.match(new RegExp(`${label}[：:]\\s*([^\\n]+)`));
  return match ? clean(match[1]) : "";
}

function extractPages() {
  const script = section("图文页脚本", ["视觉类型判断"]);
  const parts = script.split(/(?:^|\n)第\s*(\d+)\s*页[^\n]*\n/g);
  const pages = [];
  for (let i = 1; i < parts.length; i += 2) {
    const pageNo = Number(parts[i]);
    const block = parts[i + 1] || "";
    pages.push({
      pageNo,
      title: extractShortLine(block, "页标题") || `第 ${pageNo} 页`,
      body: extractShortLine(block, "正文短句") || clean(block).slice(0, 70),
      visual: extractShortLine(block, "画面建议") || "真实桌面和手写清单",
      material: extractShortLine(block, "素材需求") || "待补真实素材",
    });
  }
  return pages;
}

function extractTags() {
  return section("标签建议", ["最终成品自检"]).match(/#[\p{L}\p{N}_-]+/gu) || [];
}

function detectDomain() {
  if (/美甲|甲片|穿戴甲|色卡|手模/.test(text)) return "beauty-nail";
  if (/Plog|plog|生活方式|日常|出租屋|桌搭/.test(text)) return "plog-life";
  if (/职场|老板|会议|项目|复盘|汇报|简历/.test(text)) return "workplace-knowledge";
  return "general-rednote";
}

function domainStyle(domain) {
  const styles = {
    "beauty-nail": {
      accent: "#d65d7a",
      paper: "#fff7f2",
      ink: "#281d21",
      soft: "#f4dce4",
      subject: "甲片色卡 / 手写预约单 / 小店桌面",
      objectA: "甲片色卡",
      objectB: "预约便签",
      objectC: "磨甲工具",
      truth: "靠甲片、色板、工具、手部视角和手写单建立真实感。",
    },
    "plog-life": {
      accent: "#8a6f55",
      paper: "#fbf2e7",
      ink: "#2c251f",
      soft: "#e7d1bd",
      subject: "手机随拍 / 桌面物件 / 生活痕迹",
      objectA: "杯子",
      objectB: "便签",
      objectC: "钥匙",
      truth: "保留不完美边角和真实物件，不做样板间滤镜。",
    },
    "workplace-knowledge": {
      accent: "#2f8f83",
      paper: "#f6f3ea",
      ink: "#141923",
      soft: "#dce9e4",
      subject: "办公桌面 / 手写框架 / 脱敏材料",
      objectA: "便签框架",
      objectB: "草稿纸",
      objectC: "电脑边角",
      truth: "用桌面材料、截图样式和手写框架表达观点。",
    },
    "general-rednote": {
      accent: "#c45b4a",
      paper: "#fff6ed",
      ink: "#251f1b",
      soft: "#efd8ca",
      subject: "真实桌面 / 主物件 / 手写清单",
      objectA: "主物件",
      objectB: "手写清单",
      objectC: "手机边角",
      truth: "先保证主物件清楚，再保留真实光线和轻微杂物。",
    },
  };
  return styles[domain] || styles["general-rednote"];
}

function domainLabel(domain, kind) {
  const labels = {
    "beauty-nail": kind === "cover" ? "美甲图文笔记" : "美甲内页",
    "plog-life": kind === "cover" ? "生活图文笔记" : "Plog 内页",
    "workplace-knowledge": kind === "cover" ? "职场图文笔记" : "职场内页",
    "general-rednote": kind === "cover" ? "小红书图文笔记" : "图文内页",
  };
  return labels[domain] || labels["general-rednote"];
}

function objectsFromText(value, style) {
  const parts = clean(value)
    .replace(/素材[：:]?/g, "")
    .split(/[、，,；;。]/)
    .map((item) => clean(item))
    .filter(Boolean)
    .filter((item) => item.length <= 8)
    .slice(0, 3);
  return [
    parts[0] || style.objectA,
    parts[1] || style.objectB,
    parts[2] || style.objectC,
  ];
}

function photoScene(style, variant = "cover", objects = null) {
  const top = variant === "cover" ? 210 : 170;
  const [objectA, objectB, objectC] = objects || [style.objectA, style.objectB, style.objectC];
  return `
    <div class="photo">
      <div class="object large">${escapeHtml(objectA)}</div>
      <div class="object note">${escapeHtml(objectB)}</div>
      <div class="object tool">${escapeHtml(objectC)}</div>
      <div class="shadow"></div>
      <div class="grain"></div>
    </div>
    <style>
      .photo{position:absolute;left:74px;top:${top}px;width:932px;height:${variant === "cover" ? 560 : 470}px;border-radius:42px;background:linear-gradient(135deg,${style.soft},#fffaf4 68%);overflow:hidden;box-shadow:inset 0 0 0 2px rgba(67,45,33,.15),0 22px 70px rgba(61,44,32,.12)}
      .object{position:absolute;border-radius:24px;background:rgba(255,255,255,.82);box-shadow:0 12px 32px rgba(74,51,35,.14);display:flex;align-items:center;justify-content:center;color:${style.ink};font-weight:700}
      .large{left:84px;top:98px;width:310px;height:260px;font-size:42px;transform:rotate(-4deg)}
      .note{right:92px;top:80px;width:310px;height:190px;font-size:34px;transform:rotate(3deg);background:#fff8dc}
      .tool{right:160px;bottom:70px;width:430px;height:82px;font-size:31px;border-radius:41px;background:${style.accent};color:white;transform:rotate(-2deg)}
      .shadow{position:absolute;left:130px;right:120px;bottom:64px;height:30px;border-radius:50%;background:rgba(84,57,38,.16);filter:blur(10px)}
      .grain{position:absolute;inset:0;background-image:radial-gradient(rgba(90,65,45,.11) 1px,transparent 1px);background-size:18px 18px;opacity:.45;mix-blend-mode:multiply}
    </style>`;
}

function baseHtml({ kind, title, subtitle, footnote, style, domain, pageNo, objects }) {
  const titleLines = wrap(title, kind === "cover" ? 8 : 12, kind === "cover" ? 3 : 2);
  const subLines = wrap(subtitle, 18, 4);
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(kind)} rednote final replacement</title>
  <style>
    *{box-sizing:border-box}html,body{margin:0;width:1080px;height:1440px;overflow:hidden;font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;color:${style.ink};background:${style.paper}}.page{position:relative;width:1080px;height:1440px;padding:62px;background:linear-gradient(180deg,${style.paper},#fff 58%,${style.paper})}.bar{height:12px;width:100%;background:${style.accent};border-radius:12px}.kicker{position:absolute;left:78px;top:110px;font-size:30px;color:${style.accent};font-weight:800;letter-spacing:1px}.title{position:absolute;left:82px;right:82px;top:${kind === "cover" ? 790 : 720}px}.title div{font-size:${kind === "cover" ? 92 : 70}px;line-height:1.03;font-weight:900;letter-spacing:0}.sub{position:absolute;left:86px;right:86px;top:${kind === "cover" ? 1065 : 930}px;font-size:34px;line-height:1.38;color:#584e48}.sub div{margin-bottom:10px}.truth{position:absolute;left:86px;right:86px;bottom:82px;padding:24px 28px;border-radius:28px;background:rgba(255,255,255,.72);font-size:27px;line-height:1.42;color:#5c514b}
  </style>
</head>
<body>
  <main class="page">
    <div class="bar"></div>
    <div class="kicker">${escapeHtml(domainLabel(domain, kind))}</div>
    ${photoScene(style, kind, objects)}
    <section class="title">${titleLines.map((line) => `<div>${escapeHtml(line)}</div>`).join("")}</section>
    <section class="sub">${subLines.map((line) => `<div>${escapeHtml(line)}</div>`).join("")}</section>
    <section class="truth">${escapeHtml(footnote || style.truth)}</section>
  </main>
</body>
</html>`;
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
  for (const root of roots) {
    const direct = requireFrom(path.join(root, "playwright-core", "package.json"), "playwright-core") || requireFrom(path.join(root, "playwright", "package.json"), "playwright");
    if (direct) return direct;
    const pnpmDir = path.join(root, ".pnpm");
    if (fs.existsSync(pnpmDir)) {
      for (const entry of fs.readdirSync(pnpmDir)) {
        if (entry.startsWith("playwright-core@")) {
          const loaded = requireFrom(path.join(pnpmDir, entry, "node_modules", "playwright-core", "package.json"), "playwright-core");
          if (loaded) return loaded;
        }
        if (entry.startsWith("playwright@")) {
          const loaded = requireFrom(path.join(pnpmDir, entry, "node_modules", "playwright", "package.json"), "playwright");
          if (loaded) return loaded;
        }
      }
    }
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

async function screenshotFile(browser, htmlFile, pngFile, viewport = { width: 1080, height: 1440 }) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  try {
    await page.goto(pathToFileURL(htmlFile).href, { waitUntil: "load", timeout: 10000 });
    await page.screenshot({
      path: pngFile,
      fullPage: false,
      clip: { x: 0, y: 0, width: viewport.width, height: viewport.height },
      animations: "disabled",
      timeout: 10000,
    });
  } finally {
    await page.close();
  }
}

const pages = extractPages();
const coverLines = extractCoverLines();
const tags = extractTags();
const domain = detectDomain();
const style = domainStyle(domain);
const outputs = [
  {
    id: "final-cover",
    kind: "cover",
    title: coverLines.join(" "),
    subtitle: style.subject,
    footnote: style.truth,
    objects: [style.objectA, style.objectB, style.objectC],
    pageNo: 0,
  },
  ...pages.slice(0, 2).map((page) => ({
    id: `final-page-${String(page.pageNo).padStart(2, "0")}`,
    kind: "page",
    title: page.title,
    subtitle: page.body,
    footnote: `素材：${page.material}`,
    objects: objectsFromText(`${page.material}、${page.visual}`, style),
    pageNo: page.pageNo,
  })),
];

const failures = [];
if (pages.length < 2) failures.push(`Need at least 2 pages to build replacement pack, found ${pages.length}.`);
if (!section("视觉类型判断", ["图片生成与配图提示词"])) failures.push("Missing visual strategy section.");
if (!section("图片生成与配图提示词", ["正文草稿"])) failures.push("Missing image prompt section.");
if (coverLines.join("").length > 24) failures.push("Cover text is too long for a thumbnail-first final image.");

if (failures.length) {
  console.error("Rednote final replacement pack failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

const playwright = await loadPlaywright();
if (!playwright) {
  console.error("Playwright is required to render final replacement PNG files.");
  process.exit(1);
}

const executablePath = findBrowser();
const browser = await playwright.chromium.launch(executablePath ? { executablePath } : {});
const rendered = [];

try {
  for (const item of outputs) {
    const html = baseHtml({ ...item, style, domain });
    const htmlFile = path.join(outputDir, `${item.id}.html`);
    const pngFile = path.join(outputDir, `${item.id}.png`);
    fs.writeFileSync(htmlFile, html, "utf8");
    await screenshotFile(browser, htmlFile, pngFile);
    rendered.push({ ...item, html: path.basename(htmlFile), png: path.basename(pngFile), pngSize: fs.statSync(pngFile).size });
  }

  const coverPng = pathToFileURL(path.join(outputDir, "final-cover.png")).href;
  const feedHtml = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/><style>
html,body{margin:0;width:390px;height:844px;overflow:hidden;background:#f6f6f6;font-family:"Microsoft YaHei",Arial,sans-serif}.phone{padding:18px}.search{height:42px;border-radius:21px;background:white;margin-bottom:16px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.post{background:white;border-radius:14px;overflow:hidden;box-shadow:0 4px 18px rgba(0,0,0,.08)}.post img{display:block;width:100%;height:238px;object-fit:cover}.cap{padding:9px 10px;font-size:13px;line-height:1.25;color:#1f1f1f}.post.small{opacity:.62}.post.small .fake{height:238px;background:linear-gradient(135deg,#ddd,#f7eee6)}</style></head><body>
<main class="phone"><div class="search"></div><section class="grid"><article class="post"><img src="${coverPng}"/><div class="cap">${escapeHtml(coverLines[0] || "真实素材")}</div></article><article class="post small"><div class="fake"></div><div class="cap">同类笔记缩略图</div></article></section></main>
</body></html>`;
  const feedHtmlFile = path.join(outputDir, "phone-feed-test.html");
  const feedPngFile = path.join(outputDir, "phone-feed-test.png");
  fs.writeFileSync(feedHtmlFile, feedHtml, "utf8");
  await screenshotFile(browser, feedHtmlFile, feedPngFile, { width: 390, height: 844 });
  rendered.push({ id: "phone-feed-test", kind: "thumbnail-test", html: "phone-feed-test.html", png: "phone-feed-test.png", pngSize: fs.statSync(feedPngFile).size });
} finally {
  await browser.close();
}

const manifest = {
  input: inputPath,
  generatedAt: new Date().toISOString(),
  domain,
  aspectRatio: "3:4",
  purpose: "final replacement simulation for cover plus first two inner pages",
  boundary: "These images are publish-simulation replacements made from non-customer objects and page copy. They are not real customer photos, screenshots, backend records, or performance proof.",
  thumbnailGate: coverLines.join("").length <= 24 ? "pass" : "review",
  rendered,
  tags,
};

fs.writeFileSync(path.join(outputDir, "manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
fs.writeFileSync(path.join(outputDir, "manifest.md"), [
  "# Rednote Final Replacement Pack Manifest",
  "",
  `- Input: ${inputPath}`,
  `- Generated: ${manifest.generatedAt}`,
  `- Domain: ${domain}`,
  `- Aspect ratio: ${manifest.aspectRatio}`,
  `- Thumbnail gate: ${manifest.thumbnailGate}`,
  `- Boundary: ${manifest.boundary}`,
  "",
  "## Rendered Files",
  "",
  ...rendered.map((item) => `- ${item.id}: ${item.png} (${item.pngSize} bytes)`),
  "",
  "## Manual Review Notes",
  "",
  "- Check final-cover.png at phone-feed-test.png scale before publishing.",
  "- Replace with real uploaded photos when the user has stronger material.",
  "- Do not use this pack as proof of real customer feedback, sales, results, or platform performance.",
  "",
].join("\n"), "utf8");

console.log(`Rednote final replacement pack passed: ${rendered.length} PNG files -> ${outputDir}`);
