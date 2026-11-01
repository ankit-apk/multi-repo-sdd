from __future__ import annotations

import yaml

from multi_repo_sdd.agents.base import AgentProvider, CommandAgentProvider, ImplementationPacket, LocalPacketProvider
from multi_repo_sdd.config import SddConfig
from multi_repo_sdd.errors import GovernanceError
from multi_repo_sdd.layout import WorkspaceLayout
from multi_repo_sdd.registry import load_registry
from multi_repo_sdd.sdd.changes import find_change, move_change
from multi_repo_sdd.sdd.governance import require_approvals
from multi_repo_sdd.safety import AuditLog, utc_now
from multi_repo_sdd.scheduling import execution_batches


def implement_change(
    layout: WorkspaceLayout,
    config: SddConfig,
    change_id: str,
    authorize_writes: bool = False,
    provider: AgentProvider | None = None,
) -> dict:
    status = require_approvals(layout, config, change_id, for_implementation=True)
    stage, path = find_change(layout, change_id)
    if stage == "proposals":
        path = move_change(layout, change_id, "approved")
        stage = "approved"
    if stage == "approved":
        path = move_change(layout, change_id, "in-progress")
    registry = load_registry(layout)
    ordered_repos = list(status.get("repositories") or [])
    prerequisites = _prerequisites(path, ordered_repos)
    batches, cyclic = execution_batches(ordered_repos, prerequisites)
    if cyclic:
        batches.append(cyclic)
    packets: list[ImplementationPacket] = []
    batch_of: dict[str, int] = {}
    for index, batch in enumerate(batches, start=1):
        for repo_name in batch:
            batch_of[repo_name] = index
            repo = registry.get(repo_name)
            task_file = path / "tasks" / f"{repo_name}.md"
            packets.append(
                ImplementationPacket(
                    change_id=change_id,
                    repository=repo_name,
                    repository_path=repo.path,
                    spec_path=str(path / "spec.md"),
                    design_path=str(path / "design.md"),
                    task_path=str(task_file),
                    read_only=not (authorize_writes and config.governance.authorize_repository_writes),
                    provider=config.agents.implementation_provider,
                )
            )
    writes_allowed = authorize_writes and config.governance.authorize_repository_writes
    adapter = provider or _provider_for(config, writes_allowed)
    results = []
    batch_report = [
        {
            "batch": index,
            "repositories": batch,
            "parallel_eligible": len(batch) > 1 and not cyclic,
            "executed": "sequential",
        }
        for index, batch in enumerate(batches, start=1)
    ]
    if not writes_allowed:
        packet_dir = path / "implementation-packets"
        packet_dir.mkdir(exist_ok=True)
        for packet in packets:
            out = packet_dir / f"{packet.repository}.yaml"
            out.write_text(yaml.safe_dump(packet.model_dump(), sort_keys=False), encoding="utf-8")
            results.append(
                {
                    "repository": packet.repository,
                    "batch": batch_of.get(packet.repository),
                    "status": "packet-written",
                    "path": str(out),
                    "note": "Application repositories were not modified. Pass --authorize-writes after setting governance.authorize_repository_writes.",
                }
            )
        _store_implementation(path, mode="packets", results=results, batches=batch_report, modified=False, cyclic=cyclic)
        AuditLog(layout.audit_log()).record("implement-packets", change=change_id, count=len(packets))
        return {"change": change_id, "mode": "packets", "batches": batch_report, "cyclic": cyclic, "results": results}

    for packet in packets:
        result = adapter.submit(packet)
        results.append({**result.model_dump(), "batch": batch_of.get(packet.repository)})
        if result.status == "error":
            _store_implementation(path, mode="dispatched", results=results, batches=batch_report, modified=False, cyclic=cyclic)
            raise GovernanceError(f"Implementation failed for {packet.repository}: {result.detail}")
    modified = any(item.get("status") == "completed" for item in results)
    _store_implementation(path, mode="dispatched", results=results, batches=batch_report, modified=modified, cyclic=cyclic)
    AuditLog(layout.audit_log()).record("implement", change=change_id)
    return {"change": change_id, "mode": "dispatched", "batches": batch_report, "cyclic": cyclic, "results": results}


def record_implementation(layout: WorkspaceLayout, change_id: str, repository: str, files: list[str]) -> dict:
    _stage, path = find_change(layout, change_id)
    status_path = path / "status.yaml"
    status = yaml.safe_load(status_path.read_text(encoding="utf-8"))
    if repository not in (status.get("repositories") or []):
        raise GovernanceError(f"{repository} is not part of change {change_id}")
    clean_files = []
    for name in files:
        if not name or name.startswith("/") or ".." in name.split("/"):
            raise GovernanceError(f"Refusing recorded path {name!r}")
        clean_files.append(name)
    recorded = status.setdefault("recorded_files", {})
    current = list(recorded.get(repository) or [])
    for name in clean_files:
        if name not in current:
            current.append(name)
    recorded[repository] = current
    status["repositories_modified"] = True
    status_path.write_text(yaml.safe_dump(status, sort_keys=False), encoding="utf-8")
    AuditLog(layout.audit_log()).record("record-implementation", change=change_id, repository=repository, files=clean_files)
    return status


def _provider_for(config: SddConfig, writes_allowed: bool) -> AgentProvider:
    if not writes_allowed or config.agents.implementation_provider == "local-packet":
        return LocalPacketProvider()
    if config.agents.implementation_provider == "command":
        if not config.agents.implementation_command:
            raise GovernanceError("implementation_command is empty")
        return CommandAgentProvider(
            config.agents.implementation_command,
            timeout_seconds=config.agents.implementation_timeout_seconds,
        )
    raise GovernanceError(f"Unknown implementation provider {config.agents.implementation_provider}")


def _prerequisites(path, repos: list[str]) -> dict[str, list[str]]:
    """Read task dependency ids back into repository names when possible."""
    prerequisites = {repo: [] for repo in repos}
    id_to_repo = {}
    for repo in repos:
        task_file = path / "tasks" / f"{repo}.md"
        if not task_file.is_file():
            continue
        text = task_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("- Task ID:"):
                task_id = line.split("`", 2)[1] if "`" in line else ""
                if task_id:
                    id_to_repo[task_id] = repo
    for repo in repos:
        task_file = path / "tasks" / f"{repo}.md"
        if not task_file.is_file():
            continue
        for line in task_file.read_text(encoding="utf-8").splitlines():
            if not line.startswith("- Dependencies:"):
                continue
            for task_id, owner in id_to_repo.items():
                if task_id in line and owner != repo and owner not in prerequisites[repo]:
                    prerequisites[repo].append(owner)
    return prerequisites


def _store_implementation(path, mode: str, results: list, batches: list, modified: bool, cyclic: list[str]) -> None:
    status_path = path / "status.yaml"
    current = yaml.safe_load(status_path.read_text(encoding="utf-8"))
    current["implementation"] = {
        "at": utc_now(),
        "mode": mode,
        "repositories_modified": modified,
        "batches": batches,
        "cyclic": cyclic,
        "results": results,
    }
    current["repositories_modified"] = modified
    status_path.write_text(yaml.safe_dump(current, sort_keys=False), encoding="utf-8")
