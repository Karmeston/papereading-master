from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from finals_agent.app.background_tasks import TaskCancelledError
from finals_agent.core.exceptions import ToolInputError
from finals_agent.core.schemas import DocumentType
from finals_agent.data.external_search import ExternalPaper
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository
from finals_agent.data.research_assistant import (
    ResearchAssistant,
    _external_match_score,
    _fit_numbered_lines,
    _ground_correspondence,
)
from finals_agent.persistence.research_tasks import ResearchTaskStore
from finals_agent.persistence.storage import JsonFileStorage


class FakeExternalSearch:
    def __init__(self):
        self.queries = []

    def search(self, query: str, limit: int = 5):
        assert query
        self.queries.append(query)
        return (
            ExternalPaper(
                title="Related Retrieval Study",
                authors=("A. Researcher",),
                summary="A retrieval method evaluated on two public benchmarks.",
                url="https://arxiv.org/abs/2601.00001",
                published="2026-01-01",
                categories=("cs.CL",),
            ),
        )


class QueueModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.messages = []

    def invoke(self, messages):
        if "compact recall-oriented overview" in messages[0]["content"]:
            payload = json.loads(messages[1]["content"])
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "summaries": [
                            {
                                "id": paper["id"],
                                "brief_summary": f"Brief overview of {paper['title']}.",
                            }
                            for paper in payload["papers"]
                        ]
                    },
                    ensure_ascii=False,
                )
            )
        self.messages.append(messages)
        return SimpleNamespace(content=json.dumps(self.outputs.pop(0), ensure_ascii=False))


def _assistant(tmp_path: Path, outputs):
    repository = StudyRepository(
        index_path=tmp_path / "index.json",
        raw_data_dir=tmp_path / "raw",
    )
    paper_source = tmp_path / "paper.md"
    paper_source.write_text(
        "\n\n".join(
            [
                "Abstract",
                "The paper proposes evidence-aware retrieval.",
                "2 Method",
                "The retriever ranks passages before generation.",
                "3 Experiments",
                "The method improves accuracy but increases latency.",
            ]
        ),
        encoding="utf-8",
    )
    paper = ingest_material(
        build_ingest_request(
            paper_source,
            DocumentType.PAPER,
            field="retrieval",
            title="Local Retrieval Paper",
        ),
        repository=repository,
    ).document
    code_source = tmp_path / "retriever.py"
    code_source.write_text(
        "def rank(passages, query):\n    return sorted(passages)\n",
        encoding="utf-8",
    )
    code = ingest_material(
        build_ingest_request(
            code_source,
            DocumentType.CODE,
            field="code",
            title="retriever",
            source="src/retriever.py",
        ),
        repository=repository,
    ).document
    store = ResearchTaskStore(JsonFileStorage(tmp_path / "research-tasks.json"))
    model = QueueModel(outputs)
    assistant = ResearchAssistant(
        model,
        repository=repository,
        external_search=FakeExternalSearch(),
        task_store=store,
    )
    return assistant, model, store, paper, code


def test_research_assistant_discovers_and_persists_candidates(tmp_path: Path):
    assistant, _model, store, paper, code = _assistant(tmp_path, [])

    result = assistant.discover(
        direction="reduce retrieval latency",
        paper_ids=[paper.id],
        code_ids=[code.id],
    )

    assert result["candidates"][0]["source_level"] == "external_abstract"
    task = store.get(result["task"]["id"])
    assert task["paper_ids"] == [paper.id]
    assert task["code_ids"] == [code.id]
    assert task["related_candidates"][0]["title"] == "Related Retrieval Study"
    assert task["related_candidates"][0]["brief_summary"]


def test_research_assistant_excludes_selected_local_paper(tmp_path: Path):
    assistant, _model, _store, paper, _code = _assistant(tmp_path, [])

    class SearchWithSelectedPaper:
        def search(self, query: str, limit: int = 5):
            return (
                ExternalPaper(
                    title="Local Retrieval Paper",
                    authors=("Local Author",),
                    summary="The selected local paper.",
                    url="https://arxiv.org/abs/local",
                    published="2024-01-01",
                ),
                ExternalPaper(
                    title="New Retrieval Follow-up",
                    authors=("Other Author",),
                    summary="This work reduces retrieval latency. It evaluates a lightweight ranker.",
                    url="https://arxiv.org/abs/follow-up",
                    published="2026-02-01",
                ),
            )

    assistant.external_search = SearchWithSelectedPaper()
    assistant.model = None
    result = assistant.discover(
        direction="retrieval latency",
        paper_ids=[paper.id],
        limit=5,
    )

    assert [item["title"] for item in result["candidates"]] == ["New Retrieval Follow-up"]
    assert result["candidates"][0]["brief_summary"].startswith(
        "This work reduces retrieval latency."
    )


