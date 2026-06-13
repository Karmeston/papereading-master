from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from finals_agent.core.exceptions import ToolInputError
from finals_agent.core.config import load_settings, response_language_instruction
from finals_agent.core.schemas import DocumentType, SearchRequest, SearchResult, StudyDocument
from finals_agent.data.citations import evidence_record
from finals_agent.data.repository import StudyRepository
from finals_agent.data.retrievers import Retriever


SYNTHESIS_SECTIONS = (
    ("one_sentence_summary", "一句话结论"),
    ("core_problem", "研究问题"),
    ("method", "方法与机制"),
    ("experiments", "实验与结果"),
    ("contributions", "主要贡献"),
    ("limitations", "局限与待验证点"),
)


@dataclass(frozen=True)
class RewrittenQuery:
    intent: str
    queries: tuple[str, ...]


class ReadingIntelligence:
    """Use the configured text model for intent understanding and grounded synthesis."""

    def __init__(self, model, repository: StudyRepository | None = None):
        self.model = model
        self.repository = repository
        self.language = load_settings(validate=False).language

    def report_context(
        self,
        paper: dict[str, Any],
        section_passes: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        coverage: dict[str, Any],
    ) -> dict[str, Any]:
        records = _collect_evidence(section_passes, evidence)
        if not records:
            raise ToolInputError("No local evidence is available for whole-paper reading.")
        records = self._expand_report_records(paper, records)
        allowed_citations = tuple(record["citation"] for record in records)
        prompt = {
            "paper": {
                "title": paper.get("title"),
                "field": paper.get("field"),
                "focus": paper.get("focus"),
            },
            "coverage": coverage,
            "section_evidence": records,
        }
        if self.language == "en":
            report_prompt = (
                "You are a research-paper reading assistant who has carefully read the full paper. Write an in-depth "
                "report of roughly 1800 to 3000 English words that reflects the source instead of giving a generic "
                "template or a brief abstract. Use these headings in order: Core Conclusion; Background and Research "
                "Problem; Overall Method; Key Mechanisms and Derivations; Experimental Setup; Main Results; "
                "Contributions and Differences from Prior Work; Limitations, Conditions, and Open Questions. "
                "Explain how method components connect and why they work. Preserve datasets, baselines, metrics, "
                "numbers, and author observations where supported. Use only section_evidence facts. Every paragraph "
                "must contain an exact citation. State evidence gaps instead of adding common knowledge. Do not output "
                "the retrieval process, reading plan, JSON, or a conversational preamble."
            )
        else:
            report_prompt = (
                "你是一名认真读完论文后向研究者讲解全文的助手。请使用中文写一份约 3000 至 5000 字的"
                "深入阅读报告。内容必须具体体现原文，而不是给出通用模板或几句摘要。\n"
                "依次使用以下标题：\n"
                "【核心结论】\n【研究背景与问题】\n【方法整体思路】\n【关键机制与推导】\n"
                "【实验设置】\n【主要实验结果】\n【贡献与原有工作的区别】\n【局限、条件与待验证点】\n"
                "方法部分要解释组件如何衔接、为什么成立；实验部分要尽量保留数据集、基线、指标、"
                "数字和作者的具体观察。区分论文明确陈述与基于证据的归纳。"
                "只能使用 section_evidence 中的事实。每个自然段至少附一个原样 citation；"
                "缺少证据时直接说明，不得补写常识。总长度不要超过 5000 字。"
                "直接从【核心结论】开始，不要写“好的”“以下是”等开场白。"
                "不要输出检索过程、阅读计划或 JSON。"
            )
        messages = [
            (
                "system",
                f"{report_prompt}\n\n{response_language_instruction(self.language)}",
            ),
            ("human", json.dumps(prompt, ensure_ascii=False)),
        ]
        return {
            "messages": messages,
            "allowed_citations": allowed_citations,
            "evidence_count": len(records),
        }

    def _expand_report_records(
        self,
        paper: dict[str, Any],
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if self.repository is None:
            return records
        document_id = str(paper.get("id") or "")
        if not document_id:
            return records
        try:
            document = self.repository.get_document(document_id)
            chunks = list(self.repository.read_chunks(document))
        except Exception:
            return records
        chunks_by_id = {chunk.chunk_id: index for index, chunk in enumerate(chunks)}
        expanded = []
        for record in records:
            item = dict(record)
            target_index = chunks_by_id.get(str(record.get("chunk_id") or ""))
            if target_index is not None:
                texts = []
                target_page = chunks[target_index].metadata.get("page")
                for index in range(max(0, target_index - 1), min(len(chunks), target_index + 2)):
                    chunk = chunks[index]
                    if target_page and chunk.metadata.get("page") != target_page:
                        continue
                    texts.append(chunk.text)
                context = _clean_extracted_text(_merge_overlapping_texts(texts))
                if context:
                    item["text"] = _clip(context, 3600)
            expanded.append(item)
        return expanded

    def stream_report(self, context: dict[str, Any]):
        model = self.model
        bind = getattr(model, "bind", None)
        if callable(bind):
            model = bind(max_tokens=3200)
        stream = getattr(model, "stream", None)
        if callable(stream):
            for response in stream(context["messages"]):
                text = _message_text(response)
                if text:
                    yield text
            return
        response = model.invoke(context["messages"])
        text = _message_text(response)
        if text:
            yield text

    def synthesize(
        self,
        paper: dict[str, Any],
        section_passes: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        coverage: dict[str, Any],
    ) -> dict[str, Any]:
        records = _collect_evidence(section_passes, evidence)
        if not records:
            return _empty_synthesis("当前论文没有可用于全文总结的本地证据。")

        allowed_citations = tuple(record["citation"] for record in records)
        prompt = {
            "paper": {
                "title": paper.get("title"),
                "field": paper.get("field"),
                "focus": paper.get("focus"),
            },
            "coverage": coverage,
            "evidence": records,
            "required_output": {
                key: {
                    "text": "grounded conclusion in the configured language",
                    "citations": ["exact citation copied from evidence"],
                }
                for key, _label in SYNTHESIS_SECTIONS
            },
        }
        response = self.model.invoke(
            [
                (
                    "system",
                    "你是严谨的论文阅读助手。请综合不同章节，而不是复述检索片段。"
                    "只能依据给定 evidence 陈述论文事实；每个非空结论必须附至少一个原样 citation。"
                    "实验部分必须区分实验设置、指标和作者报告的结果；证据不足时明确写证据不足。"
                    "不要输出阅读计划、检索过程或泛泛建议。只返回一个符合 required_output 的 JSON 对象。"
                    f"\n\n{response_language_instruction(self.language)}",
                ),
                ("human", json.dumps(prompt, ensure_ascii=False)),
            ]
        )
        parsed = _extract_json_object(_message_text(response))
        return _ground_synthesis(parsed, allowed_citations)

    def rewrite_query(self, query: str, document: StudyDocument | None = None) -> RewrittenQuery:
        query = query.strip()
        if not query:
            raise ToolInputError("query cannot be empty.")
        if len(query) > 500:
            raise ToolInputError("query must be 500 characters or fewer.")

        context = {
            "user_query": query,
            "paper_title": document.title if document else None,
            "paper_field": document.field if document else None,
            "paper_focus": document.focus if document else None,
        }
        response = self.model.invoke(
            [
                (
                    "system",
                    "你负责理解用户在论文中寻找什么证据。把自然语言问题改写为 3 到 5 条互补的"
                    "本地检索查询，覆盖原文术语、英文术语、方法/实验/结论等相关表达。"
                    "查询应短而具体，不得虚构论文内容。只返回 JSON："
                    '{"intent":"configured-language intent","queries":["query 1","query 2"]}。'
                    f"\n\n{response_language_instruction(self.language)}",
                ),
                ("human", json.dumps(context, ensure_ascii=False)),
            ]
        )
        data = _extract_json_object(_message_text(response))
        intent = str(data.get("intent") or query).strip()
        candidates = data.get("queries")
        if not isinstance(candidates, list):
            candidates = []
        queries = _unique_queries([query, *candidates])
        return RewrittenQuery(intent=intent[:300], queries=tuple(queries[:5]))

    def search(
        self,
        query: str,
        retriever: Retriever,
        *,
        document: StudyDocument | None = None,
        field: str | None = None,
        document_type: DocumentType | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        rewritten = self.rewrite_query(query, document=document)
        ranked: dict[tuple[str, str], tuple[SearchResult, float, int]] = {}
        per_query_limit = max(limit * 2, 10)

        for query_index, rewritten_query in enumerate(rewritten.queries):
            response = retriever.search(
                SearchRequest(
                    query=rewritten_query,
                    document_id=document.id if document else None,
                    field=field or (document.field if document else None),
                    document_type=document_type,
                    focus=document.focus if document else None,
                    limit=per_query_limit,
                )
            )
            query_weight = 1.0 if query_index == 0 else 0.9
            for result in response.results:
                key = _result_key(result)
                weighted_score = result.score * query_weight
                previous = ranked.get(key)
                if previous is None:
                    ranked[key] = (result, weighted_score, 1)
                    continue
                best_result, best_score, matches = previous
                if weighted_score > best_score:
                    best_result = result
                    best_score = weighted_score
                ranked[key] = (best_result, best_score, matches + 1)

        merged = []
        for result, best_score, matches in ranked.values():
            scored = _with_score(result, best_score + min(0.16, 0.04 * (matches - 1)))
            enriched = self._enrich_result(scored, rewritten.queries)
            merged.append((enriched, matches))
        merged.sort(key=lambda item: item[0].score, reverse=True)
        selected = self._rerank_evidence(query, rewritten.intent, merged[: max(limit * 2, 14)], limit)
        return {
            "intent": rewritten.intent,
            "queries": list(rewritten.queries),
            "results": [
                {
                    **evidence_record(result),
                    "query_match_count": matches,
                    "relevance_reason": reason,
                    "highlights": _top_relevant_sentences(result.snippet, rewritten.queries),
                }
                for result, matches, reason in selected
            ],
            "metadata": {
                "retriever": retriever.__class__.__name__,
                "rewritten_query_count": len(rewritten.queries),
                "candidate_count": len(merged),
            },
        }

    def _enrich_result(self, result: SearchResult, queries: tuple[str, ...]) -> SearchResult:
        if self.repository is None:
            return result
        try:
            document = self.repository.get_document(result.document_id)
            snippet = _complete_evidence_passage(self.repository, document, result, queries)
        except Exception:
            return result
        return _with_snippet(result, snippet or result.snippet)

    def _rerank_evidence(
        self,
        query: str,
        intent: str,
        candidates: list[tuple[SearchResult, int]],
        limit: int,
    ) -> list[tuple[SearchResult, int, str]]:
        if not candidates:
            return []
        payload = {
            "question": query,
            "intent": intent,
            "candidates": [
                {
                    "id": f"E{index}",
                    "section": result.section,
                    "page": result.page,
                    "text": result.snippet,
                }
                for index, (result, _matches) in enumerate(candidates, start=1)
            ],
        }
        fallback = [
            (result, matches, "按本地混合检索相关度排序")
            for result, matches in candidates[:limit]
        ]
        try:
            response = self.model.invoke(
                [
                    (
                        "system",
                        "你是论文证据筛选器。根据问题，从候选原文段落中选出最直接、可用于回答问题的证据，"
                        "优先选择定义、机制、实验设置、数字结果和作者明确结论。"
                        "不要改写候选原文。只返回 JSON："
                        '{"ranked":[{"id":"E1","reason":"该段直接说明了什么"}]}。'
                        "最多返回用户需要的数量，不得返回不存在的 id。"
                        f"\n\n{response_language_instruction(self.language)}",
                    ),
                    ("human", json.dumps(payload, ensure_ascii=False)),
                ]
            )
            data = _extract_json_object(_message_text(response))
        except Exception:
            return fallback
        raw_ranked = data.get("ranked")
        if not isinstance(raw_ranked, list):
            return fallback
        by_id = {
            f"E{index}": (result, matches)
            for index, (result, matches) in enumerate(candidates, start=1)
        }
        selected = []
        used = set()
        for item in raw_ranked:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("id") or "")
            if candidate_id not in by_id or candidate_id in used:
                continue
            result, matches = by_id[candidate_id]
            reason = str(item.get("reason") or "与问题直接相关").strip()
            selected.append((result, matches, reason[:240]))
            used.add(candidate_id)
            if len(selected) >= limit:
                break
        minimum = min(3, limit, len(candidates))
        if len(selected) < minimum:
            for candidate_id, (result, matches) in by_id.items():
                if candidate_id in used:
                    continue
                selected.append((result, matches, "补充的高相关本地证据"))
                used.add(candidate_id)
                if len(selected) >= minimum:
                    break
        return selected


def _collect_evidence(
    section_passes: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = []
    seen: set[str] = set()
    for section_pass in section_passes:
        role = str(section_pass.get("role") or "")
        for item in section_pass.get("evidence") or []:
            _append_evidence(records, seen, item, role=role)
    for item in evidence:
        _append_evidence(records, seen, item, role=str(item.get("aspect") or "supporting"))
    return records[:28]


def _append_evidence(
    records: list[dict[str, Any]],
    seen: set[str],
    item: dict[str, Any],
    *,
    role: str,
) -> None:
    citation = str(item.get("citation") or "").strip()
    snippet = str(item.get("snippet") or item.get("text") or "").strip()
    if not citation or not snippet or citation in seen:
        return
    seen.add(citation)
    records.append(
        {
            "role": role,
            "citation": citation,
            "text": _clip(snippet, 3600),
            "document_id": item.get("id"),
            "chunk_id": item.get("chunk_id"),
            "page": item.get("page"),
            "section": item.get("section"),
        }
    )


def _ground_synthesis(data: dict[str, Any], allowed_citations: tuple[str, ...]) -> dict[str, Any]:
    sections = []
    unsupported = []
    used_citations: list[str] = []
    for key, label in SYNTHESIS_SECTIONS:
        raw = data.get(key)
        if isinstance(raw, dict):
            text = str(raw.get("text") or "").strip()
            requested = raw.get("citations")
        else:
            text = str(raw or "").strip()
            requested = []
        if not isinstance(requested, list):
            requested = []
        citations = [
            citation
            for citation in allowed_citations
            if citation in requested or citation in text
        ]
        if text and citations:
            for citation in citations:
                if citation not in used_citations:
                    used_citations.append(citation)
            text = _remove_citations(text, citations)
            supported = True
        else:
            text = "当前证据不足，无法可靠总结这一部分。"
            citations = []
            supported = False
            unsupported.append(key)
        sections.append(
            {
                "key": key,
                "label": label,
                "text": text,
                "citations": citations,
                "supported": supported,
            }
        )
    return {
        "sections": sections,
        "citation_check": {
            "passed": not unsupported,
            "unsupported_sections": unsupported,
            "used_citations": used_citations,
            "available_citation_count": len(allowed_citations),
        },
    }


def _empty_synthesis(reason: str) -> dict[str, Any]:
    return {
        "sections": [
            {
                "key": key,
                "label": label,
                "text": reason,
                "citations": [],
                "supported": False,
            }
            for key, label in SYNTHESIS_SECTIONS
        ],
        "citation_check": {
            "passed": False,
            "unsupported_sections": [key for key, _label in SYNTHESIS_SECTIONS],
            "used_citations": [],
            "available_citation_count": 0,
        },
    }


def _extract_json_object(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.I)
        content = re.sub(r"\s*```$", "", content)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            raise ToolInputError("The text model did not return valid JSON.")
        try:
            parsed = json.loads(content[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ToolInputError("The text model did not return valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ToolInputError("The text model must return a JSON object.")
    return parsed


def _message_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts)
    return str(content)


def _unique_queries(values: list[Any]) -> list[str]:
    queries = []
    seen = set()
    for value in values:
        query = " ".join(str(value or "").split()).strip()
        if not query or len(query) > 500:
            continue
        key = query.casefold()
        if key in seen:
            continue
        seen.add(key)
        queries.append(query)
    return queries


def _result_key(result: SearchResult) -> tuple[str, str]:
    location = result.chunk_id or f"{result.section or ''}:{result.page or ''}:{result.snippet[:80]}"
    return result.document_id, location


def _with_score(result: SearchResult, score: float) -> SearchResult:
    return SearchResult(
        document_id=result.document_id,
        title=result.title,
        document_type=result.document_type,
        course=result.course,
        path=result.path,
        snippet=result.snippet,
        score=score,
        chapter=result.chapter,
        source=result.source,
        tags=result.tags,
        chunk_id=result.chunk_id,
        page=result.page,
        section=result.section,
        block_type=result.block_type,
    )


def _with_snippet(result: SearchResult, snippet: str) -> SearchResult:
    section = _normalized_section_label(result.section) or _infer_section_from_text(snippet)
    return SearchResult(
        document_id=result.document_id,
        title=result.title,
        document_type=result.document_type,
        course=result.course,
        path=result.path,
        snippet=snippet,
        score=result.score,
        chapter=result.chapter,
        source=result.source,
        tags=result.tags,
        chunk_id=result.chunk_id,
        page=result.page,
        section=section,
        block_type=result.block_type,
    )


def _complete_evidence_passage(
    repository: StudyRepository,
    document: StudyDocument,
    result: SearchResult,
    queries: tuple[str, ...],
) -> str:
    chunks = list(repository.read_chunks(document))
    if not chunks:
        return _clean_extracted_text(result.snippet)
    target_index = next(
        (index for index, chunk in enumerate(chunks) if chunk.chunk_id == result.chunk_id),
        None,
    )
    if target_index is None:
        return _clean_extracted_text(result.snippet)
    target = chunks[target_index]
    neighbors = []
    for index in range(max(0, target_index - 1), min(len(chunks), target_index + 2)):
        chunk = chunks[index]
        if target.metadata.get("page") and chunk.metadata.get("page") != target.metadata.get("page"):
            continue
        neighbors.append(chunk.text)
    combined = _merge_overlapping_texts(neighbors)
    cleaned = _clean_extracted_text(combined)
    return _select_complete_sentences(cleaned, queries)


def _merge_overlapping_texts(texts: list[str]) -> str:
    if not texts:
        return ""
    merged = texts[0]
    for text in texts[1:]:
        overlap = 0
        maximum = min(600, len(merged), len(text))
        for size in range(maximum, 39, -1):
            if merged[-size:] == text[:size]:
                overlap = size
                break
        merged += text[overlap:]
    return merged


def _clean_extracted_text(text: str) -> str:
    lines = text.splitlines()
    if lines and re.match(r"^\s*\[page\s+\d+\]\s*$", lines[0], re.I):
        if len(lines) > 1 and _looks_like_running_header(lines[1]):
            lines.pop(1)
        text = "\n".join(lines)
    text = re.sub(r"\[page\s+\d+\]", " ", text, flags=re.I)
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _select_complete_sentences(text: str, queries: tuple[str, ...], max_length: int = 1400) -> str:
    if not text:
        return ""
    sentences = [
        item.strip()
        for item in re.findall(r"[^.!?。！？]+(?:[.!?。！？]+|$)", text)
        if item.strip()
    ]
    if not sentences:
        return text
    terms = _search_terms(" ".join(queries))
    scores = [
        sum(sentence.casefold().count(term) for term in terms)
        for sentence in sentences
    ]
    best_index = max(range(len(sentences)), key=lambda index: scores[index])
    selected = [sentences[best_index]]
    left = best_index - 1
    right = best_index + 1
    while len(" ".join(selected)) < 650 and (left >= 0 or right < len(sentences)):
        if right < len(sentences):
            selected.append(sentences[right])
            right += 1
        if len(" ".join(selected)) >= 650:
            break
        if left >= 0:
            selected.insert(0, sentences[left])
            left -= 1
    passage = " ".join(selected)
    if len(passage) <= max_length:
        return passage
    complete = []
    length = 0
    for sentence in selected:
        if complete and length + len(sentence) + 1 > max_length:
            break
        complete.append(sentence)
        length += len(sentence) + 1
    return " ".join(complete) if complete else selected[0]


def _top_relevant_sentences(
    text: str,
    queries: tuple[str, ...],
    limit: int = 2,
) -> list[str]:
    sentences = [
        item.strip()
        for item in re.findall(r".+?[.!?。！？](?=\s|$)", text)
        if item.strip()
    ]
    if not sentences:
        return []
    terms = _search_terms(" ".join(queries))
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (
            sum(item[1].casefold().count(term) for term in terms),
            len(item[1]),
        ),
        reverse=True,
    )
    selected_indexes = sorted(
        index
        for index, sentence in ranked[:limit]
        if any(term in sentence.casefold() for term in terms)
    )
    return [sentences[index] for index in selected_indexes]


def _search_terms(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9][a-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text.casefold())
    stop = {
        "the", "and", "for", "with", "from", "this", "that", "what", "how", "why",
        "论文", "作者", "什么", "如何", "为什么", "证据", "说明",
    }
    terms = []
    for item in raw:
        if item in stop or item in terms:
            continue
        terms.append(item)
    return terms


def _normalized_section_label(section: str | None) -> str | None:
    if not section:
        return None
    cleaned = " ".join(section.split()).strip()
    if not cleaned or len(cleaned) > 100:
        return None
    if re.match(r"^\d+(?:\.\d+)*\.?\s+\S+", cleaned):
        return cleaned
    if cleaned.casefold() in {
        "abstract", "introduction", "related work", "background", "method", "methods",
        "methodology", "approach", "model", "experiment", "experiments", "evaluation",
        "results", "discussion", "limitation", "limitations", "future work",
        "conclusion", "references",
    }:
        return cleaned
    return None


def _infer_section_from_text(text: str) -> str | None:
    numbered = re.search(
        r"\b(\d+(?:\.\d+)+\.?\s+[A-Z][A-Za-z0-9αβγ\- ]{2,70})(?=\s+[A-Z]|$)",
        text,
    )
    if numbered:
        return numbered.group(1).strip()
    exact = re.search(
        r"\b(Abstract|Introduction|Related Work|Method|Methods|Experiments?|"
        r"Evaluation|Results|Discussion|Limitations?|Conclusion)\b",
        text,
    )
    return exact.group(1) if exact else None


def _looks_like_running_header(line: str) -> bool:
    cleaned = " ".join(line.split()).strip()
    if not 12 <= len(cleaned) <= 180 or re.search(r"[.!?]$", cleaned):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z\-]*", cleaned)
    if len(words) < 4:
        return False
    title_words = sum(1 for word in words if word[0].isupper())
    return title_words / len(words) >= 0.55


def _clip(text: str, length: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= length:
        return cleaned
    return cleaned[: length - 3].rstrip() + "..."


def _remove_citations(text: str, citations: list[str]) -> str:
    cleaned = text
    for citation in citations:
        cleaned = cleaned.replace(citation, "")
    return " ".join(cleaned.split()).strip()
