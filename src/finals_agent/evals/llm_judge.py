from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, Callable

from finals_agent.agent.runner import run_agent
from finals_agent.core.schemas import AgentRequest, CourseContext
from finals_agent.evals.grounded_qa import FIXTURE_ANSWERS, FakeGroundedAgent, _build_fixture_repository
from finals_agent.persistence.memory import InMemoryStore


@dataclass(frozen=True)
class LLMJudgeCase:
    name: str
    question: str
    reference_answer: str
    rubric: str
    expected_facts: tuple[str, ...]
    required_citations: tuple[str, ...]
    forbidden_substrings: tuple[str, ...] = ()
    min_score: float = 0.75
    target_title: str = "RAG Target Paper"
    conversation_id: str | None = None


@dataclass(frozen=True)
class JudgeDecision:
    score: float
    passed: bool
    feedback: str
    criteria: dict[str, Any]


@dataclass(frozen=True)
class LLMJudgeResult:
    name: str
    passed: bool
    reason: str
    answer: str
    score: float
    judge_feedback: str
    judge_metadata: dict[str, Any]
    metadata: dict[str, Any]


class DeterministicJudge:
    """Offline judge used for stable CI and regression tests."""

    def judge(self, case: LLMJudgeCase, answer: str) -> JudgeDecision:
        lowered = answer.lower()
        expected_hits = [item for item in case.expected_facts if item.lower() in lowered]
        missing_facts = [item for item in case.expected_facts if item.lower() not in lowered]
        missing_citations = [item for item in case.required_citations if item not in answer]
        forbidden = [item for item in case.forbidden_substrings if item.lower() in lowered]

        fact_score = len(expected_hits) / len(case.expected_facts) if case.expected_facts else 1.0
        citation_score = 0.0 if missing_citations else 1.0
        forbidden_score = 0.0 if forbidden else 1.0
        substance_score = 1.0 if len(answer.strip()) >= 40 else 0.0
        score = round((fact_score * 0.45) + (citation_score * 0.25) + (forbidden_score * 0.2) + (substance_score * 0.1), 4)

        failures = []
        if missing_facts:
            failures.append(f"Missing expected facts: {missing_facts}")
        if missing_citations:
            failures.append(f"Missing required citations: {missing_citations}")
        if forbidden:
            failures.append(f"Forbidden substrings present: {forbidden}")
        passed = score >= case.min_score and not missing_citations and not forbidden
        return JudgeDecision(
            score=score,
            passed=passed,
            feedback="passed" if not failures else "; ".join(failures),
            criteria={
                "fact_score": fact_score,
                "citation_score": citation_score,
                "forbidden_score": forbidden_score,
                "substance_score": substance_score,
                "missing_facts": missing_facts,
                "missing_citations": missing_citations,
                "forbidden": forbidden,
                "judge": "deterministic",
            },
        )


class LLMJudge:
    """LLM-as-judge wrapper with JSON validation and deterministic fallback."""

    def __init__(self, model=None, fallback: DeterministicJudge | None = None):
        self.model = model
        self.fallback = fallback or DeterministicJudge()

    def judge(self, case: LLMJudgeCase, answer: str) -> JudgeDecision:
        try:
            data = self._invoke(case, answer)
            decision = _decision_from_payload(data)
        except Exception as exc:
            decision = self.fallback.judge(case, answer)
            criteria = dict(decision.criteria)
            criteria["judge"] = "llm_fallback"
            criteria["judge_error"] = f"{exc.__class__.__name__}: {exc}"
            return JudgeDecision(
                score=decision.score,
                passed=decision.passed,
                feedback=decision.feedback,
                criteria=criteria,
            )

        hard_failures = _hard_failures(case, answer)
        if hard_failures:
            criteria = dict(decision.criteria)
            criteria["hard_failures"] = hard_failures
            return JudgeDecision(
                score=min(decision.score, 0.5),
                passed=False,
                feedback=f"{decision.feedback}; {'; '.join(hard_failures)}",
                criteria=criteria,
            )
        return decision

    def _invoke(self, case: LLMJudgeCase, answer: str) -> dict[str, Any]:
        payload = {
            "question": case.question,
            "answer": answer,
            "reference_answer": case.reference_answer,
            "rubric": case.rubric,
            "expected_facts": case.expected_facts,
            "required_citations": case.required_citations,
            "forbidden_substrings": case.forbidden_substrings,
            "output_schema": {
                "score": "float from 0 to 1",
                "passed": "boolean",
                "feedback": "short string",
                "criteria": "object with concise per-criterion notes",
            },
        }
        messages = [
            (
                "system",
                "You are an impartial evaluator for a paper-reading agent. "
                "Grade only factual grounding, citation support, and task completeness. "
                "Return only one valid JSON object matching output_schema.",
            ),
            ("human", json.dumps(payload, ensure_ascii=False)),
        ]
        response = self._get_model().invoke(messages)
        return _extract_json_object(getattr(response, "content", response))

    def _get_model(self):
        if self.model is None:
            from finals_agent.agent.llm import build_chat_model

            self.model = build_chat_model()
        return self.model


