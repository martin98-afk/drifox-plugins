---
name: lit-interactive-fiction
description: Turns any book, play, or story — copyrighted ones included, via a built-in originalization path — into a playable single-file HTML interactive fiction game. Use for interactive fiction, text adventures, 互动小说, 文字互动游戏, or extending an existing literary IF game.
---

# Literary Interactive Fiction

Turn a literary work into an original, playable, single-file HTML interactive fiction game. The output honors the source's *spirit* while being legally safe and creatively independent — original characters, original plot, original prose.

## Core workflow

1. **Extract the kernel** — identify the source's philosophical core; run the copyright check
2. **Originalize** — invent new characters, places, and events that embody that kernel
3. **Design the narrative structure** — chapters, choice nodes, value axes, endings
4. **Design meaningful choices** — real dilemmas, butterfly effects, characters with secrets
5. **Build the HTML game** — use the scene-engine template in `assets/`
6. **Generate shareable assets** — ending cards, three-platform social copy
7. **Offer extensions** — second language, unlockable epilogues, dialogue-mode variant, deployment

Read `references/narrative-design.md` before designing chapters and choices — it contains the detailed craft rules (meaningful choices, character secrets, ending design, pacing). Read `references/html-engine.md` before writing code — it documents the template's architecture so edits go in the right place.

---

## Step 1: Extract the kernel

Ask: what is this work *about* beneath its plot? One sentence.

- *The Baron in the Trees* → "defining freedom through one irrevocable choice"
- *Invisible Cities* → "every city is a way of describing desire and memory"
- *The Metamorphosis* → "what remains of a person when their usefulness ends"
- *Hamlet* → "every hesitation defines who you are"
- *The Diary of a Madman* → "you choose what to believe: your eyes or the order"

The kernel — not the plot — is what the game adapts. This single sentence drives every design decision that follows.

If the user hasn't named a specific work, help them pick one whose kernel naturally produces dilemmas (works about choices, identity, freedom, love vs. duty adapt well; pure atmosphere pieces are harder).

### Copyright check

Verify the work's status before proceeding:

| Region | Rule | Example |
|--------|------|---------|
| China/EU | Author died + 70 years | Lu Xun (d. 1936) → PD since 2006 |
| US | Published + 95 years OR author died + 70 years | Kafka (d. 1924) → PD |
| Global | Ancient/classical texts | Shakespeare, Homer, Dream of the Red Chamber |

**Public domain → proceed to Step 2** (direct adaptation is allowed; still originalize fully — it makes a better game).

**Copyrighted → offer the two paths:**

> "《[作品名]》仍在版权保护期内（[作者]，预计 [年份] 年进入公域）。两条路径：
>
> **A. 公共领域替代** — 主题相近的公域作品：[列 2-3 部，附作者与 PD 年份]
>
> **B. 内核原创** — 提取《[作品名]》的哲学内核（[一句话]），生成完全原创的互动叙事：所有角色、地名、情节、意象均为原创，与原作无对应关系，封面注明 'inspired by' 致敬。
>
> 选 A 还是 B？"

Path B is legitimate and well-tested — a game built this way shares only an *idea* with the source, and ideas are not copyrightable. What it must never share: names, scenes, plot sequences, or prose. If the user asks to reproduce actual text, characters, or recognizable scenes from a copyrighted work, decline that specific request and restate the A/B options.

---

## Step 2: Originalize

Everything player-facing must be original. "Originalize" means transform beyond renaming — create a new interpretation that stands as an independent work.

### Transformation requirements

| Element | Minimum transformation | Example |
|---------|----------------------|---------|
| Protagonist | New identity, profession, era | Hamlet (prince) → memory archivist |
| Setting | New time/place/world | Elsinore (castle) → memory library |
| Core conflict | New physical form | Revenge → discovering erased records |
| Key imagery | New metaphor system | Ghost/mirror/sword → data ghost/glitch/fragment |
| Supporting cast | New roles, relationships | Ophelia (noblewoman) → data curator |

### Originalization checklist

- [ ] Protagonist's identity would not be recognizable without the title
- [ ] Setting has no visual or textual overlap with the source
- [ ] Core conflict operates through different mechanics
- [ ] No character names from the source appear
- [ ] No iconic scenes reproduced (even with new names)
- [ ] If the source title were removed, the work stands alone
- [ ] Cover credits the inspiration honestly ("Inspired by X — all characters and story are original")

