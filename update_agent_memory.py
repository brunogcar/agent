#!/usr/bin/env python
"""
update_agent_memory.py -- Store correct skill tool usage in agent memory.

Run this ONCE after deploying the skill dispatcher so the agent's memory
reflects the new tool. The agent recalls procedural memory before planning,
so this makes it immediately aware of how to call skill() correctly.

Usage:
  python update_agent_memory.py

Run from: D:/mcp/agent
"""

import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


def main():
    from memory.store import memory

    entries = [
        {
            "text": (
                "SKILL TOOL — B3 API USAGE PATTERNS\n\n"
                "The skill() tool is a registered MCP tool. Call it DIRECTLY like any other tool.\n"
                "DO NOT use python:run_data, workflow, or import skills.b3 — just call skill().\n\n"
                "CORRECT USAGE:\n"
                "  skill(domain='b3_api', mode='status')                          # check sync status\n"
                "  skill(domain='b3_api', mode='sync')                            # sync all 5 files\n"
                "  skill(domain='b3_api', mode='sync', files=['Instruments'])     # sync one file\n"
                "  skill(domain='b3_api', mode='sync', force=True)               # force re-download\n"
                "  skill(domain='b3_api', mode='query', ticker='PETR4')          # query one ticker\n"
                "  skill(domain='b3_api', mode='query', files=['Trades'], limit=20)  # table query\n\n"
                "WRONG (blocked by sandbox):\n"
                "  python(mode='run_data', code='from skills.b3 import route...')  # BLOCKED\n"
                "  workflow(type='data', code='from skills.b3 ...')               # BLOCKED\n\n"
                "B3 data is stored in memory_db/b3/*.db (SQLite). "
                "Instruments: 131K rows. Sync daily on weekdays."
            ),
            "memory_type": "procedural",
            "importance": 10,
            "tags": "skill,b3_api,mcp-tool,usage-patterns",
            "goal": "agent knows how to call skill() tool correctly without import errors",
            "outcome": "success",
        },
        {
            "text": (
                "TOOL CATALOG UPDATE — skill() added to MCP tools\n\n"
                "New tool: skill(domain, mode, **params)\n"
                "  - Registered in MCP via skills/dispatcher.py @tool\n"
                "  - registry.py now scans both tools/ AND skills/ flat modules\n"
                "  - One tool for all skill domains (b3_api, and future: news, macro, etc.)\n\n"
                "Available domains:\n"
                "  b3_api -- B3 Brazilian stock exchange official public data API\n"
                "    modes: sync, query, status\n"
                "    storage: memory_db/b3/*.db (SQLite, one DB per dataset)\n"
                "    source: arquivos.b3.com.br (no auth required)\n\n"
                "cli() shortcut: cli('skill b3_api status') also works for simple domain+mode calls."
            ),
            "memory_type": "semantic",
            "importance": 9,
            "tags": "skill,dispatcher,b3_api,mcp-tools,tool-catalog",
            "goal": "update tool catalog with skill dispatcher",
            "outcome": "success",
        },
        {
            "text": (
                "B3 SYNC STATUS — Instruments synced 2026-05-12\n"
                "File: InstrumentsConsolidatedFile_20260512_1.csv\n"
                "Rows: 131,028 | Size: 48.6 MB | DB: memory_db/b3/instruments.db\n"
                "Other files (Trades, AfterHours, Derivatives, MarginScenario): not yet synced.\n"
                "To sync all: skill(domain='b3_api', mode='sync')\n"
                "To query PETR4: skill(domain='b3_api', mode='query', ticker='PETR4')"
            ),
            "memory_type": "episodic",
            "importance": 7,
            "tags": "b3_api,sync,instruments,status",
            "goal": "track B3 data sync state",
            "outcome": "success",
        },
    ]

    print("Updating agent memory with skill tool patterns...")
    for entry in entries:
        result = memory.store(**entry)
        status = result.get("status", "?")
        snippet = entry["text"][:60].replace("\n", " ")
        print(f"  {status:20s} | {snippet}...")

    print("\nDone. Agent will recall these patterns before next skill() call.")
    print("Verify with: python -c \"from memory.store import memory; print(memory.recall('skill b3_api', top_k=2))\"")


if __name__ == "__main__":
    main()
