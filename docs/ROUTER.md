# 🧭 Task Router Architecture & Classification

The Task Router (`core/router.py`) is the ultra-fast classification layer that sits between the user's goal and the workflow execution engine. It uses the dedicated **Router role** (`cfg.router_model`) to classify intent, determine complexity, and select the correct workflow or direct tool, all within a strict 15-second timeout.

## 🏗️ Architecture Overview

### Design Goals

1. **Speed & Cost Efficiency**: Prevents the heavy Planner model from being loaded for simple, single-tool tasks (e.g., "read file X" or "git status").
2. **Graceful Degradation**: If the Router model is unavailable, times out, or returns unparseable JSON, the system instantly falls back to a deterministic heuristic keyword engine.
3. **Prompt Injection Mitigation**: Uses explicit `<tool_call>` XML envelopes and a deterministic bracket-counting JSON parser to prevent LLM hallucinations and markdown injection attacks.
4. **Zero Hardcoding**: All model references use the `cfg.router_model` abstraction.

### Component Hierarchy

```
TaskRouter (singleton)
├── RoutingDecision (Dataclass)
│   ├── workflow: str (research, data, autocode, direct)
│   ├── tool: str (web, file, git, memory, etc.)
│   ├── complexity: int (1-10)
│   └── confidence: str (high, medium, low)
├── Model-Based Routing (Primary)
│   ├── LLM Call (Router role, 15s timeout)
│   ├── Envelope Extraction (<tool_call> tags)
│   └── Deterministic JSON Parser (_extract_first_json)
├── Confidence Guard (Pre-Execution)
│   └── Intercepts low-confidence routes, returns clarifying questions
└── Heuristic Routing (Fallback)
    ├── Direct Tool Keywords (file, git, memory, notify, report)
    ├── Workflow Keywords (code, data, research)
    └── Default Fallback (research)
```

---

## 🧠 The Routing Decision

Every routing attempt returns a `RoutingDecision` object. This standardized output is consumed by the `workflow` tool and the gateway to dispatch the task.

```python
class RoutingDecision:
    workflow:   str        # "research", "data", "autocode", or "direct"
    tool:       str        # The specific tool to use (e.g., "file", "git", "workflow")
    complexity: int        # 1-10 scale
    reason:     str        # Human/LLM-readable explanation
    confidence: str        # "high", "medium", "low"
    clarifying_questions: list[str]  # Questions to ask user when confidence is low
```

### Workflow vs. Direct Routing

- **Workflow Routing** (`workflow="research|data|autocode"`): The task requires a multi-step LangGraph state machine. The `tool` field is usually set to `"workflow"`.
- **Direct Routing** (`workflow="direct"`): The task is a simple, single-step action. The Router bypasses the workflow engine and tells the agent to call the specific `tool` (e.g., `"file"`, `"git"`, `"memory"`) directly.

---

## 🛡️ The Confidence Guard (Pre-Execution Interception)

To prevent the agent from wasting 15+ minutes and massive VRAM on misunderstood tasks, the `workflow` tool intercepts `low` confidence routing decisions **before** launching any workflow.

### How It Works

When the Router model outputs `confidence: "low"`, it is required to also output 1-2 `clarifying_questions`. The workflow tool (`tools/workflow_tool.py`) catches this and aborts execution, returning a structured clarification request to the LLM:

```json
{
  "status": "needs_clarification",
  "reason": "The task goal is too vague or ambiguous to proceed confidently.",
  "clarifying_questions": [
    "Which specific file needs fixing?",
    "What is the exact error message?"
  ],
  "message": "To help me understand your request better, please clarify:\n- Which specific file needs fixing?\n- What is the exact error message?",
  "trace_id": "abc123"
}
```

### Confidence Thresholds

| Confidence | Meaning | System Behavior |
|---|---|---|
| **`high`** | Clear task with specific details. | Proceed immediately to workflow execution. |
| **`medium`** | Understandable but could be more specific. | Proceed, but rely on workflow nodes to ask clarifying questions if needed. |
| **`low`** | Vague, ambiguous, or missing critical context. | **ABORT.** Trigger the Confidence Guard. |

