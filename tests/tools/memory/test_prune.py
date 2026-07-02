"""Tests for the prune action."""
from __future__ import annotations

from tools.memory import memory


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
