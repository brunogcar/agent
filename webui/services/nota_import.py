"""webui/services/nota_import.py — Nota de Corretagem (PDF) → preview payload.

[v1.22.2] The broker-CSV importer the roadmap asked for, adapted to what
B3 brokers actually give retail: PDFs. Three layouts ship today (the
grammar under the table is ONE — B3's own):

  XP layout    "Nota de Negociação" (XP-branded): spec carries the
               ticker ("HAPVIDA HAPV3 ON NM"), fees under "Resumo
               Financeiro" → "Total Corretagem / Despesas".
  B3 model     "NOTA DE NEGOCIAÇÃO" (the B3 default every broker can
               emit): spec has NO ticker ("HAPVIDA ON NM") — the
               preview surfaces those as ``needs_mapping`` and the user
               maps each especificação to a ticker ONCE per import.
  BTG layout   "NOTA DE CORRETAGEM": spec LEADS with the ticker
               ("AMAR3 ON"), IRRF row present.

Pipeline: pdfplumber text (pypdf fallback) → line grammar → normalized
trades + header + fees + IRRF + cross-checks. NOTHING touches the store
here — this module only PARSES; portfolio_service.import_nota() owns the
write (dedup key cnpj+nº nota+pregão, bulk single-save, undo registry).

No scanned-PDF OCR: text extraction returning nothing is a clear PT-BR
error, not a silent empty import.
"""
from __future__ import annotations

import base64
import binascii
import io
import re
from datetime import date
from typing import Any

# ONE ticker definition for every layer (the v1.22 lesson — B3SA3/BDRs).
from webui.validators import TICKER_RE
from tools.report_ops.formats import fmt_num

# ── number grammar (PT-BR: "." thousands, "," decimals) ──────────────────────


def br_to_float(s: str) -> float | None:
    """'1.766,00' → 1766.0 · '200' → 200.0 · '8,83' → 8.83.

    None on anything that is not a plain PT-BR number (the parse is
    STRICT — a quantity like '12AB3' must not half-parse).
    """
    s = (s or "").strip()
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?", s):
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:                                    # pragma: no cover
        return None


# ── layout grammar ───────────────────────────────────────────────────────────

# Markets the Carteira store can honestly hold (roadmap: opções/termo
# import comes with the options book). Accent-tolerant ("FRACIONÁRIO").
_SUPPORTED_MARKETS = {"VISTA", "FRACIONARIO", "FRACIONÁRIO"}

# B3's obs-column legend (letters/symbols that may trail the spec):
# @ leilão · # negócio direto · D day trade · F cobertura · H home broker
# 8 institucional · X box · Y desmanche · P carteira própria · B débêntures
# L precatório · T bruto · I POP · A posição futuro · 2 vinculada · C clubes
_OBS_ALPHABET = re.compile(r"^[@#8DHFITXYBLP2AC]{1,3}$")

# The ONE trade-line grammar all three layouts share (tail-anchored):
#   1-BOVESPA C VISTA HAPVIDA HAPV3 ON NM @ 200 8,83 1.766,00 D
_RE_TRADE = re.compile(
    r"^(\d+)-BOVESPA\s+([CV])\s+(\S+)\s+(.+?)\s+"
    r"(\d[\d.]*)\s+(\d*[.,]\d+|\d+)\s+([\d.]*\d,\d{2}|\d+)\s+([DC])\s*$")

# Header — nota/folha/data (B3 model + BTG):
_RE_NR_B3 = re.compile(
    r"^Nr\.?\s*nota\s+Folha\s+Data\s*pregão\s*$", re.I)
_RE_NR_B3_VALS = re.compile(r"^(\d{4,12})\s+(\d+)\s+(\d{2}/\d{2}/\d{4})\s*$")
# Header — XP ("Data pregão Nº Nota" then "23/10/2026 147087788"):
_RE_NR_XP = re.compile(r"^Data\s*pregão\s+N[ºo°]\s*Nota\s*$", re.I)
_RE_NR_XP_VALS = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(\d{4,12})\s*$")

