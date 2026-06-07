"""scoring.py — Score calculation for benchmark results.

Formula: correctness*60 + format*20 + speed*10 + efficiency*10 = 0-100
"""
from __future__ import annotations

def calculate_task_score(
    correctness: float,
    format_score: float,
    latency: float,
    tokens: int,
    timeout: int = 120,
) -> dict:
    """Calculate per-task score.

    Returns dict with breakdown and final score (0-100).
    """
    # Speed: 1.0 if fast, 0.0 if timeout exceeded
    speed = max(0.0, 1.0 - (latency / timeout))

    # Efficiency: 1.0 if few tokens, 0.0 if >2000 tokens
    efficiency = max(0.0, 1.0 - (tokens / 2000))

    final = (correctness * 60) + (format_score * 20) + (speed * 10) + (efficiency * 10)

    return {
        "correctness": round(correctness, 2),
        "format": round(format_score, 2),
        "speed": round(speed, 2),
        "efficiency": round(efficiency, 2),
        "latency": round(latency, 2),
        "tokens": tokens,
        "final": round(final, 1),
    }

def calculate_role_score(task_scores: list[dict]) -> dict:
    """Average scores across tasks for a role."""
    if not task_scores:
        return {"final": 0.0, "tasks": 0}

    avg = {
        "correctness": round(sum(t["correctness"] for t in task_scores) / len(task_scores), 2),
        "format": round(sum(t["format"] for t in task_scores) / len(task_scores), 2),
        "speed": round(sum(t["speed"] for t in task_scores) / len(task_scores), 2),
        "efficiency": round(sum(t["efficiency"] for t in task_scores) / len(task_scores), 2),
        "latency": round(sum(t["latency"] for t in task_scores) / len(task_scores), 2),
        "tokens": round(sum(t["tokens"] for t in task_scores) / len(task_scores), 0),
        "final": round(sum(t["final"] for t in task_scores) / len(task_scores), 1),
        "tasks": len(task_scores),
    }
    return avg
