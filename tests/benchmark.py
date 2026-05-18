#!/usr/bin/env python3
"""
MCP Agent Stack — Model Benchmark
==================================

Tests Router, Executor and Planner models with curated tasks.
Uses the same LLMClient API as the live agent – no mocks.

Usage:
  python tests/benchmark.py                                    # standard depth, all roles, 1 run each
  python tests/benchmark.py --depth quick --roles router       # quick router-only
  python tests/benchmark.py --depth full --runs 5              # full suite, 5 runs per task
  python tests/benchmark.py --tag "pre-release"                # adds tag to report filename & metadata

Available options:
  --depth {quick,standard,full}    quick=3 tasks, standard=5, full=all tasks
  --roles [router] [executor] [planner]   which roles to test (default: all)
  --runs, --run N                  number of runs per task (default: 1)
  --tag TAG                        custom label appended to report filename & metadata
  --help                           show this help

Output:
  Terminal – colour‑coded V/X, timing, tokens, answer preview inline.
  JSON     – saved to workspace/benchmarks/benchmark_<depth>_<models>_runs<N>_<timestamp>[_tag].json
"""

import json, re, time, statistics, ast, sys, argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

# ── ANSI colours ────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def green(s: str) -> str:  return f"{GREEN}{s}{RESET}"
def red(s: str) -> str:    return f"{RED}{s}{RESET}"
def yellow(s: str) -> str: return f"{YELLOW}{s}{RESET}"
def cyan(s: str) -> str:   return f"{CYAN}{s}{RESET}"
def bold(s: str) -> str:   return f"{BOLD}{s}{RESET}"

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.config import Config as Cfg
from core.llm import LLMClient

# ── tokenizer ───────────────────────────────────────────────────────
try:
    import tiktoken
    TK = tiktoken.get_encoding("cl100k_base")
    def count_tokens(t): return len(TK.encode(t))
except:
    def count_tokens(t): return len(t.split())

DEPTH = {"quick": 3, "standard": 5, "full": None}    # tasks per role

# ── System prompts (same as live agent) ─────────────────────────────
ROUTER_SYSTEM = (
    "You are a task router. Output ONLY a JSON object. No thinking. No markdown.\n"
    "Start with { and end with }.\n\n"
    "Pick EXACTLY ONE value for each field from the lists below:\n"
    "- workflow: research, data, autocode, direct, general\n"
    "- tool: web, python, file, git, memory, agent, notify, report, workflow\n"
    "- complexity: 1 to 10 (integer)\n"
    "- reason: one short sentence\n"
    "- confidence: high, medium, or low\n\n"
    "Return JSON: {\"workflow\":\"...\",\"tool\":\"...\",\"complexity\":...,\"reason\":\"...\",\"confidence\":\"...\"}"
)

EXECUTOR_SYSTEM = (
    "You are the Executor agent. Write clean, well‑tested code. "
    "Provide only the code unless asked to explain. Always include imports."
)

PLANNER_SYSTEM = (
    "You are the Planner agent. Create step‑by‑step plans. "
    "Return numbered steps, each with a clear action."
)

# ── Task suites ─────────────────────────────────────────────────────
ROUTER_TASKS = [
    ("research",      "Find recent papers about CRISPR"),
    ("autocode",      "Write a Python script to download an image"),
    ("data",          "Analyze sales data and create a chart"),
    ("general",       "What is the capital of France?"),
    ("autocode",      "Generate a React component for a todo list"),
    ("autocode",      "Review this Python code for security flaws"),
    ("autocode",      "Classify these support tickets into categories"),
    ("file_operations","Read the config file and show me the database URL"),
    ("git",           "Commit all changes with message 'Fix login bug'"),
    ("memory",        "Remember that I prefer dark mode"),
    ("workflow",      "Plan a full marketing campaign for our new product"),
    ("general",       "Tell me a joke"),
]
EXECUTOR_TASKS = [
    "Write a Python function that checks if a string is a palindrome.",
    "Create a SQL query to find the top 5 customers by revenue.",
    "Review this code: def add(x,y): return x+y",
    "Extract names and phone numbers from: 'John: 555-1234, Mary: 555-5678'",
]
PLANNER_TASKS = [
    "Plan a 3‑day trip to Paris with a budget.",
    "Design a microservices architecture for e‑commerce.",
]

