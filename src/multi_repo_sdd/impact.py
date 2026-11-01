from __future__ import annotations

import re
from pathlib import Path

from multi_repo_sdd.deps import collect_dependencies, consumers, transitive
from multi_repo_sdd.knowledge import search_knowledge
from multi_repo_sdd.layout import WorkspaceLayout
from multi_repo_sdd.registry import load_registry
from multi_repo_sdd.safety import utc_now


def analyze_impact(layout: WorkspaceLayout, change: str) -> Path:
    registry = load_registry(layout)
    dependencies = collect_dependencies(layout)
    hits = search_knowledge(layout, change, limit=40)
    rows: list[dict] = []
    lowered = change.lower()
    for repo in registry.repositories:
        score = 0
        reasons: list[str] = []
        token = repo.name.lower().replace("-service", "")
        if token in lowered or repo.name.lower() in lowered:
            score += 3
            reasons.append("Named in the requested change")
        repo_hits = [
            hit
            for hit in hits
            if f"repositories/{repo.name}/" in hit["path"] or hit["path"].startswith(f"repositories/{repo.name}")
        ]
        direct_hits = _token_hits(layout.repo_knowledge_dir(repo.name), lowered)
        if direct_hits:
            score += min(5, direct_hits)
            reasons.append(f"{direct_hits} evidence token hits")
        elif repo_hits:
            score += min(4, len(repo_hits))
            reasons.append(f"{len(repo_hits)} knowledge hits")
        downstream = transitive(dependencies, repo.name)
        callers = consumers(dependencies, repo.name)
        if score >= 4 and downstream:
            reasons.append("Calls: " + ", ".join(downstream))
        if score >= 4 and callers:
            reasons.append("Called by: " + ", ".join(callers))
        impact = "none"
        action = "Ignore"
        if score >= 4:
            impact = "high"
            action = "Modify"
        elif score >= 2:
            impact = "medium"
            action = "Evaluate"
        elif score >= 1:
            impact = "low"
            action = "Monitor"
        if impact != "none":
            rows.append(
                {
                    "repository": repo.name,
                    "impact": impact,
                    "reason": "; ".join(reasons) or "Knowledge proximity",
                    "action": action,
                    "evidence": repo_hits[:3],
                }
            )
    for repo in registry.repositories:
        if any(row["repository"] == repo.name for row in rows):
            continue
        for row in list(rows):
            if row["impact"] not in {"high", "medium"}:
                continue
            related = repo.name in consumers(dependencies, row["repository"]) or repo.name in transitive(
                dependencies, row["repository"]
            )
            if related:
                rows.append(
                    {
                        "repository": repo.name,
                        "impact": "medium",
                        "reason": f"Dependency neighbor of {row['repository']}",
                        "action": "Evaluate",
                        "evidence": [],
                    }
                )
                break
    order = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda item: (order.get(item["impact"], 9), item["repository"]))
    path = layout.knowledge_root / "changes" / "proposals" / "_last-impact-analysis.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Impact analysis",
        "",
        f"- Change: {change}",
        f"- Generated: {utc_now()}",
        "- Rule: impact is evidence-backed. Absence of evidence is reported as unknown, not as zero impact.",
        "",
        "| Repository | Impact | Reason | Required action |",
        "|---|---|---|---|",
    ]
    if rows:
        for row in rows:
            lines.append(f"| {row['repository']} | {row['impact']} | {row['reason']} | {row['action']} |")
    else:
        lines.append("| unknown | unknown | No repositories matched stored knowledge | Investigate |")
    lines.extend(["", "## Evidence", ""])
    for row in rows:
        lines.append(f"### {row['repository']}")
        if row["evidence"]:
            for hit in row["evidence"]:
                lines.append(f"- `{hit['path']}`: {hit['snippet']}")
        elif "Dependency neighbor" in row["reason"]:
            lines.append("- Evidence is a dependency edge. Confirm the repository knowledge before modifying.")
        else:
            lines.append("- Unknown: weak match only. Inspect repository knowledge before modifying.")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _token_hits(directory: Path, change: str) -> int:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", change.lower())
        if len(token) > 3 and token not in {"introduce", "support", "change", "feature", "system", "with", "this"}
    ]
    if not tokens or not directory.is_dir():
        return 0
    total = 0
    for name in ("business-rules.md", "api-contracts.md", "workflows.md", "repository-overview.md", "risks-and-unknowns.md"):
        path = directory / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        total += sum(text.count(token) for token in tokens)
    return total
