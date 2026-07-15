"""consult_ops/actions/ — Action handler modules.

Each module here imports `register_action` from tools.consult_ops._registry
and decorates its top-level handler. The parent __init__.py auto-discovers
all .py files in this directory (except __init__.py itself) and imports
them, triggering registration.

Adding a new action: drop a new file here, define a handler decorated with
@register_action("consult", "<action_name>", ...). The facade will pick it
up automatically on next import — no edits to __init__.py needed.
"""
