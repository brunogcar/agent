# 🔄 Session Workflow Guide

This guide defines the standard workflow for AI-assisted development sessions on the MCP Agent Stack. It covers getting oriented, the 5-step change workflow, file delivery format, and command conventions.

> **Rule:** Every session follows this workflow. Investigate first, propose a plan, wait for greenlight, then deliver.

---

## 🚀 Getting Oriented (First Task)

1. **Clone the repo** (shallow clone if fresh):
   ```bash
   git clone --depth 1 https://github.com/brunogcar/agent.git
   ```
2. **Read README.md** to understand the architecture
3. **Read the top-level docs:**
   - `docs/TOOLS.md` — tool inventory + meta-tool pattern
   - `docs/WORKFLOWS.md` — workflow catalog + foundation layer
   - `docs/CORE.md` — core subsystem index
   - `docs/SKILLS.md` — skills layer
4. **Check the latest commits:**
   ```bash
   git log -55 --oneline
   ```
5. **Read `docs/TOOLS.md` § "New Tool Checklist"** — lists ALL files to update when adding a new tool
6. **Read `docs/WORKFLOWS.md` § "How to Add a New Workflow"** — same for workflows
7. **Read `docs/DOCUMENTATION_GUIDE.md`** — the 5-file documentation standard

---

## 📋 The 5-Step Change Workflow

Use this for EVERY change. No exceptions.

### Step 1: Investigate First
- Read the relevant code + docs before proposing anything
- Use `Grep` / `Glob` / `Read` tools to understand the current state
- Check tests to understand expected behavior
- Verify claims against actual source (docs drift)

### Step 2: Propose a Plan
- List the files to change
- Describe the changes + design decisions
- Identify findings by priority (P0/P1/P2/P3)
- **Wait for greenlight** — do not start coding until the user approves

### Step 3: Build a Zip
Build a zip at `/home/z/my-project/<feature-name>.zip`:
- **Repo-relative paths** — no wrapper folder, no `__pycache__`
- Example structure:
  ```
  tools/memory.py
  tools/memory_ops/helpers.py
  docs/tools/memory/CHANGELOG.md
  ```

### Step 4: Give PowerShell Commands
The user runs from `(venv) PS D:\mcp\agent>`. Always provide:

1. **Extract** the zip
2. **Copy** all files into the repo (single command, preserves folder structure)
3. **Compile-check** (see compileall format below)
4. **Run component-specific tests** first
5. **Run the full test suite** if component tests pass

### Step 5: Give Git Commands
Provide `git add` + commit message + `git push` in a single block.

---

## 🧪 Compile-Check Format (Preferred)

Use this emoji-output format for visual pass/fail. Replace the file list with the actual changed files:

```powershell
D:\mcp\agent\venv\Scripts\python.exe -c "
import py_compile, sys
files = [
    'tools/memory.py',
    'tools/memory_ops/helpers.py',
    'tests/tools/memory/test_helpers.py',
]
ok = fail = 0
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f'  ✅ {f}')
        ok += 1
    except Exception as e:
        print(f'  ❌ {f}: {e}')
        fail += 1
print(f'\nℹ️  {ok} passed, {fail} failed')
sys.exit(1 if fail else 0)
"
```

**Output looks like:**
```
  ✅ tools/memory.py
  ✅ tools/memory_ops/helpers.py
  ✅ tests/tools/memory/test_helpers.py

ℹ️  3 passed, 0 failed
```

> **Always use the full venv python path:** `D:\mcp\agent\venv\Scripts\python.exe`

---

## 🧪 Test Commands

### Component-specific tests (run first — fastest feedback)
```powershell
D:\mcp\agent\venv\Scripts\python.exe -m pytest tests/tools/memory/ -v -W error --tb=short
```

### Full suite (run after component tests pass)
```powershell
D:\mcp\agent\venv\Scripts\python.exe -m pytest tests -v -W error
```

**Rules:**
- Always include `-W error` (treat warnings as errors) and `--tb=short` (concise tracebacks)
- Always use `python.exe -m pytest` (not bare `pytest`) — ensures the venv pytest is used
- Run component-specific tests first for faster feedback, then the full suite

---

## 📦 Zip Delivery Format

### Build the zip
```bash
cd /home/z/my-project/agent
zip /home/z/my-project/<feature-name>.zip \
  path/to/file1.py \
  path/to/file2.py \
  docs/area/component/CHANGELOG.md
```

### PowerShell extract + copy (single block)
```powershell
# Extract
Expand-Archive -Path "E:\Downloads\<feature-name>.zip" -DestinationPath "E:\Downloads\<feature-name>" -Force

# Copy ALL files into the repo in one command (preserves folder structure)
Copy-Item -Path "E:\Downloads\<feature-name>\*" -Destination "D:\mcp\agent\" -Recurse -Force
```

> **Rules:**
> - Zips use repo-relative paths (no wrapper folder)
> - Single `Copy-Item` command with `-Recurse` — not individual file copies
> - Versioned zip names: `<feature>-v1.zip`, `<feature>-v2.zip`, etc. (when multiple iterations)

---

## 🔧 Git Commands

Provide in a single block. Use `commit -F` for multi-line commit messages:

```powershell
# Stage all changed files
git add path/to/file1.py path/to/file2.py docs/area/component/CHANGELOG.md

# Commit with a file-based message (handles multi-line + special chars)
@'
fix(component): vX.Y — short description

Detailed description of what changed and why.

- P1: finding description + fix
- P2: finding description + fix

Test results: N passed, M skipped.
'@ | Set-Content -Path commitmsg.txt -Encoding utf8
git commit -F commitmsg.txt
Remove-Item commitmsg.txt

# Push
git push
```

> **Commit message format:**
> - First line: `type(component): vX.Y — short description` (type = fix/feat/docs/refactor)
> - Blank line
> - Detailed paragraph (what + why)
> - Blank line
> - Bullet list of findings (P0/P1/P2/P3)
> - Test results line

---

## ⚠️ Hard Rules

1. **Never change code without greenlight** — propose first, wait for approval
2. **Never write `.bak` files** — forbidden by project rules
3. **Never rewrite entire files** when editing — surgical edits only
4. **Never use bare `pytest`** — always `python.exe -m pytest`
5. **Never omit `-W error`** from pytest commands
6. **Never put git commands in the extract/copy block** — keep them separate so the user can copy files first, verify, then commit
7. **Never suggest `http://localhost:3000`** or any local port — the sandbox is not accessible to the user. Use the Preview Panel.
8. **Always investigate before proposing** — read the actual code, don't guess
9. **Always provide compile-check + test commands** — don't assume the user will run them
10. **Always update CHANGELOG.md** for any version change — see `docs/DOCUMENTATION_GUIDE.md` for the CHANGELOG section structure

---

## 📚 Cross-References

- **[DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md)** — the 5-file documentation standard (what goes in ARCHITECTURE.md, API.md, CHANGELOG.md, INSTRUCTIONS.md, COMPONENT.md)
- **[TOOLS.md](TOOLS.md)** § "New Tool Checklist" — files to update when adding a new tool
- **[WORKFLOWS.md](WORKFLOWS.md)** § "How to Add a New Workflow" — files to update when adding a new workflow

---

*Last updated: 2026-07-14. This guide is updated when the session workflow changes. For documentation structure (what goes in each doc file), see [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md).*
