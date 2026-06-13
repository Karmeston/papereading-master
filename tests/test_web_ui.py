from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
from types import SimpleNamespace
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from finals_agent.app import web
from finals_agent.core.schemas import DocumentChunk, DocumentType, SearchResult
from finals_agent.core.schemas import ArtifactInterpretation, PaperArtifact
from finals_agent.persistence.reading_state import ReadingStateStore
from finals_agent.persistence.research_tasks import ResearchTaskStore
from finals_agent.persistence.storage import JsonFileStorage
from finals_agent.data.artifact_locator import ArtifactRegion
from finals_agent.data.repository import StudyRepository


@pytest.fixture(autouse=True)
def isolated_reading_state(monkeypatch, tmp_path):
    storage = JsonFileStorage(tmp_path / "reading-state.json")
    monkeypatch.setattr(web, "ReadingStateStore", lambda: ReadingStateStore(storage))
    research_storage = JsonFileStorage(tmp_path / "research-tasks.json")
    research_store = ResearchTaskStore(research_storage)
    monkeypatch.setattr(web, "ResearchTaskStore", lambda: research_store)


@dataclass(frozen=True)
class FakeDocument:
    id: str = "doc-1"
    title: str = "Target Paper"
    field: str = "nlp"
    path: Path = Path("paper.md")
    document_type: DocumentType = DocumentType.PAPER
    focus: str | None = None
    source: str | None = None
    tags: tuple[str, ...] = ()
    pinned: bool = False
    archived: bool = False
    category: str | None = None

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "field": self.field,
            "document_type": "paper",
            "path": str(self.path),
            "pinned": self.pinned,
            "archived": self.archived,
            "category": self.category,
        }


class FakeRepository:
    organized_document = None

    def list_documents(self, field=None):
        if field and field != "nlp":
            return []
        return [FakeDocument()]

    def search(self, query, field=None, document_id=None, document_type=None, focus=None, limit=8):
        return [
            SearchResult(
                document_id="doc-1",
                title="Target Paper",
                document_type=DocumentType.PAPER,
                course="nlp",
                path=Path("paper.md"),
                snippet=f"snippet for {query}",
                score=1.0,
                chunk_id="doc-1-0",
            )
        ]

    def get_document(self, document_id):
        if document_id != "doc-1":
            raise ValueError("missing document")
        return FakeDocument()

    def update_document_organization(
        self,
        document_id,
        *,
        pinned=None,
        archived=None,
        category=None,
        update_category=False,
    ):
        current = FakeDocument()
        updated = FakeDocument(
            pinned=current.pinned if pinned is None else pinned,
            archived=current.archived if archived is None else archived,
            category=category if update_category else current.category,
        )
        self.organized_document = updated
        return updated

    def read_searchable_text(self, document):
        return "Extracted paper text."

    def read_chunks(self, document):
        return (
            DocumentChunk(
                document_id=document.id,
                chunk_id="doc-1-0",
                text="The method retrieves evidence before generating an answer.",
                metadata={"section": "2 Method", "page": 2, "block_type": "paragraph"},
            ),
        )

    def read_artifacts(self, document):
        return [
            PaperArtifact(
                document_id=document.id,
                artifact_id="artifact-1",
                kind="figure",
                text="Figure 1: Retrieval pipeline.",
                page=1,
                caption="Figure 1: Retrieval pipeline.",
            )
        ]

    def read_artifact_interpretations(self, document):
        return []

    def write_artifact_interpretations(self, document, interpretations):
        self.interpretations = interpretations


