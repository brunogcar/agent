"""
apply_vision_patches.py — run from D:/mcp/agent/

Wires vision capability into the existing stack:
  1. tools/agent_tool.py — adds "vision" role with system prompt + routing
  2. system_prompts/qwen_vision.md — vision-specific system prompt file

tools/vision.py is delivered as a full file (already placed).

Run: python apply_vision_patches.py
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
        print(f"  SKIP  {label} -- already exists"); return True
    p.write_text(content, encoding="utf-8")
    print(f"  OK    {label}"); return True


print("=== Vision patches ===\n")


# ── 1. tools/agent_tool.py — add vision role ─────────────────────────────────
#
# DECISION: vision goes in agent_tool not as a standalone agent call because:
#   - It follows the exact same role dispatch pattern as all other agent roles
#   - Callers already know agent(role="...") — one consistent interface
#   - agent_tool handles all the structured output / error normalisation
#
# IMPORTANT: vision uses llm.call() not llm.complete() internally (in tools/vision.py)
# because multimodal messages need a list content block, not a string.
# agent_tool delegates to vision() directly rather than calling llm itself,
# to keep the image encoding / message building logic in one place.
#
# The vision role is NOT in _ROLE_TO_LLM (which maps to llm roles) because
# it takes a different call path — it delegates to tools/vision.py.
# A special case in the dispatch handles this cleanly.

failures += not patch(
    "tools/agent_tool.py",
    '''\
    "plan":     "planner",   # Qwen 3.5 9B  — 90s
}''',
    '''\
    "plan":     "planner",   # Qwen 3.5 9B  — 90s
    # vision delegates to tools/vision.py (not a direct llm role)
    # because multimodal messages need custom content block structure
}''',
    "agent_tool: annotate _ROLE_TO_LLM for vision delegation",
)

# Add vision system prompt
failures += not patch(
    "tools/agent_tool.py",
    '''\
    "plan": (
        "You are a task planning specialist for an autonomous AI agent. "''',
    '''\
    "vision": (
        "You are a precise visual analysis specialist. "
        "Describe what you see accurately and completely. "
        "Do not hallucinate details that are not visible in the image. "
        "Structure your response: Overview, Key Elements, Text Content (if any), Notable Details."
    ),

    "plan": (
        "You are a task planning specialist for an autonomous AI agent. "''',
    "agent_tool: add vision system prompt",
)

# Add vision to the docstring role list
failures += not patch(
    "tools/agent_tool.py",
    '''\
    role: "classify" | "route" | "research" | "summarize" | "extract" |
          "critique" | "analyze" | "code" | "review" | "plan"''',
    '''\
    role: "classify" | "route" | "research" | "summarize" | "extract" |
          "critique" | "analyze" | "code" | "review" | "plan" | "vision"''',
    "agent_tool: add vision to role docstring",
)

# Add vision to the unknown role error message
failures += not patch(
    "tools/agent_tool.py",
    '''\
            f"Unknown role '{role}'. "
            "Use: classify | route | research | summarize | extract | "
            "critique | analyze | code | review | plan"''',
    '''\
            f"Unknown role '{role}'. "
            "Use: classify | route | research | summarize | extract | "
            "critique | analyze | code | review | plan | vision"''',
    "agent_tool: add vision to unknown role error",
)

# Add vision dispatch — delegate to tools/vision.py before the standard llm.complete path.
# This is inserted right after the role validation block.
failures += not patch(
    "tools/agent_tool.py",
    '''\
    if not task:
        return {"status": "error", "error": "task is required"}

    system_prompt = _SYSTEM_PROMPTS[role]
    llm_role      = _ROLE_TO_LLM[role]''',
    '''\
    if not task:
        return {"status": "error", "error": "task is required"}

    # Vision role delegates to tools/vision.py which handles multimodal
    # message construction. It cannot go through llm.complete() because
    # that only supports string content, not image_url content blocks.
    if role == "vision":
        try:
            from tools.vision import vision as _vision
        except ImportError:
            return {
                "status": "error",
                "error":  "tools/vision.py not found. Run: python apply_vision_patches.py",
            }
        # Extract image params from context/content convention:
        #   context = file_path or url
        #   content = base64-encoded image string
        # This mirrors how other roles use context= for background and content= for material.
        file_path  = ""
        url        = ""
        b64        = ""
        mime_type  = "image/jpeg"

        if context:
            if context.startswith(("http://", "https://")):
                url = context
            elif context.startswith("data:"):
                b64 = context
            else:
                file_path = context

        if content and not b64 and not file_path and not url:
            b64 = content

        json_mode = role in _JSON_ROLES
        return _vision(
            prompt    = task,
            file_path = file_path,
            base64    = b64,
            url       = url,
            mime_type = mime_type,
            json_mode = json_mode,
            trace_id  = trace_id,
        )

    system_prompt = _SYSTEM_PROMPTS[role]
    llm_role      = _ROLE_TO_LLM[role]''',
    "agent_tool: vision role delegates to tools/vision.py",
)

# Add vision to _JSON_ROLES so parsed output is returned when json_mode is used
failures += not patch(
    "tools/agent_tool.py",
    '''\
# Roles that return JSON via system prompt only (parsed post-hoc)
# Nemotron and Qwen both reject the json_object response_format parameter
_PROMPT_JSON_ROLES = {"route", "plan", "code", "review"}''',
    '''\
# Roles that return JSON via system prompt only (parsed post-hoc)
# Nemotron and Qwen both reject the json_object response_format parameter
# vision json_mode is handled inside tools/vision.py directly
_PROMPT_JSON_ROLES = {"route", "plan", "code", "review", "vision"}''',
    "agent_tool: add vision to _PROMPT_JSON_ROLES",
)


# ── 2. system_prompts/qwen_vision.md ─────────────────────────────────────────
# Follows exact format of existing prompt files:
# Jinja template block → role identity → capabilities → output rules

failures += not write_file(
    "system_prompts/qwen_vision.md",
    '''\
# 👁️ QWEN VISION — VISUAL ANALYSIS SPECIALIST 🎯

---

## 🔗 JINJA TEMPLATE STRUCTURE (For LM Studio) ✨⚡
```jinja
You are the Vision Model (Qwen-9b). Here is the conversation:
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
Call via `agent(role="vision", task="...", context="file_path_or_url")`. You are the **visual analysis** specialist.

---

## YOUR ONLY JOB: ACCURATE VISUAL ANALYSIS 👁️

Describe ONLY what is visible. Never hallucinate details.

### Text Mode (default):
Structured plain text analysis:
```
Overview: [one sentence]
Key Elements: [list]
Text Content: [any readable text, or "none"]
Notable Details: [patterns, anomalies, colours]
```

### JSON Mode (json_mode=True):
Output ONLY valid JSON — no markdown fences, no prose:
```json
{
  "overview": "one sentence",
  "elements": ["list", "of", "visible", "elements"],
  "text_content": "readable text or null",
  "colors": ["dominant", "colors"],
  "details": "notable patterns or anomalies",
  "confidence": "high|medium|low"
}
```

---

## IMAGE INPUT CONVENTIONS 🖼️

```python
# Local file (most common):
agent(role="vision", task="What errors are shown?", context="workspace/screenshot.png")

# Public URL:
agent(role="vision", task="Describe this chart", context="https://example.com/chart.png")

# Base64 string (from file_ops or python):
agent(role="vision", task="Read all text", content="<base64_string>", mime_type="image/png")

# JSON structured output:
agent(role="vision", task="Extract all numbers", context="chart.png", json_mode=True)
```

---

## CRITICAL RULES 🛡️

✅ Describe ONLY what is visible — never invent details  
✅ For text/numbers in images — transcribe EXACTLY as shown  
✅ JSON mode: raw JSON ONLY, no fences, no preamble  
✅ Note uncertainty explicitly: "text partially obscured"  
❌ Never guess colours/shapes/text that aren\'t clearly visible  
❌ Never add interpretation beyond what is visually present  

---

## COMMON USE CASES ⚡

| Task | Example |
|------|---------|
| Screenshot analysis | "What errors are shown on screen?" |
| Chart/graph reading | "Extract all values from this bar chart" |
| Document OCR | "Read all text visible in this image" |
| Code screenshot | "What does this code do?" |
| Diagram understanding | "Describe the architecture shown" |
| Data extraction | "List all numbers and labels" |

---

**Remember:** Accuracy > completeness. If unsure — say so! 👁️🎯✅
''',
    "system_prompts/qwen_vision.md: create vision system prompt",
)


# ── Summary ───────────────────────────────────────────────────────────────────
print()
if failures == 0:
    print("All vision patches applied.")
    print("Make sure tools/vision.py is in place, then restart server.py")
    print()
    print("Test with:")
    print('  agent(role="vision", task="Describe this image", context="path/to/image.jpg")')
else:
    print(f"{failures} patch(es) failed.")
    print("Paste the failing file for a full replacement.")
    sys.exit(1)
