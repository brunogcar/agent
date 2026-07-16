"""notify_ops/actions/ — Action handler modules.

Each module here imports `register_action` from tools.notify_ops._registry
and decorates its top-level handler. The parent __init__.py auto-discovers
all .py files in this directory (except __init__.py itself) and imports
them, triggering registration.

Adding a new action: drop a new file here, define a handler decorated with
@register_action("notify", "<action_name>", ...). The facade will pick it
up automatically on next import — no edits to __init__.py needed.

v1.1: action files use bare names (list.py, test.py) matching report_ops'
convention. The action_name is set by @register_action, NOT the filename —
auto-discovery globs all *.py in actions/ and imports them.
"""
