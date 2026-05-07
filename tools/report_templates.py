"""
tools/report_templates.py -- Premium tabbed report templates.

Two template types:
  - market_report:  Market/Financial Analysis with tabs:
                    Overview | Research | Data & Charts | Sources
  - code_report:    Code Analysis Report with tabs:
                    Summary | Issues | Recommendations | Changes | Sources

Usage:
    from tools.report_templates import render_market_report, render_code_report

    html = render_market_report(
        title      = "Tesla Q3 2026 Analysis",
        subtitle   = "Brazilian Market",
        sections   = [...],
        charts     = [...],
        kpis       = [...],
        sources    = [...],
        trace_id   = "abc123",
    )
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

# -- Shared CSS ---------------------------------------------------------------

_BASE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', -apple-system, Arial, sans-serif;
    background: #f0f2f5;
    color: #1a1a2e;
    min-height: 100vh;
}

/* Header */
.report-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: white;
    padding: 40px 48px 32px;
    position: relative;
    overflow: hidden;
}
.report-header::before {
    content: '';
    position: absolute;
    top: -50%;
    right: -10%;
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, rgba(83,150,255,0.15) 0%, transparent 70%);
    border-radius: 50%;
}
.report-header h1 {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.5px;
    margin-bottom: 6px;
    position: relative;
}
.report-header .subtitle {
    font-size: 1rem;
    opacity: 0.7;
    margin-bottom: 16px;
}
.report-meta {
    display: flex;
    gap: 24px;
    font-size: 0.8rem;
    opacity: 0.6;
}
.report-meta span::before { content: ''; }

/* KPI row */
.kpi-strip {
    display: flex;
    gap: 0;
    background: white;
    border-bottom: 1px solid #e8eaf0;
    overflow-x: auto;
}
.kpi-item {
    flex: 1;
    min-width: 140px;
    padding: 20px 24px;
    border-right: 1px solid #e8eaf0;
    text-align: center;
}
.kpi-item:last-child { border-right: none; }
.kpi-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #0f3460;
    line-height: 1;
    margin-bottom: 4px;
}
.kpi-label {
    font-size: 0.75rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.kpi-delta {
    font-size: 0.8rem;
    font-weight: 600;
    margin-top: 4px;
}
.kpi-delta.pos { color: #22c55e; }
.kpi-delta.neg { color: #ef4444; }
.kpi-delta.neu { color: #94a3b8; }

/* Tabs */
.tab-bar {
    background: white;
    border-bottom: 2px solid #e8eaf0;
    padding: 0 48px;
    display: flex;
    gap: 0;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.tab-btn {
    padding: 16px 24px;
    font-size: 0.875rem;
    font-weight: 500;
    color: #64748b;
    border: none;
    background: none;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: all 0.2s;
    white-space: nowrap;
}
.tab-btn:hover { color: #0f3460; }
.tab-btn.active {
    color: #0f3460;
    border-bottom-color: #3b82f6;
    font-weight: 600;
}

/* Tab panels */
.tab-panel { display: none; padding: 32px 48px; }
.tab-panel.active { display: block; }

/* Cards */
.card {
    background: white;
    border-radius: 12px;
    padding: 28px;
    margin-bottom: 24px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.card h2 {
    font-size: 1.1rem;
    font-weight: 600;
    color: #1a1a2e;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 2px solid #f0f2f5;
}
.card p { color: #475569; line-height: 1.7; margin-bottom: 12px; }
.card p:last-child { margin-bottom: 0; }

/* Tables */
table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
th {
    background: #f8fafc;
    color: #1a1a2e;
    padding: 11px 16px;
    text-align: left;
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
td { padding: 11px 16px; border-bottom: 1px solid #f0f2f5; color: #374151; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #fafbff; }

/* Charts */
.chart-wrap {
    border: 1px solid #e8eaf0;
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 20px;
}

/* Sources */
.source-list { list-style: none; }
.source-item {
    display: flex;
    gap: 16px;
    padding: 16px 0;
    border-bottom: 1px solid #f0f2f5;
    align-items: flex-start;
}
.source-item:last-child { border-bottom: none; }
.source-num {
    background: #0f3460;
    color: white;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 700;
    flex-shrink: 0;
    margin-top: 2px;
}
.source-body { flex: 1; }
.source-title { font-weight: 600; color: #1a1a2e; margin-bottom: 4px; }
.source-url {
    font-size: 0.8rem;
    color: #3b82f6;
    word-break: break-all;
    text-decoration: none;
}
.source-url:hover { text-decoration: underline; }
.source-snippet {
    font-size: 0.82rem;
    color: #64748b;
    margin-top: 6px;
    line-height: 1.5;
    font-style: italic;
}

/* Severity badges */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.73rem;
    font-weight: 600;
}
.badge-critical { background: #fee2e2; color: #991b1b; }
.badge-high     { background: #ffedd5; color: #9a3412; }
.badge-medium   { background: #fef9c3; color: #854d0e; }
.badge-low      { background: #dcfce7; color: #166534; }
.badge-info     { background: #dbeafe; color: #1e40af; }

/* Code blocks */
pre {
    background: #1e293b;
    color: #e2e8f0;
    padding: 20px;
    border-radius: 8px;
    overflow-x: auto;
    font-size: 0.82rem;
    line-height: 1.6;
    margin: 12px 0;
}
code { font-family: 'Consolas', 'Monaco', monospace; }

/* Recommendation cards */
.rec-card {
    border-left: 4px solid #3b82f6;
    background: #f8faff;
    border-radius: 0 8px 8px 0;
    padding: 16px 20px;
    margin-bottom: 16px;
}
.rec-card.priority-high   { border-left-color: #ef4444; background: #fff8f8; }
.rec-card.priority-medium { border-left-color: #f59e0b; background: #fffdf0; }
.rec-card.priority-low    { border-left-color: #22c55e; background: #f0fdf4; }
.rec-title { font-weight: 600; color: #1a1a2e; margin-bottom: 6px; }
.rec-body  { color: #475569; font-size: 0.875rem; line-height: 1.6; }

/* Footer */
.report-footer {
    text-align: center;
    padding: 32px;
    color: #94a3b8;
    font-size: 0.8rem;
    border-top: 1px solid #e8eaf0;
    margin-top: 40px;
}

@media (max-width: 768px) {
    .report-header { padding: 24px; }
    .tab-bar       { padding: 0 16px; }
    .tab-panel     { padding: 20px 16px; }
    .kpi-strip     { flex-wrap: wrap; }
    .kpi-item      { min-width: 50%; }
}
"""

