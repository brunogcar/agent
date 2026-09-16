/* webui/static/js/app.js — client-side app logic.
 *
 * [WebUI v1] Minimal vanilla JS. Most interactivity is HTMX (server-rendered)
 * or Alpine.js (client state). This file handles:
 *   - HTMX config (error handling, indicators)
 *   - Chart initialization after HTMX swaps (the critical gotcha —
 *     <script> tags in swapped content don't execute by default)
 */

// ── HTMX error handling ──
document.body.addEventListener('htmx:responseError', function(evt) {
  console.error('HTMX error:', evt.detail);
});

// ── Chart initialization after HTMX swaps ──
// When HTMX swaps content containing <canvas data-chart-type="...">,
// the inline <script> that would init the chart doesn't execute.
// Solution: listen for htmx:afterSwap and init any charts found.
document.body.addEventListener('htmx:afterSwap', function(evt) {
  initChartsInElement(evt.detail.target);
});

// Also init on first page load
document.addEventListener('DOMContentLoaded', function() {
  initChartsInElement(document.body);
});

function initChartsInElement(el) {
  if (!el || !el.querySelectorAll) return;
  var canvases = el.querySelectorAll('canvas[data-chart-type]');
  canvases.forEach(function(canvas) {
    if (canvas._chart) return;  // already initialized
    var chartType = canvas.getAttribute('data-chart-type');
    // Fetch the chart data from the hidden sibling div
    var dataEl = document.getElementById(canvas.id.replace('-chart', '-chart-data'));
    if (dataEl && dataEl.textContent.trim()) {
      try {
        var data = JSON.parse(dataEl.textContent);
        if (window.WebUICharts && window.WebUICharts.render) {
          window.WebUICharts.render(canvas, chartType, data);
        }
      } catch (e) {
        console.error('Chart init error:', e);
      }
    }
  });
}
