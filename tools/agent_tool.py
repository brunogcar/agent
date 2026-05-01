"""
tools/agent_tool.py — Agent meta-tool.

Replaces: old agents.py (call_agent with generic prompts for every role)
The LLM sees ONE tool: agent(role, task, ...)

Key fixes over old agents.py:
  1. Every role has its OWN system prompt — CODER/REVIEWER/ANALYZER are
     no longer dead code. They are actually used.
  2. Nemotron (router) is used for fast classification tasks — not Hermes.
  3. Per-role timeouts enforced via core/llm.py (not a flat 120s for all).
  4. Structured JSON output for code roles — enforces discipline.
  5. context= and content= passed as separate parameters so the LLM client
     builds a clean multi-turn message structure.
  6. trace_id propagated through every call for full observability.

Roles:
  classify   → Nemotron 4B  — fast binary/category decisions (15s)
  route      → Nemotron 4B  — task routing decision (15s)
  research   → Hermes 3 8B  — synthesise web/memory content (120s)
  summarize  → Hermes 3 8B  — condense long content (60s)
  extract    → Hermes 3 8B  — pull structured data from text (60s)
  critique   → Hermes 3 8B  — evaluate quality, find issues (90s)
  analyze    → Hermes 3 8B  — deep analysis of code/data/text (90s)
  code       → Hermes 3 8B  — generate Python code/patches (120s)
  review     → Hermes 3 8B  — review code for bugs/quality (90s)
  plan       → Qwen 3.5 9B  — high-level task decomposition (90s)
"""

from __future__ import annotations

from registry import tool
from core.llm import llm


# ── System prompts ────────────────────────────────────────────────────────────
# Each role gets a specialist prompt.
# These are the prompts that were DEFINED but never USED in the old codebase.
# They are now wired to every call through this tool.

_SYSTEM_PROMPTS: dict[str, str] = {

    "classify": (
        "You are a fast classifier. "
        "Respond with ONLY the category label — no explanation, no punctuation, "
        "no extra words. Single word or short phrase only."
    ),

    "route": (
        "You are a task router. Respond with ONLY a JSON object. "
        "No thinking tags. No explanation. No markdown fences. "
        "Start your response with { and end with }.\n"
        'Format: {"workflow":"research or data or autocode or direct",'
        '"tool":"web or python or file or git or memory or agent or notify or visualize",'
        '"complexity":5,'
        '"reason":"one sentence why"}'
    ),

    "research": (
        "You are a research synthesis specialist. "
        "Given source material (web pages, documents, memory), produce a "
        "clear, accurate, well-structured synthesis. "
        "Cite sources where possible. "
        "Do not hallucinate facts not present in the provided content. "
        "If sources conflict, note the conflict explicitly. "
        "Format with markdown headings for readability."
    ),

    "summarize": (
        "You are a precise summarisation specialist. "
        "Produce a dense, accurate summary that preserves all key facts, "
        "numbers, dates, and conclusions. "
        "Remove filler, repetition, and preamble. "
        "Never add information not present in the original. "
        "Output only the summary — no preamble, no 'Here is a summary of...'."
    ),

    "extract": (
        "You are a structured data extraction specialist. "
        "Extract the requested information exactly as it appears in the source. "
        "Output ONLY valid JSON — no prose, no markdown fences, no explanation. "
        "If a field is not found, use null. "
        "Never invent or infer values not explicitly present in the source."
    ),

    "critique": (
        "You are a rigorous quality reviewer. "
        "Evaluate the provided work against the stated goal. "
        "Be specific about what is good, what is wrong, and what is missing. "
        "For each issue found: state the problem, explain why it matters, "
        "and suggest a concrete fix. "
        "Do not soften criticism — clarity is more useful than politeness. "
        "End with a structured verdict: APPROVE | REVISE | REJECT and why."
    ),

    "analyze": (
        "You are a senior Python code analyst. "
        "Analyse the provided code or data with precision. "
        "Identify: purpose, structure, dependencies, bugs, edge cases, "
        "performance issues, and security concerns. "
        "Be specific — reference exact line numbers, variable names, "
        "and function signatures. "
        "Do not suggest changes yet — this is analysis only."
    ),

    "code": (
        "You are a senior Python developer specialising in minimal, correct patches. "
        "\n\nCODING STANDARDS (mandatory):\n"
        "- PEP 8 formatting and PEP 484 type hints on all functions\n"
        "- Pure functions where possible; no global state mutations\n"
        "- Explicit input validation — never silently fail\n"
        "- Google-style docstrings on all public functions\n"
        "- Modular design — each function does exactly one thing\n"
        "- If uncertain about behaviour → return a safe fallback, not a guess\n"
        "\nOUTPUT FORMAT (mandatory JSON, no markdown fences):\n"
        '{"analysis": "what the problem is and why", '
        '"patch": "the complete corrected code or unified diff", '
        '"assumptions": "anything assumed about context", '
        '"tests": "how to verify this change is correct"}'
        "\n\nWrite the minimal change that solves the problem. "
        "Do not rewrite unrelated code. "
        "Do not change function signatures unless the bug requires it."
    ),

    "review": (
        "You are a senior Python code reviewer. "
        "Review the provided patch or code change. "
        "\n\nCHECK FOR (in this order):\n"
        "1. Correctness — does it actually solve the stated problem?\n"
        "2. Bugs — new errors introduced, off-by-one, uncaught exceptions\n"
        "3. Edge cases — empty input, None values, large data, concurrent access\n"
        "4. Breaking changes — function signature changes, import changes\n"
        "5. Style — PEP 8, type hints, docstrings\n"
        "6. Performance — unnecessary loops, blocking calls, memory leaks\n"
        "\nOUTPUT FORMAT (mandatory JSON, no markdown fences):\n"
        '{"verdict": "APPROVE|REVISE|REJECT", '
        '"issues": [{"severity": "critical|warning|info", "description": "...", "fix": "..."}], '
        '"corrected_patch": "corrected code if verdict is REVISE, else null"}'
    ),

    "plan": (
        "You are a task planning specialist for an autonomous AI agent. "
        "Break the given goal into a clear, ordered sequence of steps. "
        "Each step must be concrete and executable by the agent's available tools: "
        "web, python, file, git, memory, notify, visualize, agent.\n\n"
        "OUTPUT: valid JSON only. No thinking tags. No markdown fences. "
        "Start with { and end with }.\n"
        'Format: {"goal":"restated goal",'
        '"steps":[{"step":1,"action":"tool_name","description":"what to do","inputs":{"key":"value"}}],'
        '"estimated_complexity":5,'
        '"risks":["failure point 1"]}'
    ),
}

