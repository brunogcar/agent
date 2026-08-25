"""Mode: dashboard -- 3-tab B3 term (a termo) contracts dashboard.

[v5] Clean stock fallback. Stock tickers without term data (BDI 26 = 0 rows
in 17 years of COTAHIST; B3 routes stock term to BTC) show:
  - Contratos Ativos: info box + spot price snapshot (last 5 closes)
  - Spread Termo vs Spot: info box + spot price chart (90 days)
  - Volume Historico: info box only (no chart -- term volume doesn't exist)

[v6] Forward-data enrichment. The stock fallback now queries the new
b3.api derivatives.db (DerivativesOpenPosition CSV bulk download) for the
EQUITY FORWARD contract snapshot (ticker = `{TICKER}T`, e.g. PETR4T).
The dashboard shows:
  - Contratos Ativos: forward contract snapshot KPI table (ticker, company,
    ISIN, security category, forward price per share, open interest, total
    quantity, aggregate value) + the spot price snapshot (last 5 closes,
    still useful as the spot reference for spread calc) + a forward-vs-spot
    spread row when spot is available.
  - Spread Termo vs Spot: a 1-row comparison table (forward price vs spot
    price + spread) + the spot price chart (90 days, still useful as
    reference).
  - Volume Historico: open position details table (OI, total quantity,
    forward price) + an info text explaining this is a daily snapshot
    (not historical volume -- the BTC doesn't publish daily term volume).

No options data (exercise volume) is shown -- that belongs in the options
skill, not the term skill. Spot price IS shown because it's the underlying
reference for term contracts (spread = term - spot).

Index tickers (IBOV) show full term data (134K+ rows of index futures).

Registered as "dashboard" in skills.b3.term._registry.MODES.
"""
from __future__ import annotations

from datetime import datetime as _dt

from skills.b3.term._registry import register_mode
from skills.b3.term.report import (
    build_chart_section, build_table_section,
    build_text_section, build_error_section,
)
from skills.b3.term.helpers import format_value, format_brl, format_int

from data_sources.b3.cotahist.derivatives_query import (
    term_chain, term_history,
)
from data_sources.b3.cotahist.query_engine import query as _spot_query
from data_sources.b3.api.query_engine import forward_positions as _forward_positions


# -- Accent colors -----------------------------------------------------------
_COLOR_TERM   = "#3b82f6"   # blue   -- term price
_COLOR_SPOT   = "#0d9488"   # teal   -- spot price
_COLOR_VOLUME = "#f59e0b"   # orange -- volume bars
_COLOR_SPREAD = "#9ca3af"   # gray   -- spread line (right axis)
_COLOR_FWD    = "#8b5cf6"   # purple -- forward price (stock fallback)


def _format_signed_brl(v) -> str:
    """Format a value as signed BRL: +R$ 1,53 or -R$ 1,53 (PT-BR)."""
    if v is None:
        return "-"
    try:
        f = float(v)
    except (ValueError, TypeError):
        return str(v)
    sign = "+" if f >= 0 else "-"
    return f"{sign}R$ {abs(f):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _format_signed_pct(v) -> str:
    """Format a value as signed percentage: +3,66% or -3,66% (PT-BR)."""
    if v is None:
        return "-"
    try:
        f = float(v)
    except (ValueError, TypeError):
        return str(v)
    sign = "+" if f >= 0 else "-"
    return f"{sign}{abs(f):,.2f}%".replace(",", "_").replace(".", ",").replace("_", ".")


