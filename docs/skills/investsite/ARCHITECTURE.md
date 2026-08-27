<- Back to [INVESTSITE Overview](../INVESTSITE.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

**[v2.0]** `_registry.py` + `__init__.py` now delegate to the shared `skills/_base/` module (ModeSpec + `make_registry()` + `auto_discover_modes()` + `make_route()`). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md).

| File | Purpose |
|------|---------|
| `skills/_base/` | [v2.0] Shared infrastructure for ALL 11 skills: ModeSpec dataclass + make_registry() factory + auto_discover_modes() + make_route(). See [SKILLS.md → Modular Skill Pattern](../../SKILLS.md). |
| `skills/investsite/__init__.py` | [v2.0] Uses `auto_discover_modes()` + `make_route()` from `skills/_base/` — ~50 lines. MANIFEST + route (flat domain, 6 modes). Preserves `"domain"` (not `sub_domain`) + `accept_sub_domain=True` (route accepts + ignores `sub_domain` param). |
| `skills/investsite/_registry.py` | [v2.0] Delegates to `skills/_base/` — creates skill's own MODES dict via `make_registry()`. ~16 lines. investsite's flat-domain shape (`"domain"` not `"sub_domain"` + `accept_sub_domain=True`) was PRESERVED. |
| `skills/investsite/fetcher.py` | HTTP fetch (httpx + browser headers), in-memory cache (1h TTL), rate limiting (0.5s), URL builders. [v2.1] Session auth via SESSION_ID cookie (reads from cfg → .env). Auto-detects 302 → login redirect. Browser login path via Playwright if INVESTSITE_EMAIL + INVESTSITE_PASSWORD set. |
| `skills/investsite/parsers.py` | HTML table extraction: `parse_indicators()`, `parse_statement()`, `parse_events()`. UNCHANGED in v1.1. |
| `skills/investsite/report.py` | [v1.1] NEW — Dashboard composition helpers (`_fmt`/`_num`/`_kpi`/`_ok` + `build_overview_kpis` + `build_overview_section` + `build_key_indicators_section` + `build_latest_events_section`). |
| `skills/investsite/modes/__init__.py` | [v1.1] Empty package marker (auto-discovered by `__init__.py`). |
| `skills/investsite/modes/indicators.py` | [v1.1] `indicators()` mode — moved verbatim from the former `investsite.py` monolith. Fetches principais_indicadores.php. |
| `skills/investsite/modes/statements.py` | [v1.1] `statements()` mode — moved verbatim. BPA/BPP/DRE/DFC/DVA/shares with % total columns. |
| `skills/investsite/modes/events.py` | [v1.1] `events()` mode — moved verbatim. IPE by category with CVM rad.cvm.gov.br PDF links. |
| `skills/investsite/modes/summary.py` | [v1.1] `summary()` mode — moved verbatim. Combined key indicators + latest Fato Relevante. Sibling-mode imports aliased (`indicators as _indicators`, `events as _events`). |
| `skills/investsite/modes/listing.py` | [v1.1] `listing()` mode — moved verbatim. Lists available event categories. |
| `skills/investsite/modes/dashboard.py` | [v1.1] NEW — `dashboard()` mode. Thin composition of `indicators()` + `events()`. 3 tabs (Overview/Key Indicators/Latest Events) + 5 top-level KPI cards. |
| `tools/report_ops/adapters/investsite_dashboard.py` | [v1.1] NEW — Thin pass-through adapter `investsite_dashboard`. Maps KPI `unit` -> format spec (pct/num/int/text/brl). Tabs pass through verbatim. |
| `tests/skills/investsite/test_investsite.py` | 18 tests covering parsers + 5 modes + route. [v1.1] Per-mode imports updated to `skills.investsite.modes.<mode>`. |
| `tests/skills/investsite/test_dashboard.py` | [v1.1] NEW — 15 tests covering the new `dashboard()` mode. |

## Data Flow