### Why This Matters

Without the Confidence Guard, a vague request like *"Fix the bug"* would:
1. Route to `autocode` workflow
2. Take a git snapshot
3. Load the Planner model (9B parameters, ~6GB VRAM)
4. Spend 5+ minutes brainstorming and planning
5. Eventually fail because it doesn't know which file to fix

With the Confidence Guard, the same request:
1. Routes with `confidence: "low"` and `clarifying_questions`
2. Returns instantly to the LLM
3. The LLM asks the user for clarification
4. Only then does the workflow launch with a precise goal

This saves massive amounts of VRAM, compute, and user time.

---

## 🔄 Two-Tier Routing Strategy

### Tier 1: Model-Based Routing (Primary)

The Router attempts to classify the task using the lightweight Router LLM. 

**The Prompt Structure:**
The model is instructed to output **ONLY** a JSON object wrapped in `<tool_call>` tags. No thinking, no explanations.

```xml
<tool_call>
{"workflow": "autocode", "tool": "workflow", "complexity": 7, "reason": "Involves editing an existing code file", "confidence": "high", "clarifying_questions": []}
</tool_call>
```

**Extraction Pipeline:**
1. **Envelope Match**: Regex searches for `<tool_call>...</tool_call>`. This mitigates prompt injection (Consensus Item 4) by ignoring text outside the envelope.
2. **Markdown Stripping**: If no envelope is found, strips ` ```json ` fences.
3. **Deterministic JSON Parser**: Passes the text to `_extract_first_json()`.

### Tier 2: Heuristic Routing (Fallback)

If the LLM call fails, times out, or returns invalid JSON, the `_heuristic_route()` method instantly classifies the goal using keyword matching.

**Direct Tool Keywords (Fast Path):**
- `_DIRECT_FILE`: "read file", "open file", "list directory" → `workflow="direct", tool="file"`
- `_DIRECT_MEMORY`: "recall", "remember", "store this" → `workflow="direct", tool="memory"`
- `_DIRECT_GIT`: "git status", "show commits" → `workflow="direct", tool="git"`
- `_DIRECT_NOTIFY`: "notify me", "remind me" → `workflow="direct", tool="notify"`
- `_REPORT_KEYWORDS`: "create a chart", "plot", "dashboard" → `workflow="direct", tool="report"`

**Workflow Keywords:**
- `_CODE_KEYWORDS`: "fix", "bug", "refactor", "implement" → `workflow="autocode"`
- `_DATA_KEYWORDS`: "analyze", "pandas", "csv", "plot" → `workflow="data"`
- `_RESEARCH_KEYWORDS`: "what is", "explain", "research" → `workflow="research"`

---

## 🛡️ Deterministic JSON Extraction (`_extract_first_json`)

Standard regex (`\{.*\}`) fails on nested JSON, escaped quotes inside strings, or trailing markdown text. The Router implements a custom state-machine parser that guarantees safe extraction.

### How It Works

```python
def _extract_first_json(self, text: str) -> str | None:
    decoder = json.JSONDecoder()
    in_string = False
    escape = False
    depth = 0
    start = None

    for i, ch in enumerate(text):
        if escape: escape = False; continue
        if ch == '\\':
            if in_string: escape = True
            continue
        if ch == '"': in_string = not in_string; continue
        if in_string: continue

        if ch == '{':
            if depth == 0: start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                candidate = text[start:i + 1]
                try:
                    decoder.decode(candidate)
                    return candidate
                except json.JSONDecodeError:
                    start = None
    return None
```

### Key Properties
- **String Awareness**: Ignores `{` and `}` characters that appear inside JSON string values.
- **Escape Handling**: Correctly handles `\"` so it doesn't prematurely close the string state.
- **Validation**: Uses `json.JSONDecoder` to verify the extracted slice is valid JSON before returning it.
- **Resilience**: If it hits a malformed JSON block, it resets and keeps looking for the next valid block.

