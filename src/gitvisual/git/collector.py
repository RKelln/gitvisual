"""Git data extraction via subprocess calls to the git CLI."""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

from gitvisual.git.models import Commit, DaySummary, FileChange


class GitCollectorError(Exception):
    """Raised when git data extraction fails."""


def _run_git(args: list[str], repo_path: Path) -> str:
    """Run a git command in repo_path, return stdout. Raises GitCollectorError on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise GitCollectorError(
            f"git command failed: git {' '.join(args)}\n{e.stderr.strip()}"
        ) from e
    except FileNotFoundError as e:
        raise GitCollectorError("git executable not found in PATH") from e


def is_git_repo(path: Path) -> bool:
    """Return True if path is inside a git repository."""
    try:
        _run_git(["rev-parse", "--git-dir"], path)
        return True
    except GitCollectorError:
        return False


def get_repo_name(repo_path: Path) -> str:
    """Return the repository name (top-level directory basename)."""
    try:
        toplevel = _run_git(["rev-parse", "--show-toplevel"], repo_path).strip()
        return Path(toplevel).name
    except GitCollectorError:
        return repo_path.resolve().name


def _parse_stats(stats_output: str) -> tuple[int, int, int]:
    """Parse a git show --stat summary line.

    Returns (files_changed, insertions, deletions).
    """
    files_changed = 0
    insertions = 0
    deletions = 0

    for line in stats_output.splitlines():
        line = line.strip()
        if "changed" in line:
            m = re.search(r"(\d+) file", line)
            if m:
                files_changed = int(m.group(1))
            m = re.search(r"(\d+) insertion", line)
            if m:
                insertions = int(m.group(1))
            m = re.search(r"(\d+) deletion", line)
            if m:
                deletions = int(m.group(1))
            break

    return files_changed, insertions, deletions


def _parse_files(files_output: str) -> list[FileChange]:
    """Parse git diff-tree --name-status output into FileChange objects."""
    status_map = {
        "A": "Added",
        "M": "Modified",
        "D": "Deleted",
        "C": "Copied",
    }
    changes: list[FileChange] = []
    for line in files_output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 2)
        if not parts:
            continue
        raw_status = parts[0][0]  # first char (R100 -> R)
        if raw_status == "R" and len(parts) >= 3:
            status = "Renamed"
            path = f"{parts[1]} -> {parts[2]}"
        elif len(parts) >= 2:
            status = status_map.get(raw_status, raw_status)
            path = parts[1]
        else:
            continue
        changes.append(FileChange(path=path, status=status))
    return changes


def _get_commit_detail(commit_hash: str, repo_path: Path) -> Commit:
    """Fetch full detail for a single commit."""
    # Subject, body, and metadata in one call
    sep = "---METADATA---"
    info_out = _run_git(
        [
            "show",
            "--no-patch",
            f"--pretty=format:%s%n%b%n{sep}%n%an%n%ae%n%ai",
            commit_hash,
        ],
        repo_path,
    )

    parts = info_out.split(f"\n{sep}\n", 1)
    if len(parts) == 2:
        msg_block, meta_block = parts
    else:
        msg_block = info_out
        meta_block = ""

    msg_lines = msg_block.splitlines()
    message = msg_lines[0].strip() if msg_lines else ""
    body = "\n".join(msg_lines[1:]).strip() if len(msg_lines) > 1 else ""

    meta_lines = meta_block.splitlines()
    author = meta_lines[0].strip() if len(meta_lines) > 0 else "Unknown"
    email = meta_lines[1].strip() if len(meta_lines) > 1 else ""
    ts_str = meta_lines[2].strip() if len(meta_lines) > 2 else ""

    try:
        timestamp = datetime.fromisoformat(ts_str)
    except ValueError:
        timestamp = datetime.now(tz=UTC)

    # Stats
    stat_out = _run_git(
        ["show", "--stat", "--pretty=format:", commit_hash],
        repo_path,
    )
    files_changed, insertions, deletions = _parse_stats(stat_out)

    # File list — use --root so the initial commit is handled correctly
    files_out = _run_git(
        ["diff-tree", "--root", "--no-commit-id", "--name-status", "-r", commit_hash],
        repo_path,
    )
    files = _parse_files(files_out)

    return Commit(
        hash=commit_hash,
        short_hash=commit_hash[:7],
        message=message,
        body=body,
        author=author,
        email=email,
        timestamp=timestamp,
        files=files,
        insertions=insertions,
        deletions=deletions,
        files_changed=files_changed,
    )


def collect_day(repo_path: Path, target_date: date) -> DaySummary:
    """Collect all commits authored on target_date in repo_path.

    Uses author date (not commit date) for filtering, matching the behaviour
    of the original git_daily_card.py script.
    """
    repo_path = repo_path.resolve()

    if not is_git_repo(repo_path):
        raise GitCollectorError(f"{repo_path} is not a git repository")

    repo_name = get_repo_name(repo_path)
    date_str = target_date.isoformat()  # YYYY-MM-DD

    # List all commits with author date; filter by date string match
    log_out = _run_git(
        ["log", "--all", "--pretty=format:%H %ai"],
        repo_path,
    )

    commit_hashes: list[str] = []
    for line in log_out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        commit_hash, author_date = parts
        # author_date is like "2025-04-07 14:32:10 +0000"; match on the date prefix
        if author_date.startswith(date_str):
            commit_hashes.append(commit_hash)

    commits: list[Commit] = []
    for h in commit_hashes:
        commit = _get_commit_detail(h, repo_path)
        commits.append(commit)

    # Sort by timestamp ascending
    commits.sort(key=lambda c: c.timestamp)

    return DaySummary(
        date=target_date,
        repo_path=repo_path,
        repo_name=repo_name,
        commits=commits,
    )


def collect_range(repo_path: Path, date_from: date, date_to: date) -> list[DaySummary]:
    """Collect DaySummary for each day in [date_from, date_to] (inclusive)."""
    from datetime import timedelta

    days = []
    current = date_from
    while current <= date_to:
        days.append(collect_day(repo_path, current))
        current += timedelta(days=1)
    return days


def discover_repos(search_path: Path) -> list[Path]:
    """Walk search_path and return all git repository root directories found."""
    repos: list[Path] = []
    search_path = search_path.resolve()

    for candidate in search_path.rglob(".git"):
        if candidate.is_dir():
            repos.append(candidate.parent)

    return sorted(repos)
