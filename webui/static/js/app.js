/* webui/static/js/app.js — client-side app logic.
 *
 * [WebUI v1.2] Handles:
 *   - Candlestick chart (OHLCV + MM20/50/100/200) with zoom/pan — ticker first in legend
 *   - Preço tab: Cotação tables + Histograma + Início vs Fim
 *   - Indicadores subtab: RSI, MACD, Stochastic, OBV, ADX, CCI, Williams %R (with reference lines + range selector)
 *   - Volatilidade subtab: Bollinger Bands + rolling vol (with range selector)
 *   - Auto-init charts via htmx:afterSettle
 */

// Register Chart.js zoom plugin
if (typeof Chart !== 'undefined' && typeof ChartZoom !== 'undefined') {
  Chart.register(ChartZoom);
}

// ── Helpers ──
function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function fmtDate(iso) { return iso && iso.match(/^\d{4}-\d{2}-\d{2}$/) ? iso.slice(8)+'/'+iso.slice(5,7)+'/'+iso.slice(0,4) : iso; }
function fmtBRL(v) { return v !== null && v !== undefined ? 'R$ ' + Number(v).toFixed(2).replace('.', ',') : '—'; }
function chartTheme() { return { grid: cssVar('--chart-grid') || 'rgba(128,128,128,0.1)', text: cssVar('--chart-text') || '#888' }; }

// ── Range selector helper ──
function filterByRange(labels, datasets, range) {
  var rangeMap = { '1M': 21, '3M': 63, '6M': 126, '1A': 252, 'Tudo': 0 };
  var n = rangeMap[range] || 0;
  if (n === 0 || n >= labels.length) return { labels: labels, datasets: datasets };
  return {
    labels: labels.slice(-n),
    datasets: datasets.map(function(ds) { return Object.assign({}, ds, { data: ds.data.slice(-n) }); })
  };
}

// ── Candlestick chart ──
window.loadCandlestick = function(ticker, range) {
  var canvas = document.getElementById('price-chart');
  if (!canvas) return;
  document.querySelectorAll('.range-btn').forEach(function(btn) { btn.classList.toggle('active', btn.dataset.range === range); });
  var container = canvas.parentElement;
  container.style.opacity = '0.5';
  fetch('/api/webui/company/' + ticker + '/candlestick?range=' + range)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      container.style.opacity = '1';
      if (!data.labels || data.labels.length === 0) { container.innerHTML = '<div class="loading">Sem dados de cotação.</div>'; return; }
      renderCandlestick(canvas, ticker, data);
    })
    .catch(function(err) { container.style.opacity = '1'; container.innerHTML = '<div class="error">Erro: ' + err.message + '</div>'; });
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
        zoom: { pan: { enabled: true, mode: 'x', modifierKey: 'shift' }, zoom: { wheel: { enabled: true, speed: 0.1 }, pinch: { enabled: true }, mode: 'x' } }
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
  var tab = document.getElementById('tab-preco'); if (!tab) return;
  fetch('/api/webui/company/' + ticker + '/price-data?_t=' + Date.now()).then(function(r) { return r.json(); }).then(function(data) {
    if (data._error) { tab.innerHTML = '<div class="error">Erro: ' + data._error + '</div>'; return; }
    renderPrecoTab(tab, ticker, data);
  }).catch(function(err) { tab.innerHTML = '<div class="error">Erro: ' + err.message + '</div>'; });
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
function pctVs(v, current) { if (v === null || v === undefined || current === null || current === undefined || current === 0) return null; return (v - current) / current; }
function fmtPctColored(v) { if (v === null || v === undefined) return '<span class="muted">—</span>'; var pct = (v * 100).toFixed(2).replace('.', ',') + '%'; var color = v < 0 ? 'var(--color-danger)' : 'var(--color-success)'; return '<span style="color: ' + color + '">' + pct + '</span>'; }

function renderHistogram(hist) {
  var canvas = document.getElementById('histogram-chart'); if (!canvas) return; var th = chartTheme();
  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: { labels: hist.bins.map(function(b) { return b.label; }), datasets: [{ label: 'Frequência', data: hist.bins.map(function(b) { return b.count; }), backgroundColor: hist.bins.map(function(b) { return b.color; }), borderWidth: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { color: th.grid }, ticks: { color: th.text, maxTicksLimit: 15 } }, y: { grid: { color: th.grid }, ticks: { color: th.text }, title: { display: true, text: 'Pregões' } } }, plugins: { legend: { display: false } } }
  });
}

