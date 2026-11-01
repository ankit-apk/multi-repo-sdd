from __future__ import annotations

from pathlib import Path

from multi_repo_sdd.config import SddConfig
from multi_repo_sdd.deps import collect_dependencies, render_dependencies, transitive
from multi_repo_sdd.discovery.engine import discover_repositories
from multi_repo_sdd.impact import analyze_impact
from multi_repo_sdd.knowledge import read_text_if_exists, rebuild_system_knowledge, repository_freshness, search_knowledge
from multi_repo_sdd.layout import WorkspaceLayout
from multi_repo_sdd.registry import load_registry
from multi_repo_sdd.sdd.changes import archive_change, propose_change, validate_change
from multi_repo_sdd.sdd.governance import require_approvals
from multi_repo_sdd.sdd.implement import implement_change
from multi_repo_sdd.sdd.verify import verify_change
from multi_repo_sdd.workflows import discover_workflow


class Guardian:
    """Central orchestrator. Uses persistent knowledge files, not conversation memory."""

    def __init__(self, layout: WorkspaceLayout, config: SddConfig) -> None:
        self.layout = layout
        self.config = config

    def get_system_overview(self) -> str:
        rebuild_system_knowledge(self.layout)
        text = read_text_if_exists(self.layout.system_dir() / "system-overview.md")
        return text or "Unknown: run discovery first."

    def list_repositories(self) -> list[dict]:
        return [item.model_dump() for item in load_registry(self.layout).repositories]

    def get_repository_overview(self, name: str) -> str:
        text = read_text_if_exists(self.layout.repo_knowledge_dir(name) / "repository-overview.md")
        return text or f"Unknown: no overview for {name}. Run `sdd discover --repo {name}`."

    def get_repository_architecture(self, name: str) -> str:
        text = read_text_if_exists(self.layout.repo_knowledge_dir(name) / "architecture.md")
        return text or f"Unknown: no architecture document for {name}."

    def get_business_capabilities(self, name: str | None = None) -> str:
        if name:
            text = read_text_if_exists(self.layout.repo_knowledge_dir(name) / "business-capabilities.md")
            return text or f"Unknown: no capabilities for {name}."
        text = read_text_if_exists(self.layout.system_dir() / "business-capabilities.md")
        return text or "Unknown: rebuild system knowledge after discovery."

    def get_business_workflow(self, description: str) -> Path:
        return discover_workflow(self.layout, description)

    def get_repository_dependencies(self, name: str | None = None) -> str:
        deps = collect_dependencies(self.layout)
        if name:
            deps = [item for item in deps if item.source == name or item.target == name]
            extra = "\n\nTransitive from source:\n" + ", ".join(transitive(deps, name) or ["none"])
            return render_dependencies(deps) + extra
        return render_dependencies(deps)

    def get_api_contract(self, name: str) -> str:
        text = read_text_if_exists(self.layout.repo_knowledge_dir(name) / "api-contracts.md")
        return text or f"Unknown: no API contract for {name}."

    def search_knowledge(self, query: str) -> list[dict]:
        return search_knowledge(self.layout, query)

    def get_source_evidence(self, query: str) -> list[dict]:
        hits = search_knowledge(self.layout, query, limit=50)
        evidence_hits = []
        for hit in hits:
            snippet = hit["snippet"].lower()
            if any(token in snippet for token in ("verified", "inferred", "unknown", ".py", ".js", ".java", ".go", ".cs")):
                evidence_hits.append(hit)
        return evidence_hits

    def analyze_change_impact(self, change: str) -> Path:
        return analyze_impact(self.layout, change)

    def create_change_proposal(self, description: str) -> Path:
        return propose_change(self.layout, description)

    def validate_specification(self, change_id: str) -> dict:
        return validate_change(self.layout, change_id)

    def coordinate_implementation(self, change_id: str, authorize_writes: bool = False) -> dict:
        require_approvals(self.layout, self.config, change_id, for_implementation=True)
        return implement_change(self.layout, self.config, change_id, authorize_writes=authorize_writes)

    def verify_implementation(self, change_id: str) -> dict:
        return verify_change(self.layout, self.config, change_id)

    def check_knowledge_freshness(self) -> list[dict]:
        rebuild_system_knowledge(self.layout)
        registry = load_registry(self.layout)
        rows = []
        for repo in registry.repositories:
            meta_path = self.layout.repo_knowledge_dir(repo.name) / "discovery-metadata.yaml"
            meta = {}
            if meta_path.is_file():
                import yaml

                meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            recorded = meta.get("commit_sha") or repo.last_discovered_sha
            freshness = repository_freshness(Path(repo.path), recorded, meta_path.is_file())
            rows.append(
                {
                    "repository": repo.name,
                    "last_discovered_sha": recorded,
                    "current_sha": freshness["current_sha"],
                    "has_knowledge": meta_path.is_file(),
                    "fresh": freshness["fresh"],
                    "state": freshness["state"],
                }
            )
        return rows

    def refresh_all(self) -> None:
        discover_repositories(self.layout, self.config, mode="incremental")
        collect_dependencies(self.layout)
        rebuild_system_knowledge(self.layout)

    def archive(self, change_id: str) -> Path:
        return archive_change(self.layout, change_id, config=self.config)
