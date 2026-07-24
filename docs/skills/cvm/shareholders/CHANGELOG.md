<- Back to [SHAREHOLDERS Overview](../SHAREHOLDERS.md)

# 🗺️ Changelog — shareholders skill

| Version | Date | Summary |
|---------|------|---------|
| v1.0.1 | 2026-07-23 | **P1 hotfix: escala parser.** `equity_structure` mode crashed with `could not convert string to float: 'MIL'` — DFP stores ESCALA_MOEDA as Portuguese words (MIL/MILHOES/UNIDADE), not numbers. Fix: use new `parse_escala()` helper from `_db.py`. Also benefited from FRE v1.0.1 tuple fix (shareholders/free_float modes now work with tickers). |
| v1.0 | 2026-07-23 | **Initial implementation.** Combines FRE (named shareholders, free float) + DFP (equity structure in BRL). 4 modes: shareholders (FRE posicao_acionaria), free_float (FRE distribuicao_capital), equity_structure (DFP BPP 2.03.*), summary (combined). Read-only over already-synced data. 15 tests. |

---

*Last updated: 2026-07-23 (v1.0.1).*
