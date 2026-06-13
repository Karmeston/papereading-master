from __future__ import annotations

from dataclasses import dataclass

from finals_agent.core.schemas import SearchRequest, SearchResponse, TaskPlan
from finals_agent.data.citations import citation_instructions, format_evidence_line
from finals_agent.data.retrievers import Retriever


@dataclass(frozen=True)
class PreRetrievalResult:
    enabled: bool
    response: SearchResponse | None = None
    context_message: dict[str, str] | None = None

    def to_metadata(self) -> dict:
        if not self.enabled:
            return {"enabled": False, "count": 0}
        if not self.response:
            return {"enabled": True, "count": 0}
        return {
            "enabled": True,
            "count": self.response.count,
            "metadata": self.response.metadata,
            "citations": [result.to_dict()["citation"] for result in self.response.results],
        }


def run_preretrieval(
    task_plan: TaskPlan,
    query: str,
    retriever: Retriever,
    course: str | None = None,
    chapter: str | None = None,
    document_id: str | None = None,
    limit: int = 5,
    query_override: str | None = None,
) -> PreRetrievalResult:
    if not task_plan.intent.requires_retrieval:
        return PreRetrievalResult(enabled=False)

    response = retriever.search(
        SearchRequest(
            query=query_override or task_plan.intent.topic or query,
            course=task_plan.intent.course or course,
            chapter=chapter,
            document_id=document_id,
            limit=limit,
        )
    )
    return PreRetrievalResult(
        enabled=True,
        response=response,
        context_message=_build_context_message(response),
    )


def merge_preretrieval_results(
    first: PreRetrievalResult,
    second: PreRetrievalResult,
) -> PreRetrievalResult:
    if not first.enabled:
        return second
    if not second.enabled:
        return first
    if not first.response:
        return second
    if not second.response:
        return first

    merged = {}
    for result in (*first.response.results, *second.response.results):
        key = (result.document_id, result.chunk_id or "", result.snippet)
        previous = merged.get(key)
        if previous is None or result.score > previous.score:
            merged[key] = result
    results = tuple(sorted(merged.values(), key=lambda item: item.score, reverse=True))
    response = SearchResponse(
        request=second.response.request,
        results=results,
        metadata={
            **first.response.metadata,
            **second.response.metadata,
            "count": len(results),
            "retrieval_passes": [
                first.response.metadata,
                second.response.metadata,
            ],
        },
    )
    return PreRetrievalResult(
        enabled=True,
        response=response,
        context_message=_build_context_message(response),
    )


def _build_context_message(response: SearchResponse) -> dict[str, str] | None:
    if not response.results:
        return {
            "role": "system",
            "content": "预检索结果：没有找到匹配的本地论文片段。回答时请说明本地证据不足，并区分通用知识、外部检索和本地论文依据。",
        }

    lines = [
        "预检索到以下本地论文证据。回答时优先基于这些证据，并使用每条证据的 citation 字符串标注来源：",
        *[f"- {instruction}" for instruction in citation_instructions()],
    ]
    for index, result in enumerate(response.results, start=1):
        lines.append(format_evidence_line(result, index=index))
    return {"role": "system", "content": "\n".join(lines)}
