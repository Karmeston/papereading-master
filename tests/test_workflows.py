from pathlib import Path

import pytest

from finals_agent.core.exceptions import ToolInputError
from finals_agent.core.schemas import DocumentType
from finals_agent.data.external_search import ExternalPaper
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository
from finals_agent.data.workflows import PaperReadingWorkflow
from finals_agent.data.vision import VisionArtifactInterpreter
from finals_agent.persistence.reading_state import ReadingStateStore
from finals_agent.persistence.storage import JsonFileStorage


class FakeExternalSearch:
    def search(self, query: str, limit: int = 5):
        return tuple(
            ExternalPaper(
                title=f"Related {index} for {query}",
                authors=("A. Researcher",),
                summary="This paper studies retrieval methods with a different experimental setup.",
                url=f"https://arxiv.org/abs/0000.0000{index}",
                published="2024-01-01",
                categories=("cs.CL",),
            )
            for index in range(1, min(limit, 2) + 1)
        )


class FakeVisionClient:
    def analyze(self, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        return "Vision analysis: the figure shows retrieval followed by generation."


def fake_vision_factory(document):
    return VisionArtifactInterpreter(
        document=document,
        client=FakeVisionClient(),
        image_loader=lambda document, artifact, dpi: (b"image", "image/png"),
    )


def _repository_with_paper(tmp_path: Path) -> StudyRepository:
    source = tmp_path / "rag_paper.md"
    source.write_text(
        "\n\n".join(
            [
                "Abstract",
                "Retrieval augmented generation improves factual grounding.",
                "1 Introduction",
                "The problem is hallucination in knowledge-intensive tasks.",
                "2 Method",
                "Our method retrieves documents and conditions generation on evidence.",
                "Figure 1: Retrieval and generation pipeline.",
                "3 Experiments",
                "Experiments compare retrieval baselines on benchmark datasets.",
                "4 Discussion",
                "A limitation is additional latency and retrieval failure.",
            ]
        ),
        encoding="utf-8",
    )
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(
            source,
            DocumentType.PAPER,
            "nlp",
            title="RAG Paper",
            chapter="retrieval augmented generation",
        ),
        repository=repository,
    )
    return repository


def test_read_workflow_builds_evidence_backed_reading_plan(tmp_path: Path):
    repository = _repository_with_paper(tmp_path)
    workflow = PaperReadingWorkflow(repository=repository, external_search=FakeExternalSearch())

    result = workflow.read(title="RAG", field="nlp", related_limit=2)
    data = result.to_dict()["data"]

    assert result.workflow == "read_paper"
    assert data["paper"]["title"] == "RAG Paper"
    assert data["reading_state"]["status"] == "not_started"
    assert data["structure"]["section_headings"]
    assert data["structure"]["artifact_count"] >= 1
    assert data["structure"]["artifacts"][0]["nearby_text"]
    assert data["structure"]["artifact_interpretation_count"] >= 1
    assert data["structure"]["artifact_interpretations"][0]["interpretation"]
    assert data["reading_order"]
    assert data["section_passes"]
    assert data["whole_paper_synthesis_plan"]["required_outputs"]
    assert data["coverage"]["covered_count"] >= 4
    assert {"abstract", "introduction", "method", "experiments"} <= {
        item["role"] for item in data["section_passes"] if item["status"] == "covered"
    }
    assert data["evidence"]
    assert {item["aspect"] for item in data["evidence"]} & {"problem", "method", "evidence", "limitation"}
    assert data["evidence"][0]["citation"]
    assert data["citation_instructions"]
    assert len(data["related_papers"]) == 2
    assert data["related_papers"][0]["citation"].startswith("[R1:")


def test_read_workflow_keeps_evidence_scoped_to_selected_paper(tmp_path: Path):
    target = tmp_path / "target.md"
    target.write_text("Abstract\n\nTarget paper uses retrieval method Alpha.", encoding="utf-8")
    other = tmp_path / "other.md"
    other.write_text(
        "Abstract\n\nOther paper has retrieval experiments, contribution, baseline, and limitation Beta.",
        encoding="utf-8",
    )
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(target, DocumentType.PAPER, "nlp", title="Target"),
        repository=repository,
    )
    ingest_material(
        build_ingest_request(other, DocumentType.PAPER, "nlp", title="Other"),
        repository=repository,
    )
    workflow = PaperReadingWorkflow(repository=repository, external_search=FakeExternalSearch())

    data = workflow.read(title="Target", field="nlp").to_dict()["data"]

    assert data["evidence"]
    assert {item["title"] for item in data["evidence"]} == {"Target"}


