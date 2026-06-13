from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from finals_agent.core.runtime import AgentRuntime
from finals_agent.data.external_search import ArxivPaperSearch
from finals_agent.data.repository import StudyRepository
from finals_agent.data.retrievers import Retriever
from finals_agent.persistence.reading_state import ReadingStateStore
from finals_agent.persistence.research_tasks import ResearchTaskStore


LIST_PAPERS = "list_papers"
SEARCH_LOCAL_PAPERS = "search_local_papers"
ANALYZE_PAPER_STRUCTURE = "analyze_paper_structure"
SEARCH_RELATED_PAPERS = "search_related_papers"
COMPARE_PAPER_INNOVATIONS = "compare_paper_innovations"
READ_PAPER_WORKFLOW = "read_paper_workflow"
EXPLAIN_PAPER_TARGET = "explain_paper_target"
GET_READING_STATE = "get_reading_state"
UPDATE_READING_STATE = "update_reading_state"
INTELLIGENT_SEARCH_LOCAL_EVIDENCE = "intelligent_search_local_evidence"
DISCOVER_RESEARCH_PAPERS = "discover_research_papers"
ANALYZE_RESEARCH_MATERIALS = "analyze_research_materials"
IMPORT_ARXIV_PAPER = "import_arxiv_paper"
CHECK_PAPER_CODE_CORRESPONDENCE = "check_paper_code_correspondence"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    capability: str
    description: str
    requires_network: bool = False
    mutates_state: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "capability": self.capability,
            "description": self.description,
            "requires_network": self.requires_network,
            "mutates_state": self.mutates_state,
        }


DEFAULT_TOOL_SPECS = (
    ToolSpec(LIST_PAPERS, "library", "List locally available papers and notes."),
    ToolSpec(SEARCH_LOCAL_PAPERS, "retrieval", "Search indexed local paper evidence."),
    ToolSpec(
        INTELLIGENT_SEARCH_LOCAL_EVIDENCE,
        "retrieval",
        "Rewrite a question into multiple searches, rerank evidence, and return complete passages.",
    ),
    ToolSpec(ANALYZE_PAPER_STRUCTURE, "structure", "Analyze sections, captions, and formulas."),
    ToolSpec(
        SEARCH_RELATED_PAPERS,
        "external_retrieval",
        "Search arXiv for related papers.",
        requires_network=True,
    ),
    ToolSpec(
        COMPARE_PAPER_INNOVATIONS,
        "comparison",
        "Collect local and external evidence for innovation comparison.",
        requires_network=True,
    ),
    ToolSpec(READ_PAPER_WORKFLOW, "reading", "Run a section-aware full-paper reading workflow."),
    ToolSpec(EXPLAIN_PAPER_TARGET, "explanation", "Explain a focused paper target with evidence."),
    ToolSpec(GET_READING_STATE, "reading_state", "Read progress, notes, and open questions."),
    ToolSpec(
        UPDATE_READING_STATE,
        "reading_state",
        "Update progress, notes, questions, and verification items.",
        mutates_state=True,
    ),
    ToolSpec(
        DISCOVER_RESEARCH_PAPERS,
        "research",
        "Discover and summarize related papers for a research direction.",
        requires_network=True,
        mutates_state=True,
    ),
    ToolSpec(
        ANALYZE_RESEARCH_MATERIALS,
        "research",
        "Analyze selected papers and code for innovations, gaps, correspondence, and next work.",
        mutates_state=True,
    ),
    ToolSpec(
        CHECK_PAPER_CODE_CORRESPONDENCE,
        "research",
        "Verify paper claims against concrete code evidence, files, symbols, and line ranges.",
        mutates_state=True,
    ),
    ToolSpec(
        IMPORT_ARXIV_PAPER,
        "library",
        "Download an explicitly requested arXiv PDF and import it into the local library.",
        requires_network=True,
        mutates_state=True,
    ),
)


class ToolRegistry:
    def __init__(self, specs: Iterable[ToolSpec] = DEFAULT_TOOL_SPECS):
        self._specs = {}
        self._tools = {}
        for spec in specs:
            if spec.name in self._specs:
                raise ValueError(f"Duplicate tool specification: {spec.name}.")
            self._specs[spec.name] = spec

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def register(self, tool) -> None:
        name = str(getattr(tool, "name", "") or "").strip()
        if name not in self._specs:
            raise ValueError(f"Tool '{name}' has no registry specification.")
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")
        self._tools[name] = tool

    def register_many(self, tools: Iterable) -> "ToolRegistry":
        for tool in tools:
            self.register(tool)
        return self

    def get(self, name: str):
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered.")
        return self._tools[name]

    def select(self, names: Iterable[str] | None = None) -> list:
        selected = tuple(names or self.names)
        unknown = [name for name in selected if name not in self._specs]
        if unknown:
            raise ValueError(f"Unknown tool(s): {', '.join(unknown)}.")
        missing = [name for name in selected if name not in self._tools]
        if missing:
            raise ValueError(f"Tool(s) not initialized: {', '.join(missing)}.")
        return [self._tools[name] for name in selected]

    def metadata(self, names: Iterable[str] | None = None) -> list[dict]:
        selected = tuple(names or self.names)
        return [self._specs[name].to_dict() for name in selected if name in self._specs]


def allowed_tool_names() -> frozenset[str]:
    return frozenset(spec.name for spec in DEFAULT_TOOL_SPECS)


def build_tool_registry(
    repository: StudyRepository | None = None,
    runtime: AgentRuntime | None = None,
    retriever: Retriever | None = None,
    external_search: ArxivPaperSearch | None = None,
    reading_store: ReadingStateStore | None = None,
    research_task_store: ResearchTaskStore | None = None,
    model=None,
) -> ToolRegistry:
    from finals_agent.agent.tools import build_tools

    registry = ToolRegistry()
    tools = build_tools(
        repository=repository,
        runtime=runtime,
        retriever=retriever,
        external_search=external_search,
        reading_store=reading_store,
        research_task_store=research_task_store,
        model=model,
    )
    return registry.register_many(tools)
