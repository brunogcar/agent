"""tools/workflow_ops/templates/__init__.py — Template package marker.

Template JSON files (bug-fix, refactor, index-codebase, index-quick) live
alongside this __init__.py. The _registry module scans for *.json files at
import time and exposes get_template(name) + list_templates().
"""
from __future__ import annotations
