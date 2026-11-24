"""tests/webui/test_nota_import.py — the nota-import regression suite.

[v1.22.2] "An import is just many txs born together" — and the money
engine never takes unverified numbers. Every value here is
HAND-COMPUTED from synthetic notas (fictional client/broker/CNPJ — no
real PDF ships in the repo); if a refactor changes any number, the
test fails before the user's portfolio does.

Coverage:
  1.  XP layout: tickers mid-spec, obs strip (@/#/D), fees total,
      client (name line + "CPF/CNPJ"), Conta XP
  2.  Fee allocation: pro-rata by value, cent-exact Σ == nota total
      (largest-remainder apportionment, hand-computed to the cent)
  3.  B3 model: specs WITHOUT ticker → needs_mapping + suggestions,
      client line "<código> NOME <cpf>"
  4.  BTG layout: ticker-first spec, IRRF row parsed (0,005%)
  5.  br_to_float strictness ("1.234"=1234 · "8,83"=8,83 · "12.5"=None)
  6.  Unsupported market (OPCOES) excluded + warned; qty×price≠value
      line refused + warned
  7.  Fractional: KLBN4F → ticker_base KLBN4 (merge option)
  8.  Not-a-nota → clear PT-BR error (never an empty success)
  9.  import_nota: bulk single save, note tag "NC …", dedup key
      (cnpj+nº+pregão) — the SAME nota in TWO layouts is a duplicate
  10. All-or-nothing: one bad trade row → per-row PT-BR errors, store
      untouched (count before == count after)
  11. undo_import: removes exactly the nota's txs; a manually-deleted
      tx shows in the alive counter; undo of unknown id → 404 shape
  12. HTTP surface: preview 400 on garbage b64, CSRF 403 on cross-site
      commit, GET /ir scope validation

Run:  python -m pytest tests/webui/test_nota_import.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import webui.services.portfolio as pfmod            # noqa: E402
from webui.services.portfolio import PortfolioService  # noqa: E402
from webui.services.nota_import import (             # noqa: E402
    br_to_float, parse_nota_text)


# ── fixtures (synthetic notas — fictional people, real grammar) ──────────────

XP_NOTA = """
Nota de Negociação
Data pregão Nº Nota
05/03/2026 987654321
CONSUMIDOR TESTE DA SILVA
CPF/CNPJ 123.456.789-00
Rua Teste, 100 - Apto 1 Conta XP 555777
Belo Horizonte - MG
Negociações
1-BOVESPA C VISTA HAPVIDA HAPV3 ON NM @ 200 8,83 1.766,00 D
1-BOVESPA C VISTA KLABIN S/A KLBN4 PN N2 @ 900 3,62 3.258,00 D
1-BOVESPA C FRACIONARIO KLABIN S/A KLBN4F PN N2 # 80 3,63 290,40 D
1-BOVESPA C VISTA PETROBRAS PETR4 PN N2 D 100 38,50 3.850,00 D
Resumo dos Negócios
Compras à vista 9.164,40
Valor das operações 9.164,40
Total Corretagem / Despesas 50,00 D
CORRETORA TESTE CCTVM S.A.
CNPJ: 11.222.333/0001-44
"""

B3_NOTA = """
NOTA DE NEGOCIAÇÃO
Nr. nota Folha Data pregão
112233445 1 25/03/2026
CORRETORA TESTE CTVM S.A.
Avenida Teste, 10 - Centro
C.N.P.J: 11.222.333/0001-44
Cliente C.P.F./C.N.P.J/C.V.M./C.O.B.
555888 CONSUMIDOR TESTE 123.456.789-00
Negociações
1-BOVESPA C VISTA HAPVIDA ON NM @ 100 10,05 1.005,00 D
1-BOVESPA C VISTA MINERVA ON NM @ 1000 4,16 4.160,00 D
1-BOVESPA V VISTA RANDON PART PN N1 @ 100 5,02 502,00 C
Total Custos / Despesas 23,08 D
Valor das operações 5.667,00
I.R.R.F. s/ operações, base R$0,00 0,00
"""

BTG_NOTA = """
NOTA DE CORRETAGEM
Nr. nota Folha Data pregão
29000111 1 11/02/2026
BTG Pactual CTVM S.A.
Avenida Teste, 20 - Andar
C.N.P.J: 44.555.666/0001-77
Cliente C.P.F./C.N.P.J/C.V.M./C.O.B.
009988 CONSUMIDORA TESTE 987.654.321-00
1-BOVESPA V VISTA AMAR3 ON 30000 0,93 27.900,00 C
Total corretagem / Despesas 9,94 D
Valor das operações 27.900,00
I.R.R.F. s/ operações, base R$ 27.900,00 1,40
Líquido para 13/02/2026 27.890,44 C
"""


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    monkeypatch.setattr(pfmod, "_quotes_for",
                        lambda tickers: {"status": "ok", "session_date":
                                         "2026-11-21", "symbols": []})
    s = PortfolioService()
    monkeypatch.setattr(s, "_spawn_meta_refresh", lambda ticker: None)
    return s


def _seed(svc, name="Teste"):
    u = svc.create_user({"name": name})
    a = svc.create_account({"user_id": u["user"]["id"], "name": "Principal",
                            "broker": "XP"})
    return u["user"]["id"], a["account"]["id"]


# ── 1. XP layout ─────────────────────────────────────────────────────────────

def test_xp_layout_parses():
    out = parse_nota_text(XP_NOTA)
    assert out["ok"], out
    assert out["nota"] == "987654321"
    assert out["pregao"] == "2026-03-05"
    assert out["broker_cnpj"] == "11.222.333/0001-44"
    assert "CORRETORA TESTE" in out["broker"]
    assert out["client_name"] == "CONSUMIDOR TESTE DA SILVA"
    assert out["client_cpf"] == "123.456.789-00"
    assert out["account_code"] == "555777"
    assert out["fees_total"] == 50.0
    assert len(out["trades"]) == 4
    assert out["needs_mapping"] == {}

    by_spec = {t["spec"]: t for t in out["trades"]}
    xp = by_spec["HAPVIDA HAPV3 ON NM"]
    assert (xp["ticker"], xp["side"], xp["qty"], xp["price"]) == \
        ("HAPV3", "buy", 200.0, 8.83)
    assert xp["day"] is False and xp["obs"] == "@"
    # the 'D' obs is a DAY-TRADE marker, not part of the spec
    petr = by_spec["PETROBRAS PETR4 PN N2"]
    assert petr["day"] is True and petr["ticker"] == "PETR4"
    # fractional lot carries the F ticker + the merge base
    frac = by_spec["KLABIN S/A KLBN4F PN N2"]
    assert frac["ticker"] == "KLBN4F" and frac["ticker_base"] == "KLBN4"
    assert frac["fractional"] is True


# ── 2. fee allocation: hand-computed largest-remainder ───────────────────────

def test_fee_allocation_exact():
    out = parse_nota_text(XP_NOTA)
    assert out["ok"]
    # R$ 50,00 over values 1.766,00 / 3.258,00 / 290,40 / 3.850,00:
    #   HAPV3  5000×1766.0/9164.4  = 963,56… → 963 cents → 9,63
    #   KLBN4  5000×3258.0/9164.4  = 1777,79…→ 1777     → 17,77 (+1) = 17,78
    #   KLBN4F 5000×290.4/9164.4   = 158,47… → 158      → 1,58
    #   PETR4  5000×3850.0/9164.4  = 2100,17…→ 2100 (+1)          = 21,01
    #   Σ = 9,63 + 17,78 + 1,58 + 21,01 = 50,00 (cent-exact)
    want = {"HAPVIDA HAPV3 ON NM": 9.63, "KLABIN S/A KLBN4 PN N2": 17.78,
            "KLABIN S/A KLBN4F PN N2": 1.58, "PETROBRAS PETR4 PN N2": 21.01}
    got = {t["spec"]: t["fees"] for t in out["trades"]}
    assert got == want, got
    assert round(sum(got.values()), 2) == 50.0


# ── 3. B3 model: no ticker in the spec ───────────────────────────────────────

def test_b3_model_needs_mapping_and_suggestions():
    out = parse_nota_text(B3_NOTA)
    assert out["ok"], out
    assert out["nota"] == "112233445" and out["pregao"] == "2026-03-25"
    assert out["client_name"] == "CONSUMIDOR TESTE"
    assert out["account_code"] == "555888"
    nm = out["needs_mapping"]
    assert len(nm) == 3
    assert nm["VISTA|HAPVIDA ON NM"]["suggest"] == "HAPV3"
    assert nm["VISTA|MINERVA ON NM"]["suggest"] == "BEEF3"
    assert nm["VISTA|RANDON PART PN N1"]["suggest"] == "RAPP4"
    # every trade is unmapped and flagged for the UI
    assert all(t["ticker"] is None for t in out["trades"])
    # the sell is still a sell
    assert [t["side"] for t in out["trades"]] == ["buy", "buy", "sell"]


# ── 4. BTG layout: ticker first + IRRF ───────────────────────────────────────

def test_btg_layout_ticker_first_and_irrf():
    out = parse_nota_text(BTG_NOTA)
    assert out["ok"], out
    assert out["nota"] == "29000111" and out["pregao"] == "2026-02-11"
    assert "Pactual" in out["broker"] and out["broker_short"] == "BTG Pactual"
    assert out["broker_cnpj"] == "44.555.666/0001-77"
    assert out["irrf"] == 1.40
    assert out["trades"][0]["ticker"] == "AMAR3"
    assert out["trades"][0]["side"] == "sell"
    # the IRRF warning surfaces (informational — never booked as fees)
    assert any("IRRF" in w for w in out["warnings"])
    assert out["trades"][0]["fees"] == 9.94     # single trade → full share


# ── 5. PT-BR number strictness ───────────────────────────────────────────────

def test_br_to_float():
    assert br_to_float("1.766,00") == 1766.0
    assert br_to_float("200") == 200.0
    assert br_to_float("8,83") == 8.83
    assert br_to_float("1.234") == 1234.0       # thousands, never 1.234
    assert br_to_float("27.900,00") == 27900.0
    assert br_to_float("12.5") is None          # not a PT-BR number
    assert br_to_float("abc") is None
    assert br_to_float("") is None


# ── 6. unsupported markets & broken lines ────────────────────────────────────

def test_unsupported_market_and_bad_line():
    txt = XP_NOTA + ("1-BOVESPA C OPCOES PETRA171 ON COM EX 100 0,50 50,00 D\n"
                     "1-BOVESPA C VISTA TESTE TST4 ON 100 10,00 999,00 D\n")
    out = parse_nota_text(txt)
    assert out["ok"]
    # 4 vista/fracionário trades still parsed; options OUT, broken line OUT
    assert len(out["trades"]) == 4
    assert out["unsupported_count"] == 1
    assert any("não suportado" in w for w in out["warnings"])
    assert any("não interpretadas" in w for w in out["warnings"])


# ── 8. not a nota ────────────────────────────────────────────────────────────

def test_not_a_nota_is_an_error():
    out = parse_nota_text("hello world\nnothing here")
    assert out["ok"] is False
    assert "não reconhecido" in out["_error"] or "Cabeçalho" in out["_error"]


# ── 9. import + dedup (same nota, two layouts) ───────────────────────────────

def _trades_from_preview(p, mapping=None):
    mapping = mapping or {}
    return [{"ticker": t["ticker"] or mapping.get(
                 (t["market"].split(" ")[0] + "|" + t["spec"]).upper(), ""),
             "type": t["side"], "quantity": t["qty"], "price": t["price"],
             "fees": t["fees"], "date": p["pregao"]} for t in p["trades"]]


def test_import_and_dedup_two_layouts(svc):
    _, aid = _seed(svc)
    p = parse_nota_text(XP_NOTA)
    body = {"account_id": aid, "broker": "Corretora Teste",
            "broker_cnpj": p["broker_cnpj"], "nota": p["nota"],
            "pregao": p["pregao"], "fees_total": p["fees_total"],
            "trades": _trades_from_preview(p)}
    r = svc.import_nota(body)
    assert r["ok"], r
    assert r["created"] == 4

    # every imported tx carries the NC traceability tag
    txs = svc._snapshot()["txs"]
    assert len(txs) == 4
    assert all(t["note"].startswith("NC 987654321 ·") for t in txs)
    # PM blend check: fees entered the custo médio (HAPV3)
    hapv = next(t for t in txs if t["ticker"] == "HAPV3")
    assert hapv["fees"] == 9.63

    # the SAME nota re-parsed from the B3-model layout → 409 duplicate
    p2 = parse_nota_text(B3_NOTA)   # different nº — patch to the same key
    body2 = {"account_id": aid, "broker": "Corretora Teste",
             "broker_cnpj": "11.222.333/0001-44",   # same broker as XP nota
             "nota": "987654321", "pregao": "2026-03-05",
             "trades": _trades_from_preview(p2, {"VISTA|HAPVIDA ON NM": "HAPV3"})}
    r2 = svc.import_nota(body2)
    assert r2.get("status") == 409 and "já foi importada" in r2["_error"]
    assert len(svc._snapshot()["txs"]) == 4      # nothing added

    # dedup pre-check agrees (the preview banner)
    d = svc.nota_dedup_status("11.222.333/0001-44", "987654321",
                              "2026-03-05")
    assert d["imported"] is True and d["existing"]["nota"] == "987654321"


# ── 10. all-or-nothing validation ────────────────────────────────────────────

def test_import_all_or_nothing(svc):
    _, aid = _seed(svc)
    p = parse_nota_text(XP_NOTA)
    trades = _trades_from_preview(p)
    trades[2]["ticker"] = "não-é-ticker"        # row 2: KLBN4F broken
    trades[3]["price"] = -1                     # row 3: negative price
    r = svc.import_nota({"account_id": aid, "broker": "X",
                         "broker_cnpj": "11.222.333/0001-44", "nota": "1",
                         "pregao": "2026-03-05", "trades": trades})
    assert r["ok"] is False
    errs = r["errors"]["trades"]
    assert "Ticker inválido" in errs["2"]["ticker"]
    assert "negativo" in errs["3"]["price"]
    # NOTHING was written (the store is untouched)
    assert svc._snapshot()["txs"] == []


# ── 11. undo ─────────────────────────────────────────────────────────────────

def test_undo_import(svc):
    _, aid = _seed(svc)
    p = parse_nota_text(XP_NOTA)
    r = svc.import_nota({"account_id": aid, "broker": "Corretora Teste",
                         "broker_cnpj": p["broker_cnpj"], "nota": p["nota"],
                         "pregao": p["pregao"], "fees_total": p["fees_total"],
                         "trades": _trades_from_preview(p)})
    assert r["ok"]
    nota_id = r["nota_id"]

    # manually delete ONE imported tx → the registry's alive counter drops
    txs = svc._snapshot()["txs"]
    svc.delete_tx(txs[0]["id"])
    reg = svc.notas_registry(aid)["notas"]
    assert reg[0]["alive"] == 3 and reg[0]["trade_count"] == 4

    # undo removes the remaining 3 + the registry row
    r2 = svc.undo_import(nota_id)
    assert r2["ok"] and r2["removed"] == 3
    assert svc._snapshot()["txs"] == []
    assert svc.notas_registry(aid)["notas"] == []

    # unknown nota → the 404 shape
    r3 = svc.undo_import("deadbeef01")
    assert r3.get("status") == 404


# ── 12. HTTP surface ─────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from core.config import cfg
    monkeypatch.setattr(cfg, "memory_root", str(tmp_path), raising=False)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "webui_app_import_tests", Path(pfmod.__file__).parents[1] / "app.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    from fastapi.testclient import TestClient
    return TestClient(m.create_app(), base_url="http://127.0.0.1:8000")


def test_http_import_endpoints(client):
    B = "/api/webui/portfolio"
    # garbage b64 → 400 with PT-BR message
    r = client.post(B + "/import/nota", json={"pdf_b64": "!!!não-base64!!!"})
    assert r.status_code == 400
    assert "inválido" in r.json()["_error"]
    # cross-site commit → 403 (the CSRF guard covers the new surface)
    r = client.post(B + "/import/commit", content="{}",
                    headers={"Content-Type": "text/plain",
                             "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    # registry + undo 404 + /ir scope validation
    assert client.get(B + "/import/notas").status_code == 200
    assert client.delete(B + "/import/nota/deadbeef01").status_code == 404
    assert client.get(B + "/ir?scope=nonsense").status_code == 400
    assert client.get(B + "/ir?scope=all").status_code == 200
