```markdown
# Autocode Split Summary

## Overview

The monolithic `workflows/autocode.py` (62KB, 1675 lines) has been split into a modular structure following the user's git split pattern (commit 29a405cccec50340b834a39e701e0a6dd17ec548).

## Structure

```
workflows/
├── autocode.py              # Main entry point (dispatcher)
└── autocode_helpers/        # Split logic
    ├── __init__.py
    ├── constants.py          # 11 SYSTEM constants
    ├── state.py              # AutocodeState + _default_state + tunables
    ├── helpers.py            # 6 utility functions
    ├── test_runner.py        # Disk-based pytest execution
    ├── git_ops.py            # Git helper functions
    ├── routes.py             # Routing functions for state machine
    ├── graph.py              # State machine construction
    └── nodes/                # LangGraph node functions
        ├── __init__.py
        ├── classify.py        # Task classification
        ├── brainstorm.py     # Specification brainstorming
        ├── plan.py           # Structured plan writing
        ├── branch.py         # Git branch creation
        ├── tests.py          # Test generation
        ├── execute.py        # Step execution
        ├── run_tests.py      # Test execution
        ├── debug.py          # Systematic debugging
        ├── write_files.py    # File writing
        ├── verify.py          # Verification gate
        ├── commit.py         # Git commit
        ├── memory.py         # Procedural memory
        └── create_skill.py    # Skill creation

tests/
├── __init__.py
└── workflows/
    ├── __init__.py
    └── test_autocode.py      # Integration tests
```

## Pattern

- **Main file**: `workflows/autocode.py` (dispatcher, entry point)
- **Helpers**: `workflows/autocode_helpers/` (split logic)
- **No Python conflicts**: Different names (`autocode.py` vs `autocode_helpers/`)
- **Follows git pattern**: Same as `tools/git.py` + `tools/git_ops/`

## Preserved Elements

### Modes (7)
- feature
- fix_error
- improve
- add_feature
- edit
- create_skill
- audit

### Superpowers (8)
1. Task Classification
2. Memory Summarization
3. Brainstorming
4. Writing Plans
5. TDD on Disk
6. Systematic Debugging
7. Verification Gate
8. Procedural Memory

### SYSTEM Constants (11)
All preserved in `constants.py`:
- TASK_CLASSIFIER_SYSTEM
- BRAINSTORM_SYSTEM
- AUDIT_BRAINSTORM_SYSTEM
- FIX_BRAINSTORM_SYSTEM
- EDIT_BRAINSTORM_SYSTEM
- REFACTOR_BRAINSTORM_SYSTEM
- CREATE_SKILL_SYSTEM
- PLAN_SYSTEM
- TEST_SYSTEM
- CODER_SYSTEM
- DEBUG_SYSTEM
- VERIFY_SYSTEM

### Functions (25+)
- AutocodeState class
- _default_state
- 6 helpers (_files_context, _extract_code, _parse_json, _parse_json_array, _should_copy_file, _call)
- run_tests_on_disk
- 3 git ops (_git_snapshot, _git_commit, _git_create_branch)
- 12 nodes (classify, brainstorm, plan, branch, tests, execute, run_tests, debug, write_files, write_files_with_flag_reset, verify, commit, memory, create_skill)
- 6 routes (after_classify, after_brainstorm, after_run_tests, after_debug, after_write_files, after_verify)
- 2 graph builders (build_graph, get_graph)
- run_autocode_agent

## Backward Compatibility

All existing imports continue to work:
```python
from workflows.autocode import run_autocode_agent
from workflows.autocode import AutocodeState
from workflows.autocode import TASK_CLASSIFIER_SYSTEM
# ... all other exports
```

## Usage

### Running the workflow
```python
from workflows.autocode import run_autocode_agent

result = run_autocode_agent(
    task="Add input validation to memory store",
    files={"core/memory.py": open("core/memory.py").read()},
    mode="feature",
)
```

### Running tests
```bash
pytest tests/workflows/test_autocode.py -v
```

### Verifying imports
```bash
python -c "from workflows.autocode import run_autocode_agent; print('Import OK')"
```