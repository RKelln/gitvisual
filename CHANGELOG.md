# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.1.1] — Initial release: LLM-powered git activity cards — 2026-04-07

`gitvisual` generates clean, dark-themed PNG cards from git commit history —
suitable for daily photo collages, portfolio snapshots, or just keeping a
visual record of your work. Point it at one or more repos, get one PNG per
repo per day. Each card shows the repo name, date, aggregate stats (commits,
files, insertions, deletions), and per-commit detail. Enable `--summarize` and
the card also gets a one-sentence LLM narrative of the day's work, plus commits
semantically grouped into named clusters so the card reads like a story rather
than a raw log.

This is the first public release — fully functional Phase 1 implementation.

### Added

- `gitvisual generate <repos> --date <date>` — produce a PNG card per repo showing
  commits, stats, and optionally an LLM summary for a given day
- `gitvisual generate --discover <path>` — auto-find all repos with activity on a
  date and generate cards for each; replaces the old `discover --generate` pattern
- `gitvisual discover <path>` — list repos with activity (informational; no card output)
- `gitvisual config init` / `gitvisual config show` — write an example
  `~/.config/gitvisual/config.toml` or print the resolved config
- `--summarize` / `--model` / `--max-tokens` flags on `generate` and `discover` —
  opt-in LLM narrative summary (off by default to avoid accidental API calls);
  override model and token budget at runtime without editing config
- LLM commit grouping: `--summarize` also calls `group_commits()` to semantically
  cluster commits into named groups; card renders group summaries instead of raw
  commit rows
- `--json` flag on `generate` and `discover` — structured JSON output to stdout
  for scripting; includes `commit_groups` array for inspecting LLM groupings
- `show_date` / `show_repo_name` config options — suppress the date hero or repo
  label; when `show_date=false` and `show_repo_name=true`, repo name promotes to
  title-size hero
- Dark-themed card layout: 88px date hero, Inter/JetBrains Mono bundled fonts,
  configurable background opacity, height expands with content (no fixed floor)
- Config: `~/.config/gitvisual/config.toml` with deep-merge and full fallback to
  defaults; new fields `llm.max_tokens_grouping` (4096) and
  `render.max_groups_shown` (10)
- LLM support via litellm (OpenRouter, OpenAI, Anthropic, Ollama); default model
  `openrouter/nvidia/llama-3.1-nemotron-ultra-253b-v1`

### Fixed

- Collector exclude filter now uses exact path-component matching (not substring),
  preventing false positives like `lib` matching `library`
- LLM reasoning-model output stripped cleanly: quoted-sentence extraction handles
  Nemotron-style inline reasoning; last-paragraph fallback handles others
- OpenRouter model prefix corrected so litellm routes without needing `api_base`
- API key missing warning shown early (before generate runs) when `--summarize`
  is used without the key env var set
- `generate --discover` no longer prints spurious "no commits" noise for inactive repos

### Infrastructure

- Full pytest suite (200+ tests), ruff lint clean, mypy clean
- `make ci` gate: ruff → mypy → pytest
- `scripts/agent-run.sh` wraps long commands, captures output to `.agent-output/`
