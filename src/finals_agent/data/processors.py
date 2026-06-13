from __future__ import annotations

from abc import ABC, abstractmethod
import json
from pathlib import Path
import re

from finals_agent.core.exceptions import IngestInputError, UnsupportedMaterialTypeError
from finals_agent.core.schemas import DocumentChunk, PaperArtifact, ProcessingRequest, ProcessingResult
from finals_agent.data.repository import SUPPORTED_TEXT_SUFFIXES


class DocumentProcessor(ABC):
    supported_suffixes: frozenset[str] = frozenset()

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.supported_suffixes

    @abstractmethod
    def process(self, request: ProcessingRequest) -> ProcessingResult:
        raise NotImplementedError


class TextProcessor(DocumentProcessor):
    supported_suffixes = frozenset(SUPPORTED_TEXT_SUFFIXES)

    def process(self, request: ProcessingRequest) -> ProcessingResult:
        text = request.source_path.read_text(encoding="utf-8", errors="ignore")
        chunks = tuple(_chunk_text(request, text))
        artifacts = tuple(_attach_chunk_ids(_extract_artifacts(request, text), chunks))
        return ProcessingResult(
            source_path=request.source_path,
            chunks=chunks,
            text_length=len(text),
            metadata={
                "processor": self.__class__.__name__,
                "suffix": request.source_path.suffix.lower(),
                "chunk_count": len(chunks),
                "artifact_count": len(artifacts),
                "chunk_size": request.chunk_size,
                "chunk_overlap": request.chunk_overlap,
            },
            artifacts=artifacts,
        )


class NotebookProcessor(DocumentProcessor):
    supported_suffixes = frozenset({".ipynb"})

    def process(self, request: ProcessingRequest) -> ProcessingResult:
        try:
            payload = json.loads(request.source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IngestInputError("Jupyter Notebook 文件无法解析。") from exc

        cells = payload.get("cells")
        if not isinstance(cells, list):
            raise IngestInputError("Jupyter Notebook 缺少 cells 数据。")

        sections = []
        code_cell_count = 0
        markdown_cell_count = 0
        for index, cell in enumerate(cells, start=1):
            if not isinstance(cell, dict):
                continue
            cell_type = str(cell.get("cell_type") or "raw")
            source = cell.get("source") or []
            content = "".join(source) if isinstance(source, list) else str(source)
            if not content.strip():
                continue
            if cell_type == "code":
                code_cell_count += 1
            elif cell_type == "markdown":
                markdown_cell_count += 1
            sections.append(f"[{cell_type} cell {index}]\n{content.strip()}")

        text = "\n\n".join(sections).strip()
        if not text:
            raise IngestInputError("Jupyter Notebook 中没有可读取的单元格。")
        chunks = tuple(_chunk_text(request, text))
        return ProcessingResult(
            source_path=request.source_path,
            chunks=chunks,
            text_length=len(text),
            metadata={
                "processor": self.__class__.__name__,
                "suffix": ".ipynb",
                "cell_count": len(cells),
                "code_cell_count": code_cell_count,
                "markdown_cell_count": markdown_cell_count,
                "chunk_count": len(chunks),
                "artifact_count": 0,
                "chunk_size": request.chunk_size,
                "chunk_overlap": request.chunk_overlap,
            },
            artifacts=(),
        )


class PdfProcessor(DocumentProcessor):
    supported_suffixes = frozenset({".pdf"})

    def process(self, request: ProcessingRequest) -> ProcessingResult:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise IngestInputError("PDF support requires the 'pypdf' package.") from exc

        reader = PdfReader(str(request.source_path))
        page_texts = []
        chunks = []
        artifacts = []
        image_count = 0
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                page_text = f"[page {page_number}]\n{text.strip()}"
                page_texts.append(page_text)
                page_chunks = tuple(
                    _chunk_text(
                        request,
                        page_text,
                        page_number=page_number,
                        chunk_index_start=len(chunks),
                    )
                )
                chunks.extend(page_chunks)
                artifacts.extend(
                    _attach_chunk_ids(
                        _extract_artifacts(request, page_text, page_number=page_number, artifact_index_start=len(artifacts)),
                        page_chunks,
                    )
                )
            image_count += _count_page_images(page)

        text = "\n\n".join(page_texts).strip()
        if not text:
            raise IngestInputError(
                "No extractable text found in PDF. Scanned PDFs will require an OCR processor later."
            )

        chunks = tuple(chunks)
        artifacts = tuple(artifacts)
        return ProcessingResult(
            source_path=request.source_path,
            chunks=chunks,
            text_length=len(text),
            metadata={
                "processor": self.__class__.__name__,
                "suffix": request.source_path.suffix.lower(),
                "page_count": len(reader.pages),
                "image_count": image_count,
                "chunk_count": len(chunks),
                "artifact_count": len(artifacts),
                "chunk_size": request.chunk_size,
                "chunk_overlap": request.chunk_overlap,
            },
            artifacts=artifacts,
        )


class DocumentProcessingPipeline:
    def __init__(self, processors: tuple[DocumentProcessor, ...] | None = None):
        self.processors = processors or (NotebookProcessor(), TextProcessor(), PdfProcessor())

    def process(self, request: ProcessingRequest) -> ProcessingResult:
        processor = self._select_processor(request.source_path)
        return processor.process(request)

    def _select_processor(self, path: Path) -> DocumentProcessor:
        for processor in self.processors:
            if processor.supports(path):
                return processor
        raise UnsupportedMaterialTypeError(
            f"No document processor registered for '{path.suffix}'."
        )


def _chunk_text(
    request: ProcessingRequest,
    text: str,
    page_number: int | None = None,
    chunk_index_start: int = 0,
):
    if request.chunk_size < 1:
        raise ValueError("chunk_size must be at least 1.")
    if request.chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative.")
    if request.chunk_overlap >= request.chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size.")

    step = request.chunk_size - request.chunk_overlap
    base_metadata = request.metadata.to_dict()
    current_section = request.metadata.chapter

    for local_index, start in enumerate(range(0, len(text), step)):
        index = chunk_index_start + local_index
        chunk_text = text[start : start + request.chunk_size]
        if not chunk_text:
            continue
        current_section = _detect_section(chunk_text) or current_section
        yield DocumentChunk(
            document_id=request.document_id,
            chunk_id=f"{request.document_id or 'pending'}-{index}",
            text=chunk_text,
            metadata={
                **base_metadata,
                "chunk_index": index,
                "start": start,
                "end": start + len(chunk_text),
                "page": page_number or _infer_page(chunk_text),
                "section": current_section,
                "block_type": _detect_block_type(chunk_text),
            },
        )


SECTION_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\s+)?(abstract|introduction|related work|background|method|methodology|approach|model|experiment|evaluation|results|discussion|conclusion|references|摘要|引言|相关工作|方法|实验|结果|讨论|结论|参考文献)\b.*$",
    re.I,
)
NUMBERED_HEADING_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+[A-Z][^.!?]{1,100}$")
EXACT_HEADING_RE = re.compile(
    r"^\s*(abstract|introduction|related work|background|method|methods|methodology|"
    r"approach|model|experiments?|evaluation|results|discussion|limitations?|"
    r"future work|conclusion|references)\s*$",
    re.I,
)
CAPTION_RE = re.compile(
    r"^\s*((?:fig(?:ure)?|table)\.?\s*\d+\s*[.:：]\s*.+|图\s*\d+\s*[.:：、]\s*.+|表\s*\d+\s*[.:：、]\s*.+)$",
    re.I,
)
TABLE_RE = re.compile(r"^\s*(?:table\.?\s*\d+|表\s*\d+)", re.I)
FORMULA_RE = re.compile(r"(\$.*?\$|\\\(|\\\[|\\begin\{equation\}|[=≈≤≥∑∏∫√±]\s*[^.!?。！？]{3,})")
PAGE_RE = re.compile(r"\[page\s+(\d+)\]", re.I)


