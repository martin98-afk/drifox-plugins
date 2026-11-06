# file-designer 框选批量拾取与组合标注 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 预览窗口拾取/标注模式支持左键拖拽框选：一次圈选多元素批量回填；标注支持一条注释挂一组元素。

**Architecture:** JS 侧新增 `_MARQUEE_JS`（框选层，挂 document，全格式共用），改造 `_PICK_JS`（click 抑制）与 `_ANNOTATE_JS`（条目 anchor→anchors 数组、note-box 按 seq 定位）；Python 侧桥加 `pick_many` 槽，批量回填/组合标注格式化抽纯函数进 pick_format.py。

**Tech Stack:** PyQt5 QWebEngine + QWebChannel 桥、纯 Python 纯函数 + pytest、无构建步骤。

**Spec:** `docs/superpowers/specs/2026-11-06-file-designer-marquee-design.md`

**环境注意：**
- 解释器：`D:\work\drifox\.venv\Scripts\python.exe`
- 测试命令从仓库根跑：`D:\work\drifox\.venv\Scripts\python.exe -m pytest plugins/file-designer/tests/test_xxx.py -v`
- 坑：主仓库树内 pytest 可能崩 0xC0000409（历史为 Qt fixture 收集触发）。file-designer 测试多为无 Qt 纯函数，若仍崩：用 `manage_worktree(action="create")` 开 worktree 在其中跑。

---

### Task 1: pick_format.py 纯函数（归一化 + 组合标注 + 批量拾取）

**Files:**
- Modify: `plugins/file-designer/ui/pick_format.py`
- Test: `plugins/file-designer/tests/test_pick_format_formats.py`

- [ ] **Step 1: 追加失败测试**

在 `test_pick_format_formats.py` 末尾追加（该文件已有 `pf = _load_module(...)` 基建）：

```python
def test_normalize_annotations_legacy():
    old = [{"anchor": "52", "comment": "c", "seq": 1, "snippet": "s"}]
    out = pf.normalize_annotations(old)
    assert out[0]["anchors"] == ["52"]
    assert "anchor" not in out[0]
    assert old[0].get("anchor") == "52"  # 不修改输入


def test_normalize_annotations_keeps_groups():
    g = [{"anchors": ["a", "b"], "comment": "c", "seq": 2, "snippet": "s"}]
    assert pf.normalize_annotations(g)[0]["anchors"] == ["a", "b"]


def test_normalize_annotations_empty_and_bad():
    assert pf.normalize_annotations([]) == []
    assert pf.normalize_annotations(None) == []
    assert pf.normalize_annotations([{"comment": "no-anchor"}])[0]["anchors"] == ["?"]


def test_format_annotations_group_entries():
    anns = [
        {"anchors": ["52:r1c1", "52:r2c1"], "comment": "整组说明", "seq": 1, "snippet": "首元素"},
        {"anchors": ["3", "4", "5", "6", "7", "8"], "comment": "多条", "seq": 2, "snippet": "x"},
    ]
    t = pf.format_annotations(r"C:\d\a.docx", anns, mode="docx")
    assert "[表格 #52 单元格 r1c1]、[表格 #52 单元格 r2c1]" in t
    assert "等 6 处" in t
    assert "↳ 注释：整组说明" in t


def test_format_annotations_single_compat():
    """单锚点条目输出与旧版一致（回归）。"""
    anns = [{"anchors": ["52"], "comment": "改标题", "seq": 1, "snippet": "章主题"}]
    t = pf.format_annotations(r"C:\d\a.docx", anns, mode="docx")
    assert "[表格 #52] \"章主题\"" in t


def test_format_batch_pick():
    items = [
        {"anchor": "0", "preview": "第一段"},
        {"anchor": "1", "preview": "第二段"},
        {"anchor": "2", "preview": "第三段"},
    ]
    blocks = {"1": {"kind": "para", "text": "第二段全文", "style": "Normal"}}
    t = pf.format_batch_pick(3, r"C:\d\a.docx", items, blocks,
                             r"C:\picks\m.png", mode="docx", first_guide=False)
    assert t.count("拾取 #") == 3
    assert "#3" in t and "#4" in t and "#5" in t
    assert t.count("截图：") == 1  # 截图仅首条携带
    assert "第二段全文" in t  # block 上下文按锚点携带
    assert "锚点规则" not in t  # first_guide=False 不附指引


def test_format_batch_pick_first_guide():
    items = [{"anchor": "0", "preview": "x"}]
    t = pf.format_batch_pick(0, r"C:\d\a.docx", items, {}, None,
                             mode="docx", first_guide=True)
    assert "锚点规则" in t
```

