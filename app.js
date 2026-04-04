const DEFAULT_PROMPT = "We're behind on collections. Build today's collections queue and fix the follow-ups.";
const RECENT_SHEETS_KEY = "prs_ops_recent_sheets_v1";
const PROMPT_PROFILE_KEY = "prs_ops_prompt_profile_v1";
const THEME_KEY = "prs_ops_theme_v1";
const WATCH_POLL_MS = 20000;
const DEFAULT_PROMPT_PROFILE = {
  businessContext: "",
  businessLogic: "",
  operatingStyle: "",
};

const TIMELINE_STEPS = [
  "Read sheet",
  "Map columns",
  "Propose changes",
  "Review",
  "Apply",
  "Queue + report",
];

const state = {
  spreadsheetId: "",
  spreadsheetUrl: "",
  sheetName: "Receivables Raw",
  prompt: DEFAULT_PROMPT,
  promptProfile: { ...DEFAULT_PROMPT_PROFILE },
  effectivePrompt: DEFAULT_PROMPT,
  watchEnabled: false,
  watchIntervalId: null,
  watchBusy: false,
  pendingDecision: null,
  mapping: {},
  patches: [],
  selectedPatchIds: new Set(),
  proposalId: "",
  proposalArtifact: "",
  applyArtifact: "",
  appliedPatches: [],
  rowPlans: [],
  queuePreview: [],
  reportPreview: [],
  stage: 0,
  recentSheets: [],
  activitySteps: [],
  reviewIntelligence: { summary: "", risky_items: [] },
  aiEnabled: false,
  aiModel: "",
  mappingMeta: {},
  kpis: { total_outstanding: 0, at_risk: 0, projected_recovery: 0 },
  healthMeter: { score: 0, status: "red", label: "No data" },
  agingBuckets: [],
  anomalies: [],
  actionAlert: { critical_patches_ready: 0, message: "No new critical patches." },
};

const els = {
  spreadsheetIdInput: document.getElementById("spreadsheetIdInput"),
  sheetNameInput: document.getElementById("sheetNameInput"),
  promptInput: document.getElementById("promptInput"),
  businessContextInput: document.getElementById("businessContextInput"),
  businessLogicInput: document.getElementById("businessLogicInput"),
  operatingStyleInput: document.getElementById("operatingStyleInput"),
  taskPromptTabBtn: document.getElementById("taskPromptTabBtn"),
  businessPromptTabBtn: document.getElementById("businessPromptTabBtn"),
  taskPromptView: document.getElementById("taskPromptView"),
  businessPromptView: document.getElementById("businessPromptView"),
  watchToggleButton: document.getElementById("watchToggleButton"),
  watchState: document.getElementById("watchState"),
  decisionCard: document.getElementById("decisionCard"),
  decisionReason: document.getElementById("decisionReason"),
  decisionQuestion: document.getElementById("decisionQuestion"),
  decisionDetails: document.getElementById("decisionDetails"),
  decisionActions: document.getElementById("decisionActions"),
  mainNav: document.getElementById("mainNav"),
  themeToggle: document.getElementById("themeToggle"),
  patchDrawerOverlay: document.getElementById("patchDrawerOverlay"),
  patchDrawer: document.getElementById("patchDrawer"),
  openPatchDrawer: document.getElementById("openPatchDrawer"),
  closePatchDrawer: document.getElementById("closePatchDrawer"),
  toast: document.getElementById("toast"),
  toastMessage: document.getElementById("toastMessage"),
  recentSheetSelect: document.getElementById("recentSheetSelect"),
  recentSheetIds: document.getElementById("recentSheetIds"),
  createDemoButton: document.getElementById("createDemoButton"),
  proposeButton: document.getElementById("proposeButton"),
  bulkApproveButton: document.getElementById("bulkApproveButton"),
  applyButton: document.getElementById("applyButton"),
  resetButton: document.getElementById("resetButton"),
  timeline: document.getElementById("timeline"),
  timelineBadge: document.getElementById("timelineBadge"),
  mappingChips: document.getElementById("mappingChips"),
  mappingCount: document.getElementById("mappingCount"),
  proposedMetric: document.getElementById("proposedMetric"),
  approvedMetric: document.getElementById("approvedMetric"),
  recoverableMetric: document.getElementById("recoverableMetric"),
  artifactChip: document.getElementById("artifactChip"),
  activityChip: document.getElementById("activityChip"),
  activityLog: document.getElementById("activityLog"),
  aiChip: document.getElementById("aiChip"),
  reviewSummary: document.getElementById("reviewSummary"),
  riskList: document.getElementById("riskList"),
  statusMessage: document.getElementById("statusMessage"),
  proposedBody: document.getElementById("proposedBody"),
  selectAllPatches: document.getElementById("selectAllPatches"),
  queueHead: document.getElementById("queueHead"),
  queueBody: document.getElementById("queueBody"),
  reportHead: document.getElementById("reportHead"),
  reportBody: document.getElementById("reportBody"),
  proposedTabBtn: document.getElementById("proposedTabBtn"),
  queueTabBtn: document.getElementById("queueTabBtn"),
  reportTabBtn: document.getElementById("reportTabBtn"),
  proposedView: document.getElementById("proposedView"),
  queueView: document.getElementById("queueView"),
  reportView: document.getElementById("reportView"),
  sheetLink: document.getElementById("sheetLink"),
  kpiOutstanding: document.getElementById("kpiOutstanding"),
  kpiAtRisk: document.getElementById("kpiAtRisk"),
  kpiRecovery: document.getElementById("kpiRecovery"),
  healthFill: document.getElementById("healthFill"),
  healthLabel: document.getElementById("healthLabel"),
  agingBuckets: document.getElementById("agingBuckets"),
  actionAlert: document.getElementById("actionAlert"),
  anomalyList: document.getElementById("anomalyList"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatCurrency(value) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);
}

