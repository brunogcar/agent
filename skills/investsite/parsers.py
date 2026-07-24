"""skills/investsite/parsers.py -- HTML table parsing for investsite pages.

Three parser types:
  1. parse_indicators(html) — main page: 10 tables (basic data, prices, DRE, etc.)
  2. parse_statement(html) — financial statement pages: 1 table with account codes
  3. parse_events(html) — periodic info: events table with CVM PDF links

All parsers return structured dicts (not raw HTML).

[v1.0.1] Keys are normalized to ASCII (diacritics stripped) so they work
from any terminal (Windows PowerShell, Linux, etc.). Example:
  "Preço/Lucro" → "Preco/Lucro"
  "Patrimônio Líquido" → "Patrimonio Liquido"
  "Dívida Líquida/EBITDA" → "Divida Liquida/EBITDA"
"""

from __future__ import annotations

import re
import unicodedata
from html import unescape
from typing import Any


# ── Key normalization ────────────────────────────────────────────────────────

def _normalize_key(key: str) -> str:
    """Normalize a string key to ASCII (strip diacritics).

    "Preço/Lucro" → "Preco/Lucro"
    "Patrimônio" → "Patrimonio"
    "Dívida" → "Divida"

    This makes keys predictable and usable from any terminal (Windows
    PowerShell struggles with UTF-8 diacritics in inline Python commands).
    """
    # Normalize to decomposed form, then strip combining characters
    normalized = unicodedata.normalize("NFKD", key)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_str


def _try_parse_brl(value: str) -> str | float:
    """Try to parse a value as BRL. Return float on success, original string on failure.

    Uses core.br_validator.parse_brl which handles:
      "R$ 596,36 B" → 596360000000.0
      "27,18%" → 0.2718
      "5,15" → 5.15
      "PETROBRAS" → "PETROBRAS" (not a number, returns as-is)

    Non-numeric strings (company names, dates, descriptions) are returned as-is.
    """
    if not isinstance(value, str) or not value.strip():
        return value
    try:
        from core.br_validator import parse_brl
        return parse_brl(value)
    except (ValueError, ImportError):
        return value


# ── HTML helpers ─────────────────────────────────────────────────────────────

def _strip_tags(html: str) -> str:
    """Strip HTML tags + unescape entities + collapse whitespace."""
    text = re.sub(r"<[^>]+>", "", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_tables(html: str) -> list[dict]:
    """Extract all <table> elements from HTML.

    Returns list of {caption, headers, rows} dicts.

    Note: For tables with <th> header cells, the first row is treated as headers.
    For tables with only <td> cells (no <th>), all rows are data rows.
    """
    tables = []
    for table_match in re.finditer(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE):
        table_html = table_match.group(1)

        # Extract caption
        caption = ""
        cap_match = re.search(r"<caption[^>]*>(.*?)</caption>", table_html, re.DOTALL | re.IGNORECASE)
        if cap_match:
            caption = _strip_tags(cap_match.group(1))

        # Extract rows — track whether row uses <th> (header) or <td> (data)
        rows = []
        has_header = False
        for row_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE):
            row_html = row_match.group(1)
            # Check if this row has <th> cells
            th_cells = re.findall(r"<th[^>]*>(.*?)</th>", row_html, re.DOTALL | re.IGNORECASE)
            td_cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL | re.IGNORECASE)

            if th_cells and not td_cells:
                # Pure header row
                cells = [_strip_tags(c) for c in th_cells]
                has_header = True
            elif th_cells and td_cells:
                # Mixed row — treat th as headers, td as data
                cells = [_strip_tags(c) for c in th_cells + td_cells]
            else:
                # Pure data row
                cells = [_strip_tags(c) for c in td_cells]

            if any(c for c in cells):
                rows.append(cells)

        # If the table has <th> headers, first row is headers. Otherwise, all rows are data.
        if has_header and rows:
            headers = rows[0]
            data_rows = rows[1:]
        else:
            headers = []
            data_rows = rows

        tables.append({"caption": caption, "headers": headers, "rows": data_rows})

    return tables


def _extract_links_from_html(html: str) -> list[str]:
    """Extract all href links from an HTML string."""
    return re.findall(r'href=["\x27](https?://[^"\x27]+)["\x27]', html)


def _extract_links_per_row(table_html: str) -> list[list[str]]:
    """Extract links per row from a table HTML block.

    Returns list where each element is the list of links in that row.
    """
    row_links = []
    for row_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE):
        links = _extract_links_from_html(row_match.group(1))
        if links:
            row_links.append(links)
    return row_links


# ── Parser: indicators (main page) ───────────────────────────────────────────

