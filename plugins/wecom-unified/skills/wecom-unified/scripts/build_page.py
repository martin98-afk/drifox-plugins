#!/usr/bin/env python3
"""Assemble slide pages from a fixed shell.

  init:     python3 build_page.py init --set signal   [--map colors.json]              (copy shells + template pages + preset into cwd, recoloured)
  buildall: python3 build_page.py buildall                                             (build every NN_body.jsx, then contrast + images, one command)

Older single-step commands: so the header, footer, rules and page padding never drift.

  build: python3 build_page.py build --shell 00_shell.jsx --body 05_body.jsx --vars 05_vars.json [--manifest images.json] --out 05_market.jsx
  check: python3 build_page.py check --shell 00_shell.jsx 03_x.jsx 04_y.jsx ...
  recolor: python3 build_page.py recolor --map colors.json --out-dir local/ shell/content.jsx slides/*.slide   (swap a set's palette)
  contrast: python3 build_page.py contrast 01_cover.jsx 02_x.jsx ...   (text vs. the surface it sits on)
  fit: python3 build_page.py fit 01_cover.jsx 02_x.jsx ...   (does the text fit its box; absolute text landing on other text; Slide must be 1280x720)
  imgfit: python3 build_page.py imgfit --slot 576x434 --actual 1024x1024 --src <url> [--bg #DCEBFD]   (prints the Image JSX)
  images: python3 build_page.py images --manifest images.json 04_x.jsx ...   (written size vs. real aspect ratio)

The shell is a copy of templates/<slug>/shell/content.jsx. Placeholders look like 〔标题〕; 〔B区内容〕 is
where the page body goes. Values are inserted as-is, so they may contain <br /> or <span> markup. Pass "" to leave a
placeholder empty on purpose. `check` verifies that every page is the shell with only the placeholders filled in.
"""
import argparse, json, re, sys

BODY = '〔B区内容〕'
PH = re.compile(r'〔[^〔〕]*〕')

def build(a):
    shell = open(a.shell, encoding='utf-8').read()
    body = open(a.body, encoding='utf-8').read().strip('\n')
    values = json.load(open(a.vars, encoding='utf-8')) if a.vars else {}
    values = {(k[1:-1] if k.startswith('〔') and k.endswith('〕') else k): v for k, v in values.items()}   # "〔标题〕" keys too
    if BODY not in shell: sys.exit(f'shell has no {BODY} marker: {a.shell}')
    missing = []
    def fill(m):
        key = m.group(0)[1:-1]
        if m.group(0) == BODY: return m.group(0)
        if key in values: return str(values[key])
        missing.append(key); return m.group(0)
    page = PH.sub(fill, shell)
    if missing:
        allkeys = [k[1:-1] for k in dict.fromkeys(PH.findall(shell)) if k != BODY]
        ready = json.dumps({k: '' for k in allkeys}, ensure_ascii=False, indent=1)
        shellname = a.shell.replace('\\', '/').rsplit('/', 1)[-1]
        sys.exit('missing values for: ' + ', '.join(sorted(set(missing))) +
                 f'\nthese are placeholders that the shell {shellname} needs -- its header, page number, footer'
                 '\nand lead-in question live in the shell, not in the body, so every page needs its own vars file.'
                 f'\nadd them to {a.vars or "--vars"} (use "" to leave one empty). Full set of keys for this shell:\n'
                 + ready)
    indent = re.search(r'^([ \t]*)' + re.escape(BODY), page, re.M).group(1)
    page = page.replace(indent + BODY, '\n'.join(indent + ln if ln.strip() else ln for ln in body.split('\n')), 1)
    if '<Image' in page:
        if not a.manifest: sys.exit('page contains <Image>: pass --manifest images.json (real sizes recorded in Step6) so the picture cannot be squashed')
        issues = _image_issues(page, json.load(open(a.manifest, encoding='utf-8')))
        if issues: sys.exit('image would be squashed, page not written:\n  ' + '\n  '.join(issues) + '\nrun imgfit with the real size and paste its output into the body')
    open(a.out, 'w', encoding='utf-8').write(page if page.endswith('\n') else page + '\n')
    print(f'ok {a.out}')

def shell_regex(shell):
    parts, pos = [], 0
    for m in PH.finditer(shell):
        parts.append(re.escape(shell[pos:m.start()]))
        parts.append(r'[\s\S]*?' if m.group(0) == BODY else r'(?:(?!</?Box|</?Slide|<Image|<Chart|<Table|<svg)[\s\S])*?')
        pos = m.end()
    parts.append(re.escape(shell[pos:]))
    rx = ''.join(parts)
    return re.compile(r'\s*' + re.sub(r'(\\\s|\\\n|\\ )+', r'\\s*', rx) + r'\s*')

def check(a):
    shell = open(a.shell, encoding='utf-8').read().strip()
    rx, bad = shell_regex(shell), 0
    for p in a.pages:
        src = open(p, encoding='utf-8').read()
        if rx.fullmatch(src): print(f'OK    {p}'); continue
        bad += 1; print(f'DRIFT {p}')
        fixed = [ln.strip() for ln in PH.sub('\0', shell).split('\n') if ln.strip() and '\0' not in ln]
        gone = [ln for ln in fixed if ln not in src]
        for ln in gone[:6]: print('      shell line not found verbatim: ' + ln[:110])
        if not gone: print('      every fixed line is present, but order or placeholder lines differ from the shell')
    sys.exit(1 if bad else 0)

HEX = re.compile(r"#([0-9A-Fa-f]{6})\b")
def _lum(h):
    c = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
def _ratio(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True); return (la + 0.05) / (lb + 0.05)

_TAG = re.compile(r"<(/?)(Slide|Box|Text|span)\b((?:[^<>]|=>)*?)(/?)>", re.S)

def _contrast_hits(src):
    """Every text/surface pair in one page source that is under its threshold, as
    (line, text hex, surface hex, font size, ratio, needed, 'FAIL' | 'warn')."""
    stack, size, hits = ['FFFFFF'], [16], []
    for m in _TAG.finditer(src):
        close, name, attrs, selfc = m.group(1), m.group(2), m.group(3), m.group(4)
        if close:
            if name in ('Slide', 'Box') and len(stack) > 1: stack.pop()
            if name in ('Text', 'span') and len(size) > 1: size.pop()
            continue
        bg = re.search(r"background(?:Color)?:\s*'#([0-9A-Fa-f]{6})'", attrs)
        fs = re.search(r"fontSize:\s*(\d+)", attrs); col = re.search(r"(?<![A-Za-z])color:\s*'#([0-9A-Fa-f]{6})'", attrs)
        if name in ('Slide', 'Box'):
            grad = re.search(r"gradient|backgroundImage|url\(", attrs)
            if not selfc: stack.append(None if grad else (bg.group(1) if bg else stack[-1]))
            continue
        cur = int(fs.group(1)) if fs else size[-1]
        if not selfc: size.append(cur)
        if col and 'backgroundClip' not in attrs and stack[-1] and cur < 150:
            r = _ratio(col.group(1), stack[-1]); need = 3.0 if cur >= 24 else 4.5
            if r < need: hits.append((src.count('\n', 0, m.start()) + 1, col.group(1), stack[-1], cur, r, need, 'FAIL' if r < 3.0 else 'warn'))
    return hits

_DIGIT_HEX = re.compile(r"#(\d{6})\b")

def _hexsafe(h):
    """The nearest colour whose hex code contains a letter. The WeCom exporter turns an all-digit value such as
    #184785 or #244972 into pure red (FF0000) in the .pptx, so no colour may be written with six decimal digits."""
    h = h.lstrip('#').upper()
    if not h.isdigit(): return h
    for d in range(1, 16):
        for i in range(3):
            v = int(h[2 * i:2 * i + 2], 16)
            for cand in (v + d, v - d):
                if 0 <= cand <= 255 and not f'{cand:02X}'.isdigit(): return h[:2 * i] + f'{cand:02X}' + h[2 * i + 2:]
    return h

def _digit_hits(src):
    return [(src.count('\n', 0, m.start()) + 1, m.group(1)) for m in _DIGIT_HEX.finditer(src)]

_SVG_OPEN = re.compile(r"<svg\b([^>]*)>")

