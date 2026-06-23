# Benchmark Tool

🎯 Benchmark LLM roles for the agent. Measure which model is best for each role.

---

## 🚀 Quick Start

```bash
# Test router role (classify + route) — easy depth, 1 run
python -m benchmark --role router --depth easy

# Test executor role — normal depth, 3 runs for consistency
python -m benchmark --role executor --depth normal --runs 3

# Test all roles — hard depth, 5 runs
python -m benchmark --all --depth hard --runs 5

# Compare two models on the same tasks
python -m benchmark --compare granite-350m,qwen-3b --role code

# Override .env with one model across all roles
python -m benchmark --compare gemma-2-2b-it --all --depth easy

# Tag the run for tracking
python -m benchmark --role router --tag "baseline-v1"

# Baseline comparison — show delta vs previous run
python -m benchmark --role router --baseline workspace/benchmarks/baseline.json

# Regression detection — exit non-zero if any role drops > 5 points
python -m benchmark --all --baseline workspace/benchmarks/baseline.json --regression-threshold 5.0
```

---

## 📋 Commands

| Command | What it does |
|---------|-------------|
| `--role router` | Test router role (classify + route) |
| `--role executor` | Test executor role (summarize, extract, research, critique, analyze, code, review) |
| `--role planner` | Test planner role |
| `--all` | Test every role |
| `--depth easy` | 5 easiest tasks per role (fast) |
| `--depth normal` | 10 easiest tasks per role (default) |
| `--depth hard` | **All** tasks per role (thorough) |
| `--runs 3` | 3 runs per task (consistency + wobble detection) |
| `--compare modelA,modelB` | Compare two models side-by-side |
| `--compare modelA` | Override all roles to one model (no .env edit) |
| `--tag "label"` | Label the JSON report |
| `--baseline path.json` | Compare scores vs previous run |
| `--regression-threshold 5.0` | Exit code 1 if any role drops > N points |
| `--temperature 0.0` | Set LLM temperature |

---

## 🎭 Role Groups

| Group | Roles included | Tasks | Difficulty Mix |
|-------|---------------|-------|---------------|
| `router` | classify, route | 30 | easy×12, medium×8, hard×10 |
| `executor` | summarize, extract, research, critique, analyze, code, review | 23 | easy×10, medium×8, hard×5 |
| `planner` | planner | 10 | easy×3, medium×4, hard×3 |

> **Note:** `vision` and `consultor` groups are reserved but have no task YAMLs yet.

---

## 🏆 Scoring

| Metric | Weight | Description |
|--------|--------|-------------|
| Correctness | 70% | Did it do the task right? |
| Format | 20% | Was the output format valid? |
| Speed | 10% | Was it fast? (normalized by role target latency) |

**Final score:** 0-100. 80+ = ✅ pass, 50-80 = ⚠️ partial, <50 = ❌ fail.

**Target latencies by role:**
- classify/route: 2s
- summarize/extract: 5s
- critique/analyze/review: 10s
- research/code: 15s
- planner: 20s

---

## ✅ Validators

| Validator | What it checks | Multi-reference |
|-----------|---------------|-----------------|
| `exact_match` | Case-insensitive string equality | ✅ `expected: ["a", "b"]` |
| `contains` | Case-insensitive substring match | ✅ `expected: ["a", "b"]` |
| `fuzzy_match` | `difflib.SequenceMatcher` ratio (threshold default 0.6) | ✅ `expected: ["a", "b"]` |
| `json_valid` | Parses as JSON, optional schema required keys | ❌ |
| `python_ast` | Parses as Python AST (strips markdown fences) | ❌ |
| `python_execution` | **Executes code** in restricted namespace against test cases | ❌ |
| `keyword_coverage` | Fraction of expected keywords found (whole-word match) | ❌ |
| `regex_match` | Regex pattern match | ❌ |
| `composite` | **Averages multiple checks:** regex + step count + keywords + ordering | ❌ |

---

## 🔍 Failure Analysis

When tasks fail, the benchmark categorizes the failure:

| Category | Trigger |
|----------|---------|
| `timeout` | ⏱️ Task exceeded timeout |
| `llm_error` | 🤖 LLM returned an error response |
| `exception` | 💥 Python exception during execution |
| `empty_output` | 📭 Model returned nothing |
| `format_error` | 📝 Format score < 0.5 but correctness ≥ 0.5 |
| `wrong_answer` | ❌ Correctness < 0.5 |
| `unknown` | ❓ Could not categorize |

Failures are reported per-role in the terminal output.

---

## 📊 Consistency / Wobble Detection

With `--runs N`, the benchmark computes standard deviation across runs. If σ > 20 on the 0-100 scale, the task is flagged as "wobbly":

