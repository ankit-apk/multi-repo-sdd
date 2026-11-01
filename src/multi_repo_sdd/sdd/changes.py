from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

from multi_repo_sdd.config import SddConfig
from multi_repo_sdd.deps import collect_dependencies
from multi_repo_sdd.errors import GovernanceError
from multi_repo_sdd.gitutil import commit_sha
from multi_repo_sdd.impact import analyze_impact
from multi_repo_sdd.knowledge import rebuild_system_knowledge
from multi_repo_sdd.layout import WorkspaceLayout
from multi_repo_sdd.sdd.templates import (
    analysis_markdown,
    checklist_markdown,
    clarifications_markdown,
    constitution_markdown,
    design_markdown,
    integration_tasks_markdown,
    proposal_markdown,
    spec_markdown,
    tasks_markdown,
)
from multi_repo_sdd.safety import utc_now
from multi_repo_sdd.workflows import slugify


STAGES = ("proposals", "approved", "in-progress", "archive")
_CHANGE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_EXCERPT_STOP = {"introduce", "support", "change", "feature", "system", "this", "that", "with"}


def validate_change_id(change_id: str) -> str:
    if not _CHANGE_ID.fullmatch(change_id):
        raise GovernanceError("Change id must be a lowercase slug with no path separators")
    return change_id


def find_change(layout: WorkspaceLayout, change_id: str) -> tuple[str, Path]:
    validate_change_id(change_id)
    for stage in STAGES:
        path = layout.change_stage_dir(stage) / change_id
        if path.is_dir():
            return stage, path
    raise GovernanceError(f"Change not found: {change_id}")


def propose_change(layout: WorkspaceLayout, description: str) -> Path:
    change_id = validate_change_id(slugify(description))
    for stage in STAGES:
        if (layout.change_stage_dir(stage) / change_id).exists():
            raise GovernanceError(f"Change {change_id} already exists in {stage}. Revise that folder or choose a new description.")
    target = layout.change_stage_dir("proposals") / change_id
    target.mkdir(parents=True, exist_ok=True)
    impact_path = analyze_impact(layout, description)
    impact_text = impact_path.read_text(encoding="utf-8")
    repos = _repos_from_impact(impact_text)
    evidence = discovery_excerpts(layout, repos, description)
    (target / "proposal.md").write_text(proposal_markdown(change_id, description, impact_text), encoding="utf-8")
    (target / "impact-analysis.md").write_text(impact_text, encoding="utf-8")
    (target / "spec.md").write_text(spec_markdown(change_id, description, repos, evidence), encoding="utf-8")
    (target / "design.md").write_text(design_markdown(change_id, description, repos, evidence), encoding="utf-8")
    (target / "clarifications.md").write_text(clarifications_markdown(), encoding="utf-8")
    (target / "checklist.md").write_text(checklist_markdown(change_id), encoding="utf-8")
    (target / "analysis.md").write_text(analysis_markdown(change_id), encoding="utf-8")
    (target / "convergence.md").write_text(
        f"# Convergence — {change_id}\n\nStatus: not-started\n\nSpec Kit phase: converge.\n",
        encoding="utf-8",
    )
    tasks_dir = target / "tasks"
    tasks_dir.mkdir(exist_ok=True)
    prerequisites = _task_prerequisites(layout, repos)
    ids = {repo: f"{change_id}-{index:02d}-{slugify(repo)}" for index, repo in enumerate(repos, start=1)}
    for index, repo in enumerate(repos, start=1):
        depends = [ids[other] for other in prerequisites.get(repo, []) if other in ids]
        (tasks_dir / f"{repo}.md").write_text(tasks_markdown(change_id, repo, index, depends), encoding="utf-8")
    (tasks_dir / "integration-tests.md").write_text(integration_tasks_markdown(change_id, repos), encoding="utf-8")
    governance = layout.governance_dir()
    (governance / "sdd-principles.md").write_text(constitution_markdown(layout.knowledge_root.name), encoding="utf-8")
    status = {
        "id": change_id,
        "description": description,
        "stage": "proposals",
        "created_at": utc_now(),
        "repositories": repos,
        "speckit_phases": [
            "constitution",
            "specify",
            "clarify",
            "plan",
            "checklist",
            "tasks",
            "analyze",
            "implement",
            "converge",
        ],
        "approvals": {"specification": False, "design": False, "implementation": False},
        "unified_change_id": change_id,
    }
    (target / "status.yaml").write_text(yaml.safe_dump(status, sort_keys=False), encoding="utf-8")
    return target


