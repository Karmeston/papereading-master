from pathlib import Path

from finals_agent.core.schemas import DocumentType
from finals_agent.data.artifact_interpretation import (
    BaselineArtifactInterpreter,
    interpret_document_artifacts,
)
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository


def test_baseline_artifact_interpreter_uses_caption_and_nearby_text(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("Figure 1: Pipeline overview.\nThe figure shows the retrieval flow.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, field="nlp"),
        repository=repository,
    )
    artifact = repository.read_artifacts(result.document)[0]

    interpretation = BaselineArtifactInterpreter().interpret(artifact)

    assert interpretation.artifact_id == artifact.artifact_id
    assert interpretation.kind == "figure"
    assert interpretation.extracted_text == "Figure 1: Pipeline overview."
    assert interpretation.structured_data["nearby_text"]
    assert interpretation.method == "vision_api_required"
    assert interpretation.confidence == 0
    assert interpretation.metadata["requires_vision_api"] is True
    assert interpretation.limitations


def test_interpret_document_artifacts_writes_sidecar(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("Table 1: Main results.\nAccuracy improves over baselines.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, field="nlp"),
        repository=repository,
    )

    interpretations = interpret_document_artifacts(result.document, repository=repository)
    reread = repository.read_artifact_interpretations(result.document)

    assert len(interpretations) == 1
    assert len(reread) == 1
    assert reread[0].method == "vision_api_required"
    assert repository.artifact_interpretation_sidecar_path(result.document.path).exists()
