from types import SimpleNamespace

from finals_agent.agent.planning import RuleBasedTaskPlanner
from finals_agent.agent.query_rewrite import RetrievalQueryRewriter
from finals_agent.core.schemas import AgentRequest, CourseContext


def test_deterministic_query_rewrite_adds_target_and_research_terms():
    request = AgentRequest(
        question="请解释一下这篇论文的方法为什么有效",
        course_context=CourseContext(title="Speculative Decoding"),
    )
    plan = RuleBasedTaskPlanner().plan(request, request.course_context)

    rewrite = RetrievalQueryRewriter().rewrite(request, plan, "empty_retrieval")

    assert "Speculative Decoding" in rewrite.rewritten_query
    assert all(term in rewrite.rewritten_query for term in ("method", "approach", "mechanism"))
    assert all(term in rewrite.rewritten_query for term in ("evidence", "analysis", "conclusion"))
    assert rewrite.strategy == "deterministic"


def test_model_query_rewrite_uses_compact_json_query():
    class Model:
        def invoke(self, messages):
            return SimpleNamespace(content='{"query":"acceptance rate speedup experiment results"}')

    request = AgentRequest(question="为什么它更快")
    plan = RuleBasedTaskPlanner().plan(request)

    rewrite = RetrievalQueryRewriter(Model()).rewrite(
        request,
        plan,
        "citation_verification_failed",
    )

    assert rewrite.rewritten_query == "acceptance rate speedup experiment results"
    assert rewrite.strategy == "model"
