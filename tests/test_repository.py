from pathlib import Path

import json

import pytest

from finals_agent.core.exceptions import IngestInputError, ToolInputError, UnsupportedMaterialTypeError
from finals_agent.data.repository import StudyRepository
from finals_agent.core.schemas import DocumentType


def test_ingest_and_search_text_material(tmp_path: Path):
    source = tmp_path / "note.md"
    source.write_text("limit derivative lhopital rule", encoding="utf-8")

    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    document = repository.ingest(source, DocumentType.NOTE, "calculus")

    assert document.title == "note"
    results = repository.search("lhopital", course="calculus")
    assert results
    assert results[0].title == "note"
    assert results[0].score > 0
    assert results[0].field == "calculus"


def test_repository_reads_structured_artifacts(tmp_path: Path):
    from finals_agent.data.ingestion import build_ingest_request, ingest_material

    source = tmp_path / "paper.md"
    source.write_text("Figure 1: Overview\n\nscore = softmax(q k)", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, field="nlp", focus="rag"),
        repository=repository,
    )

    artifacts = repository.read_artifacts(result.document)

    assert len(artifacts) == 2
    assert artifacts[0].kind == "figure"
    assert artifacts[0].chunk_id
    assert artifacts[0].metadata["field"] == "nlp"
    assert artifacts[0].metadata["focus"] == "rag"


def test_repository_accepts_field_focus_aliases(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("retrieval grounding", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    document = repository.ingest(source, DocumentType.PAPER, field="nlp")

    documents = repository.list_documents(field="nlp")
    results = repository.search("retrieval", field="nlp")

    assert document.field == "nlp"
    assert documents[0].id == document.id
    assert results[0].field == "nlp"


def test_ingest_rejects_unsupported_file_type(tmp_path: Path):
    source = tmp_path / "note.docx"
    source.write_bytes(b"docx")

    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    with pytest.raises(UnsupportedMaterialTypeError):
        repository.ingest(source, DocumentType.NOTE, "calculus")


def test_repository_remove_document_deletes_index_and_files(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("retrieval grounding", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    document = repository.ingest(source, DocumentType.PAPER, field="nlp")
    stored_path = document.path

    removed = repository.remove_document(document.id)

    assert removed.id == document.id
    assert repository.list_documents() == []
    assert not stored_path.exists()


def test_repository_updates_document_organization(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("retrieval grounding", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    document = repository.ingest(source, DocumentType.PAPER, field="nlp")

    categorized = repository.update_document_organization(
        document.id,
        pinned=True,
        category="推理加速",
        update_category=True,
    )
    archived = repository.update_document_organization(document.id, archived=True)
    restored = repository.update_document_organization(document.id, archived=False, pinned=True)

    assert categorized.pinned is True
    assert categorized.category == "推理加速"
    assert archived.archived is True
    assert archived.pinned is False
    assert restored.archived is False
    assert restored.pinned is True
    assert repository.get_document(document.id).category == "推理加速"


def test_repository_reads_legacy_index_without_organization_fields(tmp_path: Path):
    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps(
            [
                {
                    "id": "legacy",
                    "title": "Legacy",
                    "document_type": "paper",
                    "field": "nlp",
                    "path": str(tmp_path / "legacy.pdf"),
                }
            ]
        ),
        encoding="utf-8",
    )
    repository = StudyRepository(index_path=index_path, raw_data_dir=tmp_path / "raw")

    document = repository.get_document("legacy")

    assert document.pinned is False
    assert document.archived is False
    assert document.category is None


def test_repository_rejects_duplicate_material_by_hash(tmp_path: Path):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("same content", encoding="utf-8")
    second.write_text("same content", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    repository.ingest(first, DocumentType.PAPER, field="nlp")

    with pytest.raises(IngestInputError, match="Duplicate material"):
        repository.ingest(second, DocumentType.PAPER, field="nlp")


def test_repository_rejects_overlong_search_query(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    with pytest.raises(ToolInputError, match="500"):
        repository.search("x" * 501)
