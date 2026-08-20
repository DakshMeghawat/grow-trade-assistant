const fmt = (n) => n == null || Number.isNaN(n) ? "—" : "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
const fmt2 = (n) => n == null || Number.isNaN(n) ? "—" : "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
const fmtPct = (n) => n == null || Number.isNaN(n) ? "—" : (n >= 0 ? "+" : "") + n.toFixed(1) + "%";
const cls = (n) => n == null ? "" : n >= 0 ? "positive" : "negative";

let sectorChart = null;
let holdingsChart = null;
let pollTimer = null;
let currentData = null;
let currentView = "overview";

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || r.statusText);
  }
  return r.json();
}

async function uploadGrowwFile() {
  const input = document.getElementById("importFile");
  const status = document.getElementById("importStatus");
  if (!input.files.length) {
    status.textContent = "Choose a Groww CSV or Excel file first.";
    return;
  }
  const fd = new FormData();
  fd.append("file", input.files[0]);
  fd.append("kind", document.getElementById("importKind").value);
  status.textContent = "Importing...";
  const r = await fetch("/api/import", { method: "POST", body: fd });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    status.textContent = data.detail || "Import failed";
    return;
  }
  status.textContent = `Imported ${data.stocks} stock(s), ${data.mutual_funds} fund(s). Running analysis…`;
  if (data.kind === "mf" || (data.mutual_funds && !data.stocks)) currentView = "mf";
  else if (data.stocks) currentView = "stocks";
  await runAnalysis(true);
}

async function loadReportsList() {
  const reports = await fetchJSON("/api/reports");
  const sel = document.getElementById("reportSelect");
  sel.innerHTML = reports.map(r =>
    `<option value="${r.date}">${r.date}</option>`
  ).join("");
  sel.onchange = () => loadReport(sel.value);
  return reports;
}

async function loadReport(date) {
  const url = date ? `/api/report/${date}` : "/api/report/latest";
  currentData = await fetchJSON(url);
  renderDashboard();
  updateStatus(currentData);
}

function updateStatus(data) {
  const bar = document.getElementById("statusBar");
  const gen = data.generated_at ? new Date(data.generated_at).toLocaleString("en-IN") : "—";
  bar.textContent = `Updated: ${gen} · Snapshot #${data.snapshot_id || "—"}`;
}

async function pollStatus() {
  try {
    const s = await fetchJSON("/api/status");
    const btn = document.getElementById("analyzeBtn");
    if (s.analysis_running) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span>Analyzing...';
    } else {
      btn.disabled = false;
      btn.textContent = "Run Analysis";
      if (s.analysis_error) {
        document.getElementById("statusBar").textContent = "Error: " + s.analysis_error;
      }
    }
  } catch (_) {}
}

