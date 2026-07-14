"""core/kgraph/tree_sitter_parser.py — Unified multi-language parser via tree-sitter.

[#4] Multi-language support for the understand workflow.

Replaces the Python-only `ast` parser with tree-sitter, which handles
all supported languages through one API. Currently supports:
  - Python (.py)
  - JavaScript (.js, .mjs, .cjs)
  - TypeScript (.ts, .tsx)
  - Go (.go)
  - Rust (.rs)

Two main functions:
  1. extract_imports(source, language) — dependency edges for the graph
  2. extract_definitions_ts(source, language) — per-definition chunks for embeddings

The old ast_parser.py functions (_parse_dependencies_sync_from_string etc.)
now delegate to this module for Python, keeping backward compatibility.
"""
from __future__ import annotations

import warnings
from typing import Optional

from tree_sitter_languages import get_parser as _ts_get_parser


# ─── Language detection ─────────────────────────────────────────────────────

# File extension → tree-sitter language name
LANGUAGE_MAP = {
    ".py":  "python",
    ".js":  "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts":  "typescript",
    ".tsx": "typescript",
    ".go":  "go",
    ".rs":  "rust",
}

# Languages we support (for discover_files.py)
SUPPORTED_EXTENSIONS = frozenset(LANGUAGE_MAP.keys())

# v1.3: Document file extensions — indexed via chonkie sentence chunking
# (tree-sitter can't parse prose). These files get vector embeddings but no
# graph edges (docs don't have imports).
DOC_EXTENSIONS = frozenset({".md", ".txt", ".rst"})

# All extensions discover_files should find (code + docs)
ALL_SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS | DOC_EXTENSIONS


def get_language_for_file(file_path: str) -> Optional[str]:
    """Return the tree-sitter language name for a file, or None if unsupported."""
    from pathlib import Path
    ext = Path(file_path).suffix.lower()
    return LANGUAGE_MAP.get(ext)


def is_supported(file_path: str) -> bool:
    """Check if a file's extension is supported by the multi-language parser."""
    return get_language_for_file(file_path) is not None


def is_doc_file(file_path: str) -> bool:
    """v1.3: Check if a file is a document (.md/.txt/.rst) — indexed via chonkie, not tree-sitter."""
    from pathlib import Path
    return Path(file_path).suffix.lower() in DOC_EXTENSIONS


# ─── Parser cache (one parser per language) ─────────────────────────────────

_parsers: dict[str, object] = {}


def _get_parser(language: str):
    """Get or create a cached tree-sitter parser for a language.

    Uses warnings.catch_warnings() to suppress the tree-sitter-languages
    FutureWarning — this is immune to -W error on the command line.
    """
    if language not in _parsers:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            _parsers[language] = _ts_get_parser(language)
    return _parsers[language]


# ─── Import extraction ──────────────────────────────────────────────────────

# Import node types per language (tree-sitter query syntax)
# These are the node types that represent import statements in each language's grammar.
_IMPORT_NODE_TYPES = {
    "python":     ["import_statement", "import_from_statement"],
    "javascript": ["import_statement"],
    "typescript": ["import_statement"],
    "go":         ["import_declaration"],
    "rust":       ["use_declaration"],
}


def extract_imports(source: str, language: str) -> frozenset[str]:
    """Extract import/dependency strings from source code.

    Returns a frozenset of module/package names. For Python, these are
    dotted module names (e.g. "core.config"). For JS/TS, they're the
    import paths (e.g. "./foo" or "react"). For Go, package paths.
    For Rust, crate paths.

    Returns empty frozenset on parse failure (graceful degradation).
    """
    if language not in _IMPORT_NODE_TYPES:
        return frozenset()

    try:
        parser = _get_parser(language)
        tree = parser.parse(source.encode("utf-8"))
        root = tree.root_node

        deps = set()
        import_types = _IMPORT_NODE_TYPES[language]

        def walk(node):
            if node.type in import_types:
                text = source[node.start_byte:node.end_byte]
                dep = _extract_module_name(text, language, node, source)
                if dep:
                    # Go multi-imports return newline-separated paths; split them
                    if language == "go" and "\n" in dep:
                        for d in dep.split("\n"):
                            d = d.strip()
                            if d:
                                deps.add(d)
                    else:
                        deps.add(dep)
            for child in node.children:
                walk(child)

        walk(root)
        return frozenset(deps)
    except Exception:
        return frozenset()