---

## 📊 Complexity Classification

The Router can independently score task complexity on a 1-10 scale. This is used by workflows to adjust timeout limits, retry counts, and context window sizes.

```python
complexity = router.classify_complexity("Research ChromaDB")
# Returns: 4
```

**The Scale:**
- **1-3**: Single tool, clear input/output (e.g., "read file X").
- **4-6**: Multi-step, predictable (e.g., "summarize this URL").
- **7-9**: Complex, multiple tools, uncertainty (e.g., "fix the authentication bug").
- **10**: Requires human judgment or massive architectural refactoring.

---

## 📡 API Reference

### `route(goal: str, trace_id: str = "") -> RoutingDecision`

The primary entry point. Tries model-based routing, falls back to heuristics.

```python
from core.router import router

decision = router.route("Fix the timeout bug in tools/web.py", trace_id="abc123")

print(decision.workflow)    # "autocode"
print(decision.tool)        # "workflow"
print(decision.complexity)  # 7
print(decision.confidence)  # "high"
```

### `classify_complexity(goal: str) -> int`

Quick complexity score (1-10). Uses the Router role. Falls back to `5` on failure.

```python
score = router.classify_complexity("Calculate the mean of column A in data.csv")
# Returns: 5
```

---

## ⚙️ Configuration (`.env`)

```ini
# ── Router Role ────────────────────────────────────────────────────────────
ROUTER_MODEL=<your-router-model-id>  # Must be a fast, small model
ROUTER_TIMEOUT=15                    # Hard timeout for classification
```

**Why a 15s timeout?** 
The Router must never block the user experience. If the model takes longer than 15 seconds to classify a task, the system assumes it's hung and immediately falls back to the heuristic engine.

---

## ⚠️ AI Agent Instructions for Modifying the Router

If you are an AI assistant modifying `core/router.py` or `tools/workflow_tool.py`:

1. **Never Remove the Confidence Guard:** The `low` confidence interception in `tools/workflow_tool.py` prevents massive VRAM waste on misunderstood tasks. Never bypass it.
2. **Never Remove the Fallback:** The heuristic fallback is critical for system resilience. If LM Studio is offline, the agent must still be able to route basic tasks via keywords.
2. **Preserve the Envelope Parsing**: The `<tool_call>` regex is a security feature (Consensus Item 4) to prevent prompt injection. Do not remove it.
3. **Do Not Simplify the JSON Parser**: Do not replace `_extract_first_json` with a simple `re.search(r'\{.*\}')`. The state-machine parser is required to handle nested objects and escaped quotes safely.
4. **Keep it Fast**: Do not add heavy computations, file I/O, or secondary LLM calls to the routing path. This must remain ultra-lightweight.
5. **Update Keyword Lists Carefully**: When adding to `_CODE_KEYWORDS` or `_DIRECT_FILE`, ensure there is no overlap that would cause a direct tool request to be misrouted to a heavy workflow.
6. **No Hardcoded Models**: Always use `role="router"` in `llm.complete()`. Never hardcode model identifiers.
7. **Trace Integration**: All routing decisions must be logged via `tracer.step()` using the provided `trace_id`.

---

## 🔮 Future Enhancements (Planned)

- **Dynamic Workflow Composition:** Allow the Router to chain multiple workflows (e.g., `research` → `data`) based on complex goals.
- **Few-Shot Prompting:** Inject 2-3 examples of past routing decisions into the Router prompt to improve classification accuracy.
- **✅ Confidence Guard (COMPLETED):** The Router now automatically asks the user for clarification when `confidence == "low"`, preventing wasted VRAM on misunderstood tasks.
- **Adaptive Complexity Thresholds:** Dynamically adjust the confidence threshold based on task complexity (e.g., require `high` confidence for `complexity > 7`).