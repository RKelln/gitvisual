"""Tests for LLM summarizer."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from gitvisual.git.models import DaySummary
from gitvisual.llm.summarizer import (
    LLMSummarizer,
    NullSummarizer,
    StubSummarizer,
    make_summarizer,
)
from tests.conftest import make_commit, make_day_summary


class TestNullSummarizer:
    def test_always_returns_none(self, tmp_path: Path) -> None:
        s = NullSummarizer()
        day = make_day_summary(tmp_path=tmp_path)
        assert s.summarize(day) is None

    def test_empty_day_returns_none(self, tmp_path: Path) -> None:
        s = NullSummarizer()
        day = DaySummary(date=date(2025, 4, 7), repo_path=tmp_path, repo_name="repo", commits=[])
        assert s.summarize(day) is None


class TestStubSummarizer:
    def test_returns_string_for_active_day(self, tmp_path: Path) -> None:
        s = StubSummarizer()
        day = make_day_summary(tmp_path=tmp_path)
        result = s.summarize(day)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_none_for_empty_day(self, tmp_path: Path) -> None:
        s = StubSummarizer()
        day = DaySummary(date=date(2025, 4, 7), repo_path=tmp_path, repo_name="repo", commits=[])
        assert s.summarize(day) is None

    def test_includes_repo_name(self, tmp_path: Path) -> None:
        s = StubSummarizer()
        day = make_day_summary(repo_name="my-cool-repo", tmp_path=tmp_path)
        result = s.summarize(day)
        assert result is not None
        assert "my-cool-repo" in result

    def test_includes_commit_count(self, tmp_path: Path) -> None:
        s = StubSummarizer()
        commits = [make_commit(), make_commit(hash="b" * 16)]
        day = make_day_summary(commits=commits, tmp_path=tmp_path)
        result = s.summarize(day)
        assert result is not None
        assert "2" in result


class TestLLMSummarizer:
    def test_returns_none_when_no_api_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        day = make_day_summary(tmp_path=tmp_path)
        assert s.summarize(day) is None

    def test_returns_none_for_empty_day(self, tmp_path: Path) -> None:
        s = LLMSummarizer()
        day = DaySummary(date=date(2025, 4, 7), repo_path=tmp_path, repo_name="repo", commits=[])
        assert s.summarize(day) is None

    def test_build_prompt_includes_repo_name(self, tmp_path: Path) -> None:
        s = LLMSummarizer()
        day = make_day_summary(repo_name="awesome-project", tmp_path=tmp_path)
        prompt = s._build_prompt(day)
        assert "awesome-project" in prompt

    def test_build_prompt_includes_commit_messages(self, tmp_path: Path) -> None:
        s = LLMSummarizer()
        commits = [make_commit(message="feat: something cool")]
        day = make_day_summary(commits=commits, tmp_path=tmp_path)
        prompt = s._build_prompt(day)
        assert "feat: something cool" in prompt

    def test_graceful_on_litellm_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM errors must never propagate — return None instead."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")

        def mock_completion(**kwargs: object) -> None:
            raise RuntimeError("network error")

        import sys
        import types

        fake_litellm = types.ModuleType("litellm")
        fake_litellm.completion = mock_completion  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        day = make_day_summary(tmp_path=tmp_path)
        assert s.summarize(day) is None


class TestMakeSummarizer:
    def test_disabled_returns_null(self, tmp_path: Path) -> None:
        s = make_summarizer(enabled=False, model="x", api_key_env="KEY")
        day = make_day_summary(tmp_path=tmp_path)
        assert s.summarize(day) is None

    def test_stub_returns_stub(self, tmp_path: Path) -> None:
        s = make_summarizer(enabled=True, model="x", api_key_env="KEY", stub=True)
        day = make_day_summary(tmp_path=tmp_path)
        assert s.summarize(day) is not None

    def test_enabled_returns_llm_summarizer(self) -> None:
        s = make_summarizer(enabled=True, model="openai/gpt-4o-mini", api_key_env="KEY")
        assert isinstance(s, LLMSummarizer)
