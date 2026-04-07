# gitvisual Card Design

Visual design reference for the daily git summary card. Captures decisions,
rationale, and constraints so agents and contributors can make consistent
choices when modifying the renderer.

---

## Purpose

The card is a **daily progress artefact**: a snapshot of one day's git work,
intended to appear as a tile in a long-running visual collage. It must:

- Read clearly at thumbnail size (≈300px wide) for the collage mosaic
- Hold up at full size (1200px) for individual viewing
- Feel crafted, not generated — dark-themed, editorial, not "dashboard"
- Carry no gitvisual branding — the repo name and date are the identity

---

## Canvas

| Property           | Value     | Rationale                                           |
|--------------------|-----------|-----------------------------------------------------|
| Width              | 1200px    | Square-ish; safe for both screen and print crop     |
| Min height         | 0 (none)  | Height is fully content-driven; no artificial floor |
| Aspect ratio       | flexible  | Expands vertically with commit count                |
| Background         | `#1e1e28` | Deep blue-black — richer than pure black            |
| Background opacity | 0.3       | Semi-transparent PNG; composites cleanly into collages |
| Outer padding      | 72px      | 6% of width — generous breathing room              |

The background opacity is configurable (`render.background_opacity`, 0.0–1.0).
Default is 0.3 for collage use. Set to 1.0 for opaque standalone cards.

---

## Type Scale

All sizes are for a 1200px canvas. The scale is deliberately sparse — only
four sizes — to maintain strict visual hierarchy.

| Role             | Font           | Size | Color      | Usage                              |
|------------------|----------------|------|------------|------------------------------------|
| **Hero**         | Inter Bold     | 88px | `heading`  | Date (or repo name if date hidden) |
| **Summary**      | Inter Regular  | 28px | `text`     | The "what happened" narrative      |
| **Stats bar**    | Inter Bold     | 22px | `muted`    | Aggregate totals; subordinate to hero |
| **Commit msg**   | Inter Bold     | 22px | `text`     | Primary commit info                |
| **Label / meta** | JetBrains Mono | 16px | mixed      | Repo label, per-commit +/−, files  |

### Why these sizes?

- **88px hero**: ~7.3% of canvas — dominant at any viewing size, including
  thumbnail. Previously 64px with broken fonts (Inter files were HTML blobs);
  actual rendered size was Pillow's 10px bitmap default.
- **28px summary**: clearly secondary; comfortable for 1–3 sentence wrap.
- **22px stats + commit messages**: same point size, distinguished by position
  and color. Stats are muted grey above the rule; commit messages are `text`
  white below.
- **16px meta**: per-commit +/− and file counts. Reference data — small,
  de-emphasised, but green/red for quick scanning.
- **Line height (summary)**: 44px ≈ 1.57× the 28px type. Slightly open leading
  for comfortable multi-line reading.

---

## Color Palette

| Token        | Hex       | Usage                                                    |
|--------------|-----------|----------------------------------------------------------|
| `background` | `#1e1e28` | Canvas fill (at configurable opacity)                    |
| `text`       | `#dcdce6` | Body text; commit messages                               |
| `heading`    | `#64c8ff` | Hero element (date or repo name); distinguishes the "when/who" |
| `added`      | `#64c864` | Per-commit insertion counts — standard diff green        |
| `removed`    | `#ff6464` | Per-commit deletion counts — standard diff red           |
| `accent`     | `#b48cff` | Separator rule; file-modified symbol in detailed mode    |
| `muted`      | `#969696` | Repo label; aggregate stats; separators (·); file counts |
| `subheading` | `#c8a0ff` | File-modified symbol in detailed mode                    |

### Color hierarchy for stats

- **Aggregate stats bar** (`text`/`muted`): intentionally low-colour. The big
  numbers (+9471 −67) could hijack the visual hierarchy if green/red — they're
  subordinate to the hero, so they use `muted`.
- **Per-commit meta** (`added`/`removed`): colorful green/red is fine here
  because each commit's delta is small and contextual, not totals.

---

## Layout Structure

### Default (date shown)

```
┌─────────────────────────────────────┐  ← 72px top padding
│ GITVISUAL               (16px mono, muted, uppercase)
│ 7 April 2026            (88px bold, heading blue)
│
│ Created a tool that generates ...   (28px regular, 44px lh)
│
│ 10 commits · 62 files · +9471 -67   (22px bold Inter, muted)
│ ─────────────────────────────────── (2px accent rule)
│
│ feat: initial Phase 1 implementation (22px bold)
│ +5178  -27  ·  29 files              (16px mono)
│
│ fix(llm): extract quoted sentence   (22px bold)
│ +90  -11  ·  2 files                (16px mono)
│
│  ...
└─────────────────────────────────────┘  ← 72px bottom padding
```

### Date suppressed (`show_date = false`)

