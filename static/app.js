const metricSelect = document.getElementById("metric-select");
const methodSelect = document.getElementById("method-select");
const horizonInput = document.getElementById("horizon-input");
const refreshBtn = document.getElementById("refresh-btn");
const statusEl = document.getElementById("status");
const alertsBody = document.querySelector("#alerts-table tbody");
const noAlertsEl = document.getElementById("no-alerts");

let chart;

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

async function loadMetrics() {
  const { metrics } = await fetchJSON("/api/metrics");
  metricSelect.innerHTML = metrics.map(m => `<option value="${m}">${labelFor(m)}</option>`).join("");
}

function labelFor(metric) {
  return {
    daily_revenue: "Daily revenue ($)",
    daily_signups: "Daily signups",
    churn_rate: "Churn rate (%)",
  }[metric] || metric;
}

function severityClass(sev) {
  return sev === "high" ? "severity-high" : "severity-medium";
}

async function loadChart() {
  const metric = metricSelect.value;
  const method = methodSelect.value;
  const horizon = parseInt(horizonInput.value, 10) || 14;

  const [historyData, forecastData] = await Promise.all([
    fetchJSON(`/api/history/${metric}?limit=90`),
    fetchJSON(`/api/forecast/${metric}?method=${method}&horizon=${horizon}`),
  ]);

  const historyLabels = historyData.history.map(p => p.date);
  const historyValues = historyData.history.map(p => p.value);
  const forecastLabels = forecastData.forecast.map(p => p.date);
  const forecastValues = forecastData.forecast.map(p => p.forecast_value);
  const lowerValues = forecastData.forecast.map(p => p.lower_bound);
  const upperValues = forecastData.forecast.map(p => p.upper_bound);

  const labels = [...historyLabels, ...forecastLabels];
  const padHist = new Array(historyLabels.length).fill(null);
  const padFuture = new Array(forecastLabels.length).fill(null);

  const datasets = [
    {
      label: "Actual",
      data: [...historyValues, ...padFuture],
      borderColor: "#5b8cff",
      backgroundColor: "transparent",
      pointRadius: 0,
      borderWidth: 2,
    },
    {
      label: "Forecast",
      data: [...padHist, ...forecastValues],
      borderColor: "#ffb454",
      backgroundColor: "transparent",
      borderDash: [6, 4],
      pointRadius: 0,
      borderWidth: 2,
    },
    {
      label: "Upper bound",
      data: [...padHist, ...upperValues],
      borderColor: "rgba(255,180,84,0.25)",
      backgroundColor: "rgba(255,180,84,0.12)",
      pointRadius: 0,
      borderWidth: 1,
      fill: "+1",
    },
    {
      label: "Lower bound",
      data: [...padHist, ...lowerValues],
      borderColor: "rgba(255,180,84,0.25)",
      backgroundColor: "rgba(255,180,84,0.12)",
      pointRadius: 0,
      borderWidth: 1,
      fill: false,
    },
  ];

  if (chart) chart.destroy();
  chart = new Chart(document.getElementById("kpi-chart"), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { color: "#93a0bd", maxTicksLimit: 12 }, grid: { color: "#26304a" } },
        y: { ticks: { color: "#93a0bd" }, grid: { color: "#26304a" } },
      },
      plugins: { legend: { labels: { color: "#e7ecf7" } } },
    },
  });
}

async function loadAlerts() {
  const metric = metricSelect.value;
  const { alerts } = await fetchJSON(`/api/alerts?metric=${metric}`);
  alertsBody.innerHTML = "";
  noAlertsEl.style.display = alerts.length ? "none" : "block";
  for (const a of alerts) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${a.date}</td>
      <td>${labelFor(a.metric)}</td>
      <td>${a.actual_value.toFixed(2)}</td>
      <td>${a.forecast_value.toFixed(2)}</td>
      <td>${a.lower_bound.toFixed(2)} &ndash; ${a.upper_bound.toFixed(2)}</td>
      <td class="${severityClass(a.severity)}">${a.severity}</td>
      <td>${a.method}</td>
    `;
    alertsBody.appendChild(tr);
  }
}

async function refreshAll() {
  statusEl.textContent = "Refreshing forecasts + alerts...";
  refreshBtn.disabled = true;
  try {
    await fetchJSON(`/api/refresh?method=${methodSelect.value}`, { method: "POST" });
    await Promise.all([loadChart(), loadAlerts()]);
    statusEl.textContent = "Up to date.";
  } catch (e) {
    statusEl.textContent = `Error: ${e.message}`;
  } finally {
    refreshBtn.disabled = false;
  }
}

metricSelect.addEventListener("change", () => { loadChart(); loadAlerts(); });
methodSelect.addEventListener("change", loadChart);
horizonInput.addEventListener("change", loadChart);
refreshBtn.addEventListener("click", refreshAll);

(async function init() {
  await loadMetrics();
  await loadChart();
  await loadAlerts();
})();
