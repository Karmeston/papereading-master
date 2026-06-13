from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from typing import Any, Callable
import uuid

from finals_agent.core.exceptions import ToolInputError


FINAL_STATUSES = {"completed", "failed", "cancelled"}


class TaskCancelledError(Exception):
    pass


@dataclass
class BackgroundTaskContext:
    task_id: str
    cancel_event: Event
    update_callback: Callable[[int, str], None]

    def update(self, progress: int, message: str) -> None:
        self.raise_if_cancelled()
        self.update_callback(max(0, min(int(progress), 100)), str(message))

    def raise_if_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise TaskCancelledError()


@dataclass
class _TaskRecord:
    id: str
    kind: str
    status: str = "queued"
    progress: int = 0
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())
    cancel_event: Event = field(default_factory=Event, repr=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class BackgroundTaskManager:
    def __init__(self, max_records: int = 100):
        self.max_records = max(10, max_records)
        self._records: dict[str, _TaskRecord] = {}
        self._lock = Lock()

    def submit(
        self,
        kind: str,
        worker: Callable[[BackgroundTaskContext], dict[str, Any]],
    ) -> dict[str, Any]:
        task_id = uuid.uuid4().hex[:16]
        record = _TaskRecord(id=task_id, kind=kind, message="等待执行")
        with self._lock:
            self._prune_locked()
            self._records[task_id] = record
        Thread(
            target=self._run,
            args=(record, worker),
            name=f"paper-agent-{kind}-{task_id}",
            daemon=True,
        ).start()
        return record.snapshot()

    def get(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(task_id)
            if record is None:
                raise ToolInputError(f"Background task does not exist: {task_id}.")
            return record.snapshot()

    def cancel(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(task_id)
            if record is None:
                raise ToolInputError(f"Background task does not exist: {task_id}.")
            if record.status not in FINAL_STATUSES:
                record.cancel_event.set()
                record.status = "cancelled"
                record.message = "已取消"
                record.updated_at = _now()
            return record.snapshot()

    def _run(
        self,
        record: _TaskRecord,
        worker: Callable[[BackgroundTaskContext], dict[str, Any]],
    ) -> None:
        self._update_record(record.id, status="running", progress=1, message="正在执行")
        context = BackgroundTaskContext(
            task_id=record.id,
            cancel_event=record.cancel_event,
            update_callback=lambda progress, message: self._update_record(
                record.id,
                progress=progress,
                message=message,
            ),
        )
        try:
            context.raise_if_cancelled()
            result = worker(context)
            context.raise_if_cancelled()
        except TaskCancelledError:
            self._update_record(
                record.id,
                status="cancelled",
                message="已取消",
                progress=record.progress,
            )
        except Exception as exc:
            self._update_record(
                record.id,
                status="failed",
                message="执行失败",
                error=f"{exc.__class__.__name__}: {exc}",
            )
        else:
            self._update_record(
                record.id,
                status="completed",
                progress=100,
                message="已完成",
                result=result,
            )

    def _update_record(self, task_id: str, **changes: Any) -> None:
        with self._lock:
            record = self._records.get(task_id)
            if record is None:
                return
            for key, value in changes.items():
                setattr(record, key, value)
            record.updated_at = _now()

    def _prune_locked(self) -> None:
        if len(self._records) < self.max_records:
            return
        completed = [
            record
            for record in self._records.values()
            if record.status in FINAL_STATUSES
        ]
        completed.sort(key=lambda item: item.updated_at)
        for record in completed[: max(1, len(self._records) - self.max_records + 1)]:
            self._records.pop(record.id, None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
