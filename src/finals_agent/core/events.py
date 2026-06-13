from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable, Iterator


AgentEvent = dict[str, Any]
EventSink = Callable[[AgentEvent], None]


_current_event_sink: ContextVar[EventSink | None] = ContextVar("current_event_sink", default=None)


@contextmanager
def bind_event_sink(sink: EventSink | None) -> Iterator[None]:
    token = _current_event_sink.set(sink)
    try:
        yield
    finally:
        _current_event_sink.reset(token)


def emit_event(event: str, **payload: Any) -> None:
    sink = _current_event_sink.get()
    if sink is None:
        return
    sink(
        {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
    )
