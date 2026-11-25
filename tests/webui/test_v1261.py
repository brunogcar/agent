"""tests/webui/test_v1261.py — the v1.26.1 company-fixes suite.

[v1.26.1] "general fixes and tweaks for companies" — the five backend
changes, each pinned with hand-computed fixtures that mirror the REAL
data shapes (same recipe as test_governance_v126):

  1. Financials payload cache — overview()/statements() store their
     payload in _cache.webui_payloads keyed by the composite fingerprint;
     a second call is a HIT (no rebuild, ⚡ cache_note added), a
     fingerprint change is a MISS (rebuild), no fingerprint → cache
     skipped entirely. The foundation for the future comparador.
  2. webui_fingerprint — the DFP+ITR × COTAHIST composite (embeds
     MAX(data_fim_exerc), the trimester reference the user asked for).
  3. Dividends DPA engine — the TWO merged sources: (a) the share-class
     correction (the B3 API stores PETR3+PETR4 rows under the SAME
     ticker; SUM(rate) used to double-count — now the group keeps ONE
     row, the ISIN match when cotahist knows the class); (b) the DDM
     agenda merge with NO duplicates (same type + dates within 5 days +
     rates within 2%). This is the "DPA doesn't display anything while
     the company has proventos" fix.
  4. Múltiplos Menos Comuns — the table became a colored heatmap
     (Métrica | Valor | Leitura; green/amber/red bands per direction).
  5. Insiders — the cargo/tipo color vocabulary (pills in Movimentações
     + Por Cargo + the new Por Tipo subtab) and the by_tipo aggregation
     (the vlmo query engine's new GROUP BY Tipo_Movimentacao).
  6. Proventos IPE announcements — the CVM cross-reference section
     (categoria/tipo proventos filter, link cell to the CVM document).
  7. [v1.26.1 fix 1] The Acionistas Visão Geral dedup — the evolution
     charts + top-5 preview live in their own subtabs; the overview
     renders the CURRENT snapshot instead (controle × free float doughnut
     + top-N concentration measured in quantities ÷ total emitido).

Run:  python -m pytest tests/webui/test_v1261.py -v
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_sources.cvm.ipe.catalog import SCHEMA_SQL as IPE_SCHEMA  # noqa: E402
from data_sources.cvm.vlmo.catalog import SCHEMA_SQL as VLMO_SCHEMA  # noqa: E402
from data_sources.b3.dividends.catalog import SCHEMA_SQL as B3DIV_SCHEMA  # noqa: E402
from data_sources.ddm.dividends.catalog import SCHEMA_SQL as DDM_SCHEMA  # noqa: E402

PETR = "33000167000101"
TEST = "11222333000181"


# ── shared fixture helpers ───────────────────────────────────────────────────

def _bridge(root: Path, pairs: list[tuple[str, str]]) -> None:
    b = sqlite3.connect(str(root / "cvm" / "bridge.db"))
    b.execute("""CREATE TABLE IF NOT EXISTS ticker_map (
        ticker TEXT PRIMARY KEY, issuing TEXT, cd_cvm TEXT, trading_name TEXT,
        cnpj TEXT, denom_social TEXT, denom_comerc TEXT, sit TEXT,
        setor_ativ TEXT, tp_merc TEXT, synced_at TEXT)""")
    for ticker, cnpj in pairs:
        b.execute("INSERT INTO ticker_map (ticker, cnpj) VALUES (?, ?)",
                  (ticker, cnpj))
    b.commit()
    b.close()


# ── 1. Financials payload cache ──────────────────────────────────────────────

def test_fin_overview_payload_cache_roundtrip(tmp_path, monkeypatch):
    """Build once → hit forever (same fingerprint); new fingerprint →
    rebuild. The hit carries the ⚡ cache_note; the fresh build doesn't."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    from webui.services.financials import FinancialsService

    calls = {"n": 0}

    def fake_build(self, tk):
        calls["n"] += 1
        return {"ticker": tk, "status": "ok",
                "ttm": {"metrics": {"receita_liquida": 42.0}}}

    monkeypatch.setattr(FinancialsService, "_build_overview", fake_build)
    monkeypatch.setattr(FinancialsService, "_fingerprint",
                        staticmethod(lambda tk: "fp-A"))

    svc = FinancialsService()
    r1 = svc.overview("PETR4")
    assert calls["n"] == 1
    assert "cache_note" not in r1          # fresh build — no note

    r2 = svc.overview("PETR4")
    assert calls["n"] == 1                 # HIT — no rebuild
    assert "Pré-calculado" in r2["cache_note"]
    assert r2["ttm"]["metrics"]["receita_liquida"] == 42.0  # payload intact

    # fingerprint changed (new filing/quote synced) → miss → rebuild
    monkeypatch.setattr(FinancialsService, "_fingerprint",
                        staticmethod(lambda tk: "fp-B"))
    r3 = svc.overview("PETR4")
    assert calls["n"] == 2
    assert "cache_note" not in r3

    # another ticker never collides with PETR4's row
    monkeypatch.setattr(FinancialsService, "_fingerprint",
                        staticmethod(lambda tk: "fp-A"))
    svc.overview("VALE3")
    assert calls["n"] == 3


