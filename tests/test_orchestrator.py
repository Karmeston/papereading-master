from pathlib import Path
from types import SimpleNamespace

from finals_agent.agent.query_rewrite import QueryRewrite
from finals_agent.agent.orchestrator import _invoke_agent
from finals_agent.agent.runner import run_agent
from finals_agent.agent.tool_registry import DEFAULT_TOOL_SPECS, LIST_PAPERS, ToolRegistry
from finals_agent.core.schemas import (
    AgentRequest,
    DocumentType,
    SearchRequest,
    SearchResponse,
    SearchResult,
)


class CitationRetriever:
    def __init__(self):
        self.queries = []
        self.result = SearchResult(
            document_id="doc-1",
            title="Target Paper",
            document_type=DocumentType.PAPER,
            course="nlp",
            path=Path("target.md"),
            snippet="The method retrieves evidence before generation.",
            score=1.0,
            chunk_id="doc-1-0",
            page=2,
            section="2 Method",
        )

    def search(self, request: SearchRequest):
        self.queries.append(request.query)
        return SearchResponse(
            request=request,
            results=(self.result,),
            metadata={"count": 1, "retriever": "CitationRetriever"},
        )


class RevisionAgent:
    def __init__(self, citation: str):
        self.citation = citation
        self.payloads = []

    def invoke(self, payload, config=None):
        self.payloads.append(payload)
        answer = (
            "The method retrieves evidence before generation."
            if len(self.payloads) == 1
            else f"The method retrieves evidence before generation. {self.citation}"
        )
        return {
            "messages": [
                SimpleNamespace(content="user"),
                SimpleNamespace(content=answer),
            ]
        }


class StaticRewriter:
    def __init__(self, rewritten_query="rewritten evidence query"):
        self.rewritten_query = rewritten_query
        self.calls = []

    def rewrite(self, request, task_plan, reason):
        self.calls.append((request.question, reason))
        return QueryRewrite(
            original_query=request.question,
            rewritten_query=self.rewritten_query,
            reason=reason,
            strategy="test",
        )


def test_orchestrator_reexecutes_when_verify_finds_missing_citation():
    retriever = CitationRetriever()
    citation = retriever.result.to_dict()["citation"]
    agent = RevisionAgent(citation)
    rewriter = StaticRewriter("target method supporting evidence")

    result = run_agent(
        AgentRequest(question="summarize this paper"),
        agent=agent,
        retriever=retriever,
        query_rewriter=rewriter,
        max_verification_retries=1,
    )

    assert len(agent.payloads) == 2
    assert citation in result.answer
    assert result.metadata["citation_check"]["passed"] is True
    assert result.metadata["orchestrator"]["verification_attempts"] == 1
    assert result.metadata["orchestrator"]["retrieval_rewrite_attempts"] == 1
    assert retriever.queries == ["summarize this paper", "target method supporting evidence"]
    assert rewriter.calls == [("summarize this paper", "citation_verification_failed")]
    assert [item["state"] for item in result.metadata["orchestrator"]["transitions"]] == [
        "execute",
        "verify",
        "execute",
        "verify",
        "complete",
    ]
    assert "Retain at least one exact local citation" in agent.payloads[1]["messages"][-1]["content"]


class EmptyThenEvidenceRetriever:
    def __init__(self):
        self.queries = []
        self.result = CitationRetriever().result

    def search(self, request: SearchRequest):
        self.queries.append(request.query)
        results = () if len(self.queries) == 1 else (self.result,)
        return SearchResponse(
            request=request,
            results=results,
            metadata={"count": len(results), "retriever": "EmptyThenEvidenceRetriever"},
        )


class EvidenceAwareAgent:
    def __init__(self, citation):
        self.citation = citation
        self.payload = None

    def invoke(self, payload, config=None):
        self.payload = payload
        return {
            "messages": [
                SimpleNamespace(content=f"Grounded answer. {self.citation}"),
            ]
        }


def test_orchestrator_rewrites_empty_retrieval_before_answering():
    retriever = EmptyThenEvidenceRetriever()
    citation = retriever.result.to_dict()["citation"]
    agent = EvidenceAwareAgent(citation)
    rewriter = StaticRewriter("speculative decoding acceptance experiment results")

    result = run_agent(
        AgentRequest(question="解释一下这篇论文的方法为什么有效"),
        agent=agent,
        retriever=retriever,
        query_rewriter=rewriter,
    )

    assert retriever.queries == [
        "解释一下这篇论文的方法为什么有效",
        "speculative decoding acceptance experiment results",
    ]
    assert rewriter.calls == [("解释一下这篇论文的方法为什么有效", "empty_retrieval")]
    assert citation in agent.payload["messages"][0]["content"]
    assert result.metadata["citation_check"]["passed"] is True
    assert result.metadata["query_rewrites"][0]["reason"] == "empty_retrieval"


class EmptyThenAnswerAgent:
    def __init__(self):
        self.calls = 0

    def invoke(self, payload, config=None):
        self.calls += 1
        answer = "" if self.calls == 1 else "A complete answer."
        return {"messages": [SimpleNamespace(content=answer)]}


class EmptyRetriever:
    def search(self, request: SearchRequest):
        return SearchResponse(request=request, results=(), metadata={"count": 0})


def test_orchestrator_reexecutes_empty_answer():
    agent = EmptyThenAnswerAgent()

    result = run_agent(
        AgentRequest(question="hello"),
        agent=agent,
        retriever=EmptyRetriever(),
        max_verification_retries=1,
    )

    assert agent.calls == 2
    assert result.answer == "A complete answer."
    assert result.metadata["orchestrator"]["verification_attempts"] == 1


def test_orchestrator_builds_agent_with_plan_selected_tools():
    registry = ToolRegistry()
    registry.register_many(SimpleNamespace(name=spec.name) for spec in DEFAULT_TOOL_SPECS)
    captured = {}

    def agent_factory(**kwargs):
        captured.update(kwargs)
        return RevisionAgent("unused")

    from finals_agent.agent.orchestrator import TaskOrchestrator

    result = TaskOrchestrator(
        agent_factory=agent_factory,
        tool_registry=registry,
        retriever=EmptyRetriever(),
        max_verification_retries=0,
    ).run(AgentRequest(question="list uploaded papers"))

    assert captured["tool_names"] == (LIST_PAPERS,)
    assert result.metadata["orchestrator"]["active_tools"] == [LIST_PAPERS]
    assert [item["name"] for item in result.metadata["tool_registry"]] == [LIST_PAPERS]


def test_invoke_agent_streams_model_tokens_and_returns_final_state():
    class StreamingAgent:
        def stream(self, payload, config, stream_mode):
            assert config == {"recursion_limit": 12}
            assert stream_mode == ["messages", "values"]
            yield "messages", (SimpleNamespace(content="first "), {})
            yield "messages", (SimpleNamespace(content=[{"text": "second"}]), {})
            yield "values", {"messages": [SimpleNamespace(content="first second")]}

    tokens = []
    result = _invoke_agent(StreamingAgent(), {"messages": []}, 12, token_sink=tokens.append)

    assert tokens == ["first ", "second"]
    assert result["messages"][-1].content == "first second"