def validate_change(layout: WorkspaceLayout, change_id: str) -> dict:
    stage, path = find_change(layout, change_id)
    required = ["proposal.md", "spec.md", "design.md", "impact-analysis.md", "checklist.md", "analysis.md"]
    missing = [name for name in required if not (path / name).is_file()]
    tasks = list((path / "tasks").glob("*.md")) if (path / "tasks").is_dir() else []
    status = yaml.safe_load((path / "status.yaml").read_text(encoding="utf-8"))
    issues: list[str] = []
    if missing:
        issues.append("Missing artifacts: " + ", ".join(missing))
    if not tasks:
        issues.append("No tasks were generated")
    spec = (path / "spec.md").read_text(encoding="utf-8")
    design = (path / "design.md").read_text(encoding="utf-8")
    for repo in status.get("repositories") or []:
        if repo not in spec or repo not in design:
            issues.append(f"Repository {repo} is missing from spec/design consistency")
        if not (path / "tasks" / f"{repo}.md").is_file():
            issues.append(f"Missing task file for {repo}")
    result = {
        "id": change_id,
        "stage": stage,
        "ok": not issues,
        "issues": issues,
        "approvals": status.get("approvals", {}),
    }
    (path / "validation.yaml").write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    return result


def move_change(layout: WorkspaceLayout, change_id: str, new_stage: str) -> Path:
    stage, path = find_change(layout, change_id)
    if stage == new_stage:
        return path
    dest = layout.change_stage_dir(new_stage) / change_id
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(path), str(dest))
    status_path = dest / "status.yaml"
    status = yaml.safe_load(status_path.read_text(encoding="utf-8"))
    status["stage"] = new_stage
    status["updated_at"] = utc_now()
    status_path.write_text(yaml.safe_dump(status, sort_keys=False), encoding="utf-8")
    return dest


def archive_change(
    layout: WorkspaceLayout,
    change_id: str,
    config: SddConfig | None = None,
    refresh_knowledge: bool = True,
) -> Path:
    _stage, path = find_change(layout, change_id)
    status = yaml.safe_load((path / "status.yaml").read_text(encoding="utf-8"))
    if not status.get("verification", {}).get("passed"):
        raise GovernanceError("Refuse to archive: verification has not passed")
    convergence = (path / "convergence.md").read_text(encoding="utf-8") if (path / "convergence.md").is_file() else ""
    if "Status: converged" not in convergence:
        raise GovernanceError("Refuse to archive: convergence status is not converged")
    open_tasks = unchecked_tasks(path)
    if open_tasks:
        raise GovernanceError("Refuse to archive: tasks are still open")
    _sync_living_spec(layout, change_id, path, status)
    dest = move_change(layout, change_id, "archive")
    if config is not None and refresh_knowledge:
        from multi_repo_sdd.discovery.engine import discover_repositories

        discover_repositories(layout, config, mode="incremental")
    rebuild_system_knowledge(layout)
    return dest


def unchecked_tasks(change_dir: Path) -> list[str]:
    tasks = change_dir / "tasks"
    if not tasks.is_dir():
        return ["tasks directory missing"]
    open_items: list[str] = []
    for file in sorted(tasks.glob("*.md")):
        if file.name == "convergence-followups.md":
            continue
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("- [ ]"):
                open_items.append(f"{file.name}: {line.strip()}")
    return open_items


