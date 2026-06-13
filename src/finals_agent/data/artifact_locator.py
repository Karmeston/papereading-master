from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from finals_agent.core.config import PROJECT_ROOT
from finals_agent.core.exceptions import VisionProcessingError
from finals_agent.core.schemas import PaperArtifact, StudyDocument
from finals_agent.data.repository import StudyRepository


GEOMETRY_ACCEPT_THRESHOLD = 0.72
VISUAL_CAPTION_RE = re.compile(
    r"^\s*(?:(?:fig(?:ure)?|table)\.?\s*\d+\s*[.:：]|[图表]\s*\d+\s*[.:：、])",
    re.I,
)
ALGORITHM_RE = re.compile(r"^\s*Algorithm\s+(?P<number>\d+)\b(?:\s*[:.]?\s*(?P<title>.*))?", re.I)
EQUATION_NUMBER_RE = re.compile(r"\((?P<number>\d+)\)\s*$")
MODEL_PATH = PROJECT_ROOT / "data" / "models" / "doclayout_yolo" / "doclayout_yolo_docstructbench_imgsz1024.pt"
WORKER_PATH = Path(__file__).with_name("layout_worker.py")


@dataclass(frozen=True)
class ArtifactRegion:
    artifact_id: str
    page: int
    bbox: tuple[float, float, float, float]
    confidence: float
    method: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "page": self.page,
            "bbox": list(self.bbox),
            "confidence": self.confidence,
            "method": self.method,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArtifactRegion":
        bbox = tuple(float(value) for value in payload["bbox"])
        if len(bbox) != 4:
            raise ValueError("bbox must contain four values")
        return cls(
            artifact_id=str(payload["artifact_id"]),
            page=int(payload["page"]),
            bbox=bbox,
            confidence=float(payload.get("confidence", 0.0)),
            method=str(payload.get("method") or "unknown"),
            updated_at=str(payload.get("updated_at") or ""),
        )


