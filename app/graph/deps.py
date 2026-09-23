"""Dependency bundle for graph nodes.

Nodes never import ``app.agents.tool_agent`` or the RAG pipeline directly
— they receive a :class:`GraphDeps` instance with the callables they
need. This is what makes ``app/graph/nodes.py`` testable with fakes
(``tests/test_graph_runner.py``) even though the real implementations
(``dispatch``, the RAG pipeline) depend on pydantic/SQLAlchemy, which
cannot be installed in this authoring sandbox.

Production wiring (``app/graph/workflow.py``) constructs the real
:func:`default_deps`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class GraphDeps:
    search_knowledge_base: Callable[[str, str | None], dict]
    search_incidents: Callable[[dict], dict]
    run_tool: Callable[[str, dict], dict]


def default_deps() -> GraphDeps:
    """Real production dependencies, wired to Phase 3/4 components.
    Imports are local so importing this module doesn't require the full
    dependency stack unless this factory is actually called.
    """
    from app.agents.tool_agent import dispatch

    def _search_kb(query: str, department: str | None) -> dict:
        return dispatch("search_knowledge_base", {"query": query, "department": department})

    def _search_incidents(filters: dict) -> dict:
        return dispatch("search_incidents", filters)

    def _run_tool(tool_name: str, input_data: dict) -> dict:
        return dispatch(tool_name, input_data)

    return GraphDeps(
        search_knowledge_base=_search_kb,
        search_incidents=_search_incidents,
        run_tool=_run_tool,
    )
