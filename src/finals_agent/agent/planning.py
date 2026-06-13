from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
import json
import re

from finals_agent.agent.tool_registry import (
    ANALYZE_RESEARCH_MATERIALS,
    ANALYZE_PAPER_STRUCTURE,
    CHECK_PAPER_CODE_CORRESPONDENCE,
    COMPARE_PAPER_INNOVATIONS,
    DISCOVER_RESEARCH_PAPERS,
    EXPLAIN_PAPER_TARGET,
    GET_READING_STATE,
    IMPORT_ARXIV_PAPER,
    INTELLIGENT_SEARCH_LOCAL_EVIDENCE,
    LIST_PAPERS,
    READ_PAPER_WORKFLOW,
    SEARCH_LOCAL_PAPERS,
    SEARCH_RELATED_PAPERS,
    UPDATE_READING_STATE,
    allowed_tool_names,
)
from finals_agent.core.config import Settings, load_settings
from finals_agent.core.schemas import AgentRequest, CourseContext, TaskIntent, TaskPlan, TaskType


class TaskPlanner(ABC):
    @abstractmethod
    def plan(self, request: AgentRequest, context: CourseContext | None = None) -> TaskPlan:
        raise NotImplementedError


class RuleBasedTaskPlanner(TaskPlanner):
    """Deterministic structured planner for paper-reading tasks."""

    def plan(self, request: AgentRequest, context: CourseContext | None = None) -> TaskPlan:
        text = request.question.strip()
        lowered = text.lower()
        context = context or request.course_context or CourseContext()
        slots = _extract_slots(text, lowered, context)
        intent = self._classify(text=text, lowered=lowered, context=context, slots=slots)
        return TaskPlan(intent=intent, steps=_steps_for(intent), slots=slots)

    def _classify(self, text: str, lowered: str, context: CourseContext, slots: dict) -> TaskIntent:
        base = {
            "topic": _rough_topic(text, slots),
            "course": context.field,
            "target_document_id": context.target_document_id,
            "target_title": slots.get("target_title") or context.target_title,
            "target_artifact": slots.get("target_artifact"),
            "target_section": slots.get("target_section"),
            "output_style": slots.get("output_style"),
        }
        if (
            _contains_any(text, lowered, ("下载", "导入", "download", "import"))
            and _contains_any(text, lowered, ("论文", "arxiv", "paper"))
        ):
            return TaskIntent(
                task_type=TaskType.PAPER_SEARCH,
                requires_retrieval=False,
                preferred_tools=(IMPORT_ARXIV_PAPER,),
                evidence_scope="external",
                confidence=0.93,
                rationale="Detected an explicit request to download or import an arXiv paper.",
                **base,
            )
        if _contains_any(
            text,
            lowered,
            (
                "论文与代码对应",
                "代码对应检查",
                "复现检查",
                "实现了论文",
                "paper code correspondence",
                "implementation audit",
            ),
        ):
            return TaskIntent(
                task_type=TaskType.INNOVATION_COMPARISON,
                requires_retrieval=True,
                preferred_tools=(CHECK_PAPER_CODE_CORRESPONDENCE,),
                evidence_scope="local",
                confidence=0.91,
                rationale="Detected an explicit paper-to-code correspondence audit request.",
                **base,
            )
        if slots.get("target_artifact"):
            return TaskIntent(
                task_type=TaskType.FIGURE_TABLE_EXPLANATION,
                requires_retrieval=True,
                preferred_tools=(
                    ANALYZE_PAPER_STRUCTURE,
                    EXPLAIN_PAPER_TARGET,
                    INTELLIGENT_SEARCH_LOCAL_EVIDENCE,
                ),
                evidence_scope="local+vision",
                needs_vision=slots.get("artifact_kind") in {"figure", "table"},
                confidence=0.92,
                rationale="Detected explicit figure/table/equation target.",
                **base,
            )
        if _contains_any(
            text,
            lowered,
            ("相近论文", "相似论文", "related paper", "similar paper", "arxiv"),
        ):
            return TaskIntent(
                task_type=TaskType.RELATED_WORK_DISCOVERY,
                requires_retrieval=True,
                preferred_tools=(
                    DISCOVER_RESEARCH_PAPERS,
                    SEARCH_LOCAL_PAPERS,
                    SEARCH_RELATED_PAPERS,
                ),
                evidence_scope="local+external",
                needs_related_search=True,
                confidence=0.88,
                rationale="Detected related-paper discovery intent.",
                **base,
            )
        if _contains_any(
            text,
            lowered,
            ("创新点", "不同", "区别", "对比", "贡献", "novelty", "innovation", "difference", "compare"),
        ):
            return TaskIntent(
                task_type=TaskType.INNOVATION_COMPARISON,
                requires_retrieval=True,
                preferred_tools=(
                    INTELLIGENT_SEARCH_LOCAL_EVIDENCE,
                    COMPARE_PAPER_INNOVATIONS,
                    ANALYZE_RESEARCH_MATERIALS,
                ),
                evidence_scope="local+external",
                needs_related_search=True,
                confidence=0.85,
                rationale="Detected innovation comparison intent.",
                **base,
            )
        if _contains_any(
            text,
            lowered,
            ("阅读进度", "读到哪里", "笔记", "待验证", "复习卡片", "flashcard", "note", "progress"),
        ):
            return TaskIntent(
                task_type=TaskType.PAPER_EXPLANATION,
                requires_retrieval=False,
                preferred_tools=(GET_READING_STATE, UPDATE_READING_STATE),
                evidence_scope="local",
                confidence=0.82,
                rationale="Detected reading state, note, question, verification, or flashcard intent.",
                **base,
            )
        if _contains_any(
            text,
            lowered,
            ("读这篇", "阅读", "阅读计划", "读书", "read this", "reading workflow", "reading plan"),
        ):
            return TaskIntent(
                task_type=TaskType.PAPER_EXPLANATION,
                requires_retrieval=True,
                preferred_tools=(READ_PAPER_WORKFLOW, SEARCH_LOCAL_PAPERS, ANALYZE_PAPER_STRUCTURE),
                evidence_scope="local",
                confidence=0.8,
                rationale="Detected full-paper reading workflow intent.",
                **base,
            )
        if _contains_any(
            text,
            lowered,
            ("结构", "章节", "段落", "structure", "section"),
        ):
            return TaskIntent(
                task_type=TaskType.STRUCTURE_ANALYSIS,
                requires_retrieval=True,
                preferred_tools=(ANALYZE_PAPER_STRUCTURE,),
                evidence_scope="local",
                confidence=0.78,
                rationale="Detected paper structure analysis intent.",
                **base,
            )
        if _contains_any(text, lowered, ("列表", "已有", "上传过", "list", "uploaded")):
            return TaskIntent(
                task_type=TaskType.PAPER_SEARCH,
                requires_retrieval=True,
                preferred_tools=(LIST_PAPERS,),
                evidence_scope="local",
                confidence=0.85,
                rationale="Detected local paper listing intent.",
                **base,
            )
        if _contains_any(
            text,
            lowered,
            ("解释", "讲讲", "是什么", "为什么", "explain", "what is", "why", "summarize", "总结"),
        ):
            return TaskIntent(
                task_type=TaskType.PAPER_EXPLANATION,
                requires_retrieval=True,
                preferred_tools=(INTELLIGENT_SEARCH_LOCAL_EVIDENCE, ANALYZE_PAPER_STRUCTURE),
                evidence_scope="local",
                confidence=0.72,
                rationale="Detected paper explanation intent.",
                **base,
            )
        if _contains_any(
            text,
            lowered,
            ("检索", "搜索", "查找", "找论文", "查论文", "paper", "search", "find"),
        ):
            return TaskIntent(
                task_type=TaskType.PAPER_SEARCH,
                requires_retrieval=True,
                preferred_tools=(INTELLIGENT_SEARCH_LOCAL_EVIDENCE, SEARCH_RELATED_PAPERS),
                evidence_scope="local",
                confidence=0.55,
                rationale="Detected broad paper search intent.",
                **base,
            )
        return TaskIntent(
            task_type=TaskType.GENERAL_CHAT,
            requires_retrieval=False,
            preferred_tools=(),
            evidence_scope="none",
            confidence=0.3,
            rationale="No specific paper-reading task matched.",
            **base,
        )


