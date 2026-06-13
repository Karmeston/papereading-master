from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from threading import Thread
from urllib.parse import parse_qs, quote, urlparse
import webbrowser

from finals_agent.agent.llm import build_chat_model
from finals_agent.agent.runner import run_agent
from finals_agent.app.background_tasks import BackgroundTaskContext, BackgroundTaskManager
from finals_agent.app.ui_shell import APP_HTML
from finals_agent.core.config import (
    PROJECT_ROOT,
    RESEARCH_ATTACHMENTS_DIR,
    ensure_data_dirs,
    load_settings,
    normalize_app_language,
    response_language_instruction,
)
from finals_agent.core.exceptions import FinalsAgentError, VisionProcessingError
from finals_agent.core.observability import configure_logging
from finals_agent.core.runtime import AgentRuntime
from finals_agent.core.schemas import AgentRequest, DocumentType
from finals_agent.data.ingestion import build_ingest_request, ingest_material, replace_text_document_content
from finals_agent.data.embeddings import build_embedding_provider
from finals_agent.data.artifact_manifest import ArtifactManifestStore
from finals_agent.data.artifact_locator import (
    ArtifactRegionStore,
    HybridArtifactLocator,
    discover_numbered_pdf_artifacts,
    is_likely_visual_artifact,
    render_pdf_page_image,
    render_pdf_region_image,
)
from finals_agent.data.paper_download import import_arxiv_paper
from finals_agent.data.repository import StudyRepository
from finals_agent.data.research_assistant import ResearchAssistant
from finals_agent.data.reading_intelligence import ReadingIntelligence
from finals_agent.data.retrievers import HybridRetriever
from finals_agent.data.vision import (
    VISION_INTERPRETATION_VERSION,
    build_vision_artifact_interpreter,
    build_vision_client,
    render_pdf_artifact_image,
)
from finals_agent.data.workflows import PaperReadingWorkflow
from finals_agent.persistence.memory import JsonMemoryStore
from finals_agent.persistence.reading_state import ReadingStateStore, reading_state_summary
from finals_agent.persistence.research_tasks import ResearchTaskStore
from finals_agent.persistence.runs import JsonRunRecorder


BACKGROUND_TASKS = BackgroundTaskManager()


def serve_ui(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    app_window: bool = False,
) -> None:
    settings = load_settings(validate=False)
    ensure_data_dirs(settings.paths)
    configure_logging(debug=settings.runtime.debug)
    server = ThreadingHTTPServer((host, port), PaperAgentRequestHandler)
    url = f"http://{host}:{server.server_port}"
    if app_window:
        _open_app_window(url)
    elif open_browser:
        webbrowser.open(url)
    print(f"Paper Agent UI: {url}", flush=True)
    server.serve_forever()


def _open_app_window(url: str) -> None:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        Path(program_files) / "Google/Chrome/Application/chrome.exe" if program_files else None,
        Path(program_files_x86) / "Microsoft/Edge/Application/msedge.exe" if program_files_x86 else None,
        Path(local_app_data) / "Google/Chrome/Application/chrome.exe" if local_app_data else None,
        Path(local_app_data) / "Microsoft/Edge/Application/msedge.exe" if local_app_data else None,
    ]
    browser = next((str(path) for path in candidates if path and Path(path).exists()), None)
    if browser:
        subprocess.Popen([browser, f"--app={url}"])
        return
    webbrowser.open(url)


