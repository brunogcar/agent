# 🧭 Task Router

The Task Router (`core/router.py`) is the **ultra-fast classification layer** that sits between the user's goal and the workflow execution engine. It uses the dedicated Router role (`cfg.router_model`) to classify intent, determine complexity, and select the correct workflow or direct tool, all within a strict 15-second timeout.

**Key characteristics:**
- **Speed-first** — 15s hard timeout, falls back to heuristics if model is slow or unavailable
- **Dual-mode routing** — Model-based (primary) + keyword heuristics (fallback)
- **Confidence-aware** — Low-confidence decisions include clarifying questions to prevent wasted VRAM
- **Robust JSON extraction** — 3-layer pipeline handles markdown fences, nested objects, and escaped quotes
- **Zero hardcoding** — All model references use `cfg.router_model`

---

## 🏗️ Architecture

### Component Map

```
core/router.py
├── RoutingDecision          # Dataclass: workflow, tool, complexity, reason, confidence
├── TaskRouter (singleton)
│   ├── route()              # Primary entry point — model → heuristic fallback
│   ├── classify_complexity() # Quick 1-10 complexity score
│   ├── _model_route()       # LLM-based classification (Router role, 15s timeout)
│   ├── _heuristic_route()   # Keyword-based fallback (pre-compiled regex)
│   └── _extract_first_json() # Deterministic JSON extraction (3-layer)
└── router                   # Module-level singleton
```

### Routing Flow

```mermaid
graph TD
    A["User goal<br/>e.g., 'Fix the timeout bug in web.py'"] --> B["router.route(goal)"]
    B --> C{Goal<br/>empty?}
    C -->|Yes| D["Return default<br/>workflow=research, complexity=1<br/>+ clarifying questions"]
    C -->|No| E["Tier 1: Model-Based<br/>_model_route()"]
    E --> F{LLM call<br/>succeeds?}
    F -->|Yes| G["Parse JSON<br/>_extract_first_json()"]
    G --> H{Valid<br/>RoutingDecision?}
    H -->|Yes| I["Return decision<br/>tracer.log('routed via model')"]
    H -->|No| J["Tier 2: Heuristic<br/>_heuristic_route()"]
    F -->|Timeout / Error| J
    J --> K["Return decision<br/>tracer.log('routed via heuristic')"]
```

### Design Goals

| Goal | How |
|------|-----|
| **Speed** | 15s hard timeout on LLM call; heuristic fallback is O(1) regex |
| **Cost efficiency** | Prevents heavy Planner model from loading for simple tasks |
| **Graceful degradation** | Works even when LM Studio is completely offline |
| **VRAM protection** | Confidence Guard aborts vague tasks before launching expensive workflows |
| **Robustness** | 3-layer JSON extraction handles messy LLM output |

---

## 🧠 The Routing Decision

Every routing attempt returns a `RoutingDecision` object. This standardized output is consumed by the workflow tool, the dispatcher, and the gateway.

### Dataclass

```python
class RoutingDecision:
    workflow:   str        # "research", "data", "autocode", or "direct"
    tool:       str        # "web", "file", "git", "memory", "workflow", etc.
    complexity: int        # 1-10 scale
    reason:     str        # Human/LLM-readable explanation
    confidence: str        # "high", "medium", "low"
    clarifying_questions: list[str]  # Questions for low-confidence routes
    raw:        dict       # Original raw dict from LLM or heuristic
```

### Routing Targets

```mermaid
graph LR
    subgraph "Multi-Step Workflows"
        A["workflow='research'"]
        B["workflow='data'"]
        C["workflow='autocode'"]
    end
    subgraph "Direct Tool Execution"
        D["workflow='direct'<br/>tool='file'"]
        E["workflow='direct'<br/>tool='memory'"]
        F["workflow='direct'<br/>tool='git'"]
        G["workflow='direct'<br/>tool='notify'"]
        H["workflow='direct'<br/>tool='report'"]
    end
```

