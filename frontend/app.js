/* AgentSearch — ChatGPT-style frontend logic */
const $ = (id) => document.getElementById(id);
const AGENTS = [
  { id: "planner", name: "Planner" },
  { id: "search", name: "Search" },
  { id: "reader", name: "Reader" },
  { id: "ranker", name: "Ranker" },
  { id: "synthesizer", name: "Writer" },
  { id: "critic", name: "Critic" },
];

let es = null;
let abortController = null;
let streaming = false;
let activeAssistant = null;

/* ---------------- Init ---------------- */
window.addEventListener("DOMContentLoaded", () => {
  initTheme();
  loadHealth();
  loadHistory();
  bindEvents();
  autoGrow();
});

function bindEvents() {
  $("composer").addEventListener("submit", (e) => { e.preventDefault(); submitQuery(); });
  $("queryInput").addEventListener("input", () => { autoGrow(); updateSendState(); });
  $("queryInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitQuery(); }
  });
  $("newChatBtn").addEventListener("click", newChat);
  $("stopBtn").addEventListener("click", stopSearch);
  $("clearHistory").addEventListener("click", clearHistory);
  $("themeToggle").addEventListener("click", toggleTheme);
  $("menuBtn").addEventListener("click", () => setSidebar(true));
  $("sidebarOverlay").addEventListener("click", () => setSidebar(false));
  document.querySelectorAll(".suggestion").forEach((btn) =>
    btn.addEventListener("click", () => startSearch(btn.dataset.q)));
}

function setSidebar(open) {
  $("sidebar").classList.toggle("open", open);
  $("sidebarOverlay").classList.toggle("show", open);
}

function autoGrow() {
  const ta = $("queryInput");
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
}
function updateSendState() {
  $("sendBtn").disabled = streaming || $("queryInput").value.trim().length < 2;
}

/* ---------------- Theme ---------------- */
function initTheme() {
  const saved = localStorage.getItem("agentsearch-theme");
  if (saved) document.documentElement.dataset.theme = saved;
}
function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("agentsearch-theme", next);
}

/* ---------------- Health / history ---------------- */
async function loadHealth() {
  try {
    const h = await (await fetch("/api/health")).json();
    $("modeBadge").textContent = h.tavily_enabled ? "Tavily + free fallback" : "Free mode · no API key";
  } catch { /* ignore */ }
}

async function loadHistory() {
  try {
    const { runs } = await (await fetch("/api/history?limit=30")).json();
    const box = $("historyList");
    if (!runs || !runs.length) {
      box.innerHTML = '<div class="history-empty">No searches yet.</div>';
      return;
    }
    box.innerHTML = "";
    runs.forEach((run) => {
      const btn = document.createElement("button");
      btn.className = "history-item";
      btn.title = run.query;
      btn.innerHTML = `${escapeHtml(run.query)}<span class="h-meta">${new Date(run.created_at * 1000).toLocaleString()} · ${Math.round((run.confidence || 0) * 100)}%</span>`;
      btn.addEventListener("click", () => { openHistory(run.id); setSidebar(false); });
      box.appendChild(btn);
    });
  } catch { /* ignore */ }
}

async function openHistory(id) {
  try {
    const r = await fetch(`/api/history/${id}`);
    if (!r.ok) return;
    const run = await r.json();
    stopSearch();
    clearMessages();
    appendUser(run.query);
    const a = createAssistantMessage();
    AGENTS.forEach((ag) => setStep(a, ag.id, "done"));
    setPanelSummary(a, `Loaded from history · ${run.result.stats?.elapsed_seconds ?? "—"}s`);
    collapsePanel(a, true);
    (run.events || []).forEach((e) => { if (e.message && e.type !== "result") addLog(a, e.agent, e.message, e.type); });
    renderResult(a, run.result);
    scrollBottom();
  } catch { /* ignore */ }
}

async function clearHistory() {
  await fetch("/api/history", { method: "DELETE" });
  loadHistory();
}

/* ---------------- Chat lifecycle ---------------- */
function newChat() {
  stopSearch();
  clearMessages();
  $("welcome").classList.remove("hidden");
  $("queryInput").value = "";
  autoGrow();
  updateSendState();
  setSidebar(false);
}
function clearMessages() {
  $("messages").innerHTML = "";
  activeAssistant = null;
}
function submitQuery() {
  const q = $("queryInput").value.trim();
  if (q.length < 2 || streaming) return;
  $("queryInput").value = "";
  autoGrow();
  startSearch(q);
}