class ArtifactRegionStore:
    def __init__(self, repository: StudyRepository | None = None):
        self.repository = repository or StudyRepository()

    def read(self, document: StudyDocument) -> dict[str, ArtifactRegion]:
        try:
            payload = self._read_payload(document)
            return {
                item.artifact_id: item
                for item in (ArtifactRegion.from_dict(raw) for raw in payload.get("regions", []))
            }
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return {}

    def read_unresolved(self, document: StudyDocument) -> set[str]:
        try:
            payload = self._read_payload(document)
            return {str(item) for item in payload.get("unresolved", [])}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return set()

    def write(
        self,
        document: StudyDocument,
        regions: dict[str, ArtifactRegion],
        unresolved: set[str] | None = None,
    ) -> Path:
        path = self.path(document)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.tmp")
        if unresolved is None:
            unresolved = self.read_unresolved(document)
        temp.write_text(
            json.dumps(
                {
                    "version": 2,
                    "regions": [item.to_dict() for item in regions.values()],
                    "unresolved": sorted(unresolved),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temp.replace(path)
        return path

    def set_manual(
        self,
        document: StudyDocument,
        artifact: PaperArtifact,
        bbox: tuple[float, float, float, float],
    ) -> ArtifactRegion:
        normalized = _validate_bbox(bbox)
        if artifact.page is None:
            raise VisionProcessingError("Artifact page is unknown.")
        regions = self.read(document)
        region = ArtifactRegion(
            artifact_id=artifact.artifact_id,
            page=artifact.page,
            bbox=normalized,
            confidence=1.0,
            method="manual",
            updated_at=_now(),
        )
        regions[artifact.artifact_id] = region
        unresolved = self.read_unresolved(document)
        unresolved.discard(artifact.artifact_id)
        self.write(document, regions, unresolved)
        return region

    @staticmethod
    def path(document: StudyDocument) -> Path:
        return document.path.with_suffix(document.path.suffix + ".artifact_regions.json")

    def _read_payload(self, document: StudyDocument) -> dict[str, Any]:
        path = self.path(document)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}


class HybridArtifactLocator:
    def __init__(
        self,
        repository: StudyRepository | None = None,
        region_store: ArtifactRegionStore | None = None,
        layout_python: Path | None = None,
        model_path: Path = MODEL_PATH,
    ):
        self.repository = repository or StudyRepository()
        self.region_store = region_store or ArtifactRegionStore(self.repository)
        self.layout_python = layout_python or _layout_python()
        self.model_path = model_path

    def ensure_regions(
        self,
        document: StudyDocument,
        artifacts: list[PaperArtifact] | None = None,
        force: bool = False,
    ) -> dict[str, ArtifactRegion]:
        artifacts = artifacts or self.repository.read_artifacts(document)
        visual = [item for item in artifacts if is_likely_visual_artifact(item) and item.page]
        cached = {
            artifact_id: region
            for artifact_id, region in self.region_store.read(document).items()
            if region.method != "caption_fallback"
        }
        unresolved = set() if force else self.region_store.read_unresolved(document)
        pending = [
            item for item in visual
            if force or (item.artifact_id not in cached and item.artifact_id not in unresolved)
        ]
        if not pending or document.path.suffix.lower() != ".pdf":
            return cached

        try:
            import fitz
        except ImportError as exc:
            raise VisionProcessingError("PyMuPDF is required for artifact localization.") from exc

        pdf = fitz.open(str(document.path))
        model_pages: set[int] = set()
        geometry: dict[str, ArtifactRegion] = {}
        for artifact in pending:
            page = pdf.load_page(artifact.page - 1)
            region = _geometry_region(page, artifact)
            if region:
                geometry[artifact.artifact_id] = region
            if not region or region.confidence < GEOMETRY_ACCEPT_THRESHOLD:
                model_pages.add(artifact.page)

        model_detections: dict[int, list[dict[str, Any]]] = {}
        if model_pages:
            try:
                model_detections = self._run_layout_model_pages(pdf, sorted(model_pages))
            except Exception:
                model_detections = {page_number: [] for page_number in model_pages}

        model_regions = {}
        for page_number, detections in model_detections.items():
            page_artifacts = [item for item in pending if item.page == page_number]
            model_regions.update(
                _assign_model_regions(pdf.load_page(page_number - 1), page_artifacts, detections)
            )

        for artifact in pending:
            if cached.get(artifact.artifact_id, None) and cached[artifact.artifact_id].method == "manual":
                continue
            region = geometry.get(artifact.artifact_id)
            model_region = model_regions.get(artifact.artifact_id)
            if model_region and (not region or model_region.confidence > region.confidence):
                region = model_region
            if region:
                cached[artifact.artifact_id] = region
                unresolved.discard(artifact.artifact_id)
            else:
                cached.pop(artifact.artifact_id, None)
                unresolved.add(artifact.artifact_id)
        pdf.close()
        self.region_store.write(document, cached, unresolved)
        return cached

    def _run_layout_model_pages(self, pdf, page_numbers: list[int]) -> dict[int, list[dict[str, Any]]]:
        if not self.layout_python or not self.layout_python.exists():
            return {}
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="paper-agent-layout-") as temp_dir:
            temp = Path(temp_dir)
            output_path = temp / "layout.json"
            image_paths = []
            for page_number in page_numbers:
                image_path = temp / f"page-{page_number}.png"
                pixmap = pdf.load_page(page_number - 1).get_pixmap(matrix=_fitz_matrix(1.5), alpha=False)
                pixmap.save(str(image_path))
                image_paths.append(image_path)
            command = [
                str(self.layout_python),
                str(WORKER_PATH),
                "--image",
                *(str(path) for path in image_paths),
                "--model",
                str(self.model_path),
                "--output",
                str(output_path),
                "--device",
                os.environ.get("DOCLAYOUT_DEVICE", "cuda:0"),
            ]
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            detected = {}
            for item in payload.get("pages", []):
                page_number = int(Path(item["image"]).stem.split("-")[-1])
                detected[page_number] = list(item.get("detections", []))
            return detected


def render_pdf_region_image(
    document: StudyDocument,
    page_number: int,
    bbox: tuple[float, float, float, float] | list[float],
    dpi: int = 180,
) -> tuple[bytes, str]:
    try:
        import fitz
    except ImportError as exc:
        raise VisionProcessingError("PyMuPDF is required for PDF rendering.") from exc
    normalized = _validate_bbox(tuple(float(value) for value in bbox))
    pdf = fitz.open(str(document.path))
    page = pdf.load_page(page_number - 1)
    rect = page.rect
    clip = fitz.Rect(
        rect.x0 + normalized[0] * rect.width,
        rect.y0 + normalized[1] * rect.height,
        rect.x0 + normalized[2] * rect.width,
        rect.y0 + normalized[3] * rect.height,
    )
    pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), clip=clip, alpha=False)
    image = pixmap.tobytes("png")
    pdf.close()
    return image, "image/png"


