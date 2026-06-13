from __future__ import annotations

from dataclasses import dataclass

from finals_agent.persistence.memory import MemoryStore
from finals_agent.persistence.memory import conversation_summary
from finals_agent.persistence.memory_retrieval import MemoryRetrievalResult, retrieve_relevant_memory
from finals_agent.agent.preretrieval import PreRetrievalResult
from finals_agent.core.schemas import AgentRequest, ConversationMemory
from finals_agent.data.embeddings import EmbeddingProvider


@dataclass(frozen=True)
class ContextBlock:
    name: str
    messages: tuple[dict[str, str], ...]
    metadata: dict

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "message_count": self.message_count,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ContextBundle:
    messages: tuple[dict[str, str], ...]
    blocks: tuple[ContextBlock, ...]

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def to_metadata(self) -> dict:
        return {
            "message_count": self.message_count,
            "blocks": [block.to_dict() for block in self.blocks],
        }


class ContextAssembler:
    def __init__(
        self,
        max_memory_messages: int = 12,
        max_relevant_memory: int = 0,
        max_memory_message_chars: int = 1200,
        max_memory_total_chars: int = 6000,
    ):
        self.max_memory_messages = max_memory_messages
        self.max_relevant_memory = max_relevant_memory
        self.max_memory_message_chars = max_memory_message_chars
        self.max_memory_total_chars = max_memory_total_chars

    def assemble(
        self,
        request: AgentRequest,
        memory_store: MemoryStore | None = None,
        preretrieval: PreRetrievalResult | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> ContextBundle:
        blocks = []

        preretrieval_block = self._preretrieval_block(preretrieval)
        if preretrieval_block:
            blocks.append(preretrieval_block)

        memory = self._load_memory(request, memory_store)
        summary_block = self._summary_block(memory)
        if summary_block:
            blocks.append(summary_block)

        relevant_block = self._relevant_memory_block(
            request=request,
            memory=memory,
            embedding_provider=embedding_provider,
        )
        if relevant_block:
            blocks.append(relevant_block)

        memory_block = self._memory_block(request, memory_store)
        if memory_block:
            blocks.append(memory_block)

        blocks.append(self._request_block(request))

        messages = tuple(message for block in blocks for message in block.messages)
        return ContextBundle(messages=messages, blocks=tuple(blocks))

    def _preretrieval_block(self, preretrieval: PreRetrievalResult | None) -> ContextBlock | None:
        if not preretrieval or not preretrieval.context_message:
            return None
        return ContextBlock(
            name="preretrieval",
            messages=(preretrieval.context_message,),
            metadata=preretrieval.to_metadata(),
        )

    def _load_memory(self, request: AgentRequest, memory_store: MemoryStore | None) -> ConversationMemory | None:
        if not memory_store or not request.conversation_id:
            return None
        return memory_store.get(request.conversation_id)

    def _summary_block(self, memory: ConversationMemory | None) -> ContextBlock | None:
        if not memory:
            return None
        summary = conversation_summary(memory)
        if not summary:
            return None
        summarized_count = (memory.metadata or {}).get("summarized_message_count", 0)
        return ContextBlock(
            name="memory_summary",
            messages=(
                {
                    "role": "system",
                    "content": f"对话历史摘要（用于保留较早上下文，不替代当前论文证据）：\n{summary}",
                },
            ),
            metadata={
                "conversation_id": memory.conversation_id,
                "summarized_message_count": summarized_count,
                "summary_length": len(summary),
            },
        )

    def _relevant_memory_block(
        self,
        request: AgentRequest,
        memory: ConversationMemory | None,
        embedding_provider: EmbeddingProvider | None,
    ) -> ContextBlock | None:
        if not memory or self.max_relevant_memory < 1:
            return None
        result = retrieve_relevant_memory(
            memory=memory,
            query=request.question,
            limit=self.max_relevant_memory,
            exclude_recent=self.max_memory_messages,
            embedding_provider=embedding_provider,
        )
        if not result.hits:
            return None
        return ContextBlock(
            name="relevant_memory",
            messages=(self._relevant_memory_message(result),),
            metadata=result.to_metadata(),
        )

    def _relevant_memory_message(self, result: MemoryRetrievalResult) -> dict[str, str]:
        lines = ["相关历史对话片段（仅用于保持对话连续性；论文事实仍以检索证据为准）："]
        for hit in result.hits:
            content = " ".join(hit.content.split())
            lines.append(f"- message={hit.message_index + 1} role={hit.role} score={hit.score:.3f}: {content}")
        return {"role": "system", "content": "\n".join(lines)}

    def _memory_block(self, request: AgentRequest, memory_store: MemoryStore | None) -> ContextBlock | None:
        memory = self._load_memory(request, memory_store)
        if not memory:
            return None
        if not memory.messages:
            return None
        messages, memory_metadata = self._recent_memory_messages(memory)
        return ContextBlock(
            name="memory",
            messages=messages,
            metadata={
                "conversation_id": request.conversation_id,
                "message_count": len(memory.messages),
                **memory_metadata,
            },
        )

    def _request_block(self, request: AgentRequest) -> ContextBlock:
        return ContextBlock(
            name="request",
            messages=tuple(request.to_messages()),
            metadata={"conversation_id": request.conversation_id},
        )

    def _recent_memory_messages(self, memory: ConversationMemory) -> tuple[tuple[dict[str, str], ...], dict]:
        if self.max_memory_messages < 1 or self.max_memory_total_chars < 1:
            return (), {
                "included_message_count": 0,
                "included_chars": 0,
                "truncated": bool(memory.messages),
                "truncation_reason": "memory_disabled_or_zero_budget",
            }

        selected = []
        total_chars = 0
        truncated_by_chars = False
        for message in reversed(memory.messages[-self.max_memory_messages :]):
            content = _truncate_text(message.content, self.max_memory_message_chars)
            if content != message.content:
                truncated_by_chars = True
            if total_chars + len(content) > self.max_memory_total_chars:
                remaining = self.max_memory_total_chars - total_chars
                if remaining <= 0:
                    truncated_by_chars = True
                    break
                content = _truncate_text(content, remaining)
                truncated_by_chars = True
            selected.append({"role": message.role.value, "content": content})
            total_chars += len(content)
            if total_chars >= self.max_memory_total_chars:
                break

        selected.reverse()
        truncated_by_count = len(selected) < len(memory.messages)
        return tuple(selected), {
            "included_message_count": len(selected),
            "included_chars": total_chars,
            "max_message_chars": self.max_memory_message_chars,
            "max_total_chars": self.max_memory_total_chars,
            "truncated": truncated_by_count or truncated_by_chars,
            "truncated_by_count": truncated_by_count,
            "truncated_by_chars": truncated_by_chars,
        }


def _truncate_text(text: str, limit: int) -> str:
    if limit < 1:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 20:
        return text[:limit]
    return text[: limit - 18].rstrip() + "\n...[truncated]"