class PaperAgentRequestHandler(BaseHTTPRequestHandler):
    server_version = "PaperAgentUI/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(APP_HTML)
            return
        if parsed.path == "/api/documents":
            params = parse_qs(parsed.query)
            field = _first(params.get("field"))
            documents = StudyRepository().list_documents(field=field)
            self._send_json({"documents": [document.to_dict() for document in documents]})
            return
        if parsed.path == "/api/runs":
            params = parse_qs(parsed.query)
            limit = _int(_first(params.get("limit")), default=10)
            records = JsonRunRecorder().list_records()[-max(1, limit) :]
            records.reverse()
            self._send_json({"runs": records})
            return
        if parsed.path == "/api/research-tasks":
            params = parse_qs(parsed.query)
            limit = _int(_first(params.get("limit")), default=20)
            self._send_json({"tasks": ResearchTaskStore().list(limit=max(1, min(limit, 100)))})
            return
        if parsed.path == "/api/research-task":
            params = parse_qs(parsed.query)
            self._send_json({"task": ResearchTaskStore().get(_first(params.get("id")) or "")})
            return
        if parsed.path == "/api/background-task":
            params = parse_qs(parsed.query)
            self._send_json({"task": BACKGROUND_TASKS.get(_first(params.get("id")) or "")})
            return
        if parsed.path == "/api/research-attachment":
            params = parse_qs(parsed.query)
            self._send_research_attachment(
                _first(params.get("task_id")) or "",
                _first(params.get("attachment_id")) or "",
            )
            return
        if parsed.path == "/api/document-file":
            params = parse_qs(parsed.query)
            document_id = _first(params.get("id"))
            document = StudyRepository().get_document(document_id or "")
            self._send_file(document.path, display_name=_document_display_filename(document))
            return
        if parsed.path.startswith("/api/document-file/"):
            params = parse_qs(parsed.query)
            document_id = _first(params.get("id"))
            document = StudyRepository().get_document(document_id or "")
            self._send_file(document.path, display_name=_document_display_filename(document))
            return
        if parsed.path == "/api/document-content":
            params = parse_qs(parsed.query)
            document_id = _first(params.get("id"))
            repository = StudyRepository()
            document = repository.get_document(document_id or "")
            text = repository.read_searchable_text(document) or ""
            self._send_json({"document": document.to_dict(), "text": text[:200_000]})
            return
        if parsed.path == "/api/code-workspace":
            params = parse_qs(parsed.query)
            document_id = _first(params.get("id"))
            self._send_json(_api_code_workspace(document_id or ""))
            return
        if parsed.path == "/api/code-file":
            params = parse_qs(parsed.query)
            document_id = _first(params.get("id"))
            self._send_json(_api_code_file(document_id or ""))
            return
        if parsed.path == "/api/reading-history":
            params = parse_qs(parsed.query)
            document_id = _first(params.get("id"))
            self._send_json(_api_reading_history(document_id or ""))
            return
        if parsed.path == "/api/artifacts":
            params = parse_qs(parsed.query)
            document_id = _first(params.get("id"))
            repository = StudyRepository()
            document = repository.get_document(document_id or "")
            interpretations = {
                item.artifact_id: item.to_dict()
                for item in repository.read_artifact_interpretations(document)
                if int((item.metadata or {}).get("interpretation_version") or 0)
                >= VISION_INTERPRETATION_VERSION
            }
            force_refresh = (_first(params.get("refresh")) or "").lower() in {"1", "true", "yes"}
            artifact_items, regions = _display_artifacts(
                repository,
                document,
                force_refresh=force_refresh,
            )
            artifacts = []
            is_pdf = document.path.suffix.lower() == ".pdf"
            for artifact in artifact_items:
                region = regions.get(artifact.artifact_id)
                if is_pdf and region is None:
                    continue
                item = artifact.to_dict()
                item["interpretation"] = interpretations.get(artifact.artifact_id)
                item["image_available"] = is_pdf and artifact.page is not None and region is not None
                item["region"] = region.to_dict() if region else None
                artifacts.append(item)
            self._send_json({"document": document.to_dict(), "artifacts": artifacts})
            return
        if parsed.path == "/api/artifact-image":
            params = parse_qs(parsed.query)
            repository = StudyRepository()
            document = repository.get_document(_first(params.get("id")) or "")
            artifact_id = _first(params.get("artifact_id")) or ""
            artifact = _find_display_artifact(repository, document, artifact_id)
            if artifact is None:
                self._send_error(404, "Artifact not found.")
                return
            region = ArtifactRegionStore(repository).read(document).get(artifact.artifact_id)
            if region is None:
                self._send_error(404, "Artifact region not found.")
                return
            image, content_type = render_pdf_region_image(document, region.page, region.bbox, dpi=180)
            self._send_cached_response(200, image, content_type)
            return
        if parsed.path == "/api/artifact-page-image":
            params = parse_qs(parsed.query)
            repository = StudyRepository()
            document = repository.get_document(_first(params.get("id")) or "")
            page = _int(_first(params.get("page")), default=1)
            image, content_type = render_pdf_page_image(document, page, dpi=120)
            self._send_cached_response(200, image, content_type)
            return
        if parsed.path == "/api/document-pages":
            params = parse_qs(parsed.query)
            repository = StudyRepository()
            document = repository.get_document(_first(params.get("id")) or "")
            self._send_json(_pdf_page_manifest(document))
            return
        if parsed.path == "/api/document-page-text":
            params = parse_qs(parsed.query)
            repository = StudyRepository()
            document = repository.get_document(_first(params.get("id")) or "")
            page = _int(_first(params.get("page")), default=1)
            self._send_json(_pdf_page_text(document, page))
            return
        if parsed.path == "/api/settings":
            settings = load_settings(validate=False)
            self._send_json(
                {
                    "text": {
                        "provider": settings.model.provider,
                        "model": settings.model.model,
                        "base_url": settings.model.base_url or "",
                        "api_key_configured": _real_api_key(settings.model.api_key),
                        "api_key_hint": _api_key_hint(settings.model.api_key, settings.language),
                    },
                    "vision": {
                        "provider": settings.vision.provider,
                        "model": settings.vision.model or "",
                        "base_url": settings.vision.base_url or "",
                        "api_key_configured": _real_api_key(settings.vision.api_key),
                        "api_key_hint": _api_key_hint(settings.vision.api_key, settings.language),
                    },
                    "language": settings.language,
                }
            )
            return
        self._send_error(404, "Not found.")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/upload":
                self._send_json(self._handle_upload(parsed.query))
                return
            if parsed.path == "/api/research/attachment":
                self._send_json(self._handle_research_attachment(parsed.query))
                return
            payload = self._read_json()
            if parsed.path == "/api/ingest":
                self._send_json(_api_ingest(payload))
                return
            if parsed.path == "/api/remove":
                self._send_json(_api_remove(payload))
                return
            if parsed.path == "/api/document-organize":
                self._send_json(_api_document_organize(payload))
                return
            if parsed.path == "/api/search":
                self._send_json(_api_search(payload))
                return
            if parsed.path == "/api/read-stream":
                self._send_ndjson(_api_read_stream(payload))
                return
            if parsed.path == "/api/translate-stream":
                self._send_ndjson(_api_translate_stream(payload))
                return
            if parsed.path == "/api/read":
                self._send_json(_api_read(payload))
                return
            if parsed.path == "/api/explain":
                self._send_json(_api_explain(payload))
                return
            if parsed.path == "/api/compare":
                self._send_json(_api_compare(payload))
                return
            if parsed.path == "/api/research/discover":
                self._send_json(_api_research_discover(payload))
                return
            if parsed.path == "/api/research/import":
                self._send_json(_api_research_import(payload))
                return
            if parsed.path == "/api/research/new":
                self._send_json(_api_research_new(payload))
                return
            if parsed.path == "/api/research/update":
                self._send_json(_api_research_update(payload))
                return
            if parsed.path == "/api/research/analyze":
                self._send_json(_api_research_analyze(payload))
                return
            if parsed.path == "/api/research/correspondence":
                self._send_json(_api_research_correspondence(payload))
                return
            if parsed.path == "/api/research/experiment":
                self._send_json(_api_research_experiment(payload))
                return
            if parsed.path == "/api/research/assess":
                self._send_json(_api_research_assess(payload))
                return
            if parsed.path == "/api/background/start":
                self._send_json(_api_background_start(payload), status=202)
                return
            if parsed.path == "/api/background/cancel":
                self._send_json(
                    {"task": BACKGROUND_TASKS.cancel(str(payload.get("task_id") or ""))}
                )
                return
            if parsed.path == "/api/state":
                self._send_json(_api_state(payload))
                return
            if parsed.path == "/api/progress":
                self._send_json(_api_progress(payload))
                return
            if parsed.path == "/api/personal-note":
                self._send_json(_api_personal_note(payload))
                return
            if parsed.path == "/api/document-save":
                self._send_json(_api_document_save(payload))
                return
            if parsed.path == "/api/note":
                self._send_json(_api_note(payload))
                return
            if parsed.path == "/api/timeline-reorder":
                self._send_json(_api_timeline_reorder(payload))
                return
            if parsed.path == "/api/timeline-delete":
                self._send_json(_api_timeline_delete(payload))
                return
            if parsed.path == "/api/timeline-summary":
                self._send_json(_api_timeline_summary(payload))
                return
            if parsed.path == "/api/flashcard":
                self._send_json(_api_flashcard(payload))
                return
            if parsed.path == "/api/chat":
                self._send_json(_api_chat(payload))
                return
            if parsed.path == "/api/chat-stream":
                self._send_ndjson(_api_chat_stream(payload))
                return
            if parsed.path == "/api/artifact-explain":
                self._send_json(_api_artifact_explain(payload))
                return
            if parsed.path == "/api/artifact-explain-stream":
                self._send_ndjson(_api_artifact_explain_stream(payload))
                return
            if parsed.path == "/api/artifact-note":
                self._send_json(_api_artifact_note(payload))
                return
            if parsed.path == "/api/artifact-region":
                self._send_json(_api_artifact_region(payload))
                return
            if parsed.path == "/api/settings":
                self._send_json(_api_save_settings(payload))
                return
            self._send_error(404, "Not found.")
        except FinalsAgentError as exc:
            self._send_error(400, str(exc))
        except Exception as exc:
            self._send_error(500, f"{exc.__class__.__name__}: {exc}")

    def log_message(self, format: str, *args) -> None:
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 1:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def _handle_upload(self, query: str) -> dict:
        params = parse_qs(query)
        filename = Path(_first(params.get("filename")) or "upload.bin").name
        document_type = DocumentType(_first(params.get("document_type")) or DocumentType.PAPER.value)
        field = _clean(_first(params.get("field"))) or "未分类"
        title = _clean(_first(params.get("title")))
        source = _safe_relative_source(_first(params.get("source")) or filename)
        category = _clean(_first(params.get("category")))
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 1:
            raise FinalsAgentError("请选择要导入的文件。")
        if length > 100 * 1024 * 1024:
            raise FinalsAgentError("单个文件不能超过 100 MB。")
        suffix = Path(filename).suffix
        with tempfile.TemporaryDirectory(prefix="paper-agent-upload-") as temp_dir:
            source_path = Path(temp_dir) / f"upload{suffix}"
            with source_path.open("wb") as target:
                remaining = length
                while remaining:
                    block = self.rfile.read(min(1024 * 1024, remaining))
                    if not block:
                        break
                    target.write(block)
                    remaining -= len(block)
            result = ingest_material(
                build_ingest_request(
                    source_path=source_path,
                    document_type=document_type,
                    field=field,
                    title=title or Path(filename).stem,
                    source=source,
                ),
                repository=StudyRepository(),
            )
        document = result.document
        if category:
            document = StudyRepository().update_document_organization(
                document.id,
                category=category,
                update_category=True,
            )
        return {"document": document.to_dict(), "metadata": result.metadata}

    def _handle_research_attachment(self, query: str) -> dict:
        params = parse_qs(query)
        task_id = _first(params.get("task_id")) or ""
        filename = Path(_first(params.get("filename")) or "attachment.bin").name
        suffix = Path(filename).suffix.lower()
        content_type = (_first(params.get("content_type")) or "").lower()
        task_store = ResearchTaskStore()
        task = task_store.get(task_id)
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 1:
            raise FinalsAgentError("附件不能为空。")
        if length > 20 * 1024 * 1024:
            raise FinalsAgentError("单个实验结果附件不能超过 20 MB。")
        raw = self.rfile.read(length)
        is_markdown = suffix in {".md", ".markdown"}
        is_image = suffix in {".png", ".jpg", ".jpeg", ".webp"} or content_type.startswith("image/")
        if not is_markdown and not is_image:
            raise FinalsAgentError("实验结果附件仅支持 Markdown 和 PNG/JPEG/WebP 图片。")

        attachment_id = uuid.uuid4().hex[:12]
        target_dir = RESEARCH_ATTACHMENTS_DIR / task_id
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_suffix = suffix or (".png" if is_image else ".md")
        target = target_dir / f"{attachment_id}{safe_suffix}"
        target.write_bytes(raw)
        attachment = {
            "id": attachment_id,
            "filename": filename,
            "kind": "markdown" if is_markdown else "image",
            "content_type": content_type or _attachment_content_type(safe_suffix),
            "path": str(target),
            "content": "",
            "analysis": "",
            "vision_status": None,
        }
        if is_markdown:
            attachment["content"] = raw.decode("utf-8", errors="replace")[:200_000]
        else:
            client = build_vision_client()
            if client is None:
                attachment["vision_status"] = "not_configured"
            else:
                try:
                    attachment["analysis"] = client.analyze(
                        raw,
                        attachment["content_type"],
                        (
                            "Read this experiment-result image as evidence for a research decision. Extract visible "
                            "metrics, chart trends, legends, axes, error messages, logs, comparisons, anomalies, and "
                            "uncertainty. Separate directly observed values from interpretation. Do not invent hidden "
                            "numbers or missing context."
                            f"\n\n{response_language_instruction(load_settings(validate=False).language)}"
                        ),
                    )[:50_000]
                    attachment["vision_status"] = "analyzed"
                except VisionProcessingError as exc:
                    attachment["vision_status"] = "failed"
                    attachment["vision_error"] = str(exc)
        attachments = [*(task.get("result_attachments") or []), attachment]
        updated = task_store.update(task_id, result_attachments=attachments)
        return {"task": updated, "attachment": attachment}

    def _send_research_attachment(self, task_id: str, attachment_id: str) -> None:
        task = ResearchTaskStore().get(task_id)
        attachment = next(
            (item for item in task.get("result_attachments", []) if item.get("id") == attachment_id),
            None,
        )
        if not attachment:
            self._send_error(404, "Research attachment not found.")
            return
        path = Path(str(attachment.get("path") or "")).resolve()
        root = RESEARCH_ATTACHMENTS_DIR.resolve()
        if root not in path.parents or not path.exists():
            self._send_error(404, "Research attachment file not found.")
            return
        self._send_response(
            200,
            path.read_bytes(),
            str(attachment.get("content_type") or "application/octet-stream"),
        )

    def _send_html(self, content: str) -> None:
        self._send_response(200, content.encode("utf-8"), "text/html; charset=utf-8")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send_response(status, data, "application/json; charset=utf-8")

    def _send_error(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _send_ndjson(self, events) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for event in events:
                line = json.dumps(event, ensure_ascii=False, default=str) + "\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            try:
                line = json.dumps(
                    {"type": "error", "message": f"{exc.__class__.__name__}: {exc}"},
                    ensure_ascii=False,
                ) + "\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

    def _send_response(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_cached_response(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, display_name: str | None = None) -> None:
        if not path.exists():
            self._send_error(404, "Document file not found.")
            return
        content_type = {
            ".pdf": "application/pdf",
            ".txt": "text/plain; charset=utf-8",
            ".md": "text/markdown; charset=utf-8",
        }.get(path.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        filename = display_name or path.name
        ascii_filename = "".join(
            char if char.isascii() and (char.isalnum() or char in "._- ") else "_"
            for char in filename
        ).strip() or "document.pdf"
        self.send_header(
            "Content-Disposition",
            f"inline; filename=\"{ascii_filename}\"; filename*=UTF-8''{quote(filename)}",
        )
        self.end_headers()
        with path.open("rb") as source:
            shutil.copyfileobj(source, self.wfile)


def _api_ingest(payload: dict) -> dict:
    path = Path(str(payload.get("path") or "")).expanduser()
    document_type = DocumentType(payload.get("document_type") or DocumentType.PAPER.value)
    result = ingest_material(
        build_ingest_request(
            source_path=path,
            document_type=document_type,
            field=_clean(payload.get("field")),
            title=_clean(payload.get("title")),
            focus=_clean(payload.get("focus")),
            source=_clean(payload.get("source")),
        ),
        repository=StudyRepository(),
    )
    return {"document": result.document.to_dict(), "metadata": result.metadata}


def _document_display_filename(document) -> str:
    suffix = document.path.suffix.lower() or ".pdf"
    title = str(document.title or document.source or document.id).strip()
    title = title.replace("/", "_").replace("\\", "_")
    if title.lower().endswith(suffix):
        return title
    return f"{title}{suffix}"


def _api_remove(payload: dict) -> dict:
    document = StudyRepository().remove_document(str(payload.get("document_id") or ""))
    invalidated = ResearchTaskStore().invalidate_document(document.id)
    return {
        "removed": document.to_dict(),
        "invalidated_research_tasks": [task["id"] for task in invalidated],
    }


def _research_assistant(*, require_model: bool = True) -> ResearchAssistant:
    return ResearchAssistant(
        build_chat_model() if require_model else None,
        repository=StudyRepository(),
        task_store=ResearchTaskStore(),
    )


def _api_research_discover(
    payload: dict,
    task_context: BackgroundTaskContext | None = None,
) -> dict:
    direction = str(payload.get("direction") or "")
    return _research_assistant(require_model=True).discover(
        direction=direction,
        paper_ids=_string_list(payload.get("paper_ids")),
        code_ids=_string_list(payload.get("code_ids")),
        limit=_int(payload.get("limit"), default=6),
        task_id=_clean(payload.get("task_id")),
        cancel_check=task_context.raise_if_cancelled if task_context else None,
    )


def _api_research_import(
    payload: dict,
    task_context: BackgroundTaskContext | None = None,
) -> dict:
    task_store = ResearchTaskStore()
    task_id = str(payload.get("task_id") or "")
    candidate_id = str(payload.get("candidate_id") or "")
    task = task_store.get(task_id)
    candidate = next(
        (
            item
            for item in task.get("related_candidates", [])
            if str(item.get("id") or "") == candidate_id
        ),
        None,
    )
    if not candidate:
        raise FinalsAgentError("候选论文不存在或不属于当前科研任务。")

    if task_context:
        task_context.raise_if_cancelled()
    source_url = str(candidate.get("url") or "")
    repository = StudyRepository()
    existing = None
    imported = False
    try:
        existing, imported = import_arxiv_paper(
            source_url,
            title=str(candidate.get("title") or "arXiv paper"),
            field=(candidate.get("categories") or ["arXiv"])[0],
            tags=tuple(candidate.get("categories") or ()),
            repository=repository,
        )
        if task_context:
            task_context.raise_if_cancelled()

        candidates = [
            {
                **item,
                **(
                    {"imported_document_id": existing.id}
                    if str(item.get("id") or "") == candidate_id
                    else {}
                ),
            }
            for item in task.get("related_candidates", [])
        ]
        paper_ids = list(dict.fromkeys([*task.get("paper_ids", []), existing.id]))
        selected_related = [
            item
            for item in task.get("selected_related", [])
            if str(item.get("id") or "") != candidate_id
        ]
        updated = task_store.update(
            task_id,
            expected_revision=task["revision"],
            paper_ids=paper_ids,
            related_candidates=candidates,
            selected_related=selected_related,
        )
        return {
            "task": updated,
            "document": existing.to_dict(),
            "candidate_id": candidate_id,
        }
    except Exception:
        if imported and existing is not None:
            try:
                repository.remove_document(existing.id)
            except FinalsAgentError:
                pass
        raise


def _api_research_new(payload: dict) -> dict:
    task = ResearchTaskStore().create(
        name=str(payload.get("name") or ""),
        direction=str(payload.get("direction") or ""),
        paper_ids=_string_list(payload.get("paper_ids")),
        code_ids=_string_list(payload.get("code_ids")),
        candidate_sort=str(payload.get("candidate_sort") or "relevance"),
    )
    return {"task": task}


def _api_research_update(payload: dict) -> dict:
    return _research_assistant(require_model=False).update_task(
        task_id=str(payload.get("task_id") or ""),
        name=str(payload.get("name") or ""),
        direction=str(payload.get("direction") or ""),
        paper_ids=_string_list(payload.get("paper_ids")),
        code_ids=_string_list(payload.get("code_ids")),
        candidate_sort=str(payload.get("candidate_sort") or "relevance"),
    )


def _api_research_analyze(
    payload: dict,
    task_context: BackgroundTaskContext | None = None,
) -> dict:
    return _research_assistant().analyze(
        task_id=str(payload.get("task_id") or ""),
        direction=str(payload.get("direction") or ""),
        paper_ids=_string_list(payload.get("paper_ids")),
        code_ids=_string_list(payload.get("code_ids")),
        related_papers=(
            [item for item in payload["related_papers"] if isinstance(item, dict)]
            if isinstance(payload.get("related_papers"), list)
            else None
        ),
        cancel_check=task_context.raise_if_cancelled if task_context else None,
    )


def _api_research_correspondence(
    payload: dict,
    task_context: BackgroundTaskContext | None = None,
) -> dict:
    return _research_assistant().check_correspondence(
        task_id=str(payload.get("task_id") or ""),
        direction=str(payload.get("direction") or ""),
        paper_ids=_string_list(payload.get("paper_ids")),
        code_ids=_string_list(payload.get("code_ids")),
        cancel_check=task_context.raise_if_cancelled if task_context else None,
    )


def _api_research_experiment(
    payload: dict,
    task_context: BackgroundTaskContext | None = None,
) -> dict:
    direction_index = payload.get("direction_index")
    return _research_assistant().build_experiment(
        task_id=str(payload.get("task_id") or ""),
        mode=str(payload.get("mode") or "mvp"),
        objective=str(payload.get("objective") or ""),
        direction_index=(
            _int(direction_index, default=0)
            if direction_index is not None and str(direction_index).strip()
            else None
        ),
        cancel_check=task_context.raise_if_cancelled if task_context else None,
    )


def _api_research_assess(
    payload: dict,
    task_context: BackgroundTaskContext | None = None,
) -> dict:
    return _research_assistant().assess_result(
        task_id=str(payload.get("task_id") or ""),
        result=str(payload.get("result") or ""),
        attachment_ids=_string_list(payload.get("attachment_ids")),
        cancel_check=task_context.raise_if_cancelled if task_context else None,
    )


def _api_background_start(payload: dict) -> dict:
    kind = str(payload.get("kind") or "")
    task_payload = payload.get("payload")
    if not isinstance(task_payload, dict):
        task_payload = {}
    workers = {
        "research_discover": (
            "正在寻找相关论文",
            lambda context: _api_research_discover(task_payload, context),
        ),
        "research_import": (
            "正在下载并导入论文",
            lambda context: _api_research_import(task_payload, context),
        ),
        "research_analyze": (
            "正在综合分析论文与代码",
            lambda context: _api_research_analyze(task_payload, context),
        ),
        "research_correspondence": (
            "正在核对论文与代码",
            lambda context: _api_research_correspondence(task_payload, context),
        ),
        "research_experiment": (
            "正在生成实验方案",
            lambda context: _api_research_experiment(task_payload, context),
        ),
        "research_assess": (
            "正在评估实验结果",
            lambda context: _api_research_assess(task_payload, context),
        ),
    }
    if kind not in workers:
        raise FinalsAgentError(f"Unsupported background task kind: {kind}.")
    message, operation = workers[kind]

    def worker(context: BackgroundTaskContext) -> dict:
        context.update(10, message)
        result = operation(context)
        context.update(95, "正在整理结果")
        return result

    return {"task": BACKGROUND_TASKS.submit(kind, worker)}


def _api_reading_history(document_id: str) -> dict:
    document = StudyRepository().get_document(document_id)
    state = ReadingStateStore().get(document)
    timeline = [item.to_dict() for item in state.timeline]
    personal_note = next(
        (item for item in state.notes if item.id == "personal-note" and item.text.strip()),
        None,
    )
    if personal_note:
        timeline.append(personal_note.to_dict())
    memory = JsonMemoryStore().get(f"paper-{document.id}")
    legacy_entries = []
    pending_question = None
    for message in memory.messages:
        role = message.role.value
        if role == "user":
            pending_question = message.content
        elif role == "assistant" and pending_question is not None:
            legacy_entries.append(
                {
                    "text": pending_question,
                    "question": pending_question,
                    "answer": message.content,
                    "summary": _digest_sentence(message.content, max_chars=120),
                    "kind": "question",
                }
            )
            pending_question = None
    timeline_questions = {
        (_history_text(item.get("text") or item.get("question")), _history_text(item.get("answer")))
        for item in timeline
        if item.get("kind") == "question"
    }
    unmatched_legacy = [
        item
        for item in legacy_entries
        if (_history_text(item["question"]), _history_text(item["answer"])) not in timeline_questions
    ]
    return {
        "document": document.to_dict(),
        "entries": [*unmatched_legacy, *timeline],
    }


def _history_text(value) -> str:
    return " ".join(str(value or "").split()).casefold()


def _api_code_workspace(document_id: str) -> dict:
    repository = StudyRepository()
    selected = repository.get_document(document_id)
    if selected.document_type != DocumentType.CODE:
        raise FinalsAgentError("Selected document is not code.")
    documents = [
        document
        for document in repository.list_documents()
        if document.document_type == DocumentType.CODE
        and not document.archived
        and (
            document.id == selected.id
            or (selected.category and document.category == selected.category)
        )
    ]
    files = []
    for document in sorted(documents, key=lambda item: (item.source or item.title).casefold())[:3000]:
        suffix = document.path.suffix.lower()
        relative_path = _safe_relative_source(document.source or _document_display_filename(document))
        files.append(
            {
                "id": document.id,
                "title": document.title,
                "path": relative_path,
                "suffix": suffix,
                "language": _code_language(suffix),
                "kind": "notebook" if suffix == ".ipynb" else "code",
                "size": document.path.stat().st_size if document.path.exists() else 0,
                "editable": suffix in {".md", ".markdown"},
            }
        )
    return {
        "project": selected.category or selected.title,
        "selected_id": selected.id,
        "files": files,
    }


def _api_code_file(document_id: str) -> dict:
    document = StudyRepository().get_document(document_id)
    if document.document_type != DocumentType.CODE:
        raise FinalsAgentError("Selected document is not code.")
    suffix = document.path.suffix.lower()
    payload = {
        "id": document.id,
        "title": document.title,
        "path": _safe_relative_source(document.source or _document_display_filename(document)),
        "suffix": suffix,
        "language": _code_language(suffix),
        "kind": "notebook" if suffix == ".ipynb" else "code",
        "editable": suffix in {".md", ".markdown"},
    }
    if suffix == ".ipynb":
        payload["cells"] = _notebook_cells(document.path)
    else:
        payload["content"] = document.path.read_text(encoding="utf-8", errors="ignore")[:1_000_000]
        payload["truncated"] = document.path.stat().st_size > 1_000_000
    return {"file": payload}


def _api_document_save(payload: dict) -> dict:
    repository = StudyRepository()
    document = repository.get_document(str(payload.get("document_id") or ""))
    content = str(payload.get("content") or "")
    updated = replace_text_document_content(document, content, repository=repository)
    return {"document": updated.to_dict(), "content": content}


def _api_personal_note(payload: dict) -> dict:
    document = _select_document(payload)
    state = ReadingStateStore().set_personal_note(document, str(payload.get("text") or ""))
    return {"state": reading_state_summary(state)}


def _api_document_organize(payload: dict) -> dict:
    document = StudyRepository().update_document_organization(
        str(payload.get("document_id") or ""),
        pinned=_bool_or_none(payload.get("pinned")),
        archived=_bool_or_none(payload.get("archived")),
        category=_clean(payload.get("category")),
        update_category="category" in payload,
    )
    return {"document": document.to_dict()}


def _api_search(payload: dict) -> dict:
    query = str(payload.get("query") or "")
    document_type = DocumentType(payload["document_type"]) if payload.get("document_type") else None
    repository = StudyRepository()
    document_id = _clean(payload.get("document_id"))
    document = repository.get_document(document_id) if document_id else None
    if document and document.document_type == DocumentType.CODE:
        raise FinalsAgentError("代码资料不提供证据检索，请使用代码解析。")
    retriever = HybridRetriever(
        repository=repository,
        embedding_provider=build_embedding_provider(),
    )
    result = ReadingIntelligence(build_chat_model(), repository=repository).search(
        query,
        retriever,
        document=document,
        field=_clean(payload.get("field")),
        document_type=document_type,
        limit=_int(payload.get("limit"), default=8),
    )
    if document:
        state = ReadingStateStore().add_timeline_entry(
            document,
            "evidence_search",
            query,
            answer=json.dumps(result, ensure_ascii=False),
            metadata={"result_count": len(result.get("results") or [])},
        )
        result["record"] = state.timeline[-1].to_dict()
    return result


def _api_read(payload: dict) -> dict:
    repository = StudyRepository()
    result = PaperReadingWorkflow(repository=repository).read(
        document_id=_clean(payload.get("document_id")),
        title=_clean(payload.get("title")),
        field=_clean(payload.get("field")),
        query=_clean(payload.get("query")),
        related_limit=_int(payload.get("related_limit"), default=0),
    )
    response = result.to_dict()
    data = response["data"]
    data["synthesis"] = ReadingIntelligence(build_chat_model(), repository=repository).synthesize(
        paper=data["paper"],
        section_passes=data["section_passes"],
        evidence=data["evidence"],
        coverage=data["coverage"],
    )
    return response


def _api_read_stream(payload: dict):
    language = load_settings(validate=False).language
    repository = StudyRepository()
    document_id = _clean(payload.get("document_id"))
    document = repository.get_document(document_id) if document_id else None
    if document and document.document_type == DocumentType.CODE:
        yield from _api_code_read_stream(document, repository, payload)
        return
    yield {
        "type": "status",
        "message": _language_text(language, "正在按章节整理原文证据...", "Organizing source evidence by section..."),
    }
    result = PaperReadingWorkflow(repository=repository).read(
        document_id=document_id,
        title=_clean(payload.get("title")),
        field=_clean(payload.get("field")),
        query=_clean(payload.get("query")),
        related_limit=0,
    )
    data = result.to_dict()["data"]
    intelligence = ReadingIntelligence(build_chat_model(), repository=repository)
    context = intelligence.report_context(
        paper=data["paper"],
        section_passes=data["section_passes"],
        evidence=data["evidence"],
        coverage=data["coverage"],
    )
    yield {
        "type": "metadata",
        "coverage": data["coverage"],
        "reading_state": data.get("reading_state"),
        "evidence_count": context["evidence_count"],
    }
    yield {
        "type": "status",
        "message": _language_text(language, "正在生成深入阅读报告...", "Generating the in-depth reading report..."),
    }
    answer_parts = []
    for text in intelligence.stream_report(context):
        answer_parts.append(text)
        yield {"type": "delta", "text": text}
    answer = "".join(answer_parts)
    used_citations = [
        citation
        for citation in context["allowed_citations"]
        if citation in answer
    ]
    record = None
    if document:
        state = ReadingStateStore().add_timeline_entry(
            document,
            "smart_reading",
            _language_text(language, "智能阅读", "Smart reading"),
            answer=answer,
            metadata={
                "regenerated": bool(payload.get("regenerate")),
                "evidence_count": context["evidence_count"],
            },
        )
        record = state.timeline[-1].to_dict()
    yield {
        "type": "done",
        "record": record,
        "citation_check": {
            "passed": bool(used_citations),
            "used_citations": used_citations,
            "available_citation_count": len(context["allowed_citations"]),
        },
    }


def _api_translate_stream(payload: dict):
    text = str(payload.get("text") or "").strip()
    if not text:
        raise FinalsAgentError("请选择需要翻译的原文。")
    if len(text) > 20_000:
        raise FinalsAgentError("单次翻译不能超过 20,000 个字符。")
    settings = load_settings(validate=False)
    language = settings.language
    target = "简体中文" if language == "zh" else "English"
    yield {
        "type": "status",
        "message": _language_text(language, "正在翻译选中内容...", "Translating the selection..."),
    }
    system = (
        "You are a precise academic translator. Translate only the supplied research-paper excerpt "
        f"into {target}. Preserve equations, symbols, citations, numbers, paragraph boundaries, and technical terms. "
        "Do not summarize, explain, add headings, or mention that this is a translation. "
        f"\n\n{response_language_instruction(language)}"
    )
    model = build_chat_model()
    answer_parts = []
    for chunk in model.stream(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]
    ):
        translated = getattr(chunk, "content", chunk)
        if isinstance(translated, list):
            translated = "".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in translated
            )
        translated = str(translated or "")
        if not translated:
            continue
        answer_parts.append(translated)
        yield {"type": "delta", "text": translated}
    yield {
        "type": "done",
        "source_length": len(text),
        "translation_length": len("".join(answer_parts)),
        "target_language": language,
    }


def _api_code_read_stream(document, repository: StudyRepository, payload: dict | None = None):
    payload = payload or {}
    language = load_settings(validate=False).language
    detail = str(payload.get("code_detail") or "brief").lower()
    if detail not in {"brief", "detailed"}:
        raise FinalsAgentError("Unsupported code analysis detail mode.")
    project, files, context = _code_analysis_context(
        document,
        repository,
        max_chars=50_000 if detail == "brief" else 120_000,
    )
    yield {
        "type": "status",
        "message": _language_text(language, "正在读取项目结构与关键文件...", "Reading the project structure and key files..."),
    }
    yield {
        "type": "metadata",
        "mode": "code",
        "project": project,
        "file_count": len(files),
        "included_file_count": context.count("\n--- FILE:"),
    }
    yield {
        "type": "status",
        "message": _language_text(language, "正在生成代码解析...", "Generating the code analysis..."),
    }
    if detail == "detailed":
        instructions = (
            "详细解释项目中的每个已提供文件，并按函数、类、配置块或连续代码段说明其输入、输出、"
            "状态变化、调用关系和实现目的。对关键代码段引用相对路径及符号名，解释执行流程和边界情况。"
            "不要逐字符复述，也不要推断上下文中不存在的实现。"
        )
    else:
        instructions = (
            "简要概括项目用途、目录与模块职责、入口、主要执行流程和关键依赖，帮助读者快速知道"
            "代码在做什么以及应该先读哪些文件。避免逐段解释。"
        )
    system = (
        "你是资深代码审阅者。请基于给出的本地项目内容生成结构化代码解析。"
        f"{instructions}"
        "只陈述上下文能支持的事实；引用文件时使用反引号包裹相对路径。使用 Markdown 小标题。"
        f"\n\n{response_language_instruction(language)}"
    )
    prompt = f"项目：{project}\n文件数：{len(files)}\n\n{context}"
    answer_parts = []
    model = build_chat_model()
    for chunk in model.stream(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
    ):
        text = getattr(chunk, "content", chunk)
        if isinstance(text, list):
            text = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in text)
        text = str(text or "")
        if not text:
            continue
        answer_parts.append(text)
        yield {"type": "delta", "text": text}
    answer = "".join(answer_parts)
    state = ReadingStateStore().add_timeline_entry(
        document,
        "code_analysis",
        _language_text(
            language,
            "详细代码解析" if detail == "detailed" else "简略代码解析",
            "Detailed code analysis" if detail == "detailed" else "Brief code analysis",
        ),
        answer=answer,
        metadata={
            "detail": detail,
            "regenerated": bool(payload.get("regenerate")),
            "file_count": len(files),
        },
    )
    yield {
        "type": "done",
        "mode": "code",
        "detail": detail,
        "record": state.timeline[-1].to_dict(),
        "file_count": len(files),
        "answer_length": len(answer),
    }


