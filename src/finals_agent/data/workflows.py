from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable

from finals_agent.core.exceptions import ExternalSearchError, ToolInputError
from finals_agent.core.schemas import ArtifactInterpretation, PaperArtifact, SearchRequest, SearchResult, StudyDocument
from finals_agent.data.citations import citation_instructions, evidence_record, external_record
from finals_agent.data.external_search import ArxivPaperSearch, ExternalPaper
from finals_agent.data.paper_analysis import PaperStructureAnalyzer
from finals_agent.data.repository import StudyRepository
from finals_agent.data.retrievers import HybridRetriever, Retriever
from finals_agent.data.selection import select_document
from finals_agent.data.vision import build_vision_artifact_interpreter
from finals_agent.persistence.reading_state import ReadingStateStore, reading_state_summary


READING_ASPECTS = {
    "problem": "problem motivation challenge gap objective research question",
    "method": "method approach model algorithm framework architecture",
    "evidence": "experiment dataset metric result evaluation baseline",
    "contribution": "contribution novelty innovation advantage improve",
    "limitation": "limitation future work failure analysis discussion",
}

SECTION_READING_PASSES = (
    {
        "role": "abstract",
        "labels": ("abstract", "摘要"),
        "query": "abstract summary contribution problem method result",
        "purpose": "Capture the paper's own compact statement of problem, method, and claimed result.",
    },
    {
        "role": "introduction",
        "labels": ("introduction", "引言"),
        "query": "introduction motivation problem gap contribution challenge",
        "purpose": "Ground the problem setup, motivation, and contribution claims.",
    },
    {
        "role": "method",
        "labels": ("method", "methodology", "approach", "model", "方法"),
        "query": "method approach model algorithm framework architecture implementation",
        "purpose": "Ground how the proposed method works and what components it contains.",
    },
    {
        "role": "experiments",
        "labels": ("experiment", "evaluation", "实验", "评估"),
        "query": "experiment evaluation dataset baseline metric setup",
        "purpose": "Ground experimental setup, datasets, baselines, and metrics.",
    },
    {
        "role": "results",
        "labels": ("results", "analysis", "ablation", "结果", "分析", "消融"),
        "query": "results ablation analysis performance improvement main finding",
        "purpose": "Ground empirical findings and avoid unsupported performance claims.",
    },
    {
        "role": "discussion_limitations",
        "labels": ("discussion", "limitation", "future work", "讨论", "局限"),
        "query": "discussion limitation failure future work weakness",
        "purpose": "Ground limits, failure modes, and follow-up questions.",
    },
    {
        "role": "conclusion",
        "labels": ("conclusion", "结论"),
        "query": "conclusion summary contribution future work",
        "purpose": "Capture the final author summary and closing claims.",
    },
)

HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\s+)?(?P<title>"
    r"abstract|introduction|related work|background|method|methodology|approach|model|experiment|experiments|evaluation|evaluations|results|analysis|ablation|discussion|limitation|limitations|future work|conclusion|references|"
    r"摘要|引言|相关工作|背景|方法|实验|评估|结果|分析|消融|讨论|局限|结论|参考文献"
    r")\b.*$",
    re.I,
)
PAGE_MARK_RE = re.compile(r"\[page\s+(?P<page>\d+)\]", re.I)
NUMBERED_TEXT_HEADING_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+[A-Z][^.!?]{1,100}$")
EXACT_TEXT_HEADING_RE = re.compile(
    r"^\s*(abstract|introduction|related work|background|method|methods|methodology|"
    r"approach|model|experiments?|evaluation|results|discussion|limitations?|"
    r"future work|conclusion|references)\s*$",
    re.I,
)


@dataclass(frozen=True)
class PaperEvidence:
    aspect: str
    result: SearchResult

    def to_dict(self) -> dict[str, Any]:
        return evidence_record(self.result, aspect=self.aspect)


@dataclass(frozen=True)
class WorkflowResult:
    workflow: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "data": self.data,
        }