def render_pdf_page_image(document: StudyDocument, page_number: int, dpi: int = 120) -> tuple[bytes, str]:
    try:
        import fitz
    except ImportError as exc:
        raise VisionProcessingError("PyMuPDF is required for PDF rendering.") from exc
    pdf = fitz.open(str(document.path))
    page = pdf.load_page(page_number - 1)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    image = pixmap.tobytes("png")
    pdf.close()
    return image, "image/png"


def discover_numbered_pdf_artifacts(
    document: StudyDocument,
) -> tuple[list[PaperArtifact], dict[str, ArtifactRegion]]:
    if document.path.suffix.lower() != ".pdf":
        return [], {}
    try:
        import fitz
    except ImportError:
        return [], {}

    artifacts = []
    regions = {}
    pdf = fitz.open(str(document.path))
    for page_index, page in enumerate(pdf):
        page_number = page_index + 1
        blocks = [
            {
                "rect": fitz.Rect(*raw[:4]),
                "text": " ".join(str(raw[4]).split()),
            }
            for raw in page.get_text("blocks")
            if str(raw[4]).strip()
        ]
        for block_index, block in enumerate(blocks):
            algorithm = ALGORITHM_RE.search(block["text"])
            if (
                algorithm
                and block["rect"].width < page.rect.width * 0.65
                and block["rect"].height < 32
                and len(block["text"]) < 120
            ):
                number = algorithm.group("number")
                artifact_id = f"{document.id}-algorithm-{page_number}-{number}"
                rect = _algorithm_rect(page.rect, blocks, block_index)
                artifacts.append(
                    PaperArtifact(
                        document_id=document.id,
                        artifact_id=artifact_id,
                        kind="algorithm",
                        text=block["text"],
                        page=page_number,
                        caption=f"Algorithm {number}",
                        nearby_text=block["text"],
                        metadata={"number": number, "source": "pymupdf_numbered"},
                    )
                )
                regions[artifact_id] = _region_from_rect(artifact_id, page_number, page.rect, rect)

            equation = EQUATION_NUMBER_RE.search(block["text"])
            if equation and _looks_like_equation(block["text"]):
                number = equation.group("number")
                artifact_id = f"{document.id}-equation-{page_number}-{number}"
                rect = _equation_rect(page.rect, blocks, block_index)
                artifacts.append(
                    PaperArtifact(
                        document_id=document.id,
                        artifact_id=artifact_id,
                        kind="formula",
                        text=block["text"],
                        page=page_number,
                        caption=f"Equation {number}",
                        nearby_text=block["text"],
                        metadata={"number": number, "source": "pymupdf_numbered"},
                    )
                )
                regions[artifact_id] = _region_from_rect(artifact_id, page_number, page.rect, rect)
    pdf.close()
    return artifacts, regions


def _algorithm_rect(page_rect, blocks: list[dict[str, Any]], index: int):
    heading = blocks[index]["rect"]
    left_column = heading.x0 < page_rect.x0 + page_rect.width * 0.5
    column_min = page_rect.x0 if left_column else page_rect.x0 + page_rect.width * 0.52
    column_max = page_rect.x0 + page_rect.width * 0.48 if left_column else page_rect.x1
    same_column = [
        item["rect"]
        for item in blocks[index + 1 :]
        if column_min <= item["rect"].x0 < column_max
        and item["rect"].y0 > heading.y1
    ]
    bottom = min(
        (
            rect.y0
            for rect in same_column
            if rect.x0 <= heading.x0 + 12
            and re.match(r"^\d+(?:\.\d+)*\.?\s+\D", _block_text_for_rect(blocks, rect))
        ),
        default=min(page_rect.y1, heading.y0 + page_rect.height * 0.36),
    )
    content = [
        item["rect"]
        for item in blocks
        if item["rect"].y0 >= heading.y0 - 2
        and item["rect"].y1 <= bottom
        and column_min <= item["rect"].x0 < column_max
    ]
    rect = heading
    for item in content:
        rect |= item
    return _pad_rect(page_rect, rect, 0.015, 0.012)


def _equation_rect(page_rect, blocks: list[dict[str, Any]], index: int):
    target = blocks[index]["rect"]
    rect = target
    for item in blocks:
        candidate = item["rect"]
        if candidate is target:
            continue
        same_column = abs(candidate.x0 - target.x0) < page_rect.width * 0.32
        nearby = candidate.y1 >= target.y0 - 32 and candidate.y0 <= target.y1 + 12
        if same_column and nearby and len(item["text"]) <= 180:
            rect |= candidate
    return _pad_rect(page_rect, rect, 0.02, 0.018)