def test_web_ui_serves_shell_and_document_api(monkeypatch):
    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    with _server() as base_url:
        html = _get_text(base_url + "/")
        docs = _get_json(base_url + "/api/documents?field=nlp")

    assert "Papereading Master Beta" in html
    assert "view-source" in html
    assert "论文阅读工作台" in html
    assert 'id="ingestFile" type="file"' in html
    assert 'data-type="paper"' in html
    assert 'data-type="document"' not in html
    assert 'data-type="code"' in html
    assert 'id="ingestField"' not in html
    assert 'id="ingestTitle"' not in html
    assert "复习卡片" not in html
    assert "笔记与问题" not in html
    assert "图表与概念" not in html
    assert 'id="pdfReader"' in html
    assert 'id="readingPageLabel"' in html
    assert "保存进度" not in html
    assert 'id="artifactList"' in html
    assert 'id="openSettings"' in html
    assert "保存裁剪" in html
    assert "artifact-thumb" in html
    assert "crop-handle" in html
    assert "拖动边角扩大或缩小当前范围" in html
    assert "图表、公式与算法" in html
    assert 'id="inspector-digest"' in html
    assert 'id="pageJump"' in html
    assert 'class="pdf-text-layer"' in html
    assert "/api/document-page-text" in html
    assert "renderMathInElement" in html
    assert "evidence-highlight" in html
    assert 'id="textApiKey"' in html
    assert 'id="visionApiKey"' in html
    assert 'id="libraryView"' in html
    assert 'id="categoryFilter"' in html
    assert 'id="categoryModal"' in html
    assert 'id="historyModal"' in html
    assert 'id="codeWorkspace"' in html
    assert 'id="ingestFolder"' in html
    assert ".ipynb" in html
    assert "highlight.min.js" in html
    assert 'id="closeInspector"' not in html
    assert "/api/document-organize" in html
    assert "/api/reading-history" in html
    assert "/api/code-workspace" in html
    assert "/api/code-file" in html
    assert "/api/document-save" in html
    assert "/api/timeline-summary" in html
    assert 'id="timelineNoteText"' in html
    assert 'id="codeDetailMode"' in html
    assert 'id="regenerateAnalysis"' in html
    assert 'id="markdownEditor"' in html
    assert "data-doc-action=\"pin\"" in html
    assert "data-doc-action=\"archive\"" in html
    assert "data-doc-action=\"delete\"" in html
    assert "/api/read-stream" in html
    assert "/api/translate-stream" in html
    assert "/api/artifact-explain-stream" in html
    assert "/api/artifact-note" in html
    assert "添加到纪要" in html
    assert 'id="appLanguage"' in html
    assert "translatePdfSelection" in html
    assert "lastPdfCopyAt" in html
    assert "restore-translation" in html
    assert 'id="openResearch"' in html
    assert 'id="researchWorkspace"' in html
    assert 'id="openReading"' in html
    assert "/api/background/start" in html
    assert "/api/background/cancel" in html
    assert "/api/background-task" in html
    assert "research_import" in html
    assert 'id="backgroundTaskBar"' in html
    assert 'id="refreshArtifacts"' in html
    assert "research_correspondence" in html
    assert 'id="researchCorrespondence"' in html
    assert 'id="researchCorrespondenceOutput"' in html
    assert 'id="researchPrompt"' in html
    assert 'id="researchResultFiles"' in html
    assert "/api/research/attachment" in html
    assert 'id="researchPromptAppend"' in html
    assert "追加并重新寻找" in html
    assert "/api/timeline-reorder" in html
    assert "/api/timeline-delete" in html
    assert "[hidden] { display: none !important; }" in html
    assert docs["documents"][0]["title"] == "Target Paper"


def test_web_ui_research_workflow_api(monkeypatch):
    class FakeResearchAssistant:
        def discover(self, **kwargs):
            assert kwargs["paper_ids"] == ["doc-1"]
            return {
                "task": {"id": "task-1", "paper_ids": ["doc-1"], "code_ids": []},
                "candidates": [{"id": "ext-1", "title": "Related"}],
            }

        def analyze(self, **kwargs):
            assert kwargs["related_papers"][0]["id"] == "ext-1"
            return {
                "task": {"id": "task-1"},
                "analysis": {"overview": "Combined analysis"},
            }

        def check_correspondence(self, **kwargs):
            assert kwargs["code_ids"] == ["code-1"]
            return {
                "task": {"id": "task-1"},
                "correspondence": {
                    "summary": "Checked",
                    "checks": [],
                    "coverage_percent": 0,
                    "status_counts": {},
                },
            }

        def build_experiment(self, **kwargs):
            assert kwargs["mode"] == "mvp"
            return {
                "task": {"id": "task-1"},
                "experiment": {"codex_prompt": "Implement and measure the MVP."},
            }

        def assess_result(self, **kwargs):
            assert "latency" in kwargs["result"]
            return {
                "task": {"id": "task-1"},
                "assessment": {"decision": "adjust"},
            }

    monkeypatch.setattr(web, "_research_assistant", lambda **_kwargs: FakeResearchAssistant())
    with _server() as base_url:
        discovered = _post_json(
            base_url + "/api/research/discover",
            {"direction": "retrieval", "paper_ids": ["doc-1"]},
        )
        analyzed = _post_json(
            base_url + "/api/research/analyze",
            {
                "task_id": "task-1",
                "paper_ids": ["doc-1"],
                "related_papers": [{"id": "ext-1", "title": "Related"}],
            },
        )
        correspondence = _post_json(
            base_url + "/api/research/correspondence",
            {
                "task_id": "task-1",
                "paper_ids": ["doc-1"],
                "code_ids": ["code-1"],
            },
        )
        planned = _post_json(
            base_url + "/api/research/experiment",
            {"task_id": "task-1", "mode": "mvp"},
        )
        assessed = _post_json(
            base_url + "/api/research/assess",
            {"task_id": "task-1", "result": "latency improved"},
        )

    assert discovered["candidates"][0]["id"] == "ext-1"
    assert analyzed["analysis"]["overview"] == "Combined analysis"
    assert correspondence["correspondence"]["summary"] == "Checked"
    assert "Implement" in planned["experiment"]["codex_prompt"]
    assert assessed["assessment"]["decision"] == "adjust"


def test_research_candidate_can_be_downloaded_and_imported(monkeypatch, tmp_path):
    repository = StudyRepository(
        index_path=tmp_path / "index.json",
        raw_data_dir=tmp_path / "raw",
    )
    monkeypatch.setattr(web, "StudyRepository", lambda: repository)
    store = web.ResearchTaskStore()
    task = store.create(name="Import test", direction="retrieval")
    candidate = {
        "id": "candidate-1",
        "title": "Imported arXiv Paper",
        "url": "https://arxiv.org/abs/2605.01106v1",
        "categories": ["cs.CL"],
        "source_level": "external_abstract",
    }
    store.update(task["id"], related_candidates=[candidate])

    def fake_download(_url, target):
        import fitz

        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Imported paper")
        pdf.save(target)
        pdf.close()
        return "https://arxiv.org/pdf/2605.01106v1.pdf"

    monkeypatch.setattr(
        "finals_agent.data.paper_download.download_arxiv_pdf",
        fake_download,
    )

    result = web._api_research_import(
        {"task_id": task["id"], "candidate_id": candidate["id"]}
    )

    assert result["document"]["title"] == candidate["title"]
    assert repository.get_document(result["document"]["id"]).source.endswith(".pdf")
    updated = store.get(task["id"])
    assert result["document"]["id"] in updated["paper_ids"]
    assert updated["related_candidates"][0]["imported_document_id"] == result["document"]["id"]