class LLMTaskPlanner(TaskPlanner):
    """Schema-validated planner backed by the configured chat model."""

    def __init__(self, model=None, fallback: TaskPlanner | None = None):
        self.model = model
        self.fallback = fallback or RuleBasedTaskPlanner()

    def plan(self, request: AgentRequest, context: CourseContext | None = None) -> TaskPlan:
        context = context or request.course_context or CourseContext()
        try:
            return self._plan_with_model(request, context)
        except Exception as exc:
            fallback_plan = self.fallback.plan(request, context)
            slots = dict(fallback_plan.slots or {})
            slots["planner"] = "llm_fallback"
            slots["fallback_error"] = f"{exc.__class__.__name__}: {exc}"
            return TaskPlan(intent=fallback_plan.intent, steps=fallback_plan.steps, slots=slots)

    def _plan_with_model(self, request: AgentRequest, context: CourseContext) -> TaskPlan:
        rule_hint = self.fallback.plan(request, context)
        payload = {
            "question": request.question,
            "course_context": context.describe(),
            "rule_plan": rule_hint.to_dict(),
            "allowed_task_types": [item.value for item in TaskType],
            "allowed_tools": sorted(ALLOWED_TOOLS),
            "required_json_keys": [
                "task_type",
                "requires_retrieval",
                "preferred_tools",
                "topic",
                "course",
                "target_document_id",
                "target_title",
                "target_artifact",
                "target_section",
                "output_style",
                "evidence_scope",
                "needs_vision",
                "needs_related_search",
                "clarification_needed",
                "clarification_question",
                "confidence",
                "rationale",
                "slots",
            ],
        }
        messages = [
            (
                "system",
                "You are a planner for a paper-reading agent. Return only one valid JSON object. "
                "Choose tool names only from allowed_tools. Do not answer the user question.",
            ),
            ("human", json.dumps(payload, ensure_ascii=False)),
        ]
        response = self._get_model().invoke(messages)
        data = _extract_json_object(getattr(response, "content", response))
        return _plan_from_llm_payload(data, request=request, context=context)

    def _get_model(self):
        if self.model is None:
            from finals_agent.agent.llm import build_chat_model

            self.model = build_chat_model()
        return self.model


