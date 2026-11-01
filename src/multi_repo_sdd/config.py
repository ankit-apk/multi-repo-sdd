from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from multi_repo_sdd.errors import ConfigError

Confidence = Literal["verified", "inferred", "unknown"]
DiscoveryMode = Literal["initial", "incremental", "targeted"]
SddFramework = Literal["spec-kit"]


class WorkspaceSettings(BaseModel):
    name: str = "sdd-workspace"
    repositories_root: str | None = None
    knowledge_root: str = "./sdd-workspace"


class DiscoverySettings(BaseModel):
    default_mode: DiscoveryMode = "incremental"
    read_only: bool = True
    evidence_required: bool = True
    ignore_globs: list[str] = Field(
        default_factory=lambda: [
            ".git/**",
            "node_modules/**",
            ".venv/**",
            "venv/**",
            "dist/**",
            "build/**",
            "__pycache__/**",
            "target/**",
            ".idea/**",
            ".vscode/**",
        ]
    )


class GuardianAgentSettings(BaseModel):
    enabled: bool = True


class RepositoryDiscoveryAgentSettings(BaseModel):
    enabled: bool = True
    execution_mode: Literal["parallel", "sequential"] = "parallel"


class AgentSettings(BaseModel):
    guardian: GuardianAgentSettings = Field(default_factory=GuardianAgentSettings)
    repository_discovery: RepositoryDiscoveryAgentSettings = Field(
        default_factory=RepositoryDiscoveryAgentSettings
    )
    provider: str = "cursor"
    implementation_provider: Literal["local-packet", "command"] = "local-packet"
    implementation_command: list[str] = Field(default_factory=list)
    implementation_timeout_seconds: int = 3600


class SddLifecycleSettings(BaseModel):
    primary_framework: SddFramework = "spec-kit"
    framework_version: str = "1.2.5"
    specify_command: str = "specify"
    integration: str = "copilot"
    require_spec_approval: bool = True
    require_design_approval: bool = True
    auto_init_speckit_in_app_repos: bool = False


class GovernanceSettings(BaseModel):
    require_human_approval: bool = True
    require_regression_tests: bool = True
    require_convergence: bool = True
    authorize_repository_writes: bool = False


class KnowledgeSettings(BaseModel):
    format: Literal["markdown-yaml"] = "markdown-yaml"
    track_commit_sha: bool = True
    track_confidence: bool = True


class SddConfig(BaseModel):
    workspace: WorkspaceSettings = Field(default_factory=WorkspaceSettings)
    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    agents: AgentSettings = Field(default_factory=AgentSettings)
    sdd: SddLifecycleSettings = Field(default_factory=SddLifecycleSettings)
    governance: GovernanceSettings = Field(default_factory=GovernanceSettings)
    knowledge: KnowledgeSettings = Field(default_factory=KnowledgeSettings)
    extra_repository_roots: list[str] = Field(default_factory=list)

    @field_validator("extra_repository_roots")
    @classmethod
    def _no_blank_roots(cls, value: list[str]) -> list[str]:
        return [item for item in value if item.strip()]


def default_config() -> SddConfig:
    return SddConfig()


def load_config(path: Path) -> SddConfig:
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError("Configuration root must be a mapping")
    try:
        return SddConfig.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(str(exc)) from exc


def save_config(config: SddConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = config.model_dump(mode="python")
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def find_config(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        path = candidate / "sdd.config.yaml"
        if path.is_file():
            return path
    return None
