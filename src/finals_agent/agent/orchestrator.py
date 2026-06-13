from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

from finals_agent.agent.citation_guard import CitationCheck, append_citation_warning, check_local_citations
from finals_agent.agent.context import ContextAssembler, ContextBundle
from finals_agent.agent.planning import TaskPlanner, build_task_planner
from finals_agent.agent.preretrieval import (
    PreRetrievalResult,
    merge_preretrieval_results,
    run_preretrieval,
)
from finals_agent.agent.query_rewrite import QueryRewrite, RetrievalQueryRewriter
from finals_agent.agent.tool_registry import ToolRegistry, build_tool_registry
from finals_agent.core.events import emit_event
from finals_agent.core.observability import RunObserver, get_logger
from finals_agent.core.runtime import AgentRuntime
from finals_agent.core.schemas import AgentRequest, AgentRunResult, TaskPlan, TaskType
from finals_agent.data.embeddings import build_embedding_provider
from finals_agent.data.repository import StudyRepository
from finals_agent.data.retrievers import HybridRetriever, Retriever
from finals_agent.persistence.memory import MemoryStore, assistant_message, user_message
from finals_agent.persistence.runs import RunRecord, RunRecorder


logger = get_logger("orchestrator")


class OrchestratorState(StrEnum):
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class StateTransition:
    state: OrchestratorState
    attempt: int
    detail: str

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "attempt": self.attempt,
            "detail": self.detail,
        }


@dataclass
class OrchestrationContext:
    request: AgentRequest
    runtime: AgentRuntime
    state: OrchestratorState = OrchestratorState.PLAN
    task_plan: TaskPlan | None = None
    preretrieval: PreRetrievalResult | None = None
    context_bundle: ContextBundle | None = None
    raw_messages: list[Any] = field(default_factory=list)
    draft_answer: str = ""
    final_answer: str = ""
    citation_check: CitationCheck | None = None
    active_tool_names: tuple[str, ...] = ()
    verification_attempts: int = 0
    retrieval_rewrite_attempts: int = 0
    retrieval_query: str = ""
    query_rewrites: list[QueryRewrite] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)

    def transition(self, state: OrchestratorState, detail: str) -> None:
        self.state = state
        transition = StateTransition(
            state=state,
            attempt=self.verification_attempts,
            detail=detail,
        )
        self.transitions.append(transition)
        emit_event(
            "orchestrator_state_changed",
            state=state.value,
            attempt=self.verification_attempts,
            detail=detail,
        )


