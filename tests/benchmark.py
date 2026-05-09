"""
tests/benchmark.py — Model performance benchmark for the MCP Agent stack.

PURPOSE
-------
Measure and compare model performance across configuration changes:
  - Swapping models (e.g. Qwen 3.5 → Qwen 7B)
  - Changing quantisation (Q4_0 → Q8_0)
  - Adjusting GPU offload layers
  - Tuning context window / batch size in LM Studio

Each run produces a timestamped JSON in workspace/benchmarks/ so you can
diff two files side-by-side to see exactly what changed.

WHAT IS MEASURED PER ROLE
--------------------------
  Router  (Nemotron) — routing accuracy on 8 classification tasks
                        deterministic: correct workflow name = pass
  Executor (Hermes)  — 3 code/math tasks (deterministic: execute output)
                        3 reasoning tasks (LLM self-judge with rubric)
  Planner  (Qwen)    — 4 planning tasks: valid JSON + sane step structure

METRICS
-------
  latency_ms      — wall-clock time for the model call
  tokens_per_sec  — from LM Studio usage.completion_tokens / latency
  correctness     — 0–100 per task, averaged per role
  composite       — 40% correctness + 40% speed_score + 20% efficiency_score
                    speed_score = min(1, baseline_tps / actual_tps) * 100
                    where baseline_tps = 15 tok/s (conservative local baseline)

HOW TO RUN
----------
  # All roles (< 5 min)
  python tests/benchmark.py

  # Single role (fast feedback during tuning)
  python tests/benchmark.py --role router
  python tests/benchmark.py --role executor
  python tests/benchmark.py --role planner

  # Tag the run (shows in JSON and summary for easy comparison)
  python tests/benchmark.py --tag "q8_offload32"

  # Compare two saved runs
  python tests/benchmark.py --compare workspace/benchmarks/run_A.json workspace/benchmarks/run_B.json

DESIGN DECISIONS
----------------
- Calls LM Studio API directly (no gateway, no cli() tool). This isolates each
  model so swapping one role doesn't contaminate the other roles' scores.
- LLM judge uses a SECOND Executor call with a strict 0/25/50/75/100 rubric.
  Using the same model as judge and subject is intentional: it tests whether
  the model can self-evaluate, which is a useful capability signal.
- Code tasks extract the first ```python block and actually execute it in a
  subprocess with a 10s timeout. This is the only reliable correctness signal
  for code — keyword matching is not.
- tokens_per_sec baseline of 15 is conservative for an RTX 5060 Ti 16GB with
  Q4_0 models. Adjust BASELINE_TPS if your hardware runs faster.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

# ── Bootstrap path ────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.config import cfg

# ── Constants ─────────────────────────────────────────────────────────────────

BASELINE_TPS   = 15.0   # tok/s — conservative Q4_0 baseline on RTX 5060 Ti 16 GB
                         # Raise this if your hardware is faster so speed scores reflect reality
CODE_TIMEOUT   = 10     # seconds — subprocess timeout for executing generated code
JUDGE_TOKENS   = 200    # max tokens for LLM judge responses (short rubric = cheaper)

# ── Path sanitizer ───────────────────────────────────────────────────────────
def _sanitize_filename(text: str) -> str:
    """Convert model/path names to valid filename characters."""
    return text.replace("/", "-").replace("\\", "-").strip("-_")

BENCH_DIR      = _ROOT / "workspace" / "benchmarks"


# ── LM Studio helper ──────────────────────────────────────────────────────────

def _lm_call(model: str, system: str, user: str, max_tokens: int = 512,
             temperature: float = 0.0) -> dict:
    """
    Single LM Studio chat completion.

    Returns:
      {
        "content":      str,    # model output
        "latency_ms":   float,
        "tokens_out":   int,    # completion tokens
        "tokens_in":    int,    # prompt tokens
        "tps":          float,  # tokens/sec (completion only)
        "error":        str,    # non-empty on failure
      }

    DECISION: temperature=0 by default for deterministic, reproducible results.
    Research/reasoning tasks use 0.1 to avoid degenerate empty outputs on some
    models while staying near-deterministic.
    """
    start = time.time()
    try:
        resp = requests.post(
            f"{cfg.lm_studio_base_url}/chat/completions",
            json={
                "model":       model,
                "messages":    [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                "temperature": temperature,
                "max_tokens":  max_tokens,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data       = resp.json()
        latency_ms = (time.time() - start) * 1000
        usage      = data.get("usage", {})
        tokens_out = usage.get("completion_tokens", 0)
        tokens_in  = usage.get("prompt_tokens", 0)
        tps        = (tokens_out / (latency_ms / 1000)) if latency_ms > 0 else 0
        content    = data["choices"][0]["message"]["content"].strip()
        return {"content": content, "latency_ms": round(latency_ms, 1),
                "tokens_out": tokens_out, "tokens_in": tokens_in,
                "tps": round(tps, 1), "error": ""}
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        return {"content": "", "latency_ms": round(latency_ms, 1),
                "tokens_out": 0, "tokens_in": 0, "tps": 0.0, "error": str(e)}


# ── Speed score helper ────────────────────────────────────────────────────────

def _speed_score(tps: float) -> float:
    """
    Convert tokens/sec to a 0–100 score relative to BASELINE_TPS.
    Score of 100 = at or above baseline. Score scales linearly below it.
    This means a faster config gets a higher score, not just 'pass'.
    """
    if tps <= 0:
        return 0.0
    return round(min(100.0, (tps / BASELINE_TPS) * 100), 1)


def _composite(correctness: float, tps: float) -> float:
    """
    40% correctness + 40% speed + 20% flat efficiency bonus if both > 0.
    Intentionally simple — one number to compare runs at a glance.
    """
    speed  = _speed_score(tps)
    eff    = 20.0 if (correctness > 0 and tps > 0) else 0.0
    return round(0.4 * correctness + 0.4 * speed + eff, 1)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER BENCHMARK
# ══════════════════════════════════════════════════════════════════════════════

# Each task: (user_message, expected_workflow)
# Expected workflows must match what routing/router.py actually uses.
# DECISION: 8 tasks chosen to cover all workflow types + edge cases.
# Correct answer is the workflow name Nemotron should output as JSON.

ROUTER_TASKS = [
    ("Search for the latest Python 3.13 release notes",           "research"),
    ("Fix the syntax error in tools/web.py line 42",              "autocode"),
    ("What is the SELIC rate today?",                             "research"),
    ("Calculate the mean of [4, 8, 15, 16, 23, 42]",             "data"),
    ("Add error handling to the file_ops compress action",        "autocode"),
    ("Analyze the CSV file in workspace/sales.csv",               "data"),
    ("Explain what ChromaDB is",                                  "research"),
    ("Refactor the _files_context function in autocode.py",       "autocode"),
]

_ROUTER_SYSTEM = """\
You are a task router for an AI agent. Classify the task into exactly one workflow.
Output ONLY a JSON object: {"workflow": "<name>"}
Valid workflow names: research | autocode | data
No explanation. No markdown."""


def run_router_benchmark() -> dict:
    """
    Test Nemotron's routing accuracy.

    Correctness: 1 point per correct workflow classification (max 8).
    Scaled to 0–100.
    """
    model   = cfg.router_model
    results = []
    total_tps, total_latency = 0.0, 0.0

    print(f"\n── Router ({model}) ──────────────────────────────────────")

    for task_text, expected in ROUTER_TASKS:
        r = _lm_call(model, _ROUTER_SYSTEM, f"Task: {task_text}",
                     max_tokens=40, temperature=0.0)

        # Parse workflow from response — be lenient about JSON wrapping
        got = ""
        if not r["error"]:
            try:
                got = json.loads(r["content"]).get("workflow", "").lower().strip()
            except Exception:
                # Fallback: extract first word that matches a known workflow
                for wf in ("research", "autocode", "data"):
                    if wf in r["content"].lower():
                        got = wf
                        break

        correct = (got == expected)
        total_tps     += r["tps"]
        total_latency += r["latency_ms"]

        status = "✓" if correct else f"✗ (got '{got}', expected '{expected}')"
        print(f"  {status:<40} {r['tps']:>5.1f} tok/s  {r['latency_ms']:>6.0f}ms"
              f"  | {task_text[:50]}")

        results.append({
            "task":     task_text,
            "expected": expected,
            "got":      got,
            "correct":  correct,
            **{k: r[k] for k in ("latency_ms", "tps", "tokens_out", "error")},
        })

    n            = len(ROUTER_TASKS)
    correct_n    = sum(1 for r in results if r["correct"])
    correctness  = round(correct_n / n * 100, 1)
    avg_tps      = round(total_tps / n, 1)
    avg_latency  = round(total_latency / n, 1)
    comp         = _composite(correctness, avg_tps)

    print(f"  Accuracy: {correct_n}/{n}  correctness={correctness}  "
          f"avg={avg_tps}tok/s  composite={comp}")

    return {
        "role":        "router",
        "model":       model,
        "tasks":       results,
        "correctness": correctness,
        "avg_tps":     avg_tps,
        "avg_latency_ms": avg_latency,
        "speed_score": _speed_score(avg_tps),
        "composite":   comp,
    }


# ══════════════════════════════════════════════════════════════════════════════
# EXECUTOR BENCHMARK
# ══════════════════════════════════════════════════════════════════════════════

# ── Deterministic tasks (code / math) ────────────────────────────────────────
# Each: (prompt, validator_fn)
# validator receives the raw model output string, returns (score 0–100, detail str)

def _extract_code(text: str) -> str:
    """Pull first ```python block or fall back to entire response."""
    m = re.search(r"```python\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def _run_code(code: str, check_expr: str) -> tuple[float, str]:
    """
    Execute code in a subprocess, then evaluate check_expr against its stdout.
    check_expr is a Python expression that receives `output` (str) → bool.
    Returns (score, detail).
    """
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        # Inject the check expression as an assertion at the end
        f.write(code + "\n")
        fname = f.name
    try:
        proc = subprocess.run(
            [sys.executable, fname],
            capture_output=True, text=True, timeout=CODE_TIMEOUT,
        )
        output = (proc.stdout + proc.stderr).strip()
        # Evaluate the check against the output
        passed = bool(eval(check_expr, {"output": output, "re": re}))  # noqa: S307
        score  = 100.0 if passed else 30.0  # partial credit for code that runs
        detail = output[:200] if output else "(no output)"
        if proc.returncode != 0 and not passed:
            score  = 10.0
            detail = f"returncode={proc.returncode} | {detail}"
        return score, detail
    except subprocess.TimeoutExpired:
        return 0.0, f"timeout after {CODE_TIMEOUT}s"
    except Exception as e:
        return 0.0, f"exec error: {e}"
    finally:
        Path(fname).unlink(missing_ok=True)


