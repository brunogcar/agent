"""skills/cvm/historical/metrics/__init__.py -- Auto-discovery for ratio metrics.

Auto-discovers all metric modules in this directory at import time via
glob + importlib. Each module self-registers via `register_metric()` in
`_registry.py` at import time.

Adding a new metric = drop a file in this directory + call register_metric().
No edits to __init__.py, historical.py, or __init__.py needed.

METRIC VS ENGINE — READ THIS
----------------------------
- ENGINES (in engines/): one per RAW QUANTITY. Each engine fetches ONE basic
  number at any historical date from its data source(s). Engines are leaves.
- METRICS (here): one per RATIO. A metric imports 2+ engines and combines them.
  Each metric produces BOTH a per-share value AND a price ratio:
    - lpa.py: LPA (earnings/shares) + P/L (price/LPA)
    - vpa.py: VPA (pl/shares) + P/VPA (price/VPA)

To add a new METRIC:
  1. Confirm the engines you need already exist. If not, add the ENGINE first.
  2. Create metrics/<name>.py with:
     - <name>_at(company, date) -> per-share value
     - <ratio>_at(company, date) -> price ratio
     - <name>_history(company, date_from, date_to) -> list[dict]
  3. Call register_metric(MetricSpec(...)) at module level.
  4. That's it. The MANIFEST modes, ratio_history() dispatch, and summary()
     metric-awareness all auto-generate from the registry.
  5. Add a report adapter in tools/report_ops/adapters/historical.py if you
     want chart/table rendering.
  6. Add tests in tests/skills/cvm/historical/test_<name>.py.
"""
from __future__ import annotations

import importlib
from pathlib import Path

# Auto-discover and import all metric modules (triggers register_metric calls)
for py_file in sorted(Path(__file__).parent.glob("*.py")):
    if py_file.name not in ("__init__.py", "_registry.py"):
        module_name = f"skills.cvm.historical.metrics.{py_file.stem}"
        importlib.import_module(module_name)

# Re-export registry functions for convenient access
from skills.cvm.historical.metrics._registry import (  # noqa: E402,F401
    MetricSpec,
    METRICS,
    register_metric,
    resolve_metric,
    list_metrics,
    list_all_names,
)
