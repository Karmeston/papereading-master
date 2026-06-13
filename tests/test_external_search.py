from pathlib import Path

import pytest

from finals_agent.core.exceptions import ExternalSearchError, ToolInputError
from finals_agent.core.schemas import DocumentType
from finals_agent.data.external_search import ArxivPaperSearch
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository
from finals_agent.data.workflows import PaperReadingWorkflow


class FailingExternalSearch:
    def search(self, query: str, limit: int = 5):
        raise ExternalSearchError("arXiv unavailable")


def test_arxiv_search_rejects_empty_query():
    with pytest.raises(ToolInputError):
        ArxivPaperSearch().search(" ")


def test_arxiv_search_rejects_overlong_query():
    with pytest.raises(ToolInputError, match="256"):
        ArxivPaperSearch().search("x" * 257)


def test_arxiv_search_returns_empty_for_zero_limit():
    assert ArxivPaperSearch().search("retrieval", limit=0) == ()


def test_read_workflow_preserves_local_evidence_when_related_search_fails(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("Abstract\n\nRetrieval method contribution.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(source, DocumentType.PAPER, "nlp", title="Target"),
        repository=repository,
    )
    workflow = PaperReadingWorkflow(repository=repository, external_search=FailingExternalSearch())

    data = workflow.read(title="Target", field="nlp", related_limit=2).to_dict()["data"]

    assert data["evidence"]
    assert data["related_papers"] == []
    assert data["related_papers_error"] == "arXiv unavailable"
    assert any("arXiv unavailable" in item for item in data["next_actions"])
