# 🤖 Autocode Workflow

The `autocode` workflow handles **autonomous code generation and modification**. It takes a natural-language goal, optionally some initial files, and produces working code with tests, verification, and a structured report. It is mode-driven (8 modes — see [API.md](autocode/API.md)), TDD-first, with an iterative 4-phase debug loop, blast-radius impact analysis, optional git/GitHub integration (push/PR/auto-merge), and procedural-memory distillation.

**[v3.11] Claude review fixes — 3 P1 + 4 P2 + 1 P3.** (B1 P1) Adaptive timeout now propagated to `_remaining_timeout()` — feature/fix/refactor tasks with adaptive budgets (900s/600s) no longer get a spurious 1-second subprocess timeout. (B2 P1) HiTL gate surfaces checkpoint-save failures (was: silently swallowed → resume restarted from scratch, potentially producing a different implementation than the human reviewed). (B3 P1) Audit mode no longer silently truncates to 200 files — walks all files first, sorts by line count, surfaces a `truncated` flag + uses the full set for dead-code import scanning (was: false "dead code" verdicts on repos >200 files). (B4 P2) WORKFLOW_METADATA version bumped 3.8→3.11 (was stale; CHANGELOG was at v3.10). (B5 P2) Debug paths (swarm/parallel-subagent/single-subagent) now check cancellation before dispatching LLM calls. (B6 P2) Future-dated docs fixed. (B7 P2) git_ops.py docstring honest about name-only alias (delegates to **git tool v1.3**). (B8 P3) Orphaned `branch_name` field removed from _default_state vcs dict.

The graph is a 32-node LangGraph StateGraph (29 active + 3 backward-compat wrappers — see [NODES.md](autocode/NODES.md)). State is split into 8 typed sub-states behind an accessor layer (see [SUBSTATE.md](autocode/SUBSTATE.md)). Design rationale lives in [ARCHITECTURE.md](autocode/ARCHITECTURE.md); per-version changes in [CHANGELOG.md](autocode/CHANGELOG.md); AI editing rules in [INSTRUCTIONS.md](autocode/INSTRUCTIONS.md). All 17 autocode config flags are documented in [API.md](autocode/API.md).

---

## 🚀 Quick Start

```python
from workflows.base import run_workflow

result = run_workflow(
    workflow_type="autocode",
    goal="Fix the timeout handling in web search",
    mode="fix_error",                      # feature | fix | fix_error | refactor | improve | edit | create_skill | audit
    error_msg="TimeoutError: Request timed out after 30 seconds",
    files={"web.py": "..."},
    trace_id="autocode_001",               # "" → run_workflow creates one
)
print(result["status"])                    # "success" | "failed"
print(result["result"])                    # "Code changes applied successfully: ..."
```

For the full facade signature + config flags table + return shape, see [API.md](autocode/API.md).

---

## 📂 Subfile Directory

| Subfile | Content |
|---------|---------|
| [API.md](autocode/API.md) | Facade signature, all 17 config flags (one table), return shape, state field list (links to SUBSTATE.md) |
| [ARCHITECTURE.md](autocode/ARCHITECTURE.md) | Module tree, dispatch flow (mermaid), 7 bullet design decisions |
| [NODES.md](autocode/NODES.md) | All 32 nodes in one table (name, phase, reads, writes, 1-line purpose) |
| [SUBSTATE.md](autocode/SUBSTATE.md) | 8 TypedDicts, 8 accessor signatures, writers/readers table |
| [CHANGELOG.md](autocode/CHANGELOG.md) | Version history table, completed roadmap (1-line each), open roadmap, deferred items |
| [INSTRUCTIONS.md](autocode/INSTRUCTIONS.md) | NEVER DO (1-line each), ALWAYS DO (1-line each), Anti-Patterns (restored v3.8) |

---

## 🔄 When to Use vs Alternatives

| Need | Tool |
|------|------|
| Fix code errors / add features / improve code / create skills / audit a repo | `autocode` |
| Research a topic (web search + synthesis) | `research` |
| Generate code + execute on data | `data` |
| Iterative deep research with convergence | `deep_research` |
| Static analysis of an unfamiliar codebase | `understand` |
| Optimize a metric via experiment loop | `autoresearch` |
| Structured report generation (tool, not workflow) | `report` |

---

*Last updated: 2026-07-22 (v3.11). See [CHANGELOG.md](autocode/CHANGELOG.md) for version history.*
