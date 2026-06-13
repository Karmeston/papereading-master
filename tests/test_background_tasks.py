from __future__ import annotations

from threading import Event
import time

from finals_agent.app.background_tasks import BackgroundTaskManager


def test_background_task_completes_with_result():
    manager = BackgroundTaskManager()
    task = manager.submit(
        "example",
        lambda context: (
            context.update(50, "halfway")
            or {"value": 42}
        ),
    )

    result = _wait_for_final(manager, task["id"])

    assert result["status"] == "completed"
    assert result["progress"] == 100
    assert result["result"] == {"value": 42}


def test_background_task_can_be_cancelled_before_worker_returns():
    manager = BackgroundTaskManager()
    release = Event()

    def worker(context):
        release.wait(timeout=2)
        context.raise_if_cancelled()
        return {"unexpected": True}

    task = manager.submit("slow", worker)
    cancelled = manager.cancel(task["id"])

    assert cancelled["status"] == "cancelled"
    release.set()
    time.sleep(0.05)
    assert manager.get(task["id"])["status"] == "cancelled"


def _wait_for_final(manager: BackgroundTaskManager, task_id: str) -> dict:
    deadline = time.time() + 2
    while time.time() < deadline:
        task = manager.get(task_id)
        if task["status"] in {"completed", "failed", "cancelled"}:
            return task
        time.sleep(0.01)
    raise AssertionError("background task did not finish")
