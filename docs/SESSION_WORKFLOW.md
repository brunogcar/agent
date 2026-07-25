# 🔄 Session Workflow Guide

This guide defines the standard workflow for AI-assisted development sessions on the MCP Agent Stack. It covers getting oriented, the 5-step change workflow, file delivery format, and command conventions.

> **Rule:** Every session follows this workflow. Investigate first, propose a plan, wait for greenlight, then deliver.

> **Enforcement Rule (v1.1):** If the user reminds you of this workflow mid-session, you MUST re-read this entire document before responding, then deliver ALL 5 steps (zip + PowerShell + compile-check + tests + git). A prose summary is NOT a delivery. Partial delivery (e.g. files written to the sandbox but no zip) is NOT a delivery. If you skipped a step, say so explicitly and deliver it — do not paper over the gap with a summary.

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

## ✅ Self-Verification Checklist (BEFORE sending any response that changes code)

Run through this list mentally before you hit send. If any box is unchecked, do not send — fix the gap first.

- [ ] **Investigated** the actual source (Read/Grep/Glob), not just docs?
- [ ] **Proposed** the plan + waited for greenlight (or the user explicitly said "fix it" / "do it")?
- [ ] **Zip built** at `/home/z/my-project/<feature>.zip` with repo-relative paths?
- [ ] **PowerShell block** written (extract + copy + compile-check + test commands)?
- [ ] **Compile-check** command lists every changed `.py` file?
- [ ] **Test commands** include component-specific + full suite, both with `-W error`?
- [ ] **Git block** written separately (not in the extract/copy block), with `git add` listing every changed file?
- [ ] **CHANGELOG.md** updated for any version change?
- [ ] **Full suite passes** in the sandbox (or you explicitly flag which tests can't run due to missing sandbox deps)?
- [ ] **No prose-only summary** — the response contains actual file delivery, not just a description of what you did?

> **Red flag:** If your response says "I built X" but contains no zip path, no PowerShell, and no git block — you have NOT delivered. Go back and build the zip.

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
11. **Never deliver a prose summary instead of a zip** — if you changed code, the response MUST contain a zip path, a PowerShell block, and a git block. "I did X" without the zip is a failed delivery.
12. **Never change a foundational file's call count without updating its tests** — if you add a scan/loop/dispatch branch to a core file (e.g. `registry.py` adds a 3rd `pkgutil.iter_modules` call), EVERY test that mocks that function must be updated in the same commit. Search the test suite for the mocked call site before committing.
13. **Never skip the full test suite** — component tests passing is necessary but not sufficient. Run the full suite (`tests -v -W error`) before declaring done. If the sandbox is missing optional deps (chromadb, langgraph), say so explicitly and list which test dirs couldn't run — don't silently skip them.

---

## 🚫 Anti-Patterns & Lessons Learned

### v1.1 — Registry scan drift (mock-call-count mismatch)
> - **What happened:** `registry.py` was extended to scan `data_sources/` in addition to `tools/` and `skills/` (3 `pkgutil.iter_modules` calls). The 3 tests in `tests/test_registry.py` that mock `iter_modules` were not updated — they only provided 2 `side_effect` entries, so the 3rd call raised `StopIteration`. The break went unnoticed for several commits because the full suite wasn't run.
> - **Why it matters:** A foundational file (`registry.py`) had silently broken tests. The fix was trivial (add a `[]` entry), but the break persisted because "component tests pass" masked it — the registry tests only run in the full suite.
> - **Fix:** Updated all 3 tests to provide 3 `side_effect` entries (tools/ → data_sources/ → skills/). Added Hard Rule #12.
> - **Lesson:** When you add a branch/loop/scan to a core file, grep the test suite for every mock of the functions you touched. The call count changed — the mocks must change too. Same commit.

### v1.1 — Summary-instead-of-zip hallucination
> - **What happened:** After making code changes, the AI responded with a detailed prose summary of what it built ("I implemented phases 1–4...") but provided no zip, no PowerShell, no git commands, and no tests. The user had no files to apply.
> - **Why it matters:** The user cannot push, commit, or verify from a summary. The session workflow exists precisely so the AI delivers copy-pasteable artifacts. Skipping it wastes a full round-trip.
> - **Fix:** Added the Self-Verification Checklist above + Hard Rule #11 + the Enforcement Rule at the top of this doc.
> - **Lesson:** "I built X" is not delivery. A zip at `/home/z/my-project/<feature>.zip` + PowerShell + git is delivery. If the response has no zip path, it is incomplete by definition.

---

## 📚 Cross-References

- **[DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md)** — the 5-file documentation standard (what goes in ARCHITECTURE.md, API.md, CHANGELOG.md, INSTRUCTIONS.md, COMPONENT.md)
- **[TOOLS.md](TOOLS.md)** § "New Tool Checklist" — files to update when adding a new tool
- **[WORKFLOWS.md](WORKFLOWS.md)** § "How to Add a New Workflow" — files to update when adding a new workflow

---

*Last updated: 2026-07-25 (v1.1 — enforcement rule, self-verification checklist, hard rules #11–13, anti-patterns). This guide is updated when the session workflow changes. For documentation structure (what goes in each doc file), see [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md).*
