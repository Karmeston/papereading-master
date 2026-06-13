from pathlib import Path

from finals_agent.agent.planning import RuleBasedTaskPlanner
from finals_agent.agent.preretrieval import run_preretrieval
from finals_agent.core.schemas import AgentRequest, CourseContext, DocumentType, SearchResponse
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository
from finals_agent.data.retrievers import KeywordRetriever


def test_preretrieval_returns_context_message_when_required(tmp_path: Path):
    source = tmp_path / "limits.md"
    source.write_text("limit derivative lhopital rule", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(source, DocumentType.NOTE, "calculus", chapter="limits"),
        repository=repository,
    )
    request = AgentRequest(
        question="帮我查找 lhopital 资料",
        course_context=CourseContext(course="calculus", chapter="limits"),
    )
    plan = RuleBasedTaskPlanner().plan(request, request.course_context)

    result = run_preretrieval(
        task_plan=plan,
        query=request.question,
        retriever=KeywordRetriever(repository),
        course="calculus",
        chapter="limits",
    )

    assert result.enabled is True
    assert result.response.count == 1
    assert result.context_message["role"] == "system"
    assert "预检索到以下本地论文证据" in result.context_message["content"]
    assert "citation" in result.context_message["content"]
    assert "chunk=" in result.context_message["content"]
    assert "lhopital" in result.context_message["content"]
    assert result.to_metadata()["citations"]


def test_preretrieval_is_disabled_when_plan_does_not_require_retrieval(tmp_path: Path):
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    request = AgentRequest(question="hello")
    plan = RuleBasedTaskPlanner().plan(request)

    result = run_preretrieval(
        task_plan=plan,
        query=request.question,
        retriever=KeywordRetriever(repository),
    )

    assert result.enabled is False
    assert result.response is None
    assert result.context_message is None


def test_preretrieval_can_be_scoped_to_target_document(tmp_path: Path):
    target = tmp_path / "target.md"
    target.write_text("retrieval alpha evidence", encoding="utf-8")
    other = tmp_path / "other.md"
    other.write_text("retrieval beta evidence", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    target_doc = ingest_material(
        build_ingest_request(target, DocumentType.PAPER, "nlp", title="Target"),
        repository=repository,
    ).document
    ingest_material(
        build_ingest_request(other, DocumentType.PAPER, "nlp", title="Other"),
        repository=repository,
    )
    request = AgentRequest(question="search retrieval", course_context=CourseContext(course="nlp"))
    plan = RuleBasedTaskPlanner().plan(request, request.course_context)

    result = run_preretrieval(
        task_plan=plan,
        query=request.question,
        retriever=KeywordRetriever(repository),
        course="nlp",
        document_id=target_doc.id,
    )

    assert result.response.count == 1
    assert result.response.results[0].document_id == target_doc.id
    assert "Target" in result.context_message["content"]
    assert "Other" not in result.context_message["content"]


def test_preretrieval_query_override_replaces_planner_topic():
    class RecordingRetriever:
        request = None

        def search(self, request):
            self.request = request
            return SearchResponse(request=request, results=(), metadata={"count": 0})

    retriever = RecordingRetriever()
    request = AgentRequest(question="summarize this paper")
    plan = RuleBasedTaskPlanner().plan(request)

    run_preretrieval(
        task_plan=plan,
        query=request.question,
        query_override="method experiment evidence",
        retriever=retriever,
    )

    assert retriever.request.query == "method experiment evidence"