# -- Context text section (term contract background -- always shown) ---------
_INFO_BODY = """\
Termo (a termo) = acordo bilateral de compra/venda de um ativo em data
futura, por preco fixo.

FORMATO DO TICKER:
- Acoes:   {TICKER}T  (ex: PETR4T, VALE3T)  -- o sufixo T = "termo"
- Indices: IBOV, IBRX, SMLL  (sem sufixo T)

BDI codes: 26 (acao) e 74 (indice) -> derivative_type = "TERM"

DADOS DISPONIVEIS NO COTAHIST:
- BDI 74 (indice): IBOV futures -- 134K+ rows, dados completos desde 2010
- BDI 26 (acao):   0 rows no COTAHIST (17 anos de historico). A B3 ruteia
  contratos a termo de acoes para o BTC (Balcao Organizado).

DADOS DE FORWARD (b3.api derivatives.db):
- Para acoes sem dados de termo no COTAHIST, o dashboard mostra o snapshot
  do contrato EQUITY FORWARD (ticker = {TICKER}T, ex: PETR4T) da tabela
  DerivativesOpenPosition da B3. Campos:
    * OpnIntrst = interesse aberto (contratos ainda em aberto)
    * CurQty    = quantidade total contratada (em acoes)
    * FwdPric   = preco forward agregado (R$)
    * forward_price_per_share = FwdPric / CurQty
  Join com instruments.db traz Empresa, ISIN, Categoria, Especificacao.
  ATENCAO: e um snapshot diario (nao historico) -- o BTC nao publica
  volume diario de termo.

CAMPOS (COTAHIST, BDI 74):
- close = preco do termo (preco futuro acordado), NAO o spot
- maturity = data de liquidacao
- volume = volume financeiro (R$)
- contracts = numero de contratos negociados
- days_settle = dias ate a liquidacao

Spread (termo - spot) = agio/desagio forward. Positivo = mercado em agio
(termo acima do spot); negativo = desagio.
"""


def _safe_query(fn, **kwargs) -> dict:
    """Call a query_engine function defensively."""
    try:
        return fn(**kwargs)
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def _strip_trailing_digits(s: str) -> str:
    """PETR4 -> PETR; IBOV -> IBOV."""
    s = s.strip().upper()
    while s and s[-1].isdigit():
        s = s[:-1]
    return s


def _spot_close_map(ticker: str, date_from: str, date_to: str) -> dict[str, float]:
    """Fetch spot close prices for `ticker` between date_from and date_to."""
    if not ticker or not date_from or not date_to:
        return {}
    spot_ticker = ticker.rstrip("T") if ticker.endswith("T") else ticker
    res = _safe_query(
        _spot_query,
        ticker=spot_ticker, date_from=date_from, date_to=date_to,
        limit=10000, market_type=10,
    )
    if res.get("status") != "ok":
        return {}
    out: dict[str, float] = {}
    for r in res.get("rows", []):
        d = r.get("refdate")
        c = r.get("close")
        if d and c is not None:
            try:
                out[d] = float(c)
            except (ValueError, TypeError):
                continue
    return out


def _spot_history(ticker: str, days: int = 90) -> list[dict]:
    """Fetch spot OHLCV rows for `ticker` (last N days). Returns list of dicts
    with refdate + close, ascending by date."""
    spot_ticker = ticker.rstrip("T") if ticker.endswith("T") else ticker
    res = _safe_query(
        _spot_query,
        ticker=spot_ticker, limit=days, market_type=10,
    )
    if res.get("status") != "ok":
        return []
    rows = res.get("rows", [])
    out = []
    for r in reversed(rows):
        d = r.get("refdate")
        c = r.get("close")
        if d and c is not None:
            try:
                out.append({"ref_date": d, "close": float(c)})
            except (ValueError, TypeError):
                continue
    return out


