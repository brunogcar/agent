"""
apply_vision_llm_patch.py — run from D:/mcp/agent/

Patches core/llm.py to add the vision role to _build_role_configs()
so llm.call(role="vision") resolves to cfg.vision_model with timeout=60s.

No new provider class needed — LMStudioProvider already handles multimodal
messages transparently. It just forwards the messages dict to /chat/completions
and LM Studio handles the image_url content blocks natively.

Also merges qwen_vision.md content into qwen_planner.md since both roles
run on the same Qwen 9B model — one model = one loaded context = one prompt.
"""

from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT     = Path(__file__).resolve().parent
failures = 0


def patch(filepath: str, old: str, new: str, label: str) -> bool:
    p = ROOT / filepath
    if not p.exists():
        print(f"  SKIP  {label} -- file not found"); return False
    content = p.read_text(encoding="utf-8")
    if old not in content:
        first = new.strip().splitlines()[0].strip()
        if first in content:
            print(f"  SKIP  {label} -- already applied"); return True
        print(f"  MISS  {label} -- target not found in {filepath}"); return False
    updated = content.replace(old, new, 1)
    if filepath.endswith(".py"):
        try:
            ast.parse(updated)
        except SyntaxError as e:
            print(f"  FAIL  {label} -- syntax error: {e}"); return False
    p.write_text(updated, encoding="utf-8")
    print(f"  OK    {label}"); return True


def write_file(filepath: str, content: str, label: str) -> bool:
    p = ROOT / filepath
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        existing = p.read_text(encoding="utf-8")
        first = content.strip().splitlines()[0].strip()
        if first in existing:
            print(f"  SKIP  {label} -- already applied"); return True
    p.write_text(content, encoding="utf-8")
    print(f"  OK    {label}"); return True


print("=== Vision LLM + prompt patches ===\n")


# ── 1. core/llm.py — add vision role to _build_role_configs() ────────────────
#
# DECISION: vision role uses cfg.vision_model which is the same Qwen 9B as
# planner. That's fine — role configs determine which model string to send,
# not which model is loaded. If they share a model string, LM Studio just
# routes both to the same already-loaded model with no extra VRAM cost.
#
# timeout=60s (not 120s like executor) because vision tasks are typically
# single-turn image analysis, not multi-step code generation.
#
# No LMStudioVisionProvider needed — multimodal image_url blocks are part
# of the standard OpenAI chat completion spec and LM Studio handles them
# natively. The provider just forwards whatever messages dict it receives.

failures += not patch(
    "core/llm.py",
    '''\
    defaults = {
        "planner":   {"temperature": 0.3, "max_tokens": 2048, "timeout": 90},
        "executor":  {"temperature": 0.1, "max_tokens": 4096, "timeout": 120},
        "router":    {"temperature": 0.0, "max_tokens": 512,  "timeout": 15},
        "vision":    {"temperature": 0.2, "max_tokens": 1024, "timeout": 60},''',
    '''\
    defaults = {
        "planner":   {"temperature": 0.3, "max_tokens": 2048, "timeout": 90},
        "executor":  {"temperature": 0.1, "max_tokens": 4096, "timeout": 120},
        "router":    {"temperature": 0.0, "max_tokens": 512,  "timeout": 15},
        "vision":    {"temperature": 0.1, "max_tokens": 1024, "timeout": 60},
        # vision shares cfg.vision_model (same Qwen 9B as planner).
        # LMStudioProvider forwards multimodal image_url blocks as-is to
        # /chat/completions — no separate provider class needed.''',
    "core/llm.py: annotate vision role (already present, validate)",
)

