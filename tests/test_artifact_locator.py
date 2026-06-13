from pathlib import Path

import fitz

from finals_agent.core.schemas import DocumentType
from finals_agent.core.schemas import PaperArtifact
from finals_agent.data.artifact_locator import (
    ArtifactRegionStore,
    HybridArtifactLocator,
    discover_numbered_pdf_artifacts,
    is_likely_visual_artifact,
    render_pdf_region_image,
)
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository


def test_geometry_locator_finds_vector_figure_and_caches_region(tmp_path: Path):
    source = tmp_path / "figure.pdf"
    pdf = fitz.open()
    page = pdf.new_page(width=600, height=800)
    page.draw_rect(fitz.Rect(80, 100, 520, 390), color=(0.1, 0.2, 0.5))
    page.draw_line(fitz.Point(110, 340), fitz.Point(480, 160), color=(0.1, 0.6, 0.3), width=4)
    page.insert_text(fitz.Point(80, 425), "Figure 1: Retrieval accuracy by context size.", fontsize=12)
    page.insert_text(fitz.Point(80, 470), "The figure reports the main result.", fontsize=11)
    pdf.save(source)
    pdf.close()
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, field="nlp"),
        repository=repository,
    )
    artifact = repository.read_artifacts(result.document)[0]
    locator = HybridArtifactLocator(
        repository=repository,
        layout_python=tmp_path / "missing-python.exe",
    )

    regions = locator.ensure_regions(result.document, [artifact])
    region = regions[artifact.artifact_id]
    image, mime_type = render_pdf_region_image(result.document, region.page, region.bbox)

    assert region.method == "pymupdf_geometry"
    assert region.confidence >= 0.72
    assert region.bbox[1] < 0.2
    assert region.bbox[3] < 0.6
    assert mime_type == "image/png"
    assert len(image) > 1000
    assert ArtifactRegionStore(repository).path(result.document).exists()


def test_manual_region_override_is_preserved(tmp_path: Path):
    source = tmp_path / "paper.pdf"
    pdf = fitz.open()
    page = pdf.new_page(width=600, height=800)
    page.insert_text(fitz.Point(80, 400), "Figure 1: Overview.", fontsize=12)
    pdf.save(source)
    pdf.close()
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, field="nlp"),
        repository=repository,
    )
    artifact = repository.read_artifacts(result.document)[0]
    store = ArtifactRegionStore(repository)
    store.write(result.document, {}, {artifact.artifact_id})

    manual = store.set_manual(result.document, artifact, (0.1, 0.2, 0.8, 0.7))
    regions = HybridArtifactLocator(
        repository=repository,
        region_store=store,
        layout_python=tmp_path / "missing-python.exe",
    ).ensure_regions(result.document, [artifact])

    assert manual.method == "manual"
    assert regions[artifact.artifact_id].bbox == (0.1, 0.2, 0.8, 0.7)
    assert regions[artifact.artifact_id].confidence == 1.0
    assert artifact.artifact_id not in store.read_unresolved(result.document)


def test_unresolved_region_is_cached(tmp_path: Path):
    source = tmp_path / "paper.pdf"
    pdf = fitz.open()
    page = pdf.new_page(width=600, height=800)
    page.insert_text(fitz.Point(80, 400), "Figure 1: Overview.", fontsize=12)
    pdf.save(source)
    pdf.close()
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, field="nlp"),
        repository=repository,
    )
    artifact = repository.read_artifacts(result.document)[0]
    store = ArtifactRegionStore(repository)
    locator = HybridArtifactLocator(
        repository=repository,
        region_store=store,
        layout_python=tmp_path / "missing-python.exe",
    )

    assert locator.ensure_regions(result.document, [artifact]) == {}
    assert artifact.artifact_id in store.read_unresolved(result.document)
    assert locator.ensure_regions(result.document, [artifact]) == {}


def test_visual_caption_filter_rejects_prose_reference():
    prose = PaperArtifact(
        document_id="doc",
        artifact_id="a",
        kind="table",
        text="Table 1 and Figure 4 illustrate the trade-off.",
        page=1,
        caption="Table 1 and Figure 4 illustrate the trade-off.",
    )
    caption = PaperArtifact(
        document_id="doc",
        artifact_id="b",
        kind="table",
        text="Table 1. Main results.",
        page=1,
        caption="Table 1. Main results.",
    )

    assert is_likely_visual_artifact(prose) is False
    assert is_likely_visual_artifact(caption) is True


def test_discovers_numbered_algorithm_and_equation_regions(tmp_path: Path):
    source = tmp_path / "numbered.pdf"
    pdf = fitz.open()
    page = pdf.new_page(width=600, height=800)
    page.insert_text(fitz.Point(60, 120), "Algorithm 1 RetrievalStep", fontsize=12)
    page.insert_text(fitz.Point(70, 150), "Input: query", fontsize=11)
    page.insert_text(fitz.Point(70, 175), "Return retrieved documents", fontsize=11)
    page.insert_text(fitz.Point(330, 260), "E(x) = x + 1    (1)", fontsize=12)
    pdf.save(source)
    pdf.close()
    document = type(
        "Document",
        (),
        {"id": "doc", "path": source},
    )()

    artifacts, regions = discover_numbered_pdf_artifacts(document)

    assert [(item.kind, item.caption) for item in artifacts] == [
        ("algorithm", "Algorithm 1"),
        ("formula", "Equation 1"),
    ]
    assert all(item.artifact_id in regions for item in artifacts)
