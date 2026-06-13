from finals_agent.data.embeddings import HashEmbeddingProvider
from finals_agent.persistence.memory import InMemoryStore, assistant_message, user_message
from finals_agent.persistence.memory_retrieval import retrieve_relevant_memory


def test_retrieve_relevant_memory_uses_lexical_fallback_for_old_messages():
    store = InMemoryStore()
    store.append("conv-1", user_message("We discussed bayesian optimization acquisition functions."))
    store.append("conv-1", assistant_message("Expected improvement balances exploration and exploitation."))
    store.append("conv-1", user_message("recent unrelated question"))
    store.append("conv-1", assistant_message("recent unrelated answer"))

    result = retrieve_relevant_memory(
        store.get("conv-1"),
        query="bayesian acquisition",
        limit=2,
        exclude_recent=2,
    )

    assert result.count >= 1
    assert result.metadata["method"] == "lexical"
    assert result.hits[0].message_index in {0, 1}
    assert "bayesian" in result.hits[0].content.lower() or "improvement" in result.hits[0].content.lower()


def test_retrieve_relevant_memory_uses_embedding_provider_when_available():
    store = InMemoryStore()
    store.append("conv-1", user_message("retrieval augmented generation"))
    store.append("conv-1", assistant_message("old answer about retrieval"))
    store.append("conv-1", user_message("recent unrelated question"))

    result = retrieve_relevant_memory(
        store.get("conv-1"),
        query="retrieval generation",
        limit=1,
        exclude_recent=1,
        embedding_provider=HashEmbeddingProvider(dimensions=32),
    )

    assert result.count == 1
    assert result.metadata["method"] == "embedding"
    assert result.metadata["embedding_available"] is True
    assert result.hits[0].method == "embedding"
