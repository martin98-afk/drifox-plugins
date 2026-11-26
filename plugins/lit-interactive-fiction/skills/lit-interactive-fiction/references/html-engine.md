# HTML Scene Engine Architecture

The template at `assets/game-template.html` is a complete, self-contained interactive fiction engine. This document explains its architecture so you edit the right parts and leave the machinery intact.

## Design principles

- **Single file.** No build step, no dependencies, no external JS/CSS. Playable by double-click, deployable by copy.
- **Graceful degradation.** Backgrounds have gradient fallbacks (works offline / when image CDNs are blocked). Audio wrapped in try/catch (works when WebAudio is unavailable). ES5-compatible syntax throughout.
- **Data-driven scenes.** All story content lives in one clearly-marked section. The engine below it should not need edits for a new story.

## File anatomy (top to bottom)

1. **CSS custom properties** (`:root`) — the entire color/font theme. Retheme here only.
2. **Atmosphere CSS** — scene layers, overlay gradient, particles, fire glow, mist, character portraits.
3. **UI CSS** — page card, eyebrow/chapter headers, stat tracker, story text, choices, buttons, cover, endings, audio control, language switcher, loading screen.
4. **HTML skeleton** — fixed layers (loading screen, scene bg, overlay, particles, fire, mist, portrait, lang switch, audio control) + `.stage > .book > #sceneRoot`.
5. **JS: audio system** — WebAudio tones (choice blip, page turn, fire noise, ambient drone). All guarded with try/catch and an `audioEnabled` flag.
6. **JS: scene system** — `sceneImages` (photo URLs), `sceneGradients` (fallbacks), `setScene(key, options)`, particle factories (`createLeaves/createEmbers/createSnow`).
7. **JS: portrait system** — `showCharacter(url, name, position)`.
8. **JS: game state** — `stats` object, stat rendering.
9. **JS: scene factories** — `textScene(opts)`, `choiceScene(opts)`, `showReaction`, `endingScene`.
10. **JS: STORY DATA** — `S.cover`, `S.ch1_intro` ... `S.ending_*`. **This is the section you rewrite per game.**
11. **JS: engine** — `computeEnding()`, `goto(id)`, `init()`.

## Scene node shapes

```js
// Text scene (no choice)
S.ch1_bridge = textScene({
  chapter: '卷一', roman: 'I',          // eyebrow; title optional
  paras: ['...', '...'],                 // 1-3 short paragraphs
  next: 'ch1_choiceB',
  scene: { key: 'ch1', options: { particles: 'leaves', mist: true } },
  character: { url: '...', name: '老桦', position: 'left' }  // optional
});

// Choice scene
S.ch1_choiceA = choiceScene({
  chapter: '卷一', roman: 'I', title: '誓言',
  paras: ['...'],
  options: [
    { label: '...', stat: 'freedom', delta: 2, reaction: '...', next: 'ch1_bridge' },
    { label: '...', special: 'ending_ground' }   // special = jump directly, no stat
  ],
  scene: { key: 'ch1', options: { particles: 'leaves' } }
});

// Ending
S.ending_bond = endingScene('bond', '联结', 'Title', ['para1','para2','para3']);
```

`next: '__compute_ending__'` triggers `computeEnding()` which returns `'ending_' + highest axis` (tie-break order defined in the function — put the most relational axis first).

## Scene visual options

`setScene(key, { particles, fire, mist, rays })`:
- `particles`: `'leaves' | 'embers' | 'snow' | 'fireflies' | 'rain' | 'stars'` (or omit)
- `fire: true` → orange pulsing glow + crackle noise
- `mist: false` → hide the bottom mist layer (default shown)
- `rays: true` → drifting diagonal light beams (sunlight through canopy — good for daytime/hopeful scenes)

**Matching effects to mood** (the point of having six particle types is emotional pacing, not decoration):
- `leaves` — default daytime, gentle passage of time
- `fireflies` — night scenes with warmth/wonder (first night on the tree, intimate conversations)
- `stars` — night scenes with solitude/scale (cold nights, decisions made alone)
- `rain` — grief, tension, misfortune scenes
- `embers` + `fire: true` — crisis, the climactic dilemma
- `snow` — winter, endings, elegy
- `rays: true` combines with any particle type — afternoon light, thought-and-love chapters, hopeful covers

The template also ships **mouse/gyroscope parallax** on the background (auto-disabled under `prefers-reduced-motion`). It's automatic — no per-scene config. Don't remove the `scale(1.06)` in its transform; that's what hides the edges during movement.

Every `key` needs entries in **both** `sceneImages` and `sceneGradients`. The gradient shows immediately; the photo overlays only after successful preload — never remove this two-step logic, it's what keeps the game visually alive without network.

## Adapting for a new story

1. Retheme `:root` variables if the work's palette differs (a desert story doesn't want ink-green).
2. Update `sceneImages`/`sceneGradients` keys for your chapters. Choose Unsplash (or similar hotlink-safe) images matching each chapter's mood; recolor gradients to match.
3. Rewrite the story-data section entirely: cover, chapters, choices, endings.
4. Rename `stats` keys and the labels in `renderStats()` to your value axes (three keys, consistent everywhere including `leafIconColored`'s color mapping and `computeEnding`'s order array).
5. Update loading screen text, footer note, cover credit, and `<title>`.
6. Keep character portraits optional — only use if suitable images exist; the game reads fine without them.

## Second-language version

Create a full copy of the file (not a runtime i18n layer — two files is simpler and each language's typography can be tuned):

- Swap `--font-*` variables: CJK serif stack ↔ `"EB Garamond", Georgia` stack.
- English UI text gets `text-transform: uppercase; letter-spacing: .12em` on utility elements (buttons, labels, eyebrows) — this replaces what CJK gets from its letterforms.
- Translate register, not just words. Keep compression; don't inflate.
- Rename characters for target-audience readability (single-syllable pinyin reads well: Lin, Ling, Hua).
- Language switcher links: main file → `./en/`, English file → `../`, both with `target="_self"` (the template has `<base target="_blank">`, so `_self` is required or the switcher opens new tabs).

Deploy structure:
```
repo/
  index.html        ← primary language
  en/index.html     ← second language
```

## Validation before delivery

```bash
sed -n '/<script>/,/<\/script>/p' game.html | sed '1d;$d' > /tmp/check.js
node --check /tmp/check.js
```

Also verify: every `next:` target exists in `S`; every `scene.key` exists in both image and gradient maps; every axis in choices exists in `stats`.
