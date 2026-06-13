from __future__ import annotations

import json
import hashlib
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from finals_agent.core.config import INDEX_PATH, RAW_DATA_DIR, ensure_data_dirs
from finals_agent.core.exceptions import IngestInputError, MaterialNotFoundError, RepositoryIndexError, ToolInputError, UnsupportedMaterialTypeError
from finals_agent.core.schemas import (
    ArtifactInterpretation,
    DocumentChunk,
    DocumentType,
    IngestRequest,
    PaperArtifact,
    SearchResult,
    StudyDocument,
)
from finals_agent.persistence.storage import _lock_file, _unlock_file


SUPPORTED_TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".kts",
    ".scala",
    ".sh",
    ".ps1",
    ".sql",
    ".html",
    ".css",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
}
SUPPORTED_MATERIAL_SUFFIXES = {*SUPPORTED_TEXT_SUFFIXES, ".pdf"}
SUPPORTED_MATERIAL_SUFFIXES.add(".ipynb")


class StudyRepository:
    """A small local paper repository."""

    def __init__(self, index_path: Path = INDEX_PATH, raw_data_dir: Path = RAW_DATA_DIR):
        self.raw_data_dir = raw_data_dir
        if raw_data_dir == RAW_DATA_DIR:
            ensure_data_dirs()
        else:
            for folder in ["papers", "documents", "code", "related_work", "supplements", "notes"]:
                (raw_data_dir / folder).mkdir(parents=True, exist_ok=True)
        self.index_path = index_path
        self.lock_path = index_path.with_suffix(index_path.suffix + ".lock")

    def ingest(self, source_path: Path, document_type: DocumentType, course: str | None = None, field: str | None = None) -> StudyDocument:
        return self.add_document(
            IngestRequest(
                source_path=source_path,
                document_type=document_type,
                course=field if field is not None else (course or ""),
            )
        )

    def add_document(self, request: IngestRequest) -> StudyDocument:
        document = self.stage_document(request)
        self.commit_document(document)
        return document

    def stage_document(self, request: IngestRequest) -> StudyDocument:
        if not request.source_path.exists():
            raise MaterialNotFoundError(f"Paper material does not exist: {request.source_path}")
        if request.source_path.suffix.lower() not in SUPPORTED_MATERIAL_SUFFIXES:
            supported = ", ".join(sorted(SUPPORTED_MATERIAL_SUFFIXES))
            raise UnsupportedMaterialTypeError(f"The scaffold currently supports only: {supported}.")

        content_hash = file_sha256(request.source_path)
        duplicate = self.find_duplicate_document(content_hash)
        if duplicate:
            raise IngestInputError(
                f"Duplicate material detected. Existing document: {duplicate.title} ({duplicate.id})."
            )

        doc_id = uuid.uuid4().hex[:12]
        target_dir = self.raw_data_dir / request.document_type.folder
        target_path = target_dir / f"{doc_id}_{request.source_path.name}"
        shutil.copy2(request.source_path, target_path)

        document = StudyDocument(
            id=doc_id,
            title=request.normalized_title(),
            document_type=request.document_type,
            course=request.field,
            path=target_path,
            chapter=request.focus,
            source=request.source,
            tags=request.tags,
            content_hash=content_hash,
        )
        return document

    def commit_document(self, document: StudyDocument) -> None:
        with self._locked():
            documents = self._read_index_unlocked()
            documents.append(document)
            self._write_index_unlocked(documents)

    def remove_document_files(self, document: StudyDocument) -> None:
        paths = [
            document.path,
            document.path.with_suffix(document.path.suffix + ".txt"),
            self.chunk_sidecar_path(document.path),
            self.artifact_sidecar_path(document.path),
            self.artifact_interpretation_sidecar_path(document.path),
            document.path.with_suffix(document.path.suffix + ".artifact_regions.json"),
            document.path.with_suffix(document.path.suffix + ".artifact_manifest.json"),
            document.path.with_suffix(document.path.suffix + ".embeddings.json"),
        ]
        for path in paths:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                continue

    def remove_document(self, document_id: str) -> StudyDocument:
        with self._locked():
            documents = self._read_index_unlocked()
            target = None
            remaining = []
            for document in documents:
                if document.id == document_id:
                    target = document
                else:
                    remaining.append(document)
            if target is None:
                raise MaterialNotFoundError(f"Paper document does not exist: {document_id}")
            self._write_index_unlocked(remaining)
        self.remove_document_files(target)
        return target

    def update_document_organization(
        self,
        document_id: str,
        *,
        pinned: bool | None = None,
        archived: bool | None = None,
        category: str | None = None,
        update_category: bool = False,
    ) -> StudyDocument:
        normalized_category = category
        if update_category:
            normalized_category = " ".join((category or "").split()) or None
            if normalized_category and len(normalized_category) > 60:
                raise ToolInputError("category must be 60 characters or fewer.")

        with self._locked():
            documents = self._read_index_unlocked()
            updated = None
            result = []
            for document in documents:
                if document.id != document_id:
                    result.append(document)
                    continue
                resolved_archived = document.archived if archived is None else archived
                resolved_pinned = document.pinned if pinned is None else pinned
                if resolved_archived:
                    resolved_pinned = False
                updated = replace(
                    document,
                    pinned=resolved_pinned,
                    archived=resolved_archived,
                    category=normalized_category if update_category else document.category,
                )
                result.append(updated)
            if updated is None:
                raise MaterialNotFoundError(f"Paper document does not exist: {document_id}")
            self._write_index_unlocked(result)
        return updated

    def update_document_content_hash(self, document_id: str, content_hash: str) -> StudyDocument:
        with self._locked():
            documents = self._read_index_unlocked()
            updated = None
            result = []
            for document in documents:
                if document.id == document_id:
                    updated = replace(document, content_hash=content_hash)
                    result.append(updated)
                else:
                    result.append(document)
            if updated is None:
                raise MaterialNotFoundError(f"Paper document does not exist: {document_id}")
            self._write_index_unlocked(result)
        return updated

    def find_duplicate_document(self, content_hash: str) -> StudyDocument | None:
        for document in self.list_documents():
            if document.content_hash == content_hash:
                return document
            if not document.content_hash and document.path.exists():
                try:
                    if file_sha256(document.path) == content_hash:
                        return document
                except OSError:
                    continue
        return None

    def list_documents(self, course: str | None = None, field: str | None = None) -> list[StudyDocument]:
        with self._locked():
            documents = self._read_index_unlocked()

        effective_field = field if field is not None else course
        if effective_field:
            documents = [doc for doc in documents if doc.field == effective_field]
        return documents

    def _read_index_unlocked(self) -> list[StudyDocument]:
        if not self.index_path.exists():
            return []

        try:
            raw_items = json.loads(self.index_path.read_text(encoding="utf-8"))
            return [StudyDocument.from_dict(item) for item in raw_items]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RepositoryIndexError(f"Cannot read material index: {self.index_path}") from exc

    def get_document(self, document_id: str) -> StudyDocument:
        for document in self.list_documents():
            if document.id == document_id:
                return document
        raise MaterialNotFoundError(f"Paper document does not exist: {document_id}")

    def search(
        self,
        query: str,
        course: str | None = None,
        document_id: str | None = None,
        document_type: DocumentType | None = None,
        chapter: str | None = None,
        field: str | None = None,
        focus: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        if len(query) > 500:
            raise ToolInputError("query must be 500 characters or fewer.")
        query_terms = _query_terms(query)
        if not query_terms:
            return []

        effective_field = field if field is not None else course
        effective_focus = focus if focus is not None else chapter
        candidates = self.list_documents(field=effective_field)
        if document_id:
            candidates = [doc for doc in candidates if doc.id == document_id]
        if document_type:
            candidates = [doc for doc in candidates if doc.document_type == document_type]
        if effective_focus:
            candidates = [doc for doc in candidates if doc.focus == effective_focus]

        matches: list[SearchResult] = []
        for doc in candidates:
            chunk_matches = self._search_chunks(doc, query_terms)
            if chunk_matches:
                matches.extend(chunk_matches)
                continue

            text = self._read_searchable_text(doc)
            if text is None:
                continue

            lower_text = text.lower()
            score = sum(lower_text.count(term) for term in query_terms)
            if score == 0:
                continue

            snippet = self._make_snippet(text, query_terms[0])
            matches.append(
                SearchResult(
                    document_id=doc.id,
                    title=doc.title,
                    document_type=doc.document_type,
                    course=doc.field,
                    path=doc.path,
                    snippet=snippet,
                    score=float(score),
                    chapter=doc.focus,
                    source=doc.source,
                    tags=doc.tags,
                )
            )

        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:limit]

    def read_chunks(self, doc: StudyDocument) -> list[DocumentChunk]:
        chunk_path = self.chunk_sidecar_path(doc.path)
        if not chunk_path.exists():
            return []
        try:
            raw_items = json.loads(chunk_path.read_text(encoding="utf-8"))
            return [DocumentChunk.from_dict(item) for item in raw_items]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RepositoryIndexError(f"Cannot read chunk index: {chunk_path}") from exc

    def read_artifacts(self, doc: StudyDocument) -> list[PaperArtifact]:
        artifact_path = self.artifact_sidecar_path(doc.path)
        if not artifact_path.exists():
            return []
        try:
            raw_items = json.loads(artifact_path.read_text(encoding="utf-8"))
            return [PaperArtifact.from_dict(item) for item in raw_items]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RepositoryIndexError(f"Cannot read artifact index: {artifact_path}") from exc

    def read_artifact_interpretations(self, doc: StudyDocument) -> list[ArtifactInterpretation]:
        path = self.artifact_interpretation_sidecar_path(doc.path)
        if not path.exists():
            return []
        try:
            raw_items = json.loads(path.read_text(encoding="utf-8"))
            return [ArtifactInterpretation.from_dict(item) for item in raw_items]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RepositoryIndexError(f"Cannot read artifact interpretation index: {path}") from exc

    def write_artifact_interpretations(
        self,
        doc: StudyDocument,
        interpretations: list[ArtifactInterpretation],
    ) -> Path:
        path = self.artifact_interpretation_sidecar_path(doc.path)
        payload = [item.to_dict() for item in interpretations]
        _atomic_write_json(path, payload)
        return path

    @staticmethod
    def chunk_sidecar_path(source_path: Path) -> Path:
        return source_path.with_suffix(source_path.suffix + ".chunks.json")

    @staticmethod
    def artifact_sidecar_path(source_path: Path) -> Path:
        return source_path.with_suffix(source_path.suffix + ".artifacts.json")

    @staticmethod
    def artifact_interpretation_sidecar_path(source_path: Path) -> Path:
        return source_path.with_suffix(source_path.suffix + ".artifact_interpretations.json")

    def _write_index(self, documents: list[StudyDocument]) -> None:
        with self._locked():
            self._write_index_unlocked(documents)

    def _write_index_unlocked(self, documents: list[StudyDocument]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = [doc.to_dict() for doc in documents]
            _atomic_write_json(self.index_path, payload)
        except OSError as exc:
            raise RepositoryIndexError(f"Cannot write material index: {self.index_path}") from exc

    @contextmanager
    def _locked(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock_file:
            _lock_file(lock_file)
            try:
                yield
            finally:
                _unlock_file(lock_file)

    @staticmethod
    def _make_snippet(text: str, first_term: str, radius: int = 80) -> str:
        lower_text = text.lower()
        index = lower_text.find(first_term)
        if index < 0:
            return text[: radius * 2].replace("\n", " ")
        start = max(0, index - radius)
        end = min(len(text), index + len(first_term) + radius)
        return text[start:end].replace("\n", " ")

    def _search_chunks(self, doc: StudyDocument, query_terms: list[str]) -> list[SearchResult]:
        matches = []
        for chunk in self.read_chunks(doc):
            lower_text = chunk.text.lower()
            score = sum(lower_text.count(term) for term in query_terms)
            if score == 0:
                continue
            matches.append(
                SearchResult(
                    document_id=doc.id,
                    title=doc.title,
                    document_type=doc.document_type,
                    course=doc.field,
                    path=doc.path,
                    snippet=self._make_snippet(chunk.text, query_terms[0]),
                    score=float(score),
                    chapter=doc.focus,
                    source=doc.source,
                    tags=doc.tags,
                    chunk_id=chunk.chunk_id,
                    page=chunk.metadata.get("page"),
                    section=chunk.metadata.get("section"),
                    block_type=chunk.metadata.get("block_type"),
                )
            )
        return matches

    @staticmethod
    def _read_searchable_text(doc: StudyDocument) -> str | None:
        if doc.path.exists() and doc.path.suffix.lower() in SUPPORTED_TEXT_SUFFIXES:
            return doc.path.read_text(encoding="utf-8", errors="ignore")
        sidecar_path = doc.path.with_suffix(doc.path.suffix + ".txt")
        if sidecar_path.exists():
            return sidecar_path.read_text(encoding="utf-8", errors="ignore")
        return None

    def read_searchable_text(self, doc: StudyDocument) -> str | None:
        return self._read_searchable_text(doc)


def _atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _query_terms(query: str) -> list[str]:
    terms = [term.lower() for term in query.split() if term.strip()]
    if _contains_cjk(query):
        try:
            import jieba

            terms.extend(
                token.lower()
                for token in jieba.lcut(query)
                if token.strip() and len(token.strip()) > 1
            )
        except ImportError:
            terms.extend(_cjk_ngrams(query))
    unique = []
    for term in terms:
        if term not in unique:
            unique.append(term)
    return unique


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _cjk_ngrams(text: str) -> list[str]:
    chars = [char for char in text if "\u4e00" <= char <= "\u9fff"]
    return ["".join(chars[index : index + 2]) for index in range(max(0, len(chars) - 1))]