def test_background_research_endpoint_returns_task_result(monkeypatch):
    manager = web.BackgroundTaskManager()
    monkeypatch.setattr(web, "BACKGROUND_TASKS", manager)
    monkeypatch.setattr(
        web,
        "_api_research_discover",
        lambda payload, task_context=None: {
            "candidates": [{"id": "candidate-1"}],
            "payload": payload,
        },
    )

    started = web._api_background_start(
        {
            "kind": "research_discover",
            "payload": {"direction": "retrieval"},
        }
    )
    task_id = started["task"]["id"]
    for _ in range(100):
        task = manager.get(task_id)
        if task["status"] == "completed":
            break
        threading.Event().wait(0.01)

    assert task["status"] == "completed"
    assert task["result"]["payload"]["direction"] == "retrieval"


def test_background_research_cancel_prevents_cooperative_side_effect(monkeypatch):
    manager = web.BackgroundTaskManager()
    entered = threading.Event()
    release = threading.Event()
    side_effects = []
    monkeypatch.setattr(web, "BACKGROUND_TASKS", manager)

    def fake_discover(payload, task_context=None):
        entered.set()
        release.wait(timeout=2)
        task_context.raise_if_cancelled()
        side_effects.append(payload["direction"])
        return {"candidates": []}

    monkeypatch.setattr(web, "_api_research_discover", fake_discover)
    started = web._api_background_start(
        {"kind": "research_discover", "payload": {"direction": "retrieval"}}
    )
    entered.wait(timeout=1)
    manager.cancel(started["task"]["id"])
    release.set()
    threading.Event().wait(0.05)

    assert manager.get(started["task"]["id"])["status"] == "cancelled"
    assert side_effects == []


def test_remove_api_invalidates_research_tasks(monkeypatch):
    class FakeRepository:
        def remove_document(self, document_id):
            assert document_id == "paper-1"
            return SimpleNamespace(id=document_id, to_dict=lambda: {"id": document_id})

    class FakeTaskStore:
        def invalidate_document(self, document_id):
            assert document_id == "paper-1"
            return [{"id": "task-1"}]

    monkeypatch.setattr(web, "StudyRepository", FakeRepository)
    monkeypatch.setattr(web, "ResearchTaskStore", FakeTaskStore)

    result = web._api_remove({"document_id": "paper-1"})

    assert result["invalidated_research_tasks"] == ["task-1"]


def test_web_ui_creates_research_task_and_uploads_result_attachments(monkeypatch):
    class FakeVisionClient:
        def analyze(self, image_bytes, mime_type, prompt):
            assert image_bytes == b"image-bytes"
            assert mime_type == "image/png"
            assert "experiment-result image" in prompt
            return "Observed validation accuracy is 84%."

    monkeypatch.setattr(web, "build_vision_client", lambda: FakeVisionClient())
    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    with _server() as base_url:
        created = _post_json(
            base_url + "/api/research/new",
            {"name": "Named task", "direction": "test direction"},
        )
        task_id = created["task"]["id"]
        updated = _post_json(
            base_url + "/api/research/update",
            {
                "task_id": task_id,
                "name": "Named task v2",
                "direction": "updated direction",
                "paper_ids": ["doc-1"],
                "code_ids": [],
                "candidate_sort": "newest",
            },
        )
        markdown = _post_bytes(
            base_url
            + "/api/research/attachment?"
            + urlencode(
                {
                    "task_id": task_id,
                    "filename": "result.md",
                    "content_type": "text/markdown",
                }
            ),
            b"# Result\nLatency improved.",
        )
        image = _post_bytes(
            base_url
            + "/api/research/attachment?"
            + urlencode(
                {
                    "task_id": task_id,
                    "filename": "chart.png",
                    "content_type": "image/png",
                }
            ),
            b"image-bytes",
        )

    assert created["task"]["name"] == "Named task"
    assert updated["task"]["name"] == "Named task v2"
    assert updated["task"]["paper_ids"] == ["doc-1"]
    assert updated["task"]["candidate_sort"] == "newest"
    assert markdown["attachment"]["content"].startswith("# Result")
    assert image["attachment"]["vision_status"] == "analyzed"
    assert "84%" in image["attachment"]["analysis"]
    assert len(image["task"]["result_attachments"]) == 2


def test_web_ui_reorders_and_deletes_reading_timeline(monkeypatch):
    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    first = web.ReadingStateStore().add_note(FakeDocument(), "First").timeline[-1]
    second = web.ReadingStateStore().add_note(FakeDocument(), "Second").timeline[-1]

    with _server() as base_url:
        reordered = _post_json(
            base_url + "/api/timeline-reorder",
            {"document_id": "doc-1", "entry_ids": [second.id, first.id]},
        )
        deleted = _post_json(
            base_url + "/api/timeline-delete",
            {"document_id": "doc-1", "entry_id": first.id},
        )

    assert [item["id"] for item in reordered["state"]["timeline"]] == [second.id, first.id]
    assert [item["id"] for item in deleted["state"]["timeline"]] == [second.id]


