"""Tests for CLI commands using Typer CliRunner."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gitvisual.cli import app
from tests.conftest import init_git_repo, make_commit_in_repo

runner = CliRunner()


class TestGenerate:
    def test_generate_single_repo_creates_card(self, tmp_path: Path) -> None:
        """Generate a card for a single repo on today's date."""
        repo = tmp_path / "testrepo"
        init_git_repo(repo)
        make_commit_in_repo(
            repo,
            files={"main.py": "print('hello')"},
            message="feat: add main",
            author_date=f"{date.today().isoformat()}T12:00:00+00:00",
        )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            ["generate", str(repo), "--output", str(output_dir), "--no-summary"],
        )

        assert result.exit_code == 0
        assert "commit(s)" in result.stdout
        cards = list(output_dir.glob("*.png"))
        assert len(cards) == 1

    def test_generate_with_date_option(self, tmp_path: Path) -> None:
        """Generate a card for a specific date."""
        repo = tmp_path / "testrepo"
        init_git_repo(repo)
        make_commit_in_repo(
            repo,
            files={"main.py": "x = 1"},
            message="feat: add x",
            author_date="2025-04-07T12:00:00+00:00",
        )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "generate",
                str(repo),
                "--date",
                "2025-04-07",
                "--output",
                str(output_dir),
                "--no-summary",
            ],
        )

        assert result.exit_code == 0
        cards = list(output_dir.glob("*.png"))
        assert len(cards) == 1
        assert "2025-04-07" in cards[0].name

    def test_generate_with_yesterday(self, tmp_path: Path) -> None:
        """Generate a card for yesterday's date."""
        repo = tmp_path / "testrepo"
        init_git_repo(repo)
        yesterday = date.today() - timedelta(days=1)
        make_commit_in_repo(
            repo,
            files={"main.py": "y = 2"},
            message="feat: add y",
            author_date=f"{yesterday.isoformat()}T12:00:00+00:00",
        )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            ["generate", str(repo), "--yesterday", "--output", str(output_dir), "--no-summary"],
        )

        assert result.exit_code == 0
        cards = list(output_dir.glob("*.png"))
        assert len(cards) == 1

    def test_generate_with_last_week(self, tmp_path: Path) -> None:
        """Generate cards for the last 7 days."""
        repo = tmp_path / "testrepo"
        init_git_repo(repo)
        today = date.today()
        for i in range(3):
            d = today - timedelta(days=i)
            make_commit_in_repo(
                repo,
                files={f"file{i}.py": str(i)},
                message=f"feat: day {i}",
                author_date=f"{d.isoformat()}T12:00:00+00:00",
            )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            ["generate", str(repo), "--last-week", "--output", str(output_dir), "--no-summary"],
        )

        assert result.exit_code == 0
        cards = list(output_dir.glob("*.png"))
        assert len(cards) >= 1

    def test_generate_no_commits(self, tmp_path: Path) -> None:
        """Generate with no commits produces no cards."""
        repo = tmp_path / "emptyrepo"
        init_git_repo(repo)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            ["generate", str(repo), "--output", str(output_dir), "--no-summary"],
        )

        assert result.exit_code == 0
        cards = list(output_dir.glob("*.png"))
        assert len(cards) == 0
        assert "no commits" in result.stdout.lower() or "no cards" in result.stdout.lower()

    def test_generate_with_style_option(self, tmp_path: Path) -> None:
        """Generate with custom style option."""
        repo = tmp_path / "testrepo"
        init_git_repo(repo)
        make_commit_in_repo(
            repo,
            files={"main.py": "pass"},
            message="init",
            author_date=f"{date.today().isoformat()}T12:00:00+00:00",
        )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "generate",
                str(repo),
                "--style",
                "compact",
                "--output",
                str(output_dir),
                "--no-summary",
            ],
        )

        assert result.exit_code == 0

    def test_generate_not_a_git_repo(self, tmp_path: Path) -> None:
        """Generate with non-git repo shows warning."""
        not_git = tmp_path / "notgit"
        not_git.mkdir()

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            ["generate", str(not_git), "--output", str(output_dir), "--no-summary"],
        )

        assert result.exit_code == 0
        assert "not a git repo" in result.stdout.lower() or "skipping" in result.stdout.lower()

    def test_generate_with_summarize(self, tmp_path: Path) -> None:
        """Generate with summarize option uses LLM stub."""
        repo = tmp_path / "testrepo"
        init_git_repo(repo)
        make_commit_in_repo(
            repo,
            files={"main.py": "x = 1"},
            message="feat: add feature",
            author_date=f"{date.today().isoformat()}T12:00:00+00:00",
        )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            ["generate", str(repo), "--output", str(output_dir), "--summarize", "--stub-llm"],
        )

        assert result.exit_code == 0
        cards = list(output_dir.glob("*.png"))
        assert len(cards) == 1


