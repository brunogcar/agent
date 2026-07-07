"""tests/workflows/base/test_node_helpers.py
Tests for node_step, node_error, node_done helpers.
"""
from __future__ import annotations


class TestNodeStep:
    """node_step is a HELPER (side-effect only), not a LangGraph node. Returns None."""

    def test_returns_none(self, base_state):
        from workflows.base import node_step
        result = node_step(base_state, "search", "searching web", query="test")
        assert result is None, "node_step should return None (side-effect helper)"

    def test_does_not_mutate_state(self, base_state):
        from workflows.base import node_step
        base_state["status"] = "running"
        node_step(base_state, "search", "searching web")
        assert base_state["status"] == "running", "node_step mutated state in place!"

    def test_logs_to_tracer(self, base_state, mocker):
        mock_tracer = mocker.patch("workflows.base.tracer")
        from workflows.base import node_step
        node_step(base_state, "execute", "running code", chars=42)
        mock_tracer.step.assert_called_once_with("t1", "execute", "running code", chars=42)

    def test_no_trace_id_skips_logging(self, mocker):
        from workflows.base import node_step
        mock_tracer = mocker.patch("workflows.base.tracer")
        node_step({"trace_id": "", "goal": "g"}, "node", "msg")
        assert not mock_tracer.step.called

    def test_checkpoint_true_saves_checkpoint(self, base_state, mocker):
        from workflows.base import node_step
        mocker.patch("workflows.base.tracer")  # silence tracer
        mock_save = mocker.patch("workflows.helpers.checkpoint.save_checkpoint")
        node_step(base_state, "execute", "running", checkpoint=True)
        mock_save.assert_called_once_with("t1", "execute", base_state)


class TestNodeError:
    def test_sets_failed_and_error_message(self, base_state):
        from workflows.base import node_error
        update = node_error(base_state, "test_node", "something broke")
        assert update["status"] == "failed"
        assert update["error"] == "something broke"

    def test_never_empty_error_message(self, base_state):
        from workflows.base import node_error
        update = node_error(base_state, "some_node", "")
        assert update["status"] == "failed"
        assert len(update.get("error", "")) > 0, "error message must not be empty"

    def test_returns_partial_update(self, base_state):
        from workflows.base import node_error
        update = node_error(base_state, "node", "err")
        assert isinstance(update, dict)
        assert "status" in update
        assert "error" in update
        assert "goal" not in update, "Partial dict must not echo unchanged state keys"

    def test_saves_full_state_checkpoint(self, base_state, mocker):
        """[v1.2 #1] node_error must save the FULL state, not just {status, error}."""
        from workflows.base import node_error
        mock_save = mocker.patch("workflows.helpers.checkpoint.save_checkpoint")
        base_state["memory_context"] = "some context"
        node_error(base_state, "execute", "failed")
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][2]
        assert saved_state["status"] == "failed"
        assert saved_state["error"] == "failed"
        assert saved_state["memory_context"] == "some context", (
            "node_error must save full state for resume — was only saving {status, error}"
        )


class TestNodeDone:
    def test_sets_success_and_result(self, base_state):
        from workflows.base import node_done
        update = node_done(base_state, result="final output")
        assert update["status"] == "success"
        assert update["result"] == "final output"

    def test_returns_partial_update(self, base_state):
        from workflows.base import node_done
        update = node_done(base_state, result="done")
        assert isinstance(update, dict)
        assert "status" in update
        assert "result" in update
        assert "goal" not in update

    def test_artifacts_default_to_empty_list(self, base_state):
        from workflows.base import node_done
        update = node_done(base_state, result="done")
        assert update["artifacts"] == []

    def test_saves_success_checkpoint(self, base_state, mocker):
        """[v1.2 #7] node_done must save a checkpoint before mark_complete."""
        from workflows.base import node_done
        mock_save = mocker.patch("workflows.helpers.checkpoint.save_checkpoint")
        mock_mark = mocker.patch("workflows.helpers.checkpoint.mark_complete")
        mock_tracer = mocker.patch("workflows.base.tracer")
        node_done(base_state, result="done", artifacts=["file.py"])
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][2]
        assert saved_state["status"] == "success"
        assert saved_state["result"] == "done"