# -- Tab 1: Contratos Ativos -------------------------------------------------
def _build_contracts_tab(ticker: str) -> list[dict]:
    """Build the Contratos Ativos tab sections.

    If term data found: active term contracts table.
    If not found (stock): info box + spot price snapshot (last 5 closes).
    """
    sections: list[dict] = []

    sections.append(build_text_section(
        "Termo (a termo) -- Visao Geral",
        _INFO_BODY,
    ))

    res = _safe_query(term_chain, ticker=ticker)
    status = res.get("status")
    if status == "ok" and res.get("contracts"):
        contracts = res.get("contracts", [])
        sorted_contracts = sorted(
            contracts,
            key=lambda c: (c.get("maturity") or "", c.get("refdate") or ""),
        )
        columns = [
            "Vencimento", "Preco Termo", "Volume (R$)",
            "Contratos", "Dias p/ Liquidacao",
        ]
        rows: list[list] = []
        for c in sorted_contracts:
            rows.append([
                c.get("maturity", ""),
                format_brl(c.get("close")),
                format_int(c.get("volume")),
                format_int(c.get("contracts")),
                format_int(c.get("days_settle")),
            ])
        refdate = sorted_contracts[0].get("refdate", "-")
        resolved_ticker = res.get("ticker", ticker)
        sections.append({
            "type": "table",
            "title": f"Contratos Ativos -- {resolved_ticker}",
            "description": (
                f"{len(rows)} contratos a termo para {resolved_ticker} (ref: {refdate}). "
                "Ordenados por vencimento (mais proximo primeiro). "
                "Preco Termo = preco futuro acordado (campo `close`); "
                "Volume = volume financeiro (R$)."
            ),
            "columns": columns,
            "rows": rows,
            "collapsible": True,
            "collapsible_open": True,
        })
        return sections

    # -- Fallback: no term data (stock ticker) --
    # [v6] Forward-data enrichment: query b3.api derivatives.db for the
    # EQUITY FORWARD contract snapshot (ticker = {TICKER}T). If found,
    # show the forward contract KPI table + spot price snapshot + spread.
    fwd = _safe_query(_forward_positions, ticker=ticker)
    fwd_ok = fwd.get("status") == "ok"

    if fwd_ok:
        sections.append(build_text_section(
            f"Sem dados de termo no COTAHIST -- usando forward ({fwd.get('ticker', ticker)})",
            (
                f"Nenhum contrato a termo (BDI 26) para {ticker} no COTAHIST -- "
                f"a B3 ruteia termo de acoes para o BTC (Balcao Organizado).\n\n"
                f"Como fallback, exibimos abaixo o snapshot do contrato EQUITY FORWARD "
                f"({fwd.get('ticker', ticker)}) da tabela DerivativesOpenPosition da B3 "
                f"(b3.api derivatives.db). O forward e o equivalente funcional do termo "
                f"para acoes: acordo bilateral de compra/venda a preco fixo em data futura.\n\n"
                f"Snapshot de {fwd.get('refdate', '-')}. "
                f"Atencao: e um snapshot diario (nao historico) -- o BTC nao publica "
                f"volume diario de termo. Para historico, use ticker='IBOV' (indice)."
            ),
        ))

        # Forward contract snapshot KPI table (2 cols: Campo, Valor).
        fwd_rows: list[list] = [
            ["Contrato",                      fwd.get("ticker", "")],
            ["Empresa",                       fwd.get("company", "") or "-"],
            ["ISIN",                          fwd.get("isin", "") or "-"],
            ["Categoria",                     fwd.get("security_category", "") or "-"],
            ["Especificacao",                 fwd.get("specification", "") or "-"],
            ["Preco Forward (poracao)",       format_brl(fwd.get("forward_price_per_share"))],
            ["Interesse Aberto",              f"{format_int(fwd.get('open_interest'))} contratos"],
            ["Quantidade Total",              f"{format_int(fwd.get('total_quantity'))} acoes"],
            ["Valor Total (FwdPric)",         format_brl(fwd.get("forward_price_aggregate"))],
        ]
        sections.append(build_table_section(
            f"Snapshot Forward -- {fwd.get('ticker', ticker)}",
            fwd_rows,
            ["Campo", "Valor"],
            description=(
                f"Snapshot diario do contrato EQUITY FORWARD {fwd.get('ticker', ticker)} "
                f"(underlying: {ticker}). "
                f"Preco Forward poracao = FwdPric (agregado) / CurQty (qtde total). "
                f"Interesse Aberto = contratos ainda em aberto. "
                f"Fonte: b3.api derivatives.db (DerivativesOpenPosition CSV bulk download) "
                f"+ instruments.db (join por TckrSymb)."
            ),
        ))
    else:
        # Forward data not available (derivatives.db not synced, or no
        # EQUITY FORWARD entry for this ticker). Show the legacy info box.
        sections.append(build_text_section(
            "Sem dados de termo para esta acao",
            (
                f"Nenhum contrato a termo encontrado para {ticker} no COTAHIST "
                f"(BDI 26 = 0 rows; a B3 ruteia termo de acoes para o BTC).\n\n"
                f"Tentamos tambem o snapshot EQUITY FORWARD ({ticker}T) no "
                f"b3.api derivatives.db -- status: {fwd.get('status', 'unknown')}. "
                f"Execute o sync da b3.api (derivatives + instruments) para habilitar "
                f"o fallback de forward: "
                f'data_source(domain="b3", sub_domain="api", mode="sync", '
                f'params=\'{{"table":"derivatives"}}\')\n\n'
                f"Como fallback, mostramos abaixo o preco spot recente de {ticker} "
                f"(preco spot e a referencia para o calculo do termo: spread = termo - spot)."
            ),
        ))

    # Spot price snapshot (last 5 closes) -- always useful context (the
    # spot is the underlying reference for the spread calc).
    spot_rows = _spot_history(ticker, days=10)
    spot_close = spot_rows[-1]["close"] if spot_rows else None

    if spot_rows:
        last5 = spot_rows[-5:]
        last5.reverse()  # most recent first
        table_rows = [
            [r["ref_date"], format_brl(r["close"])]
            for r in last5
        ]
        sections.append(build_table_section(
            f"Preco Spot Recente -- {ticker}",
            table_rows,
            ["Data", "Preco Spot (close)"],
            description=(
                f"Ultimos {len(last5)} pregoes de {ticker} no mercado a vista. "
                "Dados do cotahist (tabela de acoes). "
                "Preco spot e a referencia para o calculo do spread forward."
            ),
        ))

        # Forward-vs-spot spread row (only if both forward + spot available).
        if fwd_ok:
            fwd_per_share = fwd.get("forward_price_per_share")
            if fwd_per_share is not None and spot_close is not None:
                try:
                    spread = round(float(fwd_per_share) - float(spot_close), 4)
                    spread_pct = (spread / float(spot_close) * 100.0) if float(spot_close) else None
                except (ValueError, TypeError):
                    spread = None
                    spread_pct = None
                if spread is not None:
                    sections.append(build_table_section(
                        f"Spread Forward vs Spot -- {ticker}",
                        [[
                            format_brl(fwd_per_share),
                            format_brl(spot_close),
                            _format_signed_brl(spread),
                            _format_signed_pct(spread_pct) if spread_pct is not None else "-",
                        ]],
                        ["Preco Forward (poracao)", "Spot (ultimo close)", "Spread (R$)", "Spread (%)"],
                        description=(
                            f"Spread = Preco Forward - Preco Spot. "
                            f"Positivo = mercado em agio (contango); negativo = desagio (backwardation). "
                            f"Spot = ultimo close de {ticker}; Forward = FwdPric/CurQty de {fwd.get('ticker', ticker)}."
                        ),
                    ))
    else:
        sections.append(build_error_section(
            "Preco Spot Recente",
            f"nenhum preco spot encontrado para {ticker}",
        ))

    return sections