class HybridTaskPlanner(TaskPlanner):
    """Use deterministic rules for confident plans, and the LLM for ambiguous ones."""

    def __init__(
        self,
        confidence_threshold: float = 0.8,
        rule_planner: TaskPlanner | None = None,
        llm_planner: TaskPlanner | None = None,
    ):
        self.confidence_threshold = confidence_threshold
        self.rule_planner = rule_planner or RuleBasedTaskPlanner()
        self.llm_planner = llm_planner or LLMTaskPlanner(fallback=self.rule_planner)

    def plan(self, request: AgentRequest, context: CourseContext | None = None) -> TaskPlan:
        context = context or request.course_context or CourseContext()
        rule_plan = self.rule_planner.plan(request, context)
        if (
            rule_plan.intent.confidence >= self.confidence_threshold
            and not rule_plan.intent.clarification_needed
        ):
            return _with_planner_slot(rule_plan, "rule")

        llm_plan = self.llm_planner.plan(request, context)
        if (llm_plan.slots or {}).get("planner") == "llm_fallback":
            slots = dict(llm_plan.slots or {})
            slots["planner"] = "hybrid_fallback"
            return TaskPlan(intent=llm_plan.intent, steps=llm_plan.steps, slots=slots)
        return _with_planner_slot(llm_plan, "llm")


def build_task_planner(settings: Settings | None = None, model=None) -> TaskPlanner:
    settings = settings or load_settings(validate=False)
    settings.planner.validate()
    if settings.planner.provider == "rule":
        return RuleBasedTaskPlanner()
    if settings.planner.provider == "llm":
        return LLMTaskPlanner(model=model)
    return HybridTaskPlanner(
        confidence_threshold=settings.planner.confidence_threshold,
        llm_planner=LLMTaskPlanner(model=model),
        rule_planner=RuleBasedTaskPlanner(),
    )