def _svg_hits(src):
    """SVGs whose PNG fallback the WeCom exporter would flatten onto white. The exporter stores every <svg> twice,
    as the vector plus a rasterised PNG, and the PNG loses all transparency; Keynote, Quick Look and the preview
    viewers read that PNG. So the first drawn child must be an opaque <rect> covering the whole viewBox in the
    colour of the surface under it, the svg's own style may not carry opacity, and no paint may be rgba()."""
    hits = []
    for m in _SVG_OPEN.finditer(src):
        ln = src.count('\n', 0, m.start()) + 1; attrs = m.group(1)
        end = src.find('</svg>', m.end()); body = src[m.end():end if end > 0 else len(src)]
        vb = re.search(r"viewBox=['\"]0 0 ([\d.]+) ([\d.]+)['\"]", attrs)
        w = vb.group(1) if vb else (re.search(r"\bwidth=\{?['\"]?([\d.]+)", attrs) or [None, None])[1]
        h = vb.group(2) if vb else (re.search(r"\bheight=\{?['\"]?([\d.]+)", attrs) or [None, None])[1]
        if re.search(r"\bopacity:\s*[\d.]+", attrs):
            hits.append((ln, "svg style carries opacity -> drop it and premix the colours with the surface (the exporter's PNG fallback ignores it)"))
        if 'rgba(' in body:
            hits.append((ln, "rgba() inside <svg> is not a valid SVG paint -> write a hex colour plus fillOpacity / strokeOpacity "
                             "(does not blank the graphic, but the PNG fallback may drop the colour)"))
        for am in re.finditer(r'&', body):
            aln = src.count('\n', 0, m.end() + am.start()) + 1
            hits.append((aln, "'&' inside <svg> -> on export it becomes a bare '&', the svg turns into malformed XML and the WHOLE "
                              "graphic renders blank. Rewrite as 与 / and / ·. &amp;, &#38; and '\\u0026' all export to the same "
                              "bare '&' and do NOT help; '&' outside <svg> (e.g. in <Text>) is fine."))
        if w:
            for tm in re.finditer(r"<text\b([^>]*)>([^<{}]+)</text>", body):
                ta, tb = tm.group(1), tm.group(2).strip()
                mx = re.search(r"\bx=['\"{]?(-?[\d.]+)", ta)
                if not tb or not mx:
                    continue
                mfs = re.search(r"font-?[Ss]ize=['\"{]?([\d.]+)", ta)
                x, fs = float(mx.group(1)), float(mfs.group(1)) if mfs else 16.0
                # CJK full width, half width 0.55em
                tw = sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in tb) * fs
                anchor = (re.search(r"text-?[Aa]nchor=['\"](\w+)", ta) or [None, 'start'])[1]
                x0, x1 = (x - tw / 2, x + tw / 2) if anchor == 'middle' else \
                         ((x - tw, x) if anchor == 'end' else (x, x + tw))
                tln = src.count('\n', 0, m.end() + tm.start()) + 1
                if x1 > float(w) + 0.5:
                    hits.append((tln, f"svg text runs to {x1:.0f}, past the viewBox width {w} -> it gets hard-clipped. "
                                      f"Move it left, shorten it, or widen the viewBox: {tb[:34]!r}"))
                elif x0 < -0.5:
                    hits.append((tln, f"svg text starts at {x0:.0f}, left of the viewBox -> it gets hard-clipped: {tb[:34]!r}"))
        inner = re.sub(r"<defs>.*?</defs>", '', body, flags=re.S)
        first = re.search(r"<([A-Za-z]+)\b([^>]*)>", inner); ok = False
        if first and first.group(1) == 'rect':
            ra = first.group(2)
            rw = re.search(r"\bwidth=['\"{]?([\d.]+%?)", ra); rh = re.search(r"\bheight=['\"{]?([\d.]+%?)", ra)
            fill = re.search(r"\bfill=['\"]#[0-9A-Fa-f]{6}['\"]", ra)
            cov = lambda v, need: v is not None and (v.group(1) == '100%' or need is None or float(v.group(1)) >= float(need))
            ok = bool(fill) and cov(rw, w) and cov(rh, h) and 'opacity' not in ra.lower()
        if not ok:
            hits.append((ln, f"svg has no opaque backing rect -> its first drawn child must be <rect x='0' y='0' width='{w or 'W'}' height='{h or 'H'}' fill='#<colour of the surface under it>' /> (the exporter's PNG fallback turns transparency into white)"))
    return hits

_ABS_TAG = re.compile(r"<(Box|Text|Image|svg)\b([^>]*?)/?>", re.S)
_ABS_STYLE = re.compile(r"style=\{\{(.*?)\}\}", re.S)


def _sprop(style, name):
    m = (re.search(rf"\b{name}\s*:\s*'([^']*)'", style) or
         re.search(rf"\b{name}\s*:\s*\"([^\"]*)\"", style) or
         re.search(rf"\b{name}\s*:\s*([\d.-]+)", style))
    return m.group(1).strip() if m else None


def _spx(v, base):
    """'700px' / '50%' / 60 -> pixels (base is used for percentages)."""
    if v is None:
        return None
    s = str(v).strip()
    m = re.match(r"^(-?[\d.]+)\s*%$", s)
    if m:
        return float(m.group(1)) / 100.0 * base
    m = re.match(r"^(-?[\d.]+)(?:px)?$", s)
    return float(m.group(1)) if m else None


def _abs_hits(src, W=1280.0, H=720.0):
    """Absolutely positioned elements that stick out of the canvas. The renderer rejects the whole page for
    these (content overflow) instead of just clipping them, and a flow-layout height check will not catch
    them because they sit outside the flow. Mirrors the renderer's own maths:
        top  = pct(top)*H  - pct(translateY)*height
        left = pct(left)*W - pct(translateX)*width"""
    hits = []
    for m in _ABS_TAG.finditer(src):
        tag, attrs = m.group(1), m.group(2)
        ms = _ABS_STYLE.search(attrs)
        if not ms or _sprop(ms.group(1), 'position') != 'absolute':
            continue
        st = ms.group(1)
        ln = src.count('\n', 0, m.start()) + 1
        w, h = _spx(_sprop(st, 'width'), W), _spx(_sprop(st, 'height'), H)
        dx = dy = 0.0
        tr = _sprop(st, 'transform')
        if tr:
            tm = re.search(r"translate\(\s*([^,)]+)(?:,\s*([^)]+))?\)", tr)
            if tm:
                dx = _spx(tm.group(1), w or 0) or 0.0
                dy = (_spx(tm.group(2), h or 0) or 0.0) if tm.group(2) else 0.0
            for fn, idx in (("translateX", 'x'), ("translateY", 'y')):
                fm = re.search(rf"{fn}\(\s*([^)]+)\)", tr)
                if fm:
                    val = _spx(fm.group(1), (w or 0) if idx == 'x' else (h or 0)) or 0.0
                    if idx == 'x':
                        dx = val
                    else:
                        dy = val
        top, left = _spx(_sprop(st, 'top'), H), _spx(_sprop(st, 'left'), W)
        bot, rgt = _spx(_sprop(st, 'bottom'), H), _spx(_sprop(st, 'right'), W)

        y0 = y1 = x0 = x1 = None
        if top is not None:
            y0 = top + dy
            y1 = y0 + h if h is not None else None
        elif bot is not None and h is not None:
            y1 = H - bot + dy
            y0 = y1 - h
        if left is not None:
            x0 = left + dx
            x1 = x0 + w if w is not None else None
        elif rgt is not None and w is not None:
            x1 = W - rgt + dx
            x0 = x1 - w

        for val, lim, side in ((y0, 0, 'top'), (x0, 0, 'left')):
            if val is not None and val < -0.5:
                hits.append((ln, f"<{tag}> sticks out past the {side} of the canvas by {-val:.0f}px "
                                 f"({side} edge at {val:.0f}) -> the page is rejected as overflowing. "
                                 f"Pull it back inside (non-negative offsets, translate at most -50%)"))
        if y1 is not None and y1 > H + 0.5:
            hits.append((ln, f"<{tag}> sticks out past the bottom of the canvas by {y1-H:.0f}px "
                             f"(bottom edge at {y1:.0f}) -> the page is rejected as overflowing"))
        if x1 is not None and x1 > W + 0.5:
            hits.append((ln, f"<{tag}> sticks out past the right of the canvas by {x1-W:.0f}px "
                             f"(right edge at {x1:.0f}) -> the page is rejected as overflowing"))
        for k in ('top', 'left', 'bottom', 'right'):
            raw = _sprop(st, k)
            if raw and str(raw).startswith('-'):
                hits.append((ln, f"<{tag}> {k}:{raw} is a negative offset -> not allowed, "
                                 f"position with positive values instead (e.g. top:40, right:40)"))
    return hits


def contrast(a):
    """Flag text whose colour is too close to the surface it sits on (nearest ancestor with a solid background).
    Contrast under 3.0 fails; small text between 3.0 and 4.5 is only counted as a warning. Gradient surfaces and
    decorative numerals of 150px and up are skipped. Also flags what the WeCom exporter breaks (six-digit colour
    codes, SVGs without an opaque backing rect, '&' inside an svg, svg text past the viewBox) and absolutely
    positioned elements that stick out of the 1280x720 canvas."""
    bad = 0
    for p in a.pages:
        src = open(p, encoding='utf-8').read()
        hits = _contrast_hits(src); digits = _digit_hits(src); svgs = _svg_hits(src); abso = _abs_hits(src)
        fails = [h for h in hits if h[6] == 'FAIL']
        print(('LOW   ' if fails or digits or svgs or abso else 'OK    ') + p + (f'  ({len(hits) - len(fails)} small-text warnings under 4.5)' if len(hits) > len(fails) else ''))
        for ln, c, b, fsz, r, need, lvl in fails[:20]: print(f'      line {ln}: text #{c} on #{b}, {fsz}px, contrast {r:.2f} < 3.0 -> unreadable, change the text or surface colour')
        for ln, c in digits[:20]: print(f'      line {ln}: #{c} is six decimal digits; the WeCom exporter turns such values into pure red (FF0000) -> write #{_hexsafe(c)}')
        for ln, msg in svgs[:20]: print(f'      line {ln}: {msg}')
        for ln, msg in abso[:20]: print(f'      line {ln}: {msg}')
        bad += bool(fails or digits or svgs or abso)
    sys.exit(1 if bad else 0)

def _dims_from_bytes(b):
    """Return (w, h) for PNG / JPEG / GIF / WebP headers, or None."""
    import struct
    if b[:8] == b'\x89PNG\r\n\x1a\n' and len(b) >= 24: return struct.unpack('>II', b[16:24])
    if b[:6] in (b'GIF87a', b'GIF89a') and len(b) >= 10: return struct.unpack('<HH', b[6:10])
    if b[:4] == b'RIFF' and b[8:12] == b'WEBP' and len(b) >= 30:
        if b[12:16] == b'VP8 ': return struct.unpack('<HH', b[26:30])[0] & 0x3fff, struct.unpack('<HH', b[26:30])[1] & 0x3fff
        if b[12:16] == b'VP8L': bits = int.from_bytes(b[21:25], 'little'); return (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
        if b[12:16] == b'VP8X': return int.from_bytes(b[24:27], 'little') + 1, int.from_bytes(b[27:30], 'little') + 1
    if b[:2] == b'\xff\xd8':
        i = 2
        while i + 9 < len(b):
            if b[i] != 0xff: i += 1; continue
            marker = b[i + 1]; seg = int.from_bytes(b[i + 2:i + 4], 'big')
            if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
                return int.from_bytes(b[i + 7:i + 9], 'big'), int.from_bytes(b[i + 5:i + 7], 'big')
            i += 2 + seg
    return None

def _fetch_dims(url, timeout=8):
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={'Range': 'bytes=0-65535', 'User-Agent': 'build_page'})
        with urllib.request.urlopen(req, timeout=timeout) as r: return _dims_from_bytes(r.read(65536))
    except Exception: return None

