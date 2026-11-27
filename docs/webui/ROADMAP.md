<- Back to [WebUI Overview](../WEBUI.md)

# 🗺️ WebUI Roadmap

> What's next for the Brazilian Financial Data WebUI — **open work
> only**.
>
> **[v1.28.4] Pruned** — everything shipped lives in the
> [CHANGELOG](CHANGELOG.md) (one topic summary per version); the
> per-feature essays and the struck-through shipped items are gone.
> The app today, in one breath: **Painel** (the landing) · **Carteira**
> (portfolio — notas PDF, IR, proventos, evolução, alocação) ·
> **company pages** (12 tabs, Histórico → Backtest) · **Macro** ·
> **Mercado** (8 families) · **Ferramentas** (Comparação · Screener ·
> Backtest, cross-linked) · **Sincronização** · **Configurações** ·
> the 📜 system-log drawer. The architecture lives in
> [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 🔄 Next Up

### Polish
- [ ] **Theme accent color** — user-selectable accent (teal, blue, violet, orange) via CSS variable override; pairs naturally with the v1.20 settings schema.
- [ ] **i18n honesty pass** — externalize app.js strings via a `window.I18N` dump OR document pt-BR as the content language and keep en-US for the shell.
- [ ] **Accessibility** — `role=tab`/`aria-selected` on tab buttons, aria-labels on charts, keyboard nav on the search dropdown.
- [ ] **Mobile** — sidebar hamburger (the sidebar renders open and squeezes content on every page at 390px today), `overflow-x` on wide tables, touch pan on charts.

### Export
- [ ] **Download report** — "Download as HTML" on each company page (reuse `build_dashboard()`).
- [ ] **Export to Excel** — export ratios table to .xlsx.

---

## 🔮 Planned (v3)

### Agent Integration
- [ ] **Agent chat tab** — embedded chat using the existing `/chat` + `/ws` endpoints.
- [ ] **Task history** — recent agent tasks with status + result preview.

### Polish
- [ ] **Multiple themes** — solarized, midnight, high-contrast.
- [ ] **ES (Spanish) locale** — third language.
- [ ] **Keyboard shortcuts** — `/` to focus search, `g d` to go to dashboard.
- [ ] **Loading indicators** — HTMX `hx-indicator` spinners on all async requests.
- [ ] **Error toasts** — non-blocking error notifications.

---

## 🚫 Deferred / Out of Scope

- **User authentication / multi-user** — the WebUI is a local single-user tool. The gateway's Bearer token is sufficient.
- **Real-time price streaming** — prices are daily (COTAHIST). Poll on page load; don't build a real-time feed.
- **Custom chart builder** — Chart.js with predefined configs is enough.
- **Plugin system** — the page registry is a simple list of dicts. Don't build one until there are 5+ toolset pages.
- **Offline PWA** — the Python server must run; don't build a Progressive Web App.
- **Persistent log file** — the system log is an in-memory tail by design (what happened since boot). A rotating file is a `logging` config change, not a WebUI feature.
