from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from finals_agent.core.schemas import AgentRequest, TaskPlan


@dataclass(frozen=True)
class QueryRewrite:
    original_query: str
    rewritten_query: str
    reason: str
    strategy: str

    def to_dict(self) -> dict[str, str]:
        return {
            "original_query": self.original_query,
            "rewritten_query": self.rewritten_query,
            "reason": self.reason,
            "strategy": self.strategy,
        }


class RetrievalQueryRewriter:
    def __init__(self, model=None):
        self.model = model

    def rewrite(self, request: AgentRequest, task_plan: TaskPlan, reason: str) -> QueryRewrite:
        original = request.question.strip()
        if self.model is not None:
            try:
                rewritten = self._rewrite_with_model(original, task_plan, reason)
                if rewritten and _normalized(rewritten) != _normalized(original):
                    return QueryRewrite(original, rewritten, reason, "model")
            except Exception:
                pass
        return QueryRewrite(
            original_query=original,
            rewritten_query=_deterministic_rewrite(original, task_plan),
            reason=reason,
            strategy="deterministic",
        )

    def _rewrite_with_model(self, original: str, task_plan: TaskPlan, reason: str) -> str:
        payload = {
            "question": original,
            "reason": reason,
            "target_title": task_plan.intent.target_title,
            "target_section": task_plan.intent.target_section,
            "target_artifact": task_plan.intent.target_artifact,
            "topic": task_plan.intent.topic,
        }
        response = self.model.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "Rewrite the user's paper question into one compact local evidence-search query. "
                        "Keep concrete entities and technical terms, add useful English paper terminology when the "
                        "question is Chinese, and focus on method, experiment, result, limitation, or target artifact "
                        "terms that are likely to occur verbatim in the paper. Do not answer the question. "
                        'Return only JSON: {"query":"..."}.'
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
        )
        raw = getattr(response, "content", response)
        if isinstance(raw, list):
            raw = "".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in raw
            )
        text = str(raw or "").strip()
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            data = json.loads(match.group(0))
            text = str(data.get("query") or "").strip()
        return " ".join(text.split())[:500]


def _deterministic_rewrite(original: str, task_plan: TaskPlan) -> str:
    intent = task_plan.intent
    parts = [
        intent.target_title,
        intent.target_artifact,
        intent.target_section,
        _strip_conversation_words(original),
    ]
    lowered = original.casefold()
    expansions = []
    groups = (
        (("方法", "机制", "如何", "怎么", "method", "mechanism", "approach"), "method approach mechanism algorithm"),
        (("实验", "效果", "结果", "指标", "experiment", "result", "evaluation"), "experiment results evaluation metrics"),
        (("创新", "贡献", "区别", "novel", "contribution", "difference"), "contribution novelty comparison"),
        (("局限", "缺点", "失败", "limitation", "failure"), "limitations failure cases discussion"),
        (("为什么", "证明", "依据", "why", "evidence", "prove"), "evidence analysis conclusion"),
        (("图", "表", "公式", "figure", "table", "equation"), "figure table caption surrounding text"),
    )
    for keywords, expansion in groups:
        if any(keyword in lowered for keyword in keywords):
            expansions.append(expansion)
    parts.extend(expansions)
    rewritten = " ".join(str(part).strip() for part in parts if part and str(part).strip())
    rewritten = " ".join(dict.fromkeys(rewritten.split()))
    if _normalized(rewritten) == _normalized(original):
        rewritten = f"{rewritten} paper evidence method results"
    return rewritten[:500]


def _strip_conversation_words(value: str) -> str:
    cleaned = value
    for phrase in (
        "请解释一下",
        "请解释",
        "请问",
        "帮我",
        "告诉我",
        "这篇论文",
        "论文中",
        "could you",
        "please explain",
        "tell me",
        "in this paper",
    ):
        cleaned = re.sub(re.escape(phrase), " ", cleaned, flags=re.I)
    return " ".join(cleaned.split())


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())
