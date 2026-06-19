"""tools/agent.py — Agent meta-tool (thin @tool facade).

Replaces: tools/agent_tool.py (monolithic)
Split into: agent_core/prompts.py, agent_core/roles.py, agent_core/context.py

The LLM sees ONE tool: agent(role, task, ...)
All prompts, role config, and context trimming live in agent_core/.

Architecture:
  1. Validate inputs (role exists, task non-empty)
  2. Vision role → delegate to tools.vision.vision() (multimodal, not text LLM)
  3. Lookup system prompt + LLM role from agent_core/ modules
  4. Trim context + content via agent_core.context._trim_context()
  5. Call llm.complete() with role-specific model, timeout, json_mode
  6. Parse JSON for structured-output roles (extract, route, plan, code, review)
  7. Compress and return result dict

JSON Parsing:
  - API json_mode: extract role (model enforces JSON schema)
  - Prompt-only JSON: route, plan, code, review (parsed post-hoc with brace-counting fallback)
  - Non-JSON: classify, research, summarize, critique, analyze, consultor
"""
from __future__ import annotations

import json as _json
import re as _re

from registry import tool
from core.llm import llm
from core.utils import compress_result
from core.config import cfg

from tools.agent_core.prompts import _SYSTEM_PROMPTS
from tools.agent_core.roles import _ROLE_TO_LLM, _API_JSON_ROLES, _JSON_ROLES
from tools.agent_core.context import _trim_context

# Module-level flags
PARALLEL_SAFE = False

