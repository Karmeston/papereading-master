from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
import math
import re

from finals_agent.core.exceptions import ToolInputError
from finals_agent.core.schemas import DocumentChunk, SearchRequest, SearchResponse, SearchResult, StudyDocument
from finals_agent.data.embeddings import DisabledEmbeddingProvider, EmbeddingIndexStore, EmbeddingProvider, cosine
from finals_agent.data.repository import StudyRepository


class Retriever(ABC):
    @abstractmethod
    def search(self, request: SearchRequest) -> SearchResponse:
        raise NotImplementedError


class KeywordRetriever(Retriever):
    """Keyword retriever backed by StudyRepository."""

    def __init__(self, repository: StudyRepository | None = None):
        self.repository = repository or StudyRepository()

    def search(self, request: SearchRequest) -> SearchResponse:
        _validate_search_request(request)
        results = self.repository.search(
            query=request.query,
            field=request.field,
            document_id=request.document_id,
            document_type=request.document_type,
            focus=request.focus,
            limit=request.limit,
        )
        return _response(self.__class__.__name__, request, results)


class VectorRetriever(Retriever):
    """Offline lexical-vector retriever over persisted document chunks.

    This is not a substitute for embedding models. It provides a dependency-free
    semantic-ish baseline by comparing token and character n-gram vectors.
    """

    def __init__(self, repository: StudyRepository | None = None):
        self.repository = repository or StudyRepository()

    def search(self, request: SearchRequest) -> SearchResponse:
        _validate_search_request(request)
        query_vector = _vectorize(request.query)
        results = []
        for document, chunk in _iter_candidate_chunks(self.repository, request):
            score = _cosine(query_vector, _vectorize(chunk.text))
            if score <= 0:
                continue
            results.append(_search_result_from_chunk(document, chunk, score))

        results.sort(key=lambda item: item.score, reverse=True)
        return _response(self.__class__.__name__, request, results[: request.limit])


class EmbeddingRetriever(Retriever):
    """Retriever over cached local embedding indexes."""

    def __init__(
        self,
        repository: StudyRepository | None = None,
        provider: EmbeddingProvider | None = None,
    ):
        self.repository = repository or StudyRepository()
        self.provider = provider or DisabledEmbeddingProvider()
        self.store = EmbeddingIndexStore(self.repository)

    def search(self, request: SearchRequest) -> SearchResponse:
        _validate_search_request(request)
        metadata = {
            "embedding_provider": self.provider.__class__.__name__,
            "embedding_model": self.provider.model_name,
            "embedding_available": self.provider.available,
        }
        if not self.provider.available:
            return _response(self.__class__.__name__, request, [], extra_metadata=metadata)

        query_vectors = self.provider.embed_texts([request.query])
        if not query_vectors:
            return _response(self.__class__.__name__, request, [], extra_metadata=metadata)

        query_vector = query_vectors[0]
        documents = self.repository.list_documents(field=request.field)
        if request.document_id:
            documents = [doc for doc in documents if doc.id == request.document_id]
        if request.document_type:
            documents = [doc for doc in documents if doc.document_type == request.document_type]
        if request.focus:
            documents = [doc for doc in documents if doc.focus == request.focus]

        results = []
        for document in documents:
            chunks_by_id = {chunk.chunk_id: chunk for chunk in self.repository.read_chunks(document)}
            for record in self.store.read(document):
                chunk = chunks_by_id.get(record.chunk_id)
                if not chunk:
                    continue
                score = cosine(query_vector, record.vector)
                if score <= 0:
                    continue
                results.append(_search_result_from_chunk(document, chunk, score))

        results.sort(key=lambda item: item.score, reverse=True)
        return _response(self.__class__.__name__, request, results[: request.limit], extra_metadata=metadata)


