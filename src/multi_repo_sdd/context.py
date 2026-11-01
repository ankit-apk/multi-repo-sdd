from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from multi_repo_sdd.config import SddConfig, find_config, load_config, save_config
from multi_repo_sdd.errors import ConfigError
from multi_repo_sdd.guardian import Guardian
from multi_repo_sdd.layout import WorkspaceLayout, create_knowledge_tree, layout_from_config
from multi_repo_sdd.safety import AuditLog, ensure_dir, resolve_path


FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class AppContext:
    config: SddConfig
    layout: WorkspaceLayout
    guardian: Guardian
    audit: AuditLog


def load_app(start: Path | None = None) -> AppContext:
    path = find_config(start)
    if path is None:
        raise ConfigError("No sdd.config.yaml found. Run `sdd init` first.")
    config = load_config(path)
    layout = layout_from_config(config, path, FRAMEWORK_ROOT)
    create_knowledge_tree(layout)
    guardian = Guardian(layout, config)
    return AppContext(config=config, layout=layout, guardian=guardian, audit=AuditLog(layout.audit_log()))


def init_workspace(
    target: Path,
    knowledge_root: str = "./sdd-workspace",
    repositories_root: str | None = None,
    name: str = "sdd-workspace",
) -> Path:
    target = resolve_path(target)
    ensure_dir(target)
    config_path = target / "sdd.config.yaml"
    config = SddConfig()
    config.workspace.name = name
    config.workspace.knowledge_root = knowledge_root
    config.workspace.repositories_root = repositories_root
    save_config(config, config_path)
    layout = layout_from_config(config, config_path, FRAMEWORK_ROOT)
    create_knowledge_tree(layout)
    governance = layout.governance_dir()
    (governance / "agent-contracts.md").write_text(
        """# Agent contracts

## Guardian

The Guardian is the only default entry point for developers. It retrieves persistent knowledge files rather than relying on chat memory.

## Repository discovery agents

Each discovery agent analyses exactly one repository, is read-only, and must emit the standard knowledge contract with evidence and confidence.

## Implementation agents

Implementation agents receive an approved packet: specification, design, tasks, and repository path. They must not exceed assigned scope.
""",
        encoding="utf-8",
    )
    (governance / "quality-gates.md").write_text(
        """# Quality gates

- Architecture: replaceable agent providers, isolated Spec Kit adapter, file-based knowledge.
- Discovery: evidence, commit SHAs, unknowns preserved, repositories unmodified.
- Specification: testable requirements, recorded approvals, identified repository impact.
- Implementation: only approved tasks, tests updated, assigned scope only.
- Completion: acceptance criteria verified, convergence recorded, knowledge synchronized.
""",
        encoding="utf-8",
    )
    (governance / "artifact-ownership.md").write_text(
        """# Artifact ownership

| Artifact | Owner | Location |
|---|---|---|
| Baseline knowledge | Discovery agents | `sdd-workspace/repositories/` and `system/` |
| Change proposal, design, tasks, archive | This framework (OpenSpec-inspired) | `sdd-workspace/changes/` |
| Spec Kit lifecycle mapping | Spec Kit adapter | change folder files mapped to Spec Kit phases |
| Application source | Application repositories | registered paths, unmodified during discovery |
| ADRs | Humans + Guardian | `sdd-workspace/decisions/` |

Do not install Spec Kit and OpenSpec as competing workflows in the same application repository by default.
""",
        encoding="utf-8",
    )
    AuditLog(layout.audit_log()).record("init", config=str(config_path))
    return config_path
