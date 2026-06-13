from __future__ import annotations

from pathlib import Path

from finals_agent.core.schemas import DocumentType, PaperArtifact, StudyDocument
from finals_agent.data.artifact_locator import ArtifactRegion
from finals_agent.data.artifact_manifest import ArtifactManifestStore


def test_artifact_manifest_round_trip_and_source_invalidation(tmp_path: Path):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-test")
    document = StudyDocument(
        id="doc-1",
        title="Paper",
        document_type=DocumentType.PAPER,
        course="test",
        path=source,
    )
    artifact = PaperArtifact(
        document_id=document.id,
        artifact_id="figure-1",
        kind="figure",
        text="Figure 1",
        page=1,
    )
    region = ArtifactRegion(
        artifact_id=artifact.artifact_id,
        page=1,
        bbox=(0.1, 0.2, 0.9, 0.8),
        confidence=0.9,
        method="geometry",
        updated_at="2026-06-12T00:00:00Z",
    )
    store = ArtifactManifestStore()

    store.write(document, [artifact], {artifact.artifact_id: region})
    cached = store.read(document)

    assert cached is not None
    assert cached[0][0].artifact_id == artifact.artifact_id
    assert cached[1][artifact.artifact_id].bbox == region.bbox

    source.write_bytes(b"%PDF-test-updated")
    assert store.read(document) is None
