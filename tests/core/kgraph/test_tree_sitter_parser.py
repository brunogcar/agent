"""tests/workflows/understand/test_tree_sitter_parser.py
Tests for the multi-language tree-sitter parser.

Covers: language detection, import extraction, definition extraction
for Python, JavaScript, TypeScript, Go, and Rust.
"""
from __future__ import annotations

import pytest


# ─── Language detection ─────────────────────────────────────────────────────

class TestLanguageDetection:
    def test_python(self):
        from core.kgraph.tree_sitter_parser import get_language_for_file
        assert get_language_for_file("core/config.py") == "python"
        assert get_language_for_file("foo/bar.py") == "python"

    def test_javascript(self):
        from core.kgraph.tree_sitter_parser import get_language_for_file
        assert get_language_for_file("app.js") == "javascript"
        assert get_language_for_file("app.mjs") == "javascript"
        assert get_language_for_file("app.cjs") == "javascript"

    def test_typescript(self):
        from core.kgraph.tree_sitter_parser import get_language_for_file
        assert get_language_for_file("app.ts") == "typescript"
        assert get_language_for_file("component.tsx") == "typescript"

    def test_go(self):
        from core.kgraph.tree_sitter_parser import get_language_for_file
        assert get_language_for_file("main.go") == "go"

    def test_rust(self):
        from core.kgraph.tree_sitter_parser import get_language_for_file
        assert get_language_for_file("main.rs") == "rust"

    def test_unsupported_returns_none(self):
        from core.kgraph.tree_sitter_parser import get_language_for_file
        assert get_language_for_file("foo.rb") == "ruby"  # v1.4: .rb is now supported
        assert get_language_for_file("foo.java") == "java"  # v1.4: .java is now supported
        assert get_language_for_file("foo.txt") is None
        assert get_language_for_file("Makefile") is None

    def test_is_supported(self):
        from core.kgraph.tree_sitter_parser import is_supported
        assert is_supported("foo.py") is True
        assert is_supported("foo.js") is True
        assert is_supported("foo.ts") is True
        assert is_supported("foo.go") is True
        assert is_supported("foo.rs") is True
        assert is_supported("foo.rb") is True  # v1.4: .rb is now supported


# ─── Import extraction ──────────────────────────────────────────────────────