def imgfit(a):
    """Print the JSX for an image slot so the picture keeps its real aspect ratio. Never stretches, never relies on objectFit
    (the WeCom compiler crops as if every picture were square, so a non-square picture filled into a slot gets squashed)."""
    sw, sh = map(float, a.slot.lower().split('x')); aw, ah = map(float, a.actual.lower().split('x'))
    slot_r, img_r = sw / sh, aw / ah; dev = abs(img_r - slot_r) / slot_r
    if dev <= 0.03:
        w, h = int(sw), int(sh); note = f'ratio matches slot ({dev*100:.1f}% off), fill the slot'
    elif img_r > slot_r:
        w, h = int(sw), round(sw / img_r); note = f'image wider than slot ({dev*100:.0f}% off): full width, {h}px tall, letterboxed'
    else:
        h, w = int(sh), round(sh * img_r); note = f'image taller than slot ({dev*100:.0f}% off): full height, {w}px wide, pillarboxed'
    bg = f", background: '{a.bg}'" if a.bg else ''
    print(f"<Box style={{{{ width: {int(sw)}, height: {int(sh)}, justifyContent: 'center', alignItems: 'center'{bg} }}}}>")
    print(f"    <Image src=\"{a.src}\" style={{{{ width: {w}, height: {h} }}}} />")
    print("</Box>")
    print(f"// {note}" if False else "", end='')
    sys.stderr.write(note + ('\n  consider regenerating at the slot ratio instead of letterboxing' if dev > 0.03 else '') + '\n')

def _image_issues(src, manifest, fetch=True):
    tag = re.compile(r'<Image\b[^>]*?src=["\']([^"\']+)["\'][^>]*?>', re.S); issues = []
    for m in tag.finditer(src):
        url = m.group(1); attrs = m.group(0)
        w = re.search(r'width:\s*(\d+(?:\.\d+)?)', attrs); h = re.search(r'height:\s*(\d+(?:\.\d+)?)', attrs)
        if not (w and h): issues.append(f'{url[:60]}: width/height not both numeric'); continue
        act = manifest.get(url) or (_fetch_dims(url) if fetch else None)
        if not act: issues.append(f'{url[:60]}: real size unknown (not in manifest, not fetchable) -> record it in images.json'); continue
        aw, ah = act if isinstance(act, (list, tuple)) else (act['width'], act['height'])
        dev = abs((aw / ah) - (float(w.group(1)) / float(h.group(1)))) / (aw / ah)
        if dev > 0.03: issues.append(f'{url[:60]}: real {aw}x{ah} vs written {w.group(1)}x{h.group(1)}, ratio off by {dev*100:.0f}% -> squashed; use imgfit')
    return issues

def images(a):
    """Check every <Image> in the pages: its written width/height must match the picture's real aspect ratio (within 3%)."""
    manifest = json.load(open(a.manifest, encoding='utf-8')) if a.manifest else {}; bad = 0
    for p in a.pages:
        issues = _image_issues(open(p, encoding='utf-8').read(), manifest)
        print(('BAD   ' if issues else 'OK    ') + p); [print('      ' + i) for i in issues]; bad += bool(issues)
    sys.exit(1 if bad else 0)

_TEMPLATE_DIRS = (('..', 'assets', 'templates'), ('templates',), ('..', 'references', 'templates'))

def _templates_root():
    """Locate the template pool. Runtimes ship it under assets/ (sandbox) or references/ (skill tree)."""
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in _TEMPLATE_DIRS:
        cand = os.path.join(here, *rel)
        if os.path.isdir(cand): return cand
    sys.exit('template pool not found next to build_page.py; looked in: '
             + ', '.join('/'.join(r) for r in _TEMPLATE_DIRS))

def _set_root(name):
    import os
    root = os.path.join(_templates_root(), name)
    if not os.path.isdir(root): sys.exit(f'no such set: {name} (use the flat slug, e.g. signal)')
    return root

def _set_files(root):
    import os, glob
    return sorted(glob.glob(os.path.join(root, 'shell', '*.jsx'))) + sorted(glob.glob(os.path.join(root, 'slides', '*.slide')))

def _rgb_to_hsl(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b); l = (mx + mn) / 2
    if mx == mn: return 0.0, 0.0, l
    d = mx - mn; s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r: hu = ((g - b) / d) % 6
    elif mx == g: hu = (b - r) / d + 2
    else: hu = (r - g) / d + 4
    return hu * 60, s, l

