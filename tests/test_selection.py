from pathlib import Path

import pytest

from finals_agent.core.exceptions import ToolInputError
from finals_agent.core.schemas import DocumentType
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository
from finals_agent.data.selection import DocumentClarificationNeeded, select_document


def test_select_document_rejects_ambiguous_partial_title(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    for title in ("RAG Survey", "RAG System"):
        source = tmp_path / f"{title}.md"
        source.write_text(f"retrieval {title}", encoding="utf-8")
        ingest_material(
            build_ingest_request(source, DocumentType.PAPER, "nlp", title=title),
            repository=repository,
        )

    with pytest.raises(ToolInputError, match="multiple papers"):
        select_document(repository, title="RAG", field="nlp")

    with pytest.raises(DocumentClarificationNeeded) as exc:
        select_document(repository, title="RAG", field="nlp")
    metadata = exc.value.to_metadata()
    assert metadata["clarification_needed"] is True
    assert len(metadata["candidates"]) == 2
    assert "document_id" in metadata["clarification_question"]


def test_select_document_exact_title_wins_over_partial_matches(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    exact = tmp_path / "rag.md"
    exact.write_text("retrieval exact", encoding="utf-8")
    longer = tmp_path / "rag_survey.md"
    longer.write_text("retrieval survey", encoding="utf-8")
    ingest_material(
        build_ingest_request(exact, DocumentType.PAPER, "nlp", title="RAG"),
        repository=repository,
    )
    ingest_material(
        build_ingest_request(longer, DocumentType.PAPER, "nlp", title="RAG Survey"),
        repository=repository,
    )

    document = select_document(repository, title="RAG", field="nlp")

    assert document.title == "RAG"