| Routing Type | `workflow` | `tool` | When |
|-------------|-----------|--------|------|
| **Multi-step workflow** | `"research"` | `"workflow"` | Finding info, summarizing, reading docs, Q&A |
| **Multi-step workflow** | `"data"` | `"workflow"` | Pandas, analysis, calculations, charts, spreadsheets |
| **Multi-step workflow** | `"autocode"` | `"workflow"` | Fixing bugs, editing code, adding features |
| **Direct tool** | `"direct"` | `"file"` | Read file, open file, list directory |
| **Direct tool** | `"direct"` | `"memory"` | Recall, remember, store to memory |
| **Direct tool** | `"direct"` | `"git"` | Git status, show commits, git diff |
| **Direct tool** | `"direct"` | `"notify"` | Notify me, remind me |
| **Direct tool** | `"direct"` | `"report"` | Create chart, plot, dashboard |

### Workflow vs. Direct Routing

- **Workflow Routing** (`workflow="research|data|autocode"`): The task requires a multi-step LangGraph state machine. The Planner generates a plan, the Executor runs each step.
- **Direct Routing** (`workflow="direct"`): The task is a simple, single-step action. The router bypasses the workflow engine and tells the dispatcher to call the specific tool directly.

---

## 🛡️ Confidence Guard (Pre-Execution Interception)

To prevent the agent from wasting 15+ minutes and massive VRAM on misunderstood tasks, the workflow tool intercepts `low` confidence routing decisions **before** launching any workflow.

### How It Works

```mermaid
graph TD
    A["RoutingDecision<br/>confidence='low'"] --> B["workflow_tool.py<br/>Intercepts before execution"]
    B --> C["Return structured<br/>needs_clarification payload"]
    C --> D["LLM asks user<br/>clarifying questions"]
    D --> E{"User<br/>clarifies?"}
    E -->|Yes| F["Re-route with<br/>precise goal"]
    E -->|No| G["Abort"]
```

### Confidence Thresholds

| Confidence | Meaning | System Behavior |
|------------|---------|-----------------|
| **`high`** | Clear task with specific details | Proceed immediately to workflow execution |
| **`medium`** | Understandable but could be more specific | Proceed; workflow nodes may ask clarifying questions if needed |
| **`low`** | Vague, ambiguous, or missing critical context | **ABORT.** Trigger Confidence Guard. Return clarifying questions. |

### Example: Low Confidence Response

```json
{
  "status": "needs_clarification",
  "reason": "The task goal is too vague to proceed confidently.",
  "clarifying_questions": [
    "Which specific file needs fixing?",
    "What is the exact error message?"
  ],
  "message": "To help me understand your request better, please clarify:\n- Which specific file needs fixing?\n- What is the exact error message?",
  "trace_id": "abc123"
}
```

### VRAM Savings

| Scenario | Without Guard | With Guard |
|----------|--------------|------------|
| "Fix the bug" | Load Planner (6GB VRAM) → 5min planning → fail (no file specified) | Instant response → user clarifies → precise execution |
| "Do something with data" | Load Planner → load pandas → crash (no data specified) | Instant response → user specifies file and operation |
| "Help me" | Load everything → generic unhelpful response | Instant response → asks what specifically |

---

## 🔄 Two-Tier Routing Strategy

### Tier 1: Model-Based Routing (Primary)

The Router attempts to classify the task using the lightweight Router LLM.

**The Prompt:**

```
No thinking. No explanation.
{"workflow": "research or data or autocode",
 "tool": "web or python or file or git or memory or agent or notify or report or workflow",
 "complexity": 5,
 "reason": "one sentence",
 "confidence": "high or medium or low",
 "clarifying_questions": ["question1", "question2"]}

Routing rules:
- research: finding info, summarising, reading docs, Q&A
- data: pandas, analysis, calculations, charts, spreadsheets
- autocode: fixing bugs, editing code files, adding features
- direct: single-tool task (use tool field, not workflow)

Confidence rules:
- high: Clear task with specific details
- medium: Understandable but could be more specific
- low: Vague or ambiguous. MUST provide 1-2 clarifying questions.
```

**Key design decisions:**
- `"No thinking. No explanation."` — Suppresses thinking tokens for models like Qwen3 or Gemma that support them. Keeps the router fast.
- Structured JSON schema — Tells the model exactly what fields to output.
- Routing rules embedded in prompt — Gives the model clear decision boundaries.
- Confidence rules with `MUST` — Forces the model to include clarifying questions on low confidence.

**Extraction Pipeline:**