def _validate_code_task(response: str, check_expr: str) -> tuple[float, str]:
    code = _extract_code(response)
    # First check: is it valid Python syntax?
    try:
        ast.parse(code)
    except SyntaxError as e:
        return 5.0, f"syntax error: {e}"
    return _run_code(code, check_expr)


# Code tasks: (title, system_prompt, user_prompt, check_expr)
# check_expr: Python expression evaluated with `output` = stdout of the code
EXECUTOR_CODE_TASKS = [
    (
        "Fibonacci(10)",
        "You are a Python developer. Output ONLY a ```python code block. No explanation.",
        "Write a function fib(n) that returns the nth Fibonacci number (0-indexed). "
        "Print fib(10). Expected output: 55",
        # check: output contains 55
        "output.strip() == '55'",
    ),
    (
        "Word frequency counter",
        "You are a Python developer. Output ONLY a ```python code block. No explanation.",
        "Write a function word_freq(text) that returns a dict of word frequencies "
        "(case-insensitive). Test with: print(word_freq('the cat sat on the mat')['the']). "
        "Expected output: 2",
        "output.strip() == '2'",
    ),
    (
        "Celsius to Fahrenheit",
        "You are a Python developer. Output ONLY a ```python code block. No explanation.",
        "Write a function c_to_f(c) that converts Celsius to Fahrenheit. "
        "Print c_to_f(100). Expected output: 212.0",
        "output.strip() == '212.0'",
    ),
]