def test_fin_overview_no_fingerprint_skips_cache(tmp_path, monkeypatch):
    """Fingerprint unresolvable (no DFP/ITR/cotahist at all) → the cache
    is skipped entirely: every call builds, nothing crashes."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    from webui.services.financials import FinancialsService

    calls = {"n": 0}

    def fake_build(self, tk):
        calls["n"] += 1
        return {"ticker": tk, "status": "ok", "ttm": None}

    monkeypatch.setattr(FinancialsService, "_build_overview", fake_build)
    monkeypatch.setattr(FinancialsService, "_fingerprint",
                        staticmethod(lambda tk: None))
    svc = FinancialsService()
    svc.overview("PETR4")
    svc.overview("PETR4")
    assert calls["n"] == 2                 # never cached


def test_fin_statements_payload_cache(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    from webui.services.financials import FinancialsService

    calls = {"n": 0}

    def fake_build(self, tk, period, n):
        calls["n"] += 1
        return {"ticker": tk, "status": "ok", "period_type": period,
                "labels": ["2024", "2025"], "dates": ["2024-12-31",
                                                      "2025-12-31"],
                "statements": {"BPA": {"rows": []}}}

    monkeypatch.setattr(FinancialsService, "_build_statements", fake_build)
    monkeypatch.setattr(FinancialsService, "_fingerprint",
                        staticmethod(lambda tk: "fp-A"))
    svc = FinancialsService()
    r1 = svc.statements("PETR4", period="annual")
    r2 = svc.statements("PETR4", period="annual")
    assert calls["n"] == 1                 # second call = HIT
    assert r2["labels"] == r1["labels"]
    assert "cache_note" not in r2          # statements: fast, no note
    # different period → different key → separate build
    svc.statements("PETR4", period="quarterly")
    assert calls["n"] == 2


# ── 2. webui_fingerprint (the composite) ─────────────────────────────────────

def test_webui_fingerprint_composite(tmp_path, monkeypatch):
    """DFP side missing → COTAHIST side still identifies the data (and
    vice-versa); the string embeds the quote fingerprint so a new sync
    invalidates. TTL-cached in memory (second call same result)."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    b3 = tmp_path / "b3"
    b3.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(b3 / "cotahist.db"))
    c.execute("CREATE TABLE daily_prices (ticker TEXT, refdate TEXT)")
    c.execute("INSERT INTO daily_prices VALUES ('PETR4', '2026-11-20')")
    c.commit()
    c.close()

    from data_sources import _cache as _dc
    _dc._fp_cache.clear()
    fp = _dc.webui_fingerprint("PETR4")
    assert fp is not None and fp.startswith("cot:")
    assert "2026-11-20" in fp
    # a new quote date changes the composite (cache invalidation)
    c = sqlite3.connect(str(b3 / "cotahist.db"))
    c.execute("INSERT INTO daily_prices VALUES ('PETR4', '2026-11-21')")
    c.commit()
    c.close()
    _dc._fp_cache.clear()                  # (TTL bypass — deterministic)
    assert _dc.webui_fingerprint("PETR4") != fp


