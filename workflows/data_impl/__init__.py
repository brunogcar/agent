"""workflows/data_impl/ — Implementation of the data analysis workflow.

v1.0: Split from monolithic workflows/data.py into a subpackage with
per-node modules, mirroring the research_impl / understand_impl pattern.

Reuses WorkflowState from workflows/base.py (data's fields — goal, code,
memory_context, output, exec_error, result, status, trace_id — all already
exist in WorkflowState). No separate state.py is needed, same as research_impl.

Nodes (sync, return partial update dicts):
  recall  -> execute -> critique -> store -> notify
  (execute has a conditional edge: failure -> END)

Modules:
  graph.py    — build_data_graph() + WORKFLOW_METADATA
  routes.py   — route_after_execute (genuine conditional router)
  helpers.py  — _extract_code_from_response (code extraction with observability)
  nodes/      — one module per node
"""