_RE_CNPJ = re.compile(r"C\.?N\.?P\.?J:?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})")
_RE_CPF = re.compile(r"(\d{3}\.\d{3}\.\d{3}-\d{2})")
# B3/BTG client line: "<código> NOME COMPLETO <cpf>"
_RE_CLIENT_B3 = re.compile(r"^(\d{3,12})\s+(.{3,80}?)\s+(\d{3}\.\d{3}\.\d{3}-\d{2})\s*$")
# XP client block: name on its own line, then "CPF/CNPJ 012.881.526-47"
_RE_CLIENT_XP_CPF = re.compile(r"^CPF/?CNPJ\s+([\d./-]+)\s*$", re.I)
_RE_CONTA_XP = re.compile(r"Conta\s+XP\s+(\d{3,12})", re.I)

_RE_FEES_TOTAL = re.compile(
    r"^Total\s+(?:Corretagem|Custos)\s*/?\s*Despesas\s+([\d.,]+)\s+D", re.I | re.M)
_RE_IRRF = re.compile(
    r"I\.?R\.?R\.?F\.?\s*s/\s*operações,\s*base\s*R\$\s*([\d.,]+)\s+(\d[\d.,]*)")
_RE_VALOR_OPER = re.compile(
    r"^Valor\s+das\s+operações\s+([\d.,]+)\s*$", re.I | re.M)
_RE_LIQUIDO = re.compile(
    r"Líquido\s+para\s+(\d{2}/\d{2}/\d{4})\s+([\d.,]+)\s+([DC])")

# Broker line heuristic: a company-ish line (CORRETORA/CTVM/CCTVM/
# PACTUAL … S.A./S/A) — walked BACK from the CNPJ line (works on all
# three layouts: the broker always prints its name above its CNPJ).
# Mixed case on purpose ("BTG Pactual CTVM S.A."). The (?![A-Za-zÀ-ü])
# guard keeps "SALA 201" (an address) from matching the S.A. branch —
# the v1.22.2 first run named the broker "AV ATAULFO DE PAIVA, 153".
_RE_BROKER_LINE = re.compile(
    r"^[A-ZÀ-Ü][A-Za-zÀ-ü0-9 .,&/-]*?"
    r"(CORRETORA|CTVM|CCTVM|PACTUAL|S/A|S\.A\.)(?![A-Za-zÀ-ü])"
    r"[A-Za-zÀ-ü0-9 .,&/-]*$")

# Name→ticker suggestions for B3-model specs (no ticker in the PDF).
# Short by design (the most-traded papers); the preview ALWAYS shows a
# free input + the store's own tickers — this only pre-fills the field.
_SUGGEST: dict[str, str] = {
    "HAPVIDA": "HAPV3", "KLABIN": "KLBN4", "MARCOPOLO": "POMO4",
    "MITRE REALTY": "MTRE3", "PORTOBELLO": "PTBL3", "RAIZEN": "RAIZ4",
    "MINERVA": "BEEF3", "RANDON PART": "RAPP4", "PETROBRAS": "PETR4",
    "PETROBRAS PN": "PETR4", "VALE": "VALE3", "ITAUUNIBANCO": "ITUB4",
    "ITAU": "ITUB4", "BRASIL": "BBAS3", "BRADESCO": "BBDC4",
    "AMBEV": "ABEV3", "WEG": "WEGE3", "B3": "B3SA3", "TAEE": "TAEE11",
    "SABESP": "SBSP3", "ENGIE": "EGIE3", "BANCO DO BRASIL": "BBAS3",
    "CIA ENERGIA": "CMIG4", "CEMIG": "CMIG4", "GERDAU": "GGBR4",
    "USIMINAS": "USIM5", "CSN": "CSNA3", "SUZANO": "SUZB3",
    "LOCALIZA": "RENT3", "LOJAS RENNER": "LREN3", "MAGAZINE": "MGLU3",
    "BANCO PAN": "BPAN4", "ELETROBRAS": "ELET3", "SUL AMERICA": "SULA11",
}

