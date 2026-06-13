from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any
import uuid

from finals_agent.core.config import READING_STATE_PATH
from finals_agent.core.exceptions import ToolInputError
from finals_agent.core.schemas import StudyDocument
from finals_agent.persistence.storage import JsonFileStorage, StorageBackend


READING_STATUSES = {"not_started", "reading", "reviewing", "done"}
ITEM_STATUSES = {"open", "done", "archived"}


@dataclass(frozen=True)
class ReadingEntry:
    id: str
    kind: str
    text: str
    status: str = "open"
    section: str | None = None
    page: int | None = None
    citation: str | None = None
    answer: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "status": self.status,
            "section": self.section,
            "page": self.page,
            "citation": self.citation,
            "answer": self.answer,
            "metadata": self.metadata or {},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReadingEntry":
        return cls(
            id=payload["id"],
            kind=payload["kind"],
            text=payload["text"],
            status=payload.get("status", "open"),
            section=payload.get("section"),
            page=payload.get("page"),
            citation=payload.get("citation"),
            answer=payload.get("answer"),
            metadata=payload.get("metadata") or {},
            created_at=payload.get("created_at", ""),
            updated_at=payload.get("updated_at", ""),
        )


@dataclass(frozen=True)
class ReadingState:
    document_id: str
    title: str
    field: str
    status: str = "not_started"
    current_section: str | None = None
    progress_percent: int = 0
    current_page: int | None = None
    page_count: int | None = None
    max_page_reached: int = 0
    review_summary: str | None = None
    notes: tuple[ReadingEntry, ...] = ()
    questions: tuple[ReadingEntry, ...] = ()
    verification_items: tuple[ReadingEntry, ...] = ()
    flashcards: tuple[ReadingEntry, ...] = ()
    timeline: tuple[ReadingEntry, ...] = ()
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "field": self.field,
            "status": self.status,
            "current_section": self.current_section,
            "progress_percent": self.progress_percent,
            "current_page": self.current_page,
            "page_count": self.page_count,
            "max_page_reached": self.max_page_reached,
            "review_summary": self.review_summary,
            "notes": [item.to_dict() for item in self.notes],
            "questions": [item.to_dict() for item in self.questions],
            "verification_items": [item.to_dict() for item in self.verification_items],
            "flashcards": [item.to_dict() for item in self.flashcards],
            "timeline": [item.to_dict() for item in self.timeline],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReadingState":
        return cls(
            document_id=payload["document_id"],
            title=payload.get("title", ""),
            field=payload.get("field", ""),
            status=payload.get("status", "not_started"),
            current_section=payload.get("current_section"),
            progress_percent=int(payload.get("progress_percent", 0)),
            current_page=payload.get("current_page"),
            page_count=payload.get("page_count"),
            max_page_reached=int(payload.get("max_page_reached", payload.get("current_page") or 0)),
            review_summary=payload.get("review_summary"),
            notes=tuple(ReadingEntry.from_dict(item) for item in payload.get("notes", ())),
            questions=tuple(ReadingEntry.from_dict(item) for item in payload.get("questions", ())),
            verification_items=tuple(ReadingEntry.from_dict(item) for item in payload.get("verification_items", ())),
            flashcards=tuple(ReadingEntry.from_dict(item) for item in payload.get("flashcards", ())),
            timeline=tuple(ReadingEntry.from_dict(item) for item in payload.get("timeline", ())),
            created_at=payload.get("created_at", ""),
            updated_at=payload.get("updated_at", ""),
        )

    @property
    def open_question_count(self) -> int:
        return sum(1 for item in self.questions if item.status == "open")

    @property
    def open_verification_count(self) -> int:
        return sum(1 for item in self.verification_items if item.status == "open")


