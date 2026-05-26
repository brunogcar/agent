"""
core/contracts.py — Strict data contracts for inter-model communication.

Prevents silent failures from schema drift between Planner, Router, and Executor.
If a model outputs an outdated or malformed tool call, we catch it here immediately
instead of letting it crash downstream or execute the wrong action.
"""
from __future__ import annotations

from typing import Literal, Any
from pydantic import BaseModel, Field, ValidationError

# Bump this when you intentionally change the tool call structure
SCHEMA_VERSION = "1.0"


class ToolCall(BaseModel):
    """Validates tool call structure from LLM responses."""
    schema_version: Literal["1.0"] = Field(default="1.0", alias="_version")
    tool: str = Field(..., description="Tool name (memory, file, web, git, etc.)")
    action: str = Field(..., description="Action type (store, read, write, diff, etc.)")
    args: dict[str, Any] = Field(default_factory=dict, description="Tool-specific arguments")

    class Config:
        # Allows using either "schema_version" or "_version" in the JSON payload
        populate_by_name = True


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