def test_research_task_name_and_material_selection_are_persisted(tmp_path: Path):
    assistant, _model, store, paper, code = _assistant(tmp_path, [])
    task = store.create(name="Latency Study", direction="")

    result = assistant.update_task(
        task_id=task["id"],
        name="Latency Study v2",
        direction="reduce retrieval latency",
        paper_ids=[paper.id],
        code_ids=[code.id],
    )

    assert result["task"]["name"] == "Latency Study v2"
    assert result["task"]["paper_ids"] == [paper.id]
    assert result["task"]["code_ids"] == [code.id]
    assert store.get(task["id"])["direction"] == "reduce retrieval latency"

    sorted_task = assistant.update_task(
        task_id=task["id"],
        name="Latency Study v2",
        direction="reduce retrieval latency",
        paper_ids=[paper.id],
        code_ids=[code.id],
        candidate_sort="newest",
    )
    assert sorted_task["task"]["candidate_sort"] == "newest"


def test_research_assistant_checks_paper_code_correspondence_with_grounded_locations(tmp_path: Path):
    assistant, model, store, paper, code = _assistant(tmp_path, [])
    citation = assistant._paper_context(paper)["evidence"][0]["citation"]
    model.outputs = [
        {
            "requirements": [
                {
                    "category": "algorithm",
                    "paper_claim": "The method ranks passages before generation.",
                    "paper_citation": citation,
                    "expected_behavior": "Rank candidate passages.",
                    "code_search_terms": ["rank", "passages"],
                }
            ]
        },
        {
            "summary": "The retrieval step is present, but evaluation coverage is incomplete.",
            "checks": [
                {
                    "category": "algorithm",
                    "paper_claim": "The method ranks passages before generation.",
                    "paper_citation": citation,
                    "expected_behavior": "Rank candidate passages.",
                    "status": "implemented",
                    "code_evidence_ids": ["C1"],
                    "implementation_evidence": "rank sorts the supplied passages.",
                    "discrepancy": "",
                    "verification_action": "Add a unit test for ranking order.",
                },
                {
                    "category": "metric",
                    "paper_claim": "The paper reports accuracy and latency.",
                    "paper_citation": "invented citation",
                    "expected_behavior": "Compute both metrics.",
                    "status": "implemented",
                    "code_evidence_ids": ["C999"],
                    "implementation_evidence": "Claimed metric code.",
                    "discrepancy": "",
                    "verification_action": "Run evaluation.",
                },
            ],
            "missing_components": ["Latency measurement"],
            "reproduction_risks": ["No benchmark configuration"],
            "recommended_next_checks": ["Trace dataset preprocessing"],
        },
        {
            "verified_summary": "Passage ranking is implemented; metric coverage is unverified.",
            "verdicts": [
                {
                    "check_index": 0,
                    "paper_claim_supported": True,
                    "code_status_supported": True,
                    "rationale": "The cited method and rank function describe the same operation.",
                },
                {
                    "check_index": 1,
                    "paper_claim_supported": False,
                    "code_status_supported": False,
                    "rationale": "The citation and code evidence are invalid.",
                },
            ],
        },
    ]
    task = store.create(
        name="Correspondence",
        direction="retrieval",
        paper_ids=[paper.id],
        code_ids=[code.id],
    )

    result = assistant.check_correspondence(task_id=task["id"])

    report = result["correspondence"]
    assert report["checks"][0]["status"] == "implemented"
    assert report["checks"][0]["paper_citation"] == citation
    assert report["checks"][0]["code_locations"][0]["path"] == "src/retriever.py"
    assert report["checks"][0]["code_locations"][0]["line_start"] == 1
    assert report["checks"][0]["code_locations"][0]["symbols"][0]["name"] == "rank"
    assert report["checks"][1]["status"] == "uncertain"
    assert report["checks"][1]["paper_citation"] == ""
    assert report["coverage_percent"] == 50
    assert store.get(task["id"])["correspondence"]["missing_components"] == ["Latency measurement"]