# -- Tab 2: Spread Termo vs Spot ---------------------------------------------
def _build_spread_tab(ticker: str, days: int = 90) -> list[dict]:
    """Build the Spread Termo vs Spot tab sections.

    If term data found: term price + spot price + spread chart.
    If not found (stock): spot price chart (90 days) as fallback.
    """
    sections: list[dict] = []

    res = _safe_query(term_history, ticker=ticker, days=days)
    status = res.get("status")
    if status == "ok" and res.get("observations"):
        observations = res.get("observations", [])
        resolved_ticker = res.get("ticker", ticker)
        dates = [o["ref_date"] for o in observations if o.get("ref_date")]
        date_from = min(dates) if dates else ""
        date_to = max(dates) if dates else ""
        spot_map = _spot_close_map(resolved_ticker, date_from, date_to)

        labels = dates
        term_prices = [o.get("avg_price") for o in observations]
        spot_prices = [spot_map.get(d) for d in labels]
        spreads: list[float | None] = []
        for t_p, s_p in zip(term_prices, spot_prices):
            if t_p is None or s_p is None:
                spreads.append(None)
            else:
                try:
                    spreads.append(round(float(t_p) - float(s_p), 4))
                except (ValueError, TypeError):
                    spreads.append(None)

        has_spot = any(s is not None for s in spot_prices)

        chart_data = {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "type": "line",
                        "label": "Preco Termo (medio)",
                        "data": term_prices,
                        "borderColor": _COLOR_TERM,
                        "backgroundColor": _COLOR_TERM,
                        "borderWidth": 1.8,
                        "pointRadius": 1.5,
                        "pointHoverRadius": 4,
                        "tension": 0.3,
                        "fill": False,
                        "yAxisID": "y",
                    },
                    {
                        "type": "line",
                        "label": "Preco Spot",
                        "data": spot_prices,
                        "borderColor": _COLOR_SPOT,
                        "backgroundColor": _COLOR_SPOT,
                        "borderWidth": 1.8,
                        "pointRadius": 1.5,
                        "pointHoverRadius": 4,
                        "tension": 0.3,
                        "fill": False,
                        "yAxisID": "y",
                    },
                    {
                        "type": "line",
                        "label": "Spread (Termo - Spot)",
                        "data": spreads,
                        "borderColor": _COLOR_SPREAD,
                        "backgroundColor": _COLOR_SPREAD,
                        "borderWidth": 1.4,
                        "pointRadius": 0,
                        "pointHoverRadius": 3,
                        "tension": 0.2,
                        "fill": False,
                        "borderDash": [4, 3],
                        "yAxisID": "y1",
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
                        "title": {"display": True, "text": "Preco (R$)"},
                        "beginAtZero": False,
                    },
                    "y1": {
                        "position": "right",
                        "title": {"display": True, "text": "Spread (R$)"},
                        "grid": {"drawOnChartArea": False},
                    },
                },
                "plugins": {
                    "title": {"display": True, "text": f"Spread Termo vs Spot -- {resolved_ticker}"},
                    "legend": {"display": True, "position": "top"},
                },
            },
        }

        spread_desc = (
            f"Preco do termo (medio diario, azul) vs preco spot (verde-azulado) "
            f"no eixo esquerdo, spread = termo - spot (cinza, tracejado) no "
            f"eixo direito. {days} pregoes. "
            "Spread > 0 = mercado em agio (contango); < 0 = desagio (backwardation)."
        )
        if not has_spot:
            spread_desc += (
                " ATENCAO: nenhum preco spot encontrado para o ticker no "
                "intervalo -- apenas o preco do termo e exibido."
            )

        sections.append({
            "type": "chart",
            "title": f"Spread Termo vs Spot -- {resolved_ticker}",
            "description": spread_desc,
            "chart_data": chart_data,
            "price_range_selector": True,
            "price_full_labels": labels,
            "price_full_datasets": [
                {"data": term_prices, "label": "Preco Termo (medio)"},
                {"data": spot_prices, "label": "Preco Spot"},
                {"data": spreads, "label": "Spread (Termo - Spot)"},
            ],
        })

        table_rows: list[list] = []
        for obs in reversed(observations[-15:]):
            d = obs.get("ref_date", "")
            tp = obs.get("avg_price")
            sp = spot_map.get(d)
            if tp is not None and sp is not None:
                try:
                    spread = round(float(tp) - float(sp), 4)
                except (ValueError, TypeError):
                    spread = None
            else:
                spread = None
            table_rows.append([
                d,
                format_brl(tp),
                format_brl(sp) if sp is not None else "-",
                format_brl(spread) if spread is not None else "-",
            ])
        sections.append(build_table_section(
            f"Ultimas Observacoes -- {resolved_ticker}",
            table_rows,
            ["Data", "Preco Termo", "Preco Spot", "Spread"],
            description="Ultimas 15 observacoes diarias (mais recentes primeiro).",
        ))
        return sections

    # -- Fallback: no term data (stock ticker) --
    # [v6] Forward-data enrichment: show a forward-vs-spot comparison table
    # (1 row, today's snapshot) before the spot price chart (still useful
    # as reference for the 90-day window).
    fwd = _safe_query(_forward_positions, ticker=ticker)
    fwd_ok = fwd.get("status") == "ok"

    spot_rows = _spot_history(ticker, days=days)
    spot_close = spot_rows[-1]["close"] if spot_rows else None

    if fwd_ok:
        sections.append(build_text_section(
            "Sem historico de termo -- comparando Forward vs Spot",
            (
                f"Sem historico de termo para {ticker} (BDI 26 = 0 rows no COTAHIST; "
                f"B3 ruteia para o BTC). Como fallback, comparamos o Preco Forward "
                f"({fwd.get('ticker', ticker)}, snapshot diario do b3.api derivatives.db) "
                f"com o Preco Spot (ultimo close do cotahist). "
                f"Abaixo, o grafico do preco spot nos ultimos {days} pregoes como referencia."
            ),
        ))

        # 1-row comparison table: Forward vs Spot + Spread.
        fwd_per_share = fwd.get("forward_price_per_share")
        if fwd_per_share is not None and spot_close is not None:
            try:
                spread = round(float(fwd_per_share) - float(spot_close), 4)
                spread_pct = (spread / float(spot_close) * 100.0) if float(spot_close) else None
            except (ValueError, TypeError):
                spread = None
                spread_pct = None

            sections.append(build_table_section(
                f"Forward vs Spot (snapshot) -- {ticker}",
                [[
                    fwd.get("refdate", "-"),
                    format_brl(fwd_per_share),
                    format_brl(spot_close),
                    _format_signed_brl(spread) if spread is not None else "-",
                    _format_signed_pct(spread_pct) if spread_pct is not None else "-",
                ]],
                ["Data (forward)", "Preco Forward (poracao)", "Spot (ultimo close)", "Spread (R$)", "Spread (%)"],
                description=(
                    f"Snapshot diario: Forward {fwd.get('ticker', ticker)} (b3.api) vs "
                    f"Spot {ticker} (cotahist, ultimo close). "
                    f"Spread = Forward - Spot. Positivo = agio (contango); negativo = desagio (backwardation)."
                ),
            ))
        else:
            # Forward price per share not available -- show what we have.
            sections.append(build_table_section(
                f"Forward Snapshot -- {ticker}",
                [
                    ["Contrato",                  fwd.get("ticker", "")],
                    ["Preco Forward (poracao)",   format_brl(fwd_per_share)],
                    ["Interesse Aberto",          f"{format_int(fwd.get('open_interest'))} contratos"],
                    ["Quantidade Total",          f"{format_int(fwd.get('total_quantity'))} acoes"],
                ],
                ["Campo", "Valor"],
                description=(
                    f"Snapshot do contrato EQUITY FORWARD {fwd.get('ticker', ticker)}. "
                    f"Preco forward poracao indisponivel (FwdPric ou CurQty ausente) -- "
                    f"nao foi possivel calcular o spread vs spot."
                ),
            ))
    else:
        sections.append(build_text_section(
            "Sem dados de termo -- mostrando preco spot",
            (
                f"Nenhum historico de termo para {ticker} (BDI 26 = 0 rows no COTAHIST). "
                f"Tentamos tambem o snapshot EQUITY FORWARD ({ticker}T) no b3.api "
                f"derivatives.db -- status: {fwd.get('status', 'unknown')}. "
                f"Como fallback, exibimos o preco spot de {ticker} nos ultimos {days} pregoes. "
                f"Preco spot e a referencia para o calculo do termo (spread = termo - spot)."
            ),
        ))

    if not spot_rows:
        sections.append(build_error_section(
            "Preco Spot",
            f"nenhum preco spot encontrado para {ticker}",
        ))
        return sections

    labels = [r["ref_date"] for r in spot_rows]
    closes = [r["close"] for r in spot_rows]

    chart_data = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "type": "line",
                "label": "Preco Spot (close)",
                "data": closes,
                "borderColor": _COLOR_SPOT,
                "backgroundColor": _COLOR_SPOT,
                "borderWidth": 1.8,
                "pointRadius": 1.5,
                "pointHoverRadius": 4,
                "tension": 0.3,
                "fill": False,
            }],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "scales": {
                "x": {"ticks": {"maxTicksLimit": 12}},
                "y": {
                    "position": "left",
                    "title": {"display": True, "text": "Preco (R$)"},
                    "beginAtZero": False,
                },
            },
            "plugins": {
                "title": {"display": True, "text": f"Preco Spot -- {ticker} (referencia)"},
                "legend": {"display": True, "position": "top"},
            },
        },
    }

    sections.append({
        "type": "chart",
        "title": f"Preco Spot -- {ticker}",
        "description": (
            f"Preco spot (close) de {ticker} nos ultimos {len(spot_rows)} pregoes. "
            "Exibido como referencia para o calculo do spread forward (snapshot diario "
            "do b3.api nao tem historico de termo)."
        ),
        "chart_data": chart_data,
        "price_range_selector": True,
        "price_full_labels": labels,
        "price_full_datasets": [
            {"data": closes, "label": "Preco Spot (close)"},
        ],
    })
    return sections


