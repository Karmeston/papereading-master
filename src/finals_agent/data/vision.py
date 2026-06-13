from __future__ import annotations

import base64
import json
import re
import urllib.request
import urllib.error
from typing import Callable

from finals_agent.core.config import VisionSettings, load_settings, response_language_instruction
from finals_agent.core.exceptions import VisionProcessingError
from finals_agent.core.schemas import ArtifactInterpretation, PaperArtifact, StudyDocument
from finals_agent.data.artifact_interpretation import ArtifactInterpreter, BaselineArtifactInterpreter
from finals_agent.data.artifact_locator import HybridArtifactLocator, render_pdf_region_image


ImageLoader = Callable[[StudyDocument, PaperArtifact, int], tuple[bytes, str]]
VISION_INTERPRETATION_VERSION = 2


class OpenAICompatibleVisionClient:
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        timeout_seconds: int = 60,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def analyze(self, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        return "".join(self.analyze_stream(image_bytes, mime_type, prompt))

    def analyze_stream(self, image_bytes: bytes, mime_type: str, prompt: str):
        image_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        payload = {
            "model": self.model,
            "temperature": 0,
            "stream": True,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "paper-agent/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    payload = json.loads(data)
                    choice = (payload.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    text = _content_text(delta.get("content"))
                    if text:
                        yield text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise VisionProcessingError(f"Vision API request failed: HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise VisionProcessingError(f"Vision API request failed: {exc}") from exc


def build_vision_client(settings: VisionSettings | None = None) -> OpenAICompatibleVisionClient | None:
    settings = settings or load_settings(validate=False).vision
    if (
        settings.provider != "openai_compatible"
        or not settings.model
        or not settings.api_key
        or not settings.base_url
    ):
        return None
    return OpenAICompatibleVisionClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
    )


class VisionArtifactInterpreter(ArtifactInterpreter):
    method = "vision_api"

    def __init__(
        self,
        document: StudyDocument,
        client: OpenAICompatibleVisionClient | None = None,
        image_loader: ImageLoader | None = None,
        render_dpi: int = 180,
    ):
        self.document = document
        self.client = client
        self.image_loader = image_loader or render_pdf_artifact_image
        self.render_dpi = render_dpi
        self.baseline = BaselineArtifactInterpreter()

    def interpret(self, artifact: PaperArtifact) -> ArtifactInterpretation:
        stream = self.interpret_stream(artifact)
        while True:
            try:
                next(stream)
            except StopIteration as stop:
                return stop.value

    def interpret_stream(self, artifact: PaperArtifact):
        if artifact.kind not in {"figure", "table", "formula", "algorithm"}:
            return self.baseline.interpret(artifact)
        if not self.client:
            return vision_required_interpretation(artifact)
        try:
            image_bytes, mime_type = self.image_loader(self.document, artifact, self.render_dpi)
            table_cells = extract_pdf_table_cells(self.document, artifact) if artifact.kind == "table" else None
            parts = []
            analyze_stream = getattr(self.client, "analyze_stream", None)
            chunks = (
                analyze_stream(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    prompt=_vision_prompt(artifact),
                )
                if callable(analyze_stream)
                else (
                    self.client.analyze(
                        image_bytes=image_bytes,
                        mime_type=mime_type,
                        prompt=_vision_prompt(artifact),
                    ),
                )
            )
            for text in chunks:
                parts.append(text)
                yield text
            analysis = "".join(parts)
            return ArtifactInterpretation(
                document_id=artifact.document_id,
                artifact_id=artifact.artifact_id,
                kind=artifact.kind,
                extracted_text=artifact.caption or artifact.text,
                structured_data={
                    "caption": artifact.caption,
                    "nearby_text": artifact.nearby_text,
                    "page": artifact.page,
                    "chunk_id": artifact.chunk_id,
                    "vision_analysis": analysis,
                    "table_cells": table_cells,
                },
                interpretation=analysis,
                confidence=0.75,
                method=self.method,
                limitations=(
                    "Vision analysis may misread small text, dense legends, or exact numeric values.",
                    "Use the original PDF or a table parser to verify exact measurements before citing numbers.",
                ),
                metadata={
                    "source": "vision_api",
                    "render_dpi": self.render_dpi,
                    "requires_vision_api": False,
                    "interpretation_version": VISION_INTERPRETATION_VERSION,
                },
            )
        except VisionProcessingError as exc:
            return vision_required_interpretation(artifact, error=str(exc))


def build_vision_artifact_interpreter(
    document: StudyDocument,
    settings: VisionSettings | None = None,
    image_loader: ImageLoader | None = None,
) -> VisionArtifactInterpreter:
    settings = settings or load_settings(validate=False).vision
    client = build_vision_client(settings)
    return VisionArtifactInterpreter(
        document=document,
        client=client,
        image_loader=image_loader,
        render_dpi=settings.render_dpi,
    )


def vision_required_interpretation(artifact: PaperArtifact, error: str | None = None) -> ArtifactInterpretation:
    language = load_settings(validate=False).language
    extracted_text = artifact.caption or artifact.text
    reason = (
        "该图表需要视觉 API 才能完成解释，提取文字不能替代对图像内容的分析。"
        if language == "zh"
        else (
            "Vision API analysis is required for this visual paper artifact. "
            "Extracted text alone is not treated as a complete visual interpretation."
        )
    )
    if error:
        reason = f"{reason} {'最近一次视觉请求错误' if language == 'zh' else 'Last vision error'}: {error}"
    return ArtifactInterpretation(
        document_id=artifact.document_id,
        artifact_id=artifact.artifact_id,
        kind=artifact.kind,
        extracted_text=extracted_text,
        structured_data={
            "caption": artifact.caption,
            "nearby_text": artifact.nearby_text,
            "page": artifact.page,
            "chunk_id": artifact.chunk_id,
        },
        interpretation=reason,
        confidence=0.0,
        method="vision_api_required",
        limitations=(
            (
                "当前结果没有读取像素、坐标轴、图例、曲线或表格单元格。"
                if language == "zh"
                else "Does not inspect pixels, axes, legends, curves, or table cells."
            ),
            (
                "请配置视觉模型后再分析图表内容。"
                if language == "zh"
                else "Configure VISION_PROVIDER to analyze visual artifact contents."
            ),
        ),
        metadata={
            "source": "caption_and_nearby_text_only",
            "requires_vision_api": True,
            "vision_error": error,
            "interpretation_version": VISION_INTERPRETATION_VERSION,
        },
    )


def render_pdf_artifact_image(document: StudyDocument, artifact: PaperArtifact, dpi: int) -> tuple[bytes, str]:
    if document.path.suffix.lower() != ".pdf":
        raise VisionProcessingError("Vision artifact rendering requires the original PDF file.")
    if artifact.page is None:
        raise VisionProcessingError("Artifact page is unknown; cannot render image for vision analysis.")
    try:
        import fitz
    except ImportError as exc:
        raise VisionProcessingError("PDF rendering requires optional dependency: pip install -e .[vision].") from exc

    try:
        region = HybridArtifactLocator().ensure_regions(document, artifacts=[artifact]).get(artifact.artifact_id)
        if region:
            return render_pdf_region_image(document, region.page, region.bbox, dpi=dpi)
        pdf = fitz.open(str(document.path))
        page = pdf.load_page(artifact.page - 1)
        scale = dpi / 72
        clip = _artifact_clip_rect(page, artifact)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
        image = pixmap.tobytes("png")
        pdf.close()
        return image, "image/png"
    except Exception as exc:
        raise VisionProcessingError(f"Cannot render PDF page {artifact.page}: {exc}") from exc


def extract_pdf_table_cells(document: StudyDocument, artifact: PaperArtifact) -> list[list[str]] | None:
    if artifact.kind != "table" or document.path.suffix.lower() != ".pdf" or artifact.page is None:
        return None
    try:
        import fitz
    except ImportError:
        return None
    try:
        pdf = fitz.open(str(document.path))
        page = pdf.load_page(artifact.page - 1)
        region = HybridArtifactLocator().ensure_regions(document, artifacts=[artifact]).get(artifact.artifact_id)
        clip = (
            fitz.Rect(
                page.rect.x0 + region.bbox[0] * page.rect.width,
                page.rect.y0 + region.bbox[1] * page.rect.height,
                page.rect.x0 + region.bbox[2] * page.rect.width,
                page.rect.y0 + region.bbox[3] * page.rect.height,
            )
            if region
            else _artifact_clip_rect(page, artifact)
        )
        words = page.get_text("words", clip=clip)
        pdf.close()
    except Exception:
        return None
    if not words:
        return None
    rows: list[list[str]] = []
    current_y: float | None = None
    current_words: list[tuple[float, str]] = []
    for word in sorted(words, key=lambda item: (round(float(item[1]) / 4), float(item[0]))):
        x0, y0, _x1, _y1, text = float(word[0]), float(word[1]), float(word[2]), float(word[3]), str(word[4])
        if current_y is None or abs(y0 - current_y) <= 4:
            current_words.append((x0, text))
            current_y = y0 if current_y is None else current_y
            continue
        rows.append([text for _x, text in sorted(current_words)])
        current_words = [(x0, text)]
        current_y = y0
    if current_words:
        rows.append([text for _x, text in sorted(current_words)])
    return rows or None


def _artifact_clip_rect(page, artifact: PaperArtifact):
    caption_rect = _find_caption_rect(page, artifact.caption or artifact.text)
    if caption_rect is None:
        return page.rect
    return _clip_rect_from_caption_rect(page.rect, caption_rect, artifact.kind)


def _find_caption_rect(page, caption: str | None):
    if not caption:
        return None
    candidates = _caption_search_candidates(caption)
    for candidate in candidates:
        try:
            matches = page.search_for(candidate)
        except Exception:
            matches = []
        if matches:
            rect = matches[0]
            for item in matches[1:]:
                rect |= item
            return rect
    return None


def _caption_search_candidates(caption: str) -> list[str]:
    cleaned = " ".join(caption.split())
    if not cleaned:
        return []
    candidates = [cleaned]
    label = re.match(r"(?i)\s*((?:fig(?:ure)?|table)\.?\s*\d+|图\s*\d+|表\s*\d+)", cleaned)
    if label:
        candidates.append(label.group(1))
    if len(cleaned) > 80:
        candidates.append(cleaned[:80])
    return candidates


def _clip_rect_from_caption_rect(page_rect, caption_rect, kind: str):
    height = float(page_rect.height)
    margin_x = float(page_rect.width) * 0.05
    if kind == "table":
        y0 = max(float(page_rect.y0), float(caption_rect.y0) - height * 0.08)
        y1 = min(float(page_rect.y1), float(caption_rect.y1) + height * 0.45)
    else:
        y0 = max(float(page_rect.y0), float(caption_rect.y0) - height * 0.45)
        y1 = min(float(page_rect.y1), float(caption_rect.y1) + height * 0.12)
    try:
        import fitz

        return fitz.Rect(
            float(page_rect.x0) + margin_x,
            y0,
            float(page_rect.x1) - margin_x,
            y1,
        )
    except ImportError:
        return page_rect


def _vision_prompt(artifact: PaperArtifact) -> str:
    settings = load_settings(validate=False)
    return (
        "Analyze this cropped paper figure, table, equation, or algorithm region for a research-paper reading assistant.\n"
        "The primary goal is to explain what this artifact demonstrates for the paper, not to inventory every visual detail.\n"
        "Use this priority and structure:\n"
        "1. **它说明了什么**: state the paper claim, comparison, mechanism, or conclusion supported by the artifact.\n"
        "2. **关键证据**: mention only the 1-3 visible trends, contrasts, or values necessary to support that interpretation.\n"
        "3. **对原文的意义**: explain how it strengthens, qualifies, or challenges the nearby argument, method, or experiment.\n"
        "4. **注意事项**: briefly state uncertainty, limitations, or what the artifact cannot prove, only when relevant.\n"
        "Keep the whole explanation compact. Do not spend a paragraph listing every axis, legend item, curve, cell, symbol, "
        "or execution step. Do not repeat the caption. Separate directly visible evidence from contextual inference.\n"
        "For tables, quote exact numbers only when clearly readable and only when they matter to the conclusion.\n"
        "For charts, prioritize the decisive trend or comparison over a full visual walkthrough.\n"
        "For equations and algorithms, focus on their role in the paper's method; explain only the symbols or steps needed "
        "to understand that role.\n\n"
        f"Artifact kind: {artifact.kind}\n"
        f"Page: {artifact.page}\n"
        f"Caption/text: {artifact.caption or artifact.text}\n"
        f"Nearby paper context: {artifact.nearby_text or ''}\n"
        f"\n{response_language_instruction(settings.language)}"
    )


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")