def test_correspondence_downgrades_semantically_rejected_evidence():
    report = _ground_correspondence(
        {
            "checks": [
                {
                    "category": "algorithm",
                    "paper_claim": "The paper trains a 70B transformer.",
                    "paper_citation": "[Paper p.1]",
                    "expected_behavior": "Train a transformer.",
                    "status": "implemented",
                    "code_evidence_ids": ["C1"],
                    "implementation_evidence": "sort() trains the transformer.",
                }
            ]
        },
        [{"evidence": [{"citation": "[Paper p.1]", "snippet": "The paper sorts integers."}]}],
        [
            {
                "id": "C1",
                "document_id": "code",
                "path": "sort.py",
                "line_start": 1,
                "line_end": 2,
                "symbols": [],
                "content": "1: def sort(values):\n2:     return sorted(values)",
            }
        ],
        verification_raw={
            "verdicts": [
                {
                    "check_index": 0,
                    "paper_claim_supported": False,
                    "code_status_supported": False,
                    "rationale": "The claim is unrelated to the supplied evidence.",
                }
            ]
        },
        code_coverage={"is_exhaustive": True},
    )

    assert report["checks"][0]["status"] == "uncertain"
    assert report["coverage_percent"] == 0


def test_code_evidence_retrieval_prioritizes_relevant_late_file(tmp_path: Path):
    assistant, _model, _store, _paper, _code = _assistant(tmp_path, [])
    noise_source = tmp_path / "generated.py"
    noise_source.write_text(("x = '" + "a" * 200 + "'\n") * 1000, encoding="utf-8")
    noise = ingest_material(
        build_ingest_request(
            noise_source,
            DocumentType.CODE,
            field="code",
            title="generated",
            source="generated.py",
        ),
        repository=assistant.repository,
    ).document
    implementation_source = tmp_path / "speculative.py"
    implementation_source.write_text(
        "def speculative_verify(draft_tokens):\n    return verify(draft_tokens)\n",
        encoding="utf-8",
    )
    implementation = ingest_material(
        build_ingest_request(
            implementation_source,
            DocumentType.CODE,
            field="code",
            title="speculative",
            source="src/speculative.py",
        ),
        repository=assistant.repository,
    ).document

    evidence, coverage = assistant._code_evidence_context(
        [noise, implementation],
        requirements=[
            {
                "paper_claim": "Verify speculative draft tokens.",
                "expected_behavior": "Run speculative verification.",
                "code_search_terms": ["speculative_verify", "draft_tokens"],
            }
        ],
    )

    assert evidence[0]["path"] == "src/speculative.py"
    assert coverage["is_exhaustive"] is False
    assert coverage["selected_files"] >= 1


def test_numbered_code_block_reports_only_visible_lines():
    text, visible = _fit_numbered_lines(
        ["x = '" + "a" * 200 + "'" for _ in range(100)],
        start_line=1,
        max_chars=9000,
    )

    assert len(visible) < 100
    assert text.splitlines()[-1].startswith(f"{len(visible)}:")


def test_cancelled_correspondence_does_not_persist_result(tmp_path: Path):
    assistant, model, store, paper, code = _assistant(tmp_path, [])
    citation = assistant._paper_context(paper)["evidence"][0]["citation"]
    model.outputs = [
        {
            "requirements": [
                {
                    "category": "algorithm",
                    "paper_claim": "Rank passages.",
                    "paper_citation": citation,
                    "expected_behavior": "Rank passages.",
                    "code_search_terms": ["rank"],
                }
            ]
        }
    ]
    task = store.create(
        name="Cancelled",
        direction="retrieval",
        paper_ids=[paper.id],
        code_ids=[code.id],
    )
    checks = 0

    def cancel_check():
        nonlocal checks
        checks += 1
        if checks >= 2:
            raise TaskCancelledError()

    with pytest.raises(TaskCancelledError):
        assistant.check_correspondence(
            task_id=task["id"],
            cancel_check=cancel_check,
        )

    assert store.get(task["id"])["correspondence"] is None


