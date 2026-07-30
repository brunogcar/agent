<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 📖 API Reference

## skill(domain="cvm", sub_domain="financials", ...)

### mode="quarterly" (default)

Standalone quarterly summary + ratios. Derives Q1-Q4 from ITR cumulative + DFP annual.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | B3 ticker (PETR4), name, or CNPJ. Required |
| periods | int | 8 | Number of quarters |
| consolidado | int | 1 | 1=consolidated, 0=individual |

```json
{
  "status": "ok",
  "company": "PETROLEO BRASILEIRO S.A.",
  "period_type": "quarterly",
  "periods": [
    {
      "period": "1T2026",
      "year": 2026,
      "quarter": 1,
      "metrics": {
        "ativo_total": 18159922000,
        "receita_liquida": 537661000,
        "ebitda": 508485000,
        "lucro_liquido": 371553000,
        ...
      },
      "ratios": {
        "marg_bruta": 0.609,
        "marg_ebitda": 0.946,
        "roa": 0.105,
        "roe": 0.255,
        ...
      }
    }
  ]
}
```

### mode="annual"

Annual summary + ratios from DFP.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | Required |
| periods | int | 5 | Number of years |
| consolidado | int | 1 | 1=consolidated, 0=individual |

### mode="complete"

Full statements by grupo + key account codes (not all 497).

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | Required |
| period | str | "quarterly" | "quarterly" or "annual" |
| grupo | str | "" | Filter: BPA, BPP, DRE, DFC_MI, DVA. Empty = all key codes |
| consolidado | int | 1 | 1=consolidated, 0=individual |
| periods | int | 8 | Quarters (quarterly) or years (annual) |

### mode="summary"

Combined: latest annual + latest quarterly (4Q trend) + key ratios. Best-effort.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | Required |
| consolidado | int | 1 | 1=consolidated, 0=individual |

**v1.3 response:**
```json
{
  "status": "ok",
  "company": "PETR4",
  "sections": {
    "latest_annual":   { /* same as annual(periods=1).periods[0] */ },
    "latest_quarterly": { /* same as quarterly(periods=4).periods[-1] */ },
    "quarterly_trend":  [ /* quarterly(periods=4).periods, oldest-first */ ],
    "current_ratios": {
      "date": "2026-07-27",
      "roic":          0.18,
      "graham_number": 75.0,
      "ev_ebitda":     6.4,
      "p_fcf":         10.0,
      "p_ebit":        7.2,
      "p_fco":         2.8
    }
  }
}
```

`current_ratios` is computed by delegating to `skills.cvm.calculations.metrics.*` at today's date (point-in-time). Each metric is wrapped in `_safe_call` so a missing DB (e.g. `cotahist.db` for price-based ratios) returns `None` instead of crashing the whole summary. Fundamental ratios (ROIC, Graham) typically populate from DFP/ITR alone; price-based ratios (EV/EBITDA, P/FCF, P/EBIT, P/FCO) additionally require `b3/cotahist.db` + `cvm/fre.db`.

---

## Examples

```
skill(domain="cvm", sub_domain="financials", mode="quarterly", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="financials", mode="annual", params='{"company":"VALE3","periods":10}')
skill(domain="cvm", sub_domain="financials", mode="complete", params='{"company":"PETR4","grupo":"DRE"}')
skill(domain="cvm", sub_domain="financials", mode="summary", params='{"company":"PETR4"}')
```

---

*Last updated: 2026-07-30 (v2.0 — `skills/_base.py` extraction; modes + params + return shapes unchanged). See [ARCHITECTURE.md](ARCHITECTURE.md) for the updated source code reference.*
