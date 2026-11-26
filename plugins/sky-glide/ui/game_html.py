# -*- coding: utf-8 -*-
"""sky-glide 游戏文档 —— 单文件 HTML（canvas 版 Flappy，无限刷分）

欢迎卡片 tab 走 markdown → CodeWebViewer(innerHTML) 管线，注入的 `<script>`
不会执行，因此整份游戏文档塞进 `<iframe srcdoc>`：iframe 是独立文档，
脚本自行执行，键盘事件也落在自己 window 上。

对外只暴露 build_doc(is_dark) -> str：
- is_dark 由 render_func 的 ctx["is_dark"] 传入，切换两套调色板
- 文档内零外部资源（无字体/CDN/图片），断网可用

手感参数集中在 JS 顶部常量区，改数值即可调难度。
"""

import re

_BLANK_LINE = re.compile(r"\n[ \t]*\n+")

_DOC = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; background: #0b1116; }
  body { display: flex; align-items: center; justify-content: center; }
  canvas { display: block; touch-action: none; }
</style>
</head>
<body>
<canvas id="g"></canvas>
<script>
(function () {
  "use strict";

  var DARK = __DARK__;

  // ── 调色板 ───────────────────────────────────────────────
  var PAL = DARK ? {
    sky0: "#101c26", sky1: "#1b2f3d", cloud: "#22323f",
    hill: "#1f3542", hill2: "#17272f", pipe: "#3f9c6a", pipeHi: "#5cc189",
    pipeCap: "#2f7a52", capHi: "#4bab74",
    ground: "#241f19", groundTop: "#3a3229", groundLine: "#4d4234",
    bird: "#f2c14e", belly: "#ffe6a3", wing: "#c98f22", beak: "#e8833a",
    eye: "#16202b", text: "#e8f0f5", shadow: "rgba(8,14,19,.75)", panel: "rgba(12,20,26,.82)"
  } : {
    sky0: "#cfeafc", sky1: "#f4fbff", cloud: "#ffffff",
    hill: "#a9ddc6", hill2: "#8ecfb4", pipe: "#4fbd7c", pipeHi: "#7ed9a2",
    pipeCap: "#3fa96a", capHi: "#68cc8c",
    ground: "#e2d3b0", groundTop: "#f0e4c6", groundLine: "#c9b78e",
    bird: "#ffc846", belly: "#fff0bd", wing: "#d9982a", beak: "#f08a3c",
    eye: "#20303c", text: "#22384a", shadow: "rgba(255,255,255,.75)", panel: "rgba(255,255,255,.9)"
  };

  // ── 手感参数（改这里调难度）──────────────────────────────
  var W = 480, H = 270;          // 逻辑分辨率 16:9
  var GROUND = 34;               // 地面高度
  var PW = 50;                   // 管道宽度
  var GAP = 116;                 // 上下管道缝隙
  var SPACING = 190;             // 相邻管道间距
  var VX = 2.05;                 // 管道横向速度（px/帧）
  var G = 0.42;                  // 重力加速度（px/帧²）
  var FLAP = -6.1;               // 拍翼瞬时速度
  var BX = 112, BR = 10;         // 鸟的横坐标与半径

  var cv = document.getElementById("g");
  var ctx = cv.getContext("2d");
  // 画布按 16:9 letterbox：不管 iframe 实际多宽多高，画面永远是横屏，
  // 富余部分用天空色补边（防止宿主把卡片容器拉成方形）
  function fit() {
    var vw = window.innerWidth || W, vh = window.innerHeight || H;
    var s = Math.min(vw / W, vh / H);
    if (!(s > 0)) s = 1;
    var cw = Math.max(1, Math.round(W * s)), ch = Math.max(1, Math.round(H * s));
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.style.width = cw + "px";
    cv.style.height = ch + "px";
    cv.width = Math.round(cw * dpr);
    cv.height = Math.round(ch * dpr);
    ctx.setTransform(cv.width / W, 0, 0, cv.height / H, 0, 0);
  }
  fit();
  document.body.style.background = "#0b1116";
  window.addEventListener("resize", fit);
  window.addEventListener("load", fit);

  var bird, pipes, clouds, score, state, tick, wingT, best, paused = false;

  best = 0;
  try { best = parseInt(localStorage.getItem("skyglide.best") || "0", 10) || 0; } catch (e) { best = 0; }

  function rnd(a, b) { return a + Math.random() * (b - a); }

  function makePipe(x) {
    var top = rnd(26, H - GROUND - GAP - 30);
    return { x: x, top: top, gap: GAP, passed: false };
  }

  function reset() {
    bird = { y: H * 0.44, vy: 0, rot: 0 };
    pipes = [];
    clouds = [];
    score = 0;
    state = "ready";
    tick = 0;
    wingT = 0;
    // 首根管道完整出现在屏幕右侧，ready 态就能一眼看出玩法
    var x = W - 56;
    for (var i = 0; i < 3; i++) { pipes.push(makePipe(x)); x += SPACING; }
    for (var j = 0; j < 4; j++) {
      clouds.push({ x: rnd(0, W), y: rnd(14, 118), s: rnd(0.55, 1.15), v: rnd(0.10, 0.26) });
    }
  }

  function flap() {
    wingT = 1;
    if (state === "dead") {
      reset();
      state = "playing";
      bird.vy = FLAP;
      return;
    }
    if (state === "ready") state = "playing";
    bird.vy = FLAP;
  }

  function die() {
    if (state !== "playing") return;
    state = "dead";
    if (score > best) {
      best = score;
      try { localStorage.setItem("skyglide.best", String(best)); } catch (e) { /* 隐私模式忽略 */ }
    }
  }

  function hitRect(x, y, w, h) {
    return x < BX + 8 && x + w > BX - 8 && y < bird.y + 7 && y + h > bird.y - 7;
  }

  function update() {
    tick++;
    var i, c;
    for (i = 0; i < clouds.length; i++) {
      c = clouds[i];
      c.x -= c.v * (state === "playing" ? 1.6 : 1);
      if (c.x < -46) { c.x = W + 26; c.y = rnd(12, 116); }
    }

    if (state === "ready") {
      bird.y = H * 0.44 + Math.sin(tick * 0.075) * 6;
      bird.rot = 0;
      return;
    }

    bird.vy += G;
    bird.y += bird.vy;
    bird.rot = Math.max(-0.45, Math.min(1.35, bird.vy * 0.075));

    if (state === "dead") {
      if (bird.y + BR > H - GROUND) { bird.y = H - GROUND - BR; bird.vy = 0; }
      return;
    }

    for (i = 0; i < pipes.length; i++) {
      pipes[i].x -= VX;
      if (!pipes[i].passed && pipes[i].x + PW < BX - 7) {
        pipes[i].passed = true;
        score++;
      }
    }
    if (pipes.length && pipes[0].x + PW < -12) {
      pipes.shift();
      pipes.push(makePipe(pipes[pipes.length - 1].x + SPACING));
    }

    if (bird.y - BR <= 0) { bird.y = BR; bird.vy = 0; }
    if (bird.y + BR >= H - GROUND) { bird.y = H - GROUND - BR; die(); return; }

    for (i = 0; i < pipes.length; i++) {
      var p = pipes[i];
      if (p.x > BX + 10 || p.x + PW < BX - 10) continue;
      if (hitRect(p.x, 0, PW, p.top) || hitRect(p.x, p.top + p.gap, PW, H - GROUND - p.top - p.gap)) {
        die();
        return;
      }
    }
  }

  // ── 绘制 ────────────────────────────────────────────────
  function drawSky() {
    var g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, PAL.sky0);
    g.addColorStop(1, PAL.sky1);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  function drawCloud(c) {
    ctx.fillStyle = PAL.cloud;
    ctx.globalAlpha = 0.85;
    ctx.beginPath();
    ctx.arc(c.x, c.y, 13 * c.s, 0, Math.PI * 2);
    ctx.arc(c.x + 15 * c.s, c.y + 3 * c.s, 10 * c.s, 0, Math.PI * 2);
    ctx.arc(c.x - 15 * c.s, c.y + 4 * c.s, 8 * c.s, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  function hillBand(color, offset, amp, phase) {
    var base = H - GROUND;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(0, base);
    for (var x = 0; x <= W; x += 4) {
      var y = base - offset - Math.sin((x + tick * 0.12) * 0.011 + phase) * amp - Math.sin(x * 0.031 + phase) * (amp * 0.45);
      ctx.lineTo(x, y);
    }
    ctx.lineTo(W, base);
    ctx.closePath();
    ctx.fill();
  }

  function drawHills() {
    hillBand(PAL.hill, 24, 15, 0);
    hillBand(PAL.hill2, 10, 10, 2.2);
  }

  function pipeBodies(p) {
    var botY = p.top + p.gap;
    ctx.fillStyle = PAL.pipe;
    ctx.fillRect(p.x, 0, PW, p.top);
    ctx.fillRect(p.x, botY, PW, H - GROUND - botY);

    ctx.fillStyle = PAL.pipeHi;
    ctx.fillRect(p.x + 6, 0, 5, p.top);
    ctx.fillRect(p.x + 6, botY, 5, H - GROUND - botY);
  }

  function pipeCaps(p) {
    var botY = p.top + p.gap;
    var cw = PW + 10, cx = p.x - 5, ch = 13;
    ctx.fillStyle = PAL.pipeCap;
    ctx.fillRect(cx, p.top - ch, cw, ch);
    ctx.fillRect(cx, botY, cw, ch);
    ctx.fillStyle = PAL.capHi;
    ctx.fillRect(cx + 7, p.top - ch + 2, 5, ch - 4);
    ctx.fillRect(cx + 7, botY + 2, 5, ch - 4);
  }

  function drawPipes() {
    for (var i = 0; i < pipes.length; i++) pipeBodies(pipes[i]);
    for (var j = 0; j < pipes.length; j++) pipeCaps(pipes[j]);
  }

  function drawGround() {
    var y = H - GROUND;
    ctx.fillStyle = PAL.groundTop;
    ctx.fillRect(0, y, W, 5);
    ctx.fillStyle = PAL.ground;
    ctx.fillRect(0, y + 5, W, GROUND - 5);
    ctx.fillStyle = PAL.groundLine;
    var off = (tick * VX) % 24;
    for (var x = -24; x < W + 24; x += 24) {
      ctx.fillRect(x - off, y + 10, 12, 3);
      ctx.fillRect(x - off + 6, y + 19, 12, 3);
    }
  }

  function drawBird() {
    var flapPhase = state === "ready" ? Math.sin(tick * 0.22) : Math.sin(tick * 0.42) * (wingT > 0 ? 1 : 0.35);
    if (wingT > 0) wingT -= 0.06;

    ctx.save();
    ctx.translate(BX, bird.y);
    ctx.rotate(bird.rot);

    // 身体
    ctx.fillStyle = PAL.bird;
    ctx.beginPath();
    ctx.ellipse(0, 0, 12.6, 10.4, 0, 0, Math.PI * 2);
    ctx.fill();
    // 肚皮
    ctx.fillStyle = PAL.belly;
    ctx.beginPath();
    ctx.ellipse(-0.6, 3.6, 8.2, 5.8, 0, 0, Math.PI * 2);
    ctx.fill();
    // 翅膀
    ctx.fillStyle = PAL.wing;
    ctx.beginPath();
    ctx.ellipse(-2.4, 1.2 + flapPhase * 3.8, 7.2, 4.8, flapPhase * 0.35, 0, Math.PI * 2);
    ctx.fill();
    // 眼白 + 瞳孔
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(5.8, -4, 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = PAL.eye;
    ctx.beginPath();
    ctx.arc(7, -4, 1.7, 0, Math.PI * 2);
    ctx.fill();
    // 喙
    ctx.fillStyle = PAL.beak;
    ctx.beginPath();
    ctx.moveTo(10.8, 0.4);
    ctx.lineTo(18.6, 2.6);
    ctx.lineTo(10.6, 5.4);
    ctx.closePath();
    ctx.fill();

    ctx.restore();
  }

  function text(str, x, y, size, align, color) {
    ctx.font = "700 " + size + "px -apple-system, 'PingFang SC', 'Helvetica Neue', monospace";
    ctx.textAlign = align || "center";
    ctx.textBaseline = "middle";
    ctx.lineWidth = Math.max(1.2, size * 0.075);
    ctx.strokeStyle = PAL.shadow;
    ctx.strokeText(str, x, y);
    ctx.fillStyle = color || PAL.text;
    ctx.fillText(str, x, y);
  }

  function drawHud() {
    if (state === "ready") {
      text("按 空格 起飞", W / 2, H * 0.24, 17, "center", PAL.text);
      text("空格 / 点击 扇动翅膀", W / 2, H * 0.24 + 24, 12, "center", PAL.text);
      return;
    }
    text(String(score), W / 2, 44, 40);

    if (state === "dead") {
      var pw = 244, ph = 118, px = (W - pw) / 2, py = (H - ph) / 2 - 6;
      ctx.fillStyle = PAL.panel;
      roundRect(px, py, pw, ph, 14);
      ctx.fill();
      text("撞了", W / 2, py + 26, 17);
      text("得分 " + score + "   最高 " + best, W / 2, py + 56, 15);
      text("空格 / 点击 重来", W / 2, py + 86, 13);
    }
  }

  function roundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  function draw() {
    drawSky();
    for (var i = 0; i < clouds.length; i++) drawCloud(clouds[i]);
    drawHills();
    drawPipes();
    drawGround();
    drawBird();
    drawHud();
  }

  // ── 主循环（固定步长，刷新率无关）────────────────────────
  var last = 0, acc = 0, STEP = 1000 / 60, paused = false;
  function loop(t) {
    if (!last) last = t;
    var dt = t - last;
    last = t;
    if (dt > 100) dt = 100;
    if (!paused) {
      acc += dt;
      while (acc >= STEP) { update(); acc -= STEP; }
    }
    draw();
    requestAnimationFrame(loop);
  }

  // ── 输入 ────────────────────────────────────────────────
  function onKey(e) {
    var k = e.keyCode;
    if (k === 32 || k === 38 || k === 87) {
      e.preventDefault();
      if (e.repeat) return;
      flap();
    }
  }
  window.addEventListener("keydown", onKey, { passive: false });
  cv.addEventListener("mousedown", function (e) { e.preventDefault(); flap(); });
  cv.addEventListener("touchstart", function (e) { e.preventDefault(); flap(); }, { passive: false });
  // 失焦不改判死（切 tab/点别处太常见），冻结物理等焦点回来
  window.addEventListener("blur", function () { paused = true; });
  window.addEventListener("focus", function () { paused = false; });

  reset();
  requestAnimationFrame(loop);
  try { window.focus(); } catch (e) { /* 自动聚焦可能被拦，点击后自然获得 */ }
})();
</script>
</body>
</html>
"""


def build_doc(is_dark: bool) -> str:
    """返回完整游戏 HTML 文档，is_dark 决定调色板

    顺便压掉空行：整份文档最终会进 markdown 渲染，而 CommonMark 的 HTML block
    遇空行即终止，把后面的转义文本当普通 markdown 处理，iframe 标签会被截断。
    单换行保留，属性值跨行合法，也不影响 JS。
    """
    doc = _DOC.replace("__DARK__", "true" if is_dark else "false")
    return _BLANK_LINE.sub("\n", doc)