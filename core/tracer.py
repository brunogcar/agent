"""core/tracer.py — Thin facade for the tracer singleton.

The actual Tracer implementation lives in core/observability/tracer_engine.py.
This facade exists to maintain the stable `from core.tracer import tracer`
import pattern used by 71+ files across the codebase.

EXTRACTION NOTE: Tracer implementation moved to core/observability/ in v1.3.
"""
from __future__ import annotations

# Re-export all module-level public + private names that any caller (incl. tests)
# imports from this path. The tracer_engine module is the source of truth.
from core.observability.tracer_engine import (
    _HAS_STRUCTLOG,
    _FileWriter,
    _TraceStore,
    _configure_structlog,
    _log,
    _store,
    _writer,
    Tracer,
    generate_trace_id,
)

# Singleton — instantiated here so patch("core.tracer._writer") and
# patch("core.tracer.tracer") in tests still target the names callers
# actually use. tracer_engine also has its own tracer singleton, but
# every callsite imports from core.tracer, so the canonical name lives here.
tracer = Tracer()
