from __future__ import annotations

import json
import os
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class StorageBackend(ABC):
    @abstractmethod
    def read(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def write(self, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def update(self, updater) -> Any:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError


class JsonFileStorage(StorageBackend):
    def __init__(self, path: Path):
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")

    def read(self) -> dict[str, Any]:
        with self._locked():
            return self._read_unlocked()

    def write(self, payload: dict[str, Any]) -> None:
        with self._locked():
            self._write_unlocked(payload)

    def update(self, updater) -> Any:
        with self._locked():
            payload = self._read_unlocked()
            result = updater(payload)
            self._write_unlocked(payload)
            return result

    def clear(self) -> None:
        with self._locked():
            if self.path.exists():
                self.path.unlink()

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write_unlocked(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.path)

    @contextmanager
    def _locked(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock_file:
            _lock_file(lock_file)
            try:
                yield
            finally:
                _unlock_file(lock_file)


def _lock_file(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)


def _unlock_file(lock_file) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
