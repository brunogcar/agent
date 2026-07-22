"""Tests for HiTL approval gate (v3.4 #38)."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class TestHitlGateDisabled:
    """When AUTOCODE_HITL_ENABLED=0 (default), gate is a no-op."""

    def test_disabled_returns_empty(self, base_state):
        from workflows.autocode_impl.nodes.hitl_gate import node_hitl_gate
        # [v3.4 #38] Patch the attribute on the shared cfg singleton — matches
        # the swarm_integration test pattern. Module-level `from core.config
        # import cfg` binds to the singleton, so attribute patches propagate.
        with patch("core.config.cfg.autocode_hitl_enabled", False):
            result = node_hitl_gate(base_state)
        assert result == {}


class TestHitlGateEnabled:
    """When AUTOCODE_HITL_ENABLED=1, gate pauses unless approved."""

    def test_enabled_not_approved_returns_awaiting(self, base_state):
        from workflows.autocode_impl.nodes.hitl_gate import node_hitl_gate
        base_state["hitl_approved"] = False
        with patch("core.config.cfg.autocode_hitl_enabled", True):
            with patch("core.observability.checkpoint.save_checkpoint") as mock_save:
                result = node_hitl_gate(base_state)
        assert result["status"] == "awaiting_approval"
        mock_save.assert_called_once()

    def test_enabled_approved_returns_empty(self, base_state):
        from workflows.autocode_impl.nodes.hitl_gate import node_hitl_gate
        base_state["hitl_approved"] = True
        with patch("core.config.cfg.autocode_hitl_enabled", True):
            result = node_hitl_gate(base_state)
        assert result == {}

    def test_enabled_saves_checkpoint(self, base_state):
        from workflows.autocode_impl.nodes.hitl_gate import node_hitl_gate
        base_state["hitl_approved"] = False
        base_state["trace_id"] = "test-hitl-001"
        with patch("core.config.cfg.autocode_hitl_enabled", True):
            with patch("core.observability.checkpoint.save_checkpoint") as mock_save:
                node_hitl_gate(base_state)
            mock_save.assert_called_once_with("test-hitl-001", "hitl", base_state)


class TestHitlRouting:
    """Test route_after_hitl_gate."""

    def test_awaiting_routes_to_end(self, base_state):
        from workflows.autocode_impl.routes import route_after_hitl_gate
        base_state["status"] = "awaiting_approval"
        assert route_after_hitl_gate(base_state) == "END"

    def test_approved_routes_to_commit(self, base_state):
        from workflows.autocode_impl.routes import route_after_hitl_gate
        base_state["status"] = "running"
        assert route_after_hitl_gate(base_state) == "node_commit"

    def test_success_routes_to_commit(self, base_state):
        from workflows.autocode_impl.routes import route_after_hitl_gate
        base_state["status"] = "success"
        assert route_after_hitl_gate(base_state) == "node_commit"

    # [v3.11.1 B2-fix] The v3.11 B2 fix introduced hitl_checkpoint_failed but
    # the router only checked awaiting_approval → hitl_checkpoint_failed fell
    # through to node_commit, bypassing HiTL entirely. These tests cover the
    # end-to-end path (node return → router decision) that v3.11 missed.

    def test_checkpoint_failed_routes_to_end(self, base_state):
        """[v3.11.1 B2-fix] hitl_checkpoint_failed → END (NOT node_commit).
        Pre-v3.11.1, this fell through to node_commit, bypassing HiTL."""
        from workflows.autocode_impl.routes import route_after_hitl_gate
        base_state["status"] = "hitl_checkpoint_failed"
        assert route_after_hitl_gate(base_state) == "END"

    def test_failed_routes_to_end(self, base_state):
        """[v3.11.1 B2-fix] Any non-running/success status → END (fail safe)."""
        from workflows.autocode_impl.routes import route_after_hitl_gate
        base_state["status"] = "failed"
        assert route_after_hitl_gate(base_state) == "END"

    def test_error_routes_to_end(self, base_state):
        """[v3.11.1 B2-fix] error status → END (fail safe)."""
        from workflows.autocode_impl.routes import route_after_hitl_gate
        base_state["status"] = "error"
        assert route_after_hitl_gate(base_state) == "END"

    def test_empty_status_routes_to_commit(self, base_state):
        """[v3.11.1 B2-fix] Empty/missing status → node_commit (HiTL disabled
        path — node_hitl_gate returns {} so status stays at whatever it was)."""
        from workflows.autocode_impl.routes import route_after_hitl_gate
        base_state["status"] = ""
        assert route_after_hitl_gate(base_state) == "node_commit"

    def test_unknown_status_routes_to_end(self, base_state):
        """[v3.11.1 B2-fix] Unrecognized status → END (fail safe by default).
        This is the key property of the allow-list approach: any future new
        status fails safe instead of silently committing."""
        from workflows.autocode_impl.routes import route_after_hitl_gate
        base_state["status"] = "some_future_status"
        assert route_after_hitl_gate(base_state) == "END"


class TestCreateSkillHitlCheck:
    """create_skill should pause when HiTL enabled and not approved."""

    def test_create_skill_pauses_when_hitl_enabled(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.create_skill import node_create_skill
        base_state["task_type"] = "create_skill"
        base_state["hitl_approved"] = False
        with patch("core.config.cfg.autocode_hitl_enabled", True):
            with patch("core.observability.checkpoint.save_checkpoint"):
                result = node_create_skill(base_state)
        assert result["status"] == "awaiting_approval"

    def test_create_skill_proceeds_when_approved(self, base_state, temp_workspace):
        from workflows.autocode_impl.nodes.create_skill import node_create_skill
        base_state["task_type"] = "create_skill"
        base_state["hitl_approved"] = True
        base_state["dry_run"] = True  # avoid actual file writes
        with patch("core.config.cfg.autocode_hitl_enabled", True):
            with patch("workflows.autocode_impl.nodes.create_skill._call") as mock_call:
                mock_call.return_value = '{"skill_name": "test", "skill_file": "def run(): pass", "explanation": "test"}'
                result = node_create_skill(base_state)
        # Should NOT be awaiting_approval — should proceed normally
        assert result.get("status") != "awaiting_approval"


# ===========================================================================
# [v3.11 B2] Checkpoint-save failure surfaced (was: silently swallowed)
# ===========================================================================


class TestHitlCheckpointFailure:
    """[v3.11 B2] When save_checkpoint raises, the gate must return an error
    status (was: silently swallowed via `except Exception: pass` → returned
    awaiting_approval as if the pause succeeded → on resume, no checkpoint
    found → full restart from node_classify_task, re-executing LLM code
    generation, potentially producing a different implementation).
    """

    def test_checkpoint_failure_surfaces_error(self, base_state):
        """save_checkpoint raises → return status=hitl_checkpoint_failed (NOT awaiting_approval)."""
        from workflows.autocode_impl.nodes.hitl_gate import node_hitl_gate
        base_state["hitl_approved"] = False
        base_state["trace_id"] = "test-hitl-fail-001"
        with patch("core.config.cfg.autocode_hitl_enabled", True), \
             patch("core.observability.checkpoint.save_checkpoint",
                   side_effect=OSError("disk full")):
            result = node_hitl_gate(base_state)
        assert result["status"] == "hitl_checkpoint_failed"
        assert "disk full" in result["error"]
        assert "checkpoint" in result["error"].lower()

    def test_checkpoint_success_returns_awaiting(self, base_state):
        """save_checkpoint succeeds → return status=awaiting_approval (unchanged behavior)."""
        from workflows.autocode_impl.nodes.hitl_gate import node_hitl_gate
        base_state["hitl_approved"] = False
        base_state["trace_id"] = "test-hitl-ok-001"
        with patch("core.config.cfg.autocode_hitl_enabled", True), \
             patch("core.observability.checkpoint.save_checkpoint") as mock_save:
            result = node_hitl_gate(base_state)
        assert result["status"] == "awaiting_approval"
        mock_save.assert_called_once()
