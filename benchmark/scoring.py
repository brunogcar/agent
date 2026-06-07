"""scoring.py — Score calculation for benchmark results.

Formula: correctness*60 + format*20 + speed*10 + efficiency*10 = 0-100
"""
from __future__ import annotations
# Target latency per role (seconds) — what we consider "fast enough"
ROLE_TARGET_LATENCY = {
    "classify": 2.0, "route": 2.0, "router": 2.0,
    "summarize": 5.0, "extract": 5.0, "research": 15.0,
    "critique": 10.0, "analyze": 10.0, "code": 15.0,
    "review": 10.0, "executor": 15.0, "planner": 20.0,
    "vision": 10.0, "consultor": 10.0,
}

def calculate_task_score(
    correctness: float,
    format_score: float,
    latency: float,
    tokens: int,
    timeout: int = 120,
    role: str = "router",
) -> dict:
    """Calculate per-task score.

    Returns dict with breakdown and final score (0-100).
    """
    # Speed: 1.0 if fast, 0.0 if timeout exceeded
    # Speed: 1.0 if under target latency, scales down linearly. 0.0 if > 10x target.
    target = ROLE_TARGET_LATENCY.get(role, 5.0)
    speed = max(0.0, min(1.0, target / latency)) if latency > 0 else 1.0

    # Efficiency: 1.0 if few tokens, 0.0 if >2000 tokens
    # Efficiency removed from scoring — token count kept as metadata only.
    # Penalizing token count rewards terse wrong answers. See tokens in report.
    efficiency = 0.0

    # Correctness dominates (70%), format matters (20%), speed is bonus (10%)
    # Efficiency dropped — it penalized thorough correct answers unfairly
    final = (correctness * 70) + (format_score * 20) + (speed * 10)

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