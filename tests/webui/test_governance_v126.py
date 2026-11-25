"""tests/webui/test_governance_v126.py — the v1.26 Governança + IPE suite.

[v1.26 fix 1] TWO tabs, TWO purposes (the user's verdict: "both
provide info, but they are not supposed to be together, different
purpose"): the 11th tab Governança (CGVN — the self-assessment) and
the 12th tab Informações Periódicas (IPE — the event index, split
into its own tab). HAND-COMPUTED values, fixtures that mirror the
REAL data shapes (verified against the user's synced DBs via the
v1.26 inspection dump):

  1. IPE browse() — the faceted explorer's engine: the CASCADE (tipo=AGO
     narrows the categoria facet to Assembleia only), the __none__
     sentinel (72K of 502K real rows carry no tipo), EXACT match
     ("Assembleia" must not leak "Assembleia de Credores" — query() is
     LIKE-based, browse() must not be), pagination math, keyword,
     versao>1 passthrough (badged, never deduped) — and the ANOS
     ORDERING ([v1.26 fix 1] the user-reported bug: "ano is completely
     out of order… seems sorted by the number of items" — the facet
     must be CHRONOLOGICAL, newest first, never count-ordered).
  2. CGVN filings() — the per-exercício history: the EXERCÍCIO label
     comes from Data_Fim_Exercicio_Social (ref 2026-12-31 → exercício
     2025 — the CGVN convention ref = exercício + 1; the latest
     exercício is always filing-year-minus-1: the exercício-2026
     protocolos arrive with the 2027 ZIP), the score math per filing.
  3. GovernanceService.overview — KPIs (score % Sim of TOTAL, the
     reference dashboard's 88,89% = 48/54 convention), nível thresholds
     (Alto ≥ 80 / Médio ≥ 50 / Baixo), the four-bucket donut (the
     static dropped "Não se Aplica"), the evolution chart labels,
     degradation when CGVN has nothing for the ticker.
  4. GovernanceService.practices — default = latest filing, filters
     (capítulo/situação/busca) applied server-side, unknown data_ref
     falls back to latest (a stale select must not 404 the pane).
  5. IpeService.events — chips + filters passthrough, the not_synced
     degradation naming the ipe source (the SPLIT: IpeService, not
     GovernanceService).
  6. HTTP — the two dedicated routes (/governance/practices +
     /ipe/events) + the generic governance:overview section + the TWO
     tab fragments (Governança = 2 panes, NO Informações Periódicas;
     IPE = 1 pane) + both page routes + the unknown-tab 404 + the OLD
     /governance/events route being gone.

Run:  python -m pytest tests/webui/test_governance_v126.py -v
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_sources.cvm.ipe.catalog import SCHEMA_SQL as IPE_SCHEMA  # noqa: E402
from data_sources.cvm.cgvn.catalog import SCHEMA_SQL as CGVN_SCHEMA  # noqa: E402

PETR = "33000167000101"
TEST = "11222333000181"

# ── the fixture world (hand-computed) ────────────────────────────────────────
# IPE/PETR — 10 rows:
#   Assembleia ×5: AGO/Ata ×3 (2024-03-15, 2023-03-15, 2022-03-15),
#                  AGE/Edital de Convocação ×2 (2024-08-10, 2023-08-10)
#   Fato Relevante ×3: tipo/espécie/assunto ALL empty (2024-04-08,
#                  2023-04-08, 2022-04-08) — the 31%-empty-assunto case
#   Comunicado ao Mercado ×2: tipo "Outros Comunicados Não Considerados
#                  Fatos Relevantes", assunto "Acordo Logum" v2 2026-11-05
#                  (the reapresentação) + "Comunicado geral" v1 2026-11-01
_IPE_ROWS = [
    # (de, cat, tipo, especie, assunto, versao, protocolo, ano)
    ("2024-03-15", "Assembleia", "AGO", "Ata", "Ata AGO 2024", 1, "P1", 2024),
    ("2023-03-15", "Assembleia", "AGO", "Ata", "Ata AGO 2023", 1, "P2", 2023),
    ("2022-03-15", "Assembleia", "AGO", "Ata", "Ata AGO 2022", 1, "P3", 2022),
    ("2024-08-10", "Assembleia", "AGE", "Edital de Convocação", "Edital AGE 2024", 1, "P4", 2024),
    ("2023-08-10", "Assembleia", "AGE", "Edital de Convocação", "Edital AGE 2023", 1, "P5", 2023),
    ("2024-04-08", "Fato Relevante", "", "", "", 1, "P6", 2024),
    ("2023-04-08", "Fato Relevante", "", "", "", 1, "P7", 2023),
    ("2022-04-08", "Fato Relevante", "", "", "", 1, "P8", 2022),
    ("2026-11-05", "Comunicado ao Mercado", "Outros Comunicados Não Considerados Fatos Relevantes",
     "", "Acordo Logum", 2, "P9", 2026),
    ("2026-11-01", "Comunicado ao Mercado", "Outros Comunicados Não Considerados Fatos Relevantes",
     "", "Comunicado geral", 1, "P10", 2026),
]

# CGVN/PETR — 2 filings. Latest (ref 2026-12-31, exercício 2025):
#   6 practices: 4 Sim, 1 Não, 1 Não se Aplica → score 4/6 = 0.6667
# Previous (ref 2025-12-31, exercício 2024): 3 Sim, 2 Não, 1 Parcialmente
#   → score 3/6 = 0.5
_CGVN_FILINGS = [
    {"ref": "2026-12-31", "entrega": "2026-06-30", "ex_ini": "2025-01-01",
     "ex_fim": "2025-12-31",
     "practices": [("1.1.1", "Acionistas", "Estrutura Acionária", "Capital só em ações ordinárias.", "Sim", ""),
                   ("1.2.1", "Acionistas", "Assembleia Geral", "Assembleia comunica a condução.", "Sim", ""),
                   ("2.1.1", "Conselho de Administração", "Composição", "Mandato ≤ 2 anos.", "Sim", ""),
                   ("2.2.1", "Conselho de Administração", "Composição", "Conselheiros independentes.", "Sim", ""),
                   ("1.3.1", "Acionistas", "Estrutura Acionária", "Tag along 100%.", "Não",
                    "Capital dividido em ON e PN conforme Lei 9.478/97."),
                   ("3.1.1", "Órgãos de Fiscalização e Controle", "Conselho Fiscal",
                    "Voto múltiplo não cumulativo.", "Não se Aplica", "Não aplicável à SEM.")],
     },
    {"ref": "2025-12-31", "entrega": "2025-07-04", "ex_ini": "2024-01-01",
     "ex_fim": "2024-12-31",
     "practices": [("1.1.1", "Acionistas", "Estrutura Acionária", "Capital só em ações ordinárias.", "Sim", ""),
                   ("1.2.1", "Acionistas", "Assembleia Geral", "Assembleia comunica a condução.", "Sim", ""),
                   ("2.1.1", "Conselho de Administração", "Composição", "Mandato ≤ 2 anos.", "Sim", ""),
                   ("1.3.1", "Acionistas", "Estrutura Acionária", "Tag along 100%.", "Não", "ON e PN."),
                   ("2.2.1", "Conselho de Administração", "Composição", "Conselheiros independentes.", "Não", "—"),
                   ("3.1.1", "Órgãos de Fiscalização e Controle", "Conselho Fiscal",
                    "Voto múltiplo não cumulativo.", "Parcialmente", "Em revisão.")],
     },
]


@pytest.fixture()
def memory_root(tmp_path, monkeypatch):
    """Isolated memory_root (the v123/v124 recipe) with synthetic
    ipe.db + cgvn.db + bridge.db — never touches the real memory_db."""
    from core.config import cfg
    cvm = tmp_path / "cvm"
    cvm.mkdir(parents=True)
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)

    # bridge.db — ticker_map only (the resolution path the engines hit
    # after fca.db misses; keeps the tests network-free).
    b = sqlite3.connect(str(cvm / "bridge.db"))
    b.execute("""CREATE TABLE IF NOT EXISTS ticker_map (
        ticker TEXT PRIMARY KEY, issuing TEXT, cd_cvm TEXT, trading_name TEXT,
        cnpj TEXT, denom_social TEXT, denom_comerc TEXT, sit TEXT,
        setor_ativ TEXT, tp_merc TEXT, synced_at TEXT)""")
    b.execute("INSERT INTO ticker_map (ticker, cnpj) VALUES ('PETR4', ?)", (PETR,))
    b.execute("INSERT INTO ticker_map (ticker, cnpj) VALUES ('TEST4', ?)", (TEST,))
    b.commit(); b.close()

    # ipe.db — the 10-row PETR world + 2 rows for TEST4 (no CGVN).
    c = sqlite3.connect(str(cvm / "ipe.db"))
    c.executescript(IPE_SCHEMA)
    for de, cat, tip, esp, ass, ver, prot, ano in _IPE_ROWS:
        c.execute("""INSERT INTO eventos (cnpj, cd_cvm, nome, data_entrega,
                     data_referencia, categoria, tipo, especie, assunto,
                     tipo_apresentacao, versao, protocolo, link_download, ano_origem)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (PETR, "009512", "PETRÓLEO BRASILEIRO S.A. - PETROBRAS",
                   de, de, cat, tip, esp, ass, "AP - Apresentação", ver, prot,
                   f"https://rad.cvm.gov.br/{prot}", ano))
    for i, ano in enumerate((2025, 2024)):
        c.execute("""INSERT INTO eventos (cnpj, cd_cvm, nome, data_entrega,
                     data_referencia, categoria, tipo, especie, assunto,
                     tipo_apresentacao, versao, protocolo, link_download, ano_origem)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (TEST, "01234", "TESTE INDUSTRIAL S.A.", f"{ano}-04-20",
                   f"{ano}-04-20", "Assembleia", "AGO", "Ata", f"Ata AGO {ano}",
                   "AP - Apresentação", 1, f"T{i}", f"https://rad.cvm.gov.br/T{i}", ano))
    c.commit(); c.close()

    # cgvn.db — 2 PETR filings (TEST4 has none).
    g = sqlite3.connect(str(cvm / "cgvn.db"))
    g.executescript(CGVN_SCHEMA)
    for i, f in enumerate(_CGVN_FILINGS):
        g.execute("""INSERT INTO cgvn_documents (Categoria, CNPJ_Companhia,
                     Codigo_CVM, Data_Entrega, Data_Fim_Exercicio_Social,
                     Data_Inicio_Exercicio_Social, Data_Referencia,
                     ID_Documento, Link_Download, Nome_Empresarial, Versao,
                     Motivo_Reapresentacao)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                  ("Código de Governança", PETR, "009512", f["entrega"],
                   f["ex_fim"], f["ex_ini"], f["ref"], 100 + i,
                   f"https://rad.cvm.gov.br/doc{i}",
                   "PETRÓLEO BRASILEIRO S.A. - PETROBRAS", 1, ""))
        for iid, cap, prin, prat, adot, expl in f["practices"]:
            g.execute("""INSERT INTO cgvn_practices (CNPJ_Companhia,
                         Data_Referencia, ID_Documento, Nome_Empresarial,
                         Versao, ID_Item, Pratica_Recomendada, Pratica_Adotada,
                         Capitulo, Principio, Explicacao)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      (PETR, f["ref"], 100 + i,
                       "PETRÓLEO BRASILEIRO S.A. - PETROBRAS", 1,
                       iid, prat, adot, cap, prin, expl))
    g.commit(); g.close()
    return tmp_path


# ── 1. ipe.browse() — the faceted explorer engine ───────────────────────────

def test_browse_default_facets(memory_root):
    from data_sources.cvm.ipe import query_engine as ipe
    r = ipe.browse(company="PETR4")
    assert r["status"] == "ok" and r["total"] == 10 and r["pages"] == 1
    # order by n DESC, v ASC
    assert [(o["v"], o["n"]) for o in r["facets"]["categorias"]] == [
        ("Assembleia", 5), ("Fato Relevante", 3), ("Comunicado ao Mercado", 2)]
    # empty tipo ships as "" (the client labels it "— sem tipo —")
    tipos = {o["v"]: o["n"] for o in r["facets"]["tipos"]}
    assert tipos[""] == 3 and tipos["AGO"] == 3 and tipos["AGE"] == 2
    anos = {o["v"]: o["n"] for o in r["facets"]["anos"]}
    assert anos == {"2026": 2, "2024": 3, "2023": 3, "2022": 2}
    # [v1.26 fix 1] THE USER-REPORTED BUG — the Ano select must be
    # CHRONOLOGICAL (newest first), NEVER count-ordered. The fixture
    # discriminates: by-count would put 2024/2023 (3 events) before
    # 2026 (2); chronological is 2026 → 2022.
    assert [o["v"] for o in r["facets"]["anos"]] == [
        "2026", "2024", "2023", "2022"]


def test_browse_anos_ordering_under_filter(memory_root):
    """[v1.26 fix 1] The chronological order survives a narrowed facet:
    categoria=Assembleia leaves 2024:2, 2023:2, 2022:1 — a count-first
    sort would tie 2024/2023 (n=2) before 2022; the year-descending
    order must hold regardless of the counts."""
    from data_sources.cvm.ipe import query_engine as ipe
    r = ipe.browse(company="PETR4", categoria="Assembleia")
    assert [(o["v"], o["n"]) for o in r["facets"]["anos"]] == [
        ("2024", 2), ("2023", 2), ("2022", 1)]
    # [v1.26 fix 1] THE USER-REPORTED BUG — the Ano select must be
    # CHRONOLOGICAL (newest first), NEVER count-ordered. The fixture is
    # built to discriminate: by-count would put 2024/2023 (3 events)
    # before 2026 (2); chronological is 2026 → 2022.
    assert [o["v"] for o in r["facets"]["anos"]] == [
        "2026", "2024", "2023", "2022"]


def test_browse_anos_ordering_under_filter(memory_root):
    """[v1.26 fix 1] The chronological order survives a narrowed facet:
    with categoria=Assembleia the counts change (2024:2, 2023:2, 2022:1)
    but the order must still be year-descending, not count-descending
    (count-desc would tie 2024/2023 then put 2022 last — same here, so
    pin the strict sequence AND the counts)."""
    from data_sources.cvm.ipe import query_engine as ipe
    r = ipe.browse(company="PETR4", categoria="Assembleia")
    assert [(o["v"], o["n"]) for o in r["facets"]["anos"]] == [
        ("2024", 2), ("2023", 2), ("2022", 1)]


def test_browse_cascade_and_exact_match(memory_root):
    from data_sources.cvm.ipe import query_engine as ipe
    r = ipe.browse(company="PETR4", tipo="AGO")
    assert r["total"] == 3
    # THE CASCADE: the categoria facet narrows to Assembleia only
    assert [(o["v"], o["n"]) for o in r["facets"]["categorias"]] == [("Assembleia", 3)]
    assert [(o["v"], o["n"]) for o in r["facets"]["especies"]] == [("Ata", 3)]
    # EXACT match, not LIKE: "Assembleia" must not be needed here, but a
    # categoria=Assembleia filter must not leak other categorias either.
    r2 = ipe.browse(company="PETR4", categoria="Assembleia")
    assert r2["total"] == 5
    assert all(e["categoria"] == "Assembleia" for e in r2["events"])


def test_browse_sentinel_pagination_keyword_versao(memory_root):
    from data_sources.cvm.ipe import query_engine as ipe
    # the sentinel selects the EMPTY value
    r = ipe.browse(company="PETR4", tipo="__none__")
    assert r["total"] == 3
    assert all(e["tipo"] == "" for e in r["events"])
    # pagination: 10 rows, 3 per page → 4 pages; page 2 = rows 4-6
    r2 = ipe.browse(company="PETR4", page=2, per_page=3)
    assert r2["pages"] == 4 and len(r2["events"]) == 3
    # per_page capped at 100, page floored at 1
    r3 = ipe.browse(company="PETR4", page=0, per_page=999)
    assert r3["page"] == 1 and r3["per_page"] == 100
    # keyword + the reapresentação badge source
    r4 = ipe.browse(company="PETR4", keyword="logum")
    assert r4["total"] == 1 and r4["events"][0]["versao"] == 2
    assert "Logum" in r4["events"][0]["assunto"]
    # unknown company → not_found with a PT-BR message
    r5 = ipe.browse(company="ZZZZ4")
    assert r5["status"] == "not_found" and "não encontrada" in r5["message"]


# ── 2. cgvn.filings() — the per-exercício history ───────────────────────────

def test_cgvn_filings_exercicio_and_scores(memory_root):
    from data_sources.cvm.cgvn import query_engine as cgvn
    r = cgvn.filings(company="PETR4")
    assert r["status"] == "ok" and r["count"] == 2
    latest, prev = r["filings"]
    # ref 2026-12-31 → exercício 2025 (Data_Fim_Exercicio_Social), not 2026
    assert latest["data_referencia"] == "2026-12-31"
    assert latest["exercicio"] == 2025
    assert latest["data_entrega"] == "2026-06-30"
    assert latest["sim"] == 4 and latest["nao"] == 1
    assert latest["nao_se_aplica"] == 1 and latest["parcialmente"] == 0
    assert latest["score_pct"] == pytest.approx(4 / 6, abs=1e-4)
    assert prev["exercicio"] == 2024 and prev["score_pct"] == pytest.approx(0.5)
    # [v1.26 fix 1] the "missing exercício 2026" question — the CVM
    # convention is ref = exercício + 1: the exercício-2026 protocolos
    # only exist in the 2027 ZIP. A DB whose MAX(Data_Referencia) year
    # equals the current year is ALREADY up to date.
    assert max(f["data_referencia"][:4] for f in r["filings"]) == "2026"
    assert max(f["exercicio"] for f in r["filings"]) == 2025
    # [v1.26 fix 1] the "missing exercício 2026" question — the CVM
    # convention is ref = exercício + 1: the exercício-2026 protocolos
    # only exist in the 2027 ZIP. A DB whose MAX(Data_Referencia) year
    # equals the current year is ALREADY up to date.
    assert max(f["data_referencia"][:4] for f in r["filings"]) == "2026"
    assert max(f["exercicio"] for f in r["filings"]) == 2025
    # TEST4 never declared CGVN
    assert cgvn.filings(company="TEST4")["status"] == "not_found"


# ── 3. GovernanceService.overview ───────────────────────────────────────────

def test_overview_kpis_donut_evolution(memory_root):
    from webui.services.governance import GovernanceService
    d = GovernanceService().overview("PETR4")
    assert d["status"] == "ok" and "_error" not in d
    kpis = {k["label"]: k["value"] for k in d["kpis"]}
    assert kpis["Score de Governança"] == "66,67%"      # 4/6 — % Sim of TOTAL
    assert kpis["Práticas"] == "6"
    assert kpis["Nível de Conformidade"] == "Médio"     # 66.67% < 80%
    assert kpis["Exercício"] == "2025"
    donut = d["sections"][0]["chart_data"]
    assert donut["type"] == "doughnut"
    assert donut["data"]["labels"] == ["Sim", "Parcialmente", "Não", "Não se Aplica"]
    assert donut["data"]["datasets"][0]["data"] == [4, 0, 1, 1]
    # evolution: oldest → newest, % Sim per exercício
    evo = next(s for s in d["sections"] if s["title"] == "Evolução do Score")
    assert evo["chart_data"]["data"]["labels"] == ["2024", "2025"]
    assert evo["chart_data"]["data"]["datasets"][0]["data"] == [50.0, pytest.approx(66.67)]
    # the protocolos ledger
    tbl = next(s for s in d["sections"] if s["type"] == "table")
    assert tbl["rows"][0] == ["2025", "30/06/2026", "4/6", "66,67%"]


def test_overview_nivel_thresholds():
    from webui.services.governance import _compliance_label
    assert _compliance_label(0.8889) == "Alto"    # PETR4 real: 88,89%
    assert _compliance_label(0.80) == "Alto"
    assert _compliance_label(0.7999) == "Médio"
    assert _compliance_label(0.50) == "Médio"
    assert _compliance_label(0.4999) == "Baixo"


def test_overview_degradation_no_cgvn(memory_root):
    from webui.services.governance import GovernanceService
    d = GovernanceService().overview("TEST4")
    assert "_error" in d and "CGVN" in d["_error"]
    assert "Sincronização" in d["_error"]          # the sync hint


# ── 4. GovernanceService.practices ──────────────────────────────────────────

def test_practices_default_latest_and_filters(memory_root):
    from webui.services.governance import GovernanceService
    svc = GovernanceService()
    d = svc.practices("PETR4")
    assert d["status"] == "ok"
    assert d["data_referencia"] == "2026-12-31"    # latest by default
    assert d["exercicio"] == 2025
    assert len(d["rows"]) == 6
    assert [f["exercicio"] for f in d["filings"]] == [2025, 2024]
    assert d["capitulos"] == ["Acionistas", "Conselho de Administração",
                              "Órgãos de Fiscalização e Controle"]
    # situação filter
    d2 = svc.practices("PETR4", adotada="Não")
    assert [r["id_item"] for r in d2["rows"]] == ["1.3.1"]
    # capítulo filter
    d3 = svc.practices("PETR4", capitulo="Acionistas")
    assert len(d3["rows"]) == 3
    # busca hits prática text + explicação
    d4 = svc.practices("PETR4", q="tag along")
    assert len(d4["rows"]) == 1 and d4["rows"][0]["adotada"] == "Não"
    d5 = svc.practices("PETR4", q="Lei 9.478")
    assert len(d5["rows"]) == 1     # the explicação match
    # unknown data_ref falls back to latest (a stale select ≠ a 404)
    d6 = svc.practices("PETR4", data_ref="1999-12-31")
    assert d6["data_referencia"] == "2026-12-31"
    # an OLDER filing loads with its own rows
    d7 = svc.practices("PETR4", data_ref="2025-12-31")
    assert d7["exercicio"] == 2024 and len(d7["rows"]) == 6


# ── 5. IpeService.events + degradation (its own tab since v1.26 fix 1) ─────

def test_events_chips_and_filters(memory_root):
    from webui.services.ipe import IpeService
    d = IpeService().events("PETR4", categoria="Assembleia",
                            tipo="AGO", page=1, per_page=2)
    assert d["status"] == "ok" and d["total"] == 3
    assert d["ticker"] == "PETR4"
    assert d["filters"]["categoria"] == "Assembleia"
    # chips passthrough (the client renders only those present in facets)
    labels = [c["label"] for c in d["chips"]]
    assert "AGO" in labels and "AGE" in labels
    assert any(c["field"] == "categoria" and c["value"] == "Assembleia"
               for c in d["chips"])
    # TEST4: IPE works even without CGVN (the split — independent sources)
    d2 = IpeService().events("TEST4")
    assert d2["status"] == "ok" and d2["total"] == 2


def test_events_degradation_not_synced(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "cvm").mkdir(exist_ok=True)
    # no ipe.db at all → FileNotFoundError → _error naming the source
    from webui.services.ipe import IpeService
    d = IpeService().events("PETR4")
    assert "_error" in d and "ipe" in d["_error"]


# ── 6. HTTP surface ──────────────────────────────────────────────────────────

@pytest.fixture()
def client(memory_root):
    import webui.app as m
    from fastapi.testclient import TestClient
    return TestClient(m.create_app(), base_url="http://127.0.0.1:8000")


def test_http_governance_sections_overview(client):
    r = client.get("/api/webui/company/PETR4/sections/governance:overview")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert len(body["kpis"]) == 6
    assert [s["type"] for s in body["sections"]] == [
        "chart", "chart", "chart", "table"]


def test_http_governance_practices_and_ipe_events(client):
    r = client.get("/api/webui/company/PETR4/governance/practices?adotada=Não")
    assert r.status_code == 200
    assert r.json()["rows"][0]["id_item"] == "1.3.1"

    # [v1.26 fix 1] the IPE route moved to /ipe/events (its own tab)
    r2 = client.get("/api/webui/company/PETR4/ipe/events",
                    params={"tipo": "AGO", "page": 1, "per_page": 2})
    assert r2.status_code == 200
    body = r2.json()
    assert body["total"] == 3 and body["per_page"] == 2
    assert body["facets"]["categorias"] == [{"v": "Assembleia", "n": 3}]
    # the anos facet ships CHRONOLOGICAL over HTTP too — the fix 1
    # regression (fixture: AGO rows are 2024/2023/2022)
    assert [o["v"] for o in body["facets"]["anos"]] == ["2024", "2023", "2022"]

    # the OLD route is gone (a stale bookmark must not half-work)
    r_old = client.get("/api/webui/company/PETR4/governance/events")
    assert r_old.status_code == 404

    # per_page validation (le=100)
    r3 = client.get("/api/webui/company/PETR4/ipe/events?per_page=500")
    assert r3.status_code == 422


def test_http_tab_fragments_and_pages(client):
    # [v1.26 fix 1] Governança fragment — CGVN ONLY: 2 panes, no IPE
    r = client.get("/api/webui/company/PETR4/tab/governance")
    assert r.status_code == 200
    html = r.text
    for pane in ("tab-gov-overview", "tab-gov-practices"):
        assert pane in html
    assert "tab-gov-events" not in html
    assert "Informações Periódicas" not in html

    # the IPE fragment — its OWN tab, ONE pane (no subtab nav)
    r_i = client.get("/api/webui/company/PETR4/tab/ipe")
    assert r_i.status_code == 200
    assert "tab-ipe-events" in r_i.text
    assert "subtab-nav" not in r_i.text

    # both deep-linkable page routes
    assert client.get("/webui/company/PETR4/governance",
                      follow_redirects=False).status_code == 200
    assert client.get("/webui/company/PETR4/ipe",
                      follow_redirects=False).status_code == 200
    # unknown tab still 404 PT-BR
    r3 = client.get("/api/webui/company/PETR4/tab/nope")
    assert r3.status_code == 404 and "não implementada" in r3.text