def _looks_like_equation(text: str) -> bool:
    prefix = EQUATION_NUMBER_RE.sub("", text).strip()
    if not prefix or len(prefix) > 160:
        return False
    return any(token in prefix for token in ("=", "−", "+", "/", "∑", "α", "β", "γ", "E(", "P("))


def _block_text_for_rect(blocks: list[dict[str, Any]], rect) -> str:
    return next((item["text"] for item in blocks if item["rect"] == rect), "")


def _region_from_rect(artifact_id: str, page_number: int, page_rect, rect) -> ArtifactRegion:
    return ArtifactRegion(
        artifact_id=artifact_id,
        page=page_number,
        bbox=_normalize_rect(page_rect, rect),
        confidence=0.96,
        method="pymupdf_numbered",
        updated_at=_now(),
    )


def _geometry_region(page, artifact: PaperArtifact) -> ArtifactRegion | None:
    caption = _caption_rect(page, artifact.caption or artifact.text)
    candidates = _table_candidates(page) if artifact.kind == "table" else _figure_candidates(page)
    candidate, score = _best_candidate(page.rect, caption, candidates, artifact.kind)
    if candidate is None:
        return None
    crop = candidate | caption if caption is not None else candidate
    crop = _pad_rect(page.rect, crop, 0.015, 0.012)
    return ArtifactRegion(
        artifact_id=artifact.artifact_id,
        page=artifact.page or 1,
        bbox=_normalize_rect(page.rect, crop),
        confidence=round(score, 4),
        method="pymupdf_geometry",
        updated_at=_now(),
    )


def _assign_model_regions(
    page,
    artifacts: list[PaperArtifact],
    detections: list[dict[str, Any]],
) -> dict[str, ArtifactRegion]:
    pairs = []
    for artifact in artifacts:
        label = "table" if artifact.kind == "table" else "figure"
        caption = _caption_rect(page, artifact.caption or artifact.text)
        for index, item in enumerate(detections):
            if item.get("label") != label or float(item.get("confidence", 0)) < 0.2:
                continue
            rect = _denormalize_rect(page.rect, item["bbox"])
            spatial = _spatial_score(page.rect, caption, rect, artifact.kind)
            score = 0.7 * float(item["confidence"]) + 0.3 * spatial
            pairs.append((score, artifact, index, rect, caption))
    assigned_artifacts = set()
    assigned_detections = set()
    regions = {}
    for score, artifact, index, rect, caption in sorted(pairs, key=lambda item: item[0], reverse=True):
        if artifact.artifact_id in assigned_artifacts or index in assigned_detections:
            continue
        crop = rect | caption if caption is not None else rect
        crop = _pad_rect(page.rect, crop, 0.012, 0.01)
        regions[artifact.artifact_id] = ArtifactRegion(
            artifact_id=artifact.artifact_id,
            page=artifact.page or 1,
            bbox=_normalize_rect(page.rect, crop),
            confidence=round(min(0.99, score), 4),
            method="doclayout_yolo",
            updated_at=_now(),
        )
        assigned_artifacts.add(artifact.artifact_id)
        assigned_detections.add(index)
    return regions


def _figure_candidates(page) -> list[Any]:
    candidates = []
    for item in page.get_image_info():
        rect = _rect(*item["bbox"])
        if _area_ratio(page.rect, rect) >= 0.008:
            candidates.append(rect)
    drawing_rects = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is not None and rect.width > 3 and rect.height > 3:
            drawing_rects.append(rect)
    candidates.extend(_cluster_rects(drawing_rects, page.rect))
    return _dedupe_rects(candidates)


def _table_candidates(page) -> list[Any]:
    candidates = []
    try:
        finder = page.find_tables()
        candidates.extend(_rect(*table.bbox) for table in finder.tables)
    except Exception:
        pass
    return candidates


def _cluster_rects(rects: list[Any], page_rect) -> list[Any]:
    clusters = []
    for rect in sorted(rects, key=lambda item: (item.y0, item.x0)):
        expanded = _pad_rect(page_rect, rect, 0.012, 0.008)
        matches = [index for index, cluster in enumerate(clusters) if expanded.intersects(cluster)]
        if not matches:
            clusters.append(rect)
            continue
        merged = rect
        for index in reversed(matches):
            merged |= clusters.pop(index)
        clusters.append(merged)
    return [
        item for item in clusters
        if _area_ratio(page_rect, item) >= 0.015 and item.width >= page_rect.width * 0.12
    ]


def _best_candidate(page_rect, caption, candidates: list[Any], kind: str):
    best = None
    best_score = 0.0
    for candidate in candidates:
        score = _spatial_score(page_rect, caption, candidate, kind)
        if score > best_score:
            best = candidate
            best_score = score
    return best, best_score


