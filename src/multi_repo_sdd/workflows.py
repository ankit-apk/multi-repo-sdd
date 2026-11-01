from __future__ import annotations

from pathlib import Path

from multi_repo_sdd.deps import adjacency, collect_dependencies
from multi_repo_sdd.layout import WorkspaceLayout
from multi_repo_sdd.knowledge import search_knowledge
from multi_repo_sdd.models import Dependency
from multi_repo_sdd.registry import load_registry
from multi_repo_sdd.safety import utc_now


def slugify(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "workflow"


def discover_workflow(layout: WorkspaceLayout, description: str) -> Path:
    registry = load_registry(layout)
    dependencies = collect_dependencies(layout)
    names = registry.names()
    hits = search_knowledge(layout, description, limit=30)
    participating = _participants(description, names, hits, dependencies)
    steps = _sequence(participating, dependencies)
    path = layout.workflows_dir() / f"{slugify(description)}.md"
    lines = [
        f"# {description}",
        "",
        f"- Generated: {utc_now()}",
        "- Kind: reconstructed business workflow (not a dependency graph dump)",
        f"- Trigger: inferred from the requested description `{description}`",
        "",
        "## Business objective",
        "",
        description,
        "",
        "## Participating repositories",
        "",
    ]
    for name in participating:
        lines.append(f"- {name}")
    if not participating:
        lines.append("- Unknown: discovery knowledge does not yet identify participants.")
    lines.extend(["", "## Sequence of operations", ""])
    if steps:
        for index, step in enumerate(steps, start=1):
            lines.append(f"{index}. {step}")
    else:
        lines.append("Unknown: not enough verified relationships to order this workflow.")
    lines.extend(
        [
            "",
            "## APIs and events",
            "",
        ]
    )
    for name in participating:
        api_doc = layout.repo_knowledge_dir(name) / "api-contracts.md"
        lines.append(f"### {name}")
        lines.append("")
        if api_doc.is_file():
            table = [
                line
                for line in api_doc.read_text(encoding="utf-8").splitlines()
                if line.startswith("|")
            ]
            lines.extend(table or ["- Unknown: API contract file has no table."])
            lines.append("")
            lines.append(f"Full contract: `repositories/{name}/api-contracts.md`.")
        else:
            lines.append("- Unknown: no API contract has been discovered.")
        lines.append("")
    lines.extend(
        [
            "## Important business rules",
            "",
            "See repository `business-rules.md` files. Do not treat inferred rules as approved policy.",
            "",
            "## Data ownership",
            "",
            "Unknown unless a repository README or schema file states it. Ownership was not invented.",
            "",
            "## Failure, retry, and compensation",
            "",
            "Unknown from static discovery unless tests or comments described it.",
            "",
            "## Source-code evidence",
            "",
        ]
    )
    for hit in hits[:8]:
        lines.append(f"- `{hit['path']}`: {hit['snippet']}")
    if not hits:
        lines.append("- Unknown: no matching knowledge documents.")
    lines.extend(
        [
            "",
            "## Unresolved questions",
            "",
            "- Which system is the source of truth for this workflow?",
            "- What compensation happens if a downstream step fails?",
            "- Are there undocumented manual steps?",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _participants(description: str, names: list[str], hits: list[dict], dependencies: list[Dependency]) -> list[str]:
    lowered = description.lower()
    found: list[str] = []
    for name in names:
        token = name.lower().replace("-service", "").replace("_", "-")
        if token in lowered or name.lower() in lowered:
            found.append(name)
    for hit in hits:
        for name in names:
            if name in hit["path"] and name not in found:
                found.append(name)
    if found:
        extra: list[str] = []
        graph = adjacency(dependencies)
        for name in list(found):
            for edge in graph.get(name, []):
                if edge.target not in found and edge.target not in extra:
                    extra.append(edge.target)
        found.extend(extra)
    return found


def _sequence(participants: list[str], dependencies: list[Dependency]) -> list[str]:
    if not participants:
        return []
    graph = adjacency(dependencies)
    steps: list[str] = []
    remaining = list(participants)
    used: set[str] = set()
    current = remaining[0]
    while current and current not in used:
        used.add(current)
        edges = [edge for edge in graph.get(current, []) if edge.target in participants]
        if edges:
            edge = edges[0]
            steps.append(
                f"{current} → {edge.target} via {edge.interface or edge.type} ({edge.confidence})"
            )
            current = edge.target
        else:
            steps.append(f"{current} participates; next hop is unknown from verified dependencies")
            current = next((name for name in remaining if name not in used), "")
    for name in remaining:
        if name not in used:
            steps.append(f"{name} is associated with the request but has no verified hop in this workflow")
    return steps
