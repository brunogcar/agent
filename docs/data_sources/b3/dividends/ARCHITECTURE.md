<- Back to [B3 Overview](../B3.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/b3/dividends/__init__.py` | MANIFEST + route — sub-domain hub, 5 modes |
| `data_sources/b3/dividends/catalog.py` | Schema constants: API URL, SQL schema, DB path/connect helpers |
| `data_sources/b3/dividends/sync_engine.py` | Download per-ticker JSON → parse → normalize dates → store |
| `data_sources/b3/dividends/query_engine.py` | Query: dividends(), stock_dividends(), subscriptions(), status() |

## API

Per-ticker JSON API (different from the paginated table API used by instruments/trades):

```
GET https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/
    CompanyCall/GetListedSupplementCompany/{base64}

base64 = base64({"issuingCompany":"PETR","language":"pt-br"})

→ JSON: [{cashDividends: [...], stockDividends: [...], subscriptions: [...]}]
```

- issuingCompany = first 4 chars of ticker (PETR for both PETR3 and PETR4)
- Full ticker used for storage + state tracking (PETR3 and PETR4 are separate)
- No pagination — one request returns all dividend history for the company

## Design Decisions

- **Per-ticker sync (not bulk)**: Each ticker is synced individually. The API returns all dividend history for one company per request.
- **Date normalization**: B3 returns DD/MM/YYYY. Converted to YYYY-MM-DD for correct SQLite sorting.
- **Rate parsing**: B3 uses comma as decimal separator ("1,55"). Converted to float.
- **DELETE + INSERT per ticker**: Each sync replaces all data for that ticker (idempotent).

---

*Last updated: 2026-07-23 (v1.0).*