- [ ] **Step 2: 跑测试确认失败**

Run: `D:\work\drifox\.venv\Scripts\python.exe -m pytest plugins/file-designer/tests/test_pick_format_formats.py -v --noconftest`
Expected: 新 7 个用例 FAIL（`normalize_annotations`/`format_batch_pick` 属性不存在，组合断言不匹配）

- [ ] **Step 3: 实现**

`pick_format.py` 三处改动：

3a. `format_annotations` 前新增 `_anchors_desc` 与 `normalize_annotations`：

```python
def normalize_annotations(annotations):
    """旧条目 {anchor: x} → {anchors: [x]}；返回新列表，不修改输入。"""
    out = []
    for a in annotations or []:
        item = dict(a or {})
        anchors = item.get("anchors")
        if not isinstance(anchors, list) or not anchors:
            old = item.pop("anchor", None)
            anchors = [old] if old else ["?"]
        item["anchors"] = list(anchors)
        item.pop("anchor", None)
        out.append(item)
    return out

def _anchors_desc(mode, anchors):
    descs = [_desc_for(mode, a) for a in anchors]
    if len(descs) > 3:
        return "、".join(descs[:3]) + f" 等 {len(descs)} 处"
    return "、".join(descs)
```

3b. `format_annotations` 整函数替换（锚点行改多锚点 + 入口归一化）：

```python
def format_annotations(path_display, annotations, mode=None):
    """标注统一发送文本：模型逐条按注释修改。组合条目一条注释挂多个锚点。"""
    mode = mode or _mode_of(path_display, None)
    label = _MODE_LABEL.get(mode, mode)
    annotations = normalize_annotations(annotations)
    lines = [f"📝 {label} 标注 共 {len(annotations)} 条 [{path_display}]"]
    for a in annotations:
        lines.append(
            f"{_circled(int(a.get('seq') or 0))}"
            f"{_anchors_desc(mode, a.get('anchors') or ['?'])} "
            f"\"{(a.get('snippet') or '').strip()}\"")
        lines.append(f"  ↳ 注释：{a.get('comment') or ''}")
        if a.get("shot"):
            lines.append(f"  截图：{a['shot']}")
    lines.append(f"（锚点规则: {_GUIDE.get(mode, '见元素描述')};请逐条按注释修改对应元素）")
    return "\n".join(lines)
```

3c. 文件末尾新增 `format_batch_pick`：

```python
def format_batch_pick(start_count, path_display, items, blocks_by_anchor,
                      shot_path, mode, first_guide=False):
    """框选批量拾取文本：逐元素 format_pick 连号拼接，截图仅首条携带。"""
    texts = []
    for i, it in enumerate(items):
        texts.append(format_pick(
            start_count + i, path_display, it.get("anchor", "?"),
            blocks_by_anchor.get(it.get("anchor")),
            it.get("preview") or "",
            shot_path if i == 0 else None,
            include_guide=bool(first_guide and i == 0),
            mode=mode,
        ))
    return "\n".join(texts)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `D:\work\drifox\.venv\Scripts\python.exe -m pytest plugins/file-designer/tests/test_pick_format_formats.py plugins/file-designer/tests/test_pick_format.py -v`
Expected: 全部 PASS（含旧用例回归：单锚点条目经归一化后输出与旧版一致）

- [ ] **Step 5: Commit**

```bash
git add plugins/file-designer/ui/pick_format.py plugins/file-designer/tests/test_pick_format_formats.py
git commit -m "feat(file-designer): 组合标注与批量拾取纯函数（anchors 归一化/多锚点描述/批量回填拼装）"
```

---

### Task 2: _MARQUEE_JS 框选层 + _PICK_JS 抑制 + 拼装注入

**Files:**
- Modify: `plugins/file-designer/ui/html_renderer.py`（新增 `_MARQUEE_JS`、改 `_PICK_JS`、`render_full` 注入）
- Modify: `plugins/file-designer/ui/generic_renderer.py`（`wrap_html` 注入）
- Test: `plugins/file-designer/tests/test_renderer.py`

- [ ] **Step 1: 追加失败测试**

`test_renderer.py` 末尾追加：

```python
def test_marquee_js_installed():
    """框选层必须挂进 docx 与通用骨架两条拼装路径。"""
    html = render_html([_para(0, "x")])
    assert "__marqueeInstalled" in html
    assert "pick_many" in html
    assert "__marqueeJustEnded" in html

