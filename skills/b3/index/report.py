"""skills/b3/index/report.py -- Section builders for index dashboard."""
from __future__ import annotations

from skills.b3.index.helpers import build_constituent_table, build_chart_section


def build_kpi_card(label: str, value, unit: str = "", subtitle: str = "") -> dict:
    return {
        "type": "kpi",
        "label": label,
        "value": str(value) if value is not None else "-",
        "unit": unit,
        "subtitle": subtitle,
    }


def build_index_tab(index_code: str, index_data: dict) -> dict:
    """Build a tab for a single index with chart + table."""
    if index_data.get("status") != "ok":
        return {
            "name": index_code,
            "group": "Indices",
            "sections": [{"type": "text", "title": index_code,
                          "body": f"Erro: {index_data.get('error', 'sem dados')}"}],
        }

    constituents = index_data.get("constituents", [])
    name = index_data.get("name", index_code)
    ref_date = index_data.get("ref_date", "")

    sections = [
        build_chart_section(
            f"{name} - Top 15 Constituintes",
            constituents,
            f"Composicao em {ref_date} - {len(constituents)} constituintes",
        ),
        build_constituent_table(constituents, limit=20),
    ]

    return {
        "name": index_code,
        "group": "Indices",
        "sections": sections,
    }