def _code_analysis_context(document, repository: StudyRepository, max_chars: int = 80_000):
    project = document.category or document.title
    files = [
        item
        for item in repository.list_documents()
        if item.document_type == DocumentType.CODE
        and not item.archived
        and (item.id == document.id or (document.category and item.category == document.category))
    ]
    priority_names = {
        "readme.md": 0, "pyproject.toml": 1, "package.json": 1, "requirements.txt": 1,
        "main.py": 2, "app.py": 2, "index.js": 2, "index.ts": 2,
    }
    files.sort(
        key=lambda item: (
            0 if item.id == document.id else 1,
            priority_names.get(Path(item.source or item.title).name.casefold(), 5),
            (item.source or item.title).casefold(),
        )
    )
    parts = ["目录：", *[f"- {_safe_relative_source(item.source or item.title)}" for item in files[:1000]]]
    used = sum(len(part) + 1 for part in parts)
    for item in files:
        if used >= max_chars:
            break
        path = _safe_relative_source(item.source or item.title)
        if item.path.suffix.lower() == ".ipynb":
            content = "\n\n".join(
                f"[{cell['type']}]\n{cell['content']}"
                for cell in _notebook_cells(item.path)
                if cell.get("content")
            )
        else:
            content = item.path.read_text(encoding="utf-8", errors="ignore")
        remaining = max_chars - used
        excerpt = content[: min(12_000, remaining)]
        block = f"\n--- FILE: {path} ---\n{excerpt}"
        parts.append(block)
        used += len(block)
    return project, files, "\n".join(parts)


