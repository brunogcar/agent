<- Back to [Skills Overview](../SKILLS.md)

# 🌐 INVESTSITE — Financial Data from investsite.com.br

Live web scraping skill for investsite.com.br. Fetches per-ticker financial data: indicators, full statements, and periodic events with CVM PDF links.

**Key characteristics:**
- **Live fetching** — no local DB, no sync. Each call hits investsite.com.br directly.
- **In-memory cache** — 1h TTL to avoid re-fetching within a session.
- **6 modes** — indicators (default), statements, events, summary, listing, dashboard.
- **Modular layout (v1.1)** — `investsite.py` split into `_registry.py` + `modes/{indicators,statements,events,summary,listing,dashboard}.py` + `report.py`. `fetcher.py` + `parsers.py` kept as separate modules. Auto-discovery via `@register_mode`.
- **10 indicator tables** — basic data, prices/valuation, DRE TTM/quarterly, returns/margins, balance sheet, cash flow, experimental CAPEX/FCF.
- **Direct CVM links** — events mode returns `rad.cvm.gov.br` PDF links.
- **Rate-limited** — 0.5s between requests to respect the free site.

---

## 🚀 Quick Start

```
# Main indicators (valuation ratios, margins, balance, cashflow)
skill(domain="investsite", mode="indicators", params='{"ticker":"PETR4"}')

# Full DRE statement with % total columns
skill(domain="investsite", mode="statements", params='{"ticker":"PETR4","statement":"DRE"}')

# Fato Relevante events with CVM PDF links
skill(domain="investsite", mode="events", params='{"ticker":"PETR4","categoria":"Fato Relevante"}')

# Combined summary
skill(domain="investsite", mode="summary", params='{"ticker":"PETR4"}')
```

---

## ⚙️ Configuration

No config required. No `.env` vars. No local DB.

| Setting | Value |
|---------|-------|
| Base URL | `https://www.investsite.com.br` |
| Cache | In-memory, 1h TTL |
| Rate limit | 0.5s between requests |
| HTTP library | `httpx` with browser-like headers |

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [ARCHITECTURE.md](investsite/ARCHITECTURE.md) | Data flow, URL patterns, parser design, goldmine indicators for b3-api |
| [API.md](investsite/API.md) | 6 modes: indicators, statements, events, summary, listing, dashboard |
| [CHANGELOG.md](investsite/CHANGELOG.md) | Version history + roadmap (charts, caching, b3-api improvements) |
| [INSTRUCTIONS.md](investsite/INSTRUCTIONS.md) | AI editing rules — what NOT to break |

---

*Last updated: 2026-07-29 (v1.1 — modular split + dashboard mode).*
