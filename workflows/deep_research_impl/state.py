"""workflows/deep_research_impl/state.py"""
from __future__ import annotations
from typing_extensions import TypedDict
from workflows.base import WorkflowState

class DeepResearchState(WorkflowState, total=False):
    # Research inputs
    goal: str
    sub_queries: list[str]
    pending_queries: list[str]

    # Evidence
    extracted_evidence: list[dict]
    failed_sources: list[dict]

    # Knowledge
    knowledge_base: str
    _prev_knowledge: str
    completeness: float
    converged: bool

    # Control
    iteration: int
    consecutive_empty_iterations: int
    budget_api_calls: int
    budget_browser_actions: int
    budget_events: list[dict]

    # Config
    max_iterations: int
    completeness_threshold: float
    convergence_threshold: float

    # Report
    report: str
    result: str
    status: str

    # Memory (recalled context from episodic/semantic memory)
    memory_context: str

    # Cross-iteration URL deduplication
    seen_urls: list[str]