def _api_explain(payload: dict) -> dict:
    result = PaperReadingWorkflow(repository=StudyRepository()).explain(
        target=str(payload.get("target") or ""),
        document_id=_clean(payload.get("document_id")),
        title=_clean(payload.get("title")),
        field=_clean(payload.get("field")),
        query=_clean(payload.get("query")),
        limit=_int(payload.get("limit"), default=5),
    )
    return result.to_dict()


def _api_compare(payload: dict) -> dict:
    result = PaperReadingWorkflow(repository=StudyRepository()).compare(
        topic=str(payload.get("topic") or ""),
        document_id=_clean(payload.get("document_id")),
        title=_clean(payload.get("title")),
        field=_clean(payload.get("field")),
        query=_clean(payload.get("query")),
        related_limit=_int(payload.get("related_limit"), default=5),
    )
    return result.to_dict()


def _api_state(payload: dict) -> dict:
    document = _select_document(payload)
    store = ReadingStateStore()
    state = store.get(document)
    compacted = _compact_reading_digest(state.review_summary)
    if state.review_summary and compacted != state.review_summary:
        state = store.update_progress(document, review_summary=compacted)
    return {"state": reading_state_summary(state)}


def _display_artifacts(
    repository: StudyRepository,
    document,
    *,
    force_refresh: bool = False,
) -> tuple[list, dict]:
    manifest_store = ArtifactManifestStore()
    if not force_refresh:
        cached = manifest_store.read(document)
        if cached is not None:
            return cached
    stored = repository.read_artifacts(document)
    visible = [item for item in stored if is_likely_visual_artifact(item)]
    locator = HybridArtifactLocator(repository=repository)
    regions = locator.ensure_regions(document, visible, force=force_refresh)
    supplemental, discovered_regions = discover_numbered_pdf_artifacts(document)
    if discovered_regions:
        region_store = ArtifactRegionStore(repository)
        persisted = region_store.read(document)
        changed = False
        for artifact_id, region in discovered_regions.items():
            if artifact_id not in persisted:
                persisted[artifact_id] = region
                changed = True
        if changed:
            region_store.write(document, persisted)
        regions = {**regions, **persisted}
    items = [
        item
        for item in (*visible, *supplemental)
        if document.path.suffix.lower() != ".pdf" or item.artifact_id in regions
    ]
    items = _deduplicate_display_artifacts(items, regions)
    items.sort(
        key=lambda item: (
            item.page or 0,
            {"figure": 0, "table": 1, "algorithm": 2, "formula": 3}.get(item.kind, 9),
            item.artifact_id,
        )
    )
    manifest_store.write(document, items, regions)
    return items, regions


def _deduplicate_display_artifacts(items: list, regions: dict) -> list:
    deduplicated = []
    for artifact in items:
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(deduplicated)
                if _artifacts_are_duplicates(existing, artifact, regions)
            ),
            None,
        )
        if duplicate_index is None:
            deduplicated.append(artifact)
            continue
        existing = deduplicated[duplicate_index]
        if _artifact_quality(artifact, regions) > _artifact_quality(existing, regions):
            deduplicated[duplicate_index] = artifact
    return deduplicated


def _artifacts_are_duplicates(left, right, regions: dict) -> bool:
    if left.page != right.page or left.kind != right.kind:
        return False
    left_number = _artifact_number(left)
    right_number = _artifact_number(right)
    if left_number and right_number and left_number == right_number:
        return True
    left_title = _normalized_artifact_title(left.caption or left.text)
    right_title = _normalized_artifact_title(right.caption or right.text)
    if left_title and right_title and left_title == right_title:
        return True
    left_region = regions.get(left.artifact_id)
    right_region = regions.get(right.artifact_id)
    return bool(
        left_region
        and right_region
        and _bbox_iou(left_region.bbox, right_region.bbox) >= 0.72
    )


