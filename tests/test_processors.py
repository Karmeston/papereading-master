from pathlib import Path

import pytest
from pypdf import PdfWriter

from finals_agent.core.exceptions import IngestInputError, UnsupportedMaterialTypeError
from finals_agent.core.schemas import DocumentType, MaterialMetadata, ProcessingRequest
from finals_agent.data.processors import DocumentProcessingPipeline, PdfProcessor, TextProcessor


def _metadata(path: Path) -> MaterialMetadata:
    return MaterialMetadata(
        title="Lecture",
        document_type=DocumentType.NOTE,
        course="calculus",
        source_path=path,
        chapter="limits",
        tags=("week-1",),
    )


def test_text_processor_splits_text_into_chunks(tmp_path: Path):
    source = tmp_path / "lecture.md"
    source.write_text("abcdefghij", encoding="utf-8")

    result = TextProcessor().process(
        ProcessingRequest(
            source_path=source,
            metadata=_metadata(source),
            document_id="doc-1",
            chunk_size=4,
            chunk_overlap=1,
        )
    )

    assert result.text_length == 10
    assert result.metadata["chunk_count"] == 4
    assert result.metadata["artifact_count"] == 0
    assert [chunk.text for chunk in result.chunks] == ["abcd", "defg", "ghij", "j"]
    assert result.chunks[0].chunk_id == "doc-1-0"
    assert result.chunks[0].metadata["course"] == "calculus"
    assert result.chunks[0].metadata["chapter"] == "limits"
    assert result.chunks[0].metadata["section"] == "limits"
    assert result.chunks[0].metadata["block_type"] == "paragraph"


def test_text_processor_extracts_structured_artifacts(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text(
        "\n\n".join(
            [
                "Abstract",
                "Figure 1: Pipeline overview.",
                "Table 1: Main results.",
                "score = softmax(q k)",
            ]
        ),
        encoding="utf-8",
    )

    result = TextProcessor().process(
        ProcessingRequest(
            source_path=source,
            metadata=_metadata(source),
            document_id="doc-1",
        )
    )

    assert result.metadata["artifact_count"] == 3
    assert [artifact.kind for artifact in result.artifacts] == ["figure", "table", "formula"]
    assert result.artifacts[0].caption == "Figure 1: Pipeline overview."
    assert result.artifacts[0].chunk_id == "doc-1-0"
    assert "field" in result.artifacts[0].metadata


def test_pipeline_selects_matching_processor(tmp_path: Path):
    source = tmp_path / "lecture.txt"
    source.write_text("hello", encoding="utf-8")

    result = DocumentProcessingPipeline().process(
        ProcessingRequest(source_path=source, metadata=_metadata(source))
    )

    assert result.metadata["processor"] == "TextProcessor"
    assert len(result.chunks) == 1


def test_pipeline_rejects_unsupported_suffix(tmp_path: Path):
    source = tmp_path / "lecture.docx"
    source.write_bytes(b"docx")

    with pytest.raises(UnsupportedMaterialTypeError):
        DocumentProcessingPipeline().process(
            ProcessingRequest(source_path=source, metadata=_metadata(source))
        )


def test_pdf_processor_extracts_text_chunks(tmp_path: Path):
    source = tmp_path / "lecture.pdf"
    _write_text_pdf(source, "Lhopital rule limit practice")

    result = PdfProcessor().process(
        ProcessingRequest(
            source_path=source,
            metadata=_metadata(source),
            document_id="pdf-1",
            chunk_size=200,
            chunk_overlap=20,
        )
    )

    assert result.metadata["processor"] == "PdfProcessor"
    assert result.metadata["page_count"] == 1
    assert result.metadata["chunk_count"] == 1
    assert result.metadata["artifact_count"] == 0
    assert "Lhopital" in result.chunks[0].text
    assert result.chunks[0].document_id == "pdf-1"
    assert result.chunks[0].metadata["page"] == 1


def test_pipeline_selects_pdf_processor(tmp_path: Path):
    source = tmp_path / "lecture.pdf"
    _write_text_pdf(source, "PDF text for calculus")

    result = DocumentProcessingPipeline().process(
        ProcessingRequest(source_path=source, metadata=_metadata(source))
    )

    assert result.metadata["processor"] == "PdfProcessor"
    assert result.metadata["page_count"] == 1


def test_pdf_processor_reports_empty_scanned_pdf(tmp_path: Path):
    source = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with source.open("wb") as file:
        writer.write(file)

    with pytest.raises(IngestInputError, match="No extractable text"):
        PdfProcessor().process(ProcessingRequest(source_path=source, metadata=_metadata(source)))


def _write_text_pdf(path: Path, text: str) -> None:
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode("ascii"))
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(content))
