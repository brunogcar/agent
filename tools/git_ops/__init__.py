"""git_ops – plug-in git operation handlers, auto-discovered."""

import importlib
import pkgutil


def _discover():
    """Import every sibling .py file to trigger @register_git decorators."""
    package_path = __path__[0]
    for _, module_name, _ in pkgutil.iter_modules([package_path]):
        if module_name.startswith("_") or module_name == "__init__":
            continue
        importlib.import_module(f".{module_name}", package=__name__)


_discover()