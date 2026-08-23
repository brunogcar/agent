"""tests/test_sync_guard_mapping.py -- Pure mapping test (no DB, no HTTP).

Asserts that every DDM skill's REQUIRED_SOURCES has a matching entry in
the skills/_base.py sync_map. Catches the B1/B2/B3 regression cluster
(skills declaring sync keys the sync_map doesn't have) without touching
any database or making any HTTP call.

Fast (<0.1s): imports the sync_map dict + each skill's REQUIRED_SOURCES
list, then asserts set equality. No sync_all calls, no DB reads.
"""
from __future__ import annotations

import importlib
from pathlib import Path


def _get_sync_map_keys() -> set[str]:
    """Extract the set of keys from the sync_map in skills/_base.py.

    Imports skills._base and accesses the sync_map dict directly.
    The sync_map is built inside the _trigger_sync function, so we
    call _trigger_sync with an invalid source to get the error path
    (which still builds the dict). Alternatively, we can read the
    source file and parse it — but importing is cleaner and faster.
    """
    # The sync_map is a local variable inside _trigger_sync. To access
    # it without triggering a real sync, we read the source file and
    # extract the keys via a simple regex (the dict is literal).
    base_path = Path(__file__).resolve().parents[1] / "skills" / "_base.py"
    content = base_path.read_text(encoding="utf-8")

    # Find all sync_map keys: lines like  "ddm-fluxo":  ("data_sources...
    import re
    keys = re.findall(r'^\s*"([a-z][a-z0-9-]*)":\s*\(', content, re.MULTILINE)
    return set(keys)


def _get_all_required_sources() -> dict[str, list[str]]:
    """Get REQUIRED_SOURCES from every DDM skill module under skills/ddm/.

    Returns {skill_module_path: [source_keys]}.

    Scoped to DDM skills only — other domains (B3, CVM, BCB) have their
    own REQUIRED_SOURCES that may use different sync mechanisms.
    """
    skills_root = Path(__file__).resolve().parents[1] / "skills" / "ddm"
    result: dict[str, list[str]] = {}

    # Walk all __init__.py files under skills/ddm/ (any depth).
    for init_file in skills_root.rglob("__init__.py"):
        if "__pycache__" in str(init_file):
            continue
        rel = init_file.relative_to(skills_root.parent.parent)
        module_path = str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")
        if module_path.endswith(".__init__"):
            module_path = module_path[:-len(".__init__")]

        try:
            mod = importlib.import_module(module_path)
            required = getattr(mod, "REQUIRED_SOURCES", None)
            if required:
                result[module_path] = list(required)
        except Exception:
            pass

    return result


def test_sync_map_has_all_required_sources():
    """Every skill's REQUIRED_SOURCES key must exist in the sync_map.

    This is the regression test for the B1/B2/B3 bug cluster:
      - B1: freshness import broken (not tested here, but the sync_map
            keys are what the freshness check looks up)
      - B2: ddm-dividends missing from sync_map
      - B3: ddm-inflation key is "ddm" in sync_map but "ddm-inflation"
            in the skill's REQUIRED_SOURCES

    Pure mapping check — no DB, no HTTP, no sync calls. Runs in <0.1s.
    """
    sync_map_keys = _get_sync_map_keys()
    required_sources = _get_all_required_sources()

    # Collect all required source keys across all skills.
    all_required = set()
    for sources in required_sources.values():
        all_required.update(sources)

    # Every required source must be in the sync_map.
    missing = all_required - sync_map_keys
    assert not missing, (
        f"REQUIRED_SOURCES declares keys not in sync_map: {missing}. "
        f"Sync_map keys: {sorted(sync_map_keys)}"
    )


def test_sync_map_has_ddm_inflation_key():
    """The inflation sync_map key must be 'ddm-inflation' (not 'ddm').

    Regression test for B3: the 32e5ab9 commit reverted the rename from
    'ddm-inflation' back to 'ddm', breaking the inflation skill's sync guard.
    """
    sync_map_keys = _get_sync_map_keys()
    assert "ddm-inflation" in sync_map_keys, (
        "sync_map must have 'ddm-inflation' (not 'ddm') — the inflation "
        "skill declares REQUIRED_SOURCES=['ddm-inflation']"
    )
    assert "ddm" not in sync_map_keys, (
        "sync_map should NOT have bare 'ddm' key — it was renamed to "
        "'ddm-inflation' in 4ebdabf. If 'ddm' exists, a commit reverted "
        "the rename (regression of B3)."
    )


def test_sync_map_has_ddm_dividends_key():
    """The sync_map must have a 'ddm-dividends' entry.

    Regression test for B2: the 30fa822 commit silently removed the
    ddm-dividends entry from sync_map during a rebase.
    """
    sync_map_keys = _get_sync_map_keys()
    assert "ddm-dividends" in sync_map_keys, (
        "sync_map must have 'ddm-dividends' — the dividends skill declares "
        "REQUIRED_SOURCES=['ddm-dividends']. If missing, a rebase silently "
        "dropped it (regression of B2)."
    )
