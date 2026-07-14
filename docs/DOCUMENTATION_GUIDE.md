# 📚 Documentation Structure Guide

This guide defines the universal 5-file documentation standard for all components in the MCP Agent Stack: **tools**, **core**, **workflows**, **skills**, and any other major subsystem.

> **Rule:** Every major component gets a root-level landing page (`docs/<area>/COMPONENT.md`) plus a subfolder (`docs/<area>/component/*.md`) containing the detailed split files. No exceptions.

> **Auto-correction rule:** This guide is updated every session with lessons learned. When splitting a file, if the original doc has a section that doesn't fit the default mapping, place it where it makes sense and flag it — but **never delete or omit original content**. The guide is a living document, not a rigid template.

---

## The 5-File Standard

| File | Purpose | Reader | Max Size | Notes |
|------|---------|--------|----------|-------|
| **`COMPONENT.md`** | Landing page | Anyone | ~5 KB | Brief overview, quick start, config, subfile directory |
| **`ARCHITECTURE.md`** | "You will know all the files" | New developer / debugger | ~15 KB | File maps, design decisions, test trees, mermaid diagrams, source code reference |
| **`API.md`** | The contract | Tool user / integrator | ~30 KB | Signatures, actions, validation, errors, security. No version history. |
| **`CHANGELOG.md`** | History & future | Maintainer / planner | ~20 KB | Breaking changes, completed, in-progress, deferred. Self-contained. |
| **`INSTRUCTIONS.md`** | Rules for AI editors | AI assistants | ~5 KB | NEVER DO, ALWAYS DO, Anti-patterns. No API details. No architecture. |

---

## File-by-File Rules

### `COMPONENT.md` (Root-level landing page)

**Root filename = component name exactly.** `CLI.md`, `FILE.md`, `GIT.md`, `WEB.md`, `TAVILY.md` — never `INDEX.md`. The subfolder name is lowercase, matching the component name.

**What goes in:**
- 3-5 bullet overview (condensed from the original characteristic wall)
- Quick Start (placeholder if original had none)
- When to Use vs. Alternatives (tools only)
- Configuration (`.env` variables, requirements)
- **Subfile directory** - one-liner + link for each subfile

**What stays out:**
- Architecture trees, mermaid diagrams, design decisions
- Full parameter tables, action details, error tables
- Version history, breaking changes, roadmap
- AI instructions, anti-patterns, NEVER DO rules
- Test coverage tables, mock strategy

**Cross-referencing:**
- Every link must use relative paths: `see [Error Handling](API.md#error-handling)`
- Never duplicate content from subfiles

---

### `ARCHITECTURE.md` (The file map)

**What goes in:**
- **🔗 Source Code Reference** (mandatory table): `file.py` -> single-sentence purpose
- Source module tree (text diagram)
- Test module tree (text diagram)
- Dispatch / data flow (mermaid diagrams)
- Key design decisions (grouped by subsystem: Bridge, State, Resilience, SSRF, etc.)
- Testing: coverage summary tables, mock strategy, run commands

**What stays out:**
- Full action documentation (params, returns, error cases)
- Breaking changes or version history
- AI editing rules
- Quick start examples

---

### `API.md` (The detailed contract)

**What goes in:**
- Tool signature + full parameter table (tools) / API overview (core)
- Every action / operation: validation rules, return format, error cases, version additions
- Security & validation rules (SSRF, tag validation, input guards)
- Error handling classification table
- Output & pruning (if applicable)

**What stays out:**
- Architecture trees or file maps (link to ARCHITECTURE.md)
- Version history or roadmap (link to CHANGELOG.md)
- AI editing rules (link to INSTRUCTIONS.md)
- Test coverage tables (link to ARCHITECTURE.md)

---

### `CHANGELOG.md` (Self-contained history)

