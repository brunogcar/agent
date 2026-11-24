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
function fmtDate(iso) { return iso && iso.match(/^\d{4}-\d{2}-\d{2}$/) ? iso.slice(8)+'/'+iso.slice(5,7)+'/'+iso.slice(0,4) : iso; }
// [v1.15] ISO month "2026-07" → "jul/2026" (same short PT-BR month form
// the tables use — sortable by _valSortKey, readable on the x-axis).
var _MONTH_NAMES = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
function fmtMonth(iso) {
  var m = iso && iso.match(/^(\d{4})-(\d{2})$/);
  if (!m) return iso;
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
  if (hist && hist.bins) renderHistogram(hist);
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

function renderHistogram(hist) {
  var canvas = document.getElementById('histogram-chart'); if (!canvas) return; var th = chartTheme();
  if (canvas._chart) canvas._chart.destroy();
  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: { labels: hist.bins.map(function(b) { return b.label; }), datasets: [{ label: 'Frequência', data: hist.bins.map(function(b) { return b.count; }), backgroundColor: hist.bins.map(function(b) { return b.color; }), borderWidth: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: { color: th.text, maxTicksLimit: 15 } }, y: { grid: { color: th.grid }, ticks: { color: th.text }, title: { display: true, text: 'Pregões' } } }, plugins: { legend: { display: false } } }
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

  // RSI
  html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">RSI (14)</div></div><div class="chart-container"><canvas id="rsi-chart"></canvas></div></div>';
  // MACD
  html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">MACD (12/26/9)</div></div><div class="chart-container"><canvas id="macd-chart"></canvas></div></div>';
  // Stochastic
  html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">Stochastic (14/3)</div></div><div class="chart-container"><canvas id="stoch-chart"></canvas></div></div>';
  // OBV
  html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">OBV</div></div><div class="chart-container"><canvas id="obv-chart"></canvas></div></div>';
  // ADX
  if (data.adx) html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">ADX (14)</div></div><div class="chart-container"><canvas id="adx-chart"></canvas></div></div>';
  // CCI
  if (data.cci) html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">CCI (20)</div></div><div class="chart-container"><canvas id="cci-chart"></canvas></div></div>';
  // Williams %R
  if (data.williams_r) html += '<div class="chart-section"><div class="chart-header"><div class="reg-title">Williams %R (14)</div></div><div class="chart-container"><canvas id="williams-chart"></canvas></div></div>';

  html += '</div>';
  tab.innerHTML = html;

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
            '" onclick="valSubNav(this,\'val-' + panel.id + '-g' + gi + '\')">' + valEsc(g.name) + '</button>';
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
                '" onclick="valSubNav(this,\'val-' + panel.id + '-g' + gi + 's' + si + '\')">' + valEsc(s.name) + '</button>';
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
          h += '<td class="val-metric">' + valEsc(String(cell)) + '</td>';
        } else if (cell && typeof cell === 'object') {
          h += '<td class="val-heat" style="background:' + (cell.bg || 'transparent') +
               ';color:' + (cell.color || 'inherit') + '" title="' + valEsc(cell.tooltip || '') + '">' +
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
    var h = '<div class="val-section"><div class="reg-title">' + valEsc(sec.title || '') + '</div>';
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
        if (cell && typeof cell === 'object') {
          var tip = cell.tooltip || '';
          h += '<td' + (ci === 0 && tip ? ' title="' + valEsc(tip) + '"' : '') + '>' +
               valEsc(cell.text || '—') +
               (ci === 0 && tip ? ' <span class="val-info">ⓘ</span>' : '') + '</td>';
        } else {
          h += '<td' + (ci > 0 ? ' class="val-val"' : '') + '>' + valNumHtml(String(cell)) + '</td>';
        }
      });
      h += '</tr>';
    });
    h += '</tbody></table>';
    if (sec.note) h += '<div class="val-note">' + valEsc(sec.note) + '</div>';
    return h + '</div>';
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
    options = {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: true, position: 'top', labels: { color: th.text } } },
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
    // [v1.14] Honor the server's plugins.legend (display/position) — the
    // Índices composition doughnuts ship legend off (78-136 slices would
    // be a wall of legend labels; the full table below is the legend).
    // Same cutout/stacked precedent: default stays exactly as before for
    // every chart that does not ask.
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
window.loadAcoesSubtab = mercadoLoader('acoes'); // [v1.17] ações B3 + evolução
window.loadDividendosSubtab = mercadoLoader('dividendos'); // [v1.18] proventos (BDR split)

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
  var cardsBox = document.getElementById('home-cards');
  if (!kpiBox && !cardsBox) return;
  if (_homeReq && _homeReq.box === kpiBox) return;   // this pane: in flight or done
  var req = { box: kpiBox, done: false };
  _homeReq = req;
  fetch('/api/webui/home?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      req.done = true;
      renderHome(kpiBox, cardsBox, data);
    })
    .catch(function(err) {
      if (_homeReq === req) _homeReq = null;   // allow a later trigger to retry
      var msg = '<div class="error">Erro: ' + esc(err.message) + '</div>';
      if (kpiBox) kpiBox.innerHTML = msg;
      if (cardsBox) cardsBox.innerHTML = msg;
    });
};

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
  var extra = item.extra
    ? '<span class="tk-extra" title="' + valEsc(item.extra.label || '') + '">' +
      valEsc(item.extra.text) + '</span>'
    : '';
  return '<a class="ticker-row' + (item.extra ? ' has-extra' : '') +
         '" href="/webui/company/' +
         encodeURIComponent(item.ticker) + '">' +
    '<span class="tk">' + valEsc(item.ticker) + '</span>' +
    '<span class="tk-name" title="' + valEsc(item.name) + '">' + valEsc(item.name) + '</span>' +
    '<span class="tk-val">' + valEsc(item.value) + '</span>' +
    '<span class="tk-var">' + vHtml + '</span>' +
    extra +
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