def test_web_ui_search_api(monkeypatch):
    class FakeModel:
        def invoke(self, messages):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "intent": "寻找论文中的检索方法证据",
                        "queries": ["retrieval method", "evidence generation"],
                    }
                )
            )

    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    monkeypatch.setattr(web, "build_chat_model", lambda: FakeModel())
    with _server() as base_url:
        payload = _post_json(
            base_url + "/api/search",
            {"document_id": "doc-1", "query": "retrieval"},
        )

    assert payload["results"][0]["title"] == "Target Paper"
    assert payload["results"][0]["citation"]
    assert payload["intent"] == "寻找论文中的检索方法证据"
    assert payload["metadata"]["retriever"] == "HybridRetriever"
    assert payload["record"]["kind"] == "evidence_search"
    assert payload["record"]["metadata"]["result_count"] == 1
    assert "highlights" in payload["results"][0]


def test_web_ui_organizes_document(monkeypatch):
    repository = FakeRepository()
    monkeypatch.setattr(web, "StudyRepository", lambda: repository)
    with _server() as base_url:
        payload = _post_json(
            base_url + "/api/document-organize",
            {
                "document_id": "doc-1",
                "pinned": True,
                "category": "推理加速",
            },
        )

    assert payload["document"]["pinned"] is True
    assert payload["document"]["category"] == "推理加速"
    assert repository.organized_document.category == "推理加速"


def test_web_ui_returns_full_reading_history(monkeypatch):
    memory = SimpleNamespace(
        messages=(
            SimpleNamespace(role=SimpleNamespace(value="user"), content="方法是什么？"),
            SimpleNamespace(
                role=SimpleNamespace(value="assistant"),
                content="完整回答包含公式 $x^2$ 和详细解释。",
            ),
        )
    )
    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    monkeypatch.setattr(web, "JsonMemoryStore", lambda: SimpleNamespace(get=lambda _id: memory))

    with _server() as base_url:
        payload = _get_json(base_url + "/api/reading-history?id=doc-1")

    assert payload["entries"][0]["question"] == "方法是什么？"
    assert payload["entries"][0]["answer"] == "完整回答包含公式 $x^2$ 和详细解释。"
    assert payload["entries"][0]["summary"]


def test_web_ui_merges_legacy_questions_with_new_timeline_notes(monkeypatch):
    memory = SimpleNamespace(
        messages=(
            SimpleNamespace(role=SimpleNamespace(value="user"), content="Old question"),
            SimpleNamespace(role=SimpleNamespace(value="assistant"), content="Old full answer"),
        )
    )
    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    monkeypatch.setattr(web, "JsonMemoryStore", lambda: SimpleNamespace(get=lambda _id: memory))
    web.ReadingStateStore().add_note(FakeDocument(), "New reader note")

    with _server() as base_url:
        payload = _get_json(base_url + "/api/reading-history?id=doc-1")

    assert [entry["kind"] for entry in payload["entries"]] == ["question", "note"]
    assert payload["entries"][0]["answer"] == "Old full answer"
    assert payload["entries"][1]["text"] == "New reader note"


def test_web_ui_deduplicates_questions_saved_in_memory_and_timeline(monkeypatch):
    memory = SimpleNamespace(
        messages=(
            SimpleNamespace(role=SimpleNamespace(value="user"), content="Same question"),
            SimpleNamespace(role=SimpleNamespace(value="assistant"), content="Same answer"),
        )
    )
    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    monkeypatch.setattr(web, "JsonMemoryStore", lambda: SimpleNamespace(get=lambda _id: memory))
    web.ReadingStateStore().add_timeline_entry(
        FakeDocument(),
        "question",
        "Same question",
        answer="Same answer",
    )

    with _server() as base_url:
        payload = _get_json(base_url + "/api/reading-history?id=doc-1")

    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["kind"] == "question"


def test_web_ui_returns_code_workspace_with_relative_paths(monkeypatch, tmp_path):
    first_path = tmp_path / "main.py"
    second_path = tmp_path / "utils.py"
    first_path.write_text("from src.utils import value\n", encoding="utf-8")
    second_path.write_text("value = 42\n", encoding="utf-8")
    first = FakeDocument(
        id="code-1",
        title="main",
        path=first_path,
        document_type=DocumentType.CODE,
        source="main.py",
        category="demo-project",
    )
    second = FakeDocument(
        id="code-2",
        title="utils",
        path=second_path,
        document_type=DocumentType.CODE,
        source="src/utils.py",
        category="demo-project",
    )

    class CodeRepository(FakeRepository):
        def list_documents(self, field=None):
            return [first, second]

        def get_document(self, document_id):
            return first if document_id == first.id else second

    monkeypatch.setattr(web, "StudyRepository", lambda: CodeRepository())
    with _server() as base_url:
        payload = _get_json(base_url + "/api/code-workspace?id=code-1")

    assert payload["project"] == "demo-project"
    assert [item["path"] for item in payload["files"]] == ["main.py", "src/utils.py"]
    assert payload["files"][0]["language"] == "python"
    assert "content" not in payload["files"][0]

    with _server() as base_url:
        file_payload = _get_json(base_url + "/api/code-file?id=code-1")

    assert "from src.utils" in file_payload["file"]["content"]