def test_marquee_js_in_generic_wrap():
    from generic_renderer_wrap_probe import probe_wrap_html  # 占位，见下方说明
```

注意：generic 路径断言不引第三方模块，直接复用本文件既有的加载方式。查看本文件头部 import 与 `_load_module` 风格后，用同样手法加载 `generic_renderer.py`（同样无 Qt 依赖，`wrap_html` 是纯函数）：

```python
def test_marquee_js_in_generic_wrap():
    import importlib.util
    from pathlib import Path
    ui_dir = Path(__file__).resolve().parent.parent / "ui"
    spec = importlib.util.spec_from_file_location(
        "fd_generic_probe", ui_dir / "generic_renderer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    html = mod.wrap_html("<p data-anchor=\"0\">x</p>")
    assert "__marqueeInstalled" in html
```

（若本文件已有同风格的模块加载 helper，用它替代上述内联加载。）

- [ ] **Step 2: 跑测试确认失败**

Run: `D:\work\drifox\.venv\Scripts\python.exe -m pytest plugins/file-designer/tests/test_renderer.py -v`
Expected: 新 2 个用例 FAIL（html 中无 `__marqueeInstalled`）

- [ ] **Step 3: 实现**

3a. `html_renderer.py` 在 `_PICK_JS` 定义之后新增常量：

```python
_MARQUEE_JS = (
    "(function(){"
    " if (window.__marqueeInstalled) return; window.__marqueeInstalled = true;"
    " var down = false, sx = 0, sy = 0, moved = false, box = null;"
    " function active(){ return document.body.classList.contains('pick') ||"
    "  document.body.classList.contains('annotate'); }"
    " function ensureBox(){"
    "  if (!box){ box = document.createElement('div');"
    "   box.style.cssText = 'position:fixed;z-index:98;display:none;pointer-events:none;border:1px solid var(--accent);background:rgba(102,198,255,0.12);';"
    "   document.body.appendChild(box); }"
    "  return box; }"
    " function hitTest(x1, y1, x2, y2){"
    "  var hits = [];"
    "  document.querySelectorAll('[data-anchor]').forEach(function(el){"
    "   var r = el.getBoundingClientRect();"
    "   if (r.width <= 0 && r.height <= 0) return;"
    "   if (r.left < x2 && r.right > x1 && r.top < y2 && r.bottom > y1) hits.push(el); });"
    "  return hits; }"
    " document.addEventListener('mousedown', function(ev){"
    "  if (ev.button !== 0 || !active()) return;"
    "  if (ev.target.closest && ev.target.closest('#note-box')) return;"
    "  down = true; moved = false; sx = ev.clientX; sy = ev.clientY; });"
    " document.addEventListener('mousemove', function(ev){"
    "  if (!down) return;"
    "  var dx = ev.clientX - sx, dy = ev.clientY - sy;"
    "  if (!moved && Math.abs(dx) + Math.abs(dy) > 4){"
    "   moved = true;"
    "   var sel = window.getSelection && window.getSelection();"
    "   if (sel && sel.removeAllRanges) sel.removeAllRanges(); }"
    "  if (moved){ var b = ensureBox();"
    "   b.style.display = 'block';"
    "   b.style.left = Math.min(sx, ev.clientX) + 'px';"
    "   b.style.top = Math.min(sy, ev.clientY) + 'px';"
    "   b.style.width = Math.abs(ev.clientX - sx) + 'px';"
    "   b.style.height = Math.abs(ev.clientY - sy) + 'px'; } });"
    " document.addEventListener('mouseup', function(ev){"
    "  if (!down) return;"
    "  down = false;"
    "  if (!moved) return;"
    "  var r = box.getBoundingClientRect();"
    "  box.style.display = 'none';"
    "  var hits = hitTest(r.left, r.top, r.right, r.bottom);"
    "  if (!hits.length) return;"
    "  window.__marqueeJustEnded = true;"
    "  if (document.body.classList.contains('annotate')){"
    "   window.__openNoteMulti(hits); return; }"
    "  if (!window.__bridge) return;"
    "  if (hits.length === 1){"
    "   var el = hits[0]; el.scrollIntoView({block: 'center'});"
    "   var r1 = el.getBoundingClientRect();"
    "   window.__bridge.pick(el.getAttribute('data-anchor'), r1.left, r1.top,"
    "    r1.width, r1.height, (el.textContent || '').replace(/\\s+/g, ' ').slice(0, 200));"
    "   return; }"
    "  var items = hits.map(function(el2){"
    "   var r2 = el2.getBoundingClientRect();"
    "   return {anchor: el2.getAttribute('data-anchor'), x: r2.left, y: r2.top,"
    "    w: r2.width, h: r2.height,"
    "    preview: (el2.textContent || '').replace(/\\s+/g, ' ').slice(0, 200)}; });"
    "  window.__bridge.pick_many(JSON.stringify(items), r.left, r.top, r.width, r.height); });"
    "})();"
)
```

3b. `_PICK_JS` click 监听开头插入抑制检查（旧串第一行 `"document.addEventListener('click', function(ev){"` 后）：

```python
    " if (window.__marqueeJustEnded){ window.__marqueeJustEnded = false; return; }"
