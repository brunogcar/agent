# 🤖 Agent Tool

The `agent()` tool is the **meta-cognitive dispatcher** of the MCP Agent Stack. It routes tasks to specialist sub-agents (Router, Executor, Planner, Consultor, Vision) based on a `role` parameter, each with its own system prompt, model, timeout, and output format.

**Key characteristics:**
- **Single entry point** — The LLM sees one tool: `agent(role, task, ...)`
- **Role-specialized prompts** — 12 distinct personas, each with tailored instructions
- **Per-role model routing** — Router uses fast 2B models, Executor uses capable 9B models
- **Structured output enforcement** — JSON mode for `extract`, prompt-only JSON for `route`, `plan`, `code`, `review`
- **Context trimming** — Head+tail truncation with traceback preservation before reaching the LLM
- **Vision delegation** — `vision` role delegates to `tools/vision.py` for multimodal analysis
- **NOT_PARALLEL_SAFE** — Serialized via global LLM client queue; no concurrent agent calls

---

## 🏗️ Architecture

The agent tool follows a **thin facade + core submodule** pattern. `tools/agent.py` is the only file scanned by `registry.py` for `@tool` discovery; all logic lives in `tools/agent_core/`.

```
tools/agent.py              # @tool facade — role validation, LLM dispatch, JSON parsing
tools/agent_core/
├── __init__.py             # Package marker
├── prompts.py              # _SYSTEM_PROMPTS — 12 role-specific system prompts
├── roles.py                # _ROLE_TO_LLM, _API_JSON_ROLES, _PROMPT_JSON_ROLES, _JSON_ROLES
└── context.py              # _trim_context(), _max_context_chars() — head+tail truncation
```

### Dispatch Flow

```mermaid
graph TD
    A["agent(role, task, context, content)"] --> B{role == "vision"?}
    B -->|Yes| C["Delegate to tools.vision.vision()"]
    B -->|No| D{role in _ROLE_TO_LLM?}
    D -->|No| E["Return: Unknown role error"]
    D -->|Yes| F["Lookup system prompt + LLM role"]
    F --> G["_trim_context(context) + _trim_context(content)"]
    G --> H["llm.complete(role, system, user, context, content, json_mode)"]
    H --> I{result.ok?}
    I -->|No| J["Return: error dict with elapsed, model"]
    I -->|Yes| K{role in _JSON_ROLES?}
    K -->|Yes| L["Parse JSON: API parsed or regex extraction"]
    K -->|No| M["Return: text response"]
    L --> N["Return: response with parsed dict"]
```

**Key design decisions:**
- **Thin facade** — `agent.py` only validates, looks up config, calls `llm.complete()`, and parses JSON. No business logic.
- **Prompts in dedicated module** — `prompts.py` holds all 12 system prompts. Easy to extend: add a role → add a prompt → add to `_ROLE_TO_LLM`.
- **Role config centralized** — `roles.py` is the single source of truth for which model handles which role and which roles enforce JSON output.
- **Context trimming isolated** — `context.py` is reusable. The head+tail algorithm with traceback preservation is testable in isolation.
- **Vision is special** — Cannot go through `llm.complete()` because multimodal messages require list content blocks, not strings. Delegates to `tools/vision.py`.

---

## 📋 Tool Signature