If any item fails, return to redesign.

---

## Step 3: Narrative structure

Default structure (adjust to fit the work):

- **4 chapters** following life stages or escalating stakes (e.g., 誓言 → 树冠工程 → 思想与爱 → 风暴)
- **2 choice nodes per chapter** for the first three chapters, each offering 3 options mapped to value axes
- **3 hidden value axes** named for the kernel's central tensions (e.g., 自由 Freedom / 智慧 Wisdom / 联结 Bond; 看见 Seeing / 秩序 Order / 记忆 Memory). Choices add +2 to one axis. Displayed as themed icon trackers, optionally hidden.
- **1 forced final dilemma** in the last chapter — a binary choice where one option leads to its own ending directly, and the other resolves via the highest value axis
- **4 endings**: one per axis + one for the "break the premise" choice

Chapter interludes (text-only scenes between choices) control pacing — short, atmospheric, one or two paragraphs.

---

## Step 4: Meaningful choices

This is what separates a good literary IF from a quiz. Full craft rules in `references/narrative-design.md`; the non-negotiables:

- **No fake choices.** Every option must change visible text (reaction lines at minimum) and value state; major nodes should change later scenes.
- **Dilemmas, not preferences.** The player should feel "both options cost something," not "which flavor do I like."
- **Supporting characters carry secrets** — a motivation, a flaw, and one thing they never say aloud. Secrets surface (or stay buried) based on player choices.
- **Plant at least one butterfly effect** — a small early choice that visibly determines someone's fate near the end.
- **Endings are personality verdicts, not grades.** "宁愿不被任何人需要，也要保持完整的人" — never "good ending / bad ending."

---

## Step 5: Build the game

Copy `assets/game-template.html` and replace the story data. The template is a complete working game engine (scene backgrounds with gradient fallbacks, six particle systems, light rays, mouse parallax, character portraits, WebAudio sound, stat trackers, loading screen). **Do not rebuild the engine from scratch** — only edit the clearly-marked story-data section and theme variables. Architecture details in `references/html-engine.md`.

Use the atmosphere systems for *emotional pacing*, not decoration — fireflies for intimate night scenes, stars for solitary ones, rain for grief, embers+fire for the climax, light rays for hope. Every scene's effect choice should answer "what should the player feel here?" (mapping table in `references/html-engine.md`).

Writing style for game prose (Chinese or English):

- Short paragraphs, 1–3 per scene. Interactive reading punishes walls of text.
- Restraint over declaration: show the mother's voice going quiet, don't write "you felt sad."
- Reaction lines after each choice are one sentence, italic, consequences-flavored.
- Keep the literary register of the source's tradition without imitating its sentences.

---

## Step 6: Generate shareable assets

Generate these by default after the game works. Skip only if the user explicitly wants just the game.

### 6.1 Ending cards

An in-game DOM page shown after each ending (no external libraries — html2canvas and similar break the template's zero-dependency rule; players share via screenshot, which is how sharing actually happens on mobile anyway).

Each card contains:

- Game title + ending name (e.g., "化作长青 / Evergreen")
- Personality tagline (e.g., "宁愿不被任何人需要，也要保持完整的人")
- An **original fictional epigraph** attributed to an in-world source ("镇志里一句被反复传抄的话…") — never a real quote
- Choice statistics ("7/10 of your choices favored closeness over safety")
- Unique accent color per ending, drawn from the game's palette
- Designed inside a 1200×630-proportioned frame so screenshots crop cleanly for social

### 6.2 Social copy — three platform templates

Generate all three, matched to each platform's culture:

**X/Twitter (English) — hook + mechanic + link:**
```
I turned [SOURCE]'s idea of [KERNEL] into a playable game.

[One-sentence premise]. Your choices feed three hidden values — 
and the ending tells you who you became.

4 endings · ~10 min · free in browser
[LINK]

Which ending did you get?
```

**小红书 (Chinese) — 测试型标题 + 情感钩子，配结局卡截图:**
```
标题：如果你是[主角处境]，你会是哪种结局？

正文：把[灵感来源]做成了一个互动小说游戏🌲
[一句话前提]
你的每个选择都在悄悄回答一个问题：你到底是什么样的人。

四种结局——[结局1名]/[结局2名]/[结局3名]/[结局4名]
我玩出了[X]，评论区告诉我你是哪个👇

（链接放主页/评论区）
#互动小说 #文字游戏 #[作者名]
```

**itch.io (English) — page description:**
```
[TITLE] is a short literary interactive fiction inspired by [SOURCE/AUTHOR].

[Two-sentence premise, present tense.]

Every choice feeds three hidden values. The final crisis resolves 
according to who you've become — four endings, none of them "good" 
or "bad," each a verdict on the life you chose.

~10 minutes · bilingual (EN/中文) · plays in browser · free
Tags: interactive-fiction, literary, bilingual, short, narrative
```

### 6.3 Cover image guidance

Point the user to screenshot the game's own cover page (it's designed to be poster-like), or generate a simple standalone cover HTML using the same palette variables. Don't add image-generation dependencies to the game file.

