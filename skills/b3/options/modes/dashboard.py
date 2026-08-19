"""Mode: dashboard -- 5-tab B3 options analytics dashboard.

Tabs:
  Cadeia de Opções        (group: Opções)   — options chain tables + ticker legend
  Put/Call Ratio          (group: Análise)  — daily P/C ratio chart + table
  Volume por Strike       (group: Análise)  — bar chart of volume per strike
  Exercicios              (group: Opções)   — exercise of calls/puts chart + table
  Volatilidade Implícita  (group: Análise)  — IV smile chart + IV table + IV term heatmap

Workflow:
  1. Normalize the underlying code (PETR4 → PETR by stripping trailing digit)
  2. Query options_chain(underlying)  for the nearest maturity
  3. Query put_call_ratio(underlying, days=90)  for the sentiment trend
  4. Query volume_by_strike(underlying)  for the nearest maturity
  5. Query exercise_summary(underlying, days=90)  for the exercise trend
  6. [v1.2] Compute implied vol per option (Black-Scholes + Selic risk-free rate)
     + build IV smile chart + IV table + IV term structure heatmap.

Graceful degradation: if the cotahist_derivatives table doesn't exist or has
no data, the dashboard returns status=ok with error sections (so the other
tabs still render). Mirrors the CVM financials + bcb/macro contract.

[v1.2] Added 5th tab "Volatilidade Implícita" — Black-Scholes IV engine
(`skills/b3/options/engines.py`) + Selic rate from BCB SGS (series 432 =
"Meta Selic Copom", converted to continuous compounding). The IV tab is
graceful — if the spot price or Selic rate can't be fetched, it shows an
error section but doesn't break the dashboard.

[v2] Legend reworked into a 2-column table (CALLS | PUTS) so users see both
month-code systems side by side. Numeric/R$ columns in all tables now carry
a `column_align` hint that the macros.html data_table macro applies for
proper right-alignment + tabular-nums.

Registered as "dashboard" in skills.b3.options._registry.MODES.
"""
from __future__ import annotations

from datetime import datetime as _dt

from skills.b3.options._registry import register_mode
from skills.b3.options.report import (
    build_chart_section, build_table_section, build_text_section,
    build_error_section, build_heatmap_section,
)
from skills.b3.options.helpers import format_value, format_brl, format_int, format_pct

# [v1.2] Black-Scholes implied-vol engine + risk-free rate source.
from skills.b3.options.engines import implied_vol as _implied_vol
from data_sources.bcb.sgs.query_engine import last_value as _sgs_last_value
from data_sources.b3.cotahist.query_engine import query as _spot_query
from data_sources.b3.cotahist.derivatives_query import (
    options_chain, put_call_ratio, volume_by_strike, exercise_summary,
    available_maturities,
)


# Accent colors
_COLOR_CALL = "#22c55e"   # green — calls
_COLOR_PUT  = "#ef4444"   # red   — puts
_COLOR_REF  = "#9ca3af"   # gray  — reference line at 1.0


# BCB SGS series 432 = "Meta Selic Copom" (annualized % rate, simple compounding).
_SELIC_SERIES_CODE = 432


# [v2] Legend intro text — short explanation + examples. The 2-column
# CALLS|PUTS table lives in a separate table section below.
_LEGEND_INTRO = """\
Formato do ticker: UNDERLYING + MÊS + STRIKE

Códigos de mês para CALLS (compra) e PUTS (venda) — veja a tabela abaixo \
para o mapeamento completo lado-a-lado. Os códigos A-L são para CALLS e \
M-X são para PUTS (cada letra corresponde a um mês do ano).

Exemplos:
  PETRH36   →  PETR Call de Agosto, strike R$ 36,00
  PETRT36   →  PETR Put  de Agosto, strike R$ 36,00
  PETRA215  →  PETR Call de Janeiro, strike R$ 21,50  (dígito final 5 = meio-ponto)

O strike é codificado como inteiro no ticker. Quando o último dígito é 5,
o valor é dividido por 10 com meio-ponto (ex.: 215 → 21,50; 3650 → 365,00).
"""


def _normalize_underlying(underlying: str) -> str:
    """Normalize the underlying code: strip trailing digits (PETR4 → PETR).

    The cotahist_derivatives table is keyed on the 4-letter underlying code
    (e.g. "PETR"), NOT on the full equity ticker (e.g. "PETR4"). Accepts both
    forms for caller convenience.
    """
    u = (underlying or "").strip().upper()
    while u and u[-1].isdigit():
        u = u[:-1]
    return u


def _safe_query(fn, **kwargs) -> dict:
    """Call a query_engine function defensively.

    The query_engine already catches FileNotFoundError + returns
    {"status": "not_synced", ...} when the DB is missing. But the
    underlying connect() can also raise other exceptions (e.g. RuntimeError
    when core.config fails to load in a sandbox without PLANNER_MODEL, or
    sqlite3.OperationalError when the cotahist_derivatives table doesn't
    exist yet). This wrapper normalizes ALL such failures into the same
    {"status": "error", "error": <msg>} shape so the dashboard stays
    status=ok with error sections (graceful-degradation contract).
    """
    try:
        return fn(**kwargs)
    except Exception as e:  # noqa: BLE001 — we want to catch EVERYTHING here.
        return {
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
        }


