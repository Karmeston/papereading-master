from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finals_agent.core.config import RUNS_PATH
from finals_agent.core.schemas import AgentRequest, AgentRunResult
from finals_agent.persistence.storage import JsonFileStorage, StorageBackend


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: str
    question: str
    answer: str | None
    conversation_id: str | None
    task_type: str | None
    preretrieval_count: int
    message_count: int
    input_message_count: int
    duration_ms: float | None
    metadata: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "question": self.question,
            "answer": self.answer,
            "conversation_id": self.conversation_id,
            "task_type": self.task_type,
            "preretrieval_count": self.preretrieval_count,
            "message_count": self.message_count,
            "input_message_count": self.input_message_count,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "error": self.error,
        }

    @classmethod
    def from_result(cls, request: AgentRequest, result: AgentRunResult) -> "RunRecord":
        metadata = result.metadata or {}
        trace = metadata.get("trace", {})
        task_plan = metadata.get("task_plan", {})
        intent = task_plan.get("intent", {})
        preretrieval = metadata.get("preretrieval", {})
        return cls(
            run_id=trace.get("run_id", "unknown"),
            status=trace.get("status", "success"),
            question=request.question,
            answer=result.answer,
            conversation_id=result.conversation_id,
            task_type=intent.get("task_type"),
            preretrieval_count=preretrieval.get("count", 0),
            message_count=metadata.get("message_count", 0),
            input_message_count=metadata.get("input_message_count", 0),
            duration_ms=trace.get("duration_ms"),
            metadata=metadata,
            error=trace.get("error"),
        )

    @classmethod
    def failure(
        cls,
        request: AgentRequest,
        run_id: str,
        error: Exception,
        metadata: dict[str, Any],
    ) -> "RunRecord":
        trace = metadata.get("trace", {})
        return cls(
            run_id=run_id,
            status="error",
            question=request.question,
            answer=None,
            conversation_id=request.conversation_id,
            task_type=metadata.get("task_type"),
            preretrieval_count=metadata.get("preretrieval_count", 0),
            message_count=0,
            input_message_count=0,
            duration_ms=trace.get("duration_ms"),
            metadata=metadata,
            error=f"{error.__class__.__name__}: {error}",
        )


class RunRecorder:
    def record(self, record: RunRecord) -> None:
        raise NotImplementedError


class JsonRunRecorder(RunRecorder):
    def __init__(self, storage: StorageBackend | None = None):
        self.storage = storage or JsonFileStorage(RUNS_PATH)

    def record(self, record: RunRecord) -> None:
        def updater(payload):
            runs = payload.setdefault("runs", [])
            runs.append(record.to_dict())

        self.storage.update(updater)

    def list_records(self) -> list[dict[str, Any]]:
        return list(self.storage.read().get("runs", []))
