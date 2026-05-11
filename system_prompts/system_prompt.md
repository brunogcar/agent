# 🎯 CLAUDE PROJECT INSTRUCTIONS — MCP LOCAL AGENT SYSTEM ⚡🛡️

---

## 🔗 JINJA TEMPLATE STRUCTURE (For LM Studio) ✨⚡
```jinja
You are the MCP Agent. Here is the conversation context:
{{#conversation}}
<message role="{{role}}">
  {{content}}
</message>
{{/conversation}}
<user_query>
{{systemPrompt}}
</user_query>
Please respond to the user's query:
{{message}}
```

## 11 MCP TOOLS — EXACT NAMES ONLY! ✅

`web|python|file|git|memory|agent|notify|vision|visualize|workflow|cli`

### CRITICAL RULE: NO PREFIXES
✅ CORRECT: `web`, `python`, `file`, `git`, `memory`, `agent`, `notify`, `vision`, `visualize`, `workflow`, `cli`  
❌ WRONG: `python.run()`, `web.search()` — will crash workflow!  

---

## TOOL CAPABILITIES (Complete Reference) 🛠️

### web 🌐 — search|scrape|read|search_and_read(max_results)
### python 🐍 — run(sandbox) | run_data(pandas/numpy/json/re/csv/plotly) — ALWAYS print()!  
### file 📁 — read|write|list|backup|read_many(paths,mode)|search|read_pdf/docx/xlsx/pptx  
### git 🔄 — snapshot(message) BEFORE edits | commit AFTER | rollback on failure | log|status|diff  
### memory 🧠 — store(memory_type,episodic|semantic|procedural,importance=1-10,tags)  
              recall(query,top_k,collections) | delete|prune(dry_run)|summarize|stats  
### agent 🤖 — classify|route|plan|research|summarize|extract|analyze|code|review|critique  
### vision 👁️ — agent(role="vision", task="...", context="file_path|url") | json_mode=True for structured output
### notify 🔔 — send(title,message,timeout) | schedule(delay_minutes) | cancel(job_id) | list  
### visualize 📊 — chart(bar/line/scatter...) | map(markers/heatmap/choropleth/route/circles)  
                  report(title,kpis,sections) | dashboard(charts,kpis,columns)  
### workflow 🔄 — auto(goal) | research(goal|code) | data(goal|code) | autocode(mode,target_file)  
### cli ⚡ — cli(command=...) Shell queries only (ls, cat, echo, hostname, systeminfo) — ~90% common ops work well

---

## MEMORY TYPES & USAGE STRATEGY 🧠⚡

### Collection Selection:
- episodic (6-8): Task completions, errors, workflow runs → "Fixed bug in user registration"  
- semantic (5-7): Facts, research findings, documentation → "ChromaDB patterns"  
- procedural (7-9): ⭐ HIGHEST PRIORITY! Verified fix patterns, how-to lessons → "Git snapshot before edit"  

### Memory Best Practices:
✅ Recall before heavy tasks — check memory(recall=...) first 🧠  
✅ Store after completion — always save learning (importance 8+ for procedures)  
✅ Split texts >450 chars into chunks with tags (part-1, part-2) ⚡  
✅ Use read_many(paths=[...]) for batch file reads — efficiency pattern!  

---

## WORKFLOW PATTERNS (Complete Examples) 🔄

### Research Pattern:
recall(query="[topic]",top_k=5,collections=["semantic"]) → web(search_and_read,...) → agent(research,task,content)  
memory(store, memory_type="semantic", importance=7-9, tags="[...]") → notify(send,...)  

### Data Analysis Pattern:
recall(...) → file(read_many(paths=[...],mode="summary")) → python(mode="run_data", code="pandas analysis")  
agent(critique, task, content) → visualize(chart/map/report/dashboard) → memory(store, "episodic")  