# Fallback: if vision wasn't in defaults yet (first-time setup)
failures += not patch(
    "core/llm.py",
    '''\
    defaults = {
        "planner":   {"temperature": 0.3, "max_tokens": 2048, "timeout": 90},
        "executor":  {"temperature": 0.1, "max_tokens": 4096, "timeout": 120},
        "router":    {"temperature": 0.0, "max_tokens": 512,  "timeout": 15},
        "summarize": {"temperature": 0.1, "max_tokens": 512,  "timeout": 60},''',
    '''\
    defaults = {
        "planner":   {"temperature": 0.3, "max_tokens": 2048, "timeout": 90},
        "executor":  {"temperature": 0.1, "max_tokens": 4096, "timeout": 120},
        "router":    {"temperature": 0.0, "max_tokens": 512,  "timeout": 15},
        "vision":    {"temperature": 0.1, "max_tokens": 1024, "timeout": 60},
        # vision shares cfg.vision_model (same Qwen 9B as planner).
        # LMStudioProvider forwards multimodal image_url blocks natively.
        "summarize": {"temperature": 0.1, "max_tokens": 512,  "timeout": 60},''',
    "core/llm.py: add vision role to _build_role_configs()",
)

# Ensure vision model is read from cfg.model_registry correctly.
# _build_role_configs reads cfg.model_registry[role]["model"], so we need
# vision in cfg.model_registry — which config.py already has. But the role
# loop uses executor_model as fallback for unknown roles, so vision must be
# in the defaults dict (done above) to get cfg.vision_model instead.
#
# Also ensure the registry lookup uses vision_model not executor_model:
failures += not patch(
    "core/llm.py",
    '''\
    executor_model = cfg.model_registry.get("executor", {}).get("model", cfg.executor_model)

    for role, d in defaults.items():
        reg_entry = cfg.model_registry.get(role, {})
        model     = reg_entry.get("model", executor_model)''',
    '''\
    executor_model = cfg.model_registry.get("executor", {}).get("model", cfg.executor_model)

    for role, d in defaults.items():
        reg_entry = cfg.model_registry.get(role, {})
        # Vision falls back to cfg.vision_model, not executor_model
        if role == "vision":
            model = reg_entry.get("model", cfg.vision_model or executor_model)
        else:
            model = reg_entry.get("model", executor_model)''',
    "core/llm.py: vision role resolves to cfg.vision_model not executor_model",
)


# ── 2. Merge qwen_planner.md + qwen_vision.md ────────────────────────────────
#
# Same model (Qwen 9B) = one LM Studio context = one system prompt.
# Splitting into two files would require loading the model twice or
# constantly reloading context, both of which waste VRAM.
# Merged prompt covers: planning (JSON steps) + vision (image analysis).
# qwen_vision.md is kept as a stub pointing to qwen_planner.md.