```
skill(domain="investsite", mode="indicators", params='{"ticker":"PETR4"}')
  │
  ▼  fetcher.fetch_page("principais_indicadores.php", {"cod_negociacao": "PETR4"})
  │    → httpx GET with browser headers
  │    → cache check (1h TTL) → cache hit = return cached HTML
  │    → rate limit (0.5s) → fetch → cache store → return HTML
  │
  ▼  parsers.parse_indicators(html)
  │    → extract 10 <table> elements
  │    → match <caption> to section keys
  │    → parse rows as key-value pairs
  │    → return {sections: {dados_basicos, precos_relativos, ...}}
```

## URL Patterns

| Mode | URL |
|------|-----|
| indicators | `principais_indicadores.php?cod_negociacao={ticker}` |
| statements (BPA) | `balanco_patrimonial_ativo.php?cod_negociacao={ticker}` |
| statements (BPP) | `balanco_patrimonial_passivo.php?cod_negociacao={ticker}` |
| statements (DRE) | `demonstracao_resultado.php?cod_negociacao={ticker}` |
| statements (DFC) | `fluxo_caixa.php?cod_negociacao={ticker}` |
| statements (DVA) | `demonstracao_valor_adicionado.php?cod_negociacao={ticker}` |
| statements (shares) | `quantidade_acoes.php?cod_negociacao={ticker}` |
| events | `informacoes_periodicas_detalhe.php?cod_negociacao={ticker}&categoria={cat}` |

## Goldmine Indicators (for b3-api improvement)

The investsite main page computes these indicators that we should add to `data_sources/b3/api` or a new skill:

### Valuation Ratios (Preços Relativos)
| Indicator | What |
|-----------|------|
| Preço/Lucro (P/L) | Price-to-Earnings |
| Preço/VPA (P/B) | Price-to-Book |
| Preço/Receita Líquida (P/S) | Price-to-Sales |
| Preço/FCO | Price-to-Operating-Cash-Flow |
| Preço/FCF | Price-to-Free-Cash-Flow |
| Preço/Ativo Total | Price-to-Total-Assets |
| Preço/EBIT | Price-to-EBIT |
| Market Cap | Market capitalization |
| Enterprise Value (EV) | EV = Market Cap + Debt - Cash |
| Dividend Yield | Annual dividends / Price |

### Returns & Margins (Retornos e Margens)
| Indicator | What |
|-----------|------|
| ROE | Return on Equity |
| ROA | Return on Assets |
| ROIC | Return on Invested Capital |
| Margem Bruta | Gross margin |
| Margem Líquida | Net margin |
| Margem EBIT | EBIT margin |
| Margem EBITDA | EBITDA margin |
| Giro do Ativo | Asset turnover |
| Alavancagem Financeira | Financial leverage |
| Passivo/PL | Debt-to-equity |
| Dívida Líquida/EBITDA | Net debt / EBITDA |

### Experimental
| Indicator | What |
|-----------|------|
| CAPEX (3M, 12M) | Capital expenditure |
| Fluxo de Caixa Livre (3M, 12M) | Free cash flow = FCO - CAPEX |

## Parser Design

### Table extraction
The parser handles two table types:
- **Tables with `<th>` headers** — first row treated as headers, rest as data
- **Tables with only `<td>`** — all rows are data (no headers stripped)

### Events link extraction
The events page has links inside `<td>` cells (in the "Assuntos" column). The parser:
1. Finds the largest `<table>` block (the events table)
2. Extracts `<a href>` links per row
3. Pairs links with row data by index

## Modes

| Mode | Pages fetched | Returns |
|------|--------------|---------|
| `indicators` | 1 (main page) | 10 sections of key-value data |
| `statements` | 1 (per statement type) | Account codes + period values + % total |
| `events` | 1 (per category) | Events list with CVM PDF links |
| `summary` | 2 (indicators + events) | Key indicators + latest Fato Relevante |
| `listing` | 0 (static) | Available event categories |
| `dashboard` | 2 (indicators + events) | [v1.1] 3-tab payload: Overview (Summary text + 5 KPI cards), Key Indicators (8-row valuation+returns table), Latest Events (4-column Fato Relevante table). Top-level KPIs: P/L, P/VPA, EV/EBITDA, ROE, Dividend Yield. |

