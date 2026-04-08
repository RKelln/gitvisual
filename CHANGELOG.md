# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.2.0] — LLM grouping reliability and debug tooling — 2026-04-07

This release hardens the two-turn LLM grouping pipeline against real-world model
quirks (empty responses, token caps, skipped commits) and adds comprehensive debug
tooling to make diagnosing LLM failures fast and actionable.

### Added
- `--debug` / `-D` flag on `generate` exposes per-turn LLM details to stderr:
  call parameters (model, max_tokens, timeout, estimated input tokens), response
  previews, parsed group summaries, elapsed time per call, and per-call cost.
- `--max-tokens-grouping` CLI flag overrides `max_tokens_grouping` from config,
  mirroring the existing `--max-tokens` flag for the summary call.
- `--no-json-response-format` flag (and `json_response_format = false` in config)
  opts out of `response_format={type: json_object}`, enabling compatibility with
  free-tier models that silently return empty responses when JSON mode is set.
- Setting `max_tokens` or `max_tokens_grouping` to `0` in config omits the token
  cap from the litellm call entirely, letting the model use its own default limit.
- Turn 1.5 retry: when the LLM's grouping response omits commits, a second
  independent call re-groups only the unassigned commits before the Turn 2 summary.

### Fixed
- Auto-retry grouping without JSON mode when Turn 1 returns an empty response
  (common on free-tier models); warns the user to set `json_response_format = false`.
- Graceful fallback to single-turn summary when Turn 1 returns an empty or
  invalid JSON response, instead of producing a card with no summary or groups.
- Unassigned commits now each become their own singleton group (using the commit
  message as label) instead of being lumped into a vague "Other changes" bucket.
- End-of-run warnings now differentiate a missing API key from an LLM call
  failure, and always show the effective model name (including `--model` overrides).
- `--debug` mode shows `finish_reason` and token counts on empty responses, full
  tracebacks on call exceptions, and group summaries immediately after parsing.
- End-of-run warning correctly distinguishes grouping-only success from total
  failure; the yellow warning now only appears when both grouping and summary fail.

### Changed
- Grouping JSON schema switched from commit hashes to 0-based commit indices,
  saving ~140 output tokens on large commit sets — enough to fit within free-tier
  output caps on 80+ commit days.
- Summary prompts enforce verb-first active voice and a 30-word cap, explicitly
  banning preamble openers ("Today", "The repo", "The project", "The codebase").

### Infrastructure
- Test suite expanded significantly (+460 lines) covering retry logic, debug output
  paths, error visibility, fallback behaviour, and new CLI flags.

## [v0.1.2] — Two-turn LLM session and --version flag — 2026-04-07

LLM summarization now uses a single two-turn conversation: commits are sent
once in the grouping turn, and the summary turn reuses the message history.
This eliminates redundant token transmission and resolves timeout failures
on large commit sets (e.g. 57+ commits).

### Added
- `gitvisual --version` flag prints the installed package version and exits.
- `summarize_and_group()` method on all summarizer types (`LLMSummarizer`,
  `StubSummarizer`, `NullSummarizer`) and the `Summarizer` protocol. The CLI
  `generate` command now calls this single method instead of two sequential calls.
- `timeout_grouping` config field (default 120 s) in `[llm]` — separate timeout
  for the grouping turn, independent of the existing `timeout` (30 s) used for
  the summary turn. Configurable in `~/.config/gitvisual/config.toml`.

### Fixed
- `group_commits()` was incorrectly using the 30 s summary timeout for the
  heavier grouping LLM call. It now uses `timeout_grouping` (120 s).
- LLM call failures now print a `[gitvisual]` prefixed error to stderr instead
  of failing silently.
- JSON group parse failures now log to stderr instead of failing silently.

### Infrastructure
- README install instructions corrected (repo URL and `uv tool upgrade` command).

---

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
