"""
apply_phase9g_patches.py -- run from D:/mcp/agent/

Applies Phase 9g critical fixes:
  1. core/tracer.py:  bare except masks KeyboardInterrupt (Ctrl+C ignored)
  2. memory/store.py: dedup threshold 0.05 is backwards -- way too strict
  3. tools/web.py:    bare except masks KeyboardInterrupt in _fetch_html
"""

from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def patch(filepath: str, old: str, new: str, label: str) -> bool:
    p = ROOT / filepath
    if not p.exists():
        print(f"  SKIP  {label} -- file not found")
        return False
    content = p.read_text(encoding="utf-8")
    if old not in content:
        first_new_line = new.strip().splitlines()[0].strip()
        if first_new_line in content:
            print(f"  SKIP  {label} -- already applied")
            return True
        print(f"  MISS  {label} -- target not found in {filepath}")
        return False
    updated = content.replace(old, new)
    # Syntax check before writing
    try:
        ast.parse(updated)
    except SyntaxError as e:
        print(f"  FAIL  {label} -- syntax error after patch: {e}")
        return False
    p.write_text(updated, encoding="utf-8")
    print(f"  OK    {label}")
    return True


print("=== Phase 9g patches ===\n")

# ── 1. core/tracer.py: bare except masks Ctrl+C ──────────────────────────────
# The _FileWriter.write() method swallows ALL exceptions including
# KeyboardInterrupt. This means Ctrl+C to stop the agent is silently ignored
# while the agent is writing a log entry.
patch(
    "core/tracer.py",
    '''    def write(self, record: dict) -> None:
        with self._lock:
            try:
                f = self._get_file()
                f.write(json.dumps(record, ensure_ascii=False) + "\\n")
                f.flush()
            except Exception:
                pass  # never crash the agent over a log write''',
    '''    def write(self, record: dict) -> None:
        with self._lock:
            try:
                f = self._get_file()
                f.write(json.dumps(record, ensure_ascii=False) + "\\n")
                f.flush()
            except (KeyboardInterrupt, SystemExit):
                raise  # never suppress shutdown signals
            except Exception:
                pass  # non-fatal I/O errors silently ignored''',
    "tracer: KeyboardInterrupt propagates through file writer",
)

# ── 2. memory/store.py: dedup threshold 0.05 too aggressive ──────────────────
# Cosine distance 0.05 means documents must be 95%+ identical to be skipped.
# That's correct for preventing near-exact duplicates.
# BUT the report says this is "backwards" -- it's not. 0.05 is a tight
# threshold that only skips near-identical text. However, per-collection
# tuning makes sense: episodic memories (event logs) should allow more
# near-duplicates through than procedural (reusable patterns).
#
# Real fix: make the threshold configurable and per-collection so the
# agent can tune it via .env rather than hardcoding 0.05 everywhere.
patch(
    "memory/store.py",
    '''        try:
            existing = col.query(query_texts=[text], n_results=1,
                                 include=["documents", "distances"])
            docs      = existing.get("documents", [[]])[0]
            distances = existing.get("distances", [[]])[0]
            if docs and distances and distances[0] < 0.05:
                return {"status": "skipped_duplicate", "collection": collection}
        except Exception:
            pass  # dedup failure is non-fatal -- store anyway''',
    '''        # Per-collection dedup thresholds (cosine distance, lower = more similar):
        #   episodic:   0.05 -- only skip near-identical event logs
        #   semantic:   0.12 -- skip very similar facts (same topic/phrasing)
        #   procedural: 0.08 -- skip near-identical fix patterns
        # Configurable via MEMORY_DEDUP_THRESHOLD in .env (overrides all)
        _default_thresholds = {
            COLLECTION_EPISODIC:   0.05,
            COLLECTION_SEMANTIC:   0.12,
            COLLECTION_PROCEDURAL: 0.08,
        }
        _dedup_thresh = float(
            __import__("os").getenv("MEMORY_DEDUP_THRESHOLD", "")
            or _default_thresholds.get(collection, 0.08)
        )
        try:
            existing = col.query(query_texts=[text], n_results=1,
                                 include=["documents", "distances"])
            docs      = existing.get("documents", [[]])[0]
            distances = existing.get("distances", [[]])[0]
            if docs and distances and distances[0] < _dedup_thresh:
                return {"status": "skipped_duplicate", "collection": collection}
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass  # dedup failure is non-fatal -- store anyway''',
    "memory: per-collection dedup thresholds + KeyboardInterrupt propagation",
)

# ── 3. tools/web.py: bare except in _fetch_html masks Ctrl+C ─────────────────
patch(
    "tools/web.py",
    '''    except Exception as e:
        return "", f"{type(e).__name__}: {e}"''',
    '''    except (KeyboardInterrupt, SystemExit):
        raise  # never suppress shutdown signals
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"''',
    "web: KeyboardInterrupt propagates through _fetch_html",
)

print("\nDone. Run: python verify_phase9g.py to confirm.")
