"""
tests/tools/memory_tool/test_memory_tool.py
Unit tests for the memory meta-tool, focusing on:
- P2: Centralized cfg.memory_max_entry_bytes integration
- Tag validation (MED-05)
- Action dispatch
- Error handling
"""
import pytest
from unittest.mock import patch, MagicMock

from tools.memory_tool import memory, _validate_tags, _mem


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_config(monkeypatch):
    """Patch cfg attributes used by memory_tool."""
    with patch("tools.memory_tool.cfg") as mock_cfg:
        mock_cfg.memory_max_entry_bytes = 50000  # 50KB
        mock_cfg.max_tags_per_entry = 6
        mock_cfg.max_tag_length = 50
        yield mock_cfg


@pytest.fixture
def mock_store():
    """Mock the lazy-loaded memory store."""
    with patch("tools.memory_tool._mem") as mock_mem:
        store = MagicMock()
        store.store.return_value = {"status": "stored", "id": "test-id"}
        store.recall.return_value = [{"id": "1", "text": "result", "score": 0.9}]
        store.delete.return_value = {"status": "deleted", "count": 1}
        store.prune.return_value = {"status": "pruned", "would_delete": 5}
        store.summarize.return_value = {"status": "summarized"}
        store.stats.return_value = {
            "episodic": {"count": 10},
            "semantic": {"count": 20},
            "procedural": {"count": 5},
        }
        mock_mem.return_value = store
        yield store


# =============================================================================
# Test Tag Validation (MED-05)
# =============================================================================

class TestTagValidation:
    def test_empty_tags_valid(self, mock_config):
        is_valid, err = _validate_tags("", max_count=6)
        assert is_valid is True
        assert err == ""

    def test_valid_tags(self, mock_config):
        is_valid, err = _validate_tags("python,debug,mcp", max_count=6)
        assert is_valid is True

    def test_dangerous_chars_rejected(self, mock_config):
        for bad in ['<', '>', '"', "'", '`', '|']:
            is_valid, err = _validate_tags(f"tag{bad}bad", max_count=6)
            assert is_valid is False
            assert "cannot contain" in err

    def test_too_many_tags(self, mock_config):
        is_valid, err = _validate_tags("a,b,c,d,e,f,g", max_count=6)
        assert is_valid is False
        assert "Too many tags" in err

    def test_tag_too_long(self, mock_config):
        long_tag = "a" * 51
        is_valid, err = _validate_tags(long_tag, max_count=6)
        assert is_valid is False
        assert "exceeds length limit" in err

    def test_tag_must_start_with_letter(self, mock_config):
        is_valid, err = _validate_tags("123invalid", max_count=6)
        assert is_valid is False
        assert "invalid characters" in err.lower()

    def test_valid_tag_with_hyphen_and_underscore(self, mock_config):
        is_valid, err = _validate_tags("my-tag_name.v2", max_count=6)
        assert is_valid is True


# =============================================================================
# Test Store Action
# =============================================================================

class TestStoreAction:
    def test_missing_text_error(self, mock_config, mock_store):
        result = memory(action="store", text="")
        assert result["status"] == "error"
        assert "text is required" in result["error"]

    def test_invalid_importance_error(self, mock_config, mock_store):
        result = memory(action="store", text="test", importance=15)
        assert result["status"] == "error"
        assert "importance must be 1-10" in result["error"]

    def test_text_too_large_error(self, mock_config, mock_store):
        """P2: Centralized cfg.memory_max_entry_bytes enforcement."""
        huge_text = "x" * 60000  # 60KB, exceeds 50KB limit
        result = memory(action="store", text=huge_text)
        assert result["status"] == "error"
        assert "exceeds" in result["error"]
        assert "50000" in result["error"]  # Should show the cfg value

    def test_invalid_tags_error(self, mock_config, mock_store):
        result = memory(action="store", text="test", tags="<bad>")
        assert result["status"] == "error"
        assert "cannot contain" in result["error"]

    def test_successful_store(self, mock_config, mock_store):
        result = memory(
            action="store",
            text="A useful fact",
            memory_type="semantic",
            importance=7,
            tags="test,fact",
        )
        assert result["status"] == "stored"
        mock_store.store.assert_called_once()


# =============================================================================
# Test Recall Action
# =============================================================================

class TestRecallAction:
    def test_missing_query_error(self, mock_config, mock_store):
        result = memory(action="recall", query="")
        assert result["status"] == "error"
        assert "query is required" in result["error"]

    def test_invalid_tags_filter_error(self, mock_config, mock_store):
        result = memory(action="recall", query="test", tags_filter="<bad>")
        assert result["status"] == "error"
        assert "cannot contain" in result["error"]

    def test_successful_recall(self, mock_config, mock_store):
        result = memory(action="recall", query="python", top_k=3)
        assert result["status"] == "success"
        assert result["data"]["count"] == 1
        assert len(result["data"]["results"]) == 1


# =============================================================================
# Test Other Actions
# =============================================================================

class TestOtherActions:
    def test_delete_missing_query(self, mock_config, mock_store):
        result = memory(action="delete", query="")
        assert result["status"] == "error"
        assert "query is required" in result["error"]

    def test_successful_delete(self, mock_config, mock_store):
        result = memory(action="delete", query="old stuff")
        assert result["status"] == "deleted"

    def test_prune(self, mock_config, mock_store):
        result = memory(action="prune", dry_run=True)
        assert result["status"] == "pruned"

    def test_summarize(self, mock_config, mock_store):
        result = memory(action="summarize")
        assert result["status"] == "summarized"

    def test_stats(self, mock_config, mock_store):
        result = memory(action="stats")
        assert result["status"] == "success"
        assert result["data"]["total"] == 35  # 10 + 20 + 5

    def test_unknown_action(self, mock_config, mock_store):
        result = memory(action="invalid_action")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]


# =============================================================================
# Test Config Integration (P2)
# =============================================================================

class TestConfigIntegration:
    def test_memory_limit_uses_config(self, mock_config, mock_store):
        """Verify the error message dynamically uses cfg.memory_max_entry_bytes."""
        mock_config.memory_max_entry_bytes = 100  # Tiny limit for test
        huge_text = "x" * 200
        result = memory(action="store", text=huge_text)
        assert result["status"] == "error"
        assert "100" in result["error"]  # Should reflect the cfg value

    def test_tag_count_uses_config(self, mock_config):
        """Verify max_tags_per_entry is read from config."""
        mock_config.max_tags_per_entry = 2
        is_valid, err = _validate_tags("a,b,c", max_count=mock_config.max_tags_per_entry)
        assert is_valid is False

    def test_tag_length_uses_config(self, mock_config):
        """Verify max_tag_length is read from config."""
        mock_config.max_tag_length = 10
        is_valid, err = _validate_tags("verylongtagname", max_count=6)
        assert is_valid is False