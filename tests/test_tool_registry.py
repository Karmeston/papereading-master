from types import SimpleNamespace

import pytest

from finals_agent.agent.tool_registry import (
    ANALYZE_RESEARCH_MATERIALS,
    CHECK_PAPER_CODE_CORRESPONDENCE,
    DISCOVER_RESEARCH_PAPERS,
    IMPORT_ARXIV_PAPER,
    INTELLIGENT_SEARCH_LOCAL_EVIDENCE,
    LIST_PAPERS,
    SEARCH_LOCAL_PAPERS,
    ToolRegistry,
    allowed_tool_names,
)


def test_tool_registry_registers_selects_and_describes_tools():
    registry = ToolRegistry()
    list_tool = SimpleNamespace(name=LIST_PAPERS)
    search_tool = SimpleNamespace(name=SEARCH_LOCAL_PAPERS)
    registry.register_many([list_tool, search_tool])

    assert registry.select([SEARCH_LOCAL_PAPERS, LIST_PAPERS]) == [search_tool, list_tool]
    assert registry.metadata([SEARCH_LOCAL_PAPERS])[0]["capability"] == "retrieval"
    assert SEARCH_LOCAL_PAPERS in allowed_tool_names()
    assert INTELLIGENT_SEARCH_LOCAL_EVIDENCE in allowed_tool_names()
    assert DISCOVER_RESEARCH_PAPERS in allowed_tool_names()
    assert ANALYZE_RESEARCH_MATERIALS in allowed_tool_names()
    assert CHECK_PAPER_CODE_CORRESPONDENCE in allowed_tool_names()
    assert IMPORT_ARXIV_PAPER in allowed_tool_names()


def test_tool_registry_rejects_unknown_and_duplicate_tools():
    registry = ToolRegistry()
    tool = SimpleNamespace(name=LIST_PAPERS)
    registry.register(tool)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)

    with pytest.raises(ValueError, match="no registry specification"):
        registry.register(SimpleNamespace(name="unknown_tool"))

    with pytest.raises(ValueError, match="Unknown tool"):
        registry.select(["unknown_tool"])
