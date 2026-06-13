from finals_agent.agent.context import ContextAssembler
from finals_agent.persistence.memory import InMemoryStore, assistant_message, user_message
from finals_agent.agent.preretrieval import PreRetrievalResult
from finals_agent.core.schemas import AgentRequest


def test_context_assembler_includes_request_only_without_context():
    bundle = ContextAssembler().assemble(AgentRequest(question="hello"))

    assert bundle.messages == ({"role": "user", "content": "hello"},)
    assert bundle.to_metadata()["blocks"][0]["name"] == "request"


def test_context_assembler_orders_preretrieval_memory_then_request():
    memory = InMemoryStore()
    memory.append("conv-1", user_message("old question"))
    memory.append("conv-1", assistant_message("old answer"))
    preretrieval = PreRetrievalResult(
        enabled=True,
        context_message={"role": "system", "content": "retrieved context"},
    )

    bundle = ContextAssembler().assemble(
        AgentRequest(question="new question", conversation_id="conv-1"),
        memory_store=memory,
        preretrieval=preretrieval,
    )

    assert bundle.messages == (
        {"role": "system", "content": "retrieved context"},
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "new question"},
    )
    assert [block["name"] for block in bundle.to_metadata()["blocks"]] == [
        "preretrieval",
        "memory",
        "request",
    ]


def test_context_assembler_skips_empty_memory_block():
    memory = InMemoryStore()

    bundle = ContextAssembler().assemble(
        AgentRequest(question="hello", conversation_id="conv-1"),
        memory_store=memory,
    )

    assert bundle.messages == ({"role": "user", "content": "hello"},)
    assert [block["name"] for block in bundle.to_metadata()["blocks"]] == ["request"]


def test_context_assembler_limits_memory_window():
    memory = InMemoryStore()
    for index in range(5):
        memory.append("conv-1", user_message(f"question {index}"))

    bundle = ContextAssembler(max_memory_messages=2).assemble(
        AgentRequest(question="current", conversation_id="conv-1"),
        memory_store=memory,
    )

    assert bundle.messages == (
        {"role": "user", "content": "question 3"},
        {"role": "user", "content": "question 4"},
        {"role": "user", "content": "current"},
    )
    memory_block = bundle.to_metadata()["blocks"][0]
    assert memory_block["metadata"]["message_count"] == 5
    assert memory_block["metadata"]["included_message_count"] == 2
    assert memory_block["metadata"]["truncated"] is True


def test_context_assembler_includes_memory_summary():
    memory = InMemoryStore(summary_retain_recent=2)
    for index in range(5):
        memory.append("conv-1", user_message(f"older topic {index}"))

    bundle = ContextAssembler(max_memory_messages=2, max_relevant_memory=0).assemble(
        AgentRequest(question="current", conversation_id="conv-1"),
        memory_store=memory,
    )

    assert [block["name"] for block in bundle.to_metadata()["blocks"]] == [
        "memory_summary",
        "memory",
        "request",
    ]
    assert "对话历史摘要" in bundle.messages[0]["content"]
    assert "older topic 0" in bundle.messages[0]["content"]
    assert all(message["content"] != "older topic 0" for message in bundle.messages[1:])


def test_context_assembler_includes_relevant_memory_before_recent_window():
    memory = InMemoryStore()
    memory.append("conv-1", user_message("We discussed bayesian optimization earlier."))
    memory.append("conv-1", assistant_message("Acquisition functions were the key point."))
    memory.append("conv-1", user_message("recent unrelated"))
    memory.append("conv-1", assistant_message("recent answer"))

    bundle = ContextAssembler(max_memory_messages=2, max_relevant_memory=2).assemble(
        AgentRequest(question="bayesian acquisition", conversation_id="conv-1"),
        memory_store=memory,
    )

    assert [block["name"] for block in bundle.to_metadata()["blocks"]] == [
        "relevant_memory",
        "memory",
        "request",
    ]
    assert "相关历史对话片段" in bundle.messages[0]["content"]
    assert "bayesian" in bundle.messages[0]["content"].lower()


def test_context_assembler_disables_relevant_memory_by_default():
    memory = InMemoryStore()
    memory.append("conv-1", user_message("We discussed bayesian optimization earlier."))
    memory.append("conv-1", assistant_message("Acquisition functions were the key point."))
    memory.append("conv-1", user_message("recent unrelated"))
    memory.append("conv-1", assistant_message("recent answer"))

    bundle = ContextAssembler(max_memory_messages=2).assemble(
        AgentRequest(question="bayesian acquisition", conversation_id="conv-1"),
        memory_store=memory,
    )

    assert [block["name"] for block in bundle.to_metadata()["blocks"]] == [
        "memory",
        "request",
    ]
    assert all("bayesian optimization" not in message["content"].lower() for message in bundle.messages)


def test_context_assembler_truncates_recent_memory_by_message_and_total_chars():
    memory = InMemoryStore()
    memory.append("conv-1", user_message("a" * 100))
    memory.append("conv-1", assistant_message("b" * 100))
    memory.append("conv-1", user_message("c" * 100))

    bundle = ContextAssembler(
        max_memory_messages=3,
        max_relevant_memory=0,
        max_memory_message_chars=40,
        max_memory_total_chars=90,
    ).assemble(
        AgentRequest(question="current", conversation_id="conv-1"),
        memory_store=memory,
    )

    memory_messages = bundle.messages[:-1]
    assert len(memory_messages) <= 3
    assert sum(len(message["content"]) for message in memory_messages) <= 90
    assert all(len(message["content"]) <= 40 for message in memory_messages)
    metadata = bundle.to_metadata()["blocks"][0]["metadata"]
    assert metadata["truncated"] is True
    assert metadata["truncated_by_chars"] is True