```mermaid
graph TD
    A["Raw LLM Response"] --> B["Strip markdown fences<br/>```json ... ```"]
    B --> C["Try direct parse<br/>json.loads(text)"]
    C -->|Success| D["Return RoutingDecision"]
    C -->|Fail| E["Layer 3: raw_decode<br/>json.JSONDecoder().raw_decode()"]
    E -->|Find first { }| F["Parse extracted JSON"]
    F -->|Valid + has 'workflow'| D
    F -->|Invalid| G["Return None<br/>Fall back to heuristics"]
    E -->|No { } found| G
```

### Tier 2: Heuristic Routing (Fallback)

If the LLM call fails, times out, or returns invalid JSON, the `_heuristic_route()` method instantly classifies the goal using **pre-compiled regex patterns**.

**Priority Order (most specific first):**

```mermaid
graph TD
    A["Goal text"] --> B{"Report?<br/>chart, plot, dashboard"}
    B -->|Yes| R1["workflow='direct'<br/>tool='report'<br/>complexity=3"]
    B -->|No| C{"File op?<br/>read file, open file, list dir"}
    C -->|Yes| R2["workflow='direct'<br/>tool='file'<br/>complexity=2"]
    C -->|No| D{"Memory op?<br/>recall, remember, store this"}
    D -->|Yes| R3["workflow='direct'<br/>tool='memory'<br/>complexity=1"]
    D -->|No| E{"Git op?<br/>git status, show commits"}
    E -->|Yes| R4["workflow='direct'<br/>tool='git'<br/>complexity=2"]
    E -->|No| F{"Notify?<br/>notify me, remind me"}
    F -->|Yes| R5["workflow='direct'<br/>tool='notify'<br/>complexity=1"]
    F -->|No| G{"Code?<br/>fix, bug, refactor, implement"}
    G -->|Yes| R6["workflow='autocode'<br/>complexity=5 or 7"]
    G -->|No| H{"Data?<br/>analyze, pandas, csv, plot"}
    H -->|Yes| R7["workflow='data'<br/>complexity=5"]
    H -->|No| I["Default<br/>workflow='research'<br/>complexity=4"]
```

### Regex Patterns (Pre-compiled)

| Pattern | Regex | Routes To |
|---------|-------|-----------|
| `_RE_REPORT` | `\b(create a chart\|create chart\|make a chart\|plot a chart\|draw a chart\|report\|visualise\|create a graph\|make a graph\|create a map\|make a map\|create a dashboard\|make a dashboard\|create a report\|make a report\|bar chart\|line chart\|pie chart\|scatter plot\|heatmap)\b` | `direct → report` |
| `_RE_DIRECT_FILE` | `\b(read file\|open file\|list files\|list directory\|write file\|show file\|read the file\|open the file)\b` | `direct → file` |
| `_RE_DIRECT_MEMORY` | `\b(recall\|remember\|what do you know about\|store this\|save this to memory)\b` | `direct → memory` |
| `_RE_DIRECT_GIT` | `\b(git status\|git log\|show commits\|git diff\|commit this\|git commit)\b` | `direct → git` |
| `_RE_DIRECT_NOTIFY` | `\b(notify me\|send notification\|remind me\|schedule reminder)\b` | `direct → notify` |
| `_RE_CODE` | `\b(fix\|bug\|error\|patch\|refactor\|improve\|add feature\|implement\|edit\|modify\|update code)\b` | `autocode` |
| `_RE_DATA` | `\b(analyse\|analyze\|calculate\|compute\|plot\|chart\|csv\|excel\|spreadsheet\|statistics\|pandas\|numpy\|dataset)\b` | `data` |
| `_RE_RESEARCH` | `\b(what is\|what are\|how does\|explain\|research\|find information\|summarise\|summarize\|look up)\b` | `research` |

> ⚠️ **All patterns are case-insensitive** (`re.IGNORECASE`).

### Code-File Bonus

When the `_RE_CODE` pattern matches, the heuristic checks if the goal also mentions a file extension (`.py`, `.js`, `.ts`, `.json`, `.yaml`, `.md`):

| Condition | Complexity | Reasoning |
|-----------|-----------|-----------|
| Code keywords + file extension mentioned | 7 | More likely a specific file edit |
| Code keywords only | 5 | Might be a general code question |

---

## 📊 Complexity Classification

The Router can independently score task complexity on a 1-10 scale. This is used by workflows to adjust timeout limits, retry counts, and context window sizes.

### The Scale

