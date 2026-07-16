"""core/llm_backend/tools.py — Tool definitions for native LLM tool calling. (v1.4)

Provides ``ToolDefinition`` (the internal, provider-agnostic format) and
generators that build tool definitions from the ``@meta_tool`` registry.
Each provider adapter converts ``ToolDefinition`` → its native format
(OpenAI ``tools``, Anthropic ``tools``, Gemini ``functionDeclarations``).

[DESIGN] KEY DECISIONS — read before modifying:

  1. ONE TOOL DEFINITION PER META-TOOL, not per atomic action. The 18
     ``@meta_tool`` facades become 18 tool definitions — not 130. The
     action list goes in the ``description``; ``action`` is an ``enum``
     in the parameters schema. The LLM returns ``{action: "read_file",
     path: "..."}`` — a flat dict, same shape as today's dispatch.

  2. PARAMETERS SCHEMA IS DELIBERATELY LOOSE. The ``parameters`` JSON Schema
     has ``action`` as an enum + ``additionalProperties: true`` (the default).
     We do NOT try to express the union of 25 actions' params in JSON Schema
     — that's impossible to validate and would lie about what's allowed.
     The description carries the per-action param docs (generated from
     ``__tool_metadata__["dispatch"][action]["help"]``).

  3. PROVIDER ADAPTERS DO THE CONVERSION. ``ToolDefinition`` is internal;
     providers convert to their native format in their ``chat_completion()``
     when they receive a ``tools`` kwarg. This keeps the loop code
     provider-agnostic (it only sees ``ToolCall`` objects).

  4. ACTION-LEVEL FILTERING. ``tool_def_from_meta_tool()`` accepts an
     ``allowed_actions`` frozenset — if provided, the enum is filtered to
     only those actions. This is how the subagent's
     ``_ALLOWED_SUBAGENT_ACTIONS`` security boundary is preserved: the LLM
     only sees the actions it's allowed to call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolDefinition:
    """Provider-agnostic tool definition for native LLM tool calling.

    Providers convert this to their native format:
      - OpenAI:      ``{"type":"function","function":{"name","description","parameters"}}``
      - Anthropic:   ``{"name","description","input_schema"}``
      - Gemini:      ``{"functionDeclarations":[{"name","description","parameters"}]}``

    Attributes:
        name: Tool name (e.g. ``"file"``, ``"web"``). Must match the
              ``@tool``-decorated function name in ``tools/``.
        description: Human-readable description including the action list
                     + per-action help text. This is what the LLM reads to
                     decide which action to call + what params to pass.
        parameters: JSON Schema dict. Has ``action`` as an ``enum`` + allows
                    additional properties (the action-specific params).
    """
    name: str
    description: str
    parameters: dict


def _build_description(tool_name: str, meta: dict, allowed_actions: Optional[frozenset]) -> str:
    """Build the description string from __tool_metadata__.

    Includes the action list (filtered to ``allowed_actions`` if provided) +
    per-action help text (first line, truncated to 120 chars). This is what
    tells the LLM which actions are available + what params each takes.
    """
    dispatch = meta.get("dispatch", {})
    all_actions = meta.get("actions", [])
    if allowed_actions is not None:
        actions = [a for a in all_actions if a in allowed_actions]
    else:
        actions = all_actions

    lines = [f"{tool_name} meta-tool — {len(actions)} actions.", ""]
    for action_name in actions:
        info = dispatch.get(action_name, {})
        help_text = info.get("help", "").strip().split("\n")[0][:120]
        if help_text:
            lines.append(f"  {action_name}: {help_text}")
        else:
            lines.append(f"  {action_name}")
    lines.append("")
    lines.append(
        f"Call with: {{\"action\": \"<action_name>\", ...action_params}}. "
        f"The 'action' field selects the behavior; other fields are the "
        f"action's parameters (see each action's help text above)."
    )
    desc = "\n".join(lines)
    # v1.4.2: Truncate to stay within provider description limits
    # (Anthropic ~1024 chars practical, OpenAI ~4K). 2000 is a safe middle ground.
    if len(desc) > 2000:
        desc = desc[:1990] + "\n... (truncated)"
    return desc


def _build_parameters(meta: dict, allowed_actions: Optional[frozenset]) -> dict:
    """Build the JSON Schema parameters dict.

    The ``action`` field is an ``enum`` (filtered to ``allowed_actions`` if
    provided). Additional properties are allowed (the action-specific params
    that can't be expressed in a single schema).
    """
    all_actions = meta.get("actions", [])
    if allowed_actions is not None:
        actions = [a for a in all_actions if a in allowed_actions]
    else:
        actions = all_actions

    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": actions,
                "description": "The action to perform.",
            },
        },
        "required": ["action"],
        # additionalProperties defaults to true — the action-specific params
        # (path, query, code, etc.) flow through without schema validation.
        # The provider doesn't reject them; the tool's dispatch layer validates.
    }


def tool_def_from_meta_tool(
    tool_name: str,
    fn: Any,
    allowed_actions: Optional[frozenset] = None,
) -> Optional[ToolDefinition]:
    """Build a ToolDefinition from a @meta_tool-decorated function.

    Args:
        tool_name: The tool's name (e.g. ``"file"``).
        fn: The registered function (must have ``__tool_metadata__``).
        allowed_actions: Optional frozenset of action names to include in the
                         enum. If None, all actions are included. Used by the
                         subagent to enforce its ``_ALLOWED_SUBAGENT_ACTIONS``
                         security boundary.

    Returns None if ``fn`` has no ``__tool_metadata__`` (not a meta-tool —
    shouldn't be passed to ``complete_with_tools()``).
    """
    meta = getattr(fn, "__tool_metadata__", None)
    if meta is None:
        return None

    return ToolDefinition(
        name=tool_name,
        description=_build_description(tool_name, meta, allowed_actions),
        parameters=_build_parameters(meta, allowed_actions),
    )


def tool_def_from_registry(
    tool_names: list[str],
    allowed_actions_map: Optional[dict[str, frozenset]] = None,
) -> list[ToolDefinition]:
    """Build ToolDefinitions for multiple tools from the registry.

    Args:
        tool_names: List of tool names to include (e.g. ``["file", "web"]``).
        allowed_actions_map: Optional ``{tool_name: frozenset(actions)}`` to
                             filter each tool's action enum. Tools not in the
                             map get all actions.

    Returns a list of ToolDefinition objects (one per tool_name that has
    ``__tool_metadata__``). Unknown tools / non-meta-tools are silently
    skipped (return fewer entries than requested).
    """
    # Lazy import to avoid circular import at module load (registry imports
    # nothing from llm_backend, but llm_backend might be imported early).
    from registry import _registered_tool_fns

    allowed_actions_map = allowed_actions_map or {}
    defs: list[ToolDefinition] = []
    for name in tool_names:
        fn = _registered_tool_fns.get(name)
        if fn is None:
            continue
        allowed = allowed_actions_map.get(name)
        td = tool_def_from_meta_tool(name, fn, allowed)
        if td is not None:
            defs.append(td)
    return defs



# ── Provider format converters ───────────────────────────────────────────────
# Each provider's chat_completion() calls the matching converter to transform
# list[ToolDefinition] → the provider's native tools format.

def to_openai_tools(defs: list[ToolDefinition]) -> list[dict]:
    """Convert to OpenAI ``tools`` format.

    OpenAI: ``[{"type":"function","function":{"name","description","parameters"}}]``
    Used by: OpenAI-compatible providers (OpenAI, DeepSeek, Mistral, Qwen, Kimi,
    Z.ai, MiMo) + LM Studio.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": td.name,
                "description": td.description,
                "parameters": td.parameters,
            },
        }
        for td in defs
    ]


def to_anthropic_tools(defs: list[ToolDefinition]) -> list[dict]:
    """Convert to Anthropic ``tools`` format.

    Anthropic: ``[{"name","description","input_schema"}]``
    Note: Anthropic calls JSON Schema ``input_schema`` (not ``parameters``).
    """
    return [
        {
            "name": td.name,
            "description": td.description,
            "input_schema": td.parameters,
        }
        for td in defs
    ]


def to_gemini_tools(defs: list[ToolDefinition]) -> list[dict]:
    """Convert to Gemini ``tools`` format.

    Gemini: ``{"functionDeclarations":[{"name","description","parameters"}]}``
    Note: Gemini wraps the list in a ``functionDeclarations`` key. The caller
    passes ``[this_dict]`` as the ``tools`` field in the payload. Returns an
    empty list for empty input (so the provider doesn't add an empty tools key).
    """
    if not defs:
        return []
    return [
        {
            "functionDeclarations": [
                {
                    "name": td.name,
                    "description": td.description,
                    "parameters": td.parameters,
                }
                for td in defs
            ]
        }
    ]
