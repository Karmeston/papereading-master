from pathlib import Path

from finals_agent.core.schemas import DocumentType
from finals_agent.data.embeddings import (
    DisabledEmbeddingProvider,
    EmbeddingIndexStore,
    HashEmbeddingProvider,
    build_embedding_provider,
    build_document_embedding_index,
)
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository


def test_build_document_embedding_index_writes_cached_vectors(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("retrieval augmented generation", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, "nlp"),
        repository=repository,
    )

    path = build_document_embedding_index(
        result.document,
        repository=repository,
        provider=HashEmbeddingProvider(dimensions=8),
    )

    assert path is not None
    assert path.exists()
    records = EmbeddingIndexStore(repository).read(result.document)
    assert len(records) == 1
    assert records[0].chunk_id == result.metadata["chunks"][0]["chunk_id"]
    assert len(records[0].vector) == 8
    assert records[0].metadata["text_preview"]


def test_build_document_embedding_index_returns_none_when_disabled(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("retrieval augmented generation", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, "nlp"),
        repository=repository,
    )

    path = build_document_embedding_index(
        result.document,
        repository=repository,
        provider=DisabledEmbeddingProvider(),
    )

    assert path is None


def test_ingest_material_can_build_embedding_index_when_provider_is_supplied(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("retrieval augmented generation", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, "nlp"),
        repository=repository,
        embedding_provider=HashEmbeddingProvider(dimensions=8),
    )

    assert result.metadata["embedding_index_path"].endswith(".embeddings.json")
    assert Path(result.metadata["embedding_index_path"]).exists()


def test_build_embedding_provider_does_not_use_deepseek_settings():
    class Settings:
        provider = "deepseek"
        model = "deepseek-chat"
        api_key = "sk-test"
        base_url = "https://api.deepseek.com"

    provider = build_embedding_provider(Settings())

    assert isinstance(provider, DisabledEmbeddingProvider)
    assert provider.available is False