# ── [v1.2] IV helpers ───────────────────────────────────────────────────────

def _fetch_spot_price(underlying: str) -> tuple[float | None, str | None]:
    """Fetch the latest spot close for the underlying from the cotahist equities table.

    Returns (spot_price, ref_date_str) — both None if the lookup fails.
    The `underlying` is the 4-letter code (e.g. "PETR"); we try PETR4 + PETR3
    suffixes since the equities table is keyed on the full ticker.
    """
    for suffix in ("4", "3"):
        ticker = f"{underlying}{suffix}"
        res = _safe_query(_spot_query, ticker=ticker, limit=1, market_type=10)
        if res.get("status") == "ok" and res.get("rows"):
            row = res["rows"][0]
            close = row.get("close")
            if close and close > 0:
                return float(close), row.get("refdate")
    return None, None


def _fetch_selic_rate() -> float | None:
    """Fetch the latest Selic rate from BCB SGS series 432 (Meta Selic Copom).

    The series value is a percentage (e.g. 14.25 for 14.25% a.a.). We convert
    the simple annual rate to continuous compounding: r_cont = ln(1 + r/100).

    Returns None if the SGS DB is missing or the series has no observations.
    """
    res = _safe_query(_sgs_last_value, code=_SELIC_SERIES_CODE)
    if res.get("status") != "ok":
        return None
    val = res.get("value")
    if val is None:
        return None
    try:
        r_simple = float(val) / 100.0  # 14.25 -> 0.1425
    except (ValueError, TypeError):
        return None
    # Continuous-compounding conversion: r_cont = ln(1 + r_simple).
    import math as _math
    return _math.log(1.0 + r_simple)


def _compute_iv_for_option(option: dict, spot: float, r_cont: float,
                           refdate: str) -> float | None:
    """Compute implied vol for a single option row.

    Args:
        option: Dict with at least strike_parsed, close, maturity, option_type.
        spot:   Spot price of the underlying.
        r_cont: Risk-free rate (continuous compounding).
        refdate: Reference date (YYYY-MM-DD) for the T calculation.

    Returns:
        Implied vol (sigma) as a fraction (e.g. 0.35 for 35%), or None if
        the inputs are invalid (no strike, no maturity, T<=0, etc.).
    """
    K = option.get("strike_parsed")
    price = option.get("close")
    maturity = option.get("maturity")
    otype = (option.get("option_type") or "").upper()

    if K is None or price is None or not maturity or otype not in ("CALL", "PUT"):
        return None
    try:
        K = float(K)
        price = float(price)
    except (ValueError, TypeError):
        return None

    # T = (maturity - refdate).days / 365.
    try:
        d_mat = _dt.fromisoformat(maturity)
        d_ref = _dt.fromisoformat(refdate) if refdate else _dt.now()
    except ValueError:
        return None
    days = (d_mat - d_ref).days
    if days <= 0:
        return None  # Already expired or expiry day (intrinsic-only territory).
    T = days / 365.0

    return _implied_vol(price, spot, K, T, r_cont, otype)


def _iv_color(iv: float | None) -> str:
    """Background color for an IV heatmap cell.

    Maps IV from 0.10 (10%, calm) -> 1.00 (100%, panic) to a green-yellow-red
    gradient. Returns "" (empty string) for None (empty cell, no IV).
    """
    if iv is None:
        return ""
    # Clamp to [0.10, 1.00] for the gradient.
    lo, hi = 0.10, 1.00
    v = max(lo, min(hi, iv))
    # Normalized 0..1 within the [lo, hi] window.
    t = (v - lo) / (hi - lo)
    # Interpolate green (0,200,83) -> yellow (250,204,21) -> red (239,68,68).
    if t < 0.5:
        # green -> yellow
        u = t * 2.0
        r = int(0   + (250 - 0)   * u)
        g = int(200 + (204 - 200) * u)
        b = int(83  + (21  - 83)  * u)
    else:
        # yellow -> red
        u = (t - 0.5) * 2.0
        r = int(250 + (239 - 250) * u)
        g = int(204 + (68  - 204) * u)
        b = int(21  + (68  - 21)  * u)
    return f"rgb({r}, {g}, {b})"


def _iv_text_color(iv: float | None) -> str:
    """Text color (black/white) for an IV heatmap cell — high contrast against the bg."""
    if iv is None:
        return ""
    # Yellow midpoint (~0.55) is bright — use dark text. Extremes are dark — use white.
    if 0.40 < iv < 0.70:
        return "#1f2937"  # dark slate
    return "#ffffff"