| Range | Meaning | Examples |
|-------|---------|---------|
| **1-3** | Single tool, clear input/output | "read file X", "git status", "remember this" |
| **4-6** | Multi-step, predictable | "summarize this URL", "analyze this CSV" |
| **7-9** | Complex, multiple tools, uncertainty | "fix the authentication bug", "refactor the memory module" |
| **10** | Requires human judgment | "redesign the entire architecture" |

### Usage

```python
from core.router import router

# Quick complexity score (uses Router LLM, 15s timeout)
score = router.classify_complexity("Research ChromaDB")
# Returns: 4

score = router.classify_complexity("Fix the authentication bug in tools/web.py and add unit tests")
# Returns: 8

# Falls back to 5 on LLM failure
score = router.classify_complexity("do stuff")
# Returns: 5 (default)
```

---

## 📡 API Reference

### `route()` — Primary Entry Point

```python
decision = router.route(
    goal="Fix the timeout bug in tools/web.py",
    trace_id="abc123",
)
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `goal` | `str` | — | **Required.** The user's free-text task description |
| `trace_id` | `str` | `""` | Trace identifier for logging |

**Returns:** `RoutingDecision`

```python
decision.workflow    # "autocode"
decision.tool        # "workflow"
decision.complexity  # 7
decision.reason      # "Involves editing an existing code file to fix a bug"
decision.confidence  # "high"
decision.clarifying_questions  # []
```

### `classify_complexity()` — Quick Complexity Score

```python
score = router.classify_complexity("Calculate the mean of column A in data.csv")
# Returns: 5
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `goal` | `str` | — | **Required.** The user's task description |

**Returns:** `int` (1-10). Falls back to `5` on LLM failure.

---

## ⚙️ Configuration

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `ROUTER_MODEL` | Falls back to planner | Fast, small model for classification |
| `ROUTER_TIMEOUT` | `15` | Hard timeout in seconds |

**Current configuration:**

```ini
ROUTER_MODEL=gemma-2-2b-it
ROUTER_TIMEOUT=15
```

**Why a 15s timeout?**
The Router must never block the user experience. If the model takes longer than 15 seconds to classify a task, the system assumes it's hung and immediately falls back to the heuristic engine. This is the tightest timeout in the system.

---

## 🔀 When to Use vs. Alternatives

| Scenario | Tool | Why |
|----------|------|-----|
| Classify a new task | `router.route(goal)` | Determines which workflow/tool to use |
| Score task complexity | `router.classify_complexity(goal)` | Used by workflows for timeout adjustment |
| Skip routing (known task) | Call workflow/tool directly | When you already know which tool to use |
| Gateway dispatch | `dispatcher.dispatch()` | Uses router internally for `workflow: "auto"` |

---

## 🧪 Testing

```powershell
# Run all router tests
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/test_router.py -v

# Test heuristic fallback (no LLM needed)
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/test_router.py -k "heuristic" -v

# Test JSON extraction edge cases
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/test_router.py -k "extract_json" -v
```

**Mock strategy:**
- Mock `llm.complete()` to return controlled JSON responses
- Test heuristic routing separately (no LLM dependency)
- Test JSON extraction with malformed inputs (markdown fences, nested objects, trailing text)

---

## ⚠️ Known Concerns

> **Note:** These are MiMo's observations from source code review. They are constructive suggestions, not definitive prescriptions.

### Router Tool List vs. Dispatcher vs. Actual Tools

**What exists:**
- The router's model prompt lists 9 tools: `web, python, file, git, memory, agent, notify, report, workflow`
- The gateway dispatcher handles 11 tools: `web, python, file, git, memory, agent, report, notify, cli, vision, workflow`
- The actual `tools/` directory contains 15+ tools: `web, python_exec, file, git, memory_tool, agent, report, notify, cli, vision, browser, tavily, consult, parallel, workflow_tool`

**The concern:**
The router never routes to `cli`, `vision`, `browser`, `tavily`, or `consult`. The dispatcher never dispatches to `browser`, `tavily`, `consult`, or `parallel`. This means:

1. **Invisible tools** — the Planner can invoke tools the router doesn't know about, but the router can never proactively select them.
2. **Dead tools** — `consult.py`, `tavily.py`, `browser.py`, and `parallel.py` exist in `tools/` but are unreachable from the gateway dispatcher.
3. **Implicit contracts** — the gap between router, dispatcher, and actual tools is undocumented.

