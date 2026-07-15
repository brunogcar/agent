"""tools/python_ops/imports.py — Import allowlists and parser.

Extracted from the original tools/python.py during v1.0 @meta_tool refactor.
Defines the import policy used by the run_data action:
  - STDLIB_IMPORTS: fast stdlib modules → in-process execution
  - HEAVY_IMPORTS: slow heavy libs → subprocess execution (isolated)
  - CORE_ALLOWED: granular internal modules (e.g. core.br_validator)
  - BLOCKED_IMPORTS: security boundary — never allowed even in run_data
  - ALL_ALLOWED: union of all permitted import roots

The _parse_imports() function uses ast to extract top-level module names
from a code string, preserving the full dotted path for core.* modules so
the granular CORE_ALLOWED check works.
"""
from __future__ import annotations

import ast
from typing import List


# Stdlib modules — run in-process (fast, no subprocess overhead)
STDLIB_IMPORTS = {
    "random", "json", "math", "statistics", "datetime", "calendar",
    "collections", "itertools", "functools", "re", "csv",
    "io", "textwrap", "string", "decimal", "fractions",
    "heapq", "bisect", "pprint", "copy", "time", "uuid",
    "hashlib", "base64", "struct",
    "dataclasses", "typing", "enum", "abc",
}

# 🔵 Granular Core Allowlist: Only specific safe utilities can be imported by LLM scripts
CORE_ALLOWED = {
    "core.br_validator",
}

# Heavy libs — require subprocess (slow first import, worth isolating)
HEAVY_IMPORTS = {
    "pandas", "numpy", "matplotlib", "scipy", "sklearn",
    "seaborn", "plotly", "PIL", "cv2", "torch", "tensorflow",
}

ALL_ALLOWED = STDLIB_IMPORTS | HEAVY_IMPORTS | CORE_ALLOWED

# Modules that are never allowed even in run_data -- security boundary.
# These can access the filesystem, network, processes, or environment vars.
BLOCKED_IMPORTS = {
    "os", "sys", "subprocess", "shutil", "socket", "pickle",
    "multiprocessing", "ctypes", "importlib", "builtins",
    "signal", "pty", "tty", "termios", "fcntl", "resource",
}


def _parse_imports(code: str) -> List[str]:
    """Return list of top-level base module names from code.

    For `core.*` imports, the full dotted path is preserved so CORE_ALLOWED
    can apply granular (sub-module) allowlisting. For everything else, only
    the top-level package name is returned (e.g. `from os.path import X`
    yields 'os', not 'os.path').

    Returns an empty list on SyntaxError — callers should run ast.parse
    separately for proper error reporting before calling this.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Preserve full path for core.* to allow granular sandboxing
                name = alias.name
                names.append(name if name.startswith("core.") else name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            name = node.module
            names.append(name if name.startswith("core.") else name.split(".")[0])
    return names