class PaperReadingWorkflow:
    def __init__(
        self,
        repository: StudyRepository | None = None,
        retriever: Retriever | None = None,
        external_search: ArxivPaperSearch | None = None,
        vision_interpreter_factory: Callable[[StudyDocument], Any] | None = None,
        reading_store: ReadingStateStore | None = None,
    ):
        self.repository = repository or StudyRepository()
        self.retriever = retriever or HybridRetriever(self.repository)
        self.external_search = external_search or ArxivPaperSearch()
        self.analyzer = PaperStructureAnalyzer(self.repository)
        self.vision_interpreter_factory = vision_interpreter_factory or build_vision_artifact_interpreter
        self.reading_store = reading_store or ReadingStateStore()

    def read(
        self,
        document_id: str | None = None,
        title: str | None = None,
        query: str | None = None,
        field: str | None = None,
        related_limit: int = 0,
    ) -> WorkflowResult:
        document = self._select_document(document_id=document_id, title=title, query=query, field=field)
        structure = self.analyzer.analyze(document_id=document.id)
        section_passes = self._section_passes(document, structure)
        evidence = self._aspect_evidence(document, field=field, section_passes=section_passes)
        related, related_error = self._related_papers(document, structure, related_limit)
        reading_state = reading_state_summary(self.reading_store.get(document))
        return WorkflowResult(
            workflow="read_paper",
            data={
                "paper": document.to_dict(),
                "reading_state": reading_state,
                "structure": structure.to_dict(),
                "section_passes": section_passes,
                "whole_paper_synthesis_plan": _whole_paper_synthesis_plan(section_passes),
                "evidence": [item.to_dict() for item in evidence],
                "reading_order": _reading_order(structure.section_headings),
                "citation_instructions": citation_instructions(),
                "output_template": {
                    "core_problem": "Use problem evidence plus abstract/introduction.",
                    "method_summary": "Use method evidence plus figures/formulas when present.",
                    "key_experiments": "Use evidence results from experiment/evaluation sections.",
                    "claimed_contributions": "Use contribution evidence and avoid unsupported novelty claims.",
                    "limitations": "Use limitation/discussion evidence; mark absent evidence explicitly.",
                },
                "related_papers": [external_record(paper, index=index) for index, paper in enumerate(related, start=1)],
                "related_papers_error": related_error,
                "next_actions": _next_actions(structure.to_dict(), bool(related), related_error=related_error),
                "coverage": _section_coverage(section_passes),
            },
        )

    def explain(
        self,
        target: str,
        document_id: str | None = None,
        title: str | None = None,
        query: str | None = None,
        field: str | None = None,
        limit: int = 5,
    ) -> WorkflowResult:
        if not target.strip():
            raise ToolInputError("target cannot be empty.")
        document = self._select_document(document_id=document_id, title=title, query=query or target, field=field)
        structure = self.analyzer.analyze(document_id=document.id)
        reading_state = reading_state_summary(self.reading_store.get(document))
        results = self.retriever.search(
            SearchRequest(
                query=target,
                document_id=document.id,
                field=field or document.field,
                focus=document.focus,
                limit=limit,
            )
        ).results
        matched_candidates = _matching_structure_candidates(target, structure.to_dict())
        visual_artifact = _matching_visual_artifact(target, structure.artifacts)
        visual_interpretation = self._interpret_visual_artifact(document, visual_artifact) if visual_artifact else None
        return WorkflowResult(
            workflow="explain_paper_target",
            data={
                "paper": document.to_dict(),
                "reading_state": reading_state,
                "target": target,
                "matched_structure_candidates": matched_candidates,
                "visual_artifact": visual_artifact.to_dict() if visual_artifact else None,
                "visual_interpretation": visual_interpretation.to_dict() if visual_interpretation else None,
                "evidence": [evidence_record(item) for item in results],
                "citation_instructions": citation_instructions(),
                "explanation_plan": [
                    "Locate the target in the paper structure or retrieved chunks.",
                    "Explain the local meaning in plain language.",
                    "Explain its role in the paper's argument, method, or evidence chain.",
                    "List variables, assumptions, or table/figure axes when available.",
                    "Use visual_interpretation for figure/table content; if absent, state that vision API evidence is missing.",
                ],
            },
        )

    def compare(
        self,
        topic: str,
        document_id: str | None = None,
        title: str | None = None,
        query: str | None = None,
        field: str | None = None,
        related_limit: int = 5,
    ) -> WorkflowResult:
        if not topic.strip():
            raise ToolInputError("topic cannot be empty.")
        document = self._select_document(document_id=document_id, title=title, query=query or topic, field=field)
        structure = self.analyzer.analyze(document_id=document.id)
        reading_state = reading_state_summary(self.reading_store.get(document))
        local_evidence = self.retriever.search(
            SearchRequest(
                query=topic,
                document_id=document.id,
                field=field or document.field,
                focus=document.focus,
                limit=8,
            )
        ).results
        related, related_error = self._search_related(topic, related_limit)
        return WorkflowResult(
            workflow="compare_paper_innovations",
            data={
                "paper": document.to_dict(),
                "reading_state": reading_state,
                "topic": topic,
                "local_structure": structure.to_dict(),
                "local_evidence": [evidence_record(item) for item in local_evidence],
                "related_papers": [external_record(paper, index=index) for index, paper in enumerate(related, start=1)],
                "related_papers_error": related_error,
                "comparison_matrix": _comparison_matrix(related),
                "citation_instructions": citation_instructions(),
                "comparison_instructions": [
                    "Separate paper-claimed contributions from inferred differences.",
                    "Compare problem setting, method, evidence, and limitations before saying one paper is better.",
                    "Use local evidence for the uploaded paper and arXiv metadata/abstracts for external papers.",
                    "Mark any missing dataset, metric, or result detail as unknown instead of filling it in.",
                ],
            },
        )

    def _select_document(
        self,
        document_id: str | None,
        title: str | None,
        query: str | None,
        field: str | None,
    ) -> StudyDocument:
        return select_document(
            self.repository,
            document_id=document_id,
            title=title,
            query=query,
            field=field,
            retriever=self.retriever,
        )

    def _section_passes(self, document: StudyDocument, structure) -> list[dict[str, Any]]:
        sections = _extract_text_sections(
            self.repository.read_searchable_text(document) or "",
            fallback_headings=structure.section_headings,
        )
        passes = []
        used_result_keys: set[tuple[str, str | None]] = set()
        for spec in SECTION_READING_PASSES:
            role = spec["role"]
            matching_sections = _match_sections(sections, spec["labels"])
            evidence = []
            for section in matching_sections[:2]:
                result = _section_search_result(document, section, role=role)
                evidence.append(evidence_record(result, aspect=role))
                used_result_keys.add((result.document_id, result.chunk_id or result.section))

            if not evidence:
                fallback_results = self.retriever.search(
                    SearchRequest(
                        query=spec["query"],
                        document_id=document.id,
                        field=document.field,
                        focus=document.focus,
                        limit=2,
                    )
                ).results
                for result in fallback_results:
                    key = (result.document_id, result.chunk_id or result.section)
                    if key in used_result_keys:
                        continue
                    evidence.append(evidence_record(result, aspect=role))
                    used_result_keys.add(key)
                    if len(evidence) >= 2:
                        break

            passes.append(
                {
                    "role": role,
                    "purpose": spec["purpose"],
                    "query": spec["query"],
                    "target_headings": [section["heading"] for section in matching_sections],
                    "status": "covered" if evidence else "missing",
                    "evidence": evidence,
                    "missing_reason": None if evidence else "No matching section or fallback retrieval evidence found.",
                    "summary_prompt": _section_summary_prompt(role),
                }
            )
        return passes

    def _aspect_evidence(
        self,
        document: StudyDocument,
        field: str | None,
        section_passes: list[dict[str, Any]] | None = None,
    ) -> list[PaperEvidence]:
        evidence: list[PaperEvidence] = []
        seen: set[tuple[str, str | None, str]] = set()
        if section_passes:
            for section_pass in section_passes:
                aspect = _aspect_from_section_role(section_pass["role"])
                for item in section_pass.get("evidence", []):
                    key = (item["id"], item.get("chunk_id") or item.get("section"), aspect)
                    if key in seen:
                        continue
                    seen.add(key)
                    evidence.append(PaperEvidence(aspect=aspect, result=_search_result_from_evidence_record(item, document)))

        for aspect, query in READING_ASPECTS.items():
            response = self.retriever.search(
                SearchRequest(
                    query=query,
                    document_id=document.id,
                    field=field or document.field,
                    focus=document.focus,
                    limit=2,
                )
            )
            for result in response.results:
                key = (result.document_id, result.chunk_id or result.section, aspect)
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(PaperEvidence(aspect=aspect, result=result))
        return evidence

    def _related_papers(
        self,
        document: StudyDocument,
        structure,
        related_limit: int,
    ) -> tuple[tuple[ExternalPaper, ...], str | None]:
        if related_limit < 1:
            return (), None
        topic = " ".join(
            item
            for item in (
                document.title,
                document.focus,
                structure.section_headings[0] if structure.section_headings else None,
            )
            if item
        )
        return self._search_related(topic, related_limit)

    def _search_related(self, topic: str, related_limit: int) -> tuple[tuple[ExternalPaper, ...], str | None]:
        if related_limit < 1:
            return (), None
        try:
            return self.external_search.search(topic, limit=related_limit), None
        except ExternalSearchError as exc:
            return (), str(exc)

    def _interpret_visual_artifact(
        self,
        document: StudyDocument,
        artifact: PaperArtifact,
    ) -> ArtifactInterpretation:
        interpreter = self.vision_interpreter_factory(document)
        interpretation = interpreter.interpret(artifact)
        existing = {
            item.artifact_id: item
            for item in self.repository.read_artifact_interpretations(document)
        }
        existing[artifact.artifact_id] = interpretation
        ordered = []
        for item in self.repository.read_artifacts(document):
            if item.artifact_id in existing:
                ordered.append(existing[item.artifact_id])
        self.repository.write_artifact_interpretations(document, ordered)
        return interpretation