function extractSpreadsheetId(rawInput) {
  const value = String(rawInput || "").trim();
  if (!value) {
    return "";
  }

  const urlMatch = value.match(/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  if (urlMatch?.[1]) {
    return urlMatch[1];
  }

  const idMatch = value.match(/^[a-zA-Z0-9-_]{20,}$/);
  if (idMatch?.[0]) {
    return idMatch[0];
  }

  return value;
}

function sanitizePromptProfile(profile) {
  return {
    businessContext: String(profile?.businessContext || "").trim(),
    businessLogic: String(profile?.businessLogic || "").trim(),
    operatingStyle: String(profile?.operatingStyle || "").trim(),
  };
}

function buildEffectivePrompt(basePrompt, promptProfile) {
  const profile = sanitizePromptProfile(promptProfile);
  const sections = [String(basePrompt || "").trim() || DEFAULT_PROMPT];

  if (profile.businessContext) {
    sections.push(`Business context:\n${profile.businessContext}`);
  }
  if (profile.businessLogic) {
    sections.push(`Business logic and SOP:\n${profile.businessLogic}`);
  }
  if (profile.operatingStyle) {
    sections.push(`Employee operating style:\n${profile.operatingStyle}`);
  }

  return sections.join("\n\n");
}

function loadPromptProfile() {
  try {
    const raw = window.localStorage.getItem(PROMPT_PROFILE_KEY);
    if (!raw) {
      return { ...DEFAULT_PROMPT_PROFILE };
    }
    return sanitizePromptProfile(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_PROMPT_PROFILE };
  }
}

function savePromptProfile(profile) {
  window.localStorage.setItem(PROMPT_PROFILE_KEY, JSON.stringify(sanitizePromptProfile(profile)));
}

function showToast(message) {
  if (!els.toast || !els.toastMessage) {
    return;
  }
  els.toastMessage.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(showToast._timeoutId);
  showToast._timeoutId = window.setTimeout(() => {
    els.toast.classList.remove("show");
  }, 2400);
}

function setDrawerOpen(isOpen) {
  if (!els.patchDrawerOverlay) {
    return;
  }
  els.patchDrawerOverlay.classList.toggle("open", isOpen);
  document.body.style.overflow = isOpen ? "hidden" : "";
}

function openPatchDrawer() {
  setDrawerOpen(true);
}

function closePatchDrawer() {
  setDrawerOpen(false);
}

function applyInitialTheme() {
  const stored = String(window.localStorage.getItem(THEME_KEY) || "").trim();
  const initial =
    stored || (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  if (initial === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  const next = current === "dark" ? "light" : "dark";
  if (next === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  window.localStorage.setItem(THEME_KEY, next);
  showToast(next === "dark" ? "Dark mode enabled" : "Light mode enabled");
}

function initDashboardChrome() {
  applyInitialTheme();

  if (els.themeToggle) {
    els.themeToggle.addEventListener("click", toggleTheme);
  }

  if (els.openPatchDrawer) {
    els.openPatchDrawer.addEventListener("click", openPatchDrawer);
  }
  if (els.closePatchDrawer) {
    els.closePatchDrawer.addEventListener("click", closePatchDrawer);
  }
  if (els.patchDrawerOverlay) {
    els.patchDrawerOverlay.addEventListener("click", (event) => {
      if (event.target === els.patchDrawerOverlay) {
        closePatchDrawer();
      }
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closePatchDrawer();
    }
  });

  if (els.mainNav) {
    const onScroll = () => {
      els.mainNav.classList.toggle("scrolled", window.scrollY > 20);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }
}

function setWatchUi(message = "Watch mode is off.") {
  els.watchState.textContent = message;
  els.watchToggleButton.textContent = state.watchEnabled ? "Stop Watch" : "Start Watch";
  els.watchToggleButton.classList.toggle("active-watch", state.watchEnabled);
}

function hideDecisionCard() {
  state.pendingDecision = null;
  els.decisionCard.classList.add("hidden");
  els.decisionReason.textContent = "Pending";
  els.decisionQuestion.textContent = "No decision needed.";
  els.decisionDetails.innerHTML = "";
  els.decisionActions.innerHTML = "";
}

async function handleDecisionOption(option) {
  if (!option || typeof option !== "object") {
    return;
  }

  const action = String(option.action || "");
  if (action === "proceed") {
    hideDecisionCard();
    await proposeChanges(true);
    return;
  }

  if (action === "apply_prompt_hint_and_proceed") {
    const hint = String(option.prompt_hint || "").trim();
    if (hint) {
      const current = els.promptInput.value.trim();
      if (!current.includes(hint)) {
        els.promptInput.value = current ? `${current}\n\n${hint}` : hint;
        els.promptInput.dispatchEvent(new Event("input"));
      }
    }
    activatePromptTab("task");
    hideDecisionCard();
    await proposeChanges(true);
    return;
  }

  hideDecisionCard();
  updateStatus("Refine prompt/header mapping, then click Propose Changes.", "ready");
}

function showDecisionCard(decision) {
  state.pendingDecision = decision || null;
  const reason = String(decision?.reason || "needs_decision").replaceAll("_", " ");
  const question = String(decision?.question || "Need one decision before proposing.");
  const details = Array.isArray(decision?.details) ? decision.details : [];
  const options = Array.isArray(decision?.options) ? decision.options : [];

  els.decisionReason.textContent = reason;
  els.decisionQuestion.textContent = question;
  els.decisionDetails.innerHTML = details.length
    ? details.map((item) => `<li>${escapeHtml(String(item || ""))}</li>`).join("")
    : "<li>Review and choose an option to continue.</li>";
  els.decisionActions.innerHTML = "";

  const normalizedOptions = options.length
    ? options
    : [
        { label: "Proceed", action: "proceed", recommended: true },
        { label: "Pause", action: "pause", recommended: false },
      ];

  normalizedOptions.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = option.recommended ? "primary-button" : "secondary-button";
    button.textContent = option.label || option.id || "Continue";
    button.addEventListener("click", () => {
      void handleDecisionOption(option);
    });
    els.decisionActions.appendChild(button);
  });

  els.decisionCard.classList.remove("hidden");
}

function stopWatchMode() {
  if (state.watchIntervalId) {
    window.clearInterval(state.watchIntervalId);
  }
  state.watchIntervalId = null;
  state.watchEnabled = false;
  state.watchBusy = false;
  setWatchUi("Watch mode is off.");
}

async function runWatchCycle() {
  if (!state.watchEnabled || state.watchBusy) {
    return;
  }

  syncInputsToState();
  if (!state.spreadsheetId) {
    stopWatchMode();
    updateStatus("Spreadsheet ID is required for watch mode.", "idle");
    return;
  }

  state.watchBusy = true;
  try {
    const data = await postJson("/api/watch", {
      spreadsheet_id: state.spreadsheetId,
      sheet_name: state.sheetName,
      prompt: state.prompt,
      prompt_profile: state.promptProfile,
      auto_propose: true,
    });

    const checkedAt = new Date().toLocaleTimeString();
    if (data.changed && data.proposal) {
      hideDecisionCard();
      setProposedData(data.proposal);
      updateStatus(`Watch detected changes: ${data.change_reason}`, "ready");
      setWatchUi(`Watching (${checkedAt}) - detected changes and generated a fresh patch set.`);
    } else {
      setWatchUi(`Watching (${checkedAt}) - ${data.change_reason || "No new rows or tab changes."}`);
    }
  } catch (error) {
    setWatchUi(`Watch error: ${error.message}`);
  } finally {
    state.watchBusy = false;
  }
}

function startWatchMode() {
  syncInputsToState();
  if (!state.spreadsheetId) {
    throw new Error("Spreadsheet ID is required to start watch mode.");
  }
  if (state.watchEnabled) {
    return;
  }
  state.watchEnabled = true;
  setWatchUi("Watch mode started.");
  void runWatchCycle();
  state.watchIntervalId = window.setInterval(() => {
    void runWatchCycle();
  }, WATCH_POLL_MS);
}

function loadRecentSheets() {
  try {
    const raw = window.localStorage.getItem(RECENT_SHEETS_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item) => item && item.id).slice(0, 8);
  } catch {
    return [];
  }
}

function saveRecentSheets() {
  window.localStorage.setItem(RECENT_SHEETS_KEY, JSON.stringify(state.recentSheets.slice(0, 8)));
}

function updateRecentSheets(id, url = "") {
  if (!id) {
    return;
  }
  const existing = state.recentSheets.filter((item) => item.id !== id);
  state.recentSheets = [{ id, url }, ...existing].slice(0, 8);
  saveRecentSheets();
  renderRecentSheets();
}

function renderRecentSheets() {
  els.recentSheetIds.innerHTML = state.recentSheets
    .map((item) => `<option value="${escapeHtml(item.id)}"></option>`)
    .join("");

  els.recentSheetSelect.innerHTML = [
    '<option value="">Select a recent sheet</option>',
    ...state.recentSheets.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.id)}</option>`),
  ].join("");
}

function renderActivity() {
  if (!state.activitySteps.length) {
    els.activityChip.textContent = "Waiting";
    els.activityLog.innerHTML = "<li>Press Propose Changes to see what the agent is doing.</li>";
    return;
  }

  els.activityChip.textContent = `${state.activitySteps.length} steps`;
  els.activityLog.innerHTML = state.activitySteps
    .map((step) => `<li>${escapeHtml(step)}</li>`)
    .join("");
}

function renderReviewIntelligence() {
  const summary = state.reviewIntelligence?.summary || "No review intelligence yet.";
  els.reviewSummary.textContent = summary;

  const risky = state.reviewIntelligence?.risky_items || [];
  els.aiChip.textContent = risky.length ? `${risky.length} highlights` : "No highlights";
  if (!risky.length) {
    els.riskList.innerHTML = "<li>No high-risk highlights.</li>";
    return;
  }
  els.riskList.innerHTML = risky
    .map((item) => {
      const patchId = item.patch_id && item.patch_id !== "general" ? `${item.patch_id}: ` : "";
      return `<li><strong>${escapeHtml(patchId + (item.risk || "Risk"))}</strong> ${escapeHtml(item.review_focus || item.tradeoff || "")}</li>`;
    })
    .join("");
}

function renderExecutiveDashboard() {
  els.kpiOutstanding.textContent = formatCurrency(state.kpis.total_outstanding || 0);
  els.kpiAtRisk.textContent = formatCurrency(state.kpis.at_risk || 0);
  els.kpiRecovery.textContent = formatCurrency(state.kpis.projected_recovery || 0);

  const score = Number(state.healthMeter.score || 0);
  const status = state.healthMeter.status || "red";
  const statusColor = status === "green" ? "#1f7a52" : status === "yellow" ? "#d9771f" : "#b9341d";
  els.healthFill.style.width = `${Math.max(0, Math.min(score, 100))}%`;
  els.healthFill.style.backgroundColor = statusColor;
  els.healthLabel.textContent = `${state.healthMeter.label || "No data"} (${score}/100)`;

  const buckets = Array.isArray(state.agingBuckets) ? state.agingBuckets : [];
  const maxAmount = Math.max(1, ...buckets.map((item) => Number(item.amount || 0)));
  els.agingBuckets.innerHTML = buckets
    .map((item) => {
      const amount = Number(item.amount || 0);
      const width = Math.round((amount / maxAmount) * 100);
      return `
        <div class="bucket-row">
          <span class="bucket-label">${escapeHtml(item.bucket)}</span>
          <div class="bucket-track"><div class="bucket-fill" style="width:${width}%"></div></div>
          <span class="bucket-value">${formatCurrency(amount)}</span>
        </div>
      `;
    })
    .join("") || "<div class=\"bucket-row\"><span class=\"bucket-label\">-</span><div class=\"bucket-track\"></div><span class=\"bucket-value\">₹0</span></div>";

  els.actionAlert.textContent = state.actionAlert?.message || "No new critical patches.";
  const anomalies = Array.isArray(state.anomalies) ? state.anomalies : [];
  els.anomalyList.innerHTML = anomalies.length
    ? anomalies.map((item) => `<li><strong>${escapeHtml((item.severity || "medium").toUpperCase())}:</strong> ${escapeHtml(item.title)} - ${escapeHtml(item.detail)}</li>`).join("")
    : "<li>No anomalies flagged.</li>";
}

function updateStatus(message, badge = "idle") {
  els.statusMessage.textContent = message;

  const badgeMap = {
    idle: ["Idle", "status-pill idle"],
    running: ["Running", "status-pill running"],
    ready: ["Ready", "status-pill complete"],
    applied: ["Applied", "status-pill applied"],
  };

  const [text, className] = badgeMap[badge] || badgeMap.idle;
  els.timelineBadge.textContent = text;
  els.timelineBadge.className = className;
}

function renderTimeline() {
  els.timeline.innerHTML = "";

  TIMELINE_STEPS.forEach((step, index) => {
    const li = document.createElement("li");
    const status = index < state.stage ? "Done" : index === state.stage ? "Current" : "Pending";
    li.innerHTML = `
      <span class="step-index">${index + 1}</span>
      <div class="step-copy">
        <strong>${escapeHtml(step)}</strong>
        <span>${status}</span>
      </div>
    `;
    els.timeline.appendChild(li);
  });
}

function renderMapping() {
  const entries = Object.entries(state.mapping || {});
  els.mappingCount.textContent = `${entries.length} mapped`;
  els.mappingChips.innerHTML = entries
    .map(([logical, header]) => `<span class="chip">${escapeHtml(logical)} -> ${escapeHtml(header)}</span>`)
    .join("");
}

function computeSelectedRecoverable() {
  if (!state.patches.length) {
    return 0;
  }

  const selected = state.patches.filter((patch) => state.selectedPatchIds.has(patch.patch_id));
  const groupedByRow = new Map();

  selected.forEach((patch) => {
    const current = groupedByRow.get(patch.sheet_row_number) || 0;
    groupedByRow.set(patch.sheet_row_number, Math.max(current, Number(patch.projected_impact) || 0));
  });

  return [...groupedByRow.values()].reduce((sum, value) => sum + value, 0);
}

function renderMetrics() {
  els.proposedMetric.textContent = String(state.patches.length);
  els.approvedMetric.textContent = String(state.selectedPatchIds.size);
  els.recoverableMetric.textContent = formatCurrency(computeSelectedRecoverable());

  if (state.applyArtifact) {
    els.artifactChip.textContent = `Apply artifact: ${state.applyArtifact.split("/").pop()}`;
  } else if (state.proposalArtifact) {
    els.artifactChip.textContent = `Proposal artifact: ${state.proposalArtifact.split("/").pop()}`;
  } else {
    els.artifactChip.textContent = "No artifact";
  }
}

function renderProposedPatches() {
  if (!state.patches.length) {
    els.proposedBody.innerHTML = `
      <tr>
        <td colspan="12">No proposed patches yet.</td>
      </tr>
    `;
    els.selectAllPatches.checked = false;
    els.applyButton.disabled = true;
    els.bulkApproveButton.disabled = true;
    return;
  }

  els.proposedBody.innerHTML = state.patches
    .map((patch) => {
      const checked = state.selectedPatchIds.has(patch.patch_id) ? "checked" : "";
      const afterValue =
        String(patch.field || "").toLowerCase() === "priority"
          ? `<span class="risk-badge ${(patch.risk_level || "medium").toLowerCase()}" title="${escapeHtml(patch.reason || "")}">${escapeHtml(patch.after || "-")}</span>`
          : escapeHtml(patch.after || "-");
      return `
        <tr>
          <td>
            <input type="checkbox" data-patch-id="${escapeHtml(patch.patch_id)}" ${checked} />
          </td>
          <td>${escapeHtml(patch.patch_id)}</td>
          <td>${escapeHtml(patch.sheet_row_number)}</td>
          <td>${escapeHtml(patch.customer)}</td>
          <td>${escapeHtml(patch.field)}</td>
          <td>${escapeHtml(patch.before || "-")}</td>
          <td>${afterValue}</td>
          <td class="patch-reason">${escapeHtml(patch.reason || "")}</td>
          <td>${escapeHtml(Number(patch.confidence).toFixed(2))}</td>
          <td>${formatCurrency(patch.projected_impact)}</td>
          <td><span class="risk-badge ${(patch.risk_level || "medium").toLowerCase()}" title="${escapeHtml(patch.review_note || "")}">${escapeHtml((patch.risk_level || "medium").toUpperCase())}</span></td>
          <td><span class="chip">${escapeHtml((patch.context_status || "new").replaceAll("_", " "))}</span></td>
        </tr>
      `;
    })
    .join("");

  const selectedCount = state.selectedPatchIds.size;
  const lowRiskCount = state.patches.filter((patch) => patch.is_data_cleanup && String(patch.risk_level || "").toLowerCase() === "low").length;
  els.selectAllPatches.checked = selectedCount > 0 && selectedCount === state.patches.length;
  els.applyButton.disabled = selectedCount === 0;
  els.bulkApproveButton.disabled = lowRiskCount === 0;
}

function renderTableFromPreview(headEl, bodyEl, preview) {
  if (!preview || preview.length === 0) {
    headEl.innerHTML = "";
    bodyEl.innerHTML = '<tr><td>No data</td></tr>';
    return;
  }

  const [headers, ...rows] = preview;
  headEl.innerHTML = `<tr>${headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("")}</tr>`;
  bodyEl.innerHTML = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`)
    .join("");
}

