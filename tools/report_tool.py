"""
tools/report.py — Report meta-tool.

Produces self-contained HTML files (no server required — open in any browser).
Can also export charts as PNG/PDF via kaleido.

The LLM sees ONE tool: report(type, ...)

Types:
  chart     → Plotly interactive chart (bar, line, scatter, pie, histogram,
               heatmap, box, area, treemap, funnel)
  map       → Folium interactive map (markers, heatmap, choropleth, route)
  report    → HTML report with embedded charts, tables, and text
  dashboard → Multi-panel HTML with N charts in a responsive grid

Data input — two modes supported:
  inline    → data={"x": [...], "y": [...]}  (small datasets)
  from file → data_path="file.csv" / "file.json" (large datasets)

All outputs saved to workspace/visualizations/ by default.
Output path is always returned so the user knows where to open it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from core.config import cfg
from registry import tool

# ── Output directory ──────────────────────────────────────────────────────────

def _out_dir() -> Path:
    d = cfg.workspace_root / "visualizations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _out_path(name: str, ext: str = "html") -> Path:
    ts   = time.strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return _out_dir() / f"{safe}_{ts}.{ext}"


# ── Data loader ───────────────────────────────────────────────────────────────

def _load_data(
    data:      Any    = None,
    data_path: str    = "",
    x_col:     str    = "",
    y_col:     str    = "",
    label_col: str    = "",
) -> tuple[Optional[Any], str]:
    """
    Load data from inline dict/list or from a file.
    Returns (data_object, error_string).
    data_object is whatever the caller needs — could be dict, list, or DataFrame.
    """
    # Inline data takes priority
    if data is not None:
        return data, ""

    if not data_path:
        return None, "Provide either data= (dict/list) or data_path= (path to CSV/JSON)"

    from tools.file_ops import _safe_resolve
    p, err = _safe_resolve(data_path)
    if err:
        return None, err
    if not p.exists():
        return None, f"File not found: {p}"

    suffix = p.suffix.lower()

    try:
        if suffix == ".json":
            raw = json.loads(p.read_text(encoding="utf-8"))
            return raw, ""

        if suffix == ".csv":
            import pandas as pd
            df = pd.read_csv(str(p))
            # If caller specified columns, extract them to a simple dict
            if x_col and y_col and x_col in df.columns and y_col in df.columns:
                result: dict = {"x": df[x_col].tolist(), "y": df[y_col].tolist()}
                if label_col and label_col in df.columns:
                    result["labels"] = df[label_col].tolist()
                return result, ""
            # Otherwise return the full DataFrame
            return df, ""

        if suffix in (".xlsx", ".xls"):
            import pandas as pd
            df = pd.read_excel(str(p))
            if x_col and y_col and x_col in df.columns and y_col in df.columns:
                result = {"x": df[x_col].tolist(), "y": df[y_col].tolist()}
                if label_col and label_col in df.columns:
                    result["labels"] = df[label_col].tolist()
                return result, ""
            return df, ""

        return None, f"Unsupported file type '{suffix}'. Use .csv, .json, .xlsx"

    except Exception as e:
        return None, f"Failed to load {data_path}: {type(e).__name__}: {e}"


# ── Chart builder ─────────────────────────────────────────────────────────────

def _build_chart(
    chart_type: str,
    data:       Any,
    title:      str,
    x_label:    str,
    y_label:    str,
    color:      str,
    output:     str,
    export_png: bool,
) -> dict:
    try:
        import plotly.graph_objects as go
        import plotly.express as px
    except ImportError:
        return {"status": "error", "error": "plotly not installed. Run: pip install plotly"}

    chart_type = chart_type.lower().strip()
    fig        = None

    # ── Normalise data to x/y lists ───────────────────────────────────────────
    import pandas as pd

    if isinstance(data, pd.DataFrame):
        # DataFrame passed directly — use first two columns as x/y
        cols = data.columns.tolist()
        x_data = data[cols[0]].tolist() if len(cols) > 0 else []
        y_data = data[cols[1]].tolist() if len(cols) > 1 else []
        labels = data[cols[2]].tolist() if len(cols) > 2 else None
    elif isinstance(data, dict):
        x_data  = data.get("x", data.get("labels", data.get("categories", [])))
        y_data  = data.get("y", data.get("values", data.get("counts", [])))
        labels  = data.get("labels", None)
        z_data  = data.get("z", None)          # for heatmap
        names   = data.get("names", x_data)   # for pie
        sizes   = data.get("sizes", y_data)   # for bubble
        lat     = data.get("lat", [])
        lon     = data.get("lon", [])
    elif isinstance(data, list):
        # List of numbers — treat as y values, x = index
        y_data = data
        x_data = list(range(len(data)))
        labels = None
    else:
        return {"status": "error", "error": f"Unsupported data type: {type(data).__name__}"}

    # ── Build figure by type ──────────────────────────────────────────────────
    try:
        if chart_type == "bar":
            fig = go.Figure(go.Bar(x=x_data, y=y_data, marker_color=color or "#4C78A8"))

        elif chart_type == "line":
            fig = go.Figure(go.Scatter(x=x_data, y=y_data, mode="lines+markers",
                                       line=dict(color=color or "#4C78A8", width=2)))

        elif chart_type == "scatter":
            marker = dict(color=color or "#4C78A8", size=8)
            if labels:
                marker["color"] = list(range(len(labels)))
                marker["colorscale"] = "Viridis"
            fig = go.Figure(go.Scatter(x=x_data, y=y_data, mode="markers",
                                       marker=marker, text=labels))

        elif chart_type == "area":
            fig = go.Figure(go.Scatter(x=x_data, y=y_data, fill="tozeroy",
                                       mode="lines", line=dict(color=color or "#4C78A8")))

        elif chart_type == "pie":
            if isinstance(data, dict):
                fig = go.Figure(go.Pie(labels=names, values=sizes,
                                       hole=data.get("hole", 0)))
            else:
                fig = go.Figure(go.Pie(labels=x_data, values=y_data))

        elif chart_type == "histogram":
            values = y_data if y_data else x_data
            fig = go.Figure(go.Histogram(x=values, marker_color=color or "#4C78A8",
                                         nbinsx=data.get("bins", 20) if isinstance(data, dict) else 20))

        elif chart_type == "box":
            if isinstance(data, dict) and "groups" in data:
                fig = go.Figure()
                for group, values in data["groups"].items():
                    fig.add_trace(go.Box(y=values, name=group))
            else:
                fig = go.Figure(go.Box(y=y_data, marker_color=color or "#4C78A8"))

        elif chart_type == "heatmap":
            if isinstance(data, dict) and "z" in data:
                fig = go.Figure(go.Heatmap(
                    z=data["z"], x=data.get("x"), y=data.get("y"),
                    colorscale=data.get("colorscale", "RdBu"),
                ))
            else:
                return {"status": "error",
                        "error": "heatmap requires data={'z': [[...]], 'x': [...], 'y': [...]}"}

        elif chart_type == "treemap":
            if isinstance(data, dict) and "parents" in data:
                fig = go.Figure(go.Treemap(
                    labels=data.get("labels", x_data),
                    parents=data["parents"],
                    values=data.get("values", y_data),
                ))
            else:
                return {"status": "error",
                        "error": "treemap requires data={'labels': [...], 'parents': [...], 'values': [...]}"}

        elif chart_type == "funnel":
            fig = go.Figure(go.Funnel(y=x_data, x=y_data,
                                      marker=dict(color=color or "#4C78A8")))

        elif chart_type == "bubble":
            sizes_scaled = [s / max(sizes) * 60 for s in sizes] if sizes else [10] * len(x_data)
            fig = go.Figure(go.Scatter(
                x=x_data, y=y_data,
                mode="markers",
                marker=dict(size=sizes_scaled, color=color or "#4C78A8",
                            sizemode="diameter"),
                text=labels or x_data,
            ))

        else:
            return {"status": "error",
                    "error": (f"Unknown chart_type '{chart_type}'. "
                              "Use: bar | line | scatter | area | pie | histogram | "
                              "box | heatmap | treemap | funnel | bubble")}

    except Exception as e:
        return {"status": "error", "error": f"Chart build failed: {type(e).__name__}: {e}"}

    # ── Apply layout ──────────────────────────────────────────────────────────
    fig.update_layout(
        title=dict(text=title, font=dict(size=18)),
        xaxis_title=x_label,
        yaxis_title=y_label,
        template="plotly_white",
        margin=dict(l=60, r=40, t=60, b=60),
        font=dict(family="Inter, Arial, sans-serif", size=13),
    )

    # ── Save ──────────────────────────────────────────────────────────────────
    out_name = output or title.lower().replace(" ", "_") or "chart"
    html_path = _out_path(out_name, "html")

    try:
        fig.write_html(str(html_path), include_plotlyjs="cdn", full_html=True)
    except Exception as e:
        return {"status": "error", "error": f"Failed to save HTML: {e}"}

    result = {
        "status":     "success",
        "type":       "chart",
        "chart_type": chart_type,
        "title":      title,
        "html_path":  str(html_path),
        "open_cmd":   f"start {html_path}" if cfg.is_windows else f"xdg-open {html_path}",
    }

    if export_png:
        try:
            png_path = html_path.with_suffix(".png")
            fig.write_image(str(png_path), width=1200, height=700, scale=2)
            result["png_path"] = str(png_path)
        except Exception as e:
            result["png_warning"] = f"PNG export failed (kaleido issue?): {e}"

    return result


# ── Map builder ───────────────────────────────────────────────────────────────

def _build_map(
    map_type:   str,
    data:       Any,
    title:      str,
    center_lat: float,
    center_lon: float,
    zoom:       int,
    output:     str,
) -> dict:
    try:
        import folium
    except ImportError:
        return {"status": "error", "error": "folium not installed. Run: pip install folium"}

    map_type = map_type.lower().strip()
    m = folium.Map(
        location=[center_lat or -15.78, center_lon or -47.93],
        zoom_start=zoom or 5,
        tiles="CartoDB positron",
    )

    # Add title overlay
    if title:
        title_html = f"""
        <div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
                    background: white; padding: 8px 20px; border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.2); z-index: 9999;
                    font-family: Arial; font-size: 15px; font-weight: bold;">
            {title}
        </div>"""
        m.get_root().html.add_child(folium.Element(title_html))

    try:
        if map_type == "markers":
            # data = list of {lat, lon, popup, tooltip, color}
            # OR data = {"lat": [...], "lon": [...], "labels": [...]}
            if isinstance(data, dict) and "lat" in data:
                lats   = data["lat"]
                lons   = data["lon"]
                labels = data.get("labels", [""] * len(lats))
                colors = data.get("colors", ["blue"] * len(lats))
                for lat, lon, label, col in zip(lats, lons, labels, colors):
                    folium.Marker(
                        location=[lat, lon],
                        popup=folium.Popup(str(label), max_width=200),
                        tooltip=str(label),
                        icon=folium.Icon(color=col, icon="info-sign"),
                    ).add_to(m)
            elif isinstance(data, list):
                for item in data:
                    folium.Marker(
                        location=[item["lat"], item["lon"]],
                        popup=folium.Popup(item.get("popup", ""), max_width=200),
                        tooltip=item.get("tooltip", ""),
                        icon=folium.Icon(
                            color=item.get("color", "blue"),
                            icon=item.get("icon", "info-sign"),
                        ),
                    ).add_to(m)

        elif map_type == "heatmap":
            from folium.plugins import HeatMap
            # data = {"lat": [...], "lon": [...], "weights": [...optional]}
            # OR data = [[lat, lon, weight], ...]
            if isinstance(data, dict):
                lats    = data["lat"]
                lons    = data["lon"]
                weights = data.get("weights", [1.0] * len(lats))
                points  = list(zip(lats, lons, weights))
            else:
                points = data  # [[lat, lon, weight], ...]
            HeatMap(points, radius=15, blur=10).add_to(m)

        elif map_type == "choropleth":
            # data = {"geojson": "path_or_dict", "key": "field", "values": {key: value}}
            if isinstance(data, dict):
                geojson = data.get("geojson", {})
                if isinstance(geojson, str):
                    from tools.file_ops import _safe_resolve
                    p, err = _safe_resolve(geojson)
                    if not err and p.exists():
                        geojson = json.loads(p.read_text())

                folium.Choropleth(
                    geo_data=geojson,
                    data=data.get("values", {}),
                    columns=data.get("columns", ["key", "value"]),
                    key_on=data.get("key_on", "feature.properties.name"),
                    fill_color=data.get("fill_color", "YlOrRd"),
                    legend_name=data.get("legend", title),
                ).add_to(m)

        elif map_type == "route":
            # data = list of [lat, lon] waypoints
            if isinstance(data, list) and data:
                folium.PolyLine(
                    locations=data,
                    color=data[0].get("color", "blue") if isinstance(data[0], dict) else "blue",
                    weight=3,
                    opacity=0.8,
                ).add_to(m)
                # Start/end markers
                start = data[0] if not isinstance(data[0], dict) else [data[0]["lat"], data[0]["lon"]]
                end   = data[-1] if not isinstance(data[-1], dict) else [data[-1]["lat"], data[-1]["lon"]]
                folium.Marker(start, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
                folium.Marker(end,   tooltip="End",   icon=folium.Icon(color="red")).add_to(m)

        elif map_type == "circles":
            # data = list of {lat, lon, radius, color, popup}
            if isinstance(data, list):
                for item in data:
                    folium.CircleMarker(
                        location=[item["lat"], item["lon"]],
                        radius=item.get("radius", 8),
                        color=item.get("color", "#3186cc"),
                        fill=True,
                        popup=item.get("popup", ""),
                        tooltip=item.get("tooltip", ""),
                    ).add_to(m)

        else:
            return {"status": "error",
                    "error": f"Unknown map_type '{map_type}'. Use: markers | heatmap | choropleth | route | circles"}

    except Exception as e:
        return {"status": "error", "error": f"Map layer failed: {type(e).__name__}: {e}"}

    # Add layer control for multi-layer maps
    folium.LayerControl().add_to(m)

    out_name  = output or title.lower().replace(" ", "_") or "map"
    html_path = _out_path(out_name, "html")

    try:
        m.save(str(html_path))
    except Exception as e:
        return {"status": "error", "error": f"Failed to save map: {e}"}

    return {
        "status":    "success",
        "type":      "map",
        "map_type":  map_type,
        "title":     title,
        "html_path": str(html_path),
        "open_cmd":  f"start {html_path}" if cfg.is_windows else f"xdg-open {html_path}",
    }


# ── Report builder ────────────────────────────────────────────────────────────

_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', Arial, sans-serif; background: #f8f9fa;
         color: #2c3e50; line-height: 1.6; }
  .container { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }
  .header { background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
            color: white; padding: 36px 32px; border-radius: 12px;
            margin-bottom: 32px; }
  .header h1 { font-size: 2rem; font-weight: 700; margin-bottom: 6px; }
  .header .meta { opacity: 0.8; font-size: 0.9rem; }
  .section { background: white; border-radius: 10px; padding: 28px;
             margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
  .section h2 { font-size: 1.25rem; color: #2c3e50; margin-bottom: 16px;
                padding-bottom: 10px; border-bottom: 2px solid #3498db; }
  .section p  { color: #555; margin-bottom: 12px; }
  .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
              gap: 16px; margin-bottom: 24px; }
  .kpi { background: white; border-radius: 10px; padding: 20px 24px;
         box-shadow: 0 2px 8px rgba(0,0,0,0.06); text-align: center;
         border-top: 4px solid {{ accent }}; }
  .kpi .value { font-size: 2rem; font-weight: 700; color: {{ accent }}; }
  .kpi .label { font-size: 0.85rem; color: #888; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th { background: #f0f4f8; color: #2c3e50; padding: 10px 14px;
       text-align: left; font-weight: 600; }
  td { padding: 9px 14px; border-bottom: 1px solid #eee; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #f9fbff; }
  .chart-container { width: 100%; border-radius: 8px; overflow: hidden;
                     border: 1px solid #eee; }
  .footer { text-align: center; color: #aaa; font-size: 0.8rem; margin-top: 32px; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 12px;
           font-size: 0.75rem; font-weight: 600; }
  .badge-green  { background: #d4edda; color: #155724; }
  .badge-red    { background: #f8d7da; color: #721c24; }
  .badge-blue   { background: #d1ecf1; color: #0c5460; }
  .badge-yellow { background: #fff3cd; color: #856404; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{{ title }}</h1>
    <div class="meta">{{ subtitle }} &nbsp;|&nbsp; Generated {{ date }}</div>
  </div>

  {% if kpis %}
  <div class="kpi-grid">
    {% for kpi in kpis %}
    <div class="kpi">
      <div class="value">{{ kpi.value }}</div>
      <div class="label">{{ kpi.label }}</div>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  {% for section in sections %}
  <div class="section">
    {% if section.title %}<h2>{{ section.title }}</h2>{% endif %}
    {% if section.text %}<p>{{ section.text }}</p>{% endif %}

    {% if section.type == "table" and section.data %}
    <table>
      <thead><tr>
        {% for col in section.data[0].keys() %}<th>{{ col }}</th>{% endfor %}
      </tr></thead>
      <tbody>
        {% for row in section.data %}
        <tr>{% for val in row.values() %}<td>{{ val }}</td>{% endfor %}</tr>
        {% endfor %}
      </tbody>
    </table>
    {% endif %}

    {% if section.type == "chart" and section.chart_html %}
    <div class="chart-container">{{ section.chart_html | safe }}</div>
    {% endif %}
  </div>
  {% endfor %}

  <div class="footer">Generated by MCP Agent &nbsp;·&nbsp; {{ date }}</div>
</div>
</body>
</html>"""


