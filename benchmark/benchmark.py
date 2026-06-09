"""benchmark.py — Main benchmark runner."""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import yaml
from pathlib import Path
from typing import Any

from core.config import cfg
from core.llm import llm
from benchmark.validators import VALIDATORS
from benchmark.scoring import calculate_task_score, calculate_role_score

try:
    import tiktoken
    _tk = tiktoken.get_encoding("cl100k_base")
    def count_tokens(t): return len(_tk.encode(t))
except Exception:
    def count_tokens(t): return len(t.split())

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
def green(s): return f"{GREEN}{s}{RESET}"
def red(s): return f"{RED}{s}{RESET}"
def yellow(s): return f"{YELLOW}{s}{RESET}"
def cyan(s): return f"{CYAN}{s}{RESET}"
def bold(s): return f"{BOLD}{s}{RESET}"

# NOTE: vision and consultor are excluded from --all by default.
#       They have no task YAMLs yet. Test them explicitly with --role vision or --role consultor.
ROLE_GROUPS = {
    "router": ["classify", "route"],
    "executor": ["summarize", "extract", "research", "critique", "analyze", "code", "review"],
    "planner": ["planner"],
}

ROLE_TO_GROUP = {
    "classify": "router", "route": "router",
    "summarize": "executor", "extract": "executor", "research": "executor",
    "critique": "executor", "analyze": "executor", "code": "executor", "review": "executor",
    "planner": "planner",
    # "vision": "vision",       # add when vision.yaml exists
    # "consultor": "consultor", # add when consultor.yaml exists
}

DEPTH_TASKS = {"easy": 5, "normal": 10, "hard": 15}  # router & executor | planner: 3/6/9

