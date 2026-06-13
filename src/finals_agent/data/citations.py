from __future__ import annotations

from typing import Any

from finals_agent.core.schemas import SearchResult
from finals_agent.data.external_search import ExternalPaper


def local_citation(result: SearchResult) -> str:
    parts = [result.title]
    if result.section:
        parts.append(f"section={result.section}")
    elif result.chapter:
        parts.append(f"focus={result.chapter}")
    if result.page is not None:
        parts.append(f"page={result.page}")
    if result.chunk_id:
        parts.append(f"chunk={result.chunk_id}")
    return "[" + " | ".join(parts) + "]"


def external_citation(paper: ExternalPaper, index: int | None = None) -> str:
    label = f"R{index}" if index is not None else "external"
    date = paper.published or "date unknown"
    return f"[{label}: {paper.title} | {date} | {paper.url}]"


def evidence_record(result: SearchResult, aspect: str | None = None) -> dict[str, Any]:
    payload = result.to_dict()
    payload["citation"] = local_citation(result)
    if aspect:
        payload["aspect"] = aspect
    return payload


def external_record(paper: ExternalPaper, index: int | None = None) -> dict[str, Any]:
    payload = paper.to_dict()
    payload["citation"] = external_citation(paper, index=index)
    return payload


def format_evidence_line(result: SearchResult, index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else ""
    page = f" page={result.page}" if result.page is not None else ""
    block = f" block={result.block_type}" if result.block_type else ""
    return f"{prefix}{local_citation(result)} score={result.score:.3f}{page}{block}: {result.snippet}"


def citation_instructions() -> list[str]:
    return [
        "Use citation strings exactly as provided when making claims from local evidence.",
        "For local evidence, cite title, section/page when available, and chunk id.",
        "For external related papers, cite the related-paper citation string and treat abstract metadata as limited evidence.",
        "If evidence is missing, say the claim is not supported by the current local repository.",
    ]