def test_dividends_fingerprint_fixed(tmp_path, monkeypatch):
    """[the latent bug] _get_dividends_fingerprint used to query a
    `proventos` table on the B3 catalog (it only exists on DDM) — always
    None, the dividends engine cache was never valid. Now it combines
    B3 cash_dividends + DDM dividends max dates."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    b3 = tmp_path / "b3"
    ddm = tmp_path / "ddm"
    b3.mkdir(parents=True, exist_ok=True)
    ddm.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(b3 / "dividends.db"))
    c.executescript(B3DIV_SCHEMA)
    c.execute("INSERT INTO cash_dividends (ticker, label, isin_code, "
              "approved_on, last_date_prior, rate) VALUES "
              "('PETR4', 'DIVIDENDO', 'BRPETRACNPR6', '2025-01-15', "
              "'2025-02-01', 1.0)")
    c.commit()
    c.close()
    d = sqlite3.connect(str(ddm / "dividends.db"))
    d.executescript(DDM_SCHEMA)
    d.execute("INSERT INTO dividends (ticker, tipo, value, record_date, "
              "ex_date, payment_date) VALUES "
              "('PETR4', 'Dividendo', 2.0, '2026-01-10', '2026-01-15', "
              "'2026-02-01')")
    d.commit()
    d.close()

    from data_sources import _cache as _dc
    fp = _dc._get_dividends_fingerprint("PETR4")
    assert fp is not None
    assert "b3:" in fp and "ddm:" in fp
    assert "2026-02-01" in fp             # DDM side must invalidate too


# ── 3. Dividends DPA engine — class correction + DDM merge ──────────────────

# B3 cash_dividends for DUAL4 — a dual-class issuer (both classes stored
# under the same ticker, the API's shape):
#   E1: DIVIDENDO 1,00 — PR3 + PR6 rows, SAME dates (payment 2024-03-01)
#   E2: JCP different rates per class — PR3 0,50 / PR6 0,80 (payment
#       2025-03-01); cotahist knows DUAL4 = ...PR6 → 0,80 counts.
# DDM agenda for DUAL4:
#   E3: Dividendo 2,00 ex 2026-01-15 (NOT in B3 — the missing-event case)
#   E4: JCP 0,81 ex 2025-02-02 (a DUPLICATE of E2: 1 day off, rate
#       within 2% — must NOT double-count)
_DUAL_B3 = [
    # (label, isin, approved, ldp, rate, payment)
    ("DIVIDENDO", "BRDUALACNPR3", "2024-01-15", "2024-02-01", 1.00, "2024-03-01"),
    ("DIVIDENDO", "BRDUALACNPR6", "2024-01-15", "2024-02-01", 1.00, "2024-03-01"),
    ("JRS CAP PROPRIO", "BRDUALACNPR3", "2025-01-10", "2025-02-01", 0.50, "2025-03-01"),
    ("JRS CAP PROPRIO", "BRDUALACNPR6", "2025-01-10", "2025-02-01", 0.80, "2025-03-01"),
]
_DUAL_DDM = [
    # (tipo, value, record, ex, payment)
    ("Dividendo", 2.00, "2026-01-10", "2026-01-15", "2026-02-01"),
    ("JCP", 0.81, "2025-02-01", "2025-02-02", "2025-03-02"),
]


@pytest.fixture()
def div_root(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    b3 = tmp_path / "b3"
    ddm = tmp_path / "ddm"
    b3.mkdir(parents=True, exist_ok=True)
    ddm.mkdir(parents=True, exist_ok=True)

    c = sqlite3.connect(str(b3 / "dividends.db"))
    c.executescript(B3DIV_SCHEMA)
    for label, isin, ap, ldp, rate, pay in _DUAL_B3:
        c.execute("INSERT INTO cash_dividends (ticker, label, isin_code, "
                  "approved_on, last_date_prior, rate, payment_date) "
                  "VALUES (?,?,?,?,?,?,?)",
                  ("DUAL4", label, isin, ap, ldp, rate, pay))
    c.commit()
    c.close()

    # cotahist — DUAL4's class ISIN (the PR6 preferred share)
    k = sqlite3.connect(str(b3 / "cotahist.db"))
    k.execute("CREATE TABLE cotahist (symbol TEXT, isin TEXT)")
    k.execute("INSERT INTO cotahist VALUES ('DUAL4', 'BRDUALACNPR6')")
    k.commit()
    k.close()

    d = sqlite3.connect(str(ddm / "dividends.db"))
    d.executescript(DDM_SCHEMA)
    for tipo, value, rec, ex, pay in _DUAL_DDM:
        d.execute("INSERT INTO dividends (ticker, tipo, value, record_date, "
                  "ex_date, payment_date) VALUES (?,?,?,?,?,?)",
                  ("DUAL4", tipo, value, rec, ex, pay))
    d.commit()
    d.close()

    # fresh merged-events memo (module-level 60s TTL cache)
    from skills.cvm.calculations.engines import dividends as _div
    _div._events_memo.clear()
    return tmp_path


def test_dpa_dual_class_not_doubled(div_root):
    """E1 exists as TWO class rows (PR3 + PR6, same rate 1,00) — the old
    SUM(rate) counted 2,00; the class-corrected merge counts ONCE."""
    from skills.cvm.calculations.engines.dividends import dividends_at
    assert dividends_at("DUAL4", "2024-06-30") == pytest.approx(1.00)


def test_dpa_class_rate_picked_by_isin(div_root):
    """E2 carries DIFFERENT rates per class (0,50 ON vs 0,80 PN) — the
    ticker's ISIN (...PR6, from cotahist) wins: 0,80, not 1,30."""
    from skills.cvm.calculations.engines.dividends import dividends_at
    assert dividends_at("DUAL4", "2025-06-30") == pytest.approx(0.80)


