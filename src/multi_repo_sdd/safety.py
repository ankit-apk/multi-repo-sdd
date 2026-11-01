from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from multi_repo_sdd.errors import PathSafetyError

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|credential)\s*[:=]\s*['\"]?([^\s'\"]+)"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(postgres|mysql|mongodb|redis)://[^:\s]+:[^@\s]+@"),
]

REDACTED = "[REDACTED]"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def assert_within(path: Path, *roots: Path) -> Path:
    resolved = resolve_path(path)
    for root in roots:
        allowed = resolve_path(root)
        try:
            resolved.relative_to(allowed)
            return resolved
        except ValueError:
            continue
    raise PathSafetyError(
        f"Path {resolved} is outside registered workspace locations"
    )


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def redact_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def looks_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in ("secret", "password", "token", "api_key", "apikey", "credential"))


def sanitize_mapping(data: dict) -> dict:
    clean: dict = {}
    for key, value in data.items():
        if looks_secret_key(str(key)):
            clean[key] = REDACTED
        elif isinstance(value, dict):
            clean[key] = sanitize_mapping(value)
        elif isinstance(value, str):
            clean[key] = redact_text(value)
        else:
            clean[key] = value
    return clean


_AUDIT_GUARD = threading.Lock()
_AUDIT_LOCKS: dict[str, threading.Lock] = {}


def _audit_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _AUDIT_GUARD:
        lock = _AUDIT_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _AUDIT_LOCKS[key] = lock
        return lock


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, action: str, **fields: object) -> None:
        entry = {"timestamp": utc_now(), "action": action, **fields}
        line = json.dumps(entry, default=str) + "\n"
        with _audit_lock(self.path):
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
