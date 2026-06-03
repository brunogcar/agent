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
## Agent Usage Instructions
To instruct the agent to build or update the Knowledge Graph, use the following natural language prompt:

> "Please run the understand workflow to build the codebase knowledge graph for the project at [PROJECT_PATH]."

The agent will automatically translate this into the correct tool call:
`json
{
  "tool": "workflow",
  "parameters": {
    "type": "understand",
    "goal": "Build the knowledge graph for the codebase",
    "project_root": "D:/mcp/agent/workspace/projects/my_project"
  }
}
`
*Note: For the agent's own codebase, use project_root: "D:/mcp/agent". For external workspace projects, ensure the source code is located in the code/ subdirectory (e.g., workspace/projects/my_project/code/).*

## Manual Verification Commands
You can manually trigger the workflow or inspect the SQLite database to verify the graph's health without involving the LLM.

### 1. Trigger Workflow Manually
To run the understand workflow synchronously from the command line (using the virtual environment):
`powershell
# For the agent root:
D:\mcp\agent\venv\Scripts\python.exe -c "from workflows.understand import run_understand_workflow_sync; res = run_understand_workflow_sync('D:/mcp/agent', is_agent_root=True); print('Parsed:', res.get('files_parsed'), 'files')"

# For a workspace project:
D:\mcp\agent\venv\Scripts\python.exe -c "from workflows.understand import run_understand_workflow_sync; res = run_understand_workflow_sync('D:/mcp/agent/workspace/projects/my_project', is_agent_root=False); print('Parsed:', res.get('files_parsed'), 'files')"
`

### 2. Inspect the SQLite Graph
To verify the number of nodes (files) and edges (dependencies) stored in the database:
`powershell
D:\mcp\agent\venv\Scripts\python.exe -c "import sqlite3; conn = sqlite3.connect('D:/mcp/agent/.understand/kg.db'); print('Total Nodes:', conn.execute('SELECT COUNT(*) FROM nodes').fetchone()[0]); print('Total Edges:', conn.execute('SELECT COUNT(*) FROM edges').fetchone()[0]); conn.close()"
`
*(Replace the path with your specific project's .understand/kg.db path if checking a workspace project).*