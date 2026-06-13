from pathlib import Path

import pytest

from finals_agent.core.exceptions import ToolInputError
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository
from finals_agent.data.embeddings import HashEmbeddingProvider, build_document_embedding_index
from finals_agent.data.retrievers import EmbeddingRetriever, HybridRetriever, KeywordRetriever, VectorRetriever, _normalized_score
from finals_agent.core.schemas import DocumentType, SearchRequest, SearchResult


def test_keyword_retriever_returns_search_response(tmp_path: Path):
    source = tmp_path / "limits.md"
    source.write_text("limit derivative lhopital rule", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(
            source_path=source,
            document_type=DocumentType.NOTE,
            course="calculus",
            chapter="limits",
        ),
        repository=repository,
    )

    response = KeywordRetriever(repository).search(
        SearchRequest(query="lhopital", course="calculus", chapter="limits", limit=3)
    )

    assert response.count == 1
    assert response.results[0].title == "limits"
    assert response.metadata["retriever"] == "KeywordRetriever"
    assert response.metadata["chapter"] == "limits"


def test_keyword_retriever_filters_by_chapter(tmp_path: Path):
    limits = tmp_path / "limits.md"
    limits.write_text("lhopital rule limits", encoding="utf-8")
    derivatives = tmp_path / "derivatives.md"
    derivatives.write_text("lhopital rule derivatives", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(limits, DocumentType.NOTE, "calculus", chapter="limits"),
        repository=repository,
    )
    ingest_material(
        build_ingest_request(derivatives, DocumentType.NOTE, "calculus", chapter="derivatives"),
        repository=repository,
    )

    response = KeywordRetriever(repository).search(
        SearchRequest(query="lhopital", course="calculus", chapter="derivatives")
    )

    assert response.count == 1
    assert response.results[0].title == "derivatives"
    assert response.results[0].chapter == "derivatives"


def test_keyword_retriever_rejects_empty_query(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    with pytest.raises(ToolInputError):
        KeywordRetriever(repository).search(SearchRequest(query=" "))


def test_retriever_rejects_overlong_query(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    with pytest.raises(ToolInputError, match="500"):
        HybridRetriever(repository).search(SearchRequest(query="x" * 501))


def test_vector_retriever_searches_persisted_chunks(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text(
        "Abstract\n\nRetrieval augmented generation grounds answers in external documents.",
        encoding="utf-8",
    )
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(
            source,
            DocumentType.PAPER,
            "nlp",
            chapter="retrieval augmented generation",
        ),
        repository=repository,
    )

    response = VectorRetriever(repository).search(
        SearchRequest(query="retrieval grounding", field="nlp", limit=3)
    )

    assert response.count == 1
    assert response.metadata["retriever"] == "VectorRetriever"
    assert response.results[0].chunk_id is not None
    assert response.results[0].section == "Abstract"
    assert response.request.field == "nlp"


def test_hybrid_retriever_merges_keyword_and_vector_results(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("Retrieval augmented generation improves factual grounding.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(source, DocumentType.PAPER, "nlp"),
        repository=repository,
    )

    response = HybridRetriever(repository).search(SearchRequest(query="retrieval grounding", course="nlp"))

    assert response.count == 1
    assert response.metadata["retriever"] == "HybridRetriever"
    assert response.metadata["keyword_count"] == 1
    assert response.metadata["vector_count"] == 1
    assert response.metadata["embedding_count"] == 0
    assert response.metadata["embedding_available"] is False
    assert response.results[0].block_type in {"section", "paragraph"}


def test_embedding_retriever_searches_cached_embedding_index(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("Retrieval augmented generation improves factual grounding.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, "nlp"),
        repository=repository,
    )
    provider = HashEmbeddingProvider(dimensions=16)
    build_document_embedding_index(result.document, repository=repository, provider=provider)

    response = EmbeddingRetriever(repository, provider=provider).search(
        SearchRequest(query="retrieval generation", course="nlp")
    )

    assert response.count == 1
    assert response.metadata["retriever"] == "EmbeddingRetriever"
    assert response.metadata["embedding_available"] is True
    assert response.metadata["embedding_model"] == "hash-embedding"
    assert response.results[0].chunk_id is not None


def test_hybrid_retriever_includes_embedding_scores_when_available(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("Retrieval augmented generation improves factual grounding.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, "nlp"),
        repository=repository,
    )
    provider = HashEmbeddingProvider(dimensions=16)
    build_document_embedding_index(result.document, repository=repository, provider=provider)

    response = HybridRetriever(repository, embedding_provider=provider).search(
        SearchRequest(query="retrieval generation", course="nlp")
    )

    assert response.count == 1
    assert response.metadata["embedding_available"] is True
    assert response.metadata["embedding_count"] == 1
    assert response.metadata["embedding_weight"] > 0


def test_normalized_score_uses_min_max_distribution(tmp_path: Path):
    path = tmp_path / "paper.md"
    results = tuple(
        SearchResult(
            document_id=f"doc-{index}",
            title=f"Paper {index}",
            document_type=DocumentType.PAPER,
            course="nlp",
            path=path,
            snippet="snippet",
            score=score,
        )
        for index, score in enumerate((1.0, 3.0, 50.0), start=1)
    )

    assert _normalized_score(1.0, results) == 0.0
    assert round(_normalized_score(3.0, results), 3) == 0.041
    assert _normalized_score(50.0, results) == 1.0