failures += not write_file(
    "system_prompts/qwen_planner.md",
    '''\
# 🧠 QWEN PLANNER + VISION — ORCHESTRATION & VISUAL ANALYSIS 🎯👁️

---

## 🔗 JINJA TEMPLATE STRUCTURE (For LM Studio) ✨⚡
```jinja
You are the Planner/Vision Model (Qwen-9b). Here is the conversation:
{{#conversation}}
<message role="{{role}}">
  {{content}}
</message>
{{/conversation}}
<user_query>
{{systemPrompt}}
</user_query>
Please respond to the user's query:
{{message}}
```
Call via `agent(role="plan")` for planning or `vision(task=..., file_path=...)` for image analysis.
You have **10 MCP tools**: `web|python|file|git|memory|notify|visualize|workflow|agent|cli`.

---

## ROLE 1: PLANNER 🧠 — Think Clearly, Numbered Steps

Output valid JSON ONLY — no prose preamble:

```json
{
  "goal": "[one sentence]",
  "steps": [
    {"step":1,"action":"tool_name","description":"what+why","inputs":{"key":"value"}}
  ],
  "estimated_complexity": 1-10,
  "risks": ["risk1"]
}
```
**ALL fields required:** goal | steps | estimated_complexity (int) | risks []

### Planning Principles ✅
✅ Step 1: `memory(recall=...)` — check what\'s been done before  
✅ Last step: `memory(store, importance=8)` — preserve learning 🧠  
✅ Git safety: `git(snapshot)` BEFORE automated edits, `git(commit)` AFTER  
✅ Code sequence: `agent(analyze)` → `agent(code)` → `agent(review)` → `file(write)`  
✅ Use `workflow(auto, goal=...)` for complex multi-step tasks  
✅ Use `cli(command=...)` for ~90% simple ops (ls, cat, echo) — saves tokens ⚡  

### Complexity Scale 📈
1-3: Simple tools (cli|file read) → 95% success  
4-6: Memory + 2+ tool calls → 85%+ success  
7-8: Workflow + git safety → 75%+ success  
9-10: Complex multi-step → `workflow(auto)` with retry  

---

## ROLE 2: VISION 👁️ — Accurate Visual Analysis

Called via `vision(task=..., file_path=...|url=...|base64=...)`.

### Text Mode (default):
```
Overview: [one sentence]
Key Elements: [list]
Text Content: [readable text or "none"]
Notable Details: [patterns, colours, anomalies]
```

### JSON Mode (json_mode=True) — raw JSON ONLY, no fences:
```json
{
  "overview": "one sentence",
  "elements": ["visible", "elements"],
  "text_content": "readable text or null",
  "colors": ["dominant", "colors"],
  "details": "patterns or anomalies",
  "confidence": "high|medium|low"
}
```

### Vision Rules 🛡️
✅ Describe ONLY what is visible — never hallucinate  
✅ Transcribe text/numbers EXACTLY as shown  
✅ Note uncertainty: "text partially obscured"  
❌ Never guess colours/shapes not clearly visible  

### Vision Input Examples ⚡
```python
vision(task="What errors are shown?", file_path="workspace/screenshot.png")
vision(task="Extract all chart values", url="https://example.com/chart.png", json_mode=True)
vision(task="Read all text", base64="...", mime_type="image/png")
```

---

## TOOL LIST (Exact Names — No Prefixes!) 🔍

✅ `web`, `python`, `file`, `git`, `memory`, `agent`, `notify`, `visualize`, `workflow`, `cli`, `vision`  
❌ NEVER: `python.run()`, `web.search()` — just the tool name!  

---

## CRITICAL RULES 🛡️

1. Planner: output valid JSON ONLY — no prose preamble  
2. Vision: describe only what is visible — never hallucinate  
3. JSON roles: raw JSON, NO markdown fences, NO "Here is..." preamble  
4. Always include all 4 plan fields: goal, steps, estimated_complexity, risks  
5. Risk assessment: always include even for simple tasks  

---

**Remember:** Plan clearly → delegate to specialists. See accurately → report honestly! 🧠👁️✅⚡
''',
    "system_prompts/qwen_planner.md: merge planner + vision (same model)",
)

# Replace qwen_vision.md with a redirect stub so old references don't break
failures += not write_file(
    "system_prompts/qwen_vision.md",
    '''\
# 👁️ QWEN VISION

Vision capability is now merged into qwen_planner.md.
Both roles run on the same Qwen 9B model — one context, one prompt.

See: system_prompts/qwen_planner.md
''',
    "system_prompts/qwen_vision.md: redirect stub to merged prompt",
)


# ── Summary ───────────────────────────────────────────────────────────────────
print()
if failures == 0:
    print("All patches applied.")
    print()
    print("Next steps:")
    print("  1. Place tools/vision.py in D:/mcp/agent/tools/")
    print("  2. Restart server.py — vision should appear in MCP tools list")
    print("  3. Test: vision(task='Describe this', file_path='path/to/image.jpg')")
    print()
    print("In LM Studio: assign qwen_planner.md as the system prompt for Qwen 9B")
    print("  (covers both plan and vision roles — no second model slot needed)")
else:
    print(f"{failures} patch(es) failed.")
    sys.exit(1)