def _artifact_number(artifact) -> str:
    metadata = artifact.metadata or {}
    if metadata.get("number") is not None:
        return str(metadata["number"])
    text = str(artifact.caption or artifact.text or "")
    match = re.search(
        r"(?:figure|fig\.?|table|algorithm|equation|图|表|算法|公式)\s*(\d+)",
        text,
        re.I,
    )
    return match.group(1) if match else ""


def _normalized_artifact_title(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9\u3400-\u9fff]+", str(value or "").casefold()))[:180]


def _artifact_quality(artifact, regions: dict) -> tuple:
    region = regions.get(artifact.artifact_id)
    return (
        bool(region),
        float(region.confidence if region else 0),
        len(str(artifact.caption or artifact.text or "")),
    )


def _bbox_iou(left, right) -> float:
    x0 = max(float(left[0]), float(right[0]))
    y0 = max(float(left[1]), float(right[1]))
    x1 = min(float(left[2]), float(right[2]))
    y1 = min(float(left[3]), float(right[3]))
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if intersection <= 0:
        return 0.0
    left_area = max(0.0, float(left[2]) - float(left[0])) * max(
        0.0, float(left[3]) - float(left[1])
    )
    right_area = max(0.0, float(right[2]) - float(right[0])) * max(
        0.0, float(right[3]) - float(right[1])
    )
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def _find_display_artifact(repository: StudyRepository, document, artifact_id: str):
    artifacts, _regions = _display_artifacts(repository, document)
    return next((item for item in artifacts if item.artifact_id == artifact_id), None)


def _api_progress(payload: dict) -> dict:
    document = _select_document(payload)
    state = ReadingStateStore().update_progress(
        document,
        status=_clean(payload.get("status")),
        current_section=_clean(payload.get("current_section")),
        progress_percent=_int_or_none(payload.get("progress_percent")),
        current_page=_int_or_none(payload.get("current_page")),
        page_count=_int_or_none(payload.get("page_count")),
        review_summary=_clean(payload.get("review_summary")),
    )
    return {"state": reading_state_summary(state)}


def _pdf_page_manifest(document) -> dict:
    if document.path.suffix.lower() != ".pdf":
        raise FinalsAgentError("Document is not a PDF.")
    try:
        import fitz
    except ImportError as exc:
        raise FinalsAgentError("PyMuPDF is required for PDF reading.") from exc
    pdf = fitz.open(str(document.path))
    pages = [
        {
            "page": index + 1,
            "width": round(float(page.rect.width), 2),
            "height": round(float(page.rect.height), 2),
        }
        for index, page in enumerate(pdf)
    ]
    pdf.close()
    return {"document_id": document.id, "page_count": len(pages), "pages": pages}


def _pdf_page_text(document, page_number: int) -> dict:
    if document.path.suffix.lower() != ".pdf":
        raise FinalsAgentError("Document is not a PDF.")
    try:
        import fitz
    except ImportError as exc:
        raise FinalsAgentError("PyMuPDF is required for PDF text selection.") from exc
    pdf = fitz.open(str(document.path))
    try:
        if page_number < 1 or page_number > len(pdf):
            raise FinalsAgentError("PDF page is out of range.")
        page = pdf[page_number - 1]
        width = float(page.rect.width) or 1.0
        height = float(page.rect.height) or 1.0
        grouped: dict[tuple[int, int], list] = {}
        for word in page.get_text("words", sort=True):
            x0, y0, x1, y1, text, block, line, word_index = word[:8]
            grouped.setdefault((int(block), int(line)), []).append(
                (float(x0), float(y0), float(x1), float(y1), str(text), int(word_index))
            )
        lines = []
        for words in grouped.values():
            words.sort(key=lambda item: item[5])
            text = " ".join(item[4] for item in words).strip()
            if not text:
                continue
            x0 = min(item[0] for item in words)
            y0 = min(item[1] for item in words)
            x1 = max(item[2] for item in words)
            y1 = max(item[3] for item in words)
            lines.append(
                {
                    "text": text,
                    "bbox": [
                        round(x0 / width, 6),
                        round(y0 / height, 6),
                        round(x1 / width, 6),
                        round(y1 / height, 6),
                    ],
                }
            )
        return {"page": page_number, "lines": _order_pdf_text_lines(lines)}
    finally:
        pdf.close()


def _order_pdf_text_lines(lines: list[dict]) -> list[dict]:
    if len(lines) < 2:
        return lines

    def geometry(item):
        x0, y0, x1, y1 = item["bbox"]
        return float(x0), float(y0), float(x1), float(y1)

    def is_full_width(item):
        x0, _y0, x1, _y1 = geometry(item)
        return (x1 - x0) >= 0.55 or (x0 <= 0.38 and x1 >= 0.62)

    def vertical_key(item):
        x0, y0, _x1, y1 = geometry(item)
        return ((y0 + y1) / 2, x0)

    full_width = sorted((item for item in lines if is_full_width(item)), key=vertical_key)
    column_lines = [item for item in lines if not is_full_width(item)]
    ordered = []
    lower_bound = float("-inf")
    for separator in full_width:
        separator_y = vertical_key(separator)[0]
        band = [
            item
            for item in column_lines
            if lower_bound <= vertical_key(item)[0] < separator_y
        ]
        ordered.extend(_order_pdf_column_band(band))
        ordered.append(separator)
        lower_bound = separator_y
    ordered.extend(
        _order_pdf_column_band(
            [item for item in column_lines if vertical_key(item)[0] >= lower_bound]
        )
    )
    return ordered


def _order_pdf_column_band(lines: list[dict]) -> list[dict]:
    def key(item):
        x0, y0, x1, y1 = (float(value) for value in item["bbox"])
        column = 0 if (x0 + x1) / 2 < 0.5 else 1
        return column, (y0 + y1) / 2, x0

    return sorted(lines, key=key)


def _api_note(payload: dict) -> dict:
    document = _select_document(payload)
    store = ReadingStateStore()
    kind = payload.get("kind") or "note"
    kwargs = {
        "section": _clean(payload.get("section")),
        "page": _int_or_none(payload.get("page")),
        "citation": _clean(payload.get("citation")),
    }
    if kind == "question":
        state = store.add_question(document, str(payload.get("text") or ""), **kwargs)
    elif kind == "verification":
        state = store.add_verification_item(document, str(payload.get("text") or ""), **kwargs)
    else:
        state = store.add_note(document, str(payload.get("text") or ""), **kwargs)
    return {"state": reading_state_summary(state)}


def _api_timeline_reorder(payload: dict) -> dict:
    document = _select_document(payload)
    state = ReadingStateStore().reorder_timeline(
        document,
        _string_list(payload.get("entry_ids")),
    )
    return {"state": reading_state_summary(state)}


def _api_timeline_delete(payload: dict) -> dict:
    document = _select_document(payload)
    state = ReadingStateStore().delete_timeline_entry(
        document,
        str(payload.get("entry_id") or ""),
    )
    return {"state": reading_state_summary(state)}


def _api_timeline_summary(payload: dict) -> dict:
    document = _select_document(payload)
    store = ReadingStateStore()
    state = store.get(document)
    entries = [
        item
        for item in state.timeline
        if item.kind != "timeline_summary" and (item.text.strip() or (item.answer or "").strip())
    ][-60:]
    personal_note = next(
        (item for item in state.notes if item.id == "personal-note" and item.text.strip()),
        None,
    )
    if personal_note and all(item.id != personal_note.id for item in entries):
        entries.insert(0, personal_note)
    if not entries:
        raise FinalsAgentError("当前还没有可总结的阅读记录。")
    source = [
        {
            "kind": item.kind,
            "title": item.text[:500],
            "content": (item.answer or item.text)[:6000],
            "page": item.page,
            "created_at": item.created_at,
        }
        for item in entries
    ]
    language = load_settings(validate=False).language
    response = build_chat_model().invoke(
        [
            {
                "role": "system",
                "content": (
                    "Summarize this paper-reading timeline into a compact recall note. Preserve the paper's core topic, "
                    "method, important evidence, unresolved questions, and the reader's own notes. Use short Markdown "
                    "headings and bullets. Do not invent facts and do not repeat every record."
                    f"\n\n{response_language_instruction(language)}"
                ),
            },
            {"role": "user", "content": json.dumps(source, ensure_ascii=False)},
        ]
    )
    summary = getattr(response, "content", response)
    if isinstance(summary, list):
        summary = "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in summary
        )
    summary = str(summary or "").strip()
    if not summary:
        raise FinalsAgentError("模型没有返回阅读总结。")
    updated = store.add_timeline_entry(
        document,
        "timeline_summary",
        _language_text(language, "阅读记录总结", "Reading timeline summary"),
        answer=summary,
        metadata={"source_count": len(entries)},
    )
    return {
        "summary": summary,
        "record": updated.timeline[-1].to_dict(),
        "state": reading_state_summary(updated),
    }


def _api_flashcard(payload: dict) -> dict:
    document = _select_document(payload)
    state = ReadingStateStore().add_flashcard(
        document,
        question=str(payload.get("question") or ""),
        answer=str(payload.get("answer") or ""),
        section=_clean(payload.get("section")),
        page=_int_or_none(payload.get("page")),
        citation=_clean(payload.get("citation")),
    )
    return {"state": reading_state_summary(state)}


def _api_chat(payload: dict) -> dict:
    result = _run_chat_agent(payload)
    reading_state = _save_chat_reading_state(payload, result.answer)
    return {"answer": result.answer, "metadata": result.metadata, "reading_state": reading_state}


def _api_chat_stream(payload: dict):
    language = load_settings(validate=False).language
    events: Queue[dict | object] = Queue()
    sentinel = object()

    def worker() -> None:
        try:
            result = _run_chat_agent(
                payload,
                token_sink=lambda text: events.put({"type": "delta", "text": text}),
            )
            reading_state = _save_chat_reading_state(payload, result.answer)
            events.put(
                {
                    "type": "done",
                    "answer": result.answer,
                    "metadata": result.metadata,
                    "reading_state": reading_state,
                }
            )
        except Exception as exc:
            events.put({"type": "error", "message": f"{exc.__class__.__name__}: {exc}"})
        finally:
            events.put(sentinel)

    yield {
        "type": "status",
        "message": _language_text(
            language,
            "正在理解问题并检索原文证据...",
            "Understanding the question and retrieving source evidence...",
        ),
    }
    Thread(target=worker, daemon=True).start()
    while True:
        event = events.get()
        if event is sentinel:
            break
        yield event


def _run_chat_agent(payload: dict, token_sink=None):
    settings = load_settings(validate=False)
    runtime = (
        AgentRuntime.from_settings(settings.runtime)
        .with_field(_clean(payload.get("field")))
        .with_target(document_id=_clean(payload.get("document_id")), title=_clean(payload.get("title")))
    )
    conversation_id = _clean(payload.get("conversation_id"))
    result = run_agent(
        AgentRequest(
            question=str(payload.get("question") or ""),
            course_context=runtime.course_context,
            conversation_id=conversation_id,
        ),
        runtime=runtime,
        memory_store=JsonMemoryStore() if conversation_id else None,
        run_recorder=JsonRunRecorder(),
        token_sink=token_sink,
    )
    return result