def test_research_task_revision_rejects_stale_result(tmp_path: Path):
    store = ResearchTaskStore(JsonFileStorage(tmp_path / "research-tasks.json"))
    task = store.create(name="Revision", direction="initial")
    store.update(task["id"], direction="changed")

    with pytest.raises(ToolInputError, match="stale result"):
        store.update(
            task["id"],
            expected_revision=task["revision"],
            correspondence={"summary": "stale"},
        )


def test_research_task_document_invalidation_clears_derived_results(tmp_path: Path):
    store = ResearchTaskStore(JsonFileStorage(tmp_path / "research-tasks.json"))
    task = store.create(
        name="Invalidation",
        direction="audit",
        paper_ids=["paper-1"],
        code_ids=["code-1"],
    )
    store.update(
        task["id"],
        analysis={"summary": "old"},
        correspondence={"summary": "old"},
        experiment={"title": "old"},
        decisions=[{"decision": "continue"}],
    )

    changed = store.invalidate_document("code-1")
    updated = store.get(task["id"])

    assert changed[0]["id"] == task["id"]
    assert updated["code_ids"] == []
    assert updated["analysis"] is None
    assert updated["correspondence"] is None
    assert updated["experiment"] is None
    assert updated["decisions"] == []


def test_research_assistant_translates_chinese_direction_for_arxiv(tmp_path: Path):
    assistant, _model, _store, paper, _code = _assistant(tmp_path, [])
    external = FakeExternalSearch()

    class TranslationModel:
        def invoke(self, messages):
            payload = json.loads(messages[1]["content"])
            assert payload["local_papers"][0]["excerpt"]
            assert payload["research_prompt"] == "动态 gamma 调整"
            return SimpleNamespace(content="dynamic gamma speculative decoding")

    assistant.model = TranslationModel()
    assistant.external_search = external
    result = assistant.discover(direction="动态 gamma 调整", paper_ids=[paper.id])

    assert external.queries[0].startswith("dynamic gamma speculative decoding")
    assert "retrieval" in external.queries[0].casefold()
    assert all(not any("\u3400" <= char <= "\u9fff" for char in query) for query in external.queries)
    assert result["queries"][0] == external.queries[0]


def test_research_prompt_keeps_structure_and_uses_late_additions(tmp_path: Path):
    assistant, _model, store, paper, _code = _assistant(tmp_path, [])

    class PromptModel:
        def __init__(self):
            self.prompt = ""

        def invoke(self, messages):
            payload = json.loads(messages[1]["content"])
            self.prompt = payload["research_prompt"]
            return SimpleNamespace(content="adaptive draft length speculative decoding")

    model = PromptModel()
    assistant.model = model
    prompt = (
        "研究主题：推测解码\n"
        "目标：降低延迟\n\n"
        "补充要求：\n更关注动态草稿长度，排除安全对齐"
    )
    result = assistant.discover(direction=prompt, paper_ids=[paper.id])

    assert model.prompt == prompt
    assert store.get(result["task"]["id"])["direction"] == prompt
    assert result["query"].startswith("adaptive draft length speculative decoding")


def test_external_match_score_filters_ambiguous_gamma_results():
    decoding = ExternalPaper(
        title="Adaptive Gamma for Speculative Decoding",
        authors=(),
        summary="Adjusts speculative decoding acceptance behavior.",
        url="https://arxiv.org/abs/1",
    )
    astronomy = ExternalPaper(
        title="Gamma Rays from the Galactic Plane",
        authors=(),
        summary="Studies high energy astronomy observations.",
        url="https://arxiv.org/abs/2",
    )

    query = "dynamic gamma adjustment speculative decoding"

    assert _external_match_score(decoding, query) >= 2
    assert _external_match_score(astronomy, query) == 1


