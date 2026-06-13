from pathlib import Path
import json
from types import SimpleNamespace

from finals_agent.agent.tools import build_tools
from finals_agent.core.events import bind_event_sink
from finals_agent.core.runtime import AgentRuntime
from finals_agent.core.schemas import DocumentType, ToolResult, ToolStatus
from finals_agent.data.external_search import ExternalPaper
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository
from finals_agent.persistence.reading_state import ReadingStateStore
from finals_agent.persistence.research_tasks import ResearchTaskStore
from finals_agent.persistence.storage import JsonFileStorage


class FakeExternalSearch:
    def search(self, query: str, limit: int = 5):
        return (
            ExternalPaper(
                title=f"Related paper for {query}",
                authors=("A. Researcher",),
                summary="A related method with a different evaluation setup.",
                url="https://arxiv.org/abs/0000.00000",
                published="2024-01-01",
                categories=("cs.CL",),
            ),
        )


def _tool_map(repository: StudyRepository, runtime: AgentRuntime | None = None, model=None):
    return {
        tool.name: tool
        for tool in build_tools(
            repository=repository,
            runtime=runtime,
            external_search=FakeExternalSearch(),
            reading_store=ReadingStateStore(JsonFileStorage(repository.index_path.parent / "reading_state.json")),
            research_task_store=ResearchTaskStore(
                JsonFileStorage(repository.index_path.parent / "research_tasks.json")
            ),
            model=model,
        )
    }