def _save_chat_reading_state(payload: dict, answer: str) -> dict | None:
    reading_state = None
    document_id = _clean(payload.get("document_id"))
    if document_id:
        document = StudyRepository().get_document(document_id)
        store = ReadingStateStore()
        current = store.get(document)
        digest = _append_reading_digest(
            current.review_summary,
            question=str(payload.get("question") or ""),
            answer=answer,
        )
        store.update_progress(document, review_summary=digest)
        timeline_state = store.add_timeline_entry(
            document,
            "question",
            str(payload.get("question") or ""),
            answer=answer,
        )
        reading_state = reading_state_summary(timeline_state)
    return reading_state


def _api_artifact_explain(payload: dict) -> dict:
    repository = StudyRepository()
    document = repository.get_document(str(payload.get("document_id") or ""))
    artifact_id = str(payload.get("artifact_id") or "")
    artifact = _find_display_artifact(repository, document, artifact_id)
    if artifact is None:
        raise FinalsAgentError("图表不存在。")
    interpretation = build_vision_artifact_interpreter(document).interpret(artifact)
    existing = {
        item.artifact_id: item
        for item in repository.read_artifact_interpretations(document)
    }
    existing[artifact.artifact_id] = interpretation
    repository.write_artifact_interpretations(document, list(existing.values()))
    return {
        "artifact": artifact.to_dict(),
        "interpretation": interpretation.to_dict(),
    }


def _api_artifact_explain_stream(payload: dict):
    repository = StudyRepository()
    document = repository.get_document(str(payload.get("document_id") or ""))
    artifact_id = str(payload.get("artifact_id") or "")
    artifact = _find_display_artifact(repository, document, artifact_id)
    if artifact is None:
        raise FinalsAgentError("图表不存在。")
    language = load_settings(validate=False).language
    yield {
        "type": "status",
        "message": _language_text(language, "正在读取图表并生成解释...", "Reading the artifact and generating an explanation..."),
    }
    interpreter = build_vision_artifact_interpreter(document)
    stream = interpreter.interpret_stream(artifact)
    while True:
        try:
            text = next(stream)
        except StopIteration as stop:
            interpretation = stop.value
            break
        if text:
            yield {"type": "delta", "text": text}
    existing = {
        item.artifact_id: item
        for item in repository.read_artifact_interpretations(document)
    }
    existing[artifact.artifact_id] = interpretation
    repository.write_artifact_interpretations(document, list(existing.values()))
    yield {
        "type": "done",
        "artifact": artifact.to_dict(),
        "interpretation": interpretation.to_dict(),
    }


def _api_artifact_note(payload: dict) -> dict:
    repository = StudyRepository()
    document = repository.get_document(str(payload.get("document_id") or ""))
    artifact_id = str(payload.get("artifact_id") or "")
    artifact = _find_display_artifact(repository, document, artifact_id)
    if artifact is None:
        raise FinalsAgentError("图表不存在。")
    interpretation = next(
        (
            item
            for item in repository.read_artifact_interpretations(document)
            if item.artifact_id == artifact_id
        ),
        None,
    )
    if interpretation is None or not interpretation.interpretation.strip():
        raise FinalsAgentError("请先生成图表解释。")
    store = ReadingStateStore()
    current = store.get(document)
    duplicate = next(
        (
            item
            for item in current.timeline
            if item.kind == "artifact_explanation"
            and (item.metadata or {}).get("artifact_id") == artifact_id
            and (item.answer or "").strip() == interpretation.interpretation.strip()
        ),
        None,
    )
    if duplicate is not None:
        return {
            "state": reading_state_summary(current),
            "record": duplicate.to_dict(),
            "added": False,
        }
    state = store.add_timeline_entry(
        document,
        "artifact_explanation",
        artifact.caption or artifact.text or artifact.kind,
        answer=interpretation.interpretation,
        page=artifact.page,
        metadata={
            "artifact_id": artifact.artifact_id,
            "artifact_kind": artifact.kind,
            "method": interpretation.method,
            "manual": True,
        },
    )
    return {
        "state": reading_state_summary(state),
        "record": state.timeline[-1].to_dict(),
        "added": True,
    }


def _api_artifact_region(payload: dict) -> dict:
    repository = StudyRepository()
    document = repository.get_document(str(payload.get("document_id") or ""))
    artifact_id = str(payload.get("artifact_id") or "")
    artifact = _find_display_artifact(repository, document, artifact_id)
    if artifact is None:
        raise FinalsAgentError("图表不存在。")
    raw_bbox = payload.get("bbox")
    if not isinstance(raw_bbox, list) or len(raw_bbox) != 4:
        raise FinalsAgentError("裁剪区域格式错误。")
    region = ArtifactRegionStore(repository).set_manual(
        document,
        artifact,
        tuple(float(value) for value in raw_bbox),
    )
    ArtifactManifestStore().invalidate(document)
    return {"region": region.to_dict()}


def _api_save_settings(payload: dict) -> dict:
    text = payload.get("text") if isinstance(payload.get("text"), dict) else payload
    vision = payload.get("vision") if isinstance(payload.get("vision"), dict) else {}
    current = load_settings(validate=False)
    provider = _env_safe(text.get("provider") or "custom").lower()
    if provider not in {"custom", "openai", "deepseek", "local"}:
        raise FinalsAgentError("不支持的模型服务类型。")
    model = _env_safe(text.get("model"))
    base_url = _env_safe(text.get("base_url"))
    api_key = _env_safe(text.get("api_key"))
    if not model:
        raise FinalsAgentError("模型名称不能为空。")
    if provider in {"custom", "local"} and not base_url:
        raise FinalsAgentError("自定义服务必须填写 Base URL。")
    api_key = _resolved_text_api_key(
        provider=provider,
        base_url=base_url,
        supplied=api_key,
        current=current,
    )
    values = {
        "LLM_PROVIDER": provider,
        "LLM_MODEL": model,
        "LLM_BASE_URL": base_url,
        "LLM_API_KEY": api_key,
    }
    if provider == "openai":
        values["OPENAI_API_KEY"] = api_key
    elif provider == "deepseek":
        values["DEEPSEEK_API_KEY"] = api_key
    vision_provider = _env_safe(vision.get("provider") or "disabled").lower()
    if vision_provider not in {"disabled", "openai_compatible"}:
        raise FinalsAgentError("Unsupported vision model provider.")
    vision_model = _env_safe(vision.get("model"))
    vision_base_url = _env_safe(vision.get("base_url"))
    vision_api_key = _env_safe(vision.get("api_key"))
    language = normalize_app_language(payload.get("language"))
    if language not in {"zh", "en"}:
        raise FinalsAgentError("Unsupported interface language.")
    values["APP_LANGUAGE"] = language
    if vision_provider == "openai_compatible":
        if not vision_model:
            raise FinalsAgentError("Vision model name cannot be empty.")
        if not vision_base_url:
            raise FinalsAgentError("Vision model Base URL cannot be empty.")
        same_vision_endpoint = (
            current.vision.provider == "openai_compatible"
            and _normalized_endpoint(current.vision.base_url) == _normalized_endpoint(vision_base_url)
        )
        if not vision_api_key and same_vision_endpoint and _real_api_key(current.vision.api_key):
            vision_api_key = str(current.vision.api_key)
        if not vision_api_key:
            raise FinalsAgentError("Vision model API Key cannot be empty.")
        values.update(
            {
                "VISION_PROVIDER": "openai_compatible",
                "VISION_MODEL": vision_model,
                "VISION_BASE_URL": vision_base_url,
            }
        )
        values["VISION_API_KEY"] = vision_api_key
    else:
        values["VISION_PROVIDER"] = "disabled"
    _write_env_values(values)
    for key, value in values.items():
        os.environ[key] = value
    saved = load_settings(validate=False)
    return {
        "saved": True,
        "text": {
            "provider": saved.model.provider,
            "model": saved.model.model,
            "base_url": saved.model.base_url or "",
            "api_key_configured": _real_api_key(saved.model.api_key),
        },
        "vision": {
            "provider": saved.vision.provider,
            "model": saved.vision.model or "",
            "base_url": saved.vision.base_url or "",
            "api_key_configured": _real_api_key(saved.vision.api_key),
        },
        "language": saved.language,
    }


def _language_text(language: str, zh: str, en: str) -> str:
    return en if language == "en" else zh


def _write_env_values(values: dict[str, str], env_path: Path | None = None) -> None:
    env_path = env_path or PROJECT_ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = dict(values)
    updated = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            updated.append(f"{key}={remaining.pop(key)}")
        else:
            updated.append(line)
    if remaining and updated and updated[-1].strip():
        updated.append("")
    updated.extend(f"{key}={value}" for key, value in remaining.items())
    temp_path = env_path.with_name(f".{env_path.name}.tmp")
    temp_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    temp_path.replace(env_path)


def _env_safe(value) -> str:
    return str(value or "").replace("\r", "").replace("\n", "").strip()


def _resolved_text_api_key(*, provider: str, base_url: str, supplied: str, current) -> str:
    if supplied:
        return supplied
    if provider == "local" or (provider == "custom" and _is_local_endpoint(base_url)):
        return "not-needed"
    same_endpoint = (
        current.model.provider == provider
        and _normalized_endpoint(current.model.base_url) == _normalized_endpoint(base_url)
    )
    if same_endpoint and _real_api_key(current.model.api_key):
        return str(current.model.api_key)
    environment_key = {
        "openai": os.environ.get("OPENAI_API_KEY"),
        "deepseek": os.environ.get("DEEPSEEK_API_KEY"),
    }.get(provider)
    if _real_api_key(environment_key):
        return str(environment_key)
    raise FinalsAgentError("API Key cannot be empty when configuring a remote text model.")


def _normalized_endpoint(value: str | None) -> str:
    return str(value or "").strip().rstrip("/").lower()


def _is_local_endpoint(value: str | None) -> bool:
    hostname = urlparse(str(value or "")).hostname
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _real_api_key(value: str | None) -> bool:
    return bool(value and value != "not-needed")


def _api_key_hint(value: str | None, language: str = "zh") -> str:
    if not _real_api_key(value):
        return "Not configured" if language == "en" else "未配置"
    suffix = value[-4:] if len(value) >= 4 else value
    if language == "en":
        return f"Configured ····{suffix}; leave blank to keep it"
    return f"已配置 ····{suffix}，留空则不修改"


def _append_reading_digest(
    current: str | None,
    *,
    question: str,
    answer: str,
    max_chars: int = 1200,
) -> str:
    compact_question = " ".join(question.split())[:80]
    compact_answer = _digest_sentence(answer, max_chars=120)
    entry = f"• {compact_question}：{compact_answer}"
    previous = [
        line
        for line in _compact_reading_digest(current).splitlines()
        if line
    ]
    digest = "\n".join([*previous[-5:], entry])
    if len(digest) > max_chars:
        digest = digest[-max_chars:]
    return digest


def _compact_reading_digest(current: str | None, limit: int = 5) -> str:
    lines = [line.strip() for line in (current or "").splitlines() if line.strip()]
    entries = []
    pending_question = ""
    for line in lines:
        if line.startswith("• "):
            body = line[2:].strip()
            question, separator, answer = body.partition("：")
            if separator:
                entries.append(
                    f"• {' '.join(question.split())[:80]}：{_digest_sentence(answer, max_chars=120)}"
                )
            else:
                entries.append(f"• {_digest_sentence(body, max_chars=160)}")
            pending_question = ""
            continue
        if line.startswith("问："):
            pending_question = " ".join(line[2:].split())[:80]
            continue
        if line.startswith("答："):
            answer = _digest_sentence(line[2:], max_chars=120)
            entries.append(f"• {pending_question or '阅读记录'}：{answer}")
            pending_question = ""
            continue
        if not entries and not pending_question:
            entries.append(f"• {_digest_sentence(line, max_chars=160)}")
    return "\n".join(entries[-limit:])