def _hsl_to_rgb(hu, s, l):
    hu = hu % 360; c = (1 - abs(2 * l - 1)) * s; x = c * (1 - abs((hu / 60) % 2 - 1)); m = l - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(hu // 60) % 6]
    return '%02X%02X%02X' % tuple(round((v + m) * 255) for v in (r, g, b))

def _at_luminance(hu, s, target):
    """The hue/saturation asked for, with lightness tuned until the colour has the given relative luminance.
    Matching luminance (not HSL lightness) is what keeps every contrast ratio of the original palette intact:
    HSL lightness lies, a yellow and a blue at the same lightness are nowhere near the same brightness."""
    lo, hi = 0.0, 1.0
    for _ in range(24):
        mid = (lo + hi) / 2
        if _lum(_hsl_to_rgb(hu, s, mid)) < target: lo = mid
        else: hi = mid
    return _hsl_to_rgb(hu, s, (lo + hi) / 2)

def palette(a):
    """Derive a whole palette for a set from one hue, keeping every colour's luminance (so the contrast the set was
    built with survives exactly) and the hue distances between colours (so multi-colour sets stay distinguishable).
    Writes colors.json for `init --map` and checks every text/surface pair before doing so."""
    import os, json as _json, collections
    root = _set_root(a.set); files = _set_files(root)
    srcs = {f: open(f, encoding='utf-8').read() for f in files}
    counts = collections.Counter(h.upper() for s in srcs.values() for h in HEX.findall(s))
    if not counts: sys.exit(f'no colours found in {a.set}')
    hsl = {h: _rgb_to_hsl(h) for h in counts}
    chroma = [h for h in counts if hsl[h][1] >= 0.12]
    base_hue = hsl[max(chroma, key=lambda h: counts[h])][0] if chroma else 0.0
    gap = abs((a.hue - base_hue + 180) % 360 - 180)     # how far the asked-for hue is from the set's own
    if chroma and not a.invert and not a.force and gap < a.min_gap:
        print(f"{a.set} is already a {base_hue:.0f} hue set; --hue {a.hue:.0f} is only {gap:.0f} deg away "
              f"(gate: {a.min_gap:.0f}).\nA palette this close to the default is the default with the edges filed "
              "off: it clears every contrast check and\nstill looks like the set's own colours, so it is a recolour "
              "in name only.")
        print("\nUSE THE SET'S DEFAULT PALETTE. Run init WITHOUT --map, and record in DESIGN.md that the colour "
              "intent\nmatches this set's default (state both hues and the gap). That is a legitimate outcome, not "
              "a failure -- do\nNOT go hunting for some other hue just to get past this gate, and do NOT hand-write "
              "a map.")
        print(f"\nOnly if the deck genuinely needs a different colour: pick a hue at least {a.min_gap:.0f} deg from "
              f"{base_hue:.0f} (i.e. outside\n{(base_hue - a.min_gap) % 360:.0f}-{(base_hue + a.min_gap) % 360:.0f}). "
              "If the user named a brand colour that lands inside the gate, pass --force.")
        return
    cmap = {}
    for h, (hu, s, l) in hsl.items():
        if s < 0.12:                                    # neutrals: keep them neutral, just a hint of the new hue
            ns, nhu = min(s + 0.03, 0.08), a.hue
        else:                                           # chromatics: same hue distances, rotated onto the new hue.
            ns = max(0.0, min(1.0, s * a.sat))          # tinted surfaces (low saturation) collapse onto the new hue
            off = (hu - base_hue + 180) % 360 - 180     # instead of being flung to its opposite side
            nhu = a.hue + off * a.spread * min(1.0, s / 0.35)
        target = 1 - _lum(h) if a.invert else _lum(h)
        new = _at_luminance(nhu, ns, target)
        new = _hexsafe(new)                             # six decimal digits would export as pure red
        if new != h: cmap[h] = new
    if not cmap: print('the derived palette is identical to the default one -- use the default: run init without '
                       '--map.'); return
    fails = []
    for f, src in srcs.items():
        for ln, c, b, fsz, r, need, lvl in _contrast_hits(_apply_cmap(src, cmap)):
            if lvl == 'FAIL': fails.append(f'{os.path.basename(f)} line {ln}: text #{c} on #{b}, {fsz}px, contrast {r:.2f} < 3.0')
    for h, n in sorted(cmap.items(), key=lambda kv: -counts[kv[0]]): print(f'  #{h} -> #{n}   (used {counts[h]}x)')
    if fails:
        print('\ncontrast FAIL on the derived palette:'); [print('  ' + f) for f in fails[:10]]
        sys.exit('\nnot written. With --invert this is expected for most sets: flipping light and dark cannot keep the\n'
                 'contrast the set was built with. Pick a set whose default scheme is already the one you want, or drop\n'
                 '--invert (a hue on its own always keeps the contrast). Otherwise try another --hue or --sat below 1.'
                 if a.invert else '\nnot written. Try another --hue, or --sat below 1.')
    try:
        _json.dump({'#' + k: '#' + v for k, v in cmap.items()}, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except OSError as e:
        sys.exit(f'cannot write {a.out!r}: {e.strerror}.\n'
                 'Wrong location, not a broken environment -- write it inside the working directory\n'
                 'under the session output dir, then retry.')
    print(f'\ncontrast OK on every page of the set -> {a.out}\nnext: python3 "{{baseDir}}/scripts/build_page.py" init --set {a.set} --map {a.out}')

def _load_cmap(path):
    cmap = {k.strip().lstrip('#').upper(): v.strip().lstrip('#').upper() for k, v in json.load(open(path, encoding='utf-8')).items()}
    for k, v in cmap.items():
        if not re.fullmatch(r'[0-9A-F]{6}', k) or not re.fullmatch(r'[0-9A-F]{6}', v): sys.exit(f'bad colour in map: {k} -> {v} (use 6-digit hex, e.g. "#1C2644": "#F4F1EA")')
    return cmap

def _apply_cmap(text, cmap):
    """Replace every mapped colour in a single pass, so {"#A": "#B", "#B": "#A"} really swaps the two
    (replacing one entry after another would turn both into A and leave text the same colour as its background)."""
    if not cmap: return text
    rgb = {tuple(int(k[i:i + 2], 16) for i in (0, 2, 4)): v for k, v in cmap.items()}
    hexes = '|'.join(cmap)
    rgbas = '|'.join(r'%d\s*,\s*%d\s*,\s*%d\s*,' % t for t in rgb)
    rx = re.compile(r'#(' + hexes + r')(?![0-9A-Fa-f])|rgba\(\s*(?=' + rgbas + r')(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,', re.I)
    def sub(m):
        if m.group(1): return '#' + cmap[m.group(1).upper()]
        v = rgb[tuple(int(m.group(i)) for i in (2, 3, 4))]
        return 'rgba(%d, %d, %d,' % tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    return rx.sub(sub, text)

def recolor(a):
    """Apply a colour map {old_hex: new_hex} to shell / template files and write the recoloured copies to --out-dir.
    Matches hex literals case-insensitively and the matching rgba(r, g, b, ...) forms. Colours not in the map are left as they are."""
    import os
    cmap = _load_cmap(a.map)
    os.makedirs(a.out_dir, exist_ok=True); unused = set(cmap); untouched = {}
    for p in a.files:
        src = open(p, encoding='utf-8').read()
        unused -= {old for old in cmap if re.search('#' + old + '(?![0-9A-Fa-f])', src, re.I)}
        out = _apply_cmap(src, cmap)
        for h in set(x.upper() for x in HEX.findall(out)):
            if h not in cmap.values(): untouched[h] = untouched.get(h, 0) + 1
        dst = os.path.join(a.out_dir, os.path.basename(p)); open(dst, 'w', encoding='utf-8').write(out); print(f'ok {dst}')
    if unused: print('map entries that matched nothing: ' + ', '.join('#' + u for u in sorted(unused)))
    if untouched: print('colours left unchanged (not in map): ' + ', '.join('#' + u for u in sorted(untouched)) + '  -> add them to the map if they belong to the old palette')
    print('next: run `contrast` on the recoloured pages before using them')

def init(a):
    """Copy a set's shells and template pages into the working dir in one go (optionally recoloured), so the agent never
    has to run cp against the skill directory."""
    import os, shutil
    root = _set_root(a.set)
    try:
        os.makedirs(a.out, exist_ok=True)
    except OSError as e:
        sys.exit(f'cannot create the working directory {a.out!r}: {e.strerror}.\n'
                 'This is the wrong location, not a broken environment -- put the working directory\n'
                 'under the session output dir (e.g. <writable>/temp/<session_id>/output/<name>) and retry.\n'
                 'Do not probe the filesystem for other writable paths.')
    srcs = [os.path.join(root, 'shell', f) for f in sorted(os.listdir(os.path.join(root, 'shell')))] + \
           [os.path.join(root, 'slides', f) for f in sorted(os.listdir(os.path.join(root, 'slides')))] + [os.path.join(root, 'DESIGN.preset.md')]
    cmap = _load_cmap(a.map) if a.map else {}
    for src in srcs:
        name = os.path.basename(src)
        if name.startswith('content'): name = '00_shell' + name[len('content'):]
        elif src.endswith('.slide'): name = 'ref_' + name
        text = _apply_cmap(open(src, encoding='utf-8').read(), cmap)
        open(os.path.join(a.out, name), 'w', encoding='utf-8').write(text); print(f'ok {os.path.normpath(os.path.join(a.out, name))}')
    print('\nthe files above are in the working directory: open and write them by these bare file names only, never by an absolute path')
    refs = [os.path.basename(s).replace('.slide', '') for s in srcs if s.endswith('.slide')]
    print('BEFORE WRITING EACH PAGE: open the ref_*.slide whose skeleton is closest to that page and rework it —\n'
          f'      keep its columns, card shapes and gaps, type scale and signature treatment, swap only the words and numbers.\n'
          f'      Available skeletons: {", ".join("ref_" + r for r in refs)}\n'
          '      A body written without one of these open only looks like the template in its header and footer.')
    if not cmap: print('NOTE: copied with the set\'s DEFAULT palette. That is correct in exactly two cases: the user asked\n'
                       '      for the default or a brand colour by name, or palette said the colour intent is within its\n'
                       '      hue gate of this set\'s own hue. Either way say so in DESIGN.md.\n'
                       f'      Otherwise derive one first: palette --set {a.set} --hue <0-360> [--sat 0.8], then rerun init with --map colors.json')

def buildall(a):
    """Build every NN_body.jsx in the working dir with its NN_vars.json, then run check + contrast (+ images) once."""
    import glob, os, types
    bodies = sorted(glob.glob(os.path.join(a.dir, '[0-9][0-9]_body*.jsx'))); bad = 0; built = []
    # bodies written with a slug, e.g. 03_definition_body.jsx (+ 03_definition_vars.json -> 03_definition_page.jsx)
    named = sorted(p for p in glob.glob(os.path.join(a.dir, '[0-9][0-9]_*_body*.jsx'))
                   if p not in bodies and not re.match(r'\d\d_body', os.path.basename(p)))
    for body in named:
        b = os.path.basename(body); stem, suffix = re.match(r'(\d\d_.+?)_body(.*)\.jsx$', b).groups()
        shell = os.path.join(a.dir, '00_shell' + suffix + '.jsx')
        if not os.path.exists(shell): shell = os.path.join(a.dir, '00_shell.jsx')
        out = os.path.join(a.dir, f'{stem}_page.jsx'); vars_ = os.path.join(a.dir, f'{stem}_vars.json')
        manifest = os.path.join(a.dir, 'images.json')
        ns = types.SimpleNamespace(shell=shell, body=body, vars=vars_ if os.path.exists(vars_) else None,
                                   manifest=manifest if os.path.exists(manifest) else None, out=out)
        try: build(ns); built.append(out)
        except SystemExit as e: bad += 1; print(f'FAIL  {body}: {e}')
    for body in bodies:
        nn = os.path.basename(body)[:2]; suffix = os.path.basename(body)[len(nn) + 5:-4]
        shell = os.path.join(a.dir, '00_shell' + suffix + '.jsx')
        if not os.path.exists(shell): shell = os.path.join(a.dir, '00_shell.jsx')
        out = os.path.join(a.dir, f'{nn}_page.jsx'); vars_ = os.path.join(a.dir, f'{nn}_vars.json')
        manifest = os.path.join(a.dir, 'images.json')
        ns = types.SimpleNamespace(shell=shell, body=body, vars=vars_ if os.path.exists(vars_) else None,
                                   manifest=manifest if os.path.exists(manifest) else None, out=out)
        try: build(ns); built.append(out)
        except SystemExit as e: bad += 1; print(f'FAIL  {body}: {e}')
    bodies = bodies + named
    pages = sorted(set(built + [p for p in glob.glob(os.path.join(a.dir, '[0-9][0-9]_*.jsx')) if not os.path.basename(p).startswith('00_')]) - set(bodies) - {p for p in glob.glob(os.path.join(a.dir, '[0-9][0-9]_*.jsx')) if re.search(r'_body[^/]*\.jsx$', p)})
    if not bodies and not pages:
        orphan = sorted(os.path.basename(p) for p in glob.glob(os.path.join(a.dir, '[0-9][0-9]_vars.json')))
        if orphan:
            sys.exit(f'nothing to build in {os.path.abspath(a.dir)}: found {", ".join(orphan)} but no matching body.\n'
                     'A page needs BOTH files: NN_body.jsx (or NN_body_light.jsx / NN_body_dark.jsx for a second\n'
                     'shell) plus NN_vars.json. Only the body file makes buildall pick the page up -- vars alone is\n'
                     'invisible to it. Write the missing NN_body*.jsx and rerun; the suffix must match the shell you\n'
                     'want (00_shell_dark.jsx <- NN_body_dark.jsx), no suffix falls back to 00_shell.jsx.')
        sys.exit(f'nothing to build in {os.path.abspath(a.dir)}: no NN_body*.jsx and no NN_*.jsx page found.\n'
                 'Run this command from the working directory that holds the page sources (or pass --dir), '
                 'otherwise it would report ALL OK without checking anything.')
    import io, contextlib
    steps = [('contrast (colours, svg, canvas edges)', contrast, types.SimpleNamespace(pages=pages)),
             ('fit (does the text fit its box)', fit, types.SimpleNamespace(pages=pages))]
    if os.path.exists(os.path.join(a.dir, 'images.json')):
        steps.append(('images (aspect ratio)', images, types.SimpleNamespace(manifest=os.path.join(a.dir, 'images.json'), pages=pages)))
    failed = {}
    for title, fn, ns in steps:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try: fn(ns)
            except SystemExit as e: bad += bool(e.code)
        out = buf.getvalue()
        print(f'== {title} ==')
        print(out, end='')
        for ln in out.splitlines():
            m = re.match(r'(OVER|LOW|BAD|DRIFT)\s+(\S+)', ln)
            if m: failed.setdefault(os.path.basename(m.group(2)), []).append(m.group(1))
    if not bad:
        print('ALL OK'); sys.exit(0)
    print(f'\n{bad} problem(s) above. NOT OK -- these pages fail (a page is only OK when it passes EVERY section):')
    for pg, kinds in sorted(failed.items()): print(f'  {pg}: {", ".join(dict.fromkeys(kinds))}')
    print('Fix ALL of them in one pass -- read each OVER line, edit every page listed, and only then rerun\n'
          'buildall once; rerunning after each small edit burns a round trip per box. When a box is short, cut\n'
          'words or drop a block (the hint under each page says which); do not creep heights up a few px at a time.')
    print('Fix every page listed, whoever wrote it and whenever: pages submitted earlier, pages written in a\n'
          'previous plan step and cover / catalog / section / ending pages count too. Edit the source, rerun\n'
          'buildall until ALL OK. A page that is already in the document is redone as a whole: first\n'
          '`slide pages delete` at its page_index, then `slide pages addjsx` at that same page_index\n'
          '(addjsx INSERTS -- without the delete the page appears twice). Pages not submitted yet are just\n'
          'submitted as usual. Do not export or deliver while this list is not empty.')
    sys.exit(1)

# ---- fit: does the content fit the box it was written into? -----------------------------------
_FIT_TAG = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9]*)((?:[^<>]|=>)*?)(/?)>", re.S)
_NUM = re.compile(r"^-?\d+(?:\.\d+)?$")
_LEAF = ('Text', 'Image', 'Chart', 'Table', 'FAIcon', 'QRCode', 'CodeBlock', 'Math', 'svg', 'br')

