from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from multi_repo_sdd.config import SddConfig
from multi_repo_sdd.safety import ensure_dir, resolve_path

KNOWLEDGE_FILES = [
    "repository-overview.md",
    "architecture.md",
    "modules.md",
    "business-capabilities.md",
    "business-rules.md",
    "workflows.md",
    "api-contracts.md",
    "database-model.md",
    "dependencies.yaml",
    "technical-constraints.md",
    "testing-strategy.md",
    "risks-and-unknowns.md",
    "discovery-metadata.yaml",
]


@dataclass(frozen=True)
class WorkspaceLayout:
    config_path: Path
    framework_root: Path
    knowledge_root: Path
    repositories_root: Path | None

    def system_dir(self) -> Path:
        return self.knowledge_root / "system"

    def repositories_knowledge_dir(self) -> Path:
        return self.knowledge_root / "repositories"

    def workflows_dir(self) -> Path:
        return self.knowledge_root / "workflows"

    def changes_dir(self) -> Path:
        return self.knowledge_root / "changes"

    def decisions_dir(self) -> Path:
        return self.knowledge_root / "decisions" / "architecture-decisions"

    def governance_dir(self) -> Path:
        return self.knowledge_root / "governance"

    def audit_log(self) -> Path:
        return self.knowledge_root / "governance" / "audit.jsonl"

    def registry_path(self) -> Path:
        return self.system_dir() / "repository-registry.yaml"

    def knowledge_index_path(self) -> Path:
        return self.system_dir() / "knowledge-index.yaml"

    def dependency_map_path(self) -> Path:
        return self.system_dir() / "dependency-map.yaml"

    def repo_knowledge_dir(self, name: str) -> Path:
        return self.repositories_knowledge_dir() / name

    def change_stage_dir(self, stage: str) -> Path:
        return self.changes_dir() / stage


def layout_from_config(config: SddConfig, config_path: Path, framework_root: Path) -> WorkspaceLayout:
    base = config_path.parent
    knowledge = resolve_path(base / config.workspace.knowledge_root)
    repos_root = None
    if config.workspace.repositories_root:
        repos_root = resolve_path(base / config.workspace.repositories_root)
    return WorkspaceLayout(
        config_path=config_path,
        framework_root=framework_root,
        knowledge_root=knowledge,
        repositories_root=repos_root,
    )


def create_knowledge_tree(layout: WorkspaceLayout) -> None:
    for path in [
        layout.system_dir(),
        layout.repositories_knowledge_dir(),
        layout.workflows_dir(),
        layout.change_stage_dir("proposals"),
        layout.change_stage_dir("approved"),
        layout.change_stage_dir("in-progress"),
        layout.change_stage_dir("archive"),
        layout.decisions_dir(),
        layout.governance_dir(),
    ]:
        ensure_dir(path)