def test_dpa_ddm_merge_and_dedupe(div_root):
    """E3 (DDM-only, 2,00) counts in the TTM window ending 2026-06-30 —
    the 'DPA missing while the company pays' fix. E4 (the DDM duplicate
    of E2: 1 day off, rate within 2%) must NOT add on top of E2."""
    from skills.cvm.calculations.engines.dividends import dividends_at
    # window 2025-06-30..2026-06-30: only E3 (DDM-only)
    assert dividends_at("DUAL4", "2026-06-30") == pytest.approx(2.00)
    # window 2024-06-30..2025-06-30: E2 (0,80) + E4 duplicate NOT added
    assert dividends_at("DUAL4", "2025-06-30") == pytest.approx(0.80)


def test_dpa_periods_cover_merged_sources(div_root):
    from skills.cvm.calculations.engines.dividends import dividends_periods
    dates = [p["date"] for p in dividends_periods("DUAL4")]
    # B3 event dates (payment-preferred) + the DDM-only ex date
    assert "2024-03-01" in dates and "2025-03-01" in dates
    assert "2026-01-15" in dates


def test_dpa_no_data_returns_none(div_root):
    """A ticker with nothing in EITHER source → None (no data), the
    contract the ratios mode distinguishes from 0.0."""
    from skills.cvm.calculations.engines import dividends as _div
    _div._events_memo.clear()
    assert _div.dividends_at("NOTHR4", "2025-06-30") is None


# ── 4. Múltiplos Menos Comuns — the colored heatmap ──────────────────────────

def test_less_common_is_heatmap_with_verdict_colors():
    from skills.cvm.valuation.report.multiples import build_multiples_sections
    ratios = {
        "price": 10.0,
        "apa": 0.80,             # ≤ 1      → green "Barata"
        "ppa": 4.00,             # > 3      → red "Muito alavancado"
        "rbpa": 2.00,            # 1..3     → amber "Na faixa"
        "a_p_inverse": 1.25,     # ≥ 1 (high) → green "Favorável"
        "financial_leverage": 2.00,  # 1.5..3 → amber "Alavancagem média"
        "p_vpa": 2.50,           # 1..3     → amber "Na faixa"
        # p_cg / p_db / price_to_tangible_book absent → "—"
    }
    secs = build_multiples_sections(ratios)
    mc = [s for s in secs if s.get("title") == "Múltiplos Menos Comuns"]
    assert len(mc) == 1
    mc = mc[0]
    assert mc["type"] == "heatmap"
    assert mc["columns"] == ["Métrica", "Valor", "Leitura"]
    rows = {r[0]["text"]: r for r in mc["rows"]}
    assert rows["P/Ativos"][1]["bg"] == "rgba(34,197,94,0.2)"
    assert rows["P/Ativos"][2]["text"] == "Barata"
    assert rows["P/Passivos"][1]["bg"] == "rgba(220,38,38,0.2)"
    assert rows["P/Passivos"][2]["text"] == "Muito alavancado"
    assert rows["P/RB"][1]["bg"] == "rgba(245,158,11,0.2)"
    assert rows["P/RB"][2]["text"] == "Na faixa"
    assert rows["A/P"][2]["text"] == "Favorável"
    assert rows["A/P"][1]["bg"] == "rgba(34,197,94,0.2)"
    assert rows["A/PL"][2]["text"] == "Alavancagem média"
    # missing metric → uncolored "—" (absence is not a verdict)
    assert rows["P/Tangible Book"][1]["text"] == "—"
    assert rows["P/Tangible Book"][1]["bg"] == ""
    # the metric label keeps the formula tooltip
    assert rows["P/Ativos"][0]["tooltip"]


