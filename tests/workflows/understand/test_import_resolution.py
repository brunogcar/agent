"""tests/workflows/understand/test_import_resolution.py

[v1.8] Tests for `_resolve_import_to_file_paths()` in
`workflows.understand_impl.nodes.parse_and_store`.

The function takes a raw import string (e.g. "core.config", "./foo",
"../utils", "react", "fmt", "std::collections::HashMap"), the relative
path of the importing file, and the tree-sitter language name, and
returns a list of candidate file paths/strings to store as edge targets.

Per-language resolution rules:
  - python     → "core.config" → also "core/config.py" (file-path form)
  - js / ts    → "./foo" → 13 candidates (raw + 6 ext variants + 6 index variants)
                 "../utils" → resolves via parent dir walk
                 "react" / "@scope/pkg" → raw only (node_modules, not project source)
  - go         → "github.com/foo/bar" → also "bar" (package short-name)
                 "fmt" → raw only (no `/` separator)
  - rust       → "std::collections::HashMap" → also "std" + "collections"
                 "crate::models" → also "crate" + "models"
  - unknown    → raw only
  - empty dep  → []
"""
from __future__ import annotations

import pytest

from workflows.understand_impl.nodes.parse_and_store import (
    _resolve_import_to_file_paths,
    _JS_TS_EXTENSIONS,
)


# ─── Python ─────────────────────────────────────────────────────────────────

class TestResolvePython:
    """Python imports — unchanged behavior from v1.4."""

    def test_python_module_to_file_path(self):
        """`core.config` (from src/app.py) → candidates include `core/config.py`."""
        candidates = _resolve_import_to_file_paths(
            dep="core.config", rel_path="src/app.py", language="python"
        )
        assert "core/config.py" in candidates

    def test_python_stores_raw_dep(self):
        """The raw module name `core.config` is always stored (first element)."""
        candidates = _resolve_import_to_file_paths(
            dep="core.config", rel_path="src/app.py", language="python"
        )
        assert "core.config" in candidates
        # Raw dep should be the first element (documented contract).
        assert candidates[0] == "core.config"

    def test_python_nested_module(self):
        """`core.kgraph.storage` → also `core/kgraph/storage.py`."""
        candidates = _resolve_import_to_file_paths(
            dep="core.kgraph.storage", rel_path="main.py", language="python"
        )
        assert "core/kgraph/storage.py" in candidates
        assert "core.kgraph.storage" in candidates


# ─── JavaScript ─────────────────────────────────────────────────────────────

class TestResolveJavaScript:
    """JS relative imports resolve to candidate file paths.

    Non-relative imports (react, lodash, @scope/pkg) are stored raw only.
    """

    def test_js_relative_simple(self):
        """`./foo` from `src/app.js` → candidates include `src/foo.js`,
        `src/foo.mjs`, `src/foo.cjs`, `src/foo/index.js`, etc.
        """
        candidates = _resolve_import_to_file_paths(
            dep="./foo", rel_path="src/app.js", language="javascript"
        )
        # The raw import is always stored.
        assert "./foo" in candidates
        # Extension variants (relative to src/).
        assert "src/foo.js" in candidates
        assert "src/foo.mjs" in candidates
        assert "src/foo.cjs" in candidates
        assert "src/foo.jsx" in candidates
        # TS variants too (a .js file can import a .ts file in some setups).
        assert "src/foo.ts" in candidates
        assert "src/foo.tsx" in candidates
        # Index-file variants.
        assert "src/foo/index.js" in candidates
        assert "src/foo/index.mjs" in candidates
        assert "src/foo/index.ts" in candidates

    def test_js_relative_parent(self):
        """`../utils` from `src/app.js` → candidates include `utils.js`,
        `utils/index.js` (resolved from `src/..` = project root).
        """
        candidates = _resolve_import_to_file_paths(
            dep="../utils", rel_path="src/app.js", language="javascript"
        )
        # Raw is kept.
        assert "../utils" in candidates
        # Resolved base is `utils` (src/.. = project root).
        assert "utils.js" in candidates
        assert "utils.mjs" in candidates
        assert "utils/index.js" in candidates
        assert "utils/index.ts" in candidates

    def test_js_relative_nested(self):
        """`./foo/bar` from `src/app.js` → candidates include `src/foo/bar.js`,
        `src/foo/bar/index.js`.
        """
        candidates = _resolve_import_to_file_paths(
            dep="./foo/bar", rel_path="src/app.js", language="javascript"
        )
        assert "./foo/bar" in candidates
        assert "src/foo/bar.js" in candidates
        assert "src/foo/bar.mjs" in candidates
        assert "src/foo/bar/index.js" in candidates
        assert "src/foo/bar/index.ts" in candidates

    def test_js_non_relative_not_resolved(self):
        """`react` is a node_modules package → candidates = ['react'] only.

        No file-path candidates should be generated (would pollute the edge
        table with phantom paths that never match a stored node).
        """
        candidates = _resolve_import_to_file_paths(
            dep="react", rel_path="src/app.js", language="javascript"
        )
        assert candidates == ["react"]

    def test_js_absolute_scoped_not_resolved(self):
        """`@scope/pkg` is a scoped node_modules package → raw only."""
        candidates = _resolve_import_to_file_paths(
            dep="@scope/pkg", rel_path="src/app.js", language="javascript"
        )
        assert candidates == ["@scope/pkg"]

    def test_js_double_parent(self):
        """`../../utils` from `src/sub/app.js` → resolved to `utils.js`.

        Walks two parent dirs: `src/sub` → `src` → `` (project root).
        """
        candidates = _resolve_import_to_file_paths(
            dep="../../utils", rel_path="src/sub/app.js", language="javascript"
        )
        assert "../../utils" in candidates
        # Resolved base should be `utils` (project root).
        assert "utils.js" in candidates
        assert "utils/index.js" in candidates