# ── Tab 1: Cadeia de Opções ─────────────────────────────────────────────────
def _build_chain_tab(underlying: str, maturity: str = "") -> list[dict]:
    """Build the Cadeia de Opções tab sections.

    [v3] Split into 2 collapsible tables: one for calls, one for puts.
    Both expanded by default. Legend text section stays non-collapsible.

    [v2] Legend reworked: intro text section (format + examples) + a 2-column
    table (CALLS | PUTS) showing the month codes side by side. Numeric
    columns (Exercício/Último/Volume/Bid/Ask) now carry a `column_align` hint
    for right-alignment + tabular-nums.

    Sections emitted (in order):
      1. Legend intro text section (format + examples)
      2. Legend 2-column table (CALLS | PUTS month codes)
      3. Calls table (collapsible, expanded) — Papel | Exercício | Vencimento |
         Último | Volume | Bid | Ask
      4. Puts table (collapsible, expanded) — same columns
    """
    sections: list[dict] = []

    # [v2] Legend intro text (format + examples).
    sections.append(build_text_section(
        "Convenção de Ticker de Opções",
        _LEGEND_INTRO,
    ))

    # [v2] Legend 2-column table (CALLS | PUTS) — 3 rows: Jan-Abr, Mai-Ago, Set-Dez.
    legend_rows = [
        ["A=Jan  B=Fev  C=Mar  D=Abr", "M=Jan  N=Fev  O=Mar  P=Abr"],
        ["E=Mai  F=Jun  G=Jul  H=Ago", "Q=Mai  R=Jun  S=Jul  T=Ago"],
        ["I=Set  J=Out  K=Nov  L=Dez", "U=Set  V=Out  W=Nov  X=Dez"],
    ]
    sections.append(build_table_section(
        "Códigos de Mês — CALLS vs PUTS",
        legend_rows,
        ["CALLS (compra)", "PUTS (venda)"],
        description="Os códigos A-L correspondem a CALLS (opção de compra) e "
                    "M-X a PUTS (opção de venda). Cada letra mapeia um mês "
                    "do ano — idêntico para ambos os lados.",
        column_align=["left", "left"],
    ))

    # Query the options chain (nearest maturity if not specified).
    res = _safe_query(options_chain, underlying=underlying, maturity=maturity)
    status = res.get("status")
    if status != "ok":
        sections.append(build_error_section(
            "Cadeia de Opções",
            res.get("error", f"status={status}"),
        ))
        return sections

    options = res.get("options", [])
    if not options:
        sections.append(build_error_section(
            "Cadeia de Opções",
            f"nenhuma opção encontrada para {underlying}",
        ))
        return sections

    # Split into calls + puts.
    calls = [o for o in options if o.get("option_type") == "CALL"]
    puts = [o for o in options if o.get("option_type") == "PUT"]
    maturity_str = res.get("maturity", "-")
    refdate = res.get("refdate", "-")

    columns = [
        "Papel", "Exercício", "Vencimento",
        "Último", "Volume", "Bid", "Ask",
    ]
    # [v2] Papel=left, Exercício=right (R$), Vencimento=left (date),
    # Último=right (R$), Volume=right (number), Bid=right (R$), Ask=right (R$).
    chain_align = ["left", "right", "left", "right", "right", "right", "right"]

    def _build_rows(opts: list[dict]) -> list[list]:
        rows = []
        for opt in opts:
            rows.append([
                opt.get("symbol", ""),
                format_brl(opt.get("strike_parsed")),
                opt.get("maturity", ""),
                format_brl(opt.get("close")),
                format_int(opt.get("volume")),
                format_brl(opt.get("best_bid")),
                format_brl(opt.get("best_ask")),
            ])
        return rows

    # Calls table (collapsible, expanded).
    if calls:
        sections.append({
            "type": "table",
            "title": f"Calls — {underlying} ({maturity_str})",
            "description": (
                f"{len(calls)} calls para o vencimento {maturity_str} (ref: {refdate}). "
                "Ordenadas por strike."
            ),
            "columns": columns,
            "rows": _build_rows(calls),
            "collapsible": True,
            "collapsible_open": True,
            "column_align": chain_align,
        })

    # Puts table (collapsible, expanded).
    if puts:
        sections.append({
            "type": "table",
            "title": f"Puts — {underlying} ({maturity_str})",
            "description": (
                f"{len(puts)} puts para o vencimento {maturity_str} (ref: {refdate}). "
                "Ordenadas por strike."
            ),
            "columns": columns,
            "rows": _build_rows(puts),
            "collapsible": True,
            "collapsible_open": True,
            "column_align": chain_align,
        })

    return sections


