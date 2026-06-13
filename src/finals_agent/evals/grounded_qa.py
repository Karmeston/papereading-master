from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Callable

from finals_agent.agent.runner import run_agent
from finals_agent.core.schemas import AgentRequest, CourseContext, DocumentType
from finals_agent.data.external_search import ExternalPaper
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository
from finals_agent.persistence.memory import InMemoryStore


@dataclass(frozen=True)
class GroundedQACase:
    name: str
    question: str
    expected_substrings: tuple[str, ...]
    required_citations: tuple[str, ...]
    forbidden_substrings: tuple[str, ...] = ()
    target_title: str = "RAG Target Paper"
    conversation_id: str | None = None


@dataclass(frozen=True)
class GroundedQAResult:
    name: str
    passed: bool
    reason: str
    answer: str
    score: float
    metadata: dict


class FakeGroundedAgent:
    def __init__(self, answers: dict[str, str]):
        self.answers = answers

    def invoke(self, payload):
        question = payload["messages"][-1]["content"]
        answer = self.answers.get(question, "No fixture answer.")
        return {"messages": [SimpleNamespace(content=question), SimpleNamespace(content=answer)]}


class FakeRelatedSearch:
    def search(self, query: str, limit: int = 5):
        return (
            ExternalPaper(
                title="Retrieval-Augmented Generation for Knowledge-Intensive NLP",
                authors=("Patrick Lewis",),
                summary="RAG combines parametric generation with non-parametric retrieval memory.",
                url="https://arxiv.org/abs/2005.11401",
                published="2020-05-22",
                categories=("cs.CL",),
            ),
        )[:limit]


DEFAULT_GROUNDED_QA_CASES = (
    GroundedQACase(
        name="method_grounding",
        question="Explain the method of the target RAG paper.",
        expected_substrings=("retrieves passages", "conditions generation"),
        required_citations=("[RAG Target Paper",),
        forbidden_substrings=("BetaMemory",),
    ),
    GroundedQACase(
        name="limitation_grounding",
        question="What limitation does the target paper mention?",
        expected_substrings=("latency", "retrieval failure"),
        required_citations=("[RAG Target Paper",),
        forbidden_substrings=("oracle reranker",),
    ),
    GroundedQACase(
        name="comparison_grounding",
        question="Compare the target paper innovation against related papers.",
        expected_substrings=("local evidence", "related", "RAG"),
        required_citations=("[RAG Target Paper", "[R1:"),
        forbidden_substrings=("unsupported state-of-the-art",),
    ),
)


FIXTURE_ANSWERS = {
    "Explain the method of the target RAG paper.": (
        "The method retrieves passages and conditions generation on the retrieved evidence "
        "[RAG Target Paper | section=2 Method | chunk=fixture-method]."
    ),
    "What limitation does the target paper mention?": (
        "The paper mentions additional latency and retrieval failure as limitations "
        "[RAG Target Paper | section=4 Discussion | chunk=fixture-limits]."
    ),
    "Compare the target paper innovation against related papers.": (
        "Using local evidence, the target RAG paper focuses on retrieval-conditioned generation "
        "[RAG Target Paper | section=2 Method | chunk=fixture-method]. "
        "A related RAG paper also combines retrieval with generation [R1: Retrieval-Augmented Generation for Knowledge-Intensive NLP | 2020-05-22 | https://arxiv.org/abs/2005.11401]."
    ),
}


def run_grounded_qa_evals(
    cases: tuple[GroundedQACase, ...] = DEFAULT_GROUNDED_QA_CASES,
    use_real_model: bool = False,
    build_fake_answers: Callable[[], dict[str, str]] | None = None,
) -> list[GroundedQAResult]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        repository = _build_fixture_repository(root)
        fake_agent = None if use_real_model else FakeGroundedAgent((build_fake_answers or (lambda: FIXTURE_ANSWERS))())
        memory = InMemoryStore()
        results = []
        for case in cases:
            run_result = run_agent(
                request=AgentRequest(
                    question=case.question,
                    course_context=CourseContext(field="nlp", title=case.target_title),
                    conversation_id=case.conversation_id,
                ),
                repository=repository,
                agent=fake_agent,
                memory_store=memory if case.conversation_id else None,
                max_verification_retries=0 if fake_agent is not None else 1,
            )
            results.append(_score_case(case, run_result.answer, run_result.metadata))
        return results


def _score_case(case: GroundedQACase, answer: str, metadata: dict | None) -> GroundedQAResult:
    metadata = metadata or {}
    checks = []
    missing = [item for item in case.expected_substrings if item.lower() not in answer.lower()]
    missing_citations = [item for item in case.required_citations if item not in answer]
    forbidden = [item for item in case.forbidden_substrings if item.lower() in answer.lower()]
    checks.append(("expected", not missing, f"Missing expected substrings: {missing}"))
    checks.append(("citations", not missing_citations, f"Missing required citations: {missing_citations}"))
    checks.append(("forbidden", not forbidden, f"Forbidden substrings present: {forbidden}"))
    passed_checks = [name for name, ok, _ in checks if ok]
    failed = [reason for _, ok, reason in checks if not ok]
    score = len(passed_checks) / len(checks)
    return GroundedQAResult(
        name=case.name,
        passed=not failed,
        reason="passed" if not failed else "; ".join(failed),
        answer=answer,
        score=score,
        metadata=metadata,
    )


def _build_fixture_repository(root: Path) -> StudyRepository:
    repository = StudyRepository(index_path=root / "index.json", raw_data_dir=root / "raw")
    target = root / "rag_target.md"
    target.write_text(
        "\n\n".join(
            [
                "Abstract",
                "RAG improves factual grounding by retrieval-conditioned generation.",
                "1 Introduction",
                "The problem is hallucination in knowledge-intensive tasks.",
                "2 Method",
                "The method retrieves passages and conditions generation on the retrieved evidence.",
                "3 Experiments",
                "Experiments compare retrieval baselines on benchmark datasets.",
                "4 Discussion",
                "A limitation is additional latency and retrieval failure.",
            ]
        ),
        encoding="utf-8",
    )
    distractor = root / "distractor.md"
    distractor.write_text(
        "Abstract\n\nBetaMemory uses an oracle reranker and claims unsupported state-of-the-art results.",
        encoding="utf-8",
    )
    ingest_material(
        build_ingest_request(target, DocumentType.PAPER, field="nlp", title="RAG Target Paper"),
        repository=repository,
    )
    ingest_material(
        build_ingest_request(distractor, DocumentType.PAPER, field="nlp", title="Distractor Paper"),
        repository=repository,
    )
    return repository