@pytest.mark.parametrize(
    ("detail", "expected_instruction"),
    [
        ("brief", "简要概括项目用途"),
        ("detailed", "详细解释项目中的每个已提供文件"),
    ],
)
def test_code_read_stream_analyzes_project_without_evidence_search(
    monkeypatch,
    tmp_path,
    detail,
    expected_instruction,
):
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 42\n", encoding="utf-8")
    document = FakeDocument(
        id="code-1",
        title="main",
        path=source,
        document_type=DocumentType.CODE,
        source="main.py",
        category="demo-project",
    )

    class CodeRepository(FakeRepository):
        def list_documents(self, field=None):
            return [document]

        def get_document(self, document_id):
            return document

    class StreamingModel:
        def stream(self, messages):
            assert "main.py" in messages[-1]["content"]
            assert expected_instruction in messages[0]["content"]
            yield SimpleNamespace(content="## 项目用途\n")
            yield SimpleNamespace(content="入口位于 `main.py`。")

    monkeypatch.setattr(web, "StudyRepository", lambda: CodeRepository())
    monkeypatch.setattr(web, "build_chat_model", lambda: StreamingModel())

    events = list(
        web._api_read_stream(
            {
                "document_id": "code-1",
                "code_detail": detail,
                "regenerate": True,
            }
        )
    )

    assert events[1]["mode"] == "code"
    assert "".join(event.get("text", "") for event in events) == "## 项目用途\n入口位于 `main.py`。"
    assert events[-1]["mode"] == "code"
    assert events[-1]["detail"] == detail
    assert events[-1]["record"]["kind"] == "code_analysis"
    assert events[-1]["record"]["metadata"]["detail"] == detail
    assert events[-1]["record"]["metadata"]["regenerated"] is True


def test_web_ui_serves_selectable_pdf_text(monkeypatch, tmp_path):
    import fitz

    source = tmp_path / "selectable.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Selectable paper text")
    pdf.save(source)
    pdf.close()
    document = FakeDocument(path=source)

    class PdfRepository(FakeRepository):
        def get_document(self, document_id):
            return document

    monkeypatch.setattr(web, "StudyRepository", lambda: PdfRepository())
    with _server() as base_url:
        payload = _get_json(base_url + "/api/document-page-text?id=doc-1&page=1")

    assert payload["page"] == 1
    assert any("Selectable paper text" in line["text"] for line in payload["lines"])
    assert all(len(line["bbox"]) == 4 for line in payload["lines"])


def test_reading_digest_is_short_and_recall_focused():
    digest = web._append_reading_digest(
        None,
        question="这篇论文的核心方法是什么？",
        answer=(
            "核心方法是先检索证据，再基于证据生成回答。"
            "第二句包含很多实现细节，不应全部进入阅读纪要。"
            "[Target Paper | section=2 Method | page=2 | chunk=doc-1-0]"
        ),
    )

    assert digest.startswith("• 这篇论文的核心方法是什么？：")
    assert "核心方法是先检索证据" in digest
    assert "第二句包含很多实现细节" not in digest
    assert len(digest) < 260


def test_reading_digest_compacts_legacy_question_answer():
    digest = web._compact_reading_digest(
        "问：什么是自回归？\n"
        "答：自回归模型逐个预测下一个词。后面的实现细节不应保留。\n"
        "### 冗长章节"
    )

    assert digest == "• 什么是自回归？：自回归模型逐个预测下一个词。"


def test_reading_digest_skips_conversational_preamble():
    sentence = web._digest_sentence(
        "好的，结合本地论文内容，我来解释这个概念。"
        "自回归是一种逐个生成的建模方式，每一步都基于已经生成的内容预测下一个元素。"
        "如果你愿意，我还可以继续展开。",
        max_chars=120,
    )

    assert sentence.startswith("自回归是一种逐个生成")
    assert "好的" not in sentence


def test_web_ui_streams_whole_paper_reading(monkeypatch):
    citation = "[Target Paper | section=2 Method | page=2 | chunk=doc-1-0]"

    class FakeWorkflow:
        def read(self, **kwargs):
            return SimpleNamespace(
                to_dict=lambda: {
                    "workflow": "read_paper",
                    "data": {
                        "paper": FakeDocument().to_dict(),
                        "reading_state": {"status": "reading"},
                        "coverage": {"covered_count": 1, "total_count": 1},
                        "section_passes": [
                            {
                                "role": "method",
                                "evidence": [
                                    {
                                        "id": "doc-1",
                                        "title": "Target Paper",
                                        "field": "nlp",
                                        "snippet": "The method retrieves evidence before generation.",
                                        "chunk_id": "doc-1-0",
                                        "page": 2,
                                        "section": "2 Method",
                                        "citation": citation,
                                    }
                                ],
                            }
                        ],
                        "evidence": [],
                    },
                }
            )

    class FakeStreamingModel:
        def stream(self, messages):
            yield SimpleNamespace(content="【核心结论】")
            yield SimpleNamespace(content=f"深入报告。{citation}")

    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    monkeypatch.setattr(web, "PaperReadingWorkflow", lambda repository: FakeWorkflow())
    monkeypatch.setattr(web, "build_chat_model", lambda: FakeStreamingModel())
    with _server() as base_url:
        events = _post_text(base_url + "/api/read-stream", {"document_id": "doc-1"})

    parsed = [json.loads(line) for line in events.splitlines()]
    assert parsed[0]["type"] == "status"
    assert [item["type"] for item in parsed].count("delta") == 2
    assert parsed[-1]["type"] == "done"
    assert parsed[-1]["citation_check"]["passed"] is True
    assert parsed[-1]["record"]["kind"] == "smart_reading"