def _detect_section(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 120:
            continue
        if EXACT_HEADING_RE.match(line) or NUMBERED_HEADING_RE.match(line):
            return line
    return None


def _detect_block_type(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if any(CAPTION_RE.match(line) and TABLE_RE.match(line) for line in lines):
        return "table"
    if any(CAPTION_RE.match(line) for line in lines):
        return "figure"
    if any(FORMULA_RE.search(line) for line in lines):
        return "formula"
    if _detect_section(text):
        return "section"
    return "paragraph"


def _extract_artifacts(
    request: ProcessingRequest,
    text: str,
    page_number: int | None = None,
    artifact_index_start: int = 0,
) -> list[PaperArtifact]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    artifacts: list[PaperArtifact] = []
    for index, line in enumerate(lines):
        kind = None
        caption = None
        if CAPTION_RE.match(line):
            kind = "table" if TABLE_RE.match(line) else "figure"
            caption = line
        elif FORMULA_RE.search(line) and len(line) <= 240:
            kind = "formula"

        if not kind:
            continue
        global_index = artifact_index_start + len(artifacts)
        nearby_text = _nearby_text(lines, index)
        artifacts.append(
            PaperArtifact(
                document_id=request.document_id,
                artifact_id=f"{request.document_id or 'pending'}-artifact-{global_index}",
                kind=kind,
                text=line,
                page=page_number or _infer_page(text),
                caption=caption,
                nearby_text=nearby_text,
                metadata={
                    **request.metadata.to_dict(),
                    "line_index": index,
                },
            )
        )
    return artifacts


def _attach_chunk_ids(artifacts: list[PaperArtifact], chunks: tuple[DocumentChunk, ...]) -> list[PaperArtifact]:
    attached = []
    for artifact in artifacts:
        chunk_id = artifact.chunk_id
        for chunk in chunks:
            if artifact.text in chunk.text:
                chunk_id = chunk.chunk_id
                break
        attached.append(
            PaperArtifact(
                document_id=artifact.document_id,
                artifact_id=artifact.artifact_id,
                kind=artifact.kind,
                text=artifact.text,
                page=artifact.page,
                caption=artifact.caption,
                nearby_text=artifact.nearby_text,
                chunk_id=chunk_id,
                metadata=artifact.metadata,
            )
        )
    return attached


def _nearby_text(lines: list[str], index: int, radius: int = 2) -> str:
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    return " ".join(lines[start:end])


def _infer_page(text: str) -> int | None:
    match = PAGE_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def _count_page_images(page) -> int:
    try:
        resources = page.get("/Resources") or {}
        xobjects = resources.get("/XObject") or {}
    except Exception:
        return 0

    count = 0
    for item in xobjects.values():
        try:
            obj = item.get_object()
            if obj.get("/Subtype") == "/Image":
                count += 1
        except Exception:
            continue
    return count
