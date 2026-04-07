"""Pydantic data models for git commit data."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class FileChange(BaseModel):
    """A single file changed in a commit."""

    model_config = ConfigDict(frozen=True)

    path: str
    status: str  # "Added", "Modified", "Deleted", "Renamed", "Copied"
    insertions: int = 0
    deletions: int = 0


class Commit(BaseModel):
    """A single git commit with full detail."""

    model_config = ConfigDict(frozen=True)

    hash: str
    short_hash: str
    message: str  # subject line
    body: str = ""  # commit body (may be empty)
    author: str
    email: str
    timestamp: datetime
    files: list[FileChange] = Field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    files_changed: int = 0


class DaySummary(BaseModel):
    """All commits for one day in one repository."""

    model_config = ConfigDict(frozen=True)

    date: date
    repo_path: Path
    repo_name: str  # basename or configured name
    commits: list[Commit] = Field(default_factory=list)
    summary: str | None = None  # LLM-generated summary

    @property
    def total_insertions(self) -> int:
        return sum(c.insertions for c in self.commits)

    @property
    def total_deletions(self) -> int:
        return sum(c.deletions for c in self.commits)

    @property
    def total_files_changed(self) -> int:
        return sum(c.files_changed for c in self.commits)

    @property
    def is_empty(self) -> bool:
        return len(self.commits) == 0


class Report(BaseModel):
    """A full report spanning multiple repos and/or a date range."""

    model_config = ConfigDict(frozen=True)

    date_from: date
    date_to: date
    days: list[DaySummary] = Field(default_factory=list)

    @property
    def repos(self) -> list[str]:
        seen: set[str] = set()
        result = []
        for day in self.days:
            if day.repo_name not in seen:
                seen.add(day.repo_name)
                result.append(day.repo_name)
        return result

    @property
    def total_commits(self) -> int:
        return sum(len(d.commits) for d in self.days)