def test_web_ui_streams_chat_answer(monkeypatch):
    answer = r"令 $p(x)=q(x)$，因此结论成立。"

    def fake_run(payload, token_sink=None):
        assert payload["question"] == "为什么成立？"
        token_sink("令 $p(x)")
        token_sink("=q(x)$，因此结论成立。")
        return SimpleNamespace(answer=answer, metadata={"streamed": True})

    monkeypatch.setattr(web, "_run_chat_agent", fake_run)
    monkeypatch.setattr(
        web,
        "_save_chat_reading_state",
        lambda payload, saved_answer: {"saved_answer": saved_answer},
    )
    with _server() as base_url:
        events = _post_text(
            base_url + "/api/chat-stream",
            {"question": "为什么成立？", "document_id": "doc-1"},
        )

    parsed = [json.loads(line) for line in events.splitlines()]
    assert [item["type"] for item in parsed] == ["status", "delta", "delta", "done"]
    assert parsed[-1]["answer"] == answer
    assert parsed[-1]["reading_state"]["saved_answer"] == answer


def test_pdf_text_lines_use_column_reading_order():
    lines = [
        {"text": "right first", "bbox": [0.55, 0.20, 0.90, 0.23]},
        {"text": "left second", "bbox": [0.10, 0.30, 0.45, 0.33]},
        {"text": "header", "bbox": [0.20, 0.10, 0.80, 0.13]},
        {"text": "right second", "bbox": [0.55, 0.30, 0.90, 0.33]},
        {"text": "left first", "bbox": [0.10, 0.20, 0.45, 0.23]},
    ]

    ordered = web._order_pdf_text_lines(lines)

    assert [item["text"] for item in ordered] == [
        "header",
        "left first",
        "left second",
        "right first",
        "right second",
    ]


def test_web_ui_streams_selection_translation(monkeypatch):
    class FakeStreamingModel:
        def stream(self, messages):
            assert "Translate only" in messages[0]["content"]
            assert messages[1]["content"] == "Selected paper sentence."
            yield SimpleNamespace(content="选中的")
            yield SimpleNamespace(content="论文句子。")

    monkeypatch.setattr(web, "build_chat_model", lambda: FakeStreamingModel())
    with _server() as base_url:
        events = _post_text(
            base_url + "/api/translate-stream",
            {"text": "Selected paper sentence."},
        )

    parsed = [json.loads(line) for line in events.splitlines()]
    assert [item["type"] for item in parsed] == ["status", "delta", "delta", "done"]
    assert "".join(item.get("text", "") for item in parsed) == "选中的论文句子。"


def test_web_ui_serves_extracted_document_content(monkeypatch):
    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    with _server() as base_url:
        payload = _get_json(base_url + "/api/document-content?id=doc-1")

    assert payload["document"]["id"] == "doc-1"
    assert payload["text"] == "Extracted paper text."


def test_web_ui_serves_named_document_file(monkeypatch, tmp_path):
    source = tmp_path / "stored.pdf"
    source.write_bytes(b"%PDF-test")
    document = FakeDocument(title="Named Paper", path=source)

    class NamedRepository(FakeRepository):
        def get_document(self, document_id):
            return document

    monkeypatch.setattr(web, "StudyRepository", lambda: NamedRepository())
    with _server() as base_url:
        request = Request(base_url + "/api/document-file/Named%20Paper.pdf?id=doc-1")
        with urlopen(request, timeout=5) as response:
            content_disposition = response.headers["Content-Disposition"]
            body = response.read()

    assert body == b"%PDF-test"
    assert 'filename="Named Paper.pdf"' in content_disposition
    assert "filename*=UTF-8''Named%20Paper.pdf" in content_disposition


def test_web_ui_uploads_selected_file(monkeypatch):
    captured = {}

    def fake_ingest(request, repository):
        captured["suffix"] = request.source_path.suffix
        captured["content"] = request.source_path.read_text(encoding="utf-8")
        captured["type"] = request.document_type.value
        captured["title"] = request.title
        return SimpleNamespace(document=FakeDocument(), metadata={"uploaded": True})

    monkeypatch.setattr(web, "ingest_material", fake_ingest)
    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    query = urlencode(
        {
            "filename": "example.py",
            "document_type": "code",
            "field": "agents",
            "title": "Example",
        }
    )
    with _server() as base_url:
        payload = _post_bytes(base_url + "/api/upload?" + query, b"print('hello')\n")

    assert payload["metadata"]["uploaded"] is True
    assert captured == {
        "suffix": ".py",
        "content": "print('hello')\n",
        "type": "code",
        "title": "Example",
    }