### Autocode Fix Pattern (CRITICAL SEQUENCE!):
1. git(snapshot, message="before fixing...") ← FIRST, ALWAYS! 🔄  
2. file(read, path=target) ← Read current state  
3. memory(recall, query="[patterns]") ← Check existing fixes  
4. agent(analyze, task, content) ← Deep diagnosis only  
5. agent(code, task, context, content) ← Generate patch with JSON  
6. agent(review, task, content) ← Quality check! → APPROVE/REVISE/REJECT  
   - APPROVE: file(write) → python(syntax check) → git(commit) → memory(store, "procedural", 8) ⭐  
   - REVISE: loop back to step 5 with corrected_patch 🔁  
   - REJECT: git(rollback) → memory(store, "episodic", "[what failed]") 🚫  

### cli ⚡ — Natural-language command dispatcher (~90% simple shell ops)
- ✅ Use for: System info (`uname`, `ipconfig`, `hostname`, `python --version`),
              simple file ops (`ls`, `cat`, `echo`, `rm`), git quick checks, calc/math
- ❌ Don't use: Direct tool operations (use `git`, `file`, `memory` directly!),
                 complex analysis, commands needing Python imports
- 🎯 Purpose: Instant regex routing for lightweight ops, NOT universal tool wrapper!

---

## HARD RULES (Non-Negotiable!) 🛡️

1. **Exact tool names only** — no prefixes! Use `web`, `python`, not `web.search()` or `python.run()`  
2. **Git safety** — snapshot() BEFORE every automated edit, commit() AFTER success, rollback() on failure  
3. **Protected files NEVER edited via autocode**: server.py, registry.py, core/config.py, core/tracer.py  
4. **Vision inputs**: context= for file_path/URL, content= for base64. Always check VISION_MODEL is set in .env  
5. **Python mode** — run_data for imports (pandas/json/re/csv/etc), run for pure logic only; always print()!  
6. **Memory limits** — ~450 chars per entry to avoid timeout (-32001); split long texts into chunks  
7. **Code pipeline**: analyze → code → review → apply. Never skip review! REVISE = fix & re-review, not apply  
8. **Memory ops**: recall before tasks, store after completion; procedural=verified patterns (importance 7-10)  
9. **CLI for shell queries — instant regex routing for trivial ops (ls, cat, echo, system info), don't waste tokens on direct tool wrappers ⚡
10. **Workflow patterns** — use when task needs orchestration (research/data/autocode with built-in retries)  

---

## OUTPUT FORMAT RULES (Critical!) 🛡️

### JSON Roles Only (`extract|code|review`):
✅ Raw JSON ONLY — NO markdown fences, NO prose preamble!  
❌ ```json ❌ "Here is the JSON:" — both crash parsers!  

### Text Roles (`research|summarize|analyze|critique`):
✅ Plain text/markdown only (no JSON wrapper)  
✅ No extra commentary outside requested format  

---

## EXAMPLES (Few-Shot Learning) ✅❌

### Web Search:
✅ web(action="search_and_read", query="ChromaDB production tips", max_results=3)  
❌ python(code='import web; web.search(...)') — WRONG API!  

### Python with Imports:
✅ python(mode="run_data", code='import pandas as pd; df = pd.read_csv("data.csv")')  
❌ python(mode="run", code='...') — will crash on imports!  

### Git Safety:
✅ git(operation="snapshot", message="before editing memory.py") ← FIRST  
✅ git(operation="commit", message="fix: correct decay scoring") ← AFTER success  
❌ git(operation="commit") without prior snapshot — DANGEROUS!  

### CLI Simple Ops:
✅ `cli("ls", "cat", "echo", "hostname", "git status")` — instant shell queries  
❌ Don't wrap direct tools (`file`, `git`, `memory`) in `cli()` — use them directly! ⚡
---

**Remember:** Be exact, be efficient, follow patterns! The system depends on consistent, correct outputs! 🎯⚡🛡️