# ── Fuzzy router matching ───────────────────────────────────────────
WORKFLOW_SYNONYMS = {
    "search": "research", "information": "research", "find": "research",
    "data analysis": "data", "analytics": "data",
    "coding": "autocode", "fix": "autocode", "debug": "autocode",
    "static analysis": "autocode", "review": "autocode",
    "ticket categorization": "autocode", "classify": "autocode",
    "generate": "autocode", "script": "autocode",
    "read_config": "direct", "file": "direct",
    "merge": "direct", "commit": "direct", "push": "direct",
    "recall": "direct", "store": "direct",
    "workflow": "direct", "orchestrate": "direct",
}

def map_workflow(raw_wf: str) -> Optional[str]:
    wf = raw_wf.strip().lower()
    if wf in ("research","data","autocode","direct","general"):
        return wf
    if "," in wf or len(wf) > 30:       # model regurgitated list
        return None
    for syn, mapped in WORKFLOW_SYNONYMS.items():
        if syn in wf:
            return mapped
    return None

# ── Parsers / validators ────────────────────────────────────────────
def parse_router_json(text: str) -> Optional[dict]:
    clean = text.strip()
    for fence in ("```json","```"):
        if clean.startswith(fence): clean = clean[len(fence):]
    clean = clean.strip().rstrip("`").strip()
    match = re.search(r"\{(?:[^{}]|\{[^{}]*\})*\}", clean, re.DOTALL)
    if match:
        try: return json.loads(match.group(0))
        except: pass
    return None

def validate_router(parsed) -> Tuple[bool, Optional[str]]:
    if not isinstance(parsed, dict): return False, None
    if not all(k in parsed for k in ("workflow","tool","complexity","reason","confidence")):
        return False, None
    wf = map_workflow(parsed.get("workflow",""))
    if wf is None: return False, None
    tool = parsed.get("tool","")
    valid_tools = {"web","python","file","git","memory","agent","notify","report","workflow","none","…"}
    if tool not in valid_tools and not any(t in tool for t in valid_tools):
        return False, wf
    if not isinstance(parsed["complexity"], (int,float)) or not 1 <= parsed["complexity"] <= 10:
        return False, wf
    if str(parsed.get("confidence","")).lower() not in ("high","medium","low"):
        return False, wf
    return True, wf

def router_correctness(expected_cat: str, parsed) -> float:
    if not isinstance(parsed, dict): return 0.0
    expected_map = {
        "research":"research","autocode":"autocode","code":"autocode","data":"data",
        "general":"general","file_operations":"direct","git":"direct","memory":"direct",
        "workflow":"direct","chat":"research"
    }
    exp_wf = expected_map.get(expected_cat, "research")
    _, wf = validate_router(parsed) if parsed else (False, None)
    return 1.0 if wf == exp_wf else 0.0

def validate_executor(resp: str) -> Tuple[bool, float]:
    if not resp or len(resp.strip()) < 5: return False, 0.0
    cb = re.findall(r'```python\s*(.*?)```', resp, re.DOTALL) or re.findall(r'```\s*(.*?)```', resp, re.DOTALL)
    syn = 0.5
    if cb:
        try: ast.parse(cb[0]); syn = 1.0
        except: syn = 0.0
    return True, syn

def executor_correctness(task: str, resp: str, syn: float) -> float:
    sc = 0.7 if ("def " in resp or "import " in resp or "```" in resp) else 0.0
    return min(1.0, max(sc, syn * 0.9))

def planner_correctness(text: str) -> float:
    if not text or len(text) < 10: return 0.0
    steps = re.findall(r'^\s*(\d+[.)]\s|\-\s|\*\s)', text, re.MULTILINE)
    if len(steps) >= 4: return 0.9
    elif len(steps) >= 2: return 0.7
    elif len(steps) == 1: return 0.4
    return 0.2

def speed_score(lat: float, role: str) -> float:
    targets = {"router": 2.0, "executor": 3.0, "planner": 4.0}
    return min(1.0, targets.get(role, 3.0) / lat) if lat > 0 else 1.0