## Modular file layout (v1.1)

```
skills/investsite/
├── __init__.py            # MANIFEST + route + auto-discovery (105 lines)
├── _registry.py           # ModeSpec + register_mode + build_manifest_modes (104 lines)
├── fetcher.py             # HTTP fetch + cache + URL builders (158 lines, UNCHANGED)
├── parsers.py             # HTML table parsers (319 lines, UNCHANGED)
├── report.py              # NEW: dashboard composition helpers (271 lines)
└── modes/
    ├── __init__.py        # empty package marker (5 lines)
    ├── indicators.py      # indicators() mode (63 lines)
    ├── statements.py      # statements() mode (65 lines)
    ├── events.py          # events() mode (64 lines)
    ├── summary.py         # summary() mode — uses sibling-mode imports (77 lines)
    ├── listing.py         # listing() mode (33 lines)
    └── dashboard.py       # NEW: dashboard() mode (145 lines)
```

## Key Design Decisions

### Modular pattern (v1.1)
Same `_registry.py` + `modes/*.py` + `report.py` + dashboard adapter pattern as the CVM skills (financials, valuation, backtest, comparison, dividends, governance, historical, screener, shareholders, insider). Auto-discovery via `importlib.import_module` over `modes/*.py` — adding a new mode = drop a file + `@register_mode()`. No edits to `__init__.py` or `_registry.py` needed.

### Top-level flat domain (v1.1 preserved)
investsite is a TOP-LEVEL flat domain (not under cvm/). The MANIFEST keeps `"domain": "investsite"` (NOT `sub_domain`) + `"has_sub_domains": False`. The `route()` signature stays `route(sub_domain="", mode="", **kwargs)` — the `sub_domain` param is accepted for dispatcher compatibility with CVM-style routes but ignored. This is the ONLY structural difference from the CVM skill pattern.

### fetcher.py + parsers.py KEPT as separate modules
Unlike CVM skills where the monolith bundled helpers + fetchers + parsers, investsite.py was already split into 3 files (`investsite.py` for mode logic + `fetcher.py` for HTTP + `parsers.py` for HTML parsing) before v1.1. The v1.1 split only touches the mode logic — `fetcher.py` (158 lines) + `parsers.py` (319 lines) are UNCHANGED. Each mode file imports `fetch_page` + URL builders + parsers directly.

### Dashboard composition (thin)
The `dashboard` mode does NOT fetch new data beyond what `indicators()` + `events()` fetch — it calls them and reshapes their output. Each sub-call is independently try/except-wrapped so a network/parse failure degrades the corresponding tab to an empty payload (table has 0 rows, KPIs render as "—") instead of crashing the whole dashboard. The 5 top-level KPI cards (P/L, P/VPA, EV/EBITDA, ROE, Dividend Yield) are placed at the TOP LEVEL (not inside a tab) — matches the dashboard contract used by the other 10 CVM skills so the dashboard template's `kpi-grid` div renders them above all tabs.

### Dashboard adapter (thin pass-through)
The `investsite_dashboard` adapter is THIN — it passes through the dashboard mode's already-shaped tabs verbatim and only re-formats the top-level KPI cards via a unit -> format-spec map (`pct -> pct` for ROE/Dividend Yield stored as fractions, `num -> num` for P/L/P/VPA/EV/EBITDA raw multiples). Defensive: if a KPI value is already a string (pre-formatted by `report.py`), passes through verbatim; otherwise applies the format spec via `apply_fmt()`.

### Per-mode fetch_page imports
Each mode file imports `fetch_page` from `skills.investsite.fetcher` at the top level (NOT lazy). Tests that mock the fetcher must patch `skills.investsite.modes.<mode>.fetch_page` (the symbol imported into the mode module's namespace), not `skills.investsite.fetcher.fetch_page` (the original definition — patching that wouldn't affect already-imported references).

---

*Last updated: 2026-07-30 (v2.0 — `skills/_base/` extraction; flat-domain shape preserved — see CHANGELOG.md for details).*
