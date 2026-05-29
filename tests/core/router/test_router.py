"""
tests/core/router/test_router.py
Unit tests for core/router.py, focusing on:
- RoutingDecision dataclass (including new clarifying_questions)
- Model-based routing (high/medium/low confidence)
- Heuristic fallback routing
- JSON extraction robustness
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from core.router import router, RoutingDecision

# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture
def mock_llm():
    """Mock the LLM client to prevent actual LM Studio calls."""
    with patch("core.router.llm") as mock:
        yield mock

# =============================================================================
# Test RoutingDecision Dataclass
# =============================================================================
class TestRoutingDecision:
    def test_default_values(self):
        raw = {}
        decision = RoutingDecision(raw)
        assert decision.workflow == "research"
        assert decision.tool == "web"
        assert decision.complexity == 5
        assert decision.confidence == "medium"
        assert decision.clarifying_questions == []

    def test_custom_values_with_questions(self):
        raw = {
            "workflow": "autocode",
            "tool": "workflow",
            "complexity": 8,
            "reason": "Code fix",
            "confidence": "low",
            "clarifying_questions": ["Which file?", "What is the error?"]
        }
        decision = RoutingDecision(raw)
        assert decision.workflow == "autocode"
        assert decision.complexity == 8
        assert decision.confidence == "low"
        assert len(decision.clarifying_questions) == 2

# =============================================================================
# Test Model-Based Routing (Confidence Guard)
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
        # "Fix the python bug in server.py" contains code keywords, should fall back to autocode
        decision = router.route("Fix the python bug in server.py", trace_id="test-789")
        assert decision.workflow == "autocode"
        assert decision.confidence == "medium"  # Heuristic default for code

# =============================================================================
# Test Heuristic Fallback
# =============================================================================
class TestHeuristicRouting:
    def test_code_keywords(self, mock_llm):
        mock_llm.complete.return_value = MagicMock(ok=False)  # Force fallback
        decision = router.route("refactor the database connection")
        assert decision.workflow == "autocode"
        
    def test_data_keywords(self, mock_llm):
        mock_llm.complete.return_value = MagicMock(ok=False)
        decision = router.route("analyze this csv with pandas")
        assert decision.workflow == "data"

    def test_direct_file_keywords(self, mock_llm):
        mock_llm.complete.return_value = MagicMock(ok=False)
        decision = router.route("read the file config.yaml")
        assert decision.workflow == "direct"
        assert decision.tool == "file"

    def test_empty_goal(self, mock_llm):
        decision = router.route("   ")
        assert decision.confidence == "low"
        assert decision.workflow == "research"