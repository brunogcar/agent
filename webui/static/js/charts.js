/* webui/static/js/charts.js — Chart.js factory functions.
 *
 * [WebUI v1] Reuses the Chart.js patterns from the report templates.
 * Exposed as window.WebUICharts.render(canvas, type, data).
 *
 * Theme-aware: reads CSS variables for colors (so charts match the
 * active theme automatically).
 */
window.WebUICharts = {
  render: function(canvas, type, data) {
    if (!window.Chart) {
      console.error('Chart.js not loaded');
      return;
    }
    var ctx = canvas.getContext('2d');
    var cssVar = function(name) {
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    };
    var gridColor = cssVar('--chart-grid') || 'rgba(128,128,128,0.1)';
    var textColor = cssVar('--chart-text') || '#888';
    var brandColor = cssVar('--brand') || '#0d9488';

    if (type === 'line' && data.labels && data.prices) {
      canvas._chart = new Chart(ctx, {
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
                  // Format date as DD/MM/YYYY
                  var label = this.getLabelForValue(val);
                  if (label && label.match(/^\d{4}-\d{2}-\d{2}$/)) {
                    return label.slice(8) + '/' + label.slice(5, 7) + '/' + label.slice(0, 4);
                  }
                  return label;
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
                  var label = items[0].label;
                  if (label && label.match(/^\d{4}-\d{2}-\d{2}$/)) {
                    return label.slice(8) + '/' + label.slice(5, 7) + '/' + label.slice(0, 4);
                  }
                  return label;
                },
              },
            },
          },
        },
      });
    }
  },
};
