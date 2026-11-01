from __future__ import annotations

import re
from collections import defaultdict, deque

import yaml

from multi_repo_sdd.layout import WorkspaceLayout
from multi_repo_sdd.models import Dependency
from multi_repo_sdd.registry import load_registry
from multi_repo_sdd.safety import utc_now


def collect_dependencies(layout: WorkspaceLayout) -> list[Dependency]:
    registry = load_registry(layout)
    collected: list[Dependency] = []
    for repo in registry.repositories:
        path = layout.repo_knowledge_dir(repo.name) / "dependencies.yaml"
        if not path.is_file():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for item in raw.get("dependencies") or []:
            collected.append(Dependency.model_validate(item))
    payload = {
        "generated_at": utc_now(),
        "dependencies": [item.model_dump(mode="python") for item in collected],
    }
    layout.dependency_map_path().write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    graph_path = layout.system_dir() / "dependency-graph.md"
    graph_path.write_text(render_mermaid(collected), encoding="utf-8")
    return collected


def adjacency(dependencies: list[Dependency]) -> dict[str, list[Dependency]]:
    graph: dict[str, list[Dependency]] = defaultdict(list)
    for item in dependencies:
        graph[item.source].append(item)
    return dict(graph)


def consumers(dependencies: list[Dependency], target: str) -> list[str]:
    seen: list[str] = []
    for item in dependencies:
        if item.target == target and item.source not in seen:
            seen.append(item.source)
    return seen


def transitive(dependencies: list[Dependency], source: str) -> list[str]:
    graph = adjacency(dependencies)
    seen: set[str] = set()
    queue = deque([source])
    ordered: list[str] = []
    while queue:
        current = queue.popleft()
        for edge in graph.get(current, []):
            if edge.target not in seen and edge.target != source:
                seen.add(edge.target)
                ordered.append(edge.target)
                queue.append(edge.target)
    return ordered


def render_dependencies(dependencies: list[Dependency]) -> str:
    lines = [
        "# Repository dependencies",
        "",
        "| Source | Target | Type | Interface | Confidence | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    if not dependencies:
        lines.append("| — | — | — | — | unknown | none |")
        return "\n".join(lines)
    for item in dependencies:
        file = item.evidence[0].file if item.evidence else ""
        lines.append(
            f"| {item.source} | {item.target} | {item.type} | {item.interface or ''} | {item.confidence} | `{file}` |"
        )
    return "\n".join(lines)


def render_mermaid(dependencies: list[Dependency]) -> str:
    lines = [
        "# Dependency graph",
        "",
        "Projection of `dependency-map.yaml` for a future UI. This is not a business workflow.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    if not dependencies:
        lines.append('  empty["No verified or inferred dependencies"]')
    else:
        nodes: set[str] = set()
        for item in dependencies:
            nodes.add(item.source)
            nodes.add(item.target)
        for name in sorted(nodes):
            lines.append(f'  {_mermaid_id(name)}["{name}"]')
        for item in dependencies:
            label = f"{item.type} ({item.confidence})"
            lines.append(f"  {_mermaid_id(item.source)} -->|{label}| {_mermaid_id(item.target)}")
    lines.extend(["```", ""])
    return "\n".join(lines)


def _mermaid_id(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return cleaned or "node"