---

## Step 7: Offer extensions

After the core game and shareable assets, offer (in rough order of value):

- **Second language version** — separate HTML file, `en/index.html` structure, language switcher in both files (template includes it). Translate register, not just words; rename characters for target-audience readability (茯苓 → Ling, 老桦 → Elder Hua). Details in `references/html-engine.md`.
- **Unlockable epilogues** — each ending unlocks a different side-character's perspective document (the love interest's last letter, the mentor's old notebook). Resolves buried secrets; drives replay and discussion.
- **Dialogue-mode variant** — an alternative format where the player interviews the protagonist years later, powered by the Anthropic API with a locked character sheet (fixed biography facts, personality, reply length, never break character). Only offer if API access is available in the deployment context.
- **Deployment** — GitHub Pages (`index.html` + `en/index.html`), or itch.io for the IF community (use the 6.2 itch template for the page).

---

## Legal notice & commercial use

When delivering the finished game, always include a brief rights note to the user (in the conversation, not inside the game file). Adapt this template:

> **关于这个作品的权利状态（仅供参考，不构成法律意见）**
>
> - 路径：[公域改编 / 内核原创]。[公域改编：原作已进入公共领域，改编作品的版权归你所有，原则上可自由使用包括商用。/ 内核原创：本作仅与灵感来源共享不受版权保护的"思想"，所有表达均为原创，原则上是独立作品。]
> - 商用前请注意：① 不同法域的公域时间不同（在中国进入公域的作品在美国未必）；② 若灵感来源为外语作品，其**译本**可能仍在版权保护期，本作未使用任何译本表达；③ 个别角色名/标题可能存在商标注册；④ 商用会提高权利方关注度，"实质性相似"的判定存在灰色地带。
> - 素材：模板中的背景图片来自 Unsplash（其许可允许商用，但不得将图片本身作为主要产品转售）；音效与界面均为代码生成，无第三方素材。
> - **重要商业决策前，建议咨询知识产权律师。** 本说明不构成法律意见。

Rules for Claude when using this skill:

- Never state flatly that outputs "can" or "cannot" be commercialized — the honest answer is conditional, and both blanket permissions and blanket prohibitions are wrong.
- Public-domain adaptations and genuinely originalized kernel-creations are *generally* commercializable; the rights note explains the residual risks instead of promising safety.
- If the user's originalization is shallow (fails the Step 2 checklist) and they intend commercial use, flag the elevated risk explicitly and push the redesign before delivering.
- Do not present the "inspired by" credit as legal protection — it is honesty, not a license.

---

## Quality checklist before delivering

- [ ] Copyright check ran; copyrighted sources went through the A/B routing
- [ ] Originalization checklist passes; inspiration credited on cover
- [ ] Zero quoted or paraphrased source text anywhere (including epigraphs — write fictional ones)
- [ ] Every choice produces a distinct reaction line; no dead options
- [ ] At least one butterfly effect planted and payed off
- [ ] Final dilemma works: binary choice → one direct ending + axis-resolved endings
- [ ] All ending scenes reachable (trace each axis-dominant path mentally)
- [ ] Ending cards render with correct per-ending accent colors
- [ ] JS validated (`node --check` on the extracted script)
- [ ] Backgrounds show even with no network (gradient fallbacks intact)
- [ ] Mobile-safe (template handles this; don't break the media queries)
- [ ] Rights note delivered with the finished game (see Legal notice section)
