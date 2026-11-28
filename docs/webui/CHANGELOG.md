<- Back to [WebUI Overview](../WEBUI.md)

# 🗺️ WebUI Changelog

> Version history for the Brazilian Financial Data WebUI — one short
> summary per version, the major points only.
>
> **[v1.20] Format:** topic summaries; the full engineering detail of
> every version lives in its commit (git log).
>
> **[v1.28.4] Condensed** — the per-version essays became one-liners
> (the old rows had grown to multi-paragraph essays; the CHANGELOG is
> an index, not a history book). The former forward-looking section is
> gone too — [ROADMAP.md](ROADMAP.md) owns the future.

---

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.28.5** | 2026-11-28 | **THE BACKTEST EXIT-FIX + CARTEIRA CORP ROUND.** Backtest: the "Saída por sinal" thresholds now render **below** the "Sair quando o sinal reverter" checkbox and obey it (they sat above the toggle, inert — "abaixo" pointed at nothing), and the Trade Log carries the **pairing audit line** (every entrada has its saída; a leftover position is force-closed at the last close as "fim do período"). Carteira: the corp form shows **only the event fields** (quantidade/preço/taxas ocultos), plus two new corporate actions — **🔀 Inplit** (grupamento com troca de ticker, RAIZ4 → RAIZ55: qty ×= fator, PM ÷= fator, a posição migra com o **custo total e o patrimônio intactos**; fator 1 = renomeação pura) and **🔔 Direitos de subscrição** (direitos recebidos de graça a PM R$ 0,00 — vender ao mercado realiza 100%; **venda a R$ 0,00** agora é válida como vencimento sem valor em posições sem custo, e continua recusada em posições com custo ou além da quantidade). Engine, ladder, IR walk, proventos e ledger atualizados em conjunto (as duas caminhadas nunca discordam). |
| **v1.28.4** | 2026-11-27 | **THE CROSS-TOOL ROUND.** The 🎯/⏪/⚖ links between the Ferramentas (every comparison column card + the screener head carry "abrir no Screener" / "simular no Backtest" / "comparar" — the analysis flow continues without retyping); the Screener's **Posição** column (the subject's rank per metric inside the sector, "P/L: 12º de 38", 1º in green); the sector-table **range filters** (P/L · Div Yield % · Market Cap R$ bi, min–max, the ✓ re-ranking inside the filtered set, the ★ subject always visible); **📋 copiar resumo** (the verdict table as markdown in the clipboard); the Comparação's **Mediana do Setor** column (every grid row against the sector median — its own cached payload filling progressively so the grid renders instantly); and **Cancelar** on the Comparação and BOTH Backtest loads (meta + run). Also: the ROADMAP pruned to future-work-only and this CHANGELOG condensed. |
| **v1.28.3** | 2026-11-27 | **THE PAINEL SETTINGS ROUND.** The ⚙️ Gerenciar Painel box manages THREE sets: the macro KPI cards (the 19-key catalog incl. the Mercado families), the ticker KPI cards (any share-like instrument — ações, FIIs, ETFs, BDRs — reading in three horizontal bands: header + full-width 52-week chart + stats rows) and the ranking boxes (reorder/hide, incl. the new Maiores Quedas BDR). The ⭐ observados managed IN the Painel (with Mín/Máx 52 sem), and the Ações 22-range price color pill on every MAIN price (Painel, observados, carteira, comparison, screener). |
| **v1.28.2** | 2026-11-26 | **THE STABILITY ROUND** (the self-review of the Ferramentas trio): stale-response guards on the three loaders (ticker A's late answer can never overwrite B's), the Screener's Cancelar (kills the wait, not the work — the server keeps caching), the SIGNED median delta (the ratio formula's sign flipped on negative medians), the vs Setor heat, the missing-last Segmento sort, the log's thread-safe tee + date line, and the Painel's BDR/ETF data-layer fix (BDRs reach the DB + the quote universe). |
| **v1.28.1** | 2026-11-26 | **THE FERRAMENTAS POLISH ROUND + THE VISIBLE LOG.** The Backtest tool MOVES to Ferramentas; the Screener's table sorts (every header, missing last, best-per-column ✓); the Painel's ETF row + BDR risers; the 📜 drawer's HTTP/App filters + the terminal tail. |
| **v1.28** | 2026-11-26 | **FERRAMENTAS — SCREENER:** one ticker × its WHOLE sector (the PETR4_screener_dashboard concept expanded): the median KPI row, the sector table (one class per company, the subject highlighted), the position charts (P/L and ROE bars, the subject in amber, the median dashed) and the Meu Valor × Mediana verdict table — cheap/cara for multiples, acima/abaixo for quality, positive-only medians. |
| **v1.27** | 2026-11-26 | **FERRAMENTAS — THE NEW MAIN TAB + COMPARAÇÃO** (its first tool): analysis utilities get their own home; up to 4 tickers side by side, every grid row ranked (✓ best of the line), the Cotação Histórica cards, performance + normalized-price charts. |
| **v1.26.1** | 2026-11-25 | **COMPANY PAGE — the user's ten-item fixes & tweaks list:** single-series charts drop their legends, the price histogram highlights the current bar (theme-aware), Financeiro payloads cached (the webui_payloads fingerprint table — ~1ms ⚡ hits), Múltiplos Menos Comuns as a heatmap, share-class-correct DPA, the Proventos × IPE cross-reference, Insiders' cargo/tipo pills + Por Tipo. |
| **v1.26** | 2026-11-30 | **GOVERNANÇA + INFORMAÇÕES PERIÓDICAS — TWO CVM SOURCES, TWO TABS:** CGVN (the self-assessment scores, the 54-practice table) and IPE (the faceted event explorer — Categoria/Tipo/Espécie/Ano, chips, busca, CVM links). |
| **v1.25** | 2026-11-29 | **BACKTEST — THE INTERACTIVE SIMULATOR** (the company page's 10th tab, later moved to Ferramentas): 8 strategies with editable thresholds, engine params (capital, % posição, prazo, stop/take, corretagem), KPIs + equity × buy&hold + drawdown + trade log, and the Cenários manager (pin, compare, load-params-back). |
| **v1.24** | 2026-11-29 | **COMPANY HISTORICAL — THE HISTÓRICO TAB:** the company vs its OWN 5A history (the heatmap, the band charts, rentabilidade/crescimento, alavancagem + point-in-time WACC/DuPont/Altman) — "vs o setor" → "vs ela mesma". |
| **v1.23** | 2026-11-27 | **POUPANÇA + THE MATRIX-FIRST CONVENTION:** the last DDM indicator gets its Mercado family (the caderneta vs IPCA/CDI comparison the static never drew), and the per-index views get the ano×mês matrix ABOVE the histórico mensal. |
| **v1.22.4** | 2026-11-26 | **THE USER-REPORT WAVE:** the evolução 500 (a sign-flipped TWR chain annualizing into a complex number) killed, the ticker filter a prefix with suggestions, notas importadas into the Transações view, the company header's five-step setor fallback, BR month ticks + the IVVB11 benchmark on evolução, corp-event form flow, the 🔍 drawer's ✏️ edit, proventos × DDM agenda merge. |
| **v1.22.3** | 2026-11-25 | **THE WHOLE MONEY ROADMAP — six items:** 🔀 eventos corporativos (splits/grupamentos/bonificações replayed first-in-date, both walks), 🪙 proventos per position + yield-on-cost (the DATA COM entitlement rule), 📈 evolução (patrimônio curve, TWR/XIRR vs CDI/IBOV/IVVB11), 🥧 alocação (setor/ticker weights, HHI, alertas, the what-if simulator), transações as a paginated/filtered view + undo registry, engine perf/precision (threadpool mutations, revision-memoized replays, fsum aggregates). |
| **v1.22.2** | 2026-11-24 | **THE ONBOARDING KILLER FEATURE + THE TAX MAN:** nota de corretagem PDF import (XP ×2 layouts, modelo B3, BTG — dry-run preview, hand-map, atomic commit with dedup, ↩️ undo) and the 🧾 IR helper (swing × day-trade split, the R$ 20k exemption, loss carry pools, IRRF, DARF 6015/6120). |
| **v1.22.1** | 2026-11-24 | **WAVES 3–5 of the adversarial review:** the syslog↔settings lock ordering, the docs truth pass, and the regression suite (`tests/webui/` — the money engine never gets touched without it). |
| **v1.22** | 2026-11-24 | **HARDENING — the adversarial-review wave:** shorts count in the totals, CSRF guard on every router, NaN/±inf rejected at the boundary, the store's reconcile-then-write posture. |
| **v1.21** | 2026-11-23 | **CARTEIRA — THE PORTFOLIO:** múltiplos usuários → contas → transações, PM brasileiro (compras embutem taxas; vendas realizam e não alteram o PM), the ⭐ watchlist, quick ✅/❌ per position. |
| **v1.20** | 2026-11-23 | **SYSTEM LOG DRAWER + SETTINGS AS DATA:** the 📜 live request/sync/error tail on every page, and the schema-driven settings form (one dict entry = a new setting, no dead knobs). |
| **v1.19** | 2026-11-22 | **PAINEL — THE LANDING REDESIGN:** the Brazil one-screen home — SGS KPI row + ranked ticker cards, every row a company-page link. |
| **v1.18** | 2026-11-22 | **MERCADO — PROVENTOS FAMILY + the stocks_history startup self-heal** (the BDR split: the *34 twin on the same scale). |
| **v1.17** | 2026-11-22 | **MERCADO — AÇÕES FAMILY + the evolution store** (the 22-range distribution over time, 100% stacked). |
| **v1.16** | 2026-11-22 | **MERCADO — JUROS FAMILY** (Selic/Meta/CDI compared + per-rate history + the ano×mês heatmap). |
| **v1.15** | 2026-11-22 | **MERCADO — INFLAÇÃO FAMILY** (IGP-M/IPCA/INPC, the matrix-first convention's seed). |
| **v1.14** | 2026-11-22 | **MERCADO — ÍNDICES FAMILY** (compositions + the cross-index presença matrix; skill format fixes at source). |
| **v1.13** | 2026-11-22 | **MERCADO — FLUXO FAMILY** (the stacked daily + the accumulated compared; the `mercadoLoader(family)` factory). |
| **v1.12** | 2026-11-22 | **MERCADO PAGE + FOCUS FAMILY** (the DDM dashboards' new home; Focus regrouped into 6 question-driven subtabs). |
| **v1.11** | 2026-11-22 | **MACRO PAGE** (the static macro dashboard reorganized: lazy subtabs + the ticker-less generic endpoint). |
| **v1.10** | 2026-11-21 | **INSIDERS TAB** (sentiment KPIs, net volume, Por Cargo/Mensal; the prefix-matching role aggregation fix). |
| **v1.9** | 2026-11-21 | **ACIONISTAS TAB** (posição acionária, free float, estrutura patrimonial). |
| **v1.8** | 2026-11-21 | **OPÇÕES TAB** (P/C + OI walls, the chain, vol implícita, posições; BR date formatting fixed). |
| **v1.7.2** | 2026-11-21 | **VALUATION MÚLTIPLOS PARITY** (per-group 5Y charts + the range bar on every múltiplos subtab). |
| **v1.7.1** | 2026-11-21 | **QUARTERLY BALANÇOS FIX + DRE WATERFALL** (ITR point-in-time re-keyed — quarterly balanços stopped showing annual values). |
| **v1.7** | 2026-11-21 | **ADAPTER CONTRACT + PRE-FLIGHT CHECKS** (the `<family>:<sub>` registry behind one generic endpoint per scope — the plumbing the feature wave rode). |
| **v1.6** | 2026-11-20 | **PROVENTOS TAB** (histórico, visão geral, anual — dividends, JCP, rendimentos, bonificações, desdobramentos). |
| **v1.5** | 2026-11-19 | **HARDENING — the multi-LLM review round** (~50 findings triaged: pctVs sign, tz-aware freshness, reflected-XSS closed, loopback-only default). |
| **v1.4** | 2026-11-19 | **VALUATION TAB** (Visão Geral, Múltiplos, Valor Intrínseco — DCF + TIR + sensitivity, Fundamentos, todas as métricas). |
| **v1.3** | 2026-11-18 | **FINANCEIRO TAB** (REAL TTM resultado, the 10-year trajectory, all 5 demonstrações). |
| **v1.2** | 2026-09-16 | **PREÇO TAB** (OHLCV candlestick + MMs, zoom/pan; 5 lazy subtabs incl. RSI/MACD, Bollinger, Fibonacci). |
| **v1.1** | 2026-09-16 | **COMPANY PAGE RESTRUCTURE** (the persistent identity header + Visão Geral; search relevance fix). |
| **v1** | 2026-09-16 | **INITIAL VERTICAL SLICE** (`python webui.py` — one process, one port; service layer over the skill engines, vendored JS, SSE sync, the 3-layer theme system). |
