from __future__ import annotations

from abc import ABC, abstractmethod

from finals_agent.core.schemas import ArtifactInterpretation, PaperArtifact, StudyDocument
from finals_agent.data.repository import StudyRepository
from finals_agent.data.selection import select_document as select_study_document


class ArtifactInterpreter(ABC):
    method: str

    @abstractmethod
    def interpret(self, artifact: PaperArtifact) -> ArtifactInterpretation:
        raise NotImplementedError


class BaselineArtifactInterpreter(ArtifactInterpreter):
    method = "caption_nearby_text_baseline"

    def interpret(self, artifact: PaperArtifact) -> ArtifactInterpretation:
        if artifact.kind in {"figure", "table"}:
            from finals_agent.data.vision import vision_required_interpretation

            return vision_required_interpretation(artifact)
        extracted_text = artifact.caption or artifact.text
        nearby_text = artifact.nearby_text or ""
        structured_data = {
            "caption": artifact.caption,
            "nearby_text": nearby_text,
            "page": artifact.page,
            "chunk_id": artifact.chunk_id,
        }
        return ArtifactInterpretation(
            document_id=artifact.document_id,
            artifact_id=artifact.artifact_id,
            kind=artifact.kind,
            extracted_text=extracted_text,
            structured_data=structured_data,
            interpretation=_baseline_interpretation(artifact, extracted_text, nearby_text),
            confidence=_baseline_confidence(artifact),
            method=self.method,
            limitations=_baseline_limitations(artifact),
            metadata={
                "source": "caption_and_nearby_text",
                "requires_ocr_or_vision": artifact.kind in {"figure", "table"},
            },
        )


def interpret_document_artifacts(
    document: StudyDocument,
    repository: StudyRepository | None = None,
    interpreter: ArtifactInterpreter | None = None,
    force: bool = False,
) -> tuple[ArtifactInterpretation, ...]:
    repository = repository or StudyRepository()
    interpreter = interpreter or BaselineArtifactInterpreter()
    artifacts = repository.read_artifacts(document)
    if not artifacts:
        return ()

    existing = {
        item.artifact_id: item
        for item in repository.read_artifact_interpretations(document)
    }
    interpretations = []
    for artifact in artifacts:
        if artifact.artifact_id in existing and not force:
            interpretations.append(existing[artifact.artifact_id])
        else:
            interpretations.append(interpreter.interpret(artifact))
    repository.write_artifact_interpretations(document, interpretations)
    return tuple(interpretations)


def interpret_repository_artifacts(
    repository: StudyRepository | None = None,
    interpreter: ArtifactInterpreter | None = None,
    field: str | None = None,
    force: bool = False,
) -> list[ArtifactInterpretation]:
    repository = repository or StudyRepository()
    interpretations = []
    for document in repository.list_documents(field=field):
        interpretations.extend(
            interpret_document_artifacts(
                document,
                repository=repository,
                interpreter=interpreter,
                force=force,
            )
        )
    return interpretations


def select_document(
    repository: StudyRepository,
    document_id: str | None = None,
    title: str | None = None,
    field: str | None = None,
) -> StudyDocument:
    return select_study_document(
        repository,
        document_id=document_id,
        title=title,
        field=field,
        document_type=None,
    )


def _baseline_interpretation(artifact: PaperArtifact, extracted_text: str, nearby_text: str) -> str:
    if artifact.kind == "figure":
        return (
            f"This figure artifact is identified from its caption: {extracted_text}. "
            "Use nearby text to infer its role, but inspect the image body with OCR or a vision model before claiming visual details. "
            f"Nearby context: {nearby_text[:300]}"
        )
    if artifact.kind == "table":
        return (
            f"This table artifact is identified from its caption: {extracted_text}. "
            "The baseline interpreter cannot read table cells; use a table parser before reporting numeric values. "
            f"Nearby context: {nearby_text[:300]}"
        )
    if artifact.kind == "formula":
        return (
            f"This formula candidate was extracted from text: {extracted_text}. "
            "Explain symbols using the surrounding paragraph and verify formatting against the original PDF when precision matters."
        )
    return f"Artifact extracted from text: {extracted_text}. Nearby context: {nearby_text[:300]}"


def _baseline_confidence(artifact: PaperArtifact) -> float:
    if artifact.caption and artifact.nearby_text:
        return 0.65
    if artifact.text:
        return 0.45
    return 0.2


def _baseline_limitations(artifact: PaperArtifact) -> tuple[str, ...]:
    if artifact.kind == "figure":
        return (
            "Does not inspect pixels or visual layout.",
            "Cannot read axes, legends, curves, or diagram internals without a vision/OCR backend.",
        )
    if artifact.kind == "table":
        return (
            "Does not extract table cells.",
            "Cannot report numeric results without a table parser.",
        )
    if artifact.kind == "formula":
        return (
            "Formula detection is heuristic.",
            "LaTeX or PDF extraction may omit symbols or alter formatting.",
        )
    return ("Baseline interpretation only uses extracted text.",)
