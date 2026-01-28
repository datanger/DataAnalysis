/* UI-first Workbench: merge stock-selection flows into one page.
 * This file intentionally uses mock data and best-effort API calls.
 */

(function () {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const state = {
    quickTags: new Set(),
    candidates: [],
    filtered: [],
    selected: null,
    activeTab: "overview",
  };

  function fmtPct(x) {
    if (x === null || x === undefined || Number.isNaN(Number(x))) return "--";
    const n = Number(x);
    const s = (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
    return s;
  }

  function renderPriceChart(bars) {
    const chartEl = $("#price-chart");
    if (!chartEl) return;
    if (typeof ApexCharts === "undefined") {
      chartEl.innerHTML = '<div class="text-muted small">图表组件未加载（ApexCharts）。</div>';
      return;
    }
    if (!bars || bars.length === 0) {
      chartEl.innerHTML = '<div class="text-muted small">暂无K线数据。</div>';
      return;
    }

    // Destroy existing chart if any
    if (chartEl._chart) {
      chartEl._chart.destroy();
    }

    const categories = bars.map(b => b.trade_date);
    const ohlcData = bars.map(b => ({
      x: b.trade_date,
      y: [b.open, b.high, b.low, b.close]
    }));

    const options = {
      chart: {
        type: 'candlestick',
        height: 350,
        toolbar: { show: true }
      },
      series: [{
        name: 'K线',
        data: ohlcData
      }],
      xaxis: {
        type: 'datetime',
        categories: categories
      },
      yaxis: {
        tooltip: { enabled: true }
      },
      title: {
        text: 'K线图',
        align: 'left'
      }
    };

    chartEl._chart = new ApexCharts(chartEl, options);
    chartEl._chart.render();
  }

  function renderIndicatorsChart(indicators) {
    const chartEl = $("#indicators-chart");
    if (!chartEl) return;
    if (typeof ApexCharts === "undefined") {
      chartEl.innerHTML = '<div class="text-muted small">图表组件未加载（ApexCharts）。</div>';
      return;
    }
    if (!indicators || indicators.length === 0) {
      chartEl.innerHTML = '<div class="text-muted small">暂无技术指标数据。</div>';
      return;
    }

    // Destroy existing chart if any
    if (chartEl._chart) {
      chartEl._chart.destroy();
    }

    const categories = indicators.map(i => i.trade_date || i.date);
    const series = [];

    // Group indicators by type
    const grouped = {};
    indicators.forEach(ind => {
      const name = ind.indicator_name;
      if (!grouped[name]) grouped[name] = [];
      grouped[name].push(ind.value_json?.value || ind.value || 0);
    });

    // Convert to ApexCharts series format
    for (const [name, values] of Object.entries(grouped)) {
      series.push({
        name: name,
        data: values
      });
    }

    const options = {
      chart: {
        type: 'line',
        height: 300,
        toolbar: { show: true }
      },
      series: series,
      xaxis: {
        categories: categories
      },
      title: {
        text: '技术指标',
        align: 'left'
      },
      stroke: { width: 2 }
    };

    chartEl._chart = new ApexCharts(chartEl, options);
    chartEl._chart.render();
  }

  function renderNewsList(news) {
    const container = $("#wb-news-list");
    if (!container) return;

    if (!news || news.length === 0) {
      container.innerHTML = '<div class="text-muted small">暂无新闻数据</div>';
      return;
    }

    const rows = news.map((item) => {
      const publishedDate = item.published_at ? new Date(item.published_at).toLocaleDateString("zh-CN") : "--";
      const saved = Boolean(item.saved);
      const savedClass = saved ? "text-warning" : "text-muted";
      const savedIcon = saved ? "fas fa-star" : "far fa-star";
      const keywords = Array.isArray(item.keywords) && item.keywords.length ? `| 关键词: ${item.keywords.join(", ")}` : "";
      const url = item.url || "#";
      const summary = item.summary || "暂无摘要";

      return `
        <div class="list-group-item list-group-item-action">
          <div class="d-flex w-100 justify-content-between">
            <h6 class="mb-1">${item.title || "--"}</h6>
            <small class="text-muted">${publishedDate}</small>
          </div>
          <p class="mb-1 small">${summary}</p>
          <div class="d-flex justify-content-between align-items-center">
            <small class="text-muted">
              <i class="fas fa-newspaper me-1"></i>${item.source_site || "--"}
              ${keywords}
            </small>
            <div class="btn-group btn-group-sm">
              <a href="${url}" target="_blank" rel="noopener" class="btn btn-outline-primary btn-sm" title="打开原文">
                <i class="fas fa-external-link-alt"></i>
              </a>
              <button class="btn btn-outline-secondary btn-sm wb-btn-save-news" data-news-id="${item.news_id}" data-saved="${saved ? "1" : "0"}" title="收藏/取消收藏">
                <i class="${savedIcon} ${savedClass}"></i>
              </button>
            </div>
          </div>
        </div>
      `;
    });

    container.innerHTML = `<div class="list-group list-group-flush">${rows.join("")}</div>`;

    // Bind once (event delegation; the list is re-rendered frequently)
    if (container.dataset.bound !== "1") {
      container.dataset.bound = "1";
      container.addEventListener("click", (e) => {
        const btn = e.target.closest(".wb-btn-save-news");
        if (!btn) return;
        e.preventDefault();

        const newsId = btn.dataset.newsId;
        const currentSaved = btn.dataset.saved === "1";
        const newSaved = !currentSaved;

        api("POST", `/news/${newsId}/save`, { saved: newSaved })
          .then(() => {
            btn.dataset.saved = newSaved ? "1" : "0";
            const icon = btn.querySelector("i");
            if (icon) {
              icon.classList.toggle("fas", newSaved);
              icon.classList.toggle("far", !newSaved);
              icon.classList.toggle("text-warning", newSaved);
              icon.classList.toggle("text-muted", !newSaved);
            }
            if (typeof showSuccess === "function") showSuccess(newSaved ? "已收藏新闻" : "已取消收藏");
          })
          .catch((err) => {
            if (typeof showError === "function") showError(`操作失败: ${err.message}`);
          });
      });
    }
  }

  async function refreshNews(symbol, exchange) {
    try {
      // Try to ingest mock news first
      await api('POST', '/news/ingest_mock', { symbol, exchange, count: 10 });

      // Then load news
      const result = await api('GET', `/news?symbol=${symbol}&exchange=${exchange}&limit=50`);
      if (result && result.data) {
        renderNewsList(result.data);
        showSuccess('新闻刷新成功');
      }
    } catch (e) {
      console.error('Failed to refresh news:', e);
      showError(`新闻刷新失败: ${e.message}`);
    }
  }

  function formatStockReport(report) {
    let md = `# ${report.symbol} 个股研究报告\n\n`;
    md += `**生成时间**: ${report.generated_at}\n`;
    md += `**报告类型**: ${report.report_type}\n\n`;

    const sections = report.sections;

    // Executive Summary
    md += `## 执行摘要\n\n`;
    md += `- **综合评分**: ${sections.executive_summary.overall_score}\n`;
    md += `- **评级**: ${sections.executive_summary.score_level}\n\n`;
    if (sections.executive_summary.key_highlights.length > 0) {
      md += `**亮点**:\n`;
      sections.executive_summary.key_highlights.forEach(h => md += `- ${h}\n`);
      md += `\n`;
    }
    if (sections.executive_summary.key_concerns.length > 0) {
      md += `**关注点**:\n`;
      sections.executive_summary.key_concerns.forEach(c => md += `- ${c}\n`);
      md += `\n`;
    }

    // Technical Analysis
    md += `## 技术分析\n\n`;
    md += `- **趋势**: ${sections.technical_analysis.trend}\n`;
    if (sections.technical_analysis.support_level) {
      md += `- **支撑位**: ${sections.technical_analysis.support_level.toFixed(2)}\n`;
    }
    if (sections.technical_analysis.resistance_level) {
      md += `- **阻力位**: ${sections.technical_analysis.resistance_level.toFixed(2)}\n`;
    }
    md += `\n`;

    // Fundamental Analysis
    md += `## 基本面分析\n\n`;
    md += `### 估值\n`;
    md += `- PE: ${sections.fundamental_analysis.valuation.pe || '--'}\n`;
    md += `- PB: ${sections.fundamental_analysis.valuation.pb || '--'}\n`;
    md += `- PS: ${sections.fundamental_analysis.valuation.ps || '--'}\n\n`;

    md += `### 盈利能力\n`;
    md += `- ROE: ${sections.fundamental_analysis.profitability.roe || '--'}%\n`;
    md += `- 毛利率: ${sections.fundamental_analysis.profitability.gross_margin || '--'}%\n`;
    md += `- 净利率: ${sections.fundamental_analysis.profitability.net_profit_margin || '--'}%\n\n`;

    // Capital Flow
    md += `## 资金流向\n\n`;
    md += `- **净流入**: ${sections.capital_flow.net_inflow ? (sections.capital_flow.net_inflow / 10000).toFixed(2) + '万' : '--'}\n`;
    md += `- **主力流入**: ${sections.capital_flow.main_inflow ? (sections.capital_flow.main_inflow / 10000).toFixed(2) + '万' : '--'}\n`;
    md += `- **北向净流入**: ${sections.capital_flow.northbound_net ? (sections.capital_flow.northbound_net / 10000).toFixed(2) + '万' : '--'}\n`;
    md += `- **流向趋势**: ${sections.capital_flow.flow_trend}\n\n`;

    // Score Analysis
    md += `## 评分分析\n\n`;
    md += `- **当前评分**: ${sections.score_analysis.current_score}\n`;
    md += `- **评分趋势**: ${sections.score_analysis.score_trend}\n\n`;
    if (sections.score_analysis.reasons && sections.score_analysis.reasons.length > 0) {
      md += `**评分原因**:\n`;
      sections.score_analysis.reasons.forEach(r => md += `- ${r}\n`);
      md += `\n`;
    }

    // Risk Factors
    if (sections.risk_factors && sections.risk_factors.length > 0) {
      md += `## 风险因素\n\n`;
      sections.risk_factors.forEach(r => md += `- ${r}\n`);
      md += `\n`;
    }

    // Recommendations
    if (sections.recommendations && sections.recommendations.length > 0) {
      md += `## 投资建议\n\n`;
      sections.recommendations.forEach(rec => md += `- ${rec}\n`);
      md += `\n`;
    }

    // Performance
    if (sections.performance) {
      md += `## 表现回顾\n\n`;
      if (sections.performance["1_week"] !== null) {
        md += `- **1周涨跌幅**: ${sections.performance["1_week"].toFixed(2)}%\n`;
      }
      if (sections.performance["1_month"] !== null) {
        md += `- **1月涨跌幅**: ${sections.performance["1_month"].toFixed(2)}%\n`;
      }
      if (sections.performance["ytd"] !== null) {
        md += `- **年初至今**: ${sections.performance["ytd"].toFixed(2)}%\n`;
      }
      md += `\n`;
    }

    md += `---\n`;
    md += `*本报告由本地智能投资工作台自动生成*\n`;

    return md;
  }

  function downloadAsMarkdown(content, filename) {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // Configure API base URL
  const API_BASE = window.WORKBENCH_API_BASE || 'http://127.0.0.1:8000/api/v1';

  function api(method, url, body) {
    const init = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) init.body = JSON.stringify(body);
    // Use absolute URL with API base
    const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`;
    return fetch(fullUrl, init).then(async (r) => {
      const json = await r.json().catch(() => ({}));
      if (!r.ok) {
        const errMsg = json.error?.message || json.error?.code || json.message || `HTTP ${r.status}`;
        throw new Error(errMsg);
      }
      return json;
    });
  }

  function getFilters() {
    const index = ($("#wb-index")?.value || "").trim();
    const industry = ($("#wb-industry")?.value || "").trim();
    const board = ($("#wb-board")?.value || "").trim();
    const custom = ($("#wb-custom")?.value || "").trim();
    const minScore = Number(($("#wb-min-score")?.value || "60").trim());
    return { index, industry, board, custom, minScore, tags: Array.from(state.quickTags) };
  }

  function updateFilterSummary() {
    const f = getFilters();
    const parts = [];
    if (f.index) parts.push(`指数:${f.index}`);
    if (f.industry) parts.push(`行业:${f.industry}`);
    if (f.board) parts.push(`板块:${f.board}`);
    if (f.custom) parts.push(`自选:${f.custom.split(",").length}只`);
    parts.push(`>=${f.minScore}`);
    if (f.tags.length) parts.push(`条件:${f.tags.length}`);
    $("#wb-filter-summary").textContent = parts.join(" · ") || "默认";
  }

  function mockCandidates() {
    return [
      { code: "600519", name: "贵州茅台", industry: "白酒", score: 92, price: 1688.8, chg: 1.23, tags: ["强势", "抱团"], attn: "高" },
      { code: "000001", name: "平安银行", industry: "银行", score: 78, price: 12.34, chg: -0.62, tags: ["低估", "修复"], attn: "中" },
      { code: "300750", name: "宁德时代", industry: "锂电", score: 83, price: 158.6, chg: 2.81, tags: ["反弹", "成长"], attn: "高" },
      { code: "601318", name: "中国平安", industry: "保险", score: 74, price: 36.21, chg: 0.35, tags: ["价值", "修复"], attn: "中" },
      { code: "688981", name: "中芯国际", industry: "半导体", score: 81, price: 43.2, chg: 1.05, tags: ["主题", "周期"], attn: "中" },
      { code: "002594", name: "比亚迪", industry: "汽车", score: 80, price: 188.5, chg: -1.12, tags: ["趋势", "景气"], attn: "高" },
    ];
  }

  function applySearchAndSort() {
    const q = ($("#wb-search")?.value || "").trim().toLowerCase();
    const sort = ($("#wb-sort")?.value || "score_desc").trim();
    const f = getFilters();

    let rows = state.candidates.slice();

    // Min score filter (UI-first).
    rows = rows.filter((x) => Number(x.score || 0) >= f.minScore);

    // Simple search across code/name/industry/tags.
    if (q) {
      rows = rows.filter((x) => {
        const blob = [x.code, x.name, x.industry, ...(x.tags || [])].join(" ").toLowerCase();
        return blob.includes(q);
      });
    }

    // Sort
    const by = {
      score_desc: (a, b) => (b.score || 0) - (a.score || 0),
      chg_desc: (a, b) => (b.chg || 0) - (a.chg || 0),
      chg_asc: (a, b) => (a.chg || 0) - (b.chg || 0),
      name_asc: (a, b) => String(a.name || "").localeCompare(String(b.name || ""), "zh"),
    }[sort];
    if (by) rows.sort(by);

    state.filtered = rows;
    renderList();
  }

  function renderList() {
    const el = $("#wb-list");
    if (!el) return;

    $("#wb-count").textContent = String(state.filtered.length || 0);
    el.innerHTML = "";

    if (!state.filtered.length) {
      el.innerHTML = `<div class="text-muted small">暂无候选（调整条件或点击“扫描”）</div>`;
      return;
    }

    for (const item of state.filtered) {
      const div = document.createElement("div");
      div.className = "wb-item" + (state.selected && state.selected.code === item.code ? " active" : "");
      div.setAttribute("role", "button");
      div.tabIndex = 0;
      div.dataset.code = item.code;
      div.innerHTML = `
        <div class="wb-item-top">
          <div>
            <div class="wb-name">${item.name || "--"}</div>
            <div class="wb-code">${item.code || "--"} · ${item.industry || "--"}</div>
          </div>
          <div class="text-end">
            <div class="fw-bold">${item.score ?? "--"}</div>
            <div class="small ${Number(item.chg) >= 0 ? "text-success" : "text-danger"}">${fmtPct(item.chg)}</div>
          </div>
        </div>
        <div class="wb-tags">
          ${(item.tags || []).slice(0, 4).map((t) => `<span class="wb-tag">${t}</span>`).join("")}
        </div>
      `;
      div.addEventListener("click", () => { select(item.code); });
      div.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { select(item.code); }
      });
      el.appendChild(div);
    }
  }

  function setTab(name) {
    state.activeTab = name;
    $$(".wb-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    $$("[data-pane]").forEach((p) => p.classList.toggle("d-none", p.dataset.pane !== name));
  }

  async function select(code) {
    const found = state.candidates.find((x) => x.code === code) || null;
    state.selected = found;
    renderList();
    await renderSelected();
  }

  async function renderSelected() {
    const x = state.selected;
    $("#wb-selected").textContent = x ? `${x.name} ${x.code}` : "未选择";
    $("#wb-kv-price").textContent = x ? String(x.price ?? "--") : "--";
    $("#wb-kv-chg").textContent = x ? fmtPct(x.chg) : "--";
    $("#wb-kv-score").textContent = x ? String(x.score ?? "--") : "--";
    $("#wb-kv-attn").textContent = x ? String(x.attn ?? "--") : "--";

    if (!x) {
      $("#wb-one-liner").textContent = "请选择股票查看结论。";
      $("#wb-next-actions").innerHTML = `<span class="badge text-bg-secondary">等待选择</span>`;
      $("#wb-factors").innerHTML = "";
      $("#wb-tech-trend").textContent = "--";
      $("#wb-tech-momo").textContent = "--";
      $("#wb-fund-profit").textContent = "--";
      $("#wb-fund-valuation").textContent = "--";
      $("#wb-flow-5d").textContent = "--";
      $("#wb-flow-main").textContent = "--";
      $("#wb-industry-heat").textContent = "--";
      $("#wb-industry-peers").textContent = "--";
      $("#wb-scn-cases").textContent = "--";
      $("#wb-scn-risks").textContent = "--";
      return;
    }

    $("#wb-one-liner").textContent = `加载 ${x.name} 工作台数据…`;
    $("#wb-next-actions").innerHTML = `<span class="badge text-bg-secondary">加载中</span>`;

    try {
      // Load workspace data from workbench API
      const workspace = await api("GET", `/stocks/SSE/${x.code}/workspace`);
      const data = workspace.data;

      // Update latest score
      if (data.latest_score) {
        $("#wb-kv-score").textContent = String(data.latest_score.score_total ?? "--");
        const breakdown = data.latest_score.breakdown_json || {};
        const reasons = data.latest_score.reasons_json || [];
        $("#wb-one-liner").textContent = reasons.length > 0 ? reasons.join("; ") : "技术面：暂无明显信号";
      } else {
        $("#wb-one-liner").textContent = `${x.name} 当前处于"${(x.tags || [])[0] || "待判定"}"状态：优先验证消息/资金与趋势一致性。`;
      }

      // Update basic metrics
      if (data.price_bars && data.price_bars.length > 0) {
        const latestBar = data.price_bars[data.price_bars.length - 1];
        $("#wb-kv-price").textContent = latestBar.close?.toFixed(2) ?? "--";
        if (latestBar.pre_close) {
          const chg = ((latestBar.close - latestBar.pre_close) / latestBar.pre_close) * 100;
          $("#wb-kv-chg").textContent = fmtPct(chg);
        }
      }

      // Update technical indicators and render charts
      if (data.price_bars && data.price_bars.length > 0) {
        renderPriceChart(data.price_bars);
        renderIndicatorsChart(data.indicators || []);
      }

      if (data.indicators && data.indicators.length > 0) {
        const indicators = data.indicators;
        $("#wb-tech-trend").textContent = indicators.map(ind => {
          if (ind.indicator_name === 'MA') return `MA: ${ind.value_json?.ma5?.toFixed(2) ?? '--'}`;
          if (ind.indicator_name === 'RSI') return `RSI: ${ind.value?.toFixed(2) ?? '--'}`;
          return `${ind.indicator_name}: ${JSON.stringify(ind.value_json)}`;
        }).join(", ");
        $("#wb-tech-momo").textContent = "技术指标已加载，点击查看详情";
      } else {
        $("#wb-tech-trend").textContent = "暂无技术指标数据";
        $("#wb-tech-momo").textContent = "暂无动量数据";
      }

      // Update fundamentals
      if (data.fundamentals_summary) {
        const f = data.fundamentals_summary;
        $("#wb-fund-profit").textContent = `ROE: ${f.roe?.toFixed(2) ?? '--'}%, 净利率: ${(f.net_profit_margin || 0).toFixed(2)}%`;
        $("#wb-fund-valuation").textContent = `PE: ${f.pe_ttm?.toFixed(2) ?? '--'}, PB: ${f.pb?.toFixed(2) ?? '--'}`;
      } else {
        $("#wb-fund-profit").textContent = "暂无基本面数据";
        $("#wb-fund-valuation").textContent = "暂无估值数据";
      }

      // Update capital flow
      if (data.capital_flow) {
        const cf = data.capital_flow;
        const netInflow = cf.net_inflow ? (cf.net_inflow / 10000).toFixed(2) + '万' : '--';
        const mainInflow = cf.main_inflow ? (cf.main_inflow / 10000).toFixed(2) + '万' : '--';
        const northbound = cf.northbound_net ? (cf.northbound_net / 10000).toFixed(2) + '万' : '--';

        $("#wb-flow-5d").textContent = `净流入: ${netInflow}`;
        $("#wb-flow-main").textContent = `主力流入: ${mainInflow} | 北向净流入: ${northbound}`;
      } else {
        $("#wb-flow-5d").textContent = "暂无资金流数据";
        $("#wb-flow-main").textContent = "暂无资金流数据";
      }

      // Update news
      if (data.news && data.news.length > 0) {
        renderNewsList(data.news);
      } else {
        const el = $("#wb-news-list");
        if (el) el.innerHTML = '<div class="text-muted small">暂无新闻数据</div>';
      }

      // Update industry info
      $("#wb-industry-heat").textContent = `行业: ${x.industry || "--"}`;
      $("#wb-industry-peers").textContent = "暂无同行数据";

      // Update scenario
      if (data.latest_plan) {
        const plan = data.latest_plan.plan_json || {};
        $("#wb-scn-cases").textContent = plan.direction || "LONG";
        $("#wb-scn-risks").textContent = (plan.risk_notes || []).join(", ") || "暂无风险提示";
      } else {
        $("#wb-scn-cases").textContent = "暂无情景分析";
        $("#wb-scn-risks").textContent = "暂无风险提示";
      }

      // Update next actions
      $("#wb-next-actions").innerHTML = `
        <span class="badge text-bg-primary me-1">看消息面</span>
        <span class="badge text-bg-warning text-dark me-1">核对资金</span>
        <span class="badge text-bg-success me-1">设置观察价</span>
        <span class="badge text-bg-secondary">写研究纪要</span>
      `;

      // Update factors
      $("#wb-factors").innerHTML = [
        { t: "趋势", cls: "good" },
        { t: "估值", cls: "warn" },
        { t: "资金", cls: "good" },
        { t: "景气", cls: "warn" },
        { t: "事件", cls: "bad" },
      ]
        .map((f) => `<span class="wb-tag ${f.cls}">${f.t}</span>`)
        .join("");

    } catch (e) {
      console.error("Failed to load workspace:", e);
      $("#wb-one-liner").textContent = `${x.name} 工作台数据加载失败: ${e.message}`;
      $("#wb-next-actions").innerHTML = `<span class="badge text-bg-danger">加载失败</span>`;
    }
  }

  async function runScan() {
    updateFilterSummary();
    const f = getFilters();
    $("#wb-list-hint").textContent = "扫描中…";

    try {
      // First, create a radar template (if needed)
      const templates = await api("GET", "/radar/templates");
      let templateId = null;

      if (templates.data && templates.data.length > 0) {
        templateId = templates.data[0].template_id;
      } else {
        // Create a basic template
        const newTemplate = await api("POST", "/radar/templates", {
          name: "默认扫描",
          universe: {
            type: "all",  // all, index, custom
            index: f.index || "",
            custom: f.custom ? f.custom.split(",").map(s => s.trim()) : []
          },
          rules: [
            { field: "score_total", op: "gte", value: f.minScore }
          ]
        });
        templateId = newTemplate.data.template_id;
      }

      // Run radar scan
      const scanResult = await api("POST", "/radar/run", {
        template_id: templateId,
        async: true
      });

      const taskId = scanResult.data.task_id;
      if (!taskId) throw new Error("missing task_id");

      $("#wb-list-hint").textContent = `扫描任务已启动，ID: ${taskId}，等待结果…`;

      // Poll for results
      const deadline = Date.now() + 60_000;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 2000));
        const results = await api("GET", `/radar/results?task_id=${taskId}&limit=100`);

        if (results.data && results.data.length > 0) {
          const rows = results.data.map((r) => ({
            code: String(r.symbol || ""),
            name: String(r.symbol || ""), // Will be filled by instruments lookup
            industry: String(r.industry || "--"),
            score: Number(r.score_total || 0),
            price: r.price || null,
            chg: r.change_pct ?? r.pct_chg ?? r.change ?? r.chg,
            tags: r.reasons ? [String(r.reasons[0] || "")] : [],
            attn: "中",
          }));
          state.candidates = rows;
          state.selected = null;
          applySearchAndSort();
          $("#wb-list-hint").textContent = `扫描完成，找到 ${rows.length} 个候选。`;
          return;
        }
      }
      throw new Error("scan timeout");
    } catch (e) {
      console.error("Scan failed:", e);
      // Fall back to mock data with real instruments
      state.candidates = await loadMockCandidatesWithRealData();
      state.selected = null;
      applySearchAndSort();
      $("#wb-list-hint").textContent = `使用示例数据（扫描失败: ${e.message}）。`;
    }
  }

  async function loadMockCandidatesWithRealData() {
    try {
      // Load real instruments from API
      const instruments = await api("GET", "/instruments/search?q=600519");
      if (instruments.data && instruments.data.length > 0) {
        const realCodes = instruments.data.slice(0, 6).map(x => x.symbol);
        return [
          { code: "600519", name: "贵州茅台", industry: "白酒", score: 92, price: 1688.8, chg: 1.23, tags: ["强势", "抱团"], attn: "高" },
          { code: "000001", name: "平安银行", industry: "银行", score: 78, price: 12.34, chg: -0.62, tags: ["低估", "修复"], attn: "中" },
          { code: "300750", name: "宁德时代", industry: "锂电", score: 83, price: 158.6, chg: 2.81, tags: ["反弹", "成长"], attn: "高" },
          { code: "601318", name: "中国平安", industry: "保险", score: 74, price: 36.21, chg: 0.35, tags: ["价值", "修复"], attn: "中" },
          { code: "688981", name: "中芯国际", industry: "半导体", score: 81, price: 43.2, chg: 1.05, tags: ["主题", "周期"], attn: "中" },
          { code: "002594", name: "比亚迪", industry: "汽车", score: 80, price: 188.5, chg: -1.12, tags: ["趋势", "景气"], attn: "高" },
        ];
      }
    } catch (e) {
      console.error("Failed to load instruments:", e);
    }
    return mockCandidates();
  }

  async function clearAll() {
    state.quickTags.clear();
    $("#wb-index").value = "";
    $("#wb-industry").value = "";
    $("#wb-board").value = "";
    $("#wb-custom").value = "";
    $("#wb-min-score").value = "60";
    $("#wb-search").value = "";
    $("#wb-sort").value = "score_desc";
    $$("#wb-quick-tags [data-tag]").forEach((b) => b.classList.remove("btn-secondary"));
    state.candidates = mockCandidates();
    state.selected = null;
    updateFilterSummary();
    applySearchAndSort();
    await renderSelected();
    $("#wb-list-hint").textContent = "已清空，显示示例候选。";
  }

  function setup() {
    // Quick tags toggle
    $$("#wb-quick-tags [data-tag]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tag = btn.dataset.tag;
        if (!tag) return;
        if (state.quickTags.has(tag)) {
          state.quickTags.delete(tag);
          btn.classList.remove("btn-secondary");
        } else {
          state.quickTags.add(tag);
          btn.classList.add("btn-secondary");
        }
        updateFilterSummary();
      });
    });

    // Tabs
    $$(".wb-tab").forEach((t) => t.addEventListener("click", () => setTab(t.dataset.tab)));

    // Filters => summary
    ["#wb-index", "#wb-industry", "#wb-board", "#wb-custom", "#wb-min-score"].forEach((id) => {
      $(id)?.addEventListener("input", updateFilterSummary);
      $(id)?.addEventListener("change", updateFilterSummary);
    });

    // Search/sort
    $("#wb-search")?.addEventListener("input", applySearchAndSort);
    $("#wb-sort")?.addEventListener("change", applySearchAndSort);

    // Actions
    $("#wb-btn-scan")?.addEventListener("click", () => { runScan(); });
    $("#wb-btn-clear")?.addEventListener("click", () => { clearAll(); });
    $("#wb-btn-export")?.addEventListener("click", () => {
      // UI preview: export the filtered list as JSON.
      const blob = new Blob([JSON.stringify(state.filtered, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "workbench_candidates.json";
      a.click();
      URL.revokeObjectURL(a.href);
    });

    // Refresh news
    $("#wb-btn-refresh-news")?.addEventListener("click", () => {
      if (state.selected) {
        refreshNews(state.selected.code, 'SSE');
      } else {
        showInfo('请先选择股票');
      }
    });

    // Generate report
    $("#wb-btn-generate-report")?.addEventListener("click", async () => {
      if (!state.selected) {
        showInfo('请先选择股票');
        return;
      }

      try {
        showInfo('正在生成报告...');
        const result = await api('POST', '/reports/stock', {
          symbol: state.selected.code,
          exchange: 'SSE',
          report_type: 'comprehensive'
        });

        if (result && result.data) {
          const report = result.data;
          const reportContent = formatStockReport(report);
          downloadAsMarkdown(reportContent, `stock_report_${state.selected.code}_${new Date().toISOString().slice(0,10)}.md`);
          showSuccess('报告已生成并下载');
        }
      } catch (e) {
        console.error('Failed to generate report:', e);
        showError(`报告生成失败: ${e.message}`);
      }
    });

    // Compact mode toggle
    $("#wb-toggle-compact")?.addEventListener("click", () => {
      const container = document.querySelector(".container-fluid.wb");
      if (!container) return;

      const isCompact = container.classList.contains("wb-compact");
      if (isCompact) {
        container.classList.remove("wb-compact");
        $("#wb-toggle-compact").innerHTML = '<i class="fas fa-compress-alt me-1"></i>紧凑模式';
        showInfo('已切换到标准模式');
      } else {
        container.classList.add("wb-compact");
        $("#wb-toggle-compact").innerHTML = '<i class="fas fa-expand-alt me-1"></i>标准模式';
        showInfo('已切换到紧凑模式');
      }

      // 保存用户偏好到localStorage
      localStorage.setItem('workbench-compact-mode', !isCompact ? 'true' : 'false');
    });

    // 检查用户偏好的紧凑模式设置
    const savedCompactMode = localStorage.getItem('workbench-compact-mode');
    if (savedCompactMode === 'false') {
      const container = document.querySelector(".container-fluid.wb");
      if (container) {
        container.classList.remove("wb-compact");
        $("#wb-toggle-compact").innerHTML = '<i class="fas fa-compress-alt me-1"></i>紧凑模式';
      }
    }

    // Initial state: show sample candidates.
    state.candidates = mockCandidates();
    updateFilterSummary();
    applySearchAndSort();
    renderSelected();
    setTab("overview");

    // If a symbol is provided (from global search), pre-filter and auto-select when possible.
    const sym = new URLSearchParams(window.location.search || "").get("symbol");
    if (sym) {
      const s = sym.trim();
      const q = $("#wb-search");
      if (q) q.value = s;
      applySearchAndSort();
      const exact = state.candidates.find((x) => x.code === s) || state.filtered.find((x) => x.code === s);
      if (exact) { select(s); }
    }
  }

  // Initialize when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
})();