```

3c. `render_full` 拼装点（docx 路径）：

```python
        f"<script>{_ANNOTATE_JS}</script>"
        f"<script>{_MARQUEE_JS}</script>"
        f"<script>{_PICK_JS}</script></body></html>"
```

3d. `generic_renderer.py`：import 行 `from .html_renderer import _ANNOTATE_JS, _BOOT_JS, _PICK_JS` 改为

```python
from .html_renderer import _ANNOTATE_JS, _BOOT_JS, _MARQUEE_JS, _PICK_JS
```

`wrap_html` 尾部拼装同 3c。

- [ ] **Step 4: 跑测试确认通过**

Run: `D:\work\drifox\.venv\Scripts\python.exe -m pytest plugins/file-designer/tests/test_renderer.py -v`
Expected: 全部 PASS（Task 3 未做时 `__openNoteMulti` 尚不存在，本任务断言不依赖它）

- [ ] **Step 5: Commit**

```bash
git add plugins/file-designer/ui/html_renderer.py plugins/file-designer/ui/generic_renderer.py plugins/file-designer/tests/test_renderer.py
git commit -m "feat(file-designer): 框选层 _MARQUEE_JS（拖拽画框/相交收集/pick_many 回传）全格式注入"
```

---

### Task 3: _ANNOTATE_JS 组合化（anchors 数组 + seq 定位 + openNoteMulti）

**Files:**
- Modify: `plugins/file-designer/ui/html_renderer.py`（`_ANNOTATE_JS` 逐段改造）
- Test: `plugins/file-designer/tests/test_renderer.py`

- [ ] **Step 1: 追加失败测试**

```python
def test_annotate_js_group_support():
    """标注 JS 必须按 anchors 数组工作，note-box 按 seq 定位。"""
    html = render_html([_para(0, "x")])
    assert "__anchorsOf" in html
    assert "__findBySeq" in html
    assert "__openNoteMulti" in html
    assert "JSON.stringify(anchors)" in html
```

- [ ] **Step 2: 跑测试确认失败**

Run: `D:\work\drifox\.venv\Scripts\python.exe -m pytest plugins/file-designer/tests/test_renderer.py::test_annotate_js_group_support -v`
Expected: FAIL

- [ ] **Step 3: 实现（multi_edit 逐段替换 `_ANNOTATE_JS`）**

用 `multi_edit` 按下表替换（oldString 取原文精确串）：

3a. `window.__markOf` 定义之前插入 helpers——oldString：

```
    "window.__markOf = function(el){"
```

newString：

```
    "window.__anchorsOf = function(a){ return a.anchors || (a.anchor ? [a.anchor] : []); };"
    "window.__findBySeq = function(seq){"
    " for (var i = 0; i < window.__annotations.length; i++)"
    "  if (String(window.__annotations[i].seq) === String(seq)) return window.__annotations[i];"
    " return null; };"
    "window.__markOf = function(el){"