ARTIFACT_RE = re.compile(
    r"\b(?P<kind>fig(?:ure)?|table|equation|eq\.?|formula)\s*\.?\s*(?P<number>\d+(?:\.\d+)*)",
    re.I,
)
ZH_ARTIFACT_RE = re.compile(r"(?P<kind>图|表|公式)\s*(?P<number>\d+(?:\.\d+)*)")
QUOTED_TITLE_RE = re.compile(r"[《\"'](?P<title>[^》\"']{2,120})[》\"']")


def _extract_slots(text: str, lowered: str, context: CourseContext) -> dict:
    slots = {
        "target_document_id": context.target_document_id,
        "target_title": context.target_title,
    }
    artifact = _extract_artifact(text)
    if artifact:
        slots.update(artifact)
    title = _extract_title(text)
    if title:
        slots["target_title"] = title
    section = _extract_section(lowered)
    if section:
        slots["target_section"] = section
    output_style = _extract_output_style(lowered)
    if output_style:
        slots["output_style"] = output_style
    return {key: value for key, value in slots.items() if value}


def _extract_artifact(text: str) -> dict | None:
    match = ARTIFACT_RE.search(text) or ZH_ARTIFACT_RE.search(text)
    if not match:
        return None
    raw_kind = match.group("kind").lower()
    number = match.group("number")
    kind = _normalize_artifact_kind(raw_kind)
    label = {
        "figure": "Figure",
        "table": "Table",
        "equation": "Equation",
        "formula": "Formula",
    }[kind]
    return {
        "artifact_kind": kind,
        "target_artifact": f"{label} {number}",
        "target": f"{label} {number}",
    }


def _normalize_artifact_kind(raw: str) -> str:
    if raw in {"图"} or raw.startswith("fig"):
        return "figure"
    if raw in {"表", "table"}:
        return "table"
    if raw in {"公式", "formula"}:
        return "formula"
    return "equation"


def _extract_title(text: str) -> str | None:
    match = QUOTED_TITLE_RE.search(text)
    return match.group("title").strip() if match else None


def _extract_section(lowered: str) -> str | None:
    for section in ("abstract", "introduction", "related work", "method", "experiment", "evaluation", "results", "discussion", "conclusion"):
        if section in lowered:
            return section
    for section, value in {
        "摘要": "abstract",
        "引言": "introduction",
        "相关工作": "related work",
        "方法": "method",
        "实验": "experiment",
        "结果": "results",
        "讨论": "discussion",
        "结论": "conclusion",
    }.items():
        if section in lowered:
            return value
    return None


def _extract_output_style(lowered: str) -> str | None:
    if any(item in lowered for item in ("表格", "table format", "matrix", "矩阵")):
        return "table"
    if any(item in lowered for item in ("要点", "bullet", "列表")):
        return "bullets"
    if any(item in lowered for item in ("报告", "report")):
        return "report"
    return None


def _contains_any(original: str, lowered: str, keywords: tuple[str, ...]) -> bool:
    return any((keyword in original) or (keyword in lowered) for keyword in keywords)


def _rough_topic(text: str, slots: dict | None = None) -> str | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    slots = slots or {}
    for value in (slots.get("target_artifact"), slots.get("target_title")):
        if value and value in cleaned:
            cleaned = cleaned.replace(value, " ").strip()
    return " ".join(cleaned.split())[:120]


ALLOWED_TOOLS = allowed_tool_names()

ALLOWED_EVIDENCE_SCOPES = {"none", "local", "external", "local+external", "local+vision"}
ALLOWED_OUTPUT_STYLES = {"bullets", "table", "report"}
LLM_STRING_FIELDS = {
    "topic",
    "course",
    "target_document_id",
    "target_title",
    "target_artifact",
    "target_section",
    "output_style",
    "evidence_scope",
    "clarification_question",
    "rationale",
}


