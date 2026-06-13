from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
from typing import Any


class DocumentType(StrEnum):
    PAPER = "paper"
    DOCUMENT = "document"
    CODE = "code"
    RELATED_WORK = "related_work"
    SUPPLEMENT = "supplement"
    NOTE = "note"

    @property
    def folder(self) -> str:
        return {
            DocumentType.PAPER: "papers",
            DocumentType.DOCUMENT: "documents",
            DocumentType.CODE: "code",
            DocumentType.RELATED_WORK: "related_work",
            DocumentType.SUPPLEMENT: "supplements",
            DocumentType.NOTE: "notes",
        }[self]


class ReviewMode(StrEnum):
    NORMAL = "normal"
    SKIM = "skim"
    DEEP_READING = "deep_reading"
    COMPARISON = "comparison"
    PRESENTATION = "presentation"


class ToolStatus(StrEnum):
    SUCCESS = "success"
    EMPTY = "empty"
    ERROR = "error"


class IngestStatus(StrEnum):
    INGESTED = "ingested"
    SKIPPED = "skipped"
    FAILED = "failed"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class TaskType(StrEnum):
    PAPER_SEARCH = "paper_search"
    PAPER_EXPLANATION = "paper_explanation"
    STRUCTURE_ANALYSIS = "structure_analysis"
    FIGURE_TABLE_EXPLANATION = "figure_table_explanation"
    RELATED_WORK_DISCOVERY = "related_work_discovery"
    INNOVATION_COMPARISON = "innovation_comparison"
    GENERAL_CHAT = "general_chat"


@dataclass(frozen=True, init=False)
class ResearchContext:
    field: str | None = None
    focus: str | None = None
    target_document_id: str | None = None
    target_title: str | None = None
    review_mode: ReviewMode = ReviewMode.NORMAL
    goal: str | None = None

    def __init__(
        self,
        field: str | None = None,
        focus: str | None = None,
        target_document_id: str | None = None,
        target_title: str | None = None,
        review_mode: ReviewMode = ReviewMode.NORMAL,
        goal: str | None = None,
        course: str | None = None,
        chapter: str | None = None,
        document_id: str | None = None,
        title: str | None = None,
    ):
        object.__setattr__(self, "field", field if field is not None else course)
        object.__setattr__(self, "focus", focus if focus is not None else chapter)
        object.__setattr__(self, "target_document_id", target_document_id if target_document_id is not None else document_id)
        object.__setattr__(self, "target_title", target_title if target_title is not None else title)
        object.__setattr__(self, "review_mode", review_mode)
        object.__setattr__(self, "goal", goal)

    @property
    def course(self) -> str | None:
        return self.field

    @property
    def chapter(self) -> str | None:
        return self.focus

    def describe(self) -> str:
        parts = []
        if self.field:
            parts.append(f"field={self.field}")
        if self.focus:
            parts.append(f"focus={self.focus}")
        if self.target_document_id:
            parts.append(f"document_id={self.target_document_id}")
        if self.target_title:
            parts.append(f"title={self.target_title}")
        parts.append(f"mode={self.review_mode.value}")
        if self.goal:
            parts.append(f"goal={self.goal}")
        return ", ".join(parts)


CourseContext = ResearchContext


@dataclass(frozen=True)
class MaterialMetadata:
    title: str
    document_type: DocumentType
    course: str
    source_path: Path
    chapter: str | None = None
    source: str | None = None
    tags: tuple[str, ...] = ()

    @property
    def field(self) -> str:
        return self.course

    @property
    def focus(self) -> str | None:
        return self.chapter

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "document_type": self.document_type.value,
            "field": self.field,
            "course": self.course,
            "source_path": str(self.source_path),
            "focus": self.focus,
            "chapter": self.chapter,
            "source": self.source,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MaterialMetadata":
        return cls(
            title=payload["title"],
            document_type=DocumentType(payload["document_type"]),
            course=payload.get("field") or payload["course"],
            source_path=Path(payload["source_path"]),
            chapter=payload.get("focus") or payload.get("chapter"),
            source=payload.get("source"),
            tags=tuple(payload.get("tags", ())),
        )


