"""LLM summarization via litellm (model-agnostic: OpenRouter, OpenAI, Anthropic, Ollama)."""

from __future__ import annotations

import json
import os
import sys
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
        max_tokens: int = 1500,
        max_tokens_grouping: int = 4096,
        timeout: int = 30,
        timeout_grouping: int = 120,
    ) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.api_base = api_base
        self.max_tokens = max_tokens
        self.max_tokens_grouping = max_tokens_grouping
        self.timeout = timeout
        self.timeout_grouping = timeout_grouping

    def _format_commits_for_prompt(self, day: DaySummary) -> str:
        """Return a formatted multi-line string of commits for use in prompts."""
        lines: list[str] = []
        for commit in day.commits:
            lines.append(
                f"- {commit.short_hash} | {commit.message}"
                f" | +{commit.insertions} -{commit.deletions}, {commit.files_changed} files"
            )
        return "\n".join(lines)

    def _format_commit_context(self, day: DaySummary) -> str:
        """Repo/date header + formatted commit list. Sent once in turn 1."""
        lines = [
            f"Repository: {day.repo_name}",
            f"Date: {day.date}",
            "",
            "Commits (hash | message | +insertions -deletions, files_changed files):",
            self._format_commits_for_prompt(day),
        ]
        return "\n".join(lines)

    def _grouping_question(self, max_groups: int | None = None) -> str:
        """Grouping instruction only (no commits). Used as turn-1 user content suffix."""
        hint = f" Try to use at most {max_groups} groups." if max_groups is not None else ""
        return (
            f"Group the commits above into logical clusters.{hint}\n"
            "Return JSON with this exact schema:\n"
            '{"groups": [{"summary": "plain-language label", "commit_hashes": ["<short_hash>", ...]}, ...]}\n'
            "Use the short hashes shown above. Each commit must appear in at most one group."
        )

    def _summarize_question(self) -> str:
        """Summary instruction only (no commits). Used as turn-2 user content."""
        return (
            "Write a one-sentence summary of what was accomplished today.\n"
            "- If this looks like a new project or initial setup, describe what the project IS and what was built.\n"
            "- Otherwise, describe the most significant change and why it matters.\n"
            "- Be specific — a reader should understand the work without reading the commits."
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
        max_tokens: int,
        **extra_kwargs: object,
    ) -> str | None:
        """Call litellm and return the response text, or None on any failure."""
        try:
            import litellm  # type: ignore[import-untyped,unused-ignore]

            litellm.suppress_debug_info = True
            litellm.verbose = False
        except ImportError:
            return None

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            return None

        try:
            kwargs: dict[str, object] = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "timeout": self.timeout,
                "extra_body": {"reasoning": {"exclude": True}},
            }
            if self.api_base:
                kwargs["api_base"] = self.api_base
            if api_key:
                kwargs["api_key"] = api_key
            kwargs.update(extra_kwargs)

            response = litellm.completion(**kwargs)
            content = response.choices[0].message.content
            return content if content else None
        except Exception as e:
            print(f"[gitvisual] LLM call failed: {e}", file=sys.stderr)  # noqa: T201
            return None

    def _parse_groups(self, content: str, day: DaySummary) -> list[CommitGroup] | None:
        """Parse JSON groups response and match commit hashes. Logs to stderr on failure."""
        try:
            data = json.loads(content)
            raw_groups: list[dict[str, object]] = data["groups"]  # KeyError → caught below

            # Build lookup: both short_hash and full hash → Commit (single loop)
            hash_to_commit: dict[str, Commit] = {}
            for c in day.commits:
                hash_to_commit[c.hash] = c
                hash_to_commit[c.short_hash] = c

            assigned: set[str] = set()  # track by short_hash to avoid dupes
            groups: list[CommitGroup] = []

            for raw in raw_groups:
                matched: list[Commit] = []
                commit_hashes = raw.get("commit_hashes", [])
                if not isinstance(commit_hashes, list):
                    commit_hashes = []
                for h in commit_hashes:
                    found = hash_to_commit.get(str(h))
                    if found is not None and found.short_hash not in assigned:
                        matched.append(found)
                        assigned.add(found.short_hash)
                groups.append(
                    CommitGroup(summary=str(raw.get("summary", "Untitled group")), commits=matched)
                )

            # Catch-all: commits the LLM didn't assign
            unassigned = [c for c in day.commits if c.short_hash not in assigned]
            if unassigned:
                groups.append(CommitGroup(summary="Other changes", commits=unassigned))

            return groups
        except Exception as e:
            print(f"[gitvisual] Failed to parse groups JSON: {e}", file=sys.stderr)  # noqa: T201
            return None

    def summarize(self, day: DaySummary) -> str | None:
        """Generate a 1-2 sentence plain-language summary of the day's work.

        Returns None on any error (LLM calls are always optional).
        """
        if day.is_empty:
            return None

        system = (
            "You write short summaries of a day's coding work for a visual progress card. "
            "Rules: start with an action verb (Built, Started, Fixed, Added, Shipped, Refactored, etc.). "
            "Name what was built or changed — do not be vague. "
            "One sentence; two at most. No filenames, no jargon. "
            "Reply with only the summary — no preamble, explanation, or enclosing quotes."
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
        content = self._call_llm(
            messages, self.max_tokens_grouping, response_format={"type": "json_object"}
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
                "You are an assistant that helps generate visual progress cards from git commit history. "
                "Reply with only valid JSON when asked for JSON — no preamble."
            ),
        }
        context = self._format_commit_context(day)
        grouping_q = self._grouping_question(max_groups)

        # Turn 1: commits + grouping question
        messages: list[dict[str, str]] = [
            system_msg,
            {"role": "user", "content": context + "\n\n" + grouping_q},
        ]
        group_raw = self._call_llm(
            messages,
            self.max_tokens_grouping,
            timeout=self.timeout_grouping,
            response_format={"type": "json_object"},
        )

        if group_raw is None:
            return (None, None)

        groups = self._parse_groups(group_raw, day)
        if groups is None:
            # JSON parse failed — abort the session
            return (None, None)

        # Turn 2: append assistant reply + summary question (no commits repeated)
        messages.append({"role": "assistant", "content": group_raw})
        messages.append({"role": "user", "content": self._summarize_question()})
        summary_raw = self._call_llm(messages, self.max_tokens, timeout=self.timeout)
        summary = _clean_summary(summary_raw) if summary_raw else None

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
        summary = self.summarize(day)
        groups: list[CommitGroup] = (
            [CommitGroup(summary="Stub: all commits grouped", commits=list(day.commits))]
            if day.commits
            else []
        )
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
    max_tokens: int = 200,
    max_tokens_grouping: int = 4096,
    timeout: int = 30,
    timeout_grouping: int = 120,
    stub: bool = False,
) -> Summarizer:
    """Factory: return the appropriate summarizer based on settings."""
    if not enabled:
        return NullSummarizer()
    if stub:
        return StubSummarizer()
    return LLMSummarizer(
        model=model,
        api_key_env=api_key_env,
        api_base=api_base,
        max_tokens=max_tokens,
        max_tokens_grouping=max_tokens_grouping,
        timeout=timeout,
        timeout_grouping=timeout_grouping,
    )
