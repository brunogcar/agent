<- Back to [Workflow Overview](../WORKFLOW.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
def workflow(
    type: str,
    goal: str,
    # data workflow
    code: str = "",
    # autocode workflow
    target_file: str = "",
    mode: str = "improve",
    error_msg: str = "",
    feature_desc: str = "",
    # understand workflow
    project_root: str = "",
    trace_id: str = "",
    resume: bool = False,
) -> dict:
    """Launch a multi-step autonomous workflow.

    Workflows:
    - research: Gather info from web, synthesize findings.
    - data: Analyse datasets with pandas/numpy, generate reports.
    - autocode: Fix bugs, add features, refactor code (TDD + safety).
    - deep_research: Iterative multi-faceted research with ReAct loop.
    - understand: Build codebase Knowledge Graph.
    - auto: Let the Router classify the task and choose the workflow.
    """
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `type` | `str` | **Yes** | — | Workflow type. Valid: `research`, `data`, `autocode`, `deep_research`, `understand`, `auto`. Empty defaults to `auto`. |
| `goal` | `str` | **Yes** | — | Human-readable task description |
| `code` | `str` | No | `""` | Python code for `data` workflow (e.g., pandas analysis) |
| `target_file` | `str` | No | `""` | File path for `autocode` workflow. **Required** when `type="autocode"`. |
| `mode` | `str` | No | `"improve"` | Autocode mode: `improve`, `fix_error`, `add_feature`, `refactor` |
| `error_msg` | `str` | No | `""` | Error message for `autocode` mode `fix_error`. **Required** when `mode="fix_error"`. |
| `feature_desc` | `str` | No | `""` | Feature description for `autocode` mode `add_feature`. **Required** when `mode="add_feature"`. |
| `project_root` | `str` | No | `""` | Project directory for `understand` workflow. **Required** when `type="understand"`. |
| `trace_id` | `str` | No | `""` | Trace identifier. Auto-generated if not provided. |
| `resume` | `bool` | No | `False` | Continue interrupted workflow from checkpoint |

**WorkflowType Literal:** `Literal["research", "data", "autocode", "deep_research", "understand", "auto"]`

---

## ⚡ Workflow Types

### `research`

Gathers information from web sources, synthesizes findings, and generates cited reports.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal` | `trace_id`, `resume` | Research topic or question |

### `data`

Analyses datasets with pandas/numpy, generates charts, and produces data reports.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal` | `code`, `trace_id`, `resume` | Analysis goal. `code` provides initial Python code. |

### `autocode`

Fixes bugs, adds features, or refactors code with TDD and safety checks (git snapshots).

| Required | Optional | Description |
|----------|----------|-------------|
| `goal`, `target_file` | `mode`, `error_msg`, `feature_desc`, `trace_id`, `resume` | `mode` controls behaviour. `error_msg` required for `fix_error`. `feature_desc` required for `add_feature`. |

### `deep_research`

Iterative, multi-faceted research for complex questions. Uses a ReAct-style loop with self-evaluation, budget tracking, and convergence detection.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal` | `trace_id`, `resume` | Research question. The workflow decomposes, searches, and synthesizes iteratively until convergence or max iterations. |

### `understand`

Builds a codebase Knowledge Graph for dependency analysis and navigation.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal`, `project_root` | `trace_id`, `resume` | `project_root` is the directory to scan |

### `auto`

Lets the Router classify the goal and dynamically select the correct workflow.

| Required | Optional | Description |
|----------|----------|-------------|
| `goal` | `trace_id`, `resume` | The Router decides which workflow to run |

**Auto-routing outcomes:**

| Outcome | Status | Description |
|---------|--------|-------------|
| `direct` | `routed` | Router decides this is not a workflow task. Returns `tool` and `reason` for the LLM to use. |
| `low` confidence | `needs_clarification` | Goal is too vague. Returns `clarifying_questions` for the user. |
| `success` | `success` | Router selected a workflow. Execution proceeds with that type. |

---

## 📤 Output

### Success
```json
{
  "status": "success",
  "result": "...",
  "trace_id": "abc123"
}
```

### Auto-routing — Direct
```json
{
  "status": "routed",
  "workflow": "direct",
  "tool": "web",
  "reason": "This is a simple factual query best handled by web search.",
  "trace_id": "abc123"
}
```

### Auto-routing — Needs Clarification
```json
{
  "status": "needs_clarification",
  "reason": "The task goal is too vague or ambiguous to proceed confidently.",
  "clarifying_questions": [
    "What programming language is the project using?",
    "Which specific module should I focus on?"
  ],
  "message": "To help me understand your request better, please clarify:\n- What programming language is the project using?\n- Which specific module should I focus on?",
  "trace_id": "abc123"
}
```

### Validation Error
```json
{
  "status": "error",
  "error": "Invalid workflow type 'coding'. Valid types: ['auto', 'autocode', 'data', 'deep_research', 'research', 'understand']",
  "trace_id": "abc123",
  "valid_types": ["auto", "autocode", "data", "deep_research", "research", "understand"]
}
```

### Execution Error
```json
{
  "status": "error",
  "error": "Workflow execution failed: <exception>",
  "trace_id": "abc123",
  "workflow_type": "autocode"
}
```

---

## 🔒 Security

| Feature | Implementation |
|---------|---------------|
| **Type allowlist** | `VALID_WORKFLOWS` frozenset prevents LLM hallucination of non-existent types |
| **Parameter guards** | Autocode validates `target_file`, `error_msg`, `feature_desc` before any filesystem mutation |
| **Trace ID guarantee** | Every response contains `trace_id`. Auto-generated if not provided by MCP host |
| **Router confidence guard** | Low-confidence auto-routing aborts with clarifying questions instead of wasting execution time |
| **Lazy imports** | `core.router` imported inside `auto` branch to prevent startup circular dependencies |

---

*Last updated: 2026-07-05. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
