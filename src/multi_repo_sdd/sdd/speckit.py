from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from multi_repo_sdd.config import SddConfig
from multi_repo_sdd.errors import SddError


SPECKIT_PHASES = [
    "constitution",
    "specify",
    "clarify",
    "plan",
    "checklist",
    "tasks",
    "analyze",
    "implement",
    "converge",
]


class SpecKitAdapter:
    """Wraps the official Specify CLI. Never initializes Spec Kit inside app repos by default."""

    def __init__(self, config: SddConfig) -> None:
        self.config = config

    def available(self) -> bool:
        return shutil.which(self.config.sdd.specify_command) is not None

    def version(self) -> str | None:
        if not self.available():
            return None
        completed = subprocess.run(
            [self.config.sdd.specify_command, "version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return None
        return completed.stdout.strip() or completed.stderr.strip() or "unknown"

    def init_workspace(self, target: Path, integration: str | None = None) -> str:
        pinned = self.config.sdd.framework_version
        if not self.available():
            raise SddError(
                "specify CLI is not installed. Install the pinned release with: "
                f"uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v{pinned.lstrip('v')}"
            )
        if self.config.sdd.auto_init_speckit_in_app_repos:
            raise SddError("Refusing to auto-initialize Spec Kit in application repositories")
        target.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [
                self.config.sdd.specify_command,
                "init",
                "--here",
                "--force",
                "--integration",
                integration or self.config.sdd.integration,
                "--ignore-agent-tools",
            ],
            cwd=target,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise SddError(completed.stderr.strip() or completed.stdout.strip() or "specify init failed")
        return completed.stdout.strip()