_MAX_PDF_BYTES = 5 * 1024 * 1024        # decoded — notas are ~30-200 KB
_MAX_PAGES = 40


# ── PDF text extraction (pdfplumber → pypdf; both in requirements.txt) ──────

def _brl(v: float | None, dec: int = 2) -> str:
    """PT-BR money for warnings/info (fmt_num — the macro.py precedent)."""
    return fmt_num(v or 0.0, decimals=dec)


def extract_pdf_text(data: bytes) -> tuple[str, int, str]:
    """(all-pages text joined by \n\n, page count, engine name).

    pdfplumber first (the read_pdf.py precedent — best PT-BR table
    text), pypdf fallback. Raises ValueError with a PT-BR message on
    anything unusable (not a PDF, encrypted, scanned/no text).
    """
    if not data.startswith(b"%PDF"):
        raise ValueError("O arquivo não parece ser um PDF.")
    if len(data) > _MAX_PDF_BYTES:
        raise ValueError("PDF muito grande (limite 5 MB).")

    _last_pdf_err = ""
    try:
        import pdfplumber                              # lazy (requirements)
        pages: list[str] = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > _MAX_PAGES:
                raise ValueError(f"PDF com muitas páginas ({len(pdf.pages)} "
                                 "— limite 40).")
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        text = "\n\n".join(p for p in pages if p.strip())
        if text.strip():
            return text, len(pages), "pdfplumber"
    except ImportError:
        pass
    except ValueError:
        raise
    except Exception as e:                             # noqa: BLE001
        # fall through to pypdf on extraction glitches
        _last_pdf_err = f"{type(e).__name__}: {e}"

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:                           # noqa: BLE001
                raise ValueError("PDF criptografado — exporte a nota sem "
                                 "senha.")
        if len(reader.pages) > _MAX_PAGES:
            raise ValueError(f"PDF com muitas páginas ({len(reader.pages)} "
                             "— limite 40).")
        pages = [(p.extract_text() or "") for p in reader.pages]
        text = "\n\n".join(p for p in pages if p.strip())
        if text.strip():
            return text, len(pages), "pypdf"
    except ImportError:
        raise ValueError("Instale pdfplumber ou pypdf para importar notas "
                         "(pip install pdfplumber).")
    except ValueError:
        raise
    except Exception as e:                             # noqa: BLE001
        raise ValueError(f"Falha ao ler o PDF ({type(e).__name__}: {e}).")

    raise ValueError(
        "Não foi possível extrair texto do PDF"
        + (f" (pdfplumber: {_last_pdf_err})" if _last_pdf_err else "")
        + " — notas ESCANEADAS (imagem) não são suportadas; exporte o PDF "
          "original da corretora.")


# ── the parser ───────────────────────────────────────────────────────────────

def _split_obs(spec: str) -> tuple[str, str]:
    """Strip trailing obs markers from a spec → (spec, obs).

    'HAPVIDA HAPV3 ON NM @#' → ('HAPVIDA HAPV3 ON NM', '@#'). The
    markers sit between spec and quantity; class words (ON, PN, NM,
    N2…) never match the obs alphabet.
    """
    tokens = spec.split()
    obs: list[str] = []
    while len(tokens) > 1 and _OBS_ALPHABET.match(tokens[-1]):
        obs.insert(0, tokens.pop())
    return " ".join(tokens), "".join(obs)


def _find_ticker(spec: str) -> str | None:
    """First spec token that IS a B3 ticker (HAPV3 · AMAR3 · BOVA11…).

    XP embeds it mid-spec, BTG leads with it; class words never match
    the ticker grammar (no trailing digit run).
    """
    for tok in spec.split():
        if TICKER_RE.match(tok):
            return tok
    return None