class TestDiscover:
    def test_discover_finds_repos(self, tmp_path: Path) -> None:
        """Discover finds git repos in a directory."""
        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"
        init_git_repo(repo1)
        init_git_repo(repo2)
        make_commit_in_repo(
            repo1,
            files={"f.py": "pass"},
            message="feat: first",
            author_date=f"{date.today().isoformat()}T12:00:00+00:00",
        )

        result = runner.invoke(
            app,
            ["discover", str(tmp_path)],
        )

        assert result.exit_code == 0
        assert "repo1" in result.stdout or "repo2" in result.stdout

    def test_discover_with_date(self, tmp_path: Path) -> None:
        """Discover with specific date filters by activity."""
        repo = tmp_path / "myrepo"
        init_git_repo(repo)
        make_commit_in_repo(
            repo,
            files={"f.py": "x=1"},
            message="feat: add x",
            author_date="2025-04-07T12:00:00+00:00",
        )

        result = runner.invoke(
            app,
            ["discover", str(tmp_path), "--date", "2025-04-07"],
        )

        assert result.exit_code == 0

    def test_discover_with_yesterday(self, tmp_path: Path) -> None:
        """Discover with yesterday option."""
        repo = tmp_path / "myrepo"
        init_git_repo(repo)
        yesterday = date.today() - timedelta(days=1)
        make_commit_in_repo(
            repo,
            files={"f.py": "y=2"},
            message="feat: add y",
            author_date=f"{yesterday.isoformat()}T12:00:00+00:00",
        )

        result = runner.invoke(
            app,
            ["discover", str(tmp_path), "--yesterday"],
        )

        assert result.exit_code == 0

    def test_discover_no_repos_found(self, tmp_path: Path) -> None:
        """Discover with no repos shows appropriate message."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = runner.invoke(
            app,
            ["discover", str(empty_dir)],
        )

        assert result.exit_code == 0
        assert "no git repositories" in result.stdout.lower() or "found 0" in result.stdout.lower()

    def test_discover_does_not_accept_generate_flag(self, tmp_path: Path) -> None:
        """discover --generate is no longer valid; use generate --discover instead."""
        result = runner.invoke(app, ["discover", str(tmp_path), "--generate"])
        assert result.exit_code != 0


class TestGenerateDiscover:
    def test_generate_discover_creates_cards_for_active_repos(self, tmp_path: Path) -> None:
        """generate --discover finds repos with activity and generates cards."""
        repo = tmp_path / "active-repo"
        init_git_repo(repo)
        make_commit_in_repo(
            repo,
            files={"main.py": "print('active')"},
            message="feat: active commit",
            author_date=f"{date.today().isoformat()}T12:00:00+00:00",
        )

        # Repo with no commits today — should be skipped
        quiet = tmp_path / "quiet-repo"
        init_git_repo(quiet)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "generate",
                "--discover",
                str(tmp_path),
                "--output",
                str(output_dir),
                "--no-summary",
            ],
        )

        assert result.exit_code == 0, result.output
        cards = list(output_dir.glob("*.png"))
        assert len(cards) == 1

    def test_generate_repos_and_discover_are_mutually_exclusive(self, tmp_path: Path) -> None:
        """Providing both explicit repos and --discover is an error."""
        repo = tmp_path / "repo"
        init_git_repo(repo)

        result = runner.invoke(
            app,
            ["generate", str(repo), "--discover", str(tmp_path), "--no-summary"],
        )

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower() or "cannot" in result.output.lower()

    def test_generate_requires_repos_or_discover(self, tmp_path: Path) -> None:
        """generate with no repos and no --discover is an error."""
        result = runner.invoke(app, ["generate", "--no-summary"])
        assert result.exit_code != 0


class TestConfigInit:
    def test_config_init_creates_file(self, tmp_path: Path) -> None:
        """Config init creates a config.toml file."""
        config_path = tmp_path / "config.toml"

        result = runner.invoke(
            app,
            ["config", "init", "--path", str(config_path)],
        )

        assert result.exit_code == 0
        assert config_path.exists()
        assert "config" in result.stdout.lower()

    def test_config_init_fails_if_exists(self, tmp_path: Path) -> None:
        """Config init fails if file exists without --force."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("# existing")

        result = runner.invoke(
            app,
            ["config", "init", "--path", str(config_path)],
        )

        assert result.exit_code == 1
        assert "exists" in result.stdout.lower() or "force" in result.stdout.lower()

    def test_config_init_force_overwrites(self, tmp_path: Path) -> None:
        """Config init with --force overwrites existing file."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("# old")

        result = runner.invoke(
            app,
            ["config", "init", "--path", str(config_path), "--force"],
        )

        assert result.exit_code == 0
        assert config_path.exists()


class TestConfigShow:
    def test_config_show_displays_config(self, tmp_path: Path) -> None:
        """Config show displays configuration."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            """[defaults]