**Section order (mandatory):**
1. `## ✅ Completed` — parent category for the two completed-record sub-sections below.
2. `### 📝 Version History` — table with Version, Date, Summary. Always present, even if empty with placeholder notice. Newest-first.
3. `### ⚠️ Breaking Changes` — detailed per-version tables (only versions with breaking changes). Newest-first, same chronological order as Version History. Never merge with roadmap.
4. `## 🔄 In Progress / Next Up` — planned features only, prioritized. When an item ships, it moves UP into Version History + Breaking Changes (remove from In Progress).
5. `## 🚫 Deferred / Out of Scope` — explicitly rejected or postponed.

> **Why no separate `## Completed` table:** Version History + Breaking Changes together ARE the completed record. Version History answers "when did X ship?" Breaking Changes answers "what exactly changed?" A separate Completed table duplicates Version History. Done roadmap items leave "In Progress" and live only in Version History/Breaking Changes.

**What goes in:**
- Version history table (always first under Completed, always present)
- Breaking changes (detailed per-version tables, under Version History)
- In progress / next up (planned only — ✅ done items move up)
- Deferred / out of scope

**What stays out:**
- Architecture explanations
- API details or parameter tables
- AI editing rules
- Quick start or configuration

> **Rule:** New releases are appended to Version History + Breaking Changes without touching any other doc file.

> **Adaptation rule:** If the original doc has a "Roadmap" section with mixed `✅` completed and planned items, split them: `✅` items go to Version History (if not already there), planned items go to In Progress / Next Up. Never force a mixed section into a single bucket.

> **Version rule:** Preserve existing version numbers exactly. If the original doc has v1, v1.1, v2, etc., keep them. "Pre-v1" only applies to components that have never been versioned. Never flatten or rename version numbers.

> **Ordering rule:** Version History and Breaking Changes must be in the SAME chronological order (newest-first). This keeps the two sub-sections parallel — the reader can scan Version History for the "when" and Breaking Changes for the "what" at the same position.

---

### `INSTRUCTIONS.md` (AI editing rules)

**What goes in:**
- `## ❌ NEVER DO` rules (numbered, imperative, unambiguous) — separate section
- `## ✅ ALWAYS DO` rules (numbered independently) — separate section
- **Anti-patterns & Lessons Learned** - even if empty, include the heading as a placeholder so future AI editors fill it with relevant information from their own mistakes
- Hard constraints only

**What stays out:**
- API details, parameter tables, action docs
- Architecture explanations or file maps
- Version history or roadmap
- Quick start or configuration

> **Rule:** An AI assistant editing this component should be able to read ONLY `INSTRUCTIONS.md` and know what not to break.

> **Never use `## ✅ DO vs ❌ DON'T` tables.** Use separate `## ❌ NEVER DO` and `## ✅ ALWAYS DO` sections, numbered independently. Tables obscure the imperative voice and make scanning harder.

---

## Folder Layout

```text
docs/
├── DOCUMENTATION_GUIDE.md       # This file
├── tools/
│   ├── TAVILY.md                # Landing page (root index)
│   ├── AGENT.md                 # Landing page (root index)
│   ├── MEMORY.md                # Landing page (root index)
│   ├── tavily/
│   │   ├── ARCHITECTURE.md
│   │   ├── API.md
│   │   ├── CHANGELOG.md
│   │   └── INSTRUCTIONS.md
│   ├── agent/
│   │   ├── ARCHITECTURE.md
│   │   ├── API.md
│   │   ├── CHANGELOG.md
│   │   └── INSTRUCTIONS.md
│   └── memory/
│       ├── ARCHITECTURE.md
│       ├── API.md
│       ├── CHANGELOG.md
│       └── INSTRUCTIONS.md
├── core/
│   ├── MEMORY.md                # Landing page (root index)
│   ├── LLM.md                   # Landing page (root index)
│   ├── NET.md                   # Landing page (root index)
│   └── memory/
│       ├── ARCHITECTURE.md
│       ├── API.md               # Core uses API.md, same as tools
│       ├── CHANGELOG.md
│       └── INSTRUCTIONS.md
└── workflows/
    ├── RESEARCH.md              # Landing page (root index)
    └── research/
        ├── ARCHITECTURE.md
        ├── API.md               # Workflows use API.md, same as tools
        ├── CHANGELOG.md
        └── INSTRUCTIONS.md
```