# ── Role → LLM role mapping ───────────────────────────────────────────────────
# Maps agent persona → the llm.py role (which determines model + timeout)

_ROLE_TO_LLM: dict[str, str] = {
    "classify": "router",    # Nemotron 4B  — 15s
    "route":    "router",    # Nemotron 4B  — 15s
    "research": "research",  # Hermes 3 8B  — 120s
    "summarize":"summarize", # Hermes 3 8B  — 60s
    "extract":  "extract",   # Hermes 3 8B  — 60s
    "critique": "critique",  # Hermes 3 8B  — 90s
    "analyze":  "analyze",   # Hermes 3 8B  — 90s
    "code":     "code",      # Hermes 3 8B  — 120s
    "review":   "review",    # Hermes 3 8B  — 90s
    "plan":     "planner",   # Qwen 3.5 9B  — 90s
}

# Roles that return JSON via API json_object mode (only Hermes supports it)
_API_JSON_ROLES    = {"extract", "code", "review"}

# Roles that return JSON via system prompt only (parsed post-hoc)
# Nemotron and Qwen both reject the json_object response_format parameter
_PROMPT_JSON_ROLES = {"route", "plan"}

# Combined — all roles where we attempt JSON parsing
_JSON_ROLES = _API_JSON_ROLES | _PROMPT_JSON_ROLES


# ── Meta-tool ─────────────────────────────────────────────────────────────────

