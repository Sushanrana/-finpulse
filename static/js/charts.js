// FinPulse charts (Chart.js 4). Data comes from <script type="application/json"> blocks rendered by Flask.
(function () {
  "use strict";
  if (!window.Chart) return;

  var C = {
    income: "#10B981", expense: "#F43F5E", savings: "#06B6D4", invested: "#8B5CF6", spent: "#EF4444",
    categories: ["#10B981", "#06B6D4", "#6366F1", "#F59E0B", "#EC4899", "#8B5CF6", "#14B8A6", "#F43F5E"],
    grid: "#1E293B", text: "#94A3B8"
  };

  Chart.defaults.color = C.text;
  Chart.defaults.borderColor = C.grid;
  Chart.defaults.font.family = "'Plus Jakarta Sans', system-ui, sans-serif";
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.maintainAspectRatio = false;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) Chart.defaults.animation = false;

  function aud(v) {
    var n = Number(v) || 0;
    return (n < 0 ? "-" : "") + "A$" + Math.abs(n).toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function audShort(v) {
    var n = Math.abs(Number(v) || 0);
    var s = n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k" : n.toFixed(0);
    return (v < 0 ? "-" : "") + "A$" + s;
  }
  function readJSON(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }
  var moneyTooltip = { callbacks: { label: function (ctx) { return " " + ctx.dataset.label + ": " + aud(ctx.parsed.y !== undefined ? ctx.parsed.y : ctx.parsed); } } };
  var moneyAxis = { ticks: { callback: function (v) { return audShort(v); } }, grid: { color: C.grid } };

  var d = readJSON("dashboard-data");
  if (d) {
    var cat = document.getElementById("chart-category");
    if (cat) new Chart(cat, {
      type: "doughnut",
      data: { labels: d.category.labels, datasets: [{ label: "Spent", data: d.category.values, backgroundColor: C.categories, borderColor: "#111827", borderWidth: 3, hoverOffset: 6 }] },
      options: {
        cutout: "64%",
        plugins: {
          legend: { position: "right" },
          tooltip: { callbacks: { label: function (ctx) {
            var total = ctx.dataset.data.reduce(function (a, b) { return a + b; }, 0);
            return " " + ctx.label + ": " + aud(ctx.parsed) + " (" + Math.round(ctx.parsed / total * 100) + "%)";
          } } }
        }
      }
    });

    var monthly = document.getElementById("chart-monthly");
    if (monthly) new Chart(monthly, {
      type: "bar",
      data: { labels: d.monthly.labels, datasets: [
        { label: "Income", data: d.monthly.income, backgroundColor: C.income, borderRadius: 6, maxBarThickness: 28 },
        { label: "Expenses", data: d.monthly.expense, backgroundColor: C.expense, borderRadius: 6, maxBarThickness: 28 }
      ] },
      options: { plugins: { tooltip: moneyTooltip }, scales: { y: moneyAxis, x: { grid: { display: false } } } }
    });

    var trend = document.getElementById("chart-trend");
    if (trend) new Chart(trend, {
      type: "line",
      data: { labels: d.trend.labels, datasets: [
        { label: "Cumulative savings", data: d.trend.cumulative, borderColor: C.savings, backgroundColor: "rgba(6,182,212,0.12)", fill: true, tension: 0.35, pointRadius: 3 },
        { label: "Monthly net", data: d.trend.net, borderColor: C.income, borderDash: [5, 5], tension: 0.35, pointRadius: 2, fill: false }
      ] },
      options: { interaction: { mode: "index", intersect: false }, plugins: { tooltip: moneyTooltip }, scales: { y: moneyAxis, x: { grid: { display: false } } } }
    });
  }

  var tm = readJSON("time-machine-data");
  var tmCanvas = document.getElementById("chart-time-machine");
  if (tm && tmCanvas) new Chart(tmCanvas, {
    type: "line",
    data: { labels: tm.labels, datasets: [
      { label: "Invest it (portfolio value)", data: tm.invested, borderColor: C.invested, backgroundColor: "rgba(139,92,246,0.15)", fill: true, tension: 0.3, pointRadius: 0, pointHoverRadius: 4 },
      { label: "Spend it (money gone)", data: tm.spent, borderColor: C.spent, borderDash: [6, 4], tension: 0, pointRadius: 0, pointHoverRadius: 4, fill: false }
    ] },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: { tooltip: moneyTooltip },
      scales: { y: moneyAxis, x: { grid: { display: false }, ticks: { maxTicksLimit: 11 } } }
    }
  });
})();