def _build_report(
    sections:  list[dict],
    title:     str,
    subtitle:  str,
    kpis:      list[dict],
    accent:    str,
    output:    str,
    export_pdf: bool,
) -> dict:
    try:
        from jinja2 import Template
    except ImportError:
        return {"status": "error", "error": "jinja2 not installed. Run: pip install jinja2"}

    try:
        import plotly.graph_objects as go
    except ImportError:
        go = None

    import datetime

    # Process chart sections — embed Plotly div inline
    processed_sections = []
    for sec in sections:
        s = dict(sec)
        if s.get("type") == "chart" and go is not None and "chart_data" in s:
            try:
                # Build a small chart and extract the div HTML
                fig = go.Figure()
                cd  = s["chart_data"]
                ct  = cd.get("chart_type", "bar")
                if ct == "line":
                    fig.add_trace(go.Scatter(x=cd.get("x", []), y=cd.get("y", []),
                                             mode="lines+markers"))
                elif ct == "scatter":
                    fig.add_trace(go.Scatter(x=cd.get("x", []), y=cd.get("y", []),
                                             mode="markers"))
                elif ct == "pie":
                    fig.add_trace(go.Pie(labels=cd.get("labels", []),
                                         values=cd.get("values", [])))
                else:  # bar default
                    fig.add_trace(go.Bar(x=cd.get("x", []), y=cd.get("y", [])))

                fig.update_layout(
                    title=s.get("title", ""),
                    template="plotly_white",
                    height=380,
                    margin=dict(l=50, r=30, t=50, b=50),
                )
                s["chart_html"] = fig.to_html(
                    full_html=False, include_plotlyjs="cdn",
                    config={"displayModeBar": False},
                )
            except Exception as e:
                s["chart_html"] = f"<p>Chart error: {e}</p>"
        processed_sections.append(s)

    rendered = Template(_REPORT_TEMPLATE).render(
        title    = title or "Report",
        subtitle = subtitle or "",
        date     = datetime.datetime.now().strftime("%B %d, %Y at %H:%M"),
        kpis     = kpis or [],
        sections = processed_sections,
        accent   = accent or "#3498db",
    )

    out_name  = output or title.lower().replace(" ", "_") or "report"
    html_path = _out_path(out_name, "html")
    html_path.write_text(rendered, encoding="utf-8")

    result = {
        "status":    "success",
        "type":      "report",
        "title":     title,
        "sections":  len(sections),
        "html_path": str(html_path),
        "open_cmd":  f"start {html_path}" if cfg.is_windows else f"xdg-open {html_path}",
    }

    if export_pdf:
        try:
            import weasyprint
            pdf_path = html_path.with_suffix(".pdf")
            weasyprint.HTML(filename=str(html_path)).write_pdf(str(pdf_path))
            result["pdf_path"] = str(pdf_path)
        except ImportError:
            result["pdf_warning"] = "weasyprint not installed — HTML only"
        except Exception as e:
            result["pdf_warning"] = f"PDF export failed: {e}"

    return result


