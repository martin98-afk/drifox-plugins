# -*- coding: utf-8 -*-
"""sky-glide 游戏文档 —— 单文件 HTML（canvas 版 Flappy，无限刷分）

欢迎卡片 tab 走 markdown → CodeWebViewer(innerHTML) 管线，注入的 `<script>`
不会执行，因此整份游戏文档塞进 `<iframe srcdoc>`：iframe 是独立文档，
脚本自行执行，键盘事件也落在自己 window 上。

对外只暴露 build_doc(is_dark) -> str：
- is_dark 由 render_func 的 ctx["is_dark"] 传入，切换两套调色板
- 文档内零外部资源（无字体/CDN/图片），断网可用
- 画面全部矢量绘制：天空光晕、三层视差丘陵、圆柱渐变管道、曲线鸟身、
  三帧翅膀、草皮地面、气流与羽屑粒子、得分飘字、撞击抖动

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
    sky0: "#071320", sky1: "#15314a", sun: "#eef6ff", sunGlow: "rgba(180,220,255,.22)",
    cloud: "#26405a", cloudShade: "rgba(10,24,36,.45)",
    hillFar: "#1b3d4e", hillMid: "#173444", hillNear: "#122a37",
    grass: "#2c5f4a", grassDark: "#214a39",
    dirt: "#3b2f24", dirtDark: "#2a2118", pebble: "#4a3b2c",
    pipeShadow: "#11402d", pipeEdge: "#185839", pipeBody: "#27784f",
    pipeHi: "#3d9668", pipeRim: "#1f6444", pipeRimHi: "#47ab76",
    bird: "#ffcb3d", belly: "#ffeaa8", wing: "#e59d1e", wingTip: "#b8781a",
    beak: "#f2882f", beakDark: "#d96a1c", tail: "#f0b02c",
    eye: "#101a22", blush: "rgba(255,150,110,.30)", puff: "rgba(170,215,255,.55)",
    feather: "#e8a221",
    text: "#e8f0f5", textShadow: "rgba(6,12,18,.9)",
    panel: "#0c161e", panelEdge: "rgba(110,160,190,.35)", hint: "#8fb4c9"
  } : {
    sky0: "#8ed4f0", sky1: "#e3f5ff", sun: "#fffbe6", sunGlow: "rgba(255,246,200,.6)",
    cloud: "#ffffff", cloudShade: "rgba(178,214,236,.42)",
    hillFar: "#c2e8da", hillMid: "#9adcc0", hillNear: "#74c69e",
    grass: "#7cc96a", grassDark: "#5da94f",
    dirt: "#d3b384", dirtDark: "#b0905f", pebble: "#c0a173",
    pipeShadow: "#2a6d47", pipeEdge: "#35945f", pipeBody: "#4cb47c",
    pipeHi: "#86e0ad", pipeRim: "#3d9a68", pipeRimHi: "#93ebba",
    bird: "#ffcb3d", belly: "#fff0b8", wing: "#e59d1e", wingTip: "#b8781a",
    beak: "#f2882f", beakDark: "#d96a1c", tail: "#f2b52e",
    eye: "#1d2b36", blush: "rgba(255,140,90,.35)", puff: "rgba(255,255,255,.85)",
    feather: "#ffcb3d",
    text: "#22384a", textShadow: "rgba(255,255,255,.9)",
    panel: "#ffffff", panelEdge: "rgba(120,165,185,.35)", hint: "#5b6b78"
  };

  // ── 手感参数（改这里调难度）──────────────────────────────
  var W = 480, H = 270;          // 逻辑分辨率 16:9
  var GROUND = 34;               // 地面高度
  var PW = 52;                   // 管道宽度
  var GAP = 116;                 // 上下管道缝隙
  var SPACING = 190;             // 相邻管道间距
  var VX = 2.05;                 // 管道横向速度（px/帧）
  var G = 0.42;                  // 重力加速度（px/帧²）
  var FLAP = -6.1;               // 拍翼瞬时速度
  var BX = 112, BR = 11.5;       // 鸟的横坐标与碰撞半宽

  var cv = document.getElementById("g");
  var ctx = cv.getContext("2d");

  // 画布按 16:9 letterbox：容器比例不对时画面仍是横屏，富余部分填底色
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

  // iframe 自撑比例：宿主不保留外层容器样式，只能由文档内脚本按自身宽度
  // 把 frameElement 的高度设成 16:9。跨源拿不到就靠 letterbox 兜底。
  function fitFrame() {
    try {
      var fe = window.frameElement;
      if (!fe) return;
      var w = fe.clientWidth || window.innerWidth || 0;
      if (w > 0) fe.style.height = Math.round(w * H / W) + "px";
    } catch (e) { /* 跨源（sandbox）读不到，忽略 */ }
  }
  fitFrame();
  fit();
  document.body.style.background = "#0b1116";
  window.addEventListener("resize", function () { fitFrame(); fit(); });
  window.addEventListener("load", function () { fitFrame(); fit(); });

  var bird, pipes, clouds, stars, score, state, tick, wingT, best, paused = false;
  var scroll, parts, pops, shake, goTimer;

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
    stars = [];
    parts = [];
    pops = [];
    score = 0;
    state = "ready";
    tick = 0;
    wingT = 0;
    scroll = 0;
    shake = 0;
    goTimer = 0;
    var x = W - 56;
    for (var i = 0; i < 3; i++) { pipes.push(makePipe(x)); x += SPACING; }
    for (var j = 0; j < 5; j++) {
      clouds.push({ x: rnd(0, W), y: rnd(10, 108), s: rnd(0.5, 1.15), v: rnd(0.08, 0.22), a: rnd(0.45, 0.78) });
    }
    for (var k = 0; k < 26; k++) {
      stars.push({ x: rnd(0, W), y: rnd(4, 120), r: rnd(0.5, 1.3), p: rnd(0, 6.28) });
    }
  }

  function flap() {
    wingT = 1;
    if (state === "dead") {
      reset();
      state = "playing";
      goTimer = 24;
      bird.vy = FLAP;
      spawnPuff();
      return;
    }
    if (state === "ready") { state = "playing"; goTimer = 26; }
    bird.vy = FLAP;
    spawnPuff();
  }

  function die() {
    if (state !== "playing") return;
    state = "dead";
    shake = 6;
    spawnFeathers();
    if (score > best) {
      best = score;
      try { localStorage.setItem("skyglide.best", String(best)); } catch (e) { /* 隐私模式忽略 */ }
    }
  }

  function hitRect(x, y, w, h) {
    return x < BX + BR - 2 && x + w > BX - BR + 2 && y < bird.y + 8.5 && y + h > bird.y - 8.5;
  }

  // ── 粒子 ────────────────────────────────────────────────
  function spawnPuff() {
    for (var i = 0; i < 4; i++) {
      parts.push({
        kind: "puff", x: BX - 9, y: bird.y + rnd(2, 8),
        vx: rnd(-2.0, -0.6), vy: rnd(0.2, 1.4),
        life: 1, decay: rnd(0.05, 0.09), size: rnd(1.1, 2.6), rot: 0, vr: 0
      });
    }
  }

  function spawnFeathers() {
    for (var i = 0; i < 14; i++) {
      parts.push({
        kind: "feather", x: BX + rnd(-6, 8), y: bird.y + rnd(-6, 8),
        vx: rnd(-2.6, 2.6), vy: rnd(-3.2, 0.6),
        life: 1, decay: rnd(0.012, 0.026), size: rnd(2.2, 4.2),
        rot: rnd(0, 6.28), vr: rnd(-0.22, 0.22)
      });
    }
  }

  function updateParts() {
    var i, p;
    for (i = parts.length - 1; i >= 0; i--) {
      p = parts[i];
      p.x += p.vx;
      p.y += p.vy;
      p.vy += p.kind === "feather" ? 0.09 : -0.01;
      p.vx *= 0.985;
      p.rot += p.vr;
      p.life -= p.decay;
      if (p.life <= 0) parts.splice(i, 1);
    }
  }

  function drawParts() {
    var i, p;
    for (i = 0; i < parts.length; i++) {
      p = parts[i];
      ctx.save();
      ctx.globalAlpha = Math.max(0, Math.min(1, p.life));
      if (p.kind === "feather") {
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = PAL.feather;
        ctx.beginPath();
        ctx.ellipse(0, 0, p.size, p.size * 0.45, 0, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.fillStyle = PAL.puff;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }
  }

  function update() {
    tick++;
    if (shake > 0.2) shake *= 0.86; else shake = 0;
    if (goTimer > 0) goTimer--;

    var i, c;
    var worldSpeed = state === "playing" ? 1 : (state === "dead" ? 0 : 0.25);
    scroll += VX * worldSpeed;

    for (i = 0; i < clouds.length; i++) {
      c = clouds[i];
      c.x -= c.v * (state === "playing" ? 1.9 : 1);
      if (c.x < -46) { c.x = W + 26; c.y = rnd(8, 106); }
    }
    updateParts();

    for (i = pops.length - 1; i >= 0; i--) {
      pops[i].y -= 0.7;
      pops[i].life -= 0.022;
      if (pops[i].life <= 0) pops.splice(i, 1);
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
      if (!pipes[i].passed && pipes[i].x + PW < BX - 8) {
        pipes[i].passed = true;
        score++;
        pops.push({ x: BX + 18, y: bird.y - 16, life: 1, text: "+1" });
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
      if (p.x > BX + 12 || p.x + PW < BX - 12) continue;
      if (hitRect(p.x, 0, PW, p.top) || hitRect(p.x, p.top + p.gap, PW, H - GROUND - p.top - p.gap)) {
        die();
        return;
      }
    }
  }

  // ── 绘制 ────────────────────────────────────────────────
  function drawSky() {
    var g = ctx.createLinearGradient(0, 0, 0, H - GROUND);
    g.addColorStop(0, PAL.sky0);
    g.addColorStop(0.55, PAL.sky1);
    g.addColorStop(1, PAL.sky1);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  function drawSkyBody() {
    var x = W - 72, y = 50;
    var g = ctx.createRadialGradient(x, y, 2, x, y, 50);
    g.addColorStop(0, PAL.sun);
    g.addColorStop(0.3, PAL.sunGlow);
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, 50, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = PAL.sun;
    ctx.beginPath();
    ctx.arc(x, y, 13, 0, Math.PI * 2);
    ctx.fill();

    if (DARK) {
      ctx.fillStyle = "rgba(190,205,225,.18)";
      ctx.beginPath(); ctx.arc(x - 4, y - 3, 2.6, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.arc(x + 4, y + 4, 1.8, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.arc(x + 2, y - 5, 1.4, 0, Math.PI * 2); ctx.fill();
    }
  }

  function drawStars() {
    if (!DARK) return;
    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      ctx.globalAlpha = 0.25 + 0.55 * (0.5 + 0.5 * Math.sin(tick * 0.045 + s.p));
      ctx.fillStyle = "#dff0ff";
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function drawCloud(c) {
    ctx.save();
    ctx.globalAlpha = c.a;
    var x = c.x, y = c.y, s = c.s;
    ctx.fillStyle = PAL.cloud;
    ctx.beginPath(); ctx.ellipse(x, y, 20 * s, 10 * s, 0, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(x + 15 * s, y + 3 * s, 13 * s, 7.5 * s, 0, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(x - 16 * s, y + 4 * s, 11 * s, 6.5 * s, 0, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(x + 4 * s, y - 6 * s, 12 * s, 8 * s, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = PAL.cloudShade;
    ctx.beginPath(); ctx.ellipse(x + 2 * s, y + 7.5 * s, 14 * s, 2.4 * s, 0, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  function hillLayer(color, baseY, amp, freq, speed, phase) {
    var floor = H - GROUND;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(0, floor);
    for (var x = 0; x <= W; x += 3) {
      var t = (x + scroll * speed) * freq + phase;
      var y = baseY - (Math.sin(t) * 0.65 + Math.sin(t * 2.17 + 1.3) * 0.35) * amp;
      ctx.lineTo(x, y);
    }
    ctx.lineTo(W, floor);
    ctx.closePath();
    ctx.fill();
  }

  function drawHills() {
    var floor = H - GROUND;
    hillLayer(PAL.hillFar, floor - 40, 22, 0.010, 0.12, 0);
    hillLayer(PAL.hillMid, floor - 21, 16, 0.014, 0.28, 2.1);
    hillLayer(PAL.hillNear, floor - 5, 10, 0.020, 0.5, 4.3);
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

  function pipeBody(x, y, w, h) {
    if (h <= 0) return;
    var g = ctx.createLinearGradient(x, 0, x + w, 0);
    g.addColorStop(0, PAL.pipeShadow);
    g.addColorStop(0.14, PAL.pipeEdge);
    g.addColorStop(0.34, PAL.pipeHi);
    g.addColorStop(0.56, PAL.pipeBody);
    g.addColorStop(1, PAL.pipeShadow);
    ctx.fillStyle = g;
    ctx.fillRect(x, y, w, h);
  }

  function pipeRim(x, y) {
    var w = PW + 8;
    var g = ctx.createLinearGradient(x, 0, x + w, 0);
    g.addColorStop(0, PAL.pipeShadow);
    g.addColorStop(0.2, PAL.pipeRimHi);
    g.addColorStop(0.5, PAL.pipeRim);
    g.addColorStop(1, PAL.pipeShadow);
    ctx.fillStyle = g;
    roundRect(x, y, w, 12, 4);
    ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,.28)";
    ctx.fillRect(x + 4, y + 2.5, w - 8, 1.6);
    ctx.fillStyle = "rgba(0,0,0,.12)";
    ctx.fillRect(x + 4, y + 9.5, w - 8, 1.4);
  }

  function drawPipes() {
    var floor = H - GROUND;
    for (var i = 0; i < pipes.length; i++) {
      var p = pipes[i], botY = p.top + p.gap;
      // 落地投影
      ctx.fillStyle = "rgba(0,0,0,.10)";
      ctx.beginPath();
      ctx.ellipse(p.x + PW / 2, floor + 3, PW * 0.62, 4.5, 0, 0, Math.PI * 2);
      ctx.fill();

      pipeBody(p.x, 0, PW, p.top - 12);
      pipeBody(p.x, botY + 12, PW, floor - botY - 12);
      pipeRim(p.x - 4, p.top - 12);
      pipeRim(p.x - 4, botY);
    }
  }

  function drawGround() {
    var y = H - GROUND, i;
    ctx.fillStyle = PAL.grass;
    ctx.fillRect(0, y, W, 8);

    ctx.fillStyle = PAL.grassDark;
    var off = scroll % 14;
    for (i = -14; i < W + 14; i += 14) {
      ctx.beginPath();
      ctx.moveTo(i - off, y + 8);
      ctx.quadraticCurveTo(i - off + 4, y + 1.5, i - off + 8, y + 8);
      ctx.closePath();
      ctx.fill();
    }
    ctx.fillStyle = "rgba(255,255,255,.16)";
    for (i = -21; i < W + 21; i += 21) {
      ctx.beginPath();
      ctx.moveTo(i - off, y + 8);
      ctx.quadraticCurveTo(i - off + 3, y + 3.5, i - off + 6, y + 8);
      ctx.closePath();
      ctx.fill();
    }

    ctx.fillStyle = PAL.dirt;
    ctx.fillRect(0, y + 8, W, GROUND - 8);
    ctx.fillStyle = PAL.dirtDark;
    ctx.fillRect(0, y + 8, W, 1.5);

    ctx.fillStyle = PAL.pebble;
    var o2 = scroll % 34;
    for (i = -34; i < W + 34; i += 34) {
      ctx.fillRect(i - o2, y + 16, 8, 3);
      ctx.fillRect(i - o2 + 15, y + 24, 5, 2.4);
      ctx.fillRect(i - o2 + 20, y + 14, 4, 2);
    }
  }

  function drawBird() {
    var phase = state === "ready" ? Math.sin(tick * 0.18) : Math.sin(tick * 0.5) * (wingT > 0 ? 1 : 0.3);
    if (wingT > 0) wingT -= 0.07;

    ctx.save();
    ctx.translate(BX, bird.y);
    ctx.rotate(bird.rot);
    ctx.scale(1.18, 1.18);

    // 尾羽
    ctx.fillStyle = PAL.tail;
    ctx.beginPath();
    ctx.moveTo(-10, -2);
    ctx.lineTo(-17, -6.5);
    ctx.lineTo(-15, 1);
    ctx.lineTo(-9, 4);
    ctx.closePath();
    ctx.fill();

    // 身体
    ctx.fillStyle = PAL.bird;
    ctx.beginPath();
    ctx.moveTo(-12, 0);
    ctx.bezierCurveTo(-12, -9, -2, -13, 7, -10.5);
    ctx.bezierCurveTo(14, -8.5, 16, -3.5, 16, 0.5);
    ctx.bezierCurveTo(16, 9, 5, 13, -4, 11);
    ctx.bezierCurveTo(-10, 9.5, -12, 5, -12, 0);
    ctx.closePath();
    ctx.fill();

    // 肚皮高光
    ctx.fillStyle = PAL.belly;
    ctx.beginPath();
    ctx.ellipse(-0.5, 4.2, 9, 5.2, 0, 0, Math.PI * 2);
    ctx.fill();

    // 翅膀（从身体中段向后展开，超出左轮廓才看得出扇动）
    ctx.save();
    ctx.translate(-4, 3 + phase * 2.2);
    ctx.fillStyle = PAL.wing;
    ctx.beginPath();
    ctx.moveTo(3, -1.2);
    ctx.bezierCurveTo(0, -6.4, -8.6, -6.2, -11.8, -1.4);
    ctx.bezierCurveTo(-13.2, 0.6, -12, 2.8, -9.8, 3.4);
    ctx.bezierCurveTo(-4.6, 5.2, 0.6, 3.4, 3, -1.2);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = PAL.wingTip;
    ctx.beginPath();
    ctx.moveTo(-9.6, 3.2);
    ctx.bezierCurveTo(-5.2, 4.8, -0.8, 3.6, 1.2, 0.2);
    ctx.bezierCurveTo(-1.8, 2.4, -6, 3.4, -9.6, 3.2);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    // 腮红
    ctx.fillStyle = PAL.blush;
    ctx.beginPath();
    ctx.arc(2, 4.6, 3, 0, Math.PI * 2);
    ctx.fill();

    // 眼睛
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(6.4, -4, 3.8, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = PAL.eye;
    ctx.beginPath();
    ctx.arc(7.6, -4, 1.9, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,.92)";
    ctx.beginPath();
    ctx.arc(8.4, -4.9, 0.85, 0, Math.PI * 2);
    ctx.fill();

    // 喙（上下两片）
    ctx.fillStyle = PAL.beak;
    ctx.beginPath();
    ctx.moveTo(12, -1.8);
    ctx.lineTo(21, 0.8);
    ctx.lineTo(12, 2.2);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = PAL.beakDark;
    ctx.beginPath();
    ctx.moveTo(12, 2.2);
    ctx.lineTo(21, 0.8);
    ctx.lineTo(12, 4.8);
    ctx.closePath();
    ctx.fill();

    ctx.restore();
  }

  function text(str, x, y, size, align, color) {
    ctx.font = "700 " + size + "px -apple-system, 'PingFang SC', 'Helvetica Neue', monospace";
    ctx.textAlign = align || "center";
    ctx.textBaseline = "middle";
    ctx.lineWidth = Math.max(1.2, size * 0.075);
    ctx.strokeStyle = PAL.textShadow;
    ctx.strokeText(str, x, y);
    ctx.fillStyle = color || PAL.text;
    ctx.fillText(str, x, y);
  }

  function drawHud() {
    var i;
    for (i = 0; i < pops.length; i++) {
      ctx.save();
      ctx.globalAlpha = Math.max(0, pops[i].life);
      text(pops[i].text, pops[i].x, pops[i].y, 15, "center", PAL.bird);
      ctx.restore();
    }

    if (state === "ready") {
      var bw = 246, bh = 60, bx = (W - bw) / 2, by = H * 0.26 - 23;
      ctx.fillStyle = DARK ? "rgba(8,18,26,.55)" : "rgba(255,255,255,.62)";
      roundRect(bx, by, bw, bh, 16);
      ctx.fill();
      text("按 空格 起飞", W / 2, by + 22, 17);
      text("空格 / 点击 扇动翅膀", W / 2, by + 44, 12);
      return;
    }

    if (state !== "dead") text(String(score), W / 2, 42, 40);

    if (goTimer > 0) {
      ctx.save();
      ctx.globalAlpha = Math.min(1, goTimer / 12);
      text("起飞！", BX + 46, bird.y - 26, 16, "center", PAL.bird);
      ctx.restore();
    }

    if (state === "dead") {
      var pw = 252, ph = 128, px = (W - pw) / 2, py = (H - ph) / 2 - 4;
      ctx.fillStyle = PAL.panel;
      roundRect(px, py, pw, ph, 14);
      ctx.fill();
      ctx.strokeStyle = PAL.panelEdge;
      ctx.lineWidth = 1.5;
      ctx.stroke();
      text("撞上了", W / 2, py + 26, 17);
      text("得分 " + score, W / 2, py + 56, 16, "center", PAL.bird);
      text("最高 " + best, W / 2, py + 80, 13, "center", PAL.hint);
      text("空格 / 点击 再来一次", W / 2, py + 105, 12, "center", PAL.hint);
    }
  }

  function draw() {
    drawSky();
    drawSkyBody();
    drawStars();
    var i;
    for (i = 0; i < clouds.length; i++) drawCloud(clouds[i]);
    drawHills();

    var sx = 0, sy = 0;
    if (shake > 0.2) { sx = rnd(-shake, shake); sy = rnd(-shake, shake); }
    ctx.save();
    ctx.translate(sx, sy);
    drawPipes();
    drawGround();
    drawParts();
    drawBird();
    ctx.restore();

    drawHud();
  }

  // ── 主循环（固定步长，刷新率无关）────────────────────────
  var last = 0, acc = 0, STEP = 1000 / 60;
  function loop(t) {
    if (!last) last = t;
    var dt = t - last;
    last = t;
    if (dt > 100) dt = 100;
    if (!paused) {
      acc += dt;
      var guard = 0;
      while (acc >= STEP && guard < 6) { update(); acc -= STEP; guard++; }
      if (acc > STEP * 6) acc = 0;
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