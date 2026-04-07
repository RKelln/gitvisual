"""Shared test fixtures."""

from __future__ import annotations

import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from gitvisual.git.models import Commit, DaySummary, FileChange

# ---------------------------------------------------------------------------
# Sample data factories
# ---------------------------------------------------------------------------


def make_file_change(
    path: str = "src/main.py",
    status: str = "Modified",
    insertions: int = 10,
    deletions: int = 2,
) -> FileChange:
    return FileChange(path=path, status=status, insertions=insertions, deletions=deletions)


def make_commit(
    hash: str = "abcdef1234567890",
    message: str = "feat: add new feature",
    author: str = "Dev",
    files: list[FileChange] | None = None,
    insertions: int = 10,
    deletions: int = 2,
    files_changed: int = 1,
    target_date: date | None = None,
) -> Commit:
    target_date = target_date or date(2025, 4, 7)
    return Commit(
        hash=hash,
        short_hash=hash[:7],
        message=message,
        body="",
        author=author,
        email="dev@example.com",
        timestamp=datetime(
            target_date.year, target_date.month, target_date.day, 12, 0, 0, tzinfo=UTC
        ),
        files=files or [make_file_change()],
        insertions=insertions,
        deletions=deletions,
        files_changed=files_changed,
    )


def make_day_summary(
    target_date: date | None = None,
    repo_name: str = "testrepo",
    commits: list[Commit] | None = None,
    summary: str | None = None,
    tmp_path: Path | None = None,
) -> DaySummary:
    target_date = target_date or date(2025, 4, 7)
    repo_path = tmp_path or Path("/tmp/testrepo")
    return DaySummary(
        date=target_date,
        repo_path=repo_path,
        repo_name=repo_name,
        commits=commits or [make_commit(target_date=target_date)],
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Fixture git repo helpers
# ---------------------------------------------------------------------------


def init_git_repo(
    path: Path, *, author: str = "Test User", email: str = "test@example.com"
) -> None:
    """Initialize a fresh git repo with a configured author."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", author], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", email], cwd=path, check=True, capture_output=True
    )


def make_commit_in_repo(
    repo_path: Path,
    *,
    files: dict[str, str],
    message: str,
    author_date: str,  # ISO format: "2025-04-07T12:00:00+00:00"
) -> str:
    """Create a commit in a git repo. Returns the commit hash."""
    for filename, content in files.items():
        fpath = repo_path / filename
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)
        subprocess.run(["git", "add", str(fpath)], cwd=repo_path, check=True, capture_output=True)

    env = {
        "GIT_AUTHOR_DATE": author_date,
        "GIT_COMMITTER_DATE": author_date,
        "GIT_AUTHOR_NAME": "Test User",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test User",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    import os

    full_env = {**os.environ, **env}

    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_path,
        check=True,
        capture_output=True,
        env=full_env,
    )

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_file_change() -> FileChange:
    return make_file_change()


@pytest.fixture
def sample_commit() -> Commit:
    return make_commit()


@pytest.fixture
def sample_day(tmp_path: Path) -> DaySummary:
    return make_day_summary(tmp_path=tmp_path)


@pytest.fixture
def empty_day(tmp_path: Path) -> DaySummary:
    return DaySummary(
        date=date(2025, 4, 7),
        repo_path=tmp_path,
        repo_name="testrepo",
        commits=[],
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A fresh empty git repository."""
    repo = tmp_path / "repo"
    init_git_repo(repo)
    return repo
