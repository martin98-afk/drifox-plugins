#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const imageArg = process.argv[2];
const captionArg = process.argv[3] || "选图先看3点";
const outputArg = process.argv[4];
const accountArg = process.argv[5] || "真实学习记录";
const peerCaptionArg = process.argv[6] || "同类笔记封面";
const peerMetaArg = process.argv[7] || "同类笔记";

if (!imageArg || !outputArg) {
  console.error("Usage: node scripts/build-rednote-image2-feed-test.mjs <image-path> <caption> <output-dir>");
  process.exit(2);
}

const imagePath = path.resolve(imageArg);
if (!fs.existsSync(imagePath)) {
  console.error(`Image not found: ${imagePath}`);
  process.exit(2);
}

const outputDir = path.resolve(outputArg);
fs.mkdirSync(outputDir, { recursive: true });

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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

const imageUrl = pathToFileURL(imagePath).href;
const caption = escapeHtml(captionArg);
const account = escapeHtml(accountArg);
const peerCaption = escapeHtml(peerCaptionArg);
const peerMeta = escapeHtml(peerMetaArg);
const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <style>
    *{box-sizing:border-box}
    html,body{margin:0;width:390px;height:844px;overflow:hidden;background:#f6f6f6;font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;color:#1f1f1f}
    .phone{padding:16px}
    .search{height:42px;border-radius:22px;background:#fff;margin-bottom:14px;box-shadow:0 1px 8px rgba(0,0,0,.04)}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    .post{background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 4px 18px rgba(0,0,0,.08)}
    .post img{display:block;width:100%;height:234px;object-fit:cover;background:#eee}
    .cap{padding:9px 10px 10px;font-size:13px;line-height:1.25;font-weight:700}
    .meta{padding:0 10px 10px;color:#8a8a8a;font-size:11px}
    .fake{height:234px;background:linear-gradient(135deg,#eaded6,#faf5ef);position:relative}
    .fake:after{content:"同赛道封面";position:absolute;left:18px;bottom:18px;font-size:16px;color:#7a6960}
  </style>
</head>
<body>
  <main class="phone">
    <div class="search"></div>
    <section class="grid">
      <article class="post">
        <img src="${imageUrl}" alt="image2 cover" />
        <div class="cap">${caption}</div>
        <div class="meta">${account}</div>
      </article>
      <article class="post">
        <div class="fake"></div>
        <div class="cap">${peerCaption}</div>
        <div class="meta">${peerMeta}</div>
      </article>
    </section>
  </main>
</body>
</html>`;

const htmlFile = path.join(outputDir, "image2-phone-feed-test.html");
const pngFile = path.join(outputDir, "image2-phone-feed-test.png");
fs.writeFileSync(htmlFile, html, "utf8");

const playwright = await loadPlaywright();
if (!playwright) {
  console.error("Playwright is required to render image2 phone feed test.");
  process.exit(1);
}

const executablePath = findBrowser();
const browser = await playwright.chromium.launch(executablePath ? { executablePath } : {});
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(htmlFile).href, { waitUntil: "load", timeout: 10000 });
  await page.screenshot({
    path: pngFile,
    fullPage: false,
    clip: { x: 0, y: 0, width: 390, height: 844 },
    animations: "disabled",
    timeout: 10000,
  });
  await page.close();
} finally {
  await browser.close();
}

const manifest = {
  image: imagePath,
  caption: captionArg,
  account: accountArg,
  peerCaption: peerCaptionArg,
  peerMeta: peerMetaArg,
  generatedAt: new Date().toISOString(),
  output: {
    html: htmlFile,
    png: pngFile,
    pngSize: fs.statSync(pngFile).size,
  },
  reviewGate: "Open image2-phone-feed-test.png at phone width. Pass only if the subject remains clear and the first 6-10 Chinese characters are readable without relying on empty poster space.",
};

fs.writeFileSync(path.join(outputDir, "manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
console.log(`Image2 phone feed test passed: ${pngFile}`);