def test_read_workflow_includes_saved_reading_state(tmp_path: Path):
    repository = _repository_with_paper(tmp_path)
    document = repository.list_documents(field="nlp")[0]
    reading_store = ReadingStateStore(JsonFileStorage(tmp_path / "reading_state.json"))
    reading_store.update_progress(document, status="reading", current_section="2 Method", progress_percent=35)
    reading_store.add_question(document, "Which ablation supports the main claim?")
    workflow = PaperReadingWorkflow(
        repository=repository,
        external_search=FakeExternalSearch(),
        reading_store=reading_store,
    )

    data = workflow.read(title="RAG", field="nlp").to_dict()["data"]

    assert data["reading_state"]["status"] == "reading"
    assert data["reading_state"]["current_section"] == "2 Method"
    assert data["reading_state"]["open_question_count"] == 1


def test_explain_workflow_returns_target_evidence_and_plan(tmp_path: Path):
    repository = _repository_with_paper(tmp_path)
    workflow = PaperReadingWorkflow(repository=repository, external_search=FakeExternalSearch())

    result = workflow.explain(target="Figure 1", title="RAG", field="nlp")
    data = result.to_dict()["data"]

    assert result.workflow == "explain_paper_target"
    assert data["target"] == "Figure 1"
    assert data["matched_structure_candidates"]
    assert data["evidence"]
    assert data["evidence"][0]["citation"]
    assert data["citation_instructions"]
    assert data["explanation_plan"]


def test_explain_workflow_runs_vision_for_visual_artifacts(tmp_path: Path):
    repository = _repository_with_paper(tmp_path)
    workflow = PaperReadingWorkflow(
        repository=repository,
        external_search=FakeExternalSearch(),
        vision_interpreter_factory=fake_vision_factory,
    )

    result = workflow.explain(target="Figure 1", title="RAG", field="nlp")
    data = result.to_dict()["data"]

    assert data["visual_artifact"]["kind"] == "figure"
    assert data["visual_interpretation"]["method"] == "vision_api"
    assert "retrieval" in data["visual_interpretation"]["interpretation"].lower()
    document = repository.list_documents(field="nlp")[0]
    assert repository.read_artifact_interpretations(document)[0].method == "vision_api"


def test_compare_workflow_builds_related_paper_matrix(tmp_path: Path):
    repository = _repository_with_paper(tmp_path)
    workflow = PaperReadingWorkflow(repository=repository, external_search=FakeExternalSearch())

    result = workflow.compare(topic="retrieval augmented generation", title="RAG", field="nlp", related_limit=2)
    data = result.to_dict()["data"]

    assert result.workflow == "compare_paper_innovations"
    assert data["local_evidence"]
    assert data["local_evidence"][0]["citation"]
    assert len(data["related_papers"]) == 2
    assert len(data["comparison_matrix"]) == 2
    assert data["comparison_matrix"][0]["citation"].startswith("[R1:")
    assert data["citation_instructions"]
    assert data["comparison_instructions"]


def test_compare_workflow_keeps_local_evidence_scoped_to_selected_paper(tmp_path: Path):
    target = tmp_path / "target.md"
    target.write_text("Target paper studies retrieval with method Alpha.", encoding="utf-8")
    other = tmp_path / "other.md"
    other.write_text("Other paper studies retrieval with method Beta and stronger experiments.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    ingest_material(
        build_ingest_request(target, DocumentType.PAPER, "nlp", title="Target"),
        repository=repository,
    )
    ingest_material(
        build_ingest_request(other, DocumentType.PAPER, "nlp", title="Other"),
        repository=repository,
    )
    workflow = PaperReadingWorkflow(repository=repository, external_search=FakeExternalSearch())

    data = workflow.compare(topic="retrieval", title="Target", field="nlp", related_limit=0).to_dict()["data"]

    assert data["local_evidence"]
    assert {item["title"] for item in data["local_evidence"]} == {"Target"}


def test_explain_workflow_rejects_empty_target(tmp_path: Path):
    repository = _repository_with_paper(tmp_path)
    workflow = PaperReadingWorkflow(repository=repository, external_search=FakeExternalSearch())

    with pytest.raises(ToolInputError):
        workflow.explain(target=" ", title="RAG", field="nlp")
