from finals_agent.evals.smoke import DEFAULT_EVAL_CASES, EvalCase, run_smoke_evals
from finals_agent.evals.grounded_qa import (
    DEFAULT_GROUNDED_QA_CASES,
    GroundedQACase,
    run_grounded_qa_evals,
)
from finals_agent.evals.llm_judge import (
    DEFAULT_LLM_JUDGE_CASES,
    FakeJudgeModel,
    LLMJudgeCase,
    run_llm_judge_evals,
)
from finals_agent.core.schemas import AgentRequest


def test_default_smoke_evals_pass():
    results = run_smoke_evals()

    assert len(results) == len(DEFAULT_EVAL_CASES)
    assert all(result.passed for result in results)
    assert all(result.metadata["trace"]["status"] == "success" for result in results)


def test_smoke_eval_reports_missing_substring():
    case = EvalCase(
        name="missing_expected_text",
        request=AgentRequest(question="hello"),
        expected_substrings=("not-present",),
    )

    results = run_smoke_evals(
        cases=(case,),
        build_fake_answer=lambda _: "plain answer",
    )

    assert len(results) == 1
    assert not results[0].passed
    assert "Missing expected substrings" in results[0].reason


def test_default_grounded_qa_evals_pass_with_fixture_agent():
    results = run_grounded_qa_evals()

    assert len(results) == len(DEFAULT_GROUNDED_QA_CASES)
    assert all(result.passed for result in results)
    assert all(result.score == 1.0 for result in results)
    assert all("[RAG Target Paper" in result.answer for result in results)


def test_grounded_qa_eval_reports_missing_citation_and_forbidden_text():
    case = GroundedQACase(
        name="bad_answer",
        question="Explain the method of the target RAG paper.",
        expected_substrings=("retrieves passages",),
        required_citations=("[RAG Target Paper",),
        forbidden_substrings=("BetaMemory",),
    )

    results = run_grounded_qa_evals(
        cases=(case,),
        build_fake_answers=lambda: {
            "Explain the method of the target RAG paper.": "BetaMemory retrieves passages without citation."
        },
    )

    assert len(results) == 1
    assert not results[0].passed
    assert results[0].score < 1
    assert "Missing required citations" in results[0].reason
    assert "Forbidden substrings" in results[0].reason


def test_default_llm_judge_evals_pass_with_deterministic_judge():
    results = run_llm_judge_evals()

    assert len(results) == len(DEFAULT_LLM_JUDGE_CASES)
    assert all(result.passed for result in results)
    assert all(result.score >= 0.75 for result in results)
    assert all(result.judge_metadata["judge"] == "deterministic" for result in results)


def test_llm_judge_eval_reports_bad_answer():
    case = LLMJudgeCase(
        name="bad_judged_answer",
        question="Explain the method of the target RAG paper.",
        reference_answer="The method retrieves passages and conditions generation.",
        rubric="Must mention the method and cite the target paper.",
        expected_facts=("retrieves passages", "conditions generation"),
        required_citations=("[RAG Target Paper",),
        forbidden_substrings=("BetaMemory",),
    )

    results = run_llm_judge_evals(
        cases=(case,),
        build_fake_answers=lambda: {
            "Explain the method of the target RAG paper.": "BetaMemory is a better method without citation."
        },
    )

    assert len(results) == 1
    assert not results[0].passed
    assert results[0].score < 0.75
    assert "Missing expected facts" in results[0].judge_feedback
    assert "Missing required citations" in results[0].judge_feedback


def test_llm_judge_eval_uses_valid_json_judge_model():
    judge_model = FakeJudgeModel(
        {
            "score": 0.91,
            "passed": True,
            "feedback": "The answer is grounded and cited.",
            "criteria": {"grounding": "supported", "citations": "present"},
        }
    )

    results = run_llm_judge_evals(
        cases=(DEFAULT_LLM_JUDGE_CASES[0],),
        use_real_judge=True,
        judge_model=judge_model,
    )

    assert len(results) == 1
    assert results[0].passed
    assert results[0].score == 0.91
    assert results[0].judge_metadata["judge"] == "llm"
    assert judge_model.calls == 1


def test_llm_judge_hard_fails_missing_required_citation_even_if_model_passes():
    case = LLMJudgeCase(
        name="judge_hard_fail",
        question="Explain the method of the target RAG paper.",
        reference_answer="The method retrieves passages and conditions generation.",
        rubric="Must cite the target paper.",
        expected_facts=("retrieves passages",),
        required_citations=("[RAG Target Paper",),
    )
    judge_model = FakeJudgeModel(
        {
            "score": 1.0,
            "passed": True,
            "feedback": "Looks good.",
            "criteria": {},
        }
    )

    results = run_llm_judge_evals(
        cases=(case,),
        use_real_judge=True,
        judge_model=judge_model,
        build_fake_answers=lambda: {
            "Explain the method of the target RAG paper.": "The method retrieves passages and conditions generation."
        },
    )

    assert len(results) == 1
    assert not results[0].passed
    assert results[0].score <= 0.5
    assert "hard_failures" in results[0].judge_metadata
