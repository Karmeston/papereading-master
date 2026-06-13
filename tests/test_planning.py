import json
from types import SimpleNamespace

from finals_agent.agent.planning import HybridTaskPlanner, LLMTaskPlanner, RuleBasedTaskPlanner, build_task_planner
from finals_agent.core.config import load_settings
from finals_agent.core.schemas import AgentRequest, CourseContext, TaskType


def test_planner_detects_related_work_discovery():
    plan = RuleBasedTaskPlanner().plan(
        AgentRequest(
            question="按这篇论文主题查找相近论文",
            course_context=CourseContext(course="machine learning"),
        )
    )

    assert plan.intent.task_type == TaskType.RELATED_WORK_DISCOVERY
    assert plan.intent.requires_retrieval is True
    assert "search_local_papers" in plan.intent.preferred_tools
    assert "search_related_papers" in plan.intent.preferred_tools
    assert "discover_research_papers" in plan.intent.preferred_tools
    assert plan.intent.field == "machine learning"
    assert plan.intent.needs_related_search is True
    assert plan.intent.evidence_scope == "local+external"
    assert plan.intent.confidence == 0.88


def test_planner_only_selects_arxiv_import_for_explicit_download_request():
    plan = RuleBasedTaskPlanner().plan(
        AgentRequest(question="下载并导入这篇 arXiv 论文")
    )

    assert plan.intent.preferred_tools == ("import_arxiv_paper",)
    assert plan.intent.requires_retrieval is False


def test_planner_detects_innovation_comparison():
    plan = RuleBasedTaskPlanner().plan(AgentRequest(question="总结创新点并和相关论文比较不同"))

    assert plan.intent.task_type == TaskType.INNOVATION_COMPARISON
    assert plan.intent.requires_retrieval is True
    assert "compare_paper_innovations" in plan.intent.preferred_tools
    assert plan.intent.needs_related_search is True
    assert plan.intent.confidence == 0.85


def test_planner_detects_explicit_paper_code_correspondence_check():
    plan = RuleBasedTaskPlanner().plan(
        AgentRequest(question="检查论文与代码对应，哪些算法步骤没有实现")
    )

    assert plan.intent.preferred_tools == ("check_paper_code_correspondence",)
    assert plan.intent.confidence == 0.91


def test_planner_detects_structure_analysis():
    plan = RuleBasedTaskPlanner().plan(AgentRequest(question="识别这篇论文的章节结构和段落"))

    assert plan.intent.task_type == TaskType.STRUCTURE_ANALYSIS
    assert plan.intent.requires_retrieval is True
    assert plan.intent.preferred_tools == ("analyze_paper_structure",)
    assert plan.intent.confidence == 0.78


def test_planner_detects_figure_table_formula_explanation():
    plan = RuleBasedTaskPlanner().plan(AgentRequest(question="解释论文里的 Figure 2"))

    assert plan.intent.task_type == TaskType.FIGURE_TABLE_EXPLANATION
    assert plan.intent.requires_retrieval is True
    assert "analyze_paper_structure" in plan.intent.preferred_tools
    assert plan.intent.target_artifact == "Figure 2"
    assert plan.intent.needs_vision is True
    assert plan.intent.confidence == 0.92
    assert plan.slots["artifact_kind"] == "figure"


def test_planner_extracts_table_artifact_and_output_style():
    plan = RuleBasedTaskPlanner().plan(AgentRequest(question="把 Table 3 的结果整理成表格"))

    assert plan.intent.task_type == TaskType.FIGURE_TABLE_EXPLANATION
    assert plan.intent.target_artifact == "Table 3"
    assert plan.intent.output_style == "table"
    assert plan.intent.needs_vision is True


def test_planner_extracts_section_and_title():
    plan = RuleBasedTaskPlanner().plan(AgentRequest(question="总结《RAG Paper》的 method 部分，要点列出"))

    assert plan.intent.task_type == TaskType.PAPER_EXPLANATION
    assert plan.intent.target_title == "RAG Paper"
    assert plan.intent.target_section == "method"
    assert plan.intent.output_style == "bullets"
    assert plan.slots["target_title"] == "RAG Paper"


def test_planner_falls_back_to_general_chat():
    plan = RuleBasedTaskPlanner().plan(AgentRequest(question="你好"))

    assert plan.intent.task_type == TaskType.GENERAL_CHAT
    assert plan.intent.confidence < 0.5
    assert plan.to_dict()["slots"] == {}


def test_planner_explanation_beats_broad_paper_search():
    plan = RuleBasedTaskPlanner().plan(AgentRequest(question="解释一下这篇论文"))

    assert plan.intent.task_type == TaskType.PAPER_EXPLANATION
    assert plan.intent.confidence == 0.72


def test_planner_broad_paper_search_is_low_confidence():
    plan = RuleBasedTaskPlanner().plan(AgentRequest(question="search paper about retrieval"))

    assert plan.intent.task_type == TaskType.PAPER_SEARCH
    assert plan.intent.confidence == 0.55