output_dir = "/tmp/test"
summarize = false

[llm]
model = "gpt-4"

[render]
width = 800

[repos]
exclude = []

[theme]
name = "light"
"""
        )

        result = runner.invoke(
            app,
            ["config", "show", "--config", str(config_path)],
        )

        assert result.exit_code == 0
        assert (
            "defaults" in result.stdout.lower()
            or "llm" in result.stdout.lower()
            or "render" in result.stdout.lower()
        )

    def test_config_show_with_missing_file(self, tmp_path: Path) -> None:
        """Config show handles missing config gracefully by showing defaults."""
        missing = tmp_path / "nonexistent.toml"

        result = runner.invoke(
            app,
            ["config", "show", "--config", str(missing)],
        )

        assert result.exit_code == 0
        assert "defaults" in result.stdout.lower() or "llm" in result.stdout.lower()


class TestGenerateLLMSummary:
    """Tests for --summarize / LLM integration in the generate command."""

    def _make_repo_with_commit(self, tmp_path: Path) -> Path:
        repo = tmp_path / "testrepo"
        init_git_repo(repo)
        make_commit_in_repo(
            repo,
            files={"main.py": "x = 1"},
            message="feat: add feature",
            author_date=f"{date.today().isoformat()}T12:00:00+00:00",
        )
        return repo

    def test_warns_when_api_key_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--summarize without API key env var set shows a pre-flight warning."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        repo = self._make_repo_with_commit(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Suppress load_dotenv so monkeypatch.delenv isn't overridden by .env file
        with patch("dotenv.load_dotenv"):
            result = runner.invoke(
                app,
                ["generate", str(repo), "--output", str(output_dir), "--summarize"],
            )

        assert result.exit_code == 0
        assert "OPENROUTER_API_KEY" in result.output
        assert "not set" in result.output.lower() or "warning" in result.output.lower()

    def test_post_warning_when_llm_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Post-generate warning shown when --summarize is set but LLM returns None."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        repo = self._make_repo_with_commit(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with (
            patch("dotenv.load_dotenv"),
            patch("litellm.completion", side_effect=Exception("connection error")),
        ):
            result = runner.invoke(
                app,
                ["generate", str(repo), "--output", str(output_dir), "--summarize"],
            )

        assert result.exit_code == 0
        # Card still generated even when LLM fails
        cards = list(output_dir.glob("*.png"))
        assert len(cards) == 1
        # Post-generate hint shown
        assert "no llm summaries" in result.output.lower() or "not set" in result.output.lower()

    def test_summary_included_when_llm_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When LLM returns a summary, card is generated and no warning is shown."""
        import json

        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        repo = self._make_repo_with_commit(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # With summarize_and_group(): Turn 1 needs valid JSON groups, Turn 2 returns summary text
        groups_response = MagicMock()
        groups_response.choices[0].message.content = json.dumps(
            {"groups": [{"summary": "Feature work", "commit_hashes": []}]}
        )
        summary_response = MagicMock()
        summary_response.choices[0].message.content = "Built a new feature for the project."

        with (
            patch("dotenv.load_dotenv"),
            patch("litellm.completion", side_effect=[groups_response, summary_response]),
        ):
            result = runner.invoke(
                app,
                ["generate", str(repo), "--output", str(output_dir), "--summarize"],
            )

        assert result.exit_code == 0
        cards = list(output_dir.glob("*.png"))
        assert len(cards) == 1
        # No post-generate failure warning
        assert "no llm summaries" not in result.output.lower()

    def test_model_flag_overrides_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--model flag overrides the model from config."""
        import json

        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        repo = self._make_repo_with_commit(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        captured: dict[str, object] = {}
        call_count = [0]
        # Turn 1: JSON groups; Turn 2: summary text
        responses = [
            json.dumps({"groups": [{"summary": "g", "commit_hashes": []}]}),
            "Did some work.",
        ]

        def capture_completion(**kwargs: object) -> MagicMock:
            captured.update(kwargs)
            mock = MagicMock()
            mock.choices[0].message.content = responses[call_count[0] % len(responses)]
            call_count[0] += 1
            return mock

        with (
            patch("dotenv.load_dotenv"),
            patch("litellm.completion", side_effect=capture_completion),
        ):
            result = runner.invoke(
                app,
                [
                    "generate",
                    str(repo),
                    "--output",
                    str(output_dir),
                    "--summarize",
                    "--model",
                    "openrouter/openai/gpt-4o-mini",
                ],
            )

        assert result.exit_code == 0
        assert captured.get("model") == "openrouter/openai/gpt-4o-mini"

    def test_max_tokens_flag_overrides_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--max-tokens flag overrides max_tokens for the summarize LLM call."""
        import json

        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        repo = self._make_repo_with_commit(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Capture all calls (Turn 1 = grouping, Turn 2 = summary)
        all_calls: list[dict[str, object]] = []
        call_count = [0]
        responses = [
            json.dumps({"groups": [{"summary": "g", "commit_hashes": []}]}),
            "Did some work.",
        ]

        def capture_completion(**kwargs: object) -> MagicMock:
            all_calls.append(dict(kwargs))
            mock = MagicMock()
            mock.choices[0].message.content = responses[call_count[0] % len(responses)]
            call_count[0] += 1
            return mock

        with (
            patch("dotenv.load_dotenv"),
            patch("litellm.completion", side_effect=capture_completion),
        ):
            result = runner.invoke(
                app,
                [
                    "generate",
                    str(repo),
                    "--output",
                    str(output_dir),
                    "--summarize",
                    "--max-tokens",
                    "42",
                ],
            )

        assert result.exit_code == 0
        # With summarize_and_group(): Turn 1 = grouping (uses max_tokens_grouping),
        # Turn 2 = summary (uses max_tokens overridden to 42).
        assert len(all_calls) >= 2
        assert all_calls[1].get("max_tokens") == 42


class TestGenerateGroupCommits:
    """Tests for commit grouping wired into the generate command."""

    def _make_repo_with_commit(self, tmp_path: Path) -> Path:
        repo = tmp_path / "testrepo"
        init_git_repo(repo)
        make_commit_in_repo(
            repo,
            files={"main.py": "x = 1"},
            message="feat: add feature",
            author_date=f"{date.today().isoformat()}T12:00:00+00:00",
        )
        return repo

    def test_stub_llm_sets_commit_groups(self, tmp_path: Path) -> None:
        """--summarize --stub-llm → DaySummary rendered has commit_groups set."""
        from gitvisual.git.models import CommitGroup
        from gitvisual.render.card import CardRenderer

        repo = self._make_repo_with_commit(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        rendered_days: list = []

        original_render = CardRenderer.render_to_file

        def capturing_render(self_inner: CardRenderer, day: object, output_path: object) -> object:
            rendered_days.append(day)
            return original_render(self_inner, day, output_path)  # type: ignore[arg-type]

        with patch.object(CardRenderer, "render_to_file", capturing_render):
            result = runner.invoke(
                app,
                ["generate", str(repo), "--output", str(output_dir), "--summarize", "--stub-llm"],
            )

        assert result.exit_code == 0, result.output
        assert len(rendered_days) == 1
        day = rendered_days[0]
        assert day.commit_groups is not None
        assert len(day.commit_groups) >= 1
        assert all(isinstance(g, CommitGroup) for g in day.commit_groups)

    def test_no_summary_commit_groups_remain_none(self, tmp_path: Path) -> None:
        """--no-summary (default) → commit_groups stays None on rendered day."""
        from gitvisual.render.card import CardRenderer

        repo = self._make_repo_with_commit(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        rendered_days: list = []

        original_render = CardRenderer.render_to_file

        def capturing_render(self_inner: CardRenderer, day: object, output_path: object) -> object:
            rendered_days.append(day)
            return original_render(self_inner, day, output_path)  # type: ignore[arg-type]

        with patch.object(CardRenderer, "render_to_file", capturing_render):
            result = runner.invoke(
                app,
                ["generate", str(repo), "--output", str(output_dir), "--no-summary"],
            )

        assert result.exit_code == 0, result.output
        assert len(rendered_days) == 1
        day = rendered_days[0]
        assert day.commit_groups is None


class TestVersionFlag:
    def test_version_flag_exits_zero(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0

    def test_version_flag_outputs_version_string(self) -> None:
        result = runner.invoke(app, ["--version"])
        output = result.output.strip()
        assert len(output) > 0, "Expected a non-empty version string"
        # Version should look like a semver or PEP 440 string (e.g. "0.1.0")
        assert any(c.isdigit() for c in output), (
            f"Expected digits in version string, got: {output!r}"
        )


class TestGenerateSummarizeAndGroup:
    """Tests for the new summarize_and_group() wiring in generate command."""

    def _make_repo_with_commit(self, tmp_path: Path) -> Path:
        repo = tmp_path / "testrepo"
        init_git_repo(repo)
        make_commit_in_repo(
            repo,
            files={"main.py": "x = 1"},
            message="feat: add feature",
            author_date=f"{date.today().isoformat()}T12:00:00+00:00",
        )
        return repo

    def test_stub_llm_uses_summarize_and_group(self, tmp_path: Path) -> None:
        """--stub-llm triggers summarize_and_group(), not separate summarize+group_commits."""
        from gitvisual.llm.summarizer import StubSummarizer

        repo = self._make_repo_with_commit(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        summarize_and_group_calls: list = []
        original = StubSummarizer.summarize_and_group

        def capturing(self_inner: StubSummarizer, day: object, max_groups: object = None) -> object:
            summarize_and_group_calls.append({"max_groups": max_groups})
            return original(self_inner, day, max_groups=max_groups)  # type: ignore[arg-type]

        with patch.object(StubSummarizer, "summarize_and_group", capturing):
            result = runner.invoke(
                app,
                ["generate", str(repo), "--output", str(output_dir), "--summarize", "--stub-llm"],
            )

        assert result.exit_code == 0, result.output
        assert len(summarize_and_group_calls) >= 1

    def test_llm_summarize_and_group_called_with_max_groups(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """summarize_and_group() receives max_groups=config.render.max_groups_shown."""
        from gitvisual.config import Config
        from gitvisual.llm.summarizer import StubSummarizer

        repo = self._make_repo_with_commit(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        calls: list[dict] = []
        original = StubSummarizer.summarize_and_group

        def capturing(self_inner: StubSummarizer, day: object, max_groups: object = None) -> object:
            calls.append({"max_groups": max_groups})
            return original(self_inner, day, max_groups=max_groups)  # type: ignore[arg-type]

        with patch.object(StubSummarizer, "summarize_and_group", capturing):
            result = runner.invoke(
                app,
                ["generate", str(repo), "--output", str(output_dir), "--summarize", "--stub-llm"],
            )

        assert result.exit_code == 0, result.output
        assert len(calls) >= 1
        expected = Config().render.max_groups_shown
        assert calls[0]["max_groups"] == expected

    def test_summarize_and_group_sets_both_summary_and_groups(self, tmp_path: Path) -> None:
        """summarize_and_group() result populates both summary and commit_groups on day."""
        from gitvisual.render.card import CardRenderer

        repo = self._make_repo_with_commit(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        rendered_days: list = []
        original_render = CardRenderer.render_to_file

        def capturing_render(self_inner: CardRenderer, day: object, output_path: object) -> object:
            rendered_days.append(day)
            return original_render(self_inner, day, output_path)  # type: ignore[arg-type]

        with patch.object(CardRenderer, "render_to_file", capturing_render):
            result = runner.invoke(
                app,
                ["generate", str(repo), "--output", str(output_dir), "--summarize", "--stub-llm"],
            )

        assert result.exit_code == 0, result.output
        assert len(rendered_days) == 1
        day = rendered_days[0]
        assert day.summary is not None
        assert day.commit_groups is not None
        assert len(day.commit_groups) >= 1
