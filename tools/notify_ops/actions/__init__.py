"""notify_ops/actions/ — Action handler modules.

Each module here imports `register_action` from tools.notify_ops._registry
and decorates its top-level handler. The parent __init__.py auto-discovers
all .py files in this directory (except __init__.py itself) and imports
them, triggering registration.

Adding a new action: drop a new file here, define a handler decorated with
@register_action("notify", "<action_name>", ...). The facade will pick it
up automatically on next import — no edits to __init__.py needed.

NOTE: This file is named `test_notify.py` to namespace-collide-avoid with
the standard `test_*` pytest discovery pattern. The action_name registered
is "test" (not "test_notify"). The module file name is intentionally
different from the action name because the auto-discovery glob picks up
all *.py files in actions/, and we want to keep the literal "test" action
registration explicit.
"""
