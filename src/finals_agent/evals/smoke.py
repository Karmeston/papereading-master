from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable

from finals_agent.agent.runner import run_agent
from finals_agent.core.schemas import AgentRequest, CourseContext


@dataclass(frozen=True)
class EvalCase:
    name: str
    request: AgentRequest
    expected_substrings: tuple[str, ...] = ()
    min_message_count: int = 1


@dataclass(frozen=True)
class EvalResult:
    name: str
    passed: bool
    reason: str
    answer: str
    metadata: dict


class FakeEvalAgent:
    def __init__(self, answer: str):
        self.answer = answer

    def invoke(self, payload):
        user_message = payload["messages"][-1]["content"]
        return {
            "messages": [
                SimpleNamespace(content=user_message),
                SimpleNamespace(content=self.answer),
            ]
        }


DEFAULT_EVAL_CASES = (
    EvalCase(
        name="paper_explanation_request",
        request=AgentRequest(
            question="Explain the method section of this retrieval paper.",
            course_context=CourseContext(course="nlp"),
        ),
        expected_substrings=("method", "retrieval"),
        min_message_count=2,
    ),
    EvalCase(
        name="related_work_request",
        request=AgentRequest(
            question="Find related papers about retrieval augmented generation.",
            course_context=CourseContext(course="nlp"),
        ),
        expected_substrings=("related", "retrieval"),
        min_message_count=2,
    ),
)


def run_smoke_evals(
    cases: tuple[EvalCase, ...] = DEFAULT_EVAL_CASES,
    build_fake_answer: Callable[[EvalCase], str] | None = None,
) -> list[EvalResult]:
    build_fake_answer = build_fake_answer or _default_fake_answer
    results = []
    for case in cases:
        agent = FakeEvalAgent(build_fake_answer(case))
        run_result = run_agent(
            request=case.request,
            runtime=None,
            repository=None,
            agent=agent,
        )
        results.append(_score_case(case, run_result.answer, run_result.metadata))
    return results


def _score_case(case: EvalCase, answer: str, metadata: dict | None) -> EvalResult:
    metadata = metadata or {}
    missing = [text for text in case.expected_substrings if text.lower() not in answer.lower()]
    message_count = metadata.get("message_count", 0)

    if missing:
        return EvalResult(
            name=case.name,
            passed=False,
            reason=f"Missing expected substrings: {missing}",
            answer=answer,
            metadata=metadata,
        )
    if message_count < case.min_message_count:
        return EvalResult(
            name=case.name,
            passed=False,
            reason=f"Expected at least {case.min_message_count} messages, got {message_count}.",
            answer=answer,
            metadata=metadata,
        )
    return EvalResult(
        name=case.name,
        passed=True,
        reason="passed",
        answer=answer,
        metadata=metadata,
    )


def _default_fake_answer(case: EvalCase) -> str:
    return f"Smoke answer for {case.request.question}"