def test_list_papers_returns_empty_tool_result(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    tools = _tool_map(repository)

    result = ToolResult.from_json(tools["list_papers"].invoke({"field": "nlp"}))

    assert result.tool_name == "list_papers"
    assert result.status == ToolStatus.EMPTY
    assert result.data is None
    assert result.metadata == {"field": "nlp", "count": 0}


def test_tool_invocation_emits_stream_events(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    tools = _tool_map(repository)
    events = []

    with bind_event_sink(events.append):
        ToolResult.from_json(tools["list_papers"].invoke({"field": "nlp"}))

    assert [event["event"] for event in events] == ["tool_started", "tool_finished"]
    assert events[0]["tool_name"] == "list_papers"
    assert events[1]["status"] == "empty"


def test_search_local_papers_returns_ranked_data(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("retrieval augmented generation reranking", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    repository.ingest(source, DocumentType.PAPER, "nlp")
    tools = _tool_map(repository)

    result = ToolResult.from_json(
        tools["search_local_papers"].invoke(
            {
                "query": "reranking",
                "field": "nlp",
                "document_type": "paper",
            }
        )
    )

    assert result.tool_name == "search_local_papers"
    assert result.status == ToolStatus.SUCCESS
    assert result.metadata["count"] == 1
    assert result.metadata["retriever"] == "HybridRetriever"
    assert result.data[0]["title"] == "paper"
    assert result.data[0]["score"] > 0
    assert result.data[0]["citation"]


def test_search_local_papers_uses_runtime_target_title(tmp_path: Path):
    target = tmp_path / "target.md"
    target.write_text("retrieval alpha", encoding="utf-8")
    other = tmp_path / "other.md"
    other.write_text("retrieval beta", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(target, DocumentType.PAPER, "nlp", title="Target"),
        repository=repository,
    )
    ingest_material(
        build_ingest_request(other, DocumentType.PAPER, "nlp", title="Other"),
        repository=repository,
    )
    runtime = AgentRuntime.default().with_field("nlp").with_target(title="Target")
    tools = _tool_map(repository, runtime=runtime)

    result = ToolResult.from_json(tools["search_local_papers"].invoke({"query": "retrieval"}))

    assert result.status == ToolStatus.SUCCESS
    assert {item["title"] for item in result.data} == {"Target"}


def test_intelligent_search_tool_uses_query_rewrite_and_reranking(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text(
        "The method retrieves evidence before generation. "
        "Experiments report improved factual accuracy.",
        encoding="utf-8",
    )
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    document = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, "nlp", title="Target"),
        repository=repository,
    ).document

    class SearchModel:
        def invoke(self, messages):
            system = messages[0][1] if isinstance(messages[0], tuple) else messages[0]["content"]
            if "3 到 5 条互补" in system:
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "intent": "查找检索增强证据",
                            "queries": ["retrieves evidence", "factual accuracy"],
                        },
                        ensure_ascii=False,
                    )
                )
            return SimpleNamespace(
                content=json.dumps(
                    {"ranked": [{"id": "E1", "reason": "直接描述方法"}]},
                    ensure_ascii=False,
                )
            )

    tools = _tool_map(repository, model=SearchModel())
    result = ToolResult.from_json(
        tools["intelligent_search_local_evidence"].invoke(
            {"query": "方法如何利用证据？", "document_id": document.id}
        )
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.metadata["rewritten_query_count"] >= 2
    assert result.data["results"][0]["relevance_reason"]
    assert result.data["results"][0]["citation"]


def test_research_discovery_tool_exposes_research_assistant(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    class SummaryModel:
        def invoke(self, messages):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "summaries": [
                            {
                                "id": "ignored",
                                "brief_summary": "A concise summary.",
                            }
                        ]
                    }
                )
            )

    tools = _tool_map(repository, model=SummaryModel())
    result = ToolResult.from_json(
        tools["discover_research_papers"].invoke(
            {"direction": "retrieval augmented generation", "limit": 2}
        )
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.metadata["candidate_count"] == 1
    assert result.metadata["task_id"]


def test_import_arxiv_tool_uses_shared_library_import(monkeypatch, tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("Imported paper.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    document = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, "arXiv", title="Imported"),
        repository=repository,
    ).document
    monkeypatch.setattr(
        "finals_agent.agent.tools.import_arxiv_document",
        lambda *args, **kwargs: (document, True),
    )
    tools = _tool_map(repository)

    result = ToolResult.from_json(
        tools["import_arxiv_paper"].invoke(
            {
                "url": "https://arxiv.org/abs/2605.01106v1",
                "title": "Imported",
            }
        )
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.metadata["imported"] is True
    assert result.data["id"] == document.id


def test_paper_code_correspondence_tool_returns_verified_locations(tmp_path: Path):
    paper_source = tmp_path / "paper.md"
    paper_source.write_text(
        "Abstract\n\nThe algorithm ranks passages before generation.",
        encoding="utf-8",
    )
    code_source = tmp_path / "ranker.py"
    code_source.write_text(
        "def rank(passages):\n    return sorted(passages)\n",
        encoding="utf-8",
    )
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    paper = ingest_material(
        build_ingest_request(paper_source, DocumentType.PAPER, "nlp", title="Paper"),
        repository=repository,
    ).document
    code = ingest_material(
        build_ingest_request(
            code_source,
            DocumentType.CODE,
            "code",
            title="ranker.py",
            source="src/ranker.py",
        ),
        repository=repository,
    ).document

    class CorrespondenceModel:
        def invoke(self, messages):
            payload = json.loads(messages[1]["content"])
            if "requirements" in payload.get("required_output", {}):
                citation = payload["papers"][0]["evidence"][0]["citation"]
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "requirements": [
                                {
                                    "category": "algorithm",
                                    "paper_claim": "Rank passages.",
                                    "paper_citation": citation,
                                    "expected_behavior": "Sort passages.",
                                    "code_search_terms": ["rank", "passages"],
                                }
                            ]
                        }
                    )
                )
            if "verdicts" in payload.get("required_output", {}):
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "verified_summary": "Ranking is implemented.",
                            "verdicts": [
                                {
                                    "check_index": 0,
                                    "paper_claim_supported": True,
                                    "code_status_supported": True,
                                    "rationale": "The cited claim and rank function match.",
                                }
                            ],
                        }
                    )
                )
            citation = payload["papers"][0]["evidence"][0]["citation"]
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "summary": "Ranking is implemented.",
                        "checks": [
                            {
                                "category": "algorithm",
                                "paper_claim": "Rank passages.",
                                "paper_citation": citation,
                                "expected_behavior": "Sort passages.",
                                "status": "implemented",
                                "code_evidence_ids": ["C1"],
                                "implementation_evidence": "rank sorts passages.",
                                "discrepancy": "",
                                "verification_action": "Test ordering.",
                            }
                        ],
                        "missing_components": [],
                        "reproduction_risks": [],
                        "recommended_next_checks": [],
                    }
                )
            )

    tools = _tool_map(repository, model=CorrespondenceModel())
    result = ToolResult.from_json(
        tools["check_paper_code_correspondence"].invoke(
            {"paper_ids": [paper.id], "code_ids": [code.id]}
        )
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.metadata["coverage_percent"] == 100
    location = result.data["correspondence"]["checks"][0]["code_locations"][0]
    assert location["path"] == "src/ranker.py"
    assert location["symbols"][0]["name"] == "rank"


def test_search_local_papers_reports_invalid_document_type(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    tools = _tool_map(repository)

    result = ToolResult.from_json(
        tools["search_local_papers"].invoke(
            {
                "query": "retrieval",
                "document_type": "slides",
            }
        )
    )

    assert result.tool_name == "search_local_papers"
    assert result.status == ToolStatus.ERROR
    assert "Invalid document_type" in result.error
    assert result.metadata["error_type"] == "ToolInputError"


def test_analyze_paper_structure_detects_sections_captions_and_formulas(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text(
        "\n\n".join(
            [
                "Abstract",
                "We study retrieval.",
                "1 Introduction",
                "Figure 1: System overview.",
                "Table 1: Main results.",
                "score = softmax(q k)",
            ]
        ),
        encoding="utf-8",
    )
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, field="nlp"),
        repository=repository,
    )
    document = ingest_result.document
    tools = _tool_map(repository)

    result = ToolResult.from_json(
        tools["analyze_paper_structure"].invoke({"document_id": document.id})
    )

    assert result.tool_name == "analyze_paper_structure"
    assert result.status == ToolStatus.SUCCESS
    assert result.metadata["section_count"] >= 2
    assert result.metadata["figure_caption_count"] == 1
    assert result.metadata["table_caption_count"] == 1
    assert result.metadata["formula_candidate_count"] == 1
    assert result.data["artifact_interpretation_count"] == 3


def test_search_related_papers_uses_external_search(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    tools = _tool_map(repository)

    result = ToolResult.from_json(tools["search_related_papers"].invoke({"topic": "RAG", "limit": 3}))

    assert result.status == ToolStatus.SUCCESS
    assert result.metadata["source"] == "arxiv"
    assert result.data[0]["title"] == "Related paper for RAG"


def test_compare_paper_innovations_collects_local_and_related_evidence(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("RAG uses retrieval to improve generation.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    repository.ingest(source, DocumentType.PAPER, "nlp")
    tools = _tool_map(repository)

    result = ToolResult.from_json(
        tools["compare_paper_innovations"].invoke({"topic": "RAG", "local_query": "retrieval"})
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.metadata["local_count"] == 1
    assert result.metadata["related_count"] == 1
    assert result.data["local_evidence"][0]["citation"]
    assert result.data["related_papers"][0]["citation"]
    assert result.data["comparison_instructions"]


def test_compare_paper_innovations_accepts_target_title(tmp_path: Path):
    target = tmp_path / "target.md"
    target.write_text("Target paper uses retrieval method Alpha.", encoding="utf-8")
    other = tmp_path / "other.md"
    other.write_text("Other paper uses retrieval method Beta.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(target, DocumentType.PAPER, "nlp", title="Target"),
        repository=repository,
    )
    ingest_material(
        build_ingest_request(other, DocumentType.PAPER, "nlp", title="Other"),
        repository=repository,
    )
    tools = _tool_map(repository)

    result = ToolResult.from_json(
        tools["compare_paper_innovations"].invoke(
            {"topic": "retrieval", "title": "Target", "field": "nlp", "limit": 0}
        )
    )

    assert result.status == ToolStatus.SUCCESS
    assert {item["title"] for item in result.data["local_evidence"]} == {"Target"}


def test_tool_errors_include_clarification_candidates(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    for title in ("RAG Survey", "RAG System"):
        source = tmp_path / f"{title}.md"
        source.write_text(f"retrieval method {title}", encoding="utf-8")
        ingest_material(
            build_ingest_request(source, DocumentType.PAPER, "nlp", title=title),
            repository=repository,
        )
    tools = _tool_map(repository)

    result = ToolResult.from_json(
        tools["read_paper_workflow"].invoke({"title": "RAG", "field": "nlp"})
    )

    assert result.status == ToolStatus.ERROR
    assert result.metadata["clarification_needed"] is True
    assert len(result.metadata["candidates"]) == 2
    assert "document_id" in result.metadata["clarification_question"]


def test_read_paper_workflow_tool_returns_reading_plan(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("Abstract\n\nRetrieval method contribution experiment limitation.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    repository.ingest(source, DocumentType.PAPER, "nlp")
    tools = _tool_map(repository)

    result = ToolResult.from_json(
        tools["read_paper_workflow"].invoke({"title": "paper", "field": "nlp"})
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.metadata["title"] == "paper"
    assert result.metadata["section_pass_count"] >= 1
    assert result.metadata["section_coverage_ratio"] is not None
    assert result.data["section_passes"]
    assert result.data["whole_paper_synthesis_plan"]
    assert result.data["reading_order"]
    assert result.data["citation_instructions"]
    assert "output_template" in result.data


def test_explain_paper_target_tool_returns_focused_plan(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("Figure 1: Retrieval and generation pipeline.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    repository.ingest(source, DocumentType.PAPER, "nlp")
    tools = _tool_map(repository)

    result = ToolResult.from_json(
        tools["explain_paper_target"].invoke({"target": "Figure 1", "title": "paper", "field": "nlp"})
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.metadata["target"] == "Figure 1"
    assert result.data["citation_instructions"]
    assert result.data["explanation_plan"]


def test_reading_state_tools_update_and_return_summary(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("Abstract\n\nMethod and experiments.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(source, DocumentType.PAPER, "nlp", title="Target"),
        repository=repository,
    )
    tools = _tool_map(repository)

    updated = ToolResult.from_json(
        tools["update_reading_state"].invoke(
            {
                "title": "Target",
                "field": "nlp",
                "status": "reading",
                "current_section": "2 Method",
                "progress_percent": 40,
                "note": "Method depends on retrieval evidence.",
                "question": "How is retrieval failure handled?",
                "verification_item": "Verify Table 1 numbers.",
                "flashcard_question": "What is the core method?",
                "flashcard_answer": "Retrieve then generate.",
            }
        )
    )

    loaded = ToolResult.from_json(
        tools["get_reading_state"].invoke({"title": "Target", "field": "nlp"})
    )

    assert updated.status == ToolStatus.SUCCESS
    assert updated.metadata["progress_percent"] == 40
    assert updated.metadata["note_count"] == 1
    assert updated.metadata["open_question_count"] == 1
    assert updated.metadata["open_verification_count"] == 1
    assert updated.metadata["flashcard_count"] == 1
    assert loaded.status == ToolStatus.SUCCESS
    assert loaded.data["current_section"] == "2 Method"