# ── Tab 2: Put/Call Ratio ───────────────────────────────────────────────────
def _build_put_call_ratio_tab(underlying: str, days: int = 90) -> list[dict]:
    """Build the Put/Call Ratio tab sections.

    [v2] Dual-axis chart with call vol (green bars) + put vol (red bars)
    on the left axis + P/C ratio (blue line) on the right axis.

    Sections emitted:
      1. Dual-axis chart: call vol (green bars, left) + put vol (red bars,
         left) + P/C ratio (blue line, right) + reference line at 1.0 (dashed).
      2. Table of the latest 15 observations (most recent first).

    P/C ratio = total put volume / total call volume per day.
    > 1.0 = bearish sentiment (more puts than calls).
    < 1.0 = bullish sentiment (more calls than puts).
    """
    sections: list[dict] = []

    res = _safe_query(put_call_ratio, underlying=underlying, days=days)
    status = res.get("status")
    if status != "ok":
        sections.append(build_error_section(
            "Put/Call Ratio",
            res.get("error", f"status={status}"),
        ))
        return sections

    observations = res.get("observations", [])
    if not observations:
        sections.append(build_error_section(
            "Put/Call Ratio",
            f"nenhuma observação para {underlying}",
        ))
        return sections

    labels = [o["ref_date"] for o in observations]
    call_vols = [o.get("call_volume", 0) or 0 for o in observations]
    put_vols = [o.get("put_volume", 0) or 0 for o in observations]
    ratios = [o.get("ratio") for o in observations]

    # Dual-axis chart: bars (volume, left) + line (ratio, right).
    chart_data = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "type": "bar",
                    "label": "Volume Calls",
                    "data": call_vols,
                    "backgroundColor": _COLOR_CALL,
                    "borderColor": _COLOR_CALL,
                    "borderWidth": 0,
                    "yAxisID": "y",
                    "order": 3,
                },
                {
                    "type": "bar",
                    "label": "Volume Puts",
                    "data": put_vols,
                    "backgroundColor": _COLOR_PUT,
                    "borderColor": _COLOR_PUT,
                    "borderWidth": 0,
                    "yAxisID": "y",
                    "order": 2,
                },
                {
                    "type": "line",
                    "label": "P/C Ratio",
                    "data": ratios,
                    "borderColor": "#3b82f6",
                    "backgroundColor": "#3b82f6",
                    "borderWidth": 1.5,
                    "pointRadius": 0,
                    "pointHoverRadius": 3,
                    "tension": 0.2,
                    "fill": False,
                    "yAxisID": "y1",
                    "order": 1,
                },
                {
                    "type": "line",
                    "label": "Referência (1,0)",
                    "data": [1.0] * len(labels),
                    "borderColor": _COLOR_REF,
                    "backgroundColor": _COLOR_REF,
                    "borderDash": [6, 4],
                    "borderWidth": 1.2,
                    "pointRadius": 0,
                    "fill": False,
                    "tension": 0,
                    "yAxisID": "y1",
                    "order": 0,
                },
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "scales": {
                "x": {"ticks": {"maxTicksLimit": 12}},
                "y": {
                    "position": "left",
                    "title": {"display": True, "text": "Volume (R$)"},
                    "beginAtZero": True,
                },
                "y1": {
                    "position": "right",
                    "title": {"display": True, "text": "P/C Ratio"},
                    "grid": {"drawOnChartArea": False},
                },
            },
            "plugins": {
                "title": {"display": True, "text": f"Put/Call Ratio — {underlying}"},
                "legend": {"display": True, "position": "top"},
            },
        },
    }

    sections.append({
        "type": "chart",
        "title": f"Put/Call Ratio — {underlying}",
        "description": (
            f"Volume de calls (verde) + puts (vermelho) no eixo esquerdo + "
            f"razão P/C (azul) no eixo direito. {days} pregões. "
            "Ratio > 1,0 = bearish (mais puts); < 1,0 = bullish (mais calls). "
            "Linha tracejada cinza = referência 1,0."
        ),
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": call_vols, "label": "Volume Calls"},
            {"data": put_vols, "label": "Volume Puts"},
            {"data": ratios, "label": "P/C Ratio"},
            {"data": [1.0] * len(labels), "label": "Referência (1,0)"},
        ],
    })

    # Table with the latest 15 observations (most recent first).
    table_rows: list[list] = []
    for obs in reversed(observations[-15:]):
        table_rows.append([
            obs.get("ref_date", ""),
            format_int(obs.get("call_volume")),
            format_int(obs.get("put_volume")),
            format_value(obs.get("ratio"), "ratio"),
        ])
    # [v2] Right-align numeric columns (Data=left, the rest=right).
    sections.append(build_table_section(
        f"Últimas Observações — {underlying}",
        table_rows,
        ["Data", "Volume Calls", "Volume Puts", "P/C Ratio"],
        description="Últimas 15 observações diárias (mais recente primeiro).",
        column_align=["left", "right", "right", "right"],
    ))
    return sections