_TAB_JS = """
function showTab(id) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('panel-' + id).classList.add('active');
    document.querySelector('[data-tab="' + id + '"]').classList.add('active');
}
"""


# -- KPI helpers --------------------------------------------------------------

def _kpi_html(kpis: list[dict]) -> str:
    if not kpis:
        return ""
    items = []
    for k in kpis:
        delta_val = str(k.get("delta", ""))
        cls = "pos" if delta_val.startswith("+") else "neg" if delta_val.startswith("-") else "neu"
        delta_html = f'<div class="kpi-delta {cls}">{delta_val}</div>' if delta_val else ""
        items.append(
            f'<div class="kpi-item">'
            f'<div class="kpi-value">{k.get("value","")}</div>'
            f'<div class="kpi-label">{k.get("label","")}</div>'
            f'{delta_html}'
            f'</div>'
        )
    return f'<div class="kpi-strip">{"".join(items)}</div>'


def _sources_html(sources: list[dict]) -> str:
    if not sources:
        return '<p style="color:#94a3b8;font-style:italic">No sources recorded.</p>'
    items = []
    for s in sources:
        snippets = "".join(
            f'<div class="source-snippet">"{sn}"</div>'
            for sn in s.get("snippets", [])[:2]
        )
        items.append(
            f'<li class="source-item">'
            f'  <div class="source-num">{s["number"]}</div>'
            f'  <div class="source-body">'
            f'    <div class="source-title">{s.get("title","Untitled")}</div>'
            f'    <a class="source-url" href="{s["url"]}" target="_blank">{s["url"]}</a>'
            f'    {snippets}'
            f'  </div>'
            f'</li>'
        )
    return f'<ul class="source-list">{"".join(items)}</ul>'


