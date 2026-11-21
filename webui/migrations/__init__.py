"""tools/migrations — one-time data migrations for existing memory_db installs.

Each migration is a standalone module run as ``python -m tools.migrations.<name>``
from the repo root. They exist because the sync engines can only fix data they
WRITE — historical rows already in a user's DB need a bulk pass. Migrations are
idempotent and safe to re-run.
"""