def test_research_assistant_analyzes_papers_and_code(tmp_path: Path):
    analysis = {
        "overview": "The local and related work both study retrieval quality.",
        "paper_assessments": [],
        "cross_paper_synthesis": {
            "common_ground": ["retrieval before generation"],
            "key_differences": ["latency treatment"],
            "unresolved_gaps": ["cheap reranking"],
        },
        "code_correspondence": [
            {
                "paper_claim": "rank passages",
                "code_location": "src/retriever.py",
                "status": "partial",
                "explanation": "The file ranks passages but lacks learned scoring.",
                "evidence": ["src/retriever.py"],
            }
        ],
        "future_directions": [
            {
                "direction": "cheap reranking",
                "rationale": "Latency is unresolved.",
                "novelty_basis": "Different cost-quality tradeoff.",
                "risk": "May reduce recall.",
                "minimal_test": "Compare latency and recall on a small split.",
            }
        ],
        "recommendation": "Run an MVP.",
        "evidence_limits": ["The external paper is abstract-only."],
    }
    assistant, model, _store, paper, code = _assistant(tmp_path, [analysis])
    discovered = assistant.discover(
        direction="reduce retrieval latency",
        paper_ids=[paper.id],
        code_ids=[code.id],
    )

    result = assistant.analyze(
        task_id=discovered["task"]["id"],
        related_papers=discovered["candidates"],
    )

    assert result["analysis"]["code_correspondence"][0]["status"] == "partial"
    prompt_payload = json.loads(model.messages[0][1]["content"])
    assert prompt_payload["local_papers"][0]["evidence"][0]["citation"]
    assert prompt_payload["external_papers"][0]["source_level"] == "external_abstract"
    assert "src/retriever.py" in prompt_payload["code_context"][0]["path"]


def test_research_assistant_builds_coding_prompt_and_assesses_result(tmp_path: Path):
    analysis = {
        "overview": "Latency is the main gap.",
        "paper_assessments": [],
        "cross_paper_synthesis": {},
        "code_correspondence": [],
        "future_directions": [{"direction": "cheap reranking"}],
        "recommendation": "Run an MVP.",
        "evidence_limits": [],
    }
    experiment = {
        "title": "Cheap reranking MVP",
        "mode": "mvp",
        "hypothesis": "A cheap reranker preserves recall at lower latency.",
        "scope": "One dataset split.",
        "assumptions": [],
        "environment": ["Python 3.11"],
        "datasets_or_inputs": ["sample.jsonl"],
        "baseline": ["current ranker"],
        "implementation_steps": ["add benchmark"],
        "measurements": ["recall", "latency"],
        "success_criteria": ["latency -20% with recall loss <1 point"],
        "stop_conditions": ["recall loss >5 points"],
        "risks": [],
        "codex_prompt": "Inspect the repository, implement the benchmark, run tests, and report metrics.",
    }
    assessment = {
        "decision": "adjust",
        "rationale": "Latency improved but recall regressed.",
        "observations": ["latency -25%", "recall -3 points"],
        "failure_classification": "quality regression",
        "revised_hypothesis": "Use a two-stage threshold.",
        "next_measurements": ["threshold sweep"],
        "revised_steps": ["add threshold sweep"],
        "revised_codex_prompt": "Add a threshold sweep and report the Pareto frontier.",
        "stop_reason": "",
    }
    assistant, _model, store, paper, code = _assistant(
        tmp_path,
        [analysis, experiment, assessment],
    )
    task = assistant.discover(
        direction="reduce retrieval latency",
        paper_ids=[paper.id],
        code_ids=[code.id],
    )["task"]
    assistant.analyze(task_id=task["id"])

    planned = assistant.build_experiment(
        task_id=task["id"],
        mode="mvp",
        direction_index=0,
    )
    store.update(
        task["id"],
        result_attachments=[
            {
                "id": "result-md",
                "filename": "result.md",
                "kind": "markdown",
                "content": "Recall dropped by three points.",
            }
        ],
    )
    reviewed = assistant.assess_result(
        task_id=task["id"],
        result="Latency dropped 25%, recall dropped 3 points.",
        attachment_ids=["result-md"],
    )

    assert "Inspect the repository" in planned["experiment"]["codex_prompt"]
    assert planned["experiment"]["success_criteria"]
    assert reviewed["assessment"]["decision"] == "adjust"
    assert store.get(task["id"])["decisions"][-1]["revised_codex_prompt"]
    assessment_payload = json.loads(_model.messages[-1][1]["content"])
    assert assessment_payload["result_attachments"][0]["filename"] == "result.md"
