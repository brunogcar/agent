"""Mode: dashboard -- 3-tab B3 options analytics dashboard.

Tabs:
  Cadeia de Opções   (group: Opções)   — options chain table + ticker legend
  Put/Call Ratio    (group: Análise)  — daily P/C ratio chart + table
  Volume por Strike  (group: Análise)  — bar chart of volume per strike

Workflow:
  1. Normalize the underlying code (PETR4 → PETR by stripping trailing digit)
  2. Query options_chain(underlying)  for the nearest maturity
  3. Query put_call_ratio(underlying, days=90)  for the sentiment trend
  4. Query volume_by_strike(underlying)  for the nearest maturity
  5. Build tables + charts via the report builders in skills.b3.options.report

Graceful degradation: if the cotahist_derivatives table doesn't exist or has
no data, the dashboard returns status=ok with error sections (so the other
tabs still render). Mirrors the CVM financials + bcb/macro contract.

Registered as "dashboard" in skills.b3.options._registry.MODES.
"""
from __future__ import annotations

from datetime import datetime as _dt

from skills.b3.options._registry import register_mode
from skills.b3.options.report import (
    build_chart_section, build_table_section,
    build_text_section, build_error_section,
)
from skills.b3.options.helpers import format_value, format_brl, format_int

from data_sources.b3.cotahist.derivatives_query import (
    options_chain, put_call_ratio, volume_by_strike, exercise_summary,
)


# ── Accent colors ────────────────────────────────────────────────────────────
_COLOR_CALL = "#22c55e"   # green — calls
_COLOR_PUT  = "#ef4444"   # red   — puts
_COLOR_REF  = "#9ca3af"   # gray  — reference line at 1.0


# ── Option ticker legend (text section for the Cadeia de Opções tab) ───────
_LEGEND_BODY = """\
Formato do ticker: UNDERLYING + MÊS + STRIKE

Códigos de mês para CALLS (compra):
  A=Jan  B=Fev  C=Mar  D=Abr  E=Mai  F=Jun
  G=Jul  H=Ago  I=Set  J=Out  K=Nov  L=Dez

Códigos de mês para PUTS (venda):
  M=Jan  N=Fev  O=Mar  P=Abr  Q=Mai  R=Jun
  S=Jul  T=Ago  U=Set  V=Out  W=Nov  X=Dez

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


# ── Tab 1: Cadeia de Opções ─────────────────────────────────────────────────
def _build_chain_tab(underlying: str, maturity: str = "") -> list[dict]:
    """Build the Cadeia de Opções tab sections.

    [v3] Split into 2 collapsible tables: one for calls, one for puts.
    Both expanded by default. Legend text section stays non-collapsible.

    Sections emitted (in order):
      1. Legend text section (option ticker naming convention)
      2. Calls table (collapsible, expanded) — Papel | Exercício | Vencimento |
         Último | Volume | Bid | Ask
      3. Puts table (collapsible, expanded) — same columns
    """
    sections: list[dict] = []

    # Legend (always shown — explains the ticker convention)
    sections.append(build_text_section(
        "Convenção de Ticker de Opções",
        _LEGEND_BODY,
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
        })

    return sections


# ── Tab 2: Put/Call Ratio ───────────────────────────────────────────────────
def _build_put_call_ratio_tab(underlying: str, days: int = 90) -> list[dict]:
    """Build the Put/Call Ratio tab sections.

    [v2] Chart now shows BOTH call volume (green bars) + put volume (red bars)
    on the left axis AND the P/C ratio (blue line) on the right axis. The user
    wanted to see both call + put info, not just the ratio.

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
    sections.append(build_table_section(
        f"Últimas Observações — {underlying}",
        table_rows,
        ["Data", "Volume Calls", "Volume Puts", "P/C Ratio"],
        description="Últimas 15 observações diárias (mais recente primeiro).",
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
    sections.append(build_table_section(
        f"Ultimos Exercicios — {underlying}",
        table_rows,
        ["Data", "Ex. Calls (R$)", "Ex. Puts (R$)", "Total"],
        description="Ultimos 15 dias de exercicio (mais recente primeiro).",
    ))
    return sections


# ── Dashboard entrypoint ────────────────────────────────────────────────────
@register_mode(
    "dashboard",
    description=(
        "B3 options (derivatives) analytics dashboard. 4 tabs: "
        "Cadeia de Opcoes (options chain table + ticker legend), "
        "Put/Call Ratio (sentiment trend chart + table), "
        "Volume por Strike (calls vs puts bar chart), "
        "Exercicios (exercise of calls/puts). "
        "Source: cotahist.db (cotahist_derivatives table)."
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
    """Build the 4-tab B3 options dashboard for a single underlying.

    [v1.1] Added Exercicios tab (exercise of calls/puts — BDI 38/42).

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

    # ── Tab 1/4: Cadeia de Opções ──────────────────────────────────────────
    _s_t0 = _dt.now()
    chain_sections = _build_chain_tab(u)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(
        f"  [step] Cadeia de Opções: {len(chain_sections)} sections "
        f"({_s_elapsed:.1f}s)",
        flush=True,
    )

    # ── Tab 2/4: Put/Call Ratio ──────────────────────────────────────────
    _s_t0 = _dt.now()
    pc_sections = _build_put_call_ratio_tab(u, days=days)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(
        f"  [step] Put/Call Ratio: {len(pc_sections)} sections "
        f"({_s_elapsed:.1f}s)",
        flush=True,
    )

    # ── Tab 3/4: Volume por Strike ───────────────────────────────────
    _s_t0 = _dt.now()
    vbs_sections = _build_volume_by_strike_tab(u)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(
        f"  [step] Volume por Strike: {len(vbs_sections)} sections "
        f"({_s_elapsed:.1f}s)",
        flush=True,
    )

    # ── Tab 4/4: Exercicios ───────────────────────────────────────────
    _s_t0 = _dt.now()
    exercise_sections = _build_exercise_tab(u, days=days)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(
        f"  [step] Exercicios: {len(exercise_sections)} sections "
        f"({_s_elapsed:.1f}s)",
        flush=True,
    )

    tabs = [
        {"name": "Cadeia de Opções", "group": "Opções",     "sections": chain_sections},
        {"name": "Put/Call Ratio",    "group": "Análise",    "sections": pc_sections},
        {"name": "Volume por Strike", "group": "Análise",    "sections": vbs_sections},
        {"name": "Exercicios",        "group": "Opções",     "sections": exercise_sections},
    ]

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[b3.options] Done! {len(tabs)} tabs in {_total:.1f}s.", flush=True)

    return {
        "status": "ok",
        "underlying": u,
        "title": f"{underlying}_options",
        "tabs": tabs,
    }