DEFAULT_LLM_JUDGE_CASES = (
    LLMJudgeCase(
        name="judge_method_grounding",
        question="Explain the method of the target RAG paper.",
        reference_answer="The method retrieves passages and conditions generation on retrieved evidence.",
        rubric="Reward answers that identify retrieval-conditioned generation and cite the target paper evidence.",
        expected_facts=("retrieves passages", "conditions generation"),
        required_citations=("[RAG Target Paper",),
    ),
    LLMJudgeCase(
        name="judge_limitation_grounding",
        question="What limitation does the target paper mention?",
        reference_answer="The target paper mentions additional latency and retrieval failure.",
        rubric="Reward answers that state only limitations supported by the target paper and include a citation.",
        expected_facts=("latency", "retrieval failure"),
        required_citations=("[RAG Target Paper",),
        forbidden_substrings=("oracle reranker",),
    ),
    LLMJudgeCase(
        name="judge_related_comparison",
        question="Compare the target paper innovation against related papers.",
        reference_answer="The target paper uses retrieval-conditioned generation; related RAG work also combines retrieval with generation.",
        rubric="Reward answers that separate local evidence from related-paper evidence and cite both.",
        expected_facts=("local evidence", "related", "RAG"),
        required_citations=("[RAG Target Paper", "[R1:"),
        forbidden_substrings=("unsupported state-of-the-art",),
    ),
)


def run_llm_judge_evals(
    cases: tuple[LLMJudgeCase, ...] = DEFAULT_LLM_JUDGE_CASES,
    use_real_model: bool = False,
    use_real_judge: bool = False,
    judge_model=None,
    build_fake_answers: Callable[[], dict[str, str]] | None = None,
) -> list[LLMJudgeResult]:
    with TemporaryDirectory() as tmp:
        repository = _build_fixture_repository(Path(tmp))
        answer_agent = None if use_real_model else FakeGroundedAgent((build_fake_answers or (lambda: FIXTURE_ANSWERS))())
        judge = LLMJudge(model=judge_model) if use_real_judge or judge_model is not None else DeterministicJudge()
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
                agent=answer_agent,
                memory_store=memory if case.conversation_id else None,
                max_verification_retries=0 if answer_agent is not None else 1,
            )
            decision = judge.judge(case, run_result.answer)
            results.append(_build_result(case, run_result.answer, run_result.metadata, decision))
        return results


def _build_result(
    case: LLMJudgeCase,
    answer: str,
    metadata: dict | None,
    decision: JudgeDecision,
) -> LLMJudgeResult:
    metadata = metadata or {}
    passed = decision.passed and decision.score >= case.min_score
    reason = "passed" if passed else f"score={decision.score:.2f} below min={case.min_score:.2f}; {decision.feedback}"
    return LLMJudgeResult(
        name=case.name,
        passed=passed,
        reason=reason,
        answer=answer,
        score=decision.score,
        judge_feedback=decision.feedback,
        judge_metadata=decision.criteria,
        metadata=metadata,
    )


def _decision_from_payload(data: dict[str, Any]) -> JudgeDecision:
    score = _clean_score(data.get("score"))
    passed = _clean_bool(data.get("passed"), default=score >= 0.75)
    feedback = _clean_string(data.get("feedback"), max_length=500) or "No judge feedback."
    criteria = data.get("criteria") if isinstance(data.get("criteria"), dict) else {}
    criteria = {str(key)[:80]: _json_safe(value) for key, value in criteria.items()}
    criteria["judge"] = "llm"
    return JudgeDecision(score=score, passed=passed, feedback=feedback, criteria=criteria)


def _hard_failures(case: LLMJudgeCase, answer: str) -> list[str]:
    lowered = answer.lower()
    failures = []
    missing_citations = [item for item in case.required_citations if item not in answer]
    forbidden = [item for item in case.forbidden_substrings if item.lower() in lowered]
    if missing_citations:
        failures.append(f"Missing required citations: {missing_citations}")
    if forbidden:
        failures.append(f"Forbidden substrings present: {forbidden}")
    return failures


def _extract_json_object(raw: Any) -> dict[str, Any]:
    text = str(raw).strip()
    if not text:
        raise ValueError("Judge model returned an empty response.")
    fenced = re.search(r"```(?:json)?\s*(?P<body>\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group("body")
    elif not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Judge model response did not contain a JSON object.")
        text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Judge model JSON must be an object.")
    return data


def _clean_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        raise ValueError("Judge score must be numeric.")
    if not 0 <= score <= 1:
        raise ValueError("Judge score must be between 0 and 1.")
    return score


def _clean_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _clean_string(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length]


def _json_safe(value: Any) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value[:20]]
    if isinstance(value, dict):
        return {str(key)[:80]: _json_safe(item) for key, item in list(value.items())[:20]}
    return str(value)[:240]


class FakeJudgeModel:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return SimpleNamespace(content=json.dumps(self.payload))
