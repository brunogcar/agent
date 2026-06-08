# Benchmark Tool

Benchmark LLM roles for the agent. Measure which model is best for each role.

## Quick Start

```bash
# Test router role (classify + route) — easy depth, 1 run
python -m benchmark --role router --depth easy

# Test executor role — normal depth, 3 runs for consistency
python -m benchmark --role executor --depth normal --runs 3

# Test all roles — hard depth, 5 runs
python -m benchmark --all --depth hard --runs 5

# Compare two models on the same tasks
python -m benchmark --compare granite-350m,qwen-3b --role code

# Tag the run for tracking
python -m benchmark --role router --tag "baseline-v1"
```

## Commands

| Command | What it does |
|---------|-------------|
| `python -m benchmark --role router` | Test router role (classify + route) |
| `python -m benchmark --role executor` | Test executor role (summarize, extract, research, critique, analyze, code, review) |
| `python -m benchmark --role planner` | Test planner role |
| `python -m benchmark --all` | Test every role |
| `python -m benchmark --depth easy` | 5 tasks per role (fast) |
| `python -m benchmark --depth normal` | 10 tasks per role (default) |
| `python -m benchmark --depth hard` | 15 tasks per role (thorough) |
| `python -m benchmark --runs 3` | 3 runs per task (consistency) |
| `python -m benchmark --compare modelA,modelB` | Compare two models side-by-side |
| `python -m benchmark --tag "label"` | Label the JSON report |
| `python -m benchmark --temperature 0.0` | Set LLM temperature |

## Role Groups

| Group | Roles included |
|-------|---------------|
| `router` | classify, route |
| `executor` | summarize, extract, research, critique, analyze, code, review |
| `planner` | planner |

> **Note:** `vision` and `consultor` groups are reserved but have no task YAMLs yet.

## Scoring

| Metric | Weight | Description |
|--------|--------|-------------|
| Correctness | 70% | Did it do the task right? |
| Format | 20% | Was the output format valid? |
| Speed | 10% | Was it fast? (normalized by role target latency) |
| Efficiency | 0% | Token efficiency (tracked but not scored) |

**Final score:** 0-100. 80+ = pass, 50-80 = partial, <50 = fail.

**Target latencies by role:**
- classify/route: 2s
- summarize/extract: 5s
- critique/analyze/review: 10s
- research/code: 15s
- planner: 20s

## Validators

| Validator | What it checks |
|-----------|---------------|
| `exact_match` | Case-insensitive string equality |
| `contains` | Case-insensitive substring match |
| `fuzzy_match` | `difflib.SequenceMatcher` ratio (threshold default 0.6) |
| `json_valid` | Parses as JSON, optional schema required keys |
| `python_ast` | Parses as Python AST (strips markdown fences) |
| `python_execution` | **Executes code** in restricted namespace against test cases |
| `keyword_coverage` | Fraction of expected keywords found (whole-word match) |
| `regex_match` | Regex pattern match |
| `composite` | **Averages multiple checks:** regex + step count + keywords + ordering |

## Reports

JSON reports saved to `workspace/benchmarks/` with descriptive filenames:

```
workspace/benchmarks/
├── benchmark_hard_planner_qwen-3b_runs3_20250606-201500.json
└── benchmark_normal_router_granite-350m_runs1_20250606-202000.json
```

Console output includes:
- YAML-grouped role headers (`ROUTER`, `EXECUTOR`, `PLANNER`)
- Per-task latency, tokens, throughput, score
- Per-role summary: accuracy, avg time, avg tokens, t/s, score
- Final ASCII table with all roles

## Adding Tasks

Edit YAML files in `benchmark/tasks/`:

```yaml
# benchmark/tasks/planner.yaml
role: planner
tasks:
  - name: plan_migration
    system: "You are a planner. No thinking. No reasoning. Return ONLY a numbered list."
    prompt: "Plan migration from SQLite to PostgreSQL with testing and rollback. Return ONLY a numbered list."
    validator: composite
    validator_args:
      pattern: '^\d+\.'
      min_steps: 5
      required_keywords: ["backup", "test", "rollback", "schema", "data", "migrate"]
      must_appear_before:
        - ["backup", "migrate"]
        - ["test", "deploy"]
    difficulty: medium
    timeout: 180
    max_tokens: 2048
```

### Composite Validator Fields

| Field | Type | Description |
|-------|------|-------------|
| `pattern` | str | Regex for format check (e.g., `^\d+\.` for numbered lists) |
| `min_steps` | int | Minimum numbered steps or bullet points |
| `required_keywords` | list[str] | Keywords that must appear (whole-word match) |
| `must_appear_before` | list[list[str]] | Ordering constraints: `[first, second]` must appear in order |

### Code Tasks with Execution

```yaml
# benchmark/tasks/executor.yaml
  - name: code_fizzbuzz
    system: "Write Python code. Return ONLY the function, no explanation, no markdown fences."
    prompt: "Write a Python function fizzbuzz(n) that returns the correct string..."
    validator: python_execution
    validator_args:
      test_cases:
        - "assert fizzbuzz(15) == 'FizzBuzz'"
        - "assert fizzbuzz(3) == 'Fizz'"
        - "assert fizzbuzz(5) == 'Buzz'"
        - "assert fizzbuzz(7) == '7'"
    difficulty: easy
    timeout: 120
    max_tokens: 1024
```

> **Security:** Code execution runs in a restricted namespace with limited builtins. No file system, no network, no imports.
