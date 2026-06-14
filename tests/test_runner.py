from types import SimpleNamespace
from pathlib import Path

from finals_agent.agent.runner import ask_agent, run_agent, stream_agent_events
from finals_agent.core.schemas import AgentRequest, CourseContext, DocumentType, SearchRequest, SearchResponse, SearchResult
from finals_agent.persistence.memory import InMemoryStore, assistant_message, user_message


class FakeAgent:
    def __init__(self):
        self.payload = None

    def invoke(self, payload):
        self.payload = payload
        return {
            "messages": [
                SimpleNamespace(content="user message"),
                SimpleNamespace(content="agent answer"),
            ]
        }


class ConfigAwareFakeAgent(FakeAgent):
    def __init__(self):
        super().__init__()
        self.config = None

    def invoke(self, payload, config=None):
        self.payload = payload
        self.config = config
        return {
            "messages": [
                SimpleNamespace(content="user message"),
                SimpleNamespace(content="agent answer"),
            ]
        }


class FakeRetriever:
    def search(self, request: SearchRequest):
        return SearchResponse(request=request, results=(), metadata={"count": 0, "retriever": "FakeRetriever"})


class FakeCitationRetriever:
    def search(self, request: SearchRequest):
        result = SearchResult(
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
        return SearchResponse(request=request, results=(result,), metadata={"count": 1, "retriever": "FakeCitationRetriever"})


def test_run_agent_uses_request_message_protocol(monkeypatch):
    fake_agent = FakeAgent()

    def fake_build_agent(**kwargs):
        return fake_agent

    monkeypatch.setattr("finals_agent.agent.runner.build_agent", fake_build_agent)

    result = run_agent(
        AgentRequest(
            question="hello",
            course_context=CourseContext(course="calculus"),
            conversation_id="conv-1",
        ),
        model=SimpleNamespace(),
    )

    assert fake_agent.payload == {"messages": [{"role": "user", "content": "hello"}]}
    assert result.answer == "agent answer"
    assert result.conversation_id == "conv-1"
    assert result.metadata["course_context"] == "field=calculus, mode=normal"
    assert result.metadata["task_plan"]["intent"]["task_type"] == "general_chat"
    assert result.metadata["message_count"] == 2
    assert result.metadata["trace"]["status"] == "success"
    assert result.metadata["trace"]["duration_ms"] >= 0
    assert result.metadata["trace"]["metadata"]["message_count"] == 2


def test_run_agent_includes_and_updates_memory():
    fake_agent = FakeAgent()
    memory = InMemoryStore()
    memory.append("conv-1", user_message("previous question"))
    memory.append("conv-1", assistant_message("previous answer"))

    result = run_agent(
        AgentRequest(question="new question", conversation_id="conv-1"),
        agent=fake_agent,
        memory_store=memory,
    )

    assert fake_agent.payload == {
        "messages": [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"},
            {"role": "user", "content": "new question"},
        ]
    }
    assert result.metadata["input_message_count"] == 3
    assert result.metadata["context"]["message_count"] == 3
    assert result.metadata["memory_enabled"] is True
    stored = memory.get("conv-1")
    assert [message.content for message in stored.messages] == [
        "previous question",
        "previous answer",
        "new question",
        "agent answer",
    ]


def test_run_agent_injects_preretrieval_context_for_retrieval_task():
    fake_agent = FakeAgent()

    result = run_agent(
        AgentRequest(question="search limit materials", conversation_id="conv-1"),
        agent=fake_agent,
        retriever=FakeRetriever(),
    )

    assert fake_agent.payload["messages"][0]["role"] == "system"
    assert "预检索结果" in fake_agent.payload["messages"][0]["content"]
    assert fake_agent.payload["messages"][1] == {"role": "user", "content": "search limit materials"}
    assert result.metadata["preretrieval"]["enabled"] is True
    assert result.metadata["preretrieval"]["count"] == 0
    assert result.metadata["context"]["blocks"][0]["name"] == "preretrieval"


def test_run_agent_adds_warning_when_local_citations_are_missing():
    fake_agent = FakeAgent()

    result = run_agent(
        AgentRequest(question="summarize this paper", conversation_id="conv-1"),
        agent=fake_agent,
        retriever=FakeCitationRetriever(),
    )

    assert result.metadata["citation_check"]["required"] is True
    assert result.metadata["citation_check"]["passed"] is False
    assert "[引用检查]" in result.answer


def test_run_agent_passes_recursion_limit_to_agent():
    fake_agent = ConfigAwareFakeAgent()

    result = run_agent(
        AgentRequest(question="hello"),
        agent=fake_agent,
        retriever=FakeRetriever(),
        max_turns=12,
    )

    assert fake_agent.config == {"recursion_limit": 12}
    assert result.metadata["max_turns"] == 12


def test_ask_agent_returns_answer_text(monkeypatch):
    def fake_run_agent(
        request,
        repository=None,
        model=None,
        runtime=None,
        agent=None,
        memory_store=None,
        planner=None,
        retriever=None,
        run_recorder=None,
    ):
        return SimpleNamespace(answer=f"answer for {request.question}")

    monkeypatch.setattr("finals_agent.agent.runner.run_agent", fake_run_agent)

    assert ask_agent("hello") == "answer for hello"


def test_stream_agent_events_yields_progress_and_final_answer():
    fake_agent = FakeAgent()

    events = list(
        stream_agent_events(
            AgentRequest(question="hello", conversation_id="conv-1"),
            agent=fake_agent,
            retriever=FakeRetriever(),
        )
    )

    names = [event["event"] for event in events]
    assert names[:2] == ["run_started", "planning_finished"]
    assert "context_assembled" in names
    assert "agent_started" in names
    assert "agent_finished" in names
    assert names[-2] == "run_finished"
    assert events[-2]["answer"] == "agent answer"
    assert events[-1] == {"event": "stream_closed", "status": "success"}
