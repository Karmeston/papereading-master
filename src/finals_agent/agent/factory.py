from __future__ import annotations

from finals_agent.agent.llm import build_chat_model
from finals_agent.agent.prompts import build_system_prompt
from finals_agent.data.repository import StudyRepository
from finals_agent.core.runtime import AgentRuntime
from finals_agent.agent.tool_registry import ToolRegistry, build_tool_registry
from finals_agent.data.retrievers import Retriever
from typing import Iterable


def build_agent(
    repository: StudyRepository | None = None,
    model=None,
    runtime: AgentRuntime | None = None,
    tool_registry: ToolRegistry | None = None,
    retriever: Retriever | None = None,
    tool_names: Iterable[str] | None = None,
):
    """Build the LangChain agent.

    LangChain v1 uses create_agent as the standard agent entry point. The
    returned object is a LangGraph-backed runnable that accepts a messages list.
    """
    from langchain.agents import create_agent

    runtime = runtime or AgentRuntime.default()
    model = model or build_chat_model()
    registry = tool_registry or build_tool_registry(
        repository=repository,
        runtime=runtime,
        retriever=retriever,
        model=model,
    )
    return create_agent(
        model=model,
        tools=registry.select(tool_names),
        system_prompt=build_system_prompt(runtime),
    )


def ask_agent(question: str, runtime: AgentRuntime | None = None) -> str:
    """Compatibility wrapper. Prefer finals_agent.agent.runner.ask_agent."""
    from finals_agent.agent.runner import ask_agent as run_question

    return run_question(question, runtime=runtime)