def snippet(text: str, max_len: int = 55) -> str:
    s = text.replace("\n", " ").strip()
    return s[:max_len] + "…" if len(s) > max_len else s

def safe_filename(text: str) -> str:
    """Replace characters that are invalid in filenames."""
    return re.sub(r'[<>:"/\\|?*]', '-', text)

# ── Main benchmark ─────────────────────────────────────────────────
def run_benchmark(roles, depth, runs=1, tag=""):
    task_limit = DEPTH[depth]          # None for full

    test_map = {"router": ROUTER_TASKS, "executor": EXECUTOR_TASKS, "planner": PLANNER_TASKS}
    prompts = {"router": ROUTER_SYSTEM, "executor": EXECUTOR_SYSTEM, "planner": PLANNER_SYSTEM}
    max_tokens_map = {"router": 200, "executor": 1024, "planner": 2048}
    timeouts = {"router": 30, "executor": 60, "planner": 60}

    cfg = Cfg()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    results = {}
    llm = LLMClient()

    # Build descriptive filename (sanitise model names)
    if len(roles) == 3:
        model_str = "all"
    else:
        model_parts = []
        for role in roles:
            if role in test_map:
                model = safe_filename(getattr(cfg, f"{role}_model", "unknown"))
                model_parts.append(f"{role}-{model}")
        model_str = "_".join(model_parts)
    tag_part = f"_{safe_filename(tag)}" if tag else ""

    print(f"\n{bold('═'*70)}")
    print(f"{bold('  MCP AGENT BENCHMARK')}  {timestamp}")
    print(f"  depth={depth}, runs={runs}{', tag='+tag if tag else ''}")
    print(f"{bold('═'*70)}")

    for role in roles:
        if role not in test_map:
            print(f"  {red('?')} Unknown role '{role}' — skipping")
            continue

        all_tasks = test_map[role]
        tasks = all_tasks[:task_limit] if task_limit is not None else all_tasks
        model = getattr(cfg, f"{role}_model", "unknown")
        key = f"{role}_{model}"
        max_tok = max_tokens_map[role]
        system = prompts[role]
        timeout = timeouts[role]

        print(f"\n  {bold(role.upper())} ({cyan(model)})")
        print("  " + "─"*66)

        role_results = []
        for item in tasks:
            if role == "router":
                expected_cat, prompt = item
            else:
                prompt = item
                expected_cat = None

            print(f"    {prompt[:73]}{'…' if len(prompt)>73 else ''}")

            latencies, tokens, fmt_ok, corrects = [], [], [], []

            for run_idx in range(runs):
                start = time.perf_counter()
                try:
                    resp = llm.complete(
                        role=role, system=system, user=prompt,
                        max_tokens=max_tok, trace_id="", timeout=timeout
                    )
                    if resp.ok:
                        text = resp.text.strip()
                    else:
                        print(f"      {red('X')} run {run_idx+1}: response not ok")
                        continue
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(f"      {red('X')} run {run_idx+1}: {e}")
                    continue
                end = time.perf_counter()
                latency = end - start
                tok_count = count_tokens(text)

                latencies.append(latency)
                tokens.append(tok_count)

                # ── Evaluate ──
                if role == "router":
                    parsed = parse_router_json(text)
                    valid, wf = validate_router(parsed) if parsed else (False, None)
                    correct = router_correctness(expected_cat, parsed) if parsed else 0.0
                    fmt_ok.append(1.0 if valid else 0.0)
                    corrects.append(correct)
                    status = green("V") if valid and correct == 1.0 else red("X")
                    got = wf or "?"
                    # Colour the 'got' part: green if correct, red if wrong
                    got_coloured = green(got) if correct == 1.0 else red(got)
                    print(f"      {status} {latency:.1f}s │ {tok_count:4d}t │ {tok_count/latency:5.1f} t/s │ "
                          f"{expected_cat:<10s} vs {got_coloured} │ {snippet(text)}")

                elif role == "executor":
                    valid, syn = validate_executor(text)
                    correct = executor_correctness(prompt, text, syn)
                    fmt_ok.append(1.0 if valid else 0.0)
                    corrects.append(correct)
                    status = green("V") if correct >= 0.7 else red("X")
                    print(f"      {status} {latency:.1f}s │ {tok_count:4d}t │ {tok_count/latency:5.1f} t/s │ "
                          f"syntax={syn:.1f} │ {snippet(text)}")

                elif role == "planner":
                    correct = planner_correctness(text)
                    steps = len(re.findall(r'^\s*(\d+[.)]\s|\-\s|\*\s)', text, re.MULTILINE))
                    fmt_ok.append(1.0 if correct >= 0.4 else 0.0)
                    corrects.append(correct)
                    status = green("V") if correct >= 0.7 else red("X")
                    print(f"      {status} {latency:.1f}s │ {tok_count:4d}t │ {tok_count/latency:5.1f} t/s │ "
                          f"steps={steps} │ {snippet(text)}")

            if not latencies:
                continue

            avg_lat = statistics.mean(latencies)
            avg_tok = statistics.mean(tokens)
            avg_fmt = statistics.mean(fmt_ok)
            avg_correct = statistics.mean(corrects)
            spd = speed_score(avg_lat, role)

            if role == "router": comp = 0.5*avg_correct + 0.3*avg_fmt + 0.2*spd
            elif role == "executor": comp = 0.4*avg_correct + 0.3*avg_fmt + 0.3*spd
            else: comp = 0.5*avg_correct + 0.3*avg_fmt + 0.2*spd

            role_results.append({
                "task": prompt[:80],
                "expected_category": expected_cat,
                "avg_latency": round(avg_lat, 3),
                "avg_tokens": round(avg_tok, 1),
                "format_validity": round(avg_fmt, 3),
                "correctness": round(avg_correct, 3),
                "speed_score": round(spd, 3),
                "composite": round(comp, 3),
                "runs": runs,
            })

        # ── Role summary (only numbers in yellow) ──
        if role_results:
            correct_vals = [t["correctness"] for t in role_results]
            acc = statistics.mean(correct_vals)
            avg_tps = statistics.mean([t["avg_tokens"]/t["avg_latency"] for t in role_results if t["avg_latency"]>0])
            comp = statistics.mean([t["composite"] for t in role_results])
            print(f"  Accuracy: {yellow(f'{acc*100:.0f}%')}  avg {yellow(f'{avg_tps:.1f} t/s')}  composite={yellow(f'{comp:.2f}')}")
        else:
            acc = 0.0; comp = 0.0

        results[key] = {
            "role": role, "model": model,
            "accuracy": round(acc, 3),
            "role_composite": round(comp, 3),
            "details": role_results,
        }

    if not results:
        print(f"\n{red('No results collected.')}")
        return

    stack_comp = statistics.mean([v["role_composite"] for v in results.values()])
    out_dir = _ROOT / "workspace" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"benchmark_{depth}_{model_str}_runs{runs}_{safe_ts}{tag_part}.json"
    final_out = {
        "metadata": {
            "timestamp": timestamp,
            "depth": depth,
            "runs": runs,
            "tag": tag,
            "models": {role: getattr(cfg, f"{role}_model","?") for role in roles if role in test_map},
            "stack_composite": round(stack_comp, 3)
        },
        "results": results
    }
    with open(json_path, "w") as f:
        json.dump(final_out, f, indent=2)

    # Overall Stack Score – bold text with yellow number
    print(f"\n{bold('═'*70)}")
    print(f"  {bold('Overall Stack Score:')} {bold(yellow(f'{stack_comp:.3f}'))}")
    print(f"  {bold('Report →')} {json_path}")
    print(f"{bold('═'*70)}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MCP Agent Stack — Model Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    parser.add_argument("--depth", choices=["quick","standard","full"], default="standard")
    parser.add_argument("--roles", nargs="+", default=["router","executor","planner"])
    parser.add_argument("--runs", "--run", type=int, dest="runs", default=1,
                        help="number of runs per task (default: 1)")
    parser.add_argument("--tag", type=str, default="", help="label for report filename & metadata")
    args = parser.parse_args()
    try:
        run_benchmark(args.roles, args.depth, args.runs, args.tag)
    except KeyboardInterrupt:
        print(f"\n{red('✗')} Interrupted by user.")