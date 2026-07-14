"""[v1.1 #18] Tests for router swarm fallback routing.

When ROUTER_SWARM_FALLBACK=1 and the heuristic router produces a
low-confidence decision (the catch-all step #18, no keywords matched),
the router asks the swarm to vote on the workflow type. If the swarm
returns unanimous/majority agreement on a valid workflow type, that
overrides the heuristic; otherwise the heuristic stands.

These tests do NOT make real provider calls — tools.swarm.swarm is
mocked on its home module (the router does a local import, so patching
the source-of-truth attribute works).
"""
from __future__ import annotations

import pytest


def _vote_result(agreement: str, winner: str, successful_count: int = 3) -> dict:
    """Build a synthetic swarm vote() success result for tests."""
    return {
        "status": "success",
        "data": {
            "agreement": agreement,
            "groups": [{"providers": ["openai"], "count": successful_count, "preview": winner}],
            "successful_count": successful_count,
            "provider_count": successful_count,
        },
    }


class TestSwarmFallbackRouting:
    """[v1.1 #18] Swarm vote-based routing for low-confidence decisions."""

    def test_low_confidence_triggers_swarm_when_enabled(self, mocker):
        """When ROUTER_SWARM_FALLBACK=1 and heuristic returns low confidence,
        the router asks the swarm; a unanimous 'autocode' verdict overrides
        the heuristic and is returned to the caller.
        """
        from core.router import TaskRouter

        mocker.patch("core.config.cfg.router_swarm_fallback", True)
        # Force heuristic path: _model_route returns None.
        mocker.patch.object(TaskRouter, "_model_route", return_value=None)
        mock_swarm = mocker.patch("tools.swarm.swarm")
        mock_swarm.return_value = _vote_result("unanimous", "autocode", successful_count=3)

        router = TaskRouter()
        # Goal that falls through to heuristic step #18 (catch-all, low confidence).
        decision = router.route("random gibberish with no routing keywords", trace_id="t1")

        assert mock_swarm.called
        assert decision.workflow == "autocode"
        assert decision.confidence == "medium"
        assert "Swarm vote" in decision.reason

    def test_low_confidence_skips_swarm_when_disabled(self, mocker):
        """When ROUTER_SWARM_FALLBACK=0 (default), the swarm is never consulted
        even for low-confidence decisions; the heuristic result stands.
        """
        from core.router import TaskRouter

        mocker.patch("core.config.cfg.router_swarm_fallback", False)
        mocker.patch.object(TaskRouter, "_model_route", return_value=None)
        mock_swarm = mocker.patch("tools.swarm.swarm")

        router = TaskRouter()
        decision = router.route("random gibberish with no routing keywords", trace_id="t2")

        assert not mock_swarm.called
        # Heuristic step #18 catch-all: research, low confidence.
        assert decision.workflow == "research"
        assert decision.confidence == "low"

    def test_swarm_fallback_skipped_when_heuristic_is_high_confidence(self, mocker):
        """Even with ROUTER_SWARM_FALLBACK=1, the swarm is only consulted for
        low-confidence heuristic decisions. A high-confidence match (e.g.
        'create a chart' -> report) must NOT trigger the swarm.
        """
        from core.router import TaskRouter

        mocker.patch("core.config.cfg.router_swarm_fallback", True)
        mocker.patch.object(TaskRouter, "_model_route", return_value=None)
        mock_swarm = mocker.patch("tools.swarm.swarm")

        router = TaskRouter()
        # 'create a chart' matches _RE_REPORT at step #1 -> confidence='high'.
        decision = router.route("create a chart of quarterly sales", trace_id="t3")

        assert not mock_swarm.called
        assert decision.workflow == "direct"
        assert decision.tool == "report"
        assert decision.confidence == "high"

    def test_swarm_fallback_returns_none_on_low_agreement(self, mocker):
        """If the swarm returns split/disagreement/single_response, the
        fallback returns None — the swarm verdict is no more confident than
        the heuristic, so the heuristic stands.
        """
        from core.router import TaskRouter

        mocker.patch("core.config.cfg.router_swarm_fallback", True)
        mocker.patch.object(TaskRouter, "_model_route", return_value=None)
        mock_swarm = mocker.patch("tools.swarm.swarm")
        mock_swarm.return_value = _vote_result("disagreement", "autocode", successful_count=3)

        router = TaskRouter()
        decision = router.route("random gibberish with no routing keywords", trace_id="t4")

        assert mock_swarm.called
        # Swarm was inconclusive -> heuristic decision stands.
        assert decision.workflow == "research"
        assert decision.confidence == "low"

    def test_swarm_fallback_returns_none_on_invalid_workflow(self, mocker):
        """If the swarm's winning preview is not a valid workflow type
        (e.g. the model returned 'banana'), the fallback returns None.
        """
        from core.router import TaskRouter

        mocker.patch("core.config.cfg.router_swarm_fallback", True)
        mocker.patch.object(TaskRouter, "_model_route", return_value=None)
        mock_swarm = mocker.patch("tools.swarm.swarm")
        mock_swarm.return_value = _vote_result("unanimous", "banana", successful_count=3)

        router = TaskRouter()
        decision = router.route("random gibberish with no routing keywords", trace_id="t5")

        assert mock_swarm.called
        # Invalid winner -> heuristic decision stands.
        assert decision.workflow == "research"
        assert decision.confidence == "low"

    def test_swarm_fallback_returns_none_on_swarm_failure(self, mocker):
        """If swarm() returns status != 'success' (e.g. no providers
        configured), the fallback returns None — non-fatal.
        """
        from core.router import TaskRouter

        mocker.patch("core.config.cfg.router_swarm_fallback", True)
        mocker.patch.object(TaskRouter, "_model_route", return_value=None)
        mock_swarm = mocker.patch("tools.swarm.swarm")
        mock_swarm.return_value = {"status": "error", "error": "no providers configured"}

        router = TaskRouter()
        decision = router.route("random gibberish with no routing keywords", trace_id="t6")

        assert mock_swarm.called
        # Swarm failed -> heuristic decision stands.
        assert decision.workflow == "research"
        assert decision.confidence == "low"

    def test_swarm_fallback_swallows_exception(self, mocker):
        """If swarm() raises (programming error, import failure, etc.),
        the fallback catches the exception, logs a warning, and returns None.
        The router must NEVER crash because of the swarm fallback.
        """
        from core.router import TaskRouter

        mocker.patch("core.config.cfg.router_swarm_fallback", True)
        mocker.patch.object(TaskRouter, "_model_route", return_value=None)
        mock_swarm = mocker.patch("tools.swarm.swarm")
        mock_swarm.side_effect = RuntimeError("swarm imploded")

        router = TaskRouter()
        # Should NOT raise — exception is swallowed inside _swarm_fallback_route.
        decision = router.route("random gibberish with no routing keywords", trace_id="t7")

        assert mock_swarm.called
        # Exception swallowed -> heuristic decision stands.
        assert decision.workflow == "research"
        assert decision.confidence == "low"

    def test_swarm_fallback_uses_deterministic_temperature(self, mocker):
        """[v1.1 #21] The swarm vote call MUST use temperature=0 so the
        agreement classification measures genuine model disagreement, not
        sampling noise. If a future refactor changes this, the vote becomes
        meaningless.
        """
        from core.router import TaskRouter

        mocker.patch("core.config.cfg.router_swarm_fallback", True)
        mocker.patch.object(TaskRouter, "_model_route", return_value=None)
        mock_swarm = mocker.patch("tools.swarm.swarm")
        mock_swarm.return_value = _vote_result("unanimous", "research", successful_count=3)

        router = TaskRouter()
        router.route("random gibberish with no routing keywords", trace_id="t8")

        assert mock_swarm.called
        _, kwargs = mock_swarm.call_args
        assert kwargs.get("temperature") == 0
        assert kwargs.get("action") == "vote"
        # max_tokens should be small — we only need one word.
        assert kwargs.get("max_tokens") <= 50