def _chart_divs(charts: list[dict], include_plotlyjs: bool = True) -> str:
    """Render a list of chart specs as embedded Plotly divs."""
    if not charts:
        return ""
    try:
        import plotly.graph_objects as go
    except ImportError:
        return '<p style="color:red">plotly not installed</p>'

    out = []
    first = True
    for spec in charts:
        try:
            fig = go.Figure()
            ct  = spec.get("chart_type", "bar").lower()
            d   = spec.get("data", {})
            x, y = d.get("x", []), d.get("y", [])
            col = spec.get("color", "#3b82f6")

            if ct == "bar":
                fig.add_trace(go.Bar(x=x, y=y, marker_color=col))
            elif ct == "line":
                fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers",
                                         line=dict(color=col, width=2)))
            elif ct == "pie":
                fig.add_trace(go.Pie(labels=d.get("labels", x),
                                     values=d.get("values", y), hole=0.35))
            elif ct == "area":
                fig.add_trace(go.Scatter(x=x, y=y, fill="tozeroy",
                                         line=dict(color=col)))
            elif ct == "scatter":
                fig.add_trace(go.Scatter(x=x, y=y, mode="markers",
                                         marker=dict(color=col, size=8)))
            else:
                fig.add_trace(go.Bar(x=x, y=y, marker_color=col))

            fig.update_layout(
                title=dict(text=spec.get("title",""), font=dict(size=14)),
                template="plotly_white", height=320,
                margin=dict(l=40, r=20, t=44, b=40),
                xaxis_title=spec.get("x_label",""),
                yaxis_title=spec.get("y_label",""),
            )
            div = fig.to_html(
                full_html=False,
                include_plotlyjs="cdn" if first and include_plotlyjs else False,
                config={"displayModeBar": True, "responsive": True},
            )
            out.append(f'<div class="chart-wrap">{div}</div>')
            first = False
        except Exception as e:
            out.append(f'<div class="card"><p style="color:red">Chart error: {e}</p></div>')

    return "\n".join(out)


# -- Market / Financial report ------------------------------------------------

