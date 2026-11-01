from __future__ import annotations

import os
import time
from pathlib import Path

from multi_repo_sdd.errors import DiscoveryError

LOCK_TTL_SECONDS = 900


class DiscoveryLock:
    """Exclusive lock so two runs cannot rewrite one repository's knowledge."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> "DiscoveryLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.path.unlink(missing_ok=True)

    def _acquire(self) -> None:
        try:
            self._create()
        except FileExistsError:
            if not self._stale():
                raise DiscoveryError(
                    f"A discovery run is already active for this repository ({self.path.stem})"
                ) from None
            self.path.unlink(missing_ok=True)
            try:
                self._create()
            except FileExistsError as exc:
                raise DiscoveryError(
                    f"A discovery run is already active for this repository ({self.path.stem})"
                ) from exc

    def _create(self) -> None:
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, f"{os.getpid()}\n".encode())
        finally:
            os.close(fd)

    def _stale(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
        except OSError:
            return True
        return age > LOCK_TTL_SECONDS