class _N:
    __slots__ = ('tag', 'st', 'line', 'lines', 'kids', 'raw')
    def __init__(s, tag, st, line): s.tag, s.st, s.line, s.lines, s.kids, s.raw = tag, st, line, [], [], False

def _style_dict(attrs):
    """One tag's inline style={{ ... }} as {property: raw value}."""
    m = re.search(r"style=\{\{", attrs)
    if not m: return {}
    i, depth = m.end(), 2
    while i < len(attrs) and depth:
        if attrs[i] == '{': depth += 1
        elif attrs[i] == '}': depth -= 1
        i += 1
    parts, cur, depth, q = [], '', 0, ''
    for ch in attrs[m.end():i - 2]:
        if q:
            cur += ch
            if ch == q: q = ''
            continue
        if ch in '"\'': q = ch; cur += ch; continue
        if ch in '([{': depth += 1
        elif ch in ')]}': depth -= 1
        if ch == ',' and depth == 0: parts.append(cur); cur = ''; continue
        cur += ch
    parts.append(cur)
    out = {}
    for p in parts:
        if ':' not in p: continue
        k, v = p.split(':', 1)
        out[k.strip().strip("'\"")] = v.strip()
    return out

def _px(v, base=None):
    """A style value in pixels: 12, '12px', or '50%' of base. None when it cannot be resolved."""
    if v is None: return None
    v = str(v).strip().strip("'\"")
    if _NUM.match(v): return float(v)
    if v.endswith('px') and _NUM.match(v[:-2]): return float(v[:-2])
    if v.endswith('%') and _NUM.match(v[:-1]): return None if base is None else float(v[:-1]) / 100 * base
    return None

def _edges(st, key):
    """(top, right, bottom, left) for padding / margin, from the shorthand and the per-side keys."""
    t = r = b = l = 0.0
    raw = st.get(key)
    if raw is not None:
        nums = [n for n in (_px(x) for x in str(raw).strip().strip("'\"").split()) if n is not None]
        if len(nums) == 1: t = r = b = l = nums[0]
        elif len(nums) == 2: t = b = nums[0]; r = l = nums[1]
        elif len(nums) == 3: t, r, b = nums[:3]; l = r
        elif len(nums) >= 4: t, r, b, l = nums[:4]
    for i, side in enumerate(('Top', 'Right', 'Bottom', 'Left')):
        v = _px(st.get(key + side))
        if v is None: continue
        t, r, b, l = (v, r, b, l) if i == 0 else (t, v, b, l) if i == 1 else (t, r, v, l) if i == 2 else (t, r, b, v)
    return t, r, b, l

def _border(st):
    def w(k):
        m = re.match(r"\s*'?\s*(\d+(?:\.\d+)?)px", str(st.get(k, '') or ''))
        return float(m.group(1)) if m else None
    a = w('border') or 0.0
    return tuple(w('border' + s) if w('border' + s) is not None else a for s in ('Top', 'Right', 'Bottom', 'Left'))

def _advance(ch, mono):
    """Advance width of one character in em — the model the presets quote for counting lines."""
    o = ord(ch)
    if o >= 0x1100 or 0x2010 <= o <= 0x203F: return 1.0
    if mono: return 0.6
    if ch == ' ': return 0.3
    if 'A' <= ch <= 'Z': return 0.75
    if 'a' <= ch <= 'z' or ch.isdigit(): return 0.55
    return 0.5

def _runs(inner):
    """A <Text>'s body as lines of (text, span style): <br /> breaks a line, spans keep their own size."""
    lines, cur, stack, i = [], [], [], 0
    def put(s):
        s = re.sub(r"^\s*\n\s*|\s*\n\s*$", '', s)            # newlines next to a tag vanish (JSX)
        s = re.sub(r"\s*\n\s*", ' ', s).replace('&nbsp;', ' ')  # a newline between words becomes ONE space (JSX)
        if s: cur.append((s, stack[-1] if stack else {}))
    while i < len(inner):
        m = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9]*)?((?:[^<>]|=>)*?)(/?)>").search(inner, i)
        if not m: put(inner[i:]); break
        put(inner[i:m.start()])
        name, close, selfc = (m.group(2) or ''), m.group(1), m.group(4)
        if name == 'br': lines.append(cur); cur = []
        elif name == 'span' and not close and not selfc: stack.append(_style_dict(m.group(3)))
        elif name == 'span' and close and stack: stack.pop()
        i = m.end()
    lines.append(cur)
    return [ln for ln in lines if any(t.strip() for t, _ in ln)] or []

def _close_at(src, pos, name):
    """(inner end, resume) for the tag that was opened just before pos."""
    depth = 1
    for m in re.finditer(r"<(/?)" + name + r"\b((?:[^<>]|=>)*?)(/?)>", src[pos:], re.S):
        if m.group(1): depth -= 1
        elif not m.group(3): depth += 1
        if not depth: return pos + m.start(), pos + m.end()
    return len(src), len(src)

def _parse(src):
    root = _N('root', {}, 0); stack, i = [root], 0
    while True:
        m = _FIT_TAG.search(src, i)
        if not m: break
        close, name, attrs, selfc = m.group(1), m.group(2), m.group(3), m.group(4)
        if close:
            if len(stack) > 1 and stack[-1].tag == name: stack.pop()
            i = m.end(); continue
        n = _N(name, _style_dict(attrs), src.count('\n', 0, m.start()) + 1)
        stack[-1].kids.append(n)
        if name == 'Text' and not selfc:
            end, after = _close_at(src, m.end(), 'Text'); inner = src[m.end():end]
            n.lines = _runs(inner); n.raw = bool(re.search(r"[^\s<>]\s*\n\s*[^\s<>]", inner)); i = after; continue
        if name == 'svg' and not selfc:
            for k in ('width', 'height'):
                a = re.search(r"\b" + k + r"=[\"']?\{?(\d+(?:\.\d+)?)", attrs)
                if a and k not in n.st: n.st[k] = a.group(1)
            end, after = _close_at(src, m.end(), 'svg')
            n.lines = [attrs, src[m.end():end]]
            i = after; continue
        if not selfc and name not in _LEAF: stack.append(n)
        i = m.end()
    return root

def _inherit(st, parent):
    """Font context a node passes to its children: (fontSize, lineHeight, letterSpacing, family)."""
    fs, lh, ls, fam = parent
    return (_px(st.get('fontSize')) or fs, _px(st.get('lineHeight')) or lh,
            _px(st.get('letterSpacing')) if st.get('letterSpacing') is not None else ls,
            str(st.get('fontFamily') or fam).strip("'\""))

def _line_w(runs, ctx):
    fs, _lh, ls, fam = ctx
    w = 0.0
    for text, sst in runs:
        f = _px(sst.get('fontSize')) or fs
        sp = _px(sst.get('letterSpacing')) if sst.get('letterSpacing') is not None else ls
        mono = 'Courier' in str(sst.get('fontFamily') or fam)
        w += sum(_advance(c, mono) for c in text) * f + (sp or 0.0) * len(text)
    return w

def _flow(n): return [k for k in n.kids if str(k.st.get('position', '')).strip("'\"") != 'absolute']

def _max_w(n, ctx, avail=None):
    """Width the node wants when nothing forces it to wrap (flexbox max-content)."""
    st = n.st
    ex = _px(st.get('width'), avail)
    pt, pr, pb, pl = _edges(st, 'padding'); bt, br_, bb, bl = _border(st)
    ml = _edges(st, 'margin')[3] + _edges(st, 'margin')[1]
    if ex is not None: return ex + ml
    if n.tag == 'Text':
        c = _inherit(st, ctx)
        return (max([_line_w(l, c) for l in n.lines] or [0.0]) + pl + pr + bl + br_ + ml)
    if n.tag in _LEAF: return ml
    kids, c = _flow(n), _inherit(st, ctx)
    if not kids: return pl + pr + bl + br_ + ml
    inner = [_max_w(k, c) for k in kids]
    gap = _px(st.get('gap')) or 0.0
    room = sum(inner) + gap * (len(inner) - 1) if 'row' in str(st.get('flexDirection', '')) else max(inner)
    return room + pl + pr + bl + br_ + ml

def _min_w(n, ctx, avail=None):
    """Width below which the node cannot shrink (nowrap text cannot shrink at all)."""
    st = n.st
    ex = _px(st.get('width'), avail)
    if ex is not None: return ex
    if n.tag == 'Text':
        c = _inherit(st, ctx)
        if 'nowrap' in str(st.get('whiteSpace', '')): return _max_w(n, ctx)
        return max([max([_line_w([(w, s)], c) for w, s in l] or [0.0]) for l in n.lines] or [0.0]) * 0.12 + 1
    if n.tag in _LEAF: return 0.0
    kids, c = _flow(n), _inherit(st, ctx)
    if not kids: return 0.0
    pt, pr, pb, pl = _edges(st, 'padding'); bt, br_, bb, bl = _border(st)
    inner = [_min_w(k, c) for k in kids]
    return (sum(inner) if 'row' in str(st.get('flexDirection', '')) else max(inner)) + pl + pr + bl + br_

