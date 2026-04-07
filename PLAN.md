# gitvisual — Design Plan

## Purpose

A Python CLI tool that generates visual cards/infographics from git commit history.

**Primary use case:** Ryan's image-a-day collage project. Each day a few images from that day are assembled into a collage. Coding activity cards are one component alongside other daily photos/art. The tool needs to handle multiple active repos gracefully — some days many projects have changes, some days just one.

---

## Architecture

### Project Layout

```
gitvisual/
├── pyproject.toml              # uv project, hatchling build, entry point
├── Makefile                    # install, test, lint, fmt, typecheck, ci, clean
├── AGENTS.md                   # agent instructions (TDD, beads, fast path)
├── opencode.json               # opencode config (model, MCP servers)
├── scripts/
│   └── agent-run.sh            # wraps build/test commands, captures output
├── src/
│   └── gitvisual/
│       ├── __init__.py
│       ├── cli.py              # typer CLI entry point
│       ├── config.py           # TOML config loading/defaults (pydantic)
│       ├── git/
│       │   ├── __init__.py
│       │   ├── collector.py    # git data extraction via subprocess
│       │   └── models.py       # FileChange, Commit, DaySummary, Report (pydantic)
│       ├── llm/
│       │   ├── __init__.py
│       │   └── summarizer.py   # litellm integration, Summarizer protocol
│       └── render/
│           ├── __init__.py
│           ├── card.py         # Phase 1: polished data cards (Pillow)
│           ├── components.py   # Reusable drawing helpers (fonts, wrap, badges)
│           └── themes.py       # Color palettes, font path resolution
├── assets/
│   └── fonts/                  # Bundled fonts: Inter + JetBrains Mono (OFL)
└── tests/
    ├── conftest.py             # shared fixtures, git repo factories
    ├── test_models.py
    ├── test_git_collector.py
    ├── test_summarizer.py
    ├── test_card_renderer.py
    ├── test_config.py
    └── test_cli.py             # typer CliRunner integration tests
```

### Core Pipeline

```
Repos + DateRange
    → GitCollector.collect()        # subprocess git calls → raw commit data
    → DaySummary                    # structured pydantic model per repo per day
    → Summarizer.summarize()        # LLM generates 1-2 sentence narrative (optional)
    → Summarizer.group_commits()    # LLM clusters commits into semantic groups (optional)
    → CardRenderer.render()         # Pillow → PNG card image
    → Output files (PNG)
```

---

## Data Models (pydantic, frozen)

```python
class FileChange:
    path: str
    status: str          # "Added" | "Modified" | "Deleted" | "Renamed" | "Copied"
    insertions: int
    deletions: int

class Commit:
    hash: str            # full SHA
    short_hash: str      # 7-char abbreviation
    message: str         # subject line
    body: str            # full body (may be empty)
    author: str
    email: str
    timestamp: datetime
    files: list[FileChange]
    insertions: int
    deletions: int
    files_changed: int

class CommitGroup:
    summary: str          # LLM-generated group label/description
    commits: list[Commit]
    # Aggregate properties (computed from commits):
    total_insertions: int
    total_deletions: int
    total_files_changed: int

class DaySummary:
    date: date
    repo_name: str
    repo_path: Path
    commits: list[Commit]
    total_insertions: int
    total_deletions: int
    total_files_changed: int
    summary: str | None               # LLM-generated narrative, None if skipped
    commit_groups: list[CommitGroup] | None  # LLM-grouped commits, None if skipped

class Report:
    date_range: tuple[date, date]
    repos: list[str]
    days: list[DaySummary]
```

---

## CLI Interface

```bash
# Single day, single repo
gitvisual generate ./my-repo --date 2025-04-07

# Multiple repos
gitvisual generate ./repo1 ./repo2 --date 2025-04-07

# Date range
gitvisual generate ./repo1 --from 2025-04-01 --to 2025-04-07

# Shortcuts
gitvisual generate ./repo1 --yesterday
gitvisual generate ./repo1 --last-week

# Output control
gitvisual generate ./repo1 --output ./cards/
gitvisual generate ./repo1 --style compact    # compact | detailed
gitvisual generate ./repo1 --summarize        # opt-in LLM summary
gitvisual generate ./repo1 --no-summary       # skip LLM (also the default)

# Repo discovery: scan a directory tree for repos with activity on a date
gitvisual discover ~/Documents/Projects --date yesterday
gitvisual discover ~/Documents/Projects --date today --generate  # discover + generate

# Config management
gitvisual config init    # write example config to ~/.config/gitvisual/config.toml
gitvisual config show    # print resolved config
```

---

## Configuration (`~/.config/gitvisual/config.toml`)

```toml
[defaults]
output_dir = "."
theme = "dark"
style = "compact"   # "compact" | "detailed"
summarize = false   # opt-in; avoids accidental LLM calls

[llm]
provider = "openrouter"
model = "anthropic/claude-3-haiku"
api_key_env = "OPENROUTER_API_KEY"   # name of env var to read
api_base = ""                         # optional custom base URL
max_tokens = 200
max_tokens_grouping = 4096            # separate budget for group_commits() call
timeout = 30

[render]
card_width = 1200
min_card_height = 1200
padding = 60
style = "compact"
max_files_shown = 12
max_groups_shown = 10                 # cap on commit groups rendered on card

[repos]
scan_dirs = []
exclude = ["node_modules", "vendor", ".cache", "dist", "build"]

[theme]
background = "#1e1e28"
text       = "#dcdce6"
heading    = "#64c8ff"
added      = "#64c864"
removed    = "#ff6464"
accent     = "#b48cff"
muted      = "#969696"
subheading = "#c8a0ff"
```