---

## Naming Conventions

- **Root index:** `docs/<area>/COMPONENT.md` (e.g., `docs/tools/TAVILY.md`, `docs/tools/CLI.md`, `docs/tools/FILE.md`)
- **Subfolder:** `docs/<area>/component/` (lowercase, matching the component name)
- **Subfiles:** `ARCHITECTURE.md`, `API.md`, `CHANGELOG.md`, `INSTRUCTIONS.md`
- **Case:** All subfiles are UPPERCASE to match the root index style
- **No component names in H1/category titles:** Use generic titles only. `# 🗺️ Changelog`, not `# 🗺️ CLI Changelog`. `# 🏗️ Architecture`, not `# 🏗️ CLI Architecture`. The back-link and folder already identify the component.

---

## When to Split Further

If any single file exceeds **30 KB**, split it into sub-subfiles:

- `API.md` too big? -> `API.md` (index of actions) + `API_SEARCH.md`, `API_EXTRACT.md`, etc.
- `CHANGELOG.md` too big? -> `CHANGELOG.md` (recent) + `CHANGELOG_LEGACY.md` (older versions)
- `ARCHITECTURE.md` too big? -> `ARCHITECTURE.md` + `ARCHITECTURE_TESTS.md`

Always update the parent file's subfile directory when splitting.

---

## Content Mapping (Original -> New)

| Original Section | Target File | Adaptation Notes |
|------------------|-------------|------------------|
| Overview (characteristic wall) | `COMPONENT.md` (3-4 bullets) + `ARCHITECTURE.md` (design decisions) | |
| Quick Start | `COMPONENT.md` | Placeholder if original had none |
| When to Use vs. Alternatives | `COMPONENT.md` | **Never** in API.md or subfiles |
| Architecture (tree, mermaid, design decisions) | `ARCHITECTURE.md` | |
| Tool Signature + Parameter Table | `API.md` | |
| Actions / Operations (full docs) | `API.md` | |
| Security / Validation | `API.md` | |
| Error Handling Table | `API.md` | |
| Configuration | `COMPONENT.md` | |
| Output & Pruning | `API.md` | |
| Testing (layout, coverage, mock strategy) | `ARCHITECTURE.md` | |
| Breaking Changes | `CHANGELOG.md` | Under `⚠️ Breaking Changes`, never merged with roadmap |
| Roadmap (mixed ✅/planned) | `CHANGELOG.md` | Split: `✅` → Completed, planned → In Progress / Next Up |
| AI Instructions (NEVER DO) | `INSTRUCTIONS.md` | Separate `❌ NEVER DO` and `✅ ALWAYS DO` sections, numbered independently |
| Source Code Reference | `ARCHITECTURE.md` | Single section, starts right under `# 🏗️ Architecture` |
| Anti-patterns & Lessons Learned | `INSTRUCTIONS.md` | |
| `@meta_tool` Decorator docs | `ARCHITECTURE.md` (Key Design Decisions) | Never omit — if original has it, it goes somewhere |
| Known Tradeoffs / Limitations | `ARCHITECTURE.md` (Key Design Decisions) | |
| `@meta_tool` cross-reference to other tools | `ARCHITECTURE.md` | Never replace with "see other doc" — include the content |

---

## Cross-Referencing Rules

1. **Never duplicate content.** Link instead.
2. **Use relative paths:** `[Error Handling](API.md#error-handling)`
3. **Anchor headings** for deep links: `## ⚡ Actions` -> `## Actions` (clean anchors)
4. **Subfile directory** in `COMPONENT.md` must list all subfiles with one-line descriptions
5. **Back-links** in subfiles: add "<- Back to [Component Overview](../COMPONENT.md)" at the top

