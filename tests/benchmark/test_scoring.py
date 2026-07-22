"""tests/benchmark/test_scoring.py — Tests for scoring calculations.

Covers:
  calculate_task_score — formula (correctness*70 + format*20 + speed*10)
  calculate_role_score — averaging
  categorize_failure — all 7 categories
  consistency_score — std_dev + wobble
  calculate_difficulty_breakdown
"""
from __future__ import annotations

import pytest

from benchmark.scoring import (
    calculate_task_score,
    calculate_role_score,
    categorize_failure,
    consistency_score,
    calculate_difficulty_breakdown,
    ROLE_TARGET_LATENCY,
    AGENT_MODE_LATENCY_BUFFER,
)


# ===========================================================================
# calculate_task_score
# ===========================================================================


class TestCalculateTaskScore:
    def test_perfect_score(self):
        """Perfect correctness + format + fast latency = 100."""
        result = calculate_task_score(
            correctness=1.0, format_score=1.0, latency=0.5,
            tokens=10, timeout=120, role="router",
        )
        assert result["final"] == 100.0
        assert result["correctness"] == 1.0
        assert result["format"] == 1.0
        assert result["speed"] == 1.0

    def test_zero_correctness(self):
        """0 correctness → max 30 (format*20 + speed*10)."""
        result = calculate_task_score(
            correctness=0.0, format_score=1.0, latency=0.5,
            tokens=10, timeout=120, role="router",
        )
        assert result["final"] == 30.0  # 0*70 + 1*20 + 1*10

    def test_half_correctness(self):
        """0.5 correctness → 35 + format + speed."""
        result = calculate_task_score(
            correctness=0.5, format_score=1.0, latency=0.5,
            tokens=10, timeout=120, role="router",
        )
        assert result["final"] == 65.0  # 35 + 20 + 10

    def test_speed_decay(self):
        """Latency above target → speed < 1.0."""
        # router target = 2.0s; latency = 3.0s → speed = 1 - (3-2)/2 = 0.5
        result = calculate_task_score(
            correctness=1.0, format_score=1.0, latency=3.0,
            tokens=10, timeout=120, role="router",
        )
        assert result["speed"] == 0.5
        assert result["final"] == 95.0  # 70 + 20 + 5

    def test_speed_zero_at_2x_target(self):
        """Latency at 2x target → speed = 0."""
        # router target = 2.0s; latency = 4.0s → speed = 1 - (4-2)/2 = 0
        result = calculate_task_score(
            correctness=1.0, format_score=1.0, latency=4.0,
            tokens=10, timeout=120, role="router",
        )
        assert result["speed"] == 0.0
        assert result["final"] == 90.0  # 70 + 20 + 0

    def test_agent_mode_latency_buffer(self):
        """v1.3: agent_mode adds buffer to target latency."""
        # code target = 15s; agent_mode buffer = +1.0s → 16s target
        # latency = 15.5s → under target (16s) → speed = 1.0
        result_raw = calculate_task_score(
            correctness=1.0, format_score=1.0, latency=15.5,
            tokens=10, timeout=120, role="code", agent_mode=False,
        )
        result_agent = calculate_task_score(
            correctness=1.0, format_score=1.0, latency=15.5,
            tokens=10, timeout=120, role="code", agent_mode=True,
        )
        # Raw: 15.5 > 15 → speed < 1.0
        assert result_raw["speed"] < 1.0
        # Agent: 15.5 < 16 → speed = 1.0
        assert result_agent["speed"] == 1.0

    def test_zero_latency(self):
        """latency=0 → speed=1.0 (edge case)."""
        result = calculate_task_score(
            correctness=1.0, format_score=1.0, latency=0,
            tokens=10, timeout=120, role="router",
        )
        assert result["speed"] == 1.0

    def test_result_has_all_fields(self):
        result = calculate_task_score(
            correctness=0.8, format_score=0.9, latency=1.0,
            tokens=42, timeout=120, role="router",
        )
        assert "correctness" in result
        assert "format" in result
        assert "speed" in result
        assert "latency" in result
        assert "tokens" in result
        assert "final" in result
        assert result["tokens"] == 42
        assert result["latency"] == 1.0


# ===========================================================================
# calculate_role_score
# ===========================================================================