function renderInicioFim(ar) {
  var canvas = document.getElementById('inicio-fim-chart'); if (!canvas) return; var th = chartTheme();
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
  fetch('/api/webui/company/' + ticker + '/indicators?_t=' + Date.now()).then(function(r) { return r.json(); }).then(function(data) {
    if (data._error) { tab.innerHTML = '<div class="error">Erro: ' + data._error + '</div>'; return; }
    renderIndicadoresTab(tab, ticker, data);
  }).catch(function(err) { tab.innerHTML = '<div class="error">Erro: ' + err.message + '</div>'; });
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
  var n = { '1M': 21, '3M': 63, '6M': 126, '1A': 252, '5A': 1260, '10A': 2520, 'Tudo': 0 }[range] ?? 252;
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
  fetch('/api/webui/company/' + ticker + '/volatility?_t=' + Date.now()).then(function(r) { return r.json(); }).then(function(data) {
    if (data._error) { tab.innerHTML = '<div class="error">Erro: ' + data._error + '</div>'; return; }
    renderVolatilidadeTab(tab, ticker, data);
  }).catch(function(err) { tab.innerHTML = '<div class="error">Erro: ' + err.message + '</div>'; });
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
  var n = { '1M': 21, '3M': 63, '6M': 126, '1A': 252, '5A': 1260, '10A': 2520, 'Tudo': 0 }[range] ?? 252;
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
  fetch('/api/webui/company/' + ticker + '/volume?_t=' + Date.now()).then(function(r) { return r.json(); }).then(function(data) {
    if (data._error) { tab.innerHTML = '<div class="error">Erro: ' + data._error + '</div>'; return; }
    renderVolumeTab(tab, ticker, data);
  }).catch(function(err) { tab.innerHTML = '<div class="error">Erro: ' + err.message + '</div>'; });
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
  var n = { '1M': 21, '3M': 63, '6M': 126, '1A': 252, '5A': 1260, '10A': 2520, 'Tudo': 0 }[range] ?? 252;
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
  fetch('/api/webui/company/' + ticker + '/fibonacci?_t=' + Date.now()).then(function(r) { return r.json(); }).then(function(data) {
    if (data._error) { tab.innerHTML = '<div class="error">Erro: ' + data._error + '</div>'; return; }
    renderFibonacciTab(tab, ticker, data);
  }).catch(function(err) { tab.innerHTML = '<div class="error">Erro: ' + err.message + '</div>'; });
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

// ── Auto-init after HTMX settle ──
function initApp() {
  if (typeof htmx !== 'undefined') htmx.config.includeScriptTags = true;
  document.body.addEventListener('htmx:responseError', function(evt) { console.error('HTMX error:', evt.detail); });
  document.body.addEventListener('htmx:afterSettle', function(evt) {
    var canvas = document.getElementById('price-chart');
    if (canvas && !canvas._initialized) { canvas._initialized = true; var t = canvas.getAttribute('data-ticker'); var r = canvas.getAttribute('data-range') || '1A'; if (t) loadCandlestick(t, r); }
    var precoTab = document.getElementById('tab-preco');
    if (precoTab && !precoTab._initialized) { precoTab._initialized = true; var t = precoTab.getAttribute('data-ticker'); if (t) initPrecoTab(t); }
    var indTab = document.getElementById('tab-indicadores');
    if (indTab && !indTab._initialized) { indTab._initialized = true; var t = indTab.getAttribute('data-ticker'); if (t) initIndicadoresTab(t); }
    var volTab = document.getElementById('tab-volatilidade');
    var volumeTab = document.getElementById('tab-volume');
    var fibTab = document.getElementById('tab-fibonacci');
    if (fibTab && !fibTab._initialized) { fibTab._initialized = true; var t = fibTab.getAttribute('data-ticker'); if (t) initFibonacciTab(t); }
    if (volumeTab && !volumeTab._initialized) { volumeTab._initialized = true; var t = volumeTab.getAttribute('data-ticker'); if (t) initVolumeTab(t); }
    if (volTab && !volTab._initialized) { volTab._initialized = true; var t = volTab.getAttribute('data-ticker'); if (t) initVolatilidadeTab(t); }
  });
  var canvas = document.getElementById('price-chart');
  if (canvas && !canvas._initialized) { canvas._initialized = true; var t = canvas.getAttribute('data-ticker'); var r = canvas.getAttribute('data-range') || '1A'; if (t) loadCandlestick(t, r); }
}

if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', initApp); } else { initApp(); }
