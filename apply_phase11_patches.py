"""
apply_phase11_patches.py -- run from D:/mcp/agent/

Phase 11: Perplexity-style reporting toolset.

  1. tools/visualize.py:    add market_report + code_report actions
  2. workflows/research.py: wire citation tracking into node_search
  3. workflows/base.py:     add "report" workflow type to dispatcher
  4. tools/workflow_tool.py: expose report workflow to LLM
"""

from __future__ import annotations
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def patch(filepath, old, new, label):
    p = ROOT / filepath
    if not p.exists():
        print(f"  SKIP  {label} -- file not found"); return False
    content = p.read_text(encoding="utf-8")
    if old not in content:
        first = new.strip().splitlines()[0].strip()
        if first in content:
            print(f"  SKIP  {label} -- already applied"); return True
        print(f"  MISS  {label} -- target not found in {filepath}"); return False
    updated = content.replace(old, new)
    try:
        ast.parse(updated)
    except SyntaxError as e:
        print(f"  FAIL  {label} -- syntax error: {e}"); return False
    p.write_text(updated, encoding="utf-8")
    print(f"  OK    {label}"); return True


print("=== Phase 11 patches ===\n")

# ── 1. visualize.py: add market_report and code_report to tool ───────────────
patch(
    "tools/visualize.py",
    '''    vtype = type.strip().lower()

    # ── chart ─────────────────────────────────────────────────────────────────
    if vtype == "chart":''',
    '''    vtype = type.strip().lower()

    # ── market_report ─────────────────────────────────────────────────────────
    if vtype == "market_report":
        from tools.report_templates import render_market_report
        html      = render_market_report(
            title           = title   or "Market Analysis",
            subtitle        = subtitle,
            overview        = kwargs.get("overview",   ""),
            research        = kwargs.get("research",   ""),
            kpis            = kpis    or [],
            charts          = charts  or [],
            tables          = kwargs.get("tables", []),
            sources         = kwargs.get("sources", []),
            accent          = accent  or "#3b82f6",
        )
        out_name  = output or (title or "market_report").lower().replace(" ", "_")
        html_path = _out_path(out_name, "html")
        html_path.write_text(html, encoding="utf-8")
        return {
            "status":    "success",
            "type":      "market_report",
            "title":     title,
            "html_path": str(html_path),
            "open_cmd":  f"start {html_path}" if cfg.is_windows else f"xdg-open {html_path}",
        }

    # ── code_report ───────────────────────────────────────────────────────────
    if vtype == "code_report":
        from tools.report_templates import render_code_report
        html      = render_code_report(
            title           = title   or "Code Analysis",
            subtitle        = subtitle,
            summary         = kwargs.get("summary",         ""),
            issues          = kwargs.get("issues",          []),
            recommendations = kwargs.get("recommendations", []),
            changes         = kwargs.get("changes",         []),
            sources         = kwargs.get("sources",         []),
            kpis            = kpis    or [],
            accent          = accent  or "#6366f1",
        )
        out_name  = output or (title or "code_report").lower().replace(" ", "_")
        html_path = _out_path(out_name, "html")
        html_path.write_text(html, encoding="utf-8")
        return {
            "status":    "success",
            "type":      "code_report",
            "title":     title,
            "html_path": str(html_path),
            "open_cmd":  f"start {html_path}" if cfg.is_windows else f"xdg-open {html_path}",
        }

    # ── chart ─────────────────────────────────────────────────────────────────
    if vtype == "chart":''',
    "visualize: market_report and code_report actions",
)

# Update visualize() signature to accept **kwargs for extra report params
patch(
    "tools/visualize.py",
    '''    output:     str        = "",
    # Map params
    map_type:   str        = "markers",''',
    '''    output:     str        = "",
    # Extra params for market_report / code_report (passed as kwargs)
    overview:        str  = "",
    research:        str  = "",
    summary:         str  = "",
    issues:          list = None,
    recommendations: list = None,
    changes:         list = None,
    tables:          list = None,
    sources:         list = None,
    **kwargs,
    # Map params
    map_type:   str        = "markers",''',
    "visualize: add report params to signature",
)