class FakePlannerModel:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return SimpleNamespace(content=json.dumps(self.payload))


def test_llm_task_planner_parses_schema_validated_plan():
    model = FakePlannerModel(
        {
            "task_type": "figure_table_explanation",
            "requires_retrieval": True,
            "preferred_tools": ["explain_paper_target", "search_local_papers", "unknown_tool"],
            "topic": "analyze ablation table",
            "course": "nlp",
            "target_document_id": "doc-1",
            "target_title": "RAG Paper",
            "target_artifact": "Table 2",
            "target_section": "results",
            "output_style": "table",
            "evidence_scope": "local+vision",
            "needs_vision": True,
            "needs_related_search": False,
            "clarification_needed": False,
            "clarification_question": None,
            "confidence": 0.88,
            "rationale": "The request asks for a specific table.",
            "slots": {"artifact_kind": "table"},
        }
    )

    plan = LLMTaskPlanner(model=model).plan(AgentRequest(question="explain Table 2"))

    assert plan.intent.task_type == TaskType.FIGURE_TABLE_EXPLANATION
    assert plan.intent.target_artifact == "Table 2"
    assert plan.intent.needs_vision is True
    assert plan.intent.output_style == "table"
    assert plan.intent.preferred_tools == ("explain_paper_target", "search_local_papers")
    assert plan.slots["artifact_kind"] == "table"


def test_hybrid_task_planner_keeps_high_confidence_rule_plan():
    model = FakePlannerModel({"task_type": "general_chat"})
    plan = HybridTaskPlanner(confidence_threshold=0.75, llm_planner=LLMTaskPlanner(model=model)).plan(
        AgentRequest(question="explain Figure 2")
    )

    assert plan.intent.task_type == TaskType.FIGURE_TABLE_EXPLANATION
    assert plan.intent.target_artifact == "Figure 2"
    assert plan.slots["planner"] == "rule"
    assert model.calls == 0


def test_hybrid_task_planner_uses_llm_for_low_confidence_rule_plan():
    model = FakePlannerModel(
        {
            "task_type": "paper_explanation",
            "requires_retrieval": True,
            "preferred_tools": ["search_local_papers", "analyze_paper_structure"],
            "topic": "attention mechanism",
            "course": "machine learning",
            "evidence_scope": "local",
            "needs_vision": False,
            "needs_related_search": False,
            "clarification_needed": False,
            "confidence": 0.86,
            "rationale": "The request asks for a paper-grounded explanation.",
            "slots": {},
        }
    )

    plan = HybridTaskPlanner(confidence_threshold=0.75, llm_planner=LLMTaskPlanner(model=model)).plan(
        AgentRequest(question="could you help me understand the attention idea?")
    )

    assert plan.intent.task_type == TaskType.PAPER_EXPLANATION
    assert plan.intent.confidence == 0.86
    assert plan.slots["planner"] == "llm"
    assert model.calls == 1


def test_hybrid_task_planner_uses_llm_for_medium_confidence_explanation_by_default():
    model = FakePlannerModel(
        {
            "task_type": "paper_explanation",
            "requires_retrieval": True,
            "preferred_tools": ["read_paper_workflow"],
            "topic": "target paper",
            "course": "nlp",
            "evidence_scope": "local",
            "needs_vision": False,
            "needs_related_search": False,
            "clarification_needed": False,
            "confidence": 0.83,
            "rationale": "Use full-paper workflow.",
            "slots": {},
        }
    )

    plan = HybridTaskPlanner(llm_planner=LLMTaskPlanner(model=model)).plan(
        AgentRequest(question="解释一下这篇论文", course_context=CourseContext(course="nlp"))
    )

    assert plan.intent.task_type == TaskType.PAPER_EXPLANATION
    assert plan.slots["planner"] == "llm"
    assert model.calls == 1


def test_hybrid_task_planner_falls_back_to_rule_when_llm_payload_is_invalid():
    model = FakePlannerModel({"task_type": "not_a_real_task"})
    plan = HybridTaskPlanner(confidence_threshold=0.75, llm_planner=LLMTaskPlanner(model=model)).plan(
        AgentRequest(question="hello")
    )

    assert plan.intent.task_type == TaskType.GENERAL_CHAT
    assert plan.slots["planner"] == "hybrid_fallback"
    assert "fallback_error" in plan.slots


def test_build_task_planner_uses_configured_provider():
    settings = load_settings(
        env={
            "LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "sk-test",
            "PLANNER_PROVIDER": "hybrid",
            "PLANNER_CONFIDENCE_THRESHOLD": "0.65",
        }
    )

    planner = build_task_planner(settings=settings, model=FakePlannerModel({"task_type": "general_chat"}))

    assert isinstance(planner, HybridTaskPlanner)
    assert planner.confidence_threshold == 0.65
