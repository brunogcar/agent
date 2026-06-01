"""
core/gateway_backend/models.py — Pydantic request/response schemas.

EXTRACTION NOTE (Gateway Phase 1): Extracted from core/gateway.py.
These MUST remain imported at the module level in the gateway facade/factory 
because of FastAPI's ForwardRef resolution requirements.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel

# ── Request/response models (Module-level to prevent ForwardRef issues) ────
# Because of `from __future__ import annotations`, FastAPI needs these
# in the global namespace to resolve the string annotations correctly.
# If these are hidden inside a function or lazy-loaded, FastAPI will fail to 
# generate the OpenAPI schema and throw a ForwardRef error at startup.

class TaskRequest(BaseModel):
    goal:     Optional[str]  = None
    workflow: Optional[str]  = "auto"
    tool:     Optional[str]  = None
    action:   Optional[str]  = None
    params:   Optional[dict] = None
    platform: Optional[str]  = "api"
    user:     Optional[str]  = None

class ChatRequest(BaseModel):
    message:  str
    platform: Optional[str] = "api"
    user:     Optional[str] = None

# ── Response Models (Phase 2 Step 3: Contract Locking) ──────────────
# These lock the API contract. FastAPI will automatically strip internal
# fields, validate the output, and generate perfect OpenAPI documentation.
from typing import Any, Literal

class TaskSubmitResponse(BaseModel):
    trace_id: str
    status: Literal["submitted"]
    poll_url: str

class TaskResultResponse(BaseModel):
    trace_id: str
    status: Literal["pending", "running", "success", "failed", "unknown"]
    result: Optional[Any] = None
    error: Optional[str] = None
    elapsed: float

class ChatResponse(BaseModel):
    trace_id: str
    status: Literal["success", "failed"]
    result: Optional[Any] = None
    error: Optional[str] = None
    platform: str