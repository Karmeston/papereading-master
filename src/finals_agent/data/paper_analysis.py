from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from finals_agent.core.exceptions import IngestInputError
from finals_agent.core.schemas import ArtifactInterpretation, PaperArtifact, StudyDocument
from finals_agent.data.artifact_interpretation import interpret_document_artifacts
from finals_agent.data.repository import StudyRepository
from finals_agent.data.selection import select_document


SECTION_PATTERNS = (
    "abstract",
    "introduction",
    "related work",
    "background",
    "method",
    "methodology",
    "approach",
    "model",
    "experiment",
    "evaluation",
    "results",
    "discussion",
    "conclusion",
    "references",
    "摘要",
    "引言",
    "相关工作",
    "方法",
    "实验",
    "结果",
    "讨论",
    "结论",
    "参考文献",
)

CAPTION_RE = re.compile(
    r"^\s*((?:fig(?:ure)?|table)\.?\s*\d+\s*[.:：]\s*.+|图\s*\d+\s*[.:：、]\s*.+|表\s*\d+\s*[.:：、]\s*.+)$",
    re.I,
)
TABLE_RE = re.compile(r"^\s*(?:table\.?\s*\d+|表\s*\d+)", re.I)
FORMULA_RE = re.compile(r"(\$.*?\$|\\\(|\\\[|\\begin\{equation\}|[=≈≤≥∑∏∫√±]\s*[^.!?。！？]{3,})")
SECTION_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\s+)?("
    + "|".join(re.escape(item) for item in SECTION_PATTERNS)
    + r")\b.*$",
    re.I,
)


@dataclass(frozen=True)
class PaperStructure:
    document_id: str
    title: str
    section_headings: tuple[str, ...]
    figure_captions: tuple[str, ...]
    table_captions: tuple[str, ...]
    formula_candidates: tuple[str, ...]
    paragraph_count: int
    page_count: int | None
    image_count: int | None
    artifacts: tuple[PaperArtifact, ...]
    artifact_interpretations: tuple[ArtifactInterpretation, ...]
    explanation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "section_headings": list(self.section_headings),
            "figure_captions": list(self.figure_captions),
            "table_captions": list(self.table_captions),
            "formula_candidates": list(self.formula_candidates),
            "paragraph_count": self.paragraph_count,
            "page_count": self.page_count,
            "image_count": self.image_count,
            "artifact_count": len(self.artifacts),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "artifact_interpretation_count": len(self.artifact_interpretations),
            "artifact_interpretations": [item.to_dict() for item in self.artifact_interpretations],
            "explanation": self.explanation,
        }


class PaperStructureAnalyzer:
    def __init__(self, repository: StudyRepository | None = None):
        self.repository = repository or StudyRepository()

    def analyze(
        self,
        document_id: str | None = None,
        title: str | None = None,
        query: str | None = None,
        interpret_artifacts: bool = True,
    ) -> PaperStructure:
        document = self._select_document(document_id=document_id, title=title, query=query)
        text = self.repository.read_searchable_text(document)
        if not text or not text.strip():
            raise IngestInputError("No searchable text found for this paper. Upload a text PDF or add OCR output first.")

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        artifacts = tuple(self.repository.read_artifacts(document))
        artifact_interpretations = (
            interpret_document_artifacts(document, repository=self.repository)
            if interpret_artifacts and artifacts
            else tuple(self.repository.read_artifact_interpretations(document))
        )
        sections = _unique_limited(_find_sections(lines), limit=20)
        figure_captions, table_captions = _captions_from_artifacts_or_text(artifacts, lines)
        formulas = _formulas_from_artifacts_or_text(artifacts, lines)
        page_count = _extract_page_count(text)
        image_count = _extract_pdf_image_count(document)

        return PaperStructure(
            document_id=document.id,
            title=document.title,
            section_headings=tuple(sections),
            figure_captions=tuple(figure_captions[:20]),
            table_captions=tuple(table_captions[:20]),
            formula_candidates=tuple(formulas[:20]),
            paragraph_count=len(_paragraphs(text)),
            page_count=page_count,
            image_count=image_count,
            artifacts=artifacts,
            artifact_interpretations=artifact_interpretations,
            explanation=_build_explanation(
                sections,
                figure_captions,
                table_captions,
                formulas,
                artifacts,
                artifact_interpretations,
                image_count,
            ),
        )

    def _select_document(
        self,
        document_id: str | None,
        title: str | None,
        query: str | None,
    ) -> StudyDocument:
        return select_document(
            self.repository,
            document_id=document_id,
            title=title,
            query=query,
            document_type=None,
        )