```
⚠ classify_adversarial wobbly (σ=35.2)
```

Wobbly tasks indicate non-deterministic models or borderline capability.

---

## 📈 Baseline & Regression

### Baseline Comparison

Pass `--baseline path/to/old.json` to compare current scores vs a previous run:

```
  ▲ +4.2 vs baseline
  ▼ -6.1 vs baseline
```

### Regression Detection

Pass `--regression-threshold 5.0` to exit with code 1 if any role drops more than 5 points:

```
======================================================================
 ⚠️  REGRESSION DETECTED
   executor: -8.1 points below baseline
======================================================================
```

Useful for CI pipelines.

---

## 🏅 Model Recommendation

After `--compare modelA,modelB`, the benchmark recommends the best model per role:

```
RECOMMENDED MODELS
 Role                 Model                       Score   Latency
 ─────────────────────────────────────────────────────────────────
 classify             gemma-2-2b-it                91.0     0.1s
 route                gemma-2-2b-it                78.0     0.1s
```

---

## 📁 Reports

JSON reports saved to `workspace/benchmarks/` with descriptive filenames:

```
workspace/benchmarks/
├── benchmark_easy_all_mixed_runs1_20250623-115141.json
├── benchmark_normal_router_gemma-2-2b-it_runs3_20250623-120000.json
└── benchmark_hard_executor_granite-350m_vs_qwen-3b_runs3_20250623-121500.json
```

**Filename format:** `benchmark_{depth}_{roles}_{model}_runs{runs}_{timestamp}{_tag}.json`

- `--all` → `mixed` in filename
- `--compare a,b` → `a_vs_b` in filename
- Single role → actual model name in filename

Console output includes:
- YAML-grouped role headers (`ROUTER`, `EXECUTOR`, `PLANNER`)
- Per-task latency, tokens, throughput, score
- Per-role summary: accuracy, avg time, avg tokens, t/s, score, difficulty breakdown, failure counts
- Final ASCII table with all roles and per-model stack scores

---

## 📝 Adding Tasks

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

> **🔒 Security:** Code execution runs in a restricted namespace with limited builtins. No file system, no network, no imports.

### Multi-Reference Expected Answers

For tasks with multiple acceptable answers:

```yaml
    expected: ["Paris", "Paris, France", "the city of Paris"]
    validator: contains  # or fuzzy_match
```

The validator returns the best match across all references.

---

## 🗺️ Roadmap

### ✅ Completed (June 2026)

| Feature | Notes |
|---------|-------|
| Variance tracking across `--runs` | Std dev + wobble flag (σ > 20) |
| Failure categorization | 6 categories: timeout, llm_error, exception, empty_output, format_error, wrong_answer |
| Baseline pinning | `--baseline` flag + delta reporting |
| Regression threshold | `--regression-threshold` + non-zero exit |
| Model recommendation | After `--compare`, best model per role |
| Difficulty sort | Tasks sorted by difficulty before `--depth` slicing |
| Multi-reference support | `expected` as `str \| list[str]` in validators |
| New router tasks | 30 tasks covering deep_research, cli, browser, tavily, parallel, consult, vision, agent, report, notify |
| Classify threshold 0.9 | All classify tasks use `validator_args: {threshold: 0.9}` |
| `--depth hard` = all tasks | No longer capped at 15 |
| `--all` → `mixed` filename | Consistent with actual behavior |
| `--compare` → `_vs_` separator | Only when 2+ models |
| `reports.py` extraction | All terminal formatting centralized |
| Core LLM role fix | `route` added to `_defaults` in `core/llm_backend/config.py` |
| Executor difficulty balance | Every sub-role has ≥3 tasks with mixed difficulty |

### 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Baseline delta in final table | Currently shows per-role, missing from final `Model:` block | P1 |
| Semantic similarity validator | Embedding-based (ChromaDB or sentence-transformers) for subjective tasks | P2 |
| Token efficiency diagnostic | Add tokens/correctness ratio as informational column (not score penalty) | P2 |
| Parameterized tasks | Jinja2 template expansion for task variety at scale | P3 |
| Temperature sweep mode | `--temp-sweep 0.0,0.3,0.7` convenience wrapper | P3 |
| Parallel execution | Requires async `llm.complete()` or vLLM batching | P3 |
| Vision tasks | Add `vision.yaml` with image description/classification | P2 |
| Consultor tasks | Add `consultor.yaml` with second-opinion scenarios | P2 |

### 🚫 Deferred / Out of Scope

These items were evaluated and deferred. Future AIs should not recommend them without new justification:

| # | Feature | Why Deferred | Priority |
|---|---------|-------------|----------|
| 1 | **LLM-as-judge validator** | Too slow (doubles benchmark time). 7B judge unreliable. Sycophancy bias. | Skip |
| 2 | **Cross-role consistency mode** | Integration test, not benchmark feature. Different roles have different system prompts. | Skip |
| 3 | **BLEU/ROUGE validators** | No gold-standard references. Keyword coverage covers same ground. | Skip |
| 4 | **Historical trend visualization / matplotlib** | Heavy dependency for CLI tool. JSON exports feed external dashboards. | Skip |
| 5 | **Code quality validator (flake8/pylint)** | `python_execution` already tests if code works. Linting is overkill. | Skip |
| 6 | **VRAM budget in recommendation engine** | No VRAM tracking in benchmark. Requires new instrumentation. | Skip |
| 7 | **Difficulty calibration command** | Running all tasks with reference model is overkill. Manual tags are good enough. | Skip |
| 8 | **Batch inference** | LM Studio/Ollama don't support batching for different prompts. | Skip |
| 9 | **Change scoring weights to 60/15/25** | User explicitly likes 70/20/10. Speed already captured. | Skip |

---

## 🛠️ Development Guidelines

### When Editing Benchmark Files

**✅ DO:**
- Add surgical changes — one feature at a time
- Preserve existing YAML formatting (especially `test_cases` with escaped quotes)
- Use `reports.py` for all new terminal output formatting
- Add comments explaining what changed
- Test with `--role router --depth easy` as sanity check
- Test with `--all --depth easy` before declaring done
- Test `--compare modelA,modelB` when touching model resolution
- Run compileall on all `.py` files before testing

**❌ DON'T:**
- Rewrite entire files from scratch
- Regenerate YAML files from scratch (edit in-place)
- Strip `snippet()` behavior — output truncation prevents terminal pollution
- Change `executor.yaml` `test_cases` formatting — escaped quotes are fragile
- Add `conftest.py` fixtures — tests must be self-contained
- Break `python -m benchmark` entry point
- Change 70/20/10 scoring weights without explicit user approval

### File Responsibilities

| File | Responsibility |
|------|---------------|
| `benchmark.py` | Orchestration: CLI, role loops, model resolution, JSON export |
| `reports.py` | All terminal formatting: colors, tables, summaries, comparisons |
| `scoring.py` | Score calculation, failure categorization, consistency metrics |
| `validators.py` | Output validation, multi-reference support |
| `tasks/*.yaml` | Task definitions — preserve formatting, edit in-place |

### Testing Benchmark Changes

Benchmark has **no unit tests** — it IS the test. Validate by running:

```bash
# Sanity
python -m benchmark --role router --depth easy

# Full coverage
python -m benchmark --all --depth easy

# Consistency
python -m benchmark --role router --depth easy --runs 3

# Model override
python -m benchmark --compare gemma-2-2b-it --role router --depth easy

# Baseline
python -m benchmark --role router --baseline path/to/old.json
```

### Commit Checklist

- [ ] `benchmark.py` compiles
- [ ] `reports.py` compiles
- [ ] `scoring.py` compiles
- [ ] `validators.py` compiles
- [ ] All task YAMLs parse (`yaml.safe_load`)
- [ ] `--role router --depth easy` runs without errors
- [ ] `--all --depth easy` runs without errors
- [ ] `--compare` loads both models correctly
- [ ] JSON report filename is correct (`mixed` for `--all`, `_vs_` for compare)
- [ ] No tracer warnings for valid roles
- [ ] Difficulty breakdown shows in per-role summary
- [ ] Failure counts only show for actual failures (not passing tasks)

---

## 🏗️ Architecture

```
benchmark/
├── __main__.py          # Entry point: python -m benchmark
├── benchmark.py          # Main runner, CLI, model resolution
├── scoring.py            # Score calculation, failure categorization
├── validators.py         # 9 validators with multi-reference support
├── reports.py            # All terminal formatting (extracted from benchmark.py)
└── tasks/
    ├── router.yaml       # 30 tasks: 12 classify + 18 route
    ├── executor.yaml     # 23 tasks: 7 sub-roles
    └── planner.yaml      # 10 tasks
```

**Data flow:**

```
run_benchmark() → run_role() → [run_task() × tasks × runs]
  → calculate_task_score() → calculate_role_score()
  → JSON dump + terminal output via reports.py
```

---

## 🔗 Cross-References

- **Core LLM:** See `docs/LLM.md` for role-based dispatch, circuit breakers, context budgeting
- **Core Config:** See `docs/CONFIG.md` for `.env` model loading, per-role configs
- **Router:** See `docs/ROUTER.md` for task routing logic
- **Core Architecture:** See `docs/CORE.md` for full module map and dependency rules