def render_market_report(
    title:    str,
    subtitle: str          = "",
    overview: str          = "",
    research: str          = "",
    kpis:     list[dict]   = None,
    charts:   list[dict]   = None,
    tables:   list[dict]   = None,
    sources:  list[dict]   = None,
    accent:   str          = "#3b82f6",
) -> str:
    """
    Premium market/financial analysis report with 4 tabs:
    Overview | Research | Data & Charts | Sources

    Args:
        title:    Report title
        subtitle: Subtitle / context (e.g. "Brazilian Market Q3 2026")
        overview: Executive summary text (can include HTML)
        research: Full research synthesis text (can include HTML, [1] citations)
        kpis:     [{label, value, delta}] -- shown in strip under header
        charts:   [{chart_type, title, data, color, x_label, y_label}]
        tables:   [{title, headers:[str], rows:[[str]]}]
        sources:  [{number, url, title, snippets:[str]}]
        accent:   Accent colour hex
    """
    now    = datetime.now().strftime("%B %d, %Y at %H:%M")
    kpis   = kpis   or []
    charts = charts or []
    tables = tables or []
    sources= sources or []

    # Tables HTML
    tables_html = ""
    for t in tables:
        hdrs = "".join(f"<th>{h}</th>" for h in t.get("headers", []))
        rows = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
            for row in t.get("rows", [])
        )
        tables_html += (
            f'<div class="card">'
            f'<h2>{t.get("title","Table")}</h2>'
            f'<table><thead><tr>{hdrs}</tr></thead><tbody>{rows}</tbody></table>'
            f'</div>'
        )

    charts_html  = _chart_divs(charts)
    sources_html = _sources_html(sources)
    kpi_html     = _kpi_html(kpis)

    # Research text: wrap paragraphs
    research_html = "".join(
        f'<p>{para.strip()}</p>'
        for para in research.split("\n\n") if para.strip()
    ) if research else '<p style="color:#94a3b8">No research content.</p>'

    overview_html = "".join(
        f'<p>{para.strip()}</p>'
        for para in overview.split("\n\n") if para.strip()
    ) if overview else '<p style="color:#94a3b8">No overview provided.</p>'

    tab_ids   = ["overview", "research", "data", "sources"]
    tab_names = ["Overview", "Research", "Data & Charts", f"Sources ({len(sources)})"]
    tab_btns  = "".join(
        f'<button class="tab-btn{"  active" if i==0 else ""}" '
        f'data-tab="{tid}" onclick="showTab(\'{tid}\')">{name}</button>'
        for i, (tid, name) in enumerate(zip(tab_ids, tab_names))
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{_BASE_CSS}
.report-header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, {accent} 100%); }}
.tab-btn.active {{ border-bottom-color: {accent}; color: #1a1a2e; }}
.source-num {{ background: {accent}; }}
.kpi-value  {{ color: {accent}; }}
</style>
</head>
<body>

<div class="report-header">
  <h1>{title}</h1>
  <div class="subtitle">{subtitle}</div>
  <div class="report-meta">
    <span>Generated {now}</span>
    <span>{len(sources)} sources</span>
    <span>{len(charts)} charts</span>
  </div>
</div>

{kpi_html}

<div class="tab-bar">{tab_btns}</div>

<div id="panel-overview" class="tab-panel active">
  <div class="card"><h2>Executive Summary</h2>{overview_html}</div>
  {_chart_divs(charts[:1]) if charts else ""}
</div>

<div id="panel-research" class="tab-panel">
  <div class="card"><h2>Research Findings</h2>{research_html}</div>
</div>

<div id="panel-data" class="tab-panel">
  {charts_html}
  {tables_html}
</div>

<div id="panel-sources" class="tab-panel">
  <div class="card"><h2>Sources & References</h2>{sources_html}</div>
</div>

<div class="report-footer">
  Generated by MCP Agent &nbsp;&middot;&nbsp; {now}
</div>

<script>{_TAB_JS}</script>
</body>
</html>"""


# -- Code analysis report -----------------------------------------------------

def render_code_report(
    title:           str,
    subtitle:        str           = "",
    summary:         str           = "",
    issues:          list[dict]    = None,
    recommendations: list[dict]    = None,
    changes:         list[dict]    = None,
    sources:         list[dict]    = None,
    kpis:            list[dict]    = None,
    accent:          str           = "#6366f1",
) -> str:
    """
    Professional code analysis report with 5 tabs:
    Summary | Issues | Recommendations | Changes | Sources

    Args:
        title:           Report title
        subtitle:        Context (e.g. "tools/web.py -- Performance Review")
        summary:         Overall analysis summary text
        issues:          [{title, severity, description, file, line, fix}]
                         severity: "critical"|"high"|"medium"|"low"|"info"
        recommendations: [{title, priority, body}]
                         priority: "high"|"medium"|"low"
        changes:         [{file, description, before, after}]
                         before/after: code strings (shown in <pre>)
        sources:         [{number, url, title, snippets}]
        kpis:            [{label, value, delta}]
        accent:          Accent colour hex
    """
    now    = datetime.now().strftime("%B %d, %Y at %H:%M")
    issues          = issues          or []
    recommendations = recommendations or []
    changes         = changes         or []
    sources         = sources         or []
    kpis            = kpis            or []

    # Issues HTML
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    sorted_issues = sorted(issues, key=lambda i: sev_order.get(i.get("severity","info"), 4))
    issues_html = ""
    for iss in sorted_issues:
        sev  = iss.get("severity", "info").lower()
        loc  = f'<code>{iss["file"]}</code>' if iss.get("file") else ""
        line = f' line {iss["line"]}' if iss.get("line") else ""
        fix  = f'<p><strong>Fix:</strong> {iss["fix"]}</p>' if iss.get("fix") else ""
        issues_html += (
            f'<div class="card" style="margin-bottom:16px">'
            f'  <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">'
            f'    <span class="badge badge-{sev}">{sev.upper()}</span>'
            f'    <strong>{iss.get("title","Issue")}</strong>'
            f'    <span style="margin-left:auto;font-size:.8rem;color:#94a3b8">{loc}{line}</span>'
            f'  </div>'
            f'  <p>{iss.get("description","")}</p>'
            f'  {fix}'
            f'</div>'
        )
    if not issues_html:
        issues_html = '<p style="color:#22c55e;font-weight:600">No issues found.</p>'

    # Recommendations HTML
    recs_html = ""
    for rec in recommendations:
        pri = rec.get("priority", "medium").lower()
        recs_html += (
            f'<div class="rec-card priority-{pri}">'
            f'  <div class="rec-title">{rec.get("title","")}'
            f'    <span class="badge badge-{"critical" if pri=="high" else "medium" if pri=="medium" else "low"}" '
            f'    style="margin-left:8px">{pri.upper()}</span>'
            f'  </div>'
            f'  <div class="rec-body">{rec.get("body","")}</div>'
            f'</div>'
        )
    if not recs_html:
        recs_html = '<p style="color:#94a3b8;font-style:italic">No recommendations.</p>'

    # Changes HTML
    changes_html = ""
    for ch in changes:
        before = ch.get("before","").replace("<","&lt;").replace(">","&gt;")
        after  = ch.get("after","").replace("<","&lt;").replace(">","&gt;")
        diff   = ""
        if before:
            diff += f'<p style="font-size:.8rem;color:#64748b;margin-bottom:4px">Before:</p><pre><code>{before}</code></pre>'
        if after:
            diff += f'<p style="font-size:.8rem;color:#64748b;margin:8px 0 4px">After:</p><pre><code>{after}</code></pre>'
        changes_html += (
            f'<div class="card">'
            f'  <h2><code style="font-size:.9em">{ch.get("file","")}</code></h2>'
            f'  <p>{ch.get("description","")}</p>'
            f'  {diff}'
            f'</div>'
        )
    if not changes_html:
        changes_html = '<div class="card"><p style="color:#94a3b8;font-style:italic">No code changes recorded.</p></div>'

    # Summary
    summary_html = "".join(
        f'<p>{p.strip()}</p>' for p in summary.split("\n\n") if p.strip()
    ) if summary else '<p style="color:#94a3b8">No summary provided.</p>'

    sources_html = _sources_html(sources)
    kpi_html     = _kpi_html(kpis)

    # Issue count badges for summary
    crit_count = sum(1 for i in issues if i.get("severity") == "critical")
    high_count = sum(1 for i in issues if i.get("severity") == "high")

    tab_ids   = ["summary", "issues", "recs", "changes", "sources"]
    tab_names = [
        "Summary",
        f"Issues ({len(issues)})",
        f"Recommendations ({len(recommendations)})",
        f"Changes ({len(changes)})",
        f"Sources ({len(sources)})",
    ]
    tab_btns = "".join(
        f'<button class="tab-btn{"  active" if i==0 else ""}" '
        f'data-tab="{tid}" onclick="showTab(\'{tid}\')">{name}</button>'
        for i, (tid, name) in enumerate(zip(tab_ids, tab_names))
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{_BASE_CSS}
.report-header {{ background: linear-gradient(135deg, #1a1a2e 0%, #312e81 60%, {accent} 100%); }}
.tab-btn.active {{ border-bottom-color: {accent}; color: #1a1a2e; }}
.source-num {{ background: {accent}; }}
.kpi-value  {{ color: {accent}; }}
</style>
</head>
<body>

<div class="report-header">
  <h1>{title}</h1>
  <div class="subtitle">{subtitle}</div>
  <div class="report-meta">
    <span>Generated {now}</span>
    <span>{len(issues)} issues found</span>
    {f'<span style="color:#ef4444">{crit_count} critical</span>' if crit_count else ''}
    {f'<span style="color:#f97316">{high_count} high</span>' if high_count else ''}
    <span>{len(recommendations)} recommendations</span>
  </div>
</div>

{kpi_html}

<div class="tab-bar">{tab_btns}</div>

<div id="panel-summary" class="tab-panel active">
  <div class="card"><h2>Analysis Summary</h2>{summary_html}</div>
</div>

<div id="panel-issues" class="tab-panel">
  {issues_html}
</div>

<div id="panel-recs" class="tab-panel">
  {recs_html}
</div>

<div id="panel-changes" class="tab-panel">
  {changes_html}
</div>

<div id="panel-sources" class="tab-panel">
  <div class="card"><h2>Sources & References</h2>{sources_html}</div>
</div>

<div class="report-footer">
  Generated by MCP Agent &nbsp;&middot;&nbsp; {now}
</div>

<script>{_TAB_JS}</script>
</body>
</html>"""
