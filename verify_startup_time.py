"""
verify_startup_time.py -- run from D:/mcp/agent/
Measures how long tool registration takes.
LM Studio disconnects if this exceeds ~3 seconds.
Target: under 1 second.
"""
import time
import sys

print("=== Startup Time Verification ===\n")

t0 = time.perf_counter()

from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

mcp   = FastMCP("timing_test")
count = register_all_tools(mcp)

t1 = time.perf_counter()
elapsed = t1 - t0

print(f"Tools registered : {count}")
print(f"Time to register : {elapsed:.3f}s")
print()

if elapsed < 1.0:
    print("FAST - under 1s - LM Studio will not timeout")
elif elapsed < 3.0:
    print("OK - under 3s - should be fine")
else:
    print("SLOW - over 3s - LM Studio will likely timeout")
    print("Check for heavy top-level imports in tools/")
    sys.exit(1)

# Verify heavy libs are NOT loaded yet
import sys as _sys
loaded = [m for m in _sys.modules
          if any(h in m for h in
                 ['chromadb', 'plotly', 'folium', 'pandas', 'pptx', 'fpdf'])]
if loaded:
    print(f"\nWARNING: heavy modules loaded during registration: {loaded[:5]}")
else:
    print("Heavy libs not loaded at registration time - OK")

print("\nStartup time verification complete.")
