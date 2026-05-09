"""
apply_vision_system_prompt.py — run from D:/mcp/agent/

Updates system_prompts/system_prompt.md and system_prompts/hermes_executor.md
to reference the new vision role so the agent knows it can use it.

Run: python apply_vision_system_prompt.py
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT     = Path(__file__).resolve().parent
failures = 0


def patch_md(filepath: str, old: str, new: str, label: str) -> bool:
    """Patch a markdown file (no ast.parse needed)."""
    p = ROOT / filepath
    if not p.exists():
        print(f"  SKIP  {label} -- file not found"); return False
    content = p.read_text(encoding="utf-8")
    if old not in content:
        first = new.strip().splitlines()[0].strip()
        if first in content:
            print(f"  SKIP  {label} -- already applied"); return True
        print(f"  MISS  {label} -- target not found in {filepath}"); return False
    p.write_text(content.replace(old, new, 1), encoding="utf-8")
    print(f"  OK    {label}"); return True


print("=== Vision system prompt patches ===\n")


# ── system_prompt.md — add vision to agent role list ─────────────────────────
failures += not patch_md(
    "system_prompts/system_prompt.md",
    "### agent 🤖 — classify|route|plan|research|summarize|extract|analyze|code|review|critique",
    "### agent 🤖 — classify|route|plan|research|summarize|extract|analyze|code|review|critique\n"
    "### vision 👁️ — agent(role=\"vision\", task=\"...\", context=\"file_path|url\") | json_mode=True for structured output",
    "system_prompt.md: add vision to agent capabilities",
)

# Add vision to hard rules section
failures += not patch_md(
    "system_prompts/system_prompt.md",
    "3. **Protected files NEVER edited via autocode**: server.py, registry.py, core/config.py, core/tracer.py",
    "3. **Protected files NEVER edited via autocode**: server.py, registry.py, core/config.py, core/tracer.py\n"
    "3b. **Vision inputs**: context= for file_path/URL, content= for base64. Always check VISION_MODEL is set in .env",
    "system_prompt.md: add vision usage rule",
)


# ── hermes_executor.md — add vision to agent role list ───────────────────────
failures += not patch_md(
    "system_prompts/hermes_executor.md",
    "### agent → `agent(role=...)` 🤖\nclassify|route|plan|research|summarize|extract|analyze|code|review|critique",
    "### agent → `agent(role=...)` 🤖\n"
    "classify|route|plan|research|summarize|extract|analyze|code|review|critique\n\n"
    "### vision → `agent(role=\"vision\", task=\"...\", context=\"file_path|url\")` 👁️\n"
    "Analyse images: screenshots, charts, documents, diagrams. json_mode=True for structured output.",
    "hermes_executor.md: add vision to tool list",
)


print()
if failures == 0:
    print("System prompt patches applied.")
else:
    print(f"{failures} patch(es) failed.")
    sys.exit(1)