def _extract_json_object(raw: Any) -> dict[str, Any]:
    text = str(raw).strip()
    if not text:
        raise ValueError("Planner model returned an empty response.")
    fenced = re.search(r"```(?:json)?\s*(?P<body>\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group("body")
    elif not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Planner model response did not contain a JSON object.")
        text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Planner model JSON must be an object.")
    return data


def _plan_from_llm_payload(data: dict[str, Any], request: AgentRequest, context: CourseContext) -> TaskPlan:
    task_type_value = _clean_string(data.get("task_type"), max_length=80)
    try:
        task_type = TaskType(task_type_value)
    except ValueError as exc:
        raise ValueError(f"Unsupported task_type from planner: {task_type_value!r}.") from exc

    slots = _clean_slots(data.get("slots"))
    artifact_kind = slots.get("artifact_kind")
    preferred_tools = _clean_tool_list(data.get("preferred_tools"))
    evidence_scope = _clean_choice(data.get("evidence_scope"), ALLOWED_EVIDENCE_SCOPES, default="local")
    output_style = _clean_choice(data.get("output_style"), ALLOWED_OUTPUT_STYLES, default=None)
    target_artifact = _clean_string(data.get("target_artifact"), max_length=80)
    if target_artifact:
        slots.setdefault("target_artifact", target_artifact)

    intent = TaskIntent(
        task_type=task_type,
        requires_retrieval=_clean_bool(data.get("requires_retrieval"), default=task_type != TaskType.GENERAL_CHAT),
        preferred_tools=preferred_tools,
        topic=_clean_string(data.get("topic"), max_length=120) or _rough_topic(request.question, slots),
        course=_clean_string(data.get("course"), max_length=80) or context.field,
        target_document_id=_clean_string(data.get("target_document_id"), max_length=120) or context.target_document_id,
        target_title=_clean_string(data.get("target_title"), max_length=160) or context.target_title,
        target_artifact=target_artifact,
        target_section=_clean_string(data.get("target_section"), max_length=80),
        output_style=output_style,
        evidence_scope=evidence_scope,
        needs_vision=_clean_bool(data.get("needs_vision"), default=artifact_kind in {"figure", "table"}),
        needs_related_search=_clean_bool(data.get("needs_related_search"), default=False),
        clarification_needed=_clean_bool(data.get("clarification_needed"), default=False),
        clarification_question=_clean_string(data.get("clarification_question"), max_length=240),
        confidence=_clean_confidence(data.get("confidence")),
        rationale=_clean_string(data.get("rationale"), max_length=240) or "Generated by LLM task planner.",
    )
    return TaskPlan(intent=intent, steps=_steps_for(intent), slots=slots)


def _with_planner_slot(plan: TaskPlan, planner: str) -> TaskPlan:
    slots = dict(plan.slots or {})
    slots["planner"] = planner
    return TaskPlan(intent=plan.intent, steps=plan.steps, slots=slots)


def _clean_tool_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list | tuple):
        values = value
    else:
        values = []
    cleaned: list[str] = []
    for item in values:
        tool = _clean_string(item, max_length=80)
        if tool in ALLOWED_TOOLS and tool not in cleaned:
            cleaned.append(tool)
    return tuple(cleaned)


def _clean_slots(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    slots: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or len(key) > 80:
            continue
        if isinstance(item, bool | int | float):
            slots[key] = item
        else:
            cleaned = _clean_string(item, max_length=240)
            if cleaned is not None:
                slots[key] = cleaned
    return slots


def _clean_choice(value: Any, allowed: set[str], default: str | None) -> str | None:
    cleaned = _clean_string(value, max_length=80)
    return cleaned if cleaned in allowed else default


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


def _clean_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, confidence))


def _clean_string(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length]


def _steps_for(intent: TaskIntent) -> tuple[str, ...]:
    steps = ["Parse the request into target, scope, and output constraints."]
    if intent.clarification_needed:
        steps.append("Ask a clarification question before using tools.")
        return tuple(steps)
    if intent.target_artifact:
        steps.append(f"Locate artifact: {intent.target_artifact}.")
    if intent.target_section:
        steps.append(f"Focus on section: {intent.target_section}.")
    if intent.requires_retrieval:
        steps.append("Retrieve local paper context before answering.")
    if intent.needs_vision:
        steps.append("Use vision artifact interpretation for figure/table content.")
    if intent.needs_related_search:
        steps.append("Collect related-paper evidence before comparison claims.")
    if intent.preferred_tools:
        steps.append(f"Prefer tools: {', '.join(intent.preferred_tools)}.")
    steps.append("Answer with explicit evidence, limits, and next reading actions.")
    return tuple(steps)