function startSearch(query) {
  if (streaming) stopSearch();
  $("welcome").classList.add("hidden");
  appendUser(query);
  const assistant = createAssistantMessage();
  activeAssistant = assistant;
  streaming = true;
  updateSendState();
  $("stopBtn").classList.remove("hidden");
  setPanelSummary(assistant, "Starting agents…");
  scrollBottom();

  const depth = $("depthSelect").value;
  const url = `/api/search?q=${encodeURIComponent(query)}&depth=${depth}`;
  let received = false;

  es = new EventSource(url);
  es.onmessage = (ev) => {
    let data;
    try { data = JSON.parse(ev.data); } catch { return; }
    received = true;
    handleEvent(assistant, data);
  };
  es.onerror = () => {
    closeStream();
    if (assistant.dataset.done) { finishStream(); return; }
    // Some serverless hosts buffer or block SSE. If nothing ever arrived,
    // retry the same query through the plain JSON endpoint.
    if (!received) {
      setPanelSummary(assistant, "Streaming unavailable — using direct request…");
      runJsonFallback(assistant, query, depth);
      return;
    }
    setPanelSummary(assistant, "Connection interrupted");
    showError(assistant, "The connection was interrupted. Please try again.");
    finishStream();
  };
}

/* Fallback for hosts that cannot stream SSE (e.g. buffered serverless). */
async function runJsonFallback(assistant, query, depth) {
  abortController = new AbortController();
  AGENTS.forEach((ag) => setStep(assistant, ag.id, "running"));
  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, depth }),
      signal: abortController.signal,
    });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const result = await res.json();
    AGENTS.forEach((ag) => setStep(assistant, ag.id, "done"));
    handleEvent(assistant, { type: "result", data: result });
  } catch (err) {
    if (err.name === "AbortError") {
      setPanelSummary(assistant, "Stopped");
    } else {
      AGENTS.forEach((ag) => setStep(assistant, ag.id, "error"));
      setPanelSummary(assistant, "Request failed");
      showError(assistant, `Could not complete the search: ${err.message}`);
    }
  } finally {
    abortController = null;
    finishStream();
  }
}

function stopSearch() {
  if (es) { es.close(); es = null; }
  if (abortController) { abortController.abort(); abortController = null; }
  if (streaming && activeAssistant && !activeAssistant.dataset.done) {
    setPanelSummary(activeAssistant, "Stopped");
  }
  finishStream();
}
function closeStream() { if (es) { es.close(); es = null; } }
function finishStream() {
  streaming = false;
  $("stopBtn").classList.add("hidden");
  updateSendState();
  loadHistory();
}

function handleEvent(a, e) {
  const { type, agent, message, data } = e;
  if (type === "agent_start") { setStep(a, agent, "running"); setPanelSummary(a, `${agentName(agent)} is working…`); }
  else if (type === "agent_done") { setStep(a, agent, "done"); }
  else if (type === "agent_error") { setStep(a, agent, "error"); }
  else if (type === "retry") {
    AGENTS.forEach((ag) => setStep(a, ag.id, "pending"));
    setPanelSummary(a, "Running another round based on Critic feedback…");
  }
  else if (type === "result") {
    a.dataset.done = "1";
    renderResult(a, data);
    const st = data.stats || {};
    setPanelSummary(a, `Completed in ${st.elapsed_seconds ?? "—"}s · ${st.sources ?? 0} sources · ${st.rounds ?? 1} round(s)`);
    collapsePanel(a, true);
  }
  else if (type === "done") { closeStream(); finishStream(); }
  else if (type === "error") { showError(a, message || "Pipeline error"); }
  if (message && type !== "result") addLog(a, agent, message, type);
  scrollBottom();
}

/* ---------------- DOM builders ---------------- */
function appendUser(text) {
  const div = document.createElement("div");
  div.className = "message user";
  div.innerHTML = `<div class="user-bubble"></div>`;
  div.querySelector(".user-bubble").textContent = text;
  $("messages").appendChild(div);
  scrollBottom();
}

function createAssistantMessage() {
  const wrap = document.createElement("div");
  wrap.className = "message assistant";
  wrap.innerHTML = `
    <div class="avatar">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
    </div>
    <div class="assistant-content">
      <div class="agent-panel">
        <button type="button" class="agent-panel-toggle">
          <span class="agent-panel-title">Agent activity</span>
          <span class="agent-panel-summary">Waiting…</span>
          <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>
        </button>
        <div class="agent-panel-body">
          <div class="agent-steps"></div>
          <div class="agent-log"></div>
        </div>
      </div>
      <div class="answer-slot">
        <div class="typing"><span class="t-dot"></span><span class="t-dot"></span><span class="t-dot"></span><span>Researching…</span></div>
      </div>
    </div>`;
  const steps = wrap.querySelector(".agent-steps");
  AGENTS.forEach((ag) => {
    const s = document.createElement("div");
    s.className = "step";
    s.dataset.agent = ag.id;
    s.innerHTML = `<span class="dot"></span><span>${ag.name}</span>`;
    steps.appendChild(s);
  });
  wrap.querySelector(".agent-panel-toggle").addEventListener("click", () => {
    wrap.querySelector(".agent-panel").classList.toggle("collapsed");
  });
  $("messages").appendChild(wrap);
  return wrap;
}