# -- Tab 3: Volume Historico -------------------------------------------------
def _build_volume_tab(ticker: str, days: int = 90) -> list[dict]:
    """Build the Volume Historico tab sections.

    If term data found: term volume bar chart + table.
    If not found (stock): info box only (no chart -- term volume doesn't exist).
    """
    sections: list[dict] = []

    res = _safe_query(term_history, ticker=ticker, days=days)
    status = res.get("status")
    if status == "ok" and res.get("observations"):
        observations = res.get("observations", [])
        resolved_ticker = res.get("ticker", ticker)
        labels = [o["ref_date"] for o in observations]
        volumes = [o.get("total_volume", 0) or 0 for o in observations]

        chart_data = {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "type": "bar",
                    "label": "Volume (R$)",
                    "data": volumes,
                    "backgroundColor": _COLOR_VOLUME,
                    "borderColor": _COLOR_VOLUME,
                    "borderWidth": 0,
                }],
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
                    "title": {"display": True, "text": f"Volume Historico -- {resolved_ticker}"},
                    "legend": {"display": True, "position": "top"},
                },
            },
        }

        sections.append({
            "type": "chart",
            "title": f"Volume Historico -- {resolved_ticker}",
            "description": (
                f"Volume financeiro diario (R$) dos contratos a termo de {resolved_ticker}. "
                f"Ultimos {days} pregoes. Barras laranjas."
            ),
            "chart_data": chart_data,
            "price_range_selector": True,
            "price_full_labels": labels,
            "price_full_datasets": [
                {"data": volumes, "label": "Volume (R$)"},
            ],
        })

        table_rows: list[list] = []
        for obs in reversed(observations[-15:]):
            table_rows.append([
                obs.get("ref_date", ""),
                format_int(obs.get("total_volume")),
                format_int(obs.get("total_contracts")),
                format_brl(obs.get("avg_price")),
            ])
        sections.append(build_table_section(
            f"Ultimos Volumes -- {resolved_ticker}",
            table_rows,
            ["Data", "Volume (R$)", "Contratos", "Preco Medio"],
            description="Ultimas 15 observacoes diarias (mais recente primeiro).",
        ))
        return sections

    # -- Fallback: no term data (stock ticker) --
    # [v6] Forward-data enrichment: show the open position details (OI,
    # total quantity, forward price) from b3.api derivatives.db. The BTC
    # doesn't publish daily term volume, so we show the daily snapshot of
    # the open forward contract position instead.
    fwd = _safe_query(_forward_positions, ticker=ticker)
    fwd_ok = fwd.get("status") == "ok"

    if fwd_ok:
        sections.append(build_text_section(
            "Sem historico de volume -- mostrando snapshot diario do forward",
            (
                f"Nenhum volume de termo para {ticker} (BDI 26 = 0 rows no COTAHIST; "
                f"a B3 ruteia termo de acoes para o BTC, que nao publica volume diario).\n\n"
                f"Como alternativa, exibimos abaixo o snapshot diario da posicao em aberto "
                f"do contrato EQUITY FORWARD ({fwd.get('ticker', ticker)}) da tabela "
                f"DerivativesOpenPosition da B3 (b3.api derivatives.db). "
                f"E um snapshot de hoje (nao historico) -- mostra o estoque de contratos "
                f"em aberto, nao o fluxo diario.\n\n"
                f"Para historico de volume de termo, use ticker='IBOV' (indice, BDI 74)."
            ),
        ))

        # Open position details table (1 row: today's snapshot).
        pos_rows: list[list] = [[
            fwd.get("refdate", "-"),
            fwd.get("ticker", ""),
            format_int(fwd.get("open_interest")),
            format_int(fwd.get("total_quantity")),
            format_brl(fwd.get("forward_price_aggregate")),
            format_brl(fwd.get("forward_price_per_share")),
        ]]
        sections.append(build_table_section(
            f"Posicao em Aberto (Forward) -- {fwd.get('ticker', ticker)}",
            pos_rows,
            ["Data", "Contrato", "Interesse Aberto", "Qtde Total (acoes)", "Valor Total (R$)", "Preco Forward/acao"],
            description=(
                f"Snapshot diario da posicao em aberto do contrato EQUITY FORWARD "
                f"{fwd.get('ticker', ticker)} (underlying: {ticker}). "
                f"Interesse Aberto = contratos ainda em aberto (OpnIntrst). "
                f"Qtde Total = acoes contratadas (CurQty). "
                f"Valor Total = preco forward agregado (FwdPric). "
                f"Preco Forward/acao = FwdPric / CurQty. "
                f"Fonte: b3.api derivatives.db."
            ),
        ))
    else:
        sections.append(build_text_section(
            "Sem dados de volume de termo",
            (
                f"Nenhum volume de termo para {ticker} (BDI 26 = 0 rows no COTAHIST). "
                f"Contratos a termo de acoes sao negociados no BTC (Balcao Organizado), "
                f"nao no mercado a vista -- o COTAHIST nao registra esse volume.\n\n"
                f"Tentamos tambem o snapshot EQUITY FORWARD ({ticker}T) no b3.api "
                f"derivatives.db -- status: {fwd.get('status', 'unknown')}. "
                f"Execute o sync da b3.api (derivatives + instruments) para habilitar "
                f"o fallback de posicao em aberto.\n\n"
                f"Para ver volume de termo de indice, use: ticker='IBOV'"
            ),
        ))
    return sections