```

3b. `__markAll` 整函数替换——oldString（原文）：

```
    "window.__markAll = function(anchor, seq, comment){"
    " document.querySelectorAll('[data-anchor=\"' + anchor + '\"]').forEach(function(el){"
    "  el.classList.add('annotated');"
    "  if (comment) el.title = comment;"
    "  var m = window.__markOf(el);"
    "  if (m) { m.textContent = seq; }"
    "  else { var mk = document.createElement('span'); mk.className = 'amark'; mk.textContent = seq; el.insertBefore(mk, el.firstChild); }"
    " }); };"
```

newString：

```
    "window.__markAll = function(anchors, seq, comment){"
    " (anchors || []).forEach(function(anchor){"
    "  document.querySelectorAll('[data-anchor=\"' + anchor + '\"]').forEach(function(el){"
    "   el.classList.add('annotated');"
    "   if (comment) el.title = comment;"
    "   var m = window.__markOf(el);"
    "   if (m) { m.textContent = seq; }"
    "   else { var mk = document.createElement('span'); mk.className = 'amark'; mk.textContent = seq; el.insertBefore(mk, el.firstChild); }"
    "  }); }); };"
```

3c. `__unmarkAll` 整函数替换——oldString：

```
    "window.__unmarkAll = function(anchor){"
    " document.querySelectorAll('[data-anchor=\"' + anchor + '\"]').forEach(function(el){"
    "  el.classList.remove('annotated'); el.removeAttribute('title'); window.__removeMark(el); }); };"
```

newString：

```
    "window.__unmarkAll = function(anchors){"
    " (anchors || []).forEach(function(anchor){"
    "  document.querySelectorAll('[data-anchor=\"' + anchor + '\"]').forEach(function(el){"
    "   el.classList.remove('annotated'); el.removeAttribute('title'); window.__removeMark(el); }); }); };"
```

3d. `__renumber` 内 `__markAll` 调用——oldString：

```
    " window.__markAll(a.anchor, a.seq, a.comment); }); };"
```

newString：

```
    " window.__markAll(window.__anchorsOf(a), a.seq, a.comment); }); };"
```

3e. `__openNote` 整函数替换为委托 + `__openNoteMulti`——oldString 从 `"window.__openNote = function(el){"` 到 `" ta0.focus(); };"`（整段，含 box 定位逻辑）。newString：

```
    "window.__openNote = function(el){ window.__openNoteMulti([el]); };"
    "window.__openNoteMulti = function(els){"
    " var box = document.getElementById('note-box');"
    " window.__noteTarget = els && els.length === 1 ? els[0] : null;"
    " window.__noteTargets = els || [];"
    " var existing = null;"
    " if (els && els.length){"
    "  var anc0 = els[0].getAttribute('data-anchor');"
    "  for (var i = 0; i < window.__annotations.length && !existing; i++)"
    "   if (window.__anchorsOf(window.__annotations[i]).indexOf(anc0) >= 0)"
    "    existing = window.__annotations[i];"
    "  if (existing)"
    "   for (var k = 0; k < els.length; k++)"
    "    if (window.__anchorsOf(existing).indexOf(els[k].getAttribute('data-anchor')) < 0){ existing = null; break; } }"
    " box.setAttribute('data-editing', existing ? String(existing.seq) : '');"
    " var ta0 = box.querySelector('textarea');"
    " ta0.value = existing ? existing.comment : '';"
    " ta0.placeholder = els && els.length > 1 ? ('对这 ' + els.length + ' 个选中元素的注释（整组一条）…') : '输入对选中元素的注释…';"
    " box.querySelector('.nbtns .primary').textContent = existing ? '更新注释' : '保存注释';"
    " box.querySelector('.nbtns .danger').style.display = existing ? 'inline-block' : 'none';"
    " var x1 = 1e9, y1 = 1e9, x2 = -1e9, y2 = -1e9;"
    " (els || []).forEach(function(el){ var r = el.getBoundingClientRect();"
    "  x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top);"
    "  x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom); });"
    " if (!els || !els.length){ x1 = 40; y1 = 40; x2 = 320; y2 = 100; }"
    " box.style.left = Math.max(8, Math.min(x1, window.innerWidth - 300)) + 'px';"
    " box.style.top = Math.max(8, Math.min(y2 + 4, window.innerHeight - 100)) + 'px';"
    " box.style.display = 'block';"
    " window.__noteOpen = true;"
    " ta0.focus(); };"