function agentName(id) { return (AGENTS.find((a) => a.id === id) || {}).name || id; }
function setStep(a, id, state) {
  const el = a.querySelector(`.step[data-agent="${id}"]`);
  if (el) el.className = `step ${state}`;
}
function setPanelSummary(a, text) {
  const el = a.querySelector(".agent-panel-summary");
  if (el) el.textContent = text;
}
function collapsePanel(a, collapsed) {
  a.querySelector(".agent-panel").classList.toggle("collapsed", collapsed);
}
function addLog(a, agent, msg, type) {
  const log = a.querySelector(".agent-log");
  if (!log) return;
  const line = document.createElement("div");
  line.className = `log-line ${type === "agent_error" || type === "error" ? "err" : ""}`;
  line.innerHTML = `<span class="log-agent">${escapeHtml(agent || "system")}</span><span class="log-msg">${escapeHtml(msg)}</span>`;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}
function showError(a, msg) {
  const slot = a.querySelector(".answer-slot");
  slot.innerHTML = `<div class="error-box"></div>`;
  slot.querySelector(".error-box").textContent = msg;
}

/* ---------------- Result rendering ---------------- */
function renderResult(a, r) {
  const slot = a.querySelector(".answer-slot");
  slot.innerHTML = "";

  const answer = document.createElement("div");
  answer.className = "answer";
  answer.innerHTML = renderMarkdown(r.answer.markdown);
  slot.appendChild(answer);

  const meta = document.createElement("div");
  meta.className = "answer-meta";
  const conf = r.answer.confidence || 0;
  const confClass = conf >= 0.7 ? "conf-high" : conf >= 0.45 ? "conf-med" : "conf-low";
  meta.innerHTML = `
    <span class="conf-badge ${confClass}">Confidence ${Math.round(conf * 100)}%</span>
    <span>${r.stats?.elapsed_seconds ?? "—"}s</span>
    <span>${(r.sources || []).length} sources</span>
    <button type="button" class="copy-btn">Copy</button>`;
  meta.querySelector(".copy-btn").addEventListener("click", () => {
    navigator.clipboard.writeText(r.answer.markdown).then(() => {
      const b = meta.querySelector(".copy-btn");
      b.textContent = "Copied";
      setTimeout(() => (b.textContent = "Copy"), 1400);
    });
  });
  slot.appendChild(meta);

  if (r.sources && r.sources.length) {
    const cited = new Set(r.answer.cited_source_ids || []);
    const details = document.createElement("details");
    details.className = "sources";
    details.open = true;
    details.innerHTML = `<summary>Sources (${r.sources.length})</summary><div class="sources-list"></div>`;
    const list = details.querySelector(".sources-list");
    r.sources.forEach((s) => {
      const item = document.createElement("div");
      item.className = `source-item ${cited.has(s.id) ? "cited" : ""}`;
      item.dataset.sourceId = s.id;
      item.innerHTML = `
        <div class="source-head"><span class="source-num">[${s.id}]</span><span class="source-title"><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.title)}</a></span></div>
        <div class="source-domain">${escapeHtml(s.domain)} · ${escapeHtml(s.provider || "web")}${cited.has(s.id) ? " · cited" : ""}</div>
        <div class="source-snippet">${escapeHtml(s.snippet || "")}</div>`;
      list.appendChild(item);
    });
    slot.appendChild(details);
  }

  if (r.answer.warnings && r.answer.warnings.length) {
    const notes = document.createElement("details");
    notes.className = "notes";
    notes.innerHTML = `<summary>Notes</summary><ul>${r.answer.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>`;
    slot.appendChild(notes);
  }

  if (r.answer.follow_ups && r.answer.follow_ups.length) {
    const fu = document.createElement("div");
    fu.className = "followups";
    r.answer.follow_ups.forEach((q) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "followup-chip";
      chip.textContent = q;
      chip.addEventListener("click", () => startSearch(q));
      fu.appendChild(chip);
    });
    slot.appendChild(fu);
  }

  answer.querySelectorAll(".citation").forEach((c) => {
    c.addEventListener("click", (ev) => {
      ev.preventDefault();
      const target = slot.querySelector(`.source-item[data-source-id="${c.dataset.id}"]`);
      if (target) {
        const details = target.closest("details");
        if (details) details.open = true;
        target.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  });
}

/* ---------------- Markdown (safe, minimal) ---------------- */
function renderMarkdown(md) {
  const lines = (md || "").split("\n");
  let html = "", listType = null;
  const closeList = () => { if (listType) { html += `</${listType}>`; listType = null; } };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { closeList(); continue; }
    if (/^[-*]\s+/.test(line)) {
      if (listType !== "ul") { closeList(); html += "<ul>"; listType = "ul"; }
      html += `<li>${inline(escapeHtml(line.replace(/^[-*]\s+/, "")))}</li>`;
    } else if (/^\d+[.)]\s+/.test(line)) {
      if (listType !== "ol") { closeList(); html += "<ol>"; listType = "ol"; }
      html += `<li>${inline(escapeHtml(line.replace(/^\d+[.)]\s+/, "")))}</li>`;
    } else {
      closeList();
      html += `<p>${inline(escapeHtml(line))}</p>`;
    }
  }
  closeList();
  return html;
}
function inline(s) {
  return s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[(\d+)\]/g, '<a class="citation" href="#" data-id="$1">$1</a>');
}
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function scrollBottom() {
  const el = $("chatScroll");
  el.scrollTop = el.scrollHeight;
}
