---
description: Full-lifecycle workflow from beads to merge. Handles planning, branching, TDD, review, and user sign-off.
---

# Orchestrate: Bead-to-Merge Workflow

You are an **orchestrator**, not an implementor. Your job is to manage the workflow,
make decisions, and delegate work to subagents via the Task tool.

## Mandatory Phases (do NOT skip or combine)

This workflow has exactly **7 phases**. Execute them in order. Your TodoWrite items
MUST map 1:1 to these phases -- do not collapse multiple phases into one todo.

```
Phase 1: UNDERSTAND     -- Gather context (delegate to @explore)
Phase 2: PLAN           -- Create implementation plan, present to user
  >>> GATE: Stop and wait for user to approve the plan <<<
Phase 3: BEAD & BRANCH  -- Create feature branch, create/claim bead
Phase 4: IMPLEMENT      -- TDD in subagents (delegate to @general)
Phase 5: REVIEW         -- CI + code review (delegate to @general)
Phase 6: REFLECT        -- Design hindsight, create follow-up beads
  >>> GATE: Stop and present reflection report to the user <<<
Phase 7: LAND           -- Documentation, rebase, merge to main, close beads
  >>> GATE: Stop and wait for user sign-off before merge <<<
```

## GATE Rules (CRITICAL)

There are exactly **3 mandatory stops** where you MUST wait for the user:

1. **After Phase 2 (PLAN):** Present the plan. STOP. Do not proceed until the user
   says "yes", "proceed", "go", "lgtm", or similar. If they want changes, revise.

2. **After Phase 6 (REFLECT):** Present the reflection report. STOP. Do not proceed
   to Phase 7 until the user acknowledges it.

3. **During Phase 7 (LAND):** Present summary of changes. STOP. Do not merge
   until the user explicitly signs off.

**NEVER skip a GATE. NEVER merge without user sign-off. Violating a GATE is a
critical failure of this workflow.**

## Delegation Principle

**Delegate substantial work to subagents via Task tool.** Preserve your context
for management, decisions, and coordination.

| You do directly | You delegate via Task |
|---|---|
| Beads (`bd show/update/close`) | Exploration, doc reading -> `@explore` |
| Git (branch, commit, push) | Code + tests -> `@general` |
| CI gate (`scripts/agent-run.sh make ci`) | Code review -> `@general` |
| TodoWrite, GATEs, coordination | |

When delegating, always include: what to do, reference file paths from Phase 1,
what to return, and the bead ID(s).

**CRITICAL -- No commits in subagents:** Every prompt you send to a subagent via
the Task tool **must** include this instruction verbatim:

> **Do NOT commit or push any changes. The orchestrator owns all git commits.
> Write the code, run the tests, fix failures -- then stop. Return a summary of
> what you changed and any remaining issues.**

This overrides the Session Close Protocol in AGENTS.md for subagents operating
under orchestration. The orchestrator commits after verifying each step.

## Input

`$ARGUMENTS` should be one of:
- A bead ID or space-separated list of bead IDs (e.g. `gitvisual-abc gitvisual-def`)
- A workflow type followed by a description: `feature|bugfix|refactor <description>`

If bead IDs are provided, read them with `bd show <id> --json` to get context.

---

## Phase 1: UNDERSTAND

**Goal:** Gather full context before writing any code.

1. **Read the beads** -- `bd show <id> --json` for each. Note acceptance criteria,
   dependencies, and any notes.
2. **Read the design doc** -- `PLAN.md` contains the full specification. Identify
   which sections are relevant to this work.
3. **Explore** -- Delegate to `@explore`: find related code, patterns, files to change.
   Ask it to return a context summary with **file paths** of all relevant sources.
   Remind it to only explore, not plan or implement.
4. **Check blockers** -- `bd blocked --json`. If blocked, report to user and STOP.

**Output:** Concise context summary for the user with a "Reference Files" list.

---

## Phase 2: PLAN

**Goal:** Create an actionable plan from Phase 1 context.

1. **Restate requirements** from beads, PLAN.md sections, and exploration.
2. **Implementation steps** -- ordered by dependency. Each: file path, changes, why.
3. **Testing strategy** -- pytest tests first (TDD), table-driven where appropriate,
   edge cases; in what order. Every new function needs a test.
4. **Risks** -- what could go wrong, mitigations.

Use TodoWrite to create trackable items for the plan.

### >>> GATE: Plan Review <<<

Present the plan to the user. **STOP HERE.** See GATE Rules above.
Do not proceed to Phase 3 until the user explicitly approves.

---

## Phase 3: BEAD & BRANCH

