"""
core/contracts.py — Strict data contracts for inter-model communication.

Prevents silent failures from schema drift between Planner, Router, and Executor.
If a model outputs an outdated or malformed tool call, we catch it here immediately
instead of letting it crash downstream or execute the wrong action.
"""
from __future__ import annotations

from typing import Literal, Any, TypedDict, Optional
from pydantic import BaseModel, Field, ValidationError, ConfigDict

# Bump this when you intentionally change the tool call structure
SCHEMA_VERSION = "1.0"


class ToolCall(BaseModel):
    """Validates tool call structure from LLM responses."""
    schema_version: Literal["1.0"] = Field(default="1.0", alias="_version")
    tool: str = Field(..., description="Tool name (memory, file, web, git, etc.)")
    action: str = Field(..., description="Action type (store, read, write, diff, etc.)")
    args: dict[str, Any] = Field(default_factory=dict, description="Tool-specific arguments")

    model_config = ConfigDict(populate_by_name=True)


def validate_tool_call(payload: dict) -> ToolCall:
    """
    Validate tool call against current schema version.
    
    Raises ValidationError if payload doesn't match expected structure.
    This prevents silent failures from model version drift or schema incompatibility.
    """
    # Inject default version if the LLM forgot to include it (backward compatibility)
    if "_version" not in payload and "schema_version" not in payload:
        payload["_version"] = SCHEMA_VERSION
        
    return ToolCall.model_validate(payload)

# ── ToolResult Standard Schema ───────────────────────────────────────────────
# Every tool must return a dict matching this shape.

class ToolResult(TypedDict, total=False):
    """
    Standard return schema for ALL tools.
    """
    status: Literal["success", "error", "routed", "needs_clarification", "sent", "scheduled"]
    data: Optional[Any]           # Primary payload
    error: Optional[str]         # Error message if status != "success"
    trace_id: Optional[str]      # Always include for observability
    model: Optional[str]         # LLM model used
    elapsed: Optional[float]     # Execution time in seconds
    usage: Optional[dict]       # Token usage


def ok(data: Any, trace_id: str = "", **meta) -> dict:
    """Construct a standardized success response."""
    result: dict = {"status": "success", "data": data, "error": None}
    if trace_id:
        result["trace_id"] = trace_id
    result.update(meta)
    return result


def fail(error: str, trace_id: str = "", **meta) -> dict:
    """Construct a standardized error response."""
    result: dict = {"status": "error", "data": None, "error": error}
    if trace_id:
        result["trace_id"] = trace_id
    result.update(meta)
    return result