@tool
def agent(
    role: str,
    task: str,
    context: str = "",
    content: str = "",
    trace_id: str = "",
    temperature: float = -1.0,
    max_tokens: int = -1,
) -> dict:
    """
    Agent tool — call a specialist sub-agent for a specific cognitive task.

    role: "classify" | "route" | "research" | "summarize" | "extract" |
          "critique" | "analyze" | "code" | "review" | "plan" | "consultor" | "vision"

    task    : the instruction or question for this agent
    context : background information (injected before the task)
              for vision: file_path or public URL to the image
    content : raw material to process (code, text, data, or base64 image)
              for vision: base64-encoded image string
    trace_id: attach to current workflow trace for observability

    ── ROLES ────────────────────────────────────────────────────────────────────

    classify [Router, 15s]  Fast binary/category decision. Single word output.
    route    [Router, 15s]  Workflow + tool routing. Returns JSON.
    research [Executor,120s] Synthesise web/memory content into coherent answer.
    summarize[Executor, 60s] Dense accurate summary. No preamble.
    extract  [Executor, 60s] Pull structured data. Always returns JSON.
    critique [Executor, 90s] Quality evaluation. APPROVE|REVISE|REJECT verdict.
    analyze  [Executor, 90s] Deep code/data analysis. No fixes — analysis only.
    code     [Executor,120s] Generate Python patch. Returns {analysis,patch,tests}.
    review   [Executor, 90s] Review patch. Returns {verdict,issues,corrected_patch}.
    plan     [Planner, 90s]  Decompose goal into ordered steps. Returns JSON.
    consultor[Consultor,60s] Expert advisory on architecture, best practices, or pitfalls.
    vision   [Planner, 60s]  Analyse an image. Delegates to tools/vision.py.
               context= file_path or URL, content= base64 string.

    ── STRUCTURED OUTPUT ROLES ───────────────────────────────────────────────────
    These roles always return JSON in result["parsed"]:
      route, extract, code, review, plan
    """
    role = role.strip().lower()

    all_roles = set(_ROLE_TO_LLM.keys()) | {"vision"}
    if role not in all_roles:
        return {
            "status": "error",
            "error": (
                f"Unknown role '{role}'. "
                "Use: classify | route | research | summarize | extract | "
                "critique | analyze | code | review | plan | consultor | vision"
            ),
        }

    if not task:
        return {"status": "error", "error": "task is required"}

    # ── Vision: delegate to tools/vision.py ──────────────────────────────────
    # Vision cannot go through llm.complete() because multimodal messages
    # require a list content block (image_url + text), not a string.
    # tools/vision.py owns all image encoding and message construction.
    # Convention: context= for file_path/URL, content= for base64.
    if role == "vision":
        try:
            from tools.vision import vision as _vision
        except ImportError:
            return {
                "status": "error",
                "error": "tools/vision.py not found — ensure it exists and has @tool decorator.",
            }

        file_path = ""
        url = ""
        b64 = ""

        if context:
            if context.startswith(("http://", "https://")):
                url = context
            elif context.startswith("data:"):
                b64 = context
            else:
                file_path = context

        if content and not b64 and not file_path and not url:
            b64 = content

        # vision() uses "task=" for the instruction (not "prompt=")
        return _vision(
            task = task,
            file_path = file_path,
            base64 = b64,
            url = url,
            trace_id = trace_id,
            context = "",
        )

    system_prompt = _SYSTEM_PROMPTS[role]
    llm_role = _ROLE_TO_LLM[role]
    # Only use API-level json_object enforcement for models that support it.
    # The Router (classify) rejects json_object — use prompt-only for those.
    json_mode = role in _API_JSON_ROLES

    # Build call kwargs — only pass overrides if explicitly set
    call_kwargs: dict = {}
    if temperature >= 0:
        call_kwargs["temperature"] = temperature
    if max_tokens > 0:
        call_kwargs["max_tokens"] = max_tokens

    # Trim unbounded MCP conversation history before it reaches the LLM
    trimmed_context = _trim_context(context)
    trimmed_content = _trim_context(content, max_chars=4000)

    result = llm.complete(
        role = llm_role,
        system = system_prompt,
        user = task,
        context = trimmed_context,
        content = trimmed_content,
        json_mode = json_mode,
        trace_id = trace_id,
        **call_kwargs,
    )

    if not result.ok:
        return {
            "status": "error",
            "role": role,
            "error": result.error,
            "elapsed": result.elapsed,
            "model": result.model,
        }

    response: dict = {
        "status": "success",
        "role": role,
        "text": result.text,
        "model": result.model,
        "elapsed": result.elapsed,
        "usage": result.usage,
    }

    # Include parsed JSON for structured roles
    if role in _JSON_ROLES:
        if result.parsed is not None:
            # API json_mode parsed it already
            response["parsed"] = result.parsed
        else:
            # ── JSON extraction fallback ─────────────────────────────────────────
            # If the LLM wrapped JSON in prose or markdown fences, extract the
            # first complete JSON object. A naive regex like \{.*?\} breaks on
            # nested objects (e.g. {"a": {"b": 1}}). We use brace-counting that
            # respects string boundaries so nested JSON parses correctly.
            import json as _json
            clean = result.text.strip()
            for fence in ("```json", "```"):
                if clean.startswith(fence):
                    clean = clean[len(fence):]
                    clean = clean.strip().rstrip("`").strip()

            def _extract_first_json(text: str) -> str | None:
                """Extract first complete JSON object using brace counting."""
                start = text.find("{")
                if start == -1:
                    return None
                depth = 0
                in_string = False
                escape = False
                for i in range(start, len(text)):
                    c = text[i]
                    if escape:
                        escape = False
                        continue
                    if c == "\\":
                        escape = True
                        continue
                    if c == '"' and not escape:
                        in_string = not in_string
                        continue
                    if in_string:
                        continue
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            return text[start:i + 1]
                return None

            # Try clean parse first (fast path for well-behaved models)
            try:
                response["parsed"] = _json.loads(clean)
            except _json.JSONDecodeError:
                extracted = _extract_first_json(clean)
                if extracted:
                    try:
                        response["parsed"] = _json.loads(extracted)
                    except _json.JSONDecodeError:
                        response["parsed"] = {}
                        response["parse_warning"] = (
                            f"Extracted JSON was invalid for role '{role}'. "
                            "parsed={} returned. Check response.text for raw output."
                        )
                else:
                    response["parsed"] = {}
                    response["parse_warning"] = (
                        f"Response was not valid JSON for role '{role}'. "
                        "parsed={} returned. Check response.text for raw output."
                    )

    return compress_result(response)