class TestCalculateRoleScore:
    def test_empty_list(self):
        result = calculate_role_score([])
        assert result["final"] == 0.0
        assert result["tasks"] == 0

    def test_average(self):
        scores = [
            {"correctness": 1.0, "format": 1.0, "speed": 1.0, "latency": 1.0, "tokens": 10, "final": 100.0},
            {"correctness": 0.5, "format": 0.5, "speed": 0.5, "latency": 2.0, "tokens": 20, "final": 50.0},
        ]
        result = calculate_role_score(scores)
        assert result["final"] == 75.0  # (100 + 50) / 2
        assert result["correctness"] == 0.75
        assert result["tasks"] == 2

    def test_single_task(self):
        scores = [{"correctness": 1.0, "format": 1.0, "speed": 1.0, "latency": 1.0, "tokens": 10, "final": 100.0}]
        result = calculate_role_score(scores)
        assert result["final"] == 100.0


# ===========================================================================
# categorize_failure
# ===========================================================================


class TestCategorizeFailure:
    def test_timeout(self):
        result = {"error": "request timeout after 30s", "output": "", "score": {}}
        assert categorize_failure(result) == "timeout"

    def test_llm_error(self):
        result = {"error": "LLM error: model not loaded", "output": "", "score": {}}
        assert categorize_failure(result) == "llm_error"

    def test_exception(self):
        result = {"error": "exception in validator", "output": "", "score": {}}
        assert categorize_failure(result) == "exception"

    def test_empty_output(self):
        result = {"error": "", "output": "", "score": {}}
        assert categorize_failure(result) == "empty_output"

    def test_format_error(self):
        """format < 0.5 but correctness >= 0.5 → format_error."""
        result = {"error": "", "output": "some output", "score": {"format": 0.3, "correctness": 0.8}}
        assert categorize_failure(result) == "format_error"

    def test_wrong_answer(self):
        """correctness < 0.5 → wrong_answer."""
        result = {"error": "", "output": "some output", "score": {"format": 0.8, "correctness": 0.3}}
        assert categorize_failure(result) == "wrong_answer"

    def test_unknown(self):
        """format >= 0.5 + correctness >= 0.5 but still failing → unknown."""
        result = {"error": "", "output": "some output", "score": {"format": 0.6, "correctness": 0.6}}
        assert categorize_failure(result) == "unknown"


# ===========================================================================
# consistency_score
# ===========================================================================


class TestConsistencyScore:
    def test_single_run(self):
        """1 run → no std_dev."""
        result = consistency_score([{"final": 80.0}])
        assert result["std_dev"] == 0.0
        assert result["wobble"] is False

    def test_empty(self):
        result = consistency_score([])
        assert result["std_dev"] == 0.0
        assert result["wobble"] is False

    def test_consistent_scores(self):
        """Low variance → no wobble."""
        result = consistency_score([{"final": 80.0}, {"final": 82.0}, {"final": 81.0}])
        assert result["std_dev"] < 20.0
        assert result["wobble"] is False

    def test_wobble(self):
        """High variance (>20 std_dev) → wobble=True."""
        result = consistency_score([{"final": 100.0}, {"final": 50.0}, {"final": 10.0}])
        assert result["std_dev"] > 20.0
        assert result["wobble"] is True


# ===========================================================================
# calculate_difficulty_breakdown
# ===========================================================================


class TestDifficultyBreakdown:
    def test_basic_breakdown(self):
        task_results = [
            {"difficulty": "easy", "status": "pass"},
            {"difficulty": "easy", "status": "fail"},
            {"difficulty": "medium", "status": "pass"},
            {"difficulty": "hard", "status": "fail"},
        ]
        result = calculate_difficulty_breakdown(task_results)
        assert result["easy"]["total"] == 2
        assert result["easy"]["pass"] == 1
        assert result["medium"]["total"] == 1
        assert result["medium"]["pass"] == 1
        assert result["hard"]["total"] == 1
        assert result["hard"]["pass"] == 0

    def test_missing_difficulty_defaults_to_medium(self):
        task_results = [{"status": "pass"}]  # no difficulty field
        result = calculate_difficulty_breakdown(task_results)
        assert "medium" in result
        assert result["medium"]["total"] == 1

    def test_empty(self):
        result = calculate_difficulty_breakdown([])
        assert result == {}


# ===========================================================================
# Constants
# ===========================================================================


class TestConstants:
    def test_role_target_latency_exists(self):
        assert "router" in ROLE_TARGET_LATENCY
        assert "executor" in ROLE_TARGET_LATENCY
        assert "planner" in ROLE_TARGET_LATENCY

    def test_agent_mode_buffer_exists(self):
        assert "code" in AGENT_MODE_LATENCY_BUFFER
        assert "planner" in AGENT_MODE_LATENCY_BUFFER
