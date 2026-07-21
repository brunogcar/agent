"""tests/workflows/understand/test_queries.py

[v1.4.1 P1-2] Tests for core.kgraph.queries — multi-language fix.

Was: `get_dependencies` filtered `d.endswith(".py")` (silently dropped
every JS/TS/Go/Rust/Java/etc. dependency edge). `get_callers` did
`file_path.replace("/", ".").replace(".py", "")` (Python-only).

Now: get_dependencies keeps any path-like / recognized-extension / raw
module name target. get_callers strips any supported extension (not just
.py) before computing the module-name form.

These tests use real SQLite GraphStores (via ProjectManager + tmp_path)
to verify the multi-language filtering end-to-end.
"""
from __future__ import annotations

from pathlib import Path

from core.kgraph.project import ProjectManager
from core.kgraph.storage import GraphStore
from core.kgraph import queries


def _setup_project_with_edges(tmp_path, project_name, edges):
    """Create a project + GraphStore + insert the given edges.

    edges: list of (source_rel_path, [target_id, target_id, ...])
    """
    project_path = tmp_path / project_name
    (project_path / "code").mkdir(parents=True)
    pm = ProjectManager(project_path, is_agent_root=False)
    pm.ensure_initialized()

    store = GraphStore(pm.artifact_root / "kg.db")
    for source_rel, targets in edges:
        # Upsert a file node + its edges.
        store.upsert_file_graph(pm.project_id, source_rel, "hash123", targets, 0.0, 100)
    store.close()
    return project_path


class TestGetDependenciesMultiLanguage:
    """[v1.4.1 P1-2] get_dependencies must work for JS/TS/Go/Rust, not just Python."""

    def test_returns_python_file_path_targets(self, tmp_path):
        """Python file-path form (with .py) must be returned."""
        project_path = _setup_project_with_edges(
            tmp_path, "py_proj",
            [("core/config.py", ["core/utils.py"])],
        )
        deps = queries.get_dependencies(project_path, "core/config.py")
        assert "core/utils.py" in deps

    def test_returns_python_module_name_targets(self, tmp_path):
        """Python module-name form ('core.utils' — no extension) must also be kept.

        The v1.4.1 fix preserves raw module names — they're useful for
        cross-language understanding even though they don't map 1:1 to a file.
        """
        project_path = _setup_project_with_edges(
            tmp_path, "py_mod_proj",
            [("core/config.py", ["core.utils"])],
        )
        deps = queries.get_dependencies(project_path, "core/config.py")
        assert "core.utils" in deps

    def test_returns_javascript_targets(self, tmp_path):
        """JS imports like './utils' (path-form) and 'react' (raw) must be kept.

        Pre-v1.4.1: these were dropped by the `d.endswith(".py")` filter.
        """
        project_path = _setup_project_with_edges(
            tmp_path, "js_proj",
            [("app.js", ["./utils", "react"])],
        )
        deps = queries.get_dependencies(project_path, "app.js")
        # './utils' contains a slash → kept as path-form.
        assert "./utils" in deps
        # 'react' has no slash + no recognized extension → kept as raw module name.
        assert "react" in deps

    def test_returns_typescript_targets(self, tmp_path):
        project_path = _setup_project_with_edges(
            tmp_path, "ts_proj",
            [("app.ts", ["./types", "./utils.ts"])],
        )
        deps = queries.get_dependencies(project_path, "app.ts")
        assert "./types" in deps
        assert "./utils.ts" in deps

    def test_returns_go_targets(self, tmp_path):
        """Go imports are package paths like 'fmt', 'os' — must be kept."""
        project_path = _setup_project_with_edges(
            tmp_path, "go_proj",
            [("main.go", ["fmt", "os", "strings"])],
        )
        deps = queries.get_dependencies(project_path, "main.go")
        assert "fmt" in deps
        assert "os" in deps
        assert "strings" in deps

    def test_returns_rust_targets(self, tmp_path):
        """Rust use declarations like 'std::collections::HashMap' must be kept."""
        project_path = _setup_project_with_edges(
            tmp_path, "rust_proj",
            [("main.rs", ["std::collections::HashMap", "std::io"])],
        )
        deps = queries.get_dependencies(project_path, "main.rs")
        assert "std::collections::HashMap" in deps
        assert "std::io" in deps

    def test_drops_empty_string_targets(self, tmp_path):
        """Defensive: empty-string target_ids (shouldn't happen, but guard)."""
        project_path = _setup_project_with_edges(
            tmp_path, "empty_proj",
            [("main.py", ["", "os", ""])],
        )
        deps = queries.get_dependencies(project_path, "main.py")
        assert "" not in deps
        assert "os" in deps


class TestGetCallersMultiLanguage:
    """[v1.4.1 P1-2] get_callers must work for JS/TS/Go/Rust, not just Python."""

    def test_finds_python_callers_via_module_name(self, tmp_path):
        """get_callers('core/utils.py') should find files that import 'core.utils'."""
        project_path = _setup_project_with_edges(
            tmp_path, "py_callers",
            [
                ("core/config.py", ["core.utils"]),  # imports core.utils
                ("core/main.py", ["core.utils"]),    # imports core.utils
                ("core/other.py", ["os"]),           # imports os, not core.utils
            ],
        )
        callers = queries.get_callers(project_path, "core/utils.py")
        # Both config.py and main.py should be callers; other.py should not.
        assert "core/config.py" in callers
        assert "core/main.py" in callers
        assert "core/other.py" not in callers

    def test_finds_callers_via_raw_file_path(self, tmp_path):
        """get_callers('app.js') should find files that import './app' (path form).

        Pre-v1.4.1: the module_name computation was Python-specific (replace
        '/' with '.' + strip '.py'). For JS, the import string IS the path
        ('./app'), so we just need to match against the raw file_path.
        """
        project_path = _setup_project_with_edges(
            tmp_path, "js_callers",
            [
                ("main.js", ["./app"]),       # imports ./app
                ("other.js", ["react"]),      # imports react, not ./app
            ],
        )
        callers = queries.get_callers(project_path, "app.js")
        # main.js should be a caller; other.js should not.
        assert "main.js" in callers
        assert "other.js" not in callers

    def test_finds_callers_for_go(self, tmp_path):
        """Go imports are package paths — get_callers should still work via raw path match."""
        project_path = _setup_project_with_edges(
            tmp_path, "go_callers",
            [
                ("main.go", ["myapp/utils"]),    # imports myapp/utils
                ("other.go", ["fmt"]),           # imports fmt, not myapp/utils
            ],
        )
        callers = queries.get_callers(project_path, "myapp/utils.go")
        assert "main.go" in callers
        assert "other.go" not in callers