# ── Tab 3: Volume por Strike ────────────────────────────────────────────────
def _build_volume_by_strike_tab(underlying: str) -> list[dict]:
    """Build the Volume por Strike tab sections.

    Sections emitted:
      1. Bar chart of volume per strike for the nearest maturity — 2 datasets:
         calls (green #22c55e) + puts (red #ef4444). Range selector enabled.
      2. Detail table (strike / vol calls / vol puts / # calls / # puts).

    Built inline (rather than via build_chart_section) because the chart is
    a 2-dataset bar chart, which doesn't fit the observations-based
    build_chart_section signature.
    """
    sections: list[dict] = []

    res = _safe_query(volume_by_strike, underlying=underlying)
    status = res.get("status")
    if status != "ok":
        sections.append(build_error_section(
            "Volume por Strike",
            res.get("error", f"status={status}"),
        ))
        return sections

    strikes = res.get("strikes", [])
    if not strikes:
        sections.append(build_error_section(
            "Volume por Strike",
            f"nenhum strike encontrado para {underlying}",
        ))
        return sections

    # Build chart data: 2 bar datasets (calls + puts) per strike.
    labels = [format_brl(s.get("strike")) for s in strikes]
    call_data = [s.get("call_volume", 0) for s in strikes]
    put_data  = [s.get("put_volume", 0)  for s in strikes]

    call_dataset = {
        "label": "Calls",
        "data": call_data,
        "backgroundColor": _COLOR_CALL,
        "borderColor": _COLOR_CALL,
        "borderWidth": 0,
    }
    put_dataset = {
        "label": "Puts",
        "data": put_data,
        "backgroundColor": _COLOR_PUT,
        "borderColor": _COLOR_PUT,
        "borderWidth": 0,
    }

    chart_data = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [call_dataset, put_dataset],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"Volume por Strike — {underlying}",
                },
                "legend": {"display": True, "position": "top"},
            },
            "scales": {
                "x": {"ticks": {"maxTicksLimit": 20}},
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": "Volume (R$)"},
                },
            },
        },
    }

    sections.append({
        "type":        "chart",
        "title":       f"Volume por Strike — {underlying}",
        "description": (
            f"Volume financeiro (R$) por strike para o vencimento "
            f"{res.get('maturity', '-')} (ref: {res.get('refdate', '-')}). "
            "Barras verdes = calls; barras vermelhas = puts."
        ),
        "chart_data": chart_data,
        # [v3] NO range selector — this is a single-day snapshot, not a time series.
    })

    # [v3] Split detail table into 2 collapsible tables: calls + puts.
    # [v2] Right-align all columns (Strike / Vol / # are all numeric).
    strike_align = ["right", "right", "right"]
    call_rows = []
    put_rows = []
    for s in strikes:
        if s.get("call_volume", 0) > 0 or s.get("call_count", 0) > 0:
            call_rows.append([
                format_brl(s.get("strike")),
                format_int(s.get("call_volume")),
                s.get("call_count", 0),
            ])
        if s.get("put_volume", 0) > 0 or s.get("put_count", 0) > 0:
            put_rows.append([
                format_brl(s.get("strike")),
                format_int(s.get("put_volume")),
                s.get("put_count", 0),
            ])

    if call_rows:
        sections.append({
            "type": "table",
            "title": f"Volume Calls por Strike — {underlying}",
            "description": "Volume financeiro + número de calls por strike.",
            "columns": ["Strike", "Vol. Calls", "# Calls"],
            "rows": call_rows,
            "collapsible": True,
            "collapsible_open": True,
            "column_align": strike_align,
        })

    if put_rows:
        sections.append({
            "type": "table",
            "title": f"Volume Puts por Strike — {underlying}",
            "description": "Volume financeiro + número de puts por strike.",
            "columns": ["Strike", "Vol. Puts", "# Puts"],
            "rows": put_rows,
            "collapsible": True,
            "collapsible_open": True,
            "column_align": strike_align,
        })

    return sections


# ── Tab 4: Exercicios ────────────────────────────────────────────────────────
def _build_exercise_tab(underlying: str, days: int = 90) -> list[dict]:
    """Build the Exercicios tab sections.

    [v1.1] Shows exercise of stock options (BDI 38=call exercise, 42=put exercise).
    When option holders exercise their right, they buy (calls) or sell (puts)
    the underlying stock at the strike price. High exercise = options being
    assigned.

    Sections emitted:
      1. Bar chart: daily call exercise volume (green) + put exercise volume (red).
      2. Table: latest 15 observations (most recent first).
    """
    sections: list[dict] = []

    res = _safe_query(exercise_summary, underlying=underlying, days=days)
    status = res.get("status")
    if status != "ok":
        sections.append(build_error_section(
            "Exercicios de Opcoes",
            res.get("error", f"status={status}"),
        ))
        return sections

    observations = res.get("observations", [])
    if not observations:
        sections.append(build_error_section(
            "Exercicios de Opcoes",
            f"nenhum exercicio encontrado para {underlying}",
        ))
        return sections

    labels = [o["ref_date"] for o in observations]
    call_vols = [o.get("call_exercise_volume", 0) or 0 for o in observations]
    put_vols = [o.get("put_exercise_volume", 0) or 0 for o in observations]

    chart_data = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "type": "bar",
                    "label": "Exercicio Calls",
                    "data": call_vols,
                    "backgroundColor": _COLOR_CALL,
                    "borderColor": _COLOR_CALL,
                    "borderWidth": 0,
                },
                {
                    "type": "bar",
                    "label": "Exercicio Puts",
                    "data": put_vols,
                    "backgroundColor": _COLOR_PUT,
                    "borderColor": _COLOR_PUT,
                    "borderWidth": 0,
                },
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "scales": {
                "x": {"ticks": {"maxTicksLimit": 12}},
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": "Volume (R$)"},
                },
            },
            "plugins": {
                "title": {"display": True, "text": f"Exercicio de Opcoes — {underlying}"},
                "legend": {"display": True, "position": "top"},
            },
        },
    }

    sections.append({
        "type": "chart",
        "title": f"Exercicio de Opcoes — {underlying}",
        "description": (
            f"Volume de exercicio de calls (verde) + puts (vermelho) nos "
            f"ultimos {days} pregões. Exercicio = quando o titular exerce o "
            "direito de comprar (call) ou vender (put) o ativo pelo strike."
        ),
        "chart_data": chart_data,
    })

    # Table with the latest 15 observations.
    table_rows: list[list] = []
    for obs in reversed(observations[-15:]):
        table_rows.append([
            obs.get("ref_date", ""),
            format_int(obs.get("call_exercise_volume")),
            format_int(obs.get("put_exercise_volume")),
            format_int(obs.get("total")),
        ])
    # [v2] Right-align numeric columns (Data=left, the rest=right).
    sections.append(build_table_section(
        f"Ultimos Exercicios — {underlying}",
        table_rows,
        ["Data", "Ex. Calls (R$)", "Ex. Puts (R$)", "Total"],
        description="Ultimos 15 dias de exercicio (mais recente primeiro).",
        column_align=["left", "right", "right", "right"],
    ))
    return sections


