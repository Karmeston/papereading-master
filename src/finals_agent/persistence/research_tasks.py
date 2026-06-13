from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from finals_agent.core.config import RESEARCH_TASKS_PATH
from finals_agent.core.exceptions import ToolInputError
from finals_agent.persistence.storage import JsonFileStorage, StorageBackend


class ResearchTaskStore:
    def __init__(self, storage: StorageBackend | None = None):
        self.storage = storage or JsonFileStorage(RESEARCH_TASKS_PATH)

    def create(
        self,
        *,
        name: str = "",
        direction: str,
        paper_ids: list[str] | None = None,
        code_ids: list[str] | None = None,
        candidate_sort: str = "relevance",
    ) -> dict[str, Any]:
        now = _now()
        task = {
            "id": uuid.uuid4().hex[:12],
            "name": _task_name(name),
            "direction": direction.strip(),
            "paper_ids": list(dict.fromkeys(paper_ids or [])),
            "code_ids": list(dict.fromkeys(code_ids or [])),
            "related_candidates": [],
            "selected_related": [],
            "candidate_sort": (
                candidate_sort
                if candidate_sort in {"relevance", "newest", "oldest"}
                else "relevance"
            ),
            "analysis": None,
            "correspondence": None,
            "experiment": None,
            "result_attachments": [],
            "decisions": [],
            "revision": 1,
            "created_at": now,
            "updated_at": now,
        }

        def updater(payload):
            payload.setdefault("tasks", {})[task["id"]] = task
            return dict(task)

        return self.storage.update(updater)

    def get(self, task_id: str) -> dict[str, Any]:
        task = self.storage.read().get("tasks", {}).get(task_id)
        if not task:
            raise ToolInputError(f"Research task does not exist: {task_id}.")
        return _normalized_task(task)

    def update(
        self,
        task_id: str,
        *,
        expected_revision: int | None = None,
        **changes: Any,
    ) -> dict[str, Any]:
        def updater(payload):
            tasks = payload.setdefault("tasks", {})
            if task_id not in tasks:
                raise ToolInputError(f"Research task does not exist: {task_id}.")
            task = _normalized_task(tasks[task_id])
            if expected_revision is not None and task["revision"] != expected_revision:
                raise ToolInputError(
                    "Research task changed while the operation was running. "
                    "The stale result was not saved; run the operation again."
                )
            task.update(changes)
            if "name" in changes:
                task["name"] = _task_name(str(changes["name"] or ""))
            task["revision"] += 1
            task["updated_at"] = _now()
            tasks[task_id] = task
            return dict(task)

        return self.storage.update(updater)

    def invalidate_document(self, document_id: str) -> list[dict[str, Any]]:
        def updater(payload):
            tasks = payload.setdefault("tasks", {})
            changed = []
            for task_id, raw_task in list(tasks.items()):
                task = _normalized_task(raw_task)
                paper_ids = [item for item in task["paper_ids"] if item != document_id]
                code_ids = [item for item in task["code_ids"] if item != document_id]
                if paper_ids == task["paper_ids"] and code_ids == task["code_ids"]:
                    continue
                task.update(
                    paper_ids=paper_ids,
                    code_ids=code_ids,
                    analysis=None,
                    correspondence=None,
                    experiment=None,
                    decisions=[],
                    revision=task["revision"] + 1,
                    updated_at=_now(),
                )
                tasks[task_id] = task
                changed.append(dict(task))
            return changed

        return self.storage.update(updater)

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        tasks = list(self.storage.read().get("tasks", {}).values())
        tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return [_normalized_task(item) for item in tasks[: max(1, limit)]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _task_name(value: str) -> str:
    return " ".join(value.split())[:100] or "未命名科研任务"


def _normalized_task(task: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(task)
    normalized["name"] = _task_name(str(normalized.get("name") or normalized.get("direction") or ""))
    normalized.setdefault("paper_ids", [])
    normalized.setdefault("code_ids", [])
    normalized.setdefault("related_candidates", [])
    normalized.setdefault("selected_related", [])
    normalized.setdefault("candidate_sort", "relevance")
    normalized.setdefault("correspondence", None)
    normalized.setdefault("result_attachments", [])
    normalized.setdefault("decisions", [])
    normalized["revision"] = max(1, int(normalized.get("revision") or 1))
    return normalized
