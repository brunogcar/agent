from core.llm import llm

print("Roles configured:")
for r in llm.list_roles():
    print(f"  {r['role']:12} model={r['model']:40} timeout={r['timeout']}s")

print()
print("LM Studio reachable:", llm.is_available())
