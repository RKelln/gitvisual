"""Tests for git collector — uses real temporary git repos."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from gitvisual.git.collector import (
    GitCollectorError,
    _parse_files,
    _parse_stats,
    collect_day,
    collect_range,
    discover_repos,
    get_repo_name,
    is_git_repo,
)
from tests.conftest import init_git_repo, make_commit_in_repo

# ---------------------------------------------------------------------------
# Unit tests for parsing helpers
# ---------------------------------------------------------------------------


class TestParseStats:
    @pytest.mark.parametrize(
        "stat_line,expected",
        [
            ("1 file changed, 5 insertions(+), 2 deletions(-)", (1, 5, 2)),
            ("3 files changed, 10 insertions(+)", (3, 10, 0)),
            ("2 files changed, 0 insertions(+), 4 deletions(-)", (2, 0, 4)),
            ("1 file changed, 1 insertion(+)", (1, 1, 0)),
            ("", (0, 0, 0)),
            ("some random text", (0, 0, 0)),
        ],
    )
    def test_parse_stats(self, stat_line: str, expected: tuple[int, int, int]) -> None:
        assert _parse_stats(stat_line) == expected


class TestParseFiles:
    def test_added_file(self) -> None:
        out = "A\tsrc/foo.py"
        files = _parse_files(out)
        assert len(files) == 1
        assert files[0].status == "Added"
        assert files[0].path == "src/foo.py"

    def test_modified_file(self) -> None:
        files = _parse_files("M\tsrc/bar.py")
        assert files[0].status == "Modified"

    def test_deleted_file(self) -> None:
        files = _parse_files("D\told.py")
        assert files[0].status == "Deleted"

    def test_renamed_file(self) -> None:
        files = _parse_files("R100\told.py\tnew.py")
        assert files[0].status == "Renamed"
        assert "old.py" in files[0].path
        assert "new.py" in files[0].path

    def test_multiple_files(self) -> None:
        out = "A\ta.py\nM\tb.py\nD\tc.py"
        files = _parse_files(out)
        assert len(files) == 3

    def test_empty_output(self) -> None:
        assert _parse_files("") == []


# ---------------------------------------------------------------------------
# Integration tests with real git repos
# ---------------------------------------------------------------------------


class TestIsGitRepo:
    def test_valid_repo(self, git_repo: Path) -> None:
        assert is_git_repo(git_repo) is True

    def test_not_a_repo(self, tmp_path: Path) -> None:
        empty = tmp_path / "notarepo"
        empty.mkdir()
        assert is_git_repo(empty) is False

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        assert is_git_repo(tmp_path / "nonexistent") is False


class TestGetRepoName:
    def test_returns_directory_name(self, tmp_path: Path) -> None:
        repo = tmp_path / "my-project"
        init_git_repo(repo)
        assert get_repo_name(repo) == "my-project"


class TestCollectDay:
    def test_no_commits_returns_empty(self, git_repo: Path) -> None:
        day = collect_day(git_repo, date(2025, 4, 7))
        assert day.is_empty

    def test_collects_commit_on_date(self, git_repo: Path) -> None:
        make_commit_in_repo(
            git_repo,
            files={"hello.py": "print('hello')"},
            message="feat: add hello",
            author_date="2025-04-07T12:00:00+00:00",
        )
        day = collect_day(git_repo, date(2025, 4, 7))
        assert len(day.commits) == 1
        assert day.commits[0].message == "feat: add hello"

    def test_ignores_commits_on_other_dates(self, git_repo: Path) -> None:
        make_commit_in_repo(
            git_repo,
            files={"a.py": "x=1"},
            message="feat: day one",
            author_date="2025-04-06T12:00:00+00:00",
        )
        make_commit_in_repo(
            git_repo,
            files={"b.py": "y=2"},
            message="feat: day two",
            author_date="2025-04-07T12:00:00+00:00",
        )
        day = collect_day(git_repo, date(2025, 4, 7))
        assert len(day.commits) == 1
        assert day.commits[0].message == "feat: day two"

    def test_multiple_commits_same_day(self, git_repo: Path) -> None:
        make_commit_in_repo(
            git_repo,
            files={"a.py": "x=1"},
            message="feat: first",
            author_date="2025-04-07T10:00:00+00:00",
        )
        make_commit_in_repo(
            git_repo,
            files={"b.py": "y=2"},
            message="feat: second",
            author_date="2025-04-07T14:00:00+00:00",
        )
        day = collect_day(git_repo, date(2025, 4, 7))
        assert len(day.commits) == 2

    def test_commit_stats_populated(self, git_repo: Path) -> None:
        make_commit_in_repo(
            git_repo,
            files={"src/main.py": "x = 1\ny = 2\nz = 3\n"},
            message="add main",
            author_date="2025-04-07T12:00:00+00:00",
        )
        day = collect_day(git_repo, date(2025, 4, 7))
        commit = day.commits[0]
        assert commit.insertions > 0
        assert commit.files_changed >= 1
        assert len(commit.files) >= 1

    def test_not_a_repo_raises(self, tmp_path: Path) -> None:
        not_repo = tmp_path / "empty"
        not_repo.mkdir()
        with pytest.raises(GitCollectorError):
            collect_day(not_repo, date(2025, 4, 7))

    def test_repo_name_set(self, tmp_path: Path) -> None:
        repo = tmp_path / "myproject"
        init_git_repo(repo)
        make_commit_in_repo(
            repo,
            files={"f.py": "pass"},
            message="init",
            author_date="2025-04-07T12:00:00+00:00",
        )
        day = collect_day(repo, date(2025, 4, 7))
        assert day.repo_name == "myproject"

    def test_commits_sorted_by_timestamp(self, git_repo: Path) -> None:
        make_commit_in_repo(
            git_repo,
            files={"a.py": "1"},
            message="later",
            author_date="2025-04-07T18:00:00+00:00",
        )
        make_commit_in_repo(
            git_repo,
            files={"b.py": "2"},
            message="earlier",
            author_date="2025-04-07T08:00:00+00:00",
        )
        day = collect_day(git_repo, date(2025, 4, 7))
        timestamps = [c.timestamp for c in day.commits]
        assert timestamps == sorted(timestamps)


class TestCollectRange:
    def test_empty_range(self, git_repo: Path) -> None:
        days = collect_range(git_repo, date(2025, 4, 7), date(2025, 4, 7))
        assert len(days) == 1

    def test_multi_day_range(self, git_repo: Path) -> None:
        for i, d in enumerate(["2025-04-05", "2025-04-06", "2025-04-07"]):
            make_commit_in_repo(
                git_repo,
                files={f"f{i}.py": str(i)},
                message=f"commit {i}",
                author_date=f"{d}T12:00:00+00:00",
            )
        days = collect_range(git_repo, date(2025, 4, 5), date(2025, 4, 7))
        assert len(days) == 3
        assert all(len(d.commits) == 1 for d in days)


class TestDiscoverRepos:
    def test_finds_nested_repos(self, tmp_path: Path) -> None:
        r1 = tmp_path / "project-a"
        r2 = tmp_path / "sub" / "project-b"
        init_git_repo(r1)
        init_git_repo(r2)
        found = discover_repos(tmp_path)
        assert r1 in found
        assert r2 in found

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        assert discover_repos(empty) == []
