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
        max_tokens: int = 200,
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
            f"Commits: {len(day.commits)}",
            "",
        ]
        for i, commit in enumerate(day.commits, 1):
            lines.append(f"{i}. {commit.message}")
            if commit.body:
                lines.append(f"   {commit.body[:200]}")
            lines.append(
                f"   +{commit.insertions} -{commit.deletions} in {commit.files_changed} files"
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
        except ImportError:
            return None

        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            return None

        prompt = self._build_prompt(day)
        system = (
            "You summarize software development activity for a daily coding journal. "
            "Write 1-2 sentences in simple, friendly, non-technical language. "
            "Focus on what was accomplished (outcomes), not implementation details. "
            "Start with an action verb. Be concise — this text appears in an infographic."
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
            }
            if self.api_base:
                kwargs["api_base"] = self.api_base
            if api_key:
                kwargs["api_key"] = api_key

            response = litellm.completion(**kwargs)
            content = response.choices[0].message.content
            return content.strip() if content else None
        except Exception:
            return None


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
