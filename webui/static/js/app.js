/* webui/static/js/app.js — client-side app logic.
 *
 * [WebUI v2] Handles:
 *   - Price chart loading (fetch + Chart.js render)
 *   - Auto-init price chart when visao_geral tab loads (htmx:afterSettle)
 *   - Range selector for price chart
 *
 * IMPORTANT: This script is loaded in <head>. All DOM access must be
 * wrapped in DOMContentLoaded or run after the body exists.
 */

// ── Price chart loading (defined globally, called by onclick + afterSettle) ──
window.loadPriceChart = function(ticker, range) {
  var canvas = document.getElementById('price-chart');
  if (!canvas) {
    console.error('[webui] #price-chart canvas not found');
    return;
  }

  console.log('[webui] loadPriceChart:', ticker, range);

  // Update active range button
  document.querySelectorAll('.range-btn').forEach(function(btn) {
    btn.classList.toggle('active', btn.dataset.range === range);
  });

  // Show loading state
  var container = canvas.parentElement;
  container.style.opacity = '0.5';

  // Fetch price data
  fetch('/api/webui/company/' + ticker + '/price-chart?range=' + range)
    .then(function(r) {
      console.log('[webui] price-chart response status:', r.status);
      return r.json();
    })
    .then(function(data) {
      container.style.opacity = '1';
      console.log('[webui] price-chart data points:', data.labels ? data.labels.length : 0);
      if (!data.labels || !data.prices || data.labels.length === 0) {
        container.innerHTML = '<div class="loading">Sem dados de cotação disponíveis.</div>';
        return;
      }
      renderPriceChart(canvas, data);
    })
    .catch(function(err) {
      container.style.opacity = '1';
      console.error('[webui] Price chart fetch error:', err);
      container.innerHTML = '<div class="error">Erro ao carregar cotação: ' + err.message + '</div>';
    });
};

function renderPriceChart(canvas, data) {
  // Destroy existing chart if any
  if (canvas._chart) {
    canvas._chart.destroy();
  }

  var cssVar = function(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  };
  var gridColor = cssVar('--chart-grid') || 'rgba(128,128,128,0.1)';
  var textColor = cssVar('--chart-text') || '#888';
  var brandColor = cssVar('--brand') || '#0d9488';

  // Format date as DD/MM/YYYY
  function fmtDate(iso) {
    if (iso && iso.match(/^\d{4}-\d{2}-\d{2}$/)) {
      return iso.slice(8) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4);
    }
    return iso;
  }

  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: data.labels,
      datasets: [{
        label: 'Preço',
        data: data.prices,
        borderColor: brandColor,
        backgroundColor: brandColor + '20',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.1,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            maxTicksLimit: 8,
            callback: function(val, idx) {
              return fmtDate(this.getLabelForValue(val));
            },
          },
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            callback: function(val) {
              return 'R$ ' + Number(val).toFixed(2).replace('.', ',');
            },
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              return 'R$ ' + Number(ctx.parsed.y).toFixed(2).replace('.', ',');
            },
            title: function(items) {
              return fmtDate(items[0].label);
            },
          },
        },
      },
    },
  });

  console.log('[webui] Chart rendered successfully');
}

// ── Init: run after DOM is ready ──
function initApp() {
  // HTMX config: execute scripts in swapped content
  if (typeof htmx !== 'undefined') {
    htmx.config.includeScriptTags = true;
  }

  // HTMX error handling
  document.body.addEventListener('htmx:responseError', function(evt) {
    console.error('HTMX error:', evt.detail);
  });

  // Auto-init price chart after ANY HTMX settle
  document.body.addEventListener('htmx:afterSettle', function(evt) {
    initPriceChartIfPresent();
  });

  // Init on first page load
  initPriceChartIfPresent();
}

function initPriceChartIfPresent() {
  var canvas = document.getElementById('price-chart');
  if (!canvas) return;
  // Prevent double-init
  if (canvas._initialized) return;
  canvas._initialized = true;

  var ticker = canvas.getAttribute('data-ticker');
  var range = canvas.getAttribute('data-range') || '1A';
  if (ticker) {
    console.log('[webui] Initializing price chart for', ticker, 'range:', range);
    loadPriceChart(ticker, range);
  }
}

// Run initApp when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  // DOM already loaded (script loaded with defer or at end of body)
  initApp();
}
