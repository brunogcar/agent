"""workflows/data_impl/nodes/ — Per-node modules for the data workflow.

Each module exports exactly one node function with the signature
    def node_xxx(state: WorkflowState) -> dict:
returning a partial update dict (LangGraph best practice).
"""
