# Understand System: Codebase Knowledge Graph Architecture

## Core Concept
The "Understand" system is a deterministic, local-first Codebase Knowledge Graph adapted from the "Understand-Anything" architecture. It provides the agent with surgical, structural context about any codebase, eliminating blind guessing during the `autocode` workflow.

## Directory Schema & Physical Isolation
The system strictly enforces physical isolation between the agent's own code and external workspace projects.

### 1. Agent Root (Self-Analysis)
- **Source Code**: `D:/mcp/agent/`
- **Artifacts**: `D:/mcp/agent/.understand/` (Added to `.gitignore`)

### 2. Workspace Projects (External Analysis)
- **Project Container**: `D:/mcp/agent/workspace/projects/{project_name}/`
- **Source Code**: `D:/mcp/agent/workspace/projects/{project_name}/code/` (The actual Git clone)
- **Artifacts**: `D:/mcp/agent/workspace/projects/{project_name}/.understand/` (SQLite graph, ChromaDB vectors, cache)

*Rule:* The `ProjectManager` automatically resolves `source_root` and `artifact_root` based on whether `is_agent_root` is True or False.

## Storage Topology (Hybrid Approach)
- **SQLite (`kg.db`)**: The absolute source of truth for graph topology (nodes, edges, file hashes). Fast, deterministic traversal.
- **ChromaDB (`vectors/`)**: Used ONLY for semantic search (e.g., "find auth logic"). NEVER store graph edges in ChromaDB.
- **Disk Cache (`cache/`)**: Stores persistent test indexes (`test_index.json`) and AST metadata.

## LangGraph Integration
- **`workflows/understand.py`**: The dedicated workflow that scans a project, parses files via AST, and populates the SQLite graph.
- **`node_brainstorm`**: Queries the graph for relevant files before calling the Planner LLM, injecting up to 5 files (8KB each) into the context.
- **`node_systematic_debug`**: Queries the graph for "callers" of modified files and injects a "Blast Radius" warning into the debug prompt.
- **`node_analyze_impact`**: Performs "Stale Graph Micro-Updates". It checks file MD5s against `kg.db` and instantly upserts stale nodes/edges from the state snapshot before running impact analysis.

## The Ironclad Rules (What NOT to do)
1. **DO NOT** let Sleep & Learn mutate the graph structure. The graph is deterministic; Sleep & Learn only learns *how to use* it.
2. **DO NOT** store full file contents in LangGraph state. Use the `FileSnapshot` TypedDict (8KB preview + MD5) to prevent checkpoint bloat.
3. **DO NOT** use the default `asyncio.to_thread()` executor for AST parsing. Always use the dedicated `AST_EXECUTOR = ThreadPoolExecutor(max_workers=2)`.
4. **DO NOT** parse files larger than 1MB. Skip them silently.
5. **DO NOT** allow cross-project cache collisions. The AST `@lru_cache` key MUST include `project_id`.
6. **DO NOT** force graph edges into ChromaDB. Vector search is for semantics; SQLite is for structure.