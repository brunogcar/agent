"""workflow_ops — Workflow management subpackage.

Two-level dispatch:
  - actions/  — META-level: what to do (run, list, status, cancel, history).
  - types/    — WORKFLOW-TYPE-level: which workflow to run (research, data,
                autocode, deep_research, understand, autoresearch, auto).

Auto-discovery is triggered by importing the actions and types subpackages
— each one's __init__.py globs its directory and imports all .py files,
which runs their @register_action / @register_type decorators.

The `run` action handler dispatches into TYPE_DISPATCH[type]["func"]; the
other actions (list, status, cancel, history) are leaf operations that
don't need a type.

[DESIGN] WHY AUTO-DISCOVERY for both levels: every action AND type module
must be imported so its decorator runs. Hardcoding imports would create a
maintenance footgun (forgetting to add a new action/type = silent omission
from the Literal enum + "Unknown action" at runtime). Globbing keeps the
registration list authoritative — adding a new file is the only change.
"""
from __future__ import annotations

from . import _registry  # noqa: F401 — ensures DISPATCH exists before actions populate it
from . import _type_registry  # noqa: F401 — ensures TYPE_DISPATCH exists before types populate it

# Importing actions/ and types/ triggers their respective auto-discovery loops.
from . import actions  # noqa: F401 — triggers action auto-discovery
from . import types    # noqa: F401 — triggers type auto-discovery
