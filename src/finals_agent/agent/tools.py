from __future__ import annotations

from typing import Any

from finals_agent.core.events import emit_event
from finals_agent.core.exceptions import FinalsAgentError, ToolInputError
from finals_agent.core.runtime import AgentRuntime
from finals_agent.core.schemas import DocumentType, SearchRequest
from finals_agent.core.tool_protocol import expected_tool_error, tool_empty, tool_error, tool_success
from finals_agent.agent.tool_registry import (
    ANALYZE_PAPER_STRUCTURE,
    COMPARE_PAPER_INNOVATIONS,
    DISCOVER_RESEARCH_PAPERS,
    EXPLAIN_PAPER_TARGET,
    GET_READING_STATE,
    IMPORT_ARXIV_PAPER,
    INTELLIGENT_SEARCH_LOCAL_EVIDENCE,
    LIST_PAPERS,
    ANALYZE_RESEARCH_MATERIALS,
    CHECK_PAPER_CODE_CORRESPONDENCE,
    READ_PAPER_WORKFLOW,
    SEARCH_LOCAL_PAPERS,
    SEARCH_RELATED_PAPERS,
    UPDATE_READING_STATE,
)
from finals_agent.data.external_search import ArxivPaperSearch
from finals_agent.data.embeddings import build_embedding_provider
from finals_agent.data.paper_analysis import PaperStructureAnalyzer
from finals_agent.data.paper_download import import_arxiv_paper as import_arxiv_document
from finals_agent.data.reading_intelligence import ReadingIntelligence
from finals_agent.data.repository import StudyRepository
from finals_agent.data.research_assistant import ResearchAssistant
from finals_agent.data.retrievers import HybridRetriever, Retriever
from finals_agent.data.selection import select_document
from finals_agent.data.workflows import PaperReadingWorkflow
from finals_agent.persistence.reading_state import ReadingStateStore, reading_state_summary
from finals_agent.persistence.research_tasks import ResearchTaskStore


