import sqlite3, sys
from pathlib import Path

root = Path("memory_db")
print("== DB files ==")
for p in sorted(root.rglob("*.db")):
    print(f"  {p}  {p.stat().st_size/1e6:.1f} MB")

itr = root / "cvm" / "itr.db"
if not itr.exists():
    sys.exit(f"missing {itr}")
conn = sqlite3.connect(f"file:{itr}?mode=ro", uri=True)

print("\n== ITR codigo='1' (Ativo Total) by meses ==")
for r in conn.execute("SELECT meses, COUNT(*), MIN(data_fim_exerc), MAX(data_fim_exerc) FROM contas WHERE codigo='1' GROUP BY meses"):
    print("  meses=%s rows=%s %s -> %s" % r)

print("\n== Month of data_fim_exerc (codigo='1') ==")
for r in conn.execute("SELECT substr(data_fim_exerc,6,2), COUNT(*), COUNT(DISTINCT data_fim_exerc) FROM contas WHERE codigo='1' GROUP BY 1 ORDER BY 1"):
    print("  month=%s rows=%s distinct_dates=%s" % r)

print("\n== Distinct quarter-end dates per year (meses=12) ==")
for r in conn.execute("SELECT substr(data_fim_exerc,1,4), COUNT(DISTINCT data_fim_exerc) FROM contas WHERE codigo='1' AND meses=12 GROUP BY 1 ORDER BY 1 DESC LIMIT 6"):
    print("  %s: %s distinct dates" % r)
conn.close()
