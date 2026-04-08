"""LLM summarization via litellm (model-agnostic: OpenRouter, OpenAI, Anthropic, Ollama)."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from typing import Protocol

from gitvisual.git.models import Commit, CommitGroup, DaySummary


class SummarizerError(Exception):
    """Raised when LLM summarization fails non-gracefully."""


class Summarizer(Protocol):
    """Protocol for summarizers — enables mocking in tests."""

    def summarize(self, day: DaySummary) -> str | None: ...

    def group_commits(
        self, day: DaySummary, max_groups: int | None = None
    ) -> list[CommitGroup] | None: ...

    def summarize_and_group(
        self, day: DaySummary, max_groups: int | None = None
    ) -> tuple[str | None, list[CommitGroup] | None]: ...


class LLMSummarizer:
    """Summarizes a DaySummary using litellm."""

    def __init__(
        self,
        model: str = "anthropic/claude-3-haiku",
        api_key_env: str = "OPENROUTER_API_KEY",
        api_base: str | None = None,
        max_tokens: int | None = 1500,
        max_tokens_grouping: int | None = 4096,
        timeout: int = 30,
        timeout_grouping: int = 120,
        json_response_format: bool = True,
        debug: bool = False,
    ) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.api_base = api_base
        self.max_tokens = max_tokens
        self.max_tokens_grouping = max_tokens_grouping
        self.timeout = timeout
        self.timeout_grouping = timeout_grouping
        self.json_response_format = json_response_format
        self.debug = debug

    def _dbg(self, *parts: str) -> None:
        """Print a debug line to stderr (only when debug=True)."""
        if self.debug:
            print("[debug]", *parts, file=sys.stderr)  # noqa: T201

    def _format_commits_for_prompt(self, day: DaySummary) -> str:
        """Return a formatted multi-line string of commits for use in prompts."""
        lines: list[str] = []
        for i, commit in enumerate(day.commits):
            lines.append(
                f"{i}. {commit.message}"
                f" | +{commit.insertions} -{commit.deletions}, {commit.files_changed} files"
            )
        return "\n".join(lines)

    def _format_commit_context(self, day: DaySummary) -> str:
        """Repo/date header + formatted commit list. Sent once in turn 1."""
        lines = [
            f"Repository: {day.repo_name}",
            f"Date: {day.date}",
            "",
            "Commits (index. message | +insertions -deletions, files_changed files):",
            self._format_commits_for_prompt(day),
        ]
        return "\n".join(lines)

    def _grouping_question(self, max_groups: int | None = None) -> str:
        """Grouping instruction only (no commits). Used as turn-1 user content suffix."""
        hint = f" Try to use at most {max_groups} groups." if max_groups is not None else ""
        return (
            f"Group the commits above into logical clusters.{hint}\n"
            "Return JSON with this exact schema:\n"
            '{"groups": [{"summary": "plain-language label", "commit_indices": [0, 3, 7]}, ...]}\n'
            "Use the integer indices shown above. Each commit may appear in at most one group."
        )

    def _summarize_question(self) -> str:
        """Summary instruction only (no commits). Used as turn-2 user content."""
        return (
            "Write a one-sentence summary (max 30 words) of what was accomplished.\n"
            "Style: verb-first, active voice, telegraphic — like a changelog entry or PR title.\n"
            "- Start directly with an action verb: Added, Fixed, Shipped, Built, Refactored, Extended, etc.\n"
            "- NEVER start with 'Today', 'The repo', 'The project', 'The codebase', 'This commit', or any other preamble.\n"
            "- Active voice only — 'Added X' not 'X was added'.\n"
            "- For a new project or initial setup: name what the project IS, then what was built.\n"
            "- Otherwise: lead with the single most significant change.\n"
            "- Be specific — a reader must understand the work without reading the commits."
        )

    def _build_prompt(self, day: DaySummary) -> str:
        lines = [
            f"Repository: {day.repo_name}",
            f"Date: {day.date}",
            "",
            "Commits:",
            self._format_commits_for_prompt(day),
            "",
            self._summarize_question(),
        ]
        return "\n".join(lines)

    def _call_llm(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None,
        **extra_kwargs: object,
    ) -> str | None:
        """Call litellm and return the response text, or None on any failure."""
        try:
            import litellm  # type: ignore[import-untyped,unused-ignore]

            litellm.suppress_debug_info = True
            litellm.verbose = False
        except ImportError:
            self._dbg("litellm not installed — LLM calls disabled")
            return None

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            self._dbg(f"no API key found in ${self.api_key_env} — skipping LLM call")
            return None

        try:
            kwargs: dict[str, object] = {
                "model": self.model,
                "messages": messages,
                "timeout": self.timeout,
                "extra_body": {"reasoning": {"exclude": True}},
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            if self.api_base:
                kwargs["api_base"] = self.api_base
            if api_key:
                kwargs["api_key"] = api_key
            kwargs.update(extra_kwargs)

            effective_timeout = kwargs.get("timeout", self.timeout)
            # Rough token estimate: 1 token ≈ 4 chars
            input_chars = sum(len(m.get("content", "")) for m in messages)
            input_tokens_est = input_chars // 4
            max_tokens_str = str(max_tokens) if max_tokens is not None else "unlimited"
            self._dbg(
                f"{len(messages)} message(s), ~{input_tokens_est} tokens input,"
                f" max_tokens={max_tokens_str}, timeout={effective_timeout}s,"
                f" model={self.model}"
            )

            t0 = time.perf_counter()
            response = litellm.completion(**kwargs)
            elapsed = time.perf_counter() - t0

            try:
                cost = litellm.completion_cost(completion_response=response)
                cost_str = f" cost=${float(cost):.6f}" if cost else " cost=$0 (free)"
            except Exception:
                cost_str = ""

            content = response.choices[0].message.content
            if content:
                preview = content[:80].replace("\n", " ")
                self._dbg(f"  → {len(content)} chars in {elapsed:.1f}s{cost_str}: {preview!r}")
            else:
                try:
                    finish_reason = response.choices[0].finish_reason
                    completion_tokens = response.usage.completion_tokens
                    prompt_tokens = response.usage.prompt_tokens
                    reason_str = f" finish_reason={finish_reason!r}, usage={prompt_tokens}+{completion_tokens} tokens"
                except Exception:
                    reason_str = ""
                self._dbg(f"  → (empty response) in {elapsed:.1f}s{cost_str}{reason_str}")
            return content if content else None
        except Exception as e:
            print(f"[gitvisual] LLM call failed: {type(e).__name__}: {e}", file=sys.stderr)  # noqa: T201
            if self.debug:
                print(traceback.format_exc(), file=sys.stderr)  # noqa: T201
            return None

    def _call_llm_grouping(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None,
        **extra_kwargs: object,
    ) -> str | None:
        """Call litellm for a grouping turn.

        If ``json_response_format`` is enabled, passes
        ``response_format={"type": "json_object"}`` to the model.  On empty
        response it automatically retries *without* that parameter and warns
        the user — many free-tier models silently return nothing when JSON mode
        is requested.
        """
        if self.json_response_format:
            content = self._call_llm(
                messages,
                max_tokens,
                response_format={"type": "json_object"},
                **extra_kwargs,
            )
            if content is None:
                print(  # noqa: T201
                    "[gitvisual] Warning: LLM returned empty response with JSON mode enabled. "
                    "Retrying without response_format. "
                    "To skip this retry, set json_response_format = false in config.toml "
                    "or pass --no-json-response-format.",
                    file=sys.stderr,
                )
                return self._call_llm(messages, max_tokens, **extra_kwargs)
            return content
        return self._call_llm(messages, max_tokens, **extra_kwargs)

    def _parse_groups(self, content: str, day: DaySummary) -> list[CommitGroup] | None:
        """Parse JSON groups response and match commit indices. Logs to stderr on failure."""
        try:
            data = json.loads(content)
            raw_groups: list[dict[str, object]] = data["groups"]  # KeyError → caught below

            commits = day.commits
            assigned: set[int] = set()
            groups: list[CommitGroup] = []

            for raw in raw_groups:
                matched: list[Commit] = []
                indices = raw.get("commit_indices", [])
                if not isinstance(indices, list):
                    indices = []
                for idx in indices:
                    if isinstance(idx, int) and 0 <= idx < len(commits) and idx not in assigned:
                        matched.append(commits[idx])
                        assigned.add(idx)
                groups.append(
                    CommitGroup(summary=str(raw.get("summary", "Untitled group")), commits=matched)
                )

            # Catch-all: commits the LLM didn't assign
            unassigned = [c for i, c in enumerate(commits) if i not in assigned]
            if unassigned:
                groups.append(CommitGroup(summary="Other changes", commits=unassigned))

            return groups
        except Exception as e:
            print(f"[gitvisual] Failed to parse groups JSON: {e}", file=sys.stderr)  # noqa: T201
            if self.debug:
                snippet = content[:200].replace("\n", " ")
                print(f"[debug] content snippet: {snippet!r}", file=sys.stderr)  # noqa: T201
            return None

    def summarize(self, day: DaySummary) -> str | None:
        """Generate a 1-2 sentence plain-language summary of the day's work.

        Returns None on any error (LLM calls are always optional).
        """
        if day.is_empty:
            return None

        system = (
            "You write one-sentence summaries of a day's coding work for a visual progress card. "
            "Style: verb-first, active voice, telegraphic — like a changelog entry or PR title. "
            "Rules: "
            "(1) Start with an action verb — Built, Added, Fixed, Shipped, Refactored, Extended, Wired, etc. "
            "(2) Active voice only — never 'X was added', always 'Added X'. "
            "(3) Never open with 'Today', 'The repo', 'The project', 'The codebase', 'This commit', or any subject preamble. "
            "(4) One sentence, 30 words maximum. No filenames, no jargon. "
            "Reply with only the summary — no explanation, quotes, or extra punctuation."
        )
        prompt = self._build_prompt(day)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        content = self._call_llm(messages, self.max_tokens)
        return _clean_summary(content) if content else None

    def _build_grouping_prompt(self, day: DaySummary, max_groups: int | None) -> str:
        lines = [
            self._format_commit_context(day),
            "",
            self._grouping_question(max_groups),
        ]
        return "\n".join(lines)

    def group_commits(
        self, day: DaySummary, max_groups: int | None = None
    ) -> list[CommitGroup] | None:
        """Semantically group the day's commits using the LLM.

        Returns None on any error (LLM calls are always optional).
        Stats are always computed from real Commit objects — never from LLM output.
        """
        if day.is_empty:
            return None

        system = (
            "You group git commits into logical clusters for a visual progress card. "
            "Reply with only valid JSON matching the requested schema — no preamble."
        )
        prompt = self._build_grouping_prompt(day, max_groups)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        content = self._call_llm_grouping(
            messages,
            self.max_tokens_grouping,
            timeout=self.timeout_grouping,
        )
        if not content:
            return None

        return self._parse_groups(content, day)

    def summarize_and_group(
        self, day: DaySummary, max_groups: int | None = None
    ) -> tuple[str | None, list[CommitGroup] | None]:
        """Two-turn LLM session: Turn 1 groups commits, Turn 2 summarizes.

        Returns (summary, groups) tuple. Either element may be None on failure.
        """
        if day.is_empty:
            return (None, None)

        system_msg: dict[str, str] = {
            "role": "system",
            "content": (
                "You help generate visual progress cards from git commit history. "
                "When asked for JSON, reply with only valid JSON — no preamble. "
                "When asked for a summary, use verb-first active voice (changelog style): "
                "start with an action verb, never with 'Today', 'The repo', 'The project', or any subject preamble."
            ),
        }
        context = self._format_commit_context(day)
        grouping_q = self._grouping_question(max_groups)

        # Turn 1: commits + grouping question
        self._dbg(f"Turn 1 — grouping  {len(day.commits)} commit(s)")
        messages: list[dict[str, str]] = [
            system_msg,
            {"role": "user", "content": context + "\n\n" + grouping_q},
        ]
        group_raw = self._call_llm_grouping(
            messages,
            self.max_tokens_grouping,
            timeout=self.timeout_grouping,
        )

        if group_raw is None:
            self._dbg("  → Turn 1 failed (no response) — falling back to single-turn summary")
            summary = self.summarize(day)
            return (summary, None)

        groups = self._parse_groups(group_raw, day)
        if groups is None:
            self._dbg("  → Turn 1 parse failed — falling back to single-turn summary")
            summary = self.summarize(day)
            return (summary, None)

        group_lines = "  ".join(f"{g.summary!r} ({len(g.commits)})" for g in groups)
        self._dbg(f"  → {len(groups)} group(s) parsed:  {group_lines}")

        # Turn 2: append assistant reply + summary question (no commits repeated)
        self._dbg("Turn 2 — summary")
        messages.append({"role": "assistant", "content": group_raw})
        messages.append({"role": "user", "content": self._summarize_question()})
        summary_raw = self._call_llm(messages, self.max_tokens, timeout=self.timeout)
        summary = _clean_summary(summary_raw) if summary_raw else None
        self._dbg(f"  → summary: {summary!r}")

        return (summary, groups)


def _clean_summary(text: str) -> str | None:
    """Strip reasoning preamble that some models leak into the completion.

    Reasoning models sometimes output their chain-of-thought before the final
    answer. Strategy (in priority order):

    1. Extract the last double-quoted sentence — reasoning models commonly wrap
       their final answer in quotes, e.g. 'So the answer is "Improved X."'
    2. Take the last non-empty paragraph (works for models that put thinking in
       early paragraphs and the answer in the final one).
    """
    import re

    text = text.strip()
    if not text:
        return None

    # Strategy 1: find the last double-quoted string that looks like a sentence
    # (starts with a capital letter, at least 20 chars, ends with punctuation)
    quoted: list[str] = re.findall(r'"([A-Z][^"]{19,}[.!?])"', text)
    if quoted:
        return quoted[-1]

    # Strategy 2: split into paragraphs, return the last non-empty one
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return None

    return paragraphs[-1]


class StubSummarizer:
    """Returns canned summaries for testing without LLM calls."""

    def summarize(self, day: DaySummary) -> str | None:
        if day.is_empty:
            return None
        return (
            f"Worked on {day.repo_name}: made {len(day.commits)} commit(s) "
            f"with {day.total_insertions} additions and {day.total_deletions} deletions."
        )

    def group_commits(
        self, day: DaySummary, max_groups: int | None = None
    ) -> list[CommitGroup] | None:
        return [CommitGroup(summary="Stub: all commits grouped", commits=list(day.commits))]

    def summarize_and_group(
        self, day: DaySummary, max_groups: int | None = None
    ) -> tuple[str | None, list[CommitGroup] | None]:
        if not day.commits:
            return (None, None)
        summary = self.summarize(day)
        groups: list[CommitGroup] = [
            CommitGroup(summary="Stub: all commits grouped", commits=list(day.commits))
        ]
        return (summary, groups)


class NullSummarizer:
    """Always returns None — for --no-summary mode."""

    def summarize(self, day: DaySummary) -> str | None:
        return None

    def group_commits(
        self, day: DaySummary, max_groups: int | None = None
    ) -> list[CommitGroup] | None:
        return None

    def summarize_and_group(
        self, day: DaySummary, max_groups: int | None = None
    ) -> tuple[str | None, list[CommitGroup] | None]:
        return (None, None)


def make_summarizer(
    *,
    enabled: bool,
    model: str,
    api_key_env: str,
    api_base: str | None = None,
    max_tokens: int | None = 200,
    max_tokens_grouping: int | None = 4096,
    timeout: int = 30,
    timeout_grouping: int = 120,
    json_response_format: bool = True,
    stub: bool = False,
    debug: bool = False,
) -> Summarizer:
    """Factory: return the appropriate summarizer based on settings.

    ``max_tokens`` / ``max_tokens_grouping`` values that are ``None`` or ``<= 0``
    are converted to ``None``, which omits the ``max_tokens`` parameter from the
    litellm call and lets the model use its own default limit.
    """
    if not enabled:
        return NullSummarizer()
    if stub:
        return StubSummarizer()

    def _to_limit(v: int | None) -> int | None:
        return None if (v is None or v <= 0) else v

    return LLMSummarizer(
        model=model,
        api_key_env=api_key_env,
        api_base=api_base,
        max_tokens=_to_limit(max_tokens),
        max_tokens_grouping=_to_limit(max_tokens_grouping),
        timeout=timeout,
        timeout_grouping=timeout_grouping,
        json_response_format=json_response_format,
        debug=debug,
    )