# ── 5. Insiders — colors + by_tipo ───────────────────────────────────────────

# (date, cargo, tipo, qty, price, volume) — the vocabulary the user
# enumerated, one row each + a second Compra à vista (the clear
# most-frequent winner).
_VLMO_ROWS = [
    ("2026-01-10", "Diretor ou Vinculado", "Compra à vista", 1000, 10.0, 10000.0),
    ("2026-01-20", "Diretor ou Vinculado", "Compra à vista", 200, 10.5, 2100.0),
    ("2026-01-15", "Diretor ou Vinculado", "Venda à vista", 500, 11.0, 5500.0),
    ("2026-02-01", "Conselho de Administração ou Vinculado", "Posse", 2000, None, None),
    ("2026-02-10", "Controlador ou Vinculado", "Ações de plano de remuneração", 300, None, None),
    ("2026-03-01", "Diretor ou Vinculado", "Desligamento/saída", 100, None, None),
]


@pytest.fixture()
def vlmo_root(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    cvm = tmp_path / "cvm"
    cvm.mkdir(parents=True, exist_ok=True)
    _bridge(tmp_path, [("TEST4", TEST)])
    v = sqlite3.connect(str(cvm / "vlmo.db"))
    v.executescript(VLMO_SCHEMA)
    for dt, cargo, tipo, qty, price, vol in _VLMO_ROWS:
        v.execute("""INSERT INTO vlmo_movements (CNPJ_Companhia,
                     Data_Movimentacao, Tipo_Cargo, Tipo_Movimentacao,
                     Tipo_Ativo, Quantidade, Preco_Unitario, Volume)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (TEST, dt, cargo, tipo, "ACAO", qty, price, vol))
    v.commit()
    v.close()
    return tmp_path


def test_insider_color_vocabulary():
    """The user's cargo/tipo lists each carry their own stable color;
    unknown values still get a deterministic one (hash fallback)."""
    from webui.services.insiders import (
        CARGO_COLORS, TIPO_COLORS, cargo_color, tipo_color)
    for c in ("Controlador ou Vinculado", "Diretor ou Vinculado",
              "Conselho de Administração ou Vinculado",
              "Órgão Estatutário ou Vinculado",
              "Conselho Fiscal ou Vinculado"):
        assert CARGO_COLORS[c] and cargo_color(c) == CARGO_COLORS[c]
    for t in ("Compra à vista", "Venda à vista",
              "Ações de plano de remuneração", "Outras Saídas",
              "Outras Entradas", "Desligamento/saída", "Posse",
              "Compra à termo"):
        assert TIPO_COLORS[t] and tipo_color(t) == TIPO_COLORS[t]
    # semantic prefixes (plain/variant forms the DB may carry)
    assert tipo_color("Compra") == "#16a34a"
    assert tipo_color("Venda a prazo") == "#dc2626"
    # stable fallback for unknown vocabulary
    assert tipo_color("Doação").startswith("#")
    assert tipo_color("Doação") == tipo_color("Doação")
    assert cargo_color("Auditor Externo").startswith("#")


def test_vlmo_by_tipo_engine(vlmo_root):
    from data_sources.cvm.vlmo.query_engine import query
    r = query(company="TEST4", by_tipo=True, limit=30)
    assert r["status"] == "ok"
    agg = {row["Tipo_Movimentacao"]: row for row in r["by_tipo"]}
    assert agg["Compra à vista"]["transaction_count"] == 2
    assert agg["Compra à vista"]["total_volume"] == pytest.approx(12100.0)
    assert agg["Venda à vista"]["total_volume"] == pytest.approx(5500.0)
    assert agg["Posse"]["transaction_count"] == 1
    assert agg["Posse"]["total_volume"] in (None, 0)   # no price → no volume
    assert agg["Desligamento/saída"]["total_qty"] == pytest.approx(100.0)
    assert agg["Ações de plano de remuneração"]["transaction_count"] == 1


def test_insiders_by_tipo_payload(vlmo_root):
    """The Por Tipo subtab: KPIs, the pill table (each tipo its color),
    and the per-tipo colored count chart."""
    from webui.services.insiders import InsiderService, tipo_color
    svc = InsiderService()
    out = svc.by_tipo("TEST4")
    assert out["status"] == "ok"
    labels = [k["label"] for k in out["kpis"]]
    assert "Tipos" in labels and "Mais Frequente" in labels
    freq = [k for k in out["kpis"] if k["label"] == "Mais Frequente"][0]
    assert "Compra à vista" in freq["value"]      # 2× — the clear winner

    tbl = [s for s in out["sections"]
           if s.get("type") == "table" and "por Tipo" in s.get("title", "")][0]
    assert tbl["sortable"]
    by_first = {r[0]["text"]: r for r in tbl["rows"]}
    assert by_first["Compra à vista"][0]["pill"] == tipo_color("Compra à vista")
    assert by_first["Posse"][0]["pill"] == tipo_color("Posse")
    # volume only fills for priced movements
    assert by_first["Posse"][3] == "—"
    vol_txt = by_first["Compra à vista"][3]
    assert "12.100" in vol_txt

    charts = [s for s in out["sections"] if s.get("type") == "chart"]
    assert any("Movimentações por Tipo" == c["title"] for c in charts)
    count_chart = [c for c in charts if c["title"] == "Movimentações por Tipo"][0]
    ds = count_chart["chart_data"]["data"]["datasets"][0]
    assert len(set(ds["backgroundColor"])) >= 4   # per-tipo colors
    vol_chart = [c for c in charts
                 if c["title"] == "Volume Declarado por Tipo (R$)"]
    assert vol_chart                             # 2+ priced tipos → drawn


def test_insiders_tx_rows_pills(vlmo_root):
    """The Movimentações table cargo/tipo cells are {text, pill} cells."""
    from webui.services.insiders import InsiderService, cargo_color
    svc = InsiderService()
    out = svc.transactions("TEST4")
    assert out["status"] == "ok"
    tbl = [s for s in out["sections"] if s.get("type") == "table"
           and s["title"].startswith("Movimentações de Insiders")][0]
    r0 = tbl["rows"][0]
    assert r0[1]["pill"] == cargo_color(r0[1]["text"])
    assert r0[2]["pill"]                      # tipo pill present


# ── 6. Proventos — IPE announcements cross-reference ─────────────────────────

_IPE_PROV_ROWS = [
    # (data_entrega, categoria, tipo, assunto, protocolo)
    ("2026-01-20", "Dividendos, Juros sobre o Capital Próprio e Outros",
     "Aviso aos Acionistas", "Aviso de dividendo 2026", "SECP1"),
    ("2025-04-15", "Dividendos, Juros sobre o Capital Próprio e Outros",
     "Aviso aos Acionistas", "Aviso de JCP 2025", "SECP2"),
    ("2026-02-01", "Assembleia", "AGO", "Ata AGO 2026", "SECP3"),  # NOT proventos
]


@pytest.fixture()
def ipe_root(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    cvm = tmp_path / "cvm"
    cvm.mkdir(parents=True, exist_ok=True)
    _bridge(tmp_path, [("PETR4", PETR)])
    c = sqlite3.connect(str(cvm / "ipe.db"))
    c.executescript(IPE_SCHEMA)
    for de, cat, tip, ass, prot in _IPE_PROV_ROWS:
        c.execute("""INSERT INTO eventos (cnpj, cd_cvm, nome, data_entrega,
                     data_referencia, categoria, tipo, especie, assunto,
                     tipo_apresentacao, versao, protocolo, link_download, ano_origem)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (PETR, "009512", "PETRÓLEO BRASILEIRO S.A. - PETROBRAS",
                   de, de, cat, tip, "", ass, "AP - Apresentação", 1, prot,
                   f"https://rad.cvm.gov.br/{prot}", de[:4]))
    c.commit()
    c.close()
    return tmp_path


def test_proventos_ipe_announcements_filter(ipe_root):
    """Only the proventos-family filings surface (the Assembleia row
    stays out); newest first; the bridge resolves PETR4 → CNPJ."""
    from webui.services.proventos import ProventosService
    svc = ProventosService()
    rows = svc._ipe_announcements("PETR4")
    assert len(rows) == 2
    assert rows[0]["data_entrega"] == "2026-01-20"
    assert all("Dividendos" in r["categoria"] for r in rows)


def test_proventos_ipe_section_shape(ipe_root):
    """The section: link cell (opens the CVM PDF) + assunto tooltip on
    the date + the explanatory note."""
    from webui.services.proventos import ProventosService
    svc = ProventosService()
    rows = svc._ipe_announcements("PETR4")
    sec = svc._ipe_section(rows)
    assert sec["type"] == "table"
    assert sec["title"] == "Anúncios de Proventos — CVM (2)"
    assert sec["columns"] == ["Data Entrega", "Categoria", "Tipo", "Assunto"]
    r0 = sec["rows"][0]
    assert r0[0]["link"] == "https://rad.cvm.gov.br/SECP1"
    assert r0[0]["tooltip"] == "Aviso de dividendo 2026"
    assert r0[0]["text"] == "20/01/2026"
    assert "CVM" in sec["note"]


def test_proventos_ipe_graceful_without_db(tmp_path, monkeypatch):
    """No ipe.db at all → [] (the section just doesn't render)."""
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    cvm = tmp_path / "cvm"
    cvm.mkdir(parents=True, exist_ok=True)
    _bridge(tmp_path, [("PETR4", PETR)])
    from webui.services.proventos import ProventosService
    assert ProventosService()._ipe_announcements("PETR4") == []


# ── 7. [v1.26.1 fix 1] The Acionistas Visão Geral dedup ─────────────────────

def test_sh_overview_dedup_snapshot_charts(monkeypatch):
    """[v1.26.1 fix1] The Visão Geral stops repeating the other subtabs
    ("Evolução do Free Float (%)" + "Evolução de Acionistas (PF/PJ/Inst.)"
    = the Free Float subtab; "Principais Acionistas" = the Posição
    Acionária subtab) and renders the CURRENT ownership snapshot instead:
    the controle × free float doughnut + the top-N concentration bar
    (quantities ÷ total emitido — NOT the double-countable % Total, and
    the FRE's own "Outros" aggregate row excluded from the tops)."""
    import webui.services.shareholders as shm

    # 2 periods (DESC) — evolution data EXISTS, the overview just doesn't
    # repeat it anymore.
    ff = {"status": "ok", "periods": [
        {"data_referencia": "2024-12-31", "pct_total_circulacao": 62.5,
         "pct_on_circulacao": 70.0, "pct_pn_circulacao": 55.0,
         "qtd_acionistas_pf": 900, "qtd_acionistas_pj": 80,
         "qtd_acionistas_inst": 20},
        {"data_referencia": "2023-12-31", "pct_total_circulacao": 61.0,
         "qtd_acionistas_pf": 800, "qtd_acionistas_pj": 70,
         "qtd_acionistas_inst": 10},
    ]}
    # 12 declared holders (qtd sums: top1 2.5bi, top5 7.8bi, top10 9.1bi of
    # the 10bi total) + the "Outros" aggregate row that must NOT count.
    qtds = [2_500_000_000, 2_000_000_000, 1_500_000_000, 1_000_000_000,
            800_000_000, 400_000_000, 300_000_000, 250_000_000,
            200_000_000, 150_000_000, 100_000_000, 50_000_000]
    holders = [
        {"acionista": f"HOLDER {i:02d}", "cpf_cnpj": "0", "tipo_pessoa": "PJ",
         "pct_on": None, "pct_pn": None, "pct_total": q / 100_000_000.0,
         "qtd_total": q, "controlador": i == 0}
        for i, q in enumerate(qtds)]
    holders.append({"acionista": "Outros", "cpf_cnpj": "", "tipo_pessoa": "-",
                    "pct_on": None, "pct_pn": None, "pct_total": 7.5,
                    "qtd_total": 750_000_000, "controlador": False})
    sh = {"status": "ok", "data_referencia": "2024-12-31",
          "shareholders": holders}
    eq = {"status": "ok", "periods": [
        {"data_fim_exerc": "2024-12-31",
         "accounts": {"2.03": {"valor_brl": 415_000_000_000.0}}}]}
    cap = {"status": "ok", "periods": [
        {"data_referencia": "2024-12-31", "tipo_capital": "Nominativo",
         "valor_capital": 300_000_000_000.0, "qtd_acoes_on": 4_000_000_000,
         "qtd_acoes_pn": 6_000_000_000, "qtd_acoes_total": 10_000_000_000,
         "data_aprovacao": None}]}

    monkeypatch.setattr(shm, "_fre_free_float", lambda **k: ff)
    monkeypatch.setattr(shm, "_fre_shareholders", lambda **k: sh)
    monkeypatch.setattr(shm, "_dfp_equity_structure", lambda **k: eq)
    monkeypatch.setattr(shm, "_fre_capital", lambda **k: cap)

    res = shm.ShareholdersService().overview("TEST4")
    assert res["status"] == "ok"
    titles = [s["title"] for s in res["sections"] if "title" in s]
    # The duplicates are GONE…
    assert "Evolução do Free Float (%)" not in titles
    assert "Evolução de Acionistas (PF/PJ/Inst.)" not in titles
    assert "Principais Acionistas" not in titles
    # …replaced by the current-snapshot charts, with the KPIs and the
    # Mercado|Patrimônio two-column still in place.
    assert "Estrutura de Propriedade — Atual" in titles
    assert "Concentração — Maiores Acionistas" in titles
    assert any(s["type"] == "two_column" for s in res["sections"])
    assert len(res["kpis"]) == 6

    # Doughnut: 62.5% free float × 37.5% rest.
    dough = next(s for s in res["sections"]
                 if s["title"] == "Estrutura de Propriedade — Atual")
    assert dough["chart_data"]["data"]["datasets"][0]["data"] == [62.5, 37.5]
    assert dough["chart_data"]["data"]["labels"] == [
        "Free Float", "Controle / Demais"]

    # Concentration: quantities ÷ 10 bi shares — Top 1/5/10 + the FF bar.
    conc = next(s for s in res["sections"]
                if s["title"] == "Concentração — Maiores Acionistas")
    ds = conc["chart_data"]["data"]
    assert ds["labels"] == ["Top 1", "Top 5", "Top 10", "Free Float"]
    assert ds["datasets"][0]["data"] == [25.0, 78.0, 91.0, 62.5]
    # The FF reference bar is teal, the tops amber.
    assert ds["datasets"][0]["backgroundColor"] == [
        "#f59e0b", "#f59e0b", "#f59e0b", "#0d9488"]


def test_sh_overview_snapshot_degrades_without_capital(monkeypatch):
    """[v1.26.1 fix1] Degradation: no capital social → no concentration
    bar (it needs the total shares); no declared % circulação → no
    doughnut — but the KPIs + the two-column block keep the tab alive
    (same policy as every other subtab: degrade, never crash)."""
    import webui.services.shareholders as shm

    ff = {"status": "ok", "periods": [
        {"data_referencia": "2024-12-31", "pct_total_circulacao": None,
         "pct_on_circulacao": None, "pct_pn_circulacao": None,
         "qtd_acionistas_pf": 10, "qtd_acionistas_pj": 2,
         "qtd_acionistas_inst": None}]}
    sh = {"status": "ok", "data_referencia": "2024-12-31", "shareholders": [
        {"acionista": "H", "cpf_cnpj": "", "tipo_pessoa": "PF",
         "pct_on": None, "pct_pn": None, "pct_total": 5.0,
         "qtd_total": 100, "controlador": True}]}
    err = {"status": "error", "error": "no db"}
    monkeypatch.setattr(shm, "_fre_free_float", lambda **k: ff)
    monkeypatch.setattr(shm, "_fre_shareholders", lambda **k: sh)
    monkeypatch.setattr(shm, "_dfp_equity_structure", lambda **k: err)
    monkeypatch.setattr(shm, "_fre_capital", lambda **k: err)

    res = shm.ShareholdersService().overview("TEST4")
    assert res["status"] == "ok"
    titles = [s["title"] for s in res["sections"] if "title" in s]
    assert "Estrutura de Propriedade — Atual" not in titles
    assert "Concentração — Maiores Acionistas" not in titles
    assert any(s["type"] == "two_column" for s in res["sections"])