def load_tasks(role):
    group = ROLE_TO_GROUP.get(role, role)
    task_file = Path(__file__).parent / "tasks" / f"{group}.yaml"
    if not task_file.exists(): return []
    with open(task_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    all_tasks = data.get("tasks", [])
    if role == group: return all_tasks
    return [t for t in all_tasks if t.get("name", "").startswith(f"{role}_")]

def snippet(text, max_len=55):
    s = text.replace("\n", " ").strip()
    return s[:max_len] + "..." if len(s) > max_len else s

def safe_filename(text):
    return re.sub(r'[<>:"/\\|?*]', '-', text)

def run_task(role, llm_role, task, model_override="", temperature=0.0):
    original_model = None
    if model_override and llm_role in cfg.model_registry:
        original_model = cfg.model_registry[llm_role].get("model")
        cfg.model_registry[llm_role]["model"] = model_override
    start = time.time()
    try:
        response = llm.complete(
            role=llm_role,
            system=task.get("system", ""),
            user=task["prompt"],
            temperature=temperature,
            max_tokens=task.get('max_tokens', 1024),
            timeout=task.get('timeout', 120),
            trace_id="",
        )
        output = response.text if response.ok else ""
        latency = time.time() - start
        tokens = (response.usage.get("total_tokens", 0) if hasattr(response, "usage") and response.usage else 0) or count_tokens(output)
        if not response.ok:
            error_msg = response.error or "Unknown LLM error"
            print(f"      {red('X')} {latency:.1f}s | {error_msg}")
            return {"name": task["name"], "prompt": task["prompt"], "output": "", "score": calculate_task_score(0, 0, latency, 0, task.get('timeout', 120), role=role), "status": "fail", "error": error_msg, "latency": latency, "tokens": 0}
        if not output.strip():
            empty_msg = f"EMPTY | model={response.model} text={repr(response.text[:50])}"
            print(f"      {yellow('?')} {latency:.1f}s | {empty_msg}")
            return {"name": task["name"], "prompt": task["prompt"], "output": "", "score": calculate_task_score(0, 0, latency, 0, task.get('timeout', 120), role=role), "status": "fail", "error": empty_msg, "latency": latency, "tokens": 0}
        validator_name = task.get("validator", "exact_match")
        validator_fn = VALIDATORS.get(validator_name, VALIDATORS["exact_match"])
        # Shallow copy: task dict is shared YAML state across all runs.
        # Mutating it in-place corrupts subsequent runs (--runs N).
        validator_args = dict(task.get("validator_args", {}))
        if "expected" in task:
            validator_args["expected"] = task["expected"]
        format_score = validator_fn(output, **validator_args)
        # correctness == format_score for most validators.
        # python_execution validator returns partial credit based on test cases.
        correctness = format_score
        score = calculate_task_score(
            correctness=correctness,
            format_score=format_score,
            latency=latency,
            tokens=tokens,
            timeout=task.get('timeout', 120),
            role=role,
        )
        status = "pass" if score["final"] >= 80 else "partial" if score["final"] >= 50 else "fail"
        status_icon = green("✓") if status == "pass" else yellow("⚠") if status == "partial" else red("✗")
        score_col = green(f"{score['final']:.0f}") if status == "pass" else yellow(f"{score['final']:.0f}") if status == "partial" else red(f"{score['final']:.0f}")
        tps = tokens / latency if latency > 0 else 0
        expected = task.get("expected", "")
        actual = output.strip()
        if expected:
            act_col = green(actual) if status == "pass" else yellow(actual) if status == "partial" else red(actual)
            print(f"      {status_icon} {latency:.1f}s | {tokens:4d}t | {tps:5.1f} t/s | {score_col} | {expected:10s} vs {act_col}")
        else:
            out_short = snippet(actual, 50)
            print(f"      {status_icon} {latency:.1f}s | {tokens:4d}t | {tps:5.1f} t/s | {score_col} | {out_short}")
        return {"name": task["name"], "prompt": task["prompt"], "output": output, "score": score, "status": status, "latency": latency, "tokens": tokens}
    except Exception as e:
        latency = time.time() - start
        print(f"      {red('✗')} {latency:.1f}s | EXCEPTION: {e}")
        return {"name": task["name"], "prompt": task["prompt"], "output": "", "score": calculate_task_score(0, 0, latency, 0, task.get('timeout', 120), role=role), "status": "fail", "error": str(e), "latency": latency, "tokens": 0}
    finally:
        if original_model is not None:
            cfg.model_registry[llm_role]["model"] = original_model

def run_role(role, depth="standard", runs=1, model_override="", temperature=0.0):
    tasks = load_tasks(role)
    if not tasks:
        print(f"  {yellow('?')} No tasks found for role '{role}' (looked for {ROLE_TO_GROUP.get(role, role)}.yaml)")
        return {"role": role, "tasks": [], "summary": {"final": 0.0, "tasks": 0}}
    count = DEPTH_TASKS.get(depth, 8)
    selected = tasks[:count]
    llm_role = ROLE_TO_GROUP.get(role, role)
    model = model_override or cfg.model_registry.get(role, {}).get("model") or cfg.model_registry.get(llm_role, {}).get("model", "unknown")
    print(f"\n  {bold(role.upper())} ({cyan(model)})")
    print("  " + "─"*66)
    task_results = []
    for task in selected:
        print(f"    {task['name'][:73]}{'...' if len(task['name'])>73 else ''}")
        run_scores = []
        last_result = None
        for _ in range(runs):
            result = run_task(role, llm_role, task, model_override, temperature)
            run_scores.append(result["score"])
            last_result = result
        avg_score = calculate_task_score(
            correctness=sum(s["correctness"] for s in run_scores) / len(run_scores),
            format_score=sum(s["format"] for s in run_scores) / len(run_scores),
            latency=sum(s["latency"] for s in run_scores) / len(run_scores),
            tokens=round(sum(s["tokens"] for s in run_scores) / len(run_scores)),
            timeout=task.get('timeout', 120),
            role=role,
        )
        task_results.append({"name": task["name"], "difficulty": task.get("difficulty", "medium"), "score": avg_score, "status": "pass" if avg_score["final"] >= 80 else "partial" if avg_score["final"] >= 50 else "fail"})
        if last_result and last_result.get("error"):
            err = str(last_result['error'])[:60]
            print(f"      ! {err}")
    summary = calculate_role_score([t["score"] for t in task_results])
    final = summary["final"]
    final_col = green(f"{final:.1f}") if final >= 80 else yellow(f"{final:.1f}") if final >= 50 else red(f"{final:.1f}")
    avg_lat = summary.get("latency", 0)
    avg_tok = summary.get("tokens", 0)
    avg_tps = avg_tok / avg_lat if avg_lat > 0 else 0
    total_runs = len(task_results) * runs
    pass_tasks = sum(1 for t in task_results if t["status"] == "pass")
    partial_tasks = sum(1 for t in task_results if t["status"] == "partial")
    fail_tasks = len(task_results) - pass_tasks - partial_tasks
    accuracy = (pass_tasks * runs + partial_tasks * (runs // 2)) / total_runs * 100 if total_runs else 0
    acc_col = green(f"{accuracy:.0f}%") if accuracy >= 80 else yellow(f"{accuracy:.0f}%") if accuracy >= 50 else red(f"{accuracy:.0f}%")
    comp_col = green(f"{final:.1f}") if final >= 80 else yellow(f"{final:.1f}") if final >= 50 else red(f"{final:.1f}")
    print()
    print(f"  Accuracy: {acc_col} | Avg: {avg_lat:.1f}s · {avg_tok:.0f} tok · {yellow(f'{avg_tps:.1f} t/s')} | Score: {comp_col} | {summary['tasks']} tasks")
    summary["pass"] = pass_tasks
    summary["partial"] = partial_tasks
    summary["fail"] = fail_tasks
    summary["accuracy"] = accuracy
    summary["model"] = model
    return {"role": role, "tasks": task_results, "summary": summary}

def run_benchmark(roles=None, all_roles=False, depth="standard", runs=1, compare_models=None, temperature=0.0, output_dir="", tag=""):
    roles_to_test = []
    if all_roles:
        roles_to_test = list(ROLE_GROUPS.keys())
    elif roles:
        for r in roles:
            for part in [x.strip() for x in r.split(",")]:
                if part in ROLE_GROUPS:
                    roles_to_test.extend(ROLE_GROUPS[part])
                else:
                    roles_to_test.append(part)
    else:
        roles_to_test = ["router", "executor", "planner"]
    individual_roles = []
    for r in roles_to_test:
        if r in ROLE_GROUPS:
            individual_roles.extend(ROLE_GROUPS[r])
        else:
            individual_roles.append(r)
    individual_roles = list(dict.fromkeys(individual_roles))
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
    print(f"\n{bold('=')*70}")
    print(f"{bold('  MCP AGENT BENCHMARK')}  {timestamp}")
    print(f"  depth={depth}, runs={runs}{', tag='+tag if tag else ''}")
    print(f"{bold('=')*70}")
    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {"depth": depth, "runs": runs, "temperature": temperature, "roles": individual_roles},
        "role_results": {},
    }
    models = compare_models or ["default"]
    for model in models:
        model_override = model if model != "default" else ""
        model_results = {}
        current_group = None
        for role in individual_roles:
            group = ROLE_TO_GROUP.get(role, role)
            if group != current_group:
                if current_group is not None:
                    print()
                current_group = group
                print(f"{'─'*68}")
                print(f"{group.upper()}")
                print(f"{'─'*68}")
                print()
            role_result = run_role(role, depth, runs, model_override, temperature)
            model_results[role] = role_result
        results["role_results"][model] = model_results
    all_scores = []
    for model, model_results in results["role_results"].items():
        for role, role_result in model_results.items():
            all_scores.append(role_result["summary"]["final"])
    stack_comp = sum(all_scores) / len(all_scores) if all_scores else 0.0
    if compare_models and len(compare_models) > 1:
        role_str = "compare"
        model_str = "vs".join([safe_filename(m) for m in compare_models])
    else:
        actual_model = "unknown"
        for model_key, model_results in results["role_results"].items():
            if model_results:
                first_role = list(model_results.keys())[0]
                actual_model = model_results[first_role].get("summary", {}).get("model", model_key)
                break
        model_str = safe_filename(actual_model)
        if all_roles:
            role_str = "all"
        elif roles:
            role_str = "-".join([safe_filename(r) for r in roles])
        else:
            role_str = "default"
    tag_part = f"_{safe_filename(tag)}" if tag else ""
    safe_ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    json_name = f"benchmark_{depth}_{role_str}_{model_str}_runs{runs}_{safe_ts}{tag_part}.json"
    out_dir = Path(output_dir) if output_dir else cfg.workspace_root / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    filepath = out_dir / json_name
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    return results, stack_comp, filepath

def main():
    parser = argparse.ArgumentParser(description="Benchmark agent LLM roles")
    parser.add_argument("--role", nargs="+", help="Test specific role(s). Groups: router, executor, planner. Or individual: classify, code, etc.")
    parser.add_argument("--all", action="store_true", help="Test all roles")
    parser.add_argument("--depth", choices=["easy", "normal", "hard"], default="normal")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--compare", help="Comma-separated models to compare")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--output", help="Output directory")
    parser.add_argument("--tag", help="Label for this run")
    args = parser.parse_args()
    compare_models = None
    if args.compare:
        compare_models = [m.strip() for m in args.compare.split(",")]
    results, stack_comp, filepath = run_benchmark(
        roles=args.role,
        all_roles=args.all,
        depth=args.depth,
        runs=args.runs,
        compare_models=compare_models,
        temperature=args.temperature,
        output_dir=args.output,
        tag=args.tag,
    )
    print(f"\n{bold('=')*70}")
    print(f"  {bold('BENCHMARK COMPLETE')}")
    print(f"{bold('=')*70}")
    for model_key, model_results in results["role_results"].items():
        display_model = model_key
        if model_key == "default" and model_results:
            first_role = list(model_results.keys())[0]
            display_model = model_results[first_role].get("summary", {}).get("model", model_key)
            if display_model == model_key:
                from core.config import cfg
                llm_role = ROLE_TO_GROUP.get(first_role, first_role)
                display_model = cfg.model_registry.get(llm_role, {}).get("model", model_key)
        print(f"\n  Model: {cyan(display_model)}")
        print(f"  {'─'*68}")
        print(f"  {'Role':<20} {'Accuracy':>8} {'Time':>7} {'Tokens':>6} {'T/S':>12}  {'Score':>7}")
        print(f"  {'─'*68}")
        all_scores = []
        all_acc = []
        all_lat = 0.0
        all_tok = 0.0
        for role, role_result in model_results.items():
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
            role_display = ROLE_TO_GROUP.get(role, role).upper() + " - " + role
            print(f"  {role_display:<20} {acc:>7.0f}% {lat:>6.1f}s {tok:>6.0f} {tps:>8.1f} t/s  {final_col:>7}")
        if all_scores:
            print(f"  {'─'*68}")
            avg_final = sum(all_scores) / len(all_scores)
            avg_acc = sum(all_acc) / len(all_acc)
            avg_tps = all_tok / all_lat if all_lat > 0 else 0
            overall_col = green(f"{avg_final:.1f}") if avg_final >= 80 else yellow(f"{avg_final:.1f}") if avg_final >= 50 else red(f"{avg_final:.1f}")
            print(f"  {'Overall':<20} {avg_acc:>7.0f}% {all_lat:>6.1f}s {all_tok:>6.0f} {avg_tps:>8.1f} t/s  {overall_col:>7}")
            print(f"  {'─'*68}")
    stack_col = green(f"{stack_comp:.1f}") if stack_comp >= 80 else yellow(f"{stack_comp:.1f}") if stack_comp >= 50 else red(f"{stack_comp:.1f}")
    print(f"  Stack Score: {stack_col} / 100")

    print(f"\n{bold('=')*70}")
    print(f"  {bold('Report ->')} {filepath}")
    print(f"{bold('=')*70}\n")

if __name__ == "__main__":
    main()
