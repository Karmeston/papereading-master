from __future__ import annotations

from typing import Any

from finals_agent.core.events import emit_event
from finals_agent.core.exceptions import FinalsAgentError
from finals_agent.core.schemas import ToolResult


def tool_success(
    tool_name: str,
    message: str,
    data: Any = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    result = ToolResult.success(
        tool_name=tool_name,
        message=message,
        data=data,
        metadata=metadata,
    )
    emit_event(
        "tool_finished",
        tool_name=tool_name,
        status=result.status.value,
        message=message,
        metadata=metadata or {},
    )
    return result.to_json()


def tool_empty(tool_name: str, message: str, metadata: dict[str, Any] | None = None) -> str:
    result = ToolResult.empty(
        tool_name=tool_name,
        message=message,
        metadata=metadata,
    )
    emit_event(
        "tool_finished",
        tool_name=tool_name,
        status=result.status.value,
        message=message,
        metadata=metadata or {},
    )
    return result.to_json()


def tool_error(tool_name: str, message: str, error: Exception | str, metadata: dict[str, Any] | None = None) -> str:
    error_text = str(error)
    error_type = error.__class__.__name__ if isinstance(error, Exception) else "ToolError"
    error_metadata = {"error_type": error_type, **(metadata or {})}
    result = ToolResult.failure(
        tool_name=tool_name,
        message=message,
        error=error_text,
        metadata=error_metadata,
    )
    emit_event(
        "tool_finished",
        tool_name=tool_name,
        status=result.status.value,
        message=message,
        error=error_text,
        metadata=result.metadata or {},
    )
    return result.to_json()


def expected_tool_error(tool_name: str, error: FinalsAgentError) -> str:
    metadata = error.to_metadata() if hasattr(error, "to_metadata") else None
    return tool_error(
        tool_name=tool_name,
        message="The tool could not complete the request because the input or local data is not valid.",
        error=error,
        metadata=metadata,
    )