# ─── TypeScript ─────────────────────────────────────────────────────────────

class TestResolveTypeScript:
    """TS relative imports resolve to BOTH .ts/.tsx and .js/.jsx variants
    (TS projects can import .js files).
    """

    def test_ts_relative_with_ts_extensions(self):
        """`./foo` from `src/app.ts` → candidates include `src/foo.ts`,
        `src/foo.tsx`, `src/foo/index.ts`, `src/foo/index.tsx`.
        """
        candidates = _resolve_import_to_file_paths(
            dep="./foo", rel_path="src/app.ts", language="typescript"
        )
        assert "./foo" in candidates
        assert "src/foo.ts" in candidates
        assert "src/foo.tsx" in candidates
        assert "src/foo/index.ts" in candidates
        assert "src/foo/index.tsx" in candidates

    def test_ts_relative_stores_js_variants(self):
        """TS projects often have .js legacy files — verify all 6 JS/TS
        extensions appear in the candidate list.
        """
        candidates = _resolve_import_to_file_paths(
            dep="./foo", rel_path="src/app.ts", language="typescript"
        )
        for ext in _JS_TS_EXTENSIONS:
            assert f"src/foo{ext}" in candidates, f"Missing src/foo{ext}"
            assert f"src/foo/index{ext}" in candidates, f"Missing src/foo/index{ext}"

    def test_ts_relative_parent(self):
        """`../utils` from `src/app.ts` → `utils.ts`, `utils/index.ts`."""
        candidates = _resolve_import_to_file_paths(
            dep="../utils", rel_path="src/app.ts", language="typescript"
        )
        assert "../utils" in candidates
        assert "utils.ts" in candidates
        assert "utils.tsx" in candidates
        assert "utils/index.ts" in candidates


# ─── Go ─────────────────────────────────────────────────────────────────────

class TestResolveGo:
    """Go imports — raw package path + short-name derivative (no file paths)."""

    def test_go_stdlib(self):
        """`fmt` has no `/` → candidates = ['fmt'] (no short-name derivative)."""
        candidates = _resolve_import_to_file_paths(
            dep="fmt", rel_path="main.go", language="go"
        )
        assert candidates == ["fmt"]

    def test_go_package_import(self):
        """`github.com/foo/bar` → also `bar` (package short-name)."""
        candidates = _resolve_import_to_file_paths(
            dep="github.com/foo/bar", rel_path="main.go", language="go"
        )
        assert "github.com/foo/bar" in candidates
        assert "bar" in candidates

    def test_go_no_file_path_resolution(self):
        """Go candidates must NOT contain any `.go` file paths."""
        candidates = _resolve_import_to_file_paths(
            dep="github.com/foo/bar", rel_path="main.go", language="go"
        )
        for c in candidates:
            assert not c.endswith(".go"), f"Unexpected .go file path: {c}"

    def test_go_deep_package(self):
        """`github.com/foo/bar/baz` → also `baz` (last segment)."""
        candidates = _resolve_import_to_file_paths(
            dep="github.com/foo/bar/baz", rel_path="main.go", language="go"
        )
        assert "github.com/foo/bar/baz" in candidates
        assert "baz" in candidates


