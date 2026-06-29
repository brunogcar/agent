"""scoring.py — Score calculation for benchmark results.

Formula: correctness*70 + format*20 + speed*10 = 0-100
 correctness: did it answer correctly? (0.0-1.0 from validator)
 format: was output format valid? (0.0-1.0 from validator)
 speed: soft curve: 1.0 at/below target, linear decay to 0 at 2x target
 efficiency: REMOVED - penalized verbose correct answers. tokens kept as metadata.
"""
from __future__ import annotations

# Target latency per role (seconds) — what we consider "fast enough"
ROLE_TARGET_LATENCY = {
    "classify": 2.0, "route": 2.0, "router": 2.0,
    "summarize": 5.0, "extract": 5.0, "research": 15.0,
    "critique": 10.0, "analyze": 10.0, "code": 15.0,
    "review": 10.0, "executor": 15.0, "planner": 20.0,
    "vision": 10.0, "consultor": 10.0,
    # NEW: Autonomous maintenance roles
    "refactor": 15.0, "test": 15.0, "document": 10.0,
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

def categorize_failure(result: dict) -> str:
    """Categorize why a task failed.

    Returns one of: timeout, llm_error, exception, empty_output,
    format_error, wrong_answer, unknown.
    """
    error = str(result.get("error", "")).lower()
    output = result.get("output", "")
    score = result.get("score", {})

    if "timeout" in error:
        return "timeout"
    if "llm error" in error or "unknown llm error" in error:
        return "llm_error"
    if "exception" in error:
        return "exception"
    if not output.strip():
        return "empty_output"

    fmt = score.get("format", 0)
    corr = score.get("correctness", 0)
    if fmt < 0.5 and corr >= 0.5:
        return "format_error"
    if corr < 0.5:
        return "wrong_answer"
    return "unknown"

def consistency_score(run_scores: list[dict]) -> dict:
    """Compute consistency metrics across multiple runs of the same task.

    Returns std_dev on final scores (0-100 scale), wobble flag, and bonus.
    """
    if not run_scores or len(run_scores) < 2:
        return {"std_dev": 0.0, "wobble": False}

    finals = [s["final"] for s in run_scores]
    n = len(finals)
    mean = sum(finals) / n
    variance = sum((x - mean) ** 2 for x in finals) / n
    std_dev = variance ** 0.5

    # Wobble: std_dev > 20 points on 0-100 scale
    wobble = std_dev > 20.0

    return {"std_dev": round(std_dev, 1), "wobble": wobble}

def calculate_difficulty_breakdown(task_results: list[dict]) -> dict:
    """Group task results by difficulty and count passes.

    Returns {difficulty: {"total": int, "pass": int}, ...}
    """
    breakdown = {}
    for tr in task_results:
        diff = tr.get("difficulty", "medium")
        if diff not in breakdown:
            breakdown[diff] = {"total": 0, "pass": 0}
        breakdown[diff]["total"] += 1
        if tr.get("status") == "pass":
            breakdown[diff]["pass"] += 1
    return breakdown
