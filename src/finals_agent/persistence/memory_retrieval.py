from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import re

from finals_agent.core.schemas import ConversationMemory, MemoryMessage
from finals_agent.data.embeddings import DisabledEmbeddingProvider, EmbeddingProvider, cosine


@dataclass(frozen=True)
class MemoryHit:
    message_index: int
    role: str
    content: str
    score: float
    method: str

    def to_dict(self) -> dict:
        return {
            "message_index": self.message_index,
            "role": self.role,
            "content": self.content,
            "score": self.score,
            "method": self.method,
        }


@dataclass(frozen=True)
class MemoryRetrievalResult:
    hits: tuple[MemoryHit, ...]
    metadata: dict

    @property
    def count(self) -> int:
        return len(self.hits)

    def to_metadata(self) -> dict:
        return {
            **self.metadata,
            "count": self.count,
            "hits": [
                {
                    "message_index": hit.message_index,
                    "role": hit.role,
                    "score": hit.score,
                    "method": hit.method,
                }
                for hit in self.hits
            ],
        }


def retrieve_relevant_memory(
    memory: ConversationMemory,
    query: str,
    limit: int = 4,
    exclude_recent: int = 12,
    embedding_provider: EmbeddingProvider | None = None,
) -> MemoryRetrievalResult:
    if limit < 1 or not query.strip() or not memory.messages:
        return MemoryRetrievalResult(hits=(), metadata={"enabled": False, "reason": "empty_query_or_memory"})

    candidates = _candidate_messages(memory.messages, exclude_recent=exclude_recent)
    if not candidates:
        return MemoryRetrievalResult(
            hits=(),
            metadata={
                "enabled": True,
                "method": "none",
                "candidate_count": 0,
                "embedding_available": False,
            },
        )

    provider = embedding_provider or DisabledEmbeddingProvider()
    if provider.available:
        hits = _embedding_hits(query, candidates, provider)
        method = "embedding"
        embedding_available = True
        embedding_model = provider.model_name
    else:
        hits = _lexical_hits(query, candidates)
        method = "lexical"
        embedding_available = False
        embedding_model = provider.model_name

    hits = tuple(sorted((hit for hit in hits if hit.score > 0), key=lambda item: item.score, reverse=True)[:limit])
    return MemoryRetrievalResult(
        hits=hits,
        metadata={
            "enabled": True,
            "method": method,
            "candidate_count": len(candidates),
            "limit": limit,
            "exclude_recent": exclude_recent,
            "embedding_available": embedding_available,
            "embedding_model": embedding_model,
        },
    )


def _candidate_messages(messages: tuple[MemoryMessage, ...], exclude_recent: int) -> list[tuple[int, MemoryMessage]]:
    cutoff = max(0, len(messages) - max(exclude_recent, 0))
    return [
        (index, message)
        for index, message in enumerate(messages[:cutoff])
        if message.content.strip()
    ]


def _embedding_hits(
    query: str,
    candidates: list[tuple[int, MemoryMessage]],
    provider: EmbeddingProvider,
) -> list[MemoryHit]:
    vectors = provider.embed_texts([query, *[message.content for _, message in candidates]])
    if len(vectors) != len(candidates) + 1:
        return []
    query_vector = vectors[0]
    hits = []
    for (index, message), vector in zip(candidates, vectors[1:], strict=True):
        hits.append(
            MemoryHit(
                message_index=index,
                role=message.role.value,
                content=message.content,
                score=cosine(query_vector, vector),
                method="embedding",
            )
        )
    return hits


def _lexical_hits(query: str, candidates: list[tuple[int, MemoryMessage]]) -> list[MemoryHit]:
    query_vector = _vectorize(query)
    hits = []
    for index, message in candidates:
        score = _cosine(query_vector, _vectorize(message.content))
        hits.append(
            MemoryHit(
                message_index=index,
                role=message.role.value,
                content=message.content,
                score=score,
                method="lexical",
            )
        )
    return hits


TOKEN_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+", re.I)


def _vectorize(text: str) -> Counter[str]:
    tokens = TOKEN_RE.findall(text.lower())
    vector: Counter[str] = Counter(tokens)
    for token in tokens:
        if len(token) >= 4 and token.isascii():
            vector.update(token[index : index + 3] for index in range(len(token) - 2))
        elif len(token) >= 2:
            vector.update(token[index : index + 2] for index in range(len(token) - 1))
    return vector


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    dot = sum(left[key] * right[key] for key in common)
    if dot == 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