def discovery_excerpts(layout: WorkspaceLayout, repos: list[str], description: str) -> str:
    tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9_]+", description)
        if len(token) > 3 and token.lower() not in _EXCERPT_STOP
    ]
    chunks: list[str] = []
    for repo in repos:
        directory = layout.repo_knowledge_dir(repo)
        chunks.append(f"### {repo}")
        meta = directory / "discovery-metadata.yaml"
        if meta.is_file():
            chunks.append(meta.read_text(encoding="utf-8").strip())
        else:
            chunks.append("Unknown: discovery metadata is missing.")
        for filename in ("api-contracts.md", "business-rules.md", "risks-and-unknowns.md", "database-model.md"):
            path = directory / filename
            chunks.append(f"#### {filename}")
            if not path.is_file():
                chunks.append(f"Unknown: `{filename}` has not been discovered.")
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            if filename == "api-contracts.md":
                selected = [line for line in lines if line.startswith("|")]
            else:
                selected = [line for line in lines if any(token in line.lower() for token in tokens)]
            chunks.extend(selected[:30] or ["- Unknown: no lines in this file matched the change."])
        chunks.append("")
    if not repos:
        chunks.append("Unknown: impact analysis did not name a repository.")
    return "\n".join(chunks)


def _task_prerequisites(layout: WorkspaceLayout, repos: list[str]) -> dict[str, list[str]]:
    prerequisites = {repo: [] for repo in repos}
    for edge in collect_dependencies(layout):
        if edge.source in prerequisites and edge.target in prerequisites and edge.target not in prerequisites[edge.source]:
            prerequisites[edge.source].append(edge.target)
    return prerequisites


def _sync_living_spec(layout: WorkspaceLayout, change_id: str, path: Path, status: dict) -> None:
    destination = layout.knowledge_root / "specifications" / change_id
    if destination.exists():
        raise GovernanceError(f"Living specification already exists for {change_id}")
    destination.mkdir(parents=True)
    for name in ("spec.md", "design.md", "proposal.md"):
        source = path / name
        if source.is_file():
            (destination / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    repos = status.get("repositories") or []
    from multi_repo_sdd.registry import load_registry

    registry = load_registry(layout)
    commits = {}
    for repo in registry.repositories:
        if repo.name in repos:
            commits[repo.name] = commit_sha(Path(repo.path))
    sync = {
        "change_id": change_id,
        "source": "approved change archive",
        "repositories": repos,
        "commits": commits,
        "note": (
            "This living specification is the agreed change record. "
            "Discovery documents remain a separate description of what the code appears to do."
        ),
    }
    (destination / "sync.yaml").write_text(yaml.safe_dump(sync, sort_keys=False), encoding="utf-8")
    index_path = layout.knowledge_root / "specifications" / "index.yaml"
    current = []
    if index_path.is_file():
        loaded = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
        current = list(loaded.get("specifications") or [])
    current.append({"id": change_id, "path": f"specifications/{change_id}/spec.md"})
    index_path.write_text(
        yaml.safe_dump({"specifications": current}, sort_keys=False),
        encoding="utf-8",
    )
    for workflow in layout.workflows_dir().glob("*.md"):
        text = workflow.read_text(encoding="utf-8")
        if change_id in text or not any(repo in text for repo in repos):
            continue
        workflow.write_text(
            text.rstrip()
            + f"\n\n## Archived change `{change_id}`\n\n"
            + f"See `specifications/{change_id}/spec.md`. This note records that an approved change touched participants in this workflow. It does not replace the inferred sequence.\n",
            encoding="utf-8",
        )


def _repos_from_impact(text: str) -> list[str]:
    repos: list[str] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0] in {"Repository", "---", "unknown", "—"}:
            continue
        if cells[3] in {"Modify", "Evaluate"}:
            repos.append(cells[0])
    return repos
