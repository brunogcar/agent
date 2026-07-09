"""Tests for swarm list_providers action."""
from __future__ import annotations
from tools.swarm import swarm


class TestListProviders:
    """list_providers returns all configured cloud providers."""

    def test_list_providers_with_mock(self, mock_llm_registry):
        """Should list 3 cloud providers (lmstudio excluded)."""
        result = swarm(action="list_providers")
        assert result["status"] == "success"
        data = result["data"]
        assert data["count"] == 3
        provider_names = [p["name"] for p in data["providers"]]
        assert "openai" in provider_names
        assert "deepseek" in provider_names
        assert "claude" in provider_names
        assert "lmstudio" not in provider_names

    def test_list_providers_empty(self, mock_llm_empty_registry):
        """Should return count=0 when no cloud providers configured."""
        result = swarm(action="list_providers")
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert result["data"]["providers"] == []

    def test_list_providers_has_model_names(self, mock_llm_registry):
        """Each provider should have a model name."""
        result = swarm(action="list_providers")
        assert result["status"] == "success"
        for p in result["data"]["providers"]:
            assert p["model"] != ""
            assert p["available"] is True