class TestExtractImportsPython:
    def test_import_statement(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        assert "os" in extract_imports("import os\n", "python")

    def test_from_import(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        deps = extract_imports("from core.config import cfg\n", "python")
        assert "core.config" in deps

    def test_multiple_imports(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        deps = extract_imports("import os\nimport sys\nfrom pathlib import Path\n", "python")
        assert "os" in deps
        assert "sys" in deps
        assert "pathlib" in deps

    def test_no_imports(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        assert extract_imports("x = 1\n", "python") == frozenset()

    def test_empty_source(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        assert extract_imports("", "python") == frozenset()


class TestExtractImportsJavaScript:
    def test_default_import(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        deps = extract_imports('import React from "react"\n', "javascript")
        assert "react" in deps

    def test_named_import(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        deps = extract_imports('import { useState } from "react"\n', "javascript")
        assert "react" in deps

    def test_relative_import(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        deps = extract_imports('import foo from "./utils"\n', "javascript")
        assert "./utils" in deps


class TestExtractImportsTypeScript:
    def test_type_import(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        deps = extract_imports('import { Config } from "./types"\n', "typescript")
        assert "./types" in deps


class TestExtractImportsGo:
    def test_single_import(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        deps = extract_imports('package main\nimport "fmt"\n', "go")
        assert "fmt" in deps

    def test_multi_import(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        code = 'package main\nimport (\n  "fmt"\n  "os"\n  "strings"\n)\n'
        deps = extract_imports(code, "go")
        assert "fmt" in deps
        assert "os" in deps
        assert "strings" in deps


class TestExtractImportsRust:
    def test_use_declaration(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        deps = extract_imports("use std::collections::HashMap;\n", "rust")
        assert "std::collections::HashMap" in deps

    def test_grouped_use(self):
        from core.kgraph.tree_sitter_parser import extract_imports
        deps = extract_imports("use std::io::{Read, Write};\n", "rust")
        assert "std::io" in deps


# ─── Definition extraction ─────────────────────────────────────────────────

class TestExtractDefinitionsPython:
    def test_function(self):
        from core.kgraph.tree_sitter_parser import extract_definitions_ts
        defs = extract_definitions_ts("def foo():\n    return 42\n", "python")
        assert len(defs) == 1
        assert defs[0]["name"] == "foo"
        assert defs[0]["type"] == "function"

    def test_class(self):
        from core.kgraph.tree_sitter_parser import extract_definitions_ts
        defs = extract_definitions_ts("class Bar:\n    pass\n", "python")
        assert len(defs) == 1
        assert defs[0]["name"] == "Bar"
        assert defs[0]["type"] == "class"

    def test_multiple_definitions(self):
        from core.kgraph.tree_sitter_parser import extract_definitions_ts
        code = "def foo():\n    pass\n\ndef bar():\n    pass\n\nclass Baz:\n    pass\n"
        defs = extract_definitions_ts(code, "python")
        names = [d["name"] for d in defs]
        assert "foo" in names
        assert "bar" in names
        assert "Baz" in names

    def test_no_definitions_falls_back_to_module(self):
        from core.kgraph.tree_sitter_parser import extract_definitions_ts
        defs = extract_definitions_ts("x = 1\ny = 2\n", "python")
        assert len(defs) == 1
        assert defs[0]["name"] == "<module>"
        assert defs[0]["type"] == "module"


class TestExtractDefinitionsJavaScript:
    def test_function(self):
        from core.kgraph.tree_sitter_parser import extract_definitions_ts
        defs = extract_definitions_ts("function foo() { return 1; }\n", "javascript")
        names = [d["name"] for d in defs]
        assert "foo" in names

    def test_class(self):
        from core.kgraph.tree_sitter_parser import extract_definitions_ts
        defs = extract_definitions_ts("class Bar { method() {} }\n", "javascript")
        names = [d["name"] for d in defs]
        assert "Bar" in names


class TestExtractDefinitionsGo:
    def test_function(self):
        from core.kgraph.tree_sitter_parser import extract_definitions_ts
        defs = extract_definitions_ts("package main\nfunc foo() int { return 1 }\n", "go")
        names = [d["name"] for d in defs]
        assert "foo" in names

    def test_type_declaration(self):
        from core.kgraph.tree_sitter_parser import extract_definitions_ts
        defs = extract_definitions_ts("package main\ntype Bar struct { x int }\n", "go")
        names = [d["name"] for d in defs]
        assert "Bar" in names


class TestExtractDefinitionsRust:
    def test_function(self):
        from core.kgraph.tree_sitter_parser import extract_definitions_ts
        defs = extract_definitions_ts("fn foo() -> i32 { 1 }\n", "rust")
        names = [d["name"] for d in defs]
        assert "foo" in names

    def test_struct(self):
        from core.kgraph.tree_sitter_parser import extract_definitions_ts
        defs = extract_definitions_ts("struct Bar { x: i32 }\n", "rust")
        names = [d["name"] for d in defs]
        assert "Bar" in names


# ─── Supported extensions ───────────────────────────────────────────────────

class TestSupportedExtensions:
    def test_includes_all_supported(self):
        from core.kgraph.tree_sitter_parser import SUPPORTED_EXTENSIONS
        for ext in [".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".rs"]:
            assert ext in SUPPORTED_EXTENSIONS, f"Missing extension: {ext}"

    def test_excludes_unsupported(self):
        from core.kgraph.tree_sitter_parser import SUPPORTED_EXTENSIONS
        assert ".rb" in SUPPORTED_EXTENSIONS  # v1.4: .rb is now supported
        assert ".java" in SUPPORTED_EXTENSIONS  # v1.4: .java is now supported
        assert ".txt" not in SUPPORTED_EXTENSIONS


# ─── [v1.4.1 P3-4] Errors parameter for parse failure surfacing ──────────

class TestExtractImportsErrorsParam:
    """[v1.4.1 P3-4] extract_imports must surface parse errors when given an errors list."""

    def test_errors_list_populated_on_parse_failure(self):
        """When tree-sitter parsing raises, the error is appended to the errors list.

        We force a failure by clearing the parser cache + patching the
        underlying get_parser to raise. The function must still return an
        empty frozenset (graceful fallback) AND append to the errors list.
        """
        from core.kgraph import tree_sitter_parser as tsp

        # Clear the parser cache so our patched get_parser is called.
        tsp._parsers.clear()

        original_get_parser = tsp._get_parser

        def raising_get_parser(language):
            raise RuntimeError("simulated tree-sitter failure")

        # Patch _get_parser at the module level.
        tsp._get_parser = raising_get_parser
        try:
            errors: list[str] = []
            result = tsp.extract_imports("import os\n", "python", errors=errors)
            # Graceful fallback: empty frozenset.
            assert result == frozenset()
            # Error surfaced.
            assert len(errors) == 1
            assert "tree-sitter parse error" in errors[0]
            assert "python" in errors[0]
            assert "simulated tree-sitter failure" in errors[0]
        finally:
            # Restore the original.
            tsp._get_parser = original_get_parser
            tsp._parsers.clear()

    def test_no_errors_list_no_surface(self):
        """When errors=None (default), parse failures are silently swallowed.

        This preserves the pre-v1.4.1 behavior for callers that don't want
        to surface errors (e.g. the legacy ast_parser wrapper).
        """
        from core.kgraph import tree_sitter_parser as tsp

        tsp._parsers.clear()
        original_get_parser = tsp._get_parser

        def raising_get_parser(language):
            raise RuntimeError("simulated tree-sitter failure")

        tsp._get_parser = raising_get_parser
        try:
            # No errors list passed — should NOT raise, should return empty frozenset.
            result = tsp.extract_imports("import os\n", "python")
            assert result == frozenset()
        finally:
            tsp._get_parser = original_get_parser
            tsp._parsers.clear()


class TestExtractDefinitionsTsErrorsParam:
    """[v1.4.1 P3-4] extract_definitions_ts must surface parse errors too."""

    def test_errors_list_populated_on_parse_failure(self):
        from core.kgraph import tree_sitter_parser as tsp

        tsp._parsers.clear()
        original_get_parser = tsp._get_parser

        def raising_get_parser(language):
            raise RuntimeError("simulated tree-sitter failure")

        tsp._get_parser = raising_get_parser
        try:
            errors: list[str] = []
            result = tsp.extract_definitions_ts("def foo(): pass\n", "python", errors=errors)
            # Graceful fallback: single module chunk.
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["name"] == "<module>"
            # Error surfaced.
            assert len(errors) == 1
            assert "tree-sitter parse error" in errors[0]
            assert "extract_definitions_ts" in errors[0]
        finally:
            tsp._get_parser = original_get_parser
            tsp._parsers.clear()
