"""Tests for the prune action.
v1.1: Added collections validation, range check tests.
"""
from __future__ import annotations

from tools.memory import memory


class TestPruneValidation:
    def test_empty_collections_rejected(self, mock_cfg, mock_store):
        """v1.1: Empty collections list must be rejected."""
        result = memory(action="prune", collections=[])
        assert result["status"] == "error"
        assert "cannot be empty" in result["error"]

    def test_negative_max_age_days_rejected(self, mock_cfg, mock_store):
        """v1.1: Negative max_age_days must be rejected."""
        result = memory(action="prune", max_age_days=-1)
        assert result["status"] == "error"
        assert "max_age_days must be >= 0" in result["error"]

    def test_min_importance_out_of_range_rejected(self, mock_cfg, mock_store):
        """v1.1: min_importance must be 1-10."""
        result = memory(action="prune", min_importance=0)
        assert result["status"] == "error"
        assert "min_importance must be 1-10" in result["error"]

        result = memory(action="prune", min_importance=11)
        assert result["status"] == "error"
        assert "min_importance must be 1-10" in result["error"]


class TestPruneSuccess:
    def test_prune_dry_run(self, mock_cfg, mock_store):
        result = memory(action="prune", dry_run=True)
        assert result["status"] == "success"
        mock_store.prune.assert_called_once()
        call_kwargs = mock_store.prune.call_args.kwargs
        assert call_kwargs["dry_run"] is True

    def test_prune_with_filters(self, mock_cfg, mock_store):
        memory(action="prune", max_age_days=7, min_importance=5, dry_run=False)
        call_kwargs = mock_store.prune.call_args.kwargs
        assert call_kwargs["max_age_days"] == 7
        assert call_kwargs["min_importance"] == 5
        assert call_kwargs["dry_run"] is False
