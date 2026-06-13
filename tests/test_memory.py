from finals_agent.persistence.memory import (
    InMemoryStore,
    JsonMemoryStore,
    assistant_message,
    conversation_summary,
    new_conversation_id,
    user_message,
)
from finals_agent.persistence.storage import JsonFileStorage


def test_in_memory_store_appends_messages():
    store = InMemoryStore()

    store.append("conv-1", user_message("hello"))
    memory = store.append("conv-1", assistant_message("hi"))

    assert memory.conversation_id == "conv-1"
    assert [message.to_langchain_message() for message in memory.messages] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_in_memory_store_clear_removes_conversation():
    store = InMemoryStore()
    store.append("conv-1", user_message("hello"))

    store.clear("conv-1")

    assert store.get("conv-1").messages == ()


def test_new_conversation_id_is_short_string():
    conversation_id = new_conversation_id()

    assert isinstance(conversation_id, str)
    assert len(conversation_id) == 12


def test_json_memory_store_persists_messages(tmp_path):
    storage = JsonFileStorage(tmp_path / "memory.json")
    store = JsonMemoryStore(storage=storage)

    store.append("conv-1", user_message("hello"))
    store.append("conv-1", assistant_message("hi"))

    reloaded = JsonMemoryStore(storage=storage)
    memory = reloaded.get("conv-1")

    assert [message.to_langchain_message() for message in memory.messages] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_json_memory_store_clear_removes_conversation(tmp_path):
    storage = JsonFileStorage(tmp_path / "memory.json")
    store = JsonMemoryStore(storage=storage)
    store.append("conv-1", user_message("hello"))

    store.clear("conv-1")

    assert store.get("conv-1").messages == ()
    assert storage.read() == {}


def test_memory_store_maintains_rolling_summary():
    store = InMemoryStore(summary_retain_recent=2)

    for index in range(5):
        store.append("conv-1", user_message(f"question {index}"))

    memory = store.get("conv-1")

    assert conversation_summary(memory)
    assert "question 0" in conversation_summary(memory)
    assert memory.metadata["summarized_message_count"] == 3
    assert len(memory.messages) == 5