def _spatial_score(page_rect, caption, candidate, kind: str) -> float:
    area = min(1.0, _area_ratio(page_rect, candidate) / 0.18)
    if caption is None:
        return 0.35 + 0.25 * area
    horizontal_overlap = max(0.0, min(caption.x1, candidate.x1) - max(caption.x0, candidate.x0))
    horizontal_overlap /= max(1.0, min(caption.width, candidate.width))
    distance = min(abs(candidate.y1 - caption.y0), abs(candidate.y0 - caption.y1)) / page_rect.height
    proximity = max(0.0, 1.0 - distance / 0.28)
    if kind == "figure":
        direction = 1.0 if candidate.y1 <= caption.y1 else 0.55
    else:
        direction = 1.0 if candidate.y0 >= caption.y0 else 0.72
    return min(0.98, 0.42 * horizontal_overlap + 0.34 * proximity + 0.14 * direction + 0.1 * area)


def _caption_rect(page, caption: str | None):
    if not caption:
        return None
    cleaned = " ".join(caption.split())
    candidates = [cleaned]
    label = cleaned.split(":", 1)[0].split(".", 1)[0]
    if label and len(label) <= 30:
        candidates.append(label)
    if len(cleaned) > 80:
        candidates.append(cleaned[:80])
    for text in candidates:
        try:
            matches = page.search_for(text)
        except Exception:
            matches = []
        if matches:
            rect = matches[0]
            for item in matches[1:]:
                rect |= item
            return rect
    return None


def _normalize_rect(page_rect, rect) -> tuple[float, float, float, float]:
    return _validate_bbox(
        (
            (rect.x0 - page_rect.x0) / page_rect.width,
            (rect.y0 - page_rect.y0) / page_rect.height,
            (rect.x1 - page_rect.x0) / page_rect.width,
            (rect.y1 - page_rect.y0) / page_rect.height,
        )
    )


def _denormalize_rect(page_rect, bbox):
    return _rect(
        page_rect.x0 + float(bbox[0]) * page_rect.width,
        page_rect.y0 + float(bbox[1]) * page_rect.height,
        page_rect.x0 + float(bbox[2]) * page_rect.width,
        page_rect.y0 + float(bbox[3]) * page_rect.height,
    )


def _validate_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (max(0.0, min(1.0, float(value))) for value in bbox)
    if x1 - x0 < 0.01 or y1 - y0 < 0.01:
        raise VisionProcessingError("Crop region is too small.")
    if x0 >= x1 or y0 >= y1:
        raise VisionProcessingError("Invalid crop region.")
    return (round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6))


def _pad_rect(page_rect, rect, x_ratio: float, y_ratio: float):
    return _rect(
        max(page_rect.x0, rect.x0 - page_rect.width * x_ratio),
        max(page_rect.y0, rect.y0 - page_rect.height * y_ratio),
        min(page_rect.x1, rect.x1 + page_rect.width * x_ratio),
        min(page_rect.y1, rect.y1 + page_rect.height * y_ratio),
    )


def _area_ratio(page_rect, rect) -> float:
    return max(0.0, rect.width * rect.height) / max(1.0, page_rect.width * page_rect.height)


def _dedupe_rects(rects: list[Any]) -> list[Any]:
    unique = []
    for rect in sorted(rects, key=lambda item: item.width * item.height, reverse=True):
        if any(_iou(rect, existing) > 0.88 for existing in unique):
            continue
        unique.append(rect)
    return unique


def _iou(first, second) -> float:
    intersection = first & second
    if intersection.is_empty:
        return 0.0
    intersection_area = intersection.width * intersection.height
    union = first.width * first.height + second.width * second.height - intersection_area
    return intersection_area / max(1.0, union)


def _rect(x0, y0, x1, y1):
    import fitz

    return fitz.Rect(float(x0), float(y0), float(x1), float(y1))


def _fitz_matrix(scale: float):
    import fitz

    return fitz.Matrix(scale, scale)


def _layout_python() -> Path | None:
    configured = os.environ.get("DOCLAYOUT_PYTHON")
    candidates = [
        Path(configured) if configured else None,
        Path(r"D:\ananconda\envs\llm-project\python.exe"),
    ]
    return next((path for path in candidates if path and path.exists()), None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_likely_visual_artifact(artifact: PaperArtifact) -> bool:
    if artifact.kind not in {"figure", "table"}:
        return False
    return bool(VISUAL_CAPTION_RE.match(artifact.caption or artifact.text or ""))
