"""Tests for LLM summarizer."""

from __future__ import annotations

import json
import sys
import types
from datetime import date
from pathlib import Path

import pytest

from gitvisual.git.models import DaySummary
from gitvisual.llm.summarizer import (
    LLMSummarizer,
    NullSummarizer,
    StubSummarizer,
    _clean_summary,
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

    def test_missing_api_key_debug_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """Missing API key emits a debug message when debug=True."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", debug=True)
        day = make_day_summary(tmp_path=tmp_path)
        s.summarize(day)
        captured = capsys.readouterr()
        assert "OPENROUTER_API_KEY" in captured.err
        assert "skipping" in captured.err

    def test_litellm_import_error_debug_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """Missing litellm emits a debug message when debug=True."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        monkeypatch.setitem(sys.modules, "litellm", None)  # type: ignore[call-overload]
        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", debug=True)
        day = make_day_summary(tmp_path=tmp_path)
        result = s.summarize(day)
        assert result is None
        captured = capsys.readouterr()
        assert "litellm" in captured.err

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

    def test_json_response_format_false_stored(self) -> None:
        """make_summarizer(json_response_format=False) stores False on the instance."""
        s = make_summarizer(enabled=True, model="x", api_key_env="KEY", json_response_format=False)
        assert isinstance(s, LLMSummarizer)
        assert s.json_response_format is False

    def test_json_response_format_true_by_default(self) -> None:
        s = make_summarizer(enabled=True, model="x", api_key_env="KEY")
        assert isinstance(s, LLMSummarizer)
        assert s.json_response_format is True

    @pytest.mark.parametrize("sentinel", [0, -1, -999])
    def test_zero_or_negative_max_tokens_becomes_none(self, sentinel: int) -> None:
        """max_tokens <= 0 must be stored as None (omit from litellm calls)."""
        s = make_summarizer(enabled=True, model="x", api_key_env="KEY", max_tokens=sentinel)
        assert isinstance(s, LLMSummarizer)
        assert s.max_tokens is None

    @pytest.mark.parametrize("sentinel", [0, -1, -999])
    def test_zero_or_negative_max_tokens_grouping_becomes_none(self, sentinel: int) -> None:
        """max_tokens_grouping <= 0 must be stored as None (omit from litellm calls)."""
        s = make_summarizer(
            enabled=True, model="x", api_key_env="KEY", max_tokens_grouping=sentinel
        )
        assert isinstance(s, LLMSummarizer)
        assert s.max_tokens_grouping is None

    def test_stub_group_commits_returns_list(self, tmp_path: Path) -> None:
        """make_summarizer(stub=True) → group_commits() returns a list."""
        s = make_summarizer(enabled=True, model="x", api_key_env="KEY", stub=True)
        day = make_day_summary(tmp_path=tmp_path)
        result = s.group_commits(day)
        assert result is not None
        assert isinstance(result, list)

    def test_disabled_group_commits_returns_none(self, tmp_path: Path) -> None:
        """make_summarizer(enabled=False) → NullSummarizer → group_commits() returns None."""
        s = make_summarizer(enabled=False, model="x", api_key_env="KEY")
        day = make_day_summary(tmp_path=tmp_path)
        assert s.group_commits(day) is None

    def test_enabled_with_mock_litellm_group_commits_returns_list(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """make_summarizer(enabled=True) with mocked litellm → group_commits() returns a list."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        c1 = make_commit()
        day = make_day_summary(commits=[c1], tmp_path=tmp_path)

        response = json.dumps({"groups": [{"summary": "Feature work", "commit_indices": [0]}]})
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm(response))

        s = make_summarizer(
            enabled=True, model="anthropic/claude-3-haiku", api_key_env="OPENROUTER_API_KEY"
        )
        result = s.group_commits(day)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) >= 1


class TestCleanSummary:
    def test_plain_summary_passes_through(self) -> None:
        text = "Improved the card renderer with better font handling."
        assert _clean_summary(text) == text

    def test_empty_returns_none(self) -> None:
        assert _clean_summary("") is None
        assert _clean_summary("   ") is None

    def test_extracts_quoted_sentence_from_reasoning(self) -> None:
        # Nemotron-style: reasoning inline, final answer in double quotes
        text = (
            "Outcome: they built core stuff. So high-level: "
            '"Implemented core features for a visual Git summary tool." '
            "That's one sentence, starts with 'Implemented'."
        )
        result = _clean_summary(text)
        assert result == "Implemented core features for a visual Git summary tool."

    def test_extracts_last_quoted_sentence_when_multiple(self) -> None:
        text = (
            'First attempt: "Added tests." But wait, let me reconsider. '
            'Better answer: "Refactored the summarizer to handle reasoning models robustly."'
        )
        result = _clean_summary(text)
        assert result == "Refactored the summarizer to handle reasoning models robustly."

    def test_last_paragraph_used_when_no_quotes(self) -> None:
        text = "Let me think about this.\n\nAdded dark theme support to the card renderer."
        assert _clean_summary(text) == "Added dark theme support to the card renderer."

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert _clean_summary("  Fixed a bug.  ") == "Fixed a bug."

    def test_single_paragraph_no_quotes_returned_as_is(self) -> None:
        text = "Fixed broken config loading on first run."
        assert _clean_summary(text) == text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_litellm(response_json: str) -> types.ModuleType:
    """Return a fake litellm module whose completion() returns response_json."""
    from types import SimpleNamespace

    fake = types.ModuleType("litellm")
    fake.suppress_debug_info = False  # type: ignore[attr-defined]
    fake.verbose = True  # type: ignore[attr-defined]

    def completion(**kwargs: object) -> object:
        msg = SimpleNamespace(content=response_json)
        choice = SimpleNamespace(message=msg)
        return SimpleNamespace(choices=[choice])

    fake.completion = completion  # type: ignore[attr-defined]
    return fake


def _make_fake_litellm_none_content() -> types.ModuleType:
    """Return a fake litellm module whose completion() returns content=None."""
    from types import SimpleNamespace

    fake = types.ModuleType("litellm")
    fake.suppress_debug_info = False  # type: ignore[attr-defined]
    fake.verbose = True  # type: ignore[attr-defined]

    def completion(**kwargs: object) -> object:
        msg = SimpleNamespace(content=None)
        choice = SimpleNamespace(message=msg)
        return SimpleNamespace(choices=[choice])

    fake.completion = completion  # type: ignore[attr-defined]
    return fake


def _make_raising_litellm(exc: Exception) -> types.ModuleType:
    """Return a fake litellm module whose completion() raises exc."""
    fake = types.ModuleType("litellm")
    fake.suppress_debug_info = False  # type: ignore[attr-defined]
    fake.verbose = True  # type: ignore[attr-defined]

    def completion(**kwargs: object) -> None:
        raise exc

    fake.completion = completion  # type: ignore[attr-defined]
    return fake


# ---------------------------------------------------------------------------
# NullSummarizer.group_commits
# ---------------------------------------------------------------------------


class TestNullSummarizerGroupCommits:
    def test_always_returns_none(self, tmp_path: Path) -> None:
        s = NullSummarizer()
        day = make_day_summary(tmp_path=tmp_path)
        assert s.group_commits(day) is None

    def test_max_groups_ignored(self, tmp_path: Path) -> None:
        s = NullSummarizer()
        day = make_day_summary(tmp_path=tmp_path)
        assert s.group_commits(day, max_groups=3) is None


# ---------------------------------------------------------------------------
# StubSummarizer.group_commits
# ---------------------------------------------------------------------------


class TestStubSummarizerGroupCommits:
    def test_returns_single_group_with_all_commits(self, tmp_path: Path) -> None:
        s = StubSummarizer()
        c1 = make_commit()
        c2 = make_commit(hash="b" * 16)
        day = make_day_summary(commits=[c1, c2], tmp_path=tmp_path)
        result = s.group_commits(day)
        assert result is not None
        assert len(result) == 1
        assert result[0].summary == "Stub: all commits grouped"
        assert sorted(result[0].commits, key=lambda c: c.hash) == sorted(
            [c1, c2], key=lambda c: c.hash
        )

    def test_empty_day_returns_single_empty_group(self, tmp_path: Path) -> None:
        s = StubSummarizer()
        day = DaySummary(date=date(2025, 4, 7), repo_path=tmp_path, repo_name="repo", commits=[])
        result = s.group_commits(day)
        assert result is not None
        assert len(result) == 1
        assert result[0].commits == []

    def test_max_groups_ignored(self, tmp_path: Path) -> None:
        s = StubSummarizer()
        day = make_day_summary(tmp_path=tmp_path)
        result = s.group_commits(day, max_groups=1)
        assert result is not None
        assert len(result) == 1


# ---------------------------------------------------------------------------
# LLMSummarizer.group_commits
# ---------------------------------------------------------------------------


class TestLLMSummarizerGroupCommits:
    def _make_day(self, tmp_path: Path) -> tuple[DaySummary, list]:
        c1 = make_commit(
            hash="aabbccdd11223344",
            message="feat: add login",
            insertions=100,
            deletions=10,
            files_changed=3,
        )
        c2 = make_commit(
            hash="eeff00112233445566"[:16],
            message="fix: auth bug",
            insertions=20,
            deletions=5,
            files_changed=1,
        )
        c3 = make_commit(
            hash="1122334455667788",
            message="chore: update deps",
            insertions=5,
            deletions=5,
            files_changed=2,
        )
        day = make_day_summary(commits=[c1, c2, c3], tmp_path=tmp_path)
        return day, [c1, c2, c3]

    # --- happy path ---

    def test_happy_path_all_commits_assigned(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _commits = self._make_day(tmp_path)

        response = json.dumps(
            {
                "groups": [
                    {
                        "summary": "Auth work",
                        "commit_indices": [0, 1],
                    },
                    {
                        "summary": "Maintenance",
                        "commit_indices": [2],
                    },
                ]
            }
        )
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm(response))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.group_commits(day)

        assert result is not None
        assert len(result) == 2
        summaries = {g.summary for g in result}
        assert "Auth work" in summaries
        assert "Maintenance" in summaries

    def test_stats_computed_from_real_commits_not_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Stats must come from real Commit objects, never from LLM output."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _commits = self._make_day(tmp_path)

        response = json.dumps(
            {
                "groups": [
                    {
                        "summary": "All",
                        "commit_indices": [0, 1, 2],
                        # LLM might hallucinate extra fields — they must be ignored
                        "total_insertions": 99999,
                        "total_deletions": 99999,
                    }
                ]
            }
        )
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm(response))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.group_commits(day)

        assert result is not None
        group = result[0]
        # Real stats: c1(100,10,3) + c2(20,5,1) + c3(5,5,2)
        assert group.total_insertions == 125
        assert group.total_deletions == 20
        assert group.total_files_changed == 6

    # --- max_groups hint ---

    def test_max_groups_hint_in_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _commits = self._make_day(tmp_path)

        captured_kwargs: dict = {}

        def capturing_completion(**kwargs: object) -> object:
            from types import SimpleNamespace

            captured_kwargs.update(kwargs)
            content = json.dumps(
                {
                    "groups": [
                        {
                            "summary": "g",
                            "commit_indices": list(range(len(day.commits))),
                        }
                    ]
                }
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]
        fake.completion = capturing_completion  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        s.group_commits(day, max_groups=4)

        # The hint "4" must appear somewhere in the messages sent to litellm
        messages = captured_kwargs.get("messages", [])
        all_text = " ".join(str(m.get("content", "")) for m in messages)  # type: ignore[union-attr]
        assert "4" in all_text

    # --- partial assignment → per-commit fallback groups ---

    def test_partial_assignment_creates_per_commit_groups(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, (_c1, c2, c3) = self._make_day(tmp_path)

        # LLM only assigns c1 — c2 and c3 should each get their own group
        response = json.dumps(
            {
                "groups": [
                    {"summary": "Login feature", "commit_indices": [0]},
                ]
            }
        )
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm(response))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.group_commits(day)

        assert result is not None
        # "Other changes" bucket must NOT exist
        summaries = [g.summary for g in result]
        assert "Other changes" not in summaries
        # c2 and c3 each get their own singleton group
        assert len(result) == 3  # Login feature + c2 solo + c3 solo
        unassigned_groups = [g for g in result if g.summary != "Login feature"]
        unassigned_commits = [g.commits[0] for g in unassigned_groups]
        assert sorted(unassigned_commits, key=lambda c: c.hash) == sorted(
            [c2, c3], key=lambda c: c.hash
        )
        for g in unassigned_groups:
            assert len(g.commits) == 1

    def test_all_unassigned_creates_per_commit_groups(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, commits = self._make_day(tmp_path)

        # LLM returns empty groups list — every commit gets its own group
        response = json.dumps({"groups": []})
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm(response))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.group_commits(day)

        assert result is not None
        assert len(result) == len(commits)
        assert "Other changes" not in {g.summary for g in result}
        for g in result:
            assert len(g.commits) == 1
        result_commits = [g.commits[0] for g in result]
        assert sorted(result_commits, key=lambda c: c.hash) == sorted(commits, key=lambda c: c.hash)

    def test_unassigned_group_uses_commit_message_as_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each fallback group's summary is the commit message of its commit."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        c1 = make_commit(hash="aabbccdd11223344", message="feat: add login")
        day = make_day_summary(commits=[c1], tmp_path=tmp_path)

        response = json.dumps({"groups": []})
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm(response))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.group_commits(day)

        assert result is not None
        assert result[0].summary == "feat: add login"

    # --- unrecognised index silently ignored ---

    def test_unrecognised_index_silently_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, (c1, _c2, _c3) = self._make_day(tmp_path)

        response = json.dumps(
            {
                "groups": [
                    {
                        "summary": "Real work",
                        "commit_indices": [0, 99],  # 99 is out-of-range
                    },
                    {
                        "summary": "Other",
                        "commit_indices": [1, 2],
                    },
                ]
            }
        )
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm(response))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.group_commits(day)

        assert result is not None
        # index 99 is ignored; c1 in "Real work", no catch-all needed
        real_work = next(g for g in result if g.summary == "Real work")
        assert real_work.commits == [c1]
        # No "Other changes" catch-all because all real commits were assigned
        summaries = {g.summary for g in result}
        assert "Other changes" not in summaries

    # --- out-of-bounds index silently ignored ---

    def test_out_of_bounds_index_silently_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM returning an out-of-range index should be silently ignored."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        c1 = make_commit(hash="aabbccdd" * 5)
        day = make_day_summary(commits=[c1], tmp_path=tmp_path)

        response = json.dumps({"groups": [{"summary": "Only real", "commit_indices": [0, 999]}]})
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm(response))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.group_commits(day)

        assert result is not None
        assert len(result) == 1
        assert result[0].commits == [c1]

    # --- error handling ---

    def test_invalid_json_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day = make_day_summary(tmp_path=tmp_path)
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm("not valid json!!!"))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        assert s.group_commits(day) is None

    def test_exception_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day = make_day_summary(tmp_path=tmp_path)
        monkeypatch.setitem(sys.modules, "litellm", _make_raising_litellm(RuntimeError("boom")))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        assert s.group_commits(day) is None

    def test_exception_stderr_includes_type_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """Error message must include the exception type name."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day = make_day_summary(tmp_path=tmp_path)
        monkeypatch.setitem(sys.modules, "litellm", _make_raising_litellm(ValueError("bad value")))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        s.summarize(day)
        captured = capsys.readouterr()
        assert "ValueError" in captured.err
        assert "bad value" in captured.err

    def test_exception_debug_includes_traceback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """With debug=True, a full traceback is printed to stderr."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day = make_day_summary(tmp_path=tmp_path)
        monkeypatch.setitem(
            sys.modules, "litellm", _make_raising_litellm(RuntimeError("traceback test"))
        )

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", debug=True)
        s.summarize(day)
        captured = capsys.readouterr()
        assert "Traceback" in captured.err

    def test_invalid_json_debug_shows_snippet(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """With debug=True, parse failures print a content snippet to stderr."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day = make_day_summary(tmp_path=tmp_path)
        bad_json = "this-is-not-json-at-all"
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm(bad_json))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", debug=True)
        result = s.group_commits(day)
        assert result is None
        captured = capsys.readouterr()
        assert "this-is-not-json" in captured.err

    def test_missing_api_key_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        day = make_day_summary(tmp_path=tmp_path)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        assert s.group_commits(day) is None

    def test_empty_day_returns_none_without_llm_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """group_commits() on an empty day must return None and never call litellm."""
        from datetime import date

        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")

        called: list[bool] = []

        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]

        def no_call_completion(**kwargs: object) -> object:  # pragma: no cover
            called.append(True)
            raise AssertionError("litellm.completion must not be called for empty day")

        fake.completion = no_call_completion  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake)

        empty_day = DaySummary(
            date=date(2025, 4, 7), repo_path=tmp_path, repo_name="repo", commits=[]
        )
        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.group_commits(empty_day)

        assert result is None
        assert called == [], "litellm.completion was called for an empty day"

    def test_missing_summary_key_uses_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A group with a missing 'summary' key should use 'Untitled group' fallback;
        other groups are unaffected."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _commits = self._make_day(tmp_path)

        # c1 group has no 'summary' key; c2+c3 group has a valid summary
        response = json.dumps(
            {
                "groups": [
                    {
                        # 'summary' key intentionally omitted
                        "commit_indices": [0],
                    },
                    {
                        "summary": "Auth fixes",
                        "commit_indices": [1, 2],
                    },
                ]
            }
        )
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm(response))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.group_commits(day)

        assert result is not None
        summaries = {g.summary for g in result}
        # Malformed group gets fallback, not KeyError
        assert "Untitled group" in summaries
        # Good group is unaffected
        assert "Auth fixes" in summaries

    def test_missing_groups_key_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """JSON without a 'groups' key should be handled gracefully."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day = make_day_summary(tmp_path=tmp_path)
        monkeypatch.setitem(
            sys.modules, "litellm", _make_fake_litellm(json.dumps({"result": "oops"}))
        )

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        assert s.group_commits(day) is None

    def test_response_format_json_object_in_kwargs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """response_format={"type": "json_object"} must be forwarded to litellm."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, commits = self._make_day(tmp_path)
        captured: dict = {}

        def capturing_completion(**kwargs: object) -> object:
            from types import SimpleNamespace

            captured.update(kwargs)
            content = json.dumps(
                {
                    "groups": [
                        {
                            "summary": "g",
                            "commit_indices": list(range(len(commits))),
                        }
                    ]
                }
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]
        fake.completion = capturing_completion  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        s.group_commits(day)

        assert captured.get("response_format") == {"type": "json_object"}

    def test_no_json_response_format_omits_response_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """json_response_format=False must omit response_format from litellm kwargs."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, commits = self._make_day(tmp_path)
        captured: dict = {}

        def capturing_completion(**kwargs: object) -> object:
            from types import SimpleNamespace

            captured.update(kwargs)
            content = json.dumps(
                {"groups": [{"summary": "g", "commit_indices": list(range(len(commits)))}]}
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]
        fake.completion = capturing_completion  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", json_response_format=False)
        s.group_commits(day)

        assert "response_format" not in captured

    def test_group_commits_uses_max_tokens_grouping_not_max_tokens(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """group_commits() must use max_tokens_grouping, not max_tokens."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, commits = self._make_day(tmp_path)
        captured: dict = {}

        def capturing_completion(**kwargs: object) -> object:
            from types import SimpleNamespace

            captured.update(kwargs)
            content = json.dumps(
                {
                    "groups": [
                        {
                            "summary": "g",
                            "commit_indices": list(range(len(commits))),
                        }
                    ]
                }
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]
        fake.completion = capturing_completion  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake)

        # Deliberately set max_tokens and max_tokens_grouping to different values
        s = LLMSummarizer(
            api_key_env="OPENROUTER_API_KEY", max_tokens=100, max_tokens_grouping=4096
        )
        s.group_commits(day)

        # Must use max_tokens_grouping (4096), not max_tokens (100)
        assert captured.get("max_tokens") == 4096
        assert captured.get("max_tokens") != 100

    def test_max_tokens_none_omits_param_from_litellm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When max_tokens=None, the max_tokens key must not be sent to litellm at all."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _commits = self._make_day(tmp_path)
        captured: dict = {}

        def capturing_completion(**kwargs: object) -> object:
            from types import SimpleNamespace

            captured.update(kwargs)
            content = json.dumps(
                {"groups": [{"summary": "g", "commit_indices": list(range(len(day.commits)))}]}
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]
        fake.completion = capturing_completion  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", max_tokens_grouping=None)
        s.group_commits(day)

        assert "max_tokens" not in captured, "max_tokens must be absent when set to None"

    # --- None content response ---

    def test_summarize_none_content_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When response.choices[0].message.content is None, summarize() returns None."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day = make_day_summary(tmp_path=tmp_path)
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm_none_content())

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        assert s.summarize(day) is None

    def test_group_commits_none_content_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When response.choices[0].message.content is None, group_commits() returns None."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day = make_day_summary(tmp_path=tmp_path)
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm_none_content())

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        assert s.group_commits(day) is None

    # --- duplicate commit hash in LLM response ---

    @pytest.mark.parametrize(
        "scenario,build_response",
        [
            (
                "single_duplicate_across_groups",
                lambda indices: {
                    "groups": [
                        {"summary": "Group A", "commit_indices": [indices[0]]},
                        {"summary": "Group B", "commit_indices": [indices[0]]},  # duplicate
                        {"summary": "Group C", "commit_indices": [indices[1]]},
                    ]
                },
            ),
            (
                "same_index_twice_in_same_group",
                lambda indices: {
                    "groups": [
                        {
                            "summary": "Group A",
                            "commit_indices": [indices[0], indices[0]],  # same index twice
                        },
                        {"summary": "Group B", "commit_indices": [indices[1]]},
                    ]
                },
            ),
            (
                "index_in_three_groups",
                lambda indices: {
                    "groups": [
                        {"summary": "Group A", "commit_indices": [indices[0]]},
                        {"summary": "Group B", "commit_indices": [indices[0]]},  # dup
                        {"summary": "Group C", "commit_indices": [indices[0]]},  # dup again
                    ]
                },
            ),
        ],
    )
    def test_duplicate_hash_deduplication(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        scenario: str,
        build_response: object,
    ) -> None:
        """A commit index that appears in multiple groups is assigned only to the first."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        c1 = make_commit(hash="aabb" * 4)
        c2 = make_commit(hash="ccdd" * 4)
        day = make_day_summary(commits=[c1, c2], tmp_path=tmp_path)

        response = json.dumps(build_response([0, 1]))  # type: ignore[operator]
        monkeypatch.setitem(sys.modules, "litellm", _make_fake_litellm(response))

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.group_commits(day)

        assert result is not None
        # Count total times c1 appears across all groups
        c1_count = sum(
            1 for group in result for commit in group.commits if commit.short_hash == c1.short_hash
        )
        assert c1_count == 1, f"[{scenario}] c1 appeared {c1_count} times, expected 1"


# ---------------------------------------------------------------------------
# LLMSummarizer JSON-mode auto-fallback
# ---------------------------------------------------------------------------


class TestLLMSummarizerJsonFallback:
    """When json_response_format=True and the first call returns empty, the
    summarizer should automatically retry without response_format and warn."""

    def _make_day(self, tmp_path: Path) -> DaySummary:
        c1 = make_commit()
        return make_day_summary(commits=[c1], tmp_path=tmp_path)

    def _make_seq_fake(self, responses: list[str | None]) -> tuple[types.ModuleType, list[dict]]:
        """Fake litellm that returns successive responses; records kwargs of each call."""
        from types import SimpleNamespace

        calls: list[dict] = []
        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]
        call_count = [0]

        def completion(**kwargs: object) -> object:
            idx = call_count[0]
            call_count[0] += 1
            calls.append(dict(kwargs))
            content = responses[idx]
            msg = SimpleNamespace(content=content)
            choice = SimpleNamespace(message=msg, finish_reason="stop")
            usage = SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=0 if content is None else max(1, len(content or "") // 4),
            )
            return SimpleNamespace(choices=[choice], usage=usage)

        fake.completion = completion  # type: ignore[attr-defined]
        return fake, calls

    def test_group_commits_retries_without_response_format_on_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty response with json_response_format=True triggers retry without response_format."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day = self._make_day(tmp_path)
        good_json = json.dumps({"groups": [{"summary": "g", "commit_indices": [0]}]})
        fake, calls = self._make_seq_fake([None, good_json])
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", json_response_format=True)
        result = s.group_commits(day)

        assert result is not None
        assert len(calls) == 2
        assert "response_format" in calls[0]
        assert "response_format" not in calls[1]

    def test_group_commits_fallback_warns_to_stderr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """Fallback prints a warning to stderr with actionable config advice."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day = self._make_day(tmp_path)
        good_json = json.dumps({"groups": [{"summary": "g", "commit_indices": [0]}]})
        fake, _ = self._make_seq_fake([None, good_json])
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", json_response_format=True)
        s.group_commits(day)

        captured = capsys.readouterr()
        assert "json_response_format" in captured.err
        assert "json" in captured.err.lower()

    def test_group_commits_no_retry_when_json_format_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When json_response_format=False, only one call is made (no fallback)."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day = self._make_day(tmp_path)
        # First response empty; if retry happened, second would succeed — but it shouldn't
        good_json = json.dumps({"groups": [{"summary": "g", "commit_indices": [0]}]})
        fake, calls = self._make_seq_fake([None, good_json])
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", json_response_format=False)
        result = s.group_commits(day)

        assert result is None
        assert len(calls) == 1

    def test_summarize_and_group_retries_turn1_without_response_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """summarize_and_group Turn 1 also falls back on empty response."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        c1 = make_commit()
        c2 = make_commit(hash="b" * 16)
        day = make_day_summary(commits=[c1, c2], tmp_path=tmp_path)
        groups_json = json.dumps({"groups": [{"summary": "g", "commit_indices": [0, 1]}]})
        fake, calls = self._make_seq_fake([None, groups_json, "summary text"])
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", json_response_format=True)
        summary, groups = s.summarize_and_group(day)

        assert groups is not None
        assert summary == "summary text"
        assert len(calls) >= 2
        assert "response_format" in calls[0]
        assert "response_format" not in calls[1]


# ---------------------------------------------------------------------------
# LLMSummarizer.summarize_and_group (two-turn session)
# ---------------------------------------------------------------------------


def _make_fake_litellm_seq(responses: list[str]) -> types.ModuleType:
    """Fake litellm that returns successive responses from a list (one per call)."""
    from types import SimpleNamespace

    fake = types.ModuleType("litellm")
    fake.suppress_debug_info = False  # type: ignore[attr-defined]
    fake.verbose = True  # type: ignore[attr-defined]
    call_count = [0]

    def completion(**kwargs: object) -> object:
        idx = call_count[0]
        call_count[0] += 1
        content = responses[idx]
        msg = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=msg)
        return SimpleNamespace(choices=[choice])

    fake.completion = completion  # type: ignore[attr-defined]
    return fake


class TestLLMSummarizerSummarizeAndGroup:
    def _make_day(self, tmp_path: Path) -> tuple[DaySummary, list]:
        c1 = make_commit(
            hash="aabbccdd11223344",
            message="feat: add login",
            insertions=100,
            deletions=10,
            files_changed=3,
        )
        c2 = make_commit(
            hash="eeff001122334455",
            message="fix: auth bug",
            insertions=20,
            deletions=5,
            files_changed=1,
        )
        day = make_day_summary(commits=[c1, c2], tmp_path=tmp_path)
        return day, [c1, c2]

    def test_happy_path_returns_summary_and_groups(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two sequential LLM calls return (summary, groups) tuple."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _commits = self._make_day(tmp_path)

        groups_json = json.dumps({"groups": [{"summary": "Auth work", "commit_indices": [0, 1]}]})
        summary_text = "Built authentication feature with login and bug fix."

        monkeypatch.setitem(
            sys.modules, "litellm", _make_fake_litellm_seq([groups_json, summary_text])
        )

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.summarize_and_group(day)

        assert result is not None
        summary, groups = result
        assert summary == summary_text
        assert groups is not None
        assert len(groups) == 1
        assert groups[0].summary == "Auth work"

    def test_turn2_failure_returns_none_with_groups(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If Turn 2 fails, groups from Turn 1 still returned; summary is None."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _commits = self._make_day(tmp_path)

        groups_json = json.dumps({"groups": [{"summary": "Auth work", "commit_indices": [0]}]})

        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]
        call_count = [0]

        def turn2_fails(**kwargs: object) -> object:
            from types import SimpleNamespace

            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                msg = SimpleNamespace(content=groups_json)
                return SimpleNamespace(choices=[SimpleNamespace(message=msg)])
            raise RuntimeError("Turn 2 failed")

        fake.completion = turn2_fails  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        summary, groups = s.summarize_and_group(day)

        assert summary is None
        assert groups is not None
        assert len(groups) >= 1
        assert groups[0].summary == "Auth work"

    def test_invalid_json_turn1_falls_back_to_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """Invalid JSON from Turn 1 → fallback single-turn summary, groups=None. Error logged to stderr."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _ = self._make_day(tmp_path)

        monkeypatch.setitem(
            sys.modules, "litellm", _make_fake_litellm_seq(["not-valid-json", "ignored"])
        )

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        result = s.summarize_and_group(day)
        summary, groups = result
        assert groups is None
        assert summary == "ignored"  # fallback single-turn summary returned
        captured = capsys.readouterr()
        assert "[gitvisual]" in captured.err

    def test_max_groups_flows_to_grouping_instruction(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """max_groups parameter value appears in Turn 1 messages."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _ = self._make_day(tmp_path)

        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]
        captured_messages: list[list] = []
        responses = [
            json.dumps({"groups": [{"summary": "g", "commit_indices": [0]}]}),
            "summary",
        ]
        call_count = [0]

        def capturing(**kwargs: object) -> object:
            from types import SimpleNamespace

            captured_messages.append(list(kwargs.get("messages", [])))  # type: ignore[arg-type]
            idx = call_count[0]
            call_count[0] += 1
            msg = SimpleNamespace(content=responses[idx])
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        fake.completion = capturing  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        s.summarize_and_group(day, max_groups=7)

        # Turn 1 messages must mention the group count hint
        turn1_msgs = captured_messages[0]
        all_text = " ".join(str(m.get("content", "")) for m in turn1_msgs)
        assert "7 group" in all_text

    def test_max_groups_none_no_hint_in_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """max_groups=None → no group count hint in Turn 1 messages."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _ = self._make_day(tmp_path)

        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]
        captured_messages: list[list] = []
        responses = [
            json.dumps({"groups": [{"summary": "g", "commit_indices": [0]}]}),
            "summary",
        ]
        call_count = [0]

        def capturing(**kwargs: object) -> object:
            from types import SimpleNamespace

            captured_messages.append(list(kwargs.get("messages", [])))  # type: ignore[arg-type]
            idx = call_count[0]
            call_count[0] += 1
            msg = SimpleNamespace(content=responses[idx])
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        fake.completion = capturing  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        s.summarize_and_group(day, max_groups=None)

        turn1_msgs = captured_messages[0]
        all_text = " ".join(str(m.get("content", "")) for m in turn1_msgs)
        # When max_groups=None, the specific count hint "Try to use at most N groups" is absent
        import re

        assert not re.search(r"Try to use at most \d+ group", all_text)

    def test_empty_day_returns_none_none(self, tmp_path: Path) -> None:
        """Empty day → (None, None) without any LLM call."""
        from datetime import date

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY")
        empty_day = DaySummary(
            date=date(2025, 4, 7), repo_path=tmp_path, repo_name="repo", commits=[]
        )
        assert s.summarize_and_group(empty_day) == (None, None)

    # --- Turn 1.5 retry for unassigned commits ---

    def test_unassigned_commits_trigger_retry_round(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Turn 1 partial assignment → Turn 1.5 fires for unassigned → all commits in result."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, [c1, c2] = self._make_day(tmp_path)

        # Turn 1: only c1 (index 0) assigned; c2 left out
        turn1 = json.dumps({"groups": [{"summary": "Login feature", "commit_indices": [0]}]})
        # Turn 1.5: retry_day has just c2, re-indexed as 0
        turn1_5 = json.dumps({"groups": [{"summary": "Auth bug fix", "commit_indices": [0]}]})
        turn2 = "Shipped login and fixed auth."

        monkeypatch.setitem(
            sys.modules,
            "litellm",
            _make_fake_litellm_seq([turn1, turn1_5, turn2]),
        )

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", json_response_format=False)
        summary, groups = s.summarize_and_group(day)

        assert summary == turn2
        assert groups is not None
        # Both commits must appear exactly once
        all_commits = [c for g in groups for c in g.commits]
        assert sorted(all_commits, key=lambda c: c.hash) == sorted([c1, c2], key=lambda c: c.hash)
        # Both real LLM groups present (no singletons needed)
        summaries = {g.summary for g in groups}
        assert "Login feature" in summaries
        assert "Auth bug fix" in summaries

    def test_no_retry_when_all_commits_assigned(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When Turn 1 assigns all commits, no Turn 1.5 call is made (2 calls total)."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _ = self._make_day(tmp_path)

        call_count = [0]
        responses = [
            json.dumps({"groups": [{"summary": "All work", "commit_indices": [0, 1]}]}),
            "Did everything.",
        ]

        def counting_completion(**kwargs: object) -> object:
            from types import SimpleNamespace

            idx = call_count[0]
            call_count[0] += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=responses[idx]))]
            )

        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]
        fake.completion = counting_completion  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", json_response_format=False)
        summary, groups = s.summarize_and_group(day)

        assert call_count[0] == 2  # Turn 1 + Turn 2 only
        assert groups is not None
        assert summary == "Did everything."

    def test_retry_bad_json_falls_back_to_singletons(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Turn 1.5 returning invalid JSON → unassigned commit becomes singleton group."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, [_c1, c2] = self._make_day(tmp_path)

        turn1 = json.dumps({"groups": [{"summary": "Login", "commit_indices": [0]}]})
        monkeypatch.setitem(
            sys.modules,
            "litellm",
            _make_fake_litellm_seq([turn1, "not valid json", "summary"]),
        )

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", json_response_format=False)
        _summary, groups = s.summarize_and_group(day)

        assert groups is not None
        all_commits = [c for g in groups for c in g.commits]
        assert c2 in all_commits
        # c2 singleton uses the commit message as its summary
        singleton = next(g for g in groups if c2 in g.commits)
        assert singleton.summary == c2.message

    def test_retry_empty_response_falls_back_to_singletons(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Turn 1.5 returning None → unassigned commit becomes singleton group."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, [_c1, c2] = self._make_day(tmp_path)

        turn1 = json.dumps({"groups": [{"summary": "Login", "commit_indices": [0]}]})
        # None in the sequence → content=None → _call_llm returns None
        monkeypatch.setitem(
            sys.modules,
            "litellm",
            _make_fake_litellm_seq([turn1, None, "summary"]),  # type: ignore[list-item]
        )

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", json_response_format=False)
        _summary, groups = s.summarize_and_group(day)

        assert groups is not None
        all_commits = [c for g in groups for c in g.commits]
        assert c2 in all_commits

    def test_retry_debug_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """debug=True prints Turn 1.5 info to stderr when unassigned commits are retried."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _ = self._make_day(tmp_path)

        turn1 = json.dumps({"groups": [{"summary": "Login", "commit_indices": [0]}]})
        turn1_5 = json.dumps({"groups": [{"summary": "Fix", "commit_indices": [0]}]})
        monkeypatch.setitem(
            sys.modules,
            "litellm",
            _make_fake_litellm_seq([turn1, turn1_5, "summary"]),
        )

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", debug=True, json_response_format=False)
        s.summarize_and_group(day)

        captured = capsys.readouterr()
        assert "1.5" in captured.err
        assert "unassigned" in captured.err

    def test_no_json_response_format_omits_from_turn1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """json_response_format=False must not send response_format in summarize_and_group."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        day, _ = self._make_day(tmp_path)
        captured_calls: list[dict] = []

        groups_json = json.dumps({"groups": [{"summary": "g", "commit_indices": [0, 1]}]})

        def capturing(**kwargs: object) -> object:
            from types import SimpleNamespace

            captured_calls.append(dict(kwargs))
            idx = len(captured_calls) - 1
            content = groups_json if idx == 0 else "Did stuff."
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

        fake = types.ModuleType("litellm")
        fake.suppress_debug_info = False  # type: ignore[attr-defined]
        fake.verbose = True  # type: ignore[attr-defined]
        fake.completion = capturing  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", fake)

        s = LLMSummarizer(api_key_env="OPENROUTER_API_KEY", json_response_format=False)
        s.summarize_and_group(day)

        assert len(captured_calls) >= 1
        assert "response_format" not in captured_calls[0]


class TestStubSummarizerSummarizeAndGroup:
    def test_returns_summary_and_groups_for_active_day(self, tmp_path: Path) -> None:
        s = StubSummarizer()
        c1 = make_commit()
        c2 = make_commit(hash="b" * 16)
        day = make_day_summary(commits=[c1, c2], tmp_path=tmp_path)
        summary, groups = s.summarize_and_group(day)
        assert summary is not None
        assert isinstance(summary, str)
        assert groups is not None
        assert len(groups) == 1
        assert groups[0].summary == "Stub: all commits grouped"
        assert sorted(groups[0].commits, key=lambda c: c.hash) == sorted(
            [c1, c2], key=lambda c: c.hash
        )

    def test_returns_empty_groups_for_empty_day(self, tmp_path: Path) -> None:
        from datetime import date

        s = StubSummarizer()
        day = DaySummary(date=date(2025, 4, 7), repo_path=tmp_path, repo_name="repo", commits=[])
        result = s.summarize_and_group(day)
        assert result == (None, None)

    def test_max_groups_ignored(self, tmp_path: Path) -> None:
        s = StubSummarizer()
        day = make_day_summary(tmp_path=tmp_path)
        summary, groups = s.summarize_and_group(day, max_groups=1)
        assert summary is not None
        assert groups is not None


class TestNullSummarizerSummarizeAndGroup:
    def test_always_returns_none_none(self, tmp_path: Path) -> None:
        s = NullSummarizer()
        day = make_day_summary(tmp_path=tmp_path)
        assert s.summarize_and_group(day) == (None, None)

    def test_empty_day_returns_none_none(self, tmp_path: Path) -> None:
        from datetime import date

        s = NullSummarizer()
        day = DaySummary(date=date(2025, 4, 7), repo_path=tmp_path, repo_name="repo", commits=[])
        assert s.summarize_and_group(day) == (None, None)

    def test_max_groups_ignored(self, tmp_path: Path) -> None:
        s = NullSummarizer()
        day = make_day_summary(tmp_path=tmp_path)
        assert s.summarize_and_group(day, max_groups=5) == (None, None)