class TaskOrchestrator:
    def __init__(
        self,
        *,
        repository: StudyRepository | None = None,
        model=None,
        runtime: AgentRuntime | None = None,
        agent=None,
        agent_factory: Callable | None = None,
        memory_store: MemoryStore | None = None,
        planner: TaskPlanner | None = None,
        retriever: Retriever | None = None,
        run_recorder: RunRecorder | None = None,
        tool_registry: ToolRegistry | None = None,
        query_rewriter: RetrievalQueryRewriter | None = None,
        max_turns: int = 30,
        max_verification_retries: int = 1,
        max_retrieval_rewrites: int = 1,
        token_sink: Callable[[str], None] | None = None,
    ):
        self.repository = repository or StudyRepository()
        self.model = model
        self.runtime = runtime
        self.agent = agent
        self.agent_factory = agent_factory
        self.memory_store = memory_store
        self.planner = planner
        self.retriever = retriever
        self.run_recorder = run_recorder
        self.tool_registry = tool_registry
        self.query_rewriter = query_rewriter
        self.max_turns = max_turns
        self.max_verification_retries = max(0, max_verification_retries)
        self.max_retrieval_rewrites = max(0, max_retrieval_rewrites)
        self.token_sink = token_sink

    def run(self, request: AgentRequest) -> AgentRunResult:
        runtime = self.runtime or (
            AgentRuntime(course_context=request.course_context)
            if request.course_context
            else AgentRuntime.default()
        )
        context = OrchestrationContext(request=request, runtime=runtime)
        observer = RunObserver()
        observer.start(
            conversation_id=request.conversation_id,
            course_context=runtime.course_context.describe(),
            debug=runtime.debug,
        )
        emit_event(
            "run_started",
            run_id=observer.run_id,
            conversation_id=request.conversation_id,
            course_context=runtime.course_context.describe(),
        )
        logger.debug("Starting orchestrated run %s", observer.run_id)

        try:
            self._plan(context, observer.run_id)
            observer.metadata["task_type"] = context.task_plan.intent.task_type.value
            self._prepare_execution(context)
            while context.state not in {OrchestratorState.COMPLETE, OrchestratorState.FAILED}:
                if context.state == OrchestratorState.EXECUTE:
                    self._execute(context, observer.run_id)
                elif context.state == OrchestratorState.VERIFY:
                    self._verify(context, observer.run_id)
                else:
                    raise RuntimeError(f"Unsupported orchestrator state: {context.state}.")
            return self._complete(context, observer)
        except Exception as exc:
            context.transition(OrchestratorState.FAILED, f"{exc.__class__.__name__}: {exc}")
            trace = observer.fail(exc, orchestrator=self._orchestration_metadata(context))
            emit_event(
                "run_failed",
                run_id=observer.run_id,
                status="error",
                error=f"{exc.__class__.__name__}: {exc}",
                metadata={"trace": trace.to_dict(), "orchestrator": self._orchestration_metadata(context)},
            )
            if self.run_recorder:
                self.run_recorder.record(
                    RunRecord.failure(
                        request=request,
                        run_id=trace.run_id,
                        error=exc,
                        metadata={
                            "trace": trace.to_dict(),
                            "task_type": (
                                context.task_plan.intent.task_type.value
                                if context.task_plan
                                else None
                            ),
                            "orchestrator": self._orchestration_metadata(context),
                        },
                    )
                )
            logger.exception("Orchestrated run %s failed", trace.run_id)
            raise

    def _plan(self, context: OrchestrationContext, run_id: str) -> None:
        planner = self.planner or build_task_planner(model=self.model)
        context.task_plan = planner.plan(context.request, context.runtime.course_context)
        emit_event("planning_finished", run_id=run_id, task_plan=context.task_plan.to_dict())
        context.transition(OrchestratorState.EXECUTE, "Task plan created.")

    def _prepare_execution(self, context: OrchestrationContext) -> None:
        assert context.task_plan is not None
        if self.agent is None and self.model is None:
            from finals_agent.agent.llm import build_chat_model

            self.model = build_chat_model()
        self.query_rewriter = self.query_rewriter or RetrievalQueryRewriter(self.model)
        embedding_provider = build_embedding_provider()
        self.retriever = self.retriever or HybridRetriever(
            repository=self.repository,
            embedding_provider=embedding_provider,
        )
        if self.agent is None:
            self.tool_registry = self.tool_registry or build_tool_registry(
                repository=self.repository,
                runtime=context.runtime,
                retriever=self.retriever,
                model=self.model,
            )
            preferred = context.task_plan.intent.preferred_tools if context.task_plan else ()
            context.active_tool_names = tuple(preferred or self.tool_registry.names)
            self.tool_registry.select(context.active_tool_names)
            if self.agent_factory is None:
                from finals_agent.agent.factory import build_agent

                self.agent_factory = build_agent
            self.agent = self.agent_factory(
                repository=self.repository,
                model=self.model,
                runtime=context.runtime,
                tool_registry=self.tool_registry,
                retriever=self.retriever,
                tool_names=context.active_tool_names,
            )
        emit_event(
            "tool_registry_ready",
            tool_count=len(context.active_tool_names),
            tools=(
                self.tool_registry.metadata(context.active_tool_names)
                if self.tool_registry
                else []
            ),
        )

    def _execute(self, context: OrchestrationContext, run_id: str) -> None:
        assert context.task_plan is not None
        if context.preretrieval is None:
            context.retrieval_query = context.task_plan.intent.topic or context.request.question
            context.preretrieval = self._retrieve(context, run_id, context.retrieval_query)
            if self._retrieval_is_empty(context.preretrieval):
                self._rewrite_and_retrieve(context, run_id, reason="empty_retrieval")
        if context.context_bundle is None:
            context.context_bundle = ContextAssembler().assemble(
                request=context.request,
                memory_store=self.memory_store,
                preretrieval=context.preretrieval,
                embedding_provider=build_embedding_provider(),
            )
        messages = list(context.context_bundle.messages)
        if context.verification_attempts:
            messages.extend(self._verification_revision_messages(context))
        emit_event(
            "context_assembled",
            run_id=run_id,
            message_count=len(messages),
            blocks=[block.name for block in context.context_bundle.blocks],
            metadata=context.context_bundle.to_metadata(),
        )
        emit_event("agent_started", run_id=run_id, attempt=context.verification_attempts)
        result = _invoke_agent(
            self.agent,
            {"messages": messages},
            max_turns=self.max_turns,
            token_sink=self.token_sink,
        )
        context.raw_messages = list(result["messages"])
        context.draft_answer = str(context.raw_messages[-1].content)
        emit_event(
            "agent_finished",
            run_id=run_id,
            message_count=len(context.raw_messages),
            attempt=context.verification_attempts,
        )
        context.transition(OrchestratorState.VERIFY, "Agent execution completed.")

    def _verify(self, context: OrchestrationContext, run_id: str) -> None:
        emit_event("verification_started", run_id=run_id, attempt=context.verification_attempts)
        context.citation_check = check_local_citations(
            context.draft_answer,
            context.preretrieval,
        )
        answer_present = bool(context.draft_answer.strip())
        passed = answer_present and context.citation_check.passed
        retry = (
            not passed
            and context.verification_attempts < self.max_verification_retries
        )
        retrieval_rewritten = False
        if (
            retry
            and context.citation_check.required
            and not context.citation_check.passed
        ):
            retrieval_rewritten = self._rewrite_and_retrieve(
                context,
                run_id,
                reason="citation_verification_failed",
            )
            if retrieval_rewritten:
                context.context_bundle = None
                context.citation_check = check_local_citations(
                    context.draft_answer,
                    context.preretrieval,
                )
        emit_event(
            "verification_finished",
            run_id=run_id,
            attempt=context.verification_attempts,
            passed=passed,
            retry=retry,
            retrieval_rewritten=retrieval_rewritten,
            citation_check=context.citation_check.to_dict(),
        )
        if retry:
            context.verification_attempts += 1
            context.transition(
                OrchestratorState.EXECUTE,
                "Verification requested a citation-preserving revision.",
            )
            return
        if not answer_present:
            raise RuntimeError("Agent returned an empty answer after verification retries.")
        context.final_answer = append_citation_warning(
            context.draft_answer,
            context.citation_check,
        )
        context.transition(OrchestratorState.COMPLETE, "Verification completed.")

    def _complete(self, context: OrchestrationContext, observer: RunObserver) -> AgentRunResult:
        assert context.task_plan is not None
        assert context.context_bundle is not None
        self._save_turn(context.request, context.final_answer)
        emit_event(
            "memory_saved",
            run_id=observer.run_id,
            enabled=self.memory_store is not None and context.request.conversation_id is not None,
            conversation_id=context.request.conversation_id,
        )
        orchestration = self._orchestration_metadata(context)
        trace = observer.finish(
            message_count=len(context.raw_messages),
            orchestrator=orchestration,
        )
        run_result = AgentRunResult(
            answer=context.final_answer,
            raw_messages=context.raw_messages,
            conversation_id=context.request.conversation_id,
            metadata={
                "message_count": len(context.raw_messages),
                "input_message_count": context.context_bundle.message_count,
                "memory_enabled": self.memory_store is not None and context.request.conversation_id is not None,
                "context": context.context_bundle.to_metadata(),
                "course_context": context.runtime.course_context.describe(),
                "task_plan": context.task_plan.to_dict(),
                "preretrieval": context.preretrieval.to_metadata(),
                "query_rewrites": [item.to_dict() for item in context.query_rewrites],
                "citation_check": context.citation_check.to_dict(),
                "trace": trace.to_dict(),
                "max_turns": self.max_turns,
                "orchestrator": orchestration,
                "tool_registry": (
                    self.tool_registry.metadata(context.active_tool_names)
                    if self.tool_registry
                    else []
                ),
            },
        )
        if self.run_recorder:
            self.run_recorder.record(RunRecord.from_result(context.request, run_result))
        emit_event(
            "run_finished",
            run_id=observer.run_id,
            status="success",
            answer=context.final_answer,
            metadata=run_result.metadata,
        )
        logger.debug("Finished orchestrated run %s in %.2f ms", trace.run_id, trace.duration_ms)
        return run_result

    def _verification_revision_messages(self, context: OrchestrationContext) -> list[dict[str, str]]:
        if not context.draft_answer.strip():
            return [
                {
                    "role": "user",
                    "content": (
                        "The previous execution returned no usable answer. "
                        "Produce a complete answer grounded in the supplied context and state any evidence limits."
                    ),
                }
            ]
        citations = "\n".join(
            f"- {citation}" for citation in context.citation_check.available_citations
        )
        return [
            {"role": "assistant", "content": context.draft_answer},
            {
                "role": "user",
                "content": (
                    "Revise the draft without changing its supported conclusions. "
                    "Retain at least one exact local citation from the list below next to the relevant claim. "
                    "Do not invent citations.\n"
                    f"{citations}"
                ),
            },
        ]

    def _retrieve(
        self,
        context: OrchestrationContext,
        run_id: str,
        query: str,
    ) -> PreRetrievalResult:
        assert context.task_plan is not None
        emit_event(
            "preretrieval_started",
            run_id=run_id,
            query=query,
            rewrite_attempt=context.retrieval_rewrite_attempts,
            document_id=context.runtime.course_context.target_document_id,
            field=context.runtime.course_context.field,
            focus=context.runtime.course_context.focus,
        )
        result = run_preretrieval(
            task_plan=context.task_plan,
            query=context.request.question,
            query_override=query,
            retriever=self.retriever,
            course=context.runtime.course_context.field,
            chapter=context.runtime.course_context.focus,
            document_id=context.runtime.course_context.target_document_id,
            limit=context.runtime.max_search_results,
        )
        emit_event(
            "preretrieval_finished",
            run_id=run_id,
            query=query,
            rewrite_attempt=context.retrieval_rewrite_attempts,
            enabled=result.enabled,
            count=result.response.count if result.response else 0,
            metadata=result.to_metadata(),
        )
        return result

    def _rewrite_and_retrieve(
        self,
        context: OrchestrationContext,
        run_id: str,
        *,
        reason: str,
    ) -> bool:
        if not self._can_rewrite_retrieval(context):
            return False
        assert context.task_plan is not None
        assert self.query_rewriter is not None
        emit_event(
            "query_rewrite_started",
            run_id=run_id,
            reason=reason,
            original_query=context.retrieval_query or context.request.question,
        )
        rewrite = self.query_rewriter.rewrite(context.request, context.task_plan, reason)
        context.retrieval_rewrite_attempts += 1
        context.query_rewrites.append(rewrite)
        context.retrieval_query = rewrite.rewritten_query
        emit_event(
            "query_rewrite_finished",
            run_id=run_id,
            **rewrite.to_dict(),
        )
        retried = self._retrieve(context, run_id, rewrite.rewritten_query)
        if context.preretrieval is None:
            context.preretrieval = retried
        else:
            context.preretrieval = merge_preretrieval_results(context.preretrieval, retried)
        emit_event(
            "retrieval_retry_finished",
            run_id=run_id,
            reason=reason,
            query=rewrite.rewritten_query,
            count=context.preretrieval.response.count if context.preretrieval.response else 0,
        )
        return True

    def _can_rewrite_retrieval(self, context: OrchestrationContext) -> bool:
        if context.retrieval_rewrite_attempts >= self.max_retrieval_rewrites:
            return False
        if not context.task_plan or not context.task_plan.intent.requires_retrieval:
            return False
        return context.task_plan.intent.task_type in {
            TaskType.PAPER_EXPLANATION,
            TaskType.STRUCTURE_ANALYSIS,
            TaskType.FIGURE_TABLE_EXPLANATION,
            TaskType.INNOVATION_COMPARISON,
        }

    @staticmethod
    def _retrieval_is_empty(result: PreRetrievalResult) -> bool:
        return bool(result.enabled and (not result.response or not result.response.results))

    def _save_turn(self, request: AgentRequest, answer: str) -> None:
        if not self.memory_store or not request.conversation_id:
            return
        self.memory_store.append(request.conversation_id, user_message(request.question))
        self.memory_store.append(request.conversation_id, assistant_message(answer))

    def _orchestration_metadata(self, context: OrchestrationContext) -> dict:
        return {
            "state": context.state.value,
            "verification_attempts": context.verification_attempts,
            "retrieval_rewrite_attempts": context.retrieval_rewrite_attempts,
            "retrieval_query": context.retrieval_query,
            "query_rewrites": [item.to_dict() for item in context.query_rewrites],
            "active_tools": list(context.active_tool_names),
            "transitions": [item.to_dict() for item in context.transitions],
        }


def _invoke_agent(
    agent,
    payload: dict,
    max_turns: int,
    token_sink: Callable[[str], None] | None = None,
):
    if max_turns < 1:
        raise ValueError("max_turns must be at least 1.")
    if token_sink is not None and callable(getattr(agent, "stream", None)):
        latest_state = None
        for mode, data in agent.stream(
            payload,
            config={"recursion_limit": max_turns},
            stream_mode=["messages", "values"],
        ):
            if mode == "messages":
                message, _metadata = data
                text = _stream_message_text(message)
                if text:
                    token_sink(text)
            elif mode == "values" and isinstance(data, dict):
                latest_state = data
        if latest_state is not None:
            return latest_state
    try:
        return agent.invoke(payload, config={"recursion_limit": max_turns})
    except TypeError:
        return agent.invoke(payload)


def _stream_message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")
