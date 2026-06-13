from pathlib import Path
from types import SimpleNamespace
import json

from finals_agent.core.schemas import (
    DocumentType,
    SearchRequest,
    SearchResponse,
    SearchResult,
    StudyDocument,
)
from finals_agent.data.reading_intelligence import (
    ReadingIntelligence,
    _clean_extracted_text,
    _normalized_section_label,
    _select_complete_sentences,
)


class FakeModel:
    def __init__(self, payload):
        self.payload = payload
        self.messages = []

    def invoke(self, messages):
        self.messages.append(messages)
        return SimpleNamespace(content=json.dumps(self.payload, ensure_ascii=False))


class FakeStreamingModel:
    def stream(self, messages):
        self.messages = messages
        yield SimpleNamespace(content="【核心结论】\n")
        yield SimpleNamespace(content="这是逐步生成的深入报告。")


class RecordingRetriever:
    def __init__(self, result):
        self.result = result
        self.queries = []

    def search(self, request: SearchRequest):
        self.queries.append(request.query)
        return SearchResponse(
            request=request,
            results=(self.result,),
            metadata={"retriever": "RecordingRetriever"},
        )


def _document() -> StudyDocument:
    return StudyDocument(
        id="doc-1",
        title="Target Paper",
        document_type=DocumentType.PAPER,
        course="nlp",
        path=Path("paper.md"),
        chapter="retrieval",
    )


def _evidence() -> dict:
    return {
        "id": "doc-1",
        "title": "Target Paper",
        "field": "nlp",
        "snippet": "The method retrieves evidence before generation.",
        "score": 1.0,
        "chunk_id": "doc-1-2",
        "page": 2,
        "section": "2 Method",
        "citation": "[Target Paper | section=2 Method | page=2 | chunk=doc-1-2]",
    }


def test_synthesis_keeps_only_sections_with_allowed_citations():
    citation = _evidence()["citation"]
    model = FakeModel(
        {
            "one_sentence_summary": {"text": "论文先检索再生成。", "citations": [citation]},
            "core_problem": {"text": "模型声称解决幻觉。", "citations": ["[invented]"]},
            "method": {"text": "先检索证据，再生成答案。", "citations": [citation]},
        }
    )

    result = ReadingIntelligence(model).synthesize(
        paper=_document().to_dict(),
        section_passes=[{"role": "method", "evidence": [_evidence()]}],
        evidence=[],
        coverage={"covered_count": 1, "total_count": 1},
    )

    sections = {item["key"]: item for item in result["sections"]}
    assert sections["method"]["supported"] is True
    assert citation not in sections["method"]["text"]
    assert sections["method"]["citations"] == [citation]
    assert sections["core_problem"]["supported"] is False
    assert "模型声称解决幻觉" not in sections["core_problem"]["text"]
    assert result["citation_check"]["passed"] is False


def test_search_rewrites_intent_and_merges_multi_query_results():
    model = FakeModel(
        {
            "intent": "寻找方法如何使用外部证据",
            "queries": ["retrieval evidence", "grounded generation"],
        }
    )
    result = SearchResult(
        document_id="doc-1",
        title="Target Paper",
        document_type=DocumentType.PAPER,
        course="nlp",
        path=Path("paper.md"),
        snippet="The method retrieves evidence before generation.",
        score=0.7,
        chunk_id="doc-1-2",
        page=2,
        section="2 Method",
    )
    retriever = RecordingRetriever(result)

    response = ReadingIntelligence(model).search(
        "它如何找到可靠信息？",
        retriever,
        document=_document(),
        limit=5,
    )

    assert retriever.queries == ["它如何找到可靠信息？", "retrieval evidence", "grounded generation"]
    assert response["intent"] == "寻找方法如何使用外部证据"
    assert len(response["results"]) == 1
    assert response["results"][0]["query_match_count"] == 3
    assert response["results"][0]["citation"]


def test_report_stream_requests_long_grounded_output():
    model = FakeStreamingModel()
    citation = _evidence()["citation"]
    intelligence = ReadingIntelligence(model)

    context = intelligence.report_context(
        paper=_document().to_dict(),
        section_passes=[{"role": "method", "evidence": [_evidence()]}],
        evidence=[],
        coverage={"covered_count": 1, "total_count": 1},
    )
    output = "".join(intelligence.stream_report(context))

    assert output == "【核心结论】\n这是逐步生成的深入报告。"
    assert "3000" in model.messages[0][1]
    assert citation in model.messages[1][1]


def test_evidence_passage_repairs_line_wraps_and_keeps_complete_sentences():
    raw = (
        "[page 3]\n"
        "Fast Inference from Transformers via Speculative Decoding\n"
        "An unrelated sentence. The approxi-\n"
        "mation model proposes several tokens in parallel. "
        "The target model verifies those tokens without changing the distribution."
    )

    cleaned = _clean_extracted_text(raw)
    passage = _select_complete_sentences(cleaned, ("approximation model parallel tokens",))

    assert "approximation model" in passage
    assert "approxi-" not in passage
    assert not cleaned.startswith("Fast Inference from Transformers")
    assert passage[-1] in ".!?"


def test_invalid_body_text_is_not_exposed_as_section_name():
    assert _normalized_section_label("method can accelerate existing off-the-shelf mod-") is None
    assert _normalized_section_label("2.3 Speculative Sampling") == "2.3 Speculative Sampling"