def build_tools(
    repository: StudyRepository | None = None,
    runtime: AgentRuntime | None = None,
    retriever: Retriever | None = None,
    external_search: ArxivPaperSearch | None = None,
    reading_store: ReadingStateStore | None = None,
    research_task_store: ResearchTaskStore | None = None,
    model=None,
):
    from langchain.tools import tool

    repository = repository or StudyRepository()
    runtime = runtime or AgentRuntime.default()
    retriever = retriever or HybridRetriever(repository=repository, embedding_provider=build_embedding_provider())
    external_search = external_search or ArxivPaperSearch()
    analyzer = PaperStructureAnalyzer(repository=repository)
    reading_store = reading_store or ReadingStateStore()
    workflow = PaperReadingWorkflow(
        repository=repository,
        retriever=retriever,
        external_search=external_search,
        reading_store=reading_store,
    )
    shared_model = model

    def get_model():
        nonlocal shared_model
        if shared_model is None:
            from finals_agent.agent.llm import build_chat_model

            shared_model = build_chat_model()
        return shared_model

    @tool
    def list_papers(field: str | None = None) -> str:
        """List locally uploaded papers and reading notes, optionally filtered by research field."""
        tool_name = LIST_PAPERS
        _emit_tool_started(tool_name, field=field)
        try:
            effective_field = field or runtime.course_context.field
            documents = repository.list_documents(field=effective_field)
            metadata = {"field": effective_field, "count": len(documents)}

            if not documents:
                return tool_empty(tool_name, "No local papers found.", metadata=metadata)

            return tool_success(
                tool_name,
                f"Found {len(documents)} local paper document(s).",
                data=[doc.to_dict() for doc in documents],
                metadata=metadata,
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Unexpected tool failure.", exc)

    @tool
    def search_local_papers(
        query: str,
        field: str | None = None,
        document_id: str | None = None,
        title: str | None = None,
        document_type: str | None = None,
        focus: str | None = None,
    ) -> str:
        """Search locally uploaded papers, supplements, related-work notes, and reading notes."""
        tool_name = SEARCH_LOCAL_PAPERS
        _emit_tool_started(
            tool_name,
            query=query,
            field=field,
            document_id=document_id,
            title=title,
            document_type=document_type,
            focus=focus,
        )
        try:
            try:
                parsed_type = DocumentType(document_type) if document_type else None
            except ValueError as exc:
                allowed = ", ".join(item.value for item in DocumentType)
                raise ToolInputError(f"Invalid document_type. Allowed values: {allowed}.") from exc

            effective_field = field or runtime.course_context.field
            effective_focus = focus or runtime.course_context.focus
            effective_document_id = document_id or runtime.course_context.target_document_id
            effective_title = title or runtime.course_context.target_title
            if not effective_document_id and effective_title:
                effective_document_id = select_document(
                    repository,
                    title=effective_title,
                    field=effective_field,
                    document_type=parsed_type or DocumentType.PAPER,
                    retriever=retriever,
                ).id
            response = retriever.search(
                SearchRequest(
                    query=query,
                    field=effective_field,
                    document_id=effective_document_id,
                    document_type=parsed_type,
                    focus=effective_focus,
                    limit=runtime.max_search_results,
                )
            )
            metadata = response.metadata

            if not response.results:
                return tool_empty(tool_name, "No matching local paper snippet found.", metadata=metadata)

            return tool_success(
                tool_name,
                f"Found {response.count} matching local paper snippet(s).",
                data=[item.to_dict() for item in response.results],
                metadata=metadata,
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Unexpected tool failure.", exc)

    @tool
    def intelligent_search_local_evidence(
        query: str,
        document_id: str | None = None,
        title: str | None = None,
        field: str | None = None,
        document_type: str | None = None,
        limit: int = 8,
    ) -> str:
        """Understand a paper question, run several complementary local searches, rerank evidence, and return complete passages."""
        tool_name = INTELLIGENT_SEARCH_LOCAL_EVIDENCE
        _emit_tool_started(
            tool_name,
            query=query,
            document_id=document_id,
            title=title,
            field=field,
            document_type=document_type,
            limit=limit,
        )
        try:
            try:
                parsed_type = DocumentType(document_type) if document_type else None
            except ValueError as exc:
                allowed = ", ".join(item.value for item in DocumentType)
                raise ToolInputError(f"Invalid document_type. Allowed values: {allowed}.") from exc
            effective_document_id = document_id or runtime.course_context.target_document_id
            effective_title = title or runtime.course_context.target_title
            document = None
            if effective_document_id or effective_title:
                document = select_document(
                    repository,
                    document_id=effective_document_id,
                    title=effective_title,
                    field=field or runtime.course_context.field,
                    document_type=parsed_type or DocumentType.PAPER,
                    retriever=retriever,
                )
            result = ReadingIntelligence(
                get_model(),
                repository=repository,
            ).search(
                query,
                retriever,
                document=document,
                field=field or runtime.course_context.field,
                document_type=parsed_type,
                limit=max(1, min(limit, 20)),
            )
            if not result["results"]:
                return tool_empty(
                    tool_name,
                    "No grounded local evidence was found after query rewriting and reranking.",
                    metadata=result["metadata"],
                )
            return tool_success(
                tool_name,
                f"Found {len(result['results'])} reranked local evidence passage(s).",
                data=result,
                metadata={
                    **result["metadata"],
                    "intent": result["intent"],
                    "result_count": len(result["results"]),
                },
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Intelligent evidence search failed.", exc)

    @tool
    def analyze_paper_structure(
        document_id: str | None = None,
        title: str | None = None,
        query: str | None = None,
    ) -> str:
        """Analyze a local paper and identify sections, paragraphs, figure/table captions, and formula candidates."""
        tool_name = ANALYZE_PAPER_STRUCTURE
        _emit_tool_started(tool_name, document_id=document_id, title=title, query=query)
        try:
            structure = analyzer.analyze(
                document_id=document_id or runtime.course_context.target_document_id,
                title=title or runtime.course_context.target_title,
                query=query,
            )
            return tool_success(
                tool_name,
                "Analyzed local paper structure.",
                data=structure.to_dict(),
                metadata={
                    "document_id": structure.document_id,
                    "title": structure.title,
                    "section_count": len(structure.section_headings),
                    "figure_caption_count": len(structure.figure_captions),
                    "table_caption_count": len(structure.table_captions),
                    "formula_candidate_count": len(structure.formula_candidates),
                },
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Unexpected tool failure.", exc)

    @tool
    def search_related_papers(topic: str, limit: int = 5) -> str:
        """Search arXiv for papers related to a topic, method, title, or abstract."""
        tool_name = SEARCH_RELATED_PAPERS
        _emit_tool_started(tool_name, topic=topic, limit=limit)
        try:
            if not topic.strip():
                raise ToolInputError("topic cannot be empty.")
            papers = external_search.search(topic, limit=limit)
            metadata = {"topic": topic, "count": len(papers), "source": "arxiv"}

            if not papers:
                return tool_empty(tool_name, "No related papers found from arXiv.", metadata=metadata)

            return tool_success(
                tool_name,
                f"Found {len(papers)} related paper(s) from arXiv.",
                data=[paper.to_dict() for paper in papers],
                metadata=metadata,
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Related-paper search failed.", exc)

    @tool
    def compare_paper_innovations(
        topic: str,
        document_id: str | None = None,
        title: str | None = None,
        local_query: str | None = None,
        field: str | None = None,
        limit: int = 5,
    ) -> str:
        """Gather local and arXiv evidence for comparing innovation points and differences across papers."""
        tool_name = COMPARE_PAPER_INNOVATIONS
        _emit_tool_started(
            tool_name,
            topic=topic,
            document_id=document_id,
            title=title,
            local_query=local_query,
            field=field,
            limit=limit,
        )
        try:
            if not topic.strip():
                raise ToolInputError("topic cannot be empty.")

            result = workflow.compare(
                topic=topic,
                document_id=document_id or runtime.course_context.target_document_id,
                title=title or runtime.course_context.target_title,
                query=local_query,
                field=field or runtime.course_context.field,
                related_limit=limit,
            )
            data = result.to_dict()["data"]
            return tool_success(
                tool_name,
                "Collected evidence for innovation comparison.",
                data=data,
                metadata={
                    "topic": topic,
                    "local_count": len(data["local_evidence"]),
                    "related_count": len(data["related_papers"]),
                    "source": "local_repository+arxiv",
                },
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Innovation comparison failed.", exc)

    @tool
    def read_paper_workflow(
        document_id: str | None = None,
        title: str | None = None,
        query: str | None = None,
        field: str | None = None,
        related_limit: int = 0,
    ) -> str:
        """Build an evidence-backed reading workflow for one local paper."""
        tool_name = READ_PAPER_WORKFLOW
        _emit_tool_started(
            tool_name,
            document_id=document_id,
            title=title,
            query=query,
            field=field,
            related_limit=related_limit,
        )
        try:
            result = workflow.read(
                document_id=document_id or runtime.course_context.target_document_id,
                title=title or runtime.course_context.target_title,
                query=query,
                field=field or runtime.course_context.field,
                related_limit=related_limit,
            )
            data = result.to_dict()["data"]
            return tool_success(
                tool_name,
                "Built paper reading workflow.",
                data=data,
                metadata={
                    "document_id": data["paper"]["id"],
                    "title": data["paper"]["title"],
                    "evidence_count": len(data["evidence"]),
                    "section_pass_count": len(data.get("section_passes", [])),
                    "section_coverage_ratio": (data.get("coverage") or {}).get("coverage_ratio"),
                    "related_count": len(data["related_papers"]),
                },
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Paper reading workflow failed.", exc)

    @tool
    def explain_paper_target(
        target: str,
        document_id: str | None = None,
        title: str | None = None,
        query: str | None = None,
        field: str | None = None,
        limit: int = 5,
    ) -> str:
        """Build a focused explanation workflow for a paper section, paragraph, figure, table, formula, or concept."""
        tool_name = EXPLAIN_PAPER_TARGET
        _emit_tool_started(
            tool_name,
            target=target,
            document_id=document_id,
            title=title,
            query=query,
            field=field,
            limit=limit,
        )
        try:
            result = workflow.explain(
                target=target,
                document_id=document_id or runtime.course_context.target_document_id,
                title=title or runtime.course_context.target_title,
                query=query,
                field=field or runtime.course_context.field,
                limit=limit,
            )
            data = result.to_dict()["data"]
            return tool_success(
                tool_name,
                "Built focused paper explanation workflow.",
                data=data,
                metadata={
                    "document_id": data["paper"]["id"],
                    "target": target,
                    "evidence_count": len(data["evidence"]),
                    "matched_structure_count": len(data["matched_structure_candidates"]),
                },
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Focused explanation workflow failed.", exc)

    @tool
    def get_reading_state(
        document_id: str | None = None,
        title: str | None = None,
        field: str | None = None,
    ) -> str:
        """Get reading progress, notes, open questions, verification items, and flashcards for a local paper."""
        tool_name = GET_READING_STATE
        _emit_tool_started(tool_name, document_id=document_id, title=title, field=field)
        try:
            document = select_document(
                repository,
                document_id=document_id or runtime.course_context.target_document_id,
                title=title or runtime.course_context.target_title,
                field=field or runtime.course_context.field,
                document_type=None,
                retriever=retriever,
            )
            state = reading_store.get(document)
            data = reading_state_summary(state)
            return tool_success(
                tool_name,
                "Loaded reading state for local paper.",
                data=data,
                metadata={
                    "document_id": document.id,
                    "title": document.title,
                    "status": state.status,
                    "progress_percent": state.progress_percent,
                    "open_question_count": state.open_question_count,
                    "open_verification_count": state.open_verification_count,
                },
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Reading state lookup failed.", exc)

    @tool
    def update_reading_state(
        document_id: str | None = None,
        title: str | None = None,
        field: str | None = None,
        status: str | None = None,
        current_section: str | None = None,
        progress_percent: int | None = None,
        review_summary: str | None = None,
        note: str | None = None,
        question: str | None = None,
        verification_item: str | None = None,
        flashcard_question: str | None = None,
        flashcard_answer: str | None = None,
        section: str | None = None,
        page: int | None = None,
        citation: str | None = None,
        item_id: str | None = None,
        item_status: str | None = None,
    ) -> str:
        """Update reading progress or add a note, question, verification item, or flashcard for a local paper."""
        tool_name = UPDATE_READING_STATE
        _emit_tool_started(
            tool_name,
            document_id=document_id,
            title=title,
            field=field,
            status=status,
            current_section=current_section,
            progress_percent=progress_percent,
            review_summary=review_summary,
            note=note,
            question=question,
            verification_item=verification_item,
            flashcard_question=flashcard_question,
            section=section,
            page=page,
            citation=citation,
            item_id=item_id,
            item_status=item_status,
        )
        try:
            document = select_document(
                repository,
                document_id=document_id or runtime.course_context.target_document_id,
                title=title or runtime.course_context.target_title,
                field=field or runtime.course_context.field,
                document_type=None,
                retriever=retriever,
            )
            state = reading_store.update_progress(
                document,
                status=status,
                current_section=current_section,
                progress_percent=progress_percent,
                review_summary=review_summary,
            )
            if note:
                state = reading_store.add_note(document, note, section=section, page=page, citation=citation)
            if question:
                state = reading_store.add_question(document, question, section=section, page=page, citation=citation)
            if verification_item:
                state = reading_store.add_verification_item(
                    document,
                    verification_item,
                    section=section,
                    page=page,
                    citation=citation,
                )
            if flashcard_question or flashcard_answer:
                state = reading_store.add_flashcard(
                    document,
                    question=flashcard_question or "",
                    answer=flashcard_answer or "",
                    section=section,
                    page=page,
                    citation=citation,
                )
            if item_id and item_status:
                state = reading_store.mark_item(document, item_id=item_id, status=item_status)

            data = reading_state_summary(state)
            return tool_success(
                tool_name,
                "Updated reading state for local paper.",
                data=data,
                metadata={
                    "document_id": document.id,
                    "title": document.title,
                    "status": state.status,
                    "progress_percent": state.progress_percent,
                    "note_count": len(state.notes),
                    "open_question_count": state.open_question_count,
                    "open_verification_count": state.open_verification_count,
                    "flashcard_count": len(state.flashcards),
                },
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Reading state update failed.", exc)

    @tool
    def discover_research_papers(
        direction: str,
        paper_ids: list[str] | None = None,
        code_ids: list[str] | None = None,
        limit: int = 6,
        task_id: str | None = None,
    ) -> str:
        """Discover related arXiv papers for a research direction, using selected local papers and code as context."""
        tool_name = DISCOVER_RESEARCH_PAPERS
        _emit_tool_started(
            tool_name,
            direction=direction,
            paper_ids=paper_ids,
            code_ids=code_ids,
            limit=limit,
            task_id=task_id,
        )
        try:
            result = ResearchAssistant(
                get_model(),
                repository=repository,
                external_search=external_search,
                task_store=research_task_store,
            ).discover(
                direction=direction,
                paper_ids=paper_ids or (
                    [runtime.course_context.target_document_id]
                    if runtime.course_context.target_document_id
                    else []
                ),
                code_ids=code_ids or [],
                limit=max(1, min(limit, 12)),
                task_id=task_id,
            )
            return tool_success(
                tool_name,
                f"Discovered {len(result['candidates'])} related paper candidate(s).",
                data=result,
                metadata={
                    "task_id": result["task"]["id"],
                    "candidate_count": len(result["candidates"]),
                    "queries": result["queries"],
                },
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Research-paper discovery failed.", exc)

    @tool
    def analyze_research_materials(
        task_id: str | None = None,
        direction: str = "",
        paper_ids: list[str] | None = None,
        code_ids: list[str] | None = None,
        related_papers: list[dict[str, Any]] | None = None,
    ) -> str:
        """Compare selected papers and code, then identify innovations, relevance, limitations, correspondence, and feasible next work."""
        tool_name = ANALYZE_RESEARCH_MATERIALS
        _emit_tool_started(
            tool_name,
            task_id=task_id,
            direction=direction,
            paper_ids=paper_ids,
            code_ids=code_ids,
            related_paper_count=len(related_papers or []),
        )
        try:
            assistant = ResearchAssistant(
                get_model(),
                repository=repository,
                task_store=research_task_store,
            )
            effective_paper_ids = paper_ids or (
                [runtime.course_context.target_document_id]
                if runtime.course_context.target_document_id
                else []
            )
            if not task_id:
                task = assistant.task_store.create(
                    name=direction,
                    direction=direction,
                    paper_ids=effective_paper_ids,
                    code_ids=code_ids or [],
                )
                task_id = task["id"]
            result = assistant.analyze(
                task_id=task_id,
                direction=direction,
                paper_ids=effective_paper_ids,
                code_ids=code_ids,
                related_papers=related_papers,
            )
            return tool_success(
                tool_name,
                "Completed research synthesis across the selected papers and code.",
                data=result,
                metadata={
                    "task_id": result["task"]["id"],
                    "paper_count": len(result["task"].get("paper_ids", [])),
                    "code_count": len(result["task"].get("code_ids", [])),
                },
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Research-material analysis failed.", exc)

    @tool
    def check_paper_code_correspondence(
        direction: str = "",
        paper_ids: list[str] | None = None,
        code_ids: list[str] | None = None,
        task_id: str | None = None,
    ) -> str:
        """Verify paper algorithms, formulas, data handling, parameters, metrics, and experiments against concrete local code evidence."""
        tool_name = CHECK_PAPER_CODE_CORRESPONDENCE
        _emit_tool_started(
            tool_name,
            direction=direction,
            paper_ids=paper_ids,
            code_ids=code_ids,
            task_id=task_id,
        )
        try:
            assistant = ResearchAssistant(
                get_model(),
                repository=repository,
                task_store=research_task_store,
            )
            effective_paper_ids = paper_ids or (
                [runtime.course_context.target_document_id]
                if runtime.course_context.target_document_id
                else []
            )
            if not task_id:
                task = assistant.task_store.create(
                    name=direction or "Paper-code correspondence",
                    direction=direction,
                    paper_ids=effective_paper_ids,
                    code_ids=code_ids or [],
                )
                task_id = task["id"]
            result = assistant.check_correspondence(
                task_id=task_id,
                direction=direction,
                paper_ids=effective_paper_ids,
                code_ids=code_ids,
            )
            return tool_success(
                tool_name,
                "Completed the evidence-grounded paper-to-code correspondence check.",
                data=result,
                metadata={
                    "task_id": result["task"]["id"],
                    "coverage_percent": result["correspondence"]["coverage_percent"],
                    "status_counts": result["correspondence"]["status_counts"],
                },
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "Paper-to-code correspondence check failed.", exc)

    @tool
    def import_arxiv_paper(
        url: str,
        title: str,
        field: str = "arXiv",
        categories: list[str] | None = None,
    ) -> str:
        """Download and import an explicitly requested arXiv paper into the local library. Do not call without clear user intent."""
        tool_name = IMPORT_ARXIV_PAPER
        _emit_tool_started(tool_name, url=url, title=title, field=field, categories=categories)
        try:
            document, imported = import_arxiv_document(
                url,
                title=title,
                field=field,
                tags=tuple(categories or ()),
                repository=repository,
            )
            return tool_success(
                tool_name,
                "Imported the arXiv paper." if imported else "The arXiv paper already exists locally.",
                data=document.to_dict(),
                metadata={"document_id": document.id, "imported": imported},
            )
        except FinalsAgentError as exc:
            return expected_tool_error(tool_name, exc)
        except Exception as exc:
            return tool_error(tool_name, "arXiv paper import failed.", exc)

    return [
        list_papers,
        search_local_papers,
        intelligent_search_local_evidence,
        analyze_paper_structure,
        search_related_papers,
        compare_paper_innovations,
        read_paper_workflow,
        explain_paper_target,
        get_reading_state,
        update_reading_state,
        discover_research_papers,
        analyze_research_materials,
        check_paper_code_correspondence,
        import_arxiv_paper,
    ]


def _emit_tool_started(tool_name: str, **inputs) -> None:
    sanitized = {key: value for key, value in inputs.items() if value is not None}
    emit_event("tool_started", tool_name=tool_name, input=sanitized)
