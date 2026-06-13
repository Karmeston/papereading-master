from __future__ import annotations

from dataclasses import dataclass
import re

from finals_agent.agent.preretrieval import PreRetrievalResult
from finals_agent.core.config import load_settings


CITATION_RE = re.compile(r"\[[^\[\]\n]+\|[^\[\]\n]*(?:chunk=|page=|section=|focus=)[^\[\]\n]*\]")


@dataclass(frozen=True)
class CitationCheck:
    required: bool
    passed: bool
    available_citations: tuple[str, ...] = ()
    used_citations: tuple[str, ...] = ()
    missing_citations: tuple[str, ...] = ()
    warning: str | None = None

    def to_dict(self) -> dict:
        return {
            "required": self.required,
            "passed": self.passed,
            "available_citations": list(self.available_citations),
            "used_citations": list(self.used_citations),
            "missing_citations": list(self.missing_citations),
            "warning": self.warning,
        }


def check_local_citations(answer: str, preretrieval: PreRetrievalResult) -> CitationCheck:
    available = _available_citations(preretrieval)
    if not available:
        return CitationCheck(required=False, passed=True)

    used = tuple(citation for citation in available if citation in answer)
    extracted = tuple(CITATION_RE.findall(answer))
    if used:
        return CitationCheck(
            required=True,
            passed=True,
            available_citations=available,
            used_citations=used,
            missing_citations=tuple(citation for citation in available if citation not in used),
        )

    language = load_settings(validate=False).language
    warning = (
        (
            "This answer used local paper context but did not retain a local citation. "
            "Verify the conclusion against evidence that includes citations."
        )
        if language == "en"
        else (
            "本回答使用了本地论文检索上下文，但最终文本没有保留本地 citation。"
            "请优先依据带 citation 的证据核对结论。"
        )
    )
    if extracted:
        warning += (
            " The detected citation format did not match this run's local evidence."
            if language == "en"
            else " 检测到的引用格式未匹配本轮本地证据。"
        )
    return CitationCheck(
        required=True,
        passed=False,
        available_citations=available,
        used_citations=(),
        missing_citations=available,
        warning=warning,
    )


def append_citation_warning(answer: str, check: CitationCheck) -> str:
    if check.passed or not check.warning:
        return answer
    language = load_settings(validate=False).language
    suffix = (
        "[Citation Check] "
        + check.warning
        + " Available local evidence is recorded in metadata.citation_check.available_citations."
        if language == "en"
        else "[引用检查] " + check.warning + " 可用本地证据已记录在运行 metadata.citation_check.available_citations 中。"
    )
    return answer + f"\n\n{suffix}"


def _available_citations(preretrieval: PreRetrievalResult) -> tuple[str, ...]:
    if not preretrieval.enabled or not preretrieval.response:
        return ()
    citations = []
    for result in preretrieval.response.results:
        citation = result.to_dict().get("citation")
        if citation and citation not in citations:
            citations.append(citation)
    return tuple(citations)