function activateTab(tabName) {
  const tabs = {
    proposed: [els.proposedTabBtn, els.proposedView],
    queue: [els.queueTabBtn, els.queueView],
    report: [els.reportTabBtn, els.reportView],
  };

  Object.entries(tabs).forEach(([name, [btn, view]]) => {
    btn.classList.toggle("active", name === tabName);
    view.classList.toggle("active", name === tabName);
  });
}

function activatePromptTab(tabName) {
  const tabs = {
    task: [els.taskPromptTabBtn, els.taskPromptView],
    business: [els.businessPromptTabBtn, els.businessPromptView],
  };

  Object.entries(tabs).forEach(([name, [btn, view]]) => {
    const active = name === tabName;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", String(active));
    view.classList.toggle("active", active);
  });
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const contentType = String(response.headers.get("content-type") || "");
  const raw = await response.text();
  let data = null;

  try {
    data = JSON.parse(raw);
  } catch {
    const looksLikeHtml = raw.trim().startsWith("<!DOCTYPE") || raw.trim().startsWith("<html");
    if (looksLikeHtml) {
      throw new Error(
        "API returned HTML instead of JSON. Restart with `python3 sheetops_gws_demo.py serve --host 127.0.0.1 --port 8000` and open that URL.",
      );
    }
    throw new Error(
      `API returned invalid JSON (${response.status}${contentType ? `, ${contentType}` : ""}).`,
    );
  }

  if (!data || typeof data !== "object") {
    throw new Error(`API returned unexpected response (${response.status}).`);
  }

  if (!response.ok || !data.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

function syncInputsToState() {
  const normalizedId = extractSpreadsheetId(els.spreadsheetIdInput.value);
  const promptProfile = sanitizePromptProfile({
    businessContext: els.businessContextInput.value,
    businessLogic: els.businessLogicInput.value,
    operatingStyle: els.operatingStyleInput.value,
  });
  state.spreadsheetId = normalizedId;
  state.sheetName = els.sheetNameInput.value.trim() || "Receivables Raw";
  state.prompt = els.promptInput.value.trim() || DEFAULT_PROMPT;
  state.promptProfile = promptProfile;
  state.effectivePrompt = buildEffectivePrompt(state.prompt, state.promptProfile);
  els.spreadsheetIdInput.value = normalizedId;
  savePromptProfile(promptProfile);
}

function setSheetLink(url) {
  if (!url) {
    els.sheetLink.classList.add("hidden");
    els.sheetLink.removeAttribute("href");
    return;
  }

  els.sheetLink.href = url;
  els.sheetLink.classList.remove("hidden");
}

async function createDemoSheet() {
  updateStatus("Creating sample Google Sheet...", "running");
  state.activitySteps = [
    "Creating a new spreadsheet in Google Sheets.",
    "Renaming default tab to Receivables Raw.",
    "Writing a diagnostic labs receivables export with realistic row volume.",
  ];
  renderActivity();

  const data = await postJson("/api/create-demo", {
    title: "PRs for Operations - Diagnostic Labs AR Demo",
  });

  state.spreadsheetId = data.spreadsheet_id;
  state.spreadsheetUrl = data.spreadsheet_url;
  state.sheetName = data.sheet_name || "Receivables Raw";
  state.stage = 1;

  els.spreadsheetIdInput.value = state.spreadsheetId;
  els.sheetNameInput.value = state.sheetName;
  setSheetLink(state.spreadsheetUrl);
  updateRecentSheets(state.spreadsheetId, state.spreadsheetUrl);

  renderTimeline();
  updateStatus("Diagnostic labs sample sheet created. Click Propose Changes.", "ready");
}

function setProposedData(data) {
  state.mapping = data.mapping || {};
  state.mappingMeta = data.mapping_meta || {};
  state.patches = data.patches || [];
  state.rowPlans = data.row_plans || [];
  state.reviewIntelligence = data.review_intelligence || { summary: "", risky_items: [] };
  state.aiEnabled = Boolean(data.ai_enabled);
  state.aiModel = data.ai_model || "";
  state.kpis = data.kpis || { total_outstanding: 0, at_risk: 0, projected_recovery: 0 };
  state.healthMeter = data.health_meter || { score: 0, status: "red", label: "No data" };
  state.agingBuckets = data.aging_buckets || [];
  state.anomalies = data.anomalies || [];
  state.actionAlert = data.action_alert || { critical_patches_ready: 0, message: "No new critical patches." };
  state.proposalArtifact = data.proposal_artifact || "";
  state.proposalId = data.proposal_id || "";
  state.applyArtifact = "";
  state.appliedPatches = [];
  state.queuePreview = [];
  state.reportPreview = [];
  state.activitySteps = data.execution_steps || [
    `Read ${state.sheetName} rows from Google Sheets.`,
    "Mapped messy headers to AR business concepts.",
    `Generated ${state.patches.length} reviewable patches.`,
    "Wrote Proposed Changes tab for approval.",
  ];

  state.selectedPatchIds = new Set(state.patches.map((patch) => patch.patch_id));
  state.spreadsheetUrl = data.spreadsheet_url || state.spreadsheetUrl;

  setSheetLink(state.spreadsheetUrl);
  updateRecentSheets(state.spreadsheetId, state.spreadsheetUrl);
  state.stage = 4;

  els.queueTabBtn.disabled = true;
  els.reportTabBtn.disabled = true;

  renderTimeline();
  renderMapping();
  renderActivity();
  renderReviewIntelligence();
  renderExecutiveDashboard();
  renderProposedPatches();
  renderMetrics();
  activateTab("proposed");

  if (!state.patches.length) {
    updateStatus("No changes required. Sheet already looks clean.", "ready");
    showToast("No patches needed.");
  } else {
    updateStatus(`Review ${state.patches.length} proposed patches, then apply approved changes.`, "ready");
    showToast(`${state.patches.length} patches ready for review.`);
    openPatchDrawer();
  }
}

async function proposeChanges(forceProceed = false) {
  syncInputsToState();
  if (!state.spreadsheetId) {
    throw new Error("Spreadsheet ID is required.");
  }

  if (!forceProceed) {
    updateStatus("Running preflight checks for ambiguity and prompt quality...", "running");
    const preflight = await postJson("/api/preflight", {
      spreadsheet_id: state.spreadsheetId,
      sheet_name: state.sheetName,
      prompt: state.prompt,
      prompt_profile: state.promptProfile,
    });
    if (preflight.needs_decision) {
      showDecisionCard(preflight.decision);
      updateStatus("Need one decision before proposing patch set.", "ready");
      return;
    }
    hideDecisionCard();
  }

  updateStatus("Reading sheet, mapping columns, and generating patch set...", "running");
  state.activitySteps = [
    `Reading tab: ${state.sheetName}.`,
    "Detecting business columns from messy headers.",
    "Scoring overdue accounts and building patch set.",
    "Writing Proposed Changes tab.",
  ];
  renderActivity();
  state.stage = 2;
  renderTimeline();

  const data = await postJson("/api/propose", {
    spreadsheet_id: state.spreadsheetId,
    sheet_name: state.sheetName,
    prompt: state.prompt,
    prompt_profile: state.promptProfile,
  });

  setProposedData(data);
}

function setAppliedData(data) {
  state.appliedPatches = data.applied_patches || [];
  state.applyArtifact = data.apply_artifact || "";
  state.queuePreview = data.collections_queue_preview || [];
  state.reportPreview = data.report_preview || [];
  state.spreadsheetUrl = data.spreadsheet_url || state.spreadsheetUrl;
  state.activitySteps = [
    `Applied ${state.appliedPatches.length} approved patches to ${state.sheetName}.`,
    "Updated operational fields in Receivables Raw.",
    "Generated Collections Queue tab.",
    "Generated Report tab with impact and rollback instructions.",
  ];
  state.stage = 6;

  setSheetLink(state.spreadsheetUrl);
  updateRecentSheets(state.spreadsheetId, state.spreadsheetUrl);

  els.queueTabBtn.disabled = false;
  els.reportTabBtn.disabled = false;

  renderTimeline();
  renderActivity();
  renderMetrics();
  renderTableFromPreview(els.queueHead, els.queueBody, state.queuePreview);
  renderTableFromPreview(els.reportHead, els.reportBody, state.reportPreview);
  activateTab("queue");

  updateStatus(
    `Applied ${state.appliedPatches.length} patches. Collections Queue and Report tabs are updated.`,
    "applied",
  );
  showToast("Approved patches applied.");
}

async function applyApprovedChanges() {
  if (!state.spreadsheetId || !state.proposalId) {
    throw new Error("Run Propose Changes before applying.");
  }

  const selectedPatchIds = [...state.selectedPatchIds];
  if (!selectedPatchIds.length) {
    throw new Error("Select at least one patch to apply.");
  }

  updateStatus("Applying approved patches and generating queue/report tabs...", "running");
  state.stage = 5;
  renderTimeline();

  const data = await postJson("/api/apply", {
    spreadsheet_id: state.spreadsheetId,
    sheet_name: state.sheetName,
    prompt: state.prompt,
    prompt_profile: state.promptProfile,
    proposal_id: state.proposalId,
    selected_patch_ids: selectedPatchIds,
    apply_all: false,
  });

  setAppliedData(data);
}

function bulkApproveLowRisk() {
  const lowRisk = state.patches.filter(
    (patch) => patch.is_data_cleanup && String(patch.risk_level || "").toLowerCase() === "low",
  );
  if (!lowRisk.length) {
    updateStatus("No low-risk cleanup patches available.", "ready");
    return;
  }
  state.selectedPatchIds = new Set(lowRisk.map((patch) => patch.patch_id));
  renderProposedPatches();
  renderMetrics();
  updateStatus(`Selected ${lowRisk.length} low-risk cleanup patches.`, "ready");
}

function resetDemoState() {
  stopWatchMode();
  hideDecisionCard();
  closePatchDrawer();
  if (els.toast) {
    els.toast.classList.remove("show");
  }
  const savedPromptProfile = loadPromptProfile();
  state.spreadsheetId = "";
  state.spreadsheetUrl = "";
  state.sheetName = "Receivables Raw";
  state.prompt = DEFAULT_PROMPT;
  state.promptProfile = savedPromptProfile;
  state.effectivePrompt = buildEffectivePrompt(state.prompt, state.promptProfile);
  state.mapping = {};
  state.patches = [];
  state.selectedPatchIds = new Set();
  state.proposalId = "";
  state.proposalArtifact = "";
  state.applyArtifact = "";
  state.appliedPatches = [];
  state.rowPlans = [];
  state.queuePreview = [];
  state.reportPreview = [];
  state.stage = 0;
  state.activitySteps = [];
  state.reviewIntelligence = { summary: "", risky_items: [] };
  state.aiEnabled = false;
  state.aiModel = "";
  state.mappingMeta = {};
  state.kpis = { total_outstanding: 0, at_risk: 0, projected_recovery: 0 };
  state.healthMeter = { score: 0, status: "red", label: "No data" };
  state.agingBuckets = [];
  state.anomalies = [];
  state.actionAlert = { critical_patches_ready: 0, message: "No new critical patches." };

  els.spreadsheetIdInput.value = "";
  els.sheetNameInput.value = state.sheetName;
  els.promptInput.value = state.prompt;
  els.businessContextInput.value = state.promptProfile.businessContext;
  els.businessLogicInput.value = state.promptProfile.businessLogic;
  els.operatingStyleInput.value = state.promptProfile.operatingStyle;
  els.selectAllPatches.checked = false;
  els.queueTabBtn.disabled = true;
  els.reportTabBtn.disabled = true;
  els.bulkApproveButton.disabled = true;

  setSheetLink("");
  renderTimeline();
  renderMapping();
  renderActivity();
  renderReviewIntelligence();
  renderExecutiveDashboard();
  renderMetrics();
  renderProposedPatches();
  renderTableFromPreview(els.queueHead, els.queueBody, []);
  renderTableFromPreview(els.reportHead, els.reportBody, []);
  activateTab("proposed");
  activatePromptTab("task");
  setWatchUi("Watch mode is off.");
  updateStatus("Connect a sheet and click Propose Changes.", "idle");
}

els.createDemoButton.addEventListener("click", async () => {
  try {
    await createDemoSheet();
  } catch (error) {
    updateStatus(error.message, "idle");
  }
});

els.proposeButton.addEventListener("click", async () => {
  try {
    await proposeChanges();
  } catch (error) {
    updateStatus(error.message, "idle");
  }
});

els.watchToggleButton.addEventListener("click", () => {
  try {
    if (state.watchEnabled) {
      stopWatchMode();
      updateStatus("Watch mode stopped.", "idle");
      showToast("Watch mode stopped.");
      return;
    }
    startWatchMode();
    updateStatus("Watch mode active. Auto-checking for row/tab changes.", "running");
    showToast("Watch mode started.");
  } catch (error) {
    updateStatus(error.message, "idle");
  }
});

els.applyButton.addEventListener("click", async () => {
  try {
    await applyApprovedChanges();
  } catch (error) {
    updateStatus(error.message, "idle");
  }
});

els.bulkApproveButton.addEventListener("click", bulkApproveLowRisk);

els.resetButton.addEventListener("click", resetDemoState);

els.selectAllPatches.addEventListener("change", () => {
  if (els.selectAllPatches.checked) {
    state.selectedPatchIds = new Set(state.patches.map((patch) => patch.patch_id));
  } else {
    state.selectedPatchIds = new Set();
  }
  renderProposedPatches();
  renderMetrics();
});

els.proposedBody.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  const patchId = target.dataset.patchId;
  if (!patchId) {
    return;
  }

  if (target.checked) {
    state.selectedPatchIds.add(patchId);
  } else {
    state.selectedPatchIds.delete(patchId);
  }

  renderProposedPatches();
  renderMetrics();
});