def _extract_text_sections(text: str, fallback_headings: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    lines = text.splitlines()
    sections: list[dict[str, Any]] = []
    current_heading = "full_text"
    current_lines: list[str] = []
    current_page: int | None = None
    current_index = 0

    def flush() -> None:
        nonlocal current_index
        body = "\n".join(current_lines).strip()
        if not body:
            return
        sections.append(
            {
                "index": current_index,
                "heading": current_heading,
                "text": body,
                "page": current_page,
            }
        )
        current_index += 1

    for line in lines:
        page_match = PAGE_MARK_RE.search(line)
        if page_match:
            current_page = int(page_match.group("page"))
        stripped = line.strip()
        if stripped and len(stripped) <= 140 and _is_text_heading(stripped):
            flush()
            current_heading = stripped
            current_lines = [stripped]
            continue
        current_lines.append(line)
    flush()

    if sections:
        return sections
    if text.strip():
        return [{"index": 0, "heading": "full_text", "text": text.strip(), "page": None}]
    return [
        {"index": index, "heading": heading, "text": heading, "page": None}
        for index, heading in enumerate(fallback_headings)
    ]


def _is_text_heading(text: str) -> bool:
    return bool(EXACT_TEXT_HEADING_RE.match(text) or NUMBERED_TEXT_HEADING_RE.match(text))


def _match_sections(sections: list[dict[str, Any]], labels: tuple[str, ...]) -> list[dict[str, Any]]:
    matched = []
    for section in sections:
        heading = section["heading"].casefold()
        if any(label.casefold() in heading for label in labels):
            matched.append(section)
    return matched


def _section_search_result(document: StudyDocument, section: dict[str, Any], role: str) -> SearchResult:
    return SearchResult(
        document_id=document.id,
        title=document.title,
        document_type=document.document_type,
        course=document.field,
        path=document.path,
        snippet=_clip_section_evidence(section["text"], length=3200),
        score=1.0,
        chapter=document.focus,
        source=document.source,
        tags=document.tags,
        chunk_id=f"{document.id}-section-{role}-{section['index']}",
        page=section.get("page"),
        section=section["heading"],
        block_type="section",
    )


def _search_result_from_evidence_record(record: dict[str, Any], document: StudyDocument) -> SearchResult:
    return SearchResult(
        document_id=record["id"],
        title=record["title"],
        document_type=document.document_type,
        course=record.get("field") or document.field,
        path=document.path,
        snippet=record.get("snippet", ""),
        score=float(record.get("score", 1.0)),
        chapter=record.get("focus"),
        source=record.get("source"),
        tags=tuple(record.get("tags", ())),
        chunk_id=record.get("chunk_id"),
        page=record.get("page"),
        section=record.get("section"),
        block_type=record.get("block_type"),
    )


def _aspect_from_section_role(role: str) -> str:
    if role in {"abstract", "introduction"}:
        return "problem"
    if role == "method":
        return "method"
    if role in {"experiments", "results"}:
        return "evidence"
    if role == "discussion_limitations":
        return "limitation"
    return "contribution"


def _section_summary_prompt(role: str) -> str:
    prompts = {
        "abstract": "Summarize the paper's stated problem, method, and claimed result from this section only.",
        "introduction": "Extract motivation, research gap, and contribution claims from this section only.",
        "method": "Explain the method components and workflow from this section only.",
        "experiments": "Extract datasets, baselines, metrics, and setup from this section only.",
        "results": "Extract main findings, ablations, and result caveats from this section only.",
        "discussion_limitations": "Extract limitations, failure modes, and follow-up questions from this section only.",
        "conclusion": "Extract the final author summary and closing claims from this section only.",
    }
    return prompts.get(role, "Summarize this section using only the provided evidence.")


def _whole_paper_synthesis_plan(section_passes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "instruction": "Synthesize the whole paper by first summarizing each covered section role, then combining only cited claims.",
        "order": [item["role"] for item in section_passes],
        "required_outputs": [
            "one_sentence_thesis",
            "core_problem",
            "method_summary",
            "experiment_and_result_summary",
            "claimed_contributions",
            "limitations_and_open_questions",
            "missing_evidence",
        ],
        "citation_rule": "Every local claim should cite an evidence citation from the relevant section_pass.",
        "missing_roles": [item["role"] for item in section_passes if item["status"] != "covered"],
    }


def _section_coverage(section_passes: list[dict[str, Any]]) -> dict[str, Any]:
    covered = [item["role"] for item in section_passes if item["status"] == "covered"]
    missing = [item["role"] for item in section_passes if item["status"] != "covered"]
    total = len(section_passes)
    return {
        "covered_roles": covered,
        "missing_roles": missing,
        "covered_count": len(covered),
        "total_count": total,
        "coverage_ratio": round(len(covered) / total, 3) if total else 0.0,
    }


def _clip_snippet(text: str, length: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= length:
        return cleaned
    return cleaned[: length - 15].rstrip() + " ...[truncated]"


def _clip_section_evidence(text: str, length: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= length:
        return cleaned
    head_length = int(length * 0.68)
    tail_length = length - head_length
    return (
        cleaned[:head_length].rstrip()
        + " ... [section middle omitted] ... "
        + cleaned[-tail_length:].lstrip()
    )


def _reading_order(section_headings: tuple[str, ...]) -> list[dict[str, str]]:
    if not section_headings:
        return [
            {"step": "skim", "target": "abstract/introduction/conclusion if present"},
            {"step": "deep_read", "target": "method and experiment evidence retrieved from chunks"},
            {"step": "compare", "target": "related work and contribution evidence"},
        ]
    priority = ("abstract", "introduction", "method", "experiment", "evaluation", "results", "discussion", "conclusion")
    ordered = []
    for key in priority:
        for heading in section_headings:
            if key in heading.lower() and heading not in [item["target"] for item in ordered]:
                ordered.append({"step": _step_for_heading(key), "target": heading})
    for heading in section_headings:
        if heading not in [item["target"] for item in ordered]:
            ordered.append({"step": "reference", "target": heading})
    return ordered


def _step_for_heading(key: str) -> str:
    if key in {"abstract", "introduction", "conclusion"}:
        return "skim"
    if key in {"method"}:
        return "deep_read_method"
    if key in {"experiment", "evaluation", "results"}:
        return "verify_evidence"
    return "inspect_limits"


def _matching_structure_candidates(target: str, structure: dict[str, Any]) -> list[dict[str, Any]]:
    target_lower = target.casefold()
    candidates = []
    for key in ("section_headings", "figure_captions", "table_captions", "formula_candidates"):
        for value in structure.get(key, []):
            if target_lower in value.casefold() or value.casefold() in target_lower:
                candidates.append({"kind": key, "text": value})
    return candidates


def _matching_visual_artifact(target: str, artifacts: tuple[PaperArtifact, ...]) -> PaperArtifact | None:
    target_lower = target.casefold()
    for artifact in artifacts:
        if artifact.kind not in {"figure", "table"}:
            continue
        values = [artifact.text, artifact.caption or ""]
        if any(target_lower in value.casefold() or value.casefold() in target_lower for value in values if value):
            return artifact
    return None


def _comparison_matrix(related: tuple[ExternalPaper, ...]) -> list[dict[str, Any]]:
    rows = []
    for index, paper in enumerate(related, start=1):
        rows.append(
            {
                "paper": paper.title,
                "problem_setting": "unknown from metadata; inspect abstract before claiming",
                "method": _summary_sentence(paper.summary),
                "evidence": "unknown from metadata; inspect experiments before claiming",
                "difference_from_local": "to be inferred from local evidence and related-paper abstract",
                "source": paper.url,
                "citation": external_record(paper, index=index)["citation"],
            }
        )
    return rows


def _summary_sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return "unknown"
    for separator in (". ", "? ", "! "):
        if separator in cleaned:
            return cleaned.split(separator, 1)[0] + separator.strip()
    return cleaned[:240]


def _next_actions(structure: dict[str, Any], has_related: bool, related_error: str | None = None) -> list[str]:
    actions = []
    if not structure.get("section_headings"):
        actions.append("Run OCR or upload a text-extractable PDF if section headings are missing.")
    if structure.get("figure_captions") and structure.get("image_count"):
        actions.append("Use the vision API for figure body interpretation beyond captions.")
    if structure.get("table_captions"):
        actions.append("Use the vision API for table interpretation; verify exact cells before reporting numeric results.")
    if related_error:
        actions.append(f"Retry related-paper search later: {related_error}")
    elif not has_related:
        actions.append("Run related-paper search before making novelty or difference claims.")
    return actions