# ─── Rust ───────────────────────────────────────────────────────────────────

class TestResolveRust:
    """Rust `use` declarations — raw path + each `::`-segment except the
    last item name (no file paths).
    """

    def test_rust_std(self):
        """`std::collections::HashMap` → also `std` + `collections`.

        The last segment (HashMap) is the item name, not a module, so it's
        excluded.
        """
        candidates = _resolve_import_to_file_paths(
            dep="std::collections::HashMap", rel_path="src/main.rs", language="rust"
        )
        assert "std::collections::HashMap" in candidates
        assert "std" in candidates
        assert "collections" in candidates
        # The item name (last segment) is NOT included.
        assert "HashMap" not in candidates

    def test_rust_crate(self):
        """`crate::models::User` → also `crate` + `models`.

        The tree-sitter parser keeps the FULL path (including the item
        name `User`) as the raw dep. _resolve_import_to_file_paths then
        extracts parts[:-1] = ['crate', 'models'] as derivatives. The
        item name (`User`) is excluded — it's the imported item, not a
        module name.
        """
        candidates = _resolve_import_to_file_paths(
            dep="crate::models::User", rel_path="src/main.rs", language="rust"
        )
        assert "crate::models::User" in candidates
        assert "crate" in candidates
        assert "models" in candidates
        # The item name (last segment) is NOT included as a derivative.
        assert "User" not in candidates

    def test_rust_two_segment_path(self):
        """`crate::models` (2 segments) → parts[:-1] = ['crate'].

        The last segment (`models`) is treated as the "item name" and
        excluded from derivatives. Only `crate` is added.
        """
        candidates = _resolve_import_to_file_paths(
            dep="crate::models", rel_path="src/main.rs", language="rust"
        )
        assert "crate::models" in candidates
        assert "crate" in candidates

    def test_rust_no_file_path_resolution(self):
        """Rust candidates must NOT contain any `.rs` file paths."""
        candidates = _resolve_import_to_file_paths(
            dep="std::collections::HashMap", rel_path="src/main.rs", language="rust"
        )
        for c in candidates:
            assert not c.endswith(".rs"), f"Unexpected .rs file path: {c}"

    def test_rust_single_segment(self):
        """`std` (no `::`) → candidates = ['std'] (no derivatives)."""
        candidates = _resolve_import_to_file_paths(
            dep="std", rel_path="src/main.rs", language="rust"
        )
        assert candidates == ["std"]


# ─── Edge cases ─────────────────────────────────────────────────────────────

class TestResolveEdgeCases:
    """Defensive cases — empty dep, unknown language, weird inputs."""

    def test_empty_dep_returns_empty(self):
        """Empty string dep → empty list (no candidates)."""
        assert _resolve_import_to_file_paths(
            dep="", rel_path="src/app.py", language="python"
        ) == []

    def test_unknown_language_stores_raw(self):
        """Unknown language (e.g. 'ruby') → candidates = [dep] (raw only).

        No language-specific resolution applies; the raw import is still
        returned so it can be stored as an edge target.
        """
        candidates = _resolve_import_to_file_paths(
            dep="anything", rel_path="src/app.rb", language="ruby"
        )
        assert candidates == ["anything"]

    def test_no_language_specific_match_for_python_path_with_slash(self):
        """A Python dep with a `/` (unusual but possible) → still works.

        `dep = "src/utils"` (instead of dotted form). Python branch just does
        `dep.replace(".", "/") + ".py"` → `src/utils.py`. That's fine.
        """
        candidates = _resolve_import_to_file_paths(
            dep="src/utils", rel_path="main.py", language="python"
        )
        assert "src/utils" in candidates
        # replace(".", "/") on "src/utils" (no dots) → unchanged → + ".py"
        assert "src/utils.py" in candidates
