from __future__ import annotations

from queue import Queue
from threading import Thread
from typing import Callable, Iterator

from finals_agent.agent.factory import build_agent
from finals_agent.persistence.memory import MemoryStore
from finals_agent.core.events import AgentEvent, EventSink, bind_event_sink
from finals_agent.agent.planning import TaskPlanner
from finals_agent.agent.orchestrator import TaskOrchestrator
from finals_agent.agent.query_rewrite import RetrievalQueryRewriter
from finals_agent.agent.tool_registry import ToolRegistry
from finals_agent.data.repository import StudyRepository
from finals_agent.data.retrievers import Retriever
from finals_agent.persistence.runs import RunRecorder
from finals_agent.core.runtime import AgentRuntime
from finals_agent.core.schemas import AgentRequest, AgentRunResult

def run_agent(
    request: AgentRequest,
    repository: StudyRepository | None = None,
    model=None,
    runtime: AgentRuntime | None = None,
    agent=None,
    memory_store: MemoryStore | None = None,
    planner: TaskPlanner | None = None,
    retriever: Retriever | None = None,
    run_recorder: RunRecorder | None = None,
    event_sink: EventSink | None = None,
    max_turns: int = 30,
    max_verification_retries: int = 1,
    tool_registry: ToolRegistry | None = None,
    query_rewriter: RetrievalQueryRewriter | None = None,
    max_retrieval_rewrites: int = 1,
    token_sink: Callable[[str], None] | None = None,
) -> AgentRunResult:
    with bind_event_sink(event_sink):
        return _run_agent(
            request=request,
            repository=repository,
            model=model,
            runtime=runtime,
            agent=agent,
            memory_store=memory_store,
            planner=planner,
            retriever=retriever,
            run_recorder=run_recorder,
            max_turns=max_turns,
            max_verification_retries=max_verification_retries,
            tool_registry=tool_registry,
            query_rewriter=query_rewriter,
            max_retrieval_rewrites=max_retrieval_rewrites,
            token_sink=token_sink,
        )


def _run_agent(
    request: AgentRequest,
    repository: StudyRepository | None = None,
    model=None,
    runtime: AgentRuntime | None = None,
    agent=None,
    memory_store: MemoryStore | None = None,
    planner: TaskPlanner | None = None,
    retriever: Retriever | None = None,
    run_recorder: RunRecorder | None = None,
    max_turns: int = 30,
    max_verification_retries: int = 1,
    tool_registry: ToolRegistry | None = None,
    query_rewriter: RetrievalQueryRewriter | None = None,
    max_retrieval_rewrites: int = 1,
    token_sink: Callable[[str], None] | None = None,
) -> AgentRunResult:
    orchestrator = TaskOrchestrator(
        repository=repository,
        model=model,
        runtime=runtime,
        agent=agent,
        agent_factory=build_agent,
        memory_store=memory_store,
        planner=planner,
        retriever=retriever,
        run_recorder=run_recorder,
        tool_registry=tool_registry,
        query_rewriter=query_rewriter,
        max_turns=max_turns,
        max_verification_retries=max_verification_retries,
        max_retrieval_rewrites=max_retrieval_rewrites,
        token_sink=token_sink,
    )
    return orchestrator.run(request)


def stream_agent_events(
    request: AgentRequest,
    repository: StudyRepository | None = None,
    model=None,
    runtime: AgentRuntime | None = None,
    agent=None,
    memory_store: MemoryStore | None = None,
    planner: TaskPlanner | None = None,
    retriever: Retriever | None = None,
    run_recorder: RunRecorder | None = None,
    max_turns: int = 30,
    max_verification_retries: int = 1,
    tool_registry: ToolRegistry | None = None,
    query_rewriter: RetrievalQueryRewriter | None = None,
    max_retrieval_rewrites: int = 1,
) -> Iterator[AgentEvent]:
    queue: Queue[AgentEvent | object] = Queue()
    sentinel = object()
    errors: list[BaseException] = []

    def enqueue(event: AgentEvent) -> None:
        queue.put(event)

    def worker() -> None:
        status = "success"
        try:
            run_agent(
                request=request,
                repository=repository,
                model=model,
                runtime=runtime,
                agent=agent,
                memory_store=memory_store,
                planner=planner,
                retriever=retriever,
                run_recorder=run_recorder,
                max_turns=max_turns,
                max_verification_retries=max_verification_retries,
                tool_registry=tool_registry,
                query_rewriter=query_rewriter,
                max_retrieval_rewrites=max_retrieval_rewrites,
                event_sink=enqueue,
            )
        except BaseException as exc:
            status = "error"
            errors.append(exc)
        finally:
            queue.put({"event": "stream_closed", "status": status})
            queue.put(sentinel)

    thread = Thread(target=worker, daemon=True)
    thread.start()
    while True:
        item = queue.get()
        if item is sentinel:
            break
        yield item
    thread.join()
    if errors:
        raise errors[0]


def ask_agent(question: str, runtime: AgentRuntime | None = None) -> str:
    request = AgentRequest(
        question=question,
        course_context=runtime.course_context if runtime else None,
    )
    return run_agent(request=request, runtime=runtime).answer
