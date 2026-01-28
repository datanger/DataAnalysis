async function api(path, opts) {
  const res = await fetch(path, opts);
  const json = await res.json().catch(() => ({}));
  if (!res.ok || json.ok === false) {
    const err = json.error ? `${json.error.code}: ${json.error.message}` : `HTTP ${res.status}`;
    throw new Error(err);
  }
  return json.data;
}

function $(id) {
  return document.getElementById(id);
}

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

async function refreshHealth() {
  const data = await api("/api/v1/health");
  $("health").textContent = pretty(data);
}

async function listTasks() {
  const data = await api("/api/v1/tasks");
  $("tasks").textContent = pretty(data);
}

async function ingestInstruments() {
  const data = await api("/api/v1/tasks/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "ingest_instruments", payload: {} }),
  });
  await listTasks();
  return data;
}

async function ingestBars() {
  const symbol = $("barsSymbol").value.trim();
  const exchange = $("barsExchange").value;
  const start_date = $("barsStart").value.trim();
  const data = await api("/api/v1/tasks/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type: "ingest_bars_daily",
      payload: { symbols: [{ symbol, exchange }], start_date },
    }),
  });
  await listTasks();
  return data;
}

async function ingestFundamentals() {
  const symbol = $("barsSymbol").value.trim();
  const exchange = $("barsExchange").value;
  const data = await api("/api/v1/tasks/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type: "ingest_fundamentals_daily",
      payload: { symbols: [{ symbol, exchange }] },
    }),
  });
  await listTasks();
  return data;
}

async function ingestCapitalFlow() {
  const symbol = $("barsSymbol").value.trim();
  const exchange = $("barsExchange").value;
  const data = await api("/api/v1/tasks/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type: "ingest_capital_flow_daily",
      payload: { symbols: [{ symbol, exchange }] },
    }),
  });
  await listTasks();
  return data;
}

async function loadWorkspace() {
  const symbol = $("wsSymbol").value.trim();
  const exchange = $("wsExchange").value;
  const data = await api(`/api/v1/stocks/${exchange}/${symbol}/workspace`);
  $("workspace").textContent = pretty(data);
}

async function score() {
  const symbol = $("spnSymbol").value.trim();
  const exchange = $("spnExchange").value;
  const data = await api("/api/v1/scores/calc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, exchange }),
  });
  $("spnOut").textContent = pretty(data);
}

async function genPlan() {
  const symbol = $("spnSymbol").value.trim();
  const exchange = $("spnExchange").value;
  const data = await api("/api/v1/plans/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, exchange }),
  });
  $("spnOut").textContent = pretty(data);
}

async function saveNote() {
  const symbol = $("spnSymbol").value.trim();
  const exchange = $("spnExchange").value;
  const content_md = $("noteContent").value;
  const data = await api("/api/v1/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, exchange, content_md }),
  });
  $("spnOut").textContent = pretty(data);
}

async function createPortfolio() {
  const name = $("pfName").value.trim();
  const initial_cash = Number($("pfCash").value.trim() || "0");
  const data = await api("/api/v1/portfolios", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, initial_cash }),
  });
  $("draftPortfolioId").value = data.portfolio_id;
  await listPortfolios();
}

async function listPortfolios() {
  const data = await api("/api/v1/portfolios");
  $("portfolios").textContent = pretty(data);
}

async function createDraft() {
  const portfolio_id = $("draftPortfolioId").value.trim();
  const symbol = $("draftSymbol").value.trim();
  const exchange = $("draftExchange").value;
  const side = $("draftSide").value;
  const price = Number($("draftPrice").value.trim());
  const qty = Number($("draftQty").value.trim());
  const data = await api("/api/v1/order_drafts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      portfolio_id,
      symbol,
      exchange,
      side,
      order_type: "LIMIT",
      price,
      qty,
      origin: "manual",
    }),
  });
  $("draftIdOne").value = data.draft_id;
  await listDrafts();
}

async function listDrafts() {
  const portfolio_id = $("draftPortfolioId").value.trim();
  const data = await api(`/api/v1/order_drafts?portfolio_id=${encodeURIComponent(portfolio_id)}`);
  $("drafts").textContent = pretty(data);
}

async function riskCheck() {
  const draft_id = $("draftIdOne").value.trim();
  const data = await api("/api/v1/risk/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft_ids: [draft_id] }),
  });
  $("riskcheckId").value = data.riskcheck_id;
  $("tradeOut").textContent = pretty(data);
}

async function simConfirm() {
  const draft_id = $("draftIdOne").value.trim();
  const riskcheck_id = $("riskcheckId").value.trim();
  const data = await api("/api/v1/sim/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft_ids: [draft_id], riskcheck_id }),
  });
  $("tradeOut").textContent = pretty(data);
}

function wire(id, fn) {
  $(id).addEventListener("click", async () => {
    try {
      await fn();
    } catch (e) {
      alert(String(e.message || e));
    }
  });
}

wire("btnHealth", refreshHealth);
wire("btnIngestInstruments", ingestInstruments);
wire("btnIngestBars", ingestBars);
wire("btnIngestFundamentals", ingestFundamentals);
wire("btnIngestCapitalFlow", ingestCapitalFlow);
wire("btnWorkspace", loadWorkspace);
wire("btnScore", score);
wire("btnPlan", genPlan);
wire("btnNote", saveNote);
wire("btnCreatePortfolio", createPortfolio);
wire("btnListPortfolios", listPortfolios);
wire("btnCreateDraft", createDraft);
wire("btnListDrafts", listDrafts);
wire("btnRisk", riskCheck);
wire("btnConfirm", simConfirm);

// Initial load
refreshHealth().catch(() => {});
listTasks().catch(() => {});
listPortfolios().catch(() => {});
