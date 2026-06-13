from pathlib import Path

from finals_agent.core.schemas import DocumentType, PaperArtifact
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository
from finals_agent.data.vision import (
    OpenAICompatibleVisionClient,
    VISION_INTERPRETATION_VERSION,
    VisionArtifactInterpreter,
    _caption_search_candidates,
    _vision_prompt,
    vision_required_interpretation,
)


class FakeVisionClient:
    def analyze(self, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        assert image_bytes == b"image"
        assert mime_type == "image/png"
        assert "Figure 1" in prompt
        assert "what this artifact demonstrates for the paper" in prompt
        assert "Do not spend a paragraph listing every axis" in prompt
        return "The figure shows a retrieval pipeline with two stages."


def fake_image_loader(document, artifact, dpi):
    assert dpi == 144
    return b"image", "image/png"


def test_vision_required_interpretation_marks_visual_artifacts_as_pending():
    artifact = _artifact_from_markdown("Figure 1: Pipeline overview.")

    interpretation = vision_required_interpretation(artifact)

    assert interpretation.method == "vision_api_required"
    assert interpretation.metadata["requires_vision_api"] is True
    assert interpretation.confidence == 0


def test_vision_artifact_interpreter_uses_client_and_image_loader(tmp_path: Path):
    repository, document = _repository_with_artifact(tmp_path, "Figure 1: Pipeline overview.")
    artifact = repository.read_artifacts(document)[0]
    interpreter = VisionArtifactInterpreter(
        document=document,
        client=FakeVisionClient(),
        image_loader=fake_image_loader,
        render_dpi=144,
    )

    interpretation = interpreter.interpret(artifact)

    assert interpretation.method == "vision_api"
    assert "retrieval pipeline" in interpretation.interpretation
    assert interpretation.structured_data["vision_analysis"] == interpretation.interpretation
    assert interpretation.confidence > 0
    assert interpretation.metadata["interpretation_version"] == VISION_INTERPRETATION_VERSION


def test_vision_prompt_prioritizes_paper_meaning_over_visual_inventory():
    prompt = _vision_prompt(_artifact_from_markdown("Figure 1: Pipeline overview."))

    assert "**它说明了什么**" in prompt
    assert "**对原文的意义**" in prompt
    assert "only the 1-3 visible trends" in prompt
    assert "Do not repeat the caption" in prompt


def test_openai_compatible_vision_client_reads_streaming_deltas(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __iter__(self):
            return iter(
                [
                    b'data: {"choices":[{"delta":{"content":"first"}}]}\n',
                    b'data: {"choices":[{"delta":{"content":" second"}}]}\n',
                    b"data: [DONE]\n",
                ]
            )

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: FakeResponse())
    client = OpenAICompatibleVisionClient(
        model="vision-model",
        api_key="test-key",
        base_url="https://vision.example/v1",
    )

    assert list(client.analyze_stream(b"image", "image/png", "prompt")) == ["first", " second"]


def test_caption_search_candidates_include_label_and_prefix():
    candidates = _caption_search_candidates(
        "Figure 2: A very long caption that describes the pipeline and includes enough detail "
        "to require a shorter search prefix for PDF text matching."
    )

    assert candidates[0].startswith("Figure 2:")
    assert "Figure 2" in candidates
    assert any(len(item) == 80 for item in candidates)


def _artifact_from_markdown(text):
    return PaperArtifact(
        document_id="doc-1",
        artifact_id="artifact-1",
        kind="figure",
        text=text,
        page=1,
        caption=text,
        nearby_text="Nearby context.",
        chunk_id="chunk-1",
    )


def _repository_with_artifact(tmp_path: Path, text: str):
    source = tmp_path / "paper.md"
    source.write_text(text, encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, field="nlp"),
        repository=repository,
    )
    return repository, result.document
