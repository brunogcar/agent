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
  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: def.type === 'line' ? 'line' : 'bar',
    data: { labels: chartLabels, datasets: datasets },
    options: { responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { stacked: !!def.stacked, grid: { color: th.grid }, ticks: { color: th.text, maxTicksLimit: 14 } },
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
    (sec.columns || []).forEach(function(c, ci) {
      h += '<th' + (ci > 0 ? ' class="th-num"' : '') + '>' + valEsc(String(c)) + '</th>';
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
    if (srvY.title && srvY.title.text) yScale.title = { display: true, text: srvY.title.text };
    var xScale = { grid: { color: th.grid }, ticks: { color: th.text, maxTicksLimit: 14 } };
    if (srvX.stacked) xScale.stacked = true;
    // [v1.7.2] x-axis title too (the history charts label it "Data").
    if (srvX.title && srvX.title.text) xScale.title = { display: true, text: srvX.title.text };
    options = {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: true, position: 'top', labels: { color: th.text } } },
      scales: {
        x: xScale,
        y: yScale
      }
    };
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
              val: window.loadValSubtab, prov: window.loadProvSubtab };
  var fn = fns[parts[0]];
  if (fn && parts[1]) { try { fn(parts[1]); } catch (err) { /* noop */ } }
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
    // Sync page (full page load or HTMX navigation)
    initSyncPage();
  });

  initPriceRangeBar();
  initSyncButtons();
  initFinPeriodPills();
  initCompanyPage();
  initSyncPage();

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