# ── Dashboard builder ─────────────────────────────────────────────────────────

def _build_dashboard(
    charts:   list[dict],
    title:    str,
    subtitle: str,
    kpis:     list[dict],
    columns:  int,
    accent:   str,
    output:   str,
) -> dict:
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except ImportError:
        return {"status": "error", "error": "plotly not installed"}

    import datetime

    accent  = accent or "#3498db"
    columns = max(1, min(columns or 2, 4))

    # Build chart HTML divs
    chart_divs = []
    for i, spec in enumerate(charts):
        try:
            fig = go.Figure()
            ct  = spec.get("chart_type", "bar").lower()
            d   = spec.get("data", {})
            x   = d.get("x", [])
            y   = d.get("y", [])

            if ct == "bar":
                fig.add_trace(go.Bar(x=x, y=y, marker_color=spec.get("color", accent)))
            elif ct == "line":
                fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers",
                                         line=dict(color=spec.get("color", accent))))
            elif ct == "pie":
                fig.add_trace(go.Pie(labels=d.get("labels", x),
                                     values=d.get("values", y), hole=0.35))
            elif ct == "scatter":
                fig.add_trace(go.Scatter(x=x, y=y, mode="markers",
                                         marker=dict(color=spec.get("color", accent), size=8)))
            elif ct == "area":
                fig.add_trace(go.Scatter(x=x, y=y, fill="tozeroy",
                                         line=dict(color=spec.get("color", accent))))
            else:
                fig.add_trace(go.Bar(x=x, y=y))

            fig.update_layout(
                title=dict(text=spec.get("title", f"Chart {i+1}"), font=dict(size=14)),
                template="plotly_white",
                height=320,
                margin=dict(l=40, r=20, t=44, b=40),
                showlegend=spec.get("legend", True),
                xaxis_title=spec.get("x_label", ""),
                yaxis_title=spec.get("y_label", ""),
            )

            div_html = fig.to_html(
                full_html=False,
                include_plotlyjs=False,  # loaded once below
                config={"displayModeBar": True, "responsive": True},
            )
            chart_divs.append(div_html)
        except Exception as e:
            chart_divs.append(f"<div class='chart-error'>Chart {i+1} error: {e}</div>")

    # Build KPI cards
    kpi_html = ""
    if kpis:
        cards = "".join(
            f"""<div class="kpi-card">
                  <div class="kpi-value">{k.get('value','')}</div>
                  <div class="kpi-label">{k.get('label','')}</div>
                  {"<div class='kpi-delta "+('pos' if str(k.get('delta','')).startswith('+') else 'neg')+"'>"+str(k.get('delta',''))+"</div>" if k.get('delta') else ''}
               </div>"""
            for k in kpis
        )
        kpi_html = f'<div class="kpi-row">{cards}</div>'

    # Grid cells
    grid_cells = "".join(
        f'<div class="chart-cell">{div}</div>' for div in chart_divs
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5;
          color: #2c3e50; }}
  .topbar {{ background: linear-gradient(135deg, #2c3e50, {accent});
             padding: 18px 32px; display: flex; align-items: center;
             justify-content: space-between; }}
  .topbar h1 {{ color: white; font-size: 1.4rem; font-weight: 700; }}
  .topbar .sub {{ color: rgba(255,255,255,.7); font-size: .85rem; }}
  .timestamp {{ color: rgba(255,255,255,.6); font-size: .8rem; }}
  .content {{ padding: 24px 28px; }}
  .kpi-row {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
  .kpi-card {{ background: white; border-radius: 10px; padding: 18px 22px;
               flex: 1; min-width: 140px;
               border-top: 4px solid {accent};
               box-shadow: 0 2px 8px rgba(0,0,0,0.07); }}
  .kpi-value {{ font-size: 1.9rem; font-weight: 700; color: {accent}; }}
  .kpi-label {{ font-size: .8rem; color: #888; margin-top: 4px; }}
  .kpi-delta {{ font-size: .85rem; margin-top: 6px; font-weight: 600; }}
  .kpi-delta.pos {{ color: #27ae60; }}
  .kpi-delta.neg {{ color: #e74c3c; }}
  .chart-grid {{ display: grid;
                 grid-template-columns: repeat({columns}, 1fr);
                 gap: 18px; }}
  .chart-cell {{ background: white; border-radius: 10px; padding: 16px;
                 box-shadow: 0 2px 8px rgba(0,0,0,0.07); overflow: hidden; }}
  .chart-error {{ color: #e74c3c; padding: 20px; }}
  @media (max-width: 768px) {{
    .chart-grid {{ grid-template-columns: 1fr; }}
    .kpi-row {{ flex-direction: column; }}
  }}
</style>
</head>
<body>
<div class="topbar">
  <div>
    <h1>{title}</h1>
    {f'<div class="sub">{subtitle}</div>' if subtitle else ''}
  </div>
  <div class="timestamp">Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</div>
<div class="content">
  {kpi_html}
  <div class="chart-grid">
    {grid_cells}
  </div>
</div>
</body>
</html>"""

    out_name  = output or title.lower().replace(" ", "_") or "dashboard"
    html_path = _out_path(out_name, "html")
    html_path.write_text(html, encoding="utf-8")

    return {
        "status":    "success",
        "type":      "dashboard",
        "title":     title,
        "charts":    len(charts),
        "kpis":      len(kpis or []),
        "html_path": str(html_path),
        "open_cmd":  f"start {html_path}" if cfg.is_windows else f"xdg-open {html_path}",
    }


# ── Meta-tool ─────────────────────────────────────────────────────────────────

@tool
def report(
    type:       str,
    # Chart params
    chart_type: str   = "bar",
    data:       Any   = None,
    data_path:  str   = "",
    x_col:      str   = "",
    y_col:      str   = "",
    label_col:  str   = "",
    title:      str   = "",
    subtitle:   str   = "",
    x_label:    str   = "",
    y_label:    str   = "",
    color:      str   = "",
    accent:     str   = "#3498db",
    export_png: bool  = False,
    export_pdf: bool  = False,
    output:     str   = "",
    # Map params
    map_type:   str   = "markers",
    center_lat: float = 0.0,
    center_lon: float = 0.0,
    zoom:       int   = 5,
    # Report params (jinja2 sections-based)
    sections:   list  = None,
    kpis:       list  = None,
    # Dashboard params
    charts:     list  = None,
    columns:    int   = 2,
    # market_report / code_report params
    overview:        str  = "",
    research:        str  = "",
    summary:         str  = "",
    issues:          list = None,
    recommendations: list = None,
    changes:         list = None,
    tables:          list = None,
    sources:         list = None,
) -> dict:
    """
    Report tool — create interactive charts, maps, reports, and dashboards.
    All outputs are self-contained HTML files — open in any browser, no server needed.

    type: "chart" | "map" | "report" | "dashboard"

    ── CHART ────────────────────────────────────────────────────────────────────
    chart_type: bar | line | scatter | area | pie | histogram | box |
                heatmap | treemap | funnel | bubble

    Data (choose one):
      data      = {"x": [...], "y": [...]}       ← inline dict
      data      = [1, 2, 3, 4, 5]                ← list of numbers
      data_path = "file.csv", x_col="month", y_col="revenue"  ← from file

    Special data shapes:
      pie:      data = {"names": [...], "values": [...], "hole": 0.3}
      heatmap:  data = {"z": [[...]], "x": [...], "y": [...]}
      treemap:  data = {"labels": [...], "parents": [...], "values": [...]}
      box:      data = {"groups": {"A": [...], "B": [...]}}
      bubble:   data = {"x": [...], "y": [...], "sizes": [...], "labels": [...]}

    Optional: title, x_label, y_label, color ("#hex"), export_png, output (filename)

    Examples:
      report(type="chart", chart_type="bar",
                data={"x":["Q1","Q2","Q3"], "y":[100,150,130]},
                title="Quarterly Revenue")

      report(type="chart", chart_type="line",
                data_path="sales.csv", x_col="date", y_col="revenue",
                title="Revenue Trend", export_png=True)

    ── MAP ──────────────────────────────────────────────────────────────────────
    map_type: markers | heatmap | choropleth | route | circles

    Data shapes:
      markers:    data = {"lat":[...], "lon":[...], "labels":[...], "colors":[...]}
                  data = [{"lat":..., "lon":..., "popup":"...", "color":"blue"}, ...]
      heatmap:    data = {"lat":[...], "lon":[...], "weights":[...]}
                  data = [[lat, lon, weight], ...]
      route:      data = [[lat, lon], [lat, lon], ...]
      circles:    data = [{"lat":..., "lon":..., "radius":10, "color":"red"}, ...]
      choropleth: data = {"geojson": "path.json", "values": {"Brazil":100}, "key_on":"..."}

    Optional: center_lat, center_lon, zoom, title, output

    Examples:
      report(type="map", map_type="markers",
                data={"lat":[-23.5,-22.9], "lon":[-46.6,-43.2],
                      "labels":["São Paulo","Rio de Janeiro"]},
                title="Brazilian Cities", zoom=5)

    ── REPORT ───────────────────────────────────────────────────────────────────
    kpis: [{"label":"Revenue", "value":"R$1.2M"}, ...]
    sections: list of section dicts, each with:
      {"title":"...", "text":"...", "type":"text"}
      {"title":"...", "type":"table", "data":[{"col1":"val","col2":"val"}, ...]}
      {"title":"...", "type":"chart", "chart_data":{"chart_type":"bar","x":[...],"y":[...]}}

    Optional: subtitle, accent ("#hex"), export_pdf, output

    Example:
      report(type="report", title="Q3 Analysis",
                subtitle="Brazilian Market",
                kpis=[{"label":"Revenue","value":"R$1.2M"},
                      {"label":"Growth","value":"+18%"}],
                sections=[
                  {"title":"Summary","text":"Strong quarter driven by...","type":"text"},
                  {"title":"Sales","type":"table",
                   "data":[{"Month":"Jul","Sales":400},{"Month":"Aug","Sales":520}]},
                  {"title":"Trend","type":"chart",
                   "chart_data":{"chart_type":"line","x":["Jul","Aug"],"y":[400,520]}}
                ])

    ── DASHBOARD ────────────────────────────────────────────────────────────────
    charts: list of chart specs, each:
      {"chart_type":"bar","title":"...","data":{"x":[...],"y":[...]},"color":"#hex"}
    kpis:   [{"label":"...","value":"...","delta":"+5%"}, ...]
    columns: 1-4 (grid columns, default 2)

    Example:
      report(type="dashboard", title="Sales Dashboard",
                columns=2,
                kpis=[{"label":"Revenue","value":"R$1.2M","delta":"+18%"}],
                charts=[
                  {"chart_type":"bar","title":"By Month",
                   "data":{"x":["Jan","Feb"],"y":[100,150]}},
                  {"chart_type":"pie","title":"By Region",
                   "data":{"labels":["SP","RJ","MG"],"values":[50,30,20]}}
                ])
    """
    vtype = type.strip().lower()

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
    if vtype == "chart":
        loaded, err = _load_data(data, data_path, x_col, y_col, label_col)
        if err:
            return {"status": "error", "error": err}
        return _build_chart(chart_type, loaded, title, x_label, y_label,
                            color, output, export_png)

    # ── map ───────────────────────────────────────────────────────────────────
    if vtype == "map":
        loaded, err = _load_data(data, data_path)
        if err and data is None:
            return {"status": "error", "error": err}
        return _build_map(map_type, loaded or data, title,
                          center_lat, center_lon, zoom, output)

    # ── report ────────────────────────────────────────────────────────────────
    if vtype == "report":
        if not sections:
            return {"status": "error", "error": "sections list is required for report"}
        return _build_report(sections, title, subtitle, kpis or [],
                             accent, output, export_pdf)

    # ── dashboard ─────────────────────────────────────────────────────────────
    if vtype == "dashboard":
        if not charts:
            return {"status": "error", "error": "charts list is required for dashboard"}
        return _build_dashboard(charts, title, subtitle, kpis or [],
                                columns, accent, output)

    return {
        "status": "error",
        "error":  f"Unknown type '{vtype}'. Use: chart | map | report | dashboard",
    }
