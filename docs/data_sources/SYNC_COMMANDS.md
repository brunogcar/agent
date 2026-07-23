<- Back to [Data Sources Overview](../../DATA_SOURCES.md)

# 🔧 Manual Sync Commands

All commands run from the project root `(venv) PS D:\mcp\agent>`.

## CVM Data Sources

```powershell
# DFP — annual financial statements (2010-present, ~10 min full, ~30s single year)
python -c "from data_sources.cvm.dfp.sync_engine import sync; print(sync(full_history=True))"
python -c "from data_sources.cvm.dfp.sync_engine import sync; print(sync(years=[2024]))"

# ITR — quarterly financial statements (2011-present, ~15 min full, ~30s single year)
python -c "from data_sources.cvm.itr.sync_engine import sync; print(sync(full_history=True))"
python -c "from data_sources.cvm.itr.sync_engine import sync; print(sync(years=[2024]))"

# FRE — governance + ownership + compensation (2010-present, ~20 min full, ~2s single year)
python -c "from data_sources.cvm.fre.sync_engine import sync; print(sync(full_history=True))"
python -c "from data_sources.cvm.fre.sync_engine import sync; print(sync(years=[2024]))"

# IPE — material events index (2003-present, ~5 min full, ~5s single year)
python -c "from data_sources.cvm.ipe.sync_engine import sync; print(sync(full_history=True))"
python -c "from data_sources.cvm.ipe.sync_engine import sync; print(sync(years=[2024]))"

# CAD — company register (single CSV, ~2s, updated weekly)
python -c "from data_sources.cvm.cad.sync_engine import sync; print(sync())"
python -c "from data_sources.cvm.cad.sync_engine import sync; print(sync(force=True))"
```

## B3 Data Sources

```powershell
# Instruments — all listed securities (7138 pages, ~3 min with concurrent fetching)
python -c "from data_sources.b3.api.sync_engine import sync; print(sync(table='instruments'))"
python -c "from data_sources.b3.api.sync_engine import sync; print(sync(table='instruments', date_str='2026-07-22'))"

# Trades — daily trade stats (~500 pages, ~30s)
python -c "from data_sources.b3.api.sync_engine import sync; print(sync(table='trades'))"

# After-hours — after-hours session trades
python -c "from data_sources.b3.api.sync_engine import sync; print(sync(table='after_hours'))"

# Derivatives — open interest (futures, options)
python -c "from data_sources.b3.api.sync_engine import sync; print(sync(table='derivatives'))"
```

## Check Status

```powershell
# DFP status
python -c "from data_sources.cvm.dfp.status_reporter import status; [print(f'{k}: {v}') for k,v in status().items()]"

# ITR status
python -c "from data_sources.cvm.itr.status_reporter import status; [print(f'{k}: {v}') for k,v in status().items()]"

# FRE status
python -c "from data_sources.cvm.fre.status_reporter import status; [print(f'{k}: {v}') for k,v in status().items()]"

# IPE status
python -c "from data_sources.cvm.ipe.status_reporter import status; [print(f'{k}: {v}') for k,v in status().items()]"

# CAD status
python -c "from data_sources.cvm.cad.status_reporter import status; [print(f'{k}: {v}') for k,v in status().items()]"

# B3 status (all tables)
python -c "from data_sources.b3.api.query_engine import status; [print(f'{t}: {i}') for t,i in status().get('tables',{}).items()]"
```

## Query Examples

```powershell
# DFP — PETROBRAS annual resumo
python -c "from data_sources.cvm.dfp.query_engine import resumo; r=resumo(company='PETROBRAS'); [print(f'{m}: {y}') for m,y in r.get('metrics',{}).items() if m.startswith('Ativo')]"

# CAD — look up PETR4's CNPJ + CD_CVM
python -c "from data_sources.cvm.cad.query_engine import lookup; r=lookup(name='PETROBRAS'); print(r['company']['CNPJ_CIA'], r['company']['CD_CVM'])"

# B3 — look up PETR4 instrument
python -c "from data_sources.b3.api.query_engine import lookup_ticker; r=lookup_ticker(ticker='PETR4'); print(r)"
```

---

*Last updated: 2026-07-23.*