def _digest_sentence(answer: str, max_chars: int) -> str:
    cleaned = re.sub(r"\[[^\[\]\n]+\|[^\[\]\n]+\]", "", answer)
    cleaned = re.sub(r"[#*_`]+", "", cleaned)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return "暂无可用结论"
    sentences = [
        sentence.strip()
        for sentence in re.findall(r"[^。！？.!?]+(?:[。！？.!?]+|$)", cleaned)
        if sentence.strip()
    ]
    preambles = (
        "好的", "当然", "下面", "接下来", "结合本地", "结合论文",
        "我来", "让我们", "根据你的问题", "if you want",
    )
    informative = (
        "是", "指", "通过", "采用", "提出", "表明", "核心", "意味着",
        " is ", " are ", " uses ", " proposes ", " shows ", " means ",
    )

    candidates = []
    for sentence in sentences:
        lowered = f" {sentence.casefold()} "
        if any(marker in lowered for marker in preambles):
            continue
        if sentence.endswith(("？", "?")) or sentence.startswith(("如果", "需要进一步", "欢迎")):
            continue
        if "|" in sentence or sentence.count("---") > 0:
            continue
        candidates.append((sentence, lowered))
    selected = next(
        (sentence for sentence, lowered in candidates if any(marker in lowered for marker in informative)),
        candidates[0][0] if candidates else (sentences[0] if sentences else cleaned),
    )
    return selected[:max_chars].rstrip() + ("…" if len(selected) > max_chars else "")


def _select_document(payload: dict):
    from finals_agent.data.selection import select_document

    return select_document(
        StudyRepository(),
        document_id=_clean(payload.get("document_id")),
        title=_clean(payload.get("title")),
        field=_clean(payload.get("field")),
        document_type=None,
    )


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(
            text
            for item in value
            if (text := str(item or "").strip())
        )
    )


