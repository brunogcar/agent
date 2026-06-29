"""reports.py — Terminal and JSON report generation."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# ── ANSI color helpers ──────────────────────────────────────────────────────
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def green(s): return f"{GREEN}{s}{RESET}"
def red(s): return f"{RED}{s}{RESET}"
def yellow(s): return f"{YELLOW}{s}{RESET}"
def cyan(s): return f"{CYAN}{s}{RESET}"
def bold(s): return f"{BOLD}{s}{RESET}"

def color(text: str, color_code: str) -> str:
    return f"{color_code}{text}{RESET}"

# ── Role mapping for display ────────────────────────────────────────────────
ROLE_TO_GROUP = {
    "classify": "router", "route": "router",
    "summarize": "executor", "extract": "executor", "research": "executor",
    "critique": "executor", "analyze": "executor", "code": "executor", "review": "executor",
    "refactor": "executor", "test": "executor", "document": "executor",
    "planner": "planner",
}

# ── Internal helpers ────────────────────────────────────────────────────────
def _snippet(text: str, max_len: int = 55) -> str:
    s = text.replace("\n", " ").strip()
    return s[:max_len] + "..." if len(s) > max_len else s

def _pad_score(score_str: str, width: int = 7) -> str:
    """Manual padding for colored strings because ANSI codes break f-string width."""
    visible = len(re.sub(r'\033\[\d+m', '', score_str))
    return " " * (width - visible) + score_str

# ── Live task output (called from benchmark.py after each task run) ─────────
def print_task_run(name: str, result: dict, expected: str = ""):
    """Print a single task run result immediately after completion."""
    score = result.get("score", {})
    status = result.get("status", "fail")
    latency = result.get("latency", 0)
    tokens = result.get("tokens", 0)
    output = result.get("output", "").strip()
    final = score.get("final", 0)

    status_icon = green("✓") if status == "pass" else yellow("⚠") if status == "partial" else red("✗")
    score_col = green(f"{final:.0f}") if status == "pass" else yellow(f"{final:.0f}") if status == "partial" else red(f"{final:.0f}")
    tps = tokens / latency if latency > 0 else 0

    if expected:
        act_col = green(output) if status == "pass" else yellow(output) if status == "partial" else red(output)
        exp_str = expected if isinstance(expected, str) else str(expected)
        print(f" {status_icon} {latency:.1f}s | {tokens:4d}t | {tps:5.1f} t/s | {score_col} | {exp_str:10s} vs {act_col}")
    else:
        out_short = _snippet(output, 50)
        print(f" {status_icon} {latency:.1f}s | {tokens:4d}t | {tps:5.1f} t/s | {score_col} | {out_short}")

def print_task_error(error_msg: str):
    """Print a task error line (e.g. timeout, exception)."""
    err = str(error_msg)[:60]
    print(f" ! {err}")

# ── Role summaries ──────────────────────────────────────────────────────────
def print_role_header(role: str, model: str):
    """Print role section header."""
    print(f"\n {bold(role.upper())} ({cyan(model)})")
    print(" " + "─" * 66)

def print_role_summary(role: str, summary: dict, difficulty_breakdown: dict = None, failure_counts: dict = None, runs: int = 1):
    """Print per-role summary line with optional difficulty and failure info."""
    final = summary["final"]
    final_col = green(f"{final:.1f}") if final >= 80 else yellow(f"{final:.1f}") if final >= 50 else red(f"{final:.1f}")
    lat = summary.get("latency", 0)
    tok = summary.get("tokens", 0)
    tps = tok / lat if lat > 0 else 0
    acc = summary.get("accuracy", 0)
    pass_ = summary.get("pass", 0)
    partial = summary.get("partial", 0)
    fail = summary.get("fail", 0)

    runs_part = f" | {runs} run{'s' if runs > 1 else ''}" if runs > 1 else ""

    print(f" Accuracy: {green(f'{acc:.0f}%') if acc >= 80 else yellow(f'{acc:.0f}%') if acc >= 50 else red(f'{acc:.0f}%')} | "
          f"Avg: {lat:.1f}s · {tok:.0f} tok · {yellow(f'{tps:.1f} t/s')} | "
          f"Score: {final_col} | {summary['tasks']} tasks{runs_part}")

    if difficulty_breakdown:
        parts = []
        for diff in ("easy", "medium", "hard"):
            if diff in difficulty_breakdown:
                d = difficulty_breakdown[diff]
                parts.append(f"{diff}: {d['pass']}/{d['total']}")
        if parts:
            print(f" {cyan(' | '.join(parts))}")

    if failure_counts:
        active = {k: v for k, v in failure_counts.items() if v > 0}
        if active:
            parts = [f"{v} {k}" for k, v in active.items()]
            print(f" {red('Failures: ' + ' | '.join(parts))}")

def print_wobble_warning(task_name: str, std_dev: float):
    """Print a wobble warning for inconsistent task results."""
    print(f" {yellow('⚠')} {task_name[:50]} wobbly (σ={std_dev:.1f})")

# ── Comparison ────────────────────────────────────────────────────────────────
def print_comparison(model_a: str, scores_a: dict, model_b: str, scores_b: dict, role: str):
    """Print side-by-side model comparison for a role."""
    print(f"\n{color('COMPARISON', BOLD + CYAN)}: {role}")
    print(f" {'Model':<20} {'Score':>7} {'Time':>7} {'Tokens':>7} {'T/S':>9}")
    print(f" {'─' * 50}")
    for m, s in [(model_a, scores_a), (model_b, scores_b)]:
        lat = s.get("latency", 0)
        tok = s.get("tokens", 0)
        tps = tok / lat if lat > 0 else 0
        print(f" {m:<20} {s['final']:>7.1f} {lat:>6.1f}s {tok:>6.0f} {tps:>8.1f} t/s")
    delta = scores_b["final"] - scores_a["final"]
    winner = model_b if scores_b["final"] > scores_a["final"] else model_a
    print(f" Winner: {color(winner, GREEN)} (Δ {delta:+.1f})")

# ── Baseline delta ──────────────────────────────────────────────────────────
def print_baseline_delta(role: str, current: float, baseline: float):
    """Print score delta vs baseline for a role."""
    delta = current - baseline
    if delta >= 0:
        print(f" {green('▲ +' + f'{delta:.1f}')} vs baseline")
    else:
        print(f" {red('▼ ' + f'{delta:.1f}')} vs baseline")

# ── Recommendation ────────────────────────────────────────────────────────────
def print_recommendation(recommendations: dict):
    """Print per-role model recommendation table."""
    print(f"\n{color('RECOMMENDED MODELS', BOLD + CYAN)}")
    print(f" {'Role':<20} {'Model':<25} {'Score':>7} {'Latency':>9}")
    print(f" {'─' * 65}")
    for role, rec in recommendations.items():
        print(f" {role:<20} {rec['model']:<25} {rec['score']:>7.1f} {rec['latency']:>7.1f}s")

# ── Regression alert ────────────────────────────────────────────────────────
def print_regression_alert(regressions: list[tuple]):
    """Print regression warning banner. regressions: list of (role, delta)."""
    print(f"\n{RED}{BOLD}{'=' * 70}{RESET}")
    print(f" {RED}{BOLD}⚠️ REGRESSION DETECTED{RESET}")
    for role, delta in regressions:
        print(f" {role}: {red(f'{delta:.1f}')} points below baseline")
    print(f"{RED}{BOLD}{'=' * 70}{RESET}")

# ── Final benchmark table ───────────────────────────────────────────────────
def print_benchmark_header(timestamp: str, depth: str, runs: int, tag: str = ""):
    """Print benchmark run header."""
    tag_part = f", tag={tag}" if tag else ""
    print(f"\n{bold('=') * 70}")
    print(f"{bold(' MCP AGENT BENCHMARK')} {timestamp}")
    print(f" depth={depth}, runs={runs}{tag_part}")
    print(f"{bold('=') * 70}")

def print_benchmark_complete(filepath: str):
    """Print benchmark completion footer."""
    print(f"\n{bold('=') * 70}")
    print(f" {bold('BENCHMARK COMPLETE')}")
    print(f"{bold('=') * 70}\n")
    print(f" {bold('Report ->')} {filepath}")
    print(f"{bold('=') * 70}\n")

def print_final_table(model_results: dict, stack_comp: float):
    """Print the final per-role summary table."""
    for model_key, results in model_results.items():
        if model_key == "default" and results and len(results) > 1:
            display_model = "mixed"
        elif model_key == "default" and results:
            first_role = list(results.keys())[0]
            display_model = results[first_role].get("summary", {}).get("model", model_key)
        else:
            display_model = model_key

        print(f"\n Model: {cyan(display_model)}")
        print(f" {'─' * 72}")
        print(f" {'Role':<20} {'Accuracy':>8} {'Time':>7} {'Tokens':>6} {'T/S':>12} {'Score':>7}")
        print(f" {'─' * 72}")

        all_scores = []
        all_acc = []
        all_lat = 0.0
        all_tok = 0.0

        for role, role_result in results.items():
            s = role_result["summary"]
            final = s["final"]
            lat = s.get("latency", 0)
            tok = s.get("tokens", 0)
            tps = tok / lat if lat > 0 else 0
            acc = s.get("accuracy", 0)
            all_scores.append(final)
            all_acc.append(acc)
            all_lat += lat
            all_tok += tok
            final_col = green(f"{final:.1f}") if final >= 80 else yellow(f"{final:.1f}") if final >= 50 else red(f"{final:.1f}")
            group = ROLE_TO_GROUP.get(role, role)
            role_display = f"{group.upper()} - {role}"
            print(f" {role_display:<20} {acc:>7.0f}% {lat:>6.1f}s {tok:>6.0f} {tps:>8.1f} t/s {_pad_score(final_col)}")

        # Per-model stack score
        model_scores = [role_result["summary"]["final"] for role, role_result in results.items()]
        model_avg = sum(model_scores) / len(model_scores) if model_scores else 0.0
        model_stack_col = green(f"{model_avg:.1f}") if model_avg >= 80 else yellow(f"{model_avg:.1f}") if model_avg >= 50 else red(f"{model_avg:.1f}")
        print(f" {'─' * 72}")
        print(f" Stack Score: {model_stack_col} / 100")

        # Global summary only when single model (not compare)
        if len(model_results) == 1 and all_scores:
            print(f"\n {'─' * 72}")
            avg_final = sum(all_scores) / len(all_scores)
            avg_acc = sum(all_acc) / len(all_acc)
            avg_tps = all_tok / all_lat if all_lat > 0 else 0
            overall_col = green(f"{avg_final:.1f}") if avg_final >= 80 else yellow(f"{avg_final:.1f}") if avg_final >= 50 else red(f"{avg_final:.1f}")
            print(f" {'Overall':<20} {avg_acc:>7.0f}% {all_lat:>6.1f}s {all_tok:>6.0f} {avg_tps:>8.1f} t/s {_pad_score(overall_col)}")
            print(f" {'─' * 72}")

# ── JSON export (kept for compatibility, but benchmark.py does its own dump) ─
def save_json_report(results: dict, output_dir: str, tag: str = "") -> str:
    """Save results to JSON file."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_part = f"_{tag}" if tag else ""
    filename = f"benchmark{tag_part}_{ts}.json"
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    filepath = out_path / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    return str(filepath)

# ── Legacy compatibility functions ──────────────────────────────────────────
def print_header(title: str):
    print(f"\n{color(title, BOLD + CYAN)}")
    print("=" * 60)

def print_task_result(name: str, score: float, latency: float, tokens: int, status: str):
    """Legacy function — kept for compatibility."""
    if status == "pass":
        icon = color("✓", GREEN)
    elif status == "partial":
        icon = color("⚠", YELLOW)
    else:
        icon = color("✗", RED)
    score_col = color(f"{score:.0f}", GREEN if score >= 80 else YELLOW if score >= 50 else RED)
    print(f" {icon} {name:30s} {score_col:>6s} {latency:5.1f}s {tokens:4d} tok")