# -- Dashboard entrypoint ----------------------------------------------------
@register_mode(
    "dashboard",
    description=(
        "B3 term (a termo) contracts dashboard. 3 tabs: "
        "Contratos Ativos (active term contracts table), "
        "Spread Termo vs Spot (daily term price vs spot price + spread), "
        "Volume Historico (daily term volume bar chart). "
        "[v6] Stock tickers without term data (BDI 26 = 0 rows) show the "
        "EQUITY FORWARD contract snapshot from b3.api derivatives.db "
        "(ticker = {TICKER}T, e.g. PETR4T) as the term-equivalent fallback, "
        "with forward price per share + spot price + spread. Index tickers "
        "(IBOV) show full term data (134K+ rows). "
        "Sources: cotahist.db (cotahist_derivatives) + b3.api derivatives.db "
        "(EQUITY FORWARD fallback) + instruments.db (company/ISIN join)."
    ),
    params={
        "ticker": (
            "str. Stock ticker (e.g. PETR4) or index (e.g. IBOV). "
            "Stock term data (BDI 26) is NOT in COTAHIST -- dashboard shows "
            "the EQUITY FORWARD snapshot fallback (b3.api derivatives.db). "
            "Index term data (BDI 74) is available for IBOV."
        ),
        "days": "int. Lookback window in trading days. Default: 90.",
    },
    include_in_all=False,
    examples=[
        'skill(domain="b3", sub_domain="term", mode="dashboard", '
        'params=\'{"ticker":"PETR4"}\')',
        'skill(domain="b3", sub_domain="term", mode="dashboard", '
        'params=\'{"ticker":"IBOV"}\')',
        'skill(domain="b3", sub_domain="term", mode="dashboard", '
        'params=\'{"ticker":"VALE3","days":120}\')',
    ],
)
def dashboard(ticker: str = "PETR4", days: int = 90) -> dict:
    """Build the 3-tab B3 term (a termo) dashboard for a single ticker.

    [v6] Stock tickers without COTAHIST term data fall back to the EQUITY
    FORWARD snapshot from b3.api derivatives.db (forward price per share,
    open interest, total quantity) + spot price + spread. Index tickers
    (IBOV) show full term data from COTAHIST.

    Args:
        ticker: Stock ticker (e.g. PETR4, VALE3) or index (e.g. IBOV).
        days:   Lookback window (default 90 trading days).

    Returns:
        {"status": "ok", "ticker": <normalized>, "title": <ticker>_term,
         "tabs": [...]} on success.
    """
    _t0 = _dt.now()
    print(f"[b3.term] Starting dashboard for {ticker!r}...", flush=True)

    t = (ticker or "").strip().upper()
    if not t:
        return {"status": "error", "error": "ticker is required"}

    _s_t0 = _dt.now()
    contracts_sections = _build_contracts_tab(t)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(f"  [step] Contratos Ativos: {len(contracts_sections)} sections ({_s_elapsed:.1f}s)", flush=True)

    _s_t0 = _dt.now()
    spread_sections = _build_spread_tab(t, days=days)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(f"  [step] Spread Termo vs Spot: {len(spread_sections)} sections ({_s_elapsed:.1f}s)", flush=True)

    _s_t0 = _dt.now()
    volume_sections = _build_volume_tab(t, days=days)
    _s_elapsed = (_dt.now() - _s_t0).total_seconds()
    print(f"  [step] Volume Historico: {len(volume_sections)} sections ({_s_elapsed:.1f}s)", flush=True)

    tabs = [
        {"name": "Contratos Ativos",     "group": "Termo",   "sections": contracts_sections},
        {"name": "Spread Termo vs Spot", "group": "Analise", "sections": spread_sections},
        {"name": "Volume Historico",     "group": "Analise", "sections": volume_sections},
    ]

    _total = (_dt.now() - _t0).total_seconds()
    print(f"[b3.term] Done! {len(tabs)} tabs in {_total:.1f}s.", flush=True)

    return {
        "status": "ok",
        "ticker": t,
        "title": f"{ticker}_term",
        "tabs": tabs,
    }