# ── Tab 5: Volatilidade Implícita ──────────────────────────────────────────
def _build_iv_tab(underlying: str, original_input: str = "") -> list[dict]:
    """Build the Volatilidade Implícita tab sections.

    [v1.2] Black-Scholes implied volatility per option. Uses:
      - spot price from cotahist equities table (PETR4 latest close)
      - risk-free rate = Selic from BCB SGS series 432 (annualized, converted
        to continuous compounding)
      - T = (maturity - refdate).days / 365

    Sections emitted (in order):
      1. IV Smile chart — line chart of IV vs strike, separate datasets for
         calls (green) + puts (red). Range selector enabled.
      2. IV table — Papel | Tipo | Strike | Prêmio | IV, sorted by strike.
         Collapsible, expanded.
      3. IV Term Structure heatmap — strike (rows) × maturity (cols), each
         cell colored by IV (green=calm, yellow=mid, red=panic).
         [v3] ALWAYS renders — even with a single maturity (single-column
         heatmap is still useful — shows the smile). If `available_maturities`
         returns empty, falls back to the nearest-maturity chain (chain_res).

    Graceful degradation: if the spot price or Selic rate can't be fetched,
    the tab shows an error section but the rest of the dashboard is unaffected.
    """
    sections: list[dict] = []

    # ── Fetch spot + Selic ─────────────────────────────────────────────────
    spot, spot_refdate = _fetch_spot_price(underlying)
    if spot is None:
        sections.append(build_error_section(
            "Volatilidade Implícita",
            f"não foi possível obter o preço spot de {original_input or underlying} "
            "no cotahist (tabela de equities). Verifique se o ativo está sincronizado.",
        ))
        return sections

    r_cont = _fetch_selic_rate()
    if r_cont is None:
        sections.append(build_error_section(
            "Volatilidade Implícita",
            "não foi possível obter a taxa Selic (série 432 do SGS). "
            "Rode o sync do bcb.macro para popular o sgs.db.",
        ))
        return sections

    # ── Gather options across ALL maturities for the heatmap ──────────────
    mat_res = _safe_query(available_maturities, underlying=underlying)
    all_maturities: list[str] = []
    if mat_res.get("status") == "ok":
        all_maturities = [m["maturity"] for m in mat_res.get("maturities", [])
                          if m.get("maturity")]

    # ── Fetch the nearest-maturity chain (for the smile + IV table) ───────
    chain_res = _safe_query(options_chain, underlying=underlying)
    if chain_res.get("status") != "ok":
        sections.append(build_error_section(
            "Volatilidade Implícita",
            chain_res.get("error", "cadeia de opções indisponível"),
        ))
        return sections

    options = chain_res.get("options", [])
    if not options:
        sections.append(build_error_section(
            "Volatilidade Implícita",
            f"nenhuma opção encontrada para {underlying}",
        ))
        return sections

    refdate = chain_res.get("refdate") or spot_refdate
    maturity_str = chain_res.get("maturity", "-")

    # ── Compute IV per option (nearest maturity) ──────────────────────────
    enriched: list[dict] = []
    for opt in options:
        iv = _compute_iv_for_option(opt, spot, r_cont, refdate or "")
        enriched.append({**opt, "_iv": iv})

    calls = [o for o in enriched if o.get("option_type") == "CALL" and o.get("_iv") is not None]
    puts  = [o for o in enriched if o.get("option_type") == "PUT"  and o.get("_iv") is not None]

    # ── IV Smile chart (IV vs strike) ─────────────────────────────────────
    calls_sorted = sorted(calls, key=lambda o: float(o.get("strike_parsed", 0)))
    puts_sorted  = sorted(puts,  key=lambda o: float(o.get("strike_parsed", 0)))

    smile_chart_data = {
        "type": "line",
        "data": {
            "labels": [format_brl(o.get("strike_parsed")) for o in calls_sorted]
                      or [format_brl(o.get("strike_parsed")) for o in puts_sorted],
            "datasets": [
                {
                    "label": "IV Calls",
                    "data": [round(o["_iv"] * 100, 2) for o in calls_sorted],
                    "borderColor": _COLOR_CALL,
                    "backgroundColor": _COLOR_CALL,
                    "borderWidth": 1.5,
                    "pointRadius": 3,
                    "tension": 0.3,
                    "fill": False,
                },
                {
                    "label": "IV Puts",
                    "data": [round(o["_iv"] * 100, 2) for o in puts_sorted],
                    "borderColor": _COLOR_PUT,
                    "backgroundColor": _COLOR_PUT,
                    "borderWidth": 1.5,
                    "pointRadius": 3,
                    "tension": 0.3,
                    "fill": False,
                },
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "scales": {
                "x": {"title": {"display": True, "text": "Strike"},
                      "ticks": {"maxTicksLimit": 20}},
                "y": {"title": {"display": True, "text": "Volatilidade Implícita (%)"},
                      "ticks": {"callback": "((v) => v + '%')"}},
            },
            "plugins": {
                "title": {"display": True,
                          "text": f"IV Smile — {underlying} ({maturity_str})"},
                "legend": {"display": True, "position": "top"},
                "tooltip": {"callbacks": {"label": "((ctx) => ctx.dataset.label + ': ' + ctx.parsed.y + '%')"}},
            },
        },
    }

    smile_labels = ([format_brl(o.get("strike_parsed")) for o in calls_sorted]
                    or [format_brl(o.get("strike_parsed")) for o in puts_sorted])
    sections.append({
        "type": "chart",
        "title": f"IV Smile — {underlying} ({maturity_str})",
        "description": (
            f"Volatilidade Implícita por strike para o vencimento {maturity_str} "
            f"(ref: {refdate}). Spot = {format_brl(spot)}; taxa Selic (cont.) = "
            f"{r_cont*100:.4f}% a.a. Calls (verde) + Puts (vermelho). O 'smile' "
            "típico mostra IV mais alta nos strikes extremos (OTM) e mais baixa "
            "no ATM — desviô do smile indica skew de mercado."
        ),
        "chart_data": smile_chart_data,
        "price_range_selector": True,
        "price_full_labels": smile_labels,
        "price_full_datasets": [
            {"data": [round(o["_iv"] * 100, 2) for o in calls_sorted],
             "label": "IV Calls"},
            {"data": [round(o["_iv"] * 100, 2) for o in puts_sorted],
             "label": "IV Puts"},
        ],
    })

    # ── IV table ──────────────────────────────────────────────────────────
    iv_rows: list[list] = []
    for opt in sorted(enriched, key=lambda o: (o.get("option_type", ""), float(o.get("strike_parsed", 0)))):
        iv = opt.get("_iv")
        iv_rows.append([
            opt.get("symbol", ""),
            (opt.get("option_type") or "").title(),
            format_brl(opt.get("strike_parsed")),
            format_brl(opt.get("close")),
            format_pct(iv) if iv is not None else "-",
        ])
    sections.append({
        "type": "table",
        "title": f"Volatilidade Implícita — {underlying} ({maturity_str})",
        "description": (
            f"IV calculada via Black-Scholes (Newton-Raphson + bisection fallback). "
            f"Spot = {format_brl(spot)}, r (cont.) = {r_cont*100:.4f}% a.a. "
            "Opções sem IV (T≤0, prêmio < intrínseco, ou falha de convergência) "
            "mostram '-'."
        ),
        "columns": ["Papel", "Tipo", "Strike", "Prêmio", "IV"],
        "rows": iv_rows,
        "collapsible": True,
        "collapsible_open": True,
        # [v2] Right-align numeric columns (Strike/Prêmio/IV).
        "column_align": ["left", "left", "right", "right", "right"],
    })

    # ── IV Term Structure heatmap (strike × maturity) ─────────────────────
    # [v3] ALWAYS render — even with a single maturity (single-column heatmap
    # is still useful: shows the smile for the nearest expiry). If
    # `available_maturities` came back empty (failed or returned nothing),
    # fall back to the maturity from `chain_res` (already fetched above) so we
    # still render a single-column heatmap from the nearest-maturity chain.
    heatmap_maturities = list(all_maturities)
    if not heatmap_maturities and maturity_str and maturity_str != "-":
        heatmap_maturities = [maturity_str]

    if heatmap_maturities:
        # Build the (strike, maturity) -> IV map across all maturities.
        # For each maturity, re-fetch the chain so we have IVs at every expiry.
        # Exception: if the maturity matches the one we already fetched via
        # `chain_res` (the single-maturity fallback path), reuse `options`
        # instead of querying again.
        strike_set: set[float] = set()
        iv_map: dict[tuple[float, str], float | None] = {}
        for mat in heatmap_maturities:
            if mat == maturity_str and options:
                opts_for_mat = options
                mat_refdate = refdate or ""
            else:
                r = _safe_query(options_chain, underlying=underlying, maturity=mat)
                if r.get("status") != "ok":
                    continue
                opts_for_mat = r.get("options", [])
                mat_refdate = r.get("refdate") or refdate or ""
            for opt in opts_for_mat:
                K = opt.get("strike_parsed")
                if K is None:
                    continue
                try:
                    K = float(K)
                except (ValueError, TypeError):
                    continue
                strike_set.add(K)
                iv = _compute_iv_for_option(opt, spot, r_cont, mat_refdate)
                iv_map[(K, mat)] = iv

        if strike_set:
            strikes_sorted = sorted(strike_set)
            maturities_sorted = sorted(heatmap_maturities)
            # Format maturity headers as DD/MM/YY for compactness.
            def _fmt_mat(m: str) -> str:
                try:
                    d = _dt.fromisoformat(m)
                    return d.strftime("%d/%m/%y")
                except ValueError:
                    return m

            heat_columns = ["Strike"] + [_fmt_mat(m) for m in maturities_sorted]
            heat_rows: list[list] = []
            for K in strikes_sorted:
                row: list = [format_brl(K)]
                for mat in maturities_sorted:
                    iv = iv_map.get((K, mat))
                    if iv is None:
                        row.append({"text": "-", "bg": "", "color": ""})
                    else:
                        row.append({
                            "text": format_pct(iv),
                            "bg": _iv_color(iv),
                            "color": _iv_text_color(iv),
                        })
                heat_rows.append(row)

            sections.append(build_heatmap_section(
                f"Estrutura a Termo de IV — {underlying}",
                heat_columns,
                heat_rows,
                description=(
                    f"Mapa de calor strike × vencimento. Cor de fundo = IV "
                    f"(verde=calma <10%→ amarela ~55% → vermelha=pânico >100%). "
                    f"{len(strikes_sorted)} strikes × {len(maturities_sorted)} "
                    "vencimentos. Mostra a superfície de volatilidade — o 'smile' "
                    "em cada vencimento + a 'term structure' (como IV varia com o "
                    "prazo)."
                ),
            ))

    return sections


# ── Dashboard entrypoint ────────────────────────────────────────────────────
@register_mode(
    "dashboard",
    description=(
        "B3 options (derivatives) analytics dashboard. 5 tabs: "
        "Cadeia de Opções (options chain tables + ticker legend), "
        "Put/Call Ratio (sentiment trend chart + table), "
        "Volume por Strike (calls vs puts bar chart), "
        "Exercicios (exercise of calls/puts), "
        "Volatilidade Implícita (IV smile + IV table + IV term heatmap via Black-Scholes + Selic). "
        "Source: cotahist.db (cotahist_derivatives table) + sgs.db (Selic rate)."
    ),
    params={
        "underlying": (
            "str. 4-letter underlying code (e.g. PETR). Also accepts full "
            "tickers like PETR4 — the trailing digit is stripped automatically."
        ),
        "days": "int. P/C ratio lookback window in trading days. Default: 90.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="b3", sub_domain="options", mode="dashboard", '
        'params=\'{"underlying":"PETR"}\')',
        'skill(domain="b3", sub_domain="options", mode="dashboard", '
        'params=\'{"underlying":"PETR4"}\')',
    ],
)
def dashboard(underlying: str = "PETR", days: int = 90) -> dict:
    """Build the 5-tab B3 options dashboard for a single underlying.

    [v1.1] Added Exercicios tab (exercise of calls/puts — BDI 38/42).
    [v1.2] Added Volatilidade Implícita tab (Black-Scholes IV + Selic rate).
    [v2]    Legend reworked into 2-column CALLS|PUTS table + column_align on R$ cols.

    Args:
        underlying: 4-letter code (PETR) or full ticker (PETR4). The trailing
                    digit is stripped if present.
        days:       P/C ratio lookback window (default 90 trading days).

    Returns:
        {"status": "ok", "underlying": <normalized>, "title": ...,
         "tabs": [...]} on success. The dashboard stays status=ok even when
        a sub-query fails — the failed tab renders an error section, the
        others still render. status=error only if `underlying` is empty.
    """
    _t0 = _dt.now()
    print(f"[b3.options] Starting dashboard for {underlying!r}...", flush=True)

    u = _normalize_underlying(underlying)
    if not u:
        return {"status": "error", "error": "underlying is required"}

    # ── Tab 1/5: Cadeia de Opções ──────────────────────────────────────────
    _s_t0 = _dt.now()
    chain_sections = _build_chain_tab(u)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(
        f"  [step] Cadeia de Opções: {len(chain_sections)} sections "
        f"({_s_elapsed:.1f}s)",
        flush=True,
    )

    # ── Tab 2/5: Put/Call Ratio ──────────────────────────────────────────
    _s_t0 = _dt.now()
    pc_sections = _build_put_call_ratio_tab(u, days=days)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(
        f"  [step] Put/Call Ratio: {len(pc_sections)} sections "
        f"({_s_elapsed:.1f}s)",
        flush=True,
    )

    # ── Tab 3/5: Volume por Strike ───────────────────────────────────
    _s_t0 = _dt.now()
    vbs_sections = _build_volume_by_strike_tab(u)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(
        f"  [step] Volume por Strike: {len(vbs_sections)} sections "
        f"({_s_elapsed:.1f}s)",
        flush=True,
    )

    # ── Tab 4/5: Exercicios ───────────────────────────────────────────
    _s_t0 = _dt.now()
    exercise_sections = _build_exercise_tab(u, days=days)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(
        f"  [step] Exercicios: {len(exercise_sections)} sections "
        f"({_s_elapsed:.1f}s)",
        flush=True,
    )

    # ── Tab 5/5: Volatilidade Implícita ───────────────────────────────
    _s_t0 = _dt.now()
    iv_sections = _build_iv_tab(u, original_input=underlying)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(
        f"  [step] Volatilidade Implícita: {len(iv_sections)} sections "
        f"({_s_elapsed:.1f}s)",
        flush=True,
    )

    tabs = [
        {"name": "Cadeia de Opções",       "group": "Opções",  "sections": chain_sections},
        {"name": "Put/Call Ratio",         "group": "Análise", "sections": pc_sections},
        {"name": "Volume por Strike",      "group": "Análise", "sections": vbs_sections},
        {"name": "Exercicios",             "group": "Opções",  "sections": exercise_sections},
        {"name": "Volatilidade Implícita", "group": "Análise", "sections": iv_sections},
    ]

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[b3.options] Done! {len(tabs)} tabs in {_total:.1f}s.", flush=True)

    return {
        "status": "ok",
        "underlying": u,
        "title": f"{underlying}_options",
        "tabs": tabs,
    }