def _norm_spec_key(market: str, spec: str) -> str:
    """Identity of a needs-mapping spec (market + upper spec)."""
    return (market.split(" ")[0] + "|" + spec).upper()


def _suggest_for(spec: str) -> str | None:
    """Company-prefix → suggested ticker (None = no guess)."""
    words = spec.upper().split()
    for n in (3, 2, 1):
        if len(words) >= n:
            prefix = " ".join(words[:n])
            if prefix in _SUGGEST:
                return _SUGGEST[prefix]
    return None


def _strip_fraction(ticker: str) -> str:
    """KLBN4F → KLBN4 (odd-lot suffix F; base must still be a ticker)."""
    if len(ticker) > 5 and ticker.endswith("F"):
        base = ticker[:-1]
        if TICKER_RE.match(base):
            return base
    return ticker


def _broker_short(name: str) -> str:
    n = re.sub(r"\s+", " ", (name or "").strip().upper())
    if "PACTUAL" in n:
        return "BTG Pactual"
    if "XP" in n.split() or n.startswith("XP "):
        return "XP"
    if "CLEAR" in n:
        return "Clear"
    if "RICO" in n:
        return "Rico"
    if "NU" in n.split() and "INVEST" in n:
        return "Nu Invest"
    return (n.split(" S")[0].split(" -")[0][:24] or "Corretora")