Config is loaded via deep-merge: user file values override defaults; missing sections fall back to code defaults. Every command works with no config file present.

---

## Phase Plan

### Phase 1 — Polished Data Cards *(current focus)*

Goal: a CLI that takes a repo path + date and produces a clean, dark-themed PNG card suitable for inclusion in a daily collage.

**Card layout (compact style):**
- Header: repo name · date
- LLM summary (if enabled), word-wrapped
- Aggregate stats bar: N commits · N files · +insertions −deletions
- Horizontal rule
- If commit_groups available: per-group sections with group label + aggregate stats,
  each showing member commit hashes + messages (capped by max_groups_shown)
- Fallback (no groups): per-commit rows: short hash, message (wrapped), ±stats, file list (capped)

**Card layout (detailed style):**
- Same as compact but all files shown, no cap

**Visual design decisions:**
- Dark background (#1e1e28), light text (#dcdce6)
- Heading accent in blue (#64c8ff), added green, removed red, accent purple
- Bundled fonts: Inter (body/headings) + JetBrains Mono (hashes, stats)
- System font fallback if bundled fonts not found (acceptable degradation)
- Aspect ratio: soft 1:1 target; height expands with content (v1 simplification)
- Output: RGBA PNG, 1200px wide by default

**Steps completed:**
1. Project scaffolding (pyproject.toml, Makefile, AGENTS.md, scripts/)
2. Data models (FileChange, Commit, DaySummary, Report)
3. Git collector (subprocess git calls, stats parsing, initial commit edge case)
4. LLM summarizer (LLMSummarizer, StubSummarizer, NullSummarizer, factory)
5. Card renderer (CardRenderer, FontSet, theme system, compact + detailed)
6. CLI (generate, discover, config init/show — typer)
7. All tests passing, mypy clean, ruff clean
8. LLM commit grouping: CommitGroup model, group_commits() on all summarizer types,
   card renderer groups path (_draw_commit_group), max_groups_shown config,
   max_tokens_grouping config, --json includes commit_groups for debugging

**Remaining Phase 1 work:**
- Download and bundle Inter + JetBrains Mono `.ttf` files into `assets/fonts/`
- First real end-to-end smoke test against an actual repo
- `tests/test_cli.py` — CLI integration tests via typer `CliRunner`
- Initial git commit of the full codebase

### Phase 2 — Chart Components

- Contribution heatmap (GitHub-style calendar grid)
- Insertions/deletions bar charts over time
- File change treemap
- Language/extension breakdown donut chart
- Activity timeline (commits per hour of day)
- Implementation: matplotlib, rendered to Pillow image and composited

### Phase 3 — Full Infographics / Dashboard Layouts

- Dashboard-style composite layouts (multiple chart components in a grid)
- Weekly and monthly summary formats
- Combined multi-repo cards (all repos in one image for days with many active)
- Auto-decision mode: combined card when many repos active, separate when few
- Possible migration to Cairo/SVG for more layout flexibility at this stage

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python 3.12+ | Existing script, ecosystem fit |
| CLI framework | typer | Type-hint driven, auto-generates help |
| Data models | pydantic (frozen) | Validation + immutability |
| Config format | TOML | stdlib tomllib in 3.11+, human-friendly |
| Git data | subprocess + git CLI | No extra deps, full git compatibility |
| Image rendering | Pillow (Phase 1) | Lightweight, sufficient for card layout |
| Chart rendering | matplotlib (Phase 2) | Standard, good chart types |
| LLM | litellm | Model-agnostic; OpenRouter/OpenAI/Anthropic/Ollama all work |
| Fonts | Bundle Inter + JetBrains Mono (OFL) | Consistent output across machines |
| Aspect ratio | Soft 1:1, height expands | Avoids truncation complexity in v1 |
| LLM default | off (`--summarize` opt-in) | Avoid accidental API calls |
| Commit grouping | structured JSON output from LLM | Reliable parsing; group_commits() separate from summarize() |
| Issue tracking | beads (`bd`) | Project convention |

---

## Test Strategy

TDD throughout: failing test first, minimum code to pass, then refactor.

```
tests/
├── conftest.py              # fixtures: make_file_change, make_commit,
│                            #   make_day_summary, init_git_repo,
│                            #   make_commit_in_repo
├── test_models.py           # pydantic model validation, computed props
├── test_git_collector.py    # uses real tmp_path git repos
├── test_summarizer.py       # mocked litellm, all three summarizer types
├── test_card_renderer.py    # image dimensions, valid PNG, no crash on edge cases
├── test_config.py           # load/merge/defaults/write_example
└── test_cli.py              # typer CliRunner, all commands + flags
```

Renderer tests verify:
- Output image dimensions match config
- Image is valid RGBA PNG
- No crash on empty days, very long commit messages, Unicode, many files

CI gate (`make ci`): ruff lint → mypy typecheck → pytest

---

## Collage Use Case Notes

The intended output workflow:
1. End of day, run `gitvisual discover ~/Projects --date today --generate --output ~/daily-cards/`
2. This finds all repos with commits today, generates one PNG per repo (or a combined card)
3. Those PNGs are pulled into the daily collage alongside photos, sketches, etc.
4. Cards must look good at reduced size in a collage — avoid tiny text, keep high contrast

This informs layout density: even "compact" mode should not be information-overloaded. The soft 1:1 target (expanding height) is intentional — a card that's taller than wide still composites well.
