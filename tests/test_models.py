"""Tests for pydantic data models."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from gitvisual.git.models import Commit, CommitGroup, DaySummary, FileChange, Report
from tests.conftest import make_commit, make_day_summary


class TestFileChange:
    def test_basic_construction(self) -> None:
        fc = FileChange(path="src/foo.py", status="Added")
        assert fc.path == "src/foo.py"
        assert fc.status == "Added"
        assert fc.insertions == 0
        assert fc.deletions == 0

    def test_with_stats(self) -> None:
        fc = FileChange(path="src/bar.py", status="Modified", insertions=5, deletions=2)
        assert fc.insertions == 5
        assert fc.deletions == 2

    def test_frozen(self) -> None:
        fc = FileChange(path="x.py", status="Added")
        with pytest.raises(ValidationError):
            fc.path = "y.py"  # type: ignore[misc]


class TestCommit:
    def test_basic_construction(self, sample_commit: Commit) -> None:
        assert len(sample_commit.hash) > 7
        assert sample_commit.short_hash == sample_commit.hash[:7]
        assert sample_commit.message
        assert sample_commit.author

    def test_frozen(self, sample_commit: Commit) -> None:
        with pytest.raises(ValidationError):
            sample_commit.message = "changed"  # type: ignore[misc]

    def test_empty_body_default(self) -> None:
        c = make_commit()
        assert c.body == ""

    def test_with_body(self) -> None:
        c = make_commit(hash="aabbccdd11223344", message="fix: bug")
        c2 = c.model_copy(update={"body": "More details here."})
        assert c2.body == "More details here."


class TestDaySummary:
    def test_totals(self, tmp_path: Path) -> None:
        c1 = make_commit(insertions=10, deletions=2, files_changed=1)
        c2 = make_commit(hash="bbbbbbbbbbbbbbbb", insertions=5, deletions=1, files_changed=2)
        day = DaySummary(
            date=date(2025, 4, 7),
            repo_path=tmp_path,
            repo_name="repo",
            commits=[c1, c2],
        )
        assert day.total_insertions == 15
        assert day.total_deletions == 3
        assert day.total_files_changed == 3

    def test_is_empty_true(self, empty_day: DaySummary) -> None:
        assert empty_day.is_empty is True

    def test_is_empty_false(self, sample_day: DaySummary) -> None:
        assert sample_day.is_empty is False

    def test_frozen(self, sample_day: DaySummary) -> None:
        with pytest.raises(ValidationError):
            sample_day.repo_name = "other"  # type: ignore[misc]

    def test_model_copy_with_summary(self, sample_day: DaySummary) -> None:
        updated = sample_day.model_copy(update={"summary": "Did some work today."})
        assert updated.summary == "Did some work today."
        assert sample_day.summary is None  # original unchanged


class TestReport:
    def test_repos_deduplication(self, tmp_path: Path) -> None:
        d1 = make_day_summary(target_date=date(2025, 4, 7), repo_name="repo-a", tmp_path=tmp_path)
        d2 = make_day_summary(target_date=date(2025, 4, 8), repo_name="repo-a", tmp_path=tmp_path)
        d3 = make_day_summary(target_date=date(2025, 4, 7), repo_name="repo-b", tmp_path=tmp_path)
        report = Report(date_from=date(2025, 4, 7), date_to=date(2025, 4, 8), days=[d1, d2, d3])
        assert set(report.repos) == {"repo-a", "repo-b"}

    def test_total_commits(self, tmp_path: Path) -> None:
        d1 = make_day_summary(
            tmp_path=tmp_path, commits=[make_commit(), make_commit(hash="bb" * 8)]
        )
        d2 = make_day_summary(tmp_path=tmp_path, commits=[make_commit(hash="cc" * 8)])
        report = Report(date_from=date(2025, 4, 7), date_to=date(2025, 4, 7), days=[d1, d2])
        assert report.total_commits == 3

    def test_frozen(self, tmp_path: Path) -> None:
        report = Report(date_from=date(2025, 4, 7), date_to=date(2025, 4, 7))
        with pytest.raises(ValidationError):
            report.days = []  # type: ignore[misc]


class TestCommitGroup:
    """Table-driven tests for CommitGroup property computations."""

    @pytest.mark.parametrize(
        "commits, expected_ins, expected_del, expected_files",
        [
            # 0 commits → all zeros
            ([], 0, 0, 0),
            # 1 commit
            ([make_commit(insertions=10, deletions=5, files_changed=3)], 10, 5, 3),
            # 3 commits with distinct stats → sums
            (
                [
                    make_commit(
                        hash="aaa" + "a" * 13,
                        insertions=10,
                        deletions=2,
                        files_changed=1,
                    ),
                    make_commit(
                        hash="bbb" + "b" * 13,
                        insertions=20,
                        deletions=3,
                        files_changed=4,
                    ),
                    make_commit(
                        hash="ccc" + "c" * 13,
                        insertions=5,
                        deletions=0,
                        files_changed=2,
                    ),
                ],
                35,
                5,
                7,
            ),
        ],
    )
    def test_totals(
        self,
        commits: list[Commit],
        expected_ins: int,
        expected_del: int,
        expected_files: int,
    ) -> None:
        group = CommitGroup(summary="Test group", commits=commits)
        assert group.total_insertions == expected_ins
        assert group.total_deletions == expected_del
        assert group.total_files_changed == expected_files

    def test_frozen(self) -> None:
        group = CommitGroup(summary="x", commits=[])
        with pytest.raises(ValidationError):
            group.summary = "y"  # type: ignore[misc]

    def test_summary_field(self) -> None:
        group = CommitGroup(summary="Refactored auth module", commits=[])
        assert group.summary == "Refactored auth module"
        assert group.commits == []


class TestDaySummaryCommitGroups:
    """Regression tests for DaySummary.commit_groups field."""

    def test_commit_groups_defaults_to_none(self, tmp_path: Path) -> None:
        day = make_day_summary(tmp_path=tmp_path)
        assert day.commit_groups is None

    def test_commit_groups_accepts_list(self, tmp_path: Path) -> None:
        c = make_commit()
        group = CommitGroup(summary="All work", commits=[c])
        day = DaySummary(
            date=date(2025, 4, 7),
            repo_path=tmp_path,
            repo_name="repo",
            commits=[c],
            commit_groups=[group],
        )
        assert day.commit_groups is not None
        assert len(day.commit_groups) == 1
        assert day.commit_groups[0].summary == "All work"

    def test_commit_groups_model_copy(self, tmp_path: Path) -> None:
        day = make_day_summary(tmp_path=tmp_path)
        c = day.commits[0]
        group = CommitGroup(summary="Everything", commits=[c])
        updated = day.model_copy(update={"commit_groups": [group]})
        assert updated.commit_groups is not None
        assert day.commit_groups is None  # original unchanged
