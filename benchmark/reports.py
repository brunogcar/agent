"""reports.py — Terminal and JSON report generation."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

# Simple ANSI colors (no external dependency)
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def color(text: str, color_code: str) -> str:
    return f"{color_code}{text}{RESET}"

def print_header(title: str):
    print(f"\n{color(title, BOLD + CYAN)}")
    print("=" * 60)

def print_task_result(name: str, score: float, latency: float, tokens: int, status: str):
    if status == "pass":
        icon = color("✓", GREEN)
    elif status == "partial":
        icon = color("⚠", YELLOW)
    else:
        icon = color("✗", RED)

    score_col = color(f"{score:.0f}", GREEN if score >= 80 else YELLOW if score >= 50 else RED)
    print(f"  {icon} {name:30s} {score_col:>6s}  {latency:5.1f}s  {tokens:4d} tok")

def print_role_summary(role: str, scores: dict):
    final = scores["final"]
    final_col = color(f"{final:.1f}", GREEN if final >= 80 else YELLOW if final >= 50 else RED)
    print(f"\n  {color(role.upper(), BOLD)}: {final_col} avg | {scores['latency']:.1f}s | {scores['tokens']:.0f} tok | {scores['tasks']} tasks")

def print_comparison(model_a: str, scores_a: dict, model_b: str, scores_b: dict, role: str):
    print(f"\n{color('COMPARISON', BOLD + CYAN)}: {role}")
    print(f"  {model_a:20s} {scores_a['final']:>6.1f}")
    print(f"  {model_b:20s} {scores_b['final']:>6.1f}")
    delta = scores_b["final"] - scores_a["final"]
    winner = model_b if scores_b["final"] > scores_a["final"] else model_a
    print(f"  Winner: {color(winner, GREEN)} (Δ {delta:+.1f})")

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
