# DEEP RESEARCH

## Overview

**Deep Research** is a planned iterative research workflow inspired by [Alibaba-NLP/DeepResearch](https://github.com/Alibaba-NLP/DeepResearch). It replaces the linear `research` pipeline with a **ReAct-style loop** that searches, extracts, synthesizes, and self-evaluates until the research goal is sufficiently answered or a budget is exhausted.

**Key characteristics:**
- **Iterative ReAct loop** — Search → Extract → Synthesize → Evaluate → [loop]
- **Budget-aware** — Max iterations, token limits, API credit tracking
- **Tool selection** — Chooses between `web`, `tavily`, and `browser` per step
- **Evidence tracking** — Structured citations with confidence scores
- **Checkpointed** — LangGraph StateGraph with resume-on-failure

**Status:** 🚧 Planned — not yet implemented. This document serves as the architectural backbone.

---

## Architecture

```
workflows/deep_research.py (planned)
├── build_deep_research_graph()    # StateGraph with cyclic conditional edges
├── DeepResearchState (TypedDict)
│   ├── goal, trace_id
│   ├── iteration, max_iterations
│   ├── completeness_score         # 0-100
│   ├── knowledge_base             # Accumulated findings
│   ├── pending_queries            # Sub-queries to investigate
│   ├── search_results             # Raw results per iteration
│   ├── extracted_evidence         # Evidence per iteration
│   ├── synthesis                  # Running synthesis
│   ├── citations                  # All sources with scores
│   └── budget_remaining           # Token/API budget tracker
│
├── Nodes:
│   ├── node_decompose_goal        # Break goal into sub-queries
│   ├── node_select_tool           # Choose web/tavily/browser per query
│   ├── node_search                # Execute search (parallel batched)
│   ├── node_extract               # Extract content from URLs
│   ├── node_synthesize            # Synthesize findings + update knowledge_base
│   ├── node_evaluate              # Score completeness (0-100)
│   └── node_report                # Final report generation
│
└── Conditional edges:
    ├── evaluate → search          # If completeness < threshold AND budget > 0
    ├── evaluate → report          # If completeness >= threshold
    └── evaluate → report          # If budget exhausted (best effort)
```

---

## State Schema

```python
class DeepResearchState(TypedDict, total=False):
    # Input
    goal: str                       # Original research question
    trace_id: str                   # Trace identifier

    # Loop control
    iteration: int                  # Current iteration (0, 1, 2, ...)
    max_iterations: int             # Default: 10
    completeness_score: float      # 0.0 - 100.0
    completeness_threshold: float    # Default: 85.0

    # Knowledge accumulation
    knowledge_base: list[str]       # Synthesized findings per iteration
    pending_queries: list[str]       # Sub-queries still to investigate
    answered_queries: list[str]     # Sub-queries already answered

    # Evidence
    search_results: list[dict]      # Raw search results per iteration
    extracted_evidence: list[dict]   # Extracted content per iteration
    citations: list[dict]           # All sources with confidence scores

    # Budget
    budget_tokens: int              # Remaining token budget
    budget_api_calls: int           # Remaining API call budget
    budget_start_time: float        # Loop start timestamp

    # Output
    synthesis: str                   # Final synthesized answer
    report_html: str                 # Generated HTML report
    report_path: str                # Path to saved report
    status: str                     # "pending" | "running" | "complete" | "error"
```

---

## Node Details (Planned)

### `node_decompose_goal` — Query Decomposition

Uses the planner LLM to break the research goal into sub-queries:

```python
# Example:
# Goal: "Compare Python async frameworks in 2026"
# → Sub-queries:
#   1. "What are the most popular Python async frameworks in 2026?"
#   2. "Performance benchmarks asyncio vs trio vs anyio 2026"
#   3. "Production adoption rates of Python async frameworks"
#   4. "Recent breaking changes in asyncio Python 3.13+"
```

**Output:** `pending_queries` — prioritized list of sub-queries.

### `node_select_tool` — Tool Selection

Per sub-query, selects the optimal tool based on heuristics:

| Heuristic | Selected Tool | Rationale |
|-----------|---------------|-----------|
| Simple factual query | `web(search)` | Fast, free, no API costs |
| Complex/multi-faceted query | `tavily(search)` | Better ranking, AI answer, citations |
| JS-heavy site suspected | `browser(navigate+text_content)` | Renders JavaScript |
| Known URLs to extract | `tavily(extract)` | Bulk extraction, structured output |
| Site exploration needed | `tavily(crawl)` | Deep link following |

**Future:** Train a lightweight classifier to optimize tool selection based on query type.

### `node_search` — Parallel Search

Executes all `pending_queries` in parallel using LangGraph `Send`:

```python
# Parallel fan-out
for query in pending_queries:
    yield Send("node_search", {"query": query, "tool": selected_tool})
```

**Results merged into:** `search_results`.

### `node_extract` — Evidence Extraction

For each URL in search results:
1. Try `tavily(extract)` for bulk static extraction (fastest)
2. If empty/short, try `web(read)` (lightweight)
3. If still empty, try `browser(navigate+text_content)` (JS rendering)

**Evidence scored by relevance:**
```python
{
    "url": "...",
    "text": "...",
    "relevance_score": 0.87,  # LLM-scored against sub-query
    "extraction_method": "tavily|web|browser",
    "timestamp": "..."
}
```

### `node_synthesize` — Knowledge Integration

Updates `knowledge_base` with new evidence:

```python
# Prompt:
# "Given the current knowledge base and new evidence, produce an updated synthesis.
# Flag any contradictions. Cite sources."
```

**Output:** Updated `synthesis` + `citations` + `answered_queries`.

### `node_evaluate` — Completeness Check

Scores whether the goal is sufficiently answered:

```python
# Prompt:
# "Rate how completely the following synthesis answers the original goal.
# 0 = no information, 100 = fully answered with evidence."
```

**Routing logic:**
```python
if completeness_score >= completeness_threshold:
    return "report"      # Done
elif iteration >= max_iterations:
    return "report"      # Budget exhausted, best effort
else:
    # Generate new sub-queries from gaps
    return "search"      # Continue loop
```

### `node_report` — Final Output

Generates structured report:
- Executive summary
- Evidence sections with citations
- Confidence ratings per claim
- Gaps identified (if any)
- Suggestions for further research

---

## Tool Integration Strategy

### Web vs Tavily vs Browser

| Phase | Primary Tool | Fallback | Rationale |
|-------|-------------|----------|-----------|
| Discovery | `tavily(search)` | `web(search)` | Tavily has better ranking; web is free backup |
| Extraction (static) | `tavily(extract)` | `web(read)` | Bulk extraction is efficient; web is lightweight |
| Extraction (JS) | `browser(navigate+text_content)` | — | Only tool that renders JS |
| Deep crawl | `tavily(crawl)` | `browser` + manual navigation | Tavily crawl is automated; browser for targeted exploration |

### Tavily `research` Action (Workflow-Only)

The `tavily.research` action (end-to-end deep research via Tavily's API) is **not exposed as a tool action** to the LLM. Instead, it is used internally by `node_synthesize` as an optional accelerator:

```python
# When iteration > 3 and completeness is still low,
# use tavily.research as a "broad sweep" to fill gaps:
if iteration > 3 and completeness_score < 50:
    broad_result = _do_research(input=goal)
    # Merge broad_result into knowledge_base
```

This prevents the LLM from burning API credits on simple queries while making the powerful `research` action available for genuinely complex investigations.

---

## Budget Management

| Budget Type | Default | Tracking |
|-------------|---------|----------|
| Iterations | 10 | `iteration` counter in state |
| LLM tokens | 32K per iteration | `budget_tokens` decremented per call |
| Tavily API calls | 20 total | `budget_api_calls` decremented per call |
| Browser actions | 10 total | `budget_browser` decremented per call |
| Time | 5 minutes | `budget_start_time` + timeout check |

**Budget exhaustion strategy:**
- Return best-effort synthesis with gaps flagged
- Suggest which sub-queries the user should investigate manually
- Never hang or loop infinitely

---

## Comparison with Current `research` Workflow

| Aspect | `research` (Current) | `deep_research` (Planned) |
|--------|----------------------|---------------------------|
| Structure | Linear 8-node pipeline | Cyclic ReAct loop |
| Search | Single query | Multiple sub-queries, parallel |
| Extraction | Parallel scrape (all URLs) | Selective extraction (evidence-scored) |
| Synthesis | One-shot | Iterative, knowledge accumulation |
| Evaluation | None | Completeness scoring per iteration |
| Tool usage | `web` only | `web` + `tavily` + `browser` |
| Fallback | None | Browser for JS, Tavily for deep |
| Budget | Unbounded | Explicit iteration/token/API limits |
| Resume | Checkpoint at node level | Checkpoint at iteration level |
| Use case | Quick reports | Complex investigations |

---

## Implementation Timeline

| Phase | Deliverable | Dependencies |
|-------|-------------|--------------|
| **Phase 0 (Done)** | `tavily` tool + `browser` tool | ✅ Complete |
| **Phase 1 (Next)** | Browser fallback in `research.py` | `browser` tool |
| **Phase 2 (Next)** | Tavily integration in `research.py` | `tavily` tool |
| **Phase 3 (Future)** | `deep_research.py` skeleton | LangGraph cyclic edges |
| **Phase 4 (Future)** | `node_decompose` + `node_evaluate` | Planner LLM prompts |
| **Phase 5 (Future)** | Tool selection classifier | Telemetry data |
| **Phase 6 (Future)** | Budget management + streaming | StateGraph enhancements |

---

## Testing Strategy (Planned)

```powershell
# Unit tests for each node (mocked LLM + tools)
python -m pytest tests/workflows/test_deep_research_nodes.py -v

# Integration test: simple query (1-2 iterations)
python -m pytest tests/workflows/test_deep_research_simple.py -v -m integration

# Integration test: complex query (5+ iterations)
python -m pytest tests/workflows/test_deep_research_complex.py -v -m integration

# Budget exhaustion test
python -m pytest tests/workflows/test_deep_research_budget.py -v
```

---

## Open Questions

1. **Tool selection:** Heuristic rules vs. learned classifier? Start with heuristics, add classifier after 100+ traces.
2. **Synthesis format:** Markdown vs. structured JSON? Start with markdown, add structured output for programmatic consumers.
3. **Evaluation scoring:** LLM-based vs. rule-based? LLM-based for flexibility, with guardrails to prevent inflation.
4. **Streaming:** Show partial results to user in real-time? Yes, via WebSocket/SSE from the gateway.
5. **Human-in-the-loop:** Pause loop for user clarification? Future enhancement, not v1.
