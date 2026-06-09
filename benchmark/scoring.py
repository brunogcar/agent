"""scoring.py — Score calculation for benchmark results.

Formula: correctness*70 + format*20 + speed*10 = 0-100
  correctness: did it answer correctly? (0.0-1.0 from validator)
  format:      was output format valid? (0.0-1.0 from validator)
  speed:       soft curve: 1.0 at/below target, linear decay to 0 at 2x target
  efficiency:  REMOVED - penalized verbose correct answers. tokens kept as metadata.
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
    # Speed: soft degradation curve.
    # Full credit at or below target latency. Linear decay to 0 at 2x target.
    # Example: classify target=2s: 1s->1.0, 2s->1.0, 3s->0.5, 4s->0.0
    # Distinguishes fast vs very fast (unlike old hard ceiling target/latency).
    target = ROLE_TARGET_LATENCY.get(role, 5.0)
    if latency <= 0:
        speed = 1.0
    elif latency <= target:
        speed = 1.0
    else:
        speed = max(0.0, 1.0 - (latency - target) / target)

    # Correctness dominates (70%), format matters (20%), speed is bonus (10%).
    # Efficiency removed: penalized verbose correct answers. tokens = raw metadata.
    final = (correctness * 70) + (format_score * 20) + (speed * 10)

    return {
        "correctness": round(correctness, 2),
        "format": round(format_score, 2),
        "speed": round(speed, 2),
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
        "latency": round(sum(t["latency"] for t in task_scores) / len(task_scores), 2),
        "tokens": round(sum(t["tokens"] for t in task_scores) / len(task_scores), 0),
        "final": round(sum(t["final"] for t in task_scores) / len(task_scores), 1),
        "tasks": len(task_scores),
    }
    return avg