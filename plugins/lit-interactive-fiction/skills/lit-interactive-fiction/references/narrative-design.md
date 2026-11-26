# Narrative Design for Literary Interactive Fiction

Detailed craft rules for designing chapters, choices, characters, and endings. Read this before writing any story content.

## The three design pillars

1. **Meaningful choices** — every choice must materially affect story, relationships, or ending. Fake choices (all options converge with no trace) burn player trust fast.
2. **Emotional agency** — the gameplay *is* the feeling of being torn. Moral dilemmas, human struggle, love vs. self. Not puzzles.
3. **Reading rhythm** — break text into digestible beats. Use white space, pauses, and scene changes to control pace. Interactive readers abandon walls of text.

## Choice design

### The dilemma test

Before finalizing any choice node, check: would a thoughtful player hesitate? If one option is obviously "correct" or all options are just flavors of the same act, redesign.

Weak (preference): "How do you spend the evening? A) Read B) Build C) Whistle to your sister"
— acceptable for *early, tone-setting* nodes only, and each still needs a distinct reaction.

Strong (dilemma): "Your family begs from below the tree. A) Call down one comforting sentence — the vow cracks open a seam that others will later push against. B) Climb higher in silence — the vow stays pure, but this exact silence returns as a cost when your father finally speaks years later."

Both options carry a price. Neither is wrong. That hesitation is the game.

### Value axes

- Pick 3 axes named for the kernel's central tensions. For a freedom-themed work: Freedom / Wisdom / Bond. For an identity-themed work maybe: Self / Mask / Others.
- Standard choice nodes offer 3 options, one per axis, +2 each.
- Axes should be *worldviews*, not stats. The player is answering "who is this person becoming," not min-maxing.
- Display as themed icons (leaves, keys, threads) that fill as values grow. Hiding exact numbers is fine and often better.

### Butterfly effect (required, at least one)

A small, innocent-looking early choice that visibly decides someone's fate late in the story. Formula:

1. Chapter 2-ish: a minor character asks something small (a child wants to learn knots).
2. The choice looks like flavor. Do not signpost its weight.
3. Final chapter: the earlier answer determines whether that character is safe, in danger, or able to help.

This creates the "fate was written early" feeling that literary IF does better than any other medium. When implementing, store the early choice as a flag and branch the final chapter's setup text on it.

### Reaction lines

Every choice gets a one-sentence italic reaction — the immediate ripple. Rules:

- Consequence-flavored, not judgmental. "The blacksmith never spoke to you again — but he stopped calling you mad" beats "Good choice!"
- May hint at future costs without spelling them out.
- One sentence. Two at most.

## Character design

### Supporting characters need three things

- **A motivation** the player can infer
- **A flaw** that complicates their advice or love
- **A secret** they never volunteer

Example set (from a Baron in the Trees adaptation):

- The father: enforces "the correct life" — because his own youthful voyage was forbidden and he never forgave the world for it. Secret shown as an object: a yellowed ship ticket in his study, never mentioned until one late scene.
- The mentor: tells a self-deprecating story ("I only lasted one winter up there") that conceals a heavier truth (a student who copied him and fell). His every warning is secretly "I can't lose another one."
- The love interest: is quietly preparing to leave for a distant city and has told no one — because saying it aloud forces the choice between self and love.

### Secrets and player agency

Let choices determine whether secrets surface. Confront the mentor about his hypocrisy → a corner of the truth shows (a note with another name). Stay silent → the thread stays buried, revealed only in an unlockable epilogue. Either way the secret *exists* in the scene text as物件/细节 (the ticket, the note) even when unexplained — players who replay will see them differently.

## Ending design

### Personality verdicts, not grades

Each ending answers "given everything you chose, this is who he became." Never good/bad. Give each ending:

- **A name** with literary weight (化作长青 / Evergreen, not "Freedom Ending")
- **A personality tag** — one sentence of identity: "宁愿付出代价，也要靠近别人的人" ("one who would pay any price to be near others")
- **Three paragraphs**: the climax resolved in this ending's key → the aftermath → the years-later coda
- Equal dignity. The "break the premise" ending (stepping down from the tree) must feel as earned as the others — reframe it as self-determination, not failure.

### Ending resolution logic

- Final chapter presents a forced binary: honor the premise or break it.
- Breaking it → its own ending directly.
- Honoring it → resolve by highest value axis (tie-break order favoring the most relational axis reads best).

### Ending cards (extension)

A shareable card at the end containing: ending name, personality tag, an **original fictional epigraph** (write it yourself, attribute it to an in-world source like "镇志里一句被反复传抄的话" — never quote real literature), and choice statistics ("7/10 of your choices favored closeness over safety").

### Unlockable epilogues (extension)

Each ending unlocks a different side character's perspective document — the love interest's last letter, the mentor's old notebook, the child's wedding toast. Design them to resolve the secrets that stayed buried. This drives replay ("which epilogue did you get?") and discussion.

## Pacing patterns

- **Interlude scenes** (text-only, no choice) between choice nodes: 1–2 short paragraphs, atmospheric, often ending on an image rather than information.
- **The pause before the final choice**: the last dilemma deserves a beat of stillness. In prose: one short paragraph, present tense if the rest is past. In the engine: fire/ember scene effects, no music cue.
- **First-letter drop caps** and chapter eyebrows (卷一 / Book I) give scenes a "page" feeling that rewards slow reading.

## Prose register

- Match the source's *tradition*, not its sentences. A Calvino-inspired game wants lightness, irony, precision; a Kafka-inspired one wants deadpan dread.
- Concrete nouns over abstract ones: 腌橄榄和远航归来的盐味 (pickled olives and returning-ship salt) does more than "the smell of the sea."
- Trust white space. What the mother doesn't say in her voice is the emotional payload.
- Chinese prose: prefer 短句 and comma-spliced rhythm; avoid 书面化堆砌.
- English prose: keep the compression when translating — don't inflate terse Chinese into loose English. Em-dashes carry the pauses.