@tool
def agent(
    role:        str,
    task:        str,
    context:     str = "",
    content:     str = "",
    trace_id:    str = "",
    temperature: float = -1.0,   # -1 = use role default
    max_tokens:  int   = -1,     # -1 = use role default
) -> dict:
    """
    Agent tool — call a specialist sub-agent for a specific cognitive task.

    role: "classify" | "route" | "research" | "summarize" | "extract" |
          "critique" | "analyze" | "code" | "review" | "plan"

    task     : the instruction or question for this agent
    context  : background information (injected before the task)
    content  : raw material to process (code, text, data to analyse/summarise)
    trace_id : attach to current workflow trace for observability

    ── ROLES ────────────────────────────────────────────────────────────────────

    classify  [Nemotron, 15s]
        Fast binary or categorical decision.
        Returns a single word or short label — no prose.
        Use for: is_code_related, sentiment, topic category, yes/no decisions.
        Example:
            agent(role="classify",
                  task="Is this task about fixing code or writing new code?",
                  content="The function returns wrong values when input is empty")
            → "fixing"

    route  [Nemotron, 15s]
        Decide which workflow and tool to use for a task.
        Returns JSON: {workflow, tool, complexity, reason}
        Example:
            agent(role="route", task="Analyse the Q3 sales CSV and plot a chart")
            → {"workflow": "data", "tool": "python", "complexity": 5, "reason": "..."}

    research  [Hermes, 120s]
        Synthesise web pages, documents, or memory into a coherent answer.
        Preserves facts, cites sources, notes conflicts.
        Use after: web(search_and_read) or memory(recall)
        Example:
            agent(role="research",
                  task="Summarise what these sources say about ChromaDB performance",
                  content="[scraped text from 3 pages]")

    summarize  [Hermes, 60s]
        Condense long content into a dense accurate summary.
        Removes filler, preserves all key facts and numbers.
        Example:
            agent(role="summarize",
                  task="Summarise this into 3 bullet points",
                  content="[long document text]")

    extract  [Hermes, 60s]
        Pull structured data from unstructured text.
        Always returns JSON.
        Example:
            agent(role="extract",
                  task="Extract: company name, revenue, growth rate, CEO name",
                  content="[financial report text]")
            → {"company": "...", "revenue": "...", "growth_rate": "...", "ceo": "..."}

    critique  [Hermes, 90s]
        Evaluate quality against the stated goal. Harsh and specific.
        Returns verdict: APPROVE | REVISE | REJECT with specific issues.
        Example:
            agent(role="critique",
                  task="Does this patch correctly fix the memory decay bug?",
                  context="The bug: decay never applies to procedural memories",
                  content="[the patch]")

    analyze  [Hermes, 90s]
        Deep analysis of code, data, or a problem. Analysis only — no fixes yet.
        References exact line numbers, function names, variable names.
        Example:
            agent(role="analyze",
                  task="What is causing the timeout in this workflow?",
                  content="[workflow code]")

    code  [Hermes, 120s]
        Generate a Python patch or new code. Returns structured JSON:
        {analysis, patch, assumptions, tests}
        PEP 8 + type hints + docstrings enforced via system prompt.
        Use ONLY for generating code — then use 'review' to check it.
        Example:
            agent(role="code",
                  task="Fix the decay scoring — it currently ignores the floor value",
                  context="Function is in memory/store.py, _decay_score()",
                  content="[current function code]")

    review  [Hermes, 90s]
        Review a code patch for bugs, edge cases, breaking changes.
        Returns structured JSON: {verdict, issues, corrected_patch}
        Always run this after 'code' before applying any patch.
        Example:
            agent(role="review",
                  task="Review this patch for correctness and edge cases",
                  context="Goal: fix decay scoring in _decay_score()",
                  content="[the generated patch]")

    plan  [Qwen, 90s]
        Decompose a high-level goal into ordered agent steps.
        Returns structured JSON: {goal, steps, estimated_complexity, risks}
        Each step maps to a specific tool and action.
        Example:
            agent(role="plan",
                  task="Research Tesla stock performance and create a dashboard")
            → {"goal": "...", "steps": [...], "complexity": 7, "risks": [...]}

    ── STRUCTURED OUTPUT ROLES ───────────────────────────────────────────────────
    These roles always return JSON in result.parsed (in addition to result.text):
        route, extract, code, review, plan

    ── TEMPERATURE / MAX_TOKENS OVERRIDE ────────────────────────────────────────
    Leave at -1 to use role defaults (recommended).
    Override only when you have a specific reason:
        temperature=-1  → use role default (0.0 for router, 0.1 for code, etc.)
        max_tokens=-1   → use role default (256 for router, 4096 for code, etc.)
    """
    role = role.strip().lower()

    if role not in _ROLE_TO_LLM:
        return {
            "status": "error",
            "error": (
                f"Unknown role '{role}'. "
                "Use: classify | route | research | summarize | extract | "
                "critique | analyze | code | review | plan"
            ),
        }

    if not task:
        return {"status": "error", "error": "task is required"}

    system_prompt = _SYSTEM_PROMPTS[role]
    llm_role      = _ROLE_TO_LLM[role]
    # Only use API-level json_object enforcement for models that support it.
    # Nemotron (router/classify) rejects json_object — use prompt-only for those.
    json_mode     = role in _API_JSON_ROLES

    # Build call kwargs — only pass overrides if explicitly set
    call_kwargs: dict = {}
    if temperature >= 0:
        call_kwargs["temperature"] = temperature
    if max_tokens > 0:
        call_kwargs["max_tokens"] = max_tokens

    result = llm.complete(
        role      = llm_role,
        system    = system_prompt,
        user      = task,
        context   = context,
        content   = content,
        json_mode = json_mode,
        trace_id  = trace_id,
        **call_kwargs,
    )

    if not result.ok:
        return {
            "status":   "error",
            "role":     role,
            "error":    result.error,
            "elapsed":  result.elapsed,
            "model":    result.model,
        }

    response: dict = {
        "status":  "success",
        "role":    role,
        "text":    result.text,
        "model":   result.model,
        "elapsed": result.elapsed,
        "usage":   result.usage,
    }

    # Include parsed JSON for structured roles
    if role in _JSON_ROLES:
        if result.parsed is not None:
            # API json_mode parsed it already
            response["parsed"] = result.parsed
        else:
            # Prompt-only JSON role — try to parse the text ourselves
            import json as _json
            clean = result.text.strip()
            for fence in ("```json", "```"):
                if clean.startswith(fence):
                    clean = clean[len(fence):]
            clean = clean.strip().rstrip("`").strip()
            try:
                response["parsed"] = _json.loads(clean)
            except _json.JSONDecodeError:
                response["parse_warning"] = (
                    "Response was not valid JSON. "
                    "Use result.text and parse manually if needed."
                )

    return response
