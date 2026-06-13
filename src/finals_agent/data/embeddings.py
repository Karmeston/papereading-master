from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import json
import math
import uuid
from pathlib import Path
from typing import Any

from finals_agent.core.exceptions import RepositoryIndexError
from finals_agent.core.schemas import DocumentChunk, StudyDocument
from finals_agent.data.repository import StudyRepository


DEFAULT_LOCAL_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"


@dataclass(frozen=True)
class EmbeddingRecord:
    document_id: str
    chunk_id: str
    text_hash: str
    vector: tuple[float, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "text_hash": self.text_hash,
            "vector": list(self.vector),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EmbeddingRecord":
        return cls(
            document_id=payload["document_id"],
            chunk_id=payload["chunk_id"],
            text_hash=payload["text_hash"],
            vector=tuple(float(item) for item in payload["vector"]),
            metadata=payload.get("metadata") or {},
        )


class EmbeddingProvider(ABC):
    model_name: str

    @property
    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        raise NotImplementedError


class DisabledEmbeddingProvider(EmbeddingProvider):
    model_name = "disabled"

    @property
    def available(self) -> bool:
        return False

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        return []


class LocalSentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str = DEFAULT_LOCAL_EMBEDDING_MODEL, device: str | None = None):
        self.model_name = model_name
        self.device = device
        self._model = None
        self._load_error: str | None = None

    @property
    def available(self) -> bool:
        try:
            self._load_model()
            return True
        except ImportError as exc:
            self._load_error = str(exc)
            return False

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []
        model = self._load_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [tuple(float(value) for value in vector) for vector in vectors]

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "Local embeddings require the optional 'sentence-transformers' package. "
                "Install with: pip install -e .[embeddings]"
            ) from exc
        kwargs = {"device": self.device} if self.device else {}
        self._model = SentenceTransformer(self.model_name, **kwargs)
        return self._model


class HashEmbeddingProvider(EmbeddingProvider):
    """Small deterministic provider for tests and offline smoke checks."""

    def __init__(self, dimensions: int = 32):
        self.model_name = "hash-embedding"
        self.dimensions = dimensions

    @property
    def available(self) -> bool:
        return True

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [_normalize(_hash_vector(text, self.dimensions)) for text in texts]


class EmbeddingIndexStore:
    def __init__(self, repository: StudyRepository | None = None):
        self.repository = repository or StudyRepository()

    def index_path(self, document: StudyDocument) -> Path:
        return document.path.with_suffix(document.path.suffix + ".embeddings.json")

    def read(self, document: StudyDocument) -> list[EmbeddingRecord]:
        path = self.index_path(document)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return [EmbeddingRecord.from_dict(item) for item in payload.get("records", [])]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RepositoryIndexError(f"Cannot read embedding index: {path}") from exc

    def write(
        self,
        document: StudyDocument,
        records: list[EmbeddingRecord],
        provider: EmbeddingProvider,
    ) -> Path:
        path = self.index_path(document)
        payload = {
            "document_id": document.id,
            "model": provider.model_name,
            "records": [record.to_dict() for record in records],
        }
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
        return path


def build_embedding_provider(settings=None) -> EmbeddingProvider:
    if settings is None:
        from finals_agent.core.config import load_settings

        settings = load_settings(validate=False).embeddings
    provider = getattr(settings, "provider", "disabled")
    if provider == "local":
        return LocalSentenceTransformerProvider(
            model_name=getattr(settings, "model", DEFAULT_LOCAL_EMBEDDING_MODEL),
            device=getattr(settings, "device", None),
        )
    return DisabledEmbeddingProvider()


def build_document_embedding_index(
    document: StudyDocument,
    repository: StudyRepository | None = None,
    provider: EmbeddingProvider | None = None,
    force: bool = False,
) -> Path | None:
    repository = repository or StudyRepository()
    provider = provider or DisabledEmbeddingProvider()
    if not provider.available:
        return None

    store = EmbeddingIndexStore(repository)
    chunks = repository.read_chunks(document)
    if not chunks:
        return None

    existing = {record.chunk_id: record for record in store.read(document)}
    records: list[EmbeddingRecord] = []
    pending_chunks: list[DocumentChunk] = []
    for chunk in chunks:
        text_hash = hash_text(chunk.text)
        previous = existing.get(chunk.chunk_id)
        if previous and previous.text_hash == text_hash and not force:
            records.append(previous)
            continue
        pending_chunks.append(chunk)

    if pending_chunks:
        vectors = provider.embed_texts([chunk.text for chunk in pending_chunks])
        for chunk, vector in zip(pending_chunks, vectors, strict=True):
            records.append(
                EmbeddingRecord(
                    document_id=document.id,
                    chunk_id=chunk.chunk_id,
                    text_hash=hash_text(chunk.text),
                    vector=tuple(vector),
                    metadata={
                        **chunk.metadata,
                        "text_preview": " ".join(chunk.text.split())[:180],
                    },
                )
            )

    records.sort(key=lambda item: item.metadata.get("chunk_index", 0))
    return store.write(document, records, provider)


def build_repository_embedding_index(
    repository: StudyRepository | None = None,
    provider: EmbeddingProvider | None = None,
    force: bool = False,
) -> list[Path]:
    repository = repository or StudyRepository()
    paths = []
    for document in repository.list_documents():
        path = build_document_embedding_index(document, repository=repository, provider=provider, force=force)
        if path:
            paths.append(path)
    return paths


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _hash_vector(text: str, dimensions: int) -> tuple[float, ...]:
    vector = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    return tuple(vector)


def _normalize(vector: tuple[float, ...]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return tuple(value / norm for value in vector)