```python
@tool
def agent(
    role: str,                    # Required. See Roles table below.
    task: str,                    # Required. The instruction or question.
    context: str = "",            # Background information (injected before task)
    content: str = "",            # Raw material to process (code, text, data, base64 image)
    trace_id: str = "",           # Trace identifier for observability
    temperature: float = -1.0,    # Override temperature (-1 = use model default)
    max_tokens: int = -1,         # Override max_tokens (-1 = use model default)
) -> dict:
    """..."""
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `role` | `str` | — | **Required.** See Roles table below |
| `task` | `str` | — | **Required.** The instruction or question for this agent |
| `context` | `str` | `""` | Background information injected before the task |
| `content` | `str` | `""` | Raw material: code, text, data, or base64 image string |
| `trace_id` | `str` | `""` | Trace identifier for observability and logging |
| `temperature` | `float` | `-1.0` | Temperature override (-1 = model default) |
| `max_tokens` | `int` | `-1` | Max tokens override (-1 = model default) |

**For vision role:** `context` = file_path or public URL, `content` = base64-encoded image.

---

## 🎭 Roles

| Role | LLM Role | Timeout | Output | Description |
|------|----------|---------|--------|-------------|
| `classify` | `router` | 15s | Single word | Fast binary/category decision |
| `route` | `router` | 15s | JSON | Workflow + tool routing decision |
| `research` | `research` | 120s | Markdown | Synthesize web/memory content |
| `summarize` | `summarize` | 60s | Markdown | Dense, accurate summary |
| `extract` | `extract` | 60s | JSON | Structured data extraction (API json_mode) |
| `critique` | `critique` | 90s | Markdown | Quality evaluation: APPROVE / REVISE / REJECT |
| `analyze` | `analyze` | 90s | Markdown | Deep code/data analysis, no fixes |
| `code` | `code` | 120s | JSON | Generate Python patch: `{analysis, patch, assumptions, tests}` |
| `review` | `review` | 90s | JSON | Review patch: `{verdict, issues, corrected_patch}` |
| `plan` | `planner` | 90s | JSON | Decompose goal into ordered steps |
| `consultor` | `consultor` | 60s | Markdown | Expert advisory on architecture/best practices |
| `vision` | *(delegated)* | 60s | Markdown | Image analysis via `tools/vision.py` |

### Role Details

#### `classify` — Fast Binary/Category Decision

```python
result = agent(role="classify", task="Is this a bug or a feature request?")
```

Returns a single word or short phrase. No explanation, no punctuation.

```json
{
  "status": "success",
  "role": "classify",
  "text": "bug"
}
```

---

#### `route` — Task Routing Decision

```python
result = agent(role="route", task="Find the latest React documentation")
```

Returns structured JSON with workflow, tool, complexity, and reason.

```json
{
  "status": "success",
  "role": "route",
  "text": "{\"workflow\":\"research\",\"tool\":\"web\",\"complexity\":3,\"reason\":\"Requires web search and synthesis\"}",
  "parsed": {
    "workflow": "research",
    "tool": "web",
    "complexity": 3,
    "reason": "Requires web search and synthesis"
  }
}
```

---

#### `code` — Generate Python Patch

```python
result = agent(
    role="code",
    task="Fix the off-by-one error in the loop",
    context="Function: process_items(items)",
    content="def process_items(items):\n    for i in range(len(items) + 1):\n        print(items[i])"
)
```

Returns JSON with analysis, patch, assumptions, and tests.

```json
{
  "status": "success",
  "role": "code",
  "text": "...",
  "parsed": {
    "analysis": "The loop uses range(len(items) + 1) which causes IndexError on the last iteration.",
    "patch": "def process_items(items):\n    for i in range(len(items)):\n        print(items[i])",
    "assumptions": "items is a list with at least one element",
    "tests": "assert process_items([1,2,3]) == None  # prints 1, 2, 3"
  }
}
```

---

#### `vision` — Image Analysis

```python
# Via file path
result = agent(role="vision", task="What is in this image?", context="screenshot.png")

# Via URL
result = agent(role="vision", task="Describe this chart", context="https://example.com/chart.png")

# Via base64
result = agent(role="vision", task="Identify the error", content="data:image/png;base64,abc123...")
```

Delegates to `tools/vision.py`. Does NOT call `llm.complete()`.

#### Vision Role — Known Limitations

The agent facade simplifies vision to the most common use cases. The following
`tools.vision.vision()` parameters are **not exposed** through `agent(role="vision")`:

| Parameter | Status | Workaround |
|-----------|--------|------------|
| `mime_type` | Not exposed | Call `tools.vision.vision()` directly |
| `json_mode` | Not exposed | Call `tools.vision.vision()` directly |

For full vision control (e.g., requesting JSON-structured vision output or
specifying a non-default MIME type), bypass the agent facade and call
`tools.vision.vision()` directly.

---

## ✂️ Context Trimming

Before any LLM call, `context` and `content` are passed through `_trim_context()`:

| Feature | Behavior |
|---------|----------|
| **Head + Tail** | Keeps first 2000 chars (goal/objective) and last 4000 chars (recent interactions) |
| **Dynamic budget** | Derived from `cfg.max_context_tokens * 4` (config-reloadable) |
| **Traceback preservation** | If a Python traceback is detected, it is preserved in full within the tail |
| **Custom max_chars** | `_trim_context(text, max_chars=500)` for one-off overrides |

### Traceback Preservation

```python
# Input: massive context with an embedded traceback
text = "Goal: fix bug..." + "\n" * 50000 + traceback + "\nRecent: tool result"