def test_reading_digest_keeps_recent_question_and_answer():
    digest = web._append_reading_digest(
        "已有纪要",
        question="这篇论文的方法是什么？",
        answer="方法使用检索结果增强生成。",
    )

    assert "已有纪要" in digest
    assert "• 这篇论文的方法是什么？：方法使用检索结果增强生成。" in digest


def test_web_ui_lists_visual_artifacts(monkeypatch):
    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    with _server() as base_url:
        payload = _get_json(base_url + "/api/artifacts?id=doc-1")

    assert payload["artifacts"][0]["artifact_id"] == "artifact-1"
    assert payload["artifacts"][0]["image_available"] is False


def test_display_artifacts_deduplicates_same_number_and_overlapping_region():
    figure_one = PaperArtifact(
        document_id="doc-1",
        artifact_id="stored-figure",
        kind="figure",
        text="Figure 2. Main result.",
        page=3,
        caption="Figure 2. Main result.",
    )
    duplicate_number = PaperArtifact(
        document_id="doc-1",
        artifact_id="detected-figure",
        kind="figure",
        text="Figure 2",
        page=3,
        caption="Figure 2",
        metadata={"number": "2"},
    )
    distinct = PaperArtifact(
        document_id="doc-1",
        artifact_id="figure-three",
        kind="figure",
        text="Figure 3. Ablation.",
        page=3,
        caption="Figure 3. Ablation.",
    )
    regions = {
        "stored-figure": ArtifactRegion(
            artifact_id="stored-figure",
            page=3,
            bbox=(0.1, 0.1, 0.5, 0.5),
            confidence=0.9,
            method="test",
            updated_at="now",
        ),
        "detected-figure": ArtifactRegion(
            artifact_id="detected-figure",
            page=3,
            bbox=(0.11, 0.11, 0.49, 0.49),
            confidence=0.8,
            method="test",
            updated_at="now",
        ),
        "figure-three": ArtifactRegion(
            artifact_id="figure-three",
            page=3,
            bbox=(0.52, 0.1, 0.9, 0.5),
            confidence=0.9,
            method="test",
            updated_at="now",
        ),
    }

    result = web._deduplicate_display_artifacts(
        [figure_one, duplicate_number, distinct],
        regions,
    )

    assert [item.artifact_id for item in result] == ["stored-figure", "figure-three"]


def test_web_ui_explains_one_artifact(monkeypatch):
    interpretation = ArtifactInterpretation(
        document_id="doc-1",
        artifact_id="artifact-1",
        kind="figure",
        extracted_text="Figure 1",
        structured_data={},
        interpretation="The figure shows retrieval followed by generation.",
        confidence=0.8,
        method="vision_api",
    )

    class FakeInterpreter:
        def interpret(self, artifact):
            return interpretation

    repository = FakeRepository()
    monkeypatch.setattr(web, "StudyRepository", lambda: repository)
    monkeypatch.setattr(web, "build_vision_artifact_interpreter", lambda document: FakeInterpreter())
    with _server() as base_url:
        payload = _post_json(
            base_url + "/api/artifact-explain",
            {"document_id": "doc-1", "artifact_id": "artifact-1"},
        )

    assert payload["interpretation"]["method"] == "vision_api"
    assert repository.interpretations[0].artifact_id == "artifact-1"
    assert "record" not in payload
    assert web.ReadingStateStore().get(FakeDocument()).timeline == ()


def test_web_ui_streams_one_artifact_explanation(monkeypatch):
    interpretation = ArtifactInterpretation(
        document_id="doc-1",
        artifact_id="artifact-1",
        kind="figure",
        extracted_text="Figure 1",
        structured_data={},
        interpretation="图中先检索，再生成。",
        confidence=0.8,
        method="vision_api",
    )

    class FakeInterpreter:
        def interpret_stream(self, artifact):
            yield "图中先检索，"
            yield "再生成。"
            return interpretation

    repository = FakeRepository()
    monkeypatch.setattr(web, "StudyRepository", lambda: repository)
    monkeypatch.setattr(web, "build_vision_artifact_interpreter", lambda document: FakeInterpreter())
    with _server() as base_url:
        events = _post_text(
            base_url + "/api/artifact-explain-stream",
            {"document_id": "doc-1", "artifact_id": "artifact-1"},
        )

    parsed = [json.loads(line) for line in events.splitlines()]
    assert [item["type"] for item in parsed] == ["status", "delta", "delta", "done"]
    assert parsed[-1]["interpretation"]["method"] == "vision_api"
    assert "record" not in parsed[-1]
    assert repository.interpretations[0].artifact_id == "artifact-1"
    assert web.ReadingStateStore().get(FakeDocument()).timeline == ()


def test_web_ui_adds_artifact_explanation_to_timeline_only_on_request(monkeypatch):
    interpretation = ArtifactInterpretation(
        document_id="doc-1",
        artifact_id="artifact-1",
        kind="figure",
        extracted_text="Figure 1",
        structured_data={},
        interpretation="图中先检索，再生成。",
        confidence=0.8,
        method="vision_api",
    )
    repository = FakeRepository()
    repository.interpretations = [interpretation]
    repository.read_artifact_interpretations = lambda document: repository.interpretations
    monkeypatch.setattr(web, "StudyRepository", lambda: repository)

    first = web._api_artifact_note(
        {"document_id": "doc-1", "artifact_id": "artifact-1"}
    )
    second = web._api_artifact_note(
        {"document_id": "doc-1", "artifact_id": "artifact-1"}
    )

    assert first["added"] is True
    assert first["record"]["kind"] == "artifact_explanation"
    assert first["record"]["metadata"]["manual"] is True
    assert second["added"] is False


