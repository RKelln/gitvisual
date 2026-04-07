# AGENTS.md

Python 3.12+. Typer CLI. Pillow rendering. litellm for LLM. uv for dependencies.

## Defaults

- TDD: failing tests first, use pytest, table-driven where appropriate
- Use `bd` (beads) for task tracking — not markdown todo lists
- Use `context7` MCP server for external library docs
- Act without confirmation unless blocked by missing info or irreversibility
- When stuck (cryptic errors, multiple failed approaches): escalate via Task tool with `subagent_type: "diagnose"`

## Design

See `PLAN.md` for the full design plan (architecture, phases, data models, CLI interface, test strategy).
Key decisions:
- CLI via `typer`, data models via `pydantic`, rendering via `Pillow`
- LLM via `litellm` (model-agnostic; supports OpenRouter, OpenAI, Anthropic, Ollama)
- Git data via `subprocess` calling the git CLI (not GitPython)
- Config via TOML (`~/.config/gitvisual/config.toml`)
- Fonts bundled in `assets/fonts/` (Inter + JetBrains Mono, OFL licensed)
- Output: square-ish cards (soft 1:1 target, height expands for content)

## Project Structure

```
src/gitvisual/
  cli.py            -- Typer CLI entry point (generate, discover, config commands)
  config.py         -- TOML config loading, defaults, path resolution
  git/
    collector.py    -- Git data extraction via subprocess
    models.py       -- Pydantic models: FileChange, Commit, DaySummary, Report
  llm/
    summarizer.py   -- litellm integration, prompt engineering, OpenRouter support
  render/
    card.py         -- Phase 1 card renderer
    components.py   -- Reusable visual components
    themes.py       -- Color palettes and typography
assets/fonts/       -- Bundled Inter + JetBrains Mono fonts
tests/              -- pytest suite, mirrors src/ structure
```

## Fast Path

```bash
# Install dependencies
uv sync

# Run all tests
scripts/agent-run.sh uv run pytest

# Run tests with coverage
scripts/agent-run.sh uv run pytest --cov=gitvisual --cov-report=term-missing

# Lint
scripts/agent-run.sh uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/

# Type check
scripts/agent-run.sh uv run mypy src/

# Run CLI locally
uv run gitvisual --help

# CI gate before committing
scripts/agent-run.sh make ci
```

**Always wrap build/test/lint/long-output commands with `scripts/agent-run.sh`** — captures verbose output to `.agent-output/`, shows only summary.

## Conventions

- **Assertions:** pytest `assert` statements; no unittest-style self.assert*
- **Error handling:** raise specific exceptions; never silently swallow errors in non-optional paths
- **LLM calls:** always optional — every command must work with `--no-summary`
- **Subprocess:** always use `check=True`, capture stderr, use `text=True`
- **Types:** full type annotations on all public functions and methods
- **Immutability:** pydantic models are `model_config = ConfigDict(frozen=True)`
- **Tests:** fixture git repos live in `tests/fixtures/`; use `tmp_path` for output

## Commit Messages

Conventional Commits with `Generated-by` trailer:

```
feat(render): add dark theme card layout

Generated-by: <your-model-name>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`. Scope is optional.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL inter-task tracking, and other todo tools for intra-task tracking while working on a bead
- Creating and updating documentation files (PLAN.md, README.md, design docs, etc.) is encouraged — docs are part of the codebase
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
