"""tests/workflows/autocode/test_facade.py
Facade contract tests — verify the public API actually works.

[v1.1] These tests exist because the facade was silently broken for 2 versions
(v1.0.1 + v1.0.2) — dead imports made `import workflows.autocode` raise
ImportError, but no test caught it because all 106 tests imported directly
from autocode_impl/. These tests guard the public entry point.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock


class TestFacadeImports:
    """The facade must import without errors. Catches removed symbols."""

    def test_facade_imports_cleanly(self):
        """import workflows.autocode must succeed (was broken for 2 versions)."""
        import workflows.autocode as facade
        assert hasattr(facade, "run_autocode_agent")
        assert hasattr(facade, "build_graph")
        assert hasattr(facade, "get_graph")
        assert hasattr(facade, "WORKFLOW_METADATA")

    def test_facade_all_exports_resolve(self):
        """Every name in __all__ must actually exist on the module."""
        import workflows.autocode as facade
        for name in facade.__all__:
            assert hasattr(facade, name), f"__all__ lists {name!r} but it's not on the module"

    def test_no_dead_imports(self):
        """[v1.1] Verify the 4 dead imports are gone (AGENT_ROOT, route_after_brainstorm, route_after_debug, _git_snapshot)."""
        import workflows.autocode as facade
        assert not hasattr(facade, "AGENT_ROOT"), "AGENT_ROOT was removed in v1.0.1 #9 — must not be imported"
        assert not hasattr(facade, "route_after_brainstorm"), "route_after_brainstorm was removed in v1.0.2 #4"
        assert not hasattr(facade, "route_after_debug"), "route_after_debug was removed in v1.0.2 #4"
        assert not hasattr(facade, "_git_snapshot"), "_git_snapshot was removed in v1.0.1 #2"


class TestWorkflowMetadata:
    """v1.1: WORKFLOW_METADATA must exist and have correct structure."""

    def test_metadata_exists(self):
        from workflows.autocode_impl.graph import WORKFLOW_METADATA
        assert isinstance(WORKFLOW_METADATA, dict)
        assert WORKFLOW_METADATA["name"] == "autocode"
        assert WORKFLOW_METADATA["version"] == "1.1"

    def test_metadata_has_17_nodes(self):
        from workflows.autocode_impl.graph import WORKFLOW_METADATA
        nodes = WORKFLOW_METADATA["nodes"]
        assert len(nodes) == 17, f"Expected 17 nodes, got {len(nodes)}"
        names = [n["name"] for n in nodes]
        for expected in ["node_classify_task", "node_verify", "node_commit", "node_distill_memory", "node_create_skill"]:
            assert expected in names, f"Missing node: {expected}"

    def test_metadata_nodes_have_types(self):
        from workflows.autocode_impl.graph import WORKFLOW_METADATA
        for node in WORKFLOW_METADATA["nodes"]:
            assert "type" in node, f"Node {node['name']} missing type"
            assert node["type"] in ("llm", "tool", "logic", "composite"), f"Unknown type: {node['type']}"

    def test_metadata_has_loops(self):
        from workflows.autocode_impl.graph import WORKFLOW_METADATA
        loops = WORKFLOW_METADATA["loops"]
        assert len(loops) >= 1
        debug_loop = loops[0]
        assert debug_loop["name"] == "debug_loop"
        assert "exit_condition" in debug_loop
        assert "node_systematic_debug" in debug_loop["nodes"]

    def test_metadata_has_branches(self):
        from workflows.autocode_impl.graph import WORKFLOW_METADATA
        branches = WORKFLOW_METADATA["branches"]
        assert len(branches) >= 1
        skill_branch = branches[0]
        assert skill_branch["name"] == "create_skill"
        assert "skips" in skill_branch

    def test_metadata_has_safety_features(self):
        from workflows.autocode_impl.graph import WORKFLOW_METADATA
        safety = WORKFLOW_METADATA["safety_features"]
        assert "git_branch" in safety
        assert "atomic_writes" in safety


class TestRunWorkflowAutocode:
    """run_workflow(workflow_type='autocode') must reach the graph.

    This is the integration test that was missing — it catches both the
    dead-import ImportError AND the uncompiled-graph AttributeError.
    """

    def test_run_workflow_autocode_reaches_graph(self):
        """run_workflow('autocode') must call invoke_with_timeout, not crash."""
        from workflows.base import run_workflow
        with patch("workflows.autocode_impl.graph.invoke_with_timeout") as mock_invoke:
            mock_invoke.return_value = {"status": "success", "result": "done"}
            result = run_workflow(
                workflow_type="autocode",
                goal="test task",
                task="test task",
                files={},
                trace_id="test-facade-1",
            )
            assert result["status"] == "success"
            assert mock_invoke.called, "invoke_with_timeout must be called"

    def test_run_autocode_agent_delegates_to_run_workflow(self):
        """[v1.1] run_autocode_agent() is a shim that delegates to run_workflow()."""
        from workflows.autocode import run_autocode_agent
        with patch("workflows.base.run_workflow") as mock_rw:
            mock_rw.return_value = {"status": "success"}
            result = run_autocode_agent("test task", mode="feature")
            assert mock_rw.called, "run_autocode_agent must delegate to run_workflow"
            _, kwargs = mock_rw.call_args
            assert kwargs.get("workflow_type") == "autocode"
            assert kwargs.get("goal") == "test task"
            assert kwargs.get("task") == "test task"
            assert result["status"] == "success"

    def test_run_workflow_autocode_passes_through_kwargs(self):
        """files, mode, target_file, dry_run must reach the graph."""
        from workflows.base import run_workflow
        with patch("workflows.autocode_impl.graph.invoke_with_timeout") as mock_invoke:
            mock_invoke.return_value = {"status": "success"}
            run_workflow(
                workflow_type="autocode",
                goal="add retry",
                task="add retry",
                files={"tools/web.py": "content"},
                mode="feature",
                target_file="tools/web.py",
                dry_run=True,
                trace_id="t1",
            )
            _, kwargs = mock_invoke.call_args
            state = kwargs if "status" not in kwargs else mock_invoke.call_args[0][0]
            # invoke_with_timeout receives initial_state dict
            call_state = mock_invoke.call_args[0][0] if mock_invoke.call_args[0] else kwargs
            assert call_state.get("files") == {"tools/web.py": "content"}
            assert call_state.get("mode") == "feature"
            assert call_state.get("dry_run") is True


class TestGraphStructure:
    """Verify the graph compiles and has all expected nodes."""

    def test_build_graph_returns_stategraph(self):
        from workflows.autocode_impl.graph import build_graph
        graph = build_graph()
        assert graph is not None
        # build_graph returns uncompiled StateGraph; must have add_node
        assert hasattr(graph, "add_node")

    def test_get_graph_returns_compiled(self):
        from workflows.autocode_impl.graph import get_graph
        graph = get_graph()
        assert graph is not None
        # get_graph returns compiled graph; must have invoke, NOT add_node
        assert hasattr(graph, "invoke")
        assert not hasattr(graph, "add_node"), "get_graph must return compiled graph, not StateGraph"

    def test_graph_has_no_double_compile(self):
        """[v1.1] get_graph() must return a compiled graph — calling .compile() on it would crash."""
        from workflows.autocode_impl.graph import get_graph
        graph = get_graph()
        assert not hasattr(graph, "compile"), (
            "Compiled graph must not have .compile() — the old facade called it and crashed. "
            "If this fails, get_graph() is returning an uncompiled StateGraph."
        )


class TestRoutingFixes:
    """v1.1 routing fixes from cross-LLM review."""

    def test_audit_routes_to_impact_analysis(self):
        """[v1.1] audit task type must go through analyze_impact (was skipping it)."""
        from workflows.autocode_impl.routes import route_after_write_files
        assert route_after_write_files({"task_type": "audit"}) == "node_analyze_impact"

    def test_edit_routes_to_impact_analysis(self):
        """[v1.1] edit task type must go through analyze_impact (was skipping it)."""
        from workflows.autocode_impl.routes import route_after_write_files
        assert route_after_write_files({"task_type": "edit"}) == "node_analyze_impact"

    def test_feature_still_routes_to_impact_analysis(self):
        """Regression: existing task types must still work."""
        from workflows.autocode_impl.routes import route_after_write_files
        for task_type in ["fix", "fix_error", "refactor", "improve", "feature"]:
            assert route_after_write_files({"task_type": task_type}) == "node_analyze_impact"


class TestDistillMemoryNonFatal:
    """v1.1: distill_memory failure must not fail the workflow."""

    def test_distill_memory_uses_warning_not_error(self):
        """[v1.1] distill_memory must use tracer.warning (non-fatal), not tracer.error."""
        import inspect
        import ast
        from workflows.autocode_impl.nodes.memory import node_distill_memory
        source = inspect.getsource(node_distill_memory)
        # Strip comments and docstrings before checking (word "tracer.error" appears in comments)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                    node.body = node.body[1:] if len(node.body) > 1 else [ast.Pass()]
        code_only = ast.unparse(tree)
        code_lines = [line for line in code_only.split("\n") if not line.strip().startswith("#")]
        code_str = "\n".join(code_lines)
        # Must call tracer.warning, must NOT call tracer.error
        assert "tracer.warning" in code_str, (
            "distill_memory must use tracer.warning for non-fatal failures"
        )
        assert "tracer.error(" not in code_str, (
            "distill_memory must not call tracer.error() — it's non-fatal (code already committed)"
        )


class TestPartialDictReturns:
    """[#33] All autocode nodes must return partial update dicts, not {**state, ...}.

    LangGraph best practice: nodes return only the changed keys, not the whole
    state. This was already done in v1.0.1/v1.0.2 but had no test guarding it.
    This class locks in the clean state — a future refactor that reintroduces
    {**state, ...} or bare `return state` will fail these tests.

    Uses AST source inspection so the check is on actual code, not comments.
    """

    _NODE_MODULES = [
        "classify", "validate", "brainstorm", "plan", "branch", "tests",
        "execute", "write_files", "analyze_impact", "run_tests", "debug",
        "verify", "report", "commit", "memory", "create_skill",
    ]

    def _get_node_functions(self):
        """Yield (module_name, function_name, function_source) for all node_* funcs."""
        import ast, importlib, inspect
        for mod_name in self._NODE_MODULES:
            mod = importlib.import_module(f"workflows.autocode_impl.nodes.{mod_name}")
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if callable(obj) and attr.startswith("node_") and not inspect.iscoroutinefunction(obj):
                    try:
                        source = inspect.getsource(obj)
                        yield mod_name, attr, source
                    except (OSError, TypeError):
                        pass

    def test_no_node_returns_star_state_spread(self):
        """No node may return {**state, ...} — the old anti-pattern."""
        import ast
        violations = []
        for mod_name, func_name, source in self._get_node_functions():
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Return) and node.value and isinstance(node.value, ast.Dict):
                    for k, v in zip(node.value.keys, node.value.values):
                        # **state spread appears as key=None, value=Name('state')
                        if k is None and isinstance(v, ast.Name) and v.id == "state":
                            violations.append(f"{mod_name}.{func_name}")
        assert not violations, (
            f"These nodes return {{{{**state, ...}}}} (must return partial dict only): {violations}"
        )

    def test_no_node_returns_bare_state(self):
        """No node may `return state` (whole state) — must return a dict of changed keys only."""
        import ast
        violations = []
        for mod_name, func_name, source in self._get_node_functions():
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Return) and node.value and isinstance(node.value, ast.Name) and node.value.id == "state":
                    violations.append(f"{mod_name}.{func_name}")
        assert not violations, (
            f"These nodes do bare `return state` (must return partial dict): {violations}"
        )

    def test_all_nodes_are_sync(self):
        """All nodes must be sync (def, not async def) — LangGraph requirement."""
        import inspect, importlib
        violations = []
        for mod_name in self._NODE_MODULES:
            mod = importlib.import_module(f"workflows.autocode_impl.nodes.{mod_name}")
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if callable(obj) and attr.startswith("node_"):
                    if inspect.iscoroutinefunction(obj):
                        violations.append(f"{mod_name}.{attr}")
        assert not violations, f"These nodes are async (must be sync): {violations}"
