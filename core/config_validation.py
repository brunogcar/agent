"""Backwards compat shim — use core.config_backend.validation instead.

[v1.0] The actual implementation moved to core/config_backend/validation.py
as part of the config_backend split. This shim preserves the historical
import path used by server.py and existing tests:

    from core.config_validation import validate_config

NOTE: This shim re-exports ONLY ``validate_config``. The pre-v1.0 module
also exposed ``cfg`` and ``tracer`` as module-level names (imported for its
own use). Tests that previously patched ``core.config_validation.cfg`` or
``core.config_validation.tracer`` must now patch
``core.config_backend.validation.cfg`` / ``core.config_backend.validation.tracer``
instead — the function looks up those names in its defining module's globals.
"""
from core.config_backend.validation import validate_config

__all__ = ["validate_config"]
