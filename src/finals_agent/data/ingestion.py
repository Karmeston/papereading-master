from __future__ import annotations

import json
import uuid
from pathlib import Path

from finals_agent.core.exceptions import IngestInputError, MaterialNotFoundError, UnsupportedMaterialTypeError
from finals_agent.core.schemas import (
    DocumentType,
    IngestRequest,
    IngestResult,
    IngestStatus,
    ProcessingRequest,
    ProcessingResult,
)
from finals_agent.data.processors import DocumentProcessingPipeline
from finals_agent.data.embeddings import EmbeddingProvider, build_document_embedding_index
from finals_agent.data.repository import SUPPORTED_MATERIAL_SUFFIXES, StudyRepository, file_sha256


def build_ingest_request(
    source_path: Path,
    document_type: DocumentType,
    field: str | None = None,
    title: str | None = None,
    focus: str | None = None,
    source: str | None = None,
    tags: tuple[str, ...] = (),
    course: str | None = None,
    chapter: str | None = None,
) -> IngestRequest:
    effective_field = field if field is not None else course
    effective_focus = focus if focus is not None else chapter
    if effective_field is None:
        effective_field = ""
    return IngestRequest(
        source_path=source_path,
        document_type=document_type,
        course=effective_field,
        title=title,
        chapter=effective_focus,
        source=source,
        tags=tags,
    )


def ingest_material(
    request: IngestRequest,
    repository: StudyRepository | None = None,
    pipeline: DocumentProcessingPipeline | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> IngestResult:
    repository = repository or StudyRepository()
    pipeline = pipeline or DocumentProcessingPipeline()
    _validate_ingest_request(request)
    duplicate = repository.find_duplicate_document(file_sha256(request.source_path))
    if duplicate:
        raise IngestInputError(
            f"Duplicate material detected. Existing document: {duplicate.title} ({duplicate.id})."
        )

    pending_processing = pipeline.process(
        ProcessingRequest(
            source_path=request.source_path,
            metadata=request.to_metadata(),
        )
    )
    document = repository.stage_document(request)
    try:
        stored_processing = pipeline.process(
            ProcessingRequest(
                source_path=document.path,
                metadata=document.metadata,
                document_id=document.id,
            )
        )
        search_text_path = _write_search_text_sidecar(document.path, stored_processing)
        chunk_index_path = _write_chunk_index_sidecar(document.path, stored_processing)
        artifact_index_path = _write_artifact_index_sidecar(document.path, stored_processing)
        embedding_index_path = None
        if embedding_provider:
            embedding_index_path = build_document_embedding_index(
                document,
                repository=repository,
                provider=embedding_provider,
            )
        repository.commit_document(document)
    except Exception:
        repository.remove_document_files(document)
        raise
    return IngestResult(
        status=IngestStatus.INGESTED,
        document=document,
        message=f"Ingested {document.document_type.value}: {document.field} / {document.title}",
        metadata={
            "source_path": str(request.source_path),
            "stored_path": str(document.path),
            "suffix": request.source_path.suffix.lower(),
            "tags": list(request.tags),
            "processing": {
                "source_text_length": pending_processing.text_length,
                "stored_text_length": stored_processing.text_length,
                "chunk_count": len(stored_processing.chunks),
                "artifact_count": len(stored_processing.artifacts),
                "processor": stored_processing.metadata["processor"],
                "details": stored_processing.metadata,
            },
            "search_text_path": str(search_text_path) if search_text_path else None,
            "chunk_index_path": str(chunk_index_path),
            "artifact_index_path": str(artifact_index_path),
            "embedding_index_path": str(embedding_index_path) if embedding_index_path else None,
            "chunks": [chunk.to_dict() for chunk in stored_processing.chunks],
            "artifacts": [artifact.to_dict() for artifact in stored_processing.artifacts],
        },
    )


def replace_text_document_content(
    document,
    content: str,
    *,
    repository: StudyRepository | None = None,
    pipeline: DocumentProcessingPipeline | None = None,
):
    repository = repository or StudyRepository()
    pipeline = pipeline or DocumentProcessingPipeline()
    suffix = document.path.suffix.lower()
    if suffix not in {".md", ".markdown"}:
        raise UnsupportedMaterialTypeError("Only Markdown documents can be edited.")
    if len(content) > 5_000_000:
        raise IngestInputError("Markdown content cannot exceed 5 MB.")

    temp_path = document.path.with_name(f".{document.path.stem}.edit{suffix}")
    try:
        _atomic_write_text(temp_path, content)
        processing = pipeline.process(
            ProcessingRequest(
                source_path=temp_path,
                metadata=document.metadata,
                document_id=document.id,
            )
        )
        _atomic_write_text(document.path, content)
        _write_search_text_sidecar(document.path, processing)
        _write_chunk_index_sidecar(document.path, processing)
        _write_artifact_index_sidecar(document.path, processing)
        embedding_path = document.path.with_suffix(document.path.suffix + ".embeddings.json")
        if embedding_path.exists():
            embedding_path.unlink()
        return repository.update_document_content_hash(document.id, file_sha256(document.path))
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _validate_ingest_request(request: IngestRequest) -> None:
    if not request.source_path.exists():
        raise MaterialNotFoundError(f"Paper material does not exist: {request.source_path}")
    if not request.field.strip():
        raise IngestInputError("field cannot be empty.")
    if request.source_path.suffix.lower() not in SUPPORTED_MATERIAL_SUFFIXES:
        raise UnsupportedMaterialTypeError(
            f"Unsupported material type '{request.source_path.suffix}'. "
            f"Currently supported: {', '.join(sorted(SUPPORTED_MATERIAL_SUFFIXES))}."
        )


def _write_search_text_sidecar(source_path: Path, processing_result: ProcessingResult) -> Path | None:
    if source_path.suffix.lower() in {".txt", ".md", ".markdown"}:
        return None
    text = "\n\n".join(chunk.text for chunk in processing_result.chunks).strip()
    if not text:
        return None
    sidecar_path = source_path.with_suffix(source_path.suffix + ".txt")
    _atomic_write_text(sidecar_path, text)
    return sidecar_path


def _write_chunk_index_sidecar(source_path: Path, processing_result: ProcessingResult) -> Path:
    sidecar_path = StudyRepository.chunk_sidecar_path(source_path)
    payload = [chunk.to_dict() for chunk in processing_result.chunks]
    _atomic_write_json(sidecar_path, payload)
    return sidecar_path


def _write_artifact_index_sidecar(source_path: Path, processing_result: ProcessingResult) -> Path:
    sidecar_path = StudyRepository.artifact_sidecar_path(source_path)
    payload = [artifact.to_dict() for artifact in processing_result.artifacts]
    _atomic_write_json(sidecar_path, payload)
    return sidecar_path


def _atomic_write_json(path: Path, payload) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)
