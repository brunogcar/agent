# Benchmark Tool

Benchmark LLM roles for the agent. Measure which model is best for each role.

## easy Start

```bash
# Test router role (classify + route) — 3 tasks, 1 run
python -m benchmark --role router --depth easy

# Test executor group — 8 tasks, 3 runs for consistency
python -m benchmark --group executor --depth normal --runs 3

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
| `python -m benchmark --role code` | Test code generation |
| `python -m benchmark --group executor` | Test all executor sub-roles |
| `python -m benchmark --group router` | Test all router sub-roles |
| `python -m benchmark --all` | Test every role |
| `python -m benchmark --depth easy` | 3 tasks per role (fast) |
| `python -m benchmark --depth normal` | 8 tasks per role (default) |
| `python -m benchmark --depth hard` | 10 tasks per role (thorough) |
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
| `vision` | vision |
| `consultor` | consultor |

## Scoring

| Metric | Weight | Description |
|--------|--------|-------------|
| Correctness | 60% | Did it do the task right? |
| Format | 20% | Was the output format valid? |
| Speed | 10% | Was it fast? (normalized by timeout) |
| Efficiency | 10% | Was it token-efficient? |

**Final score:** 0-100. 80+ = good, 50-80 = acceptable, <50 = needs improvement.

## Reports

JSON reports saved to `workspace/benchmarks/` with timestamp.

```
workspace/benchmarks/
├── benchmark_baseline-v1_20250606_201500.json
└── benchmark_20250606_202000.json
```

## Adding Tasks

Edit YAML files in `benchmark/tasks/`:

```yaml
# benchmark/tasks/router.yaml
role: router
tasks:
  - name: my_new_task
    prompt: "Classify: ..."
    expected: "bug"
    validator: exact_match
    difficulty: easy
    timeout: 15
```

Validators: `exact_match`, `json_valid`, `python_ast`, `keyword_coverage`, `regex_match`
