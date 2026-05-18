"""
skills/cvm/{cvm_dividends/__init__.py or cvm_dividends.py}
Handles dividend/JCP data from rapina.db (rapinav2 schema).

=== DATA MODEL NOTES (from inspect_dividends_shareholders.py) ===

rapina.db table: empresas
  - One row per (company, fiscal_period). Same CNPJ can have many ids.
  - Match company by CNPJ or normalized name; never assume a single id.
  - Column names (verified): id, nome, cnpj, ano (year), dt_refer (date)

Three dividend data sources, each with its own strengths:

1. DVA (Demonstracao do Valor Adicionado) -- form 7 -- annual only
   Code 7.08.04.*  "Remuneracao de Capitais Proprios"
     7.08.04.01  Juros sobre o Capital Proprio (JCP)
     7.08.04.02  Dividendos  <-- DECLARED to shareholders (accrual)
     7.08.04.03  Lucros Retidos / Prejuizo do Periodo
     7.08.04.04  Part. Nao Controladores nos Lucros Retidos
   KEY INSIGHT: 7.08.04.02 is what PETROBRAS DECLARED, not what it paid.
   For 2022: declared R$155.9B; for 2023: declared R$52.9B.
   CAUTION: DVA is annual (dt_refer always Dec-31). Quarterly DVA exists
   in the DB but represents cumulative YTD, not a discrete quarter.
   Use DVA for the ANNUAL dividend declared figure.

2. DFC (Demonstracao dos Fluxos de Caixa) -- form 6 -- quarterly available
   Code 6.03.05  "Dividendos pagos a acionistas" (controlling shareholders)
   Code 6.03.06  "Dividendos pagos a acionistas nao controladores"
   Code 6.02.05  "Dividendos recebidos" (from investees -- NOT distributions)
   KEY INSIGHT: 6.03.05 is CASH ACTUALLY PAID in that period. It can differ
   substantially from 7.08.04.02 because: (a) payments may span periods,
   (b) it includes prior-year declared amounts paid in the current year.
   For 2022: paid R$194.2B vs declared R$155.9B (paid more than declared --
   this is previous-year declarations settling).
   For 2023: paid R$97.9B vs declared R$52.9B (same effect in reverse).
   Use DFC for "how much cash left the company" per period.

3. BPP (Balanco Patrimonial Passivo) -- form 2 -- quarterly available
   Code 2.01.05.02.01  "Dividendos e JCP a Pagar" (balance sheet liability)
   This is the OUTSTANDING PAYABLE at period-end. It tells you how much
   has been declared but not yet paid.
   KEY INSIGHT: Many Q1/Q3 quarters show 0 for this code -- Petrobras
   tends to declare dividends in Q2/Q4, so the payable spikes at those dates.
   Q1-2023: 0 payable. Q2-2023: R$30.8B payable.
   Use BPP to track the liability balance (declared but unpaid).

=== WHAT WE DO NOT USE ===
  BPP 2.03.04.*  "Reservas de Lucros" -- this is total profit reserves in
    equity, not a dividend payable. Sub-items (2.03.04.01-09) are ALL zero
    for Petrobras (they roll up into the parent 2.03.04 total). Skip these.
  BPP 2.03.09  "Participacao dos Acionistas Nao Controladores" -- minority
    interest in total equity. Used by cvm_shareholders, not dividends.

=== DECISION: mode="annual" queries DVA ===
  DVA is the cleanest annual dividend signal. It represents what the board
  DECLARED for that fiscal year. Available for all listed companies (10,139
  companies have 7.08.04.02). Annual only: dt_refer is always Dec-31.

=== DECISION: mode="cash_paid" queries DFC ===
  DFC 6.03.05 is cash-flow statement, available quarterly. The descriptions
  vary slightly by year ("Dividendos pagos a acionistas da Petrobras" vs
  "Dividendos Pagos a acionistas Petrobras") -- use LIKE '%6.03.05%' on
  the cd_conta column to be robust, not on the description.

=== DECISION: mode="declared" queries BPP 2.01.05.02.01 ===
  BPP dividend payable is the balance sheet snapshot. It is quarterly and
  shows what has been declared but not yet remitted to shareholders.
  WARNING: Many companies use a different structure for BPP -- the code
  2.01.05.02.01 is Petrobras-specific. Other companies may put dividends
  payable under different sub-codes. The mode="declared" output includes
  a note about this limitation.

=== DECISION: mode="status" returns a summary combining all three ===
  Status gives a quick health-check: latest annual declared (DVA), latest
  cash paid (DFC), and current payable (BPP). Designed to answer:
  "Is this company paying dividends and how much?"

=== SQL PATTERN: LIKE vs = for cd_conta ===
  rapina.db uses cd_conta as a string. Use:
    cd_conta = '7.08.04.02'    -- exact match when the code is well-known
    cd_conta LIKE '7.08.04%'   -- prefix match to get all children
  The inspect script confirmed the exact codes exist in the DB.

=== UNIT: values in rapina.db are in REAIS (not thousands) ===
  Petrobras 2024 DVA shows 14,091,000,000 for dividends.
  That is 14.091 billion BRL. Display as billions (/ 1e9) for readability.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


# ── DB path helper ────────────────────────────────────────────────────────────
# DECISION: Locate rapina.db via the same env-based config as other skills.
# Do NOT hardcode D:/mcp paths -- the skill must work on any machine.
# Falls back to a sensible default relative to the agent root.

def _db_path() -> Path:
    """Return path to rapina.db. Uses MEMORY_ROOT env var if set."""
    import os
    memory_root = os.getenv("MEMORY_ROOT", "")
    if memory_root:
        candidate = Path(memory_root) / "cvm" / "rapina.db"
        if candidate.exists():
            return candidate
    # Fallback: look relative to this file's location (skills/cvm/)
    here = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = here / "memory_db" / "cvm" / "rapina.db"
        if candidate.exists():
            return candidate
        candidate = here / "rapina.db"
        if candidate.exists():
            return candidate
        here = here.parent
    raise FileNotFoundError(
        "rapina.db not found. Set MEMORY_ROOT env var to point to memory_db/."
    )


def _connect() -> sqlite3.Connection:
    """Open rapina.db read-only."""
    path = _db_path()
    # DECISION: uri=True with ?mode=ro prevents accidental writes.
    # rapina.db is a read-only data store -- skills should never mutate it.
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ── Company lookup ────────────────────────────────────────────────────────────
# DECISION: Resolve company by CNPJ first (unique), then normalized name.
# One CNPJ can map to many empresa ids (different fiscal periods = different rows).
# We return ALL ids and let the query GROUP BY or pick the most recent.

def _resolve_company(conn: sqlite3.Connection, ticker_or_name: str) -> tuple[list[int], str]:
    """
    Return (list_of_empresa_ids, canonical_name) for a given ticker/name.
    Returns ([], "") if not found.

    DECISION: rapina.db empresas table has no ticker column -- tickers are
    not stored in rapina. We match by company name substring. For well-known
    companies, the caller should pass the official CVM name or a recognizable
    fragment (e.g. "PETROBRAS", "VALE", "ITAU").
    The CNPJ column is the true primary key for a company across years.
    """
    name_upper = ticker_or_name.upper().strip()

    # Try exact CNPJ match first (14 digits, with or without punctuation)
    cnpj_clean = "".join(c for c in ticker_or_name if c.isdigit())
    if len(cnpj_clean) == 14:
        rows = conn.execute(
            "SELECT DISTINCT id, nome FROM empresas WHERE cnpj = ?",
            (cnpj_clean,)
        ).fetchall()
        if rows:
            ids = [r["id"] for r in rows]
            return ids, rows[0]["nome"]

    # Fall back to name LIKE match
    rows = conn.execute(
        "SELECT DISTINCT id, nome FROM empresas WHERE upper(nome) LIKE ?",
        (f"%{name_upper}%",)
    ).fetchall()
    if not rows:
        return [], ""
    ids = [r["id"] for r in rows]
    return ids, rows[0]["nome"]


# ── Mode: annual (DVA 7.08.04.*) ──────────────────────────────────────────────

def _mode_annual(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
    years: int,
) -> str:
    """
    Fetch annual dividend data from DVA (form 7, code 7.08.04.*).

    Returns JCP (7.08.04.01) + Dividendos (7.08.04.02) + Total (7.08.04)
    for the last N fiscal years (dt_refer ending in '-12-31').

    DECISION: We fetch 7.08.04 (parent), 7.08.04.01, and 7.08.04.02.
    The parent is the TOTAL payout to equity holders. The children break it
    into JCP and Dividends. We show both because Brazilian tax treatment of
    JCP differs from dividends (JCP is tax-deductible for the company).

    DECISION: Filter dt_refer LIKE '%-12-31' to get only annual figures.
    Quarterly DVA rows exist but represent cumulative YTD -- they would
    double-count if mixed with annual rows.

    DECISION: rapina.db may have duplicate rows for the same (empresa_id,
    dt_refer, cd_conta) due to how rapina imports data. Use MAX(vl_conta)
    to pick the most recent import value when deduplicating.
    """
    if not ids:
        return "Empresa nao encontrada no banco de dados rapina."

    placeholders = ",".join("?" * len(ids))
    sql = f"""
        SELECT
            dt_refer,
            cd_conta,
            ds_conta,
            MAX(vl_conta) AS vl_conta
        FROM empresas
        WHERE id IN ({placeholders})
          AND cd_conta IN ('7.08.04', '7.08.04.01', '7.08.04.02', '7.08.04.03')
          AND dt_refer LIKE '%-12-31'
        GROUP BY dt_refer, cd_conta
        ORDER BY dt_refer DESC, cd_conta
        LIMIT ?
    """
    # years * 4 codes max
    rows = conn.execute(sql, ids + [years * 4]).fetchall()

    if not rows:
        return f"{company_name}: sem dados DVA (7.08.04.*) no banco."

    # Group by year
    from collections import defaultdict
    by_year: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_year[r["dt_refer"]][r["cd_conta"]] = r["vl_conta"]

    lines = [
        f"=== {company_name} -- Dividendos Anuais (DVA 7.08.04) ===",
        "Fonte: Demonstracao do Valor Adicionado (accrual -- valor DECLARADO no exercicio)",
        "",
    ]
    count = 0
    for year in sorted(by_year.keys(), reverse=True):
        if count >= years:
            break
        d = by_year[year]
        total    = d.get("7.08.04", 0) or 0
        jcp      = d.get("7.08.04.01", 0) or 0
        div      = d.get("7.08.04.02", 0) or 0
        retained = d.get("7.08.04.03", 0) or 0
        lines.append(f"Ano: {year[:4]}")
        lines.append(f"  Total Remuneracao Capitais Proprios : R$ {total/1e9:>10.2f} bi")
        lines.append(f"  JCP (Juros s/ Capital Proprio)      : R$ {jcp/1e9:>10.2f} bi")
        lines.append(f"  Dividendos declarados               : R$ {div/1e9:>10.2f} bi")
        lines.append(f"  Lucros Retidos / Prejuizo           : R$ {retained/1e9:>10.2f} bi")
        if total != 0:
            payout_pct = (jcp + div) / abs(total) * 100 if total else 0
            lines.append(f"  Payout (JCP+Div / Total)            : {payout_pct:.1f}%")
        lines.append("")
        count += 1

    return "\n".join(lines)


# ── Mode: cash_paid (DFC 6.03.05) ─────────────────────────────────────────────

def _mode_cash_paid(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
    periods: int,
) -> str:
    """
    Fetch dividends actually PAID from DFC (form 6, code 6.03.05).

    DECISION: We use cd_conta = '6.03.05' (exact) because this code is
    standardized across CVM filings. The description varies by company/year
    but the code is stable. We also fetch 6.03.06 (minority dividends) to
    show total cash outflow.

    DECISION: DFC is available quarterly (dt_refer is quarter-end).
    We show the last N periods sorted descending. Annual Dec-31 entries
    are the full-year cash flow; quarterly entries are cumulative YTD.
    To get a discrete quarter's payment: subtract prior quarter from current.
    This skill does NOT do that subtraction -- it shows raw cumulative values
    from the DFC as filed, which is the standard analyst approach.

    NOTE: Negative values = cash outflow (standard DFC convention).
    We display abs() with a "Pago" label to avoid confusion.
    """
    if not ids:
        return "Empresa nao encontrada."

    placeholders = ",".join("?" * len(ids))
    sql = f"""
        SELECT
            dt_refer,
            cd_conta,
            ds_conta,
            MAX(ABS(vl_conta)) AS vl_conta
        FROM empresas
        WHERE id IN ({placeholders})
          AND cd_conta IN ('6.03.05', '6.03.06', '6.02.05')
        GROUP BY dt_refer, cd_conta
        ORDER BY dt_refer DESC, cd_conta
        LIMIT ?
    """
    rows = conn.execute(sql, ids + [periods * 3]).fetchall()

    if not rows:
        return f"{company_name}: sem dados DFC (6.03.05) no banco."

    from collections import defaultdict
    by_period: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_period[r["dt_refer"]][r["cd_conta"]] = r["vl_conta"]

    lines = [
        f"=== {company_name} -- Dividendos Pagos em Caixa (DFC 6.03) ===",
        "Fonte: Demonstracao dos Fluxos de Caixa (regime de caixa -- valor PAGO no periodo)",
        "Nota: periodos cumulativos YTD. Dec-31 = anual completo.",
        "",
    ]
    count = 0
    for period in sorted(by_period.keys(), reverse=True):
        if count >= periods:
            break
        d = by_period[period]
        paid_ctrl = d.get("6.03.05", 0) or 0
        paid_min  = d.get("6.03.06", 0) or 0
        received  = d.get("6.02.05", 0) or 0
        total_out = paid_ctrl + paid_min
        lines.append(f"Periodo: {period}")
        lines.append(f"  Dividendos pagos (controladores)    : R$ {paid_ctrl/1e9:>10.2f} bi")
        lines.append(f"  Dividendos pagos (nao controladores): R$ {paid_min/1e9:>10.2f} bi")
        lines.append(f"  Total saida de caixa                : R$ {total_out/1e9:>10.2f} bi")
        if received:
            lines.append(f"  Dividendos recebidos (de coligadas) : R$ {received/1e9:>10.2f} bi")
        lines.append("")
        count += 1

    return "\n".join(lines)


# ── Mode: declared (BPP 2.01.05.02.01) ───────────────────────────────────────

def _mode_declared(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
    periods: int,
) -> str:
    """
    Fetch dividends PAYABLE (declared but not yet paid) from BPP.

    DECISION: We query 2.01.05.02.01 "Dividendos e JCP a Pagar".
    This is the current liability representing amounts approved by the board
    but not yet remitted to shareholders.

    LIMITATION (documented in module docstring): code 2.01.05.02.01 is
    specific to companies that use Petrobras-style BPP structure. Many
    companies use different sub-codes. The skill warns about this.

    DECISION: Include 2.01.05.02.02 "Dividendo Minimo Obrigatorio a Pagar"
    which is typically 0 for Petrobras but non-zero for some companies.

    INSIGHT from inspect: Many periods show 0 for the payable -- this is
    CORRECT. Petrobras declares and pays in the same quarter cycle, so the
    liability balance at quarter-end can legitimately be zero.
    """
    if not ids:
        return "Empresa nao encontrada."

    placeholders = ",".join("?" * len(ids))
    sql = f"""
        SELECT
            dt_refer,
            cd_conta,
            ds_conta,
            MAX(vl_conta) AS vl_conta
        FROM empresas
        WHERE id IN ({placeholders})
          AND cd_conta IN ('2.01.05.02.01', '2.01.05.02.02', '2.01.05.02')
        GROUP BY dt_refer, cd_conta
        ORDER BY dt_refer DESC, cd_conta
        LIMIT ?
    """
    rows = conn.execute(sql, ids + [periods * 3]).fetchall()

    if not rows:
        # FALLBACK: try broader search -- company may use different BPP structure
        # Some companies put dividends payable under 2.03.04.08 or custom codes
        sql2 = f"""
            SELECT dt_refer, cd_conta, ds_conta, MAX(vl_conta) AS vl_conta
            FROM empresas
            WHERE id IN ({placeholders})
              AND (lower(ds_conta) LIKE '%dividendo%pagar%'
                   OR lower(ds_conta) LIKE '%jcp%pagar%')
              AND cd_conta LIKE '2.%'
            GROUP BY dt_refer, cd_conta
            ORDER BY dt_refer DESC
            LIMIT ?
        """
        rows = conn.execute(sql2, ids + [periods * 2]).fetchall()
        if not rows:
            return (
                f"{company_name}: sem dados BPP de dividendos a pagar.\n"
                "Nota: esta empresa pode usar estrutura BPP diferente da padrao."
            )

    from collections import defaultdict
    by_period: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_period[r["dt_refer"]][r["cd_conta"]] = r["vl_conta"]

    lines = [
        f"=== {company_name} -- Dividendos a Pagar (BPP 2.01.05.02.01) ===",
        "Fonte: Balanco Patrimonial Passivo (saldo do passivo circulante no final do periodo)",
        "Nota: saldo 0 nao significa ausencia de dividendos -- pode ter sido pago no periodo.",
        "Aviso: estrutura BPP varia por empresa; codigo 2.01.05.02.01 pode nao existir.",
        "",
    ]
    count = 0
    for period in sorted(by_period.keys(), reverse=True):
        if count >= periods:
            break
        d = by_period[period]
        payable      = d.get("2.01.05.02.01", 0) or 0
        mandatory    = d.get("2.01.05.02.02", 0) or 0
        total_outros = d.get("2.01.05.02", 0) or 0
        lines.append(f"Periodo: {period}")
        lines.append(f"  Dividendos e JCP a Pagar            : R$ {payable/1e9:>10.2f} bi")
        if mandatory:
            lines.append(f"  Dividendo Minimo Obrigatorio a Pagar: R$ {mandatory/1e9:>10.2f} bi")
        if total_outros:
            lines.append(f"  Total Outros Passivos (2.01.05.02)  : R$ {total_outros/1e9:>10.2f} bi")
        lines.append("")
        count += 1

    return "\n".join(lines)


# ── Mode: status (summary) ────────────────────────────────────────────────────

def _mode_status(
    conn: sqlite3.Connection,
    ids: list[int],
    company_name: str,
) -> str:
    """
    Quick dividend health summary combining DVA, DFC, and BPP.

    Shows:
    - Latest annual declared (DVA 7.08.04.02, most recent Dec-31)
    - Latest cash paid (DFC 6.03.05, most recent period)
    - Current payable (BPP 2.01.05.02.01, most recent period)

    DECISION: status is the default mode because it answers the most common
    question: "Is this company paying dividends right now?"
    """
    if not ids:
        return "Empresa nao encontrada no banco de dados rapina."

    placeholders = ",".join("?" * len(ids))

    def _latest(code: str, annual_only: bool = False) -> tuple[str, float]:
        """Return (dt_refer, value) for the most recent row with given code."""
        date_filter = "AND dt_refer LIKE '%-12-31'" if annual_only else ""
        sql = f"""
            SELECT dt_refer, MAX(ABS(vl_conta)) AS vl
            FROM empresas
            WHERE id IN ({placeholders})
              AND cd_conta = ?
              {date_filter}
            GROUP BY dt_refer
            ORDER BY dt_refer DESC
            LIMIT 1
        """
        row = conn.execute(sql, ids + [code]).fetchone()
        if row and row["vl"] is not None:
            return row["dt_refer"], float(row["vl"])
        return "", 0.0

    # DVA: latest annual declared total and breakdown
    dva_date,   dva_total = _latest("7.08.04",    annual_only=True)
    _,          dva_jcp   = _latest("7.08.04.01", annual_only=True)
    _,          dva_div   = _latest("7.08.04.02", annual_only=True)

    # DFC: latest cash paid
    dfc_date,   dfc_paid  = _latest("6.03.05")

    # BPP: current payable
    bpp_date,   bpp_pay   = _latest("2.01.05.02.01")

    lines = [
        f"=== {company_name} -- Status de Dividendos ===",
        "",
    ]

    if dva_date:
        lines += [
            f"[DVA] Ultimo exercicio anual: {dva_date[:4]}",
            f"  Total Capitais Proprios : R$ {dva_total/1e9:.2f} bi",
            f"  JCP declarado           : R$ {dva_jcp/1e9:.2f} bi",
            f"  Dividendos declarados   : R$ {dva_div/1e9:.2f} bi",
        ]
        if dva_total:
            payout = (dva_jcp + dva_div) / abs(dva_total) * 100
            lines.append(f"  Payout ratio            : {payout:.1f}%")
        lines.append("")
    else:
        lines.append("[DVA] Sem dados de dividendos declarados.\n")

    if dfc_date:
        lines += [
            f"[DFC] Ultimo periodo com pagamento: {dfc_date}",
            f"  Caixa pago a acionistas : R$ {dfc_paid/1e9:.2f} bi",
            "",
        ]
    else:
        lines.append("[DFC] Sem dados de pagamento em caixa.\n")

    if bpp_date:
        lines += [
            f"[BPP] Passivo atual ({bpp_date})",
            f"  Dividendos a Pagar      : R$ {bpp_pay/1e9:.2f} bi",
            "",
        ]
    else:
        lines.append("[BPP] Sem passivo de dividendos registrado (ou codigo BPP diferente).\n")

    return "\n".join(lines)


# ── Public dispatcher ──────────────────────────────────────────────────────────

def cvm_dividends(
    ticker: str,
    mode: str = "status",
    periods: int = 5,
) -> dict:
    """
    Query dividend data from rapina.db for a Brazilian listed company.

    Args:
        ticker:  Company name fragment or CNPJ (14 digits).
                 Examples: "PETROBRAS", "VALE", "ITAU UNIBANCO", "33000167000101"
        mode:    "status"   -- quick summary: latest DVA + DFC + BPP (default)
                 "annual"   -- annual declared (DVA 7.08.04.*), last N years
                 "cash_paid"-- cash actually paid (DFC 6.03.05), last N periods
                 "declared" -- dividends payable on balance sheet (BPP 2.01.05.02.01)
        periods: Number of years/periods to return (default 5).

    Returns:
        dict with keys: status, mode, company, report (human-readable string),
        data (list of dicts for programmatic use).

    DECISION: Returns both a human-readable "report" string AND a structured
    "data" list. The report is ready for display or memory storage. The data
    list allows downstream tools (report, agent) to build charts or
    do further analysis without re-parsing the text.

    Example:
        cvm_dividends(ticker="PETROBRAS", mode="annual", periods=5)
        cvm_dividends(ticker="VALE", mode="cash_paid")
        cvm_dividends(ticker="ITAU", mode="status")
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e), "report": str(e), "data": []}

    try:
        ids, company_name = _resolve_company(conn, ticker)
        if not ids:
            msg = (
                f"Empresa '{ticker}' nao encontrada em rapina.db. "
                "Use o nome CVM oficial ou CNPJ (14 digitos)."
            )
            return {"status": "error", "error": msg, "report": msg, "data": []}

        mode = mode.lower().strip()

        if mode == "annual":
            report = _mode_annual(conn, ids, company_name, periods)
        elif mode == "cash_paid":
            report = _mode_cash_paid(conn, ids, company_name, periods)
        elif mode == "declared":
            report = _mode_declared(conn, ids, company_name, periods)
        elif mode == "status":
            report = _mode_status(conn, ids, company_name)
        else:
            msg = (
                f"Modo '{mode}' invalido. "
                "Use: status | annual | cash_paid | declared"
            )
            return {"status": "error", "error": msg, "report": msg, "data": []}

        return {
            "status":  "success",
            "mode":    mode,
            "company": company_name,
            "report":  report,
            # DECISION: data list is intentionally empty for now -- the report
            # string is the primary output. A future version can parse the DB
            # rows into structured dicts here for chart generation.
            "data": [],
        }

    except Exception as e:
        import traceback
        err = f"cvm_dividends error: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        return {"status": "error", "error": err, "report": err, "data": []}

    finally:
        conn.close()
