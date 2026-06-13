from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from finals_agent.core.config import MEMORY_PATH
from finals_agent.core.schemas import ConversationMemory, MemoryMessage, MessageRole
from finals_agent.persistence.storage import JsonFileStorage, StorageBackend


SUMMARY_KEY = "conversation_summary"
SUMMARIZED_COUNT_KEY = "summarized_message_count"
DEFAULT_SUMMARY_RETAIN_RECENT = 12
DEFAULT_SUMMARY_MAX_CHARS = 2000


class MemoryStore(ABC):
    @abstractmethod
    def get(self, conversation_id: str) -> ConversationMemory:
        raise NotImplementedError

    @abstractmethod
    def append(self, conversation_id: str, message: MemoryMessage) -> ConversationMemory:
        raise NotImplementedError

    @abstractmethod
    def clear(self, conversation_id: str) -> None:
        raise NotImplementedError


class InMemoryStore(MemoryStore):
    def __init__(
        self,
        summary_retain_recent: int = DEFAULT_SUMMARY_RETAIN_RECENT,
        summary_max_chars: int = DEFAULT_SUMMARY_MAX_CHARS,
    ):
        self._conversations: dict[str, ConversationMemory] = {}
        self.summary_retain_recent = summary_retain_recent
        self.summary_max_chars = summary_max_chars

    def get(self, conversation_id: str) -> ConversationMemory:
        return self._conversations.get(conversation_id) or ConversationMemory(conversation_id=conversation_id)

    def append(self, conversation_id: str, message: MemoryMessage) -> ConversationMemory:
        memory = self.get(conversation_id)
        updated = ConversationMemory(
            conversation_id=conversation_id,
            messages=(*memory.messages, message),
            metadata=memory.metadata,
        )
        updated = compact_memory(
            updated,
            retain_recent=self.summary_retain_recent,
            max_summary_chars=self.summary_max_chars,
        )
        self._conversations[conversation_id] = updated
        return updated

    def clear(self, conversation_id: str) -> None:
        self._conversations.pop(conversation_id, None)


class JsonMemoryStore(MemoryStore):
    def __init__(
        self,
        storage: StorageBackend | None = None,
        summary_retain_recent: int = DEFAULT_SUMMARY_RETAIN_RECENT,
        summary_max_chars: int = DEFAULT_SUMMARY_MAX_CHARS,
    ):
        self.storage = storage or JsonFileStorage(MEMORY_PATH)
        self.summary_retain_recent = summary_retain_recent
        self.summary_max_chars = summary_max_chars

    def get(self, conversation_id: str) -> ConversationMemory:
        payload = self.storage.read()
        conversations = payload.get("conversations", {})
        if conversation_id not in conversations:
            return ConversationMemory(conversation_id=conversation_id)
        return ConversationMemory.from_dict(conversations[conversation_id])

    def append(self, conversation_id: str, message: MemoryMessage) -> ConversationMemory:
        def updater(payload):
            conversations = payload.setdefault("conversations", {})
            memory = (
                ConversationMemory.from_dict(conversations[conversation_id])
                if conversation_id in conversations
                else ConversationMemory(conversation_id=conversation_id)
            )
            updated = ConversationMemory(
                conversation_id=conversation_id,
                messages=(*memory.messages, message),
                metadata=memory.metadata,
            )
            updated = compact_memory(
                updated,
                retain_recent=self.summary_retain_recent,
                max_summary_chars=self.summary_max_chars,
            )
            conversations[conversation_id] = updated.to_dict()
            return updated

        return self.storage.update(updater)

    def clear(self, conversation_id: str) -> None:
        def updater(payload):
            conversations = payload.get("conversations", {})
            conversations.pop(conversation_id, None)
            if conversations:
                payload["conversations"] = conversations
            else:
                payload.pop("conversations", None)

        self.storage.update(updater)


def new_conversation_id() -> str:
    return uuid.uuid4().hex[:12]


def user_message(content: str) -> MemoryMessage:
    return MemoryMessage(role=MessageRole.USER, content=content)


def assistant_message(content: str) -> MemoryMessage:
    return MemoryMessage(role=MessageRole.ASSISTANT, content=content)


def compact_memory(
    memory: ConversationMemory,
    retain_recent: int = DEFAULT_SUMMARY_RETAIN_RECENT,
    max_summary_chars: int = DEFAULT_SUMMARY_MAX_CHARS,
) -> ConversationMemory:
    if retain_recent < 0:
        retain_recent = 0
    metadata = dict(memory.metadata or {})
    cutoff = max(0, len(memory.messages) - retain_recent)
    summarized_count = int(metadata.get(SUMMARIZED_COUNT_KEY, 0) or 0)
    if cutoff <= summarized_count:
        return memory

    prior_summary = metadata.get(SUMMARY_KEY, "")
    new_lines = [_summary_line(index, message) for index, message in enumerate(memory.messages[summarized_count:cutoff], start=summarized_count)]
    summary = "\n".join(item for item in (prior_summary, *new_lines) if item).strip()
    if len(summary) > max_summary_chars:
        summary = "... " + summary[-max_summary_chars:]
    metadata[SUMMARY_KEY] = summary
    metadata[SUMMARIZED_COUNT_KEY] = cutoff
    metadata["summary_method"] = "deterministic_rolling_extract"
    return ConversationMemory(
        conversation_id=memory.conversation_id,
        messages=memory.messages,
        metadata=metadata,
    )


def conversation_summary(memory: ConversationMemory) -> str | None:
    summary = (memory.metadata or {}).get(SUMMARY_KEY)
    return summary if isinstance(summary, str) and summary.strip() else None


def _summary_line(index: int, message: MemoryMessage, limit: int = 240) -> str:
    content = " ".join(message.content.split())
    if len(content) > limit:
        content = content[: limit - 3].rstrip() + "..."
    return f"{index + 1}. {message.role.value}: {content}"
