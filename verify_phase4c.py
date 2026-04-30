"""
Phase 4c verification — run from D:/mcp/agent/
Tests all 5 new file actions: read_docx, read_xlsx, write_xlsx, read_pptx, write_pptx
"""
print("=== Phase 4c: Office File Actions Verification ===\n")

from tools.file_ops import file

# ── 1. read_docx ─────────────────────────────────────────────────────────────
print("1. file(read_docx)")
r = file(action="read_docx", path="autocode/test_report.docx")
assert r["status"] == "success", f"FAIL: {r}"
assert "Quarterly" in r["text"], f"Expected title in text, got: {r['text'][:100]}"
print(f"   read_docx  → {r['paragraphs']} paragraphs, {r['tables']} tables ✓")
print(f"   first 80 chars: {r['text'][:80]!r}")

# ── 2. write_xlsx ─────────────────────────────────────────────────────────────
print("\n2. file(write_xlsx) — list of dicts")
r = file(
    action="write_xlsx",
    path="autocode/test_sales.xlsx",
    content=[
        {"Month": "January",   "Revenue": 120000, "Orders": 847, "Region": "SP"},
        {"Month": "February",  "Revenue": 145000, "Orders": 923, "Region": "SP"},
        {"Month": "March",     "Revenue": 132000, "Orders": 801, "Region": "RJ"},
        {"Month": "April",     "Revenue": 178000, "Orders": 1102,"Region": "MG"},
    ],
)
assert r["status"] == "success", f"FAIL: {r}"
print(f"   write_xlsx → {r['size']} bytes, sheets: {r['sheets_written']} ✓")

print("\n   write_xlsx — multi-sheet")
r2 = file(
    action="write_xlsx",
    path="autocode/test_multisheet.xlsx",
    content={
        "Sales":   [
            {"Month": "Jan", "Revenue": 120000},
            {"Month": "Feb", "Revenue": 145000},
        ],
        "Clients": [
            {"Name": "Acme",  "Value": 50000},
            {"Name": "Beta",  "Value": 32000},
        ],
    },
)
assert r2["status"] == "success", f"FAIL: {r2}"
print(f"   write_xlsx → {r2['size']} bytes, sheets: {r2['sheets_written']} ✓")

# ── 3. read_xlsx ──────────────────────────────────────────────────────────────
print("\n3. file(read_xlsx)")
r = file(action="read_xlsx", path="autocode/test_sales.xlsx")
assert r["status"] == "success", f"FAIL: {r}"
assert "Sheet1" in r["data"]
sheet = r["data"]["Sheet1"]
assert sheet["columns"] == ["Month", "Revenue", "Orders", "Region"]
print(f"   read_xlsx  → {r['sheet_count']} sheet(s), shape={sheet['shape']} ✓")
print(f"   columns: {sheet['columns']}")
print(f"   first row: {sheet['rows'][0]}")
if r["stats"]:
    rev_stats = r["stats"].get("Revenue", {})
    print(f"   Revenue mean: {rev_stats.get('mean', 'n/a')}")

# ── 4. write_pptx ─────────────────────────────────────────────────────────────
print("\n4. file(write_pptx)")
r = file(
    action="write_pptx",
    path="autocode/test_presentation.pptx",
    content=[
        {
            "layout": "title",
            "title":  "Q3 Performance Review",
            "body":   "Brazilian Market Analysis",
            "subtitle": "MCP Agent Report — April 2026",
        },
        {
            "title":   "Executive Summary",
            "bullets": [
                "Revenue grew 18% year-over-year to R$1.2M",
                "847 new clients acquired in Q3",
                {"text": "Southeast region led growth at +22%", "level": 1},
                {"text": "São Paulo accounted for 45% of total revenue", "level": 1},
                "Operating margin improved by 3.2 percentage points",
            ],
            "notes": "Emphasise the Southeast growth story — key investor question",
        },
        {
            "title":   "Regional Performance",
            "bullets": [
                "Southeast — R$580K (+22%)",
                "South — R$310K (+15%)",
                "Northeast — R$210K (+11%)",
                "Midwest — R$100K (+8%)",
            ],
        },
        {
            "title": "Strategic Priorities — Q4",
            "bullets": [
                "Expand Northeast distribution network",
                "Launch loyalty programme for top 100 clients",
                {"text": "Target: 500 new accounts", "level": 1},
                {"text": "Investment: R$120K marketing budget", "level": 1},
                "Complete ERP integration by December",
            ],
            "notes": "Q4 budget already approved — confirm timeline with ops team",
        },
        {
            "layout": "content",
            "title":  "Thank You",
            "body":   "Questions & Discussion\n\ncontact@company.com.br",
        },
    ],
)
assert r["status"] == "success", f"FAIL: {r}"
print(f"   write_pptx → {r['slide_count']} slides, {r['size']} bytes ✓")

# ── 5. read_pptx ──────────────────────────────────────────────────────────────
print("\n5. file(read_pptx)")
r = file(action="read_pptx", path="autocode/test_presentation.pptx")
assert r["status"] == "success", f"FAIL: {r}"
assert r["slide_count"] == 5, f"Expected 5 slides, got {r['slide_count']}"
print(f"   read_pptx  → {r['slide_count']} slides ✓")
for s in r["slides"]:
    preview = s["texts"][0][:50] if s["texts"] else "(empty)"
    print(f"   Slide {s['slide']}: {preview!r}")

# ── 6. Final registry check ───────────────────────────────────────────────────
print("\n6. Registry check")
from mcp.server.fastmcp import FastMCP
from registry import register_all_tools

mcp   = FastMCP("test")
count = register_all_tools(mcp)
names = sorted([t.name for t in mcp._tool_manager.list_tools()])
print(f"   {count} tools registered: {names}")
assert count == 6
print("   all 6 tools confirmed ✓")

print("\nPhase 4c complete.")
print("Open these in Explorer to verify:")
print("  D:\\mcp\\workspace\\autocode\\test_sales.xlsx")
print("  D:\\mcp\\workspace\\autocode\\test_multisheet.xlsx")
print("  D:\\mcp\\workspace\\autocode\\test_presentation.pptx")
