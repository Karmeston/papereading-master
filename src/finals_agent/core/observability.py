from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from finals_agent.core.schemas import RunTrace


LOGGER_NAME = "finals_agent"


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger(LOGGER_NAME).setLevel(level)


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


@dataclass
class RunObserver:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: float | None = None
    end_time: float | None = None
    status: str = "pending"
    error: str | None = None

    def start(self, **metadata: Any) -> None:
        self.start_time = time.perf_counter()
        self.status = "running"
        self.metadata.update(metadata)

    def finish(self, **metadata: Any) -> RunTrace:
        self.end_time = time.perf_counter()
        self.status = "success"
        self.metadata.update(metadata)
        return self.trace()

    def fail(self, error: Exception, **metadata: Any) -> RunTrace:
        self.end_time = time.perf_counter()
        self.status = "error"
        self.error = f"{error.__class__.__name__}: {error}"
        self.metadata.update(metadata)
        return self.trace()

    def trace(self) -> RunTrace:
        start = self.start_time or time.perf_counter()
        end = self.end_time or time.perf_counter()
        return RunTrace(
            run_id=self.run_id,
            status=self.status,
            duration_ms=round((end - start) * 1000, 2),
            metadata=dict(self.metadata),
            error=self.error,
        )


@contextmanager
def observe_run(**metadata: Any) -> Iterator[RunObserver]:
    observer = RunObserver()
    observer.start(**metadata)
    try:
        yield observer
    except Exception as exc:
        observer.fail(exc)
        raise