def parse_nota_text(text: str) -> dict[str, Any]:
    """Nota text → the preview payload (no store access).

    Always returns a dict with ``ok`` — False + ``_error`` when the
    text is not recognizable as a nota at all; True with ``warnings``
    for everything recoverable (line mismatches, missing fees, …).
    """
    if not text or not text.strip():
        return {"ok": False, "_error": "PDF sem texto extraível."}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # ── header: nota nr / folha / pregão ────────────────────────────────
    nota_nr = folhas = pregao = None
    for i, ln in enumerate(lines):
        if _RE_NR_B3.match(ln) and i + 1 < len(lines):
            m = _RE_NR_B3_VALS.match(lines[i + 1])
            if m:
                nota_nr, folhas, pregao = m.group(1), m.group(2), m.group(3)
                break
        if _RE_NR_XP.match(ln) and i + 1 < len(lines):
            m = _RE_NR_XP_VALS.match(lines[i + 1])
            if m:
                pregao, nota_nr = m.group(1), m.group(2)
                folhas = "1"
                break
    if not (nota_nr and pregao):
        return {"ok": False, "_error":
                "Cabeçalho da nota não reconhecido (nº da nota / data "
                "pregão) — o layout é diferente dos suportados (XP, modelo "
                "B3, BTG)."}
    try:
        d, m, y = pregao.split("/")
        pregao_iso = date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return {"ok": False, "_error": f"Data de pregão inválida: {pregao}."}

    # ── broker (name walked back from the CNPJ line) ────────────────────
    broker_name = broker_cnpj = None
    for i, ln in enumerate(lines):
        mc = _RE_CNPJ.search(ln)
        if mc:
            broker_cnpj = mc.group(1)
            for j in range(i - 1, max(-1, i - 8), -1):
                if _RE_BROKER_LINE.match(re.sub(r"\s+", " ", lines[j])):
                    broker_name = re.sub(r"\s+", " ", lines[j])
                    break
            if broker_name:
                break

    # ── client (name + CPF + account code) ──────────────────────────────
    client_name = client_cpf = account_code = None
    for i, ln in enumerate(lines):
        m = _RE_CLIENT_B3.match(ln)
        if m:
            account_code, client_name, client_cpf = m.groups()
            break
        m = _RE_CLIENT_XP_CPF.match(ln)
        if m:
            client_cpf = m.group(1)
            client_name = lines[i - 1] if i > 0 else None
            mx = _RE_CONTA_XP.search(text)
            if mx:
                account_code = mx.group(1)
            break

    # ── trades ──────────────────────────────────────────────────────────
    trades: list[dict[str, Any]] = []
    unsupported: list[str] = []
    bad_lines: list[str] = []
    for ln in lines:
        m = _RE_TRADE.match(ln)
        if not m:
            continue
        _, cv, market, spec_raw, qty_s, price_s, value_s, dc = m.groups()
        spec, obs = _split_obs(spec_raw)
        qty = br_to_float(qty_s)
        price = br_to_float(price_s)
        value = br_to_float(value_s)
        if qty is None or price is None or value is None or qty <= 0:
            bad_lines.append(ln)
            continue
        market_u = market.upper()
        trade: dict[str, Any] = {
            "market": market_u, "side": "buy" if cv == "C" else "sell",
            "spec": spec, "qty": qty, "price": price, "value": value,
            "dc": dc, "day": "D" in obs, "obs": obs,
        }
        if market_u not in _SUPPORTED_MARKETS:
            trade["ticker"] = _find_ticker(spec)
            unsupported.append(trade)
            continue
        # qty × price ≈ value (cent-level tolerance)
        if abs(qty * price - value) > 0.02 + 1e-9:
            bad_lines.append(ln)
            continue
        tk = _find_ticker(spec)
        trade["ticker"] = tk
        trade["fractional"] = market_u.startswith("FRACION") or (
            tk is not None and tk.endswith("F") and len(tk) > 5)
        if tk is not None:
            trade["ticker_base"] = _strip_fraction(tk)
        trades.append(trade)

    if not trades and not unsupported:
        return {"ok": False, "_error":
                "Nenhuma negociação reconhecida na nota (formato de linha "
                "diferente do esperado)."}

    warnings: list[str] = []
    if bad_lines:
        warnings.append(f"{len(bad_lines)} linha(s) de negociação não "
                        "interpretadas e ignoradas — confira antes de "
                        "importar.")
    if unsupported:
        names = ", ".join(sorted({t.get("market", "?") for t in unsupported}))
        warnings.append(f"{len(unsupported)} negócio(s) em mercado não "
                        f"suportado ({names}) ficam DE FORA — o import "
                        "cobre à vista e fracionário.")

    # ── fees / IRRF / totals cross-check ────────────────────────────────
    fees_total = 0.0
    mf = _RE_FEES_TOTAL.search(text)
    if mf:
        v = br_to_float(mf.group(1))
        if v is not None and v >= 0:
            fees_total = v
    else:
        warnings.append("Total de taxas/corretagem não encontrado — as "
                        "transações serão importadas SEM taxas; edite-as "
                        "depois se preciso.")

    irrf = irrf_base = None
    mi = _RE_IRRF.search(text)
    if mi:
        irrf_base = br_to_float(mi.group(1))
        irrf = br_to_float(mi.group(2))
        if irrf is not None and irrf > 0 and irrf_base:
            warnings.append(
                f"IRRF s/ operações retido na fonte: R$ {_brl(irrf)} "
                f"(base R$ {_brl(irrf_base)}, 0,005% — compensável no IR "
                "anual; apenas informativo, não entra nas taxas).")

    sum_supported = sum(t["value"] for t in trades)
    sum_all = sum_supported + sum(t["value"] for t in unsupported)
    mo = _RE_VALOR_OPER.search(text)
    if mo:
        stated = br_to_float(mo.group(1))
        if stated is not None and abs(stated - sum_all) > 0.02 + 1e-9:
            warnings.append(
                "Soma dos negócios lidos diverge do 'Valor das operações' "
                f"da nota (lido R$ {_brl(sum_all)} × declarado "
                f"R$ {_brl(stated)}) — confira o PDF.")

    liq_date = liq_value = None
    ml = _RE_LIQUIDO.search(text)
    if ml:
        liq_date = ml.group(1)
        liq_value = br_to_float(ml.group(2))

    # ── fee allocation (pro-rata by value, cent-exact) ─────────────────
    _allocate_fees(trades, fees_total)

    # ── needs-mapping specs (B3 model: no ticker in the PDF) ───────────
    needs_mapping: dict[str, Any] = {}
    for t in trades:
        if t["ticker"] is None:
            key = _norm_spec_key(t["market"], t["spec"])
            if key not in needs_mapping:
                needs_mapping[key] = {
                    "market": t["market"], "spec": t["spec"],
                    "suggest": _suggest_for(t["spec"]),
                }
    if needs_mapping:
        warnings.append(
            f"{len(needs_mapping)} especificação(ões) sem ticker no PDF "
            "(modelo B3) — informe o ticker de cada uma antes de importar.")

    return {
        "ok": True,
        "broker": broker_name or "Corretora desconhecida",
        "broker_short": _broker_short(broker_name or ""),
        "broker_cnpj": broker_cnpj,
        "nota": nota_nr,
        "folhas": folhas,
        "pregao": pregao_iso,
        "pregao_br": pregao,
        "client_name": client_name or "—",
        "client_cpf": client_cpf,
        "account_code": account_code,
        "fees_total": round(fees_total, 2),
        "irrf": round(irrf, 2) if irrf is not None else None,
        "irrf_base": irrf_base,
        "liquido_para": liq_date,
        "liquido_value": liq_value,
        "trades": trades,
        "unsupported_count": len(unsupported),
        "needs_mapping": needs_mapping,
        "warnings": warnings,
        "sum_values": round(sum_supported, 2),
    }