def _attachment_content_type(suffix: str) -> str:
    return {
        ".md": "text/markdown; charset=utf-8",
        ".markdown": "text/markdown; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix.lower(), "application/octet-stream")


def _safe_relative_source(value: str) -> str:
    normalized = str(value or "").replace("\\", "/").strip().lstrip("/")
    parts = [part for part in normalized.split("/") if part not in {"", ".", ".."}]
    return "/".join(parts) or "untitled"


def _code_language(suffix: str) -> str:
    return {
        ".py": "python", ".ipynb": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".c": "c",
        ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp", ".go": "go",
        ".rs": "rust", ".rb": "ruby", ".php": "php", ".swift": "swift",
        ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala", ".sh": "bash",
        ".ps1": "powershell", ".sql": "sql", ".html": "html", ".css": "css",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "ini",
        ".xml": "xml", ".md": "markdown", ".markdown": "markdown", ".rst": "plaintext",
        ".txt": "plaintext",
    }.get(suffix.lower(), "plaintext")


def _notebook_cells(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalsAgentError("Jupyter Notebook 文件无法解析。") from exc
    language = (
        payload.get("metadata", {}).get("kernelspec", {}).get("language")
        or payload.get("metadata", {}).get("language_info", {}).get("name")
        or "python"
    )
    cells = []
    for index, cell in enumerate(payload.get("cells") or [], start=1):
        if not isinstance(cell, dict):
            continue
        cell_type = str(cell.get("cell_type") or "raw")
        source = cell.get("source") or []
        content = "".join(source) if isinstance(source, list) else str(source)
        outputs = []
        if cell_type == "code":
            for output in cell.get("outputs") or []:
                if not isinstance(output, dict):
                    continue
                text = output.get("text")
                if text is None:
                    text = (output.get("data") or {}).get("text/plain")
                if isinstance(text, list):
                    text = "".join(text)
                if text:
                    outputs.append(str(text))
        cells.append(
            {
                "index": index,
                "type": cell_type,
                "content": content,
                "language": language if cell_type == "code" else "markdown",
                "outputs": outputs,
                "execution_count": cell.get("execution_count"),
            }
        )
    return cells


def _bool_or_none(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if str(value).strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if str(value).strip().lower() in {"0", "false", "no", "off"}:
        return False
    raise FinalsAgentError("Boolean value is invalid.")


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value) -> int | None:
    if value in (None, ""):
        return None
    return _int(value, default=0)


def _first(values: list[str] | None) -> str | None:
    return values[0] if values else None


LEGACY_APP_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Paper Agent</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f8;
      --panel: #ffffff;
      --line: #d9dee3;
      --text: #1f2933;
      --muted: #66717d;
      --accent: #256c6a;
      --accent-2: #4f6f9f;
      --warn: #9a5b13;
      --danger: #a53c3c;
      --good: #2f7d50;
      font-family: Inter, "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-size: 14px;
      letter-spacing: 0;
    }
    .app {
      display: grid;
      grid-template-columns: minmax(280px, 340px) 1fr;
      min-height: 100vh;
    }
    aside {
      background: #eef1f4;
      border-right: 1px solid var(--line);
      padding: 14px;
      display: grid;
      grid-template-rows: auto auto 1fr;
      gap: 12px;
      min-width: 0;
    }
    main {
      padding: 14px 18px 22px;
      min-width: 0;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
    }
    h1 { font-size: 18px; margin: 0; font-weight: 650; }
    h2 { font-size: 15px; margin: 0 0 8px; font-weight: 650; }
    h3 { font-size: 13px; margin: 12px 0 6px; color: var(--muted); font-weight: 650; }
    .row { display: flex; gap: 8px; align-items: center; }
    .grid { display: grid; gap: 10px; }
    .two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 8px 9px;
      font: inherit;
      min-width: 0;
    }
    textarea { resize: vertical; min-height: 82px; }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 8px 10px;
      font: inherit;
      cursor: pointer;
      white-space: nowrap;
    }
    button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    button.danger { color: var(--danger); }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; }
    .tabs {
      display: flex;
      border-bottom: 1px solid var(--line);
      gap: 2px;
      margin-bottom: 12px;
      overflow-x: auto;
    }
    .tab {
      border: 0;
      border-bottom: 2px solid transparent;
      border-radius: 0;
      background: transparent;
      padding: 9px 12px;
    }
    .tab.active { border-bottom-color: var(--accent); color: var(--accent); font-weight: 650; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }
    .doc-list {
      overflow: auto;
      min-height: 200px;
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
    }
    .doc {
      padding: 10px;
      border-bottom: 1px solid #edf0f2;
      cursor: pointer;
    }
    .doc:last-child { border-bottom: 0; }
    .doc.active { background: #e7f1ef; }
    .doc-title { font-weight: 650; overflow-wrap: anywhere; }
    .meta { color: var(--muted); font-size: 12px; margin-top: 3px; overflow-wrap: anywhere; }
    .result {
      border-top: 1px solid #edf0f2;
      padding: 10px 0;
    }
    .result:first-child { border-top: 0; padding-top: 0; }
    .pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #f8fafb;
      border: 1px solid #e3e8ec;
      border-radius: 6px;
      padding: 10px;
      max-height: 460px;
      overflow: auto;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      color: var(--muted);
      background: #fff;
      margin: 2px 4px 2px 0;
    }
    .status { color: var(--muted); min-height: 20px; }
    .status.error { color: var(--danger); }
    .status.ok { color: var(--good); }
    .split {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, 430px);
      gap: 12px;
    }
    .hidden { display: none; }
    @media (max-width: 900px) {
      .app { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .split, .two, .three { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="row">
        <h1>Paper Agent</h1>
        <button id="refreshDocs" title="刷新论文列表">刷新</button>
      </div>
      <div class="grid">
        <input id="fieldFilter" placeholder="field" />
        <div class="panel">
          <h2>Ingest</h2>
          <div class="grid">
            <input id="ingestPath" placeholder="C:\path\paper.pdf" />
            <div class="two grid">
              <select id="ingestType">
                <option value="paper">paper</option>
                <option value="related_work">related_work</option>
                <option value="supplement">supplement</option>
                <option value="note">note</option>
              </select>
              <input id="ingestField" placeholder="field" />
            </div>
            <input id="ingestTitle" placeholder="title" />
            <button class="primary" id="ingestBtn">Ingest</button>
          </div>
        </div>
      </div>
      <div class="doc-list" id="docList"></div>
    </aside>
    <main>
      <header>
        <div>
          <h1 id="selectedTitle">未选择论文</h1>
          <div class="meta" id="selectedMeta"></div>
        </div>
        <div class="toolbar">
          <button id="removeBtn" class="danger">Remove</button>
        </div>
      </header>
      <div class="tabs" id="tabs">
        <button class="tab active" data-tab="search">Search</button>
        <button class="tab" data-tab="read">Read</button>
        <button class="tab" data-tab="explain">Explain</button>
        <button class="tab" data-tab="notes">Notes</button>
        <button class="tab" data-tab="chat">Chat</button>
        <button class="tab" data-tab="runs">Runs</button>
      </div>
      <div class="status" id="status"></div>

      <section id="tab-search" class="tabPanel">
        <div class="panel grid">
          <div class="row">
            <input id="searchQuery" placeholder="query" />
            <button class="primary" id="searchBtn">Search</button>
          </div>
          <div id="searchResults"></div>
        </div>
      </section>

      <section id="tab-read" class="tabPanel hidden">
        <div class="split">
          <div class="panel">
            <div class="toolbar">
              <button class="primary" id="readBtn">Read</button>
              <button id="compareBtn">Compare</button>
            </div>
            <div class="grid" style="margin-top:10px">
              <input id="compareTopic" placeholder="compare topic" />
              <input id="relatedLimit" type="number" min="0" value="0" />
            </div>
            <div id="readOutput" class="pre" style="margin-top:10px"></div>
          </div>
          <div class="panel">
            <h2>Coverage</h2>
            <div id="coverage"></div>
            <h3>Section Passes</h3>
            <div id="sectionPasses"></div>
          </div>
        </div>
      </section>

      <section id="tab-explain" class="tabPanel hidden">
        <div class="panel grid">
          <div class="row">
            <input id="explainTarget" placeholder="Figure 2 / Method / concept" />
            <button class="primary" id="explainBtn">Explain</button>
          </div>
          <div id="explainOutput" class="pre"></div>
        </div>
      </section>

      <section id="tab-notes" class="tabPanel hidden">
        <div class="split">
          <div class="panel grid">
            <div class="three grid">
              <select id="progressStatus">
                <option value="">status</option>
                <option value="not_started">not_started</option>
                <option value="reading">reading</option>
                <option value="reviewing">reviewing</option>
                <option value="done">done</option>
              </select>
              <input id="progressSection" placeholder="section" />
              <input id="progressPercent" type="number" min="0" max="100" placeholder="%" />
            </div>
            <textarea id="progressSummary" placeholder="review summary"></textarea>
            <button class="primary" id="saveProgressBtn">Save Progress</button>
            <h2>New Item</h2>
            <select id="noteKind">
              <option value="note">note</option>
              <option value="question">question</option>
              <option value="verification">verification</option>
            </select>
            <textarea id="noteText" placeholder="text"></textarea>
            <button id="addNoteBtn">Add</button>
            <h2>Flashcard</h2>
            <input id="flashQuestion" placeholder="question" />
            <textarea id="flashAnswer" placeholder="answer"></textarea>
            <button id="addFlashBtn">Add Flashcard</button>
          </div>
          <div class="panel">
            <h2>Reading State</h2>
            <button id="loadStateBtn">Load</button>
            <div id="stateOutput" style="margin-top:10px"></div>
          </div>
        </div>
      </section>

      <section id="tab-chat" class="tabPanel hidden">
        <div class="panel grid">
          <div class="two grid">
            <input id="conversationId" placeholder="conversation id" />
            <input id="chatField" placeholder="field override" />
          </div>
          <textarea id="chatQuestion" placeholder="question"></textarea>
          <button class="primary" id="chatBtn">Send</button>
          <div id="chatOutput" class="pre"></div>
        </div>
      </section>

      <section id="tab-runs" class="tabPanel hidden">
        <div class="panel grid">
          <div class="row">
            <input id="runsLimit" type="number" min="1" value="10" />
            <button class="primary" id="runsBtn">Load Runs</button>
          </div>
          <div id="runsOutput"></div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const state = { docs: [], selected: null };
    const $ = id => document.getElementById(id);
    const api = async (path, payload) => {
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {})
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'request failed');
      return data;
    };
    const get = async path => {
      const res = await fetch(path);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'request failed');
      return data;
    };
    const setStatus = (text, kind='') => {
      $('status').textContent = text || '';
      $('status').className = 'status ' + kind;
    };
    const selectedPayload = () => state.selected ? {
      document_id: state.selected.id,
      title: state.selected.title,
      field: state.selected.field
    } : {};
    const requireDoc = () => {
      if (!state.selected) throw new Error('select a paper first');
      return selectedPayload();
    };
    const renderDocs = () => {
      $('docList').innerHTML = state.docs.map(doc => `
        <div class="doc ${state.selected && state.selected.id === doc.id ? 'active' : ''}" data-id="${doc.id}">
          <div class="doc-title">${escapeHtml(doc.title)}</div>
          <div class="meta">${escapeHtml(doc.field || '')} · ${escapeHtml(doc.type || doc.document_type || '')} · ${escapeHtml(doc.id)}</div>
        </div>
      `).join('');
      document.querySelectorAll('.doc').forEach(el => {
        el.onclick = () => {
          state.selected = state.docs.find(doc => doc.id === el.dataset.id);
          renderSelected();
          renderDocs();
        };
      });
    };
    const renderSelected = () => {
      if (!state.selected) {
        $('selectedTitle').textContent = '未选择论文';
        $('selectedMeta').textContent = '';
        return;
      }
      $('selectedTitle').textContent = state.selected.title;
      $('selectedMeta').textContent = `${state.selected.field || ''} · ${state.selected.id} · ${state.selected.path || ''}`;
      $('chatField').value = state.selected.field || '';
    };
    const loadDocs = async () => {
      setStatus('loading documents...');
      const field = $('fieldFilter').value.trim();
      const data = await get('/api/documents' + (field ? `?field=${encodeURIComponent(field)}` : ''));
      state.docs = data.documents || [];
      if (state.selected) {
        state.selected = state.docs.find(doc => doc.id === state.selected.id) || null;
      }
      renderDocs();
      renderSelected();
      setStatus(`${state.docs.length} documents`, 'ok');
    };
    const renderResults = (items, target) => {
      $(target).innerHTML = (items || []).map(item => `
        <div class="result">
          <div><strong>${escapeHtml(item.title || '')}</strong> <span class="badge">${Number(item.score || 0).toFixed(3)}</span></div>
          <div class="meta">${escapeHtml(item.citation || '')}</div>
          <div>${escapeHtml(item.snippet || '')}</div>
        </div>
      `).join('') || '<div class="meta">No results</div>';
    };
    const renderRead = data => {
      const payload = data.data || data;
      $('readOutput').textContent = JSON.stringify({
        reading_order: payload.reading_order,
        evidence: (payload.evidence || []).slice(0, 8),
        next_actions: payload.next_actions,
        related_papers: payload.related_papers
      }, null, 2);
      const coverage = payload.coverage || {};
      $('coverage').innerHTML = `
        <span class="badge">covered ${coverage.covered_count || 0}/${coverage.total_count || 0}</span>
        <span class="badge">ratio ${coverage.coverage_ratio || 0}</span>
        <div class="meta">missing: ${escapeHtml((coverage.missing_roles || []).join(', ') || '-')}</div>
      `;
      $('sectionPasses').innerHTML = (payload.section_passes || []).map(pass => `
        <div class="result">
          <div><strong>${escapeHtml(pass.role)}</strong> <span class="badge">${escapeHtml(pass.status)}</span></div>
          <div class="meta">${escapeHtml(pass.purpose || '')}</div>
          <div class="meta">${(pass.evidence || []).length} evidence item(s)</div>
        </div>
      `).join('');
    };
    const renderState = stateData => {
      const s = stateData.state || stateData;
      $('stateOutput').innerHTML = `
        <div><span class="badge">${escapeHtml(s.status)}</span><span class="badge">${s.progress_percent}%</span></div>
        <div class="meta">section: ${escapeHtml(s.current_section || '-')}</div>
        <h3>Open questions</h3>${renderItems(s.open_questions)}
        <h3>Verification</h3>${renderItems(s.open_verification_items)}
        <h3>Notes</h3>${renderItems(s.recent_notes)}
        <h3>Flashcards</h3>${renderItems(s.recent_flashcards, true)}
      `;
    };
    const renderItems = (items, answer=false) => (items || []).map(item => `
      <div class="result">
        <div><strong>${escapeHtml(item.text || '')}</strong></div>
        ${answer ? `<div>${escapeHtml(item.answer || '')}</div>` : ''}
        <div class="meta">${escapeHtml(item.id || '')} ${escapeHtml(item.citation || '')}</div>
      </div>
    `).join('') || '<div class="meta">None</div>';
    const escapeHtml = value => String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));

    $('tabs').onclick = event => {
      const btn = event.target.closest('.tab');
      if (!btn) return;
      document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.tabPanel').forEach(panel => panel.classList.add('hidden'));
      $('tab-' + btn.dataset.tab).classList.remove('hidden');
    };
    $('refreshDocs').onclick = () => loadDocs().catch(err => setStatus(err.message, 'error'));
    $('fieldFilter').onkeydown = event => { if (event.key === 'Enter') loadDocs().catch(err => setStatus(err.message, 'error')); };
    $('ingestBtn').onclick = async () => {
      try {
        setStatus('ingesting...');
        await api('/api/ingest', {
          path: $('ingestPath').value,
          document_type: $('ingestType').value,
          field: $('ingestField').value,
          title: $('ingestTitle').value
        });
        await loadDocs();
      } catch (err) { setStatus(err.message, 'error'); }
    };
    $('removeBtn').onclick = async () => {
      try {
        requireDoc();
        if (!confirm('Remove selected paper?')) return;
        await api('/api/remove', { document_id: state.selected.id });
        state.selected = null;
        await loadDocs();
      } catch (err) { setStatus(err.message, 'error'); }
    };
    $('searchBtn').onclick = async () => {
      try {
        setStatus('searching...');
        const payload = { query: $('searchQuery').value, limit: 8 };
        if (state.selected) payload.document_id = state.selected.id;
        const data = await api('/api/search', payload);
        renderResults(data.results, 'searchResults');
        setStatus(`${(data.results || []).length} results`, 'ok');
      } catch (err) { setStatus(err.message, 'error'); }
    };
    $('readBtn').onclick = async () => {
      try {
        setStatus('reading...');
        const data = await api('/api/read', { ...requireDoc(), related_limit: Number($('relatedLimit').value || 0) });
        renderRead(data);
        setStatus('read workflow complete', 'ok');
      } catch (err) { setStatus(err.message, 'error'); }
    };
    $('compareBtn').onclick = async () => {
      try {
        setStatus('comparing...');
        const data = await api('/api/compare', { ...requireDoc(), topic: $('compareTopic').value || state.selected.title });
        $('readOutput').textContent = JSON.stringify(data.data, null, 2);
        setStatus('comparison complete', 'ok');
      } catch (err) { setStatus(err.message, 'error'); }
    };
    $('explainBtn').onclick = async () => {
      try {
        setStatus('explaining...');
        const data = await api('/api/explain', { ...requireDoc(), target: $('explainTarget').value });
        $('explainOutput').textContent = JSON.stringify(data.data, null, 2);
        setStatus('explain complete', 'ok');
      } catch (err) { setStatus(err.message, 'error'); }
    };
    $('loadStateBtn').onclick = async () => {
      try { renderState(await api('/api/state', requireDoc())); setStatus('state loaded', 'ok'); }
      catch (err) { setStatus(err.message, 'error'); }
    };
    $('saveProgressBtn').onclick = async () => {
      try {
        const payload = { ...requireDoc(), status: $('progressStatus').value, current_section: $('progressSection').value, progress_percent: $('progressPercent').value, review_summary: $('progressSummary').value };
        renderState(await api('/api/progress', payload));
        setStatus('progress saved', 'ok');
      } catch (err) { setStatus(err.message, 'error'); }
    };
    $('addNoteBtn').onclick = async () => {
      try {
        renderState(await api('/api/note', { ...requireDoc(), kind: $('noteKind').value, text: $('noteText').value }));
        $('noteText').value = '';
        setStatus('item added', 'ok');
      } catch (err) { setStatus(err.message, 'error'); }
    };
    $('addFlashBtn').onclick = async () => {
      try {
        renderState(await api('/api/flashcard', { ...requireDoc(), question: $('flashQuestion').value, answer: $('flashAnswer').value }));
        $('flashQuestion').value = '';
        $('flashAnswer').value = '';
        setStatus('flashcard added', 'ok');
      } catch (err) { setStatus(err.message, 'error'); }
    };
    $('chatBtn').onclick = async () => {
      try {
        setStatus('agent running...');
        const payload = state.selected ? selectedPayload() : {};
        payload.question = $('chatQuestion').value;
        payload.conversation_id = $('conversationId').value;
        payload.field = $('chatField').value || payload.field;
        const data = await api('/api/chat', payload);
        $('chatOutput').textContent = data.answer;
        setStatus('answer ready', 'ok');
      } catch (err) { setStatus(err.message, 'error'); }
    };
    $('runsBtn').onclick = async () => {
      try {
        const data = await get('/api/runs?limit=' + encodeURIComponent($('runsLimit').value || 10));
        $('runsOutput').innerHTML = (data.runs || []).map(run => `
          <div class="result">
            <div><strong>${escapeHtml(run.run_id)}</strong> <span class="badge">${escapeHtml(run.status)}</span> <span class="badge">${escapeHtml(run.task_type || '-')}</span></div>
            <div>${escapeHtml(run.question || '')}</div>
            <div class="meta">${escapeHtml(String(run.duration_ms || '-'))} ms</div>
          </div>
        `).join('') || '<div class="meta">No runs</div>';
        setStatus('runs loaded', 'ok');
      } catch (err) { setStatus(err.message, 'error'); }
    };
    loadDocs().catch(err => setStatus(err.message, 'error'));
  </script>
</body>
</html>"""