```

3f. `__closeNote` 整函数替换——oldString 从 `"window.__closeNote = function(commit){"` 到组合 push 段 `"  window.__bridge.annotate_added(anchor, comment, seq, snippet, r.left, r.top, r.width, r.height); };"`。newString：

```
    "window.__closeNote = function(commit){"
    " var box = document.getElementById('note-box');"
    " var ta = box.querySelector('textarea');"
    " var comment = ta.value.trim();"
    " var els = window.__noteTargets || [];"
    " var editingSeq = box.getAttribute('data-editing') || '';"
    " box.style.display = 'none'; window.__noteOpen = false;"
    " window.__noteTarget = null; window.__noteTargets = null;"
    " box.removeAttribute('data-editing');"
    " if (!commit) return;"
    " if (editingSeq) {"
    "  if (!comment) return;"
    "  var a = window.__findBySeq(editingSeq);"
    "  if (a) { a.comment = comment; window.__markAll(window.__anchorsOf(a), a.seq, comment);"
    "   if (window.__bridge && window.__bridge.annotate_updated)"
    "    window.__bridge.annotate_updated(String(a.seq), comment); }"
    "  return; }"
    " if (!comment || !els.length) return;"
    " var anchors = els.map(function(el){ return el.getAttribute('data-anchor'); });"
    " var snippet = (els[0].textContent || '').replace(/\s+/g, ' ').trim().slice(0, 120);"
    " var seq = window.__annotations.length + 1;"
    " var x1 = 1e9, y1 = 1e9, x2 = -1e9, y2 = -1e9;"
    " els.forEach(function(el){ var r = el.getBoundingClientRect();"
    "  x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top);"
    "  x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom); });"
    " window.__annotations.push({anchors: anchors, comment: comment, seq: seq, snippet: snippet});"
    " window.__markAll(anchors, seq, comment);"
    " if (window.__bridge && window.__bridge.annotate_added)"
    "  window.__bridge.annotate_added(JSON.stringify(anchors), comment, seq, snippet, x1, y1, x2 - x1, y2 - y1); };"
```

3g. `__deleteNote` + `__removeAnnotation` 替换——oldString：

```
    "window.__deleteNote = function(){"
    " var box = document.getElementById('note-box');"
    " var anchor = box.getAttribute('data-editing') || '';"
    " box.style.display = 'none'; box.removeAttribute('data-editing');"
    " window.__noteOpen = false; window.__noteTarget = null;"
    " if (anchor) window.__removeAnnotation(anchor); };"
    "window.__removeAnnotation = function(anchor){"
    " window.__annotations = window.__annotations.filter(function(a){ return a.anchor !== anchor; });"
    " window.__unmarkAll(anchor);"
    " window.__renumber();"
    " if (window.__bridge && window.__bridge.annotate_deleted)"
    "  window.__bridge.annotate_deleted(anchor); };"
```

newString：

```
    "window.__deleteNote = function(){"
    " var box = document.getElementById('note-box');"
    " var editingSeq = box.getAttribute('data-editing') || '';"
    " box.style.display = 'none'; box.removeAttribute('data-editing');"
    " window.__noteOpen = false; window.__noteTarget = null; window.__noteTargets = null;"
    " if (editingSeq) window.__removeAnnotation(editingSeq); };"
    "window.__removeAnnotation = function(seq){"
    " var a = window.__findBySeq(seq);"
    " if (!a) return;"
    " var goneSeq = String(a.seq);"
    " var i = window.__annotations.indexOf(a);"
    " if (i >= 0) window.__annotations.splice(i, 1);"
    " window.__unmarkAll(window.__anchorsOf(a));"
    " window.__renumber();"
    " if (window.__bridge && window.__bridge.annotate_deleted)"
    "  window.__bridge.annotate_deleted(goneSeq); };"
```

3h. `__restoreAnnotations` 内调用——oldString：

```
    "  window.__markAll(a.anchor, a.seq, a.comment); }); };"
