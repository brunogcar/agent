"""benchmark.py — Main benchmark runner."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import yaml
from pathlib import Path
from typing import Any

from core.config import cfg
from core.llm import llm
from benchmark.validators import VALIDATORS
from benchmark.scoring import (
    calculate_task_score,
    calculate_role_score,
    categorize_failure,
    consistency_score,
    calculate_difficulty_breakdown,
)
from benchmark import reports

try:
    import tiktoken
    _tk = tiktoken.get_encoding("cl100k_base")
    def count_tokens(t): return len(_tk.encode(t))
except Exception:
    def count_tokens(t): return len(t.split())

# NOTE: vision and consultor are excluded from --all by default.
# They have no task YAMLs yet. Test them explicitly with --role vision or --role consultor.
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
    # "vision": "vision", # add when vision.yaml exists
    # "consultor": "consultor", # add when consultor.yaml exists
}

DEPTH_TASKS = {"easy": 5, "normal": 10, "hard": 15}
DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}


def load_tasks(role):
    """Load tasks for a role, sorted by difficulty ascending (easy first)."""
    group = ROLE_TO_GROUP.get(role, role)
    task_file = Path(__file__).parent / "tasks" / f"{group}.yaml"
    if not task_file.exists():
        return []
    with open(task_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    all_tasks = data.get("tasks", [])
    # Sort by difficulty ascending before slicing
    all_tasks = sorted(
        all_tasks,
        key=lambda t: DIFFICULTY_ORDER.get(t.get("difficulty", "medium"), 1)
    )
    if role == group:
        return all_tasks
    filtered = [t for t in all_tasks if t.get("name", "").startswith(f"{role}_")]
    return sorted(
        filtered,
        key=lambda t: DIFFICULTY_ORDER.get(t.get("difficulty", "medium"), 1)
    )


def snippet(text, max_len=55):
    s = text.replace("\n", " ").strip()
    return s[:max_len] + "..." if len(s) > max_len else s


def safe_filename(text):
    return re.sub(r'[<>:"/\\|?*]', '-', text)


def run_task(role, llm_role, task, model_override="", temperature=0.0):
    """Run a single task and return result dict. No terminal output here."""
    original_model = None
    from core.llm_backend.config import RoleConfig
    if model_override and llm_role in llm._roles:
        old_cfg = llm._roles[llm_role]
        original_model = old_cfg.model
        llm._roles[llm_role] = RoleConfig(
            model=model_override,
            provider=old_cfg.provider,
            timeout=old_cfg.timeout,
            temperature=old_cfg.temperature,
            max_tokens=old_cfg.max_tokens,
        )
    elif model_override and llm_role in cfg.model_registry:
        # Fallback if _roles doesn't have it
        original_model = cfg.model_registry[llm_role].get("model")
        cfg.model_registry[llm_role]["model"] = model_override
    else:
        original_model = None

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
            result = {
                "name": task["name"], "prompt": task["prompt"], "output": "",
                "score": calculate_task_score(0, 0, latency, 0, task.get('timeout', 120), role=role),
                "status": "fail", "error": error_msg, "latency": latency, "tokens": 0,
            }
            result["failure_category"] = categorize_failure(result)
            return result

        if not output.strip():
            empty_msg = f"EMPTY | model={response.model} text={repr(response.text[:50])}"
            result = {
                "name": task["name"], "prompt": task["prompt"], "output": "",
                "score": calculate_task_score(0, 0, latency, 0, task.get('timeout', 120), role=role),
                "status": "fail", "error": empty_msg, "latency": latency, "tokens": 0,
            }
            result["failure_category"] = categorize_failure(result)
            return result

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

        result = {
            "name": task["name"], "prompt": task["prompt"], "output": output,
            "score": score, "status": status, "latency": latency, "tokens": tokens,
        }
        result["failure_category"] = categorize_failure(result)
        return result

    except Exception as e:
        latency = time.time() - start
        result = {
            "name": task["name"], "prompt": task["prompt"], "output": "",
            "score": calculate_task_score(0, 0, latency, 0, task.get('timeout', 120), role=role),
            "status": "fail", "error": str(e), "latency": latency, "tokens": 0,
        }
        result["failure_category"] = categorize_failure(result)
        return result

    finally:
        if original_model is not None and llm_role in llm._roles:
            old_cfg = llm._roles[llm_role]
            llm._roles[llm_role] = RoleConfig(
                model=original_model,
                provider=old_cfg.provider,
                timeout=old_cfg.timeout,
                temperature=old_cfg.temperature,
                max_tokens=old_cfg.max_tokens,
            )


def run_role(role, depth="normal", runs=1, model_override="", temperature=0.0):
    """Run all tasks for a role and return aggregated results."""
    tasks = load_tasks(role)
    if not tasks:
        print(f"  {reports.yellow('?')} No tasks found for role '{role}' (looked for {ROLE_TO_GROUP.get(role, role)}.yaml)")
        return {"role": role, "tasks": [], "summary": {"final": 0.0, "tasks": 0}}

    count = len(tasks) if depth == "hard" else DEPTH_TASKS.get(depth, 10)
    selected = tasks[:count]
    llm_role = ROLE_TO_GROUP.get(role, role)

    # Per-role model override: if EXTRACT_MODEL is set, use "extract" for LLM lookup
    if not model_override and cfg.model_registry.get(role, {}).get("model"):
        llm_role = role
    model = model_override or cfg.model_registry.get(role, {}).get("model") or cfg.model_registry.get(llm_role, {}).get("model", "unknown")

    reports.print_role_header(role, model)

    task_results = []
    failure_counts = {}

    for task in selected:
        print(f"  {task['name'][:73]}{'...' if len(task['name'])>73 else ''}")
        run_scores = []
        run_results = []
        last_result = None

        for _ in range(runs):
            result = run_task(role, llm_role, task, model_override, temperature)
            run_scores.append(result["score"])
            run_results.append(result)
            last_result = result

        # Consistency analysis
        consistency = consistency_score(run_scores)
        if consistency["wobble"]:
            reports.print_wobble_warning(task["name"], consistency["std_dev"])

        # Average score across runs
        avg_score = calculate_task_score(
            correctness=sum(s["correctness"] for s in run_scores) / len(run_scores),
            format_score=sum(s["format"] for s in run_scores) / len(run_scores),
            latency=sum(s["latency"] for s in run_scores) / len(run_scores),
            tokens=round(sum(s["tokens"] for s in run_scores) / len(run_scores)),
            timeout=task.get('timeout', 120),
            role=role,
        )

        status = "pass" if avg_score["final"] >= 80 else "partial" if avg_score["final"] >= 50 else "fail"

        task_result = {
            "name": task["name"],
            "difficulty": task.get("difficulty", "medium"),
            "score": avg_score,
            "status": status,
            "consistency": consistency,
            "run_scores": [dict(s) for s in run_scores],
        }
        task_results.append(task_result)

        # Print first run result (all runs have same output for deterministic models)
        first_run = run_results[0]
        expected = task.get("expected", "")
        reports.print_task_run(task["name"], first_run, expected)

        if last_result and last_result.get("error"):
            reports.print_task_error(last_result["error"])

        # Accumulate failure categories (only for non-passing runs)
        # Count per-task failure (if any run failed, the task failed)
        task_failed = any(rr.get("status") == "fail" for rr in run_results)
        if task_failed:
            # Use the most common failure category across runs, or first failure
            fail_cats = [rr.get("failure_category", "unknown") for rr in run_results if rr.get("status") == "fail"]
            if fail_cats:
                cat = fail_cats[0]  # or max(set(fail_cats), key=fail_cats.count) for most common
                failure_counts[cat] = failure_counts.get(cat, 0) + 1

    summary = calculate_role_score([t["score"] for t in task_results])
    difficulty_breakdown = calculate_difficulty_breakdown(task_results)

    total_runs = len(task_results) * runs
    pass_tasks = sum(1 for t in task_results if t["status"] == "pass")
    partial_tasks = sum(1 for t in task_results if t["status"] == "partial")
    fail_tasks = len(task_results) - pass_tasks - partial_tasks
    accuracy = (pass_tasks * runs + partial_tasks * (runs // 2)) / total_runs * 100 if total_runs else 0

    summary["pass"] = pass_tasks
    summary["partial"] = partial_tasks
    summary["fail"] = fail_tasks
    summary["accuracy"] = accuracy
    summary["model"] = model

    reports.print_role_summary(role, summary, difficulty_breakdown, failure_counts, runs=runs)

    return {
        "role": role,
        "tasks": task_results,
        "summary": summary,
        "difficulty_breakdown": difficulty_breakdown,
        "failure_counts": failure_counts,
    }


def run_benchmark(roles=None, all_roles=False, depth="normal", runs=1, compare_models=None, temperature=0.0, output_dir="", tag="", baseline_path="", regression_threshold=5.0):
    """Run benchmark across roles and models."""
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
    reports.print_benchmark_header(timestamp, depth, runs, tag)

    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {"depth": depth, "runs": runs, "temperature": temperature, "roles": individual_roles},
        "role_results": {},
    }

    models = compare_models or ["default"]
    baseline_data = None
    if baseline_path and os.path.exists(baseline_path):
        with open(baseline_path, "r", encoding="utf-8") as f:
            baseline_data = json.load(f)

    regression_detected = False
    regressions = []

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
                print(f"{'─' * 68}")
                print(f"{group.upper()}")
                print(f"{'─' * 68}")
                print()

            role_result = run_role(role, depth, runs, model_override, temperature)
            model_results[role] = role_result

            # Baseline delta
            if baseline_data:
                baseline_model_results = baseline_data.get("role_results", {})
                # Find matching model/role in baseline
                baseline_score = None
                for bm_key, bm_results in baseline_model_results.items():
                    if role in bm_results:
                        baseline_score = bm_results[role].get("summary", {}).get("final")
                        break
                if baseline_score is not None:
                    current_score = role_result["summary"]["final"]
                    reports.print_baseline_delta(role, current_score, baseline_score)
                    delta = current_score - baseline_score
                    if delta < -regression_threshold:
                        regression_detected = True
                        regressions.append((role, delta))

        results["role_results"][model] = model_results

    all_scores = []
    for model, model_results in results["role_results"].items():
        for role, role_result in model_results.items():
            all_scores.append(role_result["summary"]["final"])
    stack_comp = sum(all_scores) / len(all_scores) if all_scores else 0.0

    # Build filename
    if compare_models and len(compare_models) > 1:
        model_str = "_vs_".join(safe_filename(m) for m in compare_models)
    elif compare_models and len(compare_models) == 1:
        model_str = safe_filename(compare_models[0])
    else:
        # --all or single role: use mixed if multiple roles
        if all_roles or len(individual_roles) > 1:
            model_str = "mixed"
        else:
            # Single role, single model — get actual model name
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
        role_str = "-".join(safe_filename(r) for r in roles)
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

    # Model recommendation after compare
    if compare_models and len(compare_models) > 1:
        recommendations = {}
        for role in individual_roles:
            best_model = None
            best_score = -1
            best_lat = 0
            for model in compare_models:
                model_results = results["role_results"].get(model, {})
                if role in model_results:
                    s = model_results[role]["summary"]
                    if s["final"] > best_score:
                        best_score = s["final"]
                        best_model = model
                        best_lat = s.get("latency", 0)
            if best_model:
                recommendations[role] = {"model": best_model, "score": best_score, "latency": best_lat}
        if recommendations:
            reports.print_recommendation(recommendations)

    if regression_detected:
        reports.print_regression_alert(regressions)

    return results, stack_comp, filepath, regression_detected


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
    parser.add_argument("--baseline", help="Baseline JSON file to compare against")
    parser.add_argument("--regression-threshold", type=float, default=5.0, help="Exit non-zero if any role drops > N points from baseline")
    args = parser.parse_args()

    compare_models = None
    if args.compare:
        compare_models = [m.strip() for m in args.compare.split(",")]

    results, stack_comp, filepath, regression_detected = run_benchmark(
        roles=args.role,
        all_roles=args.all,
        depth=args.depth,
        runs=args.runs,
        compare_models=compare_models,
        temperature=args.temperature,
        output_dir=args.output,
        tag=args.tag,
        baseline_path=args.baseline,
        regression_threshold=args.regression_threshold,
    )

    reports.print_final_table(results["role_results"], stack_comp)
    reports.print_benchmark_complete(filepath)

    if regression_detected:
        sys.exit(1)


if __name__ == "__main__":
    main()
