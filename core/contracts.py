"""core/contracts.py — Strict data contracts for inter-model communication.

Prevents silent failures from schema drift between Planner, Router, and Executor.
If a model outputs an outdated or malformed tool call, we catch it here immediately
instead of letting it crash downstream or execute the wrong action.

v1.2: Added error_code parameter to fail() for structured error classification.
"""
from __future__ import annotations

from typing import Literal, Any, TypedDict, Optional
from pydantic import BaseModel, Field, ValidationError, ConfigDict

SCHEMA_VERSION = "1.0"


class ToolCall(BaseModel):
    """Validates tool call structure from LLM responses."""
    schema_version: Literal["1.0"] = Field(default="1.0", alias="_version")
    tool: str = Field(..., description="Tool name (memory, file, web, git, etc.)")
    action: str = Field(..., description="Action type (store, read, write, diff, etc.)")
    args: dict[str, Any] = Field(default_factory=dict, description="Tool-specific arguments")

    model_config = ConfigDict(populate_by_name=True)


def validate_tool_call(payload: dict) -> ToolCall:
    """Validate tool call against current schema version."""
    if "_version" not in payload and "schema_version" not in payload:
        payload["_version"] = SCHEMA_VERSION
    return ToolCall.model_validate(payload)


class ToolResult(TypedDict, total=False):
    """Standard return schema for ALL tools."""
    status: Literal["success", "error", "routed", "needs_clarification", "sent", "scheduled"]
    data: Optional[Any]
    error: Optional[str]
    trace_id: Optional[str]
    error_code: Optional[str]  # v1.2: Structured error classification
    model: Optional[str]
    elapsed: Optional[float]
    usage: Optional[dict]


def ok(data: Any, trace_id: str = "", status: str = "success", **meta) -> dict:
    """Construct a standardized success response."""
    result: dict = {"status": status, "data": data, "error": None}
    if trace_id:
        result["trace_id"] = trace_id
    result.update(meta)
    return result


def fail(error: str, trace_id: str = "", status: str = "error", error_code: str = "", **meta) -> dict:
    """Construct a standardized error response.

    v1.2: Added error_code for programmatic error classification.
          Standard codes: TIMEOUT, CONNECT_ERROR, RATE_LIMITED, SERVER_ERROR,
          CLIENT_ERROR, AUTH_FAILED, QUOTA_EXHAUSTED, INVALID_ACTION,
          INTERNAL_ERROR, UNKNOWN
    """
    result: dict = {"status": status, "data": None, "error": error}
    if trace_id:
        result["trace_id"] = trace_id
    if error_code:
        result["error_code"] = error_code
    result.update(meta)
    return result