```

newString：

```
    "  window.__markAll(window.__anchorsOf(a), a.seq, a.comment); }); };"
```

注意：`__clearAnnotations` 不改（DOM 全清语义不变）。若某 oldString 不唯一（如 3d 与 3h 相似），扩大上下文到含函数名行。

- [ ] **Step 4: 跑测试确认通过**

Run: `D:\work\drifox\.venv\Scripts\python.exe -m pytest plugins/file-designer/tests/test_renderer.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/file-designer/ui/html_renderer.py plugins/file-designer/tests/test_renderer.py
git commit -m "feat(file-designer): 标注 JS 组合化（anchors 数组条目/seq 定位/openNoteMulti 整组注释）"
```

---

### Task 4: 桥与窗口（pick_many 槽 + seq 语义 + 批量回填 + 归一化读取）

**Files:**
- Modify: `plugins/file-designer/ui/picker.py`（`DocxBridge` 槽、`write_input` append 参数）
- Modify: `plugins/file-designer/ui/docx_window.py`（`on_elements_picked` 新增、`on_annotation_*` 改造、`_load_annotations` 归一化、import）

- [ ] **Step 1: picker.py 桥改造**

`DocxBridge` 槽整体替换为：

```python
class DocxBridge(QObject):
    """QWebChannel 桥：页面 JS → Python。挂在 window 上防 GC。"""

    def __init__(self, window):
        super().__init__(window)
        self._window = window

    @pyqtSlot(str, float, float, float, float, str)
    def pick(self, anchor, x, y, w, h, preview):
        self._window.on_element_picked(anchor, x, y, w, h, preview)

    @pyqtSlot(str, float, float, float, float)
    def pick_many(self, items_json, x, y, w, h):
        self._window.on_elements_picked(items_json, x, y, w, h)

    @pyqtSlot(str, str, int, str, float, float, float, float)
    def annotate_added(self, anchors_json, comment, seq, snippet, x, y, w, h):
        self._window.on_annotation_added(anchors_json, comment, seq, snippet, x, y, w, h)

    @pyqtSlot(str, str)
    def annotate_updated(self, seq, comment):
        self._window.on_annotation_updated(seq, comment)

    @pyqtSlot(str)
    def annotate_deleted(self, seq):
        self._window.on_annotation_deleted(seq)

    @pyqtSlot()
    def escape(self):
        self._window.set_pick_mode(False)
        self._window.set_annotate_mode(False)
```

`write_input` 加显式 append 参数（默认行为不变）：

```python
def write_input(text, count, append=None):
    """经能力池写输入框。append=None 时按 count>1 推断（首条覆盖，后续追加）。"""
    try:
        from app.plugins.sdk import caps_for

        write = caps_for("input.write", plugin="file-designer", surface="ui")
    except Exception:
        write = None
    if write is None:
        return False
    try:
        flag = count > 1 if append is None else bool(append)
        write(text, append=flag, focus=False)
        return True
    except Exception:
        return False
```

- [ ] **Step 2: docx_window.py 改造**

2a. import 行：

```python
from .pick_format import format_annotations, format_batch_pick, format_pick, normalize_annotations
```

2b. `on_element_picked` 之后新增（保持单击路径不动）：

```python
    def on_elements_picked(self, items_json, x, y, w, h):
        """框选批量拾取：一张选框截图 + 逐元素连号回填（截图仅首条携带）。"""
        try:
            items = json.loads(items_json)
        except (ValueError, TypeError):
            return
        items = [it for it in items if isinstance(it, dict) and it.get("anchor")]
        if not items:
            return
        append = self._count > 0
        shot = capture_view_rect(self._view, x, y, w, h)
        blocks = {it["anchor"]: self._lookup_block(it["anchor"]) for it in items}
        text = format_batch_pick(
            self._count, self._current_path or "?", items, blocks,
            str(shot) if shot else None, mode=self._mode,
            first_guide=(self._count == 0),
        )
        self._count += len(items)
        if write_input(text, self._count, append=append):
            self._set_status(f"框选拾取 {len(items)} 个元素（Esc 退出）")
        else:
            self._set_status("已拾取，但输入框写入失败（能力 input.write 不可用）")
