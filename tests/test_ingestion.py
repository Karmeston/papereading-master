from pathlib import Path

import json

import pytest

from finals_agent.core.exceptions import IngestInputError, UnsupportedMaterialTypeError
from finals_agent.data.ingestion import build_ingest_request, ingest_material, replace_text_document_content
from finals_agent.data.repository import StudyRepository
from finals_agent.core.schemas import DocumentChunk, DocumentType, IngestStatus, ProcessingResult


def test_ingest_material_records_metadata(tmp_path: Path):
    source = tmp_path / "lecture.md"
    source.write_text("derivative chain rule", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    result = ingest_material(
        build_ingest_request(
            source_path=source,
            document_type=DocumentType.NOTE,
            course="calculus",
            title="Lecture 1",
            chapter="derivatives",
            source="classroom",
            tags=("important", "week-1"),
        ),
        repository=repository,
    )

    assert result.status == IngestStatus.INGESTED
    assert result.document is not None
    assert result.document.title == "Lecture 1"
    assert result.document.chapter == "derivatives"
    assert result.document.source == "classroom"
    assert result.document.tags == ("important", "week-1")
    assert result.metadata["processing"]["processor"] == "TextProcessor"
    assert result.metadata["processing"]["chunk_count"] == 1
    assert result.metadata["processing"]["artifact_count"] == 0
    assert result.metadata["chunk_index_path"].endswith(".md.chunks.json")
    assert result.metadata["artifact_index_path"].endswith(".md.artifacts.json")
    assert Path(result.metadata["chunk_index_path"]).exists()
    assert Path(result.metadata["artifact_index_path"]).exists()
    assert result.metadata["chunks"][0]["document_id"] == result.document.id
    assert result.metadata["chunks"][0]["metadata"]["section"] == "derivatives"
    assert result.metadata["chunks"][0]["metadata"]["block_type"] == "paragraph"
    assert result.document.field == "calculus"
    assert result.document.focus == "derivatives"

    documents = repository.list_documents()
    assert documents[0].chapter == "derivatives"
    assert documents[0].tags == ("important", "week-1")


def test_ingest_material_rejects_empty_course(tmp_path: Path):
    source = tmp_path / "lecture.md"
    source.write_text("content", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    with pytest.raises(IngestInputError):
        ingest_material(
            build_ingest_request(
                source_path=source,
                document_type=DocumentType.NOTE,
                course=" ",
            ),
            repository=repository,
        )


def test_ingest_material_rejects_unsupported_suffix(tmp_path: Path):
    source = tmp_path / "lecture.docx"
    source.write_bytes(b"docx")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    with pytest.raises(UnsupportedMaterialTypeError):
        ingest_material(
            build_ingest_request(
                source_path=source,
                document_type=DocumentType.NOTE,
                course="calculus",
            ),
            repository=repository,
        )


def test_ingest_material_does_not_commit_index_when_stored_processing_fails(tmp_path: Path):
    class FailingStoredPipeline:
        def process(self, request):
            if repository.raw_data_dir in request.source_path.parents:
                raise IngestInputError("stored processing failed")
            return ProcessingResult(
                source_path=request.source_path,
                chunks=(
                    DocumentChunk(
                        document_id=request.document_id,
                        chunk_id="pending-0",
                        text="content",
                        metadata={},
                    ),
                ),
                text_length=7,
                metadata={"processor": "FailingStoredPipeline"},
                artifacts=(),
            )

    source = tmp_path / "lecture.md"
    source.write_text("content", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    with pytest.raises(IngestInputError, match="stored processing failed"):
        ingest_material(
            build_ingest_request(source, DocumentType.NOTE, course="calculus"),
            repository=repository,
            pipeline=FailingStoredPipeline(),
        )

    assert repository.list_documents() == []
    assert not list(repository.raw_data_dir.rglob("*.md"))


def test_ingest_material_accepts_text_pdf(tmp_path: Path):
    from tests.test_processors import _write_text_pdf

    source = tmp_path / "lecture.pdf"
    _write_text_pdf(source, "Lhopital rule limit practice")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    result = ingest_material(
        build_ingest_request(
            source_path=source,
                document_type=DocumentType.PAPER,
            course="calculus",
            chapter="limits",
        ),
        repository=repository,
    )

    assert result.status == IngestStatus.INGESTED
    assert result.document is not None
    assert result.document.path.suffix == ".pdf"
    assert result.metadata["processing"]["processor"] == "PdfProcessor"
    assert result.metadata["processing"]["details"]["page_count"] == 1
    assert result.metadata["processing"]["details"]["image_count"] == 0
    assert "Lhopital" in result.metadata["chunks"][0]["text"]
    assert result.metadata["chunks"][0]["metadata"]["page"] == 1
    assert result.metadata["search_text_path"].endswith(".pdf.txt")
    assert result.metadata["chunk_index_path"].endswith(".pdf.chunks.json")
    assert result.metadata["artifact_index_path"].endswith(".pdf.artifacts.json")
    assert Path(result.metadata["search_text_path"]).exists()
    assert Path(result.metadata["chunk_index_path"]).exists()
    assert Path(result.metadata["artifact_index_path"]).exists()

    search_results = repository.search("Lhopital", course="calculus")
    assert search_results
    assert search_results[0].title == "lecture"


def test_ingest_material_accepts_code_files(tmp_path: Path):
    source = tmp_path / "agent.py"
    source.write_text("def retrieve(query):\n    return query\n", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    result = ingest_material(
        build_ingest_request(source, DocumentType.CODE, field="agents"),
        repository=repository,
    )

    assert result.document.document_type == DocumentType.CODE
    assert result.document.path.parent.name == "code"
    assert repository.search("retrieve", document_id=result.document.id)


def test_ingest_material_accepts_jupyter_notebook(tmp_path: Path):
    source = tmp_path / "analysis.ipynb"
    source.write_text(
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "source": ["# Retrieval experiment"]},
                    {
                        "cell_type": "code",
                        "execution_count": 1,
                        "source": ["def retrieve(query):\n", "    return query\n"],
                        "outputs": [],
                    },
                ],
                "metadata": {"kernelspec": {"language": "python"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    result = ingest_material(
        build_ingest_request(source, DocumentType.CODE, field="agents"),
        repository=repository,
    )

    assert result.metadata["processing"]["processor"] == "NotebookProcessor"
    assert result.metadata["processing"]["details"]["code_cell_count"] == 1
    assert result.metadata["processing"]["details"]["markdown_cell_count"] == 1
    assert repository.search("retrieve", document_id=result.document.id)


def test_replace_markdown_content_rebuilds_search_index(tmp_path: Path):
    source = tmp_path / "notes.md"
    source.write_text("# Old\n\nobsolete phrase", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, field="paper"),
        repository=repository,
    )
    embedding_path = result.document.path.with_suffix(result.document.path.suffix + ".embeddings.json")
    embedding_path.write_text("{}", encoding="utf-8")

    updated = replace_text_document_content(
        result.document,
        "# New\n\nfresh searchable phrase",
        repository=repository,
    )

    assert updated.content_hash != result.document.content_hash
    assert repository.search("fresh", document_id=result.document.id)
    assert not repository.search("obsolete", document_id=result.document.id)
    assert not embedding_path.exists()
