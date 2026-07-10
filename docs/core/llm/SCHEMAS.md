<- Back to [LLM Overview](../LLM.md)

# 📋 JSON Schemas

This document is a **consolidated reference** of every `json_schema` definition in the codebase. The `json_schema` parameter was added to `llm.complete()` / `llm.call()` / `provider.chat_completion()` in v1.2 as Phase 1 plumbing; Phase 2 (v1.3, 2026-07-08) defined schemas for 6 agent roles + the autocode debug node + the two distillation pipelines. Claude/Gemini native providers defer json_schema enforcement (different API mechanisms) — see `INSTRUCTIONS.md` rule #12.

When `json_schema` is provided, LM Studio enforces it at generation time via **outlines** — the model literally cannot produce schema-invalid output. This is strictly stronger than `json_mode` (which only guarantees valid JSON, not schema conformance). `json_schema` takes precedence over `json_mode` and implies `json_mode` for parsing.

---

## 🔗 Schema Catalog

| Schema | File | Fields | Used By |
|--------|------|--------|---------|
| `JSON_SCHEMA` | `tools/agent_ops/roles/code.py` | `analysis: str`, `patch: str`, `assumptions: str`, `tests: str` (all required, no extras) | `code` role — autonomous code generation |
| `JSON_SCHEMA` | `tools/agent_ops/roles/route.py` | `workflow: str`, `tool: str`, `complexity: int`, `reason: str`, `confidence: str`, `clarifying_questions: [str]` (all required, no extras) | `router` role — **single source of truth**, imported by `core/router.py` `_model_route()`. Do NOT define a separate schema in router.py. |
| `JSON_SCHEMA` | `tools/agent_ops/roles/plan.py` | `goal: str`, `steps: [{step: int, action: str, description: str, inputs: obj}]`, `estimated_complexity: int`, `risks: [str]` (all required, no extras) | `planner` role — task decomposition |
| `JSON_SCHEMA` | `tools/agent_ops/roles/review.py` | `verdict: str (APPROVE\|REVISE\|REJECT)`, `issues: [{severity: str (critical\|warning\|info), description: str, fix: str}]`, `corrected_patch: str (default "")` (all required, no extras) | `review` role — code review |
| `JSON_SCHEMA` | `tools/agent_ops/roles/refactor.py` | `analysis: str`, `refactored_code: str`, `risks: str`, `tests: str` (all required, no extras) | `refactor` role (fallback: `code`) — autonomous refactoring |
| `JSON_SCHEMA` | `tools/agent_ops/roles/test.py` | `test_code: str`, `coverage_analysis: str`, `setup_notes: str`, `edge_cases: str` (all required, no extras) | `test` role (fallback: `code`) — autonomous test generation |
| `_DISTILL_JSON_SCHEMA` | `core/memory_backend/procedural/distill.py` | `has_insight: bool`, `rule: str`, `tags: str` (all required, no extras) | `distill_workflow()` via `llm.complete(role="planner")` — meta-learning rule extraction from traces |
| `_DISTILL_SCHEMA` | `core/sleep_learn/distiller.py` | `rule: str`, `confidence: number (0.0–1.0, min/max enforced)` (all required, no extras) | `distill_observation()` via `llm.complete(role="executor")` — sleep-learn rule extraction with confidence scoring |
| `_DEBUG_JSON_SCHEMA` | `workflows/autocode_impl/nodes/debug.py` | `root_cause: str`, `defense_notes: str`, `fix: str` (all required, no extras) | `node_systematic_debug()` via `_call(role="executor")` — autocode TDD debug loop |

> Total: **9 schemas** across the codebase (6 role schemas + 2 distillation schemas + 1 autocode debug schema). All enforce `additionalProperties: False` to reject unexpected keys.

---

## 🧬 Field-Type Cheat Sheet

The schemas share a small set of field-type patterns:

| Pattern | Example | Purpose |
|---------|---------|---------|
| Plain `string` | `analysis`, `rule`, `fix` | Free-text LLM output |
| `string` with `enum` | `verdict: [APPROVE, REVISE, REJECT]`, `severity: [critical, warning, info]` | Closed-set classification |
| `string` with `default` | `corrected_patch: ""` | Hardening fix — small models emit `"null"` as a string instead of JSON `null`; empty string is safer |
| `integer` | `complexity`, `estimated_complexity` | Numeric scoring |
| `number` with `minimum`/`maximum` | `confidence: 0.0–1.0` | Bounded float (sleep-learn only) |
| `boolean` | `has_insight` | Yes/no signal (distill only) |
| `array of strings` | `risks`, `clarifying_questions` | Open-ended list |
| `array of objects` | `steps`, `issues` | Structured list with sub-schema |
| `object` with `additionalProperties: True` | `inputs` (in plan steps) | Free-form k/v map (plan only) |

---

## 🧭 Provider Compatibility Matrix

| Provider | `json_schema` enforced? | Mechanism |
|----------|------------------------|-----------|
| LMStudioProvider | ✅ Yes | Outlines (internal) — model cannot produce schema-invalid output |
| OpenAICompatibleProvider (OpenAI, DeepSeek, Mistral, Qwen, Kimi, Z.ai, MiMo) | ✅ Yes | `response_format={"type":"json_schema",...}` field in chat completion request |
| AnthropicProvider (Claude) | ⚠️ Phase 1 deferred | Anthropic tool-use API — different mechanism; `json_mode` via system instruction only |
| GeminiProvider (Gemini) | ⚠️ Phase 1 deferred | `responseSchema` / `responseMimeType` — different mechanism; `json_mode` via system instruction only |

For Claude/Gemini, callers should still pass `json_schema=` (it's silently ignored by these providers), but must NOT rely on schema enforcement — the model may produce schema-violating output. Always validate the parsed JSON before consuming it. Test with real API keys before relying on schema enforcement for these native providers (see `INSTRUCTIONS.md` rule #12).

---

## 🧪 How to Test a Schema Change

1. Update the schema constant in the source file (e.g., `tools/agent_ops/roles/code.py → JSON_SCHEMA`).
2. Update the matching system prompt's "OUTPUT FORMAT" line so the model's instructions and the schema agree.
3. Run the schema-enforcement tests:
   - `tests/core/llm/test_json_schema.py` — provider payload structure, parsing, backward compat
   - Per-role tests under `tests/tools/agent/` (e.g., `test_agent_roles.py`)
4. For distillation schemas, run the relevant subsystem tests:
   - `tests/core/memory/test_*` (procedural distill)
   - `tests/core/sleep_learn/test_*` (sleep-learn distiller)
5. For autocode debug schema, run `tests/workflows/autocode/test_debug.py`.

---

## 🔧 Adding a New Schema

1. Define the schema as a module-level constant in the consumer file (e.g., `JSON_SCHEMA = {...}`). Module-level (not inline) avoids re-creating the dict on every call.
2. Set `additionalProperties: False` to reject unexpected keys (every existing schema does this).
3. List every field in `required` (every existing schema marks all fields as required).
4. Document the schema in this file (add a row to the Schema Catalog table).
5. Update the consumer's system prompt to describe the JSON format (the schema and prompt must agree).
6. Pass it to `llm.complete(...)` (or `_call(...)` in autocode) via `json_schema=YOUR_SCHEMA`.

---

*Last updated: 2026-07-10. See [LLM.md](../LLM.md) for the LLM overview, [ARCHITECTURE.md](ARCHITECTURE.md) for the LLM module tree, [API.md](API.md) for `complete()` parameter details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
