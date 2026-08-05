"""skills/bcb/macro/modes/__init__.py - Empty marker for the modes package.

Mode modules (dashboard.py, rates.py, inflation.py, fx.py) are auto-
discovered by skills._base.auto_discover_modes() (or the fallback in
_registry.py) via importlib. This file just marks the directory as a
regular package so `from skills.bcb.macro.modes.<mode> import <fn>`
works reliably across Python versions.
"""
