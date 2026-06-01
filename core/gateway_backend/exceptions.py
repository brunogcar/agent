"""
core/gateway_backend/exceptions.py — Custom domain exceptions for the Gateway.

EXTRACTION NOTE (Gateway Phase 2): Replaces generic HTTPExceptions and manual
try/except blocks in routes. Global handlers in factory.py catch these to 
ensure consistent JSON error contracts and tracer logging.
"""
from __future__ import annotations

class TaskNotFoundError(Exception):
    """Raised when a trace_id is not found in the SQLite store or tracer."""
    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        super().__init__(f"trace_id '{trace_id}' not found")

class ToolExecutionError(Exception):
    """Raised when a tool or workflow fails during dispatch."""
    def __init__(self, trace_id: str, tool: str, error: str):
        self.trace_id = trace_id
        self.tool = tool
        self.error = error
        super().__init__(f"Tool '{tool}' failed: {error}")