# -*- coding: utf-8 -*-
"""agent 插件包契约测试：connect 必须返回非空键值对。

为什么单独立这个测试：magpie 的 agent 插件有两级校验，
- 加载期：``config`` 必填；``model`` 与 ``connect`` 至少有一个
- **连接期（UI 点“连接”时）**：``connect()`` 返回空对象会被拒绝，
  报 ``connect returned no keys to write``

我们最初只按加载期约束写了 ``connect() { return {} }``，CLI 能列出 agent 行
（CLI 不调 connect），但用户在 magpie 界面点连接就报错。这个测试锁住连接期
约束，防止再退回去。

跑法（项目 venv）：
    python plugins/magpie/tests/smoke_agent_contract.py

不需要 magpie 本体，纯静态解析 + 可选的 node/bun 语义校验。
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "agent_plugin"

pkg = json.loads((PKG / "package.json").read_text(encoding="utf-8"))
agent_rel = pkg.get("magpie", {}).get("agent")
assert agent_rel, "package.json 的 magpie.agent 必须指向 agent 文件"
agent_file = (PKG / agent_rel).resolve()
assert agent_file.is_file(), f"magpie.agent 指向的文件不存在: {agent_file}"

src = agent_file.read_text(encoding="utf-8")

# ── 加载期约束 ──────────────────────────────────────────
assert re.search(r'\bid:\s*"drifox"', src), "agent.id 必须是 drifox（与 agent_link.AGENT_ID 一致）"
assert re.search(r'\bconfig:\s*"', src), "agent.config 必填（加载期校验）"
assert re.search(r'\bformat:\s*"(json|yaml|env)"', src), "agent.format 必须是 json/yaml/env"
# 刻意不声明 model：模型留在 DriFox 自己设置里选
assert not re.search(r'^\s*model:\s*"', src, re.M), "不应声明 agent.model"

# config 不能指向 DriFox 的 app.config（密文 + 内存缓存整文件覆盖）
m = re.search(r'\bconfig:\s*"([^"]+)"', src)
cfg_path = m.group(1)
assert "app.config" not in cfg_path, f"config 不得指向 app.config：{cfg_path}"
assert "plugin_data" in cfg_path, f"config 应落在 DriFox 自己的 plugin_data 下：{cfg_path}"

# ── 连接期约束（这条是踩过的坑）────────────────────────
body_m = re.search(r'export\s+function\s+connect\s*\([^)]*\)\s*\{(.*?)\n\}', src, re.S)
assert body_m, "必须导出 connect 函数"
body = body_m.group(1)
# 空对象 / 空 return 都会被 magpie 拒绝（connect returned no keys to write）
assert not re.search(r'return\s*\{\s*\}', body), "connect 返回空对象会被 magpie 拒绝"
assert not re.search(r'return\s*;\s*$', body, re.M), "connect 不能空返回"
keys = re.findall(r'"([A-Za-z0-9_.\-]+)"\s*:', body)
assert len(keys) >= 1, f"connect 必须返回至少一个键，实际键: {keys}"

# ── 语义校验（有 node/bun 时跑一次真求值）───────────────
runner = shutil.which("bun") or shutil.which("node")
if runner:
    probe = (
        "import('file:///" + str(agent_file).replace("\\", "/") + "').then(m => {"
        '  const keys = m.connect({ gateway: { v1: "http://x/v1", key: "k" }, model: null });'
        '  if (!keys || typeof keys !== "object" || Object.keys(keys).length === 0) {'
        '    console.error("EMPTY"); process.exit(2);'
        "  }"
        '  console.log(JSON.stringify(keys));'
        "}).catch(e => { console.error(String(e)); process.exit(3); });"
    )
    r = subprocess.run([runner, "-e", probe], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"connect 语义求值失败: {r.stderr[:300]}"
    got = json.loads(r.stdout.strip())
    assert got.get("drifoxGateway.url") and got.get("drifoxGateway.key"), got
    print("runtime connect ok:", got)
else:
    print("(no bun/node on PATH, skipped runtime eval)")

print("agent contract ok:", agent_file.name, "| keys:", keys)