function renderHome(kpiBox, cardsBox, data) {
  if (data._error) {
    if (kpiBox) kpiBox.innerHTML = '<div class="error">' + esc(data._error) + '</div>';
    if (cardsBox) cardsBox.innerHTML = '';
    return;
  }
  if (kpiBox) {
    kpiBox.innerHTML =
      (data.kpis && data.kpis.length ? valKpisHtml(data.kpis) : '') +
      (data.kpis_note
        ? '<div class="home-note">' + valEsc(data.kpis_note) + '</div>'
        : '');
  }
  if (cardsBox) {
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
              jur: window.loadJurosSubtab, aco: window.loadAcoesSubtab,
              div: window.loadDividendosSubtab };
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
    editUser: null, editAccount: null, editTx: null,
  };

  function $(id) { return document.getElementById(id); }

  function api(method, path, body) {
    return fetch('/api/webui/portfolio' + path, {
      method: method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }).then(function(r) {
      return r.json().then(function(j) { return { ok: r.ok, j: j }; });
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
      reconcileLevel();
      renderActions();
      renderCrumbs();
      if ($('cart-manage-modal').open) renderManage();
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
  function hideNote() {
    var n = $('cart-note');
    if (n) { n.hidden = true; n.textContent = ''; }
  }

  function showNote(d) {
    var n = $('cart-note');
    if (!n) return;
    if (d && d.quotes_note) { n.hidden = false; n.textContent = d.quotes_note; }
    else { n.hidden = true; n.textContent = ''; }
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
        statCell('Lucro hoje', u.profit, 'Patrimônio − custo das posições abertas') +
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
        statCell('Lucro hoje', a.profit, 'Patrimônio − custo das posições abertas') +
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
    html += '<div class="cart-viewbar"><div class="cart-pills" role="group" aria-label="Visão">' +
      '<button class="cart-pill' + (st.view === 'positions' ? ' is-active' : '') +
        '" data-view="positions">Posições</button>' +
      '<button class="cart-pill' + (st.view === 'txs' ? ' is-active' : '') +
        '" data-view="txs">Transações</button></div>' +
      '<span class="cart-scope-label">' + esc(labelBits.join(' · ')) + '</span>' +
      '<span class="cart-toolbar-spacer"></span>' +
      '<button class="cart-btn primary" data-act="tx" ' +
        'title="Registrar transação nesta conta">➕ Transação</button>' +
      '<button class="cart-btn ghost" data-act="reload" aria-label="Recarregar" ' +
        'title="Recarregar dados">🔄</button></div>';
    html += '<div id="cart-positions" class="cart-view"' +
      (st.view === 'positions' ? '' : ' hidden') + '></div>';
    html += '<div id="cart-txs" class="cart-view"' +
      (st.view === 'txs' ? '' : ' hidden') + '></div>';
    box.innerHTML = html;
    renderPositionsTable(d);
    renderTxsTable(d);
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
      '<button class="cart-btn primary" data-act="tx">➕ Registrar transação</button></div>';
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
      var qtyCell = esc(r.qty) + shortFlag;
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
        '<td class="cart-name" title="' + esc(r.name) + '">' + esc(r.name) + '</td>' +
        '<td class="cart-sector" title="' + esc(r.sector) + '">' + esc(r.sector) + '</td>' +
        '<td class="val-val">' + valNumHtml(r.pm) + '</td>' +
        '<td class="val-val">' + valNumHtml(r.price) + '</td>' +
        '<td class="val-val">' + qtyCell + '</td>' +
        '<td class="val-val">' + valNumHtml(r.cost) + '</td>' +
        '<td class="val-val">' + valNumHtml(r.value) + '</td>' +
        '<td class="val-val">' + valNumHtml(r.profit) + '</td>' +
        '<td class="val-val">' + signedHtml(r.profit_pct) + '</td>' +
        '<td class="cart-actions">' +
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

  function renderTxsTable(d) {
    var box = $('cart-txs');
    if (!box) return;
    var rows = (d.txs || []).map(function(t) {
      var buy = t.type === 'buy';
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
      return '<tr>' +
        '<td>' + dateCell + flags + '</td>' +
        '<td class="cart-tk"><a href="/webui/company/' + encodeURIComponent(t.ticker) + '">' +
          esc(t.ticker) + '</a></td>' +
        '<td><span class="cart-type ' + (buy ? 'is-buy' : 'is-sell') + '">' +
          (buy ? '✅ Compra' : '❌ Venda') + '</span></td>' +
        '<td class="val-val">' + esc(t.qty) + '</td>' +
        '<td class="val-val">' + valNumHtml(t.price) + '</td>' +
        '<td class="val-val">' + valNumHtml(t.fees) + '</td>' +
        '<td class="val-val">' + valNumHtml(t.total) + '</td>' +
        '<td class="cart-actions">' +
          '<button class="cart-icon-btn" data-et="' + esc(t.id) + '" title="✏️ Editar transação">✏️</button>' +
          '<button class="cart-icon-btn" data-dt="' + esc(t.id) + '" title="🗑️ Excluir transação">🗑️</button>' +
        '</td></tr>';
    }).join('');

    box.innerHTML = rows
      ? '<div class="cart-table-wrap"><table class="val-table cart-table"><thead><tr>' +
        '<th class="val-sortable">🗓️ Data</th><th>Ticker</th><th>Tipo</th>' +
        '<th class="th-num val-sortable">Qtd</th><th class="th-num val-sortable">Preço</th>' +
        '<th class="th-num val-sortable">Taxas</th><th class="th-num val-sortable">Total</th>' +
        '<th></th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
        '<p class="cart-note-line">ℹ️ Ordem cronológica (mais antigas primeiro) — ' +
        'clique no cabeçalho 🗓️ Data para inverter.</p>'
      : '<div class="cart-empty"><h3>Nenhuma transação</h3>' +
        '<p>Use “➕ Transação” para registrar a primeira compra ou venda.</p></div>';
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
    var s = String(v === null || v === undefined ? '' : v).trim()
      .replace(/\./g, '').replace(',', '.');
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
      ' · Lucro hoje: ' + signedHtml(pos.profit) + ' (' + signedHtml(pos.profit_pct) + ')';
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
      hints.push('⚠️ <b>Preço R$ 0,00 — bonificação?</b> Os ativos entram ' +
        'sem custo no preço médio.');
    }
    box.innerHTML = hints.join('<br>');
    box.hidden = !hints.length;
  }

  function openTxModal(txId, prefill) {
    st.editTx = txId || null;
    prefill = prefill || {};
    var m = $('cart-tx-modal');
    var tx = null;
    if (txId) {
      tx = ((st.pos && st.pos.txs) || []).filter(function(t) {
        return t.id === txId;
      })[0];
    }
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
    $('cart-tx-qty').value = tx ? String(tx.quantity).replace('.', ',')
      : (prefQty !== undefined && prefQty !== '' && prefQty !== null
          ? String(prefQty).replace('.', ',') : '');
    // [fix 2] setMoney also primes the mask mode (a 4-decimal PM edit
    // opens in explicit mode; a fresh form starts in cents-fill).
    setMoney($('cart-tx-price'), tx ? tx.raw_price : null);
    setMoney($('cart-tx-fees'), tx ? (tx.raw_fees || 0) : null);
    $('cart-tx-note').value = tx ? (tx.note || '') : '';
    fieldErrs(m, {});
    $('cart-tx-msg').textContent = '';
    updatePosCtx();
    updateHints();
    m.showModal();
    if (!tx && !prefill.ticker) $('cart-tx-ticker').focus();
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
    var qv = parseBr($('cart-tx-qty').value);
    var pv = parseBr($('cart-tx-price').value);
    var fv = parseBr($('cart-tx-fees').value);
    var body = {
      account_id: $('cart-tx-account').value,
      ticker: $('cart-tx-ticker').value,
      type: $('cart-tx-type').value,
      date: iso,
      quantity: qv === null ? $('cart-tx-qty').value : qv,
      price: pv === null ? $('cart-tx-price').value : pv,
      fees: fv === null ? '' : fv,
      note: $('cart-tx-note').value,
    };
    var call = st.editTx
      ? api('PUT', '/txs/' + st.editTx, body)
      : api('POST', '/txs', body);
    call.then(function(res) {
      if (!res.ok) {
        fieldErrs(m, res.j);
        $('cart-tx-msg').textContent = (res.j && res.j._error) || '';
        return;
      }
      m.close();
      reload();
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
    var tx = ((st.pos && st.pos.txs) || []).filter(function(t) {
      return t.id === id;
    })[0];
    askConfirm('🗑️ Excluir transação',
      'Excluir ' + (tx
        ? 'a <b>' + (tx.type === 'buy' ? 'compra' : 'venda') + '</b> de <b>' +
          esc(tx.qty) + ' ' + esc(tx.ticker) + '</b> em ' + esc(tx.date)
        : 'esta transação') +
      '?<br><span class="cart-warn-line">ℹ️ O preço médio e o lucro são recalculados.</span>',
      '🗑️ Excluir transação', function() {
        api('DELETE', '/txs/' + id).then(function(res) {
          if (!res.ok) window.alert((res.j && res.j._error) || 'Erro ao excluir.');
          else reload();
        });
      });
  }

  function toggleWatchAccount(id) {
    var a = stAccount(id);
    if (!a) return;
    api('PUT', '/accounts/' + id, { watch: !a.watch }).then(function() { reload(); });
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

    box.innerHTML = html;

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
  }

  // ── ONE delegated click handler for the whole page ─────────────────────
  root.addEventListener('click', function(e) {
    var el = e.target && e.target.closest ? e.target.closest(
      '[data-act],[data-nav],[data-view],[data-eu],[data-du],[data-aw],' +
      '[data-ea],[data-da],[data-qb],[data-qs],[data-et],[data-dt],' +
      '.cart-ucard') : null;
    if (!el) return;

    if (el.hasAttribute('data-act')) {
      var act = el.getAttribute('data-act');
      if (act === 'user') openUserModal();
      else if (act === 'account') openAccountModal();
      else if (act === 'tx') openTxModal();
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
      var pv = $('cart-positions'), tv = $('cart-txs');
      if (pv) pv.hidden = st.view !== 'positions';
      if (tv) tv.hidden = st.view !== 'txs';
      return;
    }
    if (el.hasAttribute('data-eu')) { openUserModal(el.getAttribute('data-eu')); return; }
    if (el.hasAttribute('data-du')) { confirmDeleteUser(el.getAttribute('data-du')); return; }
    if (el.hasAttribute('data-aw')) { toggleWatchAccount(el.getAttribute('data-aw')); return; }
    if (el.hasAttribute('data-ea')) { openAccountModal(el.getAttribute('data-ea')); return; }
    if (el.hasAttribute('data-da')) { confirmDeleteAccount(el.getAttribute('data-da')); return; }
    if (el.hasAttribute('data-et')) { openTxModal(el.getAttribute('data-et')); return; }
    if (el.hasAttribute('data-dt')) { confirmDeleteTx(el.getAttribute('data-dt')); return; }
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
  $('cart-tx-type').addEventListener('change', function() { updateHints(); });
  $('cart-tx-ticker').addEventListener('input', function() { updateHints(); });

  reload();
}

// ── [v1.21 fix 1] Painel widget — ⭐ Tickers Observados (its OWN box,
// first — it is NOT part of Minhas Carteiras) then 💼 Minhas Carteiras
// (contas observadas grouped by user, per-user subtotals — never across
// users). The old single "Minhas Carteiras" box mixed both. ─────────────
function loadPortfolioWidget() {
  var box = document.getElementById('home-portfolio');
  if (!box || box._booted) return;
  box._booted = true;
  fetch('/api/webui/portfolio/overview?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d || d._error || !d.has_data) { box.innerHTML = ''; return; }
      var html = '';

      // ⭐ Tickers observados — own box, FIRST.
      if (d.tickers && d.tickers.length) {
        html += '<div class="cart-widget"><div class="cart-widget-head"><h2>⭐ Tickers Observados' +
          (d.session_date ? ' <span class="cart-widget-sub">· pregão ' + esc(d.session_date) + '</span>' : '') +
          '</h2><a class="cart-widget-link" href="/webui/carteira">Gerenciar ⭐ →</a></div>';
        if (d.quotes_note) html += '<div class="home-note">' + esc(d.quotes_note) + '</div>';
        html += '<table class="val-table"><thead><tr><th>Ticker</th><th>Nome</th>' +
          '<th class="th-num">Preço</th><th class="th-num">Var. dia</th></tr></thead><tbody>' +
          d.tickers.map(function(t) {
            var v = t.variation;
            var cls = v && v.charAt(0) === '-' ? 'val-neg'
                    : (v && v.charAt(0) === '+' ? 'val-pos' : 'val-zero');
            return '<tr><td class="cart-tk"><a href="/webui/company/' +
              encodeURIComponent(t.ticker) + '">' + esc(t.ticker) + '</a></td>' +
              '<td class="cart-name" title="' + esc(t.name) + '">' + esc(t.name) + '</td>' +
              '<td class="val-val">' + valNumHtml(t.price) + '</td>' +
              '<td class="val-val"><span class="' + cls + '">' + esc(v || '—') + '</span></td></tr>';
          }).join('') + '</tbody></table></div>';
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
    // [v1.11] Macro — first subtab of the macro page (no-op elsewhere:
    // the loader guards on the pane's existence).
    loadMacroSubtab('overview');
    // [v1.12] Mercado — first subtab of the Focus family (same no-op
    // guard — only the /webui/mercado page carries the pane).
    loadFocusSubtab('overview');
    // [v1.19] Painel — the landing page's KPI row + ticker cards (no-op
    // everywhere else: only /webui carries the panes).
    loadHomeData();
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