def _find_sections(lines: list[str]) -> list[str]:
    headings = []
    for line in lines:
        if len(line) > 120:
            continue
        if SECTION_RE.match(line):
            headings.append(line)
    return headings


def _captions_from_artifacts_or_text(artifacts: tuple[PaperArtifact, ...], lines: list[str]) -> tuple[list[str], list[str]]:
    figure_captions = [artifact.caption or artifact.text for artifact in artifacts if artifact.kind == "figure"]
    table_captions = [artifact.caption or artifact.text for artifact in artifacts if artifact.kind == "table"]
    if figure_captions or table_captions:
        return _unique_limited(figure_captions, 20), _unique_limited(table_captions, 20)

    figures = []
    tables = []
    for line in lines:
        if not CAPTION_RE.match(line):
            continue
        if TABLE_RE.match(line):
            tables.append(line)
        else:
            figures.append(line)
    return _unique_limited(figures, 20), _unique_limited(tables, 20)


def _formulas_from_artifacts_or_text(artifacts: tuple[PaperArtifact, ...], lines: list[str]) -> list[str]:
    formulas = [artifact.text for artifact in artifacts if artifact.kind == "formula"]
    if formulas:
        return _unique_limited(formulas, 20)
    candidates = []
    for line in lines:
        if len(line) > 240:
            continue
        if FORMULA_RE.search(line):
            candidates.append(line)
    return _unique_limited(candidates, 20)


def _paragraphs(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]


def _extract_page_count(text: str) -> int | None:
    pages = {int(match) for match in re.findall(r"\[page\s+(\d+)\]", text, flags=re.I)}
    if not pages:
        return None
    return max(pages)


def _extract_pdf_image_count(document: StudyDocument) -> int | None:
    if document.path.suffix.lower() != ".pdf" or not document.path.exists():
        return None
    try:
        from pypdf import PdfReader
    except ImportError:
        return None

    count = 0
    try:
        reader = PdfReader(str(document.path))
        for page in reader.pages:
            resources = page.get("/Resources") or {}
            xobjects = resources.get("/XObject") or {}
            for item in xobjects.values():
                obj = item.get_object()
                if obj.get("/Subtype") == "/Image":
                    count += 1
    except Exception:
        return None
    return count


def _build_explanation(
    sections: list[str],
    figure_captions: list[str],
    table_captions: list[str],
    formulas: list[str],
    artifacts: tuple[PaperArtifact, ...],
    artifact_interpretations: tuple[ArtifactInterpretation, ...],
    image_count: int | None,
) -> dict[str, Any]:
    return {
        "sections": "Detected section headings can be used to ask for targeted explanations by section.",
        "artifacts": (
            "Structured artifacts include kind, page, caption/text, nearby context, and chunk id."
            if artifacts
            else "No structured figure/table/formula artifacts were extracted."
        ),
        "artifact_interpretations": (
            "Baseline artifact interpretations use captions and nearby text only; OCR, table parsing, or vision backends are still needed for visual details."
            if artifact_interpretations
            else "No artifact interpretations were generated."
        ),
        "figures": (
            "Figure captions were found in text; embedded images require OCR or vision extraction for full visual explanation."
            if figure_captions or image_count
            else "No figure captions or embedded PDF images were detected."
        ),
        "tables": (
            "Table captions were found; full cell extraction requires a table parser such as camelot, tabula, or a vision model."
            if table_captions
            else "No table captions were detected."
        ),
        "formulas": (
            "Formula candidates were detected heuristically from symbols and LaTeX markers; ask about one candidate for step-by-step explanation."
            if formulas
            else "No formula candidates were detected in extractable text."
        ),
        "coverage": {
            "section_count": len(sections),
            "figure_caption_count": len(figure_captions),
            "table_caption_count": len(table_captions),
            "formula_candidate_count": len(formulas),
            "artifact_count": len(artifacts),
            "artifact_interpretation_count": len(artifact_interpretations),
            "image_count": image_count,
        },
    }


def _unique_limited(items: list[str], limit: int) -> list[str]:
    seen = set()
    unique = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique
