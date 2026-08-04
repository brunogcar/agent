"""data_sources/cvm/_repair/__init__.py — One-time data repair utilities.

These modules are NOT part of the runtime sync/query pipeline. They are
one-time repair tools for fixing legacy data corruption:

  - purge_penultimo: Delete legacy PENÚLTIMO rows from DFP/ITR databases
  - normalize_cnpj:  Normalize CNPJ to 14 digits + merge duplicate empresas
  - verify:          6-check data integrity verifier (recurring health check)

Run as modules:
  python -m data_sources.cvm._repair.purge_penultimo --dfp --vacuum
  python -m data_sources.cvm._repair.normalize_cnpj
  python -m data_sources.cvm._repair.verify
"""
