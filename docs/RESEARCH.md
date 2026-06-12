# RESEARCH

## Overview

The `research` workflow is the agent's end-to-end research pipeline. It takes a user query, discovers information via web search, extracts and summarizes content, generates a structured report, stores findings in memory, and notifies the user.

**Key characteristics:**
- **LangGraph StateGraph** — 8 nodes with conditional edges, fully checkpointed
- **Parallel extraction** — `ThreadPoolExecutor` scrapes multiple URLs concurrently
- **LLM synthesis** — Every scraped page gets an LLM summarization
- **Citation tracking** — All sources tracked via `core.citations`
- **Memory integration** — Results stored in episodic, semantic, and procedural memory

---

## Architecture

```
workflows/research.py
├── build_research_graph()         # StateGraph builder
├── WorkflowState (TypedDict)      # State schema
│   ├── goal, trace_id, query
│   ├── search_results, urls_data
│   ├── summaries, citations
│   ├── report_html, report_path
│   └── status, error
│
├── Nodes (in execution order):
│   ├── node_recall              # Memory recall: episodic + semantic
│   ├── node_search              # SearXNG search via web(action="search")
│   ├── node_parallel_scrape     # ThreadPoolExecutor + web(action="read") + LLM summarize
│   ├── node_synthesize          # Aggregate summaries into coherent report
│   ├── node_report              # Generate HTML report via report tool
│   ├── node_store               # Store findings in ChromaDB memory
│   ├── node_distill             # Procedural memory extraction
│   └── node_notify              # Send notification via notify tool
│
└── Conditional edges:
    ├── router_after_search → parallel_scrape | error
    ├── router_after_scrape → synthesize | error
    └── router_after_synthesize → report | error
```

---

## Workflow State

```python
class WorkflowState(TypedDict, total=False):
    goal: str               # Original user query
    trace_id: str           # Trace identifier
    query: str              # Refined search query
    search_results: list    # Raw SearXNG results
    urls_data: list         # URLs selected for scraping
    summaries: list         # LLM summaries per page
    citations: list         # Tracked citations
    report_html: str        # Generated HTML report
    report_path: str        # Path to saved report
    status: str             # "pending" | "running" | "complete" | "error"
    error: str              # Error message if failed
```

---

## Node Details

### `node_recall` — Memory Recall

Queries ChromaDB memory collections before searching:
- **Episodic:** "Have I researched this topic before?"
- **Semantic:** "What do I know about this topic?"
- **Procedural:** "What workflow patterns worked for similar queries?"

Results injected into `WorkflowState` as context for downstream nodes.

### `node_search` — URL Discovery

Calls `web(action="search", query=...)` to get ranked URLs from SearXNG.

**Config:**
```
WEB_MAX_SEARCH_RESULTS=10
WEB_SNIPPET_CHARS=300
```

**Output:** `urls_data` — list of `{url, title, snippet}` dicts.

### `node_parallel_scrape` — Concurrent Extraction

Uses `ThreadPoolExecutor(max_workers=cfg.max_concurrent_workers)` to process each URL:

```python
def _scrape_and_summarize(url, trace_id, goal):
    result = web(action="read", url=url, trace_id=trace_id)
    if result["status"] != "success":
        return {"url": url, "error": result.get("error")}
    text = result["data"]["text"]
    summary = llm.complete(
        role="executor",
        system="Summarize this page in context of the user's goal.",
        user=f"Goal: {goal}\n\nPage text:\n{text[:4000]}"
    )
    return {"url": url, "summary": summary, "text": text}
```

**Current limitation:** If `web(read)` returns empty/short text (< 300 chars), the page is likely JS-rendered. **Future:** Add browser fallback here.

### `node_synthesize` — Report Generation

Aggregates all summaries into a coherent markdown report using the planner LLM.

**Prompt structure:**
```
System: You are a research analyst. Synthesize the following findings into a structured report.
User: [Goal] + [Summaries] + [Citations]
```

### `node_report` — HTML Export

Calls `report(action="html", data=synthesized_text)` to generate a self-contained HTML dashboard.

**Output:** Saved to `workspace/reports/{trace_id}.html`.

### `node_store` — Memory Persistence

Stores findings in ChromaDB:
- **Episodic:** "Researched [topic] on [date], found [key findings]"
- **Semantic:** Key facts as embeddings
- **Citations:** Source URLs with relevance scores

### `node_distill` — Procedural Learning

Extracts reusable workflow patterns:
- "For technical topics, prefer official documentation over blogs"
- "For recent events, prioritize news sources < 7 days old"

### `node_notify` — User Notification

Calls `notify(action="send", message=...)` to alert the user that research is complete.

---

## Configuration

```ini
# .env
SEARXNG_URL=http://localhost:8080
WEB_MAX_SEARCH_RESULTS=10
WEB_MAX_TEXT_CHARS=8000
WEB_SNIPPET_CHARS=300
MAX_CONCURRENT_WORKERS=3
```

```python
# core/config.py
self.web_max_text_chars = int(os.getenv("WEB_MAX_TEXT_CHARS", "8000"))
self.web_max_search_results = int(os.getenv("WEB_MAX_SEARCH_RESULTS", "10"))
self.web_snippet_chars = int(os.getenv("WEB_SNIPPET_CHARS", "300"))
self.max_concurrent_workers = int(os.getenv("MAX_CONCURRENT_WORKERS", "3"))
```

---

## Citation Tracking

Every scraped page is tracked via `core.citations`:

```python
{
    "url": "https://example.com",
    "title": "Page Title",
    "accessed_at": "2026-06-12T10:00:00",
    "summary": "LLM summary...",
    "relevance_score": 0.92
}
```

Citations are:
- Included in the final HTML report
- Stored in semantic memory for future recall
- Deduplicated by URL

---

## Error Handling

| Failure Point | Behavior |
|---------------|----------|
| SearXNG down | `web` returns error → router routes to error node |
| URL scrape fails | Worker returns error dict → included in synthesis with warning |
| LLM summarization fails | Fallback to raw text truncation |
| Report generation fails | Return markdown instead of HTML |
| Memory storage fails | Log warning, continue workflow |

---

## Testing

```powershell
# Run research workflow tests
python -m pytest tests/workflows/test_research.py -v

# Run with mocked LLM calls
python -m pytest tests/workflows/test_research.py -v -k "not integration"
```

---

## When to Use vs DeepResearch

| Need | Workflow | Why |
|------|----------|-----|
| Quick fact-check | `research` | Single search + synthesis, 1-2 minutes |
| Comprehensive report | `research` | Parallel scrape + full synthesis |
| Multi-step investigation | `deep_research` (future) | Iterative ReAct loop with evaluation |
| Academic research | `deep_research` (future) | Structured decomposition + evidence tracking |
| Real-time monitoring | `research` + cron | Scheduled execution with delta reporting |

---

## Future Roadmap

- **Phase 1 (Current):** 8-node linear pipeline with parallel scrape
- **Phase 2 (Next):** Add browser fallback in `node_parallel_scrape` for JS-heavy sites
- **Phase 3 (Next):** Integrate `tavily(search)` as alternative to `web(search)`
- **Phase 4 (Future):** Replace with `deep_research` workflow for complex queries
- **Phase 5 (Future):** Add streaming partial results (show findings as they arrive)
