# Deep Research

## Overview

**DeepResearch** is an iterative, budget-aware research workflow that replaces the linear `research` pipeline with a **ReAct-style loop**: search → extract → synthesize → evaluate → [loop or exit].

It is designed for complex, multi-faceted research goals that require multiple search rounds, evidence synthesis, and self-evaluation before producing a final report.

**Key characteristics:**
- **Iterative ReAct loop** — Decompose → Search → Synthesize → Evaluate → [loop]
- **Budget-aware** — Hard caps on iterations, API calls, and browser actions
- **Tool selection** — Chooses between `tavily`, `web`, and `browser` per query with fallback chains
- **Citation tracking** — Every source is registered via `core.citations`
- **Convergence detection** — Exits when knowledge stops changing (SequenceMatcher)
- **Stuck-loop detection** — Exits when no evidence is found for 2 consecutive iterations
- **Memory integration** — Recalls past research before starting, stores results after completion

**Status:** ✅ **Implemented** — v1 hardening complete (commit `0a03458` + follow-up fixes).

---

## Architecture

```
workflows/deep_research.py (facade)
└── run_deep_research_agent(goal)
    └── workflows.base.run_workflow("deep_research", ...)
        └── build_deep_research_graph()
            ├── recall ──→ decompose ──→ search ──→ synthesize ──→ [route]
            │                                              ↑         │
            │                                              └─────────┘
            │                                                        │
            └── report ──→ store ──→ distill ──→ notify ──→ END
```

### Nodes

| Node | Purpose | Key Behavior |
|------|---------|-------------|
| `recall` | Fetch relevant memories | Calls `memory.recall(query=goal, top_k=5)` |
| `decompose` | Break goal into sub-queries | Direct `llm.complete(role="planner")` — bypasses `agent(role="plan")` to avoid autocode prompt leak |
| `search` | Execute sub-queries, extract evidence | Tavily → web fallback on empty/error; browser fallback for JS walls; URL deduplication |
| `synthesize` | Merge evidence into knowledge_base | Replaces (not appends) previous knowledge; caps at 6K chars before sending to LLM |
| `report` | Build final report + budget audit | Returns `status="incomplete"` if completeness < threshold |
| `store` | Save to semantic memory | `memory.store_semantic(text=result, importance=6, tags="deep_research")` |
| `distill` | Workflow distillation | **No-op** until v2 — `sleep_learn` does not export `distill_workflow` |
| `notify` | Send completion notification | `notify(action="send", title="DeepResearch", message=result[:500])` |

### Conditional Routing

```python
# After synthesize, route_after_synthesize decides:
if iteration >= max_iterations:           → "report" (hard cap, always)
if completeness >= threshold and converged: → "report" (dual-gate)
if consecutive_empty_iterations >= 2:      → "report" (stuck-loop guard)
else:                                      → "search" (continue loop)
```

---

## State Schema

```python
class DeepResearchState(WorkflowState, total=False):
    # Input
    goal: str
    trace_id: str
    memory_context: str          # Recalled memories from episodic/semantic

    # Loop control
    iteration: int                 # Current iteration (0, 1, 2, ...)
    max_iterations: int            # Default: 10
    consecutive_empty_iterations: int  # Stuck-loop counter

    # Evaluation
    completeness: float          # 0.0 - 100.0 (LLM-scored)
    completeness_threshold: float  # Default: 85.0
    converged: bool                # SequenceMatcher > threshold
    convergence_threshold: float   # Default: 0.85

    # Knowledge
    knowledge_base: str            # Running synthesis (replaced each iteration)
    _prev_knowledge: str           # Snapshot for convergence detection
    synthesis: str                 # Latest synthesis output

    # Evidence
    sub_queries: list[str]         # Decomposed sub-queries
    pending_queries: list[str]       # Queries yet to search
    extracted_evidence: list[dict] # Evidence per iteration (cleared after synthesize)
    failed_sources: list[dict]     # URLs that failed extraction

    # Budget
    budget_api_calls: int          # Remaining Tavily API calls
    budget_browser_actions: int    # Remaining browser actions
    budget_events: list[dict]      # Audit trail of budget decisions

    # Output
    report: str
    result: str
    status: str                    # "success" | "incomplete" | "failed"
```

---

## Tool Integration Strategy

### Three-Tier Fallback

```
Tier 1: tavily(search)     → complex queries, API key available
Tier 2: web(search)          → simple queries, tavily exhausted/failed
Tier 3: browser(navigate)  → JS walls, short content (<100 chars)
```