class HybridRetriever(Retriever):
    """Combine keyword precision with lexical-vector recall."""

    def __init__(
        self,
        repository: StudyRepository | None = None,
        keyword_weight: float = 0.55,
        vector_weight: float = 0.30,
        embedding_weight: float = 0.15,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.repository = repository or StudyRepository()
        self.keyword = KeywordRetriever(self.repository)
        self.vector = VectorRetriever(self.repository)
        self.embedding = EmbeddingRetriever(self.repository, provider=embedding_provider)
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight
        self.embedding_weight = embedding_weight

    def search(self, request: SearchRequest) -> SearchResponse:
        _validate_search_request(request)
        expanded_request = SearchRequest(
            query=request.query,
            field=request.field,
            document_id=request.document_id,
            document_type=request.document_type,
            focus=request.focus,
            limit=max(request.limit * 3, request.limit),
        )
        keyword_results = self.keyword.search(expanded_request).results
        vector_results = self.vector.search(expanded_request).results
        embedding_response = self.embedding.search(expanded_request)
        embedding_results = embedding_response.results
        merged = _merge_ranked_results(
            keyword_results,
            vector_results,
            embedding_results,
            keyword_weight=self.keyword_weight,
            vector_weight=self.vector_weight,
            embedding_weight=self.embedding_weight,
        )
        results = merged[: request.limit]
        response = _response(self.__class__.__name__, request, results)
        return SearchResponse(
            request=response.request,
            results=response.results,
            metadata={
                **response.metadata,
                "keyword_count": len(keyword_results),
                "vector_count": len(vector_results),
                "embedding_count": len(embedding_results),
                "keyword_weight": self.keyword_weight,
                "vector_weight": self.vector_weight,
                "embedding_weight": self.embedding_weight,
                "embedding_available": embedding_response.metadata.get("embedding_available", False),
                "embedding_model": embedding_response.metadata.get("embedding_model"),
            },
        )


def _validate_search_request(request: SearchRequest) -> None:
    if not request.query.strip():
        raise ToolInputError("query cannot be empty.")
    if len(request.query) > 500:
        raise ToolInputError("query must be 500 characters or fewer.")
    if request.limit < 1:
        raise ToolInputError("limit must be at least 1.")


def _response(
    retriever_name: str,
    request: SearchRequest,
    results: list[SearchResult],
    extra_metadata: dict | None = None,
) -> SearchResponse:
    return SearchResponse(
        request=request,
        results=tuple(results),
        metadata={
            "retriever": retriever_name,
            "query": request.query,
            "document_id": request.document_id,
            "field": request.field,
            "course": request.course,
            "document_type": request.document_type.value if request.document_type else None,
            "focus": request.focus,
            "chapter": request.chapter,
            "limit": request.limit,
            "count": len(results),
            **(extra_metadata or {}),
        },
    )


def _iter_candidate_chunks(repository: StudyRepository, request: SearchRequest):
    documents = repository.list_documents(field=request.field)
    if request.document_id:
        documents = [doc for doc in documents if doc.id == request.document_id]
    if request.document_type:
        documents = [doc for doc in documents if doc.document_type == request.document_type]
    if request.focus:
        documents = [doc for doc in documents if doc.focus == request.focus]

    for document in documents:
        chunks = repository.read_chunks(document)
        if not chunks:
            text = repository.read_searchable_text(document)
            if not text:
                continue
            chunks = (
                DocumentChunk(
                    document_id=document.id,
                    chunk_id=f"{document.id}-fulltext",
                    text=text,
                    metadata={
                        "chunk_index": 0,
                        "page": None,
                        "section": document.focus,
                        "block_type": "paragraph",
                    },
                ),
            )
        for chunk in chunks:
            yield document, chunk


def _search_result_from_chunk(document: StudyDocument, chunk: DocumentChunk, score: float) -> SearchResult:
    return SearchResult(
        document_id=document.id,
        title=document.title,
        document_type=document.document_type,
        course=document.field,
        path=document.path,
        snippet=_snippet(chunk.text),
        score=float(score),
        chapter=document.focus,
        source=document.source,
        tags=document.tags,
        chunk_id=chunk.chunk_id,
        page=chunk.metadata.get("page"),
        section=chunk.metadata.get("section"),
        block_type=chunk.metadata.get("block_type"),
    )


TOKEN_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+", re.I)


def _vectorize(text: str) -> Counter[str]:
    lowered = text.lower()
    tokens = TOKEN_RE.findall(lowered)
    vector: Counter[str] = Counter(tokens)
    for token in tokens:
        if len(token) >= 4 and token.isascii():
            vector.update(token[index : index + 3] for index in range(len(token) - 2))
        elif len(token) >= 2:
            vector.update(token[index : index + 2] for index in range(len(token) - 1))
    return vector


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    dot = sum(left[key] * right[key] for key in common)
    if dot == 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _merge_ranked_results(
    keyword_results: tuple[SearchResult, ...],
    vector_results: tuple[SearchResult, ...],
    embedding_results: tuple[SearchResult, ...],
    keyword_weight: float,
    vector_weight: float,
    embedding_weight: float = 0.0,
) -> list[SearchResult]:
    merged: dict[tuple[str, str | None], SearchResult] = {}
    scores: dict[tuple[str, str | None], float] = {}

    for result in keyword_results:
        key = _result_key(result)
        _merge_result(merged, scores, key, result, keyword_weight * _normalized_score(result.score, keyword_results))

    for result in vector_results:
        key = _result_key(result)
        _merge_result(merged, scores, key, result, vector_weight * _normalized_score(result.score, vector_results))

    for result in embedding_results:
        key = _result_key(result)
        _merge_result(merged, scores, key, result, embedding_weight * _normalized_score(result.score, embedding_results))

    ranked = []
    for key, result in merged.items():
        ranked.append(
            SearchResult(
                document_id=result.document_id,
                title=result.title,
                document_type=result.document_type,
                course=result.course,
                path=result.path,
                snippet=result.snippet,
                score=scores[key],
                chapter=result.chapter,
                source=result.source,
                tags=result.tags,
                chunk_id=result.chunk_id,
                page=result.page,
                section=result.section,
                block_type=result.block_type,
            )
        )
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


def _merge_result(
    merged: dict[tuple[str, str | None], SearchResult],
    scores: dict[tuple[str, str | None], float],
    key: tuple[str, str | None],
    result: SearchResult,
    contribution: float,
) -> None:
    if key not in merged or result.score > merged[key].score:
        merged[key] = result
    scores[key] = scores.get(key, 0.0) + contribution


def _normalized_score(score: float, results: tuple[SearchResult, ...]) -> float:
    scores = [item.score for item in results]
    if not scores:
        return 0.0
    min_score = min(scores)
    max_score = max(scores)
    if max_score <= min_score:
        return 1.0 if score > 0 else 0.0
    return (score - min_score) / (max_score - min_score)


def _result_key(result: SearchResult) -> tuple[str, str | None]:
    chunk_key = result.chunk_id
    if not chunk_key or chunk_key.endswith("-fulltext"):
        chunk_key = "__document__"
    return result.document_id, chunk_key


def _snippet(text: str, length: int = 180) -> str:
    return " ".join(text.split())[:length]