def _row_widths(kids, cw, gap, ctx):
    """Resolve a row's child widths the way flexbox does: explicit, then flex share, then max-content shrunk to fit."""
    n = len(kids)
    basis, grow, fixed = [], [], []
    for k in kids:
        ex = _px(k.st.get('width'), cw)
        fl = _px(str(k.st.get('flex', '')).split()[0]) if k.st.get('flex') is not None else None
        basis.append(ex if ex is not None else (0.0 if fl is not None else _max_w(k, ctx)))
        grow.append(fl); fixed.append(ex is not None)
    free = cw - gap * max(0, n - 1) - sum(basis)
    pool = [i for i, g in enumerate(grow) if g is not None]
    out = list(basis)
    if pool and free > 0:
        units = sum(grow[i] or 1.0 for i in pool) or 1.0
        for i in pool: out[i] += free * (grow[i] or 1.0) / units
    elif free < 0:
        shrink = [i for i in range(n) if not fixed[i]] or list(range(n))
        total = sum(basis[i] for i in shrink) or 1.0
        for i in shrink:
            out[i] = max(_min_w(kids[i], ctx), basis[i] + free * basis[i] / total)
    return out

def _fit(n, avail_w, avail_h, ctx, hits, sized=True):
    """Lay the node out in (avail_w, avail_h); return the height it actually needs.
    `sized`: the node has a definite width (its own, a stretched column parent's, or a flex share). Text inside an
    auto-width container is measured by the WeCom compiler at its one-line width: if that is wider than the room the
    row leaves it, the box is placed as ONE line but drawn wrapped, so it runs down behind the block below."""
    import math
    st = n.st
    if _px(st.get('width'), avail_w) is not None: sized = True
    pt, pr, pb, pl = _edges(st, 'padding'); bt, br_, bb, bl = _border(st)
    mt, mr, mb, ml = _edges(st, 'margin')
    absolute = str(st.get('position', '')).strip("'\"") == 'absolute'
    w = _px(st.get('width'), avail_w)
    if w is None and not absolute: w = None if avail_w is None else avail_w - ml - mr
    if w is None and absolute and avail_w is not None:
        lft, rgt = _px(st.get('left'), avail_w), _px(st.get('right'), avail_w)
        if lft is not None and rgt is not None: w = avail_w - lft - rgt
    cw = None if w is None else max(0.0, w - pl - pr - bl - br_)
    h = _px(st.get('height'), avail_h)
    ch = None if h is None else max(0.0, h - pt - pb - bt - bb)
    c = _inherit(st, ctx)

    if n.tag == 'Text':
        fs, lh, _ls, _fam = c
        if lh > 4: lh = lh / fs
        nowrap = 'nowrap' in str(st.get('whiteSpace', ''))
        rows, widest = 0, 0.0
        for ln in n.lines:
            wide = _line_w(ln, c); widest = max(widest, wide)
            rows += 1 if (nowrap or not cw) else max(1, math.ceil(wide / cw - 1e-6))
        if nowrap and cw and widest > cw + 1:
            hits.append((n.line, f'{fs:.0f}px nowrap text needs {widest:.0f}px, its column is {cw:.0f}px wide', widest - cw))
        elif not sized and cw and widest > cw + 1:
            hits.append((n.line, f'{fs:.0f}px text in a container with no fixed width needs {widest:.0f}px on one line but only '
                         f'{cw:.0f}px is left in the row: the compiler places it as ONE line and it runs down behind the block '
                         f'below -- break it with <br /> so every line fits, or give the container a width', widest - cw))
        if n.raw:
            hits.append((n.line, 'a raw line break inside <Text>: JSX turns it into a space, not a new line -- write <br />', 0.0))
        return rows * fs * lh * 1.2 + pt + pb + bt + bb + mt + mb   # the compiler's line box is 1.2 x the declared lineHeight (measured on exports: 76px/1.1 -> 100.5px, 15px/1.55 -> 28px, no lineHeight -> 1.2em)

    if n.tag in _LEAF: return (h if h is not None else 0.0) + mt + mb

    kids = _flow(n)
    row = 'row' in str(st.get('flexDirection', ''))
    gap = _px(st.get('gap')) or 0.0
    widths = _row_widths(kids, cw, gap, c) if (row and cw is not None) else [None if cw is None else cw] * len(kids)
    heights = []
    stretch = str(st.get('alignItems', 'stretch')).strip("'\"") == 'stretch'
    for k, kw in zip(kids, widths):
        ks = sized and (k.st.get('flex') is not None if row else stretch)   # own width is picked up inside _fit
        need = _fit(k, kw, ch, c, hits, ks)
        fix = _px(k.st.get('height'), ch)
        km = _edges(k.st, 'margin')
        heights.append((fix + km[0] + km[2]) if fix is not None else need)
    for k in n.kids:
        if str(k.st.get('position', '')).strip("'\"") == 'absolute':
            _fit(k, cw, ch, c, hits, k.st.get('left') is not None and k.st.get('right') is not None)
    inner = (max(heights) if row else sum(heights) + gap * (len(heights) - 1)) if heights else 0.0
    need = inner + pt + pb + bt + bb
    if h is not None and need > h + max(2.0, 0.015 * h):
        hits.append((n.line, f'the children need {need:.0f}px, this box is {h:.0f}px tall', need - h))
    return (h if h is not None else need) + mt + mb

_ESC_NL = re.compile(r"""(['"])(?:[^'"\\\n]|\\.)*?\\n(?:[^'"\\\n]|\\.)*?\1""")

def _escaped_nl_hits(src):
    r"""String literals holding a \n escape. The compiler renders it as a real line break, but the height
    estimate only sees the interpolation ({d[1]}) or one joined line, so such a box silently comes out
    taller than measured and runs over whatever sits below it. Write <br /> instead (or split the data)."""
    hits = []
    for m in _ESC_NL.finditer(src):
        ln = src.count('\n', 0, m.start()) + 1
        txt = m.group(0)
        n = txt.count('\\n')
        hits.append((ln, rf"a \n escape inside a string literal ({n} of them): the compiler draws it as a real "
                         rf"line break, but the height check counts ONE line -- the box renders taller than "
                         rf"measured and overlaps the block below. Use <br /> in the <Text>, or split the value "
                         rf"into separate <Text> elements: {txt[:58]}", 0.0))
    return hits

_BR_IN_STR = re.compile(r"""(['"])(?:[^'"\\\n]|\\.)*?<br\s*/?>(?:[^'"\\\n]|\\.)*?\1""")

def _in_jsx_text(src, pos):
    """True when pos sits in JSX text (child text of a tag), not inside a {...} JS expression. A quote mark
    there is a literal character, so a '<br />' next to it is a real JSX line break, not text in a string."""
    depth, q, i = 0, '', 0
    while i < pos:
        ch = src[i]
        if q:
            if ch == '\\': i += 2; continue
            if ch == q: q = ''
        elif depth and ch in '\'"`': q = ch
        elif ch == '{': depth += 1
        elif ch == '}': depth = max(0, depth - 1)
        i += 1
    if depth: return False
    k = pos - 1
    while k >= 0 and src[k] not in '<>': k -= 1
    return k >= 0 and src[k] == '>'           # last tag bracket before pos is a closing '>': we are in text

def _br_in_string_hits(src):
    r"""String literals holding a <br /> tag. <br /> only works in JSX text position (a direct child of
    <Text>); inside a data-array string interpolated via {d[i]} it is inserted as PLAIN TEXT and the
    six characters render verbatim on the page. Split the value into separate <Text> elements, or drop
    the array and write the JSX out."""
    hits = []
    for m in _BR_IN_STR.finditer(src):
        br = src.find('<br', m.start())
        if br >= 0 and _in_jsx_text(src, br): continue   # the <br /> is JSX text (quotes around it are literal characters): it works
        ln = src.count('\n', 0, m.start()) + 1
        txt = m.group(0)
        hits.append((ln, f"a <br /> tag inside a string literal: interpolated strings are inserted as plain "
                         f"text, so the tag renders verbatim on the page -- split the value into separate "
                         f"<Text> elements or write the JSX out instead of a data array: {txt[:58]}", 0.0))
    return hits

# ---- layer: absolutely positioned text vs. flow-laid-out content ---------------------------------
# The flow height check (_fit) and the canvas check (_abs_hits) each look at ONE coordinate system. A block
# pinned with bottom:/top: is placed without knowing where the flow actually put the title above it, so the
# two can land on the same pixels and both checks still say OK (seen on section pages: a lead-in pinned at
# bottom:158 sat right on top of a title the flow had pushed down to y 484). This pass lays the page out with
# real coordinates and reports every absolute text box that intersects FLOW text. Left alone on purpose: text over
# an svg / image backdrop and absolute blocks overlapping each other (Venn diagrams, badges). {[...].map(...)}
# over a literal array is unrolled first; a .map the parser cannot unroll makes it skip the page, not guess.
_VIS = ('Image', 'Chart', 'Table', 'svg', 'CodeBlock', 'Math', 'QRCode')

def _is_abs(n): return str(n.st.get('position', '')).strip("'\"") == 'absolute'

def _text_w(n, ctx, cw):
    c = _inherit(n.st, ctx)
    pl, pr = _edges(n.st, 'padding')[3], _edges(n.st, 'padding')[1]
    ex = _px(n.st.get('width'), cw)
    if ex is not None: return ex
    want = max([_line_w(l, c) for l in n.lines] or [0.0]) + pl + pr
    return want if cw is None else min(cw, want)

