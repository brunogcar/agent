"""
apply_bugfix_patches.py — run from D:/mcp/agent/

Applies remaining bug fixes from the collaborative audit.
core/llm.py and gateway/app.py were delivered as full files (already replaced).

PATCHES IN THIS SCRIPT
-----------------------
1. memory/store.py  — P1-2: dedup check moved inside _write_lock
2. tools/web.py     — P1-1: per-request httpx.Client context manager
3. tools/git_ops.py — P1-6: rollback uses git stash instead of reset --hard
4. core/config.py   — M8:   validate positive ints for key tunables
5. tools/web.py     — M3:   0.5s delay between requests

Run: python apply_bugfix_patches.py
Then restart server.py
"""

from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT     = Path(__file__).resolve().parent
failures = 0


def patch(filepath: str, old: str, new: str, label: str) -> bool:
    p = ROOT / filepath
    if not p.exists():
        print(f"  SKIP  {label} -- file not found"); return False
    content = p.read_text(encoding="utf-8")
    if old not in content:
        first = new.strip().splitlines()[0].strip()
        if first in content:
            print(f"  SKIP  {label} -- already applied"); return True
        print(f"  MISS  {label} -- target not found in {filepath}"); return False
    updated = content.replace(old, new, 1)
    if filepath.endswith(".py"):
        try:
            ast.parse(updated)
        except SyntaxError as e:
            print(f"  FAIL  {label} -- syntax error: {e}"); return False
    p.write_text(updated, encoding="utf-8")
    print(f"  OK    {label}"); return True


print("=== Bugfix patches ===\n")


# ── 1. memory/store.py — P1-2: dedup inside write lock ───────────────────────
# PROBLEM: Similarity check ran OUTSIDE _write_lock. Two concurrent inserts
# both passed the check, then both inserted, creating duplicates in ChromaDB.
# FIX: Move the similarity query inside the lock so the check+insert is atomic.
# The lock is a threading.Lock() already present in store.py — we just move
# the query inside it. Minor performance cost (one extra query while locked)
# is acceptable vs silent data corruption.

failures += not patch(
    "memory/store.py",
    '''\
    def _store(self, collection_name: str, text: str, metadata: dict) -> str:
        """Internal: embed and store a memory entry with deduplication."""
        col = self._get_collection(collection_name)

        # Deduplication: skip if very similar entry already exists
        try:
            existing = col.query(query_texts=[text], n_results=1)
            if existing["distances"] and existing["distances"][0]:
                if existing["distances"][0][0] < 0.05:
                    return existing["ids"][0][0]
        except Exception:
            pass

        mem_id = str(uuid.uuid4())
        with self._write_lock:''',
    '''\
    def _store(self, collection_name: str, text: str, metadata: dict) -> str:
        """Internal: embed and store a memory entry with deduplication.

        P1-2 fix: dedup query is now INSIDE the write lock so the
        check+insert is atomic. Without this, two concurrent callers
        could both pass the similarity check and both insert, creating
        duplicates. Locking is coarse but correctness > throughput here.
        """
        col = self._get_collection(collection_name)
        mem_id = str(uuid.uuid4())
        with self._write_lock:
            # Deduplication inside the lock -- atomic check+insert
            try:
                existing = col.query(query_texts=[text], n_results=1)
                if existing["distances"] and existing["distances"][0]:
                    if existing["distances"][0][0] < 0.05:
                        return existing["ids"][0][0]
            except Exception:
                pass''',
    "memory/store.py: P1-2 dedup inside write lock",
)

# Close the with block properly -- the original code had the col.add inside
# the with block, so we just need to remove the old standalone lock line
failures += not patch(
    "memory/store.py",
    '''\
        mem_id = str(uuid.uuid4())
        with self._write_lock:
            col.add(''',
    '''\
            col.add(''',
    "memory/store.py: P1-2 remove duplicate with block",
)


# ── 2. tools/web.py — P1-1: per-request client ───────────────────────────────
# PROBLEM: Module-level _client leaks connections and is not thread-safe.
# FIX: Use a context-managed client per request. httpx.Client as a context
# manager guarantees connection cleanup even on exceptions.
# M3 (0.5s delay) is added in the scrape/read actions that loop over URLs.

failures += not patch(
    "tools/web.py",
    '''\
_client = httpx.Client(
    headers  = {"User-Agent": "Mozilla/5.0 MCP-Agent/1.0"},
    timeout  = httpx.Timeout(10.0),
    follow_redirects = True,
)''',
    '''\
# P1-1: No module-level client. Use per-request context manager instead.
# This fixes connection leaks and thread-safety (gateway runs multiple threads).
_CLIENT_DEFAULTS = {
    "headers":          {"User-Agent": "Mozilla/5.0 MCP-Agent/1.0"},
    "timeout":          httpx.Timeout(10.0),
    "follow_redirects": True,
}

def _make_client() -> httpx.Client:
    """Create a fresh httpx.Client. Always use as a context manager."""
    return httpx.Client(**_CLIENT_DEFAULTS)''',
    "tools/web.py: P1-1 remove module-level client, add _make_client()",
)

