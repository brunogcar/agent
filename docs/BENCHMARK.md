# Benchmark Tool v1.4.1

🎯 Benchmark LLM roles for the agent. Measure which model is best for each role.

---

## 🆕 What's New in v1.4.1

v1.4.1 fixes 3 remaining issues found after v1.4 testing, and restructures
route tasks for fairness.

### Bug Fixes

| # | Fix | Impact | Files |
|---|-----|--------|-------|
| 1 | **Test agent-mode: `setup_code` parameter** | Test tasks in agent-mode scored 10/100 for schema-following models (q3: 499 tokens, correct JSON) because the production SYSTEM_PROMPT asks for "pytest test file" but the validator's test_cases reference functions the model didn't define. `setup_code` runs BEFORE the model's code, providing the implementation. Granite (350M, ignores schema) scored 100 by accident — now all models can score fairly. | `validators.py`, `tasks/executor.yaml` (5 test tasks) |
| 2 | **Planner agent-mode: `agent_mode.validator` override** | Planner agent-mode dropped 93→38 because the `composite` validator (checks `^\d+\.` numbered list pattern) doesn't work on JSON output `{"goal":"...","steps":[...]}`. Added `agent_mode.validator: keyword_coverage` override — validates keywords in JSON values instead of numbered-list format. | `benchmark.py`, `tasks/planner.yaml` (10 tasks) |
| 3 | **Route task restructuring** | Route tasks were ambiguous: "direct" was a catch-all for 12 different tools, and route_research vs route_deep_research were nearly identical. Restructured: direct tasks now validate the specific TOOL name (git, memory, file, etc.) instead of just "direct". Added `autoresearch` workflow. Added multi-reference for ambiguous cases. | `tasks/router.yaml` (19 tasks, restructured) |

### New Features

| Feature | Notes |
|---------|-------|
| **`setup_code` in `python_execution`** | `validator_args: {setup_code: "def add(a,b): return a+b"}` — runs before model's code, provides implementations for test tasks |
| **`agent_mode.validator` override** | `agent_mode: {validator: keyword_coverage}` — uses a different validator in agent-mode than raw mode |
| **`agent_mode.expected` override** | `agent_mode: {expected: ["browser", "web"]}` — different expected answer in agent-mode than raw mode |
| **Route tool validation** | Direct/tool tasks validate the `tool` JSON field in agent-mode (e.g., `git`, `memory`, `file`) instead of just `workflow: direct` |
| **Multi-reference route answers** | `expected: ["research", "deep_research"]` — both answers accepted |
| **`autoresearch` workflow** | New route task `route_autoresearch` (normal difficulty) |

### Route Task Restructuring

**v1.3 (old):** All 18 route tasks validated `workflow` field. "Direct" was a catch-all for 12 tool-use tasks.

**v1.4.1 (new):** Route tasks split into two categories:

| Category | Tasks | Raw mode | Agent mode |
|----------|-------|----------|------------|
| **Workflow routing** | 8 tasks | System prompt asks for workflow name. Validates `workflow` field. | Extracts `workflow` from JSON, validates it. |
| **Tool routing** | 11 tasks | System prompt asks for tool name. Validates tool name. | Extracts `tool` from JSON, validates it. |

Workflow options: `[autocode, research, data, understand, direct, deep_research, autoresearch]`
Tool options: `[web, browser, cli, file, git, memory, agent, notify, report, vision, parallel, consult, tavily, python]`

