"""DeepResearch workflow package.

Provides a cyclic LangGraph workflow for iterative deep research
using web search, Tavily, and browser tools with budget management.
"""
from __future__ import annotations

from workflows.deep_research_impl.graph import build_deep_research_graph

__all__ = ["build_deep_research_graph"]