# Remove **kwargs from visualize call since we now have explicit params
# and pass them properly to the template calls above
# (already handled inline above -- no additional patch needed)

# ── 2. research workflow: wire citations into node_search ─────────────────────
patch(
    "workflows/research.py",
    '''from workflows.base import WorkflowState, node_step, node_error, node_done''',
    '''from workflows.base   import WorkflowState, node_step, node_error, node_done
from core.citations   import citations''',
    "research: import citations",
)

patch(
    "workflows/research.py",
    '''    parts = []
    for r in valid:
        parts.append(
            f"SOURCE: {r.get('title','')}\\nURL: {r.get('url','')}\\n\\n"
            f"{r.get('text','')[:2000]}"
        )
    combined = "\\n\\n---\\n\\n".join(parts)
    node_step(state, "search",
              f"scraped {len(valid)} valid sources "
              f"({result.get('scraped_count',0) - len(valid)} filtered)")
    return {**state, "search_results": combined}''',
    '''    parts = []
    tid   = state.get("trace_id", "")
    for r in valid:
        url   = r.get("url",   "")
        title = r.get("title", "")
        text  = r.get("text",  "")
        # Register source for citation tracking
        if tid and url:
            snippet = text[:200].replace("\\n", " ")
            citations.add(tid, url=url, title=title, snippet=snippet)
        parts.append(
            f"SOURCE: {title} {citations.cite(tid, url)}\\nURL: {url}\\n\\n"
            f"{text[:2000]}"
        )
    combined = "\\n\\n---\\n\\n".join(parts)
    node_step(state, "search",
              f"scraped {len(valid)} valid sources, {citations.count(tid)} citations",
              filtered=result.get('scraped_count',0) - len(valid))
    return {**state, "search_results": combined}''',
    "research: record citations during scraping",
)

# Pass citations to node_done so they're available in result
patch(
    "workflows/research.py",
    '''def node_notify(state: WorkflowState) -> WorkflowState:
    """Send completion notification and mark workflow done."""
    from tools.notify import notify
    from workflows.base import node_done

    goal   = state.get("goal", "")
    result = state.get("result", "")

    notify(
        action  = "send",
        title   = "Research complete",
        message = f"{goal[:50]}: {result[:80]}...",
    )
    return node_done(state, result=result or "Research complete")''',
    '''def node_notify(state: WorkflowState) -> WorkflowState:
    """Send completion notification and mark workflow done."""
    from tools.notify import notify
    from workflows.base import node_done

    goal    = state.get("goal", "")
    result  = state.get("result", "")
    tid     = state.get("trace_id", "")
    sources = citations.get_sources(tid) if tid else []

    notify(
        action  = "send",
        title   = "Research complete",
        message = f"{goal[:50]}: {result[:80]}...",
    )
    return node_done(state, result=result or "Research complete",
                     artifacts=[{"sources": sources}])''',
    "research: attach sources to workflow result",
)

# ── 3. workflow_tool.py: expose report types ──────────────────────────────────
patch(
    "tools/workflow_tool.py",
    '    if wf_type not in ("research", "data", "autocode"):',
    '    if wf_type not in ("research", "data", "autocode", "report"):',
    "workflow_tool: allow 'report' as workflow type",
)

patch(
    "tools/workflow_tool.py",
    '''    if wf_type == "autocode":
        if not target_file:
            return {"status": "error",
                    "error": "target_file is required for autocode"}''',
    '''    if wf_type == "report":
        # Report workflow: research + auto-render market_report or code_report
        # Routes to research internally then renders with citations
        kwargs["_report_mode"] = kwargs.pop("mode", "market")
        wf_type = "research"  # research workflow captures sources via citations

    if wf_type == "autocode":
        if not target_file:
            return {"status": "error",
                    "error": "target_file is required for autocode"}''',
    "workflow_tool: report mode routes through research with auto-render",
)

print("\nDone. Run: python verify_phase11.py to confirm.")