_INDICATOR_SECTIONS = {
    "Dados Básicos": "dados_basicos",
    "Preços Relativos": "precos_relativos",
    "Resumo DRE Últimos Doze Meses": "dre_ttm",
    "Resumo DRE Último Trimestre": "dre_quarterly",
    "Comportamento de Preço e Volume": "preco_volume",
    "Retornos, Margens e Outras Medidas": "retornos_margens",
    "Resumo Balanço Patrimonial": "balanco_patrimonial",
    "Resumo Fluxo de Caixa Últimos Doze Meses": "fluxo_caixa_ttm",
    "Resumo Fluxo de Caixa Último Trimestre": "fluxo_caixa_quarterly",
    "Cálculo Experimental de CAPEX e Fluxo de Caixa Livre": "experimental",
}


def parse_indicators(html: str) -> dict:
    """Parse the main indicators page (principais_indicadores.php).

    Returns dict with section keys + key-value pairs from each table.
    """
    tables = _extract_tables(html)
    result: dict[str, Any] = {"status": "ok", "sections": {}}

    for table in tables:
        caption = table["caption"]
        section_key = None
        for cap_prefix, key in _INDICATOR_SECTIONS.items():
            if caption.startswith(cap_prefix) or cap_prefix in caption:
                section_key = key
                break

        if not section_key:
            continue

        section_data: dict[str, Any] = {"caption": caption}
        for row in table["rows"]:
            if len(row) >= 2:
                label = row[0]
                values = row[1:]
                # [v1.0.1] Normalize keys to ASCII for terminal compatibility
                normalized_label = _normalize_key(label)
                # [v1.0.2] Parse BRL values to float using core.br_validator
                parsed_values = [_try_parse_brl(v) for v in values]
                section_data[normalized_label] = parsed_values[0] if len(parsed_values) == 1 else parsed_values

        result["sections"][section_key] = section_data

    return result


# ── Parser: statement (BPA/BPP/DRE/DFC/DVA) ─────────────────────────────────

def parse_statement(html: str, statement_type: str) -> dict:
    """Parse a financial statement page.

    Returns dict with account codes, descriptions, period values + % total.
    """
    tables = _extract_tables(html)
    if not tables:
        return {"status": "error", "error": "No tables found on statement page"}

    table = tables[0]
    headers = table["headers"]
    rows = table["rows"]

    # Parse header row to extract period dates
    period_headers = []
    for h in headers[2:]:  # skip "Conta" + "Descrição"
        if h and "% total" not in h.lower():
            period_headers.append(h)

    # Parse account rows
    accounts = []
    for row in rows:
        if len(row) < 3:
            continue
        codigo = row[0].strip()
        descricao = row[1].strip()
        if not codigo or not descricao:
            continue

        # Remaining cells: alternating value, % total, value, % total, ...
        periods = []
        i = 2
        while i < len(row):
            value = row[i] if i < len(row) else ""
            pct = row[i + 1] if i + 1 < len(row) else ""
            periods.append({"value": value, "pct_total": pct})
            i += 2

        accounts.append({
            "codigo": codigo,
            "descricao": descricao,
            "periods": periods,
        })

    return {
        "status": "ok",
        "statement_type": statement_type,
        "period_headers": period_headers,
        "accounts": accounts,
        "account_count": len(accounts),
    }


# ── Parser: events (periodic info) ───────────────────────────────────────────

def parse_events(html: str, categoria: str = "") -> dict:
    """Parse the periodic info detail page.

    Returns events with direct CVM rad.cvm.gov.br PDF links.
    """
    # Find the events table (first table with >5 rows)
    tables = _extract_tables(html)
    if not tables:
        return {"status": "error", "error": "No tables found on events page"}

    # Find the events table (usually the largest one)
    events_table = max(tables, key=lambda t: len(t["rows"]))
    headers = events_table["headers"]
    rows = events_table["rows"]

    # Extract links per row from the full HTML
    # Find the table block with the most rows (the events table)
    table_blocks = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)
    row_links = []
    best_block = None
    best_count = 0
    for block in table_blocks:
        tr_count = len(re.findall(r"<tr", block, re.IGNORECASE))
        if tr_count > best_count:
            best_count = tr_count
            best_block = block
    if best_block:
        row_links = _extract_links_per_row(best_block)

    events = []
    for i, row in enumerate(rows):
        if len(row) < 5:
            continue
        while len(row) < 6:
            row.append("")

        event = {
            "data_entrega": row[0].strip(),
            "data_referencia": row[1].strip(),
            "categoria": row[2].strip(),
            "tipo": row[3].strip(),
            "especie": row[4].strip(),
            "assuntos": row[5].strip(),
            "link_cvm": row_links[i][0] if i < len(row_links) and row_links[i] else "",
        }
        events.append(event)

    return {
        "status": "ok",
        "categoria": categoria,
        "headers": headers,
        "events": events,
        "count": len(events),
    }


# ── Available event categories ───────────────────────────────────────────────

EVENT_CATEGORIES = [
    "Assembleia",
    "Aviso aos Acionistas",
    "Comunicado ao Mercado",
    "Dados Econômico-Financeiros",
    "Fato Relevante",
    "Relatório Proventos",
    "Reunião da Administração",
]