# Output: head preserved, traceback intact, tail after traceback preserved
result = _trim_context(text)
# "Goal: fix bug...\n\n[... 45000 chars truncated ...]\n\nTraceback (most recent call last):...\nZeroDivisionError"
```

---

## 📊 JSON Output Handling

Three categories of JSON roles:

| Category | Roles | Mechanism |
|----------|-------|-----------|
| **API json_mode** | `extract` | `llm.complete(json_mode=True)` — model enforces JSON schema |
| **Prompt-only JSON** | `route`, `plan`, `code`, `review` | System prompt demands JSON; post-hoc regex extraction if model adds prose |
| **Non-JSON** | `classify`, `research`, `summarize`, `critique`, `analyze`, `consultor` | Free-form text output |

### JSON Parsing Fallback

For prompt-only JSON roles, if the model wraps JSON in markdown fences or adds surrounding text:

```python
# Model output: "Here is the result:\n```json\n{\"verdict\": \"APPROVE\"}\n```"
# Extracted: {"verdict": "APPROVE"}
```

If parsing fails entirely, returns `parsed: {}` with a `parse_warning` so callers can safely do `result.get("parsed", {}).get("field")` without crashing.

**`parse_warning` field:** When JSON parsing fails, the response includes a
`parse_warning` string explaining what went wrong. This is a diagnostic aid
for debugging prompt issues — callers should not rely on it for control flow.

```json
{
  "status": "success",
  "role": "review",
  "text": "I think this looks good...",
  "parsed": {},
  "parse_warning": "Response was not valid JSON for role 'review'. parsed={} returned. Check response.text for raw output."
}
```

---

## ⚙️ Configuration

No dedicated `.env` variables. Uses:
- `cfg.max_context_tokens` — drives `_max_context_chars()` (default: 8000 tokens → 32,000 chars)
- Per-role model config in `core/config.py` — `ROUTER_MODEL`, `EXECUTOR_MODEL`, `PLANNER_MODEL`, etc.

---

## 🔒 Security & Safety

| Feature | Implementation |
|---------|---------------|
| **Input validation** | Unknown roles rejected immediately; empty tasks rejected |
| **Case normalization** | `role.strip().lower()` prevents case-sensitive mismatches |
| **Context bounds** | `_trim_context()` prevents unbounded conversation history from reaching the LLM |
| **Vision isolation** | Vision delegates to `tools/vision.py` — never mixed with text LLM paths |
| **No arbitrary code execution** | All roles are prompt-based; no `eval()` or `exec()` |

---

## 🧪 Testing

```powershell
# Run all agent tests (fully mocked, no LLM calls)
D:\mcp\agent\venv\Scripts\pytest.exe tests/tools/agent -v -W error
```

**Test architecture:**
- `conftest.py` provides `mock_cfg` (autouse, MagicMock) and `mock_llm_result` fixtures
- `mock_cfg` prevents AsyncMock leakage from other tests per test isolation rule
- Tests are **fully isolated** — no real LLM calls, no network, no shared state

**Test file layout (mirrors source concerns):**

```
tests/tools/agent/
├── conftest.py                    # Shared fixtures (mock_cfg, mock_llm_result)
├── test_agent_validation.py       # Unknown role, missing task, role→prompt coverage
├── test_agent_vision.py           # Vision delegation to tools.vision
├── test_agent_llm_dispatch.py     # Successful LLM call, LLM failure, param passthrough
├── test_agent_json_parsing.py     # Valid JSON, invalid JSON, markdown fences, extraction
└── test_agent_context.py          # _trim_context unit tests + traceback preservation
```

**Mock strategy:**
- `llm.complete` is patched at `tools.agent.llm.complete` (where it is used)
- `tools.vision.vision` is patched at `tools.vision.vision` (where it is imported inline)
- `cfg` is patched at `tools.agent_core.context.cfg` (module-level import)
- `mock_llm_result` is a pre-built `MagicMock` with all required attributes

---

## 🔀 When to Use vs. Alternatives

| Need | Tool | Why |
|------|------|-----|
| Fast classification | `agent(classify)` | 15s Router, single word output |
| Task routing | `agent(route)` | 15s Router, structured JSON |
| Web research synthesis | `agent(research)` | 120s Executor, cites sources |
| Summarize long content | `agent(summarize)` | 60s Executor, dense output |
| Extract structured data | `agent(extract)` | 60s Executor, API json_mode |
| Evaluate quality | `agent(critique)` | 90s Executor, APPROVE/REVISE/REJECT |
| Analyze code | `agent(analyze)` | 90s Executor, no fixes — analysis only |
| Generate code patch | `agent(code)` | 120s Executor, returns `{analysis, patch, tests}` |
| Review code patch | `agent(review)` | 90s Executor, returns `{verdict, issues, corrected_patch}` |
| Decompose goal | `agent(plan)` | 90s Planner, returns ordered steps JSON |
| Architecture advice | `agent(consultor)` | 60s Consultor, best practices |
| Image analysis | `agent(vision)` | Delegates to `tools/vision.py` |

---

## 🛡️ AI Agent Instructions

If you are an AI assistant modifying the agent tool:

1. **Never add business logic to `agent.py`** — the facade should only validate, dispatch, and parse. Move prompts to `prompts.py`, role config to `roles.py`, trimming to `context.py`.
2. **Never strip or rewrite entire files** — only add comments, docstrings, or formatting. Preserve all existing code exactly.
3. **Add roles in all three places** — new roles require: (a) prompt in `prompts.py`, (b) mapping in `_ROLE_TO_LLM` in `roles.py`, (c) JSON flag if applicable in `roles.py`.
4. **Module-level cfg import** — `context.py` imports `cfg` at module level. If conftest patches it, the patch must target `tools.agent_core.context.cfg`.
5. **Vision stays special** — never route `vision` through `llm.complete()`. Always delegate to `tools/vision.py`.
6. **Preserve traceback logic** — `_trim_context()` traceback detection must not be broken. Tracebacks are high-signal debugging content.
7. **Test with mock_llm_result** — new tests must use the `mock_llm_result` fixture from `conftest.py`.
8. **JSON parsing fallback** — prompt-only JSON roles must handle markdown fences, surrounding text, and parse failures gracefully.
9. **No backup files** — never create `.bak` files when applying fixes.
10. **Commit workflow** — use `git commit -m` for new work. Only `git commit --amend --no-edit` for fixing the LAST commit.

---

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `tools/agent.py` | `@tool` facade: validation, dispatch, JSON parsing, vision delegation |
| `tools/agent_core/prompts.py` | `_SYSTEM_PROMPTS` — 12 role-specific system prompts |
| `tools/agent_core/roles.py` | `_ROLE_TO_LLM`, `_API_JSON_ROLES`, `_PROMPT_JSON_ROLES`, `_JSON_ROLES` |
| `tools/agent_core/context.py` | `_trim_context()`, `_max_context_chars()`, `_KEEP_HEAD/TAIL_CHARS` |
| `tests/tools/agent/conftest.py` | Test fixtures: `mock_cfg` (autouse), `mock_llm_result` |
| `tests/tools/agent/test_agent_validation.py` | Validation and role coverage tests |
| `tests/tools/agent/test_agent_vision.py` | Vision delegation tests |
| `tests/tools/agent/test_agent_llm_dispatch.py` | LLM dispatch and error handling tests |
| `tests/tools/agent/test_agent_json_parsing.py` | JSON parsing fallback tests |
| `tests/tools/agent/test_agent_context.py` | Context trimming unit tests |

---

## 🔮 Future Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | ✅ Complete | Core roles: classify, route, research, summarize, extract, critique, analyze, code, review, plan, consultor, vision |
| **Phase 2** | ✅ Complete | Agent split: `tools/agent_tool.py` → `tools/agent.py` + `tools/agent_core/` (prompts, roles, context) |
| **Phase 3** | ✅ Complete | Bug fixes: broken imports, JSON regex → brace-counting parser, test coverage gaps |
| **Phase 4** | ✅ Complete | Features: sleep-learn integration, `parse_warning` docs, vision limitations documented |

### Future Work (Beyond Phase 4)

| Priority | Item | Effort | Why |
|----------|------|--------|-----|
| 🔵 Future | Streaming support for `research`/`code` roles | Large | Partial responses for long-running roles; requires `core/llm.py` redesign |
| 🔵 Future | Role composition chaining | Large | Chain multiple roles in single call: `analyze` → `code` → `review`; depends on streaming decision |
| 🔵 Future | Vision `mime_type` / `json_mode` exposure through agent facade | Medium | Currently only accessible via direct `tools.vision.vision()` call |
| 🔵 Future | Token-aware context trimming | Medium | Replace `* 4` char approximation with actual tokenizer count |
| 🔵 Future | Self-improving prompts via sleep-learn feedback loop | Large | Auto-tune system prompts based on success/failure metrics |
| 🔵 Future | Role-specific context budget overrides | Small | Allow per-role `max_context_tokens` instead of global default |
| 🔵 Future | New roles: `refactor`, `test`, `document` | Medium each | Autonomous code maintenance workflows |

---

*Last updated: Phase 4 complete. 34 agent tests passing. Architecture: thin facade + agent_core submodules + sleep-learn integration.*