```

2c. `on_annotation_added` 替换：

```python
    def on_annotation_added(self, anchors_json, comment, seq, snippet, x, y, w, h):
        shot = capture_view_rect(self._view, x, y, w, h)
        try:
            anchors = json.loads(anchors_json)
        except (ValueError, TypeError):
            anchors = []
        self._annotations.append(
            {"anchors": anchors or ["?"], "comment": comment, "seq": seq,
             "snippet": snippet, "shot": str(shot) if shot else None}
        )
        self._save_annotations()
        self._set_status(f"已保存第 {seq} 条标注（共 {len(self._annotations)} 条，Esc 退出）")
```

2d. `on_annotation_updated` / `on_annotation_deleted` 替换（按 seq 定位）：

```python
    def on_annotation_updated(self, seq, comment):
        for a in self._annotations:
            if str(a.get("seq")) == str(seq):
                a["comment"] = comment
        self._save_annotations()
        self._set_status(f"标注 #{seq} 已更新")

    def on_annotation_deleted(self, seq):
        before = len(self._annotations)
        self._annotations = [a for a in self._annotations if str(a.get("seq")) != str(seq)]
        if len(self._annotations) == before:
            return
        for i, a in enumerate(self._annotations, 1):
            a["seq"] = i
        self._save_annotations()
        self._set_status(f"已删除标注，剩余 {len(self._annotations)} 条")
```

2e. `_load_annotations` 读取归一化：

```python
    def _load_annotations(self):
        try:
            f = self._annotations_path()
            if f.is_file():
                return normalize_annotations(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
        return []
```

- [ ] **Step 3: 全量回归**

Run: `D:\work\drifox\.venv\Scripts\python.exe -m pytest plugins/file-designer/tests -v`
Expected: 全部 PASS（0xC0000409 崩溃则按环境注意降级 worktree 跑）

- [ ] **Step 4: 静态检查**

Run: `D:\work\drifox\.venv\Scripts\python.exe -m ruff check plugins/file-designer/ui/picker.py plugins/file-designer/ui/docx_window.py plugins/file-designer/ui/pick_format.py plugins/file-designer/ui/html_renderer.py`
Expected: 无错误

- [ ] **Step 5: Commit**

```bash
git add plugins/file-designer/ui/picker.py plugins/file-designer/ui/docx_window.py
git commit -m "feat(file-designer): 桥加 pick_many 槽；标注槽改 seq 语义；批量拾取回填与存量标注归一化"
```

---

### Task 5: 手动冒烟验证（需宿主重启加载新 UI）

**Files:** 无代码改动；验证清单。

- [ ] 重启 DriFox 宿主（UI 改动须重启，插件卡目录已同步）
- [ ] docx：打开文档 → 点「拾取」→ 单击一个段落 → 输入框出现 1 条拾取（旧行为不变）
- [ ] docx：按住左键框选 3 个不相邻段落 → 出现选框 → 松开 → 状态栏「框选拾取 3 个元素」，输入框追加 3 条连号拾取，picks 目录新增 1 张选框截图
- [ ] docx：点「标注」→ 框选 2 个元素 → note-box 出现在选框旁 → 输入注释保存 → 两元素带同号 amark
- [ ] docx：单击单个元素 → note-box 正常（单元素路径回归）；删除该标注整条消失
- [ ] 关闭重开同一文档 → 标注恢复（含组合条目整组标记）；旧版本留下的单元素标注 JSON 不丢失
- [ ] pptx / xlsx / xmind 各开一个：框选拾取与组合标注行为一致
- [ ] Esc 退出模式、框选空白处（0 命中）无副作用

---

## Self-Review 记录

- Spec 覆盖：交互层（Task 2）、数据模型归一化（Task 1/4）、批量拾取回填（Task 1/4）、组合标注与 seq 定位（Task 3/4）、回填格式（Task 1）、全格式注入（Task 2 两处拼装点）、测试（各任务）——无缺口。
- 占位符：无 TBD/TODO；所有代码步骤含完整代码。
- 类型一致性：`pick_many(items_json, x, y, w, h)` JS↔桥一致；`annotate_added(anchors_json, ...)` 首参 str↔str 一致；`format_batch_pick(start_count, path_display, items, blocks_by_anchor, shot_path, mode, first_guide)` 定义与调用一致；JS `__openNoteMulti(els)` 与 marquee 调用一致。
