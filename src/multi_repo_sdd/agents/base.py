from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class ImplementationPacket(BaseModel):
    change_id: str
    repository: str
    repository_path: str
    spec_path: str
    design_path: str
    task_path: str
    read_only: bool = True
    provider: str = "local-packet"


class AgentResult(BaseModel):
    repository: str
    status: str
    detail: str
    modified_files: list[str] = Field(default_factory=list)


class AgentProvider(Protocol):
    def submit(self, packet: ImplementationPacket) -> AgentResult: ...

    def cancel(self, packet: ImplementationPacket) -> None: ...


class CommandAgentProvider:
    """Runs a configured argv. It does not parse specification text as a shell command."""

    def __init__(self, command: list[str], timeout_seconds: int = 3600) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("implementation_command must be a non-empty argv list")
        self.command = list(command)
        self.timeout_seconds = timeout_seconds

    def submit(self, packet: ImplementationPacket) -> AgentResult:
        import os
        import subprocess

        env = os.environ.copy()
        env.update(
            {
                "SDD_CHANGE_ID": packet.change_id,
                "SDD_REPOSITORY": packet.repository,
                "SDD_REPOSITORY_PATH": packet.repository_path,
                "SDD_SPEC_PATH": packet.spec_path,
                "SDD_DESIGN_PATH": packet.design_path,
                "SDD_TASK_PATH": packet.task_path,
                "SDD_PACKET_JSON": packet.model_dump_json(),
            }
        )
        try:
            completed = subprocess.run(
                self.command,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return AgentResult(repository=packet.repository, status="error", detail=str(exc))
        output = (completed.stdout + completed.stderr)[-2000:]
        if completed.returncode != 0:
            return AgentResult(repository=packet.repository, status="error", detail=output or "command failed")
        return AgentResult(repository=packet.repository, status="completed", detail=output or "command completed")

    def cancel(self, packet: ImplementationPacket) -> None:
        return None


class LocalPacketProvider:
    """Default provider: writes packets and never mutates application repositories."""

    def submit(self, packet: ImplementationPacket) -> AgentResult:
        if packet.read_only:
            return AgentResult(
                repository=packet.repository,
                status="skipped",
                detail="Read-only packet provider does not modify application repositories",
            )
        return AgentResult(
            repository=packet.repository,
            status="error",
            detail="No mutating implementation provider is configured",
        )

    def cancel(self, packet: ImplementationPacket) -> None:
        return None