async function runAnalysis(offline = false) {
  const btn = document.getElementById("analyzeBtn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Starting...';
  await fetchJSON("/api/analyze?offline=" + (offline ? "true" : "false"), { method: "POST" });
  pollTimer = setInterval(async () => {
    await pollStatus();
    const s = await fetchJSON("/api/status");
    if (!s.analysis_running) {
      clearInterval(pollTimer);
      await loadReportsList();
      await loadReport(document.getElementById("reportSelect").value);
    }
  }, 2000);
}

function setupViewNav() {
  document.querySelectorAll(".view-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === currentView);
    btn.onclick = () => {
      currentView = btn.dataset.view;
      document.querySelectorAll(".view-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === currentView));
      renderDashboard();
    };
  });
}

function howAnalysisBox(steps) {
  const extra = (steps || []).map((s) => `<li>${s}</li>`).join("");
  return `<div class="card how-box">
    <h2>How deep analysis is done</h2>
    <ol>
      <li><strong>Bought price</strong> = your average buy (stocks) or average NAV (funds) from Groww.</li>
      <li><strong>Sell price (today)</strong> = live NSE price / latest NAV — if you exited now. Not a completed sell.</li>
      <li>Invested = qty × bought. Current = qty × sell today. P&amp;L = current − invested.</li>
      <li>Then we score concentration, MF overlap, 50/200-day trend, and write Keep / Trim / Monitor notes only.</li>
      ${extra}
    </ol>
  </div>`;
}

function renderDashboard() {
  if (!currentData) return;
  setupViewNav();
  const data = currentData;
  if (currentView === "stocks") {
    document.getElementById("app").innerHTML = renderStocksDashboard(data);
    renderCharts(
      stockSectors(data),
      (data.portfolio || {}).positions || [],
      "sectorChart",
      "holdingsChart"
    );
    return;
  }
  if (currentView === "report") {
    document.getElementById("app").innerHTML = renderMemoPage(data);
    return;
  }
  if (currentView === "mf") {
    document.getElementById("app").innerHTML = renderMfDashboard(data);
    const mfs = (data.deep_analysis || {}).mutual_funds || [];
    const total = mfs.reduce((s, m) => s + (m.market_value || 0), 0);
    renderCharts(mfWeights(mfs), mfs.map((m) => ({
      trading_symbol: (m.name || "").slice(0, 18),
      weight_pct: total ? (m.market_value / total * 100) : 0,
    })), "sectorChart", "holdingsChart");
    return;
  }
  document.getElementById("app").innerHTML = renderOverview(data);
}

function stockSectors(data) {
  const deep = data.deep_analysis || {};
  const out = {};
  Object.entries(deep.sector_weights || {}).forEach(([k, v]) => {
    if (!String(k).startsWith("MF:")) out[k] = v;
  });
  return out;
}

function mfWeights(mfs) {
  const total = mfs.reduce((s, m) => s + (m.market_value || 0), 0);
  const out = {};
  mfs.forEach((m) => {
    const cat = m.category || "Fund";
    out[cat] = (out[cat] || 0) + (total ? (m.market_value / total * 100) : 0);
  });
  return out;
}

function renderOverview(data) {
  const deep = data.deep_analysis || {};
  const memo = data.investment_memo || {};
  const portfolio = data.portfolio || {};
  const steps = memo.this_quarter || [];
  return `
    <p class="lede">${memo.headline || "Open Full memo after you run analysis."}</p>
    <div class="metrics">
      <div class="metric-card">
        <div class="metric-label">Invested</div>
        <div class="metric-value">${fmt(deep.combined_cost || portfolio.total_cost)}</div>
        <div class="metric-sub">What you paid</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">If sold today</div>
        <div class="metric-value">${fmt(deep.combined_value || portfolio.total_value)}</div>
        <div class="metric-sub">Stocks ${fmt(deep.stocks_value)} · Funds ${fmt(deep.mf_value)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Unrealized P&L</div>
        <div class="metric-value ${cls(deep.combined_pnl_pct)}">${fmt(deep.combined_pnl)} <span class="metric-sub ${cls(deep.combined_pnl_pct)}">${fmtPct(deep.combined_pnl_pct)}</span></div>
        <div class="metric-sub">Not booked</div>
      </div>
    </div>
    <div class="plan-grid">
      ${steps.map((s) => `<article class="plan-card">
        <div class="plan-num">${s.priority}</div>
        <h3>${s.title}</h3>
        <p>${s.detail}</p>
      </article>`).join("") || "<p class='metric-sub'>Run analysis to build this quarter's plan.</p>"}
    </div>
    <p class="metric-sub" style="margin-top:1.25rem">Stocks / Mutual Funds for tables. <strong>Full memo</strong> for theses. Education only.</p>
  `;
}

function renderMemoPage(data) {
  const memo = data.investment_memo || {};
  const theses = memo.stock_theses || [];
  const mfs = memo.mf_roles || [];
  const rules = memo.rules || [];
  return `
    <article class="memo">
      <p class="lede">${memo.headline || ""}</p>
      ${(memo.this_quarter || []).map((s) => `<section class="memo-block">
        <h2>${s.priority}. ${s.title}</h2>
        <p>${s.detail}</p>
      </section>`).join("")}
      <h2>Stock theses</h2>
      ${theses.map((t) => `<section class="memo-block">
        <h3>${t.name} <span class="stance">${t.stance || ""}</span></h3>
        <p class="price-line">Bought ${t.bought} → sell-today ${t.sell_today} · ${t.invested} → ${t.current} · ${t.pnl}</p>
        <p>${t.why}</p>
        <ul>
          <li><strong>Do</strong> ${t.do}</li>
          <li><strong>Don't</strong> ${t.dont}</li>
          <li><strong>Watch</strong> ${t.watch}</li>
        </ul>
      </section>`).join("")}
      <h2>Fund roles</h2>
      <table><thead><tr><th>Fund</th><th>Role</th><th>Invested</th><th>Now</th><th>P&L</th></tr></thead>
      <tbody>${mfs.map((m) => `<tr>
        <td>${(m.name || "").slice(0, 48)}</td><td>${m.role}</td>
        <td>${m.invested}</td><td>${m.current}</td><td>${m.pnl}</td>
      </tr>`).join("")}</tbody></table>
      <h2>House rules</h2>
      <ul>${rules.map((r) => `<li>${r}</li>`).join("")}</ul>
      <p class="metric-sub">${memo.sources_note || ""}</p>
    </article>
  `;
}

function renderStocksDashboard(data) {
  const deep = data.deep_analysis || {};
  const portfolio = data.portfolio || {};
  const positions = portfolio.positions || [];
  const stockPnl = portfolio.total_unrealized_pnl;
  return `
    <div class="disclaimer">Stocks only. <strong>Bought price</strong> = your avg buy. <strong>Sell price (today)</strong> = NSE LTP (Yahoo) — not a completed sell.</div>
    <div class="metrics">
      <div class="metric-card">
        <div class="metric-label">Bought (invested)</div>
        <div class="metric-value">${fmt(deep.stocks_cost || portfolio.total_cost)}</div>
        <div class="metric-sub">${positions.length} holdings</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">If sold today</div>
        <div class="metric-value">${fmt(deep.stocks_value || portfolio.total_value)}</div>
        <div class="metric-sub">qty × sell price today</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Unrealized P&L</div>
        <div class="metric-value ${cls(stockPnl)}">${fmt(stockPnl)}</div>
        <div class="metric-sub ${cls(portfolio.total_unrealized_pnl_pct)}">${fmtPct(portfolio.total_unrealized_pnl_pct)}</div>
      </div>
    </div>
    <div class="grid-2">
      <div class="card"><h2>Stock sectors</h2><div class="chart-container"><canvas id="sectorChart"></canvas></div></div>
      <div class="card"><h2>Weight</h2><div class="chart-container"><canvas id="holdingsChart"></canvas></div></div>
    </div>
    <div class="card">
      <h2>Bought price vs sell price (today)</h2>
      ${renderHoldingsTable(positions)}
    </div>
    <div class="card" style="margin-top:1rem">
      <h2>Stock suggestions</h2>
      ${renderActions(deep.strategy || {}, "stock")}
    </div>
    ${howAnalysisBox(data.analysis_method)}
  `;
}

function renderMfDashboard(data) {
  const deep = data.deep_analysis || {};
  const mfs = deep.mutual_funds || [];
  const mfPnl = (deep.mf_value || 0) - (deep.mf_cost || 0);
  const mfPct = deep.mf_cost ? mfPnl / deep.mf_cost * 100 : 0;
  return `
    <div class="disclaimer">Mutual funds only. <strong>Bought NAV</strong> = your avg purchase NAV. <strong>Sell NAV (today)</strong> = latest NAV — not a redemption.</div>
    <div class="metrics">
      <div class="metric-card">
        <div class="metric-label">Bought (invested)</div>
        <div class="metric-value">${fmt(deep.mf_cost)}</div>
        <div class="metric-sub">${mfs.length} schemes</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">If redeemed today</div>
        <div class="metric-value">${fmt(deep.mf_value)}</div>
        <div class="metric-sub">units × today’s NAV</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Unrealized P&L</div>
        <div class="metric-value ${cls(mfPnl)}">${fmt(mfPnl)}</div>
        <div class="metric-sub ${cls(mfPct)}">${fmtPct(mfPct)}</div>
      </div>
    </div>
    <div class="grid-2">
      <div class="card"><h2>By category</h2><div class="chart-container"><canvas id="sectorChart"></canvas></div></div>
      <div class="card"><h2>By fund</h2><div class="chart-container"><canvas id="holdingsChart"></canvas></div></div>
    </div>
    <div class="card">
      <h2>Bought NAV vs sell NAV (today)</h2>
      ${renderMutualFunds(mfs)}
    </div>
    <div class="card" style="margin-top:1rem">
      <h2>Fund suggestions</h2>
      ${renderActions(deep.strategy || {}, "mf")}
    </div>
    ${howAnalysisBox(data.analysis_method)}
  `;
}

function renderHoldingsTable(positions) {
  if (!positions.length) return '<div class="empty-state">No stocks. Upload a Groww stocks CSV/Excel, then open this dashboard.</div>';
  const rows = positions.map(p => {
    const bought = p.bought_price ?? p.average_price;
    const sell = p.sell_price ?? p.last_price;
    return `<tr>
      <td><strong>${p.trading_symbol}</strong></td>
      <td>${p.quantity}</td>
      <td>${fmt2(bought)}</td>
      <td>${fmt2(sell)}</td>
      <td>${fmt(p.cost_basis)}</td>
      <td>${fmt(p.market_value)}</td>
      <td class="${cls(p.unrealized_pnl)}">${fmt(p.unrealized_pnl)}</td>
      <td class="${cls(p.unrealized_pnl_pct)}">${fmtPct(p.unrealized_pnl_pct)}</td>
      <td>${p.weight_pct?.toFixed(1)}%</td>
    </tr>`;
  }).join("");
  return `<table>
    <thead><tr>
      <th>Symbol</th><th>Qty</th><th>Bought price</th><th>Sell price (today)</th>
      <th>Invested</th><th>If sold today</th><th>P&L ₹</th><th>P&L %</th><th>Weight</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function renderActions(strategy, assetType) {
  let suggestions = strategy.suggestions || [];
  if (assetType) {
    suggestions = suggestions.filter((s) => s.asset_type === assetType || (assetType === "stock" && s.asset_type === "idea"));
  }
  if (suggestions.length) {
    const titles = { trim: "Trim / concentration", monitor: "Monitor", keep: "Keep", consider: "Research later" };
    const order = ["trim", "monitor", "keep", "consider"];
    return order.map(bucket => {
      const items = suggestions.filter(s => s.bucket === bucket);
      if (!items.length) return "";
      return `<h3 style="margin:1rem 0 0.5rem"><span class="badge badge-${bucket === "consider" ? "buy" : bucket}">${titles[bucket]}</span></h3>
        ${items.map(s => `<div class="suggestion-card">
          <strong>${s.name}</strong>
          ${s.asset_type !== "idea" ? `<div class="metric-sub">Bought/invested ${fmt(s.invested)} → sell today ${fmt(s.current)} · <span class="${cls(s.pnl_pct)}">${fmt(s.pnl)} (${fmtPct(s.pnl_pct)})</span></div>` : ""}
          <p><strong>Why:</strong> ${s.why}</p>
          <p><strong>Suggestion:</strong> ${s.suggestion}</p>
          ${s.counter ? `<p class="metric-sub">${s.counter}</p>` : ""}
        </div>`).join("")}`;
    }).join("");
  }
  return '<div class="empty-state">No suggestions in this book</div>';
}

function renderMutualFunds(mfs) {
  if (!mfs.length) return `<div class="empty-state">Upload a Groww Mutual Funds CSV/Excel, then open this dashboard.</div>`;
  const total = mfs.reduce((s, m) => s + (m.market_value || 0), 0);
  const rows = mfs.map(m => {
    const bought = m.bought_price ?? m.avg_nav;
    const sell = m.sell_price ?? m.current_nav;
    const w = total ? (m.market_value / total * 100) : 0;
    return `<tr>
      <td>${(m.name || "").slice(0, 42)}</td>
      <td>${m.units ?? "—"}</td>
      <td>${fmt2(bought)}</td>
      <td>${fmt2(sell)}</td>
      <td>${fmt(m.cost_basis)}</td>
      <td>${fmt(m.market_value)}</td>
      <td class="${cls(m.unrealized_pnl)}">${fmt(m.unrealized_pnl)}</td>
      <td class="${cls(m.unrealized_pnl_pct)}">${fmtPct(m.unrealized_pnl_pct)}</td>
      <td>${w.toFixed(1)}%</td>
      <td>${m.return_1y_pct != null ? fmtPct(m.return_1y_pct) : "—"}</td>
    </tr>`;
  }).join("");
  return `<table>
    <thead><tr>
      <th>Fund</th><th>Units</th><th>Bought NAV</th><th>Sell NAV (today)</th>
      <th>Invested</th><th>If redeemed today</th><th>P&L ₹</th><th>P&L %</th><th>Weight</th><th>1Y</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function renderCharts(sectors, positions, sectorId, barId) {
  const colors = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a78bfa", "#06b6d4", "#ec4899"];
  if (sectorChart) sectorChart.destroy();
  if (holdingsChart) holdingsChart.destroy();
  const sEl = document.getElementById(sectorId);
  const bEl = document.getElementById(barId);
  if (sEl) {
    sectorChart = new Chart(sEl, {
      type: "doughnut",
      data: {
        labels: Object.keys(sectors),
        datasets: [{ data: Object.values(sectors), backgroundColor: colors, borderWidth: 0 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: "right", labels: { color: "#e2e8f0", font: { size: 11 } } } }
      }
    });
  }
  if (bEl) {
    const sorted = [...positions].sort((a, b) => (b.weight_pct || 0) - (a.weight_pct || 0));
    holdingsChart = new Chart(bEl, {
      type: "bar",
      data: {
        labels: sorted.map(p => p.trading_symbol),
        datasets: [{
          label: "Weight %",
          data: sorted.map(p => p.weight_pct),
          backgroundColor: sorted.map(p => (p.weight_pct || 0) > 15 ? "#ef4444" : "#3b82f6"),
          borderRadius: 4
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#e2e8f0" }, grid: { color: "#334155" } },
          y: { ticks: { color: "#e2e8f0" }, grid: { display: false } }
        }
      }
    });
  }
}

async function init() {
  try {
    const reports = await loadReportsList();
    if (reports.length) {
      await loadReport(reports[0].date);
    } else {
      document.getElementById("app").innerHTML = `
        <div class="empty-state">
          <h2>No reports yet</h2>
          <p style="margin:1rem 0;color:var(--muted)">Import a Groww file or run analysis.</p>
          <button class="btn" onclick="runAnalysis(true)">From files / cache</button>
        </div>`;
    }
    setInterval(pollStatus, 5000);
  } catch (e) {
    document.getElementById("app").innerHTML = `<div class="empty-state"><h2>Error</h2><p>${e.message}</p></div>`;
  }
}

init();