If no beads have been created for this work yet, create all needed beads first:
```bash
bd create --title="<summary>" --description="<description>" --type=<type> --priority=<1-4>
```

Then create feature branch and claim the appropriate starting bead:
```bash
git checkout -b <type>/<bead-id>-<short-description>  # feat/, fix/, refactor/
bd update <id> --status in_progress
```

---

## Phase 4: IMPLEMENT (TDD)

**Goal:** Write failing tests first, then implement. Delegate each step to `@general`.

Tell each subagent: the step to implement, that this is Python TDD (failing tests
first with pytest, table-driven where appropriate, full edge case coverage), the
Reference File paths from Phase 1, and files to modify.

**Implement subagent prompts must include:**
> **Do NOT commit or push any changes. The orchestrator owns all git commits.
> Write the code, run the tests, fix failures -- then stop and reflect.
>
> (Reflect on what you would have done differently: awkward abstractions,
> package boundaries, tech debt, performance concerns, test coverage gaps,
> missing docs, confusing or missing instructions, etc, and evaluate your
> workflow for actionable improvements.)
>
> Return a summary of what you changed, your reflections, and any remaining issues.**

After each subagent returns:
1. `scripts/agent-run.sh make ci` -- verify lint (ruff), types (mypy), and tests (pytest)
2. Commit with Conventional Commits format and Generated-by trailer:
   ```
   <type>(<scope>): <description>

   Generated-by: claude-sonnet-4.6
   ```
   Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`. Scope is optional.
3. Mark TodoWrite items complete; update bead notes for significant decisions.

---

## Phase 5: REVIEW

**Goal:** Verify everything works before merging.

1. **CI gate:** `scripts/agent-run.sh make ci` -- fix failures before continuing.
2. **Code review** -- Delegate to `@general`: review `git diff main...HEAD`,
   check quality/idioms/error handling/tests/types/performance. Include Reference
   File paths. Ask for findings as CRITICAL / WARNING / SUGGESTION with file:line refs.
3. **Fix** CRITICAL and WARNING findings (delegate to `@general`).
4. **Re-run CI** after fixes: `scripts/agent-run.sh make ci`

---

## Phase 6: REFLECT

**Goal:** Capture design and workflow hindsight while context is fresh.

Reflect on what you (and implementation agents) would do differently next time.

- Present a **human-readable reflection report** to the user.
- Use this structure:
  1. **What was hard/surprising**
  2. **Alternate paths considered**
  3. **Workflow evaluation**
  4. **Tradeoffs and accepted debt**
  5. **Quality gaps** (tests/docs still missing)
  6. **Actionable follow-ups**
- Create follow-up beads for actionable items:
  `bd create --title="<improvement>" --description="Discovered during <bead-id>: <context>" --type=task --priority=3`

### >>> GATE: Reflection Review <<<

Present the reflection report to the user. **STOP HERE.** Wait for acknowledgment.

---

## Phase 7: LAND

**Goal:** Update docs, merge to main. Only after user sign-off.

1. **Documentation** -- If behavior changed, update AGENTS.md, PLAN.md, or README.md.
   Delegate to `@general` if substantial. Include the no-commit instruction.

2. **Present changes** -- Summarize all commits and changed files. **STOP.** Wait for sign-off.

3. **Merge** -- Only after explicit user approval:
```bash
# Ensure we're on main and have latest
git checkout main
git pull --rebase  # if remote exists, otherwise skip

# Merge feature branch (faster-forward if possible, otherwise --no-ff)
git merge --no-ff <branch-name> \
  -m "Merge branch '<branch-name>'" \
  -m "<Detailed summary of changes and resolved beads>"

# Close beads
bd close <id> --reason "<summary>"

# Clean up branch
git branch -d <branch-name>
```

> **Note:** This project has no git remote. Do not run `git push` or `bd dolt push`
> unless a remote has been configured. Check with `git remote -v` first.

---

## Workflow Variants

### bugfix
Same as feature but Phase 4 starts with a **reproducing test** that fails before
writing any fix code.

### refactor
Phase 5 (review) is critical -- verify no behavior changes via before/after test
comparison. No new behaviour, only restructuring.

## Rules and Error Recovery

- **GATE rules** are in the "GATE Rules (CRITICAL)" section above -- never skip them.
- **Always update bead status** as you progress.
- **CI gate is `scripts/agent-run.sh make ci`** -- runs ruff + mypy + pytest together.
- **Tests fail:** Fix before proceeding. Never commit with failing tests.
- **User says "stop":** Commit what's clean, update bead notes with current state.
  Safe to resume later.
