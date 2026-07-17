"""Tests for core/memory_backend/atomic_extract.py — L1 atomic fact extraction."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from core.memory_backend.atomic_extract import (
    extract_facts_from_episodic,
    extract_and_store_facts,
    _EXTRACT_SCHEMA,
    _SYSTEM_PROMPT,
)
from core.llm_backend.response import LLMResponse


class TestExtractFacts:
    """Tests for extract_facts_from_episodic()."""

    def test_empty_text_returns_empty(self):
        """Empty text → empty list, no LLM call."""
        assert extract_facts_from_episodic("") == []
        assert extract_facts_from_episodic("   ") == []

    @patch("core.llm.llm")
    def test_successful_extraction(self, mock_llm):
        """LLM returns facts → parsed + returned."""
        mock_llm.complete.return_value = LLMResponse(
            text='{"facts": [{"fact": "Server uses port 8080", "type": "config", "confidence": 1.0}]}',
            role="router", model="test", usage={"total": 10}, elapsed=0.1, ok=True,
            parsed={"facts": [{"fact": "Server uses port 8080", "type": "config", "confidence": 1.0}]},
        )
        facts = extract_facts_from_episodic("The server runs on port 8080")
        assert len(facts) == 1
        assert facts[0]["fact"] == "Server uses port 8080"
        assert facts[0]["type"] == "config"
        assert facts[0]["confidence"] == 1.0

    @patch("core.llm.llm")
    def test_llm_error_returns_empty(self, mock_llm):
        """LLM failure → empty list (graceful)."""
        mock_llm.complete.return_value = LLMResponse.from_error("router", "test", "LLM unavailable", 0.1)
        facts = extract_facts_from_episodic("some text")
        assert facts == []

    @patch("core.llm.llm")
    def test_no_facts_in_response(self, mock_llm):
        """LLM returns empty facts array → empty list."""
        mock_llm.complete.return_value = LLMResponse(
            text='{"facts": []}', role="router", model="test",
            usage={"total": 5}, elapsed=0.1, ok=True,
            parsed={"facts": []},
        )
        facts = extract_facts_from_episodic("trivial text")
        assert facts == []

    @patch("core.llm.llm")
    def test_facts_capped_at_10(self, mock_llm):
        """More than 10 facts → only first 10 returned."""
        many_facts = [{"fact": f"Fact {i}", "type": "observation", "confidence": 0.5} for i in range(15)]
        mock_llm.complete.return_value = LLMResponse(
            text="{}", role="router", model="test",
            usage={"total": 20}, elapsed=0.1, ok=True,
            parsed={"facts": many_facts},
        )
        facts = extract_facts_from_episodic("long text")
        assert len(facts) == 10

    def test_schema_has_facts_array(self):
        """The JSON schema enforces the facts array structure."""
        assert "facts" in _EXTRACT_SCHEMA["properties"]
        assert _EXTRACT_SCHEMA["properties"]["facts"]["type"] == "array"

    def test_system_prompt_mentions_atomic(self):
        """The system prompt is about atomic fact extraction."""
        assert "atomic" in _SYSTEM_PROMPT.lower()


class TestExtractAndStoreFacts:
    """Tests for extract_and_store_facts()."""

    def test_empty_text_returns_zeros(self):
        """Empty text → all zeros, no LLM call."""
        result = extract_and_store_facts("")
        assert result["extracted"] == 0
        assert result["stored"] == 0

    @patch("core.memory_backend.atomic_extract.extract_facts_from_episodic")
    @patch("core.memory_engine.memory")
    def test_successful_store(self, mock_memory, mock_extract):
        """Facts extracted + stored successfully."""
        mock_extract.return_value = [
            {"fact": "Port 8080", "type": "config", "confidence": 1.0, "source_episodic_id": "ep1"},
        ]
        mock_memory.recall.return_value = []  # no duplicates
        mock_memory.store.return_value = {"status": "stored", "id": "fact1"}

        result = extract_and_store_facts("Server runs on port 8080", episodic_id="ep1")
        assert result["extracted"] == 1
        assert result["stored"] == 1
        assert result["skipped_duplicates"] == 0

    @patch("core.memory_backend.atomic_extract.extract_facts_from_episodic")
    @patch("core.memory_engine.memory")
    def test_duplicate_skipped(self, mock_memory, mock_extract):
        """Near-duplicate fact → skipped."""
        mock_extract.return_value = [
            {"fact": "Port 8080", "type": "config", "confidence": 1.0, "source_episodic_id": ""},
        ]
        mock_memory.recall.return_value = [
            {"text": "Port 8080", "score": 0.95},  # > 0.92 threshold
        ]

        result = extract_and_store_facts("Server runs on port 8080")
        assert result["stored"] == 0
        assert result["skipped_duplicates"] == 1
