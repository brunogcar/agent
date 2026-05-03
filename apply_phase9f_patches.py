"""
apply_phase9f_patches.py -- run from D:/mcp/agent/

Applies all Phase 9f improvements to the existing codebase in-place.
Safe to run multiple times -- each patch is idempotent.

Changes:
  1. gateway/app.py:        dev-mode security warning on startup
  2. memory/store.py:       adaptive fetch multiplier, procedural prune doc fix
  3. workflows/autocode.py: exponential backoff on retry
  4. core/config.py:        expand protected_files set
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
results = []

def patch(filepath: str, old: str, new: str, label: str) -> bool:
    p = ROOT / filepath
    if not p.exists():
        print(f"  SKIP  {label} -- file not found: {filepath}")
        return False
    content = p.read_text(encoding="utf-8")
    if old not in content:
        if new.split("\n")[0].strip() in content:
            print(f"  SKIP  {label} -- already applied")
            return True
        print(f"  MISS  {label} -- target text not found in {filepath}")
        return False
    p.write_text(content.replace(old, new), encoding="utf-8")
    print(f"  OK    {label}")
    return True


print("=== Phase 9f patches ===\n")

# ── 1. gateway/app.py: dev-mode warning ──────────────────────────────────────
patch(
    "gateway/app.py",
    '''        secret = (cfg.gateway_secret or "").strip() or "changeme"
        if secret != "changeme":
            if not creds or creds.credentials != secret:
                raise HTTPException(status_code=401, detail="Unauthorized")''',
    '''        secret = (cfg.gateway_secret or "").strip() or "changeme"
        if secret == "changeme":
            # Warn once per request in dev mode -- makes it visible in logs
            print("[SECURITY] Gateway in DEVELOPMENT MODE -- set GATEWAY_SECRET in .env",
                  file=sys.stderr)
        elif not creds or creds.credentials != secret:
            raise HTTPException(status_code=401, detail="Unauthorized")''',
    "gateway: dev-mode security warning",
)

# ── 2. memory/store.py: adaptive fetch multiplier ────────────────────────────
patch(
    "memory/store.py",
    "        fetch_k   = max(top_k * 4, 20)  # fetch more, then filter + rank",
    '''        # Adaptive fetch multiplier -- smaller for large top_k to avoid over-fetching
        # top_k=5 -> multiplier=4 (fetch 20), top_k=20 -> multiplier=2 (fetch 40)
        fetch_multiplier = max(2, 5 - top_k // 5)
        fetch_k = max(top_k * fetch_multiplier, 15)''',
    "memory: adaptive fetch multiplier",
)

# ── 3. memory/store.py: procedural prune doc clarification ───────────────────
patch(
    "memory/store.py",
    '''        Procedural collection is always protected — it\'s the most valuable collection.
        Memories tagged "summary", "critical", or "protected" are also safe.''',
    '''        Procedural collection is protected from AUTOMATIC pruning (max_age_days/
        min_importance). It can still be pruned if explicitly included in the
        collections= parameter -- this is intentional for manual maintenance.
        Memories tagged "summary", "critical", or "protected" are always safe.''',
    "memory: procedural prune documentation clarified",
)

# ── 4. workflows/autocode.py: exponential backoff on retry ───────────────────
patch(
    "workflows/autocode.py",
    '''def increment_retry(state: WorkflowState) -> WorkflowState:
    """Increment retry counter before looping back."""
    return {**state, "retries": state.get("retries", 0) + 1}''',
    '''def increment_retry(state: WorkflowState) -> WorkflowState:
    """Increment retry counter with exponential backoff before looping back."""
    import time
    retries = state.get("retries", 0)
    # Exponential backoff: retry 1=2s, retry 2=4s, retry 3=8s
    # Prevents hammering the model and file locks on repeated failures
    if retries > 0:
        delay = min(2 ** retries, 30)  # cap at 30s
        print(f"[autocode] retry {retries + 1} -- waiting {delay}s before next attempt",
              file=__import__("sys").stderr)
        time.sleep(delay)
    return {**state, "retries": retries + 1}''',
    "autocode: exponential backoff on retry",
)

# ── 5. core/config.py: expand protected_files ────────────────────────────────
patch(
    "core/config.py",
    '''        self.protected_files: frozenset[str] = frozenset({
            "server.py", "registry.py", "core/config.py", "core/tracer.py",
        })''',
    '''        self.protected_files: frozenset[str] = frozenset({
            "server.py", "registry.py",
            "core/config.py", "core/tracer.py",
            "core/llm.py",       # model dispatch -- corruption breaks all AI calls
            "memory/store.py",   # memory backend -- corruption breaks all recall
            "gateway/app.py",    # contains auth logic and secrets handling
        })''',
    "config: expand protected_files set",
)

print("\nDone. Run: python verify_phase9f.py to confirm.")
