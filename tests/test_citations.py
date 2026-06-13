from pathlib import Path

from finals_agent.core.schemas import DocumentType, SearchResult
from finals_agent.data.citations import external_citation, format_evidence_line, local_citation
from finals_agent.data.external_search import ExternalPaper


def test_local_citation_includes_available_location_fields():
    result = SearchResult(
        document_id="doc-1",
        title="RAG Paper",
        document_type=DocumentType.PAPER,
        course="nlp",
        path=Path("paper.pdf"),
        snippet="retrieval evidence",
        score=0.9,
        chapter="retrieval",
        chunk_id="doc-1-3",
        page=5,
        section="2 Method",
        block_type="paragraph",
    )

    assert local_citation(result) == "[RAG Paper | section=2 Method | page=5 | chunk=doc-1-3]"
    assert result.to_dict()["citation"] == "[RAG Paper | section=2 Method | page=5 | chunk=doc-1-3]"
    assert "score=0.900" in format_evidence_line(result)


def test_external_citation_includes_index_date_and_url():
    paper = ExternalPaper(
        title="Related Paper",
        authors=("A. Researcher",),
        summary="summary",
        url="https://arxiv.org/abs/0000.00000",
        published="2024-01-01",
    )

    assert external_citation(paper, index=2) == "[R2: Related Paper | 2024-01-01 | https://arxiv.org/abs/0000.00000]"
