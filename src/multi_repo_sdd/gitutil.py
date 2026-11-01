from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(repo: Path, *args: str) -> str | None:
    completed = _run(repo, args)
    if completed is None or completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def git_ok(repo: Path, *args: str) -> bool:
    completed = _run(repo, args)
    return completed is not None and completed.returncode == 0


def _run(repo: Path, args: tuple[str, ...]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None


def commit_sha(repo: Path) -> str | None:
    return run_git(repo, "rev-parse", "HEAD")


def is_git_repo(repo: Path) -> bool:
    return (repo / ".git").exists() or run_git(repo, "rev-parse", "--is-inside-work-tree") == "true"


def working_tree_dirty(repo: Path) -> bool | None:
    if not git_ok(repo, "rev-parse", "--is-inside-work-tree"):
        return None
    output = run_git(repo, "status", "--porcelain")
    return bool((output or "").strip())


def changed_files_since(repo: Path, sha: str) -> list[str] | None:
    """Tracked and untracked paths that differ from ``sha``.

    An empty list means the work tree matches that commit. ``None`` means git
    could not compare the commit. Empty stdout is a successful clean diff,
    not a failure.
    """
    if not git_ok(repo, "cat-file", "-e", f"{sha}^{{commit}}"):
        return None
    diff_proc = _run(repo, ("diff", "--name-only", sha))
    if diff_proc is None or diff_proc.returncode != 0:
        return None
    untracked_proc = _run(repo, ("ls-files", "--others", "--exclude-standard"))
    untracked = "" if untracked_proc is None or untracked_proc.returncode != 0 else untracked_proc.stdout
    names = [line.strip() for line in f"{diff_proc.stdout}\n{untracked}".splitlines() if line.strip()]
    return sorted(set(names))