def _place(n, x, y, avail_w, avail_h, ctx, sized, layer, out):
    """Lay n out with its border box at (x, y); append (x0, y0, x1, y1, line, layer, kind, fontSize) for every
    Text / visual leaf. `layer` is None for flow content, otherwise the line of the absolute ancestor."""
    st = n.st
    if _px(st.get('width'), avail_w) is not None: sized = True
    pt, pr, pb, pl = _edges(st, 'padding'); bt, br_, bb, bl = _border(st)
    mt, mr, mb, ml = _edges(st, 'margin')
    w = _px(st.get('width'), avail_w)
    if w is None and not _is_abs(n) and avail_w is not None: w = avail_w - ml - mr
    c = _inherit(st, ctx)
    need = _fit(n, avail_w, avail_h, ctx, [], sized) - mt - mb
    h = _px(st.get('height'), avail_h)
    h = need if h is None else h
    if n.tag == 'Text':
        tw = _text_w(n, ctx, w if w is not None else avail_w)
        op = _px(st.get('opacity'))
        if not (c[0] >= 150 or (op is not None and op < 0.5)):   # watermark numerals / ghosted text are decoration
            out.append((x, y, x + tw, y + h, n.line, layer, 'Text', c[0]))
        return
    if n.tag in _LEAF:
        if n.tag in _VIS and w is not None: out.append((x, y, x + w, y + h, n.line, layer, n.tag, 0.0))
        if n.tag == 'svg' and layer is not None and w and h and len(n.lines) == 2:
            for sx0, sy0, sx1, sy1 in _svg_shapes(n.lines[0], n.lines[1], w, h):
                out.append((x + sx0, y + sy0, x + sx1, y + sy1, n.line, layer, 'deco', 0.0))
        return
    cw = None if w is None else max(0.0, w - pl - pr - bl - br_)
    ch = max(0.0, h - pt - pb - bt - bb)
    ox, oy = x + bl + pl, y + bt + pt
    kids = _flow(n)
    row = 'row' in str(st.get('flexDirection', ''))
    gap = _px(st.get('gap')) or 0.0
    widths = _row_widths(kids, cw, gap, c) if (row and cw is not None) else [cw] * len(kids)
    stretch = str(st.get('alignItems', 'stretch')).strip("'\"") == 'stretch'
    align = str(st.get('alignItems', 'stretch')).strip("'\"")
    just = str(st.get('justifyContent', 'flex-start')).strip("'\"")
    sizes = []
    for k, kw in zip(kids, widths):
        ks = sized and (k.st.get('flex') is not None if row else stretch)
        km = _edges(k.st, 'margin')
        fix = _px(k.st.get('height'), ch)
        kh = fix if fix is not None else _fit(k, kw, ch, c, [], ks) - km[0] - km[2]
        if row: kwid = kw if kw is not None else 0.0
        elif k.tag == 'Text': kwid = _text_w(k, c, kw)
        else:
            kwid = _px(k.st.get('width'), cw)
            kwid = kwid if kwid is not None else ((kw - km[1] - km[3]) if (kw is not None and stretch) else (_max_w(k, c) - km[1] - km[3]))
        sizes.append((kwid, kh, km, ks))
    main = [(s[0] + s[2][1] + s[2][3]) if row else (s[1] + s[2][0] + s[2][2]) for s in sizes]
    room = (cw if row else ch) or 0.0
    free = room - sum(main) - gap * max(0, len(main) - 1)
    lead, step = 0.0, gap
    if free > 0 and (row or _px(st.get('height'), avail_h) is not None):
        if just == 'center': lead = free / 2
        elif just == 'flex-end': lead = free
        elif just == 'space-between' and len(main) > 1: step = gap + free / (len(main) - 1)
        elif just == 'space-around' and main: lead = free / len(main) / 2; step = gap + free / len(main)
    cur = lead
    for k, kw, (kwid, kh, km, ks) in zip(kids, widths, sizes):
        if row:
            cross = ch if ch else max([s[1] + s[2][0] + s[2][2] for s in sizes] or [0.0])
            off = (cross - kh - km[0] - km[2]) / 2 if align == 'center' else (cross - kh - km[0] - km[2]) if align == 'flex-end' else 0.0
            _place(k, ox + cur + km[3], oy + max(0.0, off) + km[0], kw, ch, c, ks, layer, out)
            cur += kwid + km[1] + km[3] + step
        else:
            off = ((cw or 0) - kwid - km[1] - km[3]) / 2 if align == 'center' else ((cw or 0) - kwid - km[1] - km[3]) if align == 'flex-end' else 0.0
            _place(k, ox + max(0.0, off) + km[3], oy + cur + km[0], kw, ch, c, ks, layer, out)
            cur += kh + km[0] + km[2] + step
    pw = w if w is not None else (avail_w or 0.0)
    for k in n.kids:
        if not _is_abs(k): continue
        ks_ = k.st
        kw_ = _px(ks_.get('width'), pw)
        lft, rgt = _px(ks_.get('left'), pw), _px(ks_.get('right'), pw)
        if kw_ is None and lft is not None and rgt is not None: kw_ = pw - lft - rgt
        if kw_ is None: kw_ = _max_w(k, c)
        kh_ = _px(ks_.get('height'), h)
        if kh_ is None: kh_ = _fit(k, kw_, h, c, [], True)
        top, bot = _px(ks_.get('top'), h), _px(ks_.get('bottom'), h)
        ax = x + (lft if lft is not None else (pw - rgt - kw_) if rgt is not None else bl + pl)
        ay = y + (top if top is not None else (h - bot - kh_) if bot is not None else bt + pt)
        _place(k, ax, ay, kw_, kh_, c, True, layer if layer is not None else k.line, out)

def _match(src, i, o, c):
    """Index just past the bracket that closes src[i] (== o), skipping string literals."""
    depth, q, j = 0, '', i
    while j < len(src):
        ch = src[j]
        if q:
            if ch == '\\': j += 2; continue
            if ch == q: q = ''
        elif ch in '\'"`': q = ch
        elif ch == o: depth += 1
        elif ch == c:
            depth -= 1
            if not depth: return j + 1
        j += 1
    return -1

def _split_top(s):
    out, cur, depth, q = [], '', 0, ''
    for ch in s:
        if q:
            cur += ch
            if ch == q: q = ''
            continue
        if ch in '\'"`': q = ch; cur += ch; continue
        if ch in '([{': depth += 1
        elif ch in ')]}': depth -= 1
        if ch == ',' and depth == 0: out.append(cur); cur = ''; continue
        cur += ch
    if cur.strip(): out.append(cur)
    return [x.strip() for x in out if x.strip()]

def _lit(v):
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in '\'"`' else None

_MAP = re.compile(r"\{\s*\[")
def _expand_maps(src):
    """Unroll {[literal, ...].map((d, i) => ( <JSX/> ))} into N copies of the JSX with d[k] / d.key / i filled
    in, so the layout pass sees the real row count and the real strings. Returns None when a .map cannot be
    unrolled (variable array, nested function body) -- the caller then skips the page instead of guessing."""
    for _ in range(50):
        m = _MAP.search(src)
        if not m: break
        a0 = m.end() - 1; a1 = _match(src, a0, '[', ']')
        if a1 < 0: return None
        mm = re.match(r"\s*\.map\(\s*\(?\s*(\w+)\s*(?:,\s*(\w+)\s*)?\)?\s*=>\s*\(", src[a1:])
        if not mm: return None
        b0 = a1 + mm.end() - 1; b1 = _match(src, b0, '(', ')')
        if b1 < 0: return None
        tail = re.match(r"\s*\)\s*\}", src[b1:])
        if not tail: return None
        var, idx, body = mm.group(1), mm.group(2), src[b0 + 1:b1 - 1]
        rows = []
        for k, el in enumerate(_split_top(src[a0 + 1:a1 - 1])):
            vals = {}
            if el.startswith('['):
                for n, v in enumerate(_split_top(el[1:-1])): vals[f'{var}[{n}]'] = _lit(v)
            elif el.startswith('{'):
                for kv in _split_top(el[1:-1]):
                    if ':' in kv:
                        kk, vv = kv.split(':', 1); vals[f'{var}.{kk.strip().strip(chr(39) + chr(34))}'] = _lit(vv)
            else: vals[var] = _lit(el)
            b = body
            if idx: b = re.sub(r"\b" + idx + r"\b(?=\s*(?:[=!<>]=?=?|\)|\}|\+|-|\*))", str(k), b)
            b = re.sub(r"\{\s*" + re.escape(var) + r"(\[\d+\]|\.\w+)?\s*\}",
                       lambda q: (vals.get(var + (q.group(1) or '')) or 'X' * 6).replace('<', '&lt;'), b)
            rows.append(b)
        src = src[:m.start()] + '\n'.join(rows) + src[b1 + tail.end():]
    if '.map(' in src or '=>' in src: return None
    # leftover JS the tag parser cannot read (ternaries, comparisons, method calls) -> the layout would be a guess
    if re.search(r"\?[^{}]*:|\b\d+\s*[<>]=?\s*\d+|\{[^{}]*\.\w+\([^{}]*\}", src): return None
    return src

_SHAPE = re.compile(r"<(rect|circle|ellipse)\b([^>]*)/?>")
def _svg_shapes(attrs, inner, w, h):
    """Solid decoration shapes inside an absolutely positioned svg, in page pixels relative to the svg box.
    Kept: rect / circle / ellipse that are filled (colour or pattern), at least 24px on both sides and cover
    less than half of the svg -- i.e. a corner mark, a bar, a stripe block. Dropped: backdrop rects, hairlines,
    sparkle dots, outline-only rings, faint (< 0.3 opacity) shapes, anything inside <defs> / <pattern>."""
    vb = re.search(r"viewBox=['\"]\s*([-\d.]+)[\s,]+([-\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)", attrs)
    vx, vy, vw, vh = (float(v) for v in vb.groups()) if vb else (0.0, 0.0, w, h)
    if not vw or not vh: return []
    kx, ky = w / vw, h / vh
    sop = re.search(r"\bopacity:\s*([\d.]+)", attrs)
    if sop and float(sop.group(1)) < 0.3: return []                  # the whole svg is a faint watermark
    inner = re.sub(r"<g\b[^>]*\bfill=['\"]none['\"][^>]*>.*?</g>", '', inner, flags=re.S)   # outline-only groups
    inner = re.sub(r"<defs\b.*?</defs>|<pattern\b.*?</pattern>|<clipPath\b.*?</clipPath>|<mask\b.*?</mask>", '', inner, flags=re.S)
    if re.search(r"<g\b[^>]*transform", inner): return []          # moved groups: geometry is not where it is written
    out = []
    for m in _SHAPE.finditer(inner):
        tag, a = m.group(1), m.group(2)
        if re.search(r"\b(?:x|y|width|height|cx|cy|r|rx|ry)=['\"][^'\"]*%", a): continue   # percent geometry
        def f(k, d=None):
            q = re.search(r"\b" + k + r"=['\"]\{?\s*([-\d.]+)", a)
            return float(q.group(1)) if q else d
        fill = re.search(r"\bfill=['\"]([^'\"]*)", a)
        if (fill and fill.group(1).strip().lower() in ('none', 'transparent')) or 'transform' in a: continue
        op = f('opacity', 1.0); fo = f('fillOpacity', 1.0)
        if op * fo < 0.3: continue
        if tag == 'rect':
            x0, y0, ww, hh = f('x', 0.0), f('y', 0.0), f('width'), f('height')
            if ww is None or hh is None: continue
        else:
            cx, cy = f('cx', 0.0), f('cy', 0.0)
            rx = f('r') if tag == 'circle' else f('rx'); ry = f('r') if tag == 'circle' else f('ry')
            if rx is None or ry is None: continue
            x0, y0, ww, hh = cx - rx, cy - ry, 2 * rx, 2 * ry
        if ww * hh >= 0.5 * vw * vh: continue                      # backdrop
        if ww * kx < 24 or hh * ky < 24: continue                   # hairline / dot
        out.append(((x0 - vx) * kx, (y0 - vy) * ky, (x0 - vx + ww) * kx, (y0 - vy + hh) * ky))
    return out