| Condition | Primary Tool | Fallback | Rationale |
|-----------|-------------|----------|-----------|
| Complex query (8+ words, "compare", "vs") | `tavily` | `web` | Tavily has better ranking |
| Tavily returns empty/error | `web` | — | Free backup, no API cost |
| Content < 100 chars | `web` | `browser` | Likely JS-rendered or paywall |
| URL contains JS hints ("dashboard", "spa", "react") | `browser` | — | Renders JavaScript |

### Budget Decisions

| Budget Type | Config Field | Default | Tracking |
|-------------|-------------|---------|----------|
| Iterations | `DEEP_RESEARCH_MAX_ITERATIONS` | 10 | `iteration` counter |
| Tavily API calls | `DEEP_RESEARCH_MAX_API_CALLS` | 20 | `budget_api_calls` |
| Browser actions | `DEEP_RESEARCH_MAX_BROWSER_ACTIONS` | 5 | `budget_browser_actions` |

**Budget exhaustion strategy:**
- API calls exhausted → fall back to `web` (free)
- Browser actions exhausted → skip browser fallback, mark as `failed_sources`
- Iterations exhausted → return best-effort report with `status="incomplete"`

---

## Comparison with `research` Workflow

| Aspect | `research` (Linear) | `deep_research` (Iterative) |
|--------|---------------------|------------------------------|
| Structure | 8-node pipeline | Cyclic ReAct loop |
| Search | Single query | Multiple sub-queries, sequential |
| Extraction | Parallel scrape (all URLs) | Selective extraction with deduplication |
| Synthesis | One-shot | Iterative, knowledge replaced each round |
| Evaluation | None | Completeness scoring + convergence detection |
| Tool usage | `web` only | `tavily` → `web` → `browser` fallback chain |
| Budget | Unbounded | Explicit iteration/API/browser limits |
| Memory | Recall + store + distill + notify | Same pattern (recall before, store after) |
| Use case | Quick reports | Complex, multi-faceted investigations |

---

## Configuration

Add to `.env`:

```env
# DeepResearch budget limits
DEEP_RESEARCH_MAX_ITERATIONS=10
DEEP_RESEARCH_MAX_API_CALLS=20
DEEP_RESEARCH_MAX_BROWSER_ACTIONS=5
DEEP_RESEARCH_COMPLETENESS_THRESHOLD=85.0
DEEP_RESEARCH_CONVERGENCE_THRESHOLD=0.85
```

Config loads these in `core/config.py` as:
- `deep_research_max_iterations` (int)
- `deep_research_max_api_calls` (int)
- `deep_research_max_browser_actions` (int)
- `deep_research_completeness_threshold` (float)
- `deep_research_convergence_threshold` (float)

---

## Testing

```powershell
# Unit tests for all nodes (mocked LLM + tools)
D:\mcpgentenv\Scripts\python.exe -m pytest tests/workflows/deep_research/ -v

# Full suite
D:\mcpgentenv\Scripts\python.exe -m pytest
```

Current coverage: 48 tests, 796 total passing.

### Known Test Gaps (v2)
- Browser fallback integration test (requires Playwright)
- Tavily `_do_research()` accelerator (not yet wired)
- Parallel sub-query dispatch (LangGraph `Send`)

---

## v2 Roadmap

| Feature | Priority | Notes |
|---------|----------|-------|
| Parallel sub-query dispatch | P1 | LangGraph `Send` for tavily/web (browser stays sequential) |
| `_do_research()` accelerator | P1 | Tavily broad-sweep when iteration > 3 and completeness < 50 |
| Workflow distillation | P2 | Wire up `_node_distill` when `sleep_learn` exports `distill_workflow` |
| Telemetry persistence | P2 | Write `budget_events` to disk per trace_id |
| Streaming partial results | P2 | Yield intermediate synthesis per iteration |
| Knowledge compaction | P3 | LLM-based summarization when knowledge_base exceeds 8K chars |
| Tool selection classifier | P3 | Train lightweight classifier after 100+ traces |

---

## Known Limitations (v1)

1. **Browser fallback is sequential** — Each sub-query processes URLs one by one. v2 will parallelize tavily/web only.
2. **No `_do_research()` accelerator** — Tavily's deep-research endpoint is implemented in `tools/tavily.py` but not wired into the loop.
3. **Distill node is no-op** — `core.sleep_learn` does not export `distill_workflow`. Node passes through silently.
4. **Convergence threshold is heuristic** — `SequenceMatcher` at 0.85 may need tuning based on local model behavior.
5. **Goal length is uncapped** — Very long goals (>2000 chars) may overflow planner context. Add truncation in v2.