def _allocate_fees(trades: list[dict], fees_total: float) -> None:
    """Pro-rata fee split by trade value — Σ alocado == total, exato.

    Cent rounding with largest-remainder correction (the classic
    apportionment): floor shares, then hand the spare cents to the
    largest trades first. A nota with fees 0 allocates 0 everywhere.
    """
    if not trades:
        return
    total_cents = int(round(round(fees_total, 2) * 100))
    if total_cents <= 0:
        for t in trades:
            t["fees"] = 0.0
        return
    vals = [abs(t["value"]) for t in trades]
    vsum = sum(vals)
    if vsum <= 0:                                    # defensive: equal split
        base_c, leftover = divmod(total_cents, len(trades))
        for t in trades:
            t["_cents"] = base_c
        for k in range(leftover):
            trades[k]["_cents"] += 1
    else:
        raw = [total_cents * v / vsum for v in vals]
        for t, r in zip(trades, raw):
            t["_cents"] = int(r // 1)              # floor cents
        leftover = total_cents - sum(t["_cents"] for t in trades)
        order = sorted(range(len(trades)),
                       key=lambda i: -trades[i]["_cents"])
        for k in range(leftover):
            trades[order[k % len(order)]]["_cents"] += 1
    for t in trades:
        t["fees"] = round(t.pop("_cents") / 100.0, 2)


# ── upload entry point (route → preview) ─────────────────────────────────────

def preview_from_b64(pdf_b64: str) -> dict[str, Any]:
    """base64 PDF → preview payload (the POST /import/nota handler).

    Size/garbage guards live here — the parser stays pure-text (and
    unit-testable without a PDF writer).
    """
    try:
        data = base64.b64decode(pdf_b64 or "", validate=True)
    except (binascii.Error, ValueError):
        return {"ok": False, "_error": "Conteúdo do arquivo inválido "
                "(base64 corrompido)."}
    try:
        text, pages, engine = extract_pdf_text(data)
    except ValueError as e:
        return {"ok": False, "_error": str(e)}
    out = parse_nota_text(text)
    if out.get("ok"):
        out["pages"] = pages
        out["engine"] = engine
    return out
