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

    def test_discover_generate_flag(self, tmp_path: Path) -> None:
        """Discover with --generate creates cards for active repos."""
        repo = tmp_path / "active-repo"
        init_git_repo(repo)
        make_commit_in_repo(
            repo,
            files={"main.py": "print('active')"},
            message="feat: active commit",
            author_date=f"{date.today().isoformat()}T12:00:00+00:00",
        )

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "discover",
                str(tmp_path),
                "--generate",
                "--output",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        cards = list(output_dir.glob("*.png"))
        assert len(cards) >= 1


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
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        repo = self._make_repo_with_commit(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Built a new feature for the project."

        with patch("dotenv.load_dotenv"), patch("litellm.completion", return_value=mock_response):
            result = runner.invoke(
                app,
                ["generate", str(repo), "--output", str(output_dir), "--summarize"],
            )

        assert result.exit_code == 0
        cards = list(output_dir.glob("*.png"))
        assert len(cards) == 1
        # No post-generate failure warning
        assert "no llm summaries" not in result.output.lower()
