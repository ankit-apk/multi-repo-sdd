from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["verified", "inferred", "unknown"]
RelationType = Literal[
    "synchronous-api",
    "asynchronous-event",
    "shared-database",
    "shared-library",
    "message-queue",
    "file-integration",
    "external-service",
    "unknown",
]


class Evidence(BaseModel):
    description: str
    repository: str
    file: str | None = None
    symbol: str | None = None
    commit_sha: str | None = None
    timestamp: str
    confidence: Confidence
    evidence_type: str = "source"


class Capability(BaseModel):
    name: str
    description: str
    evidence: list[Evidence] = Field(default_factory=list)


class ApiEndpoint(BaseModel):
    method: str
    path: str
    handler: str | None = None
    description: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class ModuleInfo(BaseModel):
    name: str
    path: str
    description: str | None = None


class WorkflowStep(BaseModel):
    order: int
    repository: str
    action: str
    interface: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class Dependency(BaseModel):
    source: str
    target: str
    type: RelationType = "unknown"
    interface: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: Confidence = "inferred"
    last_verified_commit: str | None = None


class DiscoveryReport(BaseModel):
    name: str
    path: str
    purpose: str
    language: str | None = None
    frameworks: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    modules: list[ModuleInfo] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    apis: list[ApiEndpoint] = Field(default_factory=list)
    database_notes: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    commit_sha: str | None = None
    mode: str = "initial"
    discovered_at: str
    files_scanned: int = 0