els.proposedTabBtn.addEventListener("click", () => activateTab("proposed"));
els.queueTabBtn.addEventListener("click", () => {
  if (!els.queueTabBtn.disabled) {
    activateTab("queue");
  }
});
els.reportTabBtn.addEventListener("click", () => {
  if (!els.reportTabBtn.disabled) {
    activateTab("report");
  }
});

els.taskPromptTabBtn.addEventListener("click", () => activatePromptTab("task"));
els.businessPromptTabBtn.addEventListener("click", () => activatePromptTab("business"));

els.promptInput.addEventListener("input", () => {
  state.prompt = els.promptInput.value.trim() || DEFAULT_PROMPT;
  state.effectivePrompt = buildEffectivePrompt(state.prompt, state.promptProfile);
});

[els.businessContextInput, els.businessLogicInput, els.operatingStyleInput].forEach((inputEl) => {
  inputEl.addEventListener("input", () => {
    const promptProfile = sanitizePromptProfile({
      businessContext: els.businessContextInput.value,
      businessLogic: els.businessLogicInput.value,
      operatingStyle: els.operatingStyleInput.value,
    });
    state.promptProfile = promptProfile;
    state.effectivePrompt = buildEffectivePrompt(els.promptInput.value, promptProfile);
    savePromptProfile(promptProfile);
  });
});

els.recentSheetSelect.addEventListener("change", () => {
  const selectedId = els.recentSheetSelect.value;
  if (!selectedId) {
    return;
  }
  els.spreadsheetIdInput.value = selectedId;
  state.spreadsheetId = selectedId;
});

state.recentSheets = loadRecentSheets();
renderRecentSheets();
initDashboardChrome();
resetDemoState();
