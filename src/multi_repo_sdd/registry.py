from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from multi_repo_sdd.errors import RegistryError
from multi_repo_sdd.layout import WorkspaceLayout
from multi_repo_sdd.safety import resolve_path, utc_now


class RegisteredRepository(BaseModel):
    name: str
    path: str
    language: str | None = None
    last_discovered_sha: str | None = None
    last_discovered_at: str | None = None
    registered_at: str
    tags: list[str] = Field(default_factory=list)


class RepositoryRegistry(BaseModel):
    workspace: str
    repositories: list[RegisteredRepository] = Field(default_factory=list)

    def get(self, name: str) -> RegisteredRepository:
        for repo in self.repositories:
            if repo.name == name:
                return repo
        raise RegistryError(f"Repository is not registered: {name}")

    def names(self) -> list[str]:
        return [repo.name for repo in self.repositories]

    def upsert(self, repo: RegisteredRepository) -> None:
        self.repositories = [item for item in self.repositories if item.name != repo.name]
        self.repositories.append(repo)
        self.repositories.sort(key=lambda item: item.name)

    def remove(self, name: str) -> None:
        before = len(self.repositories)
        self.repositories = [item for item in self.repositories if item.name != name]
        if len(self.repositories) == before:
            raise RegistryError(f"Repository is not registered: {name}")


def load_registry(layout: WorkspaceLayout) -> RepositoryRegistry:
    path = layout.registry_path()
    if not path.is_file():
        return RepositoryRegistry(workspace=layout.knowledge_root.name)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return RepositoryRegistry.model_validate(raw)


def save_registry(layout: WorkspaceLayout, registry: RepositoryRegistry) -> None:
    path = layout.registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = registry.model_dump(mode="python")
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}")


def infer_repo_name(path: Path) -> str:
    return path.name


def validate_repo_name(name: str) -> str:
    if not _NAME.fullmatch(name):
        raise RegistryError(
            "Repository name must be a single path segment of letters, numbers, '.', '_' or '-'"
        )
    return name


def register_repository(layout: WorkspaceLayout, path: Path, name: str | None = None) -> RegisteredRepository:
    resolved = resolve_path(path)
    if not resolved.is_dir():
        raise RegistryError(f"Repository path does not exist: {resolved}")
    registry = load_registry(layout)
    repo_name = validate_repo_name(name or infer_repo_name(resolved))
    existing_paths = {item.name: item.path for item in registry.repositories}
    if repo_name in existing_paths and resolve_path(existing_paths[repo_name]) != resolved:
        raise RegistryError(f"Repository name already registered with a different path: {repo_name}")
    repo = RegisteredRepository(
        name=repo_name,
        path=str(resolved),
        registered_at=utc_now(),
    )
    previous = next((item for item in registry.repositories if item.name == repo_name), None)
    if previous:
        repo.last_discovered_sha = previous.last_discovered_sha
        repo.last_discovered_at = previous.last_discovered_at
        repo.language = previous.language
        repo.tags = previous.tags
        repo.registered_at = previous.registered_at
    registry.upsert(repo)
    save_registry(layout, registry)
    return repo
