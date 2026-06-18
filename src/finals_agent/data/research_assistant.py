from __future__ import annotations

from hashlib import sha1
import json
import re
from typing import Any, Callable

from finals_agent.core.config import load_settings, response_language_instruction
from finals_agent.core.exceptions import ExternalSearchError, FinalsAgentError, ToolInputError
from finals_agent.core.schemas import DocumentType
from finals_agent.data.citations import evidence_record
from finals_agent.data.external_search import ArxivPaperSearch, ExternalPaper
from finals_agent.data.repository import StudyRepository
from finals_agent.persistence.research_tasks import ResearchTaskStore


DECISIONS = {"continue", "adjust", "stop"}


class ResearchAssistant:
    def __init__(
        self,
        model,
        *,
        repository: StudyRepository | None = None,
        external_search: ArxivPaperSearch | None = None,
        task_store: ResearchTaskStore | None = None,
    ):
        self.model = model
        self.repository = repository or StudyRepository()
        self.external_search = external_search or ArxivPaperSearch()
        self.task_store = task_store or ResearchTaskStore()
        self.language = load_settings(validate=False).language

    def discover(
        self,
        *,
        direction: str = "",
        paper_ids: list[str] | None = None,
        code_ids: list[str] | None = None,
        limit: int = 6,
        task_id: str | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        _check_cancel(cancel_check)
        starting_task = self.task_store.get(task_id) if task_id else None
        papers = self._documents(paper_ids or [], DocumentType.PAPER)
        codes = self._documents(code_ids or [], DocumentType.CODE)
        normalized_direction = _normalize_research_prompt(direction)
        if not normalized_direction and not papers:
            raise ToolInputError("Please select a local paper or enter a research direction.")
        queries = self._discovery_queries(normalized_direction, papers)
        local_titles = self._local_paper_titles(papers)
        related = []
        failures = []
        seen = set()
        safe_limit = max(1, min(limit, 12))
        search_limit = min(24, max(safe_limit * 3, safe_limit + len(local_titles) + 3))
        filtered_count = 0
        for query in queries:
            _check_cancel(cancel_check)
            try:
                found = self.external_search.search(query[:256], limit=search_limit)
            except ExternalSearchError as exc:
                failures.append(str(exc))
                continue
            minimum_overlap = _minimum_external_match_score(query)
            for source_index, item in enumerate(found):
                key = (item.url or item.title).casefold()
                if key in seen:
                    continue
                seen.add(key)
                if _normalized_title(item.title) in local_titles:
                    continue
                score, matched_terms = _external_match_details(item, query)
                if score < minimum_overlap:
                    filtered_count += 1
                    continue
                related.append((score, source_index, item, matched_terms))
            if len(related) >= search_limit:
                break
        if not related and failures:
            raise ExternalSearchError(
                "相关论文检索失败。已尝试英文研究方向和本地论文标题，请稍后重试。"
            )
        ranked_candidates = [
            {
                **_external_candidate(item),
                "match_score": score,
                "matched_terms": matched_terms[:10],
            }
            for score, _source_index, item, matched_terms in sorted(
                related,
                key=lambda entry: (-entry[0], entry[1]),
            )[:safe_limit]
        ]
        candidates = self._summarize_candidates(
            ranked_candidates
        )
        _check_cancel(cancel_check)
        task = (
            starting_task
            if starting_task
            else self.task_store.create(
                name=normalized_direction,
                direction=normalized_direction,
                paper_ids=[item.id for item in papers],
                code_ids=[item.id for item in codes],
            )
        )
        task = self.task_store.update(
            task["id"],
            expected_revision=task["revision"],
            direction=normalized_direction,
            paper_ids=[item.id for item in papers],
            code_ids=[item.id for item in codes],
            related_candidates=candidates,
        )
        return {
            "task": task,
            "query": queries[0],
            "queries": queries,
            "local_papers": [item.to_dict() for item in papers],
            "code_documents": [item.to_dict() for item in codes],
            "candidates": candidates,
            "filtered_count": filtered_count,
        }

    def update_task(
        self,
        *,
        task_id: str,
        name: str,
        direction: str,
        paper_ids: list[str] | None = None,
        code_ids: list[str] | None = None,
        candidate_sort: str = "relevance",
    ) -> dict[str, Any]:
        current = self.task_store.get(task_id)
        papers = self._documents(paper_ids or [], DocumentType.PAPER)
        codes = self._documents(code_ids or [], DocumentType.CODE)
        changes = {
            "name": name,
            "direction": _normalize_research_prompt(direction),
            "paper_ids": [item.id for item in papers],
            "code_ids": [item.id for item in codes],
            "candidate_sort": (
                candidate_sort
                if candidate_sort in {"relevance", "newest", "oldest"}
                else "relevance"
            ),
        }
        material_changed = any(
            current.get(key) != value
            for key, value in changes.items()
            if key not in {"name", "candidate_sort"}
        )
        if material_changed:
            changes.update(analysis=None, correspondence=None, experiment=None, decisions=[])
        task = self.task_store.update(task_id, **changes)
        return {"task": task}

    def analyze(
        self,
        *,
        task_id: str,
        direction: str = "",
        paper_ids: list[str] | None = None,
        code_ids: list[str] | None = None,
        related_papers: list[dict[str, Any]] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        _check_cancel(cancel_check)
        task = self.task_store.get(task_id)
        papers = self._documents(paper_ids or task.get("paper_ids", []), DocumentType.PAPER)
        codes = self._documents(code_ids or task.get("code_ids", []), DocumentType.CODE)
        related_source = related_papers if related_papers is not None else task.get("selected_related", [])
        related = [_clean_external(item) for item in related_source][:10]
        normalized_direction = _normalize_research_prompt(
            direction or task.get("direction") or ""
        )
        if not papers and not related:
            raise ToolInputError("Select at least one local or related paper before analysis.")
        payload = {
            "research_direction": normalized_direction,
            "local_papers": [self._paper_context(item) for item in papers[:8]],
            "external_papers": related,
            "code_context": self._code_context(codes),
            "evidence_policy": {
                "local_papers": "full-text excerpts with exact local citations",
                "external_papers": "abstract and metadata only; label conclusions as abstract-level",
                "code": "local source excerpts with file paths",
            },
            "required_output": {
                "overview": "short synthesis",
                "paper_assessments": [
                    {
                        "title": "",
                        "source_level": "local_full_text|external_abstract",
                        "relevance": "",
                        "innovations": [],
                        "limitations": [],
                        "evidence": [],
                    }
                ],
                "cross_paper_synthesis": {
                    "common_ground": [],
                    "key_differences": [],
                    "unresolved_gaps": [],
                },
                "code_correspondence": [
                    {
                        "paper_claim": "",
                        "code_location": "",
                        "status": "implemented|partial|missing|uncertain",
                        "explanation": "",
                        "evidence": [],
                    }
                ],
                "future_directions": [
                    {
                        "direction": "",
                        "rationale": "",
                        "novelty_basis": "",
                        "risk": "",
                        "minimal_test": "",
                    }
                ],
                "recommendation": "",
                "evidence_limits": [],
            },
        }
        analysis = self._invoke_json(
            (
                "You are a rigorous research copilot. Compare every selected paper, identify claimed innovation, "
                "relevance to the user's direction, limitations, unresolved gaps, and feasible next work. When code "
                "is supplied, map paper mechanisms to concrete files or symbols and mark uncertain or missing parts. "
                "Never claim to have read an external paper beyond its supplied abstract. Preserve exact local "
                "citations and code paths. Prefer testable, narrow future directions over generic suggestions."
            ),
            payload,
        )
        _check_cancel(cancel_check)
        task = self.task_store.update(
            task_id,
            expected_revision=task["revision"],
            direction=normalized_direction,
            paper_ids=[item.id for item in papers],
            code_ids=[item.id for item in codes],
            selected_related=related,
            analysis=analysis,
        )
        return {"task": task, "analysis": analysis}

    def check_correspondence(
        self,
        *,
        task_id: str,
        direction: str = "",
        paper_ids: list[str] | None = None,
        code_ids: list[str] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        _check_cancel(cancel_check)
        task = self.task_store.get(task_id)
        papers = self._documents(paper_ids or task.get("paper_ids", []), DocumentType.PAPER)
        codes = self._documents(code_ids or task.get("code_ids", []), DocumentType.CODE)
        if not papers:
            raise ToolInputError("Select at least one local paper for correspondence checking.")
        if not codes:
            raise ToolInputError("Select at least one local code project for correspondence checking.")
        paper_contexts = [self._paper_context(item) for item in papers[:6]]
        normalized_direction = _normalize_research_prompt(
            direction or task.get("direction") or ""
        )
        requirements_raw = self._invoke_json(
            (
                "Extract concrete, independently checkable implementation requirements from the supplied local-paper "
                "evidence. Each requirement must describe one algorithm step, formula, preprocessing operation, "
                "parameter, metric, or experiment condition. Copy exactly one supplied citation and include concise "
                "code-oriented search terms such as function names, variables, formulas, datasets, metrics, or method "
                "names. Do not infer requirements absent from the cited snippet."
            ),
            {
                "research_direction": normalized_direction,
                "papers": paper_contexts,
                "required_output": {
                    "requirements": [
                        {
                            "category": "algorithm|formula|data|preprocessing|parameter|metric|experiment",
                            "paper_claim": "",
                            "paper_citation": "",
                            "expected_behavior": "",
                            "code_search_terms": [],
                        }
                    ]
                },
            },
        )
        requirements = _ground_correspondence_requirements(
            requirements_raw,
            paper_contexts,
        )
        if not requirements:
            raise FinalsAgentError(
                "The model did not extract any paper requirement backed by an exact local citation."
            )
        _check_cancel(cancel_check)
        code_evidence, code_coverage = self._code_evidence_context(
            codes,
            requirements=requirements,
        )
        if not code_evidence:
            raise ToolInputError("The selected code project has no readable source evidence.")
        payload = {
            "research_direction": normalized_direction,
            "papers": paper_contexts,
            "requirements": requirements,
            "code_evidence": code_evidence,
            "code_coverage": code_coverage,
            "evidence_rules": {
                "paper": "paper_citation must exactly copy one citation from papers[].evidence",
                "code": "code_evidence_ids must only contain ids from code_evidence",
                "missing": "use status=missing with an empty code_evidence_ids list",
                "uncertain": "use status=uncertain when the supplied evidence cannot prove correspondence",
                "coverage": (
                    "When code_coverage.is_exhaustive is false, absence from selected evidence is not proof that the "
                    "implementation is missing; use uncertain instead."
                ),
            },
            "required_output": {
                "summary": "",
                "checks": [
                    {
                        "category": "algorithm|formula|data|preprocessing|parameter|metric|experiment",
                        "paper_claim": "",
                        "paper_citation": "",
                        "expected_behavior": "",
                        "status": "implemented|partial|missing|uncertain",
                        "code_evidence_ids": ["C1"],
                        "implementation_evidence": "",
                        "discrepancy": "",
                        "verification_action": "",
                    }
                ],
                "missing_components": [],
                "reproduction_risks": [],
                "recommended_next_checks": [],
            },
        }
        raw = self._invoke_json(
            (
                "Act as a paper-to-code implementation auditor. Decompose the papers into concrete algorithm steps, "
                "formulas, preprocessing operations, parameters, metrics, and experiment requirements. Match each "
                "claim only to supplied code evidence. Do not invent files, symbols, line numbers, citations, or "
                "implementation behavior. A similar name is not proof of implementation. Mark partial when only part "
                "of the required behavior is visible, missing when the requirement is absent from all supplied code, "
                "and uncertain when evidence is insufficient. Include specific verification actions."
            ),
            payload,
        )
        _check_cancel(cancel_check)
        verification_raw = self._invoke_json(
            (
                "Independently verify each proposed paper-to-code finding against the exact cited paper snippet and "
                "the exact code blocks supplied for that finding. Reject semantic mismatches even when citation and "
                "evidence IDs are syntactically valid. Similar names alone are insufficient. For implemented or "
                "partial findings, paper_claim_supported and code_status_supported must both be true only when the "
                "quoted evidence actually entails the claim and implementation status. For missing findings, only "
                "verify the paper claim; absence is handled separately by backend coverage rules."
            ),
            _correspondence_verification_payload(
                raw,
                paper_contexts,
                code_evidence,
            ),
        )
        correspondence = _ground_correspondence(
            raw,
            paper_contexts,
            code_evidence,
            verification_raw=verification_raw,
            code_coverage=code_coverage,
        )
        _check_cancel(cancel_check)
        updated = self.task_store.update(
            task_id,
            expected_revision=task["revision"],
            direction=normalized_direction,
            paper_ids=[item.id for item in papers],
            code_ids=[item.id for item in codes],
            correspondence=correspondence,
        )
        return {"task": updated, "correspondence": correspondence}

    def build_experiment(
        self,
        *,
        task_id: str,
        mode: str,
        objective: str = "",
        direction_index: int | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        _check_cancel(cancel_check)
        task = self.task_store.get(task_id)
        analysis = task.get("analysis")
        if not analysis:
            raise ToolInputError("Complete the multi-paper analysis before designing an experiment.")
        normalized_mode = mode if mode in {"reproduction", "mvp"} else "mvp"
        future = analysis.get("future_directions") or []
        selected_direction = (
            future[direction_index]
            if direction_index is not None and 0 <= direction_index < len(future)
            else None
        )
        payload = {
            "mode": normalized_mode,
            "objective": " ".join(objective.split()),
            "selected_direction": selected_direction,
            "research_analysis": analysis,
            "required_output": {
                "title": "",
                "mode": normalized_mode,
                "hypothesis": "",
                "scope": "",
                "assumptions": [],
                "environment": [],
                "datasets_or_inputs": [],
                "baseline": [],
                "implementation_steps": [],
                "measurements": [],
                "success_criteria": [],
                "stop_conditions": [],
                "risks": [],
                "codex_prompt": "",
            },
        }
        experiment = self._invoke_json(
            (
                "Design a reproducible research experiment. For reproduction mode, preserve the paper's assumptions, "
                "baselines, metrics, and expected outputs. For MVP mode, choose the smallest experiment that can "
                "falsify or support the hypothesis cheaply. Include explicit success criteria and stop conditions. "
                "The codex_prompt must be self-contained and precise enough for a strong coding agent: repository "
                "inspection, files to create or modify, dependencies, commands, tests, metrics, artifacts, constraints, "
                "and a final report format. Do not ask the coding agent to invent missing paper facts."
            ),
            payload,
        )
        _check_cancel(cancel_check)
        task = self.task_store.update(
            task_id,
            expected_revision=task["revision"],
            experiment=experiment,
        )
        return {"task": task, "experiment": experiment}

    def assess_result(
        self,
        *,
        task_id: str,
        result: str,
        attachment_ids: list[str] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        _check_cancel(cancel_check)
        task = self.task_store.get(task_id)
        experiment = task.get("experiment")
        if not experiment:
            raise ToolInputError("Create an experiment plan before submitting results.")
        cleaned_result = result.strip()
        selected_ids = set(attachment_ids or [])
        attachments = [
            item
            for item in (task.get("result_attachments") or [])
            if not selected_ids or item.get("id") in selected_ids
        ]
        attachment_context = []
        for item in attachments:
            content = str(item.get("content") or item.get("analysis") or "").strip()
            attachment_context.append(
                {
                    "id": item.get("id"),
                    "filename": item.get("filename"),
                    "kind": item.get("kind"),
                    "content": content[:20_000],
                    "vision_status": item.get("vision_status"),
                }
            )
        usable_attachment = any(item["content"] for item in attachment_context)
        if not cleaned_result and not usable_attachment:
            if attachments and all(item.get("kind") == "image" for item in attachments):
                raise ToolInputError(
                    "The uploaded images have not been analyzed. Configure the vision model or add text results."
                )
            raise ToolInputError("Experiment result cannot be empty.")
        payload = {
            "experiment": experiment,
            "observed_result": cleaned_result[:30_000],
            "result_attachments": attachment_context,
            "prior_decisions": task.get("decisions", [])[-5:],
            "required_output": {
                "decision": "continue|adjust|stop",
                "rationale": "",
                "observations": [],
                "failure_classification": "",
                "revised_hypothesis": "",
                "next_measurements": [],
                "revised_steps": [],
                "revised_codex_prompt": "",
                "stop_reason": "",
            },
        }
        decision = self._invoke_json(
            (
                "Act as a research supervisor reviewing an experiment result. Compare observations with success "
                "criteria and stop conditions. Choose exactly one decision: continue when evidence supports the plan, "
                "adjust when a specific correctable issue or informative alternative exists, and stop when the "
                "hypothesis is contradicted, the result is non-informative after reasonable fixes, or cost/risk "
                "exceeds expected value. For adjust, produce a concrete revised coding-agent prompt. For stop, explain "
                "what was learned and do not manufacture another experiment."
            ),
            payload,
        )
        _check_cancel(cancel_check)
        normalized = str(decision.get("decision") or "").lower()
        decision["decision"] = normalized if normalized in DECISIONS else "adjust"
        decisions = [
            *(task.get("decisions") or []),
            {
                "result": cleaned_result,
                "attachment_ids": [item.get("id") for item in attachment_context],
                **decision,
            },
        ]
        task = self.task_store.update(
            task_id,
            expected_revision=task["revision"],
            decisions=decisions,
        )
        return {"task": task, "assessment": decision}

    def _documents(self, ids: list[str], expected_type: DocumentType) -> list:
        documents = []
        for document_id in dict.fromkeys(str(item) for item in ids if item):
            document = self.repository.get_document(document_id)
            if document.document_type != expected_type:
                raise ToolInputError(
                    f"Document '{document.title}' is {document.document_type.value}, expected {expected_type.value}."
                )
            documents.append(document)
        return documents

    def _discovery_queries(self, direction: str, papers: list) -> list[str]:
        queries = []
        if direction:
            queries.append(self._english_search_query(direction, papers))
        queries.extend(
            title
            for title in (paper.title.strip() for paper in papers[:3])
            if title and not _contains_cjk(title)
        )
        cleaned = []
        for query in queries:
            normalized = _clean_search_query(query)
            if normalized and normalized.casefold() not in {item.casefold() for item in cleaned}:
                cleaned.append(normalized)
        if not cleaned:
            raise ToolInputError(
                "arXiv 需要英文检索词。请配置文字模型以转换中文研究方向，或选择带英文标题的本地论文。"
            )
        return cleaned[:4]

    def _english_search_query(self, direction: str, papers: list) -> str:
        paper_hint = self._local_paper_search_hint(papers)
        prompt_like = "\n" in direction or len(direction) > 140 or bool(
            re.search(
                r"(研究主题|研究目标|关注|排除|补充要求|topic|goal|focus|exclude|requirement)\s*[:：]",
                direction,
                re.I,
            )
        )
        if self.model is None:
            return " ".join(filter(None, (direction, paper_hint)))
        if not _contains_cjk(direction) and not prompt_like:
            return " ".join(filter(None, (direction, paper_hint)))
        response = self.model.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "Convert the full research-discovery prompt into a concise English arXiv search query. "
                        "Use the selected local paper excerpts to disambiguate the research domain. "
                        "Respect later additions to the prompt, especially requested focus and exclusions. "
                        "The query must include the core technical topic, not only ambiguous words from the "
                        "prompt. Keep established technical abbreviations and return only 3 to 12 English keywords, "
                        "without explanation, punctuation, quotes, or search syntax."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "research_prompt": direction,
                            "local_papers": [
                                {
                                    "title": paper.title,
                                    "excerpt": (self.repository.read_searchable_text(paper) or "")[:1400],
                                }
                                for paper in papers[:3]
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ]
        )
        raw = getattr(response, "content", response)
        if isinstance(raw, list):
            raw = " ".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in raw
            )
        return " ".join(filter(None, (str(raw or ""), paper_hint)))

    def _local_paper_search_hint(self, papers: list) -> str:
        hints = []
        for paper in papers[:2]:
            text = (self.repository.read_searchable_text(paper) or "").encode(
                "ascii", errors="ignore"
            ).decode("ascii")
            lines = [
                " ".join(line.split())
                for line in text.splitlines()
                if line.strip() and not re.fullmatch(r"\[?page\s+\d+\]?", line.strip(), re.I)
            ]
            candidate = next(
                (
                    line
                    for line in lines[:12]
                    if 3 <= len(_search_terms(line)) <= 14
                    and not re.fullmatch(r"(abstract|introduction)", line, re.I)
                ),
                "",
            )
            if not candidate and not _contains_cjk(paper.title):
                candidate = paper.title
            if candidate:
                hints.append(candidate)
        return " ".join(hints)

    def _local_paper_titles(self, papers: list) -> set[str]:
        titles = set()
        for paper in papers:
            titles.add(_normalized_title(paper.title))
            text = (self.repository.read_searchable_text(paper) or "").encode(
                "ascii", errors="ignore"
            ).decode("ascii")
            lines = [
                " ".join(line.split())
                for line in text.splitlines()
                if line.strip() and not re.fullmatch(r"\[?page\s+\d+\]?", line.strip(), re.I)
            ]
            for line in lines[:12]:
                if 3 <= len(_search_terms(line)) <= 20:
                    titles.add(_normalized_title(line))
                    break
        return {title for title in titles if title}

    def _summarize_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates:
            return candidates
        summaries = {}
        if self.model is not None:
            try:
                result = self._invoke_json(
                    (
                        "Write one compact recall-oriented overview for each arXiv paper from its title and "
                        "abstract. State the problem and main approach or finding in one sentence. Do not add "
                        "facts absent from the abstract. Keep each overview under 90 Chinese characters or "
                        "45 English words."
                    ),
                    {
                        "papers": [
                            {
                                "id": item["id"],
                                "title": item["title"],
                                "abstract": item.get("summary", ""),
                            }
                            for item in candidates
                        ],
                        "required_output": {
                            "summaries": [
                                {"id": "paper id", "brief_summary": "one concise sentence"}
                            ]
                        },
                    },
                )
                summaries = {
                    str(item.get("id") or ""): str(item.get("brief_summary") or "").strip()
                    for item in result.get("summaries", [])
                    if isinstance(item, dict)
                }
            except Exception:
                summaries = {}
        return [
            {
                **item,
                "brief_summary": summaries.get(item["id"]) or _abstract_brief(item.get("summary", "")),
            }
            for item in candidates
        ]

    def _paper_context(self, document) -> dict[str, Any]:
        chunks = self.repository.read_chunks(document)
        priority = ("abstract", "introduction", "method", "experiment", "result", "discussion", "limitation", "conclusion")
        ordered = sorted(
            chunks,
            key=lambda item: (
                next(
                    (index for index, key in enumerate(priority) if key in str(item.metadata.get("section", "")).casefold()),
                    len(priority),
                ),
                int(item.metadata.get("page") or 0),
                item.chunk_id,
            ),
        )
        evidence = []
        used = 0
        for chunk in ordered:
            record = evidence_record(_chunk_result(document, chunk))
            text = record["snippet"][:1800]
            if used + len(text) > 14_000:
                break
            record["snippet"] = text
            evidence.append(record)
            used += len(text)
        if not evidence:
            text = (self.repository.read_searchable_text(document) or "")[:14_000]
            evidence.append({"snippet": text, "citation": f"[{document.title} | local full text]"})
        return {
            "id": document.id,
            "title": document.title,
            "field": document.field,
            "evidence": evidence,
        }

    def _code_context(self, documents: list) -> list[dict[str, Any]]:
        context = []
        remaining = 45_000
        for document in documents[:80]:
            if remaining <= 0:
                break
            content = (self.repository.read_searchable_text(document) or "")[: min(8_000, remaining)]
            context.append(
                {
                    "id": document.id,
                    "path": document.source or document.title,
                    "content": content,
                }
            )
            remaining -= len(content)
        return context

    def _code_evidence_context(
        self,
        documents: list,
        *,
        requirements: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        budget = 70_000
        search_terms = _requirement_search_terms(requirements)
        candidates = []
        readable_files = 0
        scanned_files = 0
        source_truncated = False
        for document in documents[:3000]:
            content = self.repository.read_searchable_text(document) or ""
            if not content.strip():
                continue
            readable_files += 1
            path = document.source or document.title
            capped = content[:1_000_000]
            if len(capped) < len(content):
                source_truncated = True
            scanned_files += 1
            lines = capped.splitlines()
            for start in range(0, len(lines), 80):
                block = lines[start : start + 80]
                numbered, visible_lines = _fit_numbered_lines(
                    block,
                    start_line=start + 1,
                    max_chars=9_000,
                )
                if not numbered.strip() or not visible_lines:
                    continue
                symbols = _extract_code_symbols(visible_lines, start_line=start + 1)
                candidates.append(
                    {
                        "document_id": document.id,
                        "path": path,
                        "line_start": start + 1,
                        "line_end": start + len(visible_lines),
                        "symbols": symbols,
                        "content": numbered,
                        "_score": _code_block_score(
                            path,
                            numbered,
                            symbols,
                            search_terms,
                        ),
                    }
                )

        total_candidate_chars = sum(len(item["content"]) for item in candidates)
        exhaustive = (
            len(documents) <= 3000
            and readable_files == len(documents)
            and not source_truncated
            and total_candidate_chars <= budget
        )
        if exhaustive:
            selected = candidates
        else:
            ranked = sorted(
                candidates,
                key=lambda item: (
                    -item["_score"],
                    item["path"].casefold(),
                    item["line_start"],
                ),
            )
            selected = []
            remaining = budget
            selected_paths = set()
            for candidate in ranked:
                content_length = len(candidate["content"])
                if content_length > remaining:
                    continue
                # Preserve project coverage before taking additional blocks from the same file.
                if candidate["path"] in selected_paths and any(
                    item["path"] not in selected_paths for item in ranked
                ):
                    continue
                selected.append(candidate)
                selected_paths.add(candidate["path"])
                remaining -= content_length
            for candidate in ranked:
                if candidate in selected:
                    continue
                content_length = len(candidate["content"])
                if content_length > remaining:
                    continue
                selected.append(candidate)
                remaining -= content_length
                if remaining <= 0:
                    break
            selected.sort(key=lambda item: (-item["_score"], item["path"].casefold(), item["line_start"]))

        evidence = []
        for evidence_index, candidate in enumerate(selected, start=1):
            evidence.append(
                {
                    "id": f"C{evidence_index}",
                    **{key: value for key, value in candidate.items() if key != "_score"},
                    "retrieval_score": round(float(candidate["_score"]), 4),
                }
            )
        selected_files = len({item["path"] for item in evidence})
        coverage = {
            "total_selected_documents": len(documents),
            "readable_files": readable_files,
            "scanned_files": scanned_files,
            "selected_files": selected_files,
            "candidate_blocks": len(candidates),
            "selected_blocks": len(evidence),
            "is_exhaustive": exhaustive,
            "source_truncated": source_truncated or len(documents) > 3000,
            "selection_basis": "paper_requirement_retrieval",
        }
        return evidence, coverage

    def _invoke_json(self, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.model.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        system
                        + " Return one valid JSON object matching required_output. Do not wrap it in Markdown."
                        + f"\n\n{response_language_instruction(self.language)}"
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
        )
        raw = getattr(response, "content", response)
        if isinstance(raw, list):
            raw = "".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in raw
            )
        match = re.search(r"\{.*\}", str(raw or ""), re.S)
        if not match:
            raise FinalsAgentError("Research assistant model did not return a JSON object.")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise FinalsAgentError("Research assistant model returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise FinalsAgentError("Research assistant response must be a JSON object.")
        return data


def _ground_correspondence_requirements(
    raw: dict[str, Any],
    paper_contexts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    citation_map = {
        str(item.get("citation") or ""): str(item.get("snippet") or "")
        for paper in paper_contexts
        for item in paper.get("evidence", [])
        if item.get("citation")
    }
    requirements = []
    for item in raw.get("requirements", [])[:30]:
        if not isinstance(item, dict):
            continue
        citation = str(item.get("paper_citation") or "").strip()
        claim = _clip_text(item.get("paper_claim"), 1000)
        if not claim or citation not in citation_map:
            continue
        requirements.append(
            {
                "id": f"R{len(requirements) + 1}",
                "category": _choice(
                    item.get("category"),
                    {"algorithm", "formula", "data", "preprocessing", "parameter", "metric", "experiment"},
                    "algorithm",
                ),
                "paper_claim": claim,
                "paper_citation": citation,
                "paper_snippet": citation_map[citation],
                "expected_behavior": _clip_text(item.get("expected_behavior"), 1200),
                "code_search_terms": _string_items(item.get("code_search_terms"), 20),
            }
        )
    return requirements


def _correspondence_verification_payload(
    raw: dict[str, Any],
    paper_contexts: list[dict[str, Any]],
    code_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    citation_map = {
        str(item.get("citation") or ""): str(item.get("snippet") or "")
        for paper in paper_contexts
        for item in paper.get("evidence", [])
        if item.get("citation")
    }
    code_by_id = {str(item["id"]): item for item in code_evidence}
    checks = []
    for index, item in enumerate(raw.get("checks", [])):
        if not isinstance(item, dict):
            continue
        citation = str(item.get("paper_citation") or "").strip()
        requested_ids = item.get("code_evidence_ids")
        if not isinstance(requested_ids, list):
            requested_ids = []
        checks.append(
            {
                "check_index": index,
                "paper_claim": _clip_text(item.get("paper_claim"), 1000),
                "paper_citation": citation,
                "paper_snippet": citation_map.get(citation, ""),
                "expected_behavior": _clip_text(item.get("expected_behavior"), 1200),
                "proposed_status": str(item.get("status") or "uncertain"),
                "implementation_evidence": _clip_text(item.get("implementation_evidence"), 1600),
                "code_evidence": [
                    {
                        "id": evidence_id,
                        "path": code_by_id[evidence_id]["path"],
                        "line_start": code_by_id[evidence_id]["line_start"],
                        "line_end": code_by_id[evidence_id]["line_end"],
                        "content": code_by_id[evidence_id]["content"],
                    }
                    for evidence_id in (str(value) for value in requested_ids)
                    if evidence_id in code_by_id
                ],
            }
        )
    return {
        "checks": checks,
        "required_output": {
            "verified_summary": "",
            "verdicts": [
                {
                    "check_index": 0,
                    "paper_claim_supported": False,
                    "code_status_supported": False,
                    "rationale": "",
                }
            ],
        },
    }


def _ground_correspondence(
    raw: dict[str, Any],
    paper_contexts: list[dict[str, Any]],
    code_evidence: list[dict[str, Any]],
    *,
    verification_raw: dict[str, Any] | None = None,
    code_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    allowed_citations = {
        str(item.get("citation") or "")
        for paper in paper_contexts
        for item in paper.get("evidence", [])
        if item.get("citation")
    }
    code_by_id = {str(item["id"]): item for item in code_evidence}
    verification_raw = verification_raw or {}
    verdicts = {
        int(item.get("check_index")): item
        for item in verification_raw.get("verdicts", [])
        if isinstance(item, dict) and str(item.get("check_index", "")).isdigit()
    }
    coverage = dict(code_coverage or {})
    exhaustive = bool(coverage.get("is_exhaustive"))
    grounded_checks = []
    for check_index, raw_check in enumerate(raw.get("checks", [])):
        if not isinstance(raw_check, dict):
            continue
        status = str(raw_check.get("status") or "uncertain").lower()
        if status not in {"implemented", "partial", "missing", "uncertain"}:
            status = "uncertain"
        citation = str(raw_check.get("paper_citation") or "").strip()
        citation_valid = citation in allowed_citations
        requested_ids = raw_check.get("code_evidence_ids")
        if not isinstance(requested_ids, list):
            requested_ids = []
        evidence_ids = [
            str(item)
            for item in requested_ids
            if str(item) in code_by_id
        ]
        verdict = verdicts.get(check_index, {})
        paper_supported = verdict.get("paper_claim_supported") is True
        code_supported = verdict.get("code_status_supported") is True
        if status in {"implemented", "partial"} and (
            not citation_valid
            or not evidence_ids
            or not paper_supported
            or not code_supported
        ):
            status = "uncertain"
        if status == "missing":
            evidence_ids = []
            if not citation_valid or not paper_supported or not exhaustive:
                status = "uncertain"
        locations = [
            {
                "evidence_id": evidence_id,
                "document_id": code_by_id[evidence_id]["document_id"],
                "path": code_by_id[evidence_id]["path"],
                "line_start": code_by_id[evidence_id]["line_start"],
                "line_end": code_by_id[evidence_id]["line_end"],
                "symbols": code_by_id[evidence_id]["symbols"],
            }
            for evidence_id in evidence_ids
        ]
        grounded_checks.append(
            {
                "category": _choice(
                    raw_check.get("category"),
                    {"algorithm", "formula", "data", "preprocessing", "parameter", "metric", "experiment"},
                    "algorithm",
                ),
                "paper_claim": _clip_text(raw_check.get("paper_claim"), 1000),
                "paper_citation": citation if citation_valid else "",
                "paper_citation_valid": citation_valid,
                "expected_behavior": _clip_text(raw_check.get("expected_behavior"), 1200),
                "status": status,
                "code_evidence_ids": evidence_ids,
                "code_locations": locations,
                "implementation_evidence": _clip_text(raw_check.get("implementation_evidence"), 1600),
                "discrepancy": _clip_text(raw_check.get("discrepancy"), 1200),
                "verification_action": _clip_text(raw_check.get("verification_action"), 1200),
                "verification": {
                    "paper_claim_supported": paper_supported,
                    "code_status_supported": code_supported,
                    "passed": (
                        paper_supported and code_supported
                        if status in {"implemented", "partial"}
                        else paper_supported and exhaustive
                        if status == "missing"
                        else False
                    ),
                    "rationale": _clip_text(verdict.get("rationale"), 1000),
                },
            }
        )
    status_counts = {
        status: sum(1 for item in grounded_checks if item["status"] == status)
        for status in ("implemented", "partial", "missing", "uncertain")
    }
    verified = status_counts["implemented"] + status_counts["partial"]
    coverage_percent = round(verified / len(grounded_checks) * 100) if grounded_checks else 0
    verified_summary = _clip_text(verification_raw.get("verified_summary"), 2400)
    summary = verified_summary or (
        f"Verified {verified} of {len(grounded_checks)} findings against exact paper and code evidence."
    )
    missing_components = (
        _string_items(raw.get("missing_components"), 30)
        if exhaustive
        else []
    )
    return {
        "summary": summary,
        "checks": grounded_checks,
        "status_counts": status_counts,
        "coverage_percent": coverage_percent,
        "missing_components": missing_components,
        "unverified_absence_candidates": (
            [] if exhaustive else _string_items(raw.get("missing_components"), 30)
        ),
        "reproduction_risks": _string_items(raw.get("reproduction_risks"), 30),
        "recommended_next_checks": _string_items(raw.get("recommended_next_checks"), 30),
        "paper_count": len(paper_contexts),
        "code_evidence_count": len(code_evidence),
        "code_coverage": coverage,
    }


def _extract_code_symbols(lines: list[str], *, start_line: int) -> list[dict[str, Any]]:
    patterns = (
        re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)"),
        re.compile(r"^\s*class\s+([A-Za-z_]\w*)"),
        re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"),
        re.compile(
            r"^\s*(?:public|private|protected|static|final|async|\s)+"
            r"[A-Za-z_$][\w$<>,\[\]? ]*\s+([A-Za-z_$][\w$]*)\s*\("
        ),
    )
    symbols = []
    for offset, line in enumerate(lines):
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                symbols.append({"name": match.group(1), "line": start_line + offset})
                break
    return symbols[:30]


def _fit_numbered_lines(
    lines: list[str],
    *,
    start_line: int,
    max_chars: int,
) -> tuple[str, list[str]]:
    rendered = []
    visible_lines = []
    used = 0
    for offset, line in enumerate(lines):
        prefix = f"{start_line + offset}: "
        available = max_chars - used
        if available <= len(prefix):
            break
        rendered_line = prefix + line
        if len(rendered_line) + (1 if rendered else 0) > available:
            if rendered:
                break
            clipped_line = line[: max(0, available - len(prefix))]
            rendered.append(prefix + clipped_line)
            visible_lines.append(clipped_line)
            break
        rendered.append(rendered_line)
        visible_lines.append(line)
        used += len(rendered_line) + (1 if len(rendered) > 1 else 0)
    return "\n".join(rendered), visible_lines


def _requirement_search_terms(requirements: list[dict[str, Any]]) -> list[str]:
    terms = []
    for requirement in requirements:
        values = [
            *requirement.get("code_search_terms", []),
            requirement.get("paper_claim", ""),
            requirement.get("expected_behavior", ""),
        ]
        for value in values:
            normalized = " ".join(str(value or "").split()).casefold()
            if not normalized:
                continue
            if len(normalized) <= 80:
                terms.append(normalized)
            terms.extend(_technical_tokens(normalized))
    return list(dict.fromkeys(term for term in terms if term))[:200]


def _technical_tokens(value: str) -> list[str]:
    ignored = {
        "about", "after", "algorithm", "before", "code", "data", "each", "from",
        "implementation", "method", "model", "paper", "result", "should", "that",
        "their", "these", "this", "using", "with",
    }
    tokens = []
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}|[\u3400-\u9fff]{2,8}", value):
        lowered = token.casefold()
        if lowered not in ignored:
            tokens.append(lowered)
    return tokens


def _code_block_score(
    path: str,
    content: str,
    symbols: list[dict[str, Any]],
    search_terms: list[str],
) -> float:
    haystack = " ".join(
        (
            path.casefold(),
            content.casefold(),
            " ".join(str(item.get("name") or "").casefold() for item in symbols),
        )
    )
    score = 0.0
    for term in search_terms:
        if not term:
            continue
        occurrences = haystack.count(term)
        if occurrences:
            score += min(occurrences, 5) * (3.0 if " " in term or "_" in term else 1.0)
            if term in path.casefold():
                score += 4.0
    if symbols:
        score += 0.25
    if re.search(r"(?:^|/)(?:test|tests|benchmark|benchmarks|eval|evaluation)(?:/|$)", path, re.I):
        score += 0.15
    if re.search(r"(?:lock|package-lock|yarn\.lock|min\.js|dist|build|generated)", path, re.I):
        score -= 2.0
    return score


def _check_cancel(cancel_check: Callable[[], None] | None) -> None:
    if cancel_check is not None:
        cancel_check()


def _clip_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _string_items(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clip_text(item, 800) for item in value[:limit] if _clip_text(item, 800)]


def _choice(value: Any, allowed: set[str], fallback: str) -> str:
    normalized = str(value or "").lower()
    return normalized if normalized in allowed else fallback


def _external_candidate(paper: ExternalPaper) -> dict[str, Any]:
    payload = paper.to_dict()
    payload["id"] = sha1((paper.url or paper.title).encode("utf-8")).hexdigest()[:12]
    payload["source_level"] = "external_abstract"
    return payload


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value or ""))


def _normalize_research_prompt(value: str) -> str:
    lines = [" ".join(line.split()) for line in str(value or "").replace("\r\n", "\n").split("\n")]
    normalized = "\n".join(lines).strip()
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized[:8000]


def _clean_search_query(value: str) -> str:
    ascii_text = str(value or "").encode("ascii", errors="ignore").decode("ascii")
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+.#/_-]*", ascii_text)
    return " ".join(words[:18])[:256]


def _search_terms(value: str) -> set[str]:
    ignored = {
        "a", "an", "and", "for", "in", "of", "on", "the", "to", "with",
        "paper", "papers", "study", "studies", "research", "method", "methods",
        "approach", "approaches", "model", "models", "using", "based", "local",
        "related", "work", "works", "via", "from", "into", "toward", "towards",
    }
    return {
        word.casefold()
        for word in re.findall(r"[A-Za-z0-9][A-Za-z0-9+.#_-]*", value or "")
        if len(word) > 2 and word.casefold() not in ignored
    }


def _external_match_score(paper: ExternalPaper, query: str) -> int:
    return _external_match_details(paper, query)[0]


def _external_match_details(paper: ExternalPaper, query: str) -> tuple[int, list[str]]:
    haystack = " ".join((paper.title, paper.summary, " ".join(paper.categories))).casefold()
    matched = sorted(term for term in _search_terms(query) if term in haystack)
    return len(matched), matched


def _minimum_external_match_score(query: str) -> int:
    term_count = len(_search_terms(query))
    if term_count < 3:
        return 1
    if term_count >= 8:
        return 3
    return 2


def _normalized_title(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _abstract_brief(value: str, max_chars: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    brief = " ".join(sentences[:2]).strip()
    if len(brief) <= max_chars:
        return brief
    clipped = brief[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:")
    return (clipped or brief[:max_chars]).rstrip() + "…"


def _clean_external(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or "")[:40],
        "title": str(item.get("title") or "")[:500],
        "authors": [str(author)[:200] for author in item.get("authors", [])[:30]],
        "summary": str(item.get("summary") or "")[:12_000],
        "url": str(item.get("url") or "")[:1000],
        "published": item.get("published"),
        "categories": [str(value)[:100] for value in item.get("categories", [])[:20]],
        "source_level": "external_abstract",
    }


def _chunk_result(document, chunk):
    from finals_agent.core.schemas import SearchResult

    return SearchResult(
        document_id=document.id,
        title=document.title,
        document_type=document.document_type,
        course=document.field,
        path=document.path,
        snippet=chunk.text,
        score=1.0,
        source=document.source,
        chunk_id=chunk.chunk_id,
        page=chunk.metadata.get("page"),
        section=chunk.metadata.get("section"),
        block_type=chunk.metadata.get("block_type"),
    )
