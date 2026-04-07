"""LLM summarization via litellm (model-agnostic: OpenRouter, OpenAI, Anthropic, Ollama)."""

from __future__ import annotations

import os
from typing import Protocol

from gitvisual.git.models import DaySummary


class SummarizerError(Exception):
    """Raised when LLM summarization fails non-gracefully."""


class Summarizer(Protocol):
    """Protocol for summarizers — enables mocking in tests."""

    def summarize(self, day: DaySummary) -> str | None: ...


class LLMSummarizer:
    """Summarizes a DaySummary using litellm."""

    def __init__(
        self,
        model: str = "anthropic/claude-3-haiku",
        api_key_env: str = "OPENROUTER_API_KEY",
        api_base: str | None = None,
        max_tokens: int = 1500,
        timeout: int = 30,
    ) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.api_base = api_base
        self.max_tokens = max_tokens
        self.timeout = timeout

    def _build_prompt(self, day: DaySummary) -> str:
        lines = [
            f"Repository: {day.repo_name}",
            f"Date: {day.date}",
            "",
            "Commits:",
        ]
        for commit in day.commits:
            lines.append(
                f"- {commit.message} (+{commit.insertions} -{commit.deletions}, {commit.files_changed} files)"
            )
        lines.append("")
        lines.append(
            "Write a summary of what was accomplished today. "
            "Focus on high-level outcomes — do not rephrase the commit messages."
        )
        return "\n".join(lines)

    def summarize(self, day: DaySummary) -> str | None:
        """Generate a 1-2 sentence plain-language summary of the day's work.

        Returns None on any error (LLM calls are always optional).
        """
        if day.is_empty:
            return None

        try:
            import litellm  # type: ignore[import-untyped,unused-ignore]

            litellm.suppress_debug_info = True
            litellm.verbose = False
        except ImportError:
            return None

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            return None

        prompt = self._build_prompt(day)
        system = (
            "You write one-sentence summaries of a day's coding work for a visual infographic card. "
            "Start with an action verb (e.g. 'Improved...', 'Fixed...', 'Added...', 'Refactored...'). "
            "Focus on outcomes, not implementation details. "
            "No filenames, no technical jargon, no more than two sentences. "
            "Reply with only the summary — no preamble or explanation."
        )

        try:
            kwargs: dict[str, object] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": self.max_tokens,
                "timeout": self.timeout,
                # Tell OpenRouter not to include chain-of-thought in the completion
                "extra_body": {"reasoning": {"exclude": True}},
            }
            if self.api_base:
                kwargs["api_base"] = self.api_base
            if api_key:
                kwargs["api_key"] = api_key

            response = litellm.completion(**kwargs)
            content = response.choices[0].message.content
            return _clean_summary(content) if content else None
        except Exception:
            return None


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


class NullSummarizer:
    """Always returns None — for --no-summary mode."""

    def summarize(self, day: DaySummary) -> str | None:
        return None


def make_summarizer(
    *,
    enabled: bool,
    model: str,
    api_key_env: str,
    api_base: str | None = None,
    max_tokens: int = 200,
    timeout: int = 30,
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
        timeout=timeout,
    )
