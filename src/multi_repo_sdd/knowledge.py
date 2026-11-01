from __future__ import annotations

import re
from pathlib import Path

import yaml

from multi_repo_sdd.gitutil import commit_sha, working_tree_dirty
from multi_repo_sdd.layout import KNOWLEDGE_FILES, WorkspaceLayout
from multi_repo_sdd.registry import load_registry
from multi_repo_sdd.safety import utc_now


def rebuild_system_knowledge(layout: WorkspaceLayout) -> None:
    registry = load_registry(layout)
    index = {
        "generated_at": utc_now(),
        "repositories": [],
        "documents": [],
    }
    overviews = []
    capabilities = []
    for repo in registry.repositories:
        directory = layout.repo_knowledge_dir(repo.name)
        meta_path = directory / "discovery-metadata.yaml"
        meta = {}
        if meta_path.is_file():
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        recorded = meta.get("commit_sha") or repo.last_discovered_sha
        freshness = repository_freshness(Path(repo.path), recorded, meta_path.is_file())
        index["repositories"].append(
            {
                "name": repo.name,
                "path": repo.path,
                "language": repo.language or meta.get("language"),
                "commit_sha": recorded,
                "current_sha": freshness["current_sha"],
                "discovered_at": meta.get("discovered_at") or repo.last_discovered_at,
                "fresh": freshness["fresh"],
                "freshness": freshness["state"],
            }
        )
        overview = directory / "repository-overview.md"
        if overview.is_file():
            overviews.append((repo.name, overview.read_text(encoding="utf-8")))
        caps = directory / "business-capabilities.md"
        if caps.is_file():
            capabilities.append((repo.name, caps.read_text(encoding="utf-8")))
        for filename in KNOWLEDGE_FILES:
            path = directory / filename
            if path.is_file():
                index["documents"].append({"repository": repo.name, "file": filename, "path": str(path)})
    (layout.system_dir() / "knowledge-index.yaml").write_text(
        yaml.safe_dump(index, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    _write(
        layout.system_dir() / "system-overview.md",
        _system_overview(layout, registry.workspace, overviews, index),
    )
    _write(
        layout.system_dir() / "architecture-overview.md",
        _architecture_overview(overviews),
    )
    _write(
        layout.system_dir() / "business-capabilities.md",
        _capability_map(capabilities),
    )


def repository_freshness(repo_path: Path, recorded_sha: str | None, has_meta: bool) -> dict:
    current = commit_sha(repo_path) if repo_path.is_dir() else None
    dirty = working_tree_dirty(repo_path) if repo_path.is_dir() else None
    if not has_meta:
        state = "missing"
    elif current is None:
        state = "unknown"
    elif dirty:
        state = "dirty"
    elif recorded_sha and recorded_sha == current:
        state = "fresh"
    else:
        state = "stale"
    return {
        "state": state,
        "fresh": state == "fresh",
        "current_sha": current,
        "recorded_sha": recorded_sha,
    }


def read_text_if_exists(path: Path) -> str | None:
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return None


def search_knowledge(layout: WorkspaceLayout, query: str, limit: int = 20) -> list[dict]:
    tokens = [token.lower() for token in re.findall(r"[a-zA-Z0-9_\-]+", query) if len(token) > 1]
    hits: list[dict] = []
    roots = [layout.knowledge_root]
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".md", ".yaml", ".yml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            lowered = text.lower()
            score = sum(lowered.count(token) for token in tokens)
            if score <= 0:
                continue
            snippet = _snippet(text, tokens)
            hits.append(
                {
                    "path": str(path.relative_to(layout.knowledge_root)),
                    "score": score,
                    "snippet": snippet,
                }
            )
    hits.sort(key=lambda item: item["score"], reverse=True)
    return hits[:limit]


def _snippet(text: str, tokens: list[str]) -> str:
    lines = text.splitlines()
    for line in lines:
        lowered = line.lower()
        if any(token in lowered for token in tokens):
            return line.strip()[:240]
    return lines[0][:240] if lines else ""


def _system_overview(layout: WorkspaceLayout, name: str, overviews: list[tuple[str, str]], index: dict) -> str:
    lines = [
        f"# System overview — {name}",
        "",
        "This is the Guardian Level 1 summary. It is baseline knowledge, not an approved specification.",
        "",
        "## Repositories",
        "",
    ]
    for item in index["repositories"]:
        freshness = item.get("freshness") or ("fresh" if item.get("fresh") else "stale-or-missing")
        lines.append(
            f"- **{item['name']}** (`{item.get('language') or 'unknown'}`) sha=`{item.get('commit_sha') or 'n/a'}` [{freshness}]"
        )
    lines.extend(["", "## Repository summaries", ""])
    for repo_name, text in overviews:
        first = next(
            (
                line
                for line in text.splitlines()
                if line.strip() and not line.startswith("#") and not line.startswith(">")
            ),
            "",
        )
        lines.append(f"### {repo_name}")
        lines.append(first)
        lines.append("")
    if not overviews:
        lines.append("No discovery reports are available yet. Run `sdd discover --all`.")
    lines.extend(
        [
            "",
            f"Knowledge root: `{layout.knowledge_root}`",
        ]
    )
    return "\n".join(lines)


def _architecture_overview(overviews: list[tuple[str, str]]) -> str:
    lines = ["# Architecture overview", "", "High-level notes collected from repository discovery.", ""]
    for name, _ in overviews:
        lines.append(f"- See `repositories/{name}/architecture.md`")
    if not overviews:
        lines.append("Unknown until discovery has been run.")
    return "\n".join(lines)


def _capability_map(capabilities: list[tuple[str, str]]) -> str:
    lines = ["# Business capability map", ""]
    for name, text in capabilities:
        headings = [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]
        lines.append(f"## {name}")
        if headings:
            lines.extend(f"- {item}" for item in headings)
        else:
            lines.append("- Unknown")
        lines.append("")
    if not capabilities:
        lines.append("Unknown until discovery has been run.")
    return "\n".join(lines)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
