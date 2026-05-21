"""
cli_ops package — Modular components for the cli meta-tool.

This package contains the split logic from the original monolithic cli.py file.
All internal functions are imported by tools/cli.py.
"""

# Package is organized into:
# - helpers.py: Shared utility functions
# - patterns.py: Pattern matching logic
# - router.py: Router dispatch logic
# - actions/: Individual action handlers

# Empty __init__.py - imports are done explicitly in cli.py