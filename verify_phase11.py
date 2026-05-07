"""verify_phase11.py -- run from D:/mcp/agent/"""
from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
print("=== Phase 11 verification ===\n")
errors = []

def check(filepath, must_contain, label):
    p = ROOT / filepath
    if not p.exists():
        errors.append(f"MISSING {filepath}"); return
    content = p.read_text(encoding="utf-8")
    try: ast.parse(content)
    except SyntaxError as e:
        errors.append(f"SYNTAX {filepath}: {e}"); return
    if must_contain in content:
        print(f"  OK  {label}")
    else:
        errors.append(f"NOT FOUND: {label}")
        print(f"  FAIL {label}")

# New files
for f in ["core/citations.py", "tools/report_templates.py"]:
    p = ROOT / f
    if p.exists():
        try:
            ast.parse(p.read_text(encoding="utf-8"))
            print(f"  OK  {f} (syntax clean)")
        except SyntaxError as e:
            errors.append(f"SYNTAX {f}: {e}")
            print(f"  FAIL {f}")
    else:
        errors.append(f"MISSING {f}")
        print(f"  FAIL {f} -- not found")

# Patches
check("tools/visualize.py",       "market_report",           "visualize: market_report action")
check("tools/visualize.py",       "code_report",             "visualize: code_report action")
check("workflows/research.py",    "from core.citations",     "research: citations imported")
check("workflows/research.py",    "citations.add(",          "research: citations.add() called")
check("workflows/research.py",    "citations.get_sources",   "research: sources attached to result")
check("tools/workflow_tool.py",   '"report"',                "workflow_tool: report type exposed")

# Citation tracker unit test
print("\n  Running citation tracker tests...")
try:
    sys.path.insert(0, str(ROOT))
    from core.citations import CitationTracker
    ct = CitationTracker()

    # add returns sequential numbers
    n1 = ct.add("t1", url="https://a.com", title="Site A", snippet="fact about A")
    n2 = ct.add("t1", url="https://b.com", title="Site B", snippet="fact about B")
    n3 = ct.add("t1", url="https://a.com", snippet="another fact about A")  # same URL
    assert n1 == 1, f"Expected 1 got {n1}"
    assert n2 == 2, f"Expected 2 got {n2}"
    assert n3 == 1, f"Same URL should return same number, got {n3}"

    # cite returns markers
    assert ct.cite("t1", "https://a.com") == "[1]"
    assert ct.cite("t1", "https://b.com") == "[2]"

    # get_sources returns sorted
    sources = ct.get_sources("t1")
    assert len(sources) == 2
    assert sources[0]["number"] == 1
    assert len(sources[0]["snippets"]) == 2  # two snippets for site A

    # count
    assert ct.count("t1") == 2

    # different trace is isolated
    assert ct.count("t2") == 0

    print("  OK  citation tracker: all assertions passed")
except Exception as e:
    errors.append(f"Citation tracker test failed: {e}")
    print(f"  FAIL citation tracker: {e}")

# Template render test
print("\n  Running template render tests...")
try:
    from tools.report_templates import render_market_report, render_code_report

    html = render_market_report(
        title    = "Test Market Report",
        subtitle = "Unit Test",
        overview = "This is a test overview.",
        research = "Research finding one. [1]\n\nResearch finding two. [2]",
        kpis     = [{"label": "Revenue", "value": "R$1.2M", "delta": "+18%"}],
        charts   = [{"chart_type": "bar", "title": "Monthly",
                     "data": {"x": ["Jan","Feb"], "y": [100, 150]}}],
        sources  = [{"number":1,"url":"https://a.com","title":"Site A","snippets":["fact"]},
                    {"number":2,"url":"https://b.com","title":"Site B","snippets":[]}],
    )
    assert "Test Market Report" in html
    assert "tab-btn" in html
    assert "Sources (2)" in html
    assert "R$1.2M" in html
    print("  OK  market_report template renders")

    html2 = render_code_report(
        title           = "Test Code Report",
        subtitle        = "tools/web.py",
        summary         = "Two issues found.",
        issues          = [{"title":"Timeout","severity":"high",
                            "description":"Timeout too short","fix":"Increase to 30s"}],
        recommendations = [{"title":"Add retries","priority":"medium","body":"Retry 3 times"}],
        changes         = [{"file":"tools/web.py","description":"Changed timeout",
                            "before":"timeout=10","after":"timeout=30"}],
    )
    assert "Test Code Report" in html2
    assert "Issues (1)" in html2
    assert "HIGH" in html2
    assert "Changes (1)" in html2
    print("  OK  code_report template renders")
except Exception as e:
    errors.append(f"Template render test failed: {e}")
    print(f"  FAIL template: {e}")
    import traceback; traceback.print_exc()

print()
if errors:
    print(f"FAILED -- {len(errors)} issue(s):")
    for e in errors: print(f"  {e}")
    sys.exit(1)
else:
    print("All phase11 checks passed.")
    print("\nWhat was added:")
    print("  core/citations.py:       citation tracker (trace-scoped, thread-safe)")
    print("  tools/report_templates.py: market_report + code_report HTML templates")
    print("  tools/visualize.py:      visualize(type='market_report') and type='code_report'")
    print("  workflows/research.py:   auto-citation tracking during web scraping")
    print("  tools/workflow_tool.py:  workflow(type='report') routes through research")