# ── LLM judge tasks (reasoning / research) ───────────────────────────────────
# Each: (title, user_prompt, rubric)
# rubric: what the judge checks. Score must be 0/25/50/75/100.

_JUDGE_SYSTEM = """\
You are an evaluator. Score the answer strictly on the rubric provided.
Output ONLY a JSON object: {"score": <0|25|50|75|100>, "reason": "<one sentence>"}
Be strict. Partial credit only when reasoning is partially correct."""

EXECUTOR_JUDGE_TASKS = [
    (
        "Quadratic roots x²-4x+3",
        "A function f(x) = x² - 4x + 3 has two roots. "
        "Determine the exact values and show step-by-step factoring.",
        "Score 100 if both roots (x=1 AND x=3) are correct with factoring shown. "
        "Score 50 if both roots correct but no working shown. "
        "Score 25 if one root correct. Score 0 otherwise.",
    ),
    (
        "Supervised vs unsupervised ML",
        "Explain the difference between supervised and unsupervised learning "
        "with one real-world example for each.",
        "Score 100 if both concepts clearly defined AND both examples are concrete "
        "and non-technical. Score 75 if definitions clear but examples are vague. "
        "Score 50 if only one concept is explained well. Score 25 or 0 otherwise.",
    ),
    (
        "Big-O of bubble sort",
        "What is the time complexity of bubble sort in the worst case, and why?",
        "Score 100 if O(n²) stated AND the nested-loop reason is explained correctly. "
        "Score 50 if O(n²) stated but no explanation. Score 0 if wrong complexity.",
    ),
]