Multi-reference examples:
- `route_research`: `expected: ["research", "deep_research"]` (both reasonable for CRISPR literature review)
- `route_browser`: raw `expected: browser`, agent `expected: ["browser", "web"]` (browser not in production schema's tool list)
- `route_parallel`: raw `expected: parallel`, agent `expected: ["parallel", "agent"]`

---

## 🆕 What's New in v1.4

## 🆕 What's New in v1.3

| Feature | Notes |
|---------|-------|
| **`--agent-mode` flag** | Uses agent role `SYSTEM_PROMPT` + `json_schema` from `ROLE_CONFIG` instead of YAML `system:` field. Tests the actual agent pipeline (model + real prompt + schema enforcement), not just raw model capability. Raw mode (without `--agent-mode`) is unchanged. |
| **`json_field` validator** | Extracts a field from JSON output (e.g., `patch` from code role's `{"analysis":..., "patch":...}`) and runs another validator on it. Used in agent-mode for code/refactor/test tasks. |
| **`schema_match` validator** | Validates output matches a JSON schema (required fields, types, enums, additionalProperties). No `jsonschema` dependency — manual check. |
| **Agent-mode latency buffer** | JSON-returning roles get +1.0-1.5s target latency buffer in agent mode (schema compilation overhead). Raw mode latencies unchanged. |
| **Agent-mode YAML fields** | Code tasks: `agent_mode: {json_field: patch}`. Refactor tasks: `json_field: refactored_code`. Test tasks: `json_field: test_code`. Router/plan tasks: `json_field: null` (validate full JSON). |

### Usage

```bash
# Raw mode (unchanged — tests model capability with generic prompts)
python -m benchmark --role router --depth easy

# Agent mode (new — tests agent pipeline with real prompts + schema enforcement)
python -m benchmark --role code --depth easy --agent-mode

# Agent mode for all roles
python -m benchmark --all --depth easy --agent-mode
```

---

## 🆕 What's New in v1.2

| Feature | Notes |
|---------|-------|
| **3 new executor sub-roles** | `refactor`, `test`, `document` — autonomous maintenance tasks |
| **Executor task count** | 23 → 36 tasks (13 new: 3 document + 5 test + 5 refactor) |
| **Depth behavior change** | `easy` = all easy tasks, `normal` = easy + medium, `hard` = all tasks |
| **New target latencies** | `refactor`: 15s, `test`: 15s, `document`: 10s |
| **Role group expansion** | `ROLE_GROUPS` and `ROLE_TO_GROUP` now include new sub-roles |
| **Config fix** | Removed duplicate `execution_timeout` assignment in `core/config.py` |

### v1.1 (June 2026)

| Feature | Notes |
|---------|-------|
| Variance tracking across `--runs` | Std dev + wobble flag (σ > 20) |
| Failure categorization | 6 categories: timeout, llm_error, exception, empty_output, format_error, wrong_answer |
| Baseline pinning | `--baseline` flag + delta reporting |
| Regression threshold | `--regression-threshold` + non-zero exit |
| Model recommendation | After `--compare`, best model per role |
| Difficulty sort | Tasks sorted by difficulty before `--depth` slicing |
| Multi-reference support | `expected` as `str | list[str]` in validators |
| New router tasks | 30 tasks covering deep_research, cli, browser, tavily, parallel, consult, vision, agent, report, notify |
| `--depth hard` = all tasks | No longer capped at 15 |
| `--all` → `mixed` filename | Consistent with actual behavior |
| `--compare` → `_vs_` separator | Only when 2+ models |
| `reports.py` extraction | All terminal formatting centralized |

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
| `--role executor` | Test executor role (summarize, extract, research, critique, analyze, code, review, refactor, test, document) |
| `--role planner` | Test planner role |
| `--role refactor` | Test refactor sub-role only |
| `--role test` | Test test sub-role only |
| `--role document` | Test document sub-role only |
| `--all` | Test every role (excludes vision and consultor — no task YAMLs yet) |
| `--depth easy` | **All** tasks with `difficulty: easy` per role |
| `--depth normal` | **All** tasks with `difficulty: easy` or `normal` per role |
| `--depth hard` | **All** tasks per role (thorough) |
| `--runs 3` | 3 runs per task (consistency + wobble detection) |
| `--compare modelA,modelB` | Compare two models side-by-side |
| `--compare modelA` | Override all roles to one model (no .env edit) |
| `--tag "label"` | Label the JSON report |
| `--baseline path.json` | Compare scores vs previous run |
| `--regression-threshold 5.0` | Exit code 1 if any role drops more than 5 points |
| `--temperature 0.0` | Set LLM temperature |

> **Note on `--depth` behavior (v1.2+):** Previously, `--depth easy` returned the first 5 tasks regardless of difficulty mix. Now it returns **all** tasks tagged `easy`. This is more intuitive but may run more tasks than before.

---

## 🎭 Role Groups

| Group | Roles included | Tasks | Difficulty Mix |
|-------|---------------|-------|---------------|
| `router` | classify, route | 30 | easy×12, medium×8, hard×10 |
| `executor` | summarize, extract, research, critique, analyze, code, review, **refactor**, **test**, **document** | **36** | easy×14, medium×12, hard×10 |
| `planner` | planner | 10 | easy×3, medium×4, hard×3 |

> **Note:** `vision` and `consultor` groups are reserved but have no task YAMLs yet. Test them explicitly with `--role vision` or `--role consultor` when added.

### Sub-Role Task Breakdown (executor)

| Sub-Role | Tasks | Easy | Medium | Hard | Validator Pattern |
|----------|-------|------|--------|------|-------------------|
| summarize | 3 | 1 | 1 | 1 | `keyword_coverage` |
| extract | 3 | 1 | 1 | 1 | `contains` / `fuzzy_match` |
| research | 3 | 1 | 1 | 1 | `keyword_coverage` |
| critique | 3 | 1 | 1 | 1 | `keyword_coverage` |
| analyze | 3 | 1 | 1 | 1 | `keyword_coverage` |
| code | 3 | 1 | 1 | 1 | `python_execution` |
| review | 3 | 1 | 1 | 1 | `keyword_coverage` |
| **refactor** | **5** | **2** | **2** | **1** | **`python_execution`** |
| **test** | **5** | **2** | **2** | **1** | **`python_execution`** |
| **document** | **3** | **1** | **1** | **1** | **`keyword_coverage`** |

---

## 🏆 Scoring

| Metric | Weight | Description |
|--------|--------|-------------|
| Correctness | 70% | Did it do the task right? |
| Format | 20% | Was the output format valid? |
| Speed | 10% | Was it fast? (normalized by role target latency) |

**Final score:** 0-100. 80+ = ✅ pass, 50-80 = ⚠️ partial, <50 = ❌ fail.

### Target Latencies by Role

| Role | Target Latency | Rationale |
|------|---------------|-----------|
| classify / route | 2s | Fast classification decisions |
| summarize / extract | 5s | Short text generation |
| critique / analyze / review / **document** | 10s | Medium text generation |
| research / code / **refactor** / **test** | 15s | Complex reasoning or code execution |
| planner | 20s | Multi-step planning |

---

## ✅ Validators

| Validator | What it checks | Multi-reference | Best For |
|-----------|---------------|-----------------|----------|
| `exact_match` | Case-insensitive string equality | ✅ `expected: ["a", "b"]` | Simple factual answers |
| `contains` | Case-insensitive substring match | ✅ `expected: ["a", "b"]` | Keyword presence |
| `fuzzy_match` | `difflib.SequenceMatcher` ratio (threshold default 0.6) | ✅ `expected: ["a", "b"]` | Paraphrased answers |
| `json_valid` | Parses as JSON, optional schema required keys | ❌ | Structured output |
| `python_ast` | Parses as Python AST (strips markdown fences) | ❌ | Syntax validation |
| `python_execution` | **Executes code** in restricted namespace against test cases | ❌ | Code correctness |
| `keyword_coverage` | Fraction of expected keywords found (whole-word match) | ❌ | Documentation, summaries |
| `regex_match` | Regex pattern match | ❌ | Format validation |
| `composite` | **Averages multiple checks:** regex + step count + keywords + ordering | ❌ | Complex structured output |

### Validator Selection Guide

| Task Type | Recommended Validator | Why |
|-----------|----------------------|-----|
| Code generation | `python_execution` | Actually runs the code, catches syntax + logic errors |
| Code refactoring | `python_execution` | Verifies refactored code produces same output |
| Test generation | `python_execution` | Runs the generated tests, checks they pass |
| Documentation | `keyword_coverage` | Checks required concepts are mentioned |
| API docs | `keyword_coverage` or `composite` | Structured docs need both content and format |
| Planning | `composite` | Numbered steps + required keywords + ordering |
| Classification | `exact_match` or `contains` | Deterministic labels |
| Research summaries | `keyword_coverage` | Key facts must be present |

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
 ⚠️ REGRESSION DETECTED
 executor: -8.1 points below baseline
======================================================================
```

Useful for CI pipelines.

---

## 🏅 Model Recommendation

After `--compare modelA,modelB`, the benchmark recommends the best model per role:

```
RECOMMENDED MODELS
 Role                 Model                     Score   Latency
 ─────────────────────────────────────────────────────────────────
 classify             gemma-2-2b-it             91.0    0.1s
 route                gemma-2-2b-it             78.0    0.1s
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

### Task Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | **Yes** | Unique task identifier. Use `{subrole}_{description}` format for executor tasks |
| `system` | `str` | No | System prompt for the LLM |
| `prompt` | `str` | **Yes** | User prompt — the actual task |
| `validator` | `str` | No | Validator to use. Default: `exact_match` |
| `validator_args` | `dict` | No | Validator-specific arguments |
| `expected` | `str \| list[str]` | No | Expected answer(s). For multi-reference, use list |
| `difficulty` | `str` | No | `easy`, `medium`, or `hard`. Default: `medium` |
| `timeout` | `int` | No | Task timeout in seconds. Default: 120 |
| `max_tokens` | `int` | No | Max tokens for LLM response. Default: 1024 |

### Composite Validator Fields

| Field | Type | Description |
|-------|------|-------------|
| `pattern` | `str` | Regex for format check (e.g., `^\d+\.` for numbered lists) |
| `min_steps` | `int` | Minimum numbered steps or bullet points |
| `required_keywords` | `list[str]` | Keywords that must appear (whole-word match) |
| `must_appear_before` | `list[list[str]]` | Ordering constraints: `[first, second]` must appear in order |

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

### Writing Good `python_execution` Tasks

**DO:**
- Define the function at top level — the validator calls it directly
- Use `assert` statements in `test_cases` that reference the function name
- Keep test cases independent (each can run standalone)
- Test edge cases: empty input, zero, negative, large values

**DON'T:**
- Ask for a `run_tests()` wrapper — models struggle with nested function definitions
- Use complex class syntax for small models — `@dataclass`, `@property`, descriptors often fail
- Put multiple test assertions on one line — harder to debug failures

---

## 🗺️ Roadmap

### ✅ Completed

| Feature | Version | Notes |
|---------|---------|-------|
| 3 new executor sub-roles | v1.2 | refactor, test, document |
| Depth filter behavior | v1.2 | easy = all easy, normal = easy+medium, hard = all |
| Variance tracking | v1.1 | Std dev + wobble flag (σ > 20) |
| Failure categorization | v1.1 | 6 categories |
| Baseline pinning | v1.1 | `--baseline` + delta |
| Regression threshold | v1.1 | Non-zero exit on drop |
| Model recommendation | v1.1 | Best model per role after compare |
| Multi-reference support | v1.1 | `expected` as `str \| list[str]` |
| New router tasks | v1.1 | 30 tasks for new tool types |
| `--depth hard` = all tasks | v1.1 | No cap |
| `reports.py` extraction | v1.1 | Centralized terminal formatting |

### 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Baseline delta in final table | Currently shows per-role, missing from final `Model:` block | P1 |
| Semantic similarity validator | Embedding-based for subjective tasks | P2 |
| Token efficiency diagnostic | Tokens/correctness ratio as info column | P2 |
| Vision tasks | Add `vision.yaml` with image description | P2 |
| Consultor tasks | Add `consultor.yaml` with second-opinion scenarios | P2 |
| Parameterized tasks | Jinja2 template expansion for task variety | P3 |
| Temperature sweep mode | `--temp-sweep 0.0,0.3,0.7` convenience wrapper | P3 |
| Parallel execution | Requires async `llm.complete()` or vLLM batching | P3 |

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
- Update `BENCHMARK.md` when adding roles, validators, or changing behavior

**❌ DON'T:**
- Rewrite entire files from scratch
- Regenerate YAML files from scratch (edit in-place)
- Strip `snippet()` behavior — output truncation prevents terminal pollution
- Change `executor.yaml` `test_cases` formatting — escaped quotes are fragile
- Add `conftest.py` fixtures — tests must be self-contained
- Break `python -m benchmark` entry point
- Change 70/20/10 scoring weights without explicit user approval
- Add `run_tests()` wrappers to `python_execution` tasks — models struggle with nested definitions
- Use complex class syntax (`@dataclass`, `@property`) for tasks targeting small models

### File Responsibilities

| File | Responsibility |
|------|---------------|
| `benchmark.py` | Orchestration: CLI, role loops, model resolution, JSON export, depth filtering |
| `reports.py` | All terminal formatting: colors, tables, summaries, comparisons, wobble warnings |
| `scoring.py` | Score calculation (70/20/10), failure categorization, consistency metrics, difficulty breakdown |
| `validators.py` | Output validation, multi-reference support, restricted code execution |
| `tasks/*.yaml` | Task definitions — preserve formatting, edit in-place, append new tasks at end |

### Testing Benchmark Changes

Benchmark has **no unit tests** — it IS the test. Validate by running:

```bash
# Sanity
python -m benchmark --role router --depth easy

# New roles
python -m benchmark --role refactor --depth easy
python -m benchmark --role test --depth easy
python -m benchmark --role document --depth easy

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
- [ ] `--role refactor --depth easy` runs without errors
- [ ] `--role test --depth easy` runs without errors
- [ ] `--role document --depth easy` runs without errors
- [ ] `--all --depth easy` runs without errors
- [ ] `--compare` loads both models correctly
- [ ] JSON report filename is correct (`mixed` for `--all`, `_vs_` for compare)
- [ ] No tracer warnings for valid roles
- [ ] Difficulty breakdown shows in per-role summary
- [ ] Failure counts only show for actual failures (not passing tasks)
- [ ] `BENCHMARK.md` updated with new roles/behavior

---

## 🏗️ Architecture

```
benchmark/
├── __main__.py          # Entry point: python -m benchmark
├── benchmark.py          # Main runner, CLI, model resolution, depth filter, JSON export
├── reports.py            # All terminal formatting (extracted from benchmark.py)
├── scoring.py            # Score calculation, failure categorization, consistency
├── validators.py         # 9 validators with multi-reference support
└── tasks/
    ├── router.yaml       # 30 tasks: 12 classify + 18 route
    ├── executor.yaml     # 36 tasks: 10 sub-roles (incl. refactor, test, document)
    ├── planner.yaml      # 10 tasks
    ├── vision.yaml       # Reserved, minimal or empty
    └── consultor.yaml    # Reserved, minimal or empty
```

**Data flow:**

```
run_benchmark() → run_role() → [run_task() × tasks × runs]
    → calculate_task_score() → calculate_role_score()
    → JSON dump + terminal output via reports.py
```

**Depth filtering (v1.2+):**

```
tasks = load_tasks(role)  # sorted by difficulty ascending
if depth == "easy":
    selected = [t for t in tasks if t["difficulty"] == "easy"]
elif depth == "normal":
    selected = [t for t in tasks if t["difficulty"] in ("easy", "normal")]
else:  # hard
    selected = tasks  # all tasks
```

---

## 🔗 Cross-References

- **Core LLM:** See `docs/LLM.md` for role-based dispatch, circuit breakers, context budgeting
- **Core Config:** See `docs/CONFIG.md` for `.env` model loading, per-role configs, timeout resolution
- **Router:** See `docs/ROUTER.md` for task routing logic
- **Core Architecture:** See `docs/CORE.md` for full module map and dependency rules

---

*Architecture: thin facade + role groups + atomic task YAMLs + filter-based depth selection + 70/20/10 scoring + restricted code execution + multi-reference validation + wobble detection + baseline comparison + model recommendation.*