When `show_date = false`, the date hero is omitted. If `show_repo_name = true`
(the default), the **repo name steps up** to fill the hero slot — rendered at
88px, heading blue — so the card still has a strong visual anchor.

```
┌─────────────────────────────────────┐  ← 72px top padding
│ AGENTMAP                (88px bold, heading blue — now the hero)
│
│ Added release notes URL output ...  (28px regular)
│
│ 2 commits · 2 files · +17 -0        (22px bold, muted)
│ ─────────────────────────────────── (2px accent rule)
│ ...
└─────────────────────────────────────┘
```

Use this layout when the date is already provided by the surrounding collage
context and repeating it on each card would be redundant.

---

## Header Visibility Config

| Option            | Default | Effect                                                     |
|-------------------|---------|------------------------------------------------------------|
| `show_date`       | `true`  | Shows the 88px date hero                                   |
| `show_repo_name`  | `true`  | Shows repo name; becomes the 88px hero when date is hidden |

Both live under `[render]` in `~/.config/gitvisual/config.toml`.

---

## Why no commit hashes?

Hashes are git-internal reference IDs. They carry zero meaning to a human
reader looking at the card — you can't derive anything about the work from
`ec0ba98`. They also clutter the meta line with a visually dominant accent-
colored string that draws the eye before the message does. If you need to look
up a commit, you have the date, the message, and the repo — that's enough to
find it with `git log --oneline`.

## Why date-first, not repo-first? (default layout)

The date is the primary axis of the collage — you scroll by time. The repo
name is context. So the **date is the hero** and the **repo name is a small
label** above it.

When the collage already provides the date context, flip to `show_date = false`
so the repo name becomes the hero instead.

## Why message-first in commit blocks?

The hash used to be left-aligned and accent-colored, making it the most
visually dominant element in each commit row — but a hash carries zero meaning
to a human reader. The redesign puts the **message first** (bold, full width)
and relegates reference data (±lines, file count) to a small mono line below.

## Why no file list in compact mode?

Showing individual file paths in compact mode adds 1–4 lines per commit with
no corresponding increase in comprehension. For a card with 8–10 commits, this
can add 30–40 lines of low-value content. File paths are only shown in
`detailed` mode, where the user has explicitly opted in.

---

## Fonts

| Font           | Weight  | File                        | License |
|----------------|---------|-----------------------------|---------|
| Inter          | Regular | `Inter-Regular.ttf`         | OFL     |
| Inter          | Bold    | `Inter-Bold.ttf`            | OFL     |
| JetBrains Mono | Regular | `JetBrainsMono-Regular.ttf` | OFL     |
| JetBrains Mono | Bold    | `JetBrainsMono-Bold.ttf`    | OFL     |

**Inter** is chosen for prose/display roles: a geometric humanist sans-serif
optimised for screen legibility across sizes. Feels modern without being trendy.

**JetBrains Mono** is chosen for data roles: consistent character widths mean
numbers don't jitter when values change. Used for per-commit +/− counts, file
counts, and repo labels.

> **Note:** The bundled Inter files were previously HTML redirect blobs (not
> real TTF binaries), causing every Inter render to silently fall back to
> Pillow's 10px bitmap default. All fonts are now verified real TrueType files.

---

## Spacing Reference

All values are in pixels. Constants live in `card.py` as module-level
`_UPPER_SNAKE` values.

| Constant            | Value | Between                                       |
|---------------------|-------|-----------------------------------------------|
| `_REPO_LABEL_GAP`   | 8px   | Repo label bottom → date top                  |
| `_DATE_GAP`         | 26px  | Hero element bottom → summary (or stats)      |
| `_SUMMARY_GAP`      | 20px  | Last summary line → stats bar                 |
| `_STATS_GAP`        | 16px  | Stats bar → separator region                  |
| `_RULE_PAD`         | 14px  | Breathing room each side of the rule          |
| `_COMMIT_MSG_EXTRA` | 6px   | Last message line → meta line                 |
| `_COMMIT_GAP`       | 18px  | Between commit blocks                         |
| meta line height    | `small_text_size + 8` | Dynamic, not hardcoded          |

---

## What to Avoid

- **Don't show commit hashes.** They carry no meaning on the card and their
  accent color makes them visually dominant over the message.
- **Don't show the tool name on the card.** The repo name is identity enough.
- **Don't use bright green/red for aggregate stats.** Reserve those colors for
  per-commit deltas. The aggregate totals should be `muted` so they don't
  compete with the hero element.
- **Don't hardcode colors.** Use `pal.X` tokens so theme switching works
  without touching layout code.
- **Don't use global `line_height` for everything.** That constant is for
  summary text only. Commit blocks use explicit per-element heights.
- **Don't pad more between commits than between the summary and the rule.**
  The commit list is a unit; the summary/stats/rule is a header. Too much
  intra-list spacing breaks that grouping.
- **Don't set a large `min_card_height`.** Let the height be content-driven.
  A 2-commit day should produce a short card, not a tall one with empty space.
