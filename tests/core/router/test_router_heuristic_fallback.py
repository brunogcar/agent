"""tests/core/router/test_router_heuristic_fallback.py
Behavioral tests for the heuristic routing fallback in TaskRouter.

These tests verify that keyword-based routing works correctly for
all tools and workflows, including the newly added ones.
No LLM mocking is needed -- we force fallback by making llm.complete fail.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from core.router import router, RoutingDecision


# =============================================================================
# Test Model-Based Routing (migrated from old test_router.py)
# =============================================================================
class TestModelRouting:
    def test_high_confidence_route(self, mock_llm):
        mock_llm.complete.return_value = MagicMock(
            ok=True,
            text='{"workflow": "research", "tool": "web", "complexity": 4, "reason": "Clear question", "confidence": "high", "clarifying_questions": []}'
        )
        decision = router.route("What is ChromaDB?", trace_id="test-123")
        assert decision.confidence == "high"
        assert decision.workflow == "research"
        assert decision.clarifying_questions == []

    def test_low_confidence_with_questions(self, mock_llm):
        mock_llm.complete.return_value = MagicMock(
            ok=True,
            text='{"workflow": "autocode", "tool": "workflow", "complexity": 7, "reason": "Vague request", "confidence": "low", "clarifying_questions": ["Which file needs fixing?", "What is the specific bug?"]}'
        )
        decision = router.route("Fix the bug", trace_id="test-456")
        assert decision.confidence == "low"
        assert len(decision.clarifying_questions) == 2
        assert "Which file" in decision.clarifying_questions[0]

    def test_malformed_json_falls_back_to_heuristic(self, mock_llm):
        mock_llm.complete.return_value = MagicMock(
            ok=True,
            text="I cannot output JSON right now."
        )
        decision = router.route("Fix the python bug in server.py", trace_id="test-789")
        assert decision.workflow == "autocode"
        assert decision.confidence == "medium"


# =============================================================================
# Test Heuristic Fallback -- Existing Tools (migrated from old test_router.py)
# =============================================================================
class TestHeuristicExistingTools:
    def test_code_keywords(self, force_heuristic):
        decision = router.route("refactor the database connection")
        assert decision.workflow == "autocode"
        assert decision.tool == "workflow"

    def test_code_with_file_extension_complexity_7(self, force_heuristic):
        decision = router.route("fix the bug in server.py")
        assert decision.workflow == "autocode"
        assert decision.complexity == 7

    def test_code_without_file_extension_complexity_5(self, force_heuristic):
        decision = router.route("refactor the database connection")
        assert decision.workflow == "autocode"
        assert decision.complexity == 5

    def test_data_keywords(self, force_heuristic):
        decision = router.route("analyze this csv with pandas")
        assert decision.workflow == "data"
        assert decision.tool == "python"

    def test_direct_file_keywords(self, force_heuristic):
        decision = router.route("read the file config.yaml")
        assert decision.workflow == "direct"
        assert decision.tool == "file"

    def test_direct_memory_keywords(self, force_heuristic):
        decision = router.route("recall what you know about ChromaDB")
        assert decision.workflow == "direct"
        assert decision.tool == "memory"

    def test_direct_git_keywords(self, force_heuristic):
        decision = router.route("show me git status")
        assert decision.workflow == "direct"
        assert decision.tool == "git"

    def test_direct_notify_keywords(self, force_heuristic):
        decision = router.route("notify me when done")
        assert decision.workflow == "direct"
        assert decision.tool == "notify"

    def test_report_keywords(self, force_heuristic):
        decision = router.route("create a bar chart of sales data")
        assert decision.workflow == "direct"
        assert decision.tool == "report"

    def test_empty_goal(self):
        decision = router.route(" ")
        assert decision.confidence == "low"
        assert decision.workflow == "research"
        assert decision.clarifying_questions == ["What would you like me to help you with?"]

    def test_default_research(self, force_heuristic):
        decision = router.route("something completely vague")
        assert decision.workflow == "research"
        assert decision.tool == "web"
        assert decision.confidence == "low"


# =============================================================================
# Test Heuristic Fallback -- NEW Tools (Router Expansion)
# =============================================================================
class TestHeuristicBrowser:
    """Browser tool heuristic routing."""

    def test_browse_keyword(self, force_heuristic):
        decision = router.route("browse this website and take a screenshot")
        assert decision.workflow == "direct"
        assert decision.tool == "browser"
        assert decision.confidence == "high"

    def test_screenshot_keyword(self, force_heuristic):
        decision = router.route("take a screenshot of the login page")
        assert decision.workflow == "direct"
        assert decision.tool == "browser"

    def test_fill_form_keyword(self, force_heuristic):
        decision = router.route("fill form on the contact page")
        assert decision.workflow == "direct"
        assert decision.tool == "browser"

    def test_js_rendered_keyword(self, force_heuristic):
        decision = router.route("scrape the js-rendered dashboard")
        assert decision.workflow == "direct"
        assert decision.tool == "browser"


class TestHeuristicCLI:
    """CLI tool heuristic routing."""

    def test_run_command_keyword(self, force_heuristic):
        decision = router.route("run command pip install requests")
        assert decision.workflow == "direct"
        assert decision.tool == "cli"
        assert decision.confidence == "high"

    def test_terminal_keyword(self, force_heuristic):
        decision = router.route("open terminal and check disk space")
        assert decision.workflow == "direct"
        assert decision.tool == "cli"

    def test_docker_keyword(self, force_heuristic):
        decision = router.route("docker build the image")
        assert decision.workflow == "direct"
        assert decision.tool == "cli"

    def test_kubectl_keyword(self, force_heuristic):
        decision = router.route("kubectl get pods")
        assert decision.workflow == "direct"
        assert decision.tool == "cli"


class TestHeuristicTavily:
    """Tavily tool heuristic routing."""

    def test_tavily_keyword(self, force_heuristic):
        decision = router.route("use tavily to search for quantum computing")
        assert decision.workflow == "direct"
        assert decision.tool == "tavily"
        assert decision.confidence == "high"

    def test_ai_search_keyword(self, force_heuristic):
        decision = router.route("do an ai search on climate change")
        assert decision.workflow == "direct"
        assert decision.tool == "tavily"

    def test_deep_search_keyword(self, force_heuristic):
        decision = router.route("deep search for recent LLM papers")
        assert decision.workflow == "direct"
        assert decision.tool == "tavily"


class TestHeuristicConsult:
    """Consult tool heuristic routing."""

    def test_consult_keyword(self, force_heuristic):
        decision = router.route("consult a different AI about this architecture")
        assert decision.workflow == "direct"
        assert decision.tool == "consult"
        assert decision.confidence == "high"

    def test_second_opinion_keyword(self, force_heuristic):
        decision = router.route("let's get a second opinion on this code review")
        assert decision.workflow == "direct"
        assert decision.tool == "consult"


class TestHeuristicParallel:
    """Parallel tool heuristic routing (direct tool, not workflow)."""

    def test_run_in_parallel_keyword(self, force_heuristic):
        decision = router.route("run checks in parallel")
        assert decision.workflow == "direct"
        assert decision.tool == "parallel"
        assert decision.confidence == "medium"

    def test_concurrently_keyword(self, force_heuristic):
        decision = router.route("process all files concurrently")
        assert decision.workflow == "direct"
        assert decision.tool == "parallel"

    def test_batch_process_keyword(self, force_heuristic):
        decision = router.route("batch process the images")
        assert decision.workflow == "direct"
        assert decision.tool == "parallel"

    def test_run_at_the_same_time_keyword(self, force_heuristic):
        decision = router.route("run these at the same time")
        assert decision.workflow == "direct"
        assert decision.tool == "parallel"


class TestHeuristicVision:
    """Vision tool heuristic routing."""

    def test_analyze_image_keyword(self, force_heuristic):
        decision = router.route("analyze this image")
        assert decision.workflow == "direct"
        assert decision.tool == "vision"
        assert decision.confidence == "high"

    def test_describe_image_keyword(self, force_heuristic):
        decision = router.route("describe what is in this image")
        assert decision.workflow == "direct"
        assert decision.tool == "vision"

    def test_ocr_keyword(self, force_heuristic):
        decision = router.route("ocr this screenshot")
        assert decision.workflow == "direct"
        assert decision.tool == "vision"


class TestHeuristicAgent:
    """Agent tool heuristic routing."""

    def test_delegate_keyword(self, force_heuristic):
        decision = router.route("delegate this to an agent")
        assert decision.workflow == "direct"
        assert decision.tool == "agent"
        assert decision.confidence == "medium"

    def test_spawn_agent_keyword(self, force_heuristic):
        decision = router.route("spawn an agent to handle this")
        assert decision.workflow == "direct"
        assert decision.tool == "agent"


class TestHeuristicDeepResearch:
    """Deep Research workflow heuristic routing."""

    def test_deep_research_keyword(self, force_heuristic):
        decision = router.route("do deep research on renewable energy trends")
        assert decision.workflow == "deep_research"
        assert decision.tool == "workflow"
        assert decision.confidence == "medium"

    def test_thorough_investigation_keyword(self, force_heuristic):
        decision = router.route("thorough investigation of the security breach")
        assert decision.workflow == "deep_research"
        assert decision.tool == "workflow"

    def test_in_depth_analysis_keyword(self, force_heuristic):
        decision = router.route("in-depth analysis of neural network architectures")
        assert decision.workflow == "deep_research"
        assert decision.tool == "workflow"


class TestHeuristicUnderstand:
    """Understand workflow heuristic routing."""

    def test_build_knowledge_graph_keyword(self, force_heuristic):
        decision = router.route("build knowledge graph for this repository")
        assert decision.workflow == "understand"
        assert decision.tool == "workflow"
        assert decision.confidence == "medium"

    def test_index_codebase_keyword(self, force_heuristic):
        decision = router.route("index codebase and map dependencies")
        assert decision.workflow == "understand"
        assert decision.tool == "workflow"

    def test_explore_codebase_keyword(self, force_heuristic):
        decision = router.route("explore codebase structure")
        assert decision.workflow == "understand"
        assert decision.tool == "workflow"


# =============================================================================
# Test Heuristic Priority Order
# =============================================================================
class TestHeuristicPriority:
    """Verify that more specific patterns win over general ones."""

    def test_report_beats_data(self, force_heuristic):
        decision = router.route("create a chart from this csv")
        assert decision.tool == "report"

    def test_browser_beats_research(self, force_heuristic):
        decision = router.route("browse this page and summarize")
        assert decision.tool == "browser"

    def test_file_beats_code(self, force_heuristic):
        decision = router.route("read file server.py")
        assert decision.tool == "file"

    def test_deep_research_beats_research(self, force_heuristic):
        decision = router.route("deep research on neural networks")
        assert decision.workflow == "deep_research"

    def test_understand_beats_code(self, force_heuristic):
        decision = router.route("build knowledge graph for this project")
        assert decision.workflow == "understand"

    def test_cli_beats_code(self, force_heuristic):
        decision = router.route("run command to fix the build")
        assert decision.tool == "cli"

    def test_parallel_beats_data(self, force_heuristic):
        decision = router.route("batch process the csv files")
        assert decision.tool == "parallel"


# =============================================================================
# [ROUTER FIX] Test Heuristic False Positives -- Negative/Adversarial Cases
# =============================================================================
class TestHeuristicFalsePositives:
    """Verify ambiguous phrases do NOT get misrouted to the wrong tool."""

    def test_report_a_bug_not_report_tool(self, force_heuristic):
        decision = router.route("report a bug in server.py")
        assert decision.tool != "report"
        assert decision.workflow == "autocode"

    def test_consult_docs_not_consult_tool(self, force_heuristic):
        decision = router.route("consult the documentation for Flask")
        assert decision.tool != "consult"
        assert decision.workflow == "research"

    def test_research_in_parallel_not_parallel_tool(self, force_heuristic):
        decision = router.route("research these topics in parallel")
        assert decision.tool != "parallel"
        assert decision.workflow == "research"

    def test_explain_simultaneously_not_parallel_tool(self, force_heuristic):
        decision = router.route("explain how threads run simultaneously in Python")
        assert decision.tool != "parallel"
        assert decision.workflow == "research"

    def test_what_is_the_error_not_code_tool(self, force_heuristic):
        decision = router.route("what is the error in this logic")
        assert decision.workflow == "research"

    def test_process_all_data_not_parallel_tool(self, force_heuristic):
        decision = router.route("process all the data with pandas")
        assert decision.tool != "parallel"
        assert decision.workflow == "data"

    def test_second_opinion_doctor_not_consult_tool(self, force_heuristic):
        decision = router.route("get a second opinion from my doctor")
        assert decision.tool != "consult"
        assert decision.workflow == "research"
