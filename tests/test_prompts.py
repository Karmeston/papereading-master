from finals_agent.agent.prompts import build_system_prompt
from finals_agent.core.runtime import AgentRuntime
from finals_agent.core.schemas import CourseContext, ReviewMode


def test_system_prompt_contains_core_tool_rules():
    prompt = build_system_prompt()

    assert "优先调用本地论文检索" in prompt
    assert "不要凭空声称看过某篇论文" in prompt
    assert "默认使用中文回答" in prompt


def test_system_prompt_includes_research_context():
    runtime = AgentRuntime(
        course_context=CourseContext(
            course="machine learning",
            chapter="method section",
            review_mode=ReviewMode.DEEP_READING,
            goal="prepare paper discussion",
        )
    )

    prompt = build_system_prompt(runtime)

    assert "当前研究领域：machine learning" in prompt
    assert "当前阅读焦点：method section" in prompt
    assert "当前目标：prepare paper discussion" in prompt
    assert "精读" in prompt


def test_review_modes_have_distinct_prompt_text():
    normal = build_system_prompt(
        AgentRuntime(course_context=CourseContext(review_mode=ReviewMode.NORMAL))
    )
    comparison = build_system_prompt(
        AgentRuntime(course_context=CourseContext(review_mode=ReviewMode.COMPARISON))
    )

    assert "常规阅读" in normal
    assert "对比阅读" in comparison
    assert normal != comparison