class ReadingStateStore:
    def __init__(self, storage: StorageBackend | None = None):
        self.storage = storage or JsonFileStorage(READING_STATE_PATH)

    def get(self, document: StudyDocument) -> ReadingState:
        payload = self.storage.read()
        raw = payload.get("documents", {}).get(document.id)
        if raw:
            state = ReadingState.from_dict(raw)
            return _sync_document_metadata(state, document)
        now = _now()
        return ReadingState(
            document_id=document.id,
            title=document.title,
            field=document.field,
            created_at=now,
            updated_at=now,
        )

    def update_progress(
        self,
        document: StudyDocument,
        status: str | None = None,
        current_section: str | None = None,
        progress_percent: int | None = None,
        current_page: int | None = None,
        page_count: int | None = None,
        review_summary: str | None = None,
    ) -> ReadingState:
        if status is not None and status not in READING_STATUSES:
            allowed = ", ".join(sorted(READING_STATUSES))
            raise ToolInputError(f"Invalid reading status. Allowed values: {allowed}.")
        if progress_percent is not None and not 0 <= progress_percent <= 100:
            raise ToolInputError("progress_percent must be between 0 and 100.")
        if current_page is not None and current_page < 1:
            raise ToolInputError("current_page must be at least 1.")
        if page_count is not None and page_count < 1:
            raise ToolInputError("page_count must be at least 1.")
        if current_page is not None and page_count is not None and current_page > page_count:
            raise ToolInputError("current_page cannot exceed page_count.")

        def updater(payload):
            state = self._get_from_payload(payload, document)
            resolved_page_count = page_count if page_count is not None else state.page_count
            resolved_current_page = current_page if current_page is not None else state.current_page
            max_page_reached = max(state.max_page_reached, current_page or 0)
            resolved_progress = progress_percent
            if current_page is not None and resolved_page_count:
                resolved_progress = round(current_page / resolved_page_count * 100)
            updated = ReadingState(
                document_id=document.id,
                title=document.title,
                field=document.field,
                status=status or state.status,
                current_section=current_section if current_section is not None else state.current_section,
                progress_percent=resolved_progress if resolved_progress is not None else state.progress_percent,
                current_page=resolved_current_page,
                page_count=resolved_page_count,
                max_page_reached=max_page_reached,
                review_summary=review_summary if review_summary is not None else state.review_summary,
                notes=state.notes,
                questions=state.questions,
                verification_items=state.verification_items,
                flashcards=state.flashcards,
                timeline=state.timeline,
                created_at=state.created_at or _now(),
                updated_at=_now(),
            )
            self._put_into_payload(payload, updated)
            return updated

        return self.storage.update(updater)

    def add_note(
        self,
        document: StudyDocument,
        text: str,
        section: str | None = None,
        page: int | None = None,
        citation: str | None = None,
    ) -> ReadingState:
        return self._append_entry(document, "note", text=text, section=section, page=page, citation=citation)

    def set_personal_note(self, document: StudyDocument, text: str) -> ReadingState:
        if len(text) > 100_000:
            raise ToolInputError("personal note cannot exceed 100,000 characters.")

        def updater(payload):
            state = self._get_from_payload(payload, document)
            now = _now()
            note = ReadingEntry(
                id="personal-note",
                kind="note",
                text=text,
                status="open",
                section=None,
                page=None,
                citation=None,
                created_at=next(
                    (item.created_at for item in state.notes if item.id == "personal-note"),
                    now,
                ),
                updated_at=now,
            )
            notes = tuple(item for item in state.notes if item.id != "personal-note")
            updated = ReadingState(
                document_id=state.document_id,
                title=state.title,
                field=state.field,
                status=state.status,
                current_section=state.current_section,
                progress_percent=state.progress_percent,
                current_page=state.current_page,
                page_count=state.page_count,
                max_page_reached=state.max_page_reached,
                review_summary=state.review_summary,
                notes=(note, *notes),
                questions=state.questions,
                verification_items=state.verification_items,
                flashcards=state.flashcards,
                timeline=state.timeline,
                created_at=state.created_at or now,
                updated_at=now,
            )
            self._put_into_payload(payload, updated)
            return updated

        return self.storage.update(updater)

    def add_question(
        self,
        document: StudyDocument,
        text: str,
        section: str | None = None,
        page: int | None = None,
        citation: str | None = None,
    ) -> ReadingState:
        return self._append_entry(document, "question", text=text, section=section, page=page, citation=citation)

    def add_timeline_entry(
        self,
        document: StudyDocument,
        kind: str,
        text: str,
        *,
        answer: str | None = None,
        section: str | None = None,
        page: int | None = None,
        citation: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReadingState:
        if not kind.strip():
            raise ToolInputError("timeline entry kind cannot be empty.")
        if not text.strip():
            raise ToolInputError("timeline entry text cannot be empty.")

        def updater(payload):
            state = self._get_from_payload(payload, document)
            now = _now()
            entry = ReadingEntry(
                id=uuid.uuid4().hex[:10],
                kind=kind.strip(),
                text=text.strip(),
                status="open",
                section=section,
                page=page,
                citation=citation,
                answer=answer.strip() if answer else None,
                metadata=metadata or {},
                created_at=now,
                updated_at=now,
            )
            updated = ReadingState(
                document_id=state.document_id,
                title=state.title,
                field=state.field,
                status=state.status,
                current_section=state.current_section,
                progress_percent=state.progress_percent,
                current_page=state.current_page,
                page_count=state.page_count,
                max_page_reached=state.max_page_reached,
                review_summary=state.review_summary,
                notes=state.notes,
                questions=state.questions,
                verification_items=state.verification_items,
                flashcards=state.flashcards,
                timeline=(*state.timeline, entry),
                created_at=state.created_at or now,
                updated_at=now,
            )
            self._put_into_payload(payload, updated)
            return updated

        return self.storage.update(updater)

    def reorder_timeline(self, document: StudyDocument, entry_ids: list[str]) -> ReadingState:
        normalized = [str(item).strip() for item in entry_ids if str(item).strip()]
        if len(normalized) != len(set(normalized)):
            raise ToolInputError("timeline order cannot contain duplicate ids.")

        def updater(payload):
            state = self._get_from_payload(payload, document)
            by_id = {item.id: item for item in state.timeline}
            unknown = [item_id for item_id in normalized if item_id not in by_id]
            if unknown:
                raise ToolInputError(f"Unknown timeline entry id: {unknown[0]}.")
            ordered = [by_id[item_id] for item_id in normalized]
            ordered.extend(item for item in state.timeline if item.id not in set(normalized))
            updated = replace(state, timeline=tuple(ordered), updated_at=_now())
            self._put_into_payload(payload, updated)
            return updated

        return self.storage.update(updater)

    def delete_timeline_entry(self, document: StudyDocument, entry_id: str) -> ReadingState:
        normalized = entry_id.strip()
        if not normalized:
            raise ToolInputError("timeline entry id cannot be empty.")

        def updater(payload):
            state = self._get_from_payload(payload, document)
            if all(item.id != normalized for item in state.timeline):
                raise ToolInputError(f"No timeline entry matched id '{normalized}'.")

            def remove(items: tuple[ReadingEntry, ...]) -> tuple[ReadingEntry, ...]:
                return tuple(item for item in items if item.id != normalized)

            updated = replace(
                state,
                notes=remove(state.notes),
                questions=remove(state.questions),
                verification_items=remove(state.verification_items),
                flashcards=remove(state.flashcards),
                timeline=remove(state.timeline),
                updated_at=_now(),
            )
            self._put_into_payload(payload, updated)
            return updated

        return self.storage.update(updater)

    def add_verification_item(
        self,
        document: StudyDocument,
        text: str,
        section: str | None = None,
        page: int | None = None,
        citation: str | None = None,
    ) -> ReadingState:
        return self._append_entry(document, "verification", text=text, section=section, page=page, citation=citation)

    def add_flashcard(
        self,
        document: StudyDocument,
        question: str,
        answer: str,
        section: str | None = None,
        page: int | None = None,
        citation: str | None = None,
    ) -> ReadingState:
        return self._append_entry(
            document,
            "flashcard",
            text=question,
            answer=answer,
            section=section,
            page=page,
            citation=citation,
        )

    def mark_item(self, document: StudyDocument, item_id: str, status: str) -> ReadingState:
        if status not in ITEM_STATUSES:
            allowed = ", ".join(sorted(ITEM_STATUSES))
            raise ToolInputError(f"Invalid item status. Allowed values: {allowed}.")

        def updater(payload):
            state = self._get_from_payload(payload, document)
            updated, changed = _mark_entry(state, item_id=item_id, status=status)
            if not changed:
                raise ToolInputError(f"No reading item matched id '{item_id}'.")
            self._put_into_payload(payload, updated)
            return updated

        return self.storage.update(updater)

    def clear(self, document: StudyDocument) -> None:
        def updater(payload):
            documents = payload.get("documents", {})
            documents.pop(document.id, None)
            if documents:
                payload["documents"] = documents
            else:
                payload.pop("documents", None)

        self.storage.update(updater)

    def _append_entry(
        self,
        document: StudyDocument,
        kind: str,
        text: str,
        answer: str | None = None,
        section: str | None = None,
        page: int | None = None,
        citation: str | None = None,
    ) -> ReadingState:
        if not text.strip():
            raise ToolInputError("reading item text cannot be empty.")
        if kind == "flashcard" and (answer is None or not answer.strip()):
            raise ToolInputError("flashcard answer cannot be empty.")
        if page is not None and page < 1:
            raise ToolInputError("page must be at least 1.")

        def updater(payload):
            state = self._get_from_payload(payload, document)
            entry = ReadingEntry(
                id=uuid.uuid4().hex[:10],
                kind=kind,
                text=text.strip(),
                status="open",
                section=section,
                page=page,
                citation=citation,
                answer=answer.strip() if answer else None,
                created_at=_now(),
                updated_at=_now(),
            )
            updated = _append_to_state(state, entry)
            self._put_into_payload(payload, updated)
            return updated

        return self.storage.update(updater)

    def _get_from_payload(self, payload: dict[str, Any], document: StudyDocument) -> ReadingState:
        raw = payload.get("documents", {}).get(document.id)
        if raw:
            return _sync_document_metadata(ReadingState.from_dict(raw), document)
        now = _now()
        return ReadingState(
            document_id=document.id,
            title=document.title,
            field=document.field,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _put_into_payload(payload: dict[str, Any], state: ReadingState) -> None:
        documents = payload.setdefault("documents", {})
        documents[state.document_id] = state.to_dict()


def reading_state_summary(state: ReadingState, limit: int = 5) -> dict[str, Any]:
    personal_note = next((item for item in state.notes if item.id == "personal-note"), None)
    return {
        "document_id": state.document_id,
        "title": state.title,
        "field": state.field,
        "status": state.status,
        "current_section": state.current_section,
        "progress_percent": state.progress_percent,
        "current_page": state.current_page,
        "page_count": state.page_count,
        "max_page_reached": state.max_page_reached,
        "review_summary": state.review_summary,
        "personal_note": personal_note.to_dict() if personal_note else None,
        "note_count": len(state.notes),
        "open_question_count": state.open_question_count,
        "open_verification_count": state.open_verification_count,
        "flashcard_count": len(state.flashcards),
        "recent_notes": [
            item.to_dict()
            for item in state.notes
            if item.id != "personal-note"
        ][-limit:],
        "open_questions": [item.to_dict() for item in state.questions if item.status == "open"][:limit],
        "open_verification_items": [
            item.to_dict() for item in state.verification_items if item.status == "open"
        ][:limit],
        "recent_flashcards": [item.to_dict() for item in state.flashcards[-limit:]],
        "timeline": [item.to_dict() for item in state.timeline[-50:]],
        "updated_at": state.updated_at,
    }


def _append_to_state(state: ReadingState, entry: ReadingEntry) -> ReadingState:
    kwargs = {
        "document_id": state.document_id,
        "title": state.title,
        "field": state.field,
        "status": state.status,
        "current_section": state.current_section,
        "progress_percent": state.progress_percent,
        "current_page": state.current_page,
        "page_count": state.page_count,
        "max_page_reached": state.max_page_reached,
        "review_summary": state.review_summary,
        "notes": state.notes,
        "questions": state.questions,
        "verification_items": state.verification_items,
        "flashcards": state.flashcards,
        "timeline": state.timeline,
        "created_at": state.created_at or _now(),
        "updated_at": _now(),
    }
    if entry.kind == "note":
        kwargs["notes"] = (*state.notes, entry)
        kwargs["timeline"] = (*state.timeline, entry)
    elif entry.kind == "question":
        kwargs["questions"] = (*state.questions, entry)
        kwargs["timeline"] = (*state.timeline, entry)
    elif entry.kind == "verification":
        kwargs["verification_items"] = (*state.verification_items, entry)
    elif entry.kind == "flashcard":
        kwargs["flashcards"] = (*state.flashcards, entry)
    else:
        raise ToolInputError(f"Unsupported reading item kind: {entry.kind}.")
    return ReadingState(**kwargs)


def _mark_entry(state: ReadingState, item_id: str, status: str) -> tuple[ReadingState, bool]:
    changed = False

    def mark(items: tuple[ReadingEntry, ...]) -> tuple[ReadingEntry, ...]:
        nonlocal changed
        updated = []
        for item in items:
            if item.id == item_id:
                changed = True
                updated.append(
                    ReadingEntry(
                        id=item.id,
                        kind=item.kind,
                        text=item.text,
                        status=status,
                        section=item.section,
                        page=item.page,
                        citation=item.citation,
                        answer=item.answer,
                        metadata=item.metadata,
                        created_at=item.created_at,
                        updated_at=_now(),
                    )
                )
            else:
                updated.append(item)
        return tuple(updated)

    updated_state = ReadingState(
        document_id=state.document_id,
        title=state.title,
        field=state.field,
        status=state.status,
        current_section=state.current_section,
        progress_percent=state.progress_percent,
        current_page=state.current_page,
        page_count=state.page_count,
        max_page_reached=state.max_page_reached,
        review_summary=state.review_summary,
        notes=mark(state.notes),
        questions=mark(state.questions),
        verification_items=mark(state.verification_items),
        flashcards=mark(state.flashcards),
        timeline=mark(state.timeline),
        created_at=state.created_at,
        updated_at=_now() if changed else state.updated_at,
    )
    return updated_state, changed


def _sync_document_metadata(state: ReadingState, document: StudyDocument) -> ReadingState:
    if state.title == document.title and state.field == document.field:
        return state
    return ReadingState(
        document_id=document.id,
        title=document.title,
        field=document.field,
        status=state.status,
        current_section=state.current_section,
        progress_percent=state.progress_percent,
        current_page=state.current_page,
        page_count=state.page_count,
        max_page_reached=state.max_page_reached,
        review_summary=state.review_summary,
        notes=state.notes,
        questions=state.questions,
        verification_items=state.verification_items,
        flashcards=state.flashcards,
        timeline=state.timeline,
        created_at=state.created_at,
        updated_at=_now(),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
