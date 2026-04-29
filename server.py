"""
server.py — MCP agent entrypoint.

Minimal by design. All tools are registered via registry.py (auto-discovery).
This file should never contain tool logic — if you find yourself adding
business logic here, it belongs in tools/ instead.
"""

from core.config  import cfg
from core.tracer  import tracer

# Ensure all required directories exist before anything else runs
cfg.ensure_dirs()

from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

mcp = FastMCP("agent")
register_all_tools(mcp)

if __name__ == "__main__":
    tid = tracer.new_trace("startup", goal="server boot")
    tracer.step(tid, "boot", "Agent starting",
                agent_root=str(cfg.agent_root),
                planner=cfg.planner_model,
                executor=cfg.executor_model,
                router=cfg.router_model)
    print(f"Agent root:   {cfg.agent_root}")
    print(f"Memory root:  {cfg.memory_root}")
    print(f"Workspace:    {cfg.workspace_root}")
    print(f"Planner:      {cfg.planner_model}")
    print(f"Executor:     {cfg.executor_model}")
    print(f"Router:       {cfg.router_model}")
    print(f"SearXNG:      {cfg.searxng_url}")
    tracer.finish(tid, success=True, result="boot complete")
    mcp.run()