def _layer_hits(src):
    hits = []
    if '.map(' in src or '=>' in src:
        src = _expand_maps(src)
        if src is None: return hits           # data the static parser cannot unroll: stay silent rather than guess
    for top in _parse(src).kids:
        if top.tag != 'Slide': continue
        boxes = []
        _place(top, 0.0, 0.0, _px(top.st.get('width')) or 1280.0, _px(top.st.get('height')) or 720.0,
               (16.0, 1.0, 0.0, ''), True, None, boxes)
        seen = set()
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                if a[5] == b[5]: continue                      # same layer: the flow keeps them apart
                if 'deco' in (a[6], b[6]):
                    d_, t_ = (a, b) if a[6] == 'deco' else (b, a)
                    if t_[6] != 'Text' or t_[5] is not None: continue   # only flow text is checked against decoration
                    dx = min(a[2], b[2]) - max(a[0], b[0]); dy = min(a[3], b[3]) - max(a[1], b[1])
                    if dx < 8 or dy < 4 or (d_[4], t_[4]) in seen: continue
                    seen.add((d_[4], t_[4]))
                    hits.append((t_[4], f"{t_[7]:.0f}px text at x {t_[0]:.0f}-{t_[2]:.0f} y {t_[1]:.0f}-{t_[3]:.0f} runs {dx:.0f}px into the "
                                 f"decoration drawn by the svg of line {d_[4]} (a shape at x {d_[0]:.0f}-{d_[2]:.0f} y {d_[1]:.0f}-{d_[3]:.0f}). "
                                 f"Keep text left of it: give the text a width (maxWidth is ignored by the compiler) or break it with <br />", dx))
                    continue
                if a[5] is not None and b[5] is not None: continue   # two absolute blocks (Venn circles, badges) overlap on purpose
                if a[6] != 'Text' or b[6] != 'Text': continue   # svg / picture under text is a backdrop by design; text on text never is
                ab, fl = (a, b) if a[5] is not None and (b[5] is None or a[5] > b[5]) else (b, a)
                dx = min(a[2], b[2]) - max(a[0], b[0]); dy = min(a[3], b[3]) - max(a[1], b[1])
                if dx < 4 or dy < 4: continue
                key = (ab[4], fl[4])
                if key in seen: continue
                seen.add(key)
                other = 'flow' if fl[5] is None else f'absolute (line {fl[5]})'
                hits.append((ab[4], f"absolutely positioned {ab[6]} at y {ab[1]:.0f}-{ab[3]:.0f} x {ab[0]:.0f}-{ab[2]:.0f} lands on "
                             f"the {other} {fl[6]} of line {fl[4]} (y {fl[1]:.0f}-{fl[3]:.0f}): {dy:.0f}px of the two overlap. "
                             f"Absolute offsets do not move when the flow above grows -- put this block in the flow "
                             f"(drop position/top/bottom, give it a marginTop) or delete it; nudging bottom/top a few px is not a fix, "
                             f"the next longer title lands on it again", dy))
    return hits

def _slide_size_hits(src):
    hits = []
    for top in _parse(src).kids:
        if top.tag != 'Slide': continue
        w, h = _px(top.st.get('width')) or 1280.0, _px(top.st.get('height')) or 720.0   # unset = the 1280x720 default
        if (w, h) != (1280.0, 720.0):
            hits.append((top.line, f"<Slide> is {w:.0f}x{h:.0f}: every page must be exactly 1280x720 (and keep the shell's padding) "
                                   f"-- another size is stretched on export and its coordinates no longer line up with the other pages", 0.0))
    return hits

_BARE_LT = re.compile(r"<(?![A-Za-z/>!])")
def _bare_lt_hits(src):
    """A '<' in JSX text that does not open a tag ('<500ms', '< 5%', '<=') -- the compiler reads it as the start
    of an element and addjsx fails with JSX_PARSE_ERROR after the page has already been submitted."""
    hits = []
    for m in _BARE_LT.finditer(src):
        if not _in_jsx_text(src, m.start()): continue
        ln = src.count('\n', 0, m.start()) + 1
        hits.append((ln, f"a bare '<' in text ({src[m.start():m.start() + 12].splitlines()[0]!r}) is parsed as a tag and "
                         f"addjsx fails with JSX_PARSE_ERROR -- write {{'<'}} or reword it (低于 / 小于)", 0.0))
    return hits

def _fit_hits(src):
    hits = []
    for top in _parse(src).kids:
        if top.tag != 'Slide': continue
        _fit(top, _px(top.st.get('width')) or 1280.0, _px(top.st.get('height')) or 720.0,
             (16.0, 1.0, 0.0, ''), hits)
    hits += _slide_size_hits(src)
    hits += _layer_hits(src)
    hits += _escaped_nl_hits(src)
    hits += _br_in_string_hits(src)
    hits += _bare_lt_hits(src)
    return sorted(hits, key=lambda x: -x[2])

def fit(a):
    """Flag content that does not fit its container: text whose wrapped height is taller than the fixed-height
    box around it, nowrap text wider than its column, and any fixed-height box — up to the 720px Slide — whose
    children add up to more than it holds. Sizes are estimated from the type metrics the presets use."""
    bad = 0
    for p in a.pages:
        hits = _fit_hits(open(p, encoding='utf-8').read())
        print(('OVER  ' if hits else 'OK    ') + p)
        for ln, msg, over in hits[:12]:
            print(f'      line {ln}: {msg}' + (f', over by {over:.0f}px' if over > 0 else ''))
        if any('lands on the' in m for _, m, _o in hits):
            print('      -> overlap: keep all text of a page in the flow (only decoration, footer and page number may be absolute); '
                  'a lead-in under a section / cover title goes right after the title with a marginTop, not pinned with bottom:')
        if any('lands on the' not in m for _, m, _o in hits):
            print('      -> cut the words, drop a block or split the page; do not shrink the type or edit the shell')
        bad += bool(hits)
    sys.exit(1 if bad else 0)

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest='cmd', required=True)
b = sub.add_parser('build'); b.add_argument('--shell', required=True); b.add_argument('--body', required=True); b.add_argument('--vars'); b.add_argument('--manifest', help='images.json; required when the body contains <Image>'); b.add_argument('--out', required=True); b.set_defaults(fn=build)
c = sub.add_parser('check'); c.add_argument('--shell', required=True); c.add_argument('pages', nargs='+'); c.set_defaults(fn=check)
f = sub.add_parser('imgfit'); f.add_argument('--slot', required=True, help='slot WxH, e.g. 576x434'); f.add_argument('--actual', required=True, help='real picture WxH from the generator / upload result'); f.add_argument('--src', required=True); f.add_argument('--bg', help='letterbox colour, e.g. #DCEBFD'); f.set_defaults(fn=imgfit)
g = sub.add_parser('images'); g.add_argument('--manifest', help='json {url: [w, h]} written in Step6'); g.add_argument('pages', nargs='+'); g.set_defaults(fn=images)
r_ = sub.add_parser('recolor'); r_.add_argument('--map', required=True, help='json {"#old": "#new"}'); r_.add_argument('--out-dir', required=True); r_.add_argument('files', nargs='+'); r_.set_defaults(fn=recolor)
i_ = sub.add_parser('init'); i_.add_argument('--set', required=True); i_.add_argument('--out', default='.'); i_.add_argument('--map', help='colors.json for recolouring'); i_.set_defaults(fn=init)
pa = sub.add_parser('palette'); pa.add_argument('--set', required=True); pa.add_argument('--hue', type=float, required=True, help='0-360: 0 red, 30 orange, 45 gold, 90 olive, 140 green, 190 teal, 215 blue, 265 violet, 330 magenta')
pa.add_argument('--sat', type=float, default=1.0, help='saturation multiplier, e.g. 0.7 for a calmer palette'); pa.add_argument('--spread', type=float, default=1.0, help='0-1: how much of the set\'s original hue spread to keep (multi-colour sets)')
pa.add_argument('--invert', action='store_true', help='flip light and dark (light set -> dark scheme)'); pa.add_argument('--out', default='colors.json')
pa.add_argument('--min-gap', dest='min_gap', type=float, default=60.0, help="min degrees between --hue and the set's own hue; inside it, use the set's default palette instead (default 60)")
pa.add_argument('--force', action='store_true', help='derive anyway inside --min-gap (only for a brand colour the user named)'); pa.set_defaults(fn=palette)
ba = sub.add_parser('buildall'); ba.add_argument('--dir', default='.'); ba.set_defaults(fn=buildall)
ft = sub.add_parser('fit'); ft.add_argument('pages', nargs='+'); ft.set_defaults(fn=fit)
k = sub.add_parser('contrast'); k.add_argument('pages', nargs='+'); k.set_defaults(fn=contrast)
a = ap.parse_args(); a.fn(a)
