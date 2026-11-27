/* webui/static/js/app.js — client-side app logic.
 *
 * [WebUI v1.5 — HARDENING] Handles:
 *   - Candlestick chart (OHLCV + MM20/50/100/200) with zoom/pan — ticker first in legend
 *     (wheel zoom requires Ctrl — plain scroll now pans the page, not the chart)
 *   - Preço tab: Cotação tables + Histograma + Início vs Fim (5 LAZY subtabs)
 *   - Indicadores subtab: RSI, MACD, Stochastic, OBV, ADX, CCI, Williams %R
 *   - Volatilidade subtab: Bollinger Bands + rolling vol
 *   - Financials: Visão Geral (TTM + Trajetória + WACC/DuPont/Altman + Red Flags)
 *     and Demonstrações (single fetch, merged Completo BPA+BPP, per-statement
 *     charts — Ativo and Passivo+PL composition charts are SEPARATE now:
 *     the old 5-series stack mixed both balance sides and halved every %)
 *   - Valuation: 5 lazy subtabs, generic section renderer (v1.4)
 *   - Sync page: native EventSource live log + "Sincronizar" buttons (the
 *     old hx-ext="sse" markup never worked — the HTMX SSE extension was
 *     never vendored)
 *
 * v1.5 fixes (multi-LLM review round):
 *   - pctVs sign inversion fixed (Preço "vs" columns showed the WRONG sign
 *     and contradicted the Variação row two rows apart)
 *   - zero renders YELLOW everywhere (% positive green / negative red / 0 yellow)
 *   - fmtBRL has thousands separators (Intl.NumberFormat pt-BR)
 *   - esc() on every innerHTML interpolation of server data (XSS)
 *   - Chart.js destroy on htmx:beforeCleanupElement + before re-renders (leak)
 *   - loadCandlestick errors render in a SIBLING node (the old path deleted
 *     the canvas — one error killed the chart until reload) + AbortController
 *   - Lazy subtabs: only the active one fetches (was 5 eager 10y fetches)
 *   - includeScriptTags hack REMOVED (company page bootstraps from data attrs)
 */

// Register Chart.js zoom plugin
if (typeof Chart !== 'undefined' && typeof ChartZoom !== 'undefined') {
  Chart.register(ChartZoom);
}

// ── Helpers ──
function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
// [v1.22.1] fmtDate/fmtMonth: the NON-matching fallthrough used to
// return the raw string — every call site is a Chart.js canvas callback
// today (no HTML), but one future use in an innerHTML template would
// turn a crafted label into markup. The fallthrough now escapes.
function fmtDate(iso) { return iso && iso.match(/^\d{4}-\d{2}-\d{2}$/) ? iso.slice(8)+'/'+iso.slice(5,7)+'/'+iso.slice(0,4) : esc(iso); }
// [v1.15] ISO month "2026-07" → "jul/2026" (same short PT-BR month form
// the tables use — sortable by _valSortKey, readable on the x-axis).
var _MONTH_NAMES = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
function fmtMonth(iso) {
  var m = iso && iso.match(/^(\d{4})-(\d{2})$/);
  if (!m) return esc(iso);   // [v1.22.1] escaped fallthrough (fmtDate)
  var i = Number(m[2]) - 1;
  return (i >= 0 && i < 12 ? _MONTH_NAMES[i] : m[2]) + '/' + m[1];
}

// [v1.5] One pt-BR BRL formatter with thousands separators ("R$ 1.234,56").
var _brlFmt = null;
function fmtBRL(v) {
  if (v === null || v === undefined) return '—';
  if (!_brlFmt) _brlFmt = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return 'R$ ' + _brlFmt.format(Number(v));
}

// [v1.5] HTML-escape for EVERY server-provided string that lands in
// innerHTML (error messages, labels, tickers). Was valEsc (valuation-only).
function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
var valEsc = esc;  // legacy alias (v1.4 renderer name)

// [v1.22.1] safeColor (the minimax latent-XSS one-liner): heatmap cell
// colors come from the server payload straight into a style attribute —
// only well-formed color VALUES pass (hex / rgb() / hsl() / a short bare
// CSS name); anything carrying a quote, semicolon, paren-with-letters
// (url(...), expression(...)) falls back, so a crafted payload can never
// break out of the attribute.
var _SAFE_COLOR_RE = /^(#[0-9a-fA-F]{3,8}|rgba?\(\s*[\d.,\s%]+\s*\)|hsla?\(\s*[\d.,\s%]+\s*\)|transparent|inherit|initial|currentcolor|[a-z]{1,20})$/;
function safeColor(v, fb) {
  v = String(v === null || v === undefined ? '' : v).trim().toLowerCase();
  return _SAFE_COLOR_RE.test(v) ? v : (fb || 'transparent');
}

function chartTheme() { return { grid: cssVar('--chart-grid') || 'rgba(128,128,128,0.1)', text: cssVar('--chart-text') || '#888' }; }

// [v1.5] Shared range map (was duplicated ×4 with drift).
var RANGE_DAYS = { '1M': 21, '3M': 63, '6M': 126, '1A': 252, '5A': 1260, '10A': 2520, 'Tudo': 0 };

// [v1.5] Destroy every Chart.js instance under root (leak fix — Chart
// keeps resize observers + rAF loops alive after the canvas is detached).
function destroyChartsIn(root) {
  if (!root) return;
  var nodes = root.querySelectorAll ? Array.prototype.slice.call(root.querySelectorAll('canvas')) : [];
  if (root.tagName === 'CANVAS') nodes.push(root);
  nodes.forEach(function(cv) {
    if (cv._chart) { try { cv._chart.destroy(); } catch (e) { /* noop */ } cv._chart = null; }
  });
}

// ── Candlestick chart ──
// [v1.5] Range buttons are data-driven (tab_visao_geral.html renders
// #price-range-bar; one delegated listener in initApp dispatches here —
// the old inline onclick="loadCandlestick('{{ ticker }}',…)" interpolated
// the ticker into a JS-in-attribute context).
var _candleAbort = null;
window.loadCandlestick = function(ticker, range) {
  var canvas = document.getElementById('price-chart');
  if (!canvas) return;
  var bar = document.getElementById('price-range-bar');
  (bar || document).querySelectorAll('.range-btn').forEach(function(btn) { btn.classList.toggle('active', btn.dataset.range === range); });
  var wrap = document.getElementById('price-chart-wrap') || canvas.parentElement;
  var msg = document.getElementById('price-chart-msg');
  if (msg) msg.innerHTML = '';
  if (wrap) wrap.style.opacity = '0.5';
  // [v1.5] Abort the previous range fetch — a slow 1M response used to be
  // able to overwrite a newer 5A one (last-write-wins race).
  if (_candleAbort) { try { _candleAbort.abort(); } catch (e) { /* noop */ } }
  _candleAbort = (typeof AbortController !== 'undefined') ? new AbortController() : null;
  fetch('/api/webui/company/' + encodeURIComponent(ticker) + '/candlestick?range=' + encodeURIComponent(range),
        _candleAbort ? { signal: _candleAbort.signal } : undefined)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (wrap) wrap.style.opacity = '1';
      // [v1.5] Errors render in the SIBLING #price-chart-msg node. The old
      // path did container.innerHTML = …, DELETING the canvas — after one
      // error every later range click found no #price-chart until reload.
      var text = data._error || (!data.labels || data.labels.length === 0 ? 'Sem dados de cotação.' : '');
      if (text) {
        if (msg) msg.innerHTML = '<div class="error">' + esc(text) + '</div>';
        return;
      }
      renderCandlestick(canvas, ticker, data);
    })
    .catch(function(err) {
      if (err && err.name === 'AbortError') return;
      if (wrap) wrap.style.opacity = '1';
      if (msg) msg.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
};

function renderCandlestick(canvas, ticker, data) {
  if (canvas._chart) canvas._chart.destroy();
  var th = chartTheme();
  var UP = '#22c55e', DOWN = '#ef4444';
  var ohlc = data.ohlc || [];
  var bodyData = data.body_data || [];
  var maColors = { MA20: '#facc15', MA50: '#fb923c', MA100: '#ec4899', MA200: '#ef4444' };

  // Ticker dataset FIRST (so it appears first in legend), then MAs
  var tickerDataset = {
    type: 'bar', label: 'Preço', data: bodyData,
    backgroundColor: function(ctx) { var d = ohlc[ctx.dataIndex]; return d ? (d.c >= d.o ? UP : DOWN) : UP; },
    borderColor: function(ctx) { var d = ohlc[ctx.dataIndex]; return d ? (d.c >= d.o ? UP : DOWN) : UP; },
    borderWidth: 0, barPercentage: 0.7, categoryPercentage: 1.0, order: 3
  };
  var maDatasets = ['ma20', 'ma50', 'ma100', 'ma200'].map(function(key) {
    var label = key.toUpperCase();
    return { type: 'line', label: label, data: data[key] || [], borderColor: maColors[label], borderWidth: 1.5, pointRadius: 0, tension: 0, fill: false, spanGaps: true, order: 1 };
  });

  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: { labels: data.labels, datasets: [tickerDataset].concat(maDatasets) },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { grid: { color: th.grid }, ticks: { color: th.text, maxTicksLimit: 10, callback: function(v) { return fmtDate(this.getLabelForValue(v)); } } },
        y: { grid: { color: th.grid }, ticks: { color: th.text, callback: function(v) { return 'R$ ' + Number(v).toFixed(2).replace('.', ','); } }, title: { display: true, text: 'Preço (R$)' } }
      },
      plugins: {
        legend: { display: true, position: 'top' },
        tooltip: { callbacks: {
          label: function(ctx) { var d = ohlc[ctx.dataIndex]; if (!d) return ''; if (ctx.dataset.type === 'line') return ctx.dataset.label + ': R$ ' + Number(ctx.parsed.y).toFixed(2).replace('.', ','); return ticker + ' | O: ' + fmtBRL(d.o) + ' H: ' + fmtBRL(d.h) + ' L: ' + fmtBRL(d.l) + ' C: ' + fmtBRL(d.c); },
          title: function(i) { return fmtDate(i[0].label); }
        }},
        zoom: { pan: { enabled: true, mode: 'x', modifierKey: 'shift' }, zoom: { wheel: { enabled: true, speed: 0.1, modifierKey: 'ctrl' }, pinch: { enabled: true }, mode: 'x' } }
      }
    },
    plugins: [{ id: 'candleWicks', beforeDatasetsDraw: function(chart) {
      var meta = chart.getDatasetMeta(0); if (!meta || !meta.data) return;
      var ctx = chart.ctx; ctx.save(); ctx.lineWidth = 1;
      for (var i = 0; i < meta.data.length; i++) { var bar = meta.data[i]; if (!bar) continue; var d = ohlc[i]; if (!d) continue;
        var x = bar.x; ctx.strokeStyle = d.c >= d.o ? UP : DOWN; ctx.beginPath(); ctx.moveTo(x, chart.scales.y.getPixelForValue(d.h)); ctx.lineTo(x, chart.scales.y.getPixelForValue(d.l)); ctx.stroke(); }
      ctx.restore();
    }}]
  });
  canvas._chart._ohlc = ohlc;
}

// ── Preço tab (Cotação subtab) ──
window.initPrecoTab = function(ticker) {
  // [v1.5 fix1] id renamed tab-preco → tab-cotacao (the pane follows the
  // tab-<sub> convention now; loadPrecoSubtab('cotacao') looked up
  // 'tab-cotacao' and silently no-opped → "Carregando…" forever).
  var tab = document.getElementById('tab-cotacao'); if (!tab) return;
  fetch('/api/webui/company/' + encodeURIComponent(ticker) + '/price-data?_t=' + Date.now()).then(function(r) { return r.json(); }).then(function(data) {
    if (data._error) { tab.innerHTML = '<div class="error">Erro: ' + esc(data._error) + '</div>'; return; }
    renderPrecoTab(tab, ticker, data);
  }).catch(function(err) { tab.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>'; });
};

function renderPrecoTab(tab, ticker, data) {
  var snap = data.snapshot || {}; var pr = data.period_returns || []; var ar = data.annual_returns || []; var hist = data.histogram || {};
  var html = '<div class="preco-grid">';
  html += '<div class="reg-table"><div class="reg-title">Geral</div><table class="price-table">';
  html += priceRow('Fechamento Anterior', snap.prior_close, pctVs(snap.prior_close, snap.current));
  html += priceRow('Abertura', snap.open, pctVs(snap.open, snap.current));
  html += priceRow('Atual', snap.current, null);
  html += '</table></div>';
  html += '<div class="reg-table"><div class="reg-title">Dia</div><table class="price-table">';
  html += priceRow('Variação (dia)', snap.daily_diff, snap.daily_pct);
  html += priceRow('Mínima (dia)', snap.intraday_low, pctVs(snap.intraday_low, snap.current));
  html += priceRow('Máxima (dia)', snap.intraday_high, pctVs(snap.intraday_high, snap.current));
  html += priceRow('Amplitude (dia)', snap.intraday_range, snap.intraday_range_pct);
  html += '</table></div>';
  html += '<div class="reg-table"><div class="reg-title">Range 52 Semanas — Mínima</div><table class="price-table">';
  html += priceRow('Mínima 52s', snap.low_52w, pctVs(snap.low_52w, snap.current));
  html += priceRow('Da Mínima', snap.from_52w_low, snap.from_52w_low_pct);
  html += '</table></div>';
  html += '<div class="reg-table"><div class="reg-title">Range 52 Semanas — Máxima</div><table class="price-table">';
  html += priceRow('Máxima 52s', snap.high_52w, pctVs(snap.high_52w, snap.current));
  html += priceRow('Até a Máxima', snap.to_52w_high, snap.to_52w_high_pct);
  html += '</table></div>';
  html += '<div class="reg-table"><div class="reg-title">Performance por Período</div><table class="price-table">';
  pr.forEach(function(p) { html += pctRow(p.label, p.return_pct); });
  html += '</table></div>';
  html += '<div class="reg-table"><div class="reg-title">Oscilações Anuais</div><table class="price-table">';
  ar.slice().reverse().forEach(function(a) { html += pctRow(String(a.year), a.return_pct); });
  html += '</table></div>';
  html += '</div>';
  if (hist && hist.bins) { html += '<div class="chart-section" style="margin-bottom: var(--space-5);"><div class="chart-header"><div class="reg-title">Histograma de Preço</div></div><div class="chart-container"><canvas id="histogram-chart"></canvas></div></div>'; }
  if (ar && ar.length > 0) { html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">Início vs Fim</div></div><div class="chart-container"><canvas id="inicio-fim-chart"></canvas></div></div>'; }
  tab.innerHTML = html;
  if (hist && hist.bins) renderHistogram(hist, snap.current);
  if (ar && ar.length > 0) renderInicioFim(ar);
  // Close preco-charts div if it was opened
  // (already closed in the HTML above)
}

function priceRow(label, value, pct) { return '<tr><td>' + label + '</td><td class="val">' + fmtBRL(value) + '</td><td class="pct">' + fmtPctColored(pct) + '</td></tr>'; }
function pctRow(label, pct) { return '<tr><td>' + label + '</td><td class="val" colspan="2">' + fmtPctColored(pct) + '</td></tr>'; }
function pctVs(v, current) { if (v === null || v === undefined || current === null || current === undefined || v === 0) return null; return (current - v) / v; }
// [v1.5] pctVs FIXED — it returned (v − current)/current, i.e. the NEGATIVE
// daily change (a stock up 10% showed −9,09% in red two rows above a green
// +10% "Variação"). Now: change FROM the reference v TO current, divided by
// the reference — the standard convention.
function fmtPctColored(v) { if (v === null || v === undefined || isNaN(v)) return '<span class="muted">—</span>'; var pct = (v * 100).toFixed(2).replace('.', ',') + '%'; var color = v < 0 ? 'var(--color-danger)' : (v > 0 ? 'var(--color-success)' : 'var(--color-warning)'); return '<span style="color: ' + color + '">' + pct + '</span>'; }
// [v1.5] Zero renders YELLOW now (v1.4 spec: % positive green / negative
// red / zero yellow) — it was green, contradicting the Valuation tab.

function renderHistogram(hist, currentPrice) {
  var canvas = document.getElementById('histogram-chart'); if (!canvas) return; var th = chartTheme();
  if (canvas._chart) canvas._chart.destroy();
  // [v1.26.1] The bar holding the CURRENT price gets an outline —
  // the user asked to see where today's price sits inside the 10-year
  // distribution without a second series or an annotation. Bins carry
  // their [low, high] range, so the match is a simple containment scan
  // (the last matching bin wins: the top bin's high is the series max).
  // [v1.26.1 fix1] The outline is THEME-AWARE now: the v1.26.1 fixed
  // #ffffff vanished against the light theme's white background. The
  // theme's --text token (near-white on dark / near-black on light —
  // same cssVar mechanism the rest of the chart theming uses) keeps the
  // approved dark look AND stays high-contrast on the light theme,
  // against every bin color (blue→yellow→red).
  var hiIdx = -1;
  if (currentPrice !== null && currentPrice !== undefined && isFinite(Number(currentPrice))) {
    var cp = Number(currentPrice);
    for (var i = 0; i < hist.bins.length; i++) {
      var b = hist.bins[i];
      if (cp >= (b.low || 0) && cp <= (b.high || 0)) hiIdx = i;
    }
  }
  var hlColor = cssVar('--text') || th.text || '#ffffff';
  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: { labels: hist.bins.map(function(b) { return b.label; }), datasets: [{ label: 'Frequência', data: hist.bins.map(function(b) { return b.count; }), backgroundColor: hist.bins.map(function(b) { return b.color; }), borderColor: hist.bins.map(function(b, i) { return i === hiIdx ? hlColor : 'transparent'; }), borderWidth: hist.bins.map(function(b, i) { return i === hiIdx ? 2.5 : 0; }) }] },
    options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: { color: th.text, maxTicksLimit: 15 } }, y: { grid: { color: th.grid }, ticks: { color: th.text }, title: { display: true, text: 'Pregões' } } }, plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: function(it) { return it.dataIndex === hiIdx ? '← preço atual' : ''; } } } } }
  });
}

function renderInicioFim(ar) {
  var canvas = document.getElementById('inicio-fim-chart'); if (!canvas) return; var th = chartTheme();
  if (canvas._chart) canvas._chart.destroy();
  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: { labels: ar.map(function(a) { return String(a.year); }), datasets: [
      { label: 'Início', data: ar.map(function(a) { return a.inicio; }), borderColor: '#22c55e', backgroundColor: '#22c55e', borderWidth: 2, pointRadius: 3, tension: 0.1, fill: false },
      { label: 'Fim', data: ar.map(function(a) { return a.fim; }), borderColor: '#ef4444', backgroundColor: '#ef4444', borderWidth: 2, pointRadius: 3, tension: 0.1, fill: false }
    ]},
    options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: { color: th.text } }, y: { grid: { color: th.grid }, ticks: { color: th.text }, title: { display: true, text: 'Preço (R$)' } } }, plugins: { legend: { display: true, position: 'top' } } }
  });
}

// ── Indicadores subtab ──
window.initIndicadoresTab = function(ticker) {
  var tab = document.getElementById('tab-indicadores'); if (!tab) return;
  fetch('/api/webui/company/' + encodeURIComponent(ticker) + '/indicators?_t=' + Date.now()).then(function(r) { return r.json(); }).then(function(data) {
    if (data._error) { tab.innerHTML = '<div class="error">Erro: ' + esc(data._error) + '</div>'; return; }
    renderIndicadoresTab(tab, ticker, data);
  }).catch(function(err) { tab.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>'; });
};

function renderIndicadoresTab(tab, ticker, data) {
  var th = chartTheme(); var dates = data.dates || [];
  var html = '<div class="indicators-grid">';

  // Range selector
  html += '<div class="range-bar" id="ind-range-bar">';
  ['Tudo','10A','5A','1A','6M','3M','1M'].forEach(function(r) {
    html += '<button class="range-btn' + (r === '1A' ? ' active' : '') + '" data-range="' + r + '">' + r + '</button>';
  });
  html += '</div>';

  // [v1.26.1] Every indicator card is COLLAPSIBLE (open by default) —
  // indChartCard builds the header + toggle button; the delegated
  // handler below flips .collapsed (CSS hides .chart-container).
  html += indChartCard('RSI (14)', 'rsi-chart');
  html += indChartCard('MACD (12/26/9)', 'macd-chart');
  html += indChartCard('Stochastic (14/3)', 'stoch-chart');
  html += indChartCard('OBV', 'obv-chart');
  if (data.adx) html += indChartCard('ADX (14)', 'adx-chart');
  if (data.cci) html += indChartCard('CCI (20)', 'cci-chart');
  if (data.williams_r) html += indChartCard('Williams %R (14)', 'williams-chart');

  html += '</div>';
  tab.innerHTML = html;

  // [v1.26.1] Delegated collapse toggle (whole header clickable — the
  // ▾/▸ button is the visible affordance; aria-expanded tracks state).
  if (!tab._collapseInit) {
    tab._collapseInit = true;
    tab.addEventListener('click', function(e) {
      var head = e.target.closest ? e.target.closest('.collapsible-chart > .chart-header') : null;
      if (!head) return;
      var card = head.parentNode;
      var closed = card.classList.toggle('collapsed');
      var btn = head.querySelector('.chart-collapse-btn');
      if (btn) btn.setAttribute('aria-expanded', String(!closed));
    });
  }

  // Store full data for range filtering
  tab._indData = data;

  // Render all charts
  renderIndicatorCharts(data, '1A');

  // Range selector handler
  document.getElementById('ind-range-bar').addEventListener('click', function(e) {
    if (e.target.classList.contains('range-btn')) {
      var range = e.target.dataset.range;
      document.querySelectorAll('#ind-range-bar .range-btn').forEach(function(b) { b.classList.toggle('active', b === e.target); });
      renderIndicatorCharts(tab._indData, range);
    }
  });
}

// [v1.26.1] Collapsible indicator card markup — open by default; the
// header (title + chevron button) toggles .collapsed on the card.
function indChartCard(title, canvasId) {
  return '<div class="chart-section collapsible-chart"><div class="chart-header"><div class="reg-title">' + title + '</div>' +
         '<button type="button" class="chart-collapse-btn" aria-expanded="true" aria-label="Recolher gráfico" title="Recolher/expandir">▾</button></div>' +
         '<div class="chart-container"><canvas id="' + canvasId + '"></canvas></div></div>';
}

function renderIndicatorCharts(data, range) {
  var th = chartTheme();
  var dates = data.dates || [];
  var n = RANGE_DAYS[range] ?? 252;
  if (n === 0 || n >= dates.length) n = dates.length;
  var d = dates.slice(-n);

  function slice(arr) { return arr ? arr.slice(-n) : []; }
  function xTicks() { return { color: th.text, maxTicksLimit: 8, callback: function(v) { return fmtDate(this.getLabelForValue(v)); } }; }

  // RSI with 30/70 reference lines
  var rsiCanvas = document.getElementById('rsi-chart');
  if (rsiCanvas) { if (rsiCanvas._chart) rsiCanvas._chart.destroy();
    rsiCanvas._chart = new Chart(rsiCanvas.getContext('2d'), {
      type: 'line',
      data: { labels: d, datasets: [
        { label: 'RSI', data: slice(data.rsi), borderColor: '#3b82f6', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false },
        { label: 'Sobrevenda (30)', data: Array(n).fill(30), borderColor: '#ef4444', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false },
        { label: 'Sobrecompra (70)', data: Array(n).fill(70), borderColor: '#22c55e', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false }
      ]},
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: xTicks() }, y: { grid: { color: th.grid }, ticks: { color: th.text }, min: 0, max: 100 } }, plugins: { legend: { display: true, position: 'top' }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } }
    });
  }

  // MACD
  var macdCanvas = document.getElementById('macd-chart');
  if (macdCanvas) { if (macdCanvas._chart) macdCanvas._chart.destroy();
    macdCanvas._chart = new Chart(macdCanvas.getContext('2d'), {
      type: 'bar',
      data: { labels: d, datasets: [
        { type: 'bar', label: 'Histograma', data: slice(data.macd_histogram), backgroundColor: slice(data.macd_histogram).map(function(v) { return v !== null && v < 0 ? '#ef4444' : '#22c55e'; }), borderWidth: 0, order: 3 },
        { type: 'line', label: 'MACD', data: slice(data.macd_line), borderColor: '#3b82f6', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false, order: 1 },
        { type: 'line', label: 'Signal', data: slice(data.signal_line), borderColor: '#f59e0b', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false, order: 2 }
      ]},
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: xTicks() }, y: { grid: { color: th.grid }, ticks: { color: th.text } } }, plugins: { legend: { display: true, position: 'top' }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } }
    });
  }

  // Stochastic with 20/80 reference lines
  var stochCanvas = document.getElementById('stoch-chart');
  if (stochCanvas) { if (stochCanvas._chart) stochCanvas._chart.destroy();
    stochCanvas._chart = new Chart(stochCanvas.getContext('2d'), {
      type: 'line',
      data: { labels: d, datasets: [
        { label: '%K', data: slice(data.k_line), borderColor: '#3b82f6', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false },
        { label: '%D', data: slice(data.d_line), borderColor: '#f59e0b', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false },
        { label: 'Sobrevenda (20)', data: Array(n).fill(20), borderColor: '#ef4444', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false },
        { label: 'Sobrecompra (80)', data: Array(n).fill(80), borderColor: '#22c55e', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false }
      ]},
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: xTicks() }, y: { grid: { color: th.grid }, ticks: { color: th.text }, min: 0, max: 100 } }, plugins: { legend: { display: true, position: 'top' }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } }
    });
  }

  // OBV
  var obvCanvas = document.getElementById('obv-chart');
  if (obvCanvas) { if (obvCanvas._chart) obvCanvas._chart.destroy();
    obvCanvas._chart = new Chart(obvCanvas.getContext('2d'), {
      type: 'line',
      data: { labels: d, datasets: [{ label: 'OBV', data: slice(data.obv), borderColor: '#a855f7', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false }] },
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: xTicks() }, y: { grid: { color: th.grid }, ticks: { color: th.text } } }, plugins: { legend: { display: false }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } }
    });
  }

  // ADX with 25 reference line
  var adxCanvas = document.getElementById('adx-chart');
  if (adxCanvas && data.adx) { if (adxCanvas._chart) adxCanvas._chart.destroy();
    adxCanvas._chart = new Chart(adxCanvas.getContext('2d'), {
      type: 'line',
      data: { labels: d, datasets: [
        { label: 'ADX', data: slice(data.adx), borderColor: '#0d9488', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false },
        { label: 'Tendência (25)', data: Array(n).fill(25), borderColor: '#f59e0b', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false }
      ]},
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: xTicks() }, y: { grid: { color: th.grid }, ticks: { color: th.text }, min: 0, max: 60 } }, plugins: { legend: { display: true, position: 'top' }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } }
    });
  }

  // CCI with +/-100 reference lines
  var cciCanvas = document.getElementById('cci-chart');
  if (cciCanvas && data.cci) { if (cciCanvas._chart) cciCanvas._chart.destroy();
    cciCanvas._chart = new Chart(cciCanvas.getContext('2d'), {
      type: 'line',
      data: { labels: d, datasets: [
        { label: 'CCI', data: slice(data.cci), borderColor: '#ec4899', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false },
        { label: '+100', data: Array(n).fill(100), borderColor: '#22c55e', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false },
        { label: '-100', data: Array(n).fill(-100), borderColor: '#ef4444', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false }
      ]},
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: xTicks() }, y: { grid: { color: th.grid }, ticks: { color: th.text } } }, plugins: { legend: { display: true, position: 'top' }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } }
    });
  }

  // Williams %R with -20/-80 reference lines (0 to -100 scale)
  var williamsCanvas = document.getElementById('williams-chart');
  if (williamsCanvas && data.williams_r) { if (williamsCanvas._chart) williamsCanvas._chart.destroy();
    williamsCanvas._chart = new Chart(williamsCanvas.getContext('2d'), {
      type: 'line',
      data: { labels: d, datasets: [
        { label: 'Williams %R', data: slice(data.williams_r), borderColor: '#6366f1', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false },
        { label: 'Sobrecompra (-20)', data: Array(n).fill(-20), borderColor: '#22c55e', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false },
        { label: 'Sobrevenda (-80)', data: Array(n).fill(-80), borderColor: '#ef4444', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false }
      ]},
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: xTicks() }, y: { grid: { color: th.grid }, ticks: { color: th.text }, min: -100, max: 0 } }, plugins: { legend: { display: true, position: 'top' }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } }
    });
  }
}

// ── Volatilidade subtab ──
window.initVolatilidadeTab = function(ticker) {
  var tab = document.getElementById('tab-volatilidade'); if (!tab) return;
  fetch('/api/webui/company/' + encodeURIComponent(ticker) + '/volatility?_t=' + Date.now()).then(function(r) { return r.json(); }).then(function(data) {
    if (data._error) { tab.innerHTML = '<div class="error">Erro: ' + esc(data._error) + '</div>'; return; }
    renderVolatilidadeTab(tab, ticker, data);
  }).catch(function(err) { tab.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>'; });
};

function renderVolatilidadeTab(tab, ticker, data) {
  var html = '<div class="indicators-grid">';

  // Range selector
  html += '<div class="range-bar" id="vol-range-bar">';
  ['Tudo','10A','5A','1A','6M','3M','1M'].forEach(function(r) { html += '<button class="range-btn' + (r === '1A' ? ' active' : '') + '" data-range="' + r + '">' + r + '</button>'; });
  html += '</div>';

  // Bollinger Bands chart
  html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">Bollinger Bands (20, 2\u03c3)</div></div><div class="chart-container"><canvas id="bb-chart"></canvas></div></div>';
  // Rolling Volatility chart
  html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">Volatilidade Anualizada (20d/60d/252d)</div></div><div class="chart-container"><canvas id="vol-chart"></canvas></div></div>';

  html += '</div>';
  tab.innerHTML = html;
  tab._volData = data;
  renderVolatilityCharts(data, '1A', ticker);

  document.getElementById('vol-range-bar').addEventListener('click', function(e) {
    if (e.target.classList.contains('range-btn')) {
      var range = e.target.dataset.range;
      document.querySelectorAll('#vol-range-bar .range-btn').forEach(function(b) { b.classList.toggle('active', b === e.target); });
      renderVolatilityCharts(tab._volData, range, ticker);
    }
  });
}

function renderVolatilityCharts(data, range, ticker) {
  var th = chartTheme(); var dates = data.dates || [];
  var n = RANGE_DAYS[range] ?? 252;
  if (n === 0 || n >= dates.length) n = dates.length;
  var d = dates.slice(-n);
  function slice(arr) { return arr ? arr.slice(-n) : []; }
  function xTicks() { return { color: th.text, maxTicksLimit: 8, callback: function(v) { return fmtDate(this.getLabelForValue(v)); } }; }

  // Bollinger Bands — Preço first, green area above M\u00e9dia, red below
  var bbCanvas = document.getElementById('bb-chart');
  if (bbCanvas) { if (bbCanvas._chart) bbCanvas._chart.destroy();
    bbCanvas._chart = new Chart(bbCanvas.getContext('2d'), {
      type: 'line',
      data: { labels: d, datasets: [
        { label: 'Pre\u00e7o', data: slice(data.closes), borderColor: '#0d9488', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false, order: 0, spanGaps: true },
        { label: 'Superior', data: slice(data.bb_upper), borderColor: '#22c55e', borderWidth: 1, pointRadius: 0, tension: 0.1, fill: false, order: 1, spanGaps: true },
        { label: 'M\u00e9dia', data: slice(data.bb_middle), borderColor: '#f59e0b', borderWidth: 1, pointRadius: 0, tension: 0.1, fill: false, order: 2, spanGaps: true },
        { label: 'Inferior', data: slice(data.bb_lower), borderColor: '#ef4444', borderWidth: 1, pointRadius: 0, tension: 0.1, fill: false, order: 3, spanGaps: true }
      ]},
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: xTicks() }, y: { grid: { color: th.grid }, ticks: { color: th.text, callback: function(v) { return 'R$ ' + Number(v).toFixed(2).replace('.', ','); } } } }, plugins: { legend: { display: true, position: 'top' }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } },
      plugins: [{
        id: 'bbArea',
        beforeDatasetsDraw: function(chart) {
          var ctx = chart.ctx;
          var meta1 = chart.getDatasetMeta(1);
          var meta2 = chart.getDatasetMeta(2);
          var meta3 = chart.getDatasetMeta(3);
          if (!meta1 || !meta1.data || !meta2 || !meta2.data || !meta3 || !meta3.data) return;
          ctx.save();
          // Green: Superior to M\u00e9dia
          ctx.beginPath();
          for (var i = 0; i < meta1.data.length; i++) { var p = meta1.data[i]; if (!p) continue; if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); }
          for (var i = meta2.data.length - 1; i >= 0; i--) { var p = meta2.data[i]; if (!p) continue; ctx.lineTo(p.x, p.y); }
          ctx.closePath(); ctx.fillStyle = 'rgba(34,197,94,0.12)'; ctx.fill();
          // Red: M\u00e9dia to Inferior
          ctx.beginPath();
          for (var i = 0; i < meta2.data.length; i++) { var p = meta2.data[i]; if (!p) continue; if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); }
          for (var i = meta3.data.length - 1; i >= 0; i--) { var p = meta3.data[i]; if (!p) continue; ctx.lineTo(p.x, p.y); }
          ctx.closePath(); ctx.fillStyle = 'rgba(239,68,68,0.12)'; ctx.fill();
          ctx.restore();
        }
      }]
    });
  }

  // Rolling Volatility — Pre\u00e7o on right axis + vol lines
  var volCanvas = document.getElementById('vol-chart');
  if (volCanvas) { if (volCanvas._chart) volCanvas._chart.destroy();
    volCanvas._chart = new Chart(volCanvas.getContext('2d'), {
      type: 'line',
      data: { labels: d, datasets: [
        { label: 'Pre\u00e7o', data: slice(data.closes), borderColor: '#0d9488', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false, yAxisID: 'y1', order: 0 },
        { label: 'Vol 20d', data: slice(data.vol_20d).map(function(v) { return v !== null ? v * 100 : null; }), borderColor: '#facc15', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false, yAxisID: 'y', order: 1 },
        { label: 'Vol 60d', data: slice(data.vol_60d).map(function(v) { return v !== null ? v * 100 : null; }), borderColor: '#fb923c', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false, yAxisID: 'y', order: 2 },
        { label: 'Vol 252d', data: slice(data.vol_252d).map(function(v) { return v !== null ? v * 100 : null; }), borderColor: '#ef4444', borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false, yAxisID: 'y', order: 3 }
      ]},
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: xTicks() }, y: { position: 'left', grid: { color: th.grid }, ticks: { color: th.text, callback: function(v) { return Number(v).toFixed(0) + '%'; } }, title: { display: true, text: 'Volatilidade (%)' } }, y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { color: th.text, callback: function(v) { return 'R$ ' + Number(v).toFixed(2).replace('.', ','); } } } }, plugins: { legend: { display: true, position: 'top' }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } }
    });
  }
}

// Volume bars chart (green = up day, red = down day)
// ── Volume subtab ──
window.initVolumeTab = function(ticker) {
  var tab = document.getElementById('tab-volume'); if (!tab) return;
  fetch('/api/webui/company/' + encodeURIComponent(ticker) + '/volume?_t=' + Date.now()).then(function(r) { return r.json(); }).then(function(data) {
    if (data._error) { tab.innerHTML = '<div class="error">Erro: ' + esc(data._error) + '</div>'; return; }
    renderVolumeTab(tab, ticker, data);
  }).catch(function(err) { tab.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>'; });
};

function renderVolumeTab(tab, ticker, data) {
  var html = '<div class="indicators-grid">';

  // Range selector
  html += '<div class="range-bar" id="vol-range-bar-vol">';
  ['Tudo','10A','5A','1A','6M','3M','1M'].forEach(function(r) { html += '<button class="range-btn' + (r === '1A' ? ' active' : '') + '" data-range="' + r + '">' + r + '</button>'; });
  html += '</div>';

  // Stats table
  var stats = data.stats || {};
  html += '<div class="reg-grid">';
  html += '<div class="reg-table"><div class="reg-title">Estatísticas de Volume</div><table class="price-table">';
  html += '<tr><td>Volume Médio</td><td class="val">' + fmtCompact(stats.avg_volume) + '</td><td class="pct">R$</td></tr>';
  html += '<tr><td>Volume Máximo</td><td class="val">' + fmtCompact(stats.max_volume) + '</td><td class="pct">R$</td></tr>';
  html += '<tr><td>Volume Mínimo</td><td class="val">' + fmtCompact(stats.min_volume) + '</td><td class="pct">R$</td></tr>';
  html += '<tr><td>Volume Atual</td><td class="val">' + fmtCompact(stats.latest_volume) + '</td><td class="pct">R$</td></tr>';
  html += '</table></div>';
  html += '<div class="reg-table"><div class="reg-title">Negócios</div><table class="price-table">';
  html += '<tr><td>Negócios (atual)</td><td class="val">' + (stats.latest_trades || 0).toLocaleString('pt-BR') + '</td><td class="pct">neg.</td></tr>';
  html += '<tr><td>Contratos (atual)</td><td class="val">' + fmtCompact(stats.latest_contracts) + '</td><td class="pct">qtd.</td></tr>';
  html += '</table></div>';
  html += '</div>';

  html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">Volume Financeiro (R$)</div></div><div class="chart-container"><canvas id="volume-chart"></canvas></div></div>';
  html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">Número de Negócios</div></div><div class="chart-container"><canvas id="trades-chart"></canvas></div></div>';
  html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">Quantidade Negociada</div></div><div class="chart-container"><canvas id="contracts-chart"></canvas></div></div>';

  html += '</div>';
  tab.innerHTML = html;
  tab._volData = data;
  renderVolumeCharts(data, '1A', ticker);

  document.getElementById('vol-range-bar-vol').addEventListener('click', function(e) {
    if (e.target.classList.contains('range-btn')) {
      var range = e.target.dataset.range;
      document.querySelectorAll('#vol-range-bar-vol .range-btn').forEach(function(b) { b.classList.toggle('active', b === e.target); });
      renderVolumeCharts(tab._volData, range, ticker);
    }
  });
}

function fmtCompact(v) {
  if (v === null || v === undefined) return '\u2014';
  var abs = Math.abs(v);
  if (abs >= 1e9) return (v / 1e9).toFixed(2).replace('.', ',') + ' bi';
  if (abs >= 1e6) return (v / 1e6).toFixed(2).replace('.', ',') + ' mi';
  if (abs >= 1e3) return (v / 1e3).toFixed(2).replace('.', ',') + ' mil';
  return v.toFixed(0);
}

function renderVolumeCharts(data, range, ticker) {
  var th = chartTheme(); var dates = data.dates || [];
  var n = RANGE_DAYS[range] ?? 252;
  if (n === 0 || n >= dates.length) n = dates.length;
  var d = dates.slice(-n);
  function slice(arr) { return arr ? arr.slice(-n) : []; }
  function xTicks() { return { color: th.text, maxTicksLimit: 8, callback: function(v) { return fmtDate(this.getLabelForValue(v)); } }; }

  var volumes = slice(data.volumes);
  var closes = slice(data.closes);
  var opens = slice(data.opens);
  var volColors = volumes.map(function(v, i) { return closes[i] >= opens[i] ? '#22c55e' : '#ef4444'; });

  // Volume bars
  var volCanvas = document.getElementById('volume-chart');
  if (volCanvas) { if (volCanvas._chart) volCanvas._chart.destroy();
    volCanvas._chart = new Chart(volCanvas.getContext('2d'), {
      type: 'bar',
      data: { labels: d, datasets: [
        { label: 'Volume', data: volumes, backgroundColor: volColors, borderWidth: 0, yAxisID: 'y' },
        { type: 'line', label: 'Pre\u00e7o', data: closes, borderColor: '#0d9488', borderWidth: 1, pointRadius: 0, tension: 0.1, fill: false, yAxisID: 'y1' }
      ]},
      options: { responsive: true, maintainAspectRatio: false,
        scales: { x: { grid: { color: th.grid }, ticks: xTicks() },
          y: { position: 'left', grid: { color: th.grid }, ticks: { color: th.text, callback: function(v) { return fmtCompact(v); } }, title: { display: true, text: 'Volume (R$)' } },
          y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { color: th.text, callback: function(v) { return 'R$ ' + Number(v).toFixed(2).replace('.', ','); } } } },
        plugins: { legend: { display: true, position: 'top' }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } }
    });
  }

  // Trade count
  var tradesCanvas = document.getElementById('trades-chart');
  if (tradesCanvas) { if (tradesCanvas._chart) tradesCanvas._chart.destroy();
    tradesCanvas._chart = new Chart(tradesCanvas.getContext('2d'), {
      type: 'bar',
      data: { labels: d, datasets: [
        { label: 'Neg\u00f3cios', data: slice(data.trade_counts), backgroundColor: volColors, borderWidth: 0, yAxisID: 'y' },
        { type: 'line', label: 'Pre\u00e7o', data: slice(data.closes), borderColor: '#0d9488', borderWidth: 1, pointRadius: 0, tension: 0.1, fill: false, yAxisID: 'y1' }
      ]},
      options: { responsive: true, maintainAspectRatio: false,
        scales: { x: { grid: { color: th.grid }, ticks: xTicks() },
          y: { position: 'left', grid: { color: th.grid }, ticks: { color: th.text }, title: { display: true, text: 'N\u00famero de Neg\u00f3cios' } },
          y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { color: th.text, callback: function(v) { return 'R$ ' + Number(v).toFixed(2).replace('.', ','); } } } },
        plugins: { legend: { display: true, position: 'top' }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } }
    });
  }

  // Contracts
  var contractsCanvas = document.getElementById('contracts-chart');
  if (contractsCanvas) { if (contractsCanvas._chart) contractsCanvas._chart.destroy();
    contractsCanvas._chart = new Chart(contractsCanvas.getContext('2d'), {
      type: 'bar',
      data: { labels: d, datasets: [
        { label: 'Quantidade', data: slice(data.contracts), backgroundColor: volColors, borderWidth: 0, yAxisID: 'y' },
        { type: 'line', label: 'Pre\u00e7o', data: slice(data.closes), borderColor: '#0d9488', borderWidth: 1, pointRadius: 0, tension: 0.1, fill: false, yAxisID: 'y1' }
      ]},
      options: { responsive: true, maintainAspectRatio: false,
        scales: { x: { grid: { color: th.grid }, ticks: xTicks() },
          y: { position: 'left', grid: { color: th.grid }, ticks: { color: th.text, callback: function(v) { return fmtCompact(v); } }, title: { display: true, text: 'Quantidade' } },
          y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { color: th.text, callback: function(v) { return 'R$ ' + Number(v).toFixed(2).replace('.', ','); } } } },
        plugins: { legend: { display: true, position: 'top' }, tooltip: { callbacks: { title: function(i) { return fmtDate(i[0].label); } } } } }
    });
  }
}


// ── Fibonacci subtab ──
window.initFibonacciTab = function(ticker) {
  var tab = document.getElementById('tab-fibonacci'); if (!tab) return;
  fetch('/api/webui/company/' + encodeURIComponent(ticker) + '/fibonacci?_t=' + Date.now()).then(function(r) { return r.json(); }).then(function(data) {
    if (data._error) { tab.innerHTML = '<div class="error">Erro: ' + esc(data._error) + '</div>'; return; }
    renderFibonacciTab(tab, ticker, data);
  }).catch(function(err) { tab.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>'; });
};

function renderFibonacciTab(tab, ticker, data) {
  var swings = data.swings || [];
  var current = data.current_price;
  var html = '';

  var swingLabels = { 30: 'Swing 4 semanas', 90: 'Swing 12 semanas', 365: 'Swing 52 semanas' };
  var levelOptions = [0.236, 0.309, 0.382, 0.500, 0.618, 0.786, 1.000, 1.618, 2.618, 3.618, 4.236];

  // Global controls
  html += '<div class="fib-controls">';
  html += '<label>Entrada 1: <select id="fib-e1" onchange="recalcFib()">';
  levelOptions.forEach(function(l) { html += '<option value="' + l + '"' + (l === 0.382 ? ' selected' : '') + '>' + l.toFixed(3).replace('.', ',') + '</option>'; });
  html += '</select></label>';
  html += '<label>Entrada 2: <select id="fib-e2" onchange="recalcFib()">';
  levelOptions.forEach(function(l) { html += '<option value="' + l + '"' + (l === 0.618 ? ' selected' : '') + '>' + l.toFixed(3).replace('.', ',') + '</option>'; });
  html += '</select></label>';
  html += '<label>STOP: <select id="fib-stop" onchange="recalcFib()">';
  [0.05, 0.10, 0.15, 0.20, 0.25].forEach(function(l) { html += '<option value="' + l + '"' + (l === 0.10 ? ' selected' : '') + '>' + (l * 100).toFixed(0) + '%</option>'; });
  html += '</select></label>';
  html += '<label>Pre\u00e7o Atual: <strong>' + fmtBRL(current) + '</strong></label>';
  html += '</div>';

  tab._fibSwings = swings;
  tab._fibCurrent = current;
  tab._fibLabels = swingLabels;
  tab._fibDivAdj = data.dividend_adjustments || [];

  html += '<div id="fib-content"></div>';
  tab.innerHTML = html;
  recalcFib();
}

function recalcFib() {
  var tab = document.getElementById('tab-fibonacci');
  if (!tab || !tab._fibSwings) return;
  var swings = tab._fibSwings;
  var current = tab._fibCurrent;
  var swingLabels = tab._fibLabels;

  var e1 = parseFloat(document.getElementById('fib-e1').value);
  var e2 = parseFloat(document.getElementById('fib-e2').value);
  var stopBuf = parseFloat(document.getElementById('fib-stop').value);

  var content = document.getElementById('fib-content');
  var html = '';

  swings.forEach(function(sw, idx) {
    var lb = sw.lookback_days;
    var label = swingLabels[lb] || ('Swing ' + lb);
    var high = sw.high_price;
    var low = sw.low_price;
    var range = high - low;

    var compraE1 = high - range * e1, compraE2 = high - range * e2;
    var compraS1 = high + range * e1, compraS2 = high + range * e2;
    var compraStop = high - range * e2 - range * stopBuf;
    var vendaE1 = low + range * e1, vendaE2 = low + range * e2;
    var vendaS1 = low - range * e1, vendaS2 = low - range * e2;
    var vendaStop = low + range * e2 + range * stopBuf;

    html += '<div class="fib-swing-section">';
    html += '<h3 class="fib-swing-title">' + label + '</h3>';
    html += '<div class="fib-swing-grid">';

    // Swing info table (Máxima, Mínima, Range, Datas, % vs current)
    html += '<div class="reg-table fib-section">';
    html += '<div class="reg-title">Swing</div>';
    html += '<table class="price-table">';
    html += '<tr><td>M\u00e1xima</td><td class="val">' + fmtBRL(high) + '</td><td class="pct">' + fmtDate(sw.high_date) + '</td></tr>';
    html += '<tr><td>M\u00ednima</td><td class="val">' + fmtBRL(low) + '</td><td class="pct">' + fmtDate(sw.low_date) + '</td></tr>';
    html += '<tr><td>Intervalo</td><td class="val">' + fmtBRL(range) + '</td><td class="pct">\u2014</td></tr>';
    html += '<tr><td>% da M\u00e1xima</td><td class="val">\u2014</td><td class="pct">' + fmtPctColored(current ? (current - high) / high : null) + '</td></tr>';
    html += '<tr><td>% da M\u00ednima</td><td class="val">\u2014</td><td class="pct">' + fmtPctColored(current ? (current - low) / low : null) + '</td></tr>';
    html += '</table>';
    html += '</div>';

    // COMPRA table
    html += '<div class="reg-table fib-setup compra">';
    html += '<div class="reg-title">COMPRA (High ' + fmtBRL(high) + ' \u2192 Low ' + fmtBRL(low) + ')</div>';
    html += '<table class="price-table">';
    html += '<tr><td>Entrada 1 (' + e1.toFixed(3).replace('.', ',') + ')</td><td class="val">' + fmtBRL(compraE1) + '</td><td class="pct">' + fmtPctColored(current ? (compraE1 - current) / current : null) + '</td></tr>';
    html += '<tr><td>Entrada 2 (' + e2.toFixed(3).replace('.', ',') + ')</td><td class="val">' + fmtBRL(compraE2) + '</td><td class="pct">' + fmtPctColored(current ? (compraE2 - current) / current : null) + '</td></tr>';
    html += '<tr><td>Sa\u00edda 1 (' + e1.toFixed(3).replace('.', ',') + ')</td><td class="val">' + fmtBRL(compraS1) + '</td><td class="pct">' + fmtPctColored(current ? (compraS1 - current) / current : null) + '</td></tr>';
    html += '<tr><td>Sa\u00edda 2 (' + e2.toFixed(3).replace('.', ',') + ')</td><td class="val">' + fmtBRL(compraS2) + '</td><td class="pct">' + fmtPctColored(current ? (compraS2 - current) / current : null) + '</td></tr>';
    html += '<tr><td>STOP (' + (stopBuf * 100).toFixed(0) + '%)</td><td class="val">' + fmtBRL(compraStop) + '</td><td class="pct">' + fmtPctColored(current ? (compraStop - current) / current : null) + '</td></tr>';
    html += '</table>';
    html += '</div>';

    // VENDA table
    html += '<div class="reg-table fib-setup venda">';
    html += '<div class="reg-title">VENDA (Low ' + fmtBRL(low) + ' \u2192 High ' + fmtBRL(high) + ')</div>';
    html += '<table class="price-table">';
    html += '<tr><td>Entrada 1 (' + e1.toFixed(3).replace('.', ',') + ')</td><td class="val">' + fmtBRL(vendaE1) + '</td><td class="pct">' + fmtPctColored(current ? (vendaE1 - current) / current : null) + '</td></tr>';
    html += '<tr><td>Entrada 2 (' + e2.toFixed(3).replace('.', ',') + ')</td><td class="val">' + fmtBRL(vendaE2) + '</td><td class="pct">' + fmtPctColored(current ? (vendaE2 - current) / current : null) + '</td></tr>';
    html += '<tr><td>Sa\u00edda 1 (' + e1.toFixed(3).replace('.', ',') + ')</td><td class="val">' + fmtBRL(vendaS1) + '</td><td class="pct">' + fmtPctColored(current ? (vendaS1 - current) / current : null) + '</td></tr>';
    html += '<tr><td>Sa\u00edda 2 (' + e2.toFixed(3).replace('.', ',') + ')</td><td class="val">' + fmtBRL(vendaS2) + '</td><td class="pct">' + fmtPctColored(current ? (vendaS2 - current) / current : null) + '</td></tr>';
    html += '<tr><td>STOP (' + (stopBuf * 100).toFixed(0) + '%)</td><td class="val">' + fmtBRL(vendaStop) + '</td><td class="pct">' + fmtPctColored(current ? (vendaStop - current) / current : null) + '</td></tr>';
    html += '</table>';
    html += '</div>';

    html += '</div>';
    html += '</div>';
  });

  // Dividend adjustments
  var divAdj = tab._fibDivAdj || [];
  if (divAdj && divAdj.length > 0) {
    html += '<div class="fib-swing-section">';
    html += '<h3 class="fib-swing-title">Ajustes de Dividendos</h3>';
    html += '<div class="reg-table fib-section" style="grid-column: 1 / -1;">';
    html += '<table class="price-table"><thead><tr><th>Data Ex</th><th>Valor</th><th>Data Pagamento</th></tr></thead><tbody>';
    divAdj.forEach(function(a) {
      html += '<tr><td>' + fmtDate(a.ex_date || a.payment_date || '') + '</td><td class="val">' + fmtBRL(a.rate) + '</td><td class="pct">' + fmtDate(a.payment_date || '') + '</td></tr>';
    });
    html += '</tbody></table>';
    html += '</div>';
    html += '</div>';
  }

  content.innerHTML = html;
}

window.recalcFib = recalcFib;

// ── Financials subtab: Visão Geral ──
window.initFinVisaoGeral = function(ticker) {
  var tab = document.getElementById('tab-fin-visao-geral'); if (!tab) return;
  fetch('/api/webui/company/' + encodeURIComponent(ticker) + '/financials-overview?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data._error) { tab.innerHTML = '<div class="error">Erro: ' + esc(data._error) + '</div>'; return; }
      renderFinVisaoGeral(tab, ticker, data);
    })
    .catch(function(err) { tab.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>'; });
};

function renderFinVisaoGeral(tab, ticker, data) {
  var ttm = data.ttm || null;
  var annual = data.annual || {};
  var quarterly = data.quarterly || {};
  var ratios = data.ratios || {};
  var annualPeriods = annual.periods || [];
  var quarterlyPeriods = quarterly.periods || [];
  var html = '';

  // [v1.26.1] Provenance line — the overview payload is cached in the
  // webui_payloads table keyed by the company's DFP+ITR×COTAHIST
  // fingerprint; when this load came from the cache the note says when
  // it was computed (it refreshes automatically when new demonstrações
  // or cotações sync — the fingerprint changes, the cache misses).
  if (data.cache_note) {
    html += '<div class="fin-cache-note"><span class="fin-cache-bolt">⚡</span> ' + esc(data.cache_note) + '</div>';
  }

  // ── Section 1: Resultado TTM (real trailing twelve months) + Margens ──
  // [v1.3 fix 1] Uses the ttm mode (compute_ttm_with_engines) — the TTM window
  // ending at the latest quarter. Falls back to the latest annual statement
  // only when TTM can't be computed (< 4 quarters of history).
  var isTTM = !!(ttm && ttm.metrics);
  var m = isTTM ? ttm.metrics : ((annualPeriods[0] || {}).metrics || {});
  var r = isTTM ? (ttm.ratios || {}) : ((annualPeriods[0] || {}).ratios || {});
  var prevM = isTTM ? (ttm.year_ago_metrics || {}) : {};
  var title;
  if (isTTM) {
    title = 'Resultado TTM — ' + (ttm.quarter || '') +
            (ttm.period_range ? ' (' + ttm.period_range + ')' : '');
  } else {
    title = 'Resultado Anual — ' + ((annualPeriods[0] || {}).period || '—');
  }
  html += '<div class="preco-grid">';
  html += '<div class="reg-table"><div class="reg-title">' + title + '</div><table class="price-table">';
  html += finRowDelta('Receita Líquida', m.receita_liquida, prevM.receita_liquida);
  html += finRowDelta('Lucro Bruto', m.lucro_bruto, prevM.lucro_bruto);
  html += finRowDelta('EBIT', m.ebit, prevM.ebit);
  html += finRowDelta('EBITDA', m.ebitda, prevM.ebitda);
  html += finRowDelta('Lucro Líquido', m.lucro_liquido, prevM.lucro_liquido);
  html += '</table></div>';
  // [v1.7.1 fix1] Margens: single-column rows — the trailing Δ column was
  // always "—" (margins are ratios, Δ vs year-ago isn't shown), so it's gone
  // (finRowPct1, same as the WACC/DuPont/Altman boxes).
  html += '<div class="reg-table"><div class="reg-title">Margens ' + (isTTM ? '(TTM)' : '') + '</div><table class="price-table">';
  html += finRowPct1('Margem Bruta', r.marg_bruta);
  html += finRowPct1('Margem EBITDA', r.marg_ebitda);
  html += finRowPct1('Margem Operacional (EBIT)', r.marg_ebit);
  html += finRowPct1('Margem Líquida', r.marg_liquida);
  html += finRowPct1('ROE', r.roe);
  html += finRowPct1('ROA', r.roa);
  html += '</table></div>';
  // [v1.7.1 fix1] Balanço: Δ column now real — latest TTM (4-quarter average
  // snapshot) vs TTM one year ago, same semantics as the Resultado table.
  html += '<div class="reg-table"><div class="reg-title">Balanço Patrimonial</div><table class="price-table">';
  html += finRowDelta('Ativo Total', m.ativo_total, prevM.ativo_total);
  html += finRowDelta('Caixa e Equivalentes', m.caixa, prevM.caixa);
  html += finRowDelta('Dívida Bruta', m.divida_bruta, prevM.divida_bruta);
  html += finRowDelta('Dívida Líquida', numSub(m.divida_bruta, m.caixa), numSub(prevM.divida_bruta, prevM.caixa));
  html += finRowDelta('Patrimônio Líquido', m.patrimonio_liquido, prevM.patrimonio_liquido);
  html += '</table></div>';
  // [v1.7.1 fix1] Fluxo de Caixa: same Δ 1A treatment as Resultado/Balanço
  // (was a hardcoded "—" placeholder column).
  html += '<div class="reg-table"><div class="reg-title">Fluxo de Caixa ' + (isTTM ? '(TTM)' : '') + '</div><table class="price-table">';
  html += finRowDelta('FCO (Operacional)', m.fco, prevM.fco);
  html += finRowDelta('FCI (Investimento)', m.fci, prevM.fci);
  html += finRowDelta('FCF (FCO+FCI)', numAdd(m.fco, m.fci), numAdd(prevM.fco, prevM.fci));
  html += '</table></div>';
  html += '</div>';

  // ── Section 1.5: Conversão da Receita em Lucro (DRE waterfall) ──
  // [v1.7.1] Client-derived from the payloads already loaded (annual =
  // newest DFP year, quarterly = newest standalone quarter) — the
  // Anual/Trimestral pills re-derive instantly, no refetch. Deltas are
  // computed from the DRE subtotals (Custos = Receita − Lucro Bruto, …),
  // so no reliance on per-line code presence or sign conventions.
  // [v1.7.1 fix2] These pills now drive the SAME shared state as the
  // Trajetória chart and the Tendência table (tab._finPeriod) — clicking
  // Anual/Trimestral here switches all THREE cards together.
  var hasWf = (annualPeriods.length > 0) || (quarterlyPeriods.length > 0);
  if (hasWf) {
    html += '<div class="chart-section fin-wf-card">';
    html += '<div class="chart-header"><div class="reg-title">Conversão da Receita em Lucro' +
            ' <span id="fin-wf-period" class="fin-wf-period"></span>' +
            ' <span class="val-info" title="Cada barra de dedução é derivada da diferença entre os subtotais da DRE (ex.: Custos = Receita − Lucro Bruto). Impostos e Outros = residual (IR/CSLL, participações, equivalência e itens não recorrentes).">ⓘ</span></div>';
    html += '<div class="prov-pills fin-wf-pills">';
    html += '<button type="button" class="prov-pill" data-wf-mode="anual">Anual</button>';
    html += '<button type="button" class="prov-pill" data-wf-mode="trimestral">Trimestral</button>';
    html += '</div></div>';
    html += '<div class="chart-container"><canvas id="fin-waterfall-chart" aria-label="Cascata da DRE: da receita líquida ao lucro líquido"></canvas></div>';
    html += '<div class="muted fin-wf-note">Anual = último exercício anual (DFP) · Trimestral = último trimestre isolado. Barras vermelhas reduzem o resultado, verdes somam.</div>';
    html += '</div>';
  }

  // ── Section 2: Trajetória chart — Anual | Trimestral ──
  // [v1.7.1 fix1] The card now renders when EITHER dataset exists and gets
  // the same Anual/Trimestral toggle as the Tendência table below. The toggle
  // is client-side only (annual + quarterly payloads are already on the page).
  // [v1.7.1 fix2] The pills share ONE state (tab._finPeriod) with the DRE
  // waterfall above — ALL THREE cards always show the same period type.
  var hasTraj = (annualPeriods.length > 0) || (quarterlyPeriods.length > 0);
  if (hasTraj) {
    html += '<div class="chart-section fin-traj-card">';
    html += '<div class="chart-header"><div class="reg-title" id="fin-traj-title">Trajetória</div>' + finPeriodPillsHtml() + '</div>';
    html += '<div class="chart-container"><canvas id="fin-trend-chart" aria-label="Trajetória: receita, EBITDA e lucro por período"></canvas></div></div>';
  }

  // ── Section 3: Tendência table — Anual | Trimestral ──
  // [v1.7.1 fix1] Was "Quarterly Trend" (quarterly-only, English title).
  // Now PT-BR and driven by the same shared toggle: Anual = 10 DFP years with
  // YoY deltas, Trimestral = 8 standalone quarters with QoQ deltas (as before).
  // [v1.7.1 fix2] Also follows the waterfall pills (shared tab._finPeriod).
  if (hasTraj) {
    html += '<div class="reg-table fin-trend-card">';
    html += '<div class="fin-trend-head"><div class="reg-title" id="fin-trend-title">Tendência</div>' + finPeriodPillsHtml() + '</div>';
    html += '<div id="fin-trend-table-wrap"></div>';
    html += '</div>';
  }

  // ── Section 4: Análise de Risco — WACC + DuPont + Altman Z ──
  // [WebUI v1.3 fix 2] Single-column tables — the old trailing Δ column was
  // always "—" in these boxes, so it is gone (finRow1/finRowPct1 helpers).
  html += '<div class="preco-grid">';
  html += '<div class="reg-table"><div class="reg-title">WACC</div><table class="price-table">';
  html += finRowPct1('WACC', ratios.wacc);
  html += '</table></div>';
  html += '<div class="reg-table"><div class="reg-title">DuPont ROE</div><table class="price-table">';
  html += finRowPct1('Margem Líquida', ratios.net_margin !== undefined ? ratios.net_margin : ratios.margem_liquida);
  html += finRow1('Giro do Ativo', ratios.asset_turnover, 'num');
  html += finRow1('Alavancagem', ratios.financial_leverage, 'num');
  html += finRowPct1('ROE (DuPont)', ratios.dupont);
  html += '</table></div>';
  html += '<div class="reg-table"><div class="reg-title">Altman Z-Score</div><table class="price-table">';
  html += finRow1('Z-Score', ratios.altman_z, 'num');
  var zVal = ratios.altman_z;
  var zVerdict = zVal === null || zVal === undefined ? '—' : (zVal > 2.99 ? 'Segura' : zVal > 1.81 ? 'Zona Cinzenta' : 'Distress');
  html += '<tr><td>Veredito</td><td class="val">' + zVerdict + '</td></tr>';
  html += '</table></div>';
  html += '</div>';

  // ── Section 5: Red Flags (server-side consistency checks) ──
  // [v1.5] rf.error = the check itself failed (distinct from "no rows") —
  // the UI now says "verificação indisponível" instead of a false all-clear.
  var rf = data.red_flags;
  html += '<div class="reg-table"><div class="reg-title">Red Flags Contábeis' +
          (rf && rf.error ? '' : (rf && rf.has_warnings ? ' — \u26a0 atenção' : (rf ? ' — OK' : ''))) + '</div>';
  if (rf && rf.error) {
    html += '<div class="error" style="margin:0;">' + esc(rf.error) + '</div>';
  } else if (rf && rf.rows && rf.rows.length > 0) {
    html += '<div style="overflow-x: auto;"><table class="price-table fin-wide-table"><thead><tr><th>Verificação</th><th>Status</th><th style="text-align:left;">Detalhe</th></tr></thead><tbody>';
    rf.rows.forEach(function(row) {
      var warn = String(row[1] || '').indexOf('\u26a0') >= 0;
      html += '<tr><td>' + esc(row[0] || '') + '</td>';
      html += '<td class="val" style="color:' + (warn ? 'var(--color-danger)' : 'var(--color-success)') + ';font-weight:600;">' + esc(row[1] || '') + '</td>';
      html += '<td class="muted" style="text-align:left;">' + esc(row[2] && row[2] !== '—' ? row[2] : '—') + '</td></tr>';
    });
    html += '</tbody></table></div>';
    html += '<div class="muted" style="font-size:11px;margin-top:var(--space-2);">Cada verificação compara identidades contábeis (ex.: Ativo = Circulante + Não Circulante) com tolerância de 5%.</div>';
  } else {
    html += '<div class="loading">Nenhum dado contábil disponível para validação.</div>';
  }
  html += '</div>';

  tab.innerHTML = html;

  // [v1.7.1 fix2] ONE shared Anual/Trimestral state (tab._finPeriod) now
  // drives ALL THREE period cards: the DRE waterfall, the Trajetória chart
  // and the Tendência table. v1.7.1/fix1 kept the waterfall on a separate
  // tab._wf state, so its pills didn't move the other two cards (user
  // report: toggling "Conversão da Receita em Lucro" left Trajetória/
  // Tendência behind). Default = Anual when DFP years exist, Trimestral
  // otherwise; every pill group stays in sync via syncFinPeriodPills.
  tab._finPeriod = {
    annual: annualPeriods, quarterly: quarterlyPeriods,
    yearEndPrices: data.year_end_prices || {},
    mode: annualPeriods.length > 0 ? 'anual' : 'trimestral'
  };
  syncFinPeriodPills(tab);
  if (hasWf) renderFinWaterfall(tab);
  if (hasTraj) {
    renderFinTrajChart(tab);
    renderFinTrendTable(tab);
  }
}

// ── [v1.7.1] DRE waterfall: Receita → Lucro Líquido ──
// Floating-bar Chart.js waterfall with dashed carry-level connectors. All
// data comes from the overview payload (annual periods arrive NEWEST-first,
// quarterly OLDEST-first — the pickers below respect that).

function finWfPick(tab) {
  // Returns {metrics, period_label} for the active mode, or null.
  // [v1.7.1 fix2] Reads the shared tab._finPeriod state (was tab._wf) so
  // the waterfall always follows the same Anual/Trimestral mode as the
  // Trajetória chart and the Tendência table.
  var st = tab._finPeriod;
  if (!st) return null;
  if (st.mode === 'trimestral') {
    var qs = st.quarterly || [];
    if (!qs.length) return null;
    var q = qs[qs.length - 1];  // oldest-first → last = newest
    return { metrics: q.metrics || {}, period_label: String(q.period || '') };
  }
  var as = st.annual || [];
  if (!as.length) return null;
  var a = as[0];               // newest-first → first = newest
  return { metrics: a.metrics || {}, period_label: String(a.period || '') };
}

function finWfSteps(m) {
  // Build the bar chain from the DRE subtotals. Anchors (totals) come from
  // reported codes 3.01/3.03/3.05/3.11; deltas are derived differences, so
  // the chart degrades gracefully when a subtotal is missing (the chain
  // skips that anchor and merges the label).
  // Each step: {label, lo, hi (render span), kind, delta (signed change),
  //             land (running level AFTER the bar — drives the connectors)}.
  function has(v) { return v !== null && v !== undefined && isFinite(v); }
  var rec = m.receita_liquida, lb = m.lucro_bruto, ebit = m.ebit,
      rf = m.resultado_financeiro, ll = m.lucro_liquido;
  if (!has(rec)) return null;

  function span(start, land, label) {
    var d = land - start;
    return { label: label, lo: Math.min(start, land), hi: Math.max(start, land),
             kind: d < 0 ? 'down' : 'up', delta: d, land: land };
  }
  function total(label, val, kind) {
    return { label: label, lo: Math.min(val, 0), hi: Math.max(val, 0),
             kind: kind || 'total', delta: null, val: val, land: val };
  }

  var steps = [total('Receita Líquida', rec)];
  var level = rec;  // running level
  if (has(lb)) {
    steps.push(span(level, lb, 'Custos (CPV)'));
    steps.push(total('Lucro Bruto', lb));
    level = lb;
  }
  if (has(ebit)) {
    steps.push(span(level, ebit, has(lb) ? 'Despesas Operacionais'
                                         : 'Custos + Despesas Oper.'));
    steps.push(total('EBIT', ebit));
    level = ebit;
  }
  if (has(ll)) {
    if (has(ebit) && has(rf)) {
      var ebt = ebit + rf;
      steps.push(span(level, ebt, 'Resultado Financeiro'));
      steps.push(span(ebt, ll, 'Impostos e Outros'));
    } else if (has(ebit)) {
      steps.push(span(level, ll, 'Financeiro, Impostos e Outros'));
    } else {
      steps.push(span(level, ll, 'Custos, Despesas e Impostos'));
    }
    steps.push(total('Lucro Líquido', ll, 'final'));
  }

  steps.carries = steps.map(function(s) { return s.land; });
  return steps;
}

function finWfFmt(v) {
  // Compact pt-BR BRL for axis ticks and tooltips.
  var a = Math.abs(v), sign = v < 0 ? '−' : '';
  function n(x) { return x.toFixed(x >= 100 ? 0 : 1).replace('.', ','); }
  if (a >= 1e12) return sign + 'R$ ' + n(a / 1e12) + ' tri';
  if (a >= 1e9)  return sign + 'R$ ' + n(a / 1e9) + ' bi';
  if (a >= 1e6)  return sign + 'R$ ' + n(a / 1e6) + ' mi';
  if (a >= 1e3)  return sign + 'R$ ' + n(a / 1e3) + ' mil';
  return sign + 'R$ ' + n(a);
}

// Dashed carry-level connectors between consecutive bars.
var finWfConnectorPlugin = {
  id: 'finWfConnectors',
  afterDatasetsDraw: function(chart) {
    var carries = chart.$wfCarries;
    if (!carries) return;
    var meta = chart.getDatasetMeta(0);
    if (!meta || !meta.data || meta.data.length < 2) return;
    var ctx = chart.ctx, yScale = chart.scales.y;
    ctx.save();
    ctx.strokeStyle = chartTheme().text;
    ctx.globalAlpha = 0.55;
    ctx.setLineDash([4, 3]);
    ctx.lineWidth = 1;
    for (var i = 0; i < meta.data.length - 1 && i < carries.length - 1; i++) {
      var el = meta.data[i], next = meta.data[i + 1];
      if (!el || !next || el.x === undefined) continue;
      var y = yScale.getPixelForValue(carries[i]);
      ctx.beginPath();
      ctx.moveTo(el.x + (el.width || 0) / 2, y);
      ctx.lineTo(next.x - (next.width || 0) / 2, y);
      ctx.stroke();
    }
    ctx.restore();
  }
};

function renderFinWaterfall(tab) {
  var canvas = document.getElementById('fin-waterfall-chart');
  if (!canvas) return;
  var picked = finWfPick(tab);
  var steps = picked ? finWfSteps(picked.metrics) : null;
  var periodEl = document.getElementById('fin-wf-period');

  if (!steps || !steps.length) {
    if (periodEl) periodEl.textContent = '';
    if (canvas._chart) { canvas._chart.destroy(); canvas._chart = null; }
    canvas.replaceWith((function() {
      var d = document.createElement('div');
      d.className = 'loading'; d.id = 'fin-waterfall-chart';
      d.textContent = 'Sem dados de DRE para esta visão.';
      return d;
    })());
    return;
  }
  if (periodEl) periodEl.textContent = '— ' + picked.period_label;

  // The no-data path replaces the canvas with a message div (same id) —
  // rebuild a canvas before rendering when toggling back to a mode with data.
  if (canvas.tagName !== 'CANVAS') {
    var c = document.createElement('canvas');
    c.id = 'fin-waterfall-chart';
    c.setAttribute('aria-label', 'Cascata da DRE: da receita líquida ao lucro líquido');
    canvas.replaceWith(c);
    canvas = c;
  }

  var th = chartTheme();
  var COLORS = { total: '#0d9488', final: '#0f766e', down: '#e11d48', up: '#22c55e' };
  var data = steps.map(function(s) { return [s.lo, s.hi]; });
  var colors = steps.map(function(s) { return COLORS[s.kind] || COLORS.total; });

  if (canvas._chart) canvas._chart.destroy();
  var chart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: steps.map(function(s) { return s.label; }),
      datasets: [{
        label: 'DRE',
        data: data,
        backgroundColor: colors,
        borderWidth: 0,
        barPercentage: 0.62,
        categoryPercentage: 0.82
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              var s = steps[ctx.dataIndex];
              if (!s) return '';
              if (s.kind === 'total' || s.kind === 'final') {
                return ' ' + s.label + ': ' + finWfFmt(s.val);
              }
              return ' ' + s.label + ': ' + (s.delta <= 0 ? '−' : '+') +
                     finWfFmt(Math.abs(s.delta));
            }
          }
        }
      },
      scales: {
        x: { grid: { color: th.grid }, ticks: { color: th.text, maxRotation: 40,
              minRotation: 0, autoSkip: false, font: { size: 11 } } },
        y: { grid: { color: th.grid }, ticks: { color: th.text,
              callback: function(v) { return finWfFmt(v); } } }
      }
    },
    plugins: [finWfConnectorPlugin]
  });
  chart.$wfCarries = steps.carries;
  canvas._chart = chart;
}

// [v1.7.1 fix1] finRow/finRowPct removed — every Visão Geral table now
// either carries a REAL Δ (finRowDelta: Resultado/Balanço/Fluxo de Caixa) or
// is single-column (finRow1/finRowPct1: Margens, WACC, DuPont, Altman). The
// old finRow/finRowPct hardcoded a "—" placeholder in the third cell.

// [v1.3 fix 1] Row with Δ 1A (latest TTM vs TTM one year ago), colored green/red.
function finRowDelta(label, value, prev) {
  var v = value !== null && value !== undefined ? fmtCompact(value) : '—';
  var delta = fmtPctColored(deltaVs(value, prev));
  return '<tr><td>' + label + '</td><td class="val">' + v + '</td><td class="pct">' + delta + '</td></tr>';
}
function deltaVs(v, prev) {
  if (v === null || v === undefined || prev === null || prev === undefined || prev === 0) return null;
  return (v - prev) / Math.abs(prev);
}
// None-safe numeric helpers (null propagates instead of becoming NaN).
function numAdd(a, b) {
  return (a === null || a === undefined || b === null || b === undefined) ? null : (a + b);
}
function numSub(a, b) {
  return (a === null || a === undefined || b === null || b === undefined) ? null : (a - b);
}
// [WebUI v1.3 fix 2] Single-column row helpers (Margens / WACC / DuPont /
// Altman boxes) — these tables carry no Δ, so no trailing "—" cell.
function finRow1(label, value, type) {
  var v;
  if (type === 'brl') v = value !== null && value !== undefined ? fmtCompact(value) : '—';
  else v = value !== null && value !== undefined ? Number(value).toFixed(2).replace('.', ',') : '—';
  return '<tr><td>' + label + '</td><td class="val">' + v + '</td></tr>';
}
function finRowPct1(label, value) {
  var v = value !== null && value !== undefined ? (value * 100).toFixed(2).replace('.', ',') + '%' : '—';
  // [v1.5] zero → yellow (was green).
  var color = value === null || value === undefined ? '' :
    (value < 0 ? 'var(--color-danger)' : (value > 0 ? 'var(--color-success)' : 'var(--color-warning)'));
  return '<tr><td>' + label + '</td><td class="val"' + (color ? ' style="color:' + color + '"' : '') + '>' + v + '</td></tr>';
}

function renderFinTrajChart(tab) {
  // [v1.7.1 fix1] Trajetória bars (Receita/EBITDA/Lucro) for the shared
  // Anual | Trimestral mode. Anual adds the Dec-31 price overlay (right
  // axis); Trimestral has no quarterly price series in the payload, so the
  // overlay is simply omitted. No-data mode mirrors the waterfall card
  // (canvas ↔ message div swap, same id).
  var st = tab._finPeriod; if (!st) return;
  var canvas = document.getElementById('fin-trend-chart');
  if (!canvas) return;
  var titleEl = document.getElementById('fin-traj-title');
  var periods, yearEndPrices = null;
  if (st.mode === 'trimestral') {
    periods = st.quarterly || [];                  // already oldest-first
    if (titleEl) titleEl.textContent = 'Trajetória Trimestral';
  } else {
    periods = (st.annual || []).slice().reverse(); // newest-first → oldest-first
    if (titleEl) titleEl.textContent = 'Trajetória Anual';
    yearEndPrices = st.yearEndPrices;
  }

  if (!periods.length) {
    if (canvas._chart) { canvas._chart.destroy(); canvas._chart = null; }
    canvas.replaceWith((function() {
      var d = document.createElement('div');
      d.className = 'loading'; d.id = 'fin-trend-chart';
      d.textContent = 'Sem dados de trajetória para esta visão.';
      return d;
    })());
    return;
  }
  // Rebuild the canvas when toggling back from a no-data swap.
  if (canvas.tagName !== 'CANVAS') {
    var c = document.createElement('canvas');
    c.id = 'fin-trend-chart';
    c.setAttribute('aria-label', 'Trajetória: receita, EBITDA e lucro por período');
    canvas.replaceWith(c);
    canvas = c;
  }

  var th = chartTheme();
  if (canvas._chart) canvas._chart.destroy();
  var labels = periods.map(function(p) { return p.period || ''; });
  var receitas = periods.map(function(p) { return ((p.metrics || {}).receita_liquida || 0) / 1e6; });
  var ebitdas = periods.map(function(p) { return ((p.metrics || {}).ebitda || 0) / 1e6; });
  var lucros = periods.map(function(p) { return ((p.metrics || {}).lucro_liquido || 0) / 1e6; });
  // Price overlay (Anual only): Dec-31 close per year (right axis), dashed.
  var hasPrices = !!(yearEndPrices && Object.keys(yearEndPrices).length > 0);
  var prices = hasPrices ? labels.map(function(y) { return yearEndPrices[y] !== undefined ? yearEndPrices[y] : null; }) : [];
  var priceShown = hasPrices && prices.some(function(p) { return p !== null && p !== undefined; });

  var datasets = [
    { label: 'Receita', data: receitas, backgroundColor: '#f59e0b', borderWidth: 0, yAxisID: 'y', order: 3 },
    { label: 'EBITDA', data: ebitdas, backgroundColor: '#d946a0', borderWidth: 0, yAxisID: 'y', order: 3 },
    { label: 'Lucro Líquido', data: lucros, backgroundColor: '#a855f7', borderWidth: 0, yAxisID: 'y', order: 3 }
  ];
  if (priceShown) {
    datasets.push({ label: 'Preço (R$)', data: prices, type: 'line', borderColor: '#0d9488',
      backgroundColor: '#0d9488', borderDash: [5, 5], fill: false, tension: 0.3,
      pointRadius: 3, yAxisID: 'y1', order: 0 });
  }
  var scales = {
    x: { grid: { color: th.grid }, ticks: { color: th.text } },
    y: { grid: { color: th.grid }, ticks: { color: th.text, callback: function(v) { return 'R$ ' + Number(v).toFixed(0) + ' mi'; } },
         title: { display: true, text: 'R$ (mi)' } }
  };
  if (priceShown) {
    scales.y1 = { position: 'right', grid: { drawOnChartArea: false },
      ticks: { color: th.text, callback: function(v) { return 'R$ ' + Number(v).toFixed(2).replace('.', ','); } },
      title: { display: true, text: 'Preço (R$)' } };
  }

  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: { labels: labels, datasets: datasets },
    options: { responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: scales,
      plugins: { legend: { display: true, position: 'top' } }
    }
  });
}

function renderFinTrendTable(tab) {
  // [v1.7.1 fix1] Tendência table for the shared Anual | Trimestral mode.
  // Rows are the same 4 flow metrics; deltas are vs the previous column
  // (YoY in Anual, QoQ in Trimestral). Quarters arrive oldest-first; annual
  // periods arrive newest-first and are flipped.
  var st = tab._finPeriod; if (!st) return;
  var wrap = document.getElementById('fin-trend-table-wrap');
  if (!wrap) return;
  var titleEl = document.getElementById('fin-trend-title');
  var periods = st.mode === 'trimestral' ? (st.quarterly || [])
                                            : (st.annual || []).slice().reverse();
  if (titleEl) titleEl.textContent = st.mode === 'trimestral' ? 'Tendência Trimestral' : 'Tendência Anual';
  if (!periods.length) {
    wrap.innerHTML = '<div class="loading">Sem dados para esta visão.</div>';
    return;
  }
  var html = '<div style="overflow-x: auto;"><table class="price-table fin-wide-table fin-trend-table"><thead><tr><th>Métrica</th>';
  periods.forEach(function(p) {
    html += '<th>' + (p.period || '') + '</th>';
  });
  html += '</tr></thead><tbody>';
  var qMetrics = [
    ['Receita Líquida', 'receita_liquida'],
    ['Lucro Bruto', 'lucro_bruto'],
    ['EBITDA', 'ebitda'],
    ['Lucro Líquido', 'lucro_liquido'],
  ];
  qMetrics.forEach(function(qm) {
    html += '<tr><td>' + qm[0] + '</td>';
    var prev = null;
    periods.forEach(function(p) {
      var val = (p.metrics || {})[qm[1]];
      var delta = '';
      if (prev !== null && val !== null && prev !== null && prev > 0) {
        var pct = (val - prev) / prev;
        delta = ' <span style="font-size:10px;color:' + (pct < 0 ? 'var(--color-danger)' : 'var(--color-success)') + '">' + (pct >= 0 ? '+' : '') + (pct * 100).toFixed(1).replace('.', ',') + '%</span>';
      }
      html += '<td class="val">' + fmtCompact(val) + delta + '</td>';
      prev = val;
    });
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  wrap.innerHTML = html;
}

function finPeriodPillsHtml() {
  // Shared Anual/Trimestral pills — used by BOTH the Trajetória card and the
  // Tendência table. No 'active' class here; syncFinPeriodPills() sets it
  // right after the pane renders (default mode comes from the data).
  return '<div class="prov-pills fin-period-pills">' +
         '<button type="button" class="prov-pill" data-fp-mode="anual">Anual</button>' +
         '<button type="button" class="prov-pill" data-fp-mode="trimestral">Trimestral</button>' +
         '</div>';
}

function syncFinPeriodPills(tab) {
  // [v1.7.1 fix2] Syncs EVERY Anual/Trimestral pill group on the pane — the
  // waterfall pills (.fin-wf-pills, data-wf-mode) AND the Trajetória/
  // Tendência pills (.fin-period-pills, data-fp-mode) — so all three cards
  // always show the same active mode.
  Array.prototype.forEach.call(
    tab.querySelectorAll('.fin-period-pills .prov-pill, .fin-wf-pills .prov-pill'),
    function(p) {
      var m = p.getAttribute('data-fp-mode') || p.getAttribute('data-wf-mode');
      p.classList.toggle('active', m === tab._finPeriod.mode);
    });
}

// ── Financials subtab: Demonstrações ──
// [v1.3 fix 1] One fetch per period type (all 5 statements in a single payload);
// switching Completo/BPA/BPP/DRE/DFC/DVA re-renders from cached data.
// Quarterly values are STANDALONE quarters; annual = DFP years (2016+).
window.initFinDemonstracoes = function(ticker) {
  var tab = document.getElementById('tab-fin-demonstracoes'); if (!tab) return;
  tab._finState = { statement: 'balanco', subview: 'completo', period: 'annual' };
  tab._finData = {};  // {period: payload} — cached fetches
  renderFinDemonstracoes(tab, ticker);
};

function renderFinDemonstracoes(tab, ticker) {
  var state = tab._finState;
  var html = '';

  // Controls: statement type + subview + period toggle
  html += '<div class="fib-controls">';
  html += '<label>Declaração: <select id="fin-statement" onchange="updateFinDemo()">';
  html += '<option value="balanco"' + (state.statement === 'balanco' ? ' selected' : '') + '>Balanço</option>';
  html += '<option value="dre"' + (state.statement === 'dre' ? ' selected' : '') + '>DRE</option>';
  html += '<option value="dfc"' + (state.statement === 'dfc' ? ' selected' : '') + '>DFC</option>';
  html += '<option value="dva"' + (state.statement === 'dva' ? ' selected' : '') + '>DVA</option>';
  html += '</select></label>';

  if (state.statement === 'balanco') {
    html += '<label>Visão: <select id="fin-subview" onchange="updateFinDemo()">';
    html += '<option value="completo"' + (state.subview === 'completo' ? ' selected' : '') + '>Completo (BPA+BPP)</option>';
    html += '<option value="bpa"' + (state.subview === 'bpa' ? ' selected' : '') + '>BPA — Ativo</option>';
    html += '<option value="bpp"' + (state.subview === 'bpp' ? ' selected' : '') + '>BPP — Passivo + PL</option>';
    html += '</select></label>';
  }

  html += '<label>Período: <select id="fin-period" onchange="updateFinDemo()">';
  html += '<option value="annual"' + (state.period === 'annual' ? ' selected' : '') + '>Anual</option>';
  html += '<option value="quarterly"' + (state.period === 'quarterly' ? ' selected' : '') + '>Trimestral</option>';
  html += '</select></label>';
  html += '</div>';

  html += '<div id="fin-demo-content"><div class="loading">Carregando...</div></div>';
  tab.innerHTML = html;

  // Cached fetch — one payload per period type covers all subviews.
  if (tab._finData[state.period]) {
    renderFinStatements(tab, ticker, tab._finData[state.period]);
    return;
  }
  var periods = state.period === 'annual' ? 10 : 20;
  fetch('/api/webui/company/' + encodeURIComponent(ticker) + '/financials-statements?period=' + state.period + '&periods=' + periods + '&_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      tab._finData[state.period] = data;
      renderFinStatements(tab, ticker, data);
    })
    .catch(function(err) {
      document.getElementById('fin-demo-content').innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
}

// [v1.5] updateFinDemo reads the ticker from the panel's data-ticker
// attribute — the old onchange="updateFinDemo('<ticker>')" interpolated the
// ticker into an inline JS handler (B77; safe now that routes validate the
// ticker, but the pattern is gone anyway).
window.updateFinDemo = function() {
  var tab = document.getElementById('tab-fin-demonstracoes');
  if (!tab) return;
  var ticker = tab.getAttribute('data-ticker') || '';
  tab._finState.statement = document.getElementById('fin-statement').value;
  var subSel = document.getElementById('fin-subview');
  if (subSel) tab._finState.subview = subSel.value;
  tab._finState.period = document.getElementById('fin-period').value;
  renderFinDemonstracoes(tab, ticker);
};

function renderFinStatements(tab, ticker, data) {
  var content = document.getElementById('fin-demo-content');
  if (!content) return;
  var state = tab._finState;
  if (data._error) { content.innerHTML = '<div class="error">Erro: ' + esc(data._error) + '</div>'; return; }
  // [v1.5] Kill the previous view's charts before re-render (leak fix).
  destroyChartsIn(content);

  var labels = data.labels || [];
  var dates = data.dates || [];
  var stmts = data.statements || {};
  var html = '';

  var viewKey = state.statement === 'balanco' ? state.subview : state.statement;
  var titles = {
    completo: 'Balanço Completo — BPA + BPP',
    bpa: 'BPA — Ativo',
    bpp: 'BPP — Passivo + PL',
    dre: 'DRE — Demonstração do Resultado',
    dfc: 'DFC — Fluxo de Caixa',
    dva: 'DVA — Valor Adicionado'
  };
  var periodLabel = data.period_type === 'quarterly' ? 'Comparativo Trimestral' : 'Comparativo Anual';

  // [WebUI v1.3 fix 2] Statement-specific charts (reference: PETR4 financials
  // dashboard). Each view gets its own set of charts — balanço: stacked
  // absolute + % composition; DRE: Receita/EBITDA/Lucro + margens; DFC:
  // grouped + stacked + FCO vs Lucro Líquido; DVA: VA Bruta/Líquida/Total
  // lines. Series are pulled from the same statement rows the table shows.
  var chartDefs = buildFinStmtChartDefs(viewKey, stmts);
  if (chartDefs.length > 0) {
    html += '<div class="fin-charts-grid">';
    chartDefs.forEach(function(def, i) {
      html += '<div class="chart-section fin-chart-card"><div class="chart-header"><div class="reg-title">' + def.title + '</div></div>';
      html += '<div class="chart-container"><canvas id="fin-stmt-chart-' + i + '"></canvas></div></div>';
    });
    html += '</div>';
  }

  // Table (merged rows for Completo; single statement otherwise)
  var rows;
  if (state.statement === 'balanco') {
    if (state.subview === 'bpa') rows = ((stmts.BPA || {}).rows || []);
    else if (state.subview === 'bpp') rows = ((stmts.BPP || {}).rows || []);
    else rows = (((stmts.BPA || {}).rows || []).concat(((stmts.BPP || {}).rows) || []));
  } else {
    rows = ((stmts[state.statement.toUpperCase()] || {}).rows || []);
  }

  if (!rows || rows.length === 0) {
    content.innerHTML = '<div class="loading">Sem dados para ' + titles[viewKey] + '</div>';
    return;
  }

  html += '<div class="reg-table">';
  html += '<div class="reg-title">' + titles[viewKey] + ' — ' + periodLabel + '</div>';
  html += '<div class="fin-stmt-scroll">';
  // [WebUI v1.3 fix 2] table-layout: fixed + colgroup (84px Código / 220px
  // Descrição, see app.css) — auto layout let the Código column stretch wide
  // when the ANNUAL table (fewer columns) was stretched to the container.
  // The inline min-width (frozen cols + 88px per period) keeps every period
  // column wide enough for the values; extra space spreads only over periods.
  html += '<table class="fin-stmt-table" style="min-width:' + (304 + labels.length * 88) + 'px">';
  html += '<colgroup><col style="width:84px"><col style="width:220px"></colgroup>';
  html += '<thead><tr>';
  html += '<th class="frozen-col">Código</th>';
  html += '<th class="frozen-col2">Descrição</th>';
  // [WebUI v1.3 fix 4] Period columns flow oldest → newest (left → right).
  labels.forEach(function(lab, i) {
    var d = dates[i] ? fmtDate(dates[i]) : '';
    html += '<th class="period-col" title="' + (d || lab) + '">' + lab + '</th>';
  });
  html += '</tr></thead><tbody>';

  // Rows grouped by section — emit a section header row on section change.
  var lastSection = null;
  rows.forEach(function(row) {
    if (row.section && row.section !== lastSection) {
      lastSection = row.section;
      html += '<tr class="section-row"><td colspan="2" class="frozen-sec">\u2014 ' + row.section + ' \u2014</td>';
      labels.forEach(function() { html += '<td class="sec-fill"></td>'; });
      html += '</tr>';
    }
    html += '<tr><td class="frozen-col">' + esc(row.codigo || '') + '</td>';
    html += '<td class="frozen-col2" title="' + esc(row.label || '') + '">' + esc(row.label || '') + '</td>';
    (row.values || []).forEach(function(v) {
      var cls = 'val';
      if (v !== null && v !== undefined && v < 0) cls += ' neg';
      html += '<td class="' + cls + '">' + fmtCompact(v) + '</td>';
    });
    html += '</tr>';
  });

  html += '</tbody></table></div></div>';
  content.innerHTML = html;

  chartDefs.forEach(function(def, i) {
    var cv = document.getElementById('fin-stmt-chart-' + i);
    if (cv) renderFinStmtChartDef(cv, def, labels);
  });
}

// ── Statement-specific chart machinery [WebUI v1.3 fix 2] ──
// Reference: PETR4 financials dashboard — each statement view gets its own
// charts (types, series and colors mirror the dashboard).

// Values array of a statement row, by codigo. keys = statement keys to search
// (e.g. ['BPA','BPP']). Returns null when the account doesn't exist.
function stmtRow(stmts, keys, code) {
  for (var i = 0; i < keys.length; i++) {
    var rows = ((stmts[keys[i]] || {}).rows) || [];
    for (var j = 0; j < rows.length; j++) {
      if (rows[j].codigo === code) return rows[j].values || [];
    }
  }
  return null;
}
// [WebUI v1.3 fix 4] Row values are OLDEST-FIRST (service normalizes both
// annual and quarterly) — just scale, no reversal.
function finSer(vals, div) {
  if (!vals) return null;
  var d = div || 1e6;
  return vals.map(function(v) { return (v === null || v === undefined) ? null : v / d; });
}
function finHasData(series) {
  return series.some(function(s) { return s && s.some(function(v) { return v !== null && v !== undefined; }); });
}
// Element-wise null-propagating arithmetic (series share the label order).
function finAdd(a, b) {
  if (!a || !b) return null;
  return a.map(function(v, i) { return (v === null || v === undefined || b[i] === null || b[i] === undefined) ? null : v + b[i]; });
}
function finRatio(num, den) {
  if (!num || !den) return null;
  return num.map(function(v, i) { return (v === null || v === undefined || !den[i]) ? null : v / den[i] * 100; });
}
// Normalize series to 100% of the per-period total (composition charts).
// [v1.7.1 fix1] Null-tolerant: the finHasData guards in buildFinStmtChartDefs
// use ANY-series semantics, but this helper indexed series[0].data directly —
// a company missing one composition code (e.g. no 2.01/2.02 breakdown while
// 2.03 exists) crashed the whole Demonstrações pane with "Cannot read
// properties of null (reading 'length')". Missing series now join as
// all-null so the chart renders the present ones.
function finPctStack(series) {
  var n = 0, i;
  for (i = 0; i < series.length; i++) {
    if (series[i] && series[i].data) { n = series[i].data.length; break; }
  }
  if (!n) return series;
  series = series.map(function(s) {
    return { label: s.label, color: s.color,
             data: (s && s.data) ? s.data : new Array(n).fill(null) };
  });
  var totals = [];
  for (i = 0; i < n; i++) {
    var t = 0, any = false;
    series.forEach(function(s) { var v = s.data[i]; if (v !== null && v !== undefined) { t += v; any = true; } });
    totals.push(any && t > 0 ? t : null);
  }
  return series.map(function(s) {
    return { label: s.label, color: s.color, data: s.data.map(function(v, i) { return (v !== null && v !== undefined && totals[i]) ? v / totals[i] * 100 : null; }) };
  });
}

// Chart definitions per view. Each def: {title, type, stacked, pctStacked,
// yTitle, unit, series:[{label,data,color}], lineOverlay?}.
function buildFinStmtChartDefs(viewKey, stmts) {
  var defs = [];
  function ser(code, keys, div) { return finSer(stmtRow(stmts, keys, code), div); }

  if (viewKey === 'completo') {
    // [WebUI v1.5] Ativo and Passivo+PL are SEPARATE chart pairs. The old
    // 5-series stack mixed BOTH balance sides (AC+ANC+PC+PNC+PL = 2× Ativo),
    // so every % Composição segment rendered at HALF its true share and the
    // absolute bars reached 2× company size.
    var ac = ser('1.01', ['BPA']), anc = ser('1.02', ['BPA']);
    var pc = ser('2.01', ['BPP']), pnc = ser('2.02', ['BPP']), plc = ser('2.03', ['BPP']);
    if (finHasData([ac, anc])) {
      var at = [
        { label: 'Ativo Circulante', data: ac, color: '#1e3a5f' },
        { label: 'Ativo Não Circulante', data: anc, color: '#60a5fa' }
      ];
      defs.push({ title: 'Ativo — Absoluto', stacked: true, yTitle: 'R$ (mi)', unit: 'mi', series: at });
      defs.push({ title: 'Ativo — % Composição', stacked: true, pctStacked: true, yTitle: '%', unit: 'pct', series: finPctStack(at) });
    }
    if (finHasData([pc, pnc, plc])) {
      var pa = [
        { label: 'Passivo Circulante', data: pc, color: '#991b1b' },
        { label: 'Passivo Não Circulante', data: pnc, color: '#fca5a5' },
        { label: 'Patrimônio Líquido', data: plc, color: '#22c55e' }
      ];
      defs.push({ title: 'Passivo + PL — Absoluto', stacked: true, yTitle: 'R$ (mi)', unit: 'mi', series: pa });
      defs.push({ title: 'Passivo + PL — % Composição', stacked: true, pctStacked: true, yTitle: '%', unit: 'pct', series: finPctStack(pa) });
    }
  } else if (viewKey === 'bpa') {
    var ac = ser('1.01', ['BPA']), anc = ser('1.02', ['BPA']);
    if (finHasData([ac, anc])) {
      var at = [
        { label: 'Ativo Circulante', data: ac, color: '#1e3a5f' },
        { label: 'Ativo Não Circulante', data: anc, color: '#60a5fa' }
      ];
      defs.push({ title: 'Ativo — Absoluto', stacked: true, yTitle: 'R$ (mi)', unit: 'mi', series: at });
      defs.push({ title: 'Ativo — % Composição', stacked: true, pctStacked: true, yTitle: '%', unit: 'pct', series: finPctStack(at) });
    }
    if (finHasData([ac])) defs.push({ title: 'Ativo Circulante', stacked: true, yTitle: 'R$ (mi)', unit: 'mi', series: [{ label: 'Ativo Circulante', data: ac, color: '#1e3a5f' }] });
    if (finHasData([anc])) defs.push({ title: 'Ativo Não Circulante', stacked: true, yTitle: 'R$ (mi)', unit: 'mi', series: [{ label: 'Ativo Não Circulante', data: anc, color: '#60a5fa' }] });
  } else if (viewKey === 'bpp') {
    var pc = ser('2.01', ['BPP']), pnc = ser('2.02', ['BPP']), pl = ser('2.03', ['BPP']);
    if (finHasData([pc, pnc, pl])) {
      var pa = [
        { label: 'Passivo Circulante', data: pc, color: '#991b1b' },
        { label: 'Passivo Não Circulante', data: pnc, color: '#fca5a5' },
        { label: 'Patrimônio Líquido', data: pl, color: '#22c55e' }
      ];
      defs.push({ title: 'Passivo + PL — Absoluto', stacked: true, yTitle: 'R$ (mi)', unit: 'mi', series: pa });
      defs.push({ title: 'Passivo + PL — % Composição', stacked: true, pctStacked: true, yTitle: '%', unit: 'pct', series: finPctStack(pa) });
    }
    if (finHasData([pc])) defs.push({ title: 'Passivo Circulante', stacked: true, yTitle: 'R$ (mi)', unit: 'mi', series: [{ label: 'Passivo Circulante', data: pc, color: '#991b1b' }] });
    if (finHasData([pnc])) defs.push({ title: 'Passivo Não Circulante', stacked: true, yTitle: 'R$ (mi)', unit: 'mi', series: [{ label: 'Passivo Não Circulante', data: pnc, color: '#fca5a5' }] });
  } else if (viewKey === 'dre') {
    var rec = ser('3.01', ['DRE']), brut = ser('3.03', ['DRE']), ebit = ser('3.05', ['DRE']), ll = ser('3.11', ['DRE']);
    // EBITDA = EBIT + D&A (D&A from DFC indirect 6.01.01.02 / direct 6.02.01.02).
    var da = ser('6.01.01.02', ['DFC']);
    if (!finHasData([da])) da = ser('6.02.01.02', ['DFC']);
    var ebitda = finAdd(ebit, da);
    if (finHasData([rec, ebitda, ll])) {
      defs.push({ title: 'Receita, EBITDA e Lucro — DRE', yTitle: 'R$ (mi)', unit: 'mi', series: [
        { label: 'Receita Líquida', data: rec, color: '#f59e0b' },
        { label: 'EBITDA', data: ebitda, color: '#d946a0' },
        { label: 'Lucro Líquido', data: ll, color: '#a855f7' }
      ]});
    }
    var mB = finRatio(brut, rec), mL = finRatio(ll, rec), mE = finRatio(ebit, rec), mEd = finRatio(ebitda, rec);
    if (finHasData([mB, mL, mE, mEd])) {
      defs.push({ title: 'Evolução das Margens', yTitle: 'Margem (%)', unit: 'pct', series: [
        { label: 'Marg. Bruta', data: mB, color: '#7f1d1d' },
        { label: 'Marg. Líquida', data: mL, color: '#be123c' },
        { label: 'Marg. EBIT', data: mE, color: '#f9a8d4' },
        { label: 'Marg. EBITDA', data: mEd, color: '#fbcfe8' }
      ]});
    }
  } else if (viewKey === 'dfc') {
    var fco = ser('6.01', ['DFC']), fci = ser('6.02', ['DFC']), fcf = ser('6.03', ['DFC']);
    if (finHasData([fco, fci, fcf])) {
      var fl = [
        { label: 'FCO', data: fco, color: '#0891b2' },
        { label: 'FCI', data: fci, color: '#ea580c' },
        { label: 'FCF', data: fcf, color: '#e11d48' }
      ];
      defs.push({ title: 'FCO, FCI e FCF por Período', yTitle: 'R$ (mi)', unit: 'mi', series: fl });
      defs.push({ title: 'Fluxos de Caixa Consolidados', stacked: true, yTitle: 'R$ (mi)', unit: 'mi', series: fl });
    }
    var llD = ser('3.11', ['DRE']);
    if (finHasData([fco, llD])) {
      defs.push({ title: 'Divergência FCO vs Lucro Líquido', yTitle: 'R$ (mi)', unit: 'mi',
        series: [{ label: 'FCO', data: fco, color: '#0891b2' }],
        lineOverlay: { label: 'Lucro Líquido', data: llD, color: '#a855f7' } });
    }
  } else if (viewKey === 'dva') {
    // New CVM taxonomy: 7.04 VA Bruto / 7.06 VA Líquido / 7.08 Total a
    // Distribuir (old-taxonomy fallbacks 7.03 / 7.05 / 7.07).
    var vaB = ser('7.04', ['DVA'], 1e9); if (!finHasData([vaB])) vaB = ser('7.03', ['DVA'], 1e9);
    var vaL = ser('7.06', ['DVA'], 1e9); if (!finHasData([vaL])) vaL = ser('7.05', ['DVA'], 1e9);
    var tot = ser('7.08', ['DVA'], 1e9); if (!finHasData([tot])) tot = ser('7.07', ['DVA'], 1e9);
    if (finHasData([vaB, vaL, tot])) {
      defs.push({ title: 'Geração de Valor Adicionado por Período', type: 'line', yTitle: 'R$ (bi)', unit: 'bi', series: [
        { label: 'VA Bruta', data: vaB, color: '#0d9488' },
        { label: 'VA Líquida', data: vaL, color: '#f59e0b' },
        { label: 'Total a Distribuir', data: tot, color: '#3b82f6' }
      ]});
    }
  }
  return defs;
}

function renderFinStmtChartDef(canvas, def, labels) {
  var th = chartTheme();
  if (canvas._chart) { try { canvas._chart.destroy(); } catch (e) { /* noop */ } }
  // [WebUI v1.3 fix 4] Labels are OLDEST-FIRST (service) — table and charts
  // share the same left → right chronological order.
  var chartLabels = labels;
  var datasets = def.series.map(function(s) {
    if (def.type === 'line') {
      return { label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.color,
               fill: false, tension: 0.3, pointRadius: 2, borderWidth: 2 };
    }
    return { label: s.label, data: s.data, backgroundColor: s.color, borderWidth: 0 };
  });
  if (def.lineOverlay) {
    datasets.push({ label: def.lineOverlay.label, data: def.lineOverlay.data, type: 'line',
      borderColor: def.lineOverlay.color, backgroundColor: def.lineOverlay.color,
      fill: false, tension: 0.3, pointRadius: 2, order: 0 });
  }
  var yTicks = { color: th.text };
  if (def.unit === 'pct') yTicks.callback = function(v) { return Number(v).toFixed(0) + '%'; };
  else if (def.unit === 'bi') yTicks.callback = function(v) { return 'R$ ' + Number(v).toFixed(1).replace('.', ',') + ' bi'; };
  else yTicks.callback = function(v) { return 'R$ ' + Number(v).toFixed(0) + ' mi'; };
  var y = { stacked: !!def.stacked, grid: { color: th.grid }, ticks: yTicks, title: { display: true, text: def.yTitle } };
  if (def.pctStacked) { y.min = 0; y.max = 100; y.ticks.stepSize = 25; }
  // [v1.19 fix 1] Quarterly labels ("4T2024") are too wide for the chart
  // cards, so Chart.js autoSkip silently thinned them to every OTHER label —
  // which landed on the 4T/2T positions only and read as "charts display
  // data just for 4T and 2T" (the bars were all there; the AXIS only named
  // those quarters — the table below, horizontally scrollable, showed every
  // column, which is why only the charts looked wrong). Annual "2016" labels
  // always fit, so only Trimestral was affected. Fix: abbreviate the tick
  // text ("4T2024" → "4T24") and rotate instead of skipping — every quarter
  // stays labeled.
  var xTicks = { color: th.text, maxTicksLimit: 14 };
  if (labels.length && /^\dT\d{4}$/.test(String(labels[0]))) {
    xTicks = {
      color: th.text,
      autoSkip: false,
      minRotation: 0,
      maxRotation: 90,
      callback: function(v, idx) {
        var m = /^(\dT)(\d{2})(\d{2})$/.exec(String(labels[idx]));
        return m ? m[1] + m[3] : String(labels[idx]);
      }
    };
  }
  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: def.type === 'line' ? 'line' : 'bar',
    data: { labels: chartLabels, datasets: datasets },
    options: { responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { stacked: !!def.stacked, grid: { color: th.grid }, ticks: xTicks },
        y: y
      },
      plugins: { legend: { display: true, position: 'top' } }
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════
// ── Valuation tab [WebUI v1.4] ─────────────────────────────────────────
// 5 lazy subtabs (Visão Geral / Múltiplos / Valor Intrínseco / Fundamentos
// / Todas as métricas). Each fetches its own JSON endpoint ONCE
// (panel._loaded guard); the server reuses the static dashboard's report
// builders, so overview/multiples/intrinsic payloads are lists of generic
// "section" dicts rendered by valSectionHtml below. Fundamentals uses a
// grouped payload; all-metrics uses a category-grouped payload.
// [v1.4 fix1] Tooltips on every item — KPI cards, two_column blocks,
// table first columns, ratio grids, heatmaps and all-metrics rows show
// the PT-BR formula on hover (ⓘ marker; title attribute).
// [v1.4 fix2] (a) Signed-value coloring everywhere (financials parity):
// negative numbers red; % values green (+) / red (−) / yellow (0).
// (b) Múltiplos + Fundamentos render as NESTED subtabs (renderValGrouped):
// Múltiplos → Preço | EBIT/EBITDA | EV | Menos Comuns; Fundamentos →
// Rentabilidade (Retornos | Margens) | Liquidez e Alavancagem (Liquidez |
// Endividamento) | Eficiência e Crescimento. (c) Todas as métricas:
// all groups collapsed by default.

window.loadValSubtab = function(sub) {
  var panel = document.getElementById('tab-val-' + sub);
  if (!panel || panel._loaded) return;
  var ticker = panel.getAttribute('data-ticker');
  if (!ticker) return;
  // [v1.5] _loaded is set only AFTER a successful render — the old code set
  // it before the fetch, so a failed subtab could never be retried.
  // [v1.7] Fetches through the generic adapter endpoint (/sections/<key>)
  // — same payload, now dispatched + contract-checked by the registry.
  fetch('/api/webui/company/' + encodeURIComponent(ticker) + '/sections/valuation:' + sub + '?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) { panel._loaded = true; renderValSubtab(sub, panel, data); })
    .catch(function(err) {
      panel.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
};

function renderValSubtab(sub, panel, data) {
  if (data._error) { panel.innerHTML = '<div class="error">Erro: ' + esc(data._error) + '</div>'; return; }
  // [v1.5] Fresh chart-config stash per render — indices used to keep
  // growing across re-renders of the same panel (stale configs leaked).
  panel._valChartCfgs = {};
  if (sub === 'fundamentals' || sub === 'multiples') { renderValGrouped(panel, data); return; }
  if (sub === 'all') { renderValAll(panel, data); return; }
  // overview / intrinsic → optional KPIs + generic sections
  var html = '';
  if (data.kpis && data.kpis.length) html += valKpisHtml(data.kpis);
  html += valSectionsHtml(data.sections || [], panel);
  panel.innerHTML = html || '<div class="loading">Sem dados</div>';
  mountValCharts(panel);
}

// ── [v1.24] Histórico tab — the company vs its OWN 5A history ─────────────
// 4 lazy subtabs (Visão Geral / Valuation 5A / Rentabilidade e Crescimento /
// Alavancagem e Risco) over the generic /sections/historical:<sub> endpoint.
// Flat payloads ({kpis?, sections}) — the SAME generic renderer as
// Valuation/Proventos/Opções (renderValSubtab: KPI cards + heatmap +
// side-by-side chart grids via fin-charts-grid + the collapsed tables).
window.loadHistSubtab = function(sub) {
  var panel = document.getElementById('tab-hist-' + sub);
  if (!panel || panel._loaded || panel._loading) return;
  var ticker = panel.getAttribute('data-ticker');
  if (!ticker) return;
  panel._loading = true;
  fetch('/api/webui/company/' + encodeURIComponent(ticker) +
        '/sections/historical:' + encodeURIComponent(sub) + '?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      panel._loading = false;
      panel._loaded = true;   // only after a successful render (v1.5 rule)
      renderValSubtab(sub, panel, data);
    })
    .catch(function(err) {
      panel._loading = false;
      panel.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
};

// ── [v1.26] Governança tab (CGVN) — score/práticas ──────────────────────
// The Código de Melhores Práticas SELF-ASSESSMENT: how the company
// SAYS it is governed. Visão Geral is the GENERIC payload (/sections/
// governance:overview — KPIs + donut + chapter bars + score evolution);
// Práticas is a custom renderer (filter bar + expandable rows are
// interactive state — the proventos:historico precedent). The IPE
// events explorer is its OWN tab since v1.26 fix 1 (see the
// Informações Periódicas module below). All strings pass through esc().
var govPr = { ticker: '', dataRef: '', capitulo: '', adotada: '',
              q: '', timer: null };

window.loadGovSubtab = function(sub) {
  var panel = document.getElementById('tab-gov-' + sub);
  if (!panel || panel._loaded || panel._loading) return;
  var ticker = panel.getAttribute('data-ticker');
  if (!ticker) return;
  if (sub === 'overview') {
    panel._loading = true;
    fetch('/api/webui/company/' + encodeURIComponent(ticker) +
          '/sections/governance:overview?_t=' + Date.now())
      .then(function(r) { return r.json(); })
      .then(function(data) {
        panel._loading = false;
        panel._loaded = true;
        renderValSubtab('overview', panel, data);
      })
      .catch(function(err) {
        panel._loading = false;
        panel.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
      });
  } else if (sub === 'practices') {
    govPr.ticker = ticker;
    govPracticesLoad(panel);
  }
};

// .. Práticas (CGVN) — Exercício/Capítulo/Situação selects + busca .....
function govPracticesLoad(panel) {
  panel._loading = true;
  var url = '/api/webui/company/' + encodeURIComponent(govPr.ticker) +
    '/governance/practices?data_ref=' + encodeURIComponent(govPr.dataRef) +
    '&capitulo=' + encodeURIComponent(govPr.capitulo) +
    '&adotada=' + encodeURIComponent(govPr.adotada) +
    '&q=' + encodeURIComponent(govPr.q) + '&_t=' + Date.now();
  fetch(url)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      panel._loading = false;
      if (data._error) {
        panel.innerHTML = '<div class="error">Erro: ' + esc(data._error) + '</div>';
        return;
      }
      panel._loaded = true;
      govPr.dataRef = data.data_referencia || '';
      renderGovPractices(panel, data);
    })
    .catch(function(err) {
      panel._loading = false;
      panel.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
}

function _govAdotBadge(v) {
  var cls = { 'Sim': 'ok', 'Parcialmente': 'warn', 'Não': 'err',
              'Não se Aplica': 'na' }[v] || 'na';
  return '<span class="gov-badge gov-badge-' + cls + '">' + esc(v || '—') + '</span>';
}

function renderGovPractices(panel, data) {
  var filings = data.filings || [];
  var exSel = '<select class="gov-sel" data-govp="data_ref" aria-label="Exercício">';
  Array.prototype.forEach.call(filings, function(f) {
    var lbl = String(f.exercicio || f.data_referencia || '—') +
      ' — ' + _govPctBR(f.score_pct) + ' (' + f.sim + '/' + f.total + ')';
    var sel = (f.data_referencia === data.data_referencia) ? ' selected' : '';
    exSel += '<option value="' + esc(f.data_referencia) + '"' + sel + '>' +
             esc(lbl) + '</option>';
  });
  exSel += '</select>';
  var capSel = '<select class="gov-sel" data-govp="capitulo" aria-label="Capítulo">' +
    '<option value="">Todos os capítulos</option>';
  Array.prototype.forEach.call(data.capitulos || [], function(c) {
    capSel += '<option value="' + esc(c) + '"' +
      (c === data.filters.capitulo ? ' selected' : '') + '>' + esc(c) + '</option>';
  });
  capSel += '</select>';
  var adoSel = '<select class="gov-sel" data-govp="adotada" aria-label="Situação">' +
    '<option value="">Todas as situações</option>';
  Array.prototype.forEach.call(data.adotadas || [], function(a) {
    adoSel += '<option value="' + esc(a) + '"' +
      (a === data.filters.adotada ? ' selected' : '') + '>' + esc(a) + '</option>';
  });
  adoSel += '</select>';

  var linkHtml = data.link
    ? ' · <a class="gov-doc-link" href="' + esc(data.link) + '" target="_blank" rel="noopener">📄 protocolo na CVM</a>'
    : '';
  var h = '<div class="gov-card">' +
    '<div class="gov-pr-head">Exercício <strong>' + esc(String(data.exercicio || '—')) +
    '</strong> · entregue em ' + esc(fmtDate(data.data_entrega)) + linkHtml + '</div>' +
    '<div class="gov-filterbar">' +
    '<label class="gov-fl">Exercício ' + exSel + '</label>' +
    '<label class="gov-fl">Capítulo ' + capSel + '</label>' +
    '<label class="gov-fl">Situação ' + adoSel + '</label>' +
    '<label class="gov-fl gov-fl-grow">Busca <input type="search" class="gov-input" data-govp="q"' +
    ' placeholder="prática, explicação, item…" value="' + esc(data.filters.q || '') + '"></label>' +
    '<button type="button" class="gov-clear" data-govp-clear="1">Limpar</button>' +
    '</div></div>';

  var rows = data.rows || [];
  h += '<div class="val-section"><div class="reg-title">Práticas Recomendadas — ' +
    rows.length + ' linha(s)' +
    (data.filters.capitulo ? ' · ' + esc(data.filters.capitulo) : '') + '</div>';
  h += '<div class="gov-table-wrap"><table class="val-table gov-table"><thead><tr>' +
    '<th>Item</th><th>Capítulo</th><th>Prática Recomendada</th><th>Situação</th><th></th>' +
    '</tr></thead><tbody>';
  Array.prototype.forEach.call(rows, function(r, i) {
    h += '<tr class="gov-pr-row" data-govx="' + i + '">' +
      '<td class="gov-item">' + esc(r.id_item) + '</td>' +
      '<td class="gov-cap">' + esc(r.capitulo) + '</td>' +
      '<td class="gov-prat">' + esc(r.pratica) + '</td>' +
      '<td>' + _govAdotBadge(r.adotada) + '</td>' +
      '<td class="gov-chev">▸</td></tr>';
  });
  if (!rows.length) {
    h += '<tr><td colspan="5" class="gov-empty">Nenhuma prática para os filtros atuais.</td></tr>';
  }
  h += '</tbody></table></div>';
  // Expandable detail rows (Explicação texts are huge — click reveals).
  h += '<div class="gov-pr-details" style="display:none">';
  Array.prototype.forEach.call(rows, function(r, i) {
    h += '<div class="gov-pr-detail" data-govd="' + i + '">' +
      '<span class="gov-pr-det-k">Princípio</span> ' + esc(r.principio || '—') +
      '<br><span class="gov-pr-det-k">Explicação da companhia</span> ' +
      esc(r.explicacao || '— sem explicação declarada') + '</div>';
  });
  h += '</div></div>';
  panel.innerHTML = h;

  // wire: selects + busca (debounce) + limpar + expandable rows
  Array.prototype.forEach.call(panel.querySelectorAll('[data-govp]'), function(el) {
    if (el.tagName === 'SELECT') {
      el.onchange = function() {
        govPr[el.getAttribute('data-govp') === 'data_ref' ? 'dataRef'
                : el.getAttribute('data-govp')] = el.value;
        govPracticesLoad(panel);
      };
    } else {
      el.oninput = function() {
        clearTimeout(govPr.timer);
        govPr.timer = setTimeout(function() { govPr.q = el.value; govPracticesLoad(panel); }, 350);
      };
    }
  });
  var clearBtn = panel.querySelector('[data-govp-clear]');
  if (clearBtn) clearBtn.onclick = function() {
    govPr.capitulo = ''; govPr.adotada = ''; govPr.q = '';
    govPracticesLoad(panel);
  };
  panel._govToggle = panel._govToggle || function(ev) {
    var tr = ev.target && ev.target.closest ? ev.target.closest('tr.gov-pr-row') : null;
    if (!tr) return;
    var i = tr.getAttribute('data-govx');
    var det = panel.querySelector('.gov-pr-detail[data-govd="' + i + '"]');
    if (!det) return;
    var open = tr.classList.toggle('gov-open');
    det.style.display = open ? '' : 'none';
    var chev = tr.querySelector('.gov-chev');
    if (chev) chev.textContent = open ? '▾' : '▸';
  };
  panel.onclick = panel._govToggle;
}

// .. percent helper (pt-BR) — shared by the Governança renderers .....
function _govPctBR(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return Number(v * 100).toLocaleString('pt-BR',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%';
}

// ── [v1.26 fix 1] Informações Periódicas tab (IPE) — faceted events ────
// SPLIT from Governança into its OWN tab (the user's verdict: "both
// provide info, but they are not supposed to be together, different
// purpose") — CGVN is the self-assessment, IPE is WHAT THE COMPANY
// FILED (AGO/AGE, avisos aos acionistas, fatos relevantes, calendário
// de eventos corporativos). No subtabs: initIpeTab() boots the ONE
// explorer pane (#tab-ipe-events) when the tab fragment lands
// (afterSettle — the initBacktestTab no-op-away-from-the-tab
// precedent). The .gov-* CSS classes are SHARED with Governança
// (same card/filterbar/chip look). The Ano select is CHRONOLOGICAL,
// newest first — server-side since v1.26 fix 1.
var ipeEv = { ticker: '', categoria: '', tipo: '', especie: '', ano: '',
              q: '', page: 1, pages: 1, timer: null };

window.initIpeTab = function() {
  var panel = document.getElementById('tab-ipe-events');
  if (!panel || panel._loaded || panel._loading) return;
  var ticker = panel.getAttribute('data-ticker');
  if (!ticker) return;
  ipeEv.ticker = ticker;
  ipeLoad(panel);
};

function _ipeFacetOptions(field, facets, current, emptyLabel) {
  var list = (facets && facets[field]) || [];
  var h = '';
  var has = {};
  Array.prototype.forEach.call(list, function(o) {
    var val = o.v === '' ? '__none__' : o.v;
    has[val] = true;
    var lbl = o.v === '' ? emptyLabel : o.v;
    h += '<option value="' + esc(val) + '"' +
      (val === current ? ' selected' : '') + '>' + esc(lbl) + ' (' + o.n + ')</option>';
  });
  // the current value may be absent from the narrowed facet list (a
  // combination with no co-occurrence) — keep it visible so the user
  // sees WHY the table is empty instead of a silently-reset select.
  if (current && !has[current]) {
    var curLbl = current === '__none__' ? emptyLabel : current;
    h = '<option value="' + esc(current) + '" selected>' + esc(curLbl) + ' (0)</option>' + h;
  }
  return h;
}

function ipeLoad(panel) {
  panel._loading = true;
  var url = '/api/webui/company/' + encodeURIComponent(ipeEv.ticker) +
    '/ipe/events?categoria=' + encodeURIComponent(ipeEv.categoria) +
    '&tipo=' + encodeURIComponent(ipeEv.tipo) +
    '&especie=' + encodeURIComponent(ipeEv.especie) +
    '&ano=' + encodeURIComponent(ipeEv.ano) +
    '&q=' + encodeURIComponent(ipeEv.q) +
    '&page=' + ipeEv.page + '&per_page=25&_t=' + Date.now();
  fetch(url)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      panel._loading = false;
      if (data._error) {
        panel.innerHTML = '<div class="error">Erro: ' + esc(data._error) + '</div>';
        return;
      }
      panel._loaded = true;
      ipeEv.page = data.page || 1;
      ipeEv.pages = data.pages || 1;
      renderIpeEvents(panel, data);
    })
    .catch(function(err) {
      panel._loading = false;
      panel.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
}

function ipeReset() {
  ipeEv.page = 1;
}

function renderIpeEvents(panel, data) {
  var f = data.filters || {};
  var facets = data.facets || {};

  // Quick chips — only values that exist for this ticker (data-driven,
  // no dead chips). Presence is checked against the chip's OWN field's
  // facet (Assembleias → categorias; AGO/AGE → tipos). Active = set.
  var chipHtml = '';
  var chipFacet = { categoria: 'categorias', tipo: 'tipos' };
  Array.prototype.forEach.call(data.chips || [], function(c) {
    var fl = (facets[chipFacet[c.field]] ) || [];
    var present = Array.prototype.some.call(fl, function(o) { return o.v === c.value; });
    if (!present) return;
    var active = f[c.field] === c.value;
    chipHtml += '<button type="button" class="gov-chip' + (active ? ' active' : '') +
      '" data-chip-field="' + esc(c.field) + '" data-chip-val="' + esc(c.value) +
      '" aria-pressed="' + (active ? 'true' : 'false') + '">' + esc(c.label) + '</button>';
  });

  var catSel = '<select class="gov-sel" data-ipef="categoria" aria-label="Categoria">' +
    '<option value="">Todas as categorias</option>' +
    _ipeFacetOptions('categorias', facets, f.categoria, '— sem categoria —') + '</select>';
  var tipSel = '<select class="gov-sel" data-ipef="tipo" aria-label="Tipo">' +
    '<option value="">Todos os tipos</option>' +
    _ipeFacetOptions('tipos', facets, f.tipo, '— sem tipo —') + '</select>';
  var espSel = '<select class="gov-sel" data-ipef="especie" aria-label="Espécie">' +
    '<option value="">Todas as espécies</option>' +
    _ipeFacetOptions('especies', facets, f.especie, '— sem espécie —') + '</select>';
  var anoSel = '<select class="gov-sel" data-ipef="ano" aria-label="Ano">' +
    '<option value="">Todos os anos</option>' +
    _ipeFacetOptions('anos', facets, f.ano, '—') + '</select>';

  var h = '<div class="gov-card">' +
    '<div class="gov-ev-head"><strong>' + esc(data.nome || ipeEv.ticker) + '</strong>' +
    ' · <span class="gov-ev-total">' + Number(data.total || 0).toLocaleString('pt-BR') +
    ' evento(s) com os filtros atuais</span></div>';
  if (chipHtml) h += '<div class="gov-chips">' + chipHtml + '</div>';
  h += '<div class="gov-filterbar">' +
    '<label class="gov-fl">Categoria ' + catSel + '</label>' +
    '<label class="gov-fl">Tipo ' + tipSel + '</label>' +
    '<label class="gov-fl">Espécie ' + espSel + '</label>' +
    '<label class="gov-fl">Ano ' + anoSel + '</label>' +
    '<label class="gov-fl gov-fl-grow">Busca <input type="search" class="gov-input" data-ipef="q"' +
    ' placeholder="assunto…" value="' + esc(f.q || '') + '"></label>' +
    '<button type="button" class="gov-clear" data-ipef-clear="1">Limpar</button>' +
    '</div></div>';

  var evs = data.events || [];
  h += '<div class="val-section"><div class="reg-title">Eventos — Informações Periódicas e Eventuais (CVM)</div>';
  h += '<div class="gov-table-wrap"><table class="val-table gov-table gov-ev-table"><thead><tr>' +
    '<th>Data</th><th>Categoria</th><th>Tipo</th><th>Espécie</th><th>Assunto</th><th></th>' +
    '</tr></thead><tbody>';
  Array.prototype.forEach.call(evs, function(e) {
    var title = e.assunto || e.tipo || e.categoria || '—';
    var ver = (e.versao && e.versao > 1)
      ? ' <span class="gov-ver" title="Reapresentação">v' + esc(String(e.versao)) + '</span>' : '';
    h += '<tr>' +
      '<td class="gov-date">' + esc(fmtDate(e.data_entrega)) + ver + '</td>' +
      '<td class="gov-cat">' + esc(e.categoria || '—') + '</td>' +
      '<td class="gov-tip">' + esc(e.tipo || '—') + '</td>' +
      '<td class="gov-esp">' + esc(e.especie || '—') + '</td>' +
      '<td class="gov-assunto">' + esc(title) +
        (e.data_referencia && e.data_referencia !== e.data_entrega
          ? ' <span class="gov-ref">(ref. ' + esc(fmtDate(e.data_referencia)) + ')</span>' : '') +
      '</td>' +
      '<td>' + (e.link_download
        ? '<a class="gov-doc-link" href="' + esc(e.link_download) +
          '" target="_blank" rel="noopener" title="Abrir documento na CVM">📄</a>'
        : '—') + '</td></tr>';
  });
  if (!evs.length) {
    h += '<tr><td colspan="6" class="gov-empty">Nenhum evento para os filtros atuais.</td></tr>';
  }
  h += '</tbody></table></div>';
  // pager (the Carteira ledger pattern)
  if ((data.pages || 1) > 1) {
    h += '<div class="cart-pager">' +
      '<span class="cart-pager-info">' + Number(data.total || 0).toLocaleString('pt-BR') +
      ' evento(s)</span>' +
      '<button type="button" class="cart-btn cart-pager-btn" data-ipepg="prev"' +
      (data.page <= 1 ? ' disabled' : '') + '>◀</button>' +
      '<span class="cart-pager-page">' + data.page + ' / ' + data.pages + '</span>' +
      '<button type="button" class="cart-btn cart-pager-btn" data-ipepg="next"' +
      (data.page >= data.pages ? ' disabled' : '') + '>▶</button>' +
      '</div>';
  }
  h += '</div>';
  panel.innerHTML = h;

  // wire: facet selects (reset page), busca (debounce), limpar, chips, pager
  Array.prototype.forEach.call(panel.querySelectorAll('[data-ipef]'), function(el) {
    if (el.tagName === 'SELECT') {
      el.onchange = function() {
        ipeEv[el.getAttribute('data-ipef')] = el.value;
        ipeReset(); ipeLoad(panel);
      };
    } else {
      el.oninput = function() {
        clearTimeout(ipeEv.timer);
        ipeEv.timer = setTimeout(function() {
          ipeEv.q = el.value; ipeReset(); ipeLoad(panel);
        }, 350);
      };
    }
  });
  var evClear = panel.querySelector('[data-ipef-clear]');
  if (evClear) evClear.onclick = function() {
    ipeEv.categoria = ''; ipeEv.tipo = ''; ipeEv.especie = '';
    ipeEv.ano = ''; ipeEv.q = '';
    ipeReset(); ipeLoad(panel);
  };
  Array.prototype.forEach.call(panel.querySelectorAll('[data-chip-field]'), function(ch) {
    ch.onclick = function() {
      var fld = ch.getAttribute('data-chip-field');
      var val = ch.getAttribute('data-chip-val');
      ipeEv[fld] = (ipeEv[fld] === val) ? '' : val;   // toggle
      ipeReset(); ipeLoad(panel);
    };
  });
  Array.prototype.forEach.call(panel.querySelectorAll('[data-ipepg]'), function(btn) {
    btn.onclick = function() {
      var d = btn.getAttribute('data-ipepg') === 'next' ? 1 : -1;
      ipeEv.page = Math.min(Math.max(1, ipeEv.page + d), ipeEv.pages);
      ipeLoad(panel);
    };
  });
}

// ── [v1.25] Backtest — the interactive simulator. [v1.28.1] a FERRAMENTAS
// tool (moved from the company tab — the user's ask: "lets move backtest
// from companies to tools, to be with the other interactive tools we
// added — you will have do adapt to search for ticker"). The static
// PETR4_backtest_dashboard.html was ONE frozen scenario per HTML file
// (fixed thresholds, no costs, no stops, no comparison). This module is
// the interactive rebirth: a TICKER PICKER (the screener's single-
// selection pattern, ?b=PETR4 deep link) opens a parameter form fed by
// /backtest/meta (every strategy ships its own threshold specs), runs
// via POST /backtest/run, renders KPIs + equity × buy&hold + drawdown +
// price-with-trade-markers + the trade log, and keeps a PINNED SCENARIO
// list (localStorage, per ticker) with a comparison table + overlaid
// equity curves — the "different scenarios" the static report could
// never do. All server strings pass through esc(); charts are destroyed
// via canvas._chart (destroyChartsIn covers every re-render).
//
// [v1.28.1] polish: chart axes + tooltips in dd/mm/aaaa (the BR
// standard — they were aaaa-mm-dd), the trade log's headers aligned
// with the data columns (th-num over the right-aligned .val-val cells),
// two new KPI cards (Retorno Médio/Trade + Tempo Médio Posição — the
// payload already carried them, the grid never showed them) and a
// proper loading card while /backtest/meta opens a ticker.
var btState = { meta: null, ticker: '', result: null, running: false,
                toolBooted: false, activeIdx: -1 };

// scenario pin colors (fixed roster — the overlay legend stays readable)
var BT_SCEN_COLORS = ['#0d9488', '#2563eb', '#d97706', '#7c3aed', '#dc2626',
                      '#0891b2', '#65a30d', '#db2777'];
var BT_SCEN_MAX = 8;

function _btPct(v, dec) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return Number(v).toLocaleString('pt-BR',
    { minimumFractionDigits: dec === undefined ? 2 : dec,
      maximumFractionDigits: dec === undefined ? 2 : dec }) + '%';
}
function _btNum(v, dec) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return Number(v).toLocaleString('pt-BR',
    { minimumFractionDigits: dec || 0, maximumFractionDigits: dec || 0 });
}
function _btSignClass(v) { return v > 0 ? 'pos' : (v < 0 ? 'neg' : 'neu'); }

// [v1.28.1] ISO aaaa-mm-dd → dd/mm/aaaa for the chart axes/tooltips
// (fmtDate passes anything that isn't a full ISO date through — the
// downsampled labels are always full dates, so this is exact).
function _btDateFmt(v) { return fmtDate(String(v)); }

// [v1.28.1] Shared x-axis + tooltip config for every backtest chart —
// the BR date format on the ticks AND the tooltip title.
function _btDateScale(maxTicks) {
  return { grid: { color: chartTheme().grid },
           ticks: { color: chartTheme().text, maxTicksLimit: maxTicks || 10,
                    callback: function(v) {
                      return _btDateFmt(this.getLabelForValue(v));
                    } } };
}
function _btDateTooltip() {
  return { callbacks: { title: function(items) {
            return items && items[0] ? _btDateFmt(items[0].label) : '';
          } } };
}
// date-formatted tooltip + a custom label callback (the money lines)
function _btDateTooltipLabel(labelFn) {
  var tip = _btDateTooltip();
  tip.callbacks.label = labelFn;
  return tip;
}

// ── the picker (the screener's single-ticker pattern, its own ids) ──

window.btToolFocusPicker = function() {
  var el = document.getElementById('bt-tool-search');
  if (el) el.focus();
};

function initBacktestTool() {
  var input = document.getElementById('bt-tool-search');
  var drop = document.getElementById('bt-tool-dropdown');
  if (!input || !drop || btState.toolBooted) return;
  btState.toolBooted = true;

  // Deep link: ?b=PETR4 — opens the simulator and switches the family
  // pill (same as the screener's ?s= boot).
  var bootTk = '';
  try {
    bootTk = (new URLSearchParams(window.location.search).get('b') || '')
      .trim().toUpperCase();
  } catch (e) { /* noop */ }
  if (/^[A-Z0-9]{4,6}$/.test(bootTk)) {
    btState.ticker = bootTk;
    try {
      var pill = document.getElementById('family-pill-backtest');
      if (pill) pill.click();
    } catch (e) { /* noop */ }
  }

  var debounce = null;
  input.addEventListener('input', function() {
    clearTimeout(debounce);
    var q = input.value.trim();
    if (!q) { btToolDropHide(drop); return; }
    debounce = setTimeout(function() { btToolDropSearch(drop, q); }, 250);
  });
  input.addEventListener('keydown', function(ev) {
    var items = drop._items || [];
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      if (!items.length) return;
      ev.preventDefault();
      btState.activeIdx = ev.key === 'ArrowDown'
        ? Math.min(btState.activeIdx + 1, items.length - 1)
        : Math.max(btState.activeIdx - 1, 0);
      btToolDropRender(drop);
    } else if (ev.key === 'Enter') {
      ev.preventDefault();
      var tk = (btState.activeIdx >= 0 && items[btState.activeIdx])
        ? items[btState.activeIdx].ticker
        : input.value.trim().toUpperCase();
      if (tk) { btToolSetTicker(tk); input.value = ''; btToolDropHide(drop); }
    } else if (ev.key === 'Escape') {
      btToolDropHide(drop);
    }
  });
  document.addEventListener('click', function(ev) {
    if (!drop.hidden && drop.parentNode && !drop.parentNode.contains(ev.target)) {
      btToolDropHide(drop);
    }
  });

  if (btState.ticker) btToolOpen(); else btToolShowEmpty();
}

function btToolDropSearch(drop, q) {
  fetch('/api/webui/tools/comparison/search?q=' + encodeURIComponent(q))
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var items = (d && d.results) || [];
      if (!items.length) {
        drop._items = null; btState.activeIdx = -1;
        drop.hidden = true;
        return;
      }
      drop._items = items;
      btState.activeIdx = -1;
      btToolDropRender(drop);
    })
    .catch(function() { btToolDropHide(drop); });
}

function btToolDropRender(drop) {
  var items = drop._items || [];
  var current = btState.ticker;
  var html = '';
  items.forEach(function(it, i) {
    var isCur = it.ticker === current;
    html += '<button type="button" class="cmp-drop-item' +
      (i === btState.activeIdx ? ' active' : '') + (isCur ? ' added' : '') +
      '" data-tk="' + esc(it.ticker) + '">' +
      '<span class="cmp-drop-tk">' + esc(it.ticker) + '</span>' +
      '<span class="cmp-drop-name">' + esc(it.name || '') + '</span>' +
      (isCur ? '<span class="cmp-drop-added">no backtest</span>' : '') +
      '</button>';
  });
  drop.innerHTML = html;
  drop.hidden = false;
  Array.prototype.forEach.call(drop.querySelectorAll('.cmp-drop-item'), function(btn) {
    btn.addEventListener('click', function() {
      var input = document.getElementById('bt-tool-search');
      btToolSetTicker(btn.getAttribute('data-tk') || '');
      if (input) input.value = '';
      btToolDropHide(drop);
    });
  });
}

function btToolDropHide(drop) {
  drop.hidden = true;
  drop._items = null;
  btState.activeIdx = -1;
}

function btToolSetTicker(tk) {
  tk = String(tk || '').trim().toUpperCase();
  // Same B3 shape the server validates — anything from the dropdown or
  // free typing must match before it reaches the API.
  if (!/^[A-Z0-9]{4,6}$/.test(tk) || tk === btState.ticker) return;
  btState.ticker = tk;
  btToolSyncUrl();
  btToolOpen();
}

function btToolSyncUrl() {
  // Only THIS tool's ?b= key is rewritten — the comparison's ?t= and
  // the screener's ?s= deep links survive alongside.
  try {
    var url = new URL(window.location.href);
    if (btState.ticker) {
      url.searchParams.set('b', btState.ticker);
    } else {
      url.searchParams.delete('b');
    }
    window.history.replaceState('', '', url.pathname + url.search);
  } catch (e) { /* noop */ }
}

window.btToolClear = function() {
  btState.ticker = '';
  btState.meta = null;
  btState.result = null;
  btToolSyncUrl();
  btToolShowEmpty();
  btToolFocusPicker();
};

function btToolShowEmpty() {
  var box = document.getElementById('bt-tool-result');
  if (!box) return;
  destroyChartsIn(box);
  box.innerHTML =
    '<div class="cmp-empty">' +
    '<div class="cmp-empty-icon">⏪</div>' +
    '<p class="cmp-empty-title">Escolha um ticker para simular</p>' +
    '<p class="cmp-empty-hint">Informe o ticker acima. O backtest roda ' +
    '8 estratégias (valor, qualidade, renda, composta, cruzamento de ' +
    'médias e buy &amp; hold) com parâmetros livres — período, capital, ' +
    '% de posição, dias máximos, stop, take e corretagem — e fixa ' +
    'cenários lado a lado para comparar.</p></div>';
}

// open ONE ticker: loading card → /backtest/meta → the full shell
// [v1.28.2] + the stale-response guard (the cmpLoad/scrLoad rule): the
// meta build for ticker A must never overwrite the shell of ticker B.
var btToolReqSeq = 0;

function btToolOpen() {
  var box = document.getElementById('bt-tool-result');
  if (!box || !btState.ticker) return;
  var seq = ++btToolReqSeq;
  destroyChartsIn(box);
  btState.meta = null;
  btState.result = null;
  box.innerHTML = toolLoadingHtml('bt-load',
    'Abrindo o backtest de ' + esc(btState.ticker),
    'Carregando as estratégias e o histórico de preços do ticker…');
  toolLoadingStart('bt-load');
  fetch('/api/webui/company/' + encodeURIComponent(btState.ticker) +
        '/backtest/meta?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(meta) {
      if (seq !== btToolReqSeq) return;  // superseded — a newer ticker owns the pane
      toolLoadingStop('bt-load');
      if (meta._error) {
        box.innerHTML = '<div class="error">Erro: ' + esc(meta._error) + '</div>' +
          '<p class="scr-back"><button type="button" class="cmp-range-btn" ' +
          'onclick="btToolClear()">← escolher outro ticker</button></p>';
        return;
      }
      btState.meta = meta;
      _btRenderShell();
    })
    .catch(function(err) {
      if (seq !== btToolReqSeq) return;  // superseded — stay quiet
      toolLoadingStop('bt-load');
      box.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>' +
        '<p class="scr-back"><button type="button" class="cmp-range-btn" ' +
        'onclick="btToolClear()">← escolher outro ticker</button></p>';
    });
}

function _btRenderShell() {
  // [v1.28.1] The shell renders INSIDE the tool's result box — the
  // company tab's #bt-root partial is gone; the picker above owns the
  // ticker now. Everything below (#bt-result, #bt-scenarios, the form
  // inputs) keeps its v1.25 ids — btRun/btPinScenario/… unchanged.
  var box = document.getElementById('bt-tool-result');
  if (!box) return;
  var m = btState.meta;
  var d = m.defaults || {};
  var html = '<div class="tab-backtest" id="bt-root">';

  // ── 0. the ticker context row (the picker is above; this anchors
  //    WHAT is being simulated, with a jump into the company page) ──
  html += '<div class="bt-tickerbar">' +
    '<div class="bt-ticker-main"><span class="bt-ticker-label">Simulando</span>' +
    '<span class="bt-ticker-tk">' + esc(btState.ticker) + '</span>' +
    (m.range ? '<span class="bt-ticker-range">' + esc(fmtDate(m.range.first)) +
     ' → ' + esc(fmtDate(m.range.last)) + '</span>' : '') +
    '</div>' +
    '<div class="bt-ticker-actions">' +
    '<a class="cmp-range-btn" href="/webui/company/' + encodeURIComponent(btState.ticker) +
    '" title="Abrir a página da empresa">abrir empresa ↗</a>' +
    '<button type="button" class="cmp-range-btn" title="Escolher outro ticker"' +
    ' onclick="btToolClear()">trocar ticker</button>' +
    '</div></div>';

  // ── 1. Parâmetros ──
  html += '<div class="bt-card bt-form-card">';
  html += '<div class="bt-card-title">Parâmetros</div>';
  html += '<div class="bt-form">';
  // strategy + period row
  html += '<div class="bt-field"><span>Estratégia</span>' +
    '<select id="bt-strategy" class="bt-select" onchange="btStrategyChange()">';
  (m.strategies || []).forEach(function(s) {
    html += '<option value="' + esc(s.name) + '">' + esc(s.label) + '</option>';
  });
  html += '</select><div class="bt-field-note" id="bt-strategy-desc"></div></div>';
  // period presets + dates
  html += '<div class="bt-field"><span>Período</span>' +
    '<div class="bt-presets" id="bt-presets">';
  (m.presets || []).forEach(function(p, i) {
    html += '<button type="button" class="bt-preset-btn' +
      (p.label === '3A' ? ' active' : '') + '" data-start="' + esc(p.start) +
      '" data-end="' + esc(p.end) + '" onclick="btPreset(this)">' + esc(p.label) + '</button>';
  });
  html += '</div><div class="bt-dates">' +
    '<input type="date" id="bt-start" value="' + esc(d.start_date || '') + '">' +
    '<span class="bt-dates-sep">→</span>' +
    '<input type="date" id="bt-end" value="' + esc(d.end_date || '') + '">' +
    '</div></div>';
  // engine params
  html += '<div class="bt-params-grid">';
  html += '<div class="bt-field"><span>Capital inicial (R$)</span>' +
    '<input type="number" id="bt-capital" min="100" step="500" value="' +
    esc(String(d.initial_capital || 10000)) + '"></div>';
  html += '<div class="bt-field"><span>% do capital por entrada</span>' +
    '<input type="number" id="bt-position" min="5" max="100" step="5" value="' +
    esc(String(d.position_pct || 100)) + '"></div>';
  html += '<div class="bt-field" id="bt-field-mh"><span>Dias máx. de posição (0 = sem limite)</span>' +
    '<input type="number" id="bt-maxhold" min="0" max="2520" step="21" value="' +
    esc(String(d.max_holding_days || 0)) + '"></div>';
  html += '<div class="bt-field" id="bt-field-st"><span>Stop-loss % (0 = desligado)</span>' +
    '<input type="number" id="bt-stop" min="0" max="95" step="1" value="0"></div>';
  html += '<div class="bt-field" id="bt-field-tp"><span>Take-profit % (0 = desligado)</span>' +
    '<input type="number" id="bt-take" min="0" max="1000" step="5" value="0"></div>';
  html += '<div class="bt-field"><span>Corretagem por operação (R$)</span>' +
    '<input type="number" id="bt-fee" min="0" step="1" value="0"></div>';
  html += '</div>'; // bt-params-grid
  // dynamic thresholds + exit toggle
  html += '<div id="bt-thresholds"></div>';
  html += '<div class="bt-exit-row" id="bt-exit-row">' +
    '<label class="bt-check"><input type="checkbox" id="bt-exitsignal">' +
    ' Sair quando o sinal reverter (usa os limiares de saída abaixo)</label></div>';
  // run button + notes
  html += '<div class="bt-actions"><button type="button" class="bt-run-btn" id="bt-run-btn" onclick="btRun()">▶ Executar backtest</button></div>';
  html += '<div class="bt-note">Decisões no fechamento do pregão (sem look-ahead intradiário); ' +
    'stop/take verificados no fechamento diário; proventos não são reinvestidos; ' +
    'Sharpe com taxa livre de risco = 0. Preços do COTAHIST (lote padrão).</div>';
  html += '</div></div>'; // bt-form / card

  // ── 2. Resultado ──
  html += '<div id="bt-result"><div class="bt-empty">Configure os parâmetros e execute para ver o resultado.</div></div>';

  // ── 3. Cenários ──
  html += '<div id="bt-scenarios"></div>';

  html += '</div>';  // .tab-backtest#bt-root
  box.innerHTML = html;
  btStrategyChange();          // primes thresholds + kind-specific visibility
  _btRenderScenarios();
}

// strategy change → thresholds + which engine fields apply
window.btStrategyChange = function() {
  var sel = document.getElementById('bt-strategy');
  if (!sel || !btState.meta) return;
  var spec = null;
  (btState.meta.strategies || []).forEach(function(s) {
    if (s.name === sel.value) spec = s;
  });
  if (!spec) return;
  var d = spec.defaults || {};
  var desc = document.getElementById('bt-strategy-desc');
  if (desc) desc.textContent = spec.description || '';
  var mh = document.getElementById('bt-maxhold');
  if (mh) mh.value = d.max_holding_days !== undefined ? d.max_holding_days : 252;
  var es = document.getElementById('bt-exitsignal');
  if (es) es.checked = !!d.exit_on_signal;

  // thresholds (entry + exit conditions, labeled groups)
  var box = document.getElementById('bt-thresholds');
  var html = '';
  function condField(c) {
    return '<div class="bt-field"><span>' + esc(c.label) + '</span>' +
      '<input type="number" id="bt-th-' + esc(c.key) + '" min="' + esc(String(c.min)) +
      '" max="' + esc(String(c.max)) + '" step="' + esc(String(c.step)) +
      '" value="' + esc(String(c.default)) + '"></div>';
  }
  if ((spec.entry || []).length) {
    html += '<div class="bt-th-group"><div class="bt-th-title">Entrada</div>' +
      '<div class="bt-params-grid">' + spec.entry.map(condField).join('') + '</div></div>';
  }
  if ((spec.exit || []).length) {
    html += '<div class="bt-th-group"><div class="bt-th-title">Saída por sinal</div>' +
      '<div class="bt-params-grid">' + spec.exit.map(condField).join('') + '</div></div>';
  }
  if (box) box.innerHTML = html;

  // kind-specific visibility: buy_hold ignores stops/holding/exit-signal;
  // ma_cross exits by the cross itself (no exit thresholds)
  var isBh = spec.kind === 'buy_hold';
  ['bt-field-mh', 'bt-field-st', 'bt-field-tp'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.style.display = isBh ? 'none' : '';
  });
  var xr = document.getElementById('bt-exit-row');
  if (xr) xr.style.display = (spec.kind === 'fundamental') ? '' : 'none';
};

window.btPreset = function(btn) {
  var s = document.getElementById('bt-start');
  var e = document.getElementById('bt-end');
  if (!s || !e) return;
  s.value = btn.getAttribute('data-start');
  e.value = btn.getAttribute('data-end');
  Array.prototype.forEach.call(btn.parentNode.querySelectorAll('.bt-preset-btn'), function(b) {
    b.classList.toggle('active', b === btn);
  });
};

// collect the form → params object (numbers coerced; absent thresholds skipped)
function _btCollect() {
  var val = function(id) {
    var el = document.getElementById(id);
    return el ? el.value : '';
  };
  var num = function(id) {
    var v = parseFloat(val(id));
    return isNaN(v) ? null : v;
  };
  var spec = null;
  (btState.meta.strategies || []).forEach(function(s) {
    if (s.name === val('bt-strategy')) spec = s;
  });
  var p = {
    strategy: val('bt-strategy'),
    start_date: val('bt-start'),
    end_date: val('bt-end'),
    initial_capital: num('bt-capital'),
    position_pct: num('bt-position'),
    max_holding_days: num('bt-maxhold') || 0,
    stop_loss_pct: num('bt-stop') || 0,
    take_profit_pct: num('bt-take') || 0,
    fee_brl: num('bt-fee') || 0,
    exit_on_signal: false,
    thresholds: {}
  };
  if (spec) {
    (spec.entry || []).concat(spec.exit || []).forEach(function(c) {
      var v = num('bt-th-' + c.key);
      if (v !== null) p.thresholds[c.key] = v;
    });
    if (spec.kind === 'fundamental') {
      var es = document.getElementById('bt-exitsignal');
      p.exit_on_signal = !!(es && es.checked);
    }
  }
  return p;
}

window.btRun = function() {
  var root = document.getElementById('bt-root');
  var box = document.getElementById('bt-result');
  if (!root || !box || btState.running) return;
  var params = _btCollect();
  btState.running = true;
  var btn = document.getElementById('bt-run-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Executando…'; }
  box.innerHTML = '<div class="loading">Rodando o backtest…</div>';
  fetch('/api/webui/company/' + encodeURIComponent(btState.ticker) + '/backtest/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      btState.running = false;
      if (btn) { btn.disabled = false; btn.textContent = '▶ Executar backtest'; }
      if (data._error) {
        box.innerHTML = '<div class="bt-card"><div class="error">Erro: ' +
          esc(data._error) + '</div></div>';
        return;
      }
      btState.result = data;
      _btRenderResult(data);
    })
    .catch(function(err) {
      btState.running = false;
      if (btn) { btn.disabled = false; btn.textContent = '▶ Executar backtest'; }
      box.innerHTML = '<div class="bt-card"><div class="error">Erro: ' +
        esc(err.message) + '</div></div>';
    });
};

// compact one-line scenario summary (labels come from the meta specs)
function _btParamSummary(p) {
  var spec = null;
  (btState.meta.strategies || []).forEach(function(s) {
    if (s.name === p.strategy) spec = s;
  });
  var bits = [];
  if (spec) {
    (spec.entry || []).forEach(function(c) {
      var v = p.thresholds[c.key];
      if (v !== undefined)
        bits.push(c.label.replace(/ de entrada/, '') + ' ' +
          _btNum(v, String(v).indexOf('.') >= 0 ? 1 : 0) + (c.suffix || ''));
    });
  }
  if (p.position_pct && p.position_pct < 100) bits.push(_btNum(p.position_pct) + '% do capital');
  if (p.max_holding_days > 0) bits.push('máx ' + _btNum(p.max_holding_days) + 'd');
  if (p.stop_loss_pct > 0) bits.push('stop ' + _btNum(p.stop_loss_pct) + '%');
  if (p.take_profit_pct > 0) bits.push('take ' + _btNum(p.take_profit_pct) + '%');
  if (p.fee_brl > 0) bits.push('taxa R$ ' + _btNum(p.fee_brl, 2));
  return bits.join(' · ') || 'padrões da estratégia';
}

function _btRenderResult(r) {
  var box = document.getElementById('bt-result');
  if (!box) return;
  var perf = r.performance || {};
  var html = '<div class="bt-card">';
  html += '<div class="bt-card-title-row"><div class="bt-card-title">Resultado — ' +
    esc(r.label) + '</div>' +
    '<button type="button" class="bt-pin-btn" onclick="btPinScenario()">📌 Fixar cenário</button></div>';
  html += '<div class="bt-sub">' + esc(_btParamSummary(r.params)) + ' · ' +
    esc(fmtDate(r.period.start)) + ' → ' + esc(fmtDate(r.period.end)) +
    ' · ' + _btNum(r.period.bars) + ' pregões</div>';

  // warnings
  (r.warnings || []).forEach(function(w) {
    html += '<div class="bt-warn">⚠ ' + esc(w) + '</div>';
  });

  // KPI grid — [v1.28.1] + Retorno Médio/Trade and Tempo Médio de
  // Posição (the payload always carried them; the grid never showed
  // them — "you can improve if possible").
  var kpis = [
    { label: 'Retorno Total', value: _btPct(perf.total_return_pct), cls: _btSignClass(perf.total_return_pct) },
    { label: 'CAGR', value: _btPct(perf.cagr_pct), cls: _btSignClass(perf.cagr_pct) },
    { label: 'Max Drawdown', value: '−' + _btPct(perf.max_drawdown_pct), cls: 'neg' },
    { label: 'Sharpe', value: _btNum(perf.sharpe_ratio, 2), cls: perf.sharpe_ratio >= 1 ? 'pos' : 'neu' },
    { label: 'Win Rate', value: _btPct(perf.win_rate_pct, 1), cls: _btSignClass(perf.win_rate_pct - 50) },
    { label: 'Alpha vs B&H', value: _btPct(perf.alpha_vs_buy_hold), cls: _btSignClass(perf.alpha_vs_buy_hold) },
    { label: 'Fator de Lucro', value: perf.profit_factor === null ? '∞' : _btNum(perf.profit_factor, 2), cls: perf.profit_factor >= 1 ? 'pos' : 'neg' },
    { label: 'Trades', value: _btNum(perf.num_trades), cls: 'neu' },
    { label: 'Retorno Médio/Trade', value: _btPct(perf.avg_trade_pct), cls: _btSignClass(perf.avg_trade_pct) },
    { label: 'Tempo Médio Posição', value: perf.avg_holding_days === null ? '—' : _btNum(perf.avg_holding_days, 1) + ' pregões', cls: 'neu' },
    { label: 'Capital Final', value: fmtBRL(perf.final_equity), cls: _btSignClass(perf.final_equity - perf.initial_capital) }
  ];
  html += '<div class="kpi-grid">';
  kpis.forEach(function(k) {
    html += '<div class="kpi-card"><div class="kpi-label">' + esc(k.label) +
      '</div><div class="kpi-value ' + (k.cls === 'pos' ? 'bt-pos' : (k.cls === 'neg' ? 'bt-neg' : '')) +
      '">' + esc(k.value) + '</div></div>';
  });
  html += '</div>';

  // equity chart
  html += '<div class="chart-section bt-chart-block"><div class="chart-header"><div class="reg-title">Curva de Capital — Estratégia × Buy &amp; Hold</div></div>' +
    '<div class="chart-container"><canvas id="bt-equity-chart"></canvas></div></div>';

  // drawdown + price side by side
  html += '<div class="bt-pair">';
  html += '<div class="chart-section bt-chart-block"><div class="chart-header"><div class="reg-title">Drawdown (Underwater)</div></div>' +
    '<div class="chart-container"><canvas id="bt-dd-chart"></canvas></div></div>';
  html += '<div class="chart-section bt-chart-block"><div class="chart-header"><div class="reg-title">Preço + Entradas/Saídas</div></div>' +
    '<div class="chart-container"><canvas id="bt-price-chart"></canvas></div></div>';
  html += '</div>';

  // trade log — [v1.28.1] headers now MATCH the data alignment
  // (th-num over the right-aligned .val-val cells, th-ctr over the
  // centered reason badges — the old all-left headers over right
  // data read diagonally: "headers and data are not aligned").
  var trades = r.trades || [];
  html += '<div class="bt-table-wrap"><div class="reg-title">Trade Log — ' +
    trades.length + ' operação(ões)</div>' +
    '<table class="val-table bt-tradelog"><thead><tr><th>Entrada</th>' +
    '<th class="th-num">Preço</th><th>Saída</th>' +
    '<th class="th-num">Preço</th><th class="th-num">Ações</th>' +
    '<th class="th-num">Resultado</th><th class="th-num">Retorno</th>' +
    '<th class="th-num">Dias</th><th class="th-ctr">Motivo</th></tr></thead><tbody>';
  trades.forEach(function(t) {
    html += '<tr><td>' + esc(fmtDate(t.entry_date)) + '</td>' +
      '<td class="val-val">' + _btNum(t.entry_price, 2) + '</td>' +
      '<td>' + esc(fmtDate(t.exit_date)) + '</td>' +
      '<td class="val-val">' + _btNum(t.exit_price, 2) + '</td>' +
      '<td class="val-val">' + _btNum(t.shares) + '</td>' +
      '<td class="val-val ' + (t.pnl > 0 ? 'bt-pos' : (t.pnl < 0 ? 'bt-neg' : '')) + '">' +
      (t.pnl >= 0 ? '+' : '') + fmtBRL(t.pnl) + '</td>' +
      '<td class="val-val ' + (t.return_pct > 0 ? 'bt-pos' : (t.return_pct < 0 ? 'bt-neg' : '')) + '">' +
      _btPct(t.return_pct) + '</td>' +
      '<td class="val-val">' + _btNum(t.holding_days) + '</td>' +
      '<td class="bt-reason-cell"><span class="bt-reason ' + esc(String(t.exit_reason)) + '">' +
      esc(_btReasonLabel(t.exit_reason)) + '</span></td></tr>';
  });
  if (!trades.length) html += '<tr><td colspan="9">Nenhum trade executado.</td></tr>';
  html += '</tbody></table></div>';

  html += '</div>'; // card
  box.innerHTML = html;
  _btMountCharts(r);
}

function _btReasonLabel(reason) {
  return { stop_loss: 'stop', take_profit: 'take profit', signal: 'sinal',
           max_holding: 'prazo máx.', end_of_period: 'fim do período' }[reason] || reason;
}

function _btMountCharts(r) {
  var th = chartTheme();
  var c = r.curves || {};
  var labels = c.labels || [];

  // equity × buy&hold
  var eq = document.getElementById('bt-equity-chart');
  if (eq) {
    if (eq._chart) eq._chart.destroy();
    eq._chart = new Chart(eq.getContext('2d'), {
      type: 'line',
      data: { labels: labels, datasets: [
        { label: 'Estratégia', data: c.equity || [], borderColor: '#0d9488',
          backgroundColor: 'rgba(13,148,136,0.10)', borderWidth: 2, pointRadius: 0,
          tension: 0.1, fill: true },
        { label: 'Buy & Hold', data: c.buy_hold || [], borderColor: '#6b7280',
          borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, tension: 0.1, fill: false }
      ]},
      options: { responsive: true, maintainAspectRatio: false,
        scales: { x: _btDateScale(10),
                  y: { grid: { color: th.grid }, ticks: { color: th.text } } },
        plugins: { legend: { position: 'top' },
          tooltip: _btDateTooltipLabel(function(ctx) {
            return ctx.dataset.label + ': ' + fmtBRL(ctx.parsed.y);
          }) } }
    });
  }

  // drawdown (underwater, % below peak)
  var dd = document.getElementById('bt-dd-chart');
  if (dd) {
    if (dd._chart) dd._chart.destroy();
    dd._chart = new Chart(dd.getContext('2d'), {
      type: 'line',
      data: { labels: labels, datasets: [
        { label: 'Drawdown %', data: c.drawdown || [], borderColor: '#ef4444',
          backgroundColor: 'rgba(239,68,68,0.15)', borderWidth: 1.5, pointRadius: 0,
          tension: 0.1, fill: { target: 'origin' } }
      ]},
      options: { responsive: true, maintainAspectRatio: false,
        scales: { x: _btDateScale(6),
                  y: { grid: { color: th.grid }, ticks: { color: th.text,
                    callback: function(v) { return v + '%'; } } } },
        plugins: { legend: { display: false }, tooltip: _btDateTooltip() } }
    });
  }

  // price + entry/exit markers (object data keyed by label — Chart.js
  // category parsing places them on the right session)
  var pc = document.getElementById('bt-price-chart');
  if (pc) {
    if (pc._chart) pc._chart.destroy();
    var entries = (c.entries || []).map(function(e) {
      return { x: e.date, y: e.price };
    });
    var exits = (c.exits || []).map(function(e) {
      return { x: e.date, y: e.price };
    });
    pc._chart = new Chart(pc.getContext('2d'), {
      type: 'line',
      data: { labels: labels, datasets: [
        { label: 'Preço', data: c.price || [], borderColor: '#0d9488',
          borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false },
        { label: 'Compra', data: entries, showLine: false,
          pointStyle: 'triangle', rotation: 0, radius: 7,
          backgroundColor: '#22c55e', borderColor: '#16a34a' },
        { label: 'Venda', data: exits, showLine: false,
          pointStyle: 'triangle', rotation: 180, radius: 7,
          backgroundColor: '#ef4444', borderColor: '#dc2626' }
      ]},
      options: { responsive: true, maintainAspectRatio: false,
        scales: { x: _btDateScale(6),
                  y: { grid: { color: th.grid }, ticks: { color: th.text,
                    callback: function(v) { return 'R$ ' + _btNum(v, 2); } } } },
        plugins: { legend: { position: 'top' }, tooltip: _btDateTooltip() } }
    });
  }
}

// ── scenario pinning + comparison ──────────────────────────────────────────
function _btScenKey() { return 'webui_bt_scenarios_' + (btState.ticker || ''); }
function _btScenLoad() {
  try {
    var v = JSON.parse(localStorage.getItem(_btScenKey()) || '[]');
    return Array.isArray(v) ? v : [];
  } catch (e) { return []; }
}
function _btScenSave(list) {
  try { localStorage.setItem(_btScenKey(), JSON.stringify(list)); }
  catch (e) { /* quota — keep going with the in-memory copy */ }
}

window.btPinScenario = function() {
  var r = btState.result;
  if (!r) return;
  var list = _btScenLoad();
  if (list.length >= BT_SCEN_MAX) {
    _btScenToast('Máximo de ' + BT_SCEN_MAX + ' cenários fixados — remova um antes.');
    return;
  }
  list.push({ id: Date.now(), label: r.label, summary: _btParamSummary(r.params),
              params: r.params, performance: r.performance,
              curves: r.curves, period: r.period });
  _btScenSave(list);
  _btRenderScenarios();
  _btScenToast('Cenário fixado — ' + list.length + '/' + BT_SCEN_MAX);
};

window.btRemoveScenario = function(id) {
  var list = _btScenLoad().filter(function(s) { return String(s.id) !== String(id); });
  _btScenSave(list);
  _btRenderScenarios();
};

// load a pinned scenario's params back into the form
window.btLoadScenario = function(id) {
  var sc = null;
  _btScenLoad().forEach(function(s) { if (String(s.id) === String(id)) sc = s; });
  if (!sc) return;
  var p = sc.params || {};
  var set = function(id, v) {
    var el = document.getElementById(id);
    if (el && v !== undefined && v !== null) el.value = v;
  };
  set('bt-strategy', p.strategy);
  btStrategyChange();
  set('bt-start', p.start_date);
  set('bt-end', p.end_date);
  set('bt-capital', p.initial_capital);
  set('bt-position', p.position_pct);
  set('bt-maxhold', p.max_holding_days);
  set('bt-stop', p.stop_loss_pct);
  set('bt-take', p.take_profit_pct);
  set('bt-fee', p.fee_brl);
  var es = document.getElementById('bt-exitsignal');
  if (es) es.checked = !!p.exit_on_signal;
  Object.keys(p.thresholds || {}).forEach(function(k) {
    set('bt-th-' + k, p.thresholds[k]);
  });
  // clear preset chips — the dates are now manual
  var bar = document.getElementById('bt-presets');
  if (bar) Array.prototype.forEach.call(
    bar.querySelectorAll('.bt-preset-btn'), function(b) { b.classList.remove('active'); });
  _btScenToast('Parâmetros carregados — execute para revalidar.');
};

function _btScenToast(msg) {
  var root = document.getElementById('bt-root');
  if (!root) return;
  var t = document.createElement('div');
  t.className = 'bt-toast';
  t.textContent = msg;
  root.appendChild(t);
  setTimeout(function() { t.classList.add('show'); }, 10);
  setTimeout(function() {
    t.classList.remove('show');
    setTimeout(function() { if (t.parentNode) t.parentNode.removeChild(t); }, 300);
  }, 2600);
}

function _btRenderScenarios() {
  var box = document.getElementById('bt-scenarios');
  if (!box) return;
  var list = _btScenLoad();
  var html = '<div class="bt-card">';
  html += '<div class="bt-card-title-row"><div class="bt-card-title">Cenários Fixados — ' +
    list.length + '/' + BT_SCEN_MAX + '</div></div>';
  if (!list.length) {
    html += '<div class="bt-empty">Execute um backtest e clique em “📌 Fixar cenário” para comparar estratégias, períodos e parâmetros lado a lado.</div>';
    html += '</div>';
    box.innerHTML = html;
    return;
  }

  // comparison table — [v1.28.1] th-num headers over the right-aligned
  // .val-val cells, th-ctr over the actions column (the same alignment
  // fix as the trade log).
  html += '<div class="bt-table-wrap"><table class="val-table bt-scen-table"><thead><tr>' +
    '<th>Cenário</th><th class="th-num">Retorno</th><th class="th-num">CAGR</th>' +
    '<th class="th-num">Max DD</th><th class="th-num">Sharpe</th>' +
    '<th class="th-num">Win Rate</th><th class="th-num">Alpha</th>' +
    '<th class="th-num">Trades</th><th class="th-ctr"></th></tr></thead><tbody>';
  list.forEach(function(s, i) {
    var p = s.performance || {};
    var color = BT_SCEN_COLORS[i % BT_SCEN_COLORS.length];
    html += '<tr>' +
      '<td><span class="bt-scen-dot" style="background:' + color + '"></span>' +
      '<span class="bt-scen-name">' + esc(s.label) + '</span>' +
      '<div class="bt-scen-sub">' + esc(s.summary) + '</div></td>' +
      '<td class="val-val ' + _btPctCls(p.total_return_pct) + '">' + _btPct(p.total_return_pct) + '</td>' +
      '<td class="val-val ' + _btPctCls(p.cagr_pct) + '">' + _btPct(p.cagr_pct) + '</td>' +
      '<td class="val-val bt-neg">' + _btPct(p.max_drawdown_pct) + '</td>' +
      '<td class="val-val">' + _btNum(p.sharpe_ratio, 2) + '</td>' +
      '<td class="val-val">' + _btPct(p.win_rate_pct, 1) + '</td>' +
      '<td class="val-val ' + _btPctCls(p.alpha_vs_buy_hold) + '">' + _btPct(p.alpha_vs_buy_hold) + '</td>' +
      '<td class="val-val">' + _btNum(p.num_trades) + '</td>' +
      '<td class="bt-scen-actions">' +
      '<button type="button" class="bt-mini-btn" title="Carregar parâmetros no formulário" onclick="btLoadScenario(' + Number(s.id) + ')">↺</button>' +
      '<button type="button" class="bt-mini-btn bt-mini-danger" title="Remover" onclick="btRemoveScenario(' + Number(s.id) + ')">✕</button>' +
      '</td></tr>';
  });
  html += '</tbody></table></div>';

  // overlaid equity curves (union of dates; per-scenario map lookup)
  html += '<div class="chart-section bt-chart-block"><div class="chart-header">' +
    '<div class="reg-title">Curvas de Capital — Cenários Sobrepostos</div></div>' +
    '<div class="chart-container"><canvas id="bt-scen-chart"></canvas></div></div>';
  html += '</div>';
  box.innerHTML = html;
  _btMountScenChart(list);
}

function _btPctCls(v) {
  return v > 0 ? 'bt-pos' : (v < 0 ? 'bt-neg' : '');
}

function _btMountScenChart(list) {
  var cv = document.getElementById('bt-scen-chart');
  if (!cv) return;
  // union of all labels (sorted ISO dates), each scenario → aligned series
  var union = {};
  list.forEach(function(s) {
    ((s.curves || {}).labels || []).forEach(function(l) { union[l] = true; });
  });
  var labels = Object.keys(union).sort();
  var th = chartTheme();
  var datasets = list.map(function(s, i) {
    var cur = s.curves || {};
    var byDate = {};
    (cur.labels || []).forEach(function(l, j) { byDate[l] = (cur.equity || [])[j]; });
    return {
      label: s.label,
      data: labels.map(function(l) {
        return byDate.hasOwnProperty(l) ? byDate[l] : null;
      }),
      borderColor: BT_SCEN_COLORS[i % BT_SCEN_COLORS.length],
      borderWidth: 1.6, pointRadius: 0, tension: 0.1, fill: false, spanGaps: false
    };
  });
  if (cv._chart) cv._chart.destroy();
  cv._chart = new Chart(cv.getContext('2d'), {
    type: 'line',
    data: { labels: labels, datasets: datasets },
    options: { responsive: true, maintainAspectRatio: false,
      scales: { x: _btDateScale(10),
                y: { grid: { color: th.grid }, ticks: { color: th.text } } },
      plugins: { legend: { position: 'top' },
        tooltip: _btDateTooltipLabel(function(ctx) {
          return ctx.dataset.label + ': ' + fmtBRL(ctx.parsed.y);
        }) } }
  });
}

// [v1.4 fix2] Nested subtab picker for grouped payloads (Múltiplos +
// Fundamentos). Toggles the panes that share the nav's parent scope —
// works at both levels (top pills toggle .val-pane siblings, sub-pills
// toggle .val-subpane siblings) because each nav only owns its own level.
// Charts in the newly shown pane get an explicit resize() — Chart.js
// mounted them at 0×0 while the pane was display:none.
window.valSubNav = function(btn, targetId) {
  var nav = btn.closest('.val-subnav');
  if (!nav) return;
  Array.prototype.forEach.call(nav.querySelectorAll('.subtab-btn'), function(b) {
    b.classList.remove('active');
  });
  btn.classList.add('active');
  var scope = nav.parentNode;
  Array.prototype.forEach.call(
    scope.querySelectorAll(':scope > .val-pane, :scope > .val-subpane'),
    function(p) { p.style.display = 'none'; });
  var target = document.getElementById(targetId);
  if (!target) return;
  target.style.display = '';
  Array.prototype.forEach.call(target.querySelectorAll('canvas[data-val-chart]'), function(cv) {
    if (cv._chart) { try { cv._chart.resize(); } catch (e) { /* noop */ } }
  });
};

// [v1.22.1] Latent-XSS hardening (minimax wave 3): the subnav pills used
// to interpolate their target id into an INLINE onclick — data-valsub +
// ONE delegated listener instead (nothing executable is ever built into
// an attribute; the listener lives on document, so htmx-swapped content
// is covered without re-wiring).
document.addEventListener('click', function(ev) {
  var t = ev.target;
  var btn = t && t.closest ? t.closest('[data-valsub]') : null;
  if (btn) window.valSubNav(btn, btn.getAttribute('data-valsub'));
});

// Grouped payload renderer — groups become pills; a group carrying 2+
// subsections gets a second pill row (Retornos | Margens …). Chart configs
// are stashed on panel._valChartCfgs exactly like the flat path, so
// mountValCharts works unchanged.
function renderValGrouped(panel, data) {
  var groups = data.groups || [];
  if (!groups.length) { panel.innerHTML = '<div class="loading">Sem dados</div>'; return; }
  panel._valChartCfgs = {};
  var html = '<div class="val-subnav">';
  groups.forEach(function(g, gi) {
    html += '<button class="subtab-btn' + (gi === 0 ? ' active' : '') +
            '" data-valsub="' + esc('val-' + panel.id + '-g' + gi) + '">' + valEsc(g.name) + '</button>';
  });
  html += '</div>';
  groups.forEach(function(g, gi) {
    var gid = 'val-' + panel.id + '-g' + gi;
    var subs = g.subsections || [];
    if (subs.length > 1) {
      html += '<div class="val-pane" id="' + gid + '"' + (gi ? ' style="display:none"' : '') + '>';
      html += '<div class="val-subnav val-subnav2">';
      subs.forEach(function(s, si) {
        html += '<button class="subtab-btn' + (si === 0 ? ' active' : '') +
                '" data-valsub="' + esc('val-' + panel.id + '-g' + gi + 's' + si) + '">' + valEsc(s.name) + '</button>';
      });
      html += '</div>';
      subs.forEach(function(s, si) {
        html += '<div class="val-subpane" id="val-' + panel.id + '-g' + gi + 's' + si + '"' +
                (si ? ' style="display:none"' : '') + '>' +
                valSectionsHtml(s.sections || [], panel) + '</div>';
      });
      html += '</div>';
    } else {
      var secs = subs.length ? (subs[0].sections || []) : (g.sections || []);
      html += '<div class="val-pane" id="' + gid + '"' + (gi ? ' style="display:none"' : '') + '>' +
              valSectionsHtml(secs, panel) + '</div>';
    }
  });
  panel.innerHTML = html;
  mountValCharts(panel);
}

// esc()/valEsc live in the helpers section at the top of this file
// (v1.4 defined valEsc here; v1.5 renamed it esc and aliased valEsc).

// [v1.4 fix2] Signed-value coloring — financials parity. Every negative
// number renders red; % values render green (positive) / red (negative) /
// yellow (zero). Non-numeric strings (labels, interpretations, "—") pass
// through untouched. Handles every apply_fmt shape: "-5,67%", "R$ -0,06",
// "-R$ 3,50", "12,34%", "R$ 12,35 mi".
function valNumHtml(s) {
  var t = String(s === null || s === undefined ? '' : s).trim();
  if (!t || t === '—') return valEsc(t);
  // Must look numeric: optional sign, optional R$, optional sign, digit.
  if (!/^-?\s*R?\$?\s*-?\s*\d/.test(t)) return valEsc(t);
  var isPct = t.indexOf('%') >= 0;
  var neg = t.charAt(0) === '-' || t.indexOf('R$ -') >= 0 || t.indexOf('-R$') >= 0;
  var cls = '';
  if (neg) {
    cls = 'val-neg';
  } else if (isPct) {
    var n = parseFloat(t.replace(/[^\d,-]/g, '').replace(/\./g, '').replace(',', '.'));
    cls = (isNaN(n) || n > 0) ? 'val-pos' : (n < 0 ? 'val-neg' : 'val-zero');
  }
  if (!cls) return valEsc(t);
  return '<span class="' + cls + '">' + valEsc(t) + '</span>';
}

function valKpisHtml(kpis) {
  var h = '<div class="kpi-grid">';
  (kpis || []).forEach(function(k) {
    var tip = k.tooltip || '';
    h += '<div class="kpi-card"' + (tip ? ' title="' + valEsc(tip) + '"' : '') + '>' +
         '<div class="kpi-label">' + valEsc(k.label) +
         (tip ? ' <span class="val-info">ⓘ</span>' : '') + '</div>' +
         '<div class="kpi-value">' + valNumHtml(k.value) + '</div></div>';
  });
  return h + '</div>';
}

// Sections → HTML. Consecutive chart sections are grouped into a responsive
// grid (fin-charts-grid); chart configs are stashed on panel._valChartCfgs
// (index → config) and mounted by mountValCharts after innerHTML is set.
// [v1.7.2] (a) `pair_with_next` on a non-chart section renders it + the
// NEXT section side by side (val-pair-grid) — the Múltiplos table pairs
// (Múltiplos de Preço | Per-share Values, EBIT | EBITDA). (b) chart
// sections carrying `price_range_selector` (the 5Y history charts) get a
// Tudo/10A/…/1M range bar; the filter runs client-side from chart_data
// itself (valChartRange), so the server doesn't ship the duplicate
// price_full_* arrays the static dashboard's filter needs.
function valSectionsHtml(sections, panel) {
  var html = '';
  var chartBuf = [];
  var cfgs = panel._valChartCfgs = panel._valChartCfgs || {};
  function flushCharts() {
    if (!chartBuf.length) return '';
    var h = '<div class="fin-charts-grid val-charts">';
    chartBuf.forEach(function(sec) {
      var idx = Object.keys(cfgs).length;
      cfgs[idx] = sec.chart_data;
      h += '<div class="chart-section fin-chart-card"><div class="chart-header">' +
           '<div class="reg-title">' + valEsc(sec.title || '') + '</div></div>';
      if (sec.description) h += '<div class="val-desc">' + valEsc(sec.description) + '</div>';
      if (sec.price_range_selector) h += valRangeBarHtml();
      h += '<div class="chart-container"><canvas data-val-chart="' + idx + '"' +
           (sec.price_range_selector ? ' data-val-range="1"' : '') +
           '></canvas></div></div>';
    });
    chartBuf = [];
    return h + '</div>';
  }
  var secs = sections || [];
  for (var i = 0; i < secs.length; i++) {
    var sec = secs[i];
    if (sec && sec.type === 'chart') { chartBuf.push(sec); continue; }
    html += flushCharts();
    var nxt = secs[i + 1];
    if (sec && sec.pair_with_next && nxt && nxt.type !== 'chart') {
      html += '<div class="val-pair-grid">' + valSectionHtml(sec) + valSectionHtml(nxt) + '</div>';
      i++;  // the paired section is consumed
      continue;
    }
    html += valSectionHtml(sec);
  }
  html += flushCharts();
  return html;
}

// [v1.7.2] Range bar for the 5Y history charts (Tudo/10A/5A/1A/6M/3M/1M) —
// same .range-btn chips as the candlestick bar, scoped per chart card.
function valRangeBarHtml() {
  var ranges = [['all', 'Tudo'], ['10y', '10A'], ['5y', '5A'], ['1y', '1A'],
                ['6m', '6M'], ['3m', '3M'], ['1m', '1M']];
  var h = '<div class="val-range-bar">';
  ranges.forEach(function(r, i) {
    h += '<button type="button" class="range-btn' + (i === 0 ? ' active' : '') +
         '" data-range="' + r[0] + '" onclick="valChartRange(this)">' + r[1] + '</button>';
  });
  return h + '</div>';
}

// [v1.7.2] Client-side range filter for the history charts. The full data
// lives on the canvas (cv._valFull, stashed at mount) — clicking a range
// slices labels + every dataset from the full copy and updates the chart
// in place (no refetch). Labels are ISO dates, so lexicographic compare
// finds the range start. Stale series shorter than the requested range
// degrade to the last point instead of an empty chart.
window.valChartRange = function(btn) {
  var card = btn.closest('.chart-section');
  if (!card) return;
  var cv = card.querySelector('canvas');
  if (!cv || !cv._chart || !cv._valFull) return;
  var range = btn.getAttribute('data-range');
  var full = cv._valFull;
  var start = 0;
  if (range !== 'all') {
    var months = { '10y': 120, '5y': 60, '1y': 12, '6m': 6, '3m': 3, '1m': 1 }[range] || 0;
    var cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - months);
    var iso = cutoff.toISOString().slice(0, 10);
    // [v1.15] Monthly YYYY-MM labels (the Inflação family) compare against
    // a YYYY-MM cutoff: "2025-11" is a lexicographic PREFIX of
    // "2025-11-22", so the daily cutoff would wrongly drop the boundary
    // month from the window.
    var _firstLbl = String(full.labels[0] || '');
    if (/^\d{4}-\d{2}$/.test(_firstLbl)) iso = iso.slice(0, 7);
    for (var i = 0; i < full.labels.length; i++) {
      if (String(full.labels[i]) >= iso) { start = i; break; }
    }
    if (start >= full.labels.length) start = Math.max(0, full.labels.length - 1);
  }
  var chart = cv._chart;
  chart.data.labels = full.labels.slice(start);
  chart.data.datasets.forEach(function(ds, di) {
    if (full.data[di]) ds.data = full.data[di].slice(start);
  });
  chart.update('none');
  Array.prototype.forEach.call(btn.parentNode.querySelectorAll('.range-btn'), function(b) {
    b.classList.toggle('active', b === btn);
  });
};

// One generic section renderer — handles every section type the static
// dashboard's report builders emit (table / two_column / ratio_grid /
// heatmap). Chart sections are handled by valSectionsHtml's grouping.
function valSectionHtml(sec) {
  if (!sec) return '';
  var t = sec.type;

  if (t === 'heatmap') {
    var h = '<div class="val-section"><div class="reg-title">' + valEsc(sec.title || '') + '</div>';
    if (sec.description) h += '<div class="val-desc">' + valEsc(sec.description) + '</div>';
    h += '<table class="val-table val-heatmap"><thead><tr>';
    (sec.columns || ['Métrica', 'Valor']).forEach(function(c) { h += '<th>' + valEsc(String(c)) + '</th>'; });
    h += '</tr></thead><tbody>';
    (sec.rows || []).forEach(function(row) {
      h += '<tr>';
      row.forEach(function(cell, ci) {
        if (ci === 0) {
          // [v1.24] Column 0 accepts {text, tooltip} cells too (the
          // table branch precedent) — the Histórico heatmap puts the
          // formula tooltip on the metric name. Plain strings pass
          // through untouched (the Valuation heatmap's shape).
          if (cell && typeof cell === 'object') {
            var tip0 = cell.tooltip || '';
            h += '<td class="val-metric"' + (tip0 ? ' title="' + valEsc(tip0) + '"' : '') + '>' +
                 valEsc(cell.text || '—') +
                 (tip0 ? ' <span class="val-info">ⓘ</span>' : '') + '</td>';
          } else {
            h += '<td class="val-metric">' + valEsc(String(cell)) + '</td>';
          }
        } else if (cell && typeof cell === 'object') {
          h += '<td class="val-heat" style="background:' + safeColor(cell.bg) +
               ';color:' + safeColor(cell.color, 'inherit') + '" title="' + valEsc(cell.tooltip || '') + '">' +
               valEsc(cell.text || '—') + '</td>';
        } else {
          h += '<td class="val-val">' + valEsc(String(cell)) + '</td>';
        }
      });
      h += '</tr>';
    });
    return h + '</tbody></table></div>';
  }

  if (t === 'two_column') {
    var h = '<div class="val-two-col">';
    h += valBlockHtml(sec.left_title, sec.left_rows);
    h += valBlockHtml(sec.right_title, sec.right_rows);
    return h + '</div>';
  }

  if (t === 'ratio_grid') {
    var h = '<div class="val-section"><div class="reg-title">' + valEsc(sec.title || '') + '</div>';
    if (sec.description) h += '<div class="val-desc">' + valEsc(sec.description) + '</div>';
    (sec.categories || []).forEach(function(cat) {
      h += '<table class="val-table"><tbody>';
      (cat.items || []).forEach(function(item) {
        h += '<tr><td title="' + valEsc(item.tooltip || '') + '">' + valEsc(item.label || '') +
             (item.tooltip ? ' <span class="val-info">ⓘ</span>' : '') +
             '</td><td class="val-val">' + valNumHtml(item.value) + '</td></tr>';
      });
      h += '</tbody></table>';
    });
    return h + '</div>';
  }

  if (t === 'table') {
    // [v1.23] `collapsed` tables (the Histórico mensal convention — the
    // matrix heatmap above carries the same data; the full ledger opens
    // on demand) render inside a <details> that starts CLOSED: the
    // summary carries the title + row count so the user knows what's
    // inside before opening (the val-cat pattern — Todas as métricas).
    var closed = !!sec.collapsed;
    var h = closed
      ? '<details class="val-cat val-collapse"><summary>' +
        '<span class="val-collapse-title">' + valEsc(sec.title || '') + '</span>' +
        '<span class="val-count">(' + (sec.rows || []).length + ' linhas — clique para expandir)</span>' +
        '<span class="val-collapse-chev" aria-hidden="true">▸</span></summary>'
      : '<div class="val-section"><div class="reg-title">' + valEsc(sec.title || '') + '</div>';
    if (sec.description) h += '<div class="val-desc">' + valEsc(sec.description) + '</div>';
    h += '<table class="val-table"><thead><tr>';
    // [v1.6 fix1] Numeric columns get th-num so the header aligns with the
    // right-aligned val-val data below it (all-left headers over right
    // data made wide tables like Proventos por Ano / DVA read diagonally).
    // [v1.8] Sections carrying `sortable` render click-sortable headers
    // (initValTableSort — the Opções chain/position tables).
    (sec.columns || []).forEach(function(c, ci) {
      var cls = (ci > 0 ? 'th-num' : '');
      if (sec.sortable) cls += ' val-sortable';
      h += '<th' + (cls ? ' class="' + cls.trim() + '"' : '') + '>' + valEsc(String(c)) + '</th>';
    });
    h += '</tr></thead><tbody>';
    (sec.rows || []).forEach(function(row) {
      h += '<tr>';
      (row || []).forEach(function(cell, ci) {
        if (cell && typeof cell === 'object' && cell.price) {
          // [v1.28.3] PRICE-BAND cells — the Ações 22-range
          // palette chip on a table's MAIN price (contract.price_pill's
          // {pill, text, range} riding the cell; acoes.py's Última
          // column). Same solid-chip rendering as the Painel's pills;
          // the cell's own tooltip (the faixa) wins over the pill's
          // default (both name the range).
          h += '<td' + (ci > 0 ? ' class="val-val"' : '') + '>' +
            homePricePill(cell.price, cell.text) + '</td>';
        } else if (cell && typeof cell === 'object' && cell.pill) {
          // [v1.26.1] Colored pill cells — the Insiders cargo/tipo
          // vocabulary (each value its own color, stable across the
          // Movimentações / Por Cargo / Por Tipo subtabs). The color
          // rides inline (server palette, single source of truth); the
          // soft background is the same hue at ~8% alpha (hex "14").
          var ptip = cell.tooltip || '';
          h += '<td><span class="ins-pill" style="border-color:' + safeColor(cell.pill) +
               ';color:' + safeColor(cell.pill) + ';background:' + safeColor(cell.pill) + '14"' +
               (ptip ? ' title="' + valEsc(ptip) + '"' : '') + '>' +
               valEsc(cell.text || '—') + '</span></td>';
        } else if (cell && typeof cell === 'object') {
          var tip = cell.tooltip || '';
          // [v1.26.1] Optional link cell (the Proventos IPE announcements
          // date opens the CVM PDF) — renders as a same-tab-safe external
          // anchor; the tooltip stays on the td like every other col-0.
          var inner = valEsc(cell.text || '—');
          if (cell.link && typeof cell.link === 'string' &&
              /^https?:\/\//i.test(cell.link)) {
            inner = '<a href="' + valEsc(cell.link) + '" target="_blank" rel="noopener">' + inner + ' ↗</a>';
          }
          h += '<td' + (ci === 0 && tip ? ' title="' + valEsc(tip) + '"' : '') + '>' +
               inner +
               (ci === 0 && tip ? ' <span class="val-info">ⓘ</span>' : '') + '</td>';
        } else {
          h += '<td' + (ci > 0 ? ' class="val-val"' : '') + '>' + valNumHtml(String(cell)) + '</td>';
        }
      });
      h += '</tr>';
    });
    h += '</tbody></table>';
    if (sec.note) h += '<div class="val-note">' + valEsc(sec.note) + '</div>';
    return h + (closed ? '</details>' : '</div>');
  }

  return '';
}

function valBlockHtml(title, rows) {
  var h = '<div class="val-section"><div class="reg-title">' + valEsc(title || '') + '</div>' +
          '<table class="val-table"><tbody>';
  (rows || []).forEach(function(r) {
    var tip = r.tooltip || '';
    h += '<tr><td' + (tip ? ' title="' + valEsc(tip) + '"' : '') + '>' + valEsc(r.label || '') +
         (tip ? ' <span class="val-info">ⓘ</span>' : '') +
         '</td><td class="val-val">' + valNumHtml(r.value) + '</td></tr>';
  });
  return h + '</tbody></table></div>';
}

// Fundamentos + Múltiplos share renderValGrouped above (nested subtabs).

// Todas as métricas: collapsible category groups — [v1.4 fix2] ALL closed
// by default (79 metrics is a long wall of tables; users open on demand).
function renderValAll(panel, data) {
  var html = '';
  (data.groups || []).forEach(function(g) {
    var n = (g.metrics || []).length;
    html += '<details class="val-cat"><summary>' +
            valEsc(g.name) + ' <span class="val-count">(' + n + ')</span></summary>';
    html += '<table class="val-table"><tbody>';
    (g.metrics || []).forEach(function(m) {
      var tip = m.tooltip || '';
      html += '<tr><td' + (tip ? ' title="' + valEsc(tip) + '"' : '') + '>' + valEsc(m.label) +
             (tip ? ' <span class="val-info">ⓘ</span>' : '') +
             '</td><td class="val-val">' + valNumHtml(m.value) + '</td></tr>';
    });
    html += '</tbody></table></details>';
  });
  panel.innerHTML = html || '<div class="loading">Sem dados</div>';
}

// [v1.8 fix1] Returns the x-axis date kind when EVERY label is an ISO
// date string: 'date' (YYYY-MM-DD), 'month' (YYYY-MM — v1.15) or ''
// (empty / non-string / mixed axes). renderValChart uses this to decide
// whether the x-axis is worth formatting (dd/mm/yyyy / jul/2026).
function _isoDateLabels(labels) {
  if (!labels || !labels.length) return '';
  var month = false;
  for (var i = 0; i < labels.length; i++) {
    if (typeof labels[i] !== 'string') return '';
    if (/^\d{4}-\d{2}-\d{2}$/.test(labels[i])) continue;
    if (/^\d{4}-\d{2}$/.test(labels[i])) { month = true; continue; }
    return '';
  }
  return month ? 'month' : 'date';
}

// Mount every chart canvas stashed during HTML build. Chart configs come
// from the server as plain Chart.js {type, data} — options are rebuilt
// client-side with chartTheme() so dark/light mode stays consistent (the
// server's Jinja-oriented options, incl. function-string tooltip callbacks,
// are intentionally discarded).
function mountValCharts(panel) {
  var nodes = panel.querySelectorAll('canvas[data-val-chart]');
  Array.prototype.forEach.call(nodes, function(cv) {
    if (cv._chart) return;
    var idx = parseInt(cv.getAttribute('data-val-chart'), 10);
    // Find the chart_data in the stashed configs (index → config map).
    var cfg = (panel._valChartCfgs || {})[idx];
    if (!cfg) return;
    // [v1.7.2] Range-filterable charts: keep a full copy of labels + each
    // dataset's data BEFORE mounting (valChartRange slices from it, the
    // mounted chart is what gets mutated).
    if (cv.getAttribute('data-val-range') === '1' && cfg && cfg.data) {
      cv._valFull = {
        labels: (cfg.data.labels || []).slice(),
        data: (cfg.data.datasets || []).map(function(d) { return (d.data || []).slice(); })
      };
    }
    renderValChart(cv, cfg);
  });
}

function renderValChart(canvas, cd) {
  if (!cd || !cd.data) return;
  var th = chartTheme();
  var type = cd.type || 'bar';
  // [v1.5] Honor the server's y.beginAtZero (the liquidity/leverage charts
  // ask for it; the client used to discard ALL server options, so bars
  // floated above the baseline). Other options stay client-side (theme).
  // [v1.6 fix1] Honor x/y.stacked too — the Proventos composition charts
  // (Proventos por Ano, Composição Anual, DVA por Exercício) ask for
  // stacked bars, but the discarded option made Chart.js render them
  // GROUPED (each type a side-by-side bar instead of one stacked column).
  var srvScales = ((cd.options || {}).scales) || {};
  var srvY = srvScales.y || {};
  var srvX = srvScales.x || {};
  var datasets = (cd.data.datasets || []).map(function(ds) {
    var d = {};
    for (var k in ds) d[k] = ds[k];
    if (type === 'line' || d.type === 'line') {
      if (d.fill === undefined) d.fill = false;
      if (d.tension === undefined) d.tension = 0.3;
      if (d.borderWidth === undefined) d.borderWidth = 2;
    }
    return d;
  });
  var options;
  if (type === 'radar') {
    // [v1.26.1] Single-dataset radars drop the legend too (same rule as
    // the cartesian branch — the valuation radar's lone "Percentil"
    // entry only repeated the card title).
    var _radarLegend = (datasets.length <= 1);
    options = {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: !_radarLegend, position: 'top', labels: { color: th.text } } },
      scales: { r: {
        beginAtZero: true, max: 100,
        ticks: { stepSize: 20, color: th.text, backdropColor: 'transparent' },
        grid: { color: th.grid }, angleLines: { color: th.grid },
        pointLabels: { color: th.text, font: { size: 11 } }
      } }
    };
  } else {
    var yScale = { grid: { color: th.grid }, ticks: { color: th.text } };
    if (srvY.beginAtZero) yScale.beginAtZero = true;
    if (srvY.stacked) yScale.stacked = true;
    // [v1.17] y.max too — the Ações 100% stacked area sums to exactly
    // 100.00 per date, but float dust (8.87 + 9.14 + … = 100.00000000000001)
    // makes the auto-nice axis jump to 120 and leave dead space on top;
    // the server pins it.
    if (typeof srvY.max === 'number') yScale.max = srvY.max;
    if (srvY.title && srvY.title.text) yScale.title = { display: true, text: srvY.title.text };
    var xScale = { grid: { color: th.grid }, ticks: { color: th.text, maxTicksLimit: 14 } };
    if (srvX.stacked) xScale.stacked = true;
    // [v1.7.2] x-axis title too (the history charts label it "Data").
    if (srvX.title && srvX.title.text) xScale.title = { display: true, text: srvX.title.text };
    // [v1.8 fix1] Date axes render in BR format: when EVERY x label is an
    // ISO date (P/C Ratio + Exercícios charts, and the v1.7.2 valuation
    // history charts all ship ISO labels), ticks and tooltip titles are
    // formatted dd/mm/yyyy — the same fmtDate convention as every
    // hardcoded chart config in this file. Labels stay ISO in the payload
    // (valChartRange slices them); non-date axes (strikes, tickers, years)
    // are untouched.
    // [v1.15] Monthly axes: YYYY-MM labels (the Inflação family ships
    // 322-month series) format as "jul/2026" — the same short PT-BR
    // month form the tables use, instead of the raw "2026-07".
    var dateAxis = _isoDateLabels(cd.data.labels);
    var _axisFmt = dateAxis === 'month' ? fmtMonth : fmtDate;
    if (dateAxis) {
      xScale.ticks.callback = function(v) { return _axisFmt(this.getLabelForValue(v)); };
    }
    var plugins = { legend: { display: true, position: 'top', labels: { color: th.text } } };
    if (dateAxis) {
      plugins.tooltip = { callbacks: { title: function(i) { return _axisFmt(i[0].label); } } };
    }
    // [v1.24] Per-dataset `hideLegend` — datasets flagged true stay in
    // the chart (tooltips included) but drop out of the legend. The
    // Histórico 5A band charts draw the mín–máx band as TWO datasets
    // (the fill runs from one to the other); one legend entry tells
    // the story, the second line would only duplicate it.
    var _hideDs = (cd.data.datasets || []).map(function(d) {
      return !!(d && d.hideLegend);
    });
    if (_hideDs.some(function(h) { return h; })) {
      plugins.legend.labels.filter = function(item) {
        return !(_hideDs && _hideDs[item.datasetIndex]);
      };
    }
    // [v1.26.1] Single-series charts hide the legend — a one-item legend
    // only repeats the card title (Múltiplos de Preço — Comparativo's
    // "Preço", Retornos' "Retornos (%)", Margens, Liquidez, Alavancagem,
    // Sazonalidade, Volume Líquido Mensal/Acumulado, Evolução do Score…).
    // Pies/doughnuts KEEP theirs (the legend IS the category axis there);
    // an explicit server plugins.legend.display always wins over this
    // heuristic (applied right below).
    if (type !== 'pie' && type !== 'doughnut') {
      var _visible = 0;
      (cd.data.datasets || []).forEach(function(d, i) {
        if (!(_hideDs && _hideDs[i])) _visible++;
      });
      if (_visible <= 1) plugins.legend.display = false;
    }
    // [v1.14] Honor the server's plugins.legend (display/position) — the
    // Índices composition doughnuts ship legend off (78-136 slices would
    // be a wall of legend labels; the full table below is the legend).
    // Same cutout/stacked precedent: default stays exactly as before for
    // every chart that does not ask. ([v1.26.1] this now also overrides
    // the single-series suppression above — an explicit server ask wins.)
    var srvLegend = (((cd.options || {}).plugins) || {}).legend;
    if (srvLegend && typeof srvLegend === 'object') {
      if (typeof srvLegend.display === 'boolean') plugins.legend.display = srvLegend.display;
      if (typeof srvLegend.position === 'string') plugins.legend.position = srvLegend.position;
    }
    // [v1.14] Honor the server's tooltipUnit — a JSON-safe way to give
    // pie/doughnut tooltips a suffix with pt-BR value formatting (the
    // composition doughnuts ship "%"; the raw Chart.js tooltip would
    // show "VALE3: 10.886" with an EN dot and no unit). Values format
    // through toLocaleString('pt-BR') — same numerics as every table.
    var tUnit = (cd.options || {}).tooltipUnit;
    if (tUnit && typeof tUnit === 'string') {
      plugins.tooltip = plugins.tooltip || {};
      plugins.tooltip.callbacks = plugins.tooltip.callbacks || {};
      plugins.tooltip.callbacks.label = function(ctx) {
        var v = ctx.parsed !== undefined ? ctx.parsed : ctx.raw;
        var num = (typeof v === 'number' && isFinite(v))
          ? v.toLocaleString('pt-BR', { maximumFractionDigits: 3 }) : v;
        return (ctx.label ? ctx.label + ': ' : '') + num + tUnit;
      };
    }
    options = {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: plugins,
      scales: {
        x: xScale,
        y: yScale
      }
    };
    // [v1.17] Honor the server's interaction (mode/intersect) — same
    // opt-in pattern as beginAtZero (v1.5) / stacked (v1.6 fix1) /
    // legend + tooltipUnit (v1.14). The Ações evolution charts ship
    // {mode: 'nearest'} so hovering the 22 stacked bands reads the
    // band under the cursor instead of a wall of 22 tooltip rows
    // (index mode remains the default for every other chart).
    var srvInteraction = ((cd.options || {}).interaction) || null;
    if (srvInteraction && typeof srvInteraction === 'object' &&
        typeof srvInteraction.mode === 'string') {
      options.interaction = { mode: srvInteraction.mode };
      if (typeof srvInteraction.intersect === 'boolean') {
        options.interaction.intersect = srvInteraction.intersect;
      }
    }
    // [v1.7.2] Server-defined secondary axes (y1/y2/…): the Múltiplos
    // history charts are dual-axis (P/L and P/CG on the left; PSR, P/RB
    // and P/DB on the right). Datasets carrying yAxisID would otherwise
    // reference a scale Chart.js never built. Each server axis gets theme
    // defaults + position / title / beginAtZero / grid.drawOnChartArea.
    Object.keys(srvScales).forEach(function(k) {
      if (k === 'x' || k === 'y' || options.scales[k]) return;
      var s = srvScales[k] || {};
      var grid = { color: th.grid };
      if (s.grid && s.grid.drawOnChartArea === false) grid.drawOnChartArea = false;
      var sc = { grid: grid, ticks: { color: th.text } };
      if (s.position) sc.position = s.position;
      if (s.beginAtZero) sc.beginAtZero = true;
      if (s.stacked) sc.stacked = true;
      if (s.title && s.title.text) sc.title = { display: true, text: s.title.text };
      if (s.ticks && s.ticks.maxTicksLimit) sc.ticks.maxTicksLimit = s.ticks.maxTicksLimit;
      options.scales[k] = sc;
    });
    // [v1.9] Honor the server's cutout (doughnut/pie hole — the Acionistas
    // top-5 doughnut ships "60%"; Chart.js defaults to 0 = solid pie).
    // Harmless for every other type (Chart.js ignores cutout elsewhere).
    if ((cd.options || {}).cutout) options.cutout = cd.options.cutout;
  }
  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: type,
    data: { labels: cd.data.labels || [], datasets: datasets },
    options: options
  });
}

// ── Proventos tab [WebUI v1.6] ─────────────────────────────────────────
// 3 lazy subtabs (Visão Geral / Histórico / Anual), same loader contract
// as the Valuation tab: pane._loaded guard set only AFTER a successful
// render (failed subtabs stay retryable). Visão Geral + Anual render the
// generic {kpis, sections} payload with the valuation renderer; Histórico
// has a custom renderer — complete event list with type pills, year
// filter, sortable columns, per-event yield at ex-date and an
// upcoming-payments card.

window.loadProvSubtab = function(sub) {
  var panel = document.getElementById('tab-prov-' + sub);
  if (!panel || panel._loaded) return;
  var ticker = panel.getAttribute('data-ticker');
  if (!ticker) return;
  // [v1.7] Generic adapter endpoint (/sections/proventos:<sub>) — same
  // payload via the registry dispatch path.
  fetch('/api/webui/company/' + encodeURIComponent(ticker) + '/sections/proventos:' + sub + '?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) { panel._loaded = true; renderProvSubtab(sub, panel, data); })
    .catch(function(err) {
      panel.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
};

function renderProvSubtab(sub, panel, data) {
  if (data._error) { panel.innerHTML = '<div class="error">Erro: ' + esc(data._error) + '</div>'; return; }
  if (sub === 'historico') { renderProvHistorico(panel, data); return; }
  // overview / anual → KPI cards + generic sections (valuation renderer)
  panel._valChartCfgs = {};
  var html = '';
  if (data.kpis && data.kpis.length) html += valKpisHtml(data.kpis);
  html += valSectionsHtml(data.sections || [], panel);
  panel.innerHTML = html || '<div class="loading">Sem dados</div>';
  mountValCharts(panel);
}

// Per-share BRL with 2-4 decimals (rates like 0,0204 need the precision).
var _provRateFmt = null;
function provFmtRate(v) {
  if (v === null || v === undefined) return '<span class="muted">—</span>';
  if (!_provRateFmt) _provRateFmt = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  return 'R$ ' + _provRateFmt.format(Number(v));
}

function provBadge(ev, tooltips) {
  var tip = (tooltips || {})[ev.type] || '';
  return '<span class="prov-badge prov-badge-' + esc(ev.type_key) + '"' +
         (tip ? ' title="' + esc(tip) + '"' : '') + '>' + esc(ev.type) + '</span>';
}

var PROV_COLS = [
  { key: 'ex_date',     label: 'Data Ex' },
  { key: 'pay_date',    label: 'Pagamento' },
  { key: 'approved_on', label: 'Aprovação' },
  { key: 'type',        label: 'Tipo', ctr: true },
  { key: 'rate',        label: 'Valor/Ação', num: true, tip: 'Valor por ação conforme divulgado pela B3 (JCP: valor bruto).' },
  { key: 'yield_ex',    label: 'Yield Ex', num: true, tip: 'Yield do evento = valor por ação ÷ último fechamento ANTES da data-ex.' },
  { key: 'related_to',  label: 'Relativo a' }
];

function provHeadHtml(panel) {
  var st = panel._provState;
  var h = '';
  PROV_COLS.forEach(function(c) {
    var arrow = '';
    if (st.sortKey === c.key) arrow = st.sortDir > 0 ? ' ▲' : ' ▼';
    // [v1.6 fix1] Header alignment matches the data cells: numeric columns
    // (Valor/Ação, Yield Ex) right, Tipo centered (badge column).
    var cls = 'sortable';
    if (c.num) cls += ' th-num';
    else if (c.ctr) cls += ' th-ctr';
    h += '<th class="' + cls + '" data-prov-sort="' + c.key + '"' +
         (c.tip ? ' title="' + esc(c.tip) + '"' : '') + '>' + esc(c.label) + arrow + '</th>';
  });
  return h;
}

function provRowsHtml(panel) {
  var st = panel._provState, data = panel._provData;
  var rows = (data.events || []).filter(function(e) {
    if (st.type !== 'all' && e.type_key !== st.type) return false;
    if (st.year !== 'all' && String(e.year || '') !== String(st.year)) return false;
    return true;
  });
  var k = st.sortKey, dir = st.sortDir;
  rows.sort(function(a, b) {
    var va = a[k], vb = b[k];
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
    va = (va === null || va === undefined || va === '') ? '' : String(va);
    vb = (vb === null || vb === undefined || vb === '') ? '' : String(vb);
    if (va === '' && vb === '') return 0;
    if (va === '') return 1;   // empties always last, regardless of direction
    if (vb === '') return -1;
    return va.localeCompare(vb, 'pt-BR') * dir;
  });
  var h = '';
  rows.forEach(function(e) {
    var rowTip = e.remarks ? ' title="' + esc(e.remarks) + '"' : '';
    h += '<tr' + (e.future ? ' class="prov-future-row"' : '') + rowTip + '>';
    h += '<td>' + (e.ex_date ? fmtDate(e.ex_date) : '<span class="muted">—</span>') + '</td>';
    h += '<td>' + (e.pay_date ? fmtDate(e.pay_date) : '<span class="muted">—</span>') +
         (e.future ? ' <span class="prov-chip">futuro</span>' : '') + '</td>';
    h += '<td>' + (e.approved_on ? fmtDate(e.approved_on) : '<span class="muted">—</span>') + '</td>';
    h += '<td>' + provBadge(e, data.type_tooltips || {}) + '</td>';
    h += '<td class="val-val">' + provFmtRate(e.rate) + '</td>';
    h += '<td class="val-val">' + fmtPctColored(e.yield_ex) + '</td>';
    h += '<td>' + esc(e.related_to || '—') + '</td>';
    h += '</tr>';
  });
  if (!rows.length) h = '<tr><td colspan="7" class="muted">Nenhum evento com os filtros atuais.</td></tr>';
  return h;
}

function provYearOptions(data, current) {
  var h = '<option value="all"' + (String(current) === 'all' ? ' selected' : '') + '>Todos os anos</option>';
  (data.years || []).forEach(function(y) {
    h += '<option value="' + esc(String(y)) + '"' + (String(current) === String(y) ? ' selected' : '') + '>' + esc(String(y)) + '</option>';
  });
  return h;
}

function renderProvHistorico(panel, data) {
  panel._provData = data;
  if (!panel._provState) {
    panel._provState = { type: 'all', year: 'all', sortKey: 'ex_date', sortDir: -1 };
  }
  var st = panel._provState;
  var evs = data.events || [];
  var upcoming = evs.filter(function(e) { return e.future; });
  var tips = data.type_tooltips || {};
  var html = '';

  // ── Próximos pagamentos (announced, not yet paid) ──
  if (upcoming.length) {
    html += '<div class="prov-upcoming"><div class="reg-title">Próximos Pagamentos</div><div class="prov-upcoming-grid">';
    upcoming.forEach(function(e) {
      html += '<div class="prov-upcoming-item">' + provBadge(e, tips) +
              '<div class="prov-upcoming-date">' + fmtDate(e.pay_date) + '</div>' +
              '<div class="prov-upcoming-val">' + provFmtRate(e.rate) + '</div>' +
              (e.related_to ? '<div class="prov-upcoming-rel">' + esc(e.related_to) + '</div>' : '') +
              '</div>';
    });
    html += '</div></div>';
  }

  // ── Filtros: type pills + year select ──
  // [v1.6 fix1] Pills render with the prov-pill class only — they used to
  // carry subtab-btn, whose styles are scoped to .subtab-nav containers, so
  // the buttons fell back to the browser default (white bg / black text).
  var counts = data.counts || {}, labels = data.type_labels || {};
  html += '<div class="prov-filters"><div class="prov-pills">';
  html += '<button class="prov-pill' + (st.type === 'all' ? ' active' : '') + '" data-prov-type="all">Todos (' + evs.length + ')</button>';
  Object.keys(counts).forEach(function(k) {
    html += '<button class="prov-pill' + (st.type === k ? ' active' : '') +
            '" data-prov-type="' + esc(k) + '">' + esc(labels[k] || k) + ' (' + counts[k] + ')</button>';
  });
  html += '</div><select class="prov-year" data-prov-year>' + provYearOptions(data, st.year) + '</select></div>';

  // ── Main table ──
  html += '<div class="val-section prov-table-wrap"><table class="val-table prov-table"><thead><tr>' +
          provHeadHtml(panel) + '</tr></thead><tbody>' + provRowsHtml(panel) + '</tbody></table>' +
          '<div class="val-note">' + evs.length + ' evento(s) · ' + provFmtRate(data.total_paid) +
          ' por ação no total · primeiro em ' + fmtDate(data.first_date) + '</div></div>';

  // ── Corporate actions (bonificações / desdobramentos / grupamentos) ──
  var actions = data.actions || [];
  if (actions.length) {
    html += '<div class="val-section"><div class="reg-title">Bonificações, Desdobramentos e Grupamentos</div>' +
            '<table class="val-table prov-table"><thead><tr><th>Data Ex</th><th>Aprovação</th><th class="th-ctr">Tipo</th><th class="th-num">Fator</th><th>ISIN Emitido</th></tr></thead><tbody>';
    actions.forEach(function(a) {
      html += '<tr><td>' + (a.ex_date ? fmtDate(a.ex_date) : '<span class="muted">—</span>') + '</td>' +
              '<td>' + (a.approved_on ? fmtDate(a.approved_on) : '<span class="muted">—</span>') + '</td>' +
              '<td>' + esc(a.label || '—') + '</td>' +
              '<td class="val-val">' + (a.factor !== null && a.factor !== undefined ? esc(String(a.factor).replace('.', ',')) : '—') + '</td>' +
              '<td>' + esc(a.asset_issued || '—') + '</td></tr>';
    });
    html += '</tbody></table><div class="val-desc">Fatores conforme divulgado pela B3 (percentual sobre a posição: 100 = desdobramento que dobra, 33,33 = bonificação de ~33%, 0,01 = grupamento 100→1).</div></div>';
  }

  // ── Subscriptions ──
  var subs = data.subscriptions || [];
  if (subs.length) {
    html += '<div class="val-section"><div class="reg-title">Subscrições</div>' +
            '<table class="val-table prov-table"><thead><tr><th>Data Ex</th><th>Aprovação</th><th class="th-num">Percentual</th><th class="th-num">Preço/Unit</th><th>Data Limite</th><th>Período</th></tr></thead><tbody>';
    subs.forEach(function(s) {
      html += '<tr><td>' + (s.ex_date ? fmtDate(s.ex_date) : '<span class="muted">—</span>') + '</td>' +
              '<td>' + (s.approved_on ? fmtDate(s.approved_on) : '<span class="muted">—</span>') + '</td>' +
              '<td class="val-val">' + (s.percentage !== null && s.percentage !== undefined ? esc(String(s.percentage).replace('.', ',')) + '%' : '—') + '</td>' +
              '<td class="val-val">' + (s.price_unit !== null && s.price_unit !== undefined ? fmtBRL(s.price_unit) : '—') + '</td>' +
              '<td>' + (s.subscription_date ? fmtDate(s.subscription_date) : '<span class="muted">—</span>') + '</td>' +
              '<td>' + esc(s.trading_period || '—') + '</td></tr>';
    });
    html += '</tbody></table></div>';
  }

  panel.innerHTML = html;
  initProvHistoricoControls(panel);
}

// One delegated click + change listener per panel handles every control
// (type pills, th sorting, year select) — controls are re-rendered with
// the panel, so listeners live on the panel itself, not the nodes.
function initProvHistoricoControls(panel) {
  if (panel._provControls) return;
  panel._provControls = true;
  panel.addEventListener('click', function(e) {
    var t = e.target;
    if (!t || !t.closest) return;
    var pill = t.closest('[data-prov-type]');
    if (pill) {
      panel._provState.type = pill.getAttribute('data-prov-type');
      renderProvHistorico(panel, panel._provData);
      return;
    }
    var th = t.closest('th[data-prov-sort]');
    if (th) {
      var k = th.getAttribute('data-prov-sort');
      var st = panel._provState;
      if (st.sortKey === k) { st.sortDir = -st.sortDir; }
      else { st.sortKey = k; st.sortDir = -1; }
      renderProvHistorico(panel, panel._provData);
    }
  });
  panel.addEventListener('change', function(e) {
    var t = e.target;
    if (!t || !t.closest) return;
    var sel = t.closest('[data-prov-year]');
    if (sel) {
      panel._provState.year = sel.value;
      renderProvHistorico(panel, panel._provData);
    }
  });
}

// ── Auto-init after HTMX settle ──
// ── Lazy subtab loaders [WebUI v1.5] ─────────────────────────────────────
// Only the ACTIVE subtab fetches on tab open; the others fetch on first
// click (the old afterSettle hook fired ALL fetches eagerly — 5 parallel
// 10-year OHLCV computations, 4 of them for panels nobody opened).
window.loadPrecoSubtab = function(sub) {
  var el = document.getElementById('tab-' + sub);
  if (!el || el._loaded) return;
  var t = el.getAttribute('data-ticker');
  if (!t) return;
  el._loaded = true;
  var fns = { cotacao: initPrecoTab, indicadores: initIndicadoresTab,
              volatilidade: initVolatilidadeTab, volume: initVolumeTab,
              fibonacci: initFibonacciTab };
  if (fns[sub]) fns[sub](t);
};

window.loadFinSubtab = function(sub) {
  var el = document.getElementById(sub === 'visao_geral' ? 'tab-fin-visao-geral' : 'tab-fin-demonstracoes');
  if (!el || el._loaded) return;
  var t = el.getAttribute('data-ticker');
  if (!t) return;
  el._loaded = true;
  if (sub === 'visao_geral') initFinVisaoGeral(t); else initFinDemonstracoes(t);
};

// ── Sync page: native EventSource live log [WebUI v1.5] ─────────────────
// The old markup used hx-ext="sse" — but the HTMX SSE extension was never
// vendored, so the live log never received a single event. Native
// EventSource needs no extension and auto-reconnects.
function initSyncPage() {
  var log = document.getElementById('sync-log');
  if (!log || log._es) return;
  var url = log.getAttribute('data-sync-stream');
  if (!url || typeof EventSource === 'undefined') return;
  log._es = true;
  log.innerHTML = '';
  var es = new EventSource(url);
  es.onmessage = function(evt) {
    try { appendSyncLog(log, JSON.parse(evt.data)); } catch (e) { /* ignore */ }
  };
  es.onerror = function() { /* EventSource auto-reconnects (retry: 3000) */ };
}

function appendSyncLog(log, d) {
  var placeholder = log.querySelector('.loading');
  if (placeholder) placeholder.remove();
  var ev = d.event || 'sync';
  var msgs = { 'sync.started': 'sincronização iniciada',
               'sync.completed': 'sincronização concluída',
               'sync.failed': 'sincronização FALHOU' };
  var line = document.createElement('div');
  line.className = 'sync-line sync-ev-' + ev.replace('.', '-');
  var ts = new Date().toLocaleTimeString('pt-BR');
  // [v1.5 fix1] Events may carry a ready-made message (bulk per-ticker
  // progress: "PETR4: ok (12/380)") — prefer it over the generic labels.
  if (d.message) {
    line.textContent = '[' + ts + '] ' + (d.source ? d.source + ': ' : '') + d.message;
  } else {
    line.textContent = '[' + ts + '] ' + (d.source || d.job_id || '') +
                       ': ' + (msgs[ev] || ev) + (d.status ? ' (' + d.status + ')' : '');
  }
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
  // Refresh the freshness table right after a job finishes.
  if ((ev === 'sync.completed' || ev === 'sync.failed') && typeof htmx !== 'undefined') {
    var st = document.getElementById('sync-status');
    if (st) htmx.ajax('GET', '/api/webui/sync/status', '#sync-status');
  }
}

// ── Sync buttons: delegated POST (partial renders them on both the Sync
// page and the Dashboard ribbon) ─────────────────────────────────────────
function initSyncButtons() {
  document.body.addEventListener('click', function(e) {
    // [v1.7] Pre-flight "Verificar novamente" — re-run the diagnostics
    // panel via HTMX (the button lives INSIDE the swapped panel, so the
    // listener must be delegated like the sync buttons).
    var rerun = e.target && e.target.closest ? e.target.closest('.pf-rerun') : null;
    if (rerun) {
      var host = document.getElementById('preflight-panel');
      if (host && typeof htmx !== 'undefined') {
        host.innerHTML = '<div class="loading">Executando diagnóstico…</div>';
        htmx.ajax('GET', '/api/webui/preflight/panel', '#preflight-panel');
      }
      return;
    }
    // [v1.5 fix1] "Sincronizar tudo" — one POST, stale sources only.
    var allBtn = e.target && e.target.closest ? e.target.closest('.sync-all-btn') : null;
    if (allBtn) {
      if (allBtn.disabled) return;
      allBtn.disabled = true;
      var origAll = allBtn.textContent;
      allBtn.textContent = 'Sincronizando…';
      fetch('/api/webui/sync/all', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(res) {
          if (res && res._error) { allBtn.textContent = 'Erro'; return; }
          var n = res && res.started ? res.started.length : 0;
          allBtn.textContent = n > 0
            ? 'Iniciado (' + n + ' fonte' + (n > 1 ? 's' : '') + ')'
            : 'Tudo atualizado';
          setTimeout(function() { try { allBtn.disabled = false; allBtn.textContent = origAll; } catch (err) { /* noop */ } }, 30000);
        })
        .catch(function() { allBtn.disabled = false; allBtn.textContent = origAll; });
      return;
    }
    var btn = e.target && e.target.closest ? e.target.closest('.sync-btn') : null;
    if (!btn) return;
    var source = btn.getAttribute('data-source');
    if (!source || btn.disabled) return;
    btn.disabled = true;
    var original = btn.textContent;
    btn.textContent = 'Sincronizando…';
    fetch('/api/webui/sync/' + encodeURIComponent(source), { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(job) {
        if (job && job._error) { btn.textContent = 'Erro'; return; }
        btn.textContent = job && job.already_running ? 'Em andamento' : 'Iniciado';
        // The 30s HTMX refresh re-renders the table (fresh buttons); this
        // timeout is just a safety net if the page sits idle.
        setTimeout(function() { try { btn.disabled = false; btn.textContent = original; } catch (err) { /* noop */ } }, 30000);
      })
      .catch(function() { btn.disabled = false; btn.textContent = original; });
  });
}

// ── System log drawer (the 📜 top-bar button — every page) [v1.20] ────────
// The terminal tail made visible in-app. While the drawer is OPEN the feed
// is the SSE stream (GET /api/webui/logs/stream: one "snapshot" event with
// the whole ring buffer, then ~1s "logs" batches). While CLOSED it degrades
// to a lightweight 15s poll of /api/webui/logs?after=<id> — enough to keep
// the unseen-ERROR badge counting without holding a stream per page.
var SYSLOG_MAX_DOM = 500;

function initSyslogDrawer() {
  var drawer = document.getElementById('syslog-drawer');
  if (!drawer || drawer._booted) return;
  drawer._booted = true;

  var toggle = document.getElementById('syslog-toggle');
  var scrim = document.getElementById('syslog-scrim');
  var list = document.getElementById('syslog-list');
  var badge = document.getElementById('syslog-badge');
  var stateDot = document.getElementById('syslog-state');
  var pauseBtn = document.getElementById('syslog-pause');
  var clearBtn = document.getElementById('syslog-clear');
  var closeBtn = document.getElementById('syslog-close');
  var countEl = document.getElementById('syslog-count');
  var jumpBtn = document.getElementById('syslog-jump');
  var filters = document.getElementById('syslog-filters');

  var es = null;            // EventSource — only while open
  var pollTimer = null;     // setInterval handle — only while closed
  var entries = [];         // {id, ts, level, source, message}
  var lastId = 0;           // newest id ingested (poll anchor + SSE dedupe)
  var domId = 0;            // newest id rendered in the DOM
  var paused = false;
  var pinned = true;        // auto-scroll while the user is at the bottom
  var unseenErrors = 0;

  function isOpen() { return drawer.classList.contains('open'); }

  function setLive(on) {
    if (stateDot) stateDot.className = 'syslog-state' + (on ? ' is-live' : '');
  }

  function updateBadge() {
    if (isOpen()) unseenErrors = 0;
    if (!badge) return;
    badge.hidden = unseenErrors === 0;
    badge.textContent = unseenErrors > 99 ? '99+' : String(unseenErrors);
  }

  function updateCount() {
    if (countEl) {
      countEl.textContent = entries.length + ' evento' + (entries.length === 1 ? '' : 's') +
                            (paused ? ' · pausado' : '');
    }
  }

  function entryLine(e) {
    var line = document.createElement('div');
    line.className = 'log-line log-' + e.level;
    // [v1.28.1] the source rides as a data attribute — the drawer's
    // HTTP/App filter pills are pure CSS over it.
    if (e.source) line.setAttribute('data-source', e.source);
    var ts = document.createElement('span'); ts.className = 'log-ts'; ts.textContent = e.ts;
    var src = document.createElement('span'); src.className = 'log-src'; src.textContent = e.source;
    var msg = document.createElement('span'); msg.className = 'log-msg'; msg.textContent = e.message;
    line.appendChild(ts); line.appendChild(src); line.appendChild(msg);
    return line;
  }

  function appendDom() {
    var fresh = [];
    for (var i = 0; i < entries.length; i++) {
      if (entries[i].id > domId) fresh.push(entries[i]);
    }
    if (!fresh.length) return;
    var emptyEl = list.querySelector('.syslog-empty');
    if (emptyEl) emptyEl.remove();
    var frag = document.createDocumentFragment();
    for (var j = 0; j < fresh.length; j++) frag.appendChild(entryLine(fresh[j]));
    list.appendChild(frag);
    domId = fresh[fresh.length - 1].id;
    while (list.children.length > SYSLOG_MAX_DOM) list.removeChild(list.firstChild);
    if (pinned) list.scrollTop = list.scrollHeight;
    else if (jumpBtn) jumpBtn.hidden = false;  // new lines below the fold
  }

  function forceRender() {
    domId = 0;
    list.innerHTML = '';
    if (!entries.length) {
      var empty = document.createElement('div');
      empty.className = 'syslog-empty';
      empty.textContent = 'Sem eventos ainda — navegue, sincronize ou altere configurações.';
      list.appendChild(empty);
    } else {
      appendDom();
    }
    updateCount();
  }

  function ingest(arr) {
    if (!arr || !arr.length) return;
    for (var i = 0; i < arr.length; i++) {
      var e = arr[i];
      if (e.id <= lastId) continue;  // dedupe (snapshot overlap)
      entries.push(e);
      if (e.level === 'error' && !isOpen()) unseenErrors++;
      lastId = e.id;
    }
    if (entries.length > SYSLOG_MAX_DOM * 4) entries = entries.slice(-SYSLOG_MAX_DOM * 2);
    updateBadge();
    if (isOpen()) {
      if (!paused) appendDom();
      updateCount();
    }
  }

  // ── feed: SSE while open, poll while closed ──
  function connect() {
    if (es || typeof EventSource === 'undefined') return;
    es = new EventSource('/api/webui/logs/stream');
    es.addEventListener('snapshot', function(evt) {
      try {
        var arr = JSON.parse(evt.data) || [];
        // The snapshot is authoritative — replace the local view.
        entries = arr.slice(-SYSLOG_MAX_DOM * 2);
        for (var i = 0; i < entries.length; i++) {
          if (entries[i].id > lastId) lastId = entries[i].id;
        }
        forceRender();
      } catch (err) { /* ignore */ }
    });
    es.addEventListener('logs', function(evt) {
      try { ingest(JSON.parse(evt.data)); } catch (err) { /* ignore */ }
    });
    es.onopen = function() { setLive(true); };
    es.onerror = function() { setLive(false); /* auto-reconnects (retry: 3000) */ };
  }

  function disconnect() {
    if (es) { try { es.close(); } catch (err) { /* noop */ } es = null; }
    setLive(false);
  }

  function startPolling() {
    if (pollTimer || es) return;
    pollTimer = setInterval(function() {
      fetch('/api/webui/logs?after=' + lastId)
        .then(function(r) { return r.json(); })
        .then(function(d) { ingest(d && d.entries); })
        .catch(function() { /* offline — the next tick retries */ });
    }, 15000);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  // ── open/close ──
  function openDrawer() {
    drawer.classList.add('open');
    scrim.hidden = false;
    unseenErrors = 0;
    pinned = true;
    if (jumpBtn) jumpBtn.hidden = true;
    updateBadge();
    stopPolling();
    connect();
    // The snapshot handler force-renders + scrolls; if SSE is unavailable
    // (very old browser) the already-polled entries still render:
    forceRender();
  }

  function closeDrawer() {
    drawer.classList.remove('open');
    scrim.hidden = true;
    disconnect();
    startPolling();
  }

  if (toggle) toggle.addEventListener('click', function() { isOpen() ? closeDrawer() : openDrawer(); });
  if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
  if (scrim) scrim.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && isOpen()) closeDrawer();
  });

  // ── pause / clear ──
  if (pauseBtn) {
    pauseBtn.addEventListener('click', function() {
      paused = !paused;
      pauseBtn.textContent = paused ? '▶' : '⏸';
      pauseBtn.classList.toggle('is-paused', paused);
      if (!paused) { pinned = true; forceRender(); }
      updateCount();
    });
  }
  if (clearBtn) {
    clearBtn.addEventListener('click', function() {
      entries = [];  // visual only — the anchor stays, so the server's
                      // ring buffer history is not re-counted as "new"
      forceRender();
      updateBadge();
    });
  }

  // ── filters (CSS-driven: the list's data-filter attribute hides levels) ──
  if (filters) {
    filters.addEventListener('click', function(e) {
      var pill = e.target && e.target.closest ? e.target.closest('.syslog-pill') : null;
      if (!pill) return;
      filters.querySelectorAll('.syslog-pill').forEach(function(p) { p.classList.remove('is-active'); });
      pill.classList.add('is-active');
      list.setAttribute('data-filter', pill.getAttribute('data-filter') || 'all');
      pinned = true;
      forceRender();
    });
  }

  // ── auto-scroll: pinned while at the bottom, jump pill while scrolled up ──
  list.addEventListener('scroll', function() {
    pinned = (list.scrollTop + list.clientHeight >= list.scrollHeight - 40);
    if (pinned && jumpBtn) jumpBtn.hidden = true;
  });
  if (jumpBtn) {
    jumpBtn.addEventListener('click', function() {
      pinned = true;
      list.scrollTop = list.scrollHeight;
      jumpBtn.hidden = true;
    });
  }

  // Start closed: badge-only polling (15s, anchored on the first response).
  startPolling();
}

// ── Settings page (schema-driven form) [v1.20] ────────────────────────────
// The form renders itself from GET /api/webui/settings (the SCHEMA in
// webui/services/settings.py — adding a setting = one dict entry there).
// One control per type: bool → toggle, number → input + unit, select →
// dropdown. Dirty keys are tracked client-side; Save PUTs ONLY the patch.
// ui.theme / ui.locale are saved server-side via Set-Cookie — the client
// reloads so the whole shell (data-theme, FOUC script, locale) applies.
function initSettingsPage() {
  var root = document.getElementById('settings-root');
  if (!root || root._booted) return;
  root._booted = true;

  var state = { sections: [], values: {}, serverValues: {}, dirty: {} };

  function controlHtml(s) {
    var v = state.values[s.key];
    if (s.type === 'bool') {
      return '<label class="toggle"><input type="checkbox" data-key="' + s.key + '"' +
             (v ? ' checked' : '') + '><span class="toggle-track"></span></label>';
    }
    if (s.type === 'number') {
      return '<input type="number" class="set-input" data-key="' + s.key +
             '" value="' + v + '" min="' + (s.min || 0) + '" max="' + (s.max || 9999) + '" step="1">' +
             (s.unit ? '<span class="set-unit">' + esc(s.unit) + '</span>' : '');
    }
    if (s.type === 'select') {
      var opts = (s.options || []).map(function(o) {
        return '<option value="' + esc(o.value) + '"' + (o.value === v ? ' selected' : '') + '>' +
               esc(o.label) + '</option>';
      }).join('');
      return '<select class="set-select" data-key="' + s.key + '">' + opts + '</select>';
    }
    return '<input type="text" class="set-input" data-key="' + s.key + '" value="' + esc(String(v)) + '">';
  }

  function render() {
    var html = state.sections.map(function(sec) {
      var rows = sec.settings.map(function(s) {
        return '<div class="setting-row">' +
                 '<div class="setting-label">' +
                   '<span class="setting-name">' + esc(s.label) + '</span>' +
                   (s.help ? '<span class="setting-help">' + esc(s.help) + '</span>' : '') +
                 '</div>' +
                 '<div class="setting-control">' + controlHtml(s) + '</div>' +
               '</div>';
      }).join('');
      return '<div class="settings-section"><h3>' + esc(sec.name) + '</h3>' + rows + '</div>';
    }).join('');
    html += '<div class="settings-savebar" id="settings-savebar">' +
              '<span class="settings-msg" id="settings-msg"></span>' +
              '<button class="settings-btn" id="settings-reset">Descartar</button>' +
              '<button class="settings-btn primary" id="settings-save" disabled>Salvar</button>' +
            '</div>';
    root.innerHTML = html;
    wire();
    updateBar();
  }

  function wire() {
    function onEdit() {
      var key = this.getAttribute('data-key');
      if (!key) return;
      state.values[key] = this.type === 'checkbox' ? this.checked : this.value;
      state.dirty[key] = true;
      updateBar();
    }
    root.querySelectorAll('[data-key]').forEach(function(el) {
      el.addEventListener('input', onEdit);
      el.addEventListener('change', onEdit);
    });
    var save = document.getElementById('settings-save');
    var reset = document.getElementById('settings-reset');
    if (save) save.addEventListener('click', savePatch);
    if (reset) reset.addEventListener('click', function() {
      state.values = Object.assign({}, state.serverValues);
      state.dirty = {};
      render();
    });
  }

  function updateBar() {
    var save = document.getElementById('settings-save');
    var msg = document.getElementById('settings-msg');
    var n = Object.keys(state.dirty).length;
    if (save) save.disabled = n === 0;
    if (msg) {
      msg.className = 'settings-msg';
      msg.textContent = n > 0 ? n + ' alteração' + (n > 1 ? 'ões' : '') + ' sem salvar' : '';
    }
  }

  function savePatch() {
    var save = document.getElementById('settings-save');
    var msg = document.getElementById('settings-msg');
    if (!save || save.disabled) return;
    var patch = {};
    Object.keys(state.dirty).forEach(function(k) { patch[k] = state.values[k]; });
    save.disabled = true;
    save.textContent = 'Salvando…';
    fetch('/api/webui/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
      .then(function(r) { return r.json().then(function(j) { return { ok: r.ok, j: j }; }); })
      .then(function(res) {
        if (!res.ok || !res.j || res.j._error) {
          var errs = res.j && res.j.errors
            ? Object.keys(res.j.errors).map(function(k) { return res.j.errors[k]; }).join(' · ')
            : (res.j && res.j._error) || 'Erro ao salvar';
          save.textContent = 'Salvar';
          save.disabled = false;
          if (msg) { msg.className = 'settings-msg is-error'; msg.textContent = errs; }
          return;
        }
        state.dirty = {};
        state.values = Object.assign({}, res.j.values);
        state.serverValues = Object.assign({}, res.j.values);
        var applied = res.j.applied || [];
        if (applied.indexOf('ui.theme') >= 0 || applied.indexOf('ui.locale') >= 0) {
          save.textContent = 'Aplicando…';
          location.reload();
          return;
        }
        save.textContent = 'Salvo';
        updateBar();
        setTimeout(function() { save.textContent = 'Salvar'; }, 2500);
      })
      .catch(function() {
        save.disabled = false;
        save.textContent = 'Salvar';
        if (msg) { msg.className = 'settings-msg is-error'; msg.textContent = 'Erro de rede'; }
      });
  }

  fetch('/api/webui/settings')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      state.sections = (d && d.sections) || [];
      state.values = Object.assign({}, (d && d.values) || {});
      state.serverValues = Object.assign({}, state.values);
      render();
    })
    .catch(function() {
      root.innerHTML = '<div class="error">Falha ao carregar as configurações.</div>';
    });
}

// ── Company page bootstrap [WebUI v1.5] ─────────────────────────────────
// Replaces the old inline <script> in company.html that interpolated the
// ticker into a JS string (and needed htmx.config.includeScriptTags=true
// to even run — that flag also disabled HTMX's script sandbox, so it's
// gone). #tab-content carries data-ticker + data-active-tab now.
function initCompanyPage() {
  var tc = document.getElementById('tab-content');
  if (!tc || tc._booted) return;
  var ticker = tc.getAttribute('data-ticker');
  if (!ticker) return;
  tc._booted = true;
  var tab = tc.getAttribute('data-active-tab') || 'visao_geral';
  if (typeof htmx !== 'undefined') {
    htmx.ajax('GET',
      '/api/webui/company/' + encodeURIComponent(ticker) + '/tab/' + encodeURIComponent(tab),
      '#tab-content');
  }
}

// ── Candlestick range bar: one delegated listener ────────────────────────
function initPriceRangeBar() {
  document.body.addEventListener('click', function(e) {
    var btn = e.target && e.target.closest ? e.target.closest('#price-range-bar .range-btn') : null;
    if (!btn) return;
    var bar = document.getElementById('price-range-bar');
    if (!bar) return;
    var ticker = bar.getAttribute('data-ticker');
    var range = btn.getAttribute('data-range');
    if (ticker && range) loadCandlestick(ticker, range);
  });
}

// ── [v1.7.1 fix2] Unified Anual/Trimestral pills — ONE delegated listener ─
// for ALL THREE cards: the DRE waterfall (.fin-wf-pills, data-wf-mode) and
// the Trajetória + Tendência pair (.fin-period-pills, data-fp-mode). Both
// pill groups drive the SAME tab._finPeriod state, so clicking Anual or
// Trimestral on ANY card switches the waterfall, the Trajetória chart and
// the Tendência table together (pure client-side, payloads cached on
// tab._finPeriod). v1.7.1/fix1 had two separate listeners/states — the
// waterfall pills ignored the other two cards and vice versa.
function initFinPeriodPills() {
  document.body.addEventListener('click', function(e) {
    var pill = e.target && e.target.closest
      ? e.target.closest('.fin-wf-pills .prov-pill, .fin-period-pills .prov-pill')
      : null;
    if (!pill || pill.classList.contains('active')) return;
    var mode = pill.getAttribute('data-fp-mode') || pill.getAttribute('data-wf-mode');
    if (!mode) return;
    var tab = pill.closest('#tab-fin-visao-geral');
    if (!tab || !tab._finPeriod) return;
    tab._finPeriod.mode = mode;
    syncFinPeriodPills(tab);
    renderFinWaterfall(tab);
    renderFinTrajChart(tab);
    renderFinTrendTable(tab);
  });
}

// ── Opções tab [WebUI v1.8] ────────────────────────────────────────────────
// 5 lazy subtabs (Visão Geral / Cadeia / Volume & Exercícios / Vol.
// Implícita / Posições) over the generic /sections/options:<sub> endpoint.
// Payloads are the v1.7 FLAT contract ({kpis, sections}) + two options-
// specific extra keys: `maturities` (future expiries) + `active_maturity`
// — when present, renderOptSubtab draws the maturity pill bar and pill
// clicks refetch with ?maturity=YYYY-MM-DD (server-side filter; the chain
// is too big to ship every expiry at once). Everything else renders
// through the SAME generic renderer as Valuation/Proventos (valKpisHtml +
// valSectionsHtml + mountValCharts).
window.loadOptSubtab = function(sub, maturity) {
  var panel = document.getElementById('tab-opt-' + sub);
  if (!panel) return;
  var ticker = panel.getAttribute('data-ticker');
  if (!ticker) return;
  if (panel._loading) return;
  // _loaded guard only applies to the initial lazy load — a maturity pill
  // click passes maturity explicitly and forces the refetch.
  if (panel._loaded && !maturity) return;
  panel._loading = true;
  var url = '/api/webui/company/' + encodeURIComponent(ticker) +
            '/sections/options:' + encodeURIComponent(sub);
  if (maturity) url += '?maturity=' + encodeURIComponent(maturity);
  fetch(url)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      panel._loading = false;
      panel._loaded = true;   // set only after a successful render
      renderOptSubtab(sub, panel, data);
    })
    .catch(function(err) {
      panel._loading = false;
      panel.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
};

function renderOptSubtab(sub, panel, data) {
  if (data._error) {
    panel.innerHTML = '<div class="error">' + esc(data._error) + '</div>';
    return;
  }
  panel._valChartCfgs = {};
  var html = '';
  if (data.kpis && data.kpis.length) html += valKpisHtml(data.kpis);
  if (data.maturities && data.maturities.length) {
    html += optMatBarHtml(data.maturities, data.active_maturity, sub);
  }
  html += valSectionsHtml(data.sections || [], panel);
  panel.innerHTML = html || '<div class="loading">Sem dados</div>';
  mountValCharts(panel);
}

// Maturity pill bar — "Vencimento: 18/09/26 · 16/10/26 …". Refetches the
// subtab server-side (chain/activity/iv are maturity-scoped; the others
// don't carry maturities in the payload, so no bar is drawn for them).
function optMatBarHtml(maturities, active, sub) {
  var h = '<div class="opt-mat-bar" data-opt-sub="' + esc(sub) + '">' +
          '<span class="opt-mat-label">Vencimento:</span>';
  (maturities || []).forEach(function(m) {
    var lbl = m;
    var parts = String(m).split('-');       // 2026-09-18 → 18/09/26
    if (parts.length === 3) lbl = parts[2] + '/' + parts[1] + '/' + parts[0].slice(2);
    h += '<button type="button" class="prov-pill' +
         (m === active ? ' active' : '') +
         '" data-maturity="' + esc(m) + '" onclick="optMat(this)">' + esc(lbl) + '</button>';
  });
  return h + '</div>';
}

window.optMat = function(btn) {
  var bar = btn.closest('.opt-mat-bar');
  if (!bar) return;
  var sub = bar.getAttribute('data-opt-sub');
  var maturity = btn.getAttribute('data-maturity');
  if (!sub || !maturity) return;
  Array.prototype.forEach.call(bar.querySelectorAll('.prov-pill'), function(b) {
    b.classList.toggle('active', b === btn);
  });
  loadOptSubtab(sub, maturity);
};

// ── Acionistas tab [WebUI v1.9] ────────────────────────────────────────
// 4 lazy subtabs (Visão Geral / Posição Acionária / Free Float /
// Estrutura Patrimonial) over the generic /sections/shareholders:<sub>
// endpoint — the v1.7 recipe: service + register() + shell partial + this
// loader. Payloads are the FLAT contract ({kpis, sections}); everything
// renders through the SAME generic renderer as Valuation/Proventos/Opções
// (valKpisHtml + valSectionsHtml + mountValCharts). No pills/maturity
// passthrough here — FRE data is annual, nothing is refetched client-side.
window.loadShSubtab = function(sub) {
  var panel = document.getElementById('tab-sh-' + sub);
  if (!panel || panel._loaded) return;
  var ticker = panel.getAttribute('data-ticker');
  if (!ticker) return;
  fetch('/api/webui/company/' + encodeURIComponent(ticker) +
        '/sections/shareholders:' + encodeURIComponent(sub) + '?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) { panel._loaded = true; renderShSubtab(panel, data); })
    .catch(function(err) {
      panel.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
};

function renderShSubtab(panel, data) {
  if (data._error) {
    panel.innerHTML = '<div class="error">' + esc(data._error) + '</div>';
    return;
  }
  panel._valChartCfgs = {};
  var html = '';
  if (data.kpis && data.kpis.length) html += valKpisHtml(data.kpis);
  html += valSectionsHtml(data.sections || [], panel);
  panel.innerHTML = html || '<div class="loading">Sem dados</div>';
  mountValCharts(panel);
}

// ── Insiders tab [WebUI v1.10] ────────────────────────────────────────
// 4 lazy subtabs (Visão Geral / Movimentações / Por Cargo / Mensal) over
// the generic /sections/insiders:<sub> endpoint — the v1.7 recipe:
// service + register() + shell partial + this loader. Payloads are the
// FLAT contract ({kpis, sections}); everything renders through the SAME
// generic renderer as Valuation/Proventos/Opções/Acionistas (valKpisHtml
// + valSectionsHtml + mountValCharts). No pills/maturity passthrough —
// VLMO data is historical, nothing is refetched client-side.
window.loadInsSubtab = function(sub) {
  var panel = document.getElementById('tab-ins-' + sub);
  if (!panel || panel._loaded) return;
  var ticker = panel.getAttribute('data-ticker');
  if (!ticker) return;
  fetch('/api/webui/company/' + encodeURIComponent(ticker) +
        '/sections/insiders:' + encodeURIComponent(sub) + '?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) { panel._loaded = true; renderInsSubtab(panel, data); })
    .catch(function(err) {
      panel.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
};

function renderInsSubtab(panel, data) {
  if (data._error) {
    panel.innerHTML = '<div class="error">' + esc(data._error) + '</div>';
    return;
  }
  panel._valChartCfgs = {};
  var html = '';
  if (data.kpis && data.kpis.length) html += valKpisHtml(data.kpis);
  html += valSectionsHtml(data.sections || [], panel);
  panel.innerHTML = html || '<div class="loading">Sem dados</div>';
  mountValCharts(panel);
}

// ── Macro page [WebUI v1.11] ─────────────────────────────────────────
// 8 lazy subtabs (Visão Geral / Juros / Inflação / Câmbio / Atividade /
// Retorno Real / Expectativas Focus / Curva de Juros) over the
// TICKER-LESS generic /macro/sections/macro:<sub> endpoint — same v1.7
// recipe as the company tabs minus the company: macro is market-wide,
// so the URL has no ticker segment and the panes carry no data-ticker.
// Payloads are the FLAT contract ({kpis, sections}); everything renders
// through the SAME generic renderer as every tab since v1.8
// (valKpisHtml + valSectionsHtml + mountValCharts). No pills/passthrough
// — the range bar on history charts filters client-side (valChartRange).
window.loadMacroSubtab = function(sub) {
  var panel = document.getElementById('tab-macro-' + sub);
  if (!panel || panel._loaded) return;
  fetch('/api/webui/macro/sections/macro:' + encodeURIComponent(sub) +
        '?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) { panel._loaded = true; renderMacroSubtab(panel, data); })
    .catch(function(err) {
      panel.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
};

function renderMacroSubtab(panel, data) {
  if (data._error) {
    panel.innerHTML = '<div class="error">' + esc(data._error) + '</div>';
    return;
  }
  panel._valChartCfgs = {};
  var html = '';
  if (data.kpis && data.kpis.length) html += valKpisHtml(data.kpis);
  html += valSectionsHtml(data.sections || [], panel);
  panel.innerHTML = html || '<div class="loading">Sem dados</div>';
  mountValCharts(panel);
}

// ── Mercado page [WebUI v1.12 / v1.13] ───────────────────────────────
// Family subtab loaders over the TICKER-LESS generic /mercado/sections/
// <family>:<sub> endpoint — same v1.11 macro recipe (market-wide payload,
// no ticker segment, FLAT contract, generic renderer). The page carries
// one more level than macro: FAMILY pills (focus v1.12, fluxo v1.13,
// índices v1.14, inflação v1.15, juros v1.16, ações v1.17, proventos
// v1.18). The per-family loaders only differ by the family key, so
// ONE factory builds them (pane id tab-<family>-<sub>, endpoint key
// <family>:<sub>) — the v1.13 fluxo family was a one-line addition.
function mercadoLoader(family) {
  return function(sub) {
    var panel = document.getElementById('tab-' + family + '-' + sub);
    if (!panel || panel._loaded) return;
    fetch('/api/webui/mercado/sections/' + family + ':' +
          encodeURIComponent(sub) + '?_t=' + Date.now())
      .then(function(r) { return r.json(); })
      .then(function(data) {
        panel._loaded = true; renderMercadoSubtab(panel, data);
      })
      .catch(function(err) {
        panel.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
      });
  };
}

function renderMercadoSubtab(panel, data) {
  if (data._error) {
    panel.innerHTML = '<div class="error">' + esc(data._error) + '</div>';
    return;
  }
  panel._valChartCfgs = {};
  var html = '';
  if (data.kpis && data.kpis.length) html += valKpisHtml(data.kpis);
  html += valSectionsHtml(data.sections || [], panel);
  panel.innerHTML = html || '<div class="loading">Sem dados</div>';
  mountValCharts(panel);
}

window.loadFocusSubtab = mercadoLoader('focus');   // [v1.12] Boletim Focus
window.loadFluxoSubtab = mercadoLoader('fluxo');   // [v1.13] B3 flow
window.loadIndicesSubtab = mercadoLoader('indices'); // [v1.14] B3 índices
window.loadInflacaoSubtab = mercadoLoader('inflacao'); // [v1.15] índices de preços
window.loadJurosSubtab = mercadoLoader('juros'); // [v1.16] taxas de juros
window.loadPoupancaSubtab = mercadoLoader('poupanca'); // [v1.23] caderneta (× IPCA × CDI)
window.loadAcoesSubtab = mercadoLoader('acoes'); // [v1.17] ações B3 + evolução
window.loadDividendosSubtab = mercadoLoader('dividendos'); // [v1.18] proventos (BDR split)

// ── Ferramentas — Comparação [WebUI v1.27] ─────────────────────────────
// The first tool of the new Ferramentas main tab: 2-4 companies side by
// side, the online-shop way. Three layers, all owned by this block:
//
//   1. THE PICKER — debounced bridge-DB search (arrow-key navigable
//      dropdown, Enter adds the highlighted row or the typed ticker),
//      one chip per selected company (color dot + ✕), the selection in
//      the URL (?t=PETR4.VALE3 — shareable, survives reload). The
//      input disables itself at 4 companies (the max — no error toast
//      needed, the placeholder explains).
//   2. THE GRID — one COLUMN per company, metric rows grouped by theme,
//      the label column sticky on mobile horizontal scroll. The BEST
//      value of each row is ranked SERVER-side (green cell + ✓; cheaper
//      multiples, higher profitability, lower debt — size metrics don't
//      rank); the column header is a company card (dot, ticker link,
//      name, sector, last price + day change).
//   3. THE CHARTS — leader KPI cards (Menor P/L, Menor EV/EBITDA, Maior
//      ROE, Maior Div Yield) + the normalized Perfil Comparado radar +
//      grouped bars (múltiplos/margens/crescimento/dividendos, server
//      configs drawn through the shared renderValChart) + the base-100
//      performance line with range pills (1A/3A/5A/Tudo — re-sliced and
//      re-normalized client-side from the raw month-end closes payload).
//
// Payload: GET /api/webui/tools/comparison?tickers=… (webui/services/
// comparison.py — payload-cached on the composite fingerprint of every
// compared ticker, the v1.26.1 webui_payloads foundation; first builds
// compute every company's ratios/annual/growth/dividends and can take a
// few seconds — the loading line says so).

// [v1.28.1] The tools' shared LOADING CARD — the one-line italic
// "Carregando…" was easy to miss on the slow first builds (the
// screener's first pass on a 40-company sector runs MINUTES — the
// user saw a blank page and asked for a "carregando" message). A
// spinner + what's loading + why it can be slow + a live elapsed
// counter, one card per tool, timers tracked by id.
var _toolLoadTimers = {};

// [v1.28.2] + the optional Cancelar button (cancelFn = a global handler
// name for the inline onclick): the screener's minutes-long first pass is
// cancellable; the other tools pass nothing and render exactly as before.
function toolLoadingHtml(id, title, hint, cancelFn) {
  return '<div class="cmp-loading" id="' + id + '" role="status" aria-live="polite">' +
    '<div class="cmp-loading-spin" aria-hidden="true"></div>' +
    '<div class="cmp-loading-body">' +
    '<div class="cmp-loading-title">' + title + '</div>' +
    (hint ? '<div class="cmp-loading-hint">' + hint + '</div>' : '') +
    '<div class="cmp-loading-elapsed" id="' + id + '-elapsed">carregando…</div>' +
    '</div>' +
    (cancelFn
      ? '<button type="button" class="cmp-range-btn cmp-loading-cancel" onclick="' +
        cancelFn + '">Cancelar</button>'
      : '') +
    '</div>';
}

function toolLoadingStart(id) {
  toolLoadingStop(id);
  var t0 = Date.now();
  var el = function() {
    var node = document.getElementById(id + '-elapsed');
    if (!node) { delete _toolLoadTimers[id]; return; }
    var s = Math.floor((Date.now() - t0) / 1000);
    node.textContent = 'carregando há ' + (s < 60 ? s + 's'
      : Math.floor(s / 60) + 'min ' + (s % 60) + 's');
  };
  el();
  _toolLoadTimers[id] = setInterval(el, 1000);
}

function toolLoadingStop(id) {
  if (_toolLoadTimers[id]) { clearInterval(_toolLoadTimers[id]); delete _toolLoadTimers[id]; }
}

var CMP_MAX = 4;
var CMP_COLORS = ['#0d9488', '#f59e0b', '#8b5cf6', '#e11d48'];
var cmpState = { booted: false, tickers: [], perfRange: '1A', histRange: '1A', data: null, activeIdx: -1 };

window.cmpFocusPicker = function() {
  var el = document.getElementById('cmp-search');
  if (el) el.focus();
};

function initToolsPage() {
  var root = document.getElementById('tools-root');
  if (!root || cmpState.booted) return;
  cmpState.booted = true;

  // Deep link: ?t=PETR4.VALE3 (dots — tickers never carry them).
  try {
    var q = new URLSearchParams(window.location.search).get('t') || '';
    q.toUpperCase().split('.').forEach(function(tk) {
      if (/^[A-Z0-9]{4,6}$/.test(tk) && cmpState.tickers.length < CMP_MAX &&
          cmpState.tickers.indexOf(tk) < 0) cmpState.tickers.push(tk);
    });
  } catch (e) { /* noop */ }

  var input = document.getElementById('cmp-search');
  var drop = document.getElementById('cmp-dropdown');

  // [v1.28] Screener — the second tool boots alongside (its own pane;
  // its own guards, independent of the comparison picker's elements).
  // [v1.28.1] Backtest — the third tool (moved from the company tab;
  // its own picker + ?b= deep link, same boot pattern).
  initScreener();
  initBacktestTool();

  if (!input || !drop) return;

  var debounce = null;
  input.addEventListener('input', function() {
    clearTimeout(debounce);
    var q = input.value.trim();
    if (!q) { cmpDropHide(drop); return; }
    debounce = setTimeout(function() { cmpDropSearch(drop, q); }, 250);
  });
  input.addEventListener('keydown', function(ev) {
    var items = drop._items || [];
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      if (!items.length) return;
      ev.preventDefault();
      cmpState.activeIdx = ev.key === 'ArrowDown'
        ? Math.min(cmpState.activeIdx + 1, items.length - 1)
        : Math.max(cmpState.activeIdx - 1, 0);
      cmpDropRender(drop);
    } else if (ev.key === 'Enter') {
      ev.preventDefault();
      var tk = (cmpState.activeIdx >= 0 && items[cmpState.activeIdx])
        ? items[cmpState.activeIdx].ticker
        : input.value.trim().toUpperCase();
      if (tk) { cmpAddTicker(tk); input.value = ''; cmpDropHide(drop); }
    } else if (ev.key === 'Escape') {
      cmpDropHide(drop);
    }
  });
  // Click outside closes the dropdown (one listener per page boot).
  document.addEventListener('click', function(ev) {
    if (!drop.hidden && drop.parentNode && !drop.parentNode.contains(ev.target)) {
      cmpDropHide(drop);
    }
  });

  cmpRenderChips();
  if (cmpState.tickers.length >= 2) cmpLoad(); else cmpShowEmpty();
}

function cmpDropSearch(drop, q) {
  fetch('/api/webui/tools/comparison/search?q=' + encodeURIComponent(q))
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var items = (d && d.results) || [];
      if (!items.length) {
        drop._items = null; cmpState.activeIdx = -1;
        drop.hidden = true;
        return;
      }
      drop._items = items;
      cmpState.activeIdx = -1;
      cmpDropRender(drop);
    })
    .catch(function() { cmpDropHide(drop); });
}

function cmpDropRender(drop) {
  var items = drop._items || [];
  var html = '';
  items.forEach(function(it, i) {
    var already = cmpState.tickers.indexOf(it.ticker) >= 0;
    html += '<button type="button" class="cmp-drop-item' +
      (i === cmpState.activeIdx ? ' active' : '') + (already ? ' added' : '') +
      '" data-tk="' + esc(it.ticker) + '">' +
      '<span class="cmp-drop-tk">' + esc(it.ticker) + '</span>' +
      '<span class="cmp-drop-name">' + esc(it.name || '') + '</span>' +
      (already ? '<span class="cmp-drop-added">na comparação</span>' : '') +
      '</button>';
  });
  drop.innerHTML = html;
  drop.hidden = false;
  Array.prototype.forEach.call(drop.querySelectorAll('.cmp-drop-item'), function(btn) {
    btn.addEventListener('click', function() {
      var input = document.getElementById('cmp-search');
      cmpAddTicker(btn.getAttribute('data-tk') || '');
      if (input) input.value = '';
      cmpDropHide(drop);
    });
  });
}

function cmpDropHide(drop) {
  drop.hidden = true;
  drop._items = null;
  cmpState.activeIdx = -1;
}

function cmpAddTicker(tk) {
  tk = String(tk || '').trim().toUpperCase();
  // Same B3 shape the server validates — a ticker from ANY source (search
  // results included) must match before it reaches an onclick attribute.
  if (!/^[A-Z0-9]{4,6}$/.test(tk) || cmpState.tickers.indexOf(tk) >= 0 ||
      cmpState.tickers.length >= CMP_MAX) return;
  cmpState.tickers.push(tk);
  cmpRenderChips();
  cmpMaybeLoad();
}

window.cmpRemoveTicker = function(tk) {
  var i = cmpState.tickers.indexOf(tk);
  if (i >= 0) cmpState.tickers.splice(i, 1);
  cmpRenderChips();
  cmpMaybeLoad();
};

function cmpRenderChips() {
  var box = document.getElementById('cmp-chips');
  var input = document.getElementById('cmp-search');
  if (!box) return;
  var full = cmpState.tickers.length >= CMP_MAX;
  if (input) {
    input.disabled = full;
    input.placeholder = full
      ? 'Máximo de ' + CMP_MAX + ' empresas — remova uma para trocar'
      : 'Buscar empresa ou ticker (ex.: PETR4, Petrobras…)';
  }
  if (!cmpState.tickers.length) { box.innerHTML = ''; box.hidden = true; return; }
  box.hidden = false;
  var html = '';
  cmpState.tickers.forEach(function(tk, i) {
    html += '<span class="cmp-chip" style="--chip-color:' + safeColor(CMP_COLORS[i % CMP_COLORS.length], '#0d9488') + '">' +
      '<span class="cmp-chip-dot"></span>' + esc(tk) +
      '<button type="button" class="cmp-chip-x" title="Remover ' + esc(tk) +
      '" onclick="cmpRemoveTicker(\'' + esc(tk) + '\')">✕</button></span>';
  });
  var hint = cmpState.tickers.length >= 2 ? '' :
    '<span class="cmp-chip-hint">escolha mais ' + (2 - cmpState.tickers.length) +
    ' empresa' + (2 - cmpState.tickers.length > 1 ? 's' : '') + ' para comparar</span>';
  box.innerHTML = html + hint;
}

function cmpMaybeLoad() {
  cmpSyncUrl();
  if (cmpState.tickers.length >= 2) cmpLoad();
  else cmpShowEmpty();
}

function cmpSyncUrl() {
  // [v1.28] URLSearchParams — only THIS tool's ?t= key is rewritten;
  // the screener's ?s= deep link (and anything else) survives.
  try {
    var url = new URL(window.location.href);
    if (cmpState.tickers.length) {
      url.searchParams.set('t', cmpState.tickers.join('.'));
    } else {
      url.searchParams.delete('t');
    }
    window.history.replaceState('', '', url.pathname + url.search);
  } catch (e) { /* noop */ }
}

function cmpShowEmpty() {
  var box = document.getElementById('cmp-result');
  if (!box) return;
  destroyChartsIn(box);
  cmpState.data = null;
  box.innerHTML =
    '<div class="cmp-empty">' +
    '<div class="cmp-empty-icon">⚖️</div>' +
    '<p class="cmp-empty-title">Escolha de 2 a 4 empresas para comparar</p>' +
    '<p class="cmp-empty-hint">Busque por ticker ou nome acima. A comparação ' +
    'abre com a cotação histórica de cada empresa lado a lado, depois mostra ' +
    'os indicadores por tema com o melhor valor de cada linha destacado, ' +
    'e fecha com o radar de perfil, os múltiplos, as margens, o ' +
    'crescimento e o desempenho da ação em base 100.</p></div>';
}

// [v1.28.2] STALE-RESPONSE GUARD — removing/adding a ticker re-enters
// cmpLoad while a slow first build is still in flight; the older answer
// used to be free to land LAST and overwrite the newer comparison (and
// to kill ITS elapsed timer — both loads share the 'cmp-load' id).
// Every load takes a ticket from this counter; a response only touches
// the pane while it still holds the LATEST ticket.
var cmpReqSeq = 0;

function cmpLoad() {
  var box = document.getElementById('cmp-result');
  if (!box) return;
  var seq = ++cmpReqSeq;
  destroyChartsIn(box);
  cmpState.data = null;
  // [v1.28.1] the shared loading card — spinner + ticker set + elapsed
  // (the ask: "while its loading it should display some message to say
  // its carregando").
  box.innerHTML = toolLoadingHtml('cmp-load',
    'Comparando ' + esc(cmpState.tickers.join(' × ')),
    'Os indicadores de cada empresa são calculados na primeira vez — ' +
    'pode levar alguns segundos.');
  toolLoadingStart('cmp-load');
  fetch('/api/webui/tools/comparison?tickers=' +
        encodeURIComponent(cmpState.tickers.join(',')) +
        '&_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (seq !== cmpReqSeq) return;  // superseded — a newer set owns the pane
      toolLoadingStop('cmp-load');
      if (!data || data.status !== 'ok') {
        box.innerHTML = '<div class="error">' +
          esc((data && data.error) || 'falha na comparação') + '</div>';
        return;
      }
      cmpState.data = data;
      cmpRender(box, data);
    })
    .catch(function(err) {
      if (seq !== cmpReqSeq) return;  // superseded — stay quiet
      toolLoadingStop('cmp-load');
      box.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
}

function cmpRender(box, data) {
  // The Cotação Histórica cards open the comparison (the product-photo
  // slot of the online-shop layout), then the grid, then the charts.
  var html = cmpHistHtml(data);
  html += cmpGridHtml(data);
  html += cmpChartsHtml(data);
  if (data.cache_note) {
    html += '<p class="fin-cache-note"><span class="fin-cache-bolt">⚡</span> ' +
      esc(data.cache_note) + '</p>';
  }
  if (data.errors && data.errors.length) {
    html += '<p class="cmp-errors">⚠️ ' + esc(data.errors.join(' · ')) + '</p>';
  }
  box.innerHTML = html;
  cmpMountCharts(box, data);
}

// ── the grid (online-shop comparison table) ──

function cmpCoCardHtml(c) {
  var varHtml = (c.var_day === null || c.var_day === undefined)
    ? '' : ' <span class="cmp-co-var">' + fmtPctColored(c.var_day) + '</span>';
  return '<div class="cmp-co-card">' +
    '<div class="cmp-co-top">' +
    '<span class="cmp-dot" style="background:' + safeColor(c.color, '#0d9488') + '"></span>' +
    '<a class="cmp-co-tk" href="/webui/company/' + encodeURIComponent(c.ticker) + '">' +
    esc(c.ticker) + '</a>' +
    '<button type="button" class="cmp-co-x" title="Remover ' + esc(c.ticker) +
    ' da comparação" onclick="cmpRemoveTicker(\'' + esc(c.ticker) + '\')">✕</button>' +
    '</div>' +
    (c.name ? '<div class="cmp-co-name" title="' + esc(c.name) + '">' + esc(c.name) + '</div>' : '') +
    (c.sector ? '<div class="cmp-co-sector" title="' + esc(c.sector) + '">' + esc(c.sector) + '</div>' : '') +
    '<div class="cmp-co-price">' + fmtBRL(c.price) + varHtml + '</div>' +
    (c.error ? '<div class="cmp-co-err" title="Algumas fontes de dados desta empresa falharam — os indicadores dela vêm parciais">' + esc(c.error) + '</div>' : '') +
    '</div>';
}

function cmpGridHtml(data) {
  var n = data.companies.length;
  var html = '<div class="cmp-gridwrap"><table class="cmp-grid"><thead><tr>' +
    '<th class="cmp-corner" scope="col">Indicador</th>';
  data.companies.forEach(function(c) {
    html += '<th class="cmp-co" scope="col">' + cmpCoCardHtml(c) + '</th>';
  });
  html += '</tr></thead><tbody>';
  data.groups.forEach(function(g) {
    html += '<tr class="cmp-group"><td colspan="' + (n + 1) + '">' + esc(g.name) + '</td></tr>';
    g.rows.forEach(function(row) {
      html += '<tr><th scope="row" class="cmp-rowlabel" title="' + esc(row.tip || '') + '">' +
        esc(row.label) + (row.tip ? ' <span class="cmp-info" aria-hidden="true">ⓘ</span>' : '') +
        '</th>';
      row.values.forEach(function(v, i) {
        var isBest = row.best && row.best.indexOf(i) >= 0;
        // [v1.28.3] The Última Cotação row's cells wear the
        // price-band pills (server-computed row.pills — one per cell,
        // None where there's no price); every other metric row stays
        // plain (the scheme is for MAIN prices, and this row IS the
        // price row).
        var cellHtml = (row.pills && row.pills[i])
          ? homePricePill(row.pills[i], v)
          : esc(v);
        html += '<td class="cmp-cell' + (isBest ? ' cmp-best' : '') + '">' + cellHtml +
          (isBest ? ' <span class="cmp-bestbadge" title="melhor da linha">✓</span>' : '') +
          '</td>';
      });
      html += '</tr>';
    });
  });
  html += '</tbody></table></div>' +
    '<p class="cmp-legend">✓ = melhor valor da linha entre as empresas comparadas ' +
    '(múltiplos, cotação e endividamento menores; rentabilidade, ' +
    'rendimento, crescimento, tamanho e demonstrativos anuais maiores).</p>';
  return html;
}

// ── the charts ──
//
// The standard app range bar (Tudo/10A/5A/1A/6M/3M/1M — the same
// pills every other chart carries). Long ranges read the month-end
// series; 1A and shorter read the daily one (month-ends are too
// coarse for a 1M window: two points).
var CMP_RANGES = ['Tudo', '10A', '5A', '1A', '6M', '3M', '1M'];

function cmpRangeDaily(range) {
  return range === '1A' || range === '6M' || range === '3M' || range === '1M';
}

function cmpRangeCutoff(range, daily) {
  // ISO cutoff for the window (YYYY-MM-DD on daily, YYYY-MM monthly;
  // null = Tudo). ISO dates compare lexicographically. Built from
  // LOCAL calendar parts — toISOString() shifts the day/month back on
  // any TZ ahead of UTC (the 5A pill leaked one extra month there).
  var now = new Date();
  var p2 = function(n) { return (n < 10 ? '0' : '') + n; };
  if (daily) {
    var days = { '1A': 365, '6M': 183, '3M': 92, '1M': 31 }[range] || 0;
    var d = new Date(now.getTime() - days * 86400000);
    return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate());
  }
  var months = { '10A': 120, '5A': 60 }[range] || 0;
  if (!months) return null;
  var m = new Date(now.getFullYear(), now.getMonth() - months, 1);
  return m.getFullYear() + '-' + p2(m.getMonth() + 1);
}

function cmpWindow(points, cutoff) {
  // points: [{date, close}, …] — the service's price_hist contract
  // ("date" carries YYYY-MM-DD on the daily series, YYYY-MM on the
  // month-ends; both slice lexicographically). A stale series shorter
  // than the window degrades to its last point.
  if (!cutoff) return points;
  for (var i = 0; i < points.length; i++) {
    if (String(points[i].date) >= cutoff) return points.slice(i);
  }
  return points.slice(-1);
}

function cmpRangeBarHtml(active, handler) {
  var html = '';
  CMP_RANGES.forEach(function(r) {
    html += '<button type="button" class="cmp-range-btn' +
      (active === r ? ' active' : '') + '" data-range="' + r +
      '" onclick="' + handler + '(this)">' + r + '</button>';
  });
  return html;
}

// ── Cotação Histórica — one mini chart per company, ABOVE the grid ──

function cmpHistHtml(data) {
  var html = '<div class="cmp-chartcard cmp-hist-card">' +
    '<div class="cmp-chart-head"><div class="cmp-chart-title">Cotação Histórica</div>' +
    '<div class="cmp-range-bar" role="group" aria-label="Período da cotação">' +
    cmpRangeBarHtml(cmpState.histRange, 'cmpHistRange') + '</div></div>' +
    '<p class="cmp-chart-desc">Fechamentos de cada empresa no período selecionado ' +
    '— mensais nos períodos longos, diários nos curtos.</p>' +
    '<div class="cmp-hist-grid" style="--n:' + data.companies.length + '">';
  data.companies.forEach(function(c) {
    html += '<div class="cmp-hist-cell">' +
      '<div class="cmp-hist-head">' +
      '<span class="cmp-dot" style="background:' + safeColor(c.color, '#0d9488') + '"></span>' +
      '<span class="cmp-hist-tk">' + esc(c.ticker) + '</span>' +
      '</div>' +
      '<div class="cmp-hist-chart"><canvas id="cmp-hist-' + esc(c.ticker) + '"></canvas>' +
      '<div class="cmp-hist-none" id="cmp-hist-none-' + esc(c.ticker) + '" hidden>sem cotações no período</div></div>' +
      '</div>';
  });
  html += '</div></div>';
  return html;
}

window.cmpHistRange = function(btn) {
  var bar = btn.parentNode;
  Array.prototype.forEach.call(bar.querySelectorAll('.cmp-range-btn'), function(b) {
    b.classList.remove('active');
  });
  btn.classList.add('active');
  cmpState.histRange = btn.getAttribute('data-range') || '1A';
  cmpMountHist();
};

function cmpMountHist() {
  var data = cmpState.data;
  if (!data || !data.price_hist) return;
  var daily = cmpRangeDaily(cmpState.histRange);
  var src = (data.price_hist[daily ? 'daily' : 'monthly']) || {};
  var cutoff = cmpRangeCutoff(cmpState.histRange, daily);
  data.companies.forEach(function(c) {
    var canvas = document.getElementById('cmp-hist-' + c.ticker);
    if (!canvas) return;
    var noneEl = document.getElementById('cmp-hist-none-' + c.ticker);
    var pts = cmpWindow(src[c.ticker] || [], cutoff);
    destroyChartsIn(canvas);
    // [v1.28.1] the period-% chip is GONE ("not really needed") — the
    // card is just the line now; the Desempenho base-100 chart owns the
    // period comparison story.
    if (pts.length < 2) {
      // nothing to draw — say so, don't show a void. The inline display
      // matters: Chart.js stamps display:block on every canvas it owns,
      // and an inline style BEATS the hidden attribute (the v1.21 fix 3
      // lesson — attribute hiding loses to any explicit display).
      canvas.hidden = true;
      canvas.style.display = 'none';
      if (noneEl) noneEl.hidden = false;
      return;
    }
    canvas.hidden = false;
    canvas.style.display = '';
    if (noneEl) noneEl.hidden = true;
    renderValChart(canvas, {
      type: 'line',
      data: {
        labels: pts.map(function(p) { return String(p.date); }),
        datasets: [{
          label: c.ticker,
          data: pts.map(function(p) { return p.close; }),
          borderColor: safeColor(c.color, '#0d9488'),
          backgroundColor: safeColor(c.color, '#0d9488') + '22',
          fill: true, pointRadius: 0, pointHitRadius: 6
        }]
      },
      options: { scales: { y: { title: { text: 'R$' } } } }
    });
  });
}

function cmpChartsHtml(data) {
  // Performance first (with the range pills), then the server configs.
  var html = '<div class="cmp-chartcard cmp-perf-card">' +
    '<div class="cmp-chart-head"><div class="cmp-chart-title">Desempenho — Base 100</div>' +
    '<div class="cmp-range-bar" role="group" aria-label="Período do desempenho">' +
    cmpRangeBarHtml(cmpState.perfRange, 'cmpPerfRange') + '</div></div>' +
    '<p class="cmp-chart-desc">Cada ação normalizada para 100 no início do ' +
    'período selecionado — fechamentos mensais nos períodos longos, ' +
    'diários nos curtos.</p>' +
    '<div class="chart-container"><canvas id="cmp-chart-perf"></canvas></div></div>';

  html += '<div class="cmp-chartgrid">';
  (data.charts || []).forEach(function(ch) {
    html += '<div class="cmp-chartcard">' +
      '<div class="cmp-chart-head"><div class="cmp-chart-title">' + esc(ch.title) + '</div></div>' +
      (ch.desc ? '<p class="cmp-chart-desc">' + esc(ch.desc) + '</p>' : '') +
      '<div class="chart-container"><canvas id="cmp-chart-' + esc(ch.id) + '"></canvas></div>' +
      '</div>';
  });
  html += '</div>';
  return html;
}

window.cmpPerfRange = function(btn) {
  var bar = btn.parentNode;
  Array.prototype.forEach.call(bar.querySelectorAll('.cmp-range-btn'), function(b) {
    b.classList.remove('active');
  });
  btn.classList.add('active');
  cmpState.perfRange = btn.getAttribute('data-range') || '1A';
  cmpMountPerf();
};

function cmpPerfCd() {
  var data = cmpState.data;
  if (!data || !data.price_hist) return null;
  var daily = cmpRangeDaily(cmpState.perfRange);
  var src = (data.price_hist[daily ? 'daily' : 'monthly']) || {};
  var cutoff = cmpRangeCutoff(cmpState.perfRange, daily);
  // union axis: each company keeps its own dates; dates only one
  // company has render as gaps (null) for the others
  var seen = {};
  var labels = [];
  data.companies.forEach(function(c) {
    cmpWindow(src[c.ticker] || [], cutoff).forEach(function(p) {
      var l = String(p.date);
      if (!seen[l]) { seen[l] = true; labels.push(l); }
    });
  });
  labels.sort();
  if (!labels.length) return null;
  var datasets = [];
  data.companies.forEach(function(c) {
    var pts = cmpWindow(src[c.ticker] || [], cutoff);
    if (pts.length < 2) return;               // no line to draw in window
    var byLbl = {};
    pts.forEach(function(p) { byLbl[String(p.date)] = p.close; });
    var base = null;
    for (var i = 0; i < labels.length; i++) {
      if (byLbl[labels[i]] !== undefined) { base = byLbl[labels[i]]; break; }
    }
    if (base === null || !isFinite(base) || base <= 0) return;  // no data in window
    datasets.push({
      label: c.ticker,
      data: labels.map(function(l) {
        var v = byLbl[l];
        return v === undefined ? null : Math.round(v / base * 1000) / 10;
      }),
      borderColor: safeColor(c.color, '#0d9488'),
      backgroundColor: safeColor(c.color, '#0d9488') + '20',
      pointRadius: 0, pointHitRadius: 6
    });
  });
  if (!datasets.length) return null;
  return {
    type: 'line',
    data: { labels: labels, datasets: datasets },
    options: { scales: { y: { title: { text: 'base 100' } } } }
  };
}

function cmpMountPerf() {
  var canvas = document.getElementById('cmp-chart-perf');
  if (!canvas) return;
  destroyChartsIn(canvas);
  var cd = cmpPerfCd();
  if (cd) renderValChart(canvas, cd);
}

function cmpMountCharts(box, data) {
  (data.charts || []).forEach(function(ch) {
    var canvas = document.getElementById('cmp-chart-' + ch.id);
    if (canvas) renderValChart(canvas, ch.cd);
  });
  cmpMountHist();
  cmpMountPerf();
}

// ═══════════════════════════════════════════════════════════════════
// SCREENER — the Ferramentas tab's second tool [WebUI v1.28].
//
// ONE ticker screened against its whole SECTOR: the sector-median KPI
// row + the Cotação Histórica card (the comparison tool's range-bar
// machinery, subject only) + the sector table (one class per company,
// P/L cheapest-first, the subject row highlighted) + the P/L and ROE
// position charts (server configs — the subject in amber, the median
// as a dashed line) + the Meu Valor × Mediana verdict table (cheap /
// expensive for multiples and leverage, above / below for quality)
// and its grouped-bars chart.
//
// The picker reuses the comparison search endpoint (same bridge-DB
// search, JSON) with its own single-selection state. The deep link is
// ?s=PETR4 (the comparison's ?t= survives alongside — both sync
// through URLSearchParams, each touching only its own key).
//
// Payload: GET /api/webui/tools/screener?ticker=… (webui/services/
// screener.py — payload-cached on the composite fingerprint of every
// sector company + the peer list; the first build computes the whole
// sector and can take a few seconds — the loading line says so).
// ═══════════════════════════════════════════════════════════════════

var scrState = { booted: false, ticker: '', histRange: '1A', data: null,
                activeIdx: -1, sortKey: 'p_l', sortDir: 'asc' };

window.scrFocusPicker = function() {
  var el = document.getElementById('scr-search');
  if (el) el.focus();
};

function initScreener() {
  var input = document.getElementById('scr-search');
  var drop = document.getElementById('scr-dropdown');
  if (!input || !drop || scrState.booted) return;
  scrState.booted = true;

  // Deep link: ?s=PETR4 — boots the screen and switches the family
  // pill (the click drives Alpine's family state, same as a user tap).
  var bootTk = '';
  try {
    bootTk = (new URLSearchParams(window.location.search).get('s') || '')
      .trim().toUpperCase();
  } catch (e) { /* noop */ }
  if (/^[A-Z0-9]{4,6}$/.test(bootTk)) {
    scrState.ticker = bootTk;
    try {
      var pill = document.getElementById('family-pill-screener');
      if (pill) pill.click();
    } catch (e) { /* noop */ }
  }

  var debounce = null;
  input.addEventListener('input', function() {
    clearTimeout(debounce);
    var q = input.value.trim();
    if (!q) { scrDropHide(drop); return; }
    debounce = setTimeout(function() { scrDropSearch(drop, q); }, 250);
  });
  input.addEventListener('keydown', function(ev) {
    var items = drop._items || [];
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      if (!items.length) return;
      ev.preventDefault();
      scrState.activeIdx = ev.key === 'ArrowDown'
        ? Math.min(scrState.activeIdx + 1, items.length - 1)
        : Math.max(scrState.activeIdx - 1, 0);
      scrDropRender(drop);
    } else if (ev.key === 'Enter') {
      ev.preventDefault();
      var tk = (scrState.activeIdx >= 0 && items[scrState.activeIdx])
        ? items[scrState.activeIdx].ticker
        : input.value.trim().toUpperCase();
      if (tk) { scrSetTicker(tk); input.value = ''; scrDropHide(drop); }
    } else if (ev.key === 'Escape') {
      scrDropHide(drop);
    }
  });
  document.addEventListener('click', function(ev) {
    if (!drop.hidden && drop.parentNode && !drop.parentNode.contains(ev.target)) {
      scrDropHide(drop);
    }
  });

  // [v1.28.1] the sector table's sort — ONE delegated listener on the
  // result box (the table re-renders on every sort/screen; per-th
  // listeners would need re-binding every time).
  var scrBox = document.getElementById('scr-result');
  if (scrBox) {
    scrBox.addEventListener('click', function(ev) {
      var th = ev.target && ev.target.closest ? ev.target.closest('th.scr-sortable') : null;
      if (!th) return;
      scrSortBy(th.getAttribute('data-scrsort') || '');
    });
  }

  if (scrState.ticker) scrLoad(); else scrShowEmpty();
}

// ── the picker dropdown (same search endpoint as the comparison) ──

function scrDropSearch(drop, q) {
  fetch('/api/webui/tools/comparison/search?q=' + encodeURIComponent(q))
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var items = (d && d.results) || [];
      if (!items.length) {
        drop._items = null; scrState.activeIdx = -1;
        drop.hidden = true;
        return;
      }
      drop._items = items;
      scrState.activeIdx = -1;
      scrDropRender(drop);
    })
    .catch(function() { scrDropHide(drop); });
}

function scrDropRender(drop) {
  var items = drop._items || [];
  var current = scrState.ticker;
  var html = '';
  items.forEach(function(it, i) {
    var isCur = it.ticker === current;
    html += '<button type="button" class="cmp-drop-item' +
      (i === scrState.activeIdx ? ' active' : '') + (isCur ? ' added' : '') +
      '" data-tk="' + esc(it.ticker) + '">' +
      '<span class="cmp-drop-tk">' + esc(it.ticker) + '</span>' +
      '<span class="cmp-drop-name">' + esc(it.name || '') + '</span>' +
      (isCur ? '<span class="cmp-drop-added">no screener</span>' : '') +
      '</button>';
  });
  drop.innerHTML = html;
  drop.hidden = false;
  Array.prototype.forEach.call(drop.querySelectorAll('.cmp-drop-item'), function(btn) {
    btn.addEventListener('click', function() {
      var input = document.getElementById('scr-search');
      scrSetTicker(btn.getAttribute('data-tk') || '');
      if (input) input.value = '';
      scrDropHide(drop);
    });
  });
}

function scrDropHide(drop) {
  drop.hidden = true;
  drop._items = null;
  scrState.activeIdx = -1;
}

function scrSetTicker(tk) {
  tk = String(tk || '').trim().toUpperCase();
  // Same B3 shape the server validates — anything from the dropdown or
  // free typing must match before it reaches the API.
  if (!/^[A-Z0-9]{4,6}$/.test(tk) || tk === scrState.ticker) return;
  scrState.ticker = tk;
  scrSyncUrl();
  scrLoad();
}

window.scrClear = function() {
  scrState.ticker = '';
  scrSyncUrl();
  scrShowEmpty();
  scrFocusPicker();
};

function scrSyncUrl() {
  // Only THIS tool's ?s= key is rewritten — the comparison's ?t= deep
  // link (and anything else) survives.
  try {
    var url = new URL(window.location.href);
    if (scrState.ticker) {
      url.searchParams.set('s', scrState.ticker);
    } else {
      url.searchParams.delete('s');
    }
    window.history.replaceState('', '', url.pathname + url.search);
  } catch (e) { /* noop */ }
}

function scrShowEmpty() {
  var box = document.getElementById('scr-result');
  if (!box) return;
  destroyChartsIn(box);
  scrState.data = null;
  box.innerHTML =
    '<div class="cmp-empty">' +
    '<div class="cmp-empty-icon">🎯</div>' +
    '<p class="cmp-empty-title">Escolha um ticker para peneirar o setor</p>' +
    '<p class="cmp-empty-hint">Informe o ticker acima. O screener encontra ' +
    'todas as empresas do setor, calcula as medianas (P/L, P/VPA, EV/EBITDA, ' +
    'ROE, Div Yield…) e mostra onde a empresa está: mais barata ou mais cara ' +
    'que o setor, melhor ou pior em rentabilidade, margens e dividendos — ' +
    'uma linha por métrica com o veredito.</p></div>';
}

// [v1.28.2] STALE-RESPONSE GUARD + CANCELAR — the screener's first pass
// runs minutes; switching tickers mid-flight used to let ticker A's late
// answer overwrite B's cached screen (and kill B's elapsed timer). Every
// load takes a ticket (scrReqSeq); a response only touches the pane while
// it still holds the LATEST ticket. scrAbort also kills the superseded
// request's socket — Cancelar uses the same lever on purpose.
var scrReqSeq = 0;
var scrAbort = null;

function scrLoad() {
  var box = document.getElementById('scr-result');
  if (!box) return;
  var seq = ++scrReqSeq;
  if (scrAbort) { try { scrAbort.abort(); } catch (e) { /* noop */ } }
  var ac = (typeof AbortController !== 'undefined') ? new AbortController() : null;
  scrAbort = ac;
  destroyChartsIn(box);
  scrState.data = null;
  // [v1.28.1] the shared loading card — the first pass on a big sector
  // computes EVERY company and can take minutes (a real POMO4 run took
  // 123s); the elapsed counter + the "why" hint keep the wait legible
  // (the ask: "while its loading it should display some message to say
  // its carregando"). [v1.28.2] the card now carries a Cancelar button.
  box.innerHTML = toolLoadingHtml('scr-load',
    'Peneirando ' + esc(scrState.ticker) + ' contra o setor',
    'Cada empresa do setor é calculada na primeira vez — em setores ' +
    'grandes a primeira análise pode levar alguns minutos. As próximas ' +
    'visitas ficam pré-calculadas (⚡).', 'scrCancel()');
  toolLoadingStart('scr-load');
  fetch('/api/webui/tools/screener?ticker=' +
        encodeURIComponent(scrState.ticker) +
        '&_t=' + Date.now(), ac ? { signal: ac.signal } : undefined)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (seq !== scrReqSeq) return;  // superseded — a newer ticker owns the pane
      if (scrAbort === ac) scrAbort = null;
      toolLoadingStop('scr-load');
      if (!data || data.status !== 'ok') {
        box.innerHTML = '<div class="error">' +
          esc((data && data.error) || 'falha no screener') + '</div>' +
          '<p class="scr-back"><button type="button" class="cmp-range-btn" ' +
          'onclick="scrClear()">← escolher outro ticker</button></p>';
        return;
      }
      scrState.data = data;
      scrRender(box, data);
    })
    .catch(function(err) {
      if (seq !== scrReqSeq) return;  // superseded / canceled — stay quiet
      if (scrAbort === ac) scrAbort = null;
      toolLoadingStop('scr-load');
      if (ac && err && err.name === 'AbortError') return;  // Cancelar owns the UI
      box.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>' +
        '<p class="scr-back"><button type="button" class="cmp-range-btn" ' +
        'onclick="scrClear()">← escolher outro ticker</button></p>';
    });
}

// [v1.28.2] Cancelar — kills the WAIT, not the work: the fetch aborts
// and the pane rests, while the server finishes the sector build and
// caches it (the retry picks up the ⚡ payload when it's ready).
window.scrCancel = function() {
  scrReqSeq++;  // the in-flight answer, if any, is stale from this moment
  if (scrAbort) { try { scrAbort.abort(); } catch (e) { /* noop */ } scrAbort = null; }
  toolLoadingStop('scr-load');
  var box = document.getElementById('scr-result');
  if (!box) return;
  destroyChartsIn(box);
  box.innerHTML =
    '<div class="cmp-empty">' +
    '<p class="cmp-empty-title">Análise cancelada.</p>' +
    '<p class="cmp-empty-hint">O servidor continua calculando o setor em ' +
    'segundo plano — quando terminar, a análise de ' + esc(scrState.ticker) +
    ' sai pré-calculada (⚡).</p>' +
    '<p class="scr-back"><button type="button" class="cmp-range-btn" ' +
    'onclick="scrRetry()">analisar ' + esc(scrState.ticker) + ' novamente</button> ' +
    '<button type="button" class="cmp-range-btn" ' +
    'onclick="scrClear()">← escolher outro ticker</button></p></div>';
};

window.scrRetry = function() { scrLoad(); };

function scrRender(box, data) {
  var html = scrHeadHtml(data);
  html += scrKpisHtml(data);
  html += scrHistHtml(data);
  html += scrTableHtml(data);
  html += scrChartsHtml(data);
  html += scrVsHtml(data);
  if (data.cache_note) {
    html += '<p class="fin-cache-note"><span class="fin-cache-bolt">⚡</span> ' +
      esc(data.cache_note) + '</p>';
  }
  if (data.errors && data.errors.length) {
    html += '<p class="cmp-errors">⚠️ ' + esc(data.errors.join(' · ')) + '</p>';
  }
  box.innerHTML = html;
  scrMountCharts(box, data);
}

// ── the subject header ──

function scrHeadHtml(data) {
  var varHtml = (data.var_day === null || data.var_day === undefined)
    ? '' : ' <span class="cmp-co-var">' + fmtPctColored(data.var_day) + '</span>';
  return '<div class="scr-head">' +
    '<div class="scr-head-main">' +
    '<div class="scr-head-tk">' + esc(data.ticker) + '</div>' +
    '<div class="scr-head-name" title="' + esc(data.name || data.ticker) + '">' +
    esc(data.name || data.ticker) + '</div>' +
    (data.sector ? '<div class="scr-head-sector">' + esc(data.sector) +
     ' · ' + data.company_count + ' empresa' + (data.company_count > 1 ? 's' : '') +
     '</div>' : '') +
    '</div>' +
    '<div class="scr-head-side">' +
    '<div class="scr-head-price">' + fmtBRL(data.price) + varHtml + '</div>' +
    (data.price_date ? '<div class="scr-head-date">' + esc(data.price_date) + '</div>' : '') +
    '<button type="button" class="cmp-range-btn scr-head-x" title="Escolher outro ticker"' +
    ' onclick="scrClear()">trocar ticker</button>' +
    '</div></div>';
}

// ── the sector-median KPI row (plain values — no pos/neg coloring:
// a median is a reference, not a good/bad number) ──

function scrKpisHtml(data) {
  var html = '<div class="kpi-grid scr-kpis">';
  (data.kpis || []).forEach(function(k) {
    html += '<div class="kpi-card">' +
      '<div class="kpi-label">' + esc(k.label) + '</div>' +
      '<div class="kpi-value">' + esc(k.value) + '</div></div>';
  });
  return html + '</div>';
}

// ── the Cotação Histórica card (the comparison range machinery,
//    subject only) ──

function scrHistHtml(data) {
  return '<div class="cmp-chartcard scr-hist-card">' +
    '<div class="cmp-chart-head"><div class="cmp-chart-title">Cotação Histórica — ' +
    esc(data.ticker) + '</div>' +
    '<div class="cmp-range-bar" role="group" aria-label="Período da cotação">' +
    cmpRangeBarHtml(scrState.histRange, 'scrHistRange') + '</div></div>' +
    '<p class="cmp-chart-desc">Fechamentos no período selecionado — mensais ' +
    'nos períodos longos, diários nos curtos.</p>' +
    '<div class="scr-hist-chart"><canvas id="scr-hist"></canvas>' +
    '<div class="cmp-hist-none" id="scr-hist-none" hidden>sem cotações no período</div></div>' +
    '</div>';
}

window.scrHistRange = function(btn) {
  var bar = btn.parentNode;
  Array.prototype.forEach.call(bar.querySelectorAll('.cmp-range-btn'), function(b) {
    b.classList.remove('active');
  });
  btn.classList.add('active');
  scrState.histRange = btn.getAttribute('data-range') || '1A';
  scrMountHist();
};

function scrMountHist() {
  var data = scrState.data;
  if (!data || !data.price_hist) return;
  var canvas = document.getElementById('scr-hist');
  if (!canvas) return;
  var noneEl = document.getElementById('scr-hist-none');
  var daily = cmpRangeDaily(scrState.histRange);
  var src = (data.price_hist[daily ? 'daily' : 'monthly'] || {})[data.ticker] || [];
  var cutoff = cmpRangeCutoff(scrState.histRange, daily);
  var pts = cmpWindow(src, cutoff);
  destroyChartsIn(canvas);
  // [v1.28.1] the period-% chip is GONE ("there is some % number on each
  // chart bottom left corner… not really needed") — just the line.
  if (pts.length < 2) {
    // nothing to draw — say so, don't show a void (the v1.21 fix 3
    // lesson: an inline display beats the hidden attribute).
    canvas.hidden = true;
    canvas.style.display = 'none';
    if (noneEl) noneEl.hidden = false;
    return;
  }
  canvas.hidden = false;
  canvas.style.display = '';
  if (noneEl) noneEl.hidden = true;
  renderValChart(canvas, {
    type: 'line',
    data: {
      labels: pts.map(function(p) { return String(p.date); }),
      datasets: [{
        label: data.ticker,
        data: pts.map(function(p) { return p.close; }),
        borderColor: '#0d9488',
        backgroundColor: '#0d948822',
        fill: true, pointRadius: 0, pointHitRadius: 6
      }]
    },
    options: { scales: { y: { title: { text: 'R$' } } } }
  });
}

// ── the sector table (one class per company, P/L cheapest-first) ──
//
// [v1.28.1] SORTABLE + RANKED, the user's two asks: "not possible to
// sort the info on headers" and "doesnt display with green V and
// background the best one for each type like comparison". Every header
// is a sort button (click → toggle asc/desc; the active column carries
// ▲/▼; missing values always last), and every metric column paints the
// best value green with ✓ — the comparison grid's convention, applied
// per COLUMN here: multiples and the share price rank min (cheapest),
// everything else ranks max. The *_raw numbers the payload now ships
// drive both (no PT-BR string re-parsing); ties share the ✓, and a
// column needs 2+ eligible values to rank at all (a lone value can't
// win a comparison — the comparison grid rule).

var SCR_COLS = [
  { key: 'price',       raw: 'price_raw',       label: 'Preço',       dir: 'min' },
  { key: 'market_cap',  raw: 'mktcap_raw',      label: 'Market Cap',  dir: 'max' },
  { key: 'p_l',         raw: 'p_l_raw',         label: 'P/L',         dir: 'min', pos: true },
  { key: 'p_vpa',       raw: 'p_vpa_raw',       label: 'P/VPA',       dir: 'min', pos: true },
  { key: 'ev_ebitda',   raw: 'ev_ebitda_raw',   label: 'EV/EBITDA',   dir: 'min', pos: true },
  { key: 'roe',         raw: 'roe_raw',         label: 'ROE',         dir: 'max' },
  { key: 'dy',          raw: 'dy_raw',          label: 'Div Yield',   dir: 'max' },
  { key: 'receita',     raw: 'receita_raw',     label: 'Receita Líq.', dir: 'max', fin: true },
  { key: 'ebitda',      raw: 'ebitda_raw',      label: 'EBITDA',      dir: 'max', fin: true },
  { key: 'marg_ebitda', raw: 'marg_ebitda_raw', label: 'Marg. EBITDA', dir: 'max' },
  { key: 'cresc',       raw: 'cresc_raw',       label: 'Cresc. Rec.', dir: 'max' }
];

function _scrCol(key) {
  var col = null;
  SCR_COLS.forEach(function(c) { if (c.key === key) col = c; });
  return col;
}

function _scrSortTh(key, label, extraCls) {
  var active = scrState.sortKey === key;
  return '<th class="scr-sortable' + (extraCls ? ' ' + extraCls : '') +
    (active ? ' is-active' : '') + '" data-scrsort="' + esc(key) +
    '" scope="col" title="ordenar por ' + esc(label) + '">' + esc(label) +
    '<span class="scr-sort-ind" aria-hidden="true">' +
    (active ? (scrState.sortDir === 'asc' ? '▲' : '▼') : '↕') + '</span></th>';
}

function scrSortedRows(data) {
  var rows = (data.table || []).slice();
  var key = scrState.sortKey;
  var col = _scrCol(key);
  var dir = scrState.sortDir === 'desc' ? -1 : 1;
  var num = function(r) {
    var v = col ? r[col.raw] : null;
    if (v === null || v === undefined || isNaN(Number(v))) return null;
    return Number(v);
  };
  rows.sort(function(a, b) {
    // [v1.28.2] text sorts: explicit pt-BR collation (deterministic
    // across browsers/locales), and on the segmento column the missing
    // values ('' → rendered '—') go LAST like every numeric column —
    // '' used to win ascending, putting the least-informative rows on
    // top of the table.
    if (key === 'ticker') return dir * String(a.ticker).localeCompare(String(b.ticker), 'pt-BR');
    if (key === 'segmento') {
      var sa = String(a.segmento || '').trim();
      var sb = String(b.segmento || '').trim();
      if (!sa && !sb) return 0;
      if (!sa) return 1;   // missing always last
      if (!sb) return -1;
      return dir * sa.localeCompare(sb, 'pt-BR');
    }
    var na = num(a), nb = num(b);
    if (na === null && nb === null) return 0;
    if (na === null) return 1;    // missing values always last
    if (nb === null) return -1;
    return dir * (na - nb);
  });
  return rows;
}

// best value per metric column → {colKey: [row indexes]} (ties share it)
function _scrBestMap(rows) {
  var best = {};
  SCR_COLS.forEach(function(col) {
    var eligible = [];
    rows.forEach(function(r, i) {
      var v = r[col.raw];
      if (v === null || v === undefined || isNaN(Number(v))) return;
      var n = Number(v);
      if (col.pos && n <= 0) return;  // a negative P/L is a loss, not a bargain
      eligible.push([i, n]);
    });
    if (eligible.length < 2) return;
    var target = eligible[0][1];
    eligible.forEach(function(e) {
      if (col.dir === 'min' ? e[1] < target : e[1] > target) target = e[1];
    });
    eligible.forEach(function(e) {
      if (e[1] === target) (best[col.key] = best[col.key] || []).push(e[0]);
    });
  });
  return best;
}

function _scrCell(r, i, best, key, extraCls) {
  var isBest = !!(best[key] && best[key].indexOf(i) >= 0);
  // [v1.28.3] The Preço column (the row's MAIN price) wears the
  // band pill (server-computed price_pill); every multiple stays plain.
  var inner = (key === 'price' && r.price_pill)
    ? homePricePill(r.price_pill, r[key])
    : esc(r[key]);
  return '<td class="' + (extraCls ? extraCls + ' ' : '') + 'scr-cell' +
    (isBest ? ' scr-best' : '') + '">' + inner +
    (isBest ? ' <span class="cmp-bestbadge" title="melhor da coluna">✓</span>' : '') +
    '</td>';
}

function scrTableInnerHtml(data) {
  var rows = scrSortedRows(data);
  var best = _scrBestMap(rows);
  var html = '<div class="cmp-chart-head"><div class="cmp-chart-title">Empresas do Setor' +
    (data.sector ? ' — ' + esc(data.sector) : '') + '</div></div>' +
    '<p class="cmp-chart-desc">Todas as companhias do setor na Bridge (uma ' +
    'classe de ação por empresa — a mais líquida). Clique nos títulos para ' +
    'ordenar; ✓ marca o melhor valor de cada coluna. A linha destacada é a ' +
    'empresa analisada.</p>' +
    '<div class="scr-tablewrap"><table class="scr-table"><thead><tr>' +
    _scrSortTh('ticker', 'Empresa') +
    _scrSortTh('price', 'Preço') +
    _scrSortTh('market_cap', 'Market Cap') +
    _scrSortTh('p_l', 'P/L') +
    _scrSortTh('p_vpa', 'P/VPA') +
    _scrSortTh('ev_ebitda', 'EV/EBITDA') +
    _scrSortTh('roe', 'ROE') +
    _scrSortTh('dy', 'Div Yield') +
    _scrSortTh('receita', 'Receita Líq.', 'scr-col-fin') +
    _scrSortTh('ebitda', 'EBITDA', 'scr-col-fin') +
    _scrSortTh('marg_ebitda', 'Marg. EBITDA') +
    _scrSortTh('cresc', 'Cresc. Rec.') +
    _scrSortTh('segmento', 'Segmento', 'scr-col-seg') +
    '</tr></thead><tbody>';
  rows.forEach(function(r, i) {
    var cls = r.is_subject ? ' class="scr-subject"' : '';
    var star = r.is_subject ? ' <span class="scr-star" title="empresa analisada">★</span>' : '';
    var warn = r.partial
      ? ' <span class="scr-partial" title="algumas fontes desta empresa falharam — indicadores parciais">⚠</span>'
      : '';
    html += '<tr' + cls + '>' +
      '<th scope="row"><a class="scr-tk" href="/webui/company/' +
      encodeURIComponent(r.ticker) + '">' + esc(r.ticker) + '</a>' + star + warn +
      '<span class="scr-name" title="' + esc(r.name || '') + '">' + esc(r.name || '') + '</span></th>' +
      _scrCell(r, i, best, 'price') +
      _scrCell(r, i, best, 'market_cap') +
      _scrCell(r, i, best, 'p_l') +
      _scrCell(r, i, best, 'p_vpa') +
      _scrCell(r, i, best, 'ev_ebitda') +
      _scrCell(r, i, best, 'roe') +
      _scrCell(r, i, best, 'dy') +
      _scrCell(r, i, best, 'receita', 'scr-col-fin') +
      _scrCell(r, i, best, 'ebitda', 'scr-col-fin') +
      _scrCell(r, i, best, 'marg_ebitda') +
      _scrCell(r, i, best, 'cresc') +
      '<td class="scr-col-seg">' + esc(r.segmento || '—') + '</td>' +
      '</tr>';
  });
  html += '</tbody></table></div>';
  return html;
}

function scrTableHtml(data) {
  // The card carries its own id — scrSortBy re-renders JUST this card
  // (charts and the rest of the screen stay mounted).
  return '<div class="cmp-chartcard" id="scr-table-card">' +
    scrTableInnerHtml(data) + '</div>';
}

function scrSortBy(key) {
  if (!key || !scrState.data) return;
  if (scrState.sortKey === key) {
    scrState.sortDir = scrState.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    scrState.sortKey = key;
    // natural first direction: cheapest-first on min columns,
    // highest-first on max columns, A→Z on the text ones
    var col = _scrCol(key);
    scrState.sortDir = (col && col.dir === 'max') ? 'desc' : 'asc';
  }
  var card = document.getElementById('scr-table-card');
  if (card) card.innerHTML = scrTableInnerHtml(scrState.data);
}

// ── the position charts (server configs) ──

function scrChartsHtml(data) {
  var html = '<div class="cmp-chartgrid">';
  (data.charts || []).forEach(function(ch) {
    if (ch.id === 'vs_mediana') return;  // rendered after the verdict table
    html += '<div class="cmp-chartcard">' +
      '<div class="cmp-chart-head"><div class="cmp-chart-title">' + esc(ch.title) + '</div></div>' +
      (ch.desc ? '<p class="cmp-chart-desc">' + esc(ch.desc) + '</p>' : '') +
      '<div class="chart-container"><canvas id="scr-chart-' + esc(ch.id) + '"></canvas></div>' +
      '</div>';
  });
  html += '</div>';
  return html;
}

// ── the Meu Valor × Mediana verdict table ──

var SCR_VERDICTS = {
  cheap:     { txt: 'barata',   cls: 'good', title: 'abaixo da mediana do setor (menor é melhor)' },
  expensive: { txt: 'cara',     cls: 'bad',  title: 'acima da mediana do setor' },
  above:     { txt: 'acima',    cls: 'good', title: 'acima da mediana do setor (maior é melhor)' },
  below:     { txt: 'abaixo',   cls: 'bad',  title: 'abaixo da mediana do setor' },
  na:        { txt: '—',        cls: 'na',   title: 'sem comparação possível (valor indisponível ou mediana sem dados)' }
};

// [v1.28.1] the heat tint — how FAR from the median, in which DIRECTION
// (the "add heat map like you did with others tabs" ask; the valuation
// overview heatmap's green/amber/red language, applied RELATIVE to the
// sector median instead of absolute thresholds). [v1.28.2] applied to
// BOTH the Meu Valor cell and the vs Setor verdict cell (the user's
// review: the heat belongs on the comparison column; the Meu Valor tint
// stays):
//   |delta| < 10%  → no tint (statistically at the median)
//   10-30% / 30-75% / 75%+ → 1 / 2 / 3 (the intensity steps)
//   favorable (cheap/above) → green; unfavorable (expensive/below) → red
function scrHeatCls(r) {
  if (!r || r.delta === null || r.delta === undefined) return '';
  if (r.verdict !== 'cheap' && r.verdict !== 'expensive' &&
      r.verdict !== 'above' && r.verdict !== 'below') return '';
  var fav = r.direction === 'above' ? r.delta > 0 : r.delta < 0;
  var mag = Math.abs(r.delta);
  var lvl = mag >= 0.75 ? 3 : mag >= 0.30 ? 2 : mag >= 0.10 ? 1 : 0;
  if (!lvl) return '';
  return 'scr-heat-' + (fav ? 'pos' : 'neg') + lvl;
}

function scrVsHtml(data) {
  var html = '<div class="cmp-chartcard">' +
    '<div class="cmp-chart-head"><div class="cmp-chart-title">Meu Valor × Mediana do Setor</div></div>' +
    '<p class="cmp-chart-desc">Cada métrica da empresa contra a mediana do ' +
    'setor. Múltiplos de valuation e alavancagem: menor que a mediana = ' +
    'barata. Qualidade (ROE, ROA, margens, Div Yield, crescimento): maior ' +
    'que a mediana = acima. Múltiplos negativos são prejuízo — ficam sem ' +
    'veredito. O fundo do Meu Valor e do vs Setor marca a distância da ' +
    'mediana: verde = favorável, vermelho = desfavorável — quanto mais ' +
    'forte, mais distante.</p>' +
    '<div class="scr-tablewrap"><table class="scr-table scr-vs-table"><thead><tr>' +
    '<th>Métrica</th><th>Meu Valor</th><th>Mediana do Setor</th><th>Delta</th><th>vs Setor</th>' +
    '</tr></thead><tbody>';
  (data.vs_rows || []).forEach(function(r) {
    var v = SCR_VERDICTS[r.verdict] || SCR_VERDICTS.na;
    var deltaCls = (r.verdict === 'cheap' || r.verdict === 'above') ? 'good'
      : (r.verdict === 'expensive' || r.verdict === 'below') ? 'bad' : 'na';
    html += '<tr><th scope="row" class="cmp-rowlabel" title="' + esc(r.tip || '') + '">' +
      esc(r.label) + (r.tip ? ' <span class="cmp-info" aria-hidden="true">ⓘ</span>' : '') + '</th>' +
      '<td class="scr-heat-cell ' + scrHeatCls(r) + '">' + esc(r.my_fmt) + '</td>' +
      '<td>' + esc(r.med_fmt) + '</td>' +
      '<td class="scr-delta-' + deltaCls + '">' + esc(r.delta_fmt) + '</td>' +
      // [v1.28.2] the heat tint rides the VERDICT cell too (the user's
      // ask: the distance-to-median heat on the vs Setor column, keeping
      // the Meu Valor tint) — same bands, same colors, so the whole row
      // reads at one glance: how far (intensity) and which way (green/
      // red), with the badge spelling the verdict out.
      '<td class="scr-heat-cell ' + scrHeatCls(r) + '"><span class="scr-badge scr-badge-' + v.cls + '" title="' + esc(v.title) + '">' +
      esc(v.txt) + '</span></td></tr>';
  });
  html += '</tbody></table></div></div>';

  // the vs-median grouped bars close the page (its own card, full width).
  (data.charts || []).forEach(function(ch) {
    if (ch.id !== 'vs_mediana') return;
    html += '<div class="cmp-chartcard">' +
      '<div class="cmp-chart-head"><div class="cmp-chart-title">' + esc(ch.title) + '</div></div>' +
      (ch.desc ? '<p class="cmp-chart-desc">' + esc(ch.desc) + '</p>' : '') +
      '<div class="chart-container"><canvas id="scr-chart-' + esc(ch.id) + '"></canvas></div>' +
      '</div>';
  });
  return html;
}

function scrMountCharts(box, data) {
  (data.charts || []).forEach(function(ch) {
    var canvas = document.getElementById('scr-chart-' + ch.id);
    if (canvas) renderValChart(canvas, ch.cd);
  });
  scrMountHist();
}

// ── Painel (landing page) [WebUI v1.19] ─────────────────────────────
// The dashboard's own loader — NOT the generic subtab recipe: the landing
// page is a launcher, not a report. GET /api/webui/home returns the KPI row
// (rendered through the SHARED valKpisHtml — same cards as every other
// page) + 5 ranked ticker CARDS whose rows are <a> links into the company
// pages (ticker · name · value · colored variation · context extra).
// Server ships pre-formatted PT-BR strings; the client only colorizes
// (leading '+' → val-pos, '-' → val-neg — the variation contract carries
// the sign explicitly, null → '—').
//
// [v1.19 fix 1] SINGLE-FLIGHT: the old guard set _loaded only AFTER the
// fetch resolved, so the direct boot + the sync-box/banner afterSettle
// triggers all passed the check while the first request was still in
// flight (3 concurrent /api/webui/home calls per page load) — and the 30s
// sync-box refresh kept firing new ones, so a slow snapshot compounded
// forever. The guard is keyed to the PANE ELEMENT (a fresh DOM node per
// page load — the sidebar is plain <a> navigation, so every load gets a
// new kpiBox): all triggers within one page see the same node and no-op,
// a re-entered pane (future soft swap) gets a fresh request. A failed
// fetch resets it so the next trigger can retry.
var _homeReq = null;
window.loadHomeData = function() {
  var kpiBox = document.getElementById('home-kpis');
  var tickersBox = document.getElementById('home-tickers');
  var cardsBox = document.getElementById('home-cards');
  if (!kpiBox && !tickersBox && !cardsBox) return;
  if (_homeReq && _homeReq.box === kpiBox) return;   // this pane: in flight or done
  var req = { box: kpiBox, done: false };
  _homeReq = req;
  fetch('/api/webui/home?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      req.done = true;
      renderHome(kpiBox, tickersBox, cardsBox, data);
    })
    .catch(function(err) {
      if (_homeReq === req) _homeReq = null;   // allow a later trigger to retry
      var msg = '<div class="error">Erro: ' + esc(err.message) + '</div>';
      if (kpiBox) kpiBox.innerHTML = msg;
      if (tickersBox) tickersBox.innerHTML = msg;
      if (cardsBox) cardsBox.innerHTML = msg;
    });
};

// [v1.28.3] The price pill — the Ações family's 22-range palette
// (server-computed {pill, text, range}; the palette lives in Python —
// skills/_colors/price.py, the acoes.py precedent — the client only
// renders). Solid band chip in the Insiders cargo/tipo pill shape:
// rounded, bold, mono, the range label in the tooltip.
function homePricePill(price, value, cls) {
  if (!price) return valEsc(value);
  return '<span class="home-price-pill' + (cls || '') + '" style="background:' +
    safeColor(price.pill) + ';color:' + safeColor(price.text) +
    '" title="Faixa de preço (Ações): ' + valEsc(price.range) + '">' +
    valEsc(value) + '</span>';
}

function homeTickerRow(item) {
  var v = item.variation;
  var vHtml;
  if (v === null || v === undefined) {
    vHtml = '<span class="muted">—</span>';
  } else {
    var cls = v.charAt(0) === '-' ? 'val-neg'
            : (v.charAt(0) === '+' ? 'val-pos' : 'val-zero');
    vHtml = '<span class="' + cls + '">' + valEsc(v) + '</span>';
  }
  // [v1.28.3] The STANDARDIZED row — "ticker - that extra info -
  // price - %" (the user's ask): the SECOND slot carries the card's
  // context (peso / negócios / volume — the label in the tooltip) and
  // falls back to the NAME for the cards with no extra (altas/baixas
  // and the BDR twins — "volume or peso or negocios or name"). The
  // PRICE is always the main value and always wears the palette pill
  // (the volumes card included — its cotação IS the main price now,
  // the volume rides the info slot).
  var valHtml = homePricePill(item.price, item.value);
  var infoHtml;
  if (item.extra) {
    infoHtml = item.extra.price
      ? homePricePill(item.extra.price, item.extra.text, ' home-price-pill-xs')
      : valEsc(item.extra.text);
  } else {
    infoHtml = '<span class="tk-name" title="' + valEsc(item.name) + '">' +
      valEsc(item.name) + '</span>';
  }
  // [v1.28.3] The extra's tooltip carries the VALUE ("the tooltip
  // should be Volume - Value") — exactly "volume — R$ 1,87 bi", no
  // company name: the info slot ellipsizes, so the tooltip is the one
  // place the whole volume reads.
  var infoTip = item.extra
    ? (valEsc(item.extra.label || '') + ' — ' + valEsc(item.extra.text || ''))
    : valEsc(item.name);
  return '<a class="ticker-row" href="/webui/company/' +
         encodeURIComponent(item.ticker) + '" title="' + infoTip + '">' +
    '<span class="tk">' + valEsc(item.ticker) + '</span>' +
    '<span class="tk-info" title="' + infoTip + '">' + infoHtml + '</span>' +
    '<span class="tk-val">' + valHtml + '</span>' +
    '<span class="tk-var">' + vHtml + '</span>' +
    '</a>';
}

function homeCard(card) {
  var h = '<div class="home-card">';
  h += '<div class="home-card-head"><div class="home-card-title">' +
       valEsc(card.title) + '</div>';
  if (card.subtitle) {
    h += '<div class="home-card-sub">' + valEsc(card.subtitle) + '</div>';
  }
  h += '</div>';
  if (card.error) {
    h += '<div class="home-card-error">' + valEsc(card.error) + '</div>';
  } else if (card.items && card.items.length) {
    h += card.items.map(homeTickerRow).join('');
  } else {
    h += '<div class="muted home-card-empty">Sem dados</div>';
  }
  return h + '</div>';
}

// [v1.28.3] The ticker card's CHART — the middle band: an inline SVG
// of the 52-week close series (server-shipped, ≤40 points), stretched
// to the FULL card width (preserveAspectRatio="none" +
// vector-effect keeps the stroke uniform), a soft green fill under
// the line (the mockup's tinted chart) and a DASHED REFERENCE LINE
// marking the last close ("the chart has a line in the value instead
// of displaying the value over the chart") — the price itself lives
// in the header band's pill; the line only shows WHERE it sits on the
// series, painted with the price-band palette so pill + reference
// line + the position bar under the chart read as one scheme.
function homeSparkHtml(spark, price) {
  if (!spark || spark.length < 2) {
    // No series (unsynced window / degraded symbol) — the empty state
    // keeps the middle band's height so the card doesn't collapse.
    return '<div class="home-tk-spark is-empty" title="Série de 52 semanas indisponível">' +
      '<span class="muted">—</span></div>';
  }
  var W = 100, H = 40, PAD = 3;
  var lo = Math.min.apply(null, spark);
  var hi = Math.max.apply(null, spark);
  var span = (hi - lo) || 1;
  var n = spark.length;
  var pts = [];
  for (var i = 0; i < n; i++) {
    var x = n > 1 ? (i / (n - 1)) * W : 0;
    var y = PAD + (1 - (spark[i] - lo) / span) * (H - 2 * PAD);
    pts.push(x.toFixed(2) + ',' + y.toFixed(2));
  }
  var lastY = parseFloat(pts[n - 1].split(',')[1]);
  // The soft area under the line (down to the chart's floor).
  var area = '0,' + H + ' ' + pts.join(' ') + ' ' + W + ',' + H;
  // The value's reference line — dashed, in the band color when the
  // palette knows the price (plain neutral gray when it doesn't).
  var refStyle = price
    ? ' style="stroke:' + safeColor(price.pill) + '"'
    : '';
  return '<div class="home-tk-spark" title="Fechamentos das últimas 52 semanas — a linha tracejada marca o último fechamento">' +
    '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" ' +
      'aria-hidden="true" focusable="false">' +
      '<polygon class="home-tk-spark-area" points="' + area + '"/>' +
      '<line class="home-tk-spark-ref" x1="0" x2="' + W + '" y1="' +
        lastY.toFixed(2) + '" y2="' + lastY.toFixed(2) + '"' +
        ' vector-effect="non-scaling-stroke"' + refStyle + '/>' +
      '<polyline class="home-tk-spark-line" points="' + pts.join(' ') + '"' +
        ' vector-effect="non-scaling-stroke"/>' +
    '</svg></div>';
}

function homeTickerCard(tc) {
  // [v1.28.3] The ticker KPI card reads in THREE HORIZONTAL BANDS
  // (the user's mockup, top → bottom): the HEADER — ticker + badge +
  // name on the left, the price PILL and the day % right-aligned;
  // the CHART — the green 52-week line across the FULL card width
  // with the value's dashed reference line, the 52-week POSITION bar
  // under it ("keep that progression bar under the chart with posição
  // do range de 52 semanas"); the STATS — Mín 52 sem (first), Máx 52
  // sem, Volume (dia), label left / value right. ANY share-like
  // instrument (home.ticker_kpis: ações, FIIs, ETFs, BDRs). The whole
  // card links to the company page — the landing page is a launcher.
  var v = tc.variation;
  var cls = v === null || v === undefined ? 'val-zero'
    : (v.charAt(0) === '-' ? 'val-neg' : (v.charAt(0) === '+' ? 'val-pos' : 'val-zero'));
  var priceHtml = tc.price
    ? homePricePill(tc.price, tc.value, ' home-price-pill-lg')
    : '<span class="home-tk-price">' + valEsc(tc.value) + '</span>';
  // The 52-week position bar — fill width = pos_52%, the fill painted
  // with the price band color (the scheme reads as one: pill + line +
  // bar).
  var barHtml = '';
  if (tc.pos_52 !== null && tc.pos_52 !== undefined && tc.price) {
    barHtml = '<div class="home-tk-bar" title="Posição no range de 52 semanas: ' +
      tc.pos_52 + '%">' +
      '<div class="home-tk-bar-fill" style="width:' + Math.max(2, Math.min(100, tc.pos_52)) +
      '%;background:' + safeColor(tc.price.pill) + '"></div></div>';
  } else {
    barHtml = '<div class="home-tk-bar is-empty" title="Range de 52 semanas indisponível">' +
      '</div>';
  }
  return '<a class="home-card home-tk-card" href="/webui/company/' +
    encodeURIComponent(tc.ticker) + '" title="' + valEsc(tc.tooltip || '') + '">' +
    '<div class="home-tk-stack">' +
      '<div class="home-tk-head">' +
        '<div class="home-tk-head-id">' +
          '<div class="home-tk-tkline">' + valEsc(tc.ticker) +
            (tc.kind ? '<span class="home-tk-kind">' + valEsc(tc.kind) + '</span>' : '') +
          '</div>' +
          (tc.name ? '<div class="home-tk-name" title="' + valEsc(tc.name) + '">' +
            valEsc(tc.name) + '</div>' : '<div class="home-tk-name">&nbsp;</div>') +
        '</div>' +
        '<div class="home-tk-head-quote">' +
          '<div class="home-tk-quote">' + priceHtml + '</div>' +
          '<div class="home-tk-var ' + cls + '">' +
            (v === null || v === undefined ? '—' : valEsc(v)) + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="home-tk-chart">' +
        homeSparkHtml(tc.spark, tc.price) +
        barHtml +
      '</div>' +
      '<div class="home-tk-meta">' +
        '<div class="home-tk-meta-row"><span>Mín 52 sem</span>' +
          '<span class="home-tk-rval">' +
          (tc.low_52 ? valEsc(tc.low_52) : '—') + '</span></div>' +
        '<div class="home-tk-meta-row"><span>Máx 52 sem</span>' +
          '<span class="home-tk-rval">' +
          (tc.high_52 ? valEsc(tc.high_52) : '—') + '</span></div>' +
        '<div class="home-tk-meta-row"><span>Volume (dia)</span>' +
          '<span class="home-tk-rval">' +
          (tc.volume ? valEsc(tc.volume) : '—') + '</span></div>' +
      '</div>' +
    '</div></a>';
}

function renderHome(kpiBox, tickersBox, cardsBox, data) {
  if (data._error) {
    var errMsg = '<div class="error">' + esc(data._error) + '</div>';
    if (kpiBox) kpiBox.innerHTML = errMsg;
    if (tickersBox) tickersBox.innerHTML = '';
    if (cardsBox) cardsBox.innerHTML = '';
    return;
  }
  // [v1.28.3] The payload stays on the window — the ⚙️ Gerenciar Painel
  // box reads card_catalog + kpi_catalog from it (no second fetch when
  // it's warm).
  window._homeData = data;
  if (kpiBox) {
    // [v1.28.3] The FIRST set — the macro KPI cards (home.kpis
    // order; small boxes, as they always were).
    kpiBox.innerHTML =
      (data.kpis && data.kpis.length ? valKpisHtml(data.kpis) : '') +
      (data.kpis_note
        ? '<div class="home-note">' + valEsc(data.kpis_note) + '</div>'
        : '');
  }
  if (tickersBox) {
    // [v1.28.3] The SECOND set — the ticker KPI cards in their
    // OWN grid (home.ticker_kpis order): ranking-card width, medium
    // length, richer than the v1.28.1 strips.
    tickersBox.innerHTML = (data.ticker_cards || []).map(homeTickerCard).join('');
  }
  if (cardsBox) {
    // [v1.28.3] The THIRD set — the ranking boxes at FULL size
    // (home.cards order), never stretched alongside the ticker cards.
    cardsBox.innerHTML = (data.cards || []).map(homeCard).join('');
  }
}

// ── Generic table click-sort [WebUI v1.8] ─────────────────────────────────
// Server table sections can carry `sortable: true` (extra key the contract
// ignores — same mechanism as pair_with_next). Those tables render their
// headers as .val-sortable buttons; ONE delegated listener reorders the
// tbody rows by the clicked column, parsing PT-BR formatted cells
// ("R$ 1.234,56" → 1234.56, "4,19%" → 4.19, compact BRL "R$ 4,27 bi" →
// 4.27e9, dates — ISO, dd/mm/yyyy, dd/mm/yy and BR month labels (jun/2026)
// — chronologically, tooltip ⓘ markers stripped, "-" always last).
// Benefits every tab that marks a table sortable, not just Opções.
function _valSortKey(cell) {
  var el = cell.querySelector ? cell : null;
  // [v1.10] First-column cells carry a tooltip ⓘ marker INSIDE the cell
  // ("03/11/2026 ⓘ") — strip it, or the anchored date regexes below never
  // match and dates fall back to lexicographic order (01/12/2026 sorting
  // before 05/01/2024 — not chronological). Affects every sortable table
  // whose first column has a tooltip.
  var text = (el ? el.textContent : String(cell)).replace(/\s*ⓘ/g, '').trim();
  if (!text || text === '-' || text === '—') return null;
  var m = String(text).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return {num: Date.parse(m[0]) / 1e13, str: m[0], isNum: true};
  // [v1.10] Month keys — "YYYY-MM" and BR month labels ("jun/2026") —
  // sorted chronologically (lexicographic would put "abr/2025" before
  // "dez/2024" and "2025-9" issues aside, keep it explicit).
  var ym = String(text).match(/^(\d{4})-(\d{2})$/);
  if (ym) return {num: (Number(ym[1]) * 12 + Number(ym[2])) / 1e5, str: text, isNum: true};
  var brm = String(text).match(/^(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\/(\d{4})$/i);
  if (brm) {
    var mi = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'].indexOf(brm[1].toLowerCase());
    return {num: (Number(brm[2]) * 12 + mi + 1) / 1e5, str: text, isNum: true};
  }
  // [v1.8 fix1] BR dates (tables render dd/mm/yyyy since the fix; the
  // maturity pills / heatmap headers use the 2-digit year). Reordered to
  // ISO so Date.parse sorts them chronologically — a plain string compare
  // would put "01/12/2026" before "05/01/2024" (day-first isn't sortable).
  var br = String(text).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (br) return {num: Date.parse(br[3] + '-' + br[2] + '-' + br[1]) / 1e13, str: text, isNum: true};
  var br2 = String(text).match(/^(\d{2})\/(\d{2})\/(\d{2})$/);
  if (br2) return {num: Date.parse('20' + br2[3] + '-' + br2[2] + '-' + br2[1]) / 1e13, str: text, isNum: true};
  // [v1.10] Compact BRL ("R$ 4,27 bi" / "R$ 225,94 mi" / "R$ 1.234 mil" /
  // "R$ -4,25 bi") — the suffix multiplies; a plain string compare would
  // put "R$ 1,39 bi" before "R$ 22,40 mi" and "R$ 133,50 mi" before
  // "R$ 75,00 mi". "mil" must alternate before "mi" or it never matches.
  var cb = String(text).match(/^R\$\s*(-?[\d.]+(?:,\d+)?)\s*(tri|bi|mil|mi)\s*$/i);
  if (cb) {
    var mult = {tri: 1e12, bi: 1e9, mil: 1e3, mi: 1e6}[cb[2].toLowerCase()];
    var cv = parseFloat(cb[1].replace(/\./g, '').replace(',', '.'));
    if (!isNaN(cv)) return {num: cv * mult, str: text, isNum: true};
  }
  var s = text.replace(/^R\$\s*/, '').replace(/%/g, '').replace(/\s/g, '');
  if (/^-?\d{1,3}(\.\d{3})+(,\d+)?$/.test(s)) s = s.replace(/\./g, '').replace(',', '.');
  else if (/^-?\d+,\d+$/.test(s)) s = s.replace(',', '.');
  else if (/^-?\d+(\.\d+)?$/.test(s)) { /* already plain */ }
  else return {str: text, isNum: false};
  var n = parseFloat(s);
  return isNaN(n) ? {str: text, isNum: false} : {num: n, str: text, isNum: true};
}

function initValTableSort() {
  document.body.addEventListener('click', function(e) {
    var th = e.target && e.target.closest
      ? e.target.closest('th.val-sortable') : null;
    if (!th) return;
    var table = th.closest('table');
    if (!table || !table.tBodies.length) return;
    var col = Array.prototype.indexOf.call(th.parentNode.children, th);
    if (col < 0) return;
    var dir = (table.getAttribute('data-sort-col') === String(col) &&
               table.getAttribute('data-sort-dir') === 'asc') ? -1 : 1;
    table.setAttribute('data-sort-col', String(col));
    table.setAttribute('data-sort-dir', dir > 0 ? 'asc' : 'desc');
    var tbody = table.tBodies[0];
    var rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function(a, b) {
      var ka = _valSortKey(a.cells[col]);
      var kb = _valSortKey(b.cells[col]);
      if (ka === null && kb === null) return 0;
      if (ka === null) return 1;    // empties always last
      if (kb === null) return -1;
      if (ka.isNum && kb.isNum) return (ka.num - kb.num) * dir;
      return ka.str.localeCompare(kb.str, 'pt-BR') * dir;
    });
    rows.forEach(function(r) { tbody.appendChild(r); });
    Array.prototype.forEach.call(th.parentNode.children, function(h) {
      var base = h.textContent.replace(/\s*[▲▼]\s*$/, '');
      if (h === th) base += dir > 0 ? ' ▲' : ' ▼';
      h.textContent = base;
    });
  });
}

// ── Hover/focus prefetch for lazy subtabs [WebUI v1.5 fix1] ───────────────
// Subtab buttons carry data-lazy="<family>:<sub>" (preco/fin/val). Pointer
// intent (mouseover) or keyboard focus starts the fetch ~300ms before the
// click lands — the lazy model keeps its cold-start savings, the user
// stops seeing a "Carregando…" flash on every first click.
function prefetchSubtab(e) {
  var btn = e.target && e.target.closest ? e.target.closest('[data-lazy]') : null;
  if (!btn || btn._prefetched) return;
  btn._prefetched = true;
  var parts = (btn.getAttribute('data-lazy') || '').split(':');
  var fns = { preco: window.loadPrecoSubtab, fin: window.loadFinSubtab,
              val: window.loadValSubtab, prov: window.loadProvSubtab,
              opt: window.loadOptSubtab, sh: window.loadShSubtab,
              ins: window.loadInsSubtab, mac: window.loadMacroSubtab,
              foc: window.loadFocusSubtab, flx: window.loadFluxoSubtab,
              ind: window.loadIndicesSubtab, inf: window.loadInflacaoSubtab,
              jur: window.loadJurosSubtab, pou: window.loadPoupancaSubtab,
              aco: window.loadAcoesSubtab,
              div: window.loadDividendosSubtab,
              hist: window.loadHistSubtab,
              gov: window.loadGovSubtab };
  var fn = fns[parts[0]];
  if (fn && parts[1]) { try { fn(parts[1]); } catch (err) { /* noop */ } }
}

// ═════════════════════════════════════════════════════════════════════════
// ── Carteira (portfolio) [WebUI v1.21 fix 1] ────────────────────────────────
// The DRILL-DOWN rework — the page IS the hierarchy:
//   👥 Usuários   landing: user cards with the totals of THEIR accounts
//                (per-user sums only, never across users) + ✏️ 🗑️ ➕
//   👤 Usuário   account cards (ativos, transações, patrimônio, lucro)
//                + the user's consolidated KPI row + ⭐ ✏️ 🗑️ ➕
//   🏦 Conta     the KPI row + posições/transações tables scoped to
//                THIS account + ➕ Transação (always relative).
// Header actions are contextual (one create per level), every dialog is
// dead-center, the tx form is BR-standard (money fills from the cents —
// 3,6 5 → 3,65; dd/mm/aaaa dates), sells may short (🚨 tooltip), price
// R$ 0,00 is a bonificação (⚠️ tooltip), and position rows carry the
// quick ✅ buy / ❌ sell that pre-fills ticker + account + qty.
// loadPortfolioWidget() renders the Painel: ⭐ Tickers Observados (its
// OWN box, first) then 💼 Minhas Carteiras (contas grouped by user,
// per-user subtotals). Both no-op away from their pages.
// ═════════════════════════════════════════════════════════════════════════

function initCarteiraPage() {
  var root = document.getElementById('carteira-root');
  if (!root || root._booted) return;
  root._booted = true;

  var st = {
    users: [], accounts: [], watchlist: [], tickers: [],
    dir: null,          // GET /directory — users/user levels
    pos: null,          // GET /positions?scope=account:ID — account level
    level: readLevel(),
    view: 'positions',
    // [v1.22.3] the ledger's own page + filters (GET /txs) — the
    // positions payload ships only page-1 + the count.
    txRows: null, txPage: 1, txPages: 1, txTotal: 0,
    txFilters: { ticker: '', type: '', from: '', to: '', q: '' },
    editUser: null, editAccount: null, editTx: null,
    storeError: null,   // [v1.22] degraded-store banner (corrupt file)
    pendingNote: null,  // [v1.22] {text, until} — post-mutation warnings
    undoTimer: null,    // [v1.22.3] the undo toast's expiry timer
  };

  function $(id) { return document.getElementById(id); }

  // [v1.22.4] NEVER "Unexpected token 'I'": any non-JSON answer (a
  // proxy error page, a plain-text 500) becomes a friendly PT-BR
  // error the caller's catch can render — the fetch itself only
  // rejects on network failure.
  function api(method, path, body) {
    return fetch('/api/webui/portfolio' + path, {
      method: method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }).then(function(r) {
      return r.text().then(function(txt) {
        var j = null;
        try { j = JSON.parse(txt); } catch (e) { /* not JSON */ }
        if (j === null) {
          var msg = r.status === 500
            ? 'Erro interno do servidor (resposta não-JSON) — veja o log do sistema (📜).'
            : 'Resposta inválida do servidor (HTTP ' + r.status + ').';
          var err = new Error(msg);
          err.status = r.status;
          throw err;
        }
        return { ok: r.ok, j: j };
      });
    });
  }

  function fieldErrs(modal, j) {
    var errs = (j && j.errors) || {};
    modal.querySelectorAll('.cart-err').forEach(function(el) {
      var key = el.getAttribute('data-err');
      var msg = errs[key];
      el.hidden = !msg;
      el.textContent = msg || '';
    });
    return Object.keys(errs).length ? errs : null;
  }

  // ── level plumbing (👥 users → 👤 user → 🏦 account) ──────────────────
  // [v1.21 fix 2] Entering via the sidebar ALWAYS lands on 👥 Usuários —
  // the old localStorage scope restored the last-visited user/account on
  // every entry. The Painel's conta rows still deep-link: they set a
  // ONE-SHOT sessionStorage key right before navigating (consumed and
  // removed here, so a refresh after landing also goes to the users page).
  function readLevel() {
    var v = '';
    try {
      v = sessionStorage.getItem('webui_carteira_goto') || '';
      sessionStorage.removeItem('webui_carteira_goto');
    } catch (err) { /* storage disabled — plain users landing */ }
    if (v.indexOf('user:') === 0) return { kind: 'user', id: v.slice(5) };
    if (v.indexOf('account:') === 0) return { kind: 'account', id: v.slice(8) };
    return { kind: 'users' };
  }

  function goto(kind, id) {
    st.level = kind === 'users' ? { kind: 'users' }
             : { kind: kind, id: id };
    st.view = 'positions';
    st.txPage = 1;                     // [v1.22.3] ledger state resets
    st.txRows = null;
    st.txFilters = { ticker: '', type: '', from: '', to: '', q: '' };
    $('cart-level').innerHTML = '<span class="loading">⏳ Carregando…</span>';
    hideNote();
    loadLevel();
  }

  function reconcileLevel() {
    if (st.level.kind === 'users') return;
    var alive = st.level.kind === 'user'
      ? st.users.some(function(u) { return u.id === st.level.id; })
      : st.accounts.some(function(a) { return a.id === st.level.id; });
    if (!alive) {                    // deleted entity — back to L0, re-render
      st.level = { kind: 'users' };
      loadLevel();
    }
  }

  function scopeStr() {
    return st.level.kind === 'account' ? 'account:' + st.level.id
         : st.level.kind === 'user' ? 'user:' + st.level.id : 'all';
  }

  function userById(id) {
    return st.users.filter(function(u) { return u.id === id; })[0] || null;
  }

  function stAccount(id) {
    return st.accounts.filter(function(a) { return a.id === id; })[0] || null;
  }

  function dirUser(id) {
    return ((st.dir && st.dir.users) || [])
      .filter(function(u) { return u.id === id; })[0] || null;
  }

  // ── data loads ─────────────────────────────────────────────────────────
  function loadState() {
    return api('GET', '/state').then(function(res) {
      if (!res.ok || !res.j || res.j._error) return;
      st.users = res.j.users || [];
      st.accounts = res.j.accounts || [];
      st.watchlist = res.j.watchlist || [];
      st.tickers = res.j.tickers || [];
      st.storeError = res.j.store_error || null;   // [v1.22]
      reconcileLevel();
      renderActions();
      renderCrumbs();
      if ($('cart-manage-modal').open) renderManage();
      // [v1.22] The store banner must show even if the level payload
      // rendered first — showNote is idempotent per current state.
      showNote(st.level.kind === 'account' ? (st.pos || {}) : (st.dir || {}));
    });
  }

  function loadDirectory() {
    return api('GET', '/directory').then(function(res) {
      st.dir = res.ok ? res.j : { _error: (res.j && res.j._error) || 'Erro' };
      renderLevel();
    }).catch(function(err) {
      st.dir = { _error: 'Erro: ' + err.message };
      renderLevel();
    });
  }

  function loadPositions() {
    return api('GET', '/positions?scope=' + encodeURIComponent(scopeStr()))
      .then(function(res) {
        st.pos = res.ok ? res.j : { _error: (res.j && res.j._error) || 'Erro' };
        renderLevel();
      })
      .catch(function(err) {
        st.pos = { _error: 'Erro: ' + err.message };
        renderLevel();
      });
  }

  function loadLevel() {
    if (st.level.kind === 'account') loadPositions();
    else loadDirectory();
  }

  function reload() { loadState(); loadLevel(); }

  // ── notes ──────────────────────────────────────────────────────────────
  // [v1.22] Three layers: the degraded-store banner (sticky — it is a
  // MODE, cleared only by a healthy /state), post-mutation warnings
  // (time-boxed ~15s — they must survive the reload race) and the
  // quotes note. hideNote() keeps the store banner visible.
  function hideNote() {
    var n = $('cart-note');
    if (!n) return;
    if (st.storeError) {
      n.hidden = false;
      n.innerHTML = '🚨 ' + esc(st.storeError);
      return;
    }
    n.hidden = true;
    n.textContent = '';
  }

  function showNote(d) {
    var n = $('cart-note');
    if (!n) return;
    var bits = [];
    if (st.storeError) bits.push('🚨 ' + esc(st.storeError));
    if (st.pendingNote && Date.now() < st.pendingNote.until) {
      bits.push('⚠️ ' + esc(st.pendingNote.text));
    }
    if (d && d.quotes_note) bits.push(esc(d.quotes_note));
    if (bits.length) {
      n.hidden = false;
      n.innerHTML = bits.join('<br>');
    } else {
      hideNote();
    }
  }

  // ── header actions (contextual: one create per level) ─────────────────
  function renderActions() {
    var box = $('cart-actions');
    if (!box) return;
    var html = '';
    if (st.level.kind !== 'users') {
      html += '<button class="cart-btn" data-nav="users" ' +
              'title="Voltar para os usuários">👤 Usuários</button>';
    }
    if (st.level.kind === 'user') {
      html += '<button class="cart-btn" data-act="account" ' +
              'title="Nova conta para este usuário">🏦 Nova conta</button>';
    }
    if (st.level.kind === 'account') {
      html += '<button class="cart-btn primary" data-act="tx" ' +
              'title="Registrar transação nesta conta">➕ Transação</button>';
      // [v1.22.2] the onboarding killer feature at arm's reach: import
      // the broker PDF instead of typing each trade.
      html += '<button class="cart-btn" data-act="import" ' +
              'title="Importar nota de corretagem (PDF) nesta conta">📥 Importar nota</button>';
    }
    if (st.level.kind === 'users') {
      html += '<button class="cart-btn primary" data-act="user" ' +
              'title="Criar um usuário">➕ Novo usuário</button>';
    }
    html += '<button class="cart-btn" data-act="manage" ' +
            'title="⭐ Observados e 📇 cadastro de tickers">⚙️ Gerenciar</button>';
    html += '<button class="cart-btn ghost" data-act="reload" ' +
            'aria-label="Recarregar" title="Recarregar dados">🔄</button>';
    box.innerHTML = html;
  }

  // ── breadcrumb ─────────────────────────────────────────────────────────
  function renderCrumbs() {
    var box = $('cart-crumbs');
    if (!box) return;
    var html = '<span class="cart-crumb' +
      (st.level.kind === 'users' ? ' is-here' : '') + '" data-nav="users">👥 Usuários</span>';
    if (st.level.kind === 'user') {
      var u = userById(st.level.id);
      html += '<span class="cart-crumb-sep">›</span>' +
        '<span class="cart-crumb is-here" title="' + esc(u ? u.name : '') + '">👤 ' +
        esc(u ? u.name : '—') + '</span>';
    } else if (st.level.kind === 'account') {
      var a = stAccount(st.level.id);
      var au = a ? userById(a.user_id) : null;
      if (au) {
        html += '<span class="cart-crumb-sep">›</span>' +
          '<span class="cart-crumb" data-nav="user" data-id="' + esc(au.id) + '">👤 ' +
          esc(au.name) + '</span>';
      }
      html += '<span class="cart-crumb-sep">›</span>' +
        '<span class="cart-crumb is-here" title="' +
        esc((a && a.broker) || '') + '">🏦 ' + esc(a ? a.name : '—') + '</span>';
    }
    box.innerHTML = html;
    box.style.display = st.level.kind === 'users' ? 'none' : '';
  }

  // ── level dispatch ─────────────────────────────────────────────────────
  function renderLevel() {
    renderActions();
    renderCrumbs();
    if (st.level.kind === 'users') renderUsersPage();
    else if (st.level.kind === 'user') renderUserPage();
    else renderAccountPage();
  }

  // ── 👥 L0: the users landing (cards with their accounts' totals) ───────
  function renderUsersPage() {
    var box = $('cart-level');
    var d = st.dir || {};
    if (d._error) {
      box.innerHTML = '<div class="error">' + esc(d._error) + '</div>';
      return;
    }
    showNote(d);
    if (d.empty === 'no_users' || !(d.users || []).length) {
      hideNote();
      box.innerHTML = emptyGuide('no_users');
      return;
    }
    box.innerHTML = '<div class="cart-ucard-grid">' +
      d.users.map(userCard).join('') + '</div>';
  }

  function statCell(label, val, tooltip) {
    var v = (val === null || val === undefined || val === '')
      ? '<span class="muted">—</span>' : valNumHtml(val);
    return '<div class="cart-stat"' + (tooltip ? ' title="' + esc(tooltip) + '"' : '') + '>' +
      '<span class="cart-stat-l">' + esc(label) + '</span>' +
      '<span class="cart-stat-v">' + v + '</span></div>';
  }

  function userCard(u) {
    return '<div class="cart-ucard" data-user="' + esc(u.id) + '" role="button" tabindex="0">' +
      '<div class="cart-ucard-head">' +
        '<span class="cart-ucard-name" title="' + esc(u.name) + '">👤 ' + esc(u.name) + '</span>' +
        '<span class="cart-actions">' +
          '<button class="cart-icon-btn" data-eu="' + esc(u.id) + '" title="✏️ Editar usuário">✏️</button>' +
          '<button class="cart-icon-btn" data-du="' + esc(u.id) +
            '" title="🗑️ Excluir usuário (contas e transações junto)">🗑️</button>' +
        '</span></div>' +
      '<div class="cart-ucard-stats">' +
        statCell('Patrimônio', u.value, 'Soma das contas deste usuário ao último pregão com cotação') +
        statCell('Lucro não realizado', u.profit, 'Patrimônio − custo das posições abertas') +
        statCell('Lucro %', u.profit_pct, 'Lucro sobre o custo (PM)') +
      '</div>' +
      '<div class="cart-ucard-meta">🏦 ' + esc(String(u.account_count)) + ' conta(s) · 📋 ' +
        esc(String(u.asset_count)) + ' ativo(s) · 🧾 ' + esc(String(u.tx_count)) +
        ' transação(ões) · 💰 custo ' + esc(u.cost || '—') + '</div>' +
      '<div class="cart-ucard-open">Abrir contas →</div>' +
      '</div>';
  }

  // ── 👤 L1: inside a user (KPIs + account cards) ────────────────────────
  function renderUserPage() {
    var box = $('cart-level');
    var d = st.dir || {};
    if (d._error) {
      box.innerHTML = '<div class="error">' + esc(d._error) + '</div>';
      return;
    }
    var u = dirUser(st.level.id);
    if (!u) {                                   // deleted — back to L0
      st.level = { kind: 'users' };
      loadDirectory();
      return;
    }
    showNote(d);
    var kpis = [
      { label: 'Patrimônio', value: u.value,
        tooltip: 'Soma das contas deste usuário ao último pregão com cotação' },
      { label: 'Custo (PM)', value: u.cost,
        tooltip: 'Total original — quantidade × preço médio (taxas incluídas)' },
      { label: 'Lucro não realizado', value: u.profit,
        tooltip: 'Patrimônio − custo das posições abertas' },
      { label: 'Lucro %', value: u.profit_pct,
        tooltip: 'Lucro não realizado sobre o custo' },
      { label: 'Lucro realizado', value: u.realized,
        tooltip: 'Vendas já efetuadas: (preço de venda − PM) × quantidade − taxas' },
    ];
    var html = '<div class="cart-kpis">' + valKpisHtml(kpis) + '</div>';
    html += '<div class="cart-sec-head"><h3>🏦 Contas de ' + esc(u.name) + '</h3>' +
      '<button class="cart-btn primary" data-act="account">➕ Nova conta</button></div>';
    if (!(u.accounts || []).length) {
      html += emptyGuide('no_accounts');
    } else {
      html += '<div class="cart-ucard-grid">' + u.accounts.map(accountCard).join('') + '</div>';
    }
    // [v1.22.2] IR mês a mês — collapsed by default, lazy-loaded on
    // first open (the walk replays the user's whole history).
    html += '<details id="cart-ir" class="cart-ir">' +
      '<summary>🧾 IR — mês a mês (swing × day trade, estimativa)</summary>' +
      '<div id="cart-ir-body"><span class="loading">⏳ Carregando…</span></div></details>';
    box.innerHTML = html;
    var irBox = $('cart-ir');
    if (irBox) irBox.addEventListener('toggle', onIrToggle);
  }

  function onIrToggle() {
    var box = $('cart-ir');
    if (!box || !box.open) return;
    loadIR();
  }

  function loadIR() {
    var box = $('cart-ir-body');
    if (!box) return;
    api('GET', '/ir?scope=' + encodeURIComponent(scopeStr())).then(function(res) {
      if (res.ok && res.j && !res.j._error) renderIR(res.j);
      else box.innerHTML = '<div class="error">' +
        esc((res.j && res.j._error) || 'Erro ao carregar o IR.') + '</div>';
    }).catch(function(err) {
      box.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
    });
  }

  function renderIR(j) {
    var box = $('cart-ir-body');
    if (!box) return;
    var html = '';
    if (j.partial_account) {
      html += '<div class="cart-ir-partial">⚠️ Parcial — apenas a conta <b>' +
        esc(j.partial_account) + '</b>. O IR é por CPF: some todas as ' +
        'contas do usuário (veja o nível 👤 do usuário).</div>';
    }
    var any = false;
    (j.users || []).forEach(function(u) {
      if (!u.months.length) return;
      any = true;
      html += '<h4 class="cart-ir-user">👤 ' + esc(u.user_name || '—') + '</h4>';
      html += '<div class="cart-table-wrap"><table class="val-table cart-table cart-ir-table">' +
        '<thead><tr><th>Mês</th>' +
        '<th class="th-num" title="Valor bruto das compras do mês (informativo)">Compras</th>' +
        '<th class="th-num" title="Vendas fora de day trade — a base da isenção de R$ 20 mil">Vendas swing</th>' +
        '<th class="th-num" title="Resultado swing: vendas − custo médio − taxas">Result. swing</th>' +
        '<th class="th-num" title="Vendas casadas no mesmo dia (compra + venda)">Vendas day</th>' +
        '<th class="th-num" title="Resultado day trade do mês">Result. day</th>' +
        '<th class="th-num" title="IRRF estimado: 0,005% das vendas swing + 1% do resultado day">IRRF</th>' +
        '<th class="th-num" title="IR estimado a pagar (alíquota − IRRF)">IR a pagar</th>' +
        '<th title="Código DARF e vencimento (último dia útil do mês seguinte)">DARF · venc.</th>' +
        '</tr></thead><tbody>';
      u.months.forEach(function(m) {
        var irrfTotal = (m.irrf_s || 0) + (m.irrf_d || 0);
        var darf = (m.darfs || []).map(function(d) {
          return d.code + ' · R$ ' + d.value_br;
        }).join('<br>') || '<span class="muted">—</span>';
        html += '<tr>' +
          '<td><b>' + esc(m.month_br) + '</b>' +
            (m.in_progress ? ' ' + flagHtml('⏳', 'Mês em andamento — os números ainda mudam') : '') + '</td>' +
          '<td class="val-val">' + valNumHtml(m.buy_vol_br) + '</td>' +
          '<td class="val-val">' + valNumHtml(m.swing_vol_br) +
            (m.exempt && m.swing_vol > 0
              ? ' ' + flagHtml('🛡️', 'Vendas swing até R$ 20 mil — isento (Lei 11.033)')
              : '') + '</td>' +
          '<td class="val-val">' + signedHtml(m.swing_res_br) +
            (m.carry_used_s > 0 ? ' ' + flagHtml('↩️',
              'Compensado R$ ' + String(m.carry_used_s).replace('.', ',') +
              ' de prejuízo swing anterior') : '') + '</td>' +
          '<td class="val-val">' + valNumHtml(m.day_vol_br) + '</td>' +
          '<td class="val-val">' + signedHtml(m.day_res_br) +
            (m.carry_used_d > 0 ? ' ' + flagHtml('↩️',
              'Compensado R$ ' + String(m.carry_used_d).replace('.', ',') +
              ' de prejuízo day trade anterior') : '') + '</td>' +
          '<td class="val-val" title="Swing R$ ' + m.irrf_s_br + ' · Day R$ ' + m.irrf_d_br + '">' +
            (irrfTotal > 0 ? valNumHtml(fmtBRL(irrfTotal)) : '<span class="muted">—</span>') + '</td>' +
          '<td class="val-val"><b>' + (m.due_total > 0
              ? valNumHtml(m.due_total_br)
              : '<span class="muted">—</span>') + '</b></td>' +
          '<td>' + darf + '<br><span class="muted">' + esc(fmtDate(m.due_date)) + '</span></td>' +
          '</tr>';
      });
      html += '</tbody></table></div>';
      if (u.months.some(function(m) { return m.carry_s_after > 0 || m.carry_d_after > 0; })) {
        var last = u.months[u.months.length - 1];
        html += '<p class="cart-note-line">↩️ Prejuízo a compensar (acumulado até ' +
          esc(last.month_br) + '): swing ' + valNumHtml(last.carry_s_after_br) +
          ' · day trade ' + valNumHtml(last.carry_d_after_br) + '.</p>';
      }
    });
    if (!any) {
      html += '<div class="cart-empty"><h3>Nada por aqui ainda</h3>' +
        '<p>O IR mês a mês aparece quando houver transações — vendas ' +
        'swing (com isenção até R$ 20 mil) e day trade (20%).</p></div>';
    }
    html += '<ul class="cart-ir-notes">' + (j.notes || []).map(function(n) {
      return '<li>' + esc(n) + '</li>';
    }).join('') + '</ul>';
    box.innerHTML = html;
  }

  function accountCard(a) {
    return '<div class="cart-ucard" data-acc="' + esc(a.id) + '" role="button" tabindex="0">' +
      '<div class="cart-ucard-head">' +
        '<span class="cart-ucard-name" title="' +
          esc(a.name + (a.broker ? ' · ' + a.broker : '')) + '">🏦 ' + esc(a.name) +
          (a.watch ? ' <span class="cart-flag" title="⭐ Conta exibida no Painel">⭐</span>' : '') +
        '</span>' +
        '<span class="cart-actions">' +
          '<button class="cart-icon-btn" data-aw="' + esc(a.id) + '" ' +
            (a.watch ? 'title="⭐ Retirar conta do Painel"' : 'title="☆ Exibir conta no Painel"') + '>' +
            (a.watch ? '⭐' : '☆') + '</button>' +
          '<button class="cart-icon-btn" data-ea="' + esc(a.id) + '" title="✏️ Editar conta">✏️</button>' +
          '<button class="cart-icon-btn" data-da="' + esc(a.id) +
            '" title="🗑️ Excluir conta (transações junto)">🗑️</button>' +
        '</span></div>' +
      (a.broker ? '<div class="cart-ucard-broker">🏢 ' + esc(a.broker) + '</div>' : '') +
      '<div class="cart-ucard-stats">' +
        statCell('Patrimônio', a.value, 'Posições desta conta ao último pregão com cotação') +
        statCell('Lucro não realizado', a.profit, 'Patrimônio − custo das posições abertas') +
        statCell('Lucro %', a.profit_pct, 'Lucro sobre o custo (PM)') +
      '</div>' +
      '<div class="cart-ucard-meta">📋 ' + esc(String(a.asset_count)) + ' ativo(s) · 🧾 ' +
        esc(String(a.tx_count)) + ' transação(ões) · 💰 custo ' + esc(a.cost || '—') + '</div>' +
      '<div class="cart-ucard-open">Abrir posições →</div>' +
      '</div>';
  }

  // ── 🏦 L2: inside an account (KPIs + posições + transações) ────────────
  function renderAccountPage() {
    var box = $('cart-level');
    var d = st.pos || {};
    if (d._error) {
      box.innerHTML = '<div class="error">' + esc(d._error) + '</div>';
      return;
    }
    showNote(d);
    if (d.empty) {
      if (d.empty === 'no_txs') {
        box.innerHTML = emptyGuide('no_txs');
      } else {
        box.innerHTML = '<div class="cart-empty"><h3>💡 Conta não encontrada</h3>' +
          '<p>Esta conta não existe mais — volte aos usuários.</p>' +
          '<button class="cart-btn" data-nav="users">👤 Usuários</button></div>';
      }
      return;
    }

    var labelBits = [];
    if (d.scope_label) labelBits.push(d.scope_label);
    if (d.session_date) labelBits.push('pregão ' + d.session_date);
    var html = '<div class="cart-kpis">' + valKpisHtml(d.kpis || []) + '</div>';
    // [v1.22.3] Alertas disparados — the banner between the KPIs and
    // the view bar (loaded async; hidden when empty).
    html += '<div id="cart-alert-banner"></div>';
    // [v1.22.3] FIVE views now: Posições · Transações · Proventos ·
    // Evolução · Alocação — each lazy (loaded on first open).
    html += '<div class="cart-viewbar"><div class="cart-pills" role="group" aria-label="Visão">' +
      '<button class="cart-pill' + (st.view === 'positions' ? ' is-active' : '') +
        '" data-view="positions">Posições</button>' +
      '<button class="cart-pill' + (st.view === 'txs' ? ' is-active' : '') +
        '" data-view="txs">Transações</button>' +
      '<button class="cart-pill' + (st.view === 'proventos' ? ' is-active' : '') +
        '" data-view="proventos">🪙 Proventos</button>' +
      '<button class="cart-pill' + (st.view === 'perf' ? ' is-active' : '') +
        '" data-view="perf">📈 Evolução</button>' +
      '<button class="cart-pill' + (st.view === 'alloc' ? ' is-active' : '') +
        '" data-view="alloc">🥧 Alocação</button></div>' +
      '<span class="cart-scope-label">' + esc(labelBits.join(' · ')) + '</span>' +
      '<span class="cart-toolbar-spacer"></span>' +
      '<button class="cart-btn" data-act="sim" ' +
        'title="Simular vendas/compras sem gravar nada">🧪 Simular</button>' +
      '<button class="cart-btn primary" data-act="tx" ' +
        'title="Registrar transação ou evento corporativo nesta conta">➕ Transação</button>' +
      '<button class="cart-btn" data-act="import" ' +
        'title="Importar nota de corretagem (PDF) nesta conta">📥 Importar nota</button>' +
      '<button class="cart-btn ghost" data-act="reload" aria-label="Recarregar" ' +
        'title="Recarregar dados">🔄</button></div>';
    html += '<div id="cart-positions" class="cart-view"' +
      (st.view === 'positions' ? '' : ' hidden') + '></div>';
    html += '<div id="cart-txs" class="cart-view"' +
      (st.view === 'txs' ? '' : ' hidden') + '></div>';
    // [v1.22.3] the three lazy views — filled on demand.
    html += '<div id="cart-proventos" class="cart-view"' +
      (st.view === 'proventos' ? '' : ' hidden') + '></div>';
    html += '<div id="cart-perf" class="cart-view"' +
      (st.view === 'perf' ? '' : ' hidden') + '></div>';
    html += '<div id="cart-alloc" class="cart-view"' +
      (st.view === 'alloc' ? '' : ' hidden') + '></div>';
    // [v1.22.2] imported-notas registry (undo/dedup visibility).
    // [v1.22.4] It belongs to the TRANSAÇÕES view only (it used to
    // hang under every view — now it shows/hides with the pill).
    html += '<div id="cart-notas" class="cart-notas"' +
      (st.view === 'txs' ? '' : ' hidden') + '></div>';
    box.innerHTML = html;
    renderPositionsTable(d);
    // [v1.22.3] page-1 seeds the ledger; the filter bar re-fetches.
    st.txRows = d.txs || [];
    st.txTotal = d.tx_total || st.txRows.length;
    st.txPages = Math.max(1, Math.ceil(st.txTotal / 50));
    renderTxsTable();
    if (st.view === 'proventos') loadProventos();
    if (st.view === 'perf') loadPerf();
    if (st.view === 'alloc') loadAlloc();
    loadAlertBanner();
    loadNotas();
  }

  function emptyGuide(kind) {
    if (kind === 'no_users') {
      return '<div class="cart-empty"><h3>💡 Comece pela estrutura</h3>' +
        '<ol><li>Crie um <b>usuário</b> (você, cônjuge, empresa…)</li>' +
        '<li>Adicione uma <b>conta</b> por corretora</li>' +
        '<li>Registre <b>compras e vendas</b> — as posições e o preço médio ' +
        'se montam sozinhos</li></ol>' +
        '<button class="cart-btn primary" data-act="user">➕ Criar primeiro usuário</button></div>';
    }
    if (kind === 'no_accounts') {
      return '<div class="cart-empty"><h3>💡 Sem contas ainda</h3>' +
        '<p>Adicione uma conta de corretora para começar a lançar transações.</p>' +
        '<button class="cart-btn primary" data-act="account">➕ Adicionar conta</button></div>';
    }
    return '<div class="cart-empty"><h3>💡 Sem transações</h3>' +
      '<p>Registre uma compra ou venda — a posição, o preço médio e o lucro ' +
      'aparecem aqui. ✅ compra · ❌ venda · preço 0 = ⚠️ bonificação.</p>' +
      '<button class="cart-btn primary" data-act="tx">➕ Registrar transação</button> ' +
      '<button class="cart-btn" data-act="import">📥 Importar nota de corretagem</button></div>';
  }

  function signedHtml(s) {
    if (s === null || s === undefined) return '<span class="muted">—</span>';
    var cls = String(s).charAt(0) === '-' ? 'val-neg'
            : (String(s).charAt(0) === '+' ? 'val-pos' : 'val-zero');
    return '<span class="' + cls + '">' + esc(s) + '</span>';
  }

  function flagHtml(emoji, tip) {
    return '<span class="cart-flag" title="' + esc(tip) + '">' + emoji + '</span>';
  }

  function renderPositionsTable(d) {
    var box = $('cart-positions');
    if (!box) return;
    var head = '<tr>' +
      '<th class="val-sortable">Ticker</th><th>Nome</th><th>Setor</th>' +
      '<th class="th-num val-sortable" title="ℹ️ Preço médio de compra">PM</th>' +
      '<th class="th-num val-sortable">Valor Hoje</th>' +
      '<th class="th-num val-sortable">Qtd</th>' +
      '<th class="th-num val-sortable">Total Original</th>' +
      '<th class="th-num val-sortable">Total Hoje</th>' +
      '<th class="th-num val-sortable">Lucro $</th>' +
      '<th class="th-num val-sortable">Lucro %</th>' +
      '<th></th></tr>';

    var rows = (d.positions || []).map(function(r) {
      var shortFlag = r.short
        ? ' ' + flagHtml('🚨', 'Posição vendida a descoberto (short) — a ' +
            'quantidade está negativa; a cobertura exige compras.') : '';
      // [v1.22] Long in one account + short in another: no consolidated PM.
      var mixFlag = r.mixed
        ? ' ' + flagHtml('🔀', 'Posição mista: long em uma conta e short ' +
            'em outra — o PM consolidado não se aplica; veja por conta.') : '';
      var qtyCell = esc(r.qty) + shortFlag + mixFlag;
      var pmCell = r.pm == null
        ? '<span class="muted" title="' + esc(r.mixed
            ? 'Sem PM consolidado — o mesmo ticker está comprado em uma conta e vendido em outra.'
            : 'Sem cotação') + '">—</span>'
        : valNumHtml(r.pm);
      // [v1.22.3] Illiquid paper: the quote is from an OLDER session —
      // say so next to the price ("cotação de 21/11").
      var staleFlag = r.stale_quote && r.quote_date
        ? ' ' + flagHtml('🕰️', 'Cotação de ' + esc(fmtDate(r.quote_date)) +
                         ' — o papel não negociou na última sessão.') : '';
      // [v1.28.3] The Valor Hoje (the row's MAIN price) wears
      // the band pill; PM (a cost basis, not a market price) stays
      // plain — "just apply to main price".
      var priceCell = r.price_pill
        ? homePricePill(r.price_pill, r.price) + staleFlag
        : valNumHtml(r.price) + staleFlag;
      var sellTitle = r.short
        ? '❌ Vender mais ' + esc(r.ticker) + ' (aumentar o short)'
        : '❌ Vender ' + esc(r.ticker) + ' — fecha a posição (ajuste a quantidade para vender menos)';
      var buyTitle = r.short
        ? '✅ Comprar ' + esc(r.ticker) + ' — cobre o short (ajuste a quantidade)'
        : '✅ Comprar mais ' + esc(r.ticker) + ' (aumenta a posição)';
      var sellQty = r.short ? '' : Math.abs(r.raw_qty || 0);
      var buyQty = r.short ? Math.abs(r.raw_qty || 0) : '';
      return '<tr>' +
        '<td class="cart-tk"><a href="/webui/company/' + encodeURIComponent(r.ticker) + '">' +
          esc(r.ticker) + '</a></td>' +
        '<td class="cart-name">' + esc(r.name) + '</td>' +
        '<td class="cart-sector" title="' + esc(r.sector) + '">' + esc(r.sector) + '</td>' +
        '<td class="val-val">' + pmCell + '</td>' +
        '<td class="val-val">' + priceCell + '</td>' +
        '<td class="val-val">' + qtyCell + '</td>' +
        '<td class="val-val">' + valNumHtml(r.cost) + '</td>' +
        '<td class="val-val">' + valNumHtml(r.value) + '</td>' +
        '<td class="val-val">' + valNumHtml(r.profit) + '</td>' +
        '<td class="val-val">' + signedHtml(r.profit_pct) + '</td>' +
        '<td class="cart-actions">' +
          // [v1.22.3] position-detail drawer — the full PM ladder +
          // proventos of this ticker.
          '<button class="cart-icon-btn" data-pd="' + esc(r.ticker) +
            '" title="🔍 Detalhes da posição — escada de PM, proventos e lucro realizado">🔍</button>' +
          '<button class="cart-icon-btn" data-qb="' + esc(r.ticker) + '" data-qq="' +
            esc(String(buyQty)) + '" title="' + esc(buyTitle) + '">✅</button>' +
          '<button class="cart-icon-btn" data-qs="' + esc(r.ticker) + '" data-qq="' +
            esc(String(sellQty)) + '" title="' + esc(sellTitle) + '">❌</button>' +
        '</td></tr>';
    }).join('');

    var t = d.totals || {};
    var foot = '<tr class="cart-total">' +
      '<td colspan="7">Total</td>' +
      '<td class="val-val">' + valNumHtml(t.value) + '</td>' +
      '<td class="val-val">' + valNumHtml(t.profit) + '</td>' +
      '<td class="val-val">' + signedHtml(t.profit_pct) + '</td>' +
      '<td></td></tr>';

    box.innerHTML = (d.positions && d.positions.length)
      ? '<div class="cart-table-wrap"><table class="val-table cart-table"><thead>' + head +
        '</thead><tbody>' + rows + '</tbody><tfoot>' + foot + '</tfoot></table></div>'
      : '<div class="cart-empty"><h3>Posição zerada</h3><p>Todas as posições ' +
        'já foram vendidas — registre uma nova compra para vê-la aqui.</p></div>';
  }

  // [v1.22.3] The ledger view: FILTER BAR + PAGINATION over GET /txs.
  // Page-1 comes seeded from the positions payload; any filter change
  // re-fetches. Rows render buy/sell AND the corp-event rows (×2 etc).
  var CORP_NAMES = { split: 'Desdobramento', group: 'Grupamento',
                     bonus: 'Bonificação' };

  function txFilter_qs() {
    var f = st.txFilters;
    var parts = ['scope=' + encodeURIComponent(scopeStr()),
                 'page=' + st.txPage, 'per_page=50'];
    if (f.ticker) parts.push('ticker=' + encodeURIComponent(f.ticker));
    if (f.type) parts.push('type=' + encodeURIComponent(f.type));
    if (f.from) parts.push('date_from=' + encodeURIComponent(f.from));
    if (f.to) parts.push('date_to=' + encodeURIComponent(f.to));
    if (f.q) parts.push('q=' + encodeURIComponent(f.q));
    return parts.join('&');
  }

  // [v1.22.4] Known-ticker suggestions for the filter (the store's
  // ticker metadata + every position) — the native datalist pops the
  // matches while you type ("KL" → KLBN4, KLBN11…).
  function txTickerOptions() {
    var seen = {};
    var out = [];
    function add(tk) {
      if (tk && !seen[tk]) { seen[tk] = 1; out.push(tk); }
    }
    ((st.pos && st.pos.positions) || []).forEach(function(p) { add(p.ticker); });
    (st.tickers || []).forEach(function(t) { add(t.ticker); });
    (st.txRows || []).forEach(function(t) { add(t.ticker); });
    return out.sort();
  }

  // [v1.22.4] The filter bar is its own builder — the ERROR path keeps
  // it alive (the old code replaced the whole view with the error,
  // wiping the input mid-typing; with prefix filtering the server no
  // longer 400s on partials, but any error must stay non-destructive).
  function txFilterBarHtml() {
    var f = st.txFilters;
    var opts = txTickerOptions().map(function(tk) {
      return '<option value="' + esc(tk) + '"></option>';
    }).join('');
    return '<div class="cart-filterbar">' +
      '<input type="text" id="txf-ticker" maxlength="8" placeholder="Ticker" list="txf-ticker-list" ' +
        'value="' + esc(f.ticker) + '" style="text-transform: uppercase;" aria-label="Filtrar por ticker">' +
      '<datalist id="txf-ticker-list">' + opts + '</datalist>' +
      '<select id="txf-type" aria-label="Filtrar por tipo">' +
        '<option value="">Tipo: todos</option>' +
        '<option value="buy"' + (f.type === 'buy' ? ' selected' : '') + '>✅ Compras</option>' +
        '<option value="sell"' + (f.type === 'sell' ? ' selected' : '') + '>❌ Vendas</option>' +
        '<option value="corp"' + (f.type === 'corp' ? ' selected' : '') + '>🔀 Eventos</option>' +
      '</select>' +
      '<input type="text" id="txf-from" maxlength="10" placeholder="dd/mm/aaaa" ' +
        'inputmode="numeric" value="' + esc(f.from ? fmtDate(f.from) : '') + '" aria-label="Data inicial">' +
      '<span class="cart-filter-sep">→</span>' +
      '<input type="text" id="txf-to" maxlength="10" placeholder="dd/mm/aaaa" ' +
        'inputmode="numeric" value="' + esc(f.to ? fmtDate(f.to) : '') + '" aria-label="Data final">' +
      '<input type="text" id="txf-q" maxlength="80" placeholder="🔎 Buscar (ticker ou nota)" ' +
        'value="' + esc(f.q) + '" aria-label="Buscar">' +
      '<button class="cart-btn" id="txf-clear" title="Limpar filtros">✖</button>' +
      '</div>';
  }

  function loadTxs() {
    var box = $('cart-txs');
    if (!box) return;
    box.innerHTML = '<span class="loading">⏳ Carregando transações…</span>';
    api('GET', '/txs?' + txFilter_qs()).then(function(res) {
      if (!res.ok) {
        // non-destructive: the bar (with the user's typing) stays.
        renderTxsTable();
        var errBox = $('txf-error');
        if (errBox) {
          errBox.innerHTML = '<div class="error">' +
            esc((res.j && res.j._error) || 'Erro') + '</div>';
        }
        return;
      }
      st.txRows = res.j.rows || [];
      st.txTotal = res.j.total || 0;
      st.txPages = res.j.pages || 1;
      st.txPage = res.j.page || 1;
      renderTxsTable();
    }).catch(function(err) {
      renderTxsTable();
      var errBox = $('txf-error');
      if (errBox) {
        errBox.innerHTML = '<div class="error">Erro: ' + esc(err.message) + '</div>';
      }
    });
  }

  function renderTxsTable() {
    var box = $('cart-txs');
    if (!box) return;
    var bar = txFilterBarHtml() + '<div id="txf-error"></div>';

    var rows = (st.txRows || []).map(function(t) {
      var buy = t.type === 'buy';
      var corp = t.type === 'corp';
      var flags = '';
      if (t.zero) {
        flags += ' ' + flagHtml('⚠️', 'Preço R$ 0,00 — bonificação: os ativos ' +
                 'entraram sem custo no preço médio.');
      }
      if (t.short) {
        flags += ' ' + flagHtml('🚨', 'Esta venda deixou a posição negativa ' +
                 '(venda a descoberto / short).');
      }
      var dateCell = t.note
        ? '<span title="📝 ' + esc(t.note) + '">' + esc(t.date) + ' ' +
          flagHtml('📝', esc(t.note)) + '</span>'
        : esc(t.date);
      var typeCell = corp
        ? '<span class="cart-type is-corp" title="' +
          esc(CORP_NAMES[t.action] || 'Evento corporativo') +
          ' — quantidade e PM re-basados; o custo total não muda.">🔀 ' +
          esc(CORP_NAMES[t.action] || 'Evento') + '</span>'
        : '<span class="cart-type ' + (buy ? 'is-buy' : 'is-sell') + '">' +
          (buy ? '✅ Compra' : '❌ Venda') + '</span>';
      return '<tr>' +
        '<td>' + dateCell + flags + '</td>' +
        '<td class="cart-tk"><a href="/webui/company/' + encodeURIComponent(t.ticker) + '">' +
          esc(t.ticker) + '</a></td>' +
        '<td>' + typeCell + '</td>' +
        '<td class="val-val">' + esc(corp ? (t.factor_br || '—') : t.qty) + '</td>' +
        '<td class="val-val">' + (corp ? '<span class="muted">—</span>'
                                        : valNumHtml(t.price)) + '</td>' +
        '<td class="val-val">' + (corp ? '<span class="muted">—</span>'
                                        : valNumHtml(t.fees)) + '</td>' +
        '<td class="val-val">' + (corp ? '<span class="muted">—</span>'
                                        : valNumHtml(t.total)) + '</td>' +
        '<td class="cart-actions">' +
          '<button class="cart-icon-btn" data-et="' + esc(t.id) + '" title="✏️ Editar">✏️</button>' +
          '<button class="cart-icon-btn" data-dt="' + esc(t.id) + '" title="🗑️ Excluir">🗑️</button>' +
        '</td></tr>';
    }).join('');

    var pager = '<div class="cart-pager">' +
      '<span class="cart-pager-info">' + esc(String(st.txTotal)) +
        ' transação(ões)</span>' +
      '<button class="cart-btn cart-pager-btn" data-tp="prev"' +
        (st.txPage <= 1 ? ' disabled' : '') + '>◀</button>' +
      '<span class="cart-pager-page">' + esc(String(st.txPage)) + ' / ' +
        esc(String(st.txPages)) + '</span>' +
      '<button class="cart-btn cart-pager-btn" data-tp="next"' +
        (st.txPage >= st.txPages ? ' disabled' : '') + '>▶</button>' +
      '</div>';

    box.innerHTML = rows
      ? bar + '<div class="cart-table-wrap"><table class="val-table cart-table"><thead><tr>' +
        '<th class="val-sortable">🗓️ Data</th><th>Ticker</th><th>Tipo</th>' +
        '<th class="th-num val-sortable">Qtd</th><th class="th-num val-sortable">Preço</th>' +
        '<th class="th-num val-sortable">Taxas</th><th class="th-num val-sortable">Total</th>' +
        '<th></th></tr></thead><tbody>' + rows + '</tbody></table></div>' + pager +
        '<p class="cart-note-line">ℹ️ Ordem cronológica (mais antigas primeiro) — ' +
        'a página 1 traz as mais recentes; 🔀 eventos corporativos não movem dinheiro.</p>'
      : bar + '<div class="cart-empty"><h3>Nenhuma transação</h3>' +
        '<p>Nada com esses filtros — limpe-os ou registre a primeira compra.</p></div>';

    // Filter wiring (re-created each render — the bar is fresh HTML).
    var tkEl = $('txf-ticker'), tyEl = $('txf-type'),
        frEl = $('txf-from'), toEl = $('txf-to'), qEl = $('txf-q');
    brDateMask(frEl); brDateMask(toEl);
    function applyFilters() {
      st.txFilters = {
        ticker: (tkEl.value || '').trim().toUpperCase(),
        type: tyEl.value || '',
        from: brToIso(frEl.value) || '',
        to: brToIso(toEl.value) || '',
        q: (qEl.value || '').trim(),
      };
      st.txPage = 1;
      loadTxs();
    }
    var deb = null;
    function debounced() {
      clearTimeout(deb);
      deb = setTimeout(applyFilters, 350);
    }
    tkEl.addEventListener('input', debounced);
    qEl.addEventListener('input', debounced);
    tyEl.addEventListener('change', applyFilters);
    [frEl, toEl].forEach(function(el) {
      el.addEventListener('change', applyFilters);
    });
    $('txf-clear').addEventListener('click', function() {
      st.txFilters = { ticker: '', type: '', from: '', to: '', q: '' };
      st.txPage = 1;
      loadTxs();
    });
    box.querySelectorAll('[data-tp]').forEach(function(b) {
      b.addEventListener('click', function() {
        var dir = b.getAttribute('data-tp');
        var np = dir === 'prev' ? st.txPage - 1 : st.txPage + 1;
        if (np < 1 || np > st.txPages) return;
        st.txPage = np;
        loadTxs();
      });
    });
  }

  // ══════════════════════════════════════════════════════════════════════
  // [v1.22.3] The three lazy views + the drawer + what-if + undo toast.
  // ══════════════════════════════════════════════════════════════════════

  function kpiCardsHtml(kpis) {
    return '<div class="cart-kpis">' + valKpisHtml(kpis || []) + '</div>';
  }

  // ── 🪙 Proventos per position / yield-on-cost (roadmap 2) ─────────────
  function loadProventos() {
    var box = $('cart-proventos');
    if (!box) return;
    box.innerHTML = '<span class="loading">⏳ Calculando proventos…</span>';
    api('GET', '/proventos?scope=' + encodeURIComponent(scopeStr()))
      .then(function(res) {
        renderProventos(res.ok ? res.j : { _error: (res.j && res.j._error) || 'Erro' });
      })
      .catch(function(err) {
        renderProventos({ _error: 'Erro: ' + err.message });
      });
  }

  function renderProventos(j) {
    var box = $('cart-proventos');
    if (!box) return;
    if (j._error) {
      box.innerHTML = '<div class="error">' + esc(j._error) + '</div>';
      return;
    }
    if (j.empty) {
      box.innerHTML = '<div class="cart-empty"><h3>💡 Sem dados ainda</h3>' +
        '<p>Registre transações para ver os proventos recebidos por posição.</p></div>';
      return;
    }
    var html = kpiCardsHtml(j.kpis);
    if ((j.by_ticker || []).length) {
      html += '<div class="cart-sec-head"><h3>🪙 Por ativo</h3></div>' +
        '<div class="cart-table-wrap"><table class="val-table cart-table"><thead><tr>' +
        '<th>Ticker</th><th>Nome</th><th class="th-num">Eventos</th>' +
        '<th class="th-num">Qtd atual</th><th class="th-num">PM</th>' +
        '<th class="th-num">Recebido</th><th class="th-num">A receber</th>' +
        '<th class="th-num" title="Yield sobre o custo — total recebido ÷ custo atual">YOC</th>' +
        '<th>Período</th></tr></thead><tbody>' +
        j.by_ticker.map(function(r) {
          return '<tr>' +
            '<td class="cart-tk"><a href="/webui/company/' + encodeURIComponent(r.ticker) + '">' +
              esc(r.ticker) + '</a></td>' +
            '<td class="cart-name" title="' + esc(r.name) + '">' + esc(r.name) + '</td>' +
            '<td class="val-val">' + esc(String(r.events)) + '</td>' +
            '<td class="val-val">' + esc(r.qty_br) + '</td>' +
            '<td class="val-val">' + (r.pm_br ? valNumHtml(r.pm_br) : '<span class="muted">—</span>') + '</td>' +
            '<td class="val-val">' + valNumHtml(r.received_br) + '</td>' +
            '<td class="val-val">' + (r.pending_br ? valNumHtml(r.pending_br) : '<span class="muted">—</span>') + '</td>' +
            '<td class="val-val">' + (r.yoc_br ? signedHtml(r.yoc_br) : '<span class="muted">—</span>') + '</td>' +
            '<td>' + esc(r.first_ex_br) + ' → ' + esc(r.last_ex_br) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    } else {
      html += '<div class="cart-empty"><h3>Sem proventos registrados</h3>' +
        '<p>Nenhum evento (B3 provents + agenda Dados de Mercado) ' +
        'encontrou posição nas datas com dos seus tickers — sincronize ' +
        'as fontes <b>dividendos</b> e <b>ddm-dividends</b> na página ' +
        'Sincronização se faltar histórico.</p></div>';
    }
    if ((j.events || []).length) {
      html += '<div class="cart-sec-head"><h3>📋 Eventos recebidos' +
        (j.events_total > j.events.length
          ? ' <span class="muted">(mostrando ' + j.events.length + ' de ' +
            j.events_total + ')</span>' : '') + '</h3></div>' +
        '<div class="cart-table-wrap cart-scroll-y"><table class="val-table cart-table"><thead><tr>' +
        '<th>Data com</th><th>Pagamento</th><th>Ticker</th><th>Tipo</th>' +
        '<th class="th-num">R$/ação</th><th class="th-num">Qtd na data</th>' +
        '<th class="th-num">Valor</th></tr></thead><tbody>' +
        j.events.map(function(e) {
          return '<tr>' +
            '<td>' + esc(e.ex_br) + (e.future ? ' ' + flagHtml('⏳',
              'Pagamento futuro — direito já garantido na data com.') : '') + '</td>' +
            '<td>' + (e.pay_br ? esc(e.pay_br) : '—') + '</td>' +
            '<td class="cart-tk">' + esc(e.ticker) + '</td>' +
            '<td>' + esc(e.type) + '</td>' +
            '<td class="val-val">' + esc(e.rate_br) +
              (e.source === 'ddm' ? ' ' + flagHtml('🅓',
                'Evento da agenda Dados de Mercado — fora do provents da B3.') : '') + '</td>' +
            '<td class="val-val">' + esc(e.qty_br) +
              (e.debit_br ? ' ' + flagHtml('🚨', 'Short na data com: ' + e.debit_br +
                ' debitados (quem vende a descoberto paga o provento).') : '') + '</td>' +
            '<td class="val-val">' + valNumHtml(e.valor_br) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    if ((j.notes || []).length) {
      html += '<ul class="cart-notes-list">' +
        j.notes.map(function(n) { return '<li>ℹ️ ' + esc(n) + '</li>'; }).join('') +
        '</ul>';
    }
    box.innerHTML = html;
  }

  // ── 📈 Evolução: curve + TWR/XIRR vs CDI/IBOV (roadmap 4) ─────────────
  function loadPerf() {
    var box = $('cart-perf');
    if (!box) return;
    box.innerHTML = '<span class="loading">⏳ Calculando evolução…</span>';
    api('GET', '/performance?scope=' + encodeURIComponent(scopeStr()))
      .then(function(res) {
        renderPerf(res.ok ? res.j : { _error: (res.j && res.j._error) || 'Erro' });
      })
      .catch(function(err) {
        renderPerf({ _error: 'Erro: ' + err.message });
      });
  }

  function renderPerf(j) {
    var box = $('cart-perf');
    if (!box) return;
    if (j._error) {
      box.innerHTML = '<div class="error">' + esc(j._error) + '</div>';
      return;
    }
    if (j.empty) {
      box.innerHTML = '<div class="cart-empty"><h3>💡 Sem dados ainda</h3>' +
        '<p>Registre transações para ver a evolução do patrimônio.</p></div>';
      return;
    }
    var html = kpiCardsHtml(j.kpis);
    if ((j.curve || {}).labels && j.curve.labels.length > 1) {
      html += '<div class="cart-sec-head"><h3>📈 Patrimônio × CDI × IBOV × S&P 500</h3></div>' +
        '<div class="cart-chart-box"><canvas id="cart-perf-chart" height="120"></canvas></div>';
    }
    html += '<ul class="cart-notes-list">' +
      (j.notes || []).map(function(n) { return '<li>ℹ️ ' + esc(n) + '</li>'; }).join('') +
      '</ul>';
    box.innerHTML = html;

    // The curve chart — the vendored Chart.js, the page's theme colors
    // (the company pages' renderValChart conventions, simplified for a
    // line quartet; [v1.22.4] tick labels are BR months ("mar/2025" —
    // the raw ISO slice "2025-03" leaked before) and IVVB11 joins as
    // the S&P 500 (BRL) line).
    var cv = $('cart-perf-chart');
    if (!cv || typeof Chart === 'undefined') return;
    var th = chartTheme();
    var isoLabels = j.curve.labels;
    var labels = isoLabels.map(function(iso) { return fmtMonth(iso.slice(0, 7)); });
    var mk = function(label, data, color, dash) {
      return { label: label, data: data, borderColor: color,
               backgroundColor: color, borderWidth: 2, pointRadius: 0,
               pointHoverRadius: 4, tension: 0.25, fill: false,
               borderDash: dash || [] };
    };
    var ds = [mk('Patrimônio', j.curve.patrimonio, cssVar('--color-primary') || '#0d9488')];
    if (j.curve.cdi && j.curve.cdi.some(function(v) { return v !== null; })) {
      ds.push(mk('CDI', j.curve.cdi, '#f59e0b', [5, 3]));
    }
    if (j.curve.ibov && j.curve.ibov.some(function(v) { return v !== null; })) {
      ds.push(mk('IBOV (BOVA11)', j.curve.ibov, '#94a3b8', [2, 3]));
    }
    if (j.curve.ivvb && j.curve.ivvb.some(function(v) { return v !== null; })) {
      ds.push(mk('S&P 500 (IVVB11)', j.curve.ivvb, '#dc2626', [6, 3]));
    }
    new Chart(cv, {
      type: 'line',
      data: { labels: labels, datasets: ds },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: th.text } },
          tooltip: {
            callbacks: {
              title: function(items) {
                // the full ISO date under the month tick (precision
                // the tick itself doesn't carry)
                var i = items[0].dataIndex;
                return i < isoLabels.length ? fmtDate(isoLabels[i])
                                            : items[0].label;
              },
              label: function(item) {
                return item.dataset.label + ': ' + fmtBRL(item.parsed.y);
              },
            },
          },
        },
        scales: {
          x: { ticks: { color: th.text, maxTicksLimit: 12 },
               grid: { color: th.grid } },
          y: { ticks: { color: th.text,
                        callback: function(v) { return fmtCompact(v); } },
               grid: { color: th.grid } },
        },
      },
    });
  }

  // ── 🥧 Alocação: weights + HHI (roadmap 6) ────────────────────────────
  function loadAlloc() {
    var box = $('cart-alloc');
    if (!box) return;
    box.innerHTML = '<span class="loading">⏳ Calculando alocação…</span>';
    api('GET', '/allocation?scope=' + encodeURIComponent(scopeStr()))
      .then(function(res) {
        renderAlloc(res.ok ? res.j : { _error: (res.j && res.j._error) || 'Erro' });
      })
      .catch(function(err) {
        renderAlloc({ _error: 'Erro: ' + err.message });
      });
  }

  function renderAlloc(j) {
    var box = $('cart-alloc');
    if (!box) return;
    if (j._error) {
      box.innerHTML = '<div class="error">' + esc(j._error) + '</div>';
      return;
    }
    if (j.empty) {
      box.innerHTML = '<div class="cart-empty"><h3>💡 Sem dados ainda</h3>' +
        '<p>Registre transações para ver a alocação por setor.</p></div>';
      return;
    }
    var html = kpiCardsHtml(j.kpis);
    if (j.quotes_note) html += '<div class="home-note">' + esc(j.quotes_note) + '</div>';
    html += '<div class="cart-alloc-grid">' +
      '<div class="cart-alloc-chart"><canvas id="cart-alloc-chart" height="180"></canvas></div>' +
      '<div class="cart-alloc-tables">';
    if ((j.by_sector || []).length) {
      html += '<div class="cart-sec-head"><h3>🏭 Por setor</h3></div>' +
        '<div class="cart-table-wrap"><table class="val-table cart-table"><thead><tr>' +
        '<th>Setor</th><th class="th-num">Valor</th><th class="th-num">Peso</th>' +
        '<th class="th-num">Ativos</th></tr></thead><tbody>' +
        j.by_sector.map(function(s) {
          return '<tr><td class="cart-sector" title="' + esc(s.tickers.join(', ')) + '">' +
            esc(s.sector) + '</td>' +
            '<td class="val-val">' + valNumHtml(s.value_br) + '</td>' +
            '<td class="val-val">' + esc(s.weight_br || '—') + '</td>' +
            '<td class="val-val">' + esc(String(s.count)) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    if ((j.by_ticker || []).length) {
      html += '<div class="cart-sec-head"><h3>🎯 Por ativo</h3></div>' +
        '<div class="cart-table-wrap cart-scroll-y"><table class="val-table cart-table"><thead><tr>' +
        '<th>Ticker</th><th>Setor</th><th class="th-num">Valor</th>' +
        '<th class="th-num">Peso</th><th class="th-num">Lucro</th></tr></thead><tbody>' +
        j.by_ticker.map(function(r) {
          return '<tr>' +
            '<td class="cart-tk"><a href="/webui/company/' + encodeURIComponent(r.ticker) + '">' +
              esc(r.ticker) + '</a></td>' +
            '<td class="cart-sector">' + esc(r.sector) + '</td>' +
            '<td class="val-val">' + valNumHtml(r.value_br) + '</td>' +
            '<td class="val-val">' + esc(r.weight_br || '—') + '</td>' +
            '<td class="val-val">' + (r.profit_br ? signedHtml(r.profit_br) : '<span class="muted">—</span>') + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    html += '</div></div>';
    box.innerHTML = html;

    var cv = $('cart-alloc-chart');
    if (cv && (j.chart || {}).labels && typeof Chart !== 'undefined') {
      var th = chartTheme();
      new Chart(cv, {
        type: 'doughnut',
        data: {
          labels: j.chart.labels,
          datasets: [{ data: j.chart.data,
                       backgroundColor: _pieColors(j.chart.labels.length),
                       borderWidth: 1 }],
        },
        options: {
          responsive: true, maintainAspectRatio: false, cutout: '45%',
          plugins: {
            legend: { position: 'bottom', labels: { color: th.text,
                                                    boxWidth: 12 } },
            tooltip: { callbacks: { label: function(item) {
              return item.label + ': ' + fmtBRL(item.parsed);
            } } },
          },
        },
      });
    }
  }

  // The pages' pie palette (indexes.py's _pie_colors recipe, client side).
  function _pieColors(n) {
    var base = ['#0d9488', '#f59e0b', '#a855f7', '#16a34a', '#dc2626',
                '#0284c7', '#db2777', '#65a30d', '#7c3aed', '#ea580c',
                '#0891b2', '#ca8a04', '#9333ea', '#059669', '#be123c'];
    var out = [];
    for (var i = 0; i < n; i++) out.push(base[i % base.length]);
    return out;
  }

  // ── 🔍 position-detail drawer (roadmap 7) ─────────────────────────────
  function openPositionDetail(ticker) {
    var drawer = $('cart-drawer');
    if (!drawer) return;
    st.drawerTicker = ticker;          // [v1.22.4] refresh after edits
    drawer.hidden = false;
    drawer.classList.add('open');
    drawer.innerHTML = '<div class="cart-drawer-head"><span class="loading">' +
      '⏳ Carregando ' + esc(ticker) + '…</span></div>';
    api('GET', '/position-detail?scope=' + encodeURIComponent(scopeStr()) +
        '&ticker=' + encodeURIComponent(ticker))
      .then(function(res) {
        if (!res.ok) {
          drawer.innerHTML = '<div class="cart-drawer-head"><button class="cart-icon-btn" ' +
            'data-dclose title="Fechar">✖</button> <span class="error">' +
            esc((res.j && res.j._error) || 'Erro') + '</span></div>';
          return;
        }
        renderPositionDetail(res.j);
      });
  }

  function renderPositionDetail(j) {
    var drawer = $('cart-drawer');
    if (!drawer) return;
    var head = '<div class="cart-drawer-head">' +
      '<span class="cart-drawer-title">🔍 ' + esc(j.ticker) +
        ' <span class="muted">· ' + esc(j.name) + '</span></span>' +
      '<button class="cart-icon-btn" data-dclose title="Fechar">✖</button></div>';
    var facts = '<div class="cart-drawer-facts">' +
      '<span>Qtd: <b>' + esc(j.qty_br) + '</b></span>' +
      '<span>PM: <b>' + (j.pm_br ? esc(j.pm_br) : '—') + '</b></span>' +
      '<span>Custo: <b>' + (j.cost_br ? esc(j.cost_br) : '—') + '</b></span>' +
      '<span>Hoje: <b>' + (j.price_br ? esc(j.price_br) : '—') + '</b></span>' +
      '<span>Valor: <b>' + (j.value_br ? esc(j.value_br) : '—') + '</b></span>' +
      '<span>Lucro realizado: <b>' + signedHtml(j.realized_br) + '</b></span>' +
      (j.short ? '<span class="cart-flag-short">🚨 short aberto</span>' : '') +
      '</div>';
    var html = head + facts;
    (j.ladders || []).forEach(function(l) {
      html += '<div class="cart-sec-head"><h4>🏦 ' + esc(l.account) + '</h4></div>' +
        '<div class="cart-table-wrap cart-scroll-y"><table class="val-table cart-table">' +
        '<thead><tr><th></th><th>🗓️</th><th>Tipo</th><th class="th-num">Qtd</th>' +
        '<th class="th-num">Preço</th><th class="th-num">Taxas</th>' +
        '<th class="th-num">Qtd após</th><th class="th-num">PM após</th>' +
        '<th class="th-num">Δ realizado</th></tr></thead><tbody>' +
        l.rows.map(function(r) {
          var corp = r.type === 'corp';
          return '<tr>' +
            '<td class="cart-actions"><button class="cart-icon-btn" data-et="' +
              esc(r.id) + '" title="✏️ Editar esta transação (a gaveta fica aberta)">✏️</button></td>' +
            '<td>' + esc(fmtDate(r.date)) + (r.note ? ' ' + flagHtml('📝', r.note) : '') + '</td>' +
            '<td>' + (corp
              ? '<span class="cart-type is-corp" title="' +
                esc(CORP_NAMES[r.action] || 'Evento') + '">🔀 ' +
                esc(CORP_NAMES[r.action] || 'Evento') + '</span>'
              : '<span class="cart-type ' + (r.type === 'buy' ? 'is-buy' : 'is-sell') + '">' +
                (r.type === 'buy' ? '✅' : '❌') + '</span>') + '</td>' +
            '<td class="val-val">' + esc(corp ? (r.factor_br || '—')
              : String(r.qty).replace('.', ',')) + '</td>' +
            '<td class="val-val">' + (corp || r.price === null ? '—' : esc(String(r.price).replace('.', ','))) + '</td>' +
            '<td class="val-val">' + (corp || !r.fees ? '—' : esc(String(r.fees).replace('.', ','))) + '</td>' +
            '<td class="val-val">' + esc(String(Math.round(r.run_qty * 10000) / 10000).replace('.', ',')) + '</td>' +
            '<td class="val-val">' + esc(String(Math.round(r.run_pm * 10000) / 10000).replace('.', ',')) + '</td>' +
            '<td class="val-val">' + (r.delta_realized ? signedHtml(
                (r.delta_realized > 0 ? '+' : '') + 'R$ ' +
                String(Math.abs(r.delta_realized)).replace('.', ','))
              : '<span class="muted">—</span>') + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    });
    if ((j.proventos || []).length) {
      html += '<div class="cart-sec-head"><h4>🪙 Proventos desta posição · total ' +
        esc(j.proventos_total_br || '—') + '</h4></div>' +
        '<div class="cart-table-wrap cart-scroll-y"><table class="val-table cart-table">' +
        '<thead><tr><th>Data com</th><th>Pagamento</th><th>Tipo</th>' +
        '<th class="th-num">R$/ação</th><th class="th-num">Qtd</th>' +
        '<th class="th-num">Valor</th></tr></thead><tbody>' +
        j.proventos.map(function(p) {
          return '<tr><td>' + esc(p.ex_br) + (p.future ? ' ⏳' : '') + '</td>' +
            '<td>' + (p.pay_br ? esc(p.pay_br) : '—') + '</td>' +
            '<td>' + esc(p.type) + '</td>' +
            '<td class="val-val">' + esc(p.rate_br) + '</td>' +
            '<td class="val-val">' + esc(p.qty_br) + '</td>' +
            '<td class="val-val">' + valNumHtml(p.valor_br) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    drawer.innerHTML = html;
  }

  function closeDrawer() {
    var drawer = $('cart-drawer');
    if (!drawer) return;
    drawer.classList.remove('open');
    drawer.hidden = true;
    st.drawerTicker = null;            // [v1.22.4] stop post-edit refreshes
  }

  // ── 🧪 what-if simulator (roadmap 6) ──────────────────────────────────
  function openSimModal() {
    var m = $('cart-sim-modal');
    if (!m) return;
    st.simRows = [{ ticker: '', type: 'sell', qty: '', price: '' }];
    renderSimForm();
    $('cart-sim-results').innerHTML = '';
    $('cart-sim-msg').textContent = '';
    m.showModal();
  }

  function renderSimForm() {
    var box = $('cart-sim-form');
    if (!box) return;
    var held = ((st.pos && st.pos.positions) || []).map(function(p) {
      return p.ticker;
    });
    var opts = held.map(function(tk) {
      return '<option value="' + esc(tk) + '">' + esc(tk) + '</option>';
    }).join('');
    box.innerHTML = st.simRows.map(function(r, i) {
      return '<div class="cart-sim-row">' +
        '<select class="cart-select" data-si="' + i + '" data-sf="ticker" aria-label="Ativo">' +
          '<option value="">— ativo —</option>' + opts + '</select>' +
        '<select class="cart-select" data-si="' + i + '" data-sf="type" aria-label="Operação">' +
          '<option value="sell"' + (r.type === 'sell' ? ' selected' : '') + '>❌ Vender</option>' +
          '<option value="buy"' + (r.type === 'buy' ? ' selected' : '') + '>✅ Comprar</option>' +
        '</select>' +
        '<input type="text" inputmode="decimal" placeholder="Qtd" data-si="' + i +
          '" data-sf="qty" value="' + esc(r.qty) + '" aria-label="Quantidade">' +
        '<span class="muted">@</span>' +
        '<input type="text" inputmode="decimal" placeholder="0,00" data-si="' + i +
          '" data-sf="price" value="' + esc(r.price) + '" aria-label="Preço">' +
        (st.simRows.length > 1
          ? '<button class="cart-icon-btn" data-sdel="' + i + '" title="Remover linha">✖</button>'
          : '') +
        '</div>';
    }).join('') +
    '<div class="cart-sim-actions">' +
      '<button class="cart-btn" id="cart-sim-add">➕ Operação</button>' +
      '<button class="cart-btn primary" id="cart-sim-run">🧪 Simular</button></div>';

    box.querySelectorAll('[data-sf]').forEach(function(el) {
      el.addEventListener('input', function() {
        var i = parseInt(el.getAttribute('data-si'), 10);
        var f = el.getAttribute('data-sf');
        st.simRows[i][f] = el.value;
      });
      el.addEventListener('change', function() {
        var i = parseInt(el.getAttribute('data-si'), 10);
        var f = el.getAttribute('data-sf');
        st.simRows[i][f] = el.value;
      });
    });
    box.querySelectorAll('[data-sdel]').forEach(function(b) {
      b.addEventListener('click', function() {
        st.simRows.splice(parseInt(b.getAttribute('data-sdel'), 10), 1);
        renderSimForm();
      });
    });
    $('cart-sim-add').addEventListener('click', function() {
      st.simRows.push({ ticker: '', type: 'sell', qty: '', price: '' });
      renderSimForm();
    });
    $('cart-sim-run').addEventListener('click', runSim);
  }

  function runSim() {
    var trades = [];
    for (var i = 0; i < st.simRows.length; i++) {
      var r = st.simRows[i];
      var q = parseBr(r.qty), p = parseBr(r.price);
      if (!r.ticker || q === null || p === null) continue;
      trades.push({ ticker: r.ticker, type: r.type, quantity: q, price: p });
    }
    if (!trades.length) {
      $('cart-sim-msg').textContent = 'Preencha ao menos uma operação (ativo, qtd e preço).';
      return;
    }
    $('cart-sim-results').innerHTML = '<span class="loading">⏳ Simulando…</span>';
    api('POST', '/simulate', { scope: scopeStr(), trades: trades })
      .then(function(res) {
        if (!res.ok) {
          $('cart-sim-results').innerHTML = '';
          $('cart-sim-msg').textContent = (res.j && res.j._error) || 'Erro.';
          return;
        }
        $('cart-sim-msg').textContent = '';
        renderSimResults(res.j);
      });
  }

  function renderSimResults(j) {
    var box = $('cart-sim-results');
    var html = '<div class="cart-sim-kpis">' +
      (j.kpis || []).map(function(k) {
        return '<div class="cart-sim-kpi"' + (k.tooltip ? ' title="' + esc(k.tooltip) + '"' : '') + '>' +
          '<span class="cart-stat-l">' + esc(k.label) + '</span>' +
          '<span class="cart-sim-vals">' +
            '<span class="cart-sim-before">' + (k.before ? esc(k.before) : '—') + '</span>' +
            '<span class="cart-sim-arrow">→</span>' +
            '<span class="cart-sim-after">' + (k.after ? signedHtml(k.after) : '—') + '</span>' +
          '</span></div>';
      }).join('') + '</div>';
    html += '<div class="cart-table-wrap"><table class="val-table cart-table"><thead><tr>' +
      '<th>Ativo</th><th>Operação</th><th class="th-num">Qtd</th>' +
      '<th class="th-num">Preço</th><th class="th-num">Δ Lucro realizado</th>' +
      '<th class="th-num">Qtd após</th></tr></thead><tbody>' +
      (j.trades || []).map(function(t) {
        return '<tr><td class="cart-tk">' + esc(t.ticker) + '</td>' +
          '<td>' + (t.type === 'sell' ? '❌ Venda' : '✅ Compra') + '</td>' +
          '<td class="val-val">' + esc(t.qty_br) + '</td>' +
          '<td class="val-val">' + esc(t.price_br) + '</td>' +
          '<td class="val-val">' + signedHtml(t.delta_realized_br) + '</td>' +
          '<td class="val-val">' + esc(t.qty_after_br) + '</td></tr>';
      }).join('') + '</tbody></table></div>';
    html += '<ul class="cart-notes-list">' +
      (j.notes || []).map(function(n) { return '<li>ℹ️ ' + esc(n) + '</li>'; }).join('') +
      '</ul>';
    box.innerHTML = html;
  }

  // ── ↩️ undo toast (roadmap 7) ─────────────────────────────────────────
  function showUndoToast(label, token) {
    var t = $('cart-toast');
    if (!t || !token) return;
    t.innerHTML = '<span class="cart-toast-label">✅ ' + esc(label) + '</span>' +
      '<button class="cart-btn cart-toast-btn" id="cart-toast-undo">↩️ Desfazer</button>';
    t.hidden = false;
    clearTimeout(st.undoTimer);
    st.undoTimer = setTimeout(function() { t.hidden = true; }, 12000);
    $('cart-toast-undo').addEventListener('click', function() {
      t.hidden = true;
      clearTimeout(st.undoTimer);
      api('POST', '/undo', { token: token }).then(function(res) {
        if (res.ok && res.j && res.j.warnings && res.j.warnings.length) {
          st.pendingNote = { text: res.j.warnings.join(' '),
                             until: Date.now() + 15000 };
        }
        if (!res.ok) {
          st.pendingNote = { text: (res.j && res.j._error) ||
            'Não foi possível desfazer — a ação expirou.',
            until: Date.now() + 15000 };
        }
        reload();
      });
    });
  }

  // ── 🔔 alertas banner (roadmap 6) ─────────────────────────────────────
  function loadAlertBanner() {
    var box = $('cart-alert-banner');
    if (!box) return;
    api('GET', '/alerts').then(function(res) {
      if (!res.ok) { box.innerHTML = ''; return; }
      var triggered = (res.j.alerts || []).filter(function(a) {
        return a.triggered === true;
      });
      if (!triggered.length) { box.innerHTML = ''; return; }
      box.innerHTML = '<div class="cart-alerts-banner">🔔 ' +
        triggered.map(function(a) {
          return '<span class="cart-alert-chip" title="Alerta: ' +
            esc(a.ticker) + (a.op === 'above' ? ' acima de ' : ' abaixo de ') +
            esc(a.price_br) + ' — cotação ' + esc(a.current || '—') +
            (a.quote_date ? ' (pregão ' + esc(fmtDate(a.quote_date)) + ')' : '') +
            '. Gerencie em ⚙️ Gerenciar → Alertas.">' +
            '<b>' + esc(a.ticker) + '</b> ' +
            (a.op === 'above' ? '≥' : '≤') + ' ' + esc(a.price_br) +
            ' <span class="muted">(agora ' + esc(a.current || '—') + ')</span></span>';
        }).join('') + '</div>';
    });
  }

  // ── BR-standard input masks ────────────────────────────────────────────
  function centsFmt(n) {
    var s = String(n);
    var dec = s.length <= 2 ? ('00' + s).slice(-2) : s.slice(-2);
    var int = s.length <= 2 ? '0' : s.slice(0, s.length - 2);
    var t = int.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return t + ',' + dec;
  }

  // [fix 2] Programmatic money write — sets the value AND the right
  // mask mode (edit prefill, paste): >2 decimals (penny stocks) enter
  // the explicit-decimals mode; anything else cents-fill.
  function setMoney(el, n) {
    if (n === null || n === undefined || isNaN(n)) {
      el.value = '';
      el._explicit = false;
      return;
    }
    el.value = moneyStr(n);
    el._explicit = ((el.value.split(',')[1] || '').length > 2);
  }

  function brCents(el) {
    // [fix 2] POS-style money mask, CORRECTED: digits fill from the
    // cents — typing 1·2·3·4 reads 0,01 → 0,12 → 1,23 → 12,34. The
    // fix 1 version appended AFTER its own mask comma ("0,01" + "2"
    // → "0,012" — you had to click on the 0, to keep typing). The
    // digits of the WHOLE value (mask comma stripped) re-feed
    // centsFmt on every input, so each keystroke shifts left —
    // backspace shifts right, exactly like a Brazilian POS.
    // A typed ',' (or '.') switches to EXPLICIT decimals (penny
    // stocks, 0,0432): the integer part stops shifting and digits
    // extend the decimals; deleting the comma (or clearing the field)
    // returns to the cents-fill mode.
    el.addEventListener('keydown', function(e) {
      if (e.key === ',' || e.key === '.') {
        e.preventDefault();          // never a literal '.'/second ','
        if (!el._explicit) {
          el._explicit = true;
          if (!el.value.replace(/\D/g, '')) el.value = '0,';
          // cents mode already displays a comma — the value stands
          // as-is; further digits now extend the decimals.
        }
      }
    });
    el.addEventListener('paste', function(e) {
      var txt = e.clipboardData ? e.clipboardData.getData('text') : '';
      e.preventDefault();
      setMoney(el, parseBr(txt));    // "3,65"/"3.65"/"0,0432" all land right
      updateHints();
    });
    el.addEventListener('input', function() {
      var v = el.value;
      if (el._explicit) {
        var hasComma = v.indexOf(',') >= 0;
        if (!hasComma) {             // comma removed → back to cents-fill
          el._explicit = false;
          var back = v.replace(/\D/g, '').slice(0, 11);
          el.value = back === '' ? '' : centsFmt(parseInt(back, 10));
        } else {
          var parts = v.split(',');
          var int = parts[0].replace(/\D/g, '');
          var dec = (parts[1] || '').replace(/\D/g, '').slice(0, 4);
          el.value = int + ',' + dec;
        }
      } else {
        var dd = v.replace(/\D/g, '').slice(0, 11);
        el.value = dd === '' ? '' : centsFmt(parseInt(dd, 10));
      }
      updateHints();
    });
  }

  function brQtyMask(el) {
    // Quantity: digits + ONE comma (fractional lots), max 4 decimals.
    el.addEventListener('input', function() {
      var v = el.value;
      var parts = v.split(',');
      var int = parts[0].replace(/\D/g, '');
      var dec = parts.length > 1 ? ',' + parts[1].replace(/\D/g, '').slice(0, 4) : '';
      el.value = int + dec;
      updateHints();
    });
  }

  function brDateMask(el) {
    // dd/mm/aaaa — the BR standard (the native date input follows the
    // BROWSER locale, which read as mm/dd/aaaa on en-US systems).
    el.addEventListener('input', function() {
      var dd = el.value.replace(/\D/g, '').slice(0, 8);
      el.value = dd.length > 4
        ? dd.slice(0, 2) + '/' + dd.slice(2, 4) + '/' + dd.slice(4)
        : dd.length > 2 ? dd.slice(0, 2) + '/' + dd.slice(2) : dd;
    });
  }

  function brToIso(s) {
    var m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(s || '');
    if (!m) return null;
    var d = +m[1], mo = +m[2], y = +m[3];
    var dt = new Date(y, mo - 1, d);
    if (dt.getDate() !== d || dt.getMonth() !== mo - 1) return null;
    return y + '-' + m[2] + '-' + m[1];
  }

  function isoToBr(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || '');
    return m ? m[3] + '/' + m[2] + '/' + m[1] : (s || '');
  }

  function todayBr() {
    var d = new Date();
    return ('0' + d.getDate()).slice(-2) + '/' +
           ('0' + (d.getMonth() + 1)).slice(-2) + '/' + d.getFullYear();
  }

  function parseBr(v) {
    var raw = String(v === null || v === undefined ? '' : v).trim();
    // [v1.22] A paste like "3.65" / "0.0432" / "12.5" (no comma, ONE
    // dot, not a 3-digit group) is a US-style decimal: stripping the
    // dot read it as 365 (100×). Masked fields always carry a comma,
    // so typed input is unaffected; "1.234" stays PT-BR thousands.
    if (raw.indexOf(',') < 0 && /^\d+\.\d+$/.test(raw) &&
        !/^\d{1,3}\.\d{3}$/.test(raw)) {
      var dn = parseFloat(raw);
      return isNaN(dn) ? null : dn;
    }
    var s = raw.replace(/\./g, '').replace(',', '.');
    var n = parseFloat(s);
    return isNaN(n) ? null : n;
  }

  function moneyStr(v) {
    if (v === null || v === undefined) return '';
    var dec = (v > 0 && v < 1) ? 4 : 2;
    var n = Math.round(v * Math.pow(10, dec)) / Math.pow(10, dec);
    return String(n).replace('.', ',');
  }

  // ── tx modal ───────────────────────────────────────────────────────────
  function findPos(ticker) {
    if (st.level.kind !== 'account' || !st.pos || !st.pos.positions) return null;
    return st.pos.positions.filter(function(p) {
      return p.ticker === ticker;
    })[0] || null;
  }

  function updatePosCtx() {
    var box = $('cart-tx-posctx');
    if (!box) return;
    var tk = ($('cart-tx-ticker').value || '').trim().toUpperCase();
    var pos = tk ? findPos(tk) : null;
    if (!tk || !pos) { box.hidden = true; box.innerHTML = ''; return; }
    box.hidden = false;
    box.innerHTML = '📋 <b>Posição atual nesta conta:</b> ' + esc(pos.qty) + ' ' +
      esc(tk) + ' @ PM ' + (pos.pm ? esc(pos.pm) : '—') +
      ' · Lucro não realizado: ' + signedHtml(pos.profit) + ' (' + signedHtml(pos.profit_pct) + ')';
  }

  function updateHints() {
    var box = $('cart-tx-hints');
    if (!box) return;
    var hints = [];
    var type = $('cart-tx-type').value;
    var tk = ($('cart-tx-ticker').value || '').trim().toUpperCase();
    var qty = parseBr($('cart-tx-qty').value);
    var priceRaw = $('cart-tx-price').value;
    var price = priceRaw === '' ? null : parseBr(priceRaw);
    if (type === 'corp') {
      // [v1.22.3] corp hints: the factor's plain-language meaning +
      // the fraction warning (B3 pays fractions in cash).
      // [v1.22.4] with no event selected yet, the only hint is the
      // nudge (the instructions block below carries the detail).
      var action = $('cart-tx-action').value;
      if (!action) {
        hints.push('🔀 <b>Selecione o tipo de evento</b> acima ' +
          '(desdobramento, grupamento ou bonificação) e informe o fator.');
        box.innerHTML = hints.join('<br>');
        box.hidden = !hints.length;
        return;
      }
      var f = parseBr($('cart-tx-factor').value);
      if (tk && f !== null && Math.abs(f - 1) > 1e-9) {
        hints.push('🔀 <b>' + esc(CORP_NAMES[action] || 'Evento') +
          ':</b> a quantidade multiplica por <b>' + esc(String(f).replace('.', ',')) +
          '</b> e o PM divide pelo mesmo fator — o custo total não muda.');
        var pos0 = findPos(tk);
        if (pos0 && pos0.raw_qty) {
          var after = pos0.raw_qty * f;
          hints.push('ℹ️ Posição de ' + esc(pos0.qty) + ' → <b>' +
            esc(String(Math.round(after * 10000) / 10000).replace('.', ',')) +
            '</b> ' + esc(tk) + '.');
          if (!Number.isInteger(Math.round(after * 1e6) / 1e6)) {
            hints.push('⚠️ <b>Frações:</b> a B3 liquida frações em dinheiro — ' +
              'se você recebeu o dinheiro, registre uma venda da fração.');
          }
        }
      }
      box.innerHTML = hints.join('<br>');
      box.hidden = !hints.length;
      return;
    }
    if (type === 'sell' && qty !== null && tk) {
      var pos = findPos(tk);
      var cur = pos ? (pos.raw_qty || 0) : 0;
      if (qty > cur + 1e-9) {
        var rest = Math.round((cur - qty) * 10000) / 10000;
        hints.push('🚨 <b>Venda a descoberto (short):</b> a posição de ' +
          esc(pos ? String(pos.qty) : '0') + ' ficará em ' + esc(String(rest)) +
          ' ' + esc(tk) + '.');
      }
    }
    if (price === 0) {
      // [v1.22] Sell at R$ 0,00 is refused by the server — say it here
      // too (bonificação is a BUY at 0).
      hints.push(type === 'sell'
        ? '🚫 <b>Venda a R$ 0,00 não é válida</b> — bonificações se ' +
          'registram como COMPRA a R$ 0,00.'
        : '⚠️ <b>Preço R$ 0,00 — bonificação?</b> Os ativos entram ' +
          'sem custo no preço médio.');
    }
    box.innerHTML = hints.join('<br>');
    box.hidden = !hints.length;
  }

  function findTxRow(id) {
    // [v1.22.3] The tx may live on ANY ledger page now — check the
    // seeded rows and the paged rows before giving up.
    var pools = [((st.pos && st.pos.txs) || []), (st.txRows || [])];
    for (var i = 0; i < pools.length; i++) {
      for (var k = 0; k < pools[i].length; k++) {
        if (pools[i][k].id === id) return pools[i][k];
      }
    }
    return null;
  }

  function openTxModal(txId, prefill) {
    st.editTx = txId || null;
    prefill = prefill || {};
    var m = $('cart-tx-modal');
    var tx = null;
    if (txId) tx = findTxRow(txId);
    m.querySelector('#cart-tx-title').textContent =
      tx ? '✏️ Editar transação' : '➕ Nova transação';
    // Account options — RELATIVE to where you are: inside an account,
    // just that account; inside a user, their accounts grouped.
    var groups = {};
    var accs = st.accounts || [];
    if (st.level.kind === 'account') {
      accs = accs.filter(function(a) { return a.id === st.level.id; });
    } else if (st.level.kind === 'user') {
      accs = accs.filter(function(a) { return a.user_id === st.level.id; });
    }
    accs.forEach(function(a) {
      var g = a.user_name || a.user_id;
      (groups[g] = groups[g] || []).push(a);
    });
    var html = '';
    Object.keys(groups).forEach(function(g) {
      html += '<optgroup label="' + esc(g) + '">';
      groups[g].forEach(function(a) {
        html += '<option value="' + esc(a.id) + '">' +
          esc(a.name + (a.broker ? ' · ' + a.broker : '')) + '</option>';
      });
      html += '</optgroup>';
    });
    var accSel = $('cart-tx-account');
    accSel.innerHTML = st.accounts.length && html
      ? html : '<option value="">— crie uma conta primeiro —</option>';
    var preferred = tx ? tx.account_id
      : (prefill.account_id ||
         (st.level.kind === 'account' ? st.level.id : null));
    if (preferred) accSel.value = preferred;
    $('cart-tx-ticker').value = tx ? tx.ticker : (prefill.ticker || '');
    $('cart-tx-type').value = tx ? tx.type : (prefill.type || 'buy');
    $('cart-tx-date').value = tx ? isoToBr(tx.date_iso) : todayBr();
    var prefQty = prefill.qty;
    $('cart-tx-qty').value = tx && tx.type !== 'corp'
      ? String(tx.quantity).replace('.', ',')
      : (prefQty !== undefined && prefQty !== '' && prefQty !== null
          ? String(prefQty).replace('.', ',') : '');
    // [v1.22.3] Corporate action fields — prefills from the tx (edit);
    // [v1.22.4] NEW corp txs start with NOTHING selected (the
    // placeholder option) and an empty factor — the flow is: pick the
    // event, then the factor (the instructions block under the fields
    // spells out each one).
    var isCorp = (tx ? tx.type : $('cart-tx-type').value) === 'corp';
    $('cart-tx-action').value = tx && tx.type === 'corp' ? (tx.action || '') : '';
    $('cart-tx-factor').value = tx && tx.type === 'corp'
      ? String(tx.factor || '').replace('.', ',') : '';
    // [fix 2] setMoney also primes the mask mode (a 4-decimal PM edit
    // opens in explicit mode; a fresh form starts in cents-fill).
    setMoney($('cart-tx-price'), tx && tx.type !== 'corp' ? tx.raw_price : null);
    setMoney($('cart-tx-fees'), tx && tx.type !== 'corp' ? (tx.raw_fees || 0) : null);
    $('cart-tx-note').value = tx ? (tx.note || '') : '';
    toggleCorpFields(isCorp);
    fieldErrs(m, {});
    $('cart-tx-msg').textContent = '';
    updatePosCtx();
    updateHints();
    m.showModal();
    if (!tx && !prefill.ticker) $('cart-tx-ticker').focus();
  }

  // [v1.22.3] corp mode: the action select + factor (with quick
  // presets) show. Nothing is traded — only the quantity/PM re-base.
  // [v1.22.4] The money/qty fields STAY VISIBLE but lock at 0 (the
  // user reads "nothing was traded here" right on the form); leaving
  // corp mode unlocks them empty again.
  function toggleCorpFields(isCorp) {
    ['cart-tx-qty', 'cart-tx-price', 'cart-tx-fees'].forEach(function(id) {
      var el = $(id);
      if (!el) return;
      if (isCorp) {
        el.disabled = true;
        el.value = id === 'cart-tx-qty' ? '0' : '0,00';
        el.setAttribute('aria-readonly', 'true');
        var fld = el.closest('.cart-field');
        if (fld) fld.classList.add('cart-field-locked');
      } else {
        el.disabled = false;
        el.removeAttribute('aria-readonly');
        var fld2 = el.closest('.cart-field');
        if (fld2) fld2.classList.remove('cart-field-locked');
        // Only reset when they still carry the locked zeros — a fresh
        // buy form opened straight away keeps its empty cents-fill.
        if (el.value === '0' || el.value === '0,00') {
          if (id === 'cart-tx-qty') el.value = '';
          else setMoney(el, null);
        }
      }
    });
    var corp = $('cart-tx-corp');
    if (corp) corp.hidden = !isCorp;
  }

  function corpFactorFor(action, raw) {
    // Presets translate the plain-language proportion into the factor
    // the engine multiplies the quantity by (and divides the PM).
    var v = parseBr(raw);
    if (v !== null) return v;
    return action === 'group' ? 0.5 : 2;
  }

  // ── user / account modals ──────────────────────────────────────────────
  function openUserModal(id) {
    st.editUser = id || null;
    var m = $('cart-user-modal');
    var u = id ? userById(id) : null;
    m.querySelector('#cart-user-title').textContent =
      u ? '✏️ Editar usuário' : '👤 Novo usuário';
    $('cart-user-name').value = u ? u.name : '';
    fieldErrs(m, {});
    $('cart-user-msg').textContent = '';
    m.showModal();
    $('cart-user-name').focus();
  }

  function openAccountModal(id) {
    st.editAccount = id || null;
    var m = $('cart-account-modal');
    var a = id ? stAccount(id) : null;
    m.querySelector('#cart-account-title').textContent =
      a ? '✏️ Editar conta' : '🏦 Nova conta';
    var uSel = $('cart-account-user');
    var users = st.users || [];
    if (st.level.kind === 'user') {          // relative: this user preselected
      users = users.filter(function(u) { return u.id === st.level.id; });
    }
    uSel.innerHTML = users.map(function(u) {
      return '<option value="' + esc(u.id) + '">' + esc(u.name) + '</option>';
    }).join('');
    if (!users.length) {
      uSel.innerHTML = '<option value="">— crie um usuário primeiro —</option>';
    }
    var uid = a ? a.user_id
      : (st.level.kind === 'user' ? st.level.id : null);
    if (uid) uSel.value = uid;
    $('cart-account-name').value = a ? a.name : '';
    $('cart-account-broker').value = a ? (a.broker || '') : '';
    $('cart-account-watch').checked = a ? !!a.watch : false;
    fieldErrs(m, {});
    $('cart-account-msg').textContent = '';
    m.showModal();
    $('cart-account-name').focus();
  }

  // ── saves ──────────────────────────────────────────────────────────────
  function saveUser() {
    var m = $('cart-user-modal');
    var body = { name: $('cart-user-name').value };
    var call = st.editUser
      ? api('PUT', '/users/' + st.editUser, body)
      : api('POST', '/users', body);
    call.then(function(res) {
      if (!res.ok) {
        fieldErrs(m, res.j);
        $('cart-user-msg').textContent = (res.j && res.j._error) || '';
        return;
      }
      m.close();
      reload();
    }).catch(function() {
      $('cart-user-msg').textContent = 'Erro de rede.';
    });
  }

  function saveAccount() {
    var m = $('cart-account-modal');
    var body = {
      user_id: $('cart-account-user').value,
      name: $('cart-account-name').value,
      broker: $('cart-account-broker').value,
      watch: $('cart-account-watch').checked,
    };
    var call = st.editAccount
      ? api('PUT', '/accounts/' + st.editAccount, body)
      : api('POST', '/accounts', body);
    call.then(function(res) {
      if (!res.ok) {
        fieldErrs(m, res.j);
        $('cart-account-msg').textContent = (res.j && res.j._error) || '';
        return;
      }
      m.close();
      reload();
    }).catch(function() {
      $('cart-account-msg').textContent = 'Erro de rede.';
    });
  }

  function saveTx() {
    var m = $('cart-tx-modal');
    var iso = brToIso($('cart-tx-date').value);
    if (!iso) {
      fieldErrs(m, { date: 'Data inválida — use dd/mm/aaaa.' });
      return;
    }
    var type = $('cart-tx-type').value;
    var body = {
      account_id: $('cart-tx-account').value,
      ticker: $('cart-tx-ticker').value,
      type: type,
      date: iso,
      note: $('cart-tx-note').value,
    };
    if (type === 'corp') {
      // [v1.22.3] Corporate action: no money fields — action + factor.
      // [v1.22.4] The event must be chosen (the placeholder option is
      // not one) — caught here AND on the server.
      if (!$('cart-tx-action').value) {
        fieldErrs(m, { action: 'Selecione o tipo de evento — desdobramento, ' +
                             'grupamento ou bonificação.' });
        $('cart-tx-msg').textContent = 'Selecione o tipo de evento.';
        return;
      }
      body.action = $('cart-tx-action').value;
      body.factor = parseBr($('cart-tx-factor').value);
    } else {
      var qv = parseBr($('cart-tx-qty').value);
      var pv = parseBr($('cart-tx-price').value);
      var fv = parseBr($('cart-tx-fees').value);
      body.quantity = qv === null ? $('cart-tx-qty').value : qv;
      body.price = pv === null ? $('cart-tx-price').value : pv;
      body.fees = fv === null ? '' : fv;
    }
    var call = st.editTx
      ? api('PUT', '/txs/' + st.editTx, body)
      : api('POST', '/txs', body);
    call.then(function(res) {
      if (!res.ok) {
        fieldErrs(m, res.j);
        $('cart-tx-msg').textContent = (res.j && res.j._error) || '';
        return;
      }
      // [v1.22] Edit left shorts open? Show the server's warning.
      if (res.j && res.j.warnings && res.j.warnings.length) {
        st.pendingNote = { text: res.j.warnings.join(' '),
                           until: Date.now() + 15000 };
      }
      m.close();
      // [v1.22.3] ↩️ undo toast — the mutation response carries the
      // token; 12s to regret.
      showUndoToast(res.j && res.j.undo_label, res.j && res.j.undo_token);
      reload();
      // [v1.22.4] The drawer (if open on this ticker) shows the edit —
      // refresh its ladder instead of serving stale numbers.
      if (st.drawerTicker) openPositionDetail(st.drawerTicker);
    }).catch(function() {
      $('cart-tx-msg').textContent = 'Erro de rede.';
    });
  }

  // ── deletes / watch toggle ─────────────────────────────────────────────
  // [fix 2] ALL destructive ops go through the styled 🗑️ confirmation
  // (dead-center <dialog>, same language as the other modals — the
  // window.confirm popup is gone) and spell out the blast radius.
  var confirmAction = null;

  function askConfirm(title, textHtml, okLabel, cb) {
    var m = $('cart-confirm-modal');
    if (!m) {                          // template drift — native fallback
      if (window.confirm(textHtml.replace(/<[^>]+>/g, ' '))) cb();
      return;
    }
    $('cart-confirm-title').textContent = title;
    $('cart-confirm-text').innerHTML = textHtml;
    $('cart-confirm-ok').textContent = okLabel;
    confirmAction = cb;
    m.showModal();
  }

  function confirmDeleteUser(id) {
    var u = userById(id);
    var n = st.accounts.filter(function(a) { return a.user_id === id; }).length;
    askConfirm('🗑️ Excluir usuário',
      'Excluir o usuário <b>' + esc(u ? u.name : '—') + '</b>' +
      (n ? ' e suas <b>' + n + ' conta(s)</b> com <b>todas as transações</b>' : '') + '?<br>' +
      '<span class="cart-warn-line">ℹ️ Não há como desfazer.</span>',
      '🗑️ Excluir usuário', function() {
        api('DELETE', '/users/' + id).then(function(res) {
          if (!res.ok) window.alert((res.j && res.j._error) || 'Erro ao excluir.');
          else reload();
        });
      });
  }

  function confirmDeleteAccount(id) {
    var a = stAccount(id);
    var n = a ? (a.tx_count || 0) : 0;
    askConfirm('🗑️ Excluir conta',
      'Excluir a conta <b>' + esc(a ? a.name : '—') + '</b>' +
      (a && a.broker ? ' (' + esc(a.broker) + ')' : '') +
      (n ? ' e suas <b>' + n + ' transação(ões)</b>' : '') + '?<br>' +
      '<span class="cart-warn-line">ℹ️ Não há como desfazer.</span>',
      '🗑️ Excluir conta', function() {
        api('DELETE', '/accounts/' + id).then(function(res) {
          if (!res.ok) window.alert((res.j && res.j._error) || 'Erro ao excluir.');
          else reload();
        });
      });
  }

  function confirmDeleteTx(id) {
    var tx = findTxRow(id);
    askConfirm('🗑️ Excluir transação',
      'Excluir ' + (tx
        ? (tx.type === 'corp'
            ? 'o <b>evento corporativo</b> de <b>' + esc(tx.ticker) + '</b> (' +
              esc(tx.factor_br || '') + ') em ' + esc(tx.date)
            : 'a <b>' + (tx.type === 'buy' ? 'compra' : 'venda') + '</b> de <b>' +
              esc(tx.qty) + ' ' + esc(tx.ticker) + '</b> em ' + esc(tx.date))
        : 'esta transação') +
      '?<br><span class="cart-warn-line">ℹ️ O preço médio e o lucro são recalculados.</span>',
      '🗑️ Excluir transação', function() {
        api('DELETE', '/txs/' + id).then(function(res) {
          if (!res.ok) window.alert((res.j && res.j._error) || 'Erro ao excluir.');
          else {
            // [v1.22] Delete left shorts open? Show the server's warning.
            if (res.j && res.j.warnings && res.j.warnings.length) {
              st.pendingNote = { text: res.j.warnings.join(' '),
                                 until: Date.now() + 15000 };
            }
            // [v1.22.3] ↩️ undo toast.
            showUndoToast(res.j && res.j.undo_label, res.j && res.j.undo_token);
            reload();
            // [v1.22.4] keep an open drawer honest after a delete.
            if (st.drawerTicker) openPositionDetail(st.drawerTicker);
          }
        });
      });
  }

  function toggleWatchAccount(id) {
    var a = stAccount(id);
    if (!a) return;
    api('PUT', '/accounts/' + id, { watch: !a.watch }).then(function() { reload(); });
  }

  // ── 📥 nota import (PDF → preview → commit) [v1.22.2] ──────────────────
  // The dry-run discipline of a money engine: the PDF is parsed on the
  // server into a PREVIEW (nothing written), specs without ticker
  // (modelo B3) get mapped by hand, and only then the commit — one
  // atomic bulk insert with dedup (cnpj + nº nota + pregão) and undo.
  function normSpecKey(market, spec) {
    return (String(market || '').split(' ')[0] + '|' + String(spec || '')).toUpperCase();
  }

  function importMsg(text) {
    $('cart-import-msg').textContent = text || '';
  }

  function openImportModal() {
    if (st.level.kind !== 'account') return;
    st.import = null;
    $('cart-import-file').value = '';
    $('cart-import-preview').innerHTML = '';
    $('cart-import-commit').hidden = true;
    importMsg('');
    $('cart-import-modal').showModal();
  }

  function readImportFile(file) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      importMsg('PDF muito grande (limite 5 MB).');
      return;
    }
    var reader = new FileReader();
    reader.onload = function() {
      var b64 = String(reader.result || '').split(',')[1] || '';
      $('cart-import-preview').innerHTML = '<span class="loading">⏳ Lendo a nota…</span>';
      $('cart-import-commit').hidden = true;
      importMsg('');
      api('POST', '/import/nota', { pdf_b64: b64 }).then(function(res) {
        if (!res.ok || !res.j || !res.j.ok) {
          $('cart-import-preview').innerHTML = '';
          importMsg((res.j && res.j._error) || 'Não foi possível ler a nota.');
          return;
        }
        st.import = res.j;
        renderImportPreview();
      }).catch(function(err) {
        importMsg('Erro: ' + err.message);
      });
    };
    reader.readAsDataURL(file);
  }

  function knownTickerList() {
    var seen = {};
    (st.tickers || []).forEach(function(t) { seen[t.ticker] = 1; });
    (st.watchlist || []).forEach(function(w) { seen[w.ticker] = 1; });
    ((st.pos && st.pos.positions) || []).forEach(function(p) { seen[p.ticker] = 1; });
    return Object.keys(seen).sort();
  }

  function renderImportPreview() {
    var p = st.import;
    var box = $('cart-import-preview');
    if (!p) return;
    var acc = stAccount(st.level.id);
    var html = '';

    // header facts
    html += '<div class="cart-import-grid">' +
      importCell('Corretora', p.broker + (p.broker_cnpj ? ' · CNPJ ' + p.broker_cnpj : '')) +
      importCell('Nota nº', p.nota + (p.folhas ? ' · folha ' + p.folhas : '')) +
      importCell('Pregão', p.pregao_br) +
      importCell('Cliente', p.client_name + (p.client_cpf ? ' · ' + p.client_cpf : '')) +
      importCell('Conta na corretora', p.account_code || '—') +
      importCell('Destino', '🏦 ' + (acc ? acc.name : '—') +
        ' (usuário ' + esc((userById(acc && acc.user_id) || {}).name || '—') + ')') +
      '</div>';

    // dedup — the same nota in two layouts (XP vs modelo B3) is the
    // same import; refuse BEFORE any write.
    if (p.dedup && p.dedup.imported) {
      var ex = p.dedup.existing || {};
      html += '<div class="cart-import-banner is-error">🚫 <b>Esta nota já foi ' +
        'importada</b>' + (ex.imported_at_br ? ' em ' + esc(ex.imported_at_br) : '') +
        (ex.account_name ? ' para a conta ' + esc(ex.account_name) : '') + '. ' +
        'Use ↩️ Desfazer na lista de notas para reimportar.</div>';
    }

    if ((p.warnings || []).length) {
      html += '<div class="cart-import-banner is-warn">⚠️ ' +
        p.warnings.map(esc).join('<br>⚠️ ') + '</div>';
    }

    // ticker mapping (modelo B3 prints no ticker in the spec)
    var nm = p.needs_mapping || {};
    var keys = Object.keys(nm);
    if (keys.length) {
      html += '<div class="cart-import-map"><h4>🔎 Informe o ticker de cada ' +
        'especificação</h4>' +
        '<datalist id="cart-import-datalist">' + knownTickerList().map(function(tk) {
          return '<option value="' + esc(tk) + '"></option>';
        }).join('') + '</datalist>';
      keys.forEach(function(k, i) {
        var s = nm[k];
        html += '<label class="cart-import-maprow">' +
          '<span class="cart-import-mapsec" title="' + esc(s.market + ' — ' + s.spec) + '">' +
          esc(s.spec) + ' <em>(' + esc(s.market.toLowerCase()) + ')</em></span>' +
          '<input type="text" class="cart-import-mapinput" data-map="' + esc(k) +
          '" list="cart-import-datalist" maxlength="8" placeholder="' +
          esc(s.suggest || 'TICKER') + '" value="' + esc(s.suggest || '') +
          '" style="text-transform: uppercase;" autocomplete="off">' +
          '</label>';
      });
      html += '</div>';
    }

    // options
    var hasFrac = (p.trades || []).some(function(t) { return t.fractional && t.ticker; });
    html += '<div class="cart-import-opts">' +
      '<label class="cart-check"><input type="checkbox" id="cart-import-merge"' +
      (hasFrac ? ' checked' : ' disabled') + '> Unificar fracionário com o lote ' +
      'padrão (KLBN4F → KLBN4 — mesmo papel, PM único)</label>' +
      '<span class="cart-muted">' + (p.pages || '?') + ' página(s) · extração ' +
      esc(p.engine || '?') + '</span></div>';

    // trades table
    html += '<div class="cart-table-wrap"><table class="val-table cart-table">' +
      '<thead><tr><th>Mercado</th><th>Especificação</th><th>Ticker</th>' +
      '<th>C/V</th><th class="th-num">Qtd</th><th class="th-num">Preço</th>' +
      '<th class="th-num">Valor</th><th class="th-num">Taxas</th></tr></thead><tbody id="cart-import-rows">';
    html += importRowsHtml(p, {});
    html += '</tbody></table></div>';
    html += '<p class="cart-note-line">💰 Taxas da nota (R$ ' +
      esc(String(p.fees_total).replace('.', ',')) + ') rateadas pelo valor de cada ' +
      'negócio — a soma fecha exata no centavo.' +
      (p.irrf ? ' IRRF retido: R$ ' + esc(String(p.irrf).replace('.', ',')) +
        ' (não entra nas taxas — compensável no IR anual).' : '') +
      (p.unsupported_count ? ' ⛔ ' + p.unsupported_count +
        ' negócio(s) em mercado não suportado ficam de fora.' : '') + '</p>';

    box.innerHTML = html;

    // live mapping → table ticker cells + spec auto-copy between markets
    box.querySelectorAll('[data-map]').forEach(function(inp) {
      inp.addEventListener('input', function() {
        var k = inp.getAttribute('data-map');
        var v = (inp.value || '').trim().toUpperCase();
        // same spec in another market → copy (VISTA + FRACIONARIO of the
        // same paper are two keys, one ticker)
        var spec = k.split('|').slice(1).join('|');
        box.querySelectorAll('[data-map]').forEach(function(other) {
          var ok2 = other.getAttribute('data-map');
          if (other !== inp && ok2.split('|').slice(1).join('|') === spec && !other.value) {
            other.value = v;
          }
        });
        refreshImportRows();
      });
    });
    var merge = $('cart-import-merge');
    if (merge) merge.addEventListener('change', refreshImportRows);

    var dup = p.dedup && p.dedup.imported;
    var btn = $('cart-import-commit');
    btn.hidden = !!dup;
    btn.textContent = '✅ Importar ' + (p.trades || []).length + ' negócio(s)';
  }

  function importCell(label, valueHtml) {
    return '<div class="cart-import-cell"><span>' + esc(label) + '</span>' +
      '<b>' + (valueHtml || '—') + '</b></div>';
  }

  function importMapping() {
    var map = {};
    document.querySelectorAll('#cart-import-preview [data-map]').forEach(function(inp) {
      map[inp.getAttribute('data-map')] = (inp.value || '').trim().toUpperCase();
    });
    return map;
  }

  function importRowsHtml(p, map) {
    var merge = !!($('cart-import-merge') && $('cart-import-merge').checked);
    return (p.trades || []).map(function(t) {
      var tk = t.ticker;
      if (!tk) tk = map[normSpecKey(t.market, t.spec)] || '';
      if (tk && merge && t.ticker_base && t.ticker !== t.ticker_base) tk = t.ticker_base;
      var ok = /^[A-Z][A-Z0-9]{3,5}\d{1,2}[A-Z]?$/.test(tk);
      return '<tr' + (tk && !ok ? ' class="is-map-bad"' : '') + '>' +
        '<td>' + esc(t.market === 'FRACIONARIO' ? 'Fracionário' : 'À vista') + '</td>' +
        '<td class="cart-name" title="' + esc(t.spec) + '">' + esc(t.spec) + '</td>' +
        '<td class="cart-tk">' + (ok ? esc(tk)
          : (tk ? '<span class="val-neg">' + esc(tk) + '</span>'
                : '<span class="muted">⚠️ mapear</span>')) + '</td>' +
        '<td><span class="cart-type ' + (t.side === 'buy' ? 'is-buy' : 'is-sell') + '">' +
          (t.side === 'buy' ? '✅ C' : '❌ V') + '</span>' + (t.day ? ' ' +
          flagHtml('⏱️', 'Negócio marcado como day trade na nota') : '') + '</td>' +
        '<td class="val-val">' + esc(String(t.qty).replace('.', ',')) + '</td>' +
        '<td class="val-val">' + valNumHtml(moneyStr(t.price)) + '</td>' +
        '<td class="val-val">' + valNumHtml(moneyStr(t.value)) + '</td>' +
        '<td class="val-val">' + valNumHtml(moneyStr(t.fees)) + '</td>' +
        '</tr>';
    }).join('');
  }

  function refreshImportRows() {
    var rows = $('cart-import-rows');
    if (rows && st.import) {
      rows.innerHTML = importRowsHtml(st.import, importMapping());
    }
  }

  function commitImport() {
    var p = st.import;
    if (!p) return;
    var map = importMapping();
    var merge = !!($('cart-import-merge') && $('cart-import-merge').checked);
    var trades = (p.trades || []).map(function(t) {
      var tk = t.ticker;
      if (!tk) tk = map[normSpecKey(t.market, t.spec)] || '';
      if (tk && merge && t.ticker_base && t.ticker !== t.ticker_base) tk = t.ticker_base;
      return { ticker: tk, type: t.side, quantity: t.qty,
               price: t.price, fees: t.fees, date: p.pregao };
    });
    var missing = trades.some(function(t) { return !t.ticker; });
    if (missing) {
      importMsg('Informe o ticker de todas as especificações antes de importar.');
      return;
    }
    var btn = $('cart-import-commit');
    btn.disabled = true;
    btn.textContent = '⏳ Importando…';
    api('POST', '/import/commit', {
      account_id: st.level.id,
      broker: p.broker_short || p.broker, broker_cnpj: p.broker_cnpj,
      nota: p.nota, pregao: p.pregao, client_name: p.client_name,
      fees_total: p.fees_total, irrf: p.irrf, trades: trades,
    }).then(function(res) {
      btn.disabled = false;
      btn.textContent = '✅ Importar';
      if (!res.ok) {
        var j = res.j || {};
        if (j.errors && j.errors.trades) {
          var first = Object.keys(j.errors.trades)[0];
          var fe = j.errors.trades[first];
          var fld = Object.keys(fe)[0];
          importMsg('Negócio ' + (Number(first) + 1) + ': ' + fe[fld]);
        } else {
          importMsg(j._error || 'Erro ao importar.');
        }
        return;
      }
      $('cart-import-modal').close();
      st.pendingNote = {
        text: 'Nota ' + p.nota + ' importada: ' + res.j.created +
              ' negócio(s) em ' + (stAccount(st.level.id) || {}).name + '.',
        until: Date.now() + 15000,
      };
      reload();
    }).catch(function(err) {
      btn.disabled = false;
      btn.textContent = '✅ Importar';
      importMsg('Erro: ' + err.message);
    });
  }

  // ── imported-notas registry (per account) ───────────────────────────────
  function loadNotas() {
    var box = $('cart-notas');
    if (!box || st.level.kind !== 'account') return;
    api('GET', '/import/notas?account_id=' + encodeURIComponent(st.level.id))
      .then(function(res) {
        if (!res.ok || !res.j || !res.j.ok) return;
        renderNotas(res.j.notas || []);
      });
  }

  function renderNotas(notas) {
    var box = $('cart-notas');
    if (!box) return;
    if (!notas.length) {
      box.innerHTML = '';
      return;
    }
    var rows = notas.map(function(n) {
      return '<tr>' +
        '<td class="cart-tk" title="CNPJ ' + esc(n.broker_cnpj) + '">' + esc(n.nota) + '</td>' +
        '<td>' + esc(n.broker || '—') + '</td>' +
        '<td>' + esc(fmtDate(n.pregao)) + '</td>' +
        '<td class="val-val">' + esc(String(n.alive)) + (n.alive !== n.trade_count
            ? ' <span class="muted" title="Negócios da nota que ainda existem (algum foi editado/excluído)">' +
              'de ' + esc(String(n.trade_count)) + '</span>' : '') + '</td>' +
        '<td class="val-val">' + valNumHtml(moneyStr(n.fees_total || 0)) + '</td>' +
        '<td class="val-val">' + (n.irrf ? valNumHtml(moneyStr(n.irrf)) : '<span class="muted">—</span>') + '</td>' +
        '<td class="cart-actions">' +
          '<button class="cart-icon-btn" data-un="' + esc(n.id) +
            '" title="↩️ Desfazer importação (remove os negócios da nota)">↩️</button>' +
        '</td></tr>';
    }).join('');
    box.innerHTML = '<div class="cart-sec-head"><h3>📥 Notas importadas nesta conta</h3></div>' +
      '<div class="cart-table-wrap"><table class="val-table cart-table">' +
      '<thead><tr><th>Nota</th><th>Corretora</th><th>Pregão</th>' +
      '<th class="th-num">Negócios</th><th class="th-num">Taxas</th>' +
      '<th class="th-num">IRRF</th><th></th></tr></thead><tbody>' + rows +
      '</tbody></table></div>' +
      '<p class="cart-note-line">ℹ️ Cada transação importada carrega a etiqueta ' +
      '📝 “NC &lt;nº&gt; · corretora · data”. ↩️ remove TODOS os negócios da nota ' +
      '(transações editadas mantêm as alterações fora da nota… confira o contador).</p>';
  }

  function confirmUndoNota(id) {
    askConfirm('↩️ Desfazer importação',
      'Remover <b>todos os negócios importados</b> desta nota?<br>' +
      '<span class="cart-warn-line">ℹ️ O preço médio e o lucro são recalculados.</span>',
      '↩️ Desfazer', function() {
        api('DELETE', '/import/nota/' + encodeURIComponent(id)).then(function(res) {
          if (!res.ok) window.alert((res.j && res.j._error) || 'Erro ao desfazer.');
          else {
            if (res.j && res.j.warnings && res.j.warnings.length) {
              st.pendingNote = { text: res.j.warnings.join(' '),
                                 until: Date.now() + 15000 };
            }
            reload();
          }
        });
      });
  }

  // ── manage modal (⭐ observados + 📇 cadastro) ──────────────────────────
  function renderManage() {
    var box = $('cart-manage-body');
    var html = '';

    // ⭐ Tickers observados
    html += '<section class="cart-manage-sec"><h4>⭐ Tickers observados no Painel</h4>' +
      '<div class="cart-watch-add">' +
      '<input type="text" id="cart-watch-input" maxlength="8" placeholder="PETR4" ' +
      'style="text-transform: uppercase;" aria-label="Ticker">' +
      '<button class="cart-btn" id="cart-watch-add">➕ Adicionar</button></div>';
    html += st.watchlist.length ? '<ul class="cart-manage-list">' +
      st.watchlist.map(function(w) {
        return '<li><span class="cart-mname">' + esc(w.ticker) + '</span>' +
          '<span class="cart-actions">' +
          '<button class="cart-icon-btn" data-dw="' + esc(w.ticker) +
          '" title="🗑️ Remover dos observados">🗑️</button>' +
          '</span></li>';
      }).join('') + '</ul>'
      : '<p class="cart-muted">💡 Nenhum ticker observado — adicione pelo campo ' +
        'acima ou pela ⭐ na página da empresa.</p>';
    html += '</section>';

    // 📇 Cadastro (ticker metadata)
    html += '<section class="cart-manage-sec"><h4>📇 Cadastro de tickers</h4>' +
      '<p class="cart-muted">💡 Nome e setor vêm do CVM (FCA/CAD) na primeira ' +
      'transação; use 🔄 para buscar de novo.</p>';
    html += st.tickers.length ? '<div class="cart-table-wrap"><table class="val-table">' +
      '<thead><tr><th>Ticker</th><th>Nome</th><th>Setor</th><th></th></tr></thead><tbody>' +
      st.tickers.map(function(t) {
        return '<tr><td class="cart-tk">' + esc(t.ticker) + '</td>' +
          '<td class="cart-name" title="' + esc(t.name) + '">' + esc(t.name || '—') + '</td>' +
          '<td class="cart-sector" title="' + esc(t.sector) + '">' + esc(t.sector || '—') + '</td>' +
          '<td class="cart-actions"><button class="cart-icon-btn" data-rt="' + esc(t.ticker) +
          '" title="🔄 Buscar nome/setor no CVM">🔄</button></td></tr>';
      }).join('') + '</tbody></table></div>'
      : '<p class="cart-muted">Os tickers aparecem aqui após a primeira transação.</p>';
    html += '</section>';

    // [v1.22.3] 🔔 Alertas de preço (roadmap 6) — the form + the live
    // list (fetched async into the placeholder div below).
    html += '<section class="cart-manage-sec"><h4>🔔 Alertas de preço</h4>' +
      '<p class="cart-muted">💡 Aviso quando a cotação cruza o limite — ' +
      'aparece no topo da página da conta (e aqui, com a cotação atual).</p>' +
      '<div class="cart-watch-add">' +
      '<input type="text" id="cart-alert-ticker" maxlength="8" placeholder="PETR4" ' +
      'style="text-transform: uppercase;" aria-label="Ticker do alerta">' +
      '<select id="cart-alert-op" class="cart-select" aria-label="Condição">' +
        '<option value="above">acima de</option>' +
        '<option value="below">abaixo de</option></select>' +
      '<input type="text" id="cart-alert-price" inputmode="decimal" placeholder="0,00" ' +
        'aria-label="Preço" style="max-width: 110px;">' +
      '<button class="cart-btn" id="cart-alert-add">➕ Criar</button></div>' +
      '<div id="cart-alert-list"></div></section>';

    // [v1.22.3] 💾 Backup — export the store JSON / restore from a file
    // (validate-then-swap on the server; the .bak of the current file
    // is automatic).
    html += '<section class="cart-manage-sec"><h4>💾 Backup da carteira</h4>' +
      '<p class="cart-muted">💡 O arquivo é o webui_portfolio.json completo — ' +
      'usuários, contas, transações, alertas e notas importadas.</p>' +
      '<div class="cart-backup-row">' +
      '<button class="cart-btn" id="cart-export-btn">⬇️ Exportar (JSON)</button>' +
      '<button class="cart-btn" id="cart-restore-btn">⬆️ Restaurar arquivo…</button>' +
      '<input type="file" id="cart-restore-file" accept="application/json,.json" hidden>' +
      '</div></section>';

    box.innerHTML = html;

    loadAlertsManage();

    box.querySelectorAll('[data-dw]').forEach(function(b) {
      b.addEventListener('click', function() {
        var tk = b.getAttribute('data-dw');
        // [fix 2] confirmation for the watchlist removal too (it was a
        // one-click silent delete before).
        askConfirm('🗑️ Remover dos observados',
          'Remover <b>' + esc(tk) + '</b> dos Tickers Observados no Painel?',
          '🗑️ Remover', function() {
            api('DELETE', '/watchlist/' + encodeURIComponent(tk))
              .then(function(res) {
                if (!res.ok) $('cart-manage-msg').textContent = (res.j && res.j._error) || 'Erro.';
                else { $('cart-manage-msg').textContent = ''; reload(); }
              });
          });
      });
    });
    box.querySelectorAll('[data-rt]').forEach(function(b) {
      b.addEventListener('click', function() {
        var tk = b.getAttribute('data-rt');
        b.disabled = true; b.textContent = '⏳';
        api('POST', '/tickers/' + encodeURIComponent(tk) + '/refresh', {})
          .then(function() { setTimeout(loadState, 1200); });
      });
    });
    var addBtn = box.querySelector('#cart-watch-add');
    var addInput = box.querySelector('#cart-watch-input');
    function doAddWatch() {
      var v = (addInput.value || '').trim().toUpperCase();
      if (!v) return;
      api('POST', '/watchlist', { ticker: v }).then(function(res) {
        if (!res.ok) {
          $('cart-manage-msg').textContent =
            (res.j && res.j.errors && res.j.errors.ticker) || 'Ticker inválido.';
          return;
        }
        $('cart-manage-msg').textContent = '';
        reload();
      });
    }
    if (addBtn) addBtn.addEventListener('click', doAddWatch);
    if (addInput) addInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); doAddWatch(); }
    });

    // [v1.22.3] Alertas + backup wiring (the sections above).
    wireAlertsManage();
    wireBackupManage();
  }

  // ── [v1.22.3] Gerenciar: the alerts section ────────────────────────────
  function loadAlertsManage() {
    var box = $('cart-alert-list');
    if (!box) return;
    api('GET', '/alerts').then(function(res) {
      if (!res.ok || !res.j || !res.j.ok) {
        box.innerHTML = '<p class="cart-muted">' +
          esc((res.j && (res.j._error || res.j.quotes_note)) || 'Erro') + '</p>';
        return;
      }
      var alerts = res.j.alerts || [];
      if (!alerts.length) {
        box.innerHTML = '<p class="cart-muted">Nenhum alerta — crie o primeiro ' +
          'acima (ex: PETR4 acima de 40).</p>';
        return;
      }
      box.innerHTML = '<div class="cart-table-wrap"><table class="val-table">' +
        '<thead><tr><th>Ticker</th><th>Condição</th><th class="th-num">Limite</th>' +
        '<th class="th-num">Cotação</th><th>Estado</th><th></th></tr></thead><tbody>' +
        alerts.map(function(a) {
          var state = a.triggered === true
            ? '<span class="val-pos">🔔 disparado</span>'
            : (a.triggered === false
                ? '<span class="val-zero">aguardando</span>'
                : '<span class="muted">sem cotação</span>');
          return '<tr><td class="cart-tk">' + esc(a.ticker) + '</td>' +
            '<td>' + (a.op === 'above' ? 'acima de' : 'abaixo de') + '</td>' +
            '<td class="val-val">' + esc(a.price_br || '—') + '</td>' +
            '<td class="val-val">' + esc(a.current || '—') +
              (a.quote_date ? ' <span class="muted">(' + esc(fmtDate(a.quote_date)) + ')</span>' : '') + '</td>' +
            '<td>' + state + '</td>' +
            '<td class="cart-actions"><button class="cart-icon-btn" data-dal="' + esc(a.id) +
              '" title="🗑️ Remover alerta">🗑️</button></td></tr>';
        }).join('') + '</tbody></table></div>';
      box.querySelectorAll('[data-dal]').forEach(function(b) {
        b.addEventListener('click', function() {
          api('DELETE', '/alerts/' + b.getAttribute('data-dal'))
            .then(function() { loadState(); loadAlertsManage(); });
        });
      });
    });
  }

  function wireAlertsManage() {
    var addBtn = $('cart-alert-add');
    if (!addBtn) return;
    var priceEl = $('cart-alert-price');
    brCents(priceEl);
    function doAddAlert() {
      var tk = ($('cart-alert-ticker').value || '').trim().toUpperCase();
      var price = parseBr(priceEl.value);
      api('POST', '/alerts', {
        ticker: tk, op: $('cart-alert-op').value, price: price,
      }).then(function(res) {
        if (!res.ok) {
          $('cart-manage-msg').textContent =
            (res.j && res.j.errors && (res.j.errors.ticker ||
                                       res.j.errors.price)) || 'Alerta inválido.';
          return;
        }
        $('cart-manage-msg').textContent = '';
        $('cart-alert-ticker').value = '';
        priceEl.value = '';
        loadState();
        loadAlertsManage();
      });
    }
    addBtn.addEventListener('click', doAddAlert);
    $('cart-alert-ticker').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); doAddAlert(); }
    });
  }

  // ── [v1.22.3] Gerenciar: export / restore the store ───────────────────
  function wireBackupManage() {
    var exp = $('cart-export-btn');
    if (!exp) return;
    exp.addEventListener('click', function() {
      fetch('/api/webui/portfolio/export')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          var blob = new Blob(
            [JSON.stringify(data, null, 2)],
            { type: 'application/json' });
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = 'webui_portfolio_' + new Date().toISOString().slice(0, 10) +
                       '.json';
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(function() { URL.revokeObjectURL(a.href); }, 5000);
        });
    });
    var fileBtn = $('cart-restore-btn');
    var fileEl = $('cart-restore-file');
    if (!fileBtn || !fileEl) return;
    fileBtn.addEventListener('click', function() { fileEl.click(); });
    fileEl.addEventListener('change', function() {
      var f = this.files && this.files[0];
      this.value = '';
      if (!f) return;
      if (f.size > 20 * 1024 * 1024) {
        $('cart-manage-msg').textContent = 'Arquivo muito grande (limite 20 MB).';
        return;
      }
      var reader = new FileReader();
      reader.onload = function() {
        var payload;
        try { payload = JSON.parse(String(reader.result)); }
        catch (err) {
          $('cart-manage-msg').textContent = 'JSON ilegível: ' + err.message;
          return;
        }
        askConfirm('⬆️ Restaurar carteira',
          'Substituir <b>TODA a carteira atual</b> pelo conteúdo de <b>' +
          esc(f.name) + '</b>?<br>' +
          '<span class="cart-warn-line">⚠️ Usuários, contas, transações, alertas ' +
          'e notas importadas serão trocados pelos do arquivo (o servidor ' +
          'guarda um .bak do atual).</span>',
          '⬆️ Restaurar', function() {
            api('POST', '/restore', payload).then(function(res) {
              if (!res.ok) {
                $('cart-manage-msg').textContent =
                  (res.j && res.j._error) || 'Erro ao restaurar.';
                return;
              }
              $('cart-manage-msg').textContent = '';
              $('cart-manage-modal').close();
              st.level = { kind: 'users' };
              reload();
            });
          });
      };
      reader.readAsText(f);
    });
  }

  // ── ONE delegated click handler for the whole page ─────────────────────
  root.addEventListener('click', function(e) {
    var el = e.target && e.target.closest ? e.target.closest(
      '[data-act],[data-nav],[data-view],[data-eu],[data-du],[data-aw],' +
      '[data-ea],[data-da],[data-qb],[data-qs],[data-et],[data-dt],[data-un],' +
      '[data-pd],[data-dclose],.cart-ucard') : null;
    if (!el) return;

    if (el.hasAttribute('data-act')) {
      var act = el.getAttribute('data-act');
      if (act === 'user') openUserModal();
      else if (act === 'account') openAccountModal();
      else if (act === 'tx') openTxModal();
      else if (act === 'import') openImportModal();
      else if (act === 'sim') openSimModal();   // [v1.22.3] what-if
      else if (act === 'manage') {
        $('cart-manage-msg').textContent = '';
        renderManage();
        $('cart-manage-modal').showModal();
      } else if (act === 'reload') reload();
      return;
    }
    if (el.hasAttribute('data-nav')) {
      goto(el.getAttribute('data-nav'), el.getAttribute('data-id'));
      return;
    }
    if (el.hasAttribute('data-view')) {
      st.view = el.getAttribute('data-view');
      root.querySelectorAll('.cart-pill').forEach(function(p) {
        p.classList.toggle('is-active', p === el);
      });
      // [v1.22.3] five views — the lazy ones fetch on first open.
      var views = { positions: 'cart-positions', txs: 'cart-txs',
                    proventos: 'cart-proventos', perf: 'cart-perf',
                    alloc: 'cart-alloc' };
      Object.keys(views).forEach(function(v) {
        var node = $(views[v]);
        if (node) node.hidden = v !== st.view;
      });
      // [v1.22.4] the notas registry rides the Transações view.
      var notas = $('cart-notas');
      if (notas) notas.hidden = st.view !== 'txs';
      if (st.view === 'txs' && st.txRows === null) loadTxs();
      if (st.view === 'txs') loadNotas();
      if (st.view === 'proventos') loadProventos();
      if (st.view === 'perf') loadPerf();
      if (st.view === 'alloc') loadAlloc();
      return;
    }
    if (el.hasAttribute('data-pd')) { openPositionDetail(el.getAttribute('data-pd')); return; }
    if (el.hasAttribute('data-dclose')) { closeDrawer(); return; }
    if (el.hasAttribute('data-eu')) { openUserModal(el.getAttribute('data-eu')); return; }
    if (el.hasAttribute('data-du')) { confirmDeleteUser(el.getAttribute('data-du')); return; }
    if (el.hasAttribute('data-aw')) { toggleWatchAccount(el.getAttribute('data-aw')); return; }
    if (el.hasAttribute('data-ea')) { openAccountModal(el.getAttribute('data-ea')); return; }
    if (el.hasAttribute('data-da')) { confirmDeleteAccount(el.getAttribute('data-da')); return; }
    if (el.hasAttribute('data-et')) { openTxModal(el.getAttribute('data-et')); return; }
    if (el.hasAttribute('data-dt')) { confirmDeleteTx(el.getAttribute('data-dt')); return; }
    if (el.hasAttribute('data-un')) { confirmUndoNota(el.getAttribute('data-un')); return; }
    if (el.hasAttribute('data-qb')) {
      var q = el.getAttribute('data-qq');
      openTxModal(null, { ticker: el.getAttribute('data-qb'), type: 'buy',
                          qty: q ? parseFloat(q) : '' });
      return;
    }
    if (el.hasAttribute('data-qs')) {
      var q2 = el.getAttribute('data-qq');
      openTxModal(null, { ticker: el.getAttribute('data-qs'), type: 'sell',
                          qty: q2 ? parseFloat(q2) : '' });
      return;
    }
    // Card click (not on a button) → drill in.
    if (el.classList.contains('cart-ucard') && !e.target.closest('button')) {
      if (el.hasAttribute('data-user')) goto('user', el.getAttribute('data-user'));
      else if (el.hasAttribute('data-acc')) goto('account', el.getAttribute('data-acc'));
    }
  });

  root.addEventListener('keydown', function(e) {
    if (e.key !== 'Enter') return;
    var card = e.target && e.target.closest ? e.target.closest('.cart-ucard') : null;
    if (card && e.target === card) {
      if (card.hasAttribute('data-user')) goto('user', card.getAttribute('data-user'));
      else if (card.hasAttribute('data-acc')) goto('account', card.getAttribute('data-acc'));
    }
  });

  // ── boot wiring (static elements) ──────────────────────────────────────
  root.querySelectorAll('dialog.cart-modal').forEach(function(m) {
    m.querySelectorAll('[data-close]').forEach(function(b) {
      b.addEventListener('click', function() { m.close(); });
    });
    // [fix 2] Click OUTSIDE the box (the backdrop) cancels — the classic
    // modal affordance, for every dialog: ➕ Novo usuário, 🏦 Nova conta,
    // ➕/✏️ Transação, ⚙️ Gerenciar and the 🗑️ confirmação. Clicks land on
    // the dialog element itself when they miss the inner form; the
    // mousedown guard keeps a text-selection drag that ends outside
    // from being read as a cancel.
    var downOnDialog = false;
    m.addEventListener('mousedown', function(e) {
      downOnDialog = (e.target === m);
    });
    m.addEventListener('click', function(e) {
      if (e.target === m && downOnDialog) m.close();
    });
  });
  $('cart-user-modal').querySelector('[data-save]').addEventListener('click', saveUser);
  $('cart-account-modal').querySelector('[data-save]').addEventListener('click', saveAccount);
  $('cart-tx-modal').querySelector('[data-save]').addEventListener('click', saveTx);
  // [fix 2] the 🗑️ confirmation's OK runs the stored action
  $('cart-confirm-ok').addEventListener('click', function() {
    var cb = confirmAction;
    confirmAction = null;
    $('cart-confirm-modal').close();
    if (cb) cb();
  });
  $('cart-user-name').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); saveUser(); }
  });

  // BR masks — attached once; the modal is static in the DOM.
  brDateMask($('cart-tx-date'));
  brQtyMask($('cart-tx-qty'));
  brCents($('cart-tx-price'));
  brCents($('cart-tx-fees'));
  ['cart-tx-ticker', 'cart-tx-account'].forEach(function(id) {
    $(id).addEventListener('input', function() { updatePosCtx(); });
  });
  // [v1.22.3] type switch flips the corp fields; the action preset
  // primes the factor input (split 2 / group 0,5 / bonus 1,1).
  // [v1.22.4] the placeholder option clears the factor — the event is
  // chosen FIRST, the factor after (the instructions explain both).
  $('cart-tx-type').addEventListener('change', function() {
    toggleCorpFields($('cart-tx-type').value === 'corp');
    updateHints();
  });
  $('cart-tx-action').addEventListener('change', function() {
    var a = $('cart-tx-action').value;
    $('cart-tx-factor').value = a === 'group' ? '0,5'
      : (a === 'bonus' ? '1,1' : (a === 'split' ? '2' : ''));
    updateHints();
  });
  $('cart-tx-factor').addEventListener('input', updateHints);
  $('cart-tx-ticker').addEventListener('input', function() {
    updatePosCtx();
    updateHints();
  });

  // [v1.22.2] nota import — the file input and commit button are static
  // in the template; the preview inside is re-rendered per file.
  $('cart-import-file').addEventListener('change', function() {
    readImportFile(this.files && this.files[0]);
  });
  $('cart-import-commit').addEventListener('click', commitImport);

  // [v1.22.4] 🔍 drawer — a click OUTSIDE it (or Esc) closes. The
  // opener button [data-pd] is excluded (it re-opens); clicks inside
  // any open <dialog> are the modal's business, not the drawer's.
  document.addEventListener('click', function(e) {
    var drawer = $('cart-drawer');
    if (!drawer || drawer.hidden || !drawer.classList.contains('open')) return;
    if (drawer.contains(e.target)) return;
    if (e.target.closest && e.target.closest('[data-pd]')) return;
    if (e.target.closest && e.target.closest('dialog[open]')) return;
    closeDrawer();
  });
  document.addEventListener('keydown', function(e) {
    if (e.key !== 'Escape') return;
    if (document.querySelector('dialog[open]')) return;
    var drawer = $('cart-drawer');
    if (drawer && !drawer.hidden && drawer.classList.contains('open')) {
      closeDrawer();
    }
  });

  reload();
}

// ── [v1.21 fix 1] Painel widget — ⭐ Tickers Observados (its OWN box,
// first — it is NOT part of Minhas Carteiras) then 💼 Minhas Carteiras
// (contas observadas grouped by user, per-user subtotals — never across
// users). The old single "Minhas Carteiras" box mixed both. ─────────────
function loadPortfolioWidget(force) {
  var box = document.getElementById('home-portfolio');
  if (!box || (box._booted && !force)) return;
  box._booted = true;
  fetch('/api/webui/portfolio/overview?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d || d._error || !d.has_data) { box.innerHTML = ''; return; }
      var html = '';

      // ⭐ Tickers observados — own box, FIRST.
      // [v1.28.3] the ⭐ Máx/Mín 52 sem columns join the table ("add
      // more info like max and min 52 weeks") and "Gerenciar" opens
      // the ⚙️ box IN the Painel (data-hm-open="watch" → the modal's ⭐
      // section) — the old link detoured through /webui/carteira
      // ("clicking from painel Gerenciar goes to …/carteira / it should
      // open a management box to do it in painel, not in carteira").
      // The row read: SETOR after the name; each pair closed by its
      // variation — Mín (dia) · Máx (dia) · Var. (dia), then Mín (52) ·
      // Máx (52) · Var. (52) (the 52s Mín-first, wearing parentheses).
      // Every min/max stays PLAIN (the main-price-only rule — only the
      // Preço wears the band pill).
      if (d.tickers && d.tickers.length) {
        html += '<div class="cart-widget"><div class="cart-widget-head"><h2>⭐ Tickers Observados' +
          (d.session_date ? ' <span class="cart-widget-sub">· pregão ' + esc(d.session_date) + '</span>' : '') +
          '</h2><button type="button" class="cart-widget-link hm-open-btn" data-hm-open="watch">⚙️ Gerenciar ⭐</button></div>';
        if (d.quotes_note) html += '<div class="home-note">' + esc(d.quotes_note) + '</div>';
        html += '<div class="cart-table-wrap"><table class="val-table"><thead><tr><th>Ticker</th><th>Nome</th><th>Setor</th>' +
          '<th class="th-num">Preço</th>' +
          '<th class="th-num">Mín (dia)</th><th class="th-num">Máx (dia)</th><th class="th-num">Var. (dia)</th>' +
          '<th class="th-num">Mín (52)</th><th class="th-num">Máx (52)</th><th class="th-num">Var. (52)</th></tr></thead><tbody>' +
          d.tickers.map(function(t) {
            var v = t.variation;
            var cls = v && v.charAt(0) === '-' ? 'val-neg'
                    : (v && v.charAt(0) === '+' ? 'val-pos' : 'val-zero');
            // The Preço (the row's MAIN price) wears the band pill —
            // Máx/Mín (dia/52) stay plain ("if it has multiple prices
            // like min, max… just apply to main price").
            var priceCell = t.price_pill
              ? homePricePill(t.price_pill, t.price)
              : valNumHtml(t.price);
            // Setor — the CVM/FCA sector cached in the cadastro
            // (ellipsized at 170px, the full text on hover); the day's
            // Mín/Máx ride the quote's OWN session high/low.
            var setorCell = t.sector
              ? '<td class="cart-sector" title="' + esc(t.sector) + '">' + esc(t.sector) + '</td>'
              : '<td class="cart-sector"><span class="muted">—</span></td>';
            // Var. (52) — the 52-week variation (the window's first
            // close vs the last), colored like the day one.
            var v52 = t.var_52;
            var cls52 = v52 && v52.charAt(0) === '-' ? 'val-neg'
                      : (v52 && v52.charAt(0) === '+' ? 'val-pos' : 'val-zero');
            return '<tr><td class="cart-tk"><a href="/webui/company/' +
              encodeURIComponent(t.ticker) + '">' + esc(t.ticker) + '</a></td>' +
              '<td class="cart-name" title="' + esc(t.name) + '">' + esc(t.name) + '</td>' +
              setorCell +
              '<td class="val-val">' + priceCell + '</td>' +
              '<td class="val-val">' + (t.low_day ? valNumHtml(t.low_day) : '<span class="muted">—</span>') + '</td>' +
              '<td class="val-val">' + (t.high_day ? valNumHtml(t.high_day) : '<span class="muted">—</span>') + '</td>' +
              '<td class="val-val"><span class="' + cls + '">' + esc(v || '—') + '</span></td>' +
              '<td class="val-val">' + (t.low_52 ? valNumHtml(t.low_52) : '<span class="muted">—</span>') + '</td>' +
              '<td class="val-val">' + (t.high_52 ? valNumHtml(t.high_52) : '<span class="muted">—</span>') + '</td>' +
              '<td class="val-val">' + (v52 ? '<span class="' + cls52 + '">' + esc(v52) + '</span>' : '<span class="muted">—</span>') + '</td></tr>';
          }).join('') + '</tbody></table></div></div>';
      }

      // 💼 Minhas Carteiras — contas observadas, grouped by user.
      if (d.groups && d.groups.length) {
        html += '<div class="cart-widget"><div class="cart-widget-head"><h2>💼 Minhas Carteiras' +
          (d.session_date ? ' <span class="cart-widget-sub">· pregão ' + esc(d.session_date) + '</span>' : '') +
          '</h2><a class="cart-widget-link" href="/webui/carteira">Abrir carteira →</a></div>';
        if (d.quotes_note) html += '<div class="home-note">' + esc(d.quotes_note) + '</div>';
        d.groups.forEach(function(g) {
          html += '<div class="cart-widget-block"><h3>👤 ' + esc(g.user) + '</h3>' +
            '<table class="val-table"><thead><tr><th>Conta</th>' +
            '<th class="th-num">Patrimônio</th><th class="th-num">Lucro $</th>' +
            '<th class="th-num">Lucro %</th></tr></thead><tbody>';
          (g.accounts || []).forEach(function(a) {
            var pct = a.profit_pct;
            var cls = pct && pct.charAt(0) === '-' ? 'val-neg'
                    : (pct && pct.charAt(0) === '+' ? 'val-pos' : 'val-zero');
            html += '<tr class="cart-wrow" data-acc="' + esc(a.id) + '" ' +
              'title="Abrir esta conta na Carteira">' +
              '<td class="cart-name" title="' + esc(a.label) + '">' + esc(a.label) + '</td>' +
              '<td class="val-val">' + valNumHtml(a.value) + '</td>' +
              '<td class="val-val">' + valNumHtml(a.profit) + '</td>' +
              '<td class="val-val"><span class="' + cls + '">' + esc(pct || '—') + '</span></td></tr>';
          });
          if (g.subtotal) {
            var s = g.subtotal;
            var scls = s.profit_pct && s.profit_pct.charAt(0) === '-' ? 'val-neg'
                     : (s.profit_pct && s.profit_pct.charAt(0) === '+' ? 'val-pos' : 'val-zero');
            html += '<tr class="cart-subrow">' +
              '<td class="cart-name">Σ ' + esc(s.label) + '</td>' +
              '<td class="val-val">' + valNumHtml(s.value) + '</td>' +
              '<td class="val-val">' + valNumHtml(s.profit) + '</td>' +
              '<td class="val-val"><span class="' + scls + '">' + esc(s.profit_pct || '—') + '</span></td></tr>';
          }
          html += '</tbody></table></div>';
        });
        html += '</div>';
      }

      box.innerHTML = html;
      box.querySelectorAll('[data-acc]').forEach(function(tr) {
        tr.addEventListener('click', function() {
          // [fix 2] ONE-SHOT deep link: entering Carteira via the
          // sidebar always lands on 👥 Usuários now — only this click
          // drills straight into the account (sessionStorage key,
          // consumed by readLevel on the next boot).
          try {
            sessionStorage.setItem('webui_carteira_goto',
              'account:' + tr.getAttribute('data-acc'));
          } catch (err) {}
          window.location.href = '/webui/carteira';
        });
      });
    })
    .catch(function() { box.innerHTML = ''; });
}

// ═════════════════════════════════════════════════════════════════════════
// ── [v1.28.3] ⚙️ Gerenciar Painel — the settings box ─────────────────────
// The icon in the Painel's TOP-RIGHT corner ("make management box with
// icon in the top right corner to settle painel settings") opens a modal
// with the three managed things:
//   📊 KPIs de tickers   home.ticker_kpis — arrange (▲▼) / add / remove,
//                        ANY share-like instrument (ações, FIIs, ETFs,
//                        BDRs) — the quote cards render in their OWN
//                        medium-sized grid between the macro KPIs and
//                        the rankings.
//   📈 KPIs macro       [v1.28.3] home.kpis — the FIRST set (the
//                        small boxes): which catalog entries show and in
//                        what ORDER, with the hidden options below (+
//                        to add) — the Mercado families' new KPIs live
//                        there (CDI, Meta Selic, INPC, Poupança).
//   🃏 Cards de ranking  home.cards — which boxes show (☑) and in what
//                        ORDER (▲▼); the hidden ones wait below with a
//                        + to come back (at the end of the row).
//   ⭐ Tickers Observados the watchlist — managed IN the Painel now (the
//                        old "Gerenciar" link detoured through Carteira).
// Every mutation saves IMMEDIATELY (the carteira manage-modal precedent
// — no dirty-state concept) and the Painel reloads behind the modal:
// _homeReq is reset so loadHomeData() refetches, and the memo key on
// the server (kpis + ticker_kpis + cards) busts the 60s payload cache.
// ═════════════════════════════════════════════════════════════════════════
var _HM_TICKER_RE = /^[A-Z]{4,6}\d{1,2}[A-Z]?$/;   // validators.TICKER_RE

function initHomeManage() {
  var btn = document.getElementById('home-manage-btn');
  var dlg = document.getElementById('home-manage-modal');
  if (!btn || !dlg || dlg._booted) return;
  dlg._booted = true;

  var st = { kpiKeys: [], kpiCatalog: [], kpis: [], cards: [], catalog: [],
             watch: [], loaded: false, loadError: false };

  function msg(text) {
    var el = document.getElementById('home-manage-msg');
    if (el) el.textContent = text || '';
  }

  function refreshPainel() {
    // settings changed → the memo key changed → force the refetch
    _homeReq = null;
    loadHomeData();
    loadPortfolioWidget(true);
  }

  function saveLayout() {
    fetch('/api/webui/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        'home.kpis': st.kpiKeys,
        'home.ticker_kpis': st.kpis,
        'home.cards': st.cards,
      }),
    })
      .then(function(r) { return r.json(); })
      .then(function(j) {
        if (!j || !j.ok) {
          msg((j && j.errors &&
               (j.errors['home.kpis'] || j.errors['home.ticker_kpis'] ||
                j.errors['home.cards'])) ||
              'Erro ao salvar.');
          return;
        }
        msg('✅ Salvo');
        refreshPainel();
      })
      .catch(function() { msg('Erro ao salvar.'); });
  }

  function title(key) {
    for (var i = 0; i < st.catalog.length; i++) {
      if (st.catalog[i].key === key) return st.catalog[i].title;
    }
    return key;
  }

  // [v1.28.3] the macro-KPI catalog lookup (📈)
  function kpiTitle(key) {
    for (var i = 0; i < st.kpiCatalog.length; i++) {
      if (st.kpiCatalog[i].key === key) return st.kpiCatalog[i].title;
    }
    return key;
  }

  function moveBtns(list, i, attr) {
    return '<button class="cart-icon-btn" data-hm-up="' + attr + i + '"' +
        (i === 0 ? ' disabled' : '') + ' title="▲ Mover para cima">▲</button>' +
      '<button class="cart-icon-btn" data-hm-down="' + attr + i + '"' +
        (i === list.length - 1 ? ' disabled' : '') +
        ' title="▼ Mover para baixo">▼</button>';
  }

  function render() {
    var body = document.getElementById('home-manage-body');
    if (!body) return;
    // A failed settings load must NOT render empty lists — the next
    // mutation would save them and wipe the user's layout.
    if (st.loadError) {
      body.innerHTML = '<p class="cart-muted">⚠️ Não foi possível carregar ' +
        'as configurações — feche e abra de novo.</p>';
      return;
    }
    var h = '';

    // 📈 KPIs macro — [v1.28.3] the FIRST set: which macro cards
    // show and in what order; the hidden catalog options below (+ to
    // add — the Mercado families' new KPIs live there).
    var hiddenKpis = st.kpiCatalog
      .map(function(c) { return c.key; })
      .filter(function(k) { return st.kpiKeys.indexOf(k) < 0; });
    h += '<section class="cart-manage-sec" data-hm-sec="macro"><h4>📈 KPIs macro</h4>' +
      '<p class="cart-muted">💡 Os KPIs do topo do Painel, em ordem — as ' +
      'opções novas vêm das famílias do Mercado: CDI e Meta Selic ' +
      '(Juros), INPC (Inflação) e Poupança.</p>';
    h += st.kpiKeys.length
      ? '<ul class="cart-manage-list">' + st.kpiKeys.map(function(k, i) {
          return '<li><label class="hm-card-label">' +
            '<input type="checkbox" checked data-hm-macro="' + esc(k) + '">' +
            '<span class="cart-mname">' + esc(kpiTitle(k)) + '</span></label>' +
            '<span class="cart-actions">' + moveBtns(st.kpiKeys, i, 'm') +
            '<button class="cart-icon-btn" data-hm-del-m="' + i +
            '" title="🗑️ Ocultar KPI">🗑️</button></span></li>';
        }).join('') + '</ul>'
      : '<p class="cart-muted">Nenhum KPI — o Painel abre direto nos cards ' +
        'de tickers.</p>';
    if (hiddenKpis.length) {
      h += '<div class="hm-hidden-row"><span class="hm-hidden-title">Ocultos:</span>' +
        hiddenKpis.map(function(k) {
          return '<button class="cart-btn hm-enable" data-hm-showm="' + esc(k) +
            '" title="Mostrar no Painel">+ ' + esc(kpiTitle(k)) + '</button>';
        }).join('') + '</div>';
    }
    h += '</section>';

    // 📊 KPIs de tickers
    h += '<section class="cart-manage-sec" data-hm-sec="kpis"><h4>📊 KPIs de tickers</h4>' +
      '<p class="cart-muted">💡 Cards de cotação (tamanho médio, na própria ' +
      'faixa entre os KPIs macro e os rankings) — ações, FIIs, ETFs e ' +
      'BDRs (ex.: PETR4, HGBS11, BOVA11, AAPL34).</p>' +
      '<div class="cart-watch-add">' +
      '<input type="text" id="hm-kpi-input" maxlength="8" placeholder="PETR4" ' +
      'style="text-transform: uppercase;" aria-label="Ticker do KPI">' +
      '<button class="cart-btn" id="hm-kpi-add">➕ Adicionar</button></div>';
    h += st.kpis.length
      ? '<ul class="cart-manage-list">' + st.kpis.map(function(tk, i) {
          return '<li><span class="cart-mname cart-tk">' + esc(tk) + '</span>' +
            '<span class="cart-actions">' + moveBtns(st.kpis, i, 'k') +
            '<button class="cart-icon-btn" data-hm-del-k="' + i +
            '" title="🗑️ Remover KPI">🗑️</button></span></li>';
        }).join('') + '</ul>'
      : '<p class="cart-muted">💡 Nenhum KPI — adicione um ticker acima.</p>';
    h += '</section>';

    // 🃏 Cards de ranking — the visible ones (order + uncheck) then the
    // hidden ones (a + re-enables, at the end of the row).
    var hidden = st.catalog
      .map(function(c) { return c.key; })
      .filter(function(k) { return st.cards.indexOf(k) < 0; });
    h += '<section class="cart-manage-sec" data-hm-sec="cards"><h4>🃏 Cards de ranking</h4>' +
      '<p class="cart-muted">💡 Marque as caixas que aparecem no Painel e ' +
      'ordene com ▲▼ — cada mudança salva na hora.</p>';
    h += st.cards.length
      ? '<ul class="cart-manage-list">' + st.cards.map(function(k, i) {
          return '<li><label class="hm-card-label">' +
            '<input type="checkbox" checked data-hm-card="' + esc(k) + '">' +
            '<span class="cart-mname">' + esc(title(k)) + '</span></label>' +
            '<span class="cart-actions">' + moveBtns(st.cards, i, 'c') +
            '<button class="cart-icon-btn" data-hm-del-c="' + i +
            '" title="🗑️ Ocultar card">🗑️</button></span></li>';
        }).join('') + '</ul>'
      : '<p class="cart-muted">Nenhuma caixa visível — o Painel mostra só ' +
        'os KPIs de tickers.</p>';
    if (hidden.length) {
      h += '<div class="hm-hidden-row"><span class="hm-hidden-title">Ocultas:</span>' +
        hidden.map(function(k) {
          return '<button class="cart-btn hm-enable" data-hm-show="' + esc(k) +
            '" title="Mostrar no Painel">+ ' + esc(title(k)) + '</button>';
        }).join('') + '</div>';
    }
    h += '</section>';

    // ⭐ Tickers Observados — the watchlist, IN the Painel
    h += '<section class="cart-manage-sec" data-hm-sec="watch"><h4>⭐ Tickers Observados</h4>' +
      '<p class="cart-muted">💡 Os tickers acompanhados no Painel — com ' +
      'cotação, variação do dia e máx/mín de 52 semanas.</p>' +
      '<div class="cart-watch-add">' +
      '<input type="text" id="hm-watch-input" maxlength="8" placeholder="PETR4" ' +
      'style="text-transform: uppercase;" aria-label="Ticker observado">' +
      '<button class="cart-btn" id="hm-watch-add">➕ Adicionar</button></div>';
    h += st.watch.length
      ? '<ul class="cart-manage-list">' + st.watch.map(function(tk) {
          return '<li><span class="cart-mname cart-tk">' + esc(tk) + '</span>' +
            '<span class="cart-actions">' +
            '<button class="cart-icon-btn" data-hm-del-w="' + esc(tk) +
            '" title="🗑️ Remover dos observados">🗑️</button></span></li>';
        }).join('') + '</ul>'
      : '<p class="cart-muted">💡 Nenhum ticker observado — adicione acima ' +
        'ou pela ⭐ na página da empresa.</p>';
    h += '</section>';

    body.innerHTML = h;
  }

  // ── state loaders ─────────────────────────────────────────────────────
  function loadState(cb) {
    var jobs = 3;
    st.loadError = false;
    function done() { if (--jobs === 0) { st.loaded = true; if (cb) cb(); } }
    fetch('/api/webui/settings?_t=' + Date.now())
      .then(function(r) { return r.json(); })
      .then(function(j) {
        var vals = {};
        (j && j.sections || []).forEach(function(s) {
          (s.settings || []).forEach(function(x) { vals[x.key] = x.value; });
        });
        // [v1.28.3] home.kpis joined (the 📈 macro list)
        st.kpiKeys = (vals['home.kpis'] || []).map(String);
        st.kpis = (vals['home.ticker_kpis'] || []).map(String);
        st.cards = (vals['home.cards'] || []).map(String);
        done();
      })
      .catch(function() { st.loadError = true; done(); });
    // [v1.28.3] BOTH catalogs (cards + macro KPIs) ride the same
    // home payload — warm from the pane's own load, one fetch cold.
    var cat = (window._homeData && window._homeData.card_catalog) || null;
    var kcat = (window._homeData && window._homeData.kpi_catalog) || null;
    if (cat && cat.length) {
      st.catalog = cat;
      st.kpiCatalog = kcat && kcat.length ? kcat : [];
      done();
    } else {
      fetch('/api/webui/home?_t=' + Date.now())
        .then(function(r) { return r.json(); })
        .then(function(d) {
          st.catalog = d.card_catalog || [];
          st.kpiCatalog = d.kpi_catalog || [];
          done();
        })
        .catch(function() { st.catalog = []; st.kpiCatalog = []; done(); });
    }
    fetch('/api/webui/portfolio/state?_t=' + Date.now())
      .then(function(r) { return r.json(); })
      .then(function(s) {
        st.watch = (s.watchlist || []).map(function(w) { return w.ticker; });
        done();
      })
      .catch(function() { st.watch = []; done(); });
  }

  function reloadWatch(cb) {
    fetch('/api/webui/portfolio/state?_t=' + Date.now())
      .then(function(r) { return r.json(); })
      .then(function(s) {
        st.watch = (s.watchlist || []).map(function(w) { return w.ticker; });
        if (cb) cb();
      })
      .catch(function() { if (cb) cb(); });
  }

  function addTicker(list, value) {
    var v = (value || '').trim().toUpperCase();
    if (!v) return null;
    if (!_HM_TICKER_RE.test(v)) return 'Ticker inválido — use o padrão B3 (ex: PETR4, BOVA11).';
    if (list.indexOf(v) >= 0) return v + ' já está na lista.';
    list.push(v);
    return null;
  }

  // ── one delegated listener for the whole body (re-rendered per change) ──
  var body = document.getElementById('home-manage-body');
  body.addEventListener('click', function(e) {
    var t = e.target && e.target.closest ? e.target.closest('button') : null;
    if (!t) return;
    var i, k, touched = false;
    if (t.id === 'hm-kpi-add') {
      var err = addTicker(st.kpis, (document.getElementById('hm-kpi-input') || {}).value);
      if (err) { msg(err); return; }
      touched = true;
    } else if (t.id === 'hm-watch-add') {
      var wv = ((document.getElementById('hm-watch-input') || {}).value || '').trim().toUpperCase();
      if (!wv) return;
      if (!_HM_TICKER_RE.test(wv)) { msg('Ticker inválido — use o padrão B3 (ex: PETR4, BOVA11).'); return; }
      if (st.watch.indexOf(wv) >= 0) { msg(wv + ' já está na lista.'); return; }
      fetch('/api/webui/portfolio/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: wv }),
      })
        .then(function(r) { return r.json(); })
        .then(function(j) {
          if (!j || !j.ok) {
            msg((j && j.errors && j.errors.ticker) || 'Ticker inválido.');
            return;
          }
          msg('✅ ' + wv + ' adicionado aos observados');
          reloadWatch(function() { render(); loadPortfolioWidget(true); });
        })
        .catch(function() { msg('Erro ao adicionar.'); });
      return;
    } else if (t.hasAttribute('data-hm-up') || t.hasAttribute('data-hm-down')) {
      // attr value: 'k<idx>' (kpis), 'c<idx>' (cards) or 'm<idx>' (macro)
      var down = t.hasAttribute('data-hm-down');
      var attr = t.getAttribute('data-hm-up') !== null ? 'data-hm-up' : 'data-hm-down';
      var prefix = t.getAttribute(attr).charAt(0);
      var list = prefix === 'k' ? st.kpis : (prefix === 'm' ? st.kpiKeys : st.cards);
      var idx = parseInt(t.getAttribute(attr).slice(1), 10);
      var to = down ? idx + 1 : idx - 1;
      if (to < 0 || to >= list.length) return;
      var tmp = list[idx]; list[idx] = list[to]; list[to] = tmp;
      touched = true;
    } else if (t.hasAttribute('data-hm-del-k')) {
      i = parseInt(t.getAttribute('data-hm-del-k'), 10);
      st.kpis.splice(i, 1);
      touched = true;
    } else if (t.hasAttribute('data-hm-del-m')) {
      // [v1.28.3] hide a macro KPI (the 📈 list)
      i = parseInt(t.getAttribute('data-hm-del-m'), 10);
      st.kpiKeys.splice(i, 1);
      touched = true;
    } else if (t.hasAttribute('data-hm-showm')) {
      // [v1.28.3] re-enable a hidden macro KPI (at the end)
      k = t.getAttribute('data-hm-showm');
      if (st.kpiKeys.indexOf(k) < 0) { st.kpiKeys.push(k); touched = true; }
    } else if (t.hasAttribute('data-hm-del-c')) {
      i = parseInt(t.getAttribute('data-hm-del-c'), 10);
      st.cards.splice(i, 1);
      touched = true;
    } else if (t.hasAttribute('data-hm-show')) {
      k = t.getAttribute('data-hm-show');
      if (st.cards.indexOf(k) < 0) { st.cards.push(k); touched = true; }
    } else if (t.hasAttribute('data-hm-del-w')) {
      var wt = t.getAttribute('data-hm-del-w');
      fetch('/api/webui/portfolio/watchlist/' + encodeURIComponent(wt),
            { method: 'DELETE' })
        .then(function(r) { return r.json(); })
        .then(function(j) {
          if (!j || !j.ok) { msg((j && j._error) || 'Erro.'); return; }
          msg('✅ ' + wt + ' removido dos observados');
          reloadWatch(function() { render(); loadPortfolioWidget(true); });
        })
        .catch(function() { msg('Erro ao remover.'); });
      return;
    }
    if (touched) { msg(''); render(); saveLayout(); }
  });

  body.addEventListener('change', function(e) {
    var cb = e.target;
    if (!cb || !cb.hasAttribute) return;
    // [v1.28.3] the macro-KPI checkboxes (📈) share the flow
    if (cb.hasAttribute('data-hm-macro')) {
      var mk = cb.getAttribute('data-hm-macro');
      if (!cb.checked) {
        var mi = st.kpiKeys.indexOf(mk);
        if (mi >= 0) st.kpiKeys.splice(mi, 1);
      } else if (st.kpiKeys.indexOf(mk) < 0) {
        st.kpiKeys.push(mk);
      }
      msg(''); render(); saveLayout();
      return;
    }
    if (!cb.hasAttribute('data-hm-card')) return;
    var k = cb.getAttribute('data-hm-card');
    if (!cb.checked) {
      var i = st.cards.indexOf(k);
      if (i >= 0) st.cards.splice(i, 1);
    } else if (st.cards.indexOf(k) < 0) {
      st.cards.push(k);
    }
    msg(''); render(); saveLayout();
  });

  // Enter in the add inputs = the ➕ button
  body.addEventListener('keydown', function(e) {
    if (e.key !== 'Enter') return;
    if (e.target && e.target.id === 'hm-kpi-input') {
      e.preventDefault();
      var b = document.getElementById('hm-kpi-add');
      if (b) b.click();
    } else if (e.target && e.target.id === 'hm-watch-input') {
      e.preventDefault();
      var wb = document.getElementById('hm-watch-add');
      if (wb) wb.click();
    }
  });

  function open(sec) {
    if (typeof dlg.showModal !== 'function') return;
    dlg.showModal();
    msg('');
    loadState(function() {
      render();
      if (sec) {
        var el = dlg.querySelector('[data-hm-sec="' + sec + '"]');
        if (el) el.scrollIntoView({ block: 'start' });
      }
    });
  }

  btn.addEventListener('click', function() { open(); });

  // The widget's "⚙️ Gerenciar ⭐" button (rendered async by
  // loadPortfolioWidget) — delegation, the same pattern as the syslog.
  document.body.addEventListener('click', function(e) {
    var b = e.target && e.target.closest
      ? e.target.closest('[data-hm-open]') : null;
    if (!b) return;
    open(b.getAttribute('data-hm-open') || undefined);
  });

  // Fechar + the classic backdrop cancel (the carteira modal pattern)
  dlg.querySelectorAll('[data-close]').forEach(function(b) {
    b.addEventListener('click', function() { dlg.close(); });
  });
  var downOnDialog = false;
  dlg.addEventListener('mousedown', function(e) { downOnDialog = (e.target === dlg); });
  dlg.addEventListener('click', function(e) {
    if (e.target === dlg && downOnDialog) dlg.close();
  });
}

// ── [v1.21 fix 1] Company page — the ⭐ watch button (tab bar, every tab
// including Visão Geral). Toggles the ticker in/out of the Painel's
// Tickers Observados; state boots from GET /state (light, no compute). ──
function initCompanyWatch() {
  var btn = document.getElementById('company-watch-star');
  if (!btn || btn._booted) return;
  btn._booted = true;
  var ticker = (btn.getAttribute('data-ticker') || '').toUpperCase();
  if (!ticker) return;

  function paint(on) {
    btn.textContent = on ? '⭐' : '☆';
    btn.classList.toggle('is-on', on);
    btn.title = on
      ? '⭐ Remover ' + ticker + ' dos Tickers Observados'
      : '☆ Adicionar ' + ticker + ' aos Tickers Observados (Painel)';
    btn.setAttribute('aria-label', btn.title);
  }

  fetch('/api/webui/portfolio/state?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(st) {
      if (!st || st._error) return;
      var on = (st.watchlist || []).some(function(w) {
        return (w.ticker || '').toUpperCase() === ticker;
      });
      paint(on);
      btn.addEventListener('click', function() {
        on = !on;
        paint(on);
        var call = on
          ? fetch('/api/webui/portfolio/watchlist', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ ticker: ticker }),
            })
          : fetch('/api/webui/portfolio/watchlist/' + encodeURIComponent(ticker),
              { method: 'DELETE' });
        call.then(function(r) { return r.json(); })
          .then(function(j) {
            if (!j || !j.ok) { on = !on; paint(on); }
          })
          .catch(function() { on = !on; paint(on); });
      });
    })
    .catch(function() { /* portfolio API down — the star stays inert */ });
}

// ── Auto-init after HTMX settle ──
function initApp() {
  // [v1.5] htmx.config.includeScriptTags = true is GONE — it disabled
  // HTMX's script sandbox (injected <script> tags in swapped content ran;
  // combined with the old reflected-XSS paths that was zero-click XSS).
  // The company page now bootstraps from data attributes (initCompanyPage).

  // Chart lifecycle: destroy Chart.js instances in every element HTMX is
  // about to remove (tab switches used to leak them — resize observers +
  // rAF loops kept running on detached canvases).
  document.body.addEventListener('htmx:beforeCleanupElement', function(evt) {
    destroyChartsIn(evt.target);
  });

  // Failed HTMX swaps now show a message in the target (the old handler
  // only console.error'd — the identity card spun "Carregando…" forever
  // when /header 500'd).
  document.body.addEventListener('htmx:responseError', function(evt) {
    console.error('HTMX error:', evt.detail);
    var tgt = evt.detail && evt.detail.target;
    if (tgt && tgt.innerHTML !== undefined) {
      var code = evt.detail.xhr ? evt.detail.xhr.status : 0;
      tgt.innerHTML = '<div class="error">Falha ao carregar' + (code ? ' (HTTP ' + code + ')' : '') + '.</div>';
    }
  });

  // [v1.19] The Painel's bottom sync box refreshes every 30s (freshness
  // rows + fresh "Sincronizar" buttons after a click) — but hx-swap
  // replaces the whole <details>, collapsing an expanded box every cycle.
  // Remember the open state across swaps (the box starts collapsed; this
  // only preserves what the user opened).
  document.body.addEventListener('htmx:beforeSwap', function(evt) {
    var tgt = evt.target;
    if (tgt && tgt.classList && tgt.classList.contains('sync-box-slot')) {
      var box = tgt.querySelector('.sync-box');
      tgt._syncBoxOpen = !!(box && box.open);
    }
  });
  document.body.addEventListener('htmx:afterSwap', function(evt) {
    var tgt = evt.target;
    if (tgt && tgt.classList && tgt.classList.contains('sync-box-slot') &&
        tgt._syncBoxOpen) {
      var box = tgt.querySelector('.sync-box');
      if (box) box.open = true;
    }
  });

  document.body.addEventListener('htmx:afterSettle', function() {
    // Candlestick (Visão Geral tab)
    var canvas = document.getElementById('price-chart');
    if (canvas && !canvas._initialized) {
      canvas._initialized = true;
      var t = canvas.getAttribute('data-ticker');
      var r = canvas.getAttribute('data-range') || '1A';
      if (t) loadCandlestick(t, r);
    }
    // First (active) subtab of each tab — the rest load on click.
    loadPrecoSubtab('cotacao');
    loadFinSubtab('visao_geral');
    loadValSubtab('overview');
    loadProvSubtab('overview');
    // [v1.8] Opções — first subtab of the options tab (loads on settle,
    // same pattern as the other lazy tabs; the shell no-ops elsewhere).
    loadOptSubtab('overview');
    // [v1.9] Acionistas — first subtab of the shareholders tab.
    loadShSubtab('overview');
    // [v1.10] Insiders — first subtab of the insiders tab.
    loadInsSubtab('overview');
    // [v1.24] Histórico — first subtab of the historical tab (the
    // KPI row + heatmap; the heavy 5A charts load on subtab click).
    loadHistSubtab('overview');
    // [v1.26] Governança — first subtab (CGVN KPIs + donut + evolução;
    // Práticas loads on subtab click).
    loadGovSubtab('overview');
    // [v1.26 fix 1] Informações Periódicas — its OWN tab now (no-op
    // elsewhere: only the ipe tab carries #tab-ipe-events).
    initIpeTab();
    // [v1.28.1] Backtest — the simulator lives in the FERRAMENTAS page
    // now (initToolsPage boots it); the company tab's boot call is gone
    // with the tab itself.
    // [v1.11] Macro — first subtab of the macro page (no-op elsewhere:
    // the loader guards on the pane's existence).
    loadMacroSubtab('overview');
    // [v1.12] Mercado — first subtab of the Focus family (same no-op
    // guard — only the /webui/mercado page carries the pane).
    loadFocusSubtab('overview');
    // [v1.19] Painel — the landing page's KPI row + ticker cards (no-op
    // everywhere else: only /webui carries the panes).
    loadHomeData();
    // [v1.28.3] Painel — the ⚙️ Gerenciar Painel box (ticker KPIs +
    // ranking cards + ⭐ observados; no-op everywhere else).
    initHomeManage();
    // [v1.27] Ferramentas — the Comparação picker + deep-linked comparison
    // (no-op elsewhere: only /webui/tools carries #tools-root).
    initToolsPage();
    // [v1.21] Painel — the carteira widget (⭐ Tickers Observados own
    // box first, then Minhas Carteiras grouped by user; no-op elsewhere
    // and hides itself when nothing is watched).
    loadPortfolioWidget();
    // [v1.21 fix 1] Company page — the ⭐ watch button in the tab bar
    // (no-op everywhere else: only company pages carry the button).
    initCompanyWatch();
    // [v1.13/v1.14] Fluxo/Índices — NOT booted eagerly (fluxo precedent:
    // only the first family boots; the others load on family-pill click,
    // with the data-lazy hover prefetch hiding the latency).
    // [v1.15] Inflação — same (boot on family-pill click only).
    // Sync page (full page load or HTMX navigation)
    initSyncPage();
    // [v1.20] drawer + settings (idempotent — the _booted guards no-op
    // on every HTMX settle after the first).
    initSyslogDrawer();
    initSettingsPage();
    // [v1.21] Carteira page (idempotent — the _booted guard no-ops
    // everywhere but /webui/carteira).
    initCarteiraPage();
  });

  initPriceRangeBar();
  initSyncButtons();
  initFinPeriodPills();
  initValTableSort();
  initCompanyPage();
  initSyncPage();
  // [v1.20] System log drawer (base.html — every page) + the
  // schema-driven settings form (settings.html — the loader no-ops
  // everywhere else).
  initSyslogDrawer();
  initSettingsPage();
  // [v1.21] Carteira — direct full-page load (the /webui/carteira page
  // is server-rendered; the loader no-ops on every other page) + the
  // Painel's carteira widget + the company page's ⭐ watch button.
  initCarteiraPage();
  loadPortfolioWidget();
  initCompanyWatch();
  // [v1.11] Macro — direct full-page load (the /webui/macro page is
  // server-rendered; no HTMX settle fires, so the first subtab boots
  // here — the loader no-ops on every other page).
  loadMacroSubtab('overview');
  // [v1.12] Mercado — same for /webui/mercado (Focus family first).
  loadFocusSubtab('overview');
  // [v1.19] Painel — direct full-page load (the /webui landing is
  // server-rendered; the loader no-ops on every other page).
  loadHomeData();
  // [v1.28.3] Painel — the ⚙️ manage box (direct full-page load; the
  // _booted guard no-ops on every other page).
  initHomeManage();
  // [v1.27] Ferramentas — direct full-page load (the /webui/tools page
  // is server-rendered; the boot guard no-ops on every other page).
  initToolsPage();
  // [v1.13/v1.14] Fluxo/Índices boot on family-pill click only (the
  // mercadoLoader pane guard no-ops them everywhere else).
  // [v1.15] Inflação — same.

  // [v1.5 fix1] Hover/focus prefetch for lazy subtabs — the fetch starts
  // when the pointer heads toward the button (~300ms before the click),
  // so first-click latency shrinks without v1.4's eager 5-fetch burst.
  // Buttons carry data-lazy="<family>:<sub>"; the loaders are idempotent
  // (_loaded guard on the pane), so a hover that never turns into a click
  // costs one request that lands in the pane early.
  document.body.addEventListener('mouseover', prefetchSubtab);
  document.body.addEventListener('focusin', prefetchSubtab);

  // Full page load with the chart already in the DOM (no HTMX settle).
  var canvas = document.getElementById('price-chart');
  if (canvas && !canvas._initialized) {
    canvas._initialized = true;
    var t = canvas.getAttribute('data-ticker');
    var r = canvas.getAttribute('data-range') || '1A';
    if (t) loadCandlestick(t, r);
  }
}

if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', initApp); } else { initApp(); }
