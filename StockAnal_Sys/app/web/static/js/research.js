/* Research Center UI:
 * - merges "agent assistant" + "Q&A" into a single conversation + workspace
 * - UI-first: no backend dependency; best-effort loads news sources from /api/latest_news
 */

(function () {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const state = {
    mode: "qa", // qa | research
    target: "",
    messages: [],
  };

  function esc(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function nowHHMM() {
    const d = new Date();
    return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  }

  function renderMsgCount() {
    $("#rc-msg-count").textContent = String(state.messages.length);
  }

  function appendMessage(role, contentHtml) {
    const chat = $("#rc-chat");
    if (!chat) return;

    const wrap = document.createElement("div");
    wrap.className = "rc-msg " + (role === "user" ? "rc-msg-user" : "rc-msg-assistant");
    wrap.innerHTML = `
      <div class="rc-bubble">
        <div class="small text-muted mb-1">${role === "user" ? "你" : "助手"} · ${nowHHMM()} · ${state.mode === "qa" ? "问答" : "研究"}</div>
        <div>${contentHtml}</div>
      </div>
    `;
    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
  }

  function setMode(mode) {
    state.mode = mode;
    $("#rc-mode-qa")?.classList.toggle("active", mode === "qa");
    $("#rc-mode-research")?.classList.toggle("active", mode === "research");
    $("#rc-mode-badge").textContent = mode === "qa" ? "问答" : "研究";
  }

  function setTarget(target) {
    state.target = (target || "").trim();
    $("#rc-active-target").textContent = state.target ? `对象：${state.target}` : "未绑定对象";
  }

  function setTab(name) {
    $$(".rc-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    $$("[data-pane]").forEach((p) => p.classList.toggle("d-none", p.dataset.pane !== name));
  }

  async function apiGet(url) {
    const r = await fetch(url);
    const json = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(json.error || `HTTP ${r.status}`);
    return json;
  }

  async function apiV1(method, path, body) {
    // Prefer the global helper injected by layout.html (unifies base URL + errors).
    if (window.App && typeof window.App.apiV1 === "function") {
      return window.App.apiV1(method, path, body);
    }

    const base = window.WORKBENCH_API_BASE || "http://127.0.0.1:8000/api/v1";
    const url = path.startsWith("http") ? path : `${base}${path}`;
    const init = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) init.body = JSON.stringify(body);
    const r = await fetch(url, init);
    const json = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(json.error?.message || json.message || `HTTP ${r.status}`);
    return json;
  }

  function renderSources(items) {
    const el = $("#rc-sources");
    if (!el) return;
    el.innerHTML = "";

    if (!items || !items.length) {
      el.innerHTML = `<div class="rc-empty"><div class="fw-semibold">暂无可用消息</div><div class="small text-muted mt-1">可在“消息面”窗口刷新新闻。</div></div>`;
      return;
    }

    for (const n of items.slice(0, 18)) {
      const title = (n.title || n.content || "").slice(0, 60);
      const time = n.time || n.datetime || n.pub_time || "";
      const src = n.source || n.media || "";
      const div = document.createElement("div");
      div.className = "rc-source";
      div.innerHTML = `
        <div class="t">${esc(title || "新闻")}</div>
        <div class="m">${esc([time, src].filter(Boolean).join(" · "))}</div>
      `;
      el.appendChild(div);
    }
  }

  async function loadSources() {
    try {
      const json = await apiGet("/api/latest_news?days=1&limit=80&important=0&type=all");
      renderSources(json.news || []);
    } catch (e) {
      renderSources([]);
    }
  }

  function ensureReportVisible() {
    $("#rc-report-empty")?.classList.add("d-none");
    $("#rc-report")?.classList.remove("d-none");
  }

  function fillReport(report) {
    ensureReportVisible();
    const r = report || {};
    $("#rc-report-conclusion").textContent = r.conclusion || "--";

    const evidence = Array.isArray(r.evidence) ? r.evidence : [];
    $("#rc-report-evidence").innerHTML = evidence.length
      ? `<ul class="small mb-0">${evidence.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
      : `<div class="small text-muted">暂无依据</div>`;

    const risks = Array.isArray(r.risks) ? r.risks : [];
    $("#rc-report-risks").textContent = risks.length ? risks.join("；") : "--";

    const plan = Array.isArray(r.plan) ? r.plan : [];
    $("#rc-report-plan").textContent = plan.length ? plan.join("；") : "--";
  }

  function renderSourcesFromAssistant(sources) {
    // Render assistant citations into the "引用" pane.
    const el = $("#rc-sources");
    if (!el) return;
    el.innerHTML = "";

    if (!sources || !sources.length) {
      el.innerHTML = `<div class="rc-empty"><div class="fw-semibold">暂无引用</div><div class="small text-muted mt-1">可在“消息面”窗口刷新新闻，或导入本地资料到知识库。</div></div>`;
      return;
    }

    for (const s of sources.slice(0, 18)) {
      const div = document.createElement("div");
      div.className = "rc-source";

      const t = s.type === "news" ? "NEWS" : "KB";
      const title = (s.title || s.snippet || "").slice(0, 80);
      const meta =
        s.type === "news"
          ? [s.published_at, s.source_site].filter(Boolean).join(" · ")
          : [s.created_at].filter(Boolean).join(" · ");

      div.innerHTML = `
        <div class="t">${esc(`[${t}] ` + (title || "引用"))}</div>
        <div class="m">${esc(meta)}</div>
      `;
      el.appendChild(div);
    }
  }

  async function send() {
    const ta = $("#rc-input");
    if (!ta) return;
    const text = (ta.value || "").trim();
    if (!text) return;
    ta.value = "";

    const u = esc(text).replaceAll("\n", "<br>");
    state.messages.push({ role: "user", text });
    appendMessage("user", u);
    renderMsgCount();

    const placeholderId = `rc-wait-${Date.now()}`;
    appendMessage(
      "assistant",
      `<div id="${placeholderId}" class="small text-muted">正在生成…</div>`
    );

    try {
      const style = $("#rc-style")?.value || "balanced";
      const cite = $("#rc-cite")?.value || "news";
      const res = await apiV1("POST", "/assistant/chat", {
        mode: state.mode,
        prompt: text,
        target: state.target || "",
        style,
        cite,
        save_note: state.mode === "research",
      });

      const data = res && res.ok === true ? res.data : res;
      const report = (data && data.report) || {};
      const conclusion = esc(report.conclusion || "完成");

      const node = document.getElementById(placeholderId);
      if (node) {
        node.innerHTML = `<div class="fw-semibold">${conclusion}</div>`;
      }

      state.messages.push({ role: "assistant", text: report.conclusion || "" });
      renderMsgCount();

      if (state.mode === "research") {
        fillReport(report);
        setTab("report");
      }

      renderSourcesFromAssistant((data && data.sources) || []);
    } catch (e) {
      const node = document.getElementById(placeholderId);
      if (node) node.textContent = `生成失败：${e.message || e}`;
    }
  }

  function clearAll() {
    state.messages = [];
    const chat = $("#rc-chat");
    if (chat) {
      chat.innerHTML = `
        <div class="rc-msg rc-msg-assistant">
          <div class="rc-bubble">
            <div class="fw-semibold">UI 预览</div>
            <div class="small text-muted mt-1">已清空对话。研究助理 + 智能问答共用同一对话入口。</div>
          </div>
        </div>
      `;
    }
    renderMsgCount();
    $("#rc-report")?.classList.add("d-none");
    $("#rc-report-empty")?.classList.remove("d-none");
  }

  function setup() {
    $("#rc-mode-qa")?.addEventListener("click", () => setMode("qa"));
    $("#rc-mode-research")?.addEventListener("click", () => setMode("research"));

    $$(".rc-tab").forEach((t) => t.addEventListener("click", () => setTab(t.dataset.tab)));

    $("#rc-btn-use-target")?.addEventListener("click", () => setTarget($("#rc-target")?.value || ""));
    $("#rc-target")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        setTarget($("#rc-target")?.value || "");
      }
    });

    $("#rc-send")?.addEventListener("click", send);
    $("#rc-input")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });

    $$(".rc-prompt").forEach((b) =>
      b.addEventListener("click", () => {
        const p = b.dataset.prompt || "";
        const ta = $("#rc-input");
        if (!ta) return;
        ta.value = p;
        ta.focus();
      })
    );

    $("#rc-btn-report")?.addEventListener("click", () => {
      // Trigger a structured "research" output (uses the same assistant backend).
      const ta = $("#rc-input");
      if (ta) ta.value = "生成研究报告（结论/依据/风险/计划）";
      setMode("research");
      send();
    });

    $("#rc-btn-clear")?.addEventListener("click", clearAll);

    $("#rc-refresh-sources")?.addEventListener("click", loadSources);

    setMode("qa");
    setTab("report");
    setTarget("");
    renderMsgCount();
    loadSources();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
})();