def _extract_module_name(import_text: str, language: str, node, source: str) -> str:
    """Extract the module/package name from an import statement's text.

    Each language formats imports differently:
      Python:  "import os" / "from core.config import cfg"
      JS/TS:   'import foo from "./bar"' / 'import { x } from "react"'
      Go:      'import "fmt"' / 'import (\n  "fmt"\n  "os"\n)'
      Rust:    'use std::collections::HashMap'
    """
    if language == "python":
        # "import os" → "os"; "from core.config import cfg" → "core.config"
        text = import_text.strip()
        if text.startswith("from "):
            # from X import Y → X
            parts = text.split()
            if len(parts) >= 2:
                return parts[1]
        elif text.startswith("import "):
            # import X → X (may have "as Y" — take just X)
            parts = text.split()
            if len(parts) >= 2:
                return parts[1].split(",")[0].split(" as ")[0]
        return ""

    elif language in ("javascript", "typescript"):
        # import ... from "path" → path
        # Find the string literal in the import statement
        for child in node.children:
            if child.type == "string":
                return source[child.start_byte:child.end_byte].strip("\"'`")
        return ""

    elif language == "go":
        # import "fmt" → fmt; import ( "fmt" "os" ) → fmt\nos
        # Go import strings are "interpreted_string_literal" nodes inside "import_spec"
        specs = []
        for child in node.children:
            if child.type == "import_spec":
                for s in child.children:
                    if s.type == "interpreted_string_literal":
                        specs.append(source[s.start_byte:s.end_byte].strip('"'))
            elif child.type == "import_spec_list":
                for spec in child.children:
                    if spec.type == "import_spec":
                        for s in spec.children:
                            if s.type == "interpreted_string_literal":
                                specs.append(source[s.start_byte:s.end_byte].strip('"'))
        return "\n".join(specs) if specs else ""

    elif language == "rust":
        # use std::collections::HashMap → std::collections
        # use std::io::{Read, Write} → std::io
        text = import_text.strip()
        if text.startswith("use "):
            text = text[4:]
        # Remove trailing ';' and whitespace
        text = text.rstrip(";").strip()
        # Take the path before any '::{' (grouped imports) or '::' (specific item)
        if "::{" in text:
            text = text[:text.index("::{")]
        elif "::" in text:
            # Keep the full path — it's more useful for dependency tracking
            pass
        return text

    return ""


# ─── Definition extraction (for embeddings) ────────────────────────────────

# Definition node types per language
_DEFINITION_NODE_TYPES = {
    "python":     ["function_definition", "class_definition"],
    "javascript": ["function_declaration", "class_declaration", "method_definition"],
    "typescript": ["function_declaration", "class_declaration", "method_definition"],
    "go":         ["function_declaration", "method_declaration", "type_declaration"],
    "rust":       ["function_item", "struct_item", "enum_item", "impl_item"],
}


def extract_definitions_ts(source: str, language: str) -> list[dict]:
    """Extract top-level definitions from source code for embedding.

    Returns a list of dicts: {name, type, source, line_start, line_end}

    Falls back to a single "module" chunk if the file has no parseable
    definitions (scripts, config files, etc.).
    """
    if language not in _DEFINITION_NODE_TYPES:
        return [{
            "name": "<module>",
            "type": "module",
            "source": source[:4000],
            "line_start": 1,
            "line_end": len(source.splitlines()),
        }]

    try:
        parser = _get_parser(language)
        tree = parser.parse(source.encode("utf-8"))
        root = tree.root_node

        definitions = []
        def_types = _DEFINITION_NODE_TYPES[language]

        def walk(node):
            if node.type in def_types:
                name = _extract_definition_name(node, source, language)
                source_text = source[node.start_byte:node.end_byte]
                if source_text.strip():
                    definitions.append({
                        "name": name,
                        "type": _definition_type(node.type, language),
                        "source": source_text,
                        "line_start": node.start_point[0] + 1,  # tree-sitter is 0-indexed
                        "line_end": node.end_point[0] + 1,
                    })
            for child in node.children:
                walk(child)

        walk(root)

        # Fallback: no definitions found → embed whole file
        if not definitions:
            definitions.append({
                "name": "<module>",
                "type": "module",
                "source": source[:4000],
                "line_start": 1,
                "line_end": len(source.splitlines()),
            })

        return definitions
    except Exception:
        return [{
            "name": "<module>",
            "type": "module",
            "source": source[:4000],
            "line_start": 1,
            "line_end": len(source.splitlines()),
        }]


def _extract_definition_name(node, source: str, language: str) -> str:
    """Extract the name of a function/class/etc. from its tree-sitter node.

    The name is usually in a direct child of type "identifier" or "type_identifier".
    For Go type declarations, the name is nested in a type_spec child.
    """
    # Direct identifier child (most languages)
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            return source[child.start_byte:child.end_byte]

    # Go: type_declaration → type_spec → type_identifier
    if language == "go" and node.type == "type_declaration":
        for child in node.children:
            if child.type == "type_spec":
                for grandchild in child.children:
                    if grandchild.type in ("identifier", "type_identifier"):
                        return source[grandchild.start_byte:grandchild.end_byte]

    return "<anonymous>"


def _definition_type(node_type: str, language: str) -> str:
    """Normalize a tree-sitter node type to a generic definition type."""
    if "function" in node_type or "method" in node_type:
        return "function"
    if "class" in node_type or "struct" in node_type or "impl" in node_type:
        return "class"
    if "enum" in node_type:
        return "class"
    if "type" in node_type:
        return "type"
    return "definition"