---

## Creating New Docs

When adding a new major component:

1. Create the root index: `docs/<area>/NEWCOMPONENT.md`
2. Create the subfolder: `docs/<area>/newcomponent/`
3. Create all 5 subfiles (even if some are stubs)
4. Fill `COMPONENT.md` first - it defines the contract for the other files
5. Fill `INSTRUCTIONS.md` second - it protects against bad edits
6. Fill `ARCHITECTURE.md` third - it maps the codebase
7. Fill `API.md` - the detailed contract
8. Fill `CHANGELOG.md` last - version history accumulates over time

---

## AI Assistant Rules (Hard Constraints)

These rules are for AI assistants splitting docs. They are non-negotiable.

1. **Never omit original content.** If the original doc has a section, it goes somewhere in the split. No "cross-reference" excuses, no "not file-specific" judgments. Place it where it makes sense and flag it for review.
2. **Preserve existing version numbers exactly.** If the original doc has v1, v1.1, v2, etc., keep them. "Pre-v1" only for never-versioned components. Never flatten or rename.
3. **Version History table always present in CHANGELOG.** Even if empty, include the table with placeholder notice: `*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*`
4. **Version History comes BEFORE Breaking Changes** in CHANGELOG.
5. **Never merge Breaking Changes with Roadmap.** `⚠️ Breaking Changes` and `🔄 In Progress / Next Up` are separate sections. Breaking changes go under `⚠️ Breaking Changes`. Roadmap items go under `🔄 In Progress / Next Up` and `🚫 Deferred / Out of Scope`.
6. **Never use `## ✅ DO vs ❌ DON'T` tables.** Use separate `## ❌ NEVER DO` and `## ✅ ALWAYS DO` sections, numbered independently. Tables obscure the imperative voice.
7. **No component names in any H1/category titles.** Generic only: `Changelog`, `Architecture`, `API Reference`, `AI Instructions`. The back-link and folder already identify the component.
8. **Root filename = component name.** `CLI.md`, `FILE.md`, `GIT.md`, `WEB.md` — never `INDEX.md`.
9. **"When to Use vs Alternatives" = root COMPONENT.md only.** Never in API.md or any subfile.
10. **Zip preserves exact folder structure.** `COMPONENT.md` at root, `component/*.md` in subfolder.
11. **Follow the pattern, adapt old docs to fit.** Old sections that don't map cleanly get split or placed where they make sense, but nothing gets dropped. Adaptation over rigidity.
12. **Never create `.bak` files** when applying fixes.
13. **Never rewrite entire files** when editing. Surgical edits only. Preserve existing code exactly.

> **Items 14-18 moved to [SESSION_WORKFLOW.md](SESSION_WORKFLOW.md):** pytest flags, venv python path, zip delivery format, PowerShell command order, and temp-file cleanup now live in the session workflow guide (they're session conventions, not documentation structure rules).

---

## 🔗 Cross-References

- **[SESSION_WORKFLOW.md](SESSION_WORKFLOW.md)** — session workflow (getting oriented, 5-step change workflow, compile-check format, test commands, zip delivery, git commands). Read this before starting any session.
- **[TOOLS.md](TOOLS.md)** § "New Tool Checklist" — files to update when adding a new tool
- **[WORKFLOWS.md](WORKFLOWS.md)** § "How to Add a New Workflow" — files to update when adding a new workflow

---

*Last updated: 2026-07-14. Applies to all docs in `docs/tools/`, `docs/core/`, `docs/workflows/`, `docs/skills/`, and future areas. For session workflow conventions (compile-check, test commands, zip delivery, git format), see [SESSION_WORKFLOW.md](SESSION_WORKFLOW.md).*