def _llm_judge(model: str, question: str, answer: str, rubric: str) -> tuple[float, str, dict]:
    """
    Ask the Executor to score its own answer against a rubric.
    Returns (score 0-100, reason, raw_call_result).

    DECISION: Self-judging with the same model is intentional. A smarter model
    should be better at both answering AND evaluating. This is a useful single-
    model capability signal. If you want cross-model judging, swap the model arg.
    """
    prompt = (
        f"Question: {question}\n\n"
        f"Answer to evaluate:\n{answer}\n\n"
        f"Rubric: {rubric}"
    )
    r = _lm_call(model, _JUDGE_SYSTEM, prompt,
                 max_tokens=JUDGE_TOKENS, temperature=0.0)
    if r["error"]:
        return 0.0, f"judge error: {r['error']}", r
    try:
        parsed = json.loads(r["content"])
        score  = float(parsed.get("score", 0))
        reason = parsed.get("reason", "")
        return score, reason, r
    except Exception:
        # Fallback: extract number from response
        nums = re.findall(r"\b(100|75|50|25|0)\b", r["content"])
        score = float(nums[0]) if nums else 0.0
        return score, r["content"][:100], r


def run_executor_benchmark() -> dict:
    """
    Test Hermes on code correctness (deterministic) and reasoning (LLM judge).
    """
    model   = cfg.executor_model
    results = []
    total_tps, total_latency, total_score = 0.0, 0.0, 0.0

    print(f"\n── Executor ({model}) ────────────────────────────────────")
    print("  Code tasks (deterministic):")

    # ── Code tasks ────────────────────────────────────────────────────────────
    for title, system, user, check_expr in EXECUTOR_CODE_TASKS:
        r = _lm_call(model, system, user, max_tokens=400, temperature=0.0)
        if r["error"]:
            score, detail = 0.0, r["error"]
        else:
            score, detail = _validate_code_task(r["content"], check_expr)

        total_tps     += r["tps"]
        total_latency += r["latency_ms"]
        total_score   += score

        mark = "✓" if score >= 100 else ("~" if score >= 50 else "✗")
        print(f"  {mark} {title:<35} score={score:>5.0f}  {r['tps']:>5.1f}tok/s"
              f"  | {detail[:60]}")

        results.append({
            "task": title, "type": "code", "score": score,
            "detail": detail,
            **{k: r[k] for k in ("latency_ms", "tps", "tokens_out", "error")},
        })

    # ── Reasoning tasks (LLM judge) ───────────────────────────────────────────
    print("  Reasoning tasks (LLM judge):")
    for title, user, rubric in EXECUTOR_JUDGE_TASKS:
        system = ("You are a knowledgeable assistant. Answer clearly and concisely. "
                  "Show your reasoning step by step when relevant.")
        r = _lm_call(model, system, user, max_tokens=400, temperature=0.1)

        if r["error"]:
            score, reason = 0.0, r["error"]
            judge_r: dict = {}
        else:
            score, reason, judge_r = _llm_judge(model, user, r["content"], rubric)

        total_tps     += r["tps"]
        total_latency += r["latency_ms"]
        total_score   += score

        mark = "✓" if score >= 75 else ("~" if score >= 50 else "✗")
        print(f"  {mark} {title:<35} score={score:>5.0f}  {r['tps']:>5.1f}tok/s"
              f"  | {reason[:60]}")

        results.append({
            "task": title, "type": "reasoning", "score": score,
            "detail": reason,
            "judge_tokens": judge_r.get("tokens_out", 0),
            **{k: r[k] for k in ("latency_ms", "tps", "tokens_out", "error")},
        })

    n           = len(results)
    correctness = round(total_score / n, 1)
    avg_tps     = round(total_tps / n, 1)
    avg_latency = round(total_latency / n, 1)
    comp        = _composite(correctness, avg_tps)

    print(f"  correctness={correctness}  avg={avg_tps}tok/s  composite={comp}")

    return {
        "role":           "executor",
        "model":          model,
        "tasks":          results,
        "correctness":    correctness,
        "avg_tps":        avg_tps,
        "avg_latency_ms": avg_latency,
        "speed_score":    _speed_score(avg_tps),
        "composite":      comp,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PLANNER BENCHMARK
# ══════════════════════════════════════════════════════════════════════════════

# Planner produces structured JSON plans. We validate:
#   1. Valid JSON
#   2. Has "steps" key with a list
#   3. Step count is in a sensible range (not 0, not 50)
#   4. Each step has at minimum a "description" or "action" key
# DECISION: We don't validate step *content* — that would require an LLM judge
# and the Planner is Qwen 9B which is slow. Structure checks are fast and still
# meaningful: a model that can't produce valid JSON plans is unusable.

PLANNER_TASKS = [
    (
        "Research SELIC rate and write a report",
        2, 6,   # min_steps, max_steps
    ),
    (
        "Fix the syntax error in autocode.py and run the tests",
        2, 5,
    ),
    (
        "Analyse workspace/sales.csv and create a bar chart of monthly totals",
        2, 5,
    ),
    (
        "Recall recent memory about ChromaDB, then update the README with findings",
        3, 7,
    ),
]

_PLANNER_SYSTEM = """\
You are a planning model for an AI agent. Given a task, output a structured JSON plan.
Output ONLY a JSON object with this structure:
{
  "goal": "<restate the task>",
  "steps": [
    {"step": 1, "action": "<tool or operation>", "description": "<what to do>"},
    ...
  ]
}
Be concise. Include only necessary steps. No explanation outside the JSON."""


def run_planner_benchmark() -> dict:
    """
    Test Qwen's ability to produce valid, well-structured JSON plans.
    """
    model   = cfg.planner_model
    results = []
    total_tps, total_latency, total_score = 0.0, 0.0, 0.0

    print(f"\n── Planner ({model}) ─────────────────────────────────────")

    for task_text, min_steps, max_steps in PLANNER_TASKS:
        r = _lm_call(model, _PLANNER_SYSTEM, f"Task: {task_text}",
                     max_tokens=512, temperature=0.0)

        score, detail = 0.0, ""

        if r["error"]:
            detail = r["error"]
        else:
            # Strip markdown fences if model wraps output
            raw = re.sub(r"^```json\s*|```$", "", r["content"].strip(), flags=re.MULTILINE).strip()
            try:
                plan   = json.loads(raw)
                steps  = plan.get("steps", [])
                n_steps = len(steps)

                if not isinstance(steps, list) or n_steps == 0:
                    score, detail = 10.0, "empty steps list"
                elif n_steps < min_steps:
                    score, detail = 40.0, f"too few steps ({n_steps}, min={min_steps})"
                elif n_steps > max_steps:
                    score, detail = 60.0, f"too many steps ({n_steps}, max={max_steps})"
                else:
                    # Check each step has at least one meaningful key
                    has_desc = all(
                        any(k in s for k in ("description", "action", "tool"))
                        for s in steps
                    )
                    if has_desc:
                        score, detail = 100.0, f"{n_steps} steps, structure valid"
                    else:
                        score, detail = 70.0, f"{n_steps} steps but missing action/description keys"

            except json.JSONDecodeError as e:
                score, detail = 5.0, f"invalid JSON: {e}"

        total_tps     += r["tps"]
        total_latency += r["latency_ms"]
        total_score   += score

        mark = "✓" if score >= 100 else ("~" if score >= 60 else "✗")
        print(f"  {mark} {task_text[:45]:<45} score={score:>5.0f}  "
              f"{r['tps']:>5.1f}tok/s  | {detail}")

        results.append({
            "task": task_text, "score": score, "detail": detail,
            **{k: r[k] for k in ("latency_ms", "tps", "tokens_out", "error")},
        })

    n           = len(results)
    correctness = round(total_score / n, 1)
    avg_tps     = round(total_tps / n, 1)
    avg_latency = round(total_latency / n, 1)
    comp        = _composite(correctness, avg_tps)

    print(f"  correctness={correctness}  avg={avg_tps}tok/s  composite={comp}")

    return {
        "role":           "planner",
        "model":          model,
        "tasks":          results,
        "correctness":    correctness,
        "avg_tps":        avg_tps,
        "avg_latency_ms": avg_latency,
        "speed_score":    _speed_score(avg_tps),
        "composite":      comp,
    }


# ══════════════════════════════════════════════════════════════════════════════
# COMPARE MODE
# ══════════════════════════════════════════════════════════════════════════════

def _load_run(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare_runs(path_a: str, path_b: str) -> None:
    """
    Print a side-by-side diff of two saved benchmark runs.
    Highlights which role improved, degraded, or stayed the same.
    """
    a = _load_run(path_a)
    b = _load_run(path_b)

    tag_a = a.get("tag", Path(path_a).stem)
    tag_b = b.get("tag", Path(path_b).stem)

    print(f"\n{'='*65}")
    print(f" BENCHMARK COMPARISON")
    print(f" A: {tag_a}  ({a.get('timestamp','')})")
    print(f" B: {tag_b}  ({b.get('timestamp','')})")
    print(f"{'='*65}")
    print(f"{'Role':<12} {'Metric':<18} {'A':>8} {'B':>8} {'Δ':>8}")
    print(f"{'-'*65}")

    roles_a = {r["role"]: r for r in a.get("roles", [])}
    roles_b = {r["role"]: r for r in b.get("roles", [])}

    for role in ("router", "executor", "planner"):
        ra = roles_a.get(role)
        rb = roles_b.get(role)
        if not ra or not rb:
            continue
        for metric in ("composite", "correctness", "avg_tps", "avg_latency_ms"):
            va = ra.get(metric, 0)
            vb = rb.get(metric, 0)
            delta = vb - va
            # For latency, lower is better — invert the arrow
            if metric == "avg_latency_ms":
                arrow = "▼" if delta < -10 else ("▲" if delta > 10 else "─")
            else:
                arrow = "▲" if delta > 1 else ("▼" if delta < -1 else "─")
            print(f"{role:<12} {metric:<18} {va:>8.1f} {vb:>8.1f} {arrow}{abs(delta):>6.1f}")
        print()

    # Overall composite comparison
    oa = a.get("overall_composite", 0)
    ob = b.get("overall_composite", 0)
    delta = ob - oa
    direction = "IMPROVED ▲" if delta > 0.5 else ("DEGRADED ▼" if delta < -0.5 else "NO CHANGE ─")
    print(f"{'─'*65}")
    print(f" Overall composite: {oa:.1f} → {ob:.1f}  ({direction}  Δ{delta:+.1f})")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def _save_run(results: list[dict], tag: str) -> Path:
    """Save benchmark results to workspace/benchmarks/run_role_model_timestamp[_tag].json."""
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    
    # Extract date/time components for custom format with h/m/s letters
    now = datetime.now()
    ts = f"{now.day}-{now.month:02d}-{now.year}_{now.hour:02d}h-{now.minute:02d}m-{now.second:02d}s"
    
    # Determine role prefix from results
    roles = sorted(set(r["role"] for r in results))
    if len(roles) == 3:  # All roles ran
        role_prefix = "all"
    else:  # Single role
        role_prefix = roles[0]
    
    # Build model identifier from cfg (router/executor/planner models)
    seen_models = sorted(set(r["model"] for r in results))
    model_identifier = "_".join(_sanitize_filename(m) for m in seen_models[:1]) if seen_models else ""
    
    tag_suffix = f"_{tag}" if tag else ""
    out_path = BENCH_DIR / f"run_{ts}_{role_prefix}_{model_identifier}_{tag_suffix}.json"

    overall = round(sum(r["composite"] for r in results) / len(results), 1) if results else 0

    payload = {
        "timestamp":         datetime.now().isoformat(),
        "tag":               tag,
        "baseline_tps":      BASELINE_TPS,
        "overall_composite": overall,
        "roles":             results,
        "models": {
            "router":   cfg.router_model,
            "executor": cfg.executor_model,
            "planner":  cfg.planner_model,
        },
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def _print_summary(results: list[dict], tag: str, saved_path: Path) -> None:
    overall = round(sum(r["composite"] for r in results) / len(results), 1) if results else 0
    print(f"\n{'='*65}")
    print(f" BENCHMARK SUMMARY  {f'[{tag}]' if tag else ''}")
    print(f"{'='*65}")
    print(f" {'Role':<12} {'Model':<35} {'Correct':>7} {'tok/s':>6} {'Comp':>6}")
    print(f" {'-'*62}")
    for r in results:
        model_short = r["model"].split("/")[-1][:34]
        print(f" {r['role']:<12} {model_short:<35} "
              f"{r['correctness']:>6.1f}% {r['avg_tps']:>6.1f} {r['composite']:>6.1f}")
    print(f" {'─'*62}")
    print(f" {'OVERALL':<12} {'':35} {'':>7} {'':>6} {overall:>6.1f}")
    print(f"\n Saved → {saved_path}")
    print(f" Compare: python tests/benchmark.py --compare <run_a.json> <run_b.json>")


def main() -> None:
    global BASELINE_TPS               # ← declare BEFORE any use

    parser = argparse.ArgumentParser(
        description="MCP Agent model benchmark — measures speed, correctness, routing accuracy."
    )
    parser.add_argument("--role",    choices=["router", "executor", "planner"],
                        help="Run only one role (default: all)")
    parser.add_argument("--tag",     default="",
                        help="Label for this run, e.g. 'q8_offload32' (appears in JSON + summary)")
    parser.add_argument("--compare", nargs=2, metavar=("RUN_A", "RUN_B"),
                        help="Compare two saved JSON run files instead of running benchmarks")
    parser.add_argument("--baseline-tps", type=float, default=BASELINE_TPS,
                        help=f"tok/s baseline for speed scoring (default: {BASELINE_TPS})")
    args = parser.parse_args()

    if args.compare:
        compare_runs(args.compare[0], args.compare[1])
        return

    # Override baseline if provided
    BASELINE_TPS = args.baseline_tps

    print("=" * 65)
    print(f" MCP AGENT BENCHMARK  {f'[{args.tag}]' if args.tag else ''}")
    print(f" baseline_tps={BASELINE_TPS}  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" router:   {cfg.router_model}")
    print(f" executor: {cfg.executor_model}")
    print(f" planner:  {cfg.planner_model}")
    print("=" * 65)

    role_fns = {
        "router":   run_router_benchmark,
        "executor": run_executor_benchmark,
        "planner":  run_planner_benchmark,
    }

    roles_to_run = [args.role] if args.role else ["router", "executor", "planner"]
    results = [role_fns[r]() for r in roles_to_run]

    saved = _save_run(results, args.tag)
    _print_summary(results, args.tag, saved)


if __name__ == "__main__":
    main()