**Suggestion:**
1. Add `browser`, `tavily`, `consult`, `cli`, `vision` to the router's model prompt with clear routing rules.
2. Add the missing tools to the dispatcher's if-chain.
3. Create a `TOOLS.md` that documents every tool, its routing rules, and its entry points.

### Heuristic Pattern Overlap

**What exists:**
The `_RE_REPORT` regex matches words like `chart`, `plot`, `report`, `dashboard`. The `_RE_DATA` regex also matches `plot` and `chart`. This means some goals could match both patterns.

**The concern:**
Since report is checked first in `_heuristic_route()`, goals like "plot a chart of this data" will route to `direct → report` instead of `data → python`. This may or may not be the desired behavior depending on whether the user wants a static report or a data analysis workflow.

**Suggestion:**
Either remove `plot` and `chart` from `_RE_DATA` (since report takes priority anyway), or add a disambiguation step when both patterns match.

### Router Doesn't Know About Browser

The `browser` tool exists for JavaScript-rendered pages, interactive forms, and screenshots. But the router has no keyword for it. A user saying "browse this website" or "open this page" will route to `research → web` instead of using the browser tool.

**Suggestion:**
Add a `_RE_DIRECT_BROWSER` pattern for keywords like "browse", "open page", "screenshot", "fill form", "click button".

---

## 🛡️ AI Agent Instructions

If you are an AI assistant modifying `core/router.py`:

1. **Never remove the Confidence Guard** — the `low` confidence interception in `tools/workflow_tool.py` prevents massive VRAM waste on misunderstood tasks.
2. **Never remove the heuristic fallback** — if LM Studio is offline, the agent must still route basic tasks via keywords.
3. **Do not simplify the JSON parser** — do not replace `_extract_first_json()` with `re.search(r'\{.*\}')`. The `raw_decode()` approach handles nested objects and escaped quotes safely.
4. **Keep it fast** — do not add heavy computations, file I/O, or secondary LLM calls to the routing path. This must remain ultra-lightweight.
5. **Update keyword lists carefully** — when adding to regex patterns, ensure there is no overlap that would cause a direct tool request to be misrouted to a heavy workflow.
6. **No hardcoded models** — always use `role="router"` in `llm.complete()`. Never hardcode model identifiers.
7. **Trace integration** — all routing decisions must be logged via `tracer.step()` with `trace_id`.
8. **Pre-compiled regex** — all new keyword patterns must be `re.compile()` at class level, not compiled on every call.
9. **Check priority order** — when adding new patterns, insert them in the correct priority position in `_heuristic_route()`. More specific patterns must come before more general ones.

---

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `core/router.py` | `TaskRouter`, `RoutingDecision`, model + heuristic routing, JSON extraction |
| `tools/workflow_tool.py` | Confidence Guard interception (low confidence → clarifying questions) |
| `core/llm.py` | LLM client used by `router.route()` and `router.classify_complexity()` |
| `core/tracer.py` | Trace logging for routing decisions |
| `core/config.py` | `router_model`, `router_timeout` configuration |
| `core/gateway_backend/dispatcher.py` | Consumes routing decisions for gateway dispatch |

---

## 🔮 Future Roadmap

| Status | Enhancement | Description |
|--------|-------------|-------------|
| ✅ Complete | Model-based routing | Router LLM with 15s timeout |
| ✅ Complete | Heuristic fallback | Pre-compiled regex, O(1) matching |
| ✅ Complete | Confidence Guard | Low-confidence interception + clarifying questions |
| ✅ Complete | Deterministic JSON extraction | 3-layer pipeline with raw_decode |
| 🚧 Planned | Browser routing | Add `_RE_DIRECT_BROWSER` for browse/screenshot/form keywords |
| 🚧 Planned | Tool registry sync | Auto-generate router prompt from tool metadata |
| 🚧 Planned | Dynamic workflow composition | Chain multiple workflows (e.g., research → data) |
| 🚧 Planned | Few-shot prompting | Inject 2-3 past routing examples into Router prompt |
| 🚧 Planned | Adaptive complexity thresholds | Require `high` confidence for complexity > 7 |

---

*Last updated: June 2026. All regex patterns, model names, and routing rules reflect current source code in `core/router.py`.*