@dataclass(frozen=True)
class StudyDocument:
    id: str
    title: str
    document_type: DocumentType
    course: str
    path: Path
    chapter: str | None = None
    source: str | None = None
    tags: tuple[str, ...] = ()
    content_hash: str | None = None
    pinned: bool = False
    archived: bool = False
    category: str | None = None

    @property
    def field(self) -> str:
        return self.course

    @property
    def focus(self) -> str | None:
        return self.chapter

    @property
    def metadata(self) -> MaterialMetadata:
        return MaterialMetadata(
            title=self.title,
            document_type=self.document_type,
            course=self.course,
            source_path=self.path,
            chapter=self.chapter,
            source=self.source,
            tags=self.tags,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "document_type": self.document_type.value,
            "field": self.field,
            "course": self.course,
            "path": str(self.path),
            "focus": self.focus,
            "chapter": self.chapter,
            "source": self.source,
            "tags": list(self.tags),
            "content_hash": self.content_hash,
            "pinned": self.pinned,
            "archived": self.archived,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StudyDocument":
        return cls(
            id=payload["id"],
            title=payload["title"],
            document_type=DocumentType(payload["document_type"]),
            course=payload.get("field") or payload["course"],
            path=Path(payload["path"]),
            chapter=payload.get("focus") or payload.get("chapter"),
            source=payload.get("source"),
            tags=tuple(payload.get("tags", ())),
            content_hash=payload.get("content_hash"),
            pinned=bool(payload.get("pinned", False)),
            archived=bool(payload.get("archived", False)),
            category=payload.get("category"),
        )


@dataclass(frozen=True)
class IngestRequest:
    source_path: Path
    document_type: DocumentType
    course: str
    title: str | None = None
    chapter: str | None = None
    source: str | None = None
    tags: tuple[str, ...] = ()

    @property
    def field(self) -> str:
        return self.course

    @property
    def focus(self) -> str | None:
        return self.chapter

    def normalized_title(self) -> str:
        return self.title or self.source_path.stem

    def to_metadata(self) -> MaterialMetadata:
        return MaterialMetadata(
            title=self.normalized_title(),
            document_type=self.document_type,
            course=self.course,
            source_path=self.source_path,
            chapter=self.chapter,
            source=self.source,
            tags=self.tags,
        )


@dataclass(frozen=True)
class IngestResult:
    status: IngestStatus
    document: StudyDocument | None = None
    message: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class DocumentChunk:
    document_id: str | None
    chunk_id: str
    text: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "text": self.text,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DocumentChunk":
        return cls(
            document_id=payload.get("document_id"),
            chunk_id=payload["chunk_id"],
            text=payload["text"],
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class PaperArtifact:
    document_id: str | None
    artifact_id: str
    kind: str
    text: str
    page: int | None = None
    caption: str | None = None
    nearby_text: str | None = None
    chunk_id: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "text": self.text,
            "page": self.page,
            "caption": self.caption,
            "nearby_text": self.nearby_text,
            "chunk_id": self.chunk_id,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PaperArtifact":
        return cls(
            document_id=payload.get("document_id"),
            artifact_id=payload["artifact_id"],
            kind=payload["kind"],
            text=payload["text"],
            page=payload.get("page"),
            caption=payload.get("caption"),
            nearby_text=payload.get("nearby_text"),
            chunk_id=payload.get("chunk_id"),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class ArtifactInterpretation:
    document_id: str | None
    artifact_id: str
    kind: str
    extracted_text: str
    structured_data: dict[str, Any]
    interpretation: str
    confidence: float
    method: str
    limitations: tuple[str, ...] = ()
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "extracted_text": self.extracted_text,
            "structured_data": self.structured_data,
            "interpretation": self.interpretation,
            "confidence": self.confidence,
            "method": self.method,
            "limitations": list(self.limitations),
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArtifactInterpretation":
        return cls(
            document_id=payload.get("document_id"),
            artifact_id=payload["artifact_id"],
            kind=payload["kind"],
            extracted_text=payload.get("extracted_text", ""),
            structured_data=payload.get("structured_data") or {},
            interpretation=payload.get("interpretation", ""),
            confidence=float(payload.get("confidence", 0.0)),
            method=payload.get("method", "unknown"),
            limitations=tuple(payload.get("limitations", ())),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class ProcessingRequest:
    source_path: Path
    metadata: MaterialMetadata
    document_id: str | None = None
    chunk_size: int = 1000
    chunk_overlap: int = 100


@dataclass(frozen=True)
class ProcessingResult:
    source_path: Path
    chunks: tuple[DocumentChunk, ...]
    text_length: int
    metadata: dict[str, Any]
    artifacts: tuple[PaperArtifact, ...] = ()


@dataclass(frozen=True)
class SearchResult:
    document_id: str
    title: str
    document_type: DocumentType
    course: str
    path: Path
    snippet: str
    score: float
    chapter: str | None = None
    source: str | None = None
    tags: tuple[str, ...] = ()
    chunk_id: str | None = None
    page: int | None = None
    section: str | None = None
    block_type: str | None = None

    @property
    def field(self) -> str:
        return self.course

    @property
    def focus(self) -> str | None:
        return self.chapter

    def to_dict(self) -> dict[str, Any]:
        citation_parts = [self.title]
        if self.section:
            citation_parts.append(f"section={self.section}")
        elif self.chapter:
            citation_parts.append(f"focus={self.chapter}")
        if self.page is not None:
            citation_parts.append(f"page={self.page}")
        if self.chunk_id:
            citation_parts.append(f"chunk={self.chunk_id}")
        return {
            "id": self.document_id,
            "title": self.title,
            "field": self.field,
            "course": self.course,
            "type": self.document_type.value,
            "path": str(self.path),
            "snippet": self.snippet,
            "score": self.score,
            "focus": self.focus,
            "chapter": self.chapter,
            "source": self.source,
            "tags": list(self.tags),
            "chunk_id": self.chunk_id,
            "page": self.page,
            "section": self.section,
            "block_type": self.block_type,
            "citation": "[" + " | ".join(citation_parts) + "]",
        }


@dataclass(frozen=True, init=False)
class SearchRequest:
    query: str
    course: str | None = None
    document_id: str | None = None
    document_type: DocumentType | None = None
    chapter: str | None = None
    limit: int = 5

    def __init__(
        self,
        query: str,
        course: str | None = None,
        document_id: str | None = None,
        document_type: DocumentType | None = None,
        chapter: str | None = None,
        limit: int = 5,
        field: str | None = None,
        focus: str | None = None,
    ):
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "course", field if field is not None else course)
        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "document_type", document_type)
        object.__setattr__(self, "chapter", focus if focus is not None else chapter)
        object.__setattr__(self, "limit", limit)

    @property
    def field(self) -> str | None:
        return self.course

    @property
    def focus(self) -> str | None:
        return self.chapter


@dataclass(frozen=True)
class SearchResponse:
    request: SearchRequest
    results: tuple[SearchResult, ...]
    metadata: dict[str, Any]

    @property
    def count(self) -> int:
        return len(self.results)


@dataclass(frozen=True)
class TaskIntent:
    task_type: TaskType
    requires_retrieval: bool
    preferred_tools: tuple[str, ...] = ()
    topic: str | None = None
    course: str | None = None
    target_document_id: str | None = None
    target_title: str | None = None
    target_artifact: str | None = None
    target_section: str | None = None
    output_style: str | None = None
    evidence_scope: str = "local"
    needs_vision: bool = False
    needs_related_search: bool = False
    clarification_needed: bool = False
    clarification_question: str | None = None
    confidence: float = 0.0
    rationale: str = ""

    @property
    def field(self) -> str | None:
        return self.course

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type.value,
            "requires_retrieval": self.requires_retrieval,
            "preferred_tools": list(self.preferred_tools),
            "topic": self.topic,
            "field": self.field,
            "course": self.course,
            "target_document_id": self.target_document_id,
            "target_title": self.target_title,
            "target_artifact": self.target_artifact,
            "target_section": self.target_section,
            "output_style": self.output_style,
            "evidence_scope": self.evidence_scope,
            "needs_vision": self.needs_vision,
            "needs_related_search": self.needs_related_search,
            "clarification_needed": self.clarification_needed,
            "clarification_question": self.clarification_question,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class TaskPlan:
    intent: TaskIntent
    steps: tuple[str, ...]
    slots: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.to_dict(),
            "steps": list(self.steps),
            "slots": self.slots or {},
        }


@dataclass(frozen=True)
class AgentResponse:
    answer: str
    sources: tuple[SearchResult, ...] = ()
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentRequest:
    question: str
    course_context: CourseContext | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def research_context(self) -> ResearchContext | None:
        return self.course_context

    def to_messages(self) -> list[dict[str, str]]:
        return [{"role": "user", "content": self.question}]


@dataclass(frozen=True)
class MemoryMessage:
    role: MessageRole
    content: str
    metadata: dict[str, Any] | None = None

    def to_langchain_message(self) -> dict[str, str]:
        return {"role": self.role.value, "content": self.content}

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryMessage":
        return cls(
            role=MessageRole(payload["role"]),
            content=payload["content"],
            metadata=payload.get("metadata") or None,
        )


@dataclass(frozen=True)
class ConversationMemory:
    conversation_id: str
    messages: tuple[MemoryMessage, ...] = ()
    metadata: dict[str, Any] | None = None

    def to_messages(self) -> list[dict[str, str]]:
        return [message.to_langchain_message() for message in self.messages]

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "messages": [message.to_dict() for message in self.messages],
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ConversationMemory":
        return cls(
            conversation_id=payload["conversation_id"],
            messages=tuple(MemoryMessage.from_dict(item) for item in payload.get("messages", ())),
            metadata=payload.get("metadata") or None,
        )


@dataclass(frozen=True)
class AgentRunResult:
    answer: str
    raw_messages: list[Any]
    conversation_id: str | None = None
    metadata: dict[str, Any] | None = None

    def to_response(self) -> AgentResponse:
        return AgentResponse(
            answer=self.answer,
            metadata={
                "conversation_id": self.conversation_id,
                **(self.metadata or {}),
            },
        )


@dataclass(frozen=True)
class RunTrace:
    run_id: str
    status: str
    duration_ms: float
    metadata: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    status: ToolStatus
    message: str
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def success(
        cls,
        tool_name: str,
        message: str,
        data: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            tool_name=tool_name,
            status=ToolStatus.SUCCESS,
            message=message,
            data=data,
            metadata=metadata,
        )

    @classmethod
    def empty(cls, tool_name: str, message: str, metadata: dict[str, Any] | None = None) -> "ToolResult":
        return cls(
            tool_name=tool_name,
            status=ToolStatus.EMPTY,
            message=message,
            metadata=metadata,
        )

    @classmethod
    def failure(
        cls,
        tool_name: str,
        message: str,
        error: str,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            tool_name=tool_name,
            status=ToolStatus.ERROR,
            message=message,
            error=error,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "message": self.message,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata or {},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, payload: str) -> "ToolResult":
        data = json.loads(payload)
        return cls(
            tool_name=data["tool_name"],
            status=ToolStatus(data["status"]),
            message=data["message"],
            data=data.get("data"),
            error=data.get("error"),
            metadata=data.get("metadata") or None,
        )