def test_web_ui_summarizes_interleaved_timeline(monkeypatch):
    class FakeModel:
        def invoke(self, messages):
            assert "reader's own notes" in messages[0]["content"]
            source = json.loads(messages[1]["content"])
            assert [item["kind"] for item in source] == ["note", "question"]
            return SimpleNamespace(content="## Recall\n\n- Retrieve evidence before generation.")

    monkeypatch.setattr(web, "StudyRepository", lambda: FakeRepository())
    monkeypatch.setattr(web, "build_chat_model", lambda: FakeModel())
    store = web.ReadingStateStore()
    store.add_note(FakeDocument(), "Check retrieval failures.")
    store.add_timeline_entry(
        FakeDocument(),
        "question",
        "What is the core method?",
        answer="Retrieve evidence, then generate the answer.",
    )

    with _server() as base_url:
        payload = _post_json(
            base_url + "/api/timeline-summary",
            {"document_id": "doc-1"},
        )

    assert payload["summary"].startswith("## Recall")
    assert payload["record"]["kind"] == "timeline_summary"
    assert payload["record"]["metadata"]["source_count"] == 2


def test_write_env_values_updates_without_exposing_other_values(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("KEEP=value\nLLM_MODEL=old\n", encoding="utf-8")

    web._write_env_values(
        {"LLM_MODEL": "qwen-plus", "LLM_API_KEY": "secret"},
        env_path=env_path,
    )

    content = env_path.read_text(encoding="utf-8")
    assert "KEEP=value" in content
    assert "LLM_MODEL=qwen-plus" in content
    assert "LLM_API_KEY=secret" in content


def test_save_settings_applies_separate_text_and_vision_models(monkeypatch):
    captured = {}
    monkeypatch.setattr(web, "_write_env_values", lambda values: captured.update(values))
    for key in (
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "VISION_PROVIDER",
        "VISION_MODEL",
        "VISION_BASE_URL",
        "VISION_API_KEY",
    ):
        monkeypatch.setenv(key, "")

    result = web._api_save_settings(
        {
            "language": "en",
            "text": {
                "provider": "custom",
                "model": "qwen-plus",
                "base_url": "https://text.example/v1",
                "api_key": "text-secret",
            },
            "vision": {
                "provider": "openai_compatible",
                "model": "qwen-vl-max",
                "base_url": "https://vision.example/v1",
                "api_key": "vision-secret",
            },
        }
    )

    assert captured["LLM_MODEL"] == "qwen-plus"
    assert captured["LLM_API_KEY"] == "text-secret"
    assert captured["VISION_MODEL"] == "qwen-vl-max"
    assert captured["VISION_API_KEY"] == "vision-secret"
    assert captured["APP_LANGUAGE"] == "en"
    assert result["text"]["model"] == "qwen-plus"
    assert result["vision"]["model"] == "qwen-vl-max"
    assert result["language"] == "en"


def test_save_settings_rejects_blank_key_for_new_remote_text_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_MODEL", "old-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://old.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "old-secret")

    with pytest.raises(web.FinalsAgentError, match="API Key cannot be empty"):
        web._api_save_settings(
            {
                "text": {
                    "provider": "custom",
                    "model": "new-model",
                    "base_url": "https://new.example/v1",
                    "api_key": "",
                },
                "vision": {"provider": "disabled"},
            }
        )


def test_save_settings_allows_local_endpoint_without_key(monkeypatch):
    captured = {}
    monkeypatch.setattr(web, "_write_env_values", lambda values: captured.update(values))
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_MODEL", "old-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://old.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "old-secret")

    web._api_save_settings(
        {
            "text": {
                "provider": "custom",
                "model": "local-model",
                "base_url": "http://127.0.0.1:5050/v1",
                "api_key": "",
            },
            "vision": {"provider": "disabled"},
        }
    )

    assert captured["LLM_API_KEY"] == "not-needed"


def test_save_settings_does_not_reuse_vision_key_for_new_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_MODEL", "text-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://text.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "text-secret")
    monkeypatch.setenv("VISION_PROVIDER", "openai_compatible")
    monkeypatch.setenv("VISION_MODEL", "old-vision")
    monkeypatch.setenv("VISION_BASE_URL", "https://old-vision.example/v1")
    monkeypatch.setenv("VISION_API_KEY", "old-vision-secret")

    with pytest.raises(web.FinalsAgentError, match="Vision model API Key cannot be empty"):
        web._api_save_settings(
            {
                "text": {
                    "provider": "custom",
                    "model": "text-model",
                    "base_url": "https://text.example/v1",
                    "api_key": "",
                },
                "vision": {
                    "provider": "openai_compatible",
                    "model": "new-vision",
                    "base_url": "https://new-vision.example/v1",
                    "api_key": "",
                },
            }
        )


class _server:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web.PaperAgentRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def _get_text(url: str) -> str:
    with urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8")


def _get_json(url: str) -> dict:
    return json.loads(_get_text(url))


def _post_json(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_text(url: str, payload: dict) -> str:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return response.read().decode("utf-8")


def _post_bytes(url: str, payload: bytes) -> dict:
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/octet-stream"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))
