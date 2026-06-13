from __future__ import annotations

from finals_agent.core.exceptions import MaterialNotFoundError, ToolInputError
from finals_agent.core.schemas import DocumentType, SearchRequest, StudyDocument
from finals_agent.data.repository import StudyRepository
from finals_agent.data.retrievers import Retriever


class DocumentClarificationNeeded(ToolInputError):
    def __init__(self, message: str, candidates: list[StudyDocument], question: str):
        super().__init__(message)
        self.candidates = tuple(candidates)
        self.question = question

    def to_metadata(self) -> dict:
        return {
            "clarification_needed": True,
            "clarification_question": self.question,
            "candidates": [doc.to_dict() for doc in self.candidates],
        }


def select_document(
    repository: StudyRepository,
    document_id: str | None = None,
    title: str | None = None,
    query: str | None = None,
    field: str | None = None,
    document_type: DocumentType | None = DocumentType.PAPER,
    retriever: Retriever | None = None,
) -> StudyDocument:
    if document_id:
        document = repository.get_document(document_id)
        if field and document.field != field:
            raise MaterialNotFoundError(f"Document {document_id} is not in field '{field}'.")
        if document_type and document.document_type != document_type:
            raise MaterialNotFoundError(f"Document {document_id} is not a {document_type.value}.")
        return document

    documents = repository.list_documents(field=field)
    if document_type:
        documents = [doc for doc in documents if doc.document_type == document_type]

    if title:
        return _select_by_title(documents, title)

    if query:
        if retriever:
            matches = list(
                retriever.search(
                    SearchRequest(
                        query=query,
                        field=field,
                        document_type=document_type,
                        limit=3,
                    )
                ).results
            )
        else:
            matches = repository.search(
                query=query,
                field=field,
                document_type=document_type,
                limit=3,
            )
        if matches:
            document_ids = _unique_ids(result.document_id for result in matches)
            if len(document_ids) == 1:
                return repository.get_document(document_ids[0])
            candidates = [repository.get_document(item) for item in document_ids]
            raise DocumentClarificationNeeded(
                f"Query matched multiple candidate papers: {_format_candidates(candidates)}",
                candidates=candidates,
                question=f"你是指哪篇论文？请用 document_id 或 title 指定：{_format_candidates(candidates)}",
            )

    if len(documents) == 1:
        return documents[0]
    if not documents:
        type_text = f" {document_type.value}" if document_type else ""
        raise MaterialNotFoundError(f"No local{type_text} document found.")
    raise DocumentClarificationNeeded(
        f"Specify document_id or title. Candidates: {_format_candidates(documents)}",
        candidates=documents,
        question=f"本地有多篇候选论文。请指定 document_id 或 title：{_format_candidates(documents)}",
    )


def _select_by_title(documents: list[StudyDocument], title: str) -> StudyDocument:
    normalized = title.casefold().strip()
    exact = [doc for doc in documents if doc.title.casefold() == normalized]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ToolInputError(f"Title matched multiple papers exactly: {_format_candidates(exact)}")

    partial = [doc for doc in documents if normalized in doc.title.casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise DocumentClarificationNeeded(
            f"Title matched multiple papers: {_format_candidates(partial)}",
            candidates=partial,
            question=f"标题匹配到多篇论文。请指定 document_id 或完整 title：{_format_candidates(partial)}",
        )
    raise MaterialNotFoundError(f"No local paper title matched '{title}'.")


def _format_candidates(documents: list[StudyDocument]) -> str:
    return "; ".join(f"{doc.title} ({doc.id})" for doc in documents[:10])


def _unique_ids(values) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