# Replace usages of _client.get() with context-managed client
# Search action
failures += not patch(
    "tools/web.py",
    '''\
        resp = _client.get(cfg.searxng_url, params={''',
    '''\
        with _make_client() as _client:
         resp = _client.get(cfg.searxng_url, params={''',
    "tools/web.py: P1-1 search uses context client",
)

# Scrape action — also add M3 rate-limit delay
failures += not patch(
    "tools/web.py",
    '''\
        resp = _client.get(url)''',
    '''\
        import time as _time
        _time.sleep(0.5)  # M3: polite delay between requests
        with _make_client() as _client:
         resp = _client.get(url)''',
    "tools/web.py: P1-1 scrape uses context client + M3 delay",
)


# ── 3. tools/git_ops.py — P1-6: rollback uses stash not reset --hard ─────────
# PROBLEM: git reset --hard HEAD permanently destroys uncommitted work.
# FIX: git stash is recoverable. The stash message includes a timestamp
# so the user can find and pop it if needed (git stash list).
# We keep reset --hard as an explicit "force" option for power users.

failures += not patch(
    "tools/git_ops.py",
    '''\
    if operation == "rollback":
        version = kwargs.get("version") or kwargs.get("target", "HEAD")
        try:
            subprocess.run(
                ["git", "-C", root, "reset", "--hard", version],
                check=True, capture_output=True,
            )
            return {"status": "success", "message": f"Rolled back to {version}"}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "error": e.stderr.decode()}''',
    '''\
    if operation == "rollback":
        """
        P1-6 fix: use git stash instead of git reset --hard.

        reset --hard permanently destroys uncommitted work with no recovery path.
        git stash saves the current state to the stash stack (recoverable via
        git stash pop or git stash list) before resetting.

        If force=True is passed, uses reset --hard (opt-in destructive mode).
        """
        version = kwargs.get("version") or kwargs.get("target", "HEAD")
        force   = kwargs.get("force", False)

        if force:
            try:
                subprocess.run(
                    ["git", "-C", root, "reset", "--hard", version],
                    check=True, capture_output=True,
                )
                return {"status": "success",
                        "message": f"Force rolled back to {version} (reset --hard)"}
            except subprocess.CalledProcessError as e:
                return {"status": "error", "error": e.stderr.decode()}

        # Safe default: stash first, then reset
        import time as _t
        stash_msg = f"autocode-rollback-{int(_t.time())}"
        try:
            # Stash any uncommitted changes (recoverable)
            stash_result = subprocess.run(
                ["git", "-C", root, "stash", "push", "-m", stash_msg],
                capture_output=True, text=True,
            )
            stashed = "No local changes" not in stash_result.stdout

            subprocess.run(
                ["git", "-C", root, "reset", "--hard", version],
                check=True, capture_output=True,
            )
            msg = f"Rolled back to {version}."
            if stashed:
                msg += f" Uncommitted work saved to stash '{stash_msg}' (git stash pop to restore)."
            return {"status": "success", "message": msg, "stash_ref": stash_msg if stashed else ""}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "error": e.stderr.decode()}''',
    "tools/git_ops.py: P1-6 rollback uses stash not reset --hard",
)


# ── 4. core/config.py — M8: validate positive ints ───────────────────────────
# PROBLEM: If someone sets AUTOCODE_MAX_RETRIES=0 or a negative number by
# mistake, the retry loop silently breaks. Validate at startup.
# FIX: Assert positive ints for key tunables after loading from env.
# Using assert keeps it simple -- if validation fails, server won't start,
# which is the correct behaviour (fail fast, not fail silently later).

failures += not patch(
    "core/config.py",
    '''\
        self.autocode_max_file_chars: int = int(os.getenv("AUTOCODE_MAX_FILE_CHARS", "6000"))''',
    '''\
        self.autocode_max_file_chars: int = int(os.getenv("AUTOCODE_MAX_FILE_CHARS", "6000"))

        # M8: validate tunables -- fail fast at startup rather than silently misbehave
        assert self.autocode_max_retries  > 0,  "AUTOCODE_MAX_RETRIES must be > 0"
        assert self.autocode_max_file_chars > 0, "AUTOCODE_MAX_FILE_CHARS must be > 0"''',
    "core/config.py: M8 validate positive ints",
)


# ── Summary ───────────────────────────────────────────────────────────────────
print()
if failures == 0:
    print("All patches applied.")
    print("Also install slowapi for rate limiting: pip install slowapi")
    print("Then restart server.py")
else:
    print(f"{failures} patch(es) failed -- review MISS/FAIL lines above.")
    print("For failed patches: paste the relevant file and get the full fixed version.")
    sys.exit(1)
