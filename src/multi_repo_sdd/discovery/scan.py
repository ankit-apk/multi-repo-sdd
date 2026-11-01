from __future__ import annotations

from pathlib import Path

from multi_repo_sdd.config import DiscoverySettings

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    "target",
    ".idea",
    ".vscode",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
}


def iter_files(root: Path, settings: DiscoverySettings, limit: int = 4000) -> list[Path]:
    files: list[Path] = []
    root_resolved = root.resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.is_symlink() and not _symlink_stays_inside(path, root_resolved):
            continue
        try:
            rel = path.resolve().relative_to(root_resolved).as_posix() if path.is_symlink() else path.relative_to(root).as_posix()
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in Path(rel).parts):
            continue
        if _ignored(rel, settings.ignore_globs):
            continue
        files.append(path)
        if len(files) >= limit:
            break
    return files


def _symlink_stays_inside(path: Path, root_resolved: Path) -> bool:
    try:
        target = path.resolve()
        target.relative_to(root_resolved)
    except (OSError, ValueError):
        return False
    return target.is_file()


def _ignored(relative: str, globs: list[str]) -> bool:
    from fnmatch import fnmatch

    return any(fnmatch(relative, pattern) or fnmatch(relative, pattern.rstrip("/**")) for pattern in globs)


def read_text(path: Path, max_bytes: int = 200_000) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > max_bytes:
        data = data[:max_bytes]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""
