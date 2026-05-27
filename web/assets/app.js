const REVIEW_STORAGE_KEY = "canslim-sepa-review-queue-v1";
const WORKSPACE_STORAGE_KEY = "canslim-sepa-workspace-v1";
const REVIEW_STATUS_OPTIONS = [
  ["watch", "Watch"],
  ["ready", "Ready"],
  ["pass", "Pass"],
  ["bought", "Bought"],
  ["sold", "Sold"],
];
const REVIEW_PRIORITY_OPTIONS = [
  ["high", "High"],
  ["normal", "Normal"],
  ["low", "Low"],
];
const REVIEW_CHECK_OPTIONS = [
  ["weekly_chart", "Weekly"],
  ["daily_chart", "Daily"],
  ["volume_confirmed", "Volume"],
  ["market_aligned", "Market"],
  ["risk_defined", "Risk"],
];
const READINESS_BLOCKER_LABELS = {
  checklist_incomplete: "Checklist",
  missing_position_size: "Position size",
};
const POSITION_ALERT_LABELS = {
  ok: "Within plan",
  stop_breached: "Stop breached",
  near_stop: "Near stop",
  missing_current_price: "Missing price",
  missing_stop_loss: "Missing stop",
};
const POSITION_ALERT_NEAR_STOP_PCT = 3;
const REVIEW_STALE_DAYS = 5;
const READY_STALE_DAYS = 2;
const POSITION_ALERT_ATTENTION_ORDER = {
  stop_breached: 0,
  near_stop: 1,
  missing_current_price: 2,
  missing_stop_loss: 3,
};
const REVIEW_STATUS_PRIORITY = { ready: 0, watch: 1, bought: 2, sold: 3, pass: 4 };
const REVIEW_SORT_DEFAULT_DIR = {
  added_at: "desc",
  ticker: "asc",
  status: "asc",
  priority: "asc",
  score: "desc",
  risk: "desc",
  capital: "desc",
  shares: "desc",
};
const API_TIMEOUT_MS = 15000;
const CLIENT_EVENT_REPORT_LIMIT = 8;
const CLEAR_CONFIRM_MS = 8000;
const SCREENER_VIEW_LIMIT = 12;
const REVIEW_VIEW_LIMIT = 12;
const COMPARE_LIMIT = 4;
const WORKSPACE_AUDIT_DEFAULT_LIMIT = 8;
const WORKSPACE_AUDIT_FILTER_LIMIT = 24;
const WORKSPACE_AUDIT_LIMIT_STEP = 24;
const WORKSPACE_AUDIT_MAX_LIMIT = 120;
const SCREENER_SETUP_OPTIONS = new Set([
  "",
  "near_pivot",
  "forming_base",
  "extended",
  "breakout_confirmed",
  "breakout_unconfirmed",
  "below_pivot_not_actionable",
]);

const state = {
  profile: "canslim_score_rank",
  overview: null,
  screener: null,
  analysis: null,
  reviewQueue: [],
  reviewSummary: null,
  reviewActivity: [],
  reviewImportReport: null,
  preferences: null,
  screenerViews: [],
  reviewViews: [],
  sessionJournal: null,
  journalDirty: false,
  provenance: null,
  artifacts: null,
  diagnostics: null,
  requestTrace: null,
  clientEvents: null,
  risk: {
    account_equity: 100000,
    risk_pct: 0.5,
    max_capital_pct: 80,
    max_queue_risk_pct: 5,
    max_open_position_risk_pct: 6,
    max_concentration_pct: 60,
    max_open_concentration_pct: 60,
  },
  reviewSortBy: "added_at",
  reviewSortDir: "desc",
  reviewQuery: "",
  reviewStatus: "",
  reviewPriority: "",
  reviewTag: "",
  selectedReviewTickers: new Set(),
  selectedCompareTickers: new Set(),
  sortBy: "score",
  sortDir: "desc",
  job: { status: "idle", running: false },
  jobHistory: [],
  runtime: null,
  csrfToken: "",
  workspaceBackups: [],
  workspaceAudit: [],
  workspaceAuditMeta: null,
  workspaceAuditQuery: "",
  workspaceAuditType: "",
  workspaceAuditLimit: WORKSPACE_AUDIT_DEFAULT_LIMIT,
  syncIssues: [],
  clearConfirmUntil: 0,
};

const $ = (selector) => document.querySelector(selector);
let clientEventReportCount = 0;
const clientEventSignatures = new Set();

const els = {
  profileSelect: $("#profileSelect"),
  accountEquity: $("#accountEquity"),
  riskPerTrade: $("#riskPerTrade"),
  maxCapitalPct: $("#maxCapitalPct"),
  maxQueueRiskPct: $("#maxQueueRiskPct"),
  maxOpenRiskPct: $("#maxOpenRiskPct"),
  maxConcentrationPct: $("#maxConcentrationPct"),
  maxOpenConcentrationPct: $("#maxOpenConcentrationPct"),
  appStatus: $("#appStatus"),
  appStatusText: $("#appStatusText"),
  runtimeBadge: $("#runtimeBadge"),
  disclosureTitle: $("#disclosureTitle"),
  disclosureText: $("#disclosureText"),
  disclosureFreshness: $("#disclosureFreshness"),
  workspaceImportInput: $("#workspaceImportInput"),
  workspaceImportButton: $("#workspaceImportButton"),
  workspaceExportButton: $("#workspaceExportButton"),
  workspaceImportModal: $("#workspaceImportModal"),
  workspaceImportFilename: $("#workspaceImportFilename"),
  workspaceImportMetrics: $("#workspaceImportMetrics"),
  workspaceImportDetail: $("#workspaceImportDetail"),
  workspaceImportCancelButton: $("#workspaceImportCancelButton"),
  workspaceImportConfirmButton: $("#workspaceImportConfirmButton"),
  workspaceBackupButton: $("#workspaceBackupButton"),
  workspaceBackupModal: $("#workspaceBackupModal"),
  workspaceBackupSummary: $("#workspaceBackupSummary"),
  workspaceBackupList: $("#workspaceBackupList"),
  workspaceAuditSearch: $("#workspaceAuditSearch"),
  workspaceAuditType: $("#workspaceAuditType"),
  workspaceAuditClearButton: $("#workspaceAuditClearButton"),
  workspaceAuditList: $("#workspaceAuditList"),
  workspaceAuditExportButton: $("#workspaceAuditExportButton"),
  workspaceBackupCloseButton: $("#workspaceBackupCloseButton"),
  viewNameModal: $("#viewNameModal"),
  viewNameForm: $("#viewNameForm"),
  viewNameMode: $("#viewNameMode"),
  viewNameModalTitle: $("#viewNameModalTitle"),
  viewNameSummary: $("#viewNameSummary"),
  viewNameInput: $("#viewNameInput"),
  viewNameError: $("#viewNameError"),
  viewNameCancelButton: $("#viewNameCancelButton"),
  viewNameConfirmButton: $("#viewNameConfirmButton"),
  refreshButton: $("#refreshButton"),
  marketStatus: $("#marketStatus"),
  marketAsOf: $("#marketAsOf"),
  exposureMeter: $("#exposureMeter"),
  exposureValue: $("#exposureValue"),
  indicatorGrid: $("#indicatorGrid"),
  profileName: $("#profileName"),
  profileResultFile: $("#profileResultFile"),
  profileRuleGrid: $("#profileRuleGrid"),
  profileMatrixSummary: $("#profileMatrixSummary"),
  profileSweepButton: $("#profileSweepButton"),
  profileMatrix: $("#profileMatrix"),
  actionPosture: $("#actionPosture"),
  actionBrief: $("#actionBrief"),
  actionMetrics: $("#actionMetrics"),
  actionList: $("#actionList"),
  decisionBrief: $("#decisionBrief"),
  decisionTitle: $("#decisionTitle"),
  decisionSummary: $("#decisionSummary"),
  decisionMetrics: $("#decisionMetrics"),
  decisionFocus: $("#decisionFocus"),
  decisionSteps: $("#decisionSteps"),
  sessionJournalDate: $("#sessionJournalDate"),
  journalMarketThesis: $("#journalMarketThesis"),
  journalWatchlistFocus: $("#journalWatchlistFocus"),
  journalRiskNotes: $("#journalRiskNotes"),
  journalPostReview: $("#journalPostReview"),
  saveJournalButton: $("#saveJournalButton"),
  journalSavedAt: $("#journalSavedAt"),
  newsList: $("#newsList"),
  tickerForm: $("#tickerForm"),
  tickerInput: $("#tickerInput"),
  reviewAnalysisButton: $("#reviewAnalysisButton"),
  analysisExportButton: $("#analysisExportButton"),
  analysisTicker: $("#analysisTicker"),
  analysisName: $("#analysisName"),
  analysisScore: $("#analysisScore"),
  analysisBand: $("#analysisBand"),
  analysisMetrics: $("#analysisMetrics"),
  tradePlan: $("#tradePlan"),
  setupBrief: $("#setupBrief"),
  componentScores: $("#componentScores"),
  passReasons: $("#passReasons"),
  failReasons: $("#failReasons"),
  healthSummary: $("#healthSummary"),
  healthChecks: $("#healthChecks"),
  healthWarnings: $("#healthWarnings"),
  candidateQuality: $("#candidateQuality"),
  diagnosticsPanel: $("#diagnosticsPanel"),
  securityPosturePanel: $("#securityPosturePanel"),
  releaseReadinessPanel: $("#releaseReadinessPanel"),
  requestTracePanel: $("#requestTracePanel"),
  clientEventsPanel: $("#clientEventsPanel"),
  opsRunbook: $("#opsRunbook"),
  jobStatus: $("#jobStatus"),
  jobHistory: $("#jobHistory"),
  artifactList: $("#artifactList"),
  runNextButton: $("#runNextButton"),
  runEnrichButton: $("#runEnrichButton"),
  runScreenButton: $("#runScreenButton"),
  runTvExportButton: $("#runTvExportButton"),
  sessionReportButton: $("#sessionReportButton"),
  supportBundleButton: $("#supportBundleButton"),
  cancelJobButton: $("#cancelJobButton"),
  provenanceSummary: $("#provenanceSummary"),
  provenanceList: $("#provenanceList"),
  reviewList: $("#reviewList"),
  reviewActivity: $("#reviewActivity"),
  reviewSummary: $("#reviewSummary"),
  reviewCount: $("#reviewCount"),
  reviewSearchInput: $("#reviewSearchInput"),
  reviewSortSelect: $("#reviewSortSelect"),
  reviewSortDirection: $("#reviewSortDirection"),
  reviewStatusFilter: $("#reviewStatusFilter"),
  reviewPriorityFilter: $("#reviewPriorityFilter"),
  reviewTagFilter: $("#reviewTagFilter"),
  reviewViewSelect: $("#reviewViewSelect"),
  saveReviewViewButton: $("#saveReviewViewButton"),
  deleteReviewViewButton: $("#deleteReviewViewButton"),
  reviewClearFiltersButton: $("#reviewClearFiltersButton"),
  reviewExportFormat: $("#reviewExportFormat"),
  exportReviewButton: $("#exportReviewButton"),
  clearReviewButton: $("#clearReviewButton"),
  reviewBulkBar: $("#reviewBulkBar"),
  reviewSelectVisible: $("#reviewSelectVisible"),
  reviewSelectedCount: $("#reviewSelectedCount"),
  reviewBulkStatus: $("#reviewBulkStatus"),
  reviewBulkApply: $("#reviewBulkApply"),
  reviewBulkPriority: $("#reviewBulkPriority"),
  reviewBulkPriorityApply: $("#reviewBulkPriorityApply"),
  reviewBulkTags: $("#reviewBulkTags"),
  reviewBulkTagAdd: $("#reviewBulkTagAdd"),
  reviewBulkTagReplace: $("#reviewBulkTagReplace"),
  reviewBulkExport: $("#reviewBulkExport"),
  reviewBulkRemove: $("#reviewBulkRemove"),
  reviewImportForm: $("#reviewImportForm"),
  reviewImportTickers: $("#reviewImportTickers"),
  reviewImportButton: $("#reviewImportButton"),
  reviewPriceForm: $("#reviewPriceForm"),
  reviewPriceUpdates: $("#reviewPriceUpdates"),
  reviewPriceButton: $("#reviewPriceButton"),
  reviewImportReport: $("#reviewImportReport"),
  priceCanvas: $("#priceCanvas"),
  scoreCanvas: $("#scoreCanvas"),
  candidateSearch: $("#candidateSearch"),
  minScore: $("#minScore"),
  setupFilter: $("#setupFilter"),
  screenerViewSelect: $("#screenerViewSelect"),
  saveScreenerViewButton: $("#saveScreenerViewButton"),
  deleteScreenerViewButton: $("#deleteScreenerViewButton"),
  exportScreenerButton: $("#exportScreenerButton"),
  bulkReviewButton: $("#bulkReviewButton"),
  candidateCompare: $("#candidateCompare"),
  compareSummary: $("#compareSummary"),
  compareGrid: $("#compareGrid"),
  exportCompareButton: $("#exportCompareButton"),
  clearCompareButton: $("#clearCompareButton"),
  candidateStats: $("#candidateStats"),
  candidateRows: $("#candidateRows"),
};

async function api(path, params = {}, options = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });
  const controller = new AbortController();
  const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : API_TIMEOUT_MS;
  const timeout = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null;
  const method = String(options.method || "GET").toUpperCase();
  const headers = options.body ? { "Content-Type": "application/json" } : {};
  const writeRequest = isWriteMethod(method);
  if (writeRequest) {
    await ensureCsrfToken();
    if (state.csrfToken) headers["X-CSRF-Token"] = state.csrfToken;
  }
  const request = {
    method,
    headers: Object.keys(headers).length ? headers : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: controller.signal,
  };
  try {
    let response = await fetch(url, request);
    if (response.status === 403 && writeRequest) {
      state.csrfToken = "";
      if (await ensureCsrfToken()) {
        request.headers = { ...(request.headers || {}), "X-CSRF-Token": state.csrfToken };
        response = await fetch(url, request);
      }
    }
    if (!response.ok) {
      throw new Error(await responseErrorMessage(response));
    }
    if (response.status === 204) return null;
    return response.json();
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(`Request timed out: ${path}`);
    }
    throw error;
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

function isWriteMethod(method) {
  return ["POST", "PUT", "PATCH", "DELETE"].includes(String(method || "").toUpperCase());
}

async function ensureCsrfToken() {
  if (state.csrfToken) return true;
  const response = await fetch("/api/health", { cache: "no-store" });
  if (!response.ok) return false;
  applyHealthPayload(await response.json());
  return Boolean(state.csrfToken);
}

async function triggerDownload(url, filename) {
  try {
    await ensureCsrfToken();
    if (!state.csrfToken) throw new Error("Download token unavailable");
    let response = await fetchDownload(url);
    if (response.status === 403) {
      state.csrfToken = "";
      await ensureCsrfToken();
      response = await fetchDownload(url);
    }
    if (!response.ok) {
      throw new Error(await responseErrorMessage(response));
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename || downloadFilenameFromResponse(response) || "download";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    return true;
  } catch (error) {
    setAppStatus("error", "Download failed", userMessage(error));
    return false;
  }
}

async function fetchDownload(url) {
  return fetch(url.toString(), {
    cache: "no-store",
    headers: { "X-CSRF-Token": state.csrfToken },
  });
}

function downloadFilenameFromResponse(response) {
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/i);
  return match ? match[1] : "";
}

async function responseErrorMessage(response) {
  const headerRequestId = response.headers.get("X-Request-ID") || "";
  try {
    const contentType = response.headers.get("Content-Type") || "";
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      if (payload?.error) return withRequestId(payload.error, payload.request_id || headerRequestId);
    }
    const text = await response.text();
    if (text) return withRequestId(text, headerRequestId);
  } catch (error) {
    // Fall through to the status line.
  }
  return withRequestId(`${response.status} ${response.statusText || "Request failed"}`, headerRequestId);
}

function withRequestId(message, requestId) {
  const normalizedId = String(requestId || "").trim();
  const text = String(message || "Request failed").trim();
  return normalizedId ? `${text} · request ${normalizedId}` : text;
}

function installClientEventReporting() {
  window.addEventListener(
    "error",
    (event) => {
      if (event.target && event.target !== window) {
        const target = event.target;
        const tag = String(target.tagName || "resource").toLowerCase();
        reportClientEvent("resource_error", {
          message: `${tag} failed to load`,
          source: target.currentSrc || target.src || target.href || "",
        });
        return;
      }
      reportClientEvent("error", {
        message: event.message || "Unhandled browser error",
        source: event.filename || "",
        line: event.lineno,
        column: event.colno,
      });
    },
    true,
  );
  window.addEventListener("unhandledrejection", (event) => {
    reportClientEvent("unhandledrejection", {
      message: clientEventMessage(event.reason) || "Unhandled promise rejection",
    });
  });
}

function reportClientEvent(kind, detail = {}) {
  if (clientEventReportCount >= CLIENT_EVENT_REPORT_LIMIT) return;
  const event = {
    kind,
    message: clientEventMessage(detail.message),
    source: clientEventSource(detail.source),
    page_path: window.location.pathname || "/",
    line: Number.isFinite(Number(detail.line)) ? Number(detail.line) : undefined,
    column: Number.isFinite(Number(detail.column)) ? Number(detail.column) : undefined,
  };
  const signature = [event.kind, event.message, event.source, event.line, event.column].join("|");
  if (clientEventSignatures.has(signature)) return;
  clientEventSignatures.add(signature);
  clientEventReportCount += 1;
  fetch("/api/client-events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile: state.profile, event }),
    keepalive: true,
  }).catch(() => {
    // Client diagnostics must never interrupt the trading workflow.
  });
}

function clientEventMessage(value) {
  if (value && typeof value === "object" && "message" in value) {
    return String(value.message || "").slice(0, 220);
  }
  return String(value || "").slice(0, 220);
}

function clientEventSource(value) {
  const text = String(value || "");
  if (!text) return "";
  try {
    const url = new URL(text, window.location.origin);
    if (url.origin === window.location.origin) return url.pathname.slice(0, 160);
    return "external";
  } catch (error) {
    return text.split("?")[0].split("#")[0].slice(0, 160);
  }
}

function safeExternalHref(value) {
  const text = String(value || "").trim();
  if (!text) return "#";
  try {
    const url = new URL(text, window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch (error) {
    return "#";
  }
}

function safeSameOriginApiHref(value, fallback = "") {
  const candidates = [value, fallback].map((item) => String(item || "").trim()).filter(Boolean);
  for (const candidate of candidates) {
    try {
      const url = new URL(candidate, window.location.origin);
      if (url.origin === window.location.origin && url.pathname.startsWith("/api/")) {
        return `${url.pathname}${url.search}`;
      }
    } catch (error) {
      // Try the next candidate.
    }
  }
  return "#";
}

async function loadDashboard() {
  setLoading(true);
  state.syncIssues = [];
  setAppStatus("syncing", "Syncing");
  try {
    const [overview, screener] = await Promise.all([
      api("/api/overview", { profile: state.profile }),
      loadScreenerData(),
      loadServerReviewQueue(),
      loadReviewSummary(),
      loadServerHealth(),
      loadCurrentJob(),
      loadJobHistory(),
      loadArtifacts(),
      loadDiagnostics(),
      loadRequestTrace(),
      loadClientEvents(),
      loadProvenance(),
      loadSessionJournal(),
    ]);
    state.overview = overview;
    state.screener = screener;
    state.profile = overview.profile;
    renderOverview();
    renderScreener();
    renderReviewQueue();
    if (!state.analysis && overview.top_candidates?.[0]?.ticker) {
      await analyzeTicker(overview.top_candidates[0].ticker);
    }
    if (state.syncIssues.length) {
      setAppStatus("offline", "Partial sync", state.syncIssues.join(" | "));
    } else {
      setAppStatus("online", `Synced ${formatTime(new Date())}`, runtimeStatusDetail());
    }
  } catch (error) {
    setAppStatus("error", "Dashboard error", userMessage(error));
    renderError(error);
  } finally {
    setLoading(false);
  }
}

async function loadScreenerData() {
  return api("/api/screener", {
    profile: state.profile,
    q: els.candidateSearch.value,
    min_score: els.minScore.value,
    setup: els.setupFilter.value,
    sort_by: state.sortBy,
    sort_dir: state.sortDir,
    limit: 120,
  });
}

async function loadServerReviewQueue() {
  try {
    const payload = await api("/api/review", { profile: state.profile });
    applyReviewPayload(payload);
    return payload;
  } catch (error) {
    recordSyncIssue("Local review", error);
    applyLocalReviewBucket();
    return null;
  }
}

async function loadSessionJournal() {
  try {
    const payload = await api("/api/session/journal", {
      profile: state.profile,
      date: ensureJournalDate(),
    });
    state.sessionJournal = payload;
    renderSessionJournal(payload);
    return payload;
  } catch (error) {
    recordSyncIssue("Journal offline", error);
    state.sessionJournal = null;
    renderJournalStatus("Journal offline");
    return null;
  }
}

async function loadReviewSummary() {
  try {
    const payload = await api("/api/review/summary", reviewRiskParams());
    state.reviewSummary = payload;
    renderReviewSummary(payload);
    return payload;
  } catch (error) {
    recordSyncIssue("Local sizing", error);
    const fallback = calculateReviewSummary();
    state.reviewSummary = fallback;
    renderReviewSummary(fallback);
    return fallback;
  }
}

async function loadServerHealth() {
  try {
    const payload = await api("/api/health");
    applyHealthPayload(payload);
    return payload;
  } catch (error) {
    recordSyncIssue("Runtime offline", error);
    state.runtime = null;
    renderRuntimeBadge();
    return null;
  }
}

function applyHealthPayload(payload) {
  state.runtime = payload?.server || null;
  state.csrfToken = String(payload?.csrf_token || state.csrfToken || "");
  renderRuntimeBadge();
}

async function loadProvenance() {
  try {
    const payload = await api("/api/provenance", { profile: state.profile });
    state.provenance = payload;
    renderProvenance(payload);
    return payload;
  } catch (error) {
    recordSyncIssue("Evidence offline", error);
    state.provenance = null;
    renderProvenance(null, userMessage(error));
    return null;
  }
}

async function loadArtifacts() {
  try {
    const payload = await api("/api/artifacts", { profile: state.profile });
    state.artifacts = payload;
    renderArtifacts(payload);
    return payload;
  } catch (error) {
    recordSyncIssue("Artifacts offline", error);
    state.artifacts = null;
    renderArtifacts(null, userMessage(error));
    return null;
  }
}

async function loadDiagnostics() {
  try {
    const payload = await api("/api/diagnostics", { profile: state.profile });
    state.diagnostics = payload;
    renderDiagnostics(payload);
    return payload;
  } catch (error) {
    recordSyncIssue("Diagnostics offline", error);
    state.diagnostics = null;
    renderDiagnostics(null, userMessage(error));
    return null;
  }
}

async function loadRequestTrace() {
  try {
    const payload = await api("/api/request-trace", { limit: 8 });
    state.requestTrace = payload;
    renderRequestTrace(payload);
    return payload;
  } catch (error) {
    recordSyncIssue("Request trace offline", error);
    state.requestTrace = null;
    renderRequestTrace(null, userMessage(error));
    return null;
  }
}

async function loadClientEvents() {
  try {
    const payload = await api("/api/client-events", { limit: 8 });
    state.clientEvents = payload;
    renderClientEvents(payload);
    return payload;
  } catch (error) {
    recordSyncIssue("Browser diagnostics offline", error);
    state.clientEvents = null;
    renderClientEvents(null, userMessage(error));
    return null;
  }
}

async function cleanupWorkspaceTempFiles() {
  setLoading(true);
  setAppStatus("syncing", "Cleaning temp files");
  try {
    const payload = await api(
      "/api/workspace/temp-files/cleanup",
      {},
      { method: "POST", body: { confirm: "cleanup" } },
    );
    await loadDiagnostics();
    const deleted = Number(payload.deleted_count || 0);
    const failed = Number(payload.failed_count || 0);
    setAppStatus(
      failed ? "error" : "online",
      failed ? "Cleanup incomplete" : "Temp files cleaned",
      failed ? `${failed} failed · ${deleted} deleted` : `${deleted} deleted`,
    );
  } catch (error) {
    setAppStatus("error", "Cleanup failed", userMessage(error));
    await loadDiagnostics();
  } finally {
    setLoading(false);
  }
}

async function repairWorkspaceAuditStore() {
  setLoading(true);
  setAppStatus("syncing", "Repairing audit");
  try {
    const payload = await api(
      "/api/workspace/audit/repair",
      {},
      { method: "POST", body: { confirm: "repair" } },
    );
    await Promise.all([loadDiagnostics(), loadWorkspaceAudit()]);
    const repaired = Boolean(payload.repaired);
    setAppStatus(
      "online",
      repaired ? "Audit repaired" : "Audit readable",
      payload.quarantine_path ? `Quarantined ${payload.quarantine_path}` : payload.reason || "",
    );
  } catch (error) {
    setAppStatus("error", "Audit repair failed", userMessage(error));
    await loadDiagnostics();
  } finally {
    setLoading(false);
  }
}

async function loadWorkspacePreferences() {
  try {
    const payload = await api("/api/preferences");
    applyWorkspacePreferences(payload);
    return payload;
  } catch (error) {
    setAppStatus("offline", "Local prefs", userMessage(error));
    applyWorkspacePreferences(loadLocalWorkspacePreferences());
    return null;
  }
}

async function saveWorkspacePreferences() {
  const preferences = currentWorkspacePreferences();
  state.preferences = preferences;
  saveLocalWorkspacePreferences(preferences);
  try {
    const payload = await api("/api/preferences", {}, { method: "POST", body: preferences });
    applyWorkspacePreferences(payload, { updateControls: false });
    setAppStatus("online", "Preferences saved");
  } catch (error) {
    setAppStatus("offline", "Prefs local", userMessage(error));
  }
}

let preferencesTimer = null;
let clearConfirmTimer = null;
let workspaceImportConfirmation = null;
let viewNameConfirmation = null;
let workspaceAuditFilterTimer = null;
let workspaceAuditRequestId = 0;
let pendingScreenerViewDeleteId = "";
let pendingReviewViewDeleteId = "";
let pendingBackupRestoreFilename = "";
let pendingBackupRestorePreview = null;
let pendingBackupDeleteFilename = "";
let activeModal = null;
let modalReturnFocus = null;

const MODAL_FOCUS_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function saveWorkspacePreferencesDebounced() {
  clearTimeout(preferencesTimer);
  preferencesTimer = setTimeout(saveWorkspacePreferences, 350);
}

function applyWorkspacePreferences(payload, { updateControls = true } = {}) {
  const preferences = normalizeWorkspacePreferences(payload);
  state.preferences = preferences;
  state.profile = preferences.profile;
  state.sortBy = preferences.screener.sort_by;
  state.sortDir = preferences.screener.sort_dir;
  state.screenerViews = preferences.screener_views;
  state.reviewViews = preferences.review_views;
  state.risk = preferences.risk;
  state.reviewSortBy = preferences.review.sort_by;
  state.reviewSortDir = preferences.review.sort_dir;
  state.reviewQuery = preferences.review.query;
  state.reviewStatus = preferences.review.status;
  state.reviewPriority = preferences.review.priority;
  state.reviewTag = preferences.review.tag;
  saveLocalWorkspacePreferences(preferences);
  if (updateControls) {
    els.candidateSearch.value = preferences.screener.query;
    els.minScore.value = preferences.screener.min_score;
    els.setupFilter.value = preferences.screener.setup;
    els.accountEquity.value = formatPreferenceNumber(preferences.risk.account_equity, 0);
    els.riskPerTrade.value = formatPreferenceNumber(preferences.risk.risk_pct, 1);
    els.maxCapitalPct.value = formatPreferenceNumber(preferences.risk.max_capital_pct, 0);
    els.maxQueueRiskPct.value = formatPreferenceNumber(preferences.risk.max_queue_risk_pct, 1);
    els.maxOpenRiskPct.value = formatPreferenceNumber(preferences.risk.max_open_position_risk_pct, 1);
    els.maxConcentrationPct.value = formatPreferenceNumber(preferences.risk.max_concentration_pct, 0);
    els.maxOpenConcentrationPct.value = formatPreferenceNumber(preferences.risk.max_open_concentration_pct, 0);
    els.reviewSortSelect.value = preferences.review.sort_by;
    els.reviewSearchInput.value = preferences.review.query;
    els.reviewStatusFilter.value = preferences.review.status;
    els.reviewPriorityFilter.value = preferences.review.priority;
    els.reviewTagFilter.value = preferences.review.tag;
    renderReviewSortDirection();
  }
  renderScreenerViews();
  renderReviewViews();
}

function currentWorkspacePreferences() {
  return normalizeWorkspacePreferences({
    profile: state.profile,
    screener: {
      query: els.candidateSearch.value,
      min_score: els.minScore.value,
      setup: els.setupFilter.value,
      sort_by: state.sortBy,
      sort_dir: state.sortDir,
    },
    screener_views: state.screenerViews,
    review_views: state.reviewViews,
    risk: {
      account_equity: els.accountEquity.value,
      risk_pct: els.riskPerTrade.value,
      max_capital_pct: els.maxCapitalPct.value,
      max_queue_risk_pct: els.maxQueueRiskPct.value,
      max_open_position_risk_pct: els.maxOpenRiskPct.value,
      max_concentration_pct: els.maxConcentrationPct.value,
      max_open_concentration_pct: els.maxOpenConcentrationPct.value,
    },
    review: {
      query: state.reviewQuery,
      sort_by: state.reviewSortBy,
      sort_dir: state.reviewSortDir,
      status: state.reviewStatus,
      priority: state.reviewPriority,
      tag: state.reviewTag,
    },
  });
}

function normalizeWorkspacePreferences(payload) {
  const screener = payload?.screener || {};
  const risk = payload?.risk || {};
  const review = payload?.review || {};
  return {
    profile: payload?.profile || "canslim_score_rank",
    screener: {
      query: String(screener.query || ""),
      min_score: boundedNumber(screener.min_score, 70, 0, 100),
      setup: normalizeScreenerSetup(screener.setup),
      sort_by: normalizeSortBy(screener.sort_by),
      sort_dir: normalizeSortDir(screener.sort_dir),
    },
    screener_views: normalizeScreenerViews(payload?.screener_views),
    review_views: normalizeReviewViews(payload?.review_views),
    risk: {
      account_equity: boundedNumber(risk.account_equity, 100000, 0, 1_000_000_000),
      risk_pct: boundedNumber(risk.risk_pct, 0.5, 0, 5),
      max_capital_pct: boundedNumber(risk.max_capital_pct, 80, 0, 100),
      max_queue_risk_pct: boundedNumber(risk.max_queue_risk_pct, 5, 0, 25),
      max_open_position_risk_pct: boundedNumber(risk.max_open_position_risk_pct, 6, 0, 25),
      max_concentration_pct: boundedNumber(risk.max_concentration_pct, 60, 0, 100),
      max_open_concentration_pct: boundedNumber(risk.max_open_concentration_pct, 60, 0, 100),
    },
    review: {
      query: cleanReviewQuery(review.query),
      sort_by: normalizeReviewSortBy(review.sort_by),
      sort_dir: normalizeSortDir(review.sort_dir),
      status: normalizeReviewStatus(review.status),
      priority: normalizeReviewPriorityFilter(review.priority),
      tag: normalizeReviewTag(review.tag),
    },
  };
}

function normalizeScreenerViews(value) {
  if (!Array.isArray(value)) return [];
  const views = [];
  const seenIds = new Set();
  value.forEach((item) => {
    if (!item || typeof item !== "object" || views.length >= SCREENER_VIEW_LIMIT) return;
    const name = cleanScreenerViewName(item.name);
    if (!name) return;
    let id = cleanScreenerViewId(item.id) || screenerViewId(name);
    id = dedupeScreenerViewId(id, seenIds);
    seenIds.add(id);
    views.push({
      id,
      name,
      query: cleanScreenerQuery(item.query),
      min_score: boundedNumber(item.min_score, 70, 0, 100),
      setup: normalizeScreenerSetup(item.setup),
      sort_by: normalizeSortBy(item.sort_by),
      sort_dir: normalizeSortDir(item.sort_dir),
    });
  });
  return views;
}

function normalizeReviewViews(value) {
  if (!Array.isArray(value)) return [];
  const views = [];
  const seenIds = new Set();
  value.forEach((item) => {
    if (!item || typeof item !== "object" || views.length >= REVIEW_VIEW_LIMIT) return;
    const name = cleanReviewViewName(item.name);
    if (!name) return;
    let id = cleanReviewViewId(item.id) || reviewViewId(name);
    id = dedupeReviewViewId(id, seenIds);
    seenIds.add(id);
    views.push({
      id,
      name,
      query: cleanReviewQuery(item.query),
      sort_by: normalizeReviewSortBy(item.sort_by),
      sort_dir: normalizeSortDir(item.sort_dir),
      status: normalizeReviewStatus(item.status),
      priority: normalizeReviewPriorityFilter(item.priority),
      tag: normalizeReviewTag(item.tag),
    });
  });
  return views;
}

function cleanScreenerViewName(value) {
  return String(value || "").trim().replace(/\s+/g, " ").slice(0, 40);
}

function cleanReviewViewName(value) {
  return cleanScreenerViewName(value);
}

function cleanScreenerQuery(value) {
  return String(value || "").trim().replace(/\s+/g, " ").slice(0, 80);
}

function cleanScreenerViewId(value) {
  return String(value || "")
    .trim()
    .replace(/[^A-Za-z0-9_-]/g, "")
    .slice(0, 48);
}

function cleanReviewViewId(value) {
  return cleanScreenerViewId(value);
}

function dedupeScreenerViewId(id, seenIds) {
  let candidate = id || "view";
  let suffix = 2;
  while (seenIds.has(candidate)) {
    const suffixText = `-${suffix}`;
    candidate = `${id.slice(0, 48 - suffixText.length)}${suffixText}`;
    suffix += 1;
  }
  return candidate;
}

function dedupeReviewViewId(id, seenIds) {
  return dedupeScreenerViewId(id, seenIds);
}

function screenerViewId(name) {
  const slug =
    cleanScreenerViewName(name)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 24) || "view";
  return `${slug}-${Date.now().toString(36)}`.slice(0, 48);
}

function reviewViewId(name) {
  const slug =
    cleanReviewViewName(name)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 24) || "review";
  return `${slug}-${Date.now().toString(36)}`.slice(0, 48);
}

function loadLocalWorkspacePreferences() {
  try {
    return JSON.parse(localStorage.getItem(WORKSPACE_STORAGE_KEY) || "{}");
  } catch (error) {
    return {};
  }
}

function saveLocalWorkspacePreferences(preferences) {
  try {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(preferences));
  } catch (error) {
    // Preference persistence is best-effort.
  }
}

function updateRiskFromControls() {
  state.risk = currentWorkspacePreferences().risk;
  saveWorkspacePreferencesDebounced();
  if (state.analysis?.found) {
    renderTradePlan(state.analysis.research_brief || makeResearchBrief(state.analysis));
  }
  renderReviewQueue();
}

function renderOverview() {
  const overview = state.overview;
  renderProfiles(overview.profiles || []);
  renderProfileMatrix(overview.profiles || []);
  renderResearchDisclosure(overview.research_disclosure || {}, overview.data_health || {});
  renderDataHealth(overview.data_health || {});
  renderCandidateQuality(overview.candidate_quality || {});
  renderMarketDirection(overview.market_direction || {});
  renderIndicators(overview.indicators || []);
  renderProfileSummary(overview.profile_summary || {});
  renderActionCenter(overview.action_center || {});
  renderDecisionBrief(overview.decision_brief || {});
  renderNews(overview.news || []);
}

function renderProfiles(profiles) {
  els.profileSelect.innerHTML = profiles
    .map((profile) => {
      const selected = profile.name === state.profile ? "selected" : "";
      const count = Number.isFinite(profile.candidate_count) ? ` (${profile.candidate_count})` : "";
      return `<option value="${escapeHtml(profile.name)}" ${selected}>${escapeHtml(profile.label)}${count}</option>`;
    })
    .join("");
}

function renderProfileMatrix(profiles) {
  if (!els.profileMatrix) return;
  const rows = Array.isArray(profiles) ? profiles : [];
  const generatedCount = rows.filter((profile) => profile.state !== "missing").length;
  const candidateProfileCount = rows.filter((profile) => profile.state === "ready" || Number(profile.candidate_count || 0) > 0).length;
  const active = rows.find((profile) => profile.name === state.profile) || {};
  const running = Boolean(state.job?.running);
  const profileSweepRunning = running && state.job?.mode === "profile-sweep";
  els.profileMatrixSummary.textContent = rows.length
    ? `${formatNumber(generatedCount)}/${formatNumber(rows.length)} generated · ${formatNumber(candidateProfileCount)} with candidates · active ${active.label || state.profile.replaceAll("_", " ")}`
    : "No profiles";
  if (els.profileSweepButton) {
    els.profileSweepButton.disabled = running || !rows.length;
    els.profileSweepButton.textContent = profileSweepRunning ? "Running" : "Screen all";
    els.profileSweepButton.title = profileSweepRunning
      ? "Screening all configured profiles"
      : "Screen every configured strategy profile";
  }
  if (!rows.length) {
    els.profileMatrix.innerHTML = `<div class="profile-matrix-empty">No profile metadata</div>`;
    return;
  }
  els.profileMatrix.innerHTML = rows
    .map((profile) => {
      const isActive = profile.name === state.profile;
      const count = Number(profile.candidate_count || 0);
      const stateClass = profile.state || (count > 0 ? "ready" : profile.result_exists ? "empty" : "missing");
      const stateLabel = profileStateLabel(stateClass);
      const ageLabel = profile.result_age_hours === null || profile.result_age_hours === undefined
        ? "not generated"
        : formatAgeHours(profile.result_age_hours);
      const scoreLabel = Number.isFinite(Number(profile.top_score)) ? formatScore(profile.top_score) : "-";
      const runLabel = profileRunLabel(stateClass);
      const jobOnThisProfile = running && state.job?.profile === profile.name;
      return `
        <article class="profile-card ${escapeHtml(stateClass)} ${isActive ? "active" : ""}" aria-current="${isActive ? "true" : "false"}">
          <div>
            <span>${escapeHtml(stateLabel)}</span>
            <b>${escapeHtml(profile.label || profile.name || "Profile")}</b>
            <small title="${escapeHtml(profile.result_file || "")}">${escapeHtml(profile.result_file || "No result file")}</small>
          </div>
          <dl>
            <div><dt>Candidates</dt><dd>${escapeHtml(formatNumber(count))}</dd></div>
            <div><dt>Top</dt><dd>${escapeHtml(scoreLabel)}</dd></div>
            <div><dt>Age</dt><dd>${escapeHtml(ageLabel)}</dd></div>
          </dl>
          <div class="profile-card-actions">
            <button class="subtle" type="button" data-profile-switch="${escapeHtml(profile.name || "")}" ${isActive ? "disabled" : ""}>
              ${isActive ? "Active" : "Select"}
            </button>
            <button class="subtle" type="button" data-profile-run="${escapeHtml(profile.name || "")}" data-profile-run-mode="screen" ${running ? "disabled" : ""}>
              ${jobOnThisProfile ? "Running" : escapeHtml(runLabel)}
            </button>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderResearchDisclosure(disclosure, health = {}) {
  const resultAge = formatAgeHours(health.result_age_hours);
  const marketAge = formatMarketFreshness(health);
  els.disclosureTitle.textContent = disclosure.title || "Research aid only";
  els.disclosureText.textContent = disclosure.text || "Verify source data before acting.";
  els.disclosureFreshness.textContent = `Results ${resultAge} · Market ${marketAge}`;
}

function renderMarketDirection(market) {
  const status = market.market_direction_status || "not collected";
  const exposure = clamp(Number(market.recommended_exposure ?? 0), 0, 1);
  els.marketStatus.textContent = status.replaceAll("_", " ");
  els.marketAsOf.textContent = market.as_of ? `as of ${market.as_of}` : "";
  els.exposureMeter.value = exposure;
  els.exposureValue.textContent = formatPercent(exposure, { signed: false });
}

function renderIndicators(indicators) {
  if (!indicators.length) {
    els.indicatorGrid.innerHTML = `<div class="indicator-card"><span>Status</span><b>offline</b><p class="change flat">local data only</p></div>`;
    return;
  }
  els.indicatorGrid.innerHTML = indicators
    .map((item) => {
      const trend = Number(item.change_pct || 0);
      const klass = trend > 0.0001 ? "up" : trend < -0.0001 ? "down" : "flat";
      return `
        <div class="indicator-card">
          <span>${escapeHtml(item.label)}</span>
          <b>${formatNumber(item.latest, item.suffix)}</b>
          <p class="change ${klass}">${formatPercent(item.change_pct)} ${item.as_of ? `<small>${escapeHtml(item.as_of)}</small>` : ""}</p>
        </div>
      `;
    })
    .join("");
}

function renderProfileSummary(summary) {
  const profileLabel = summary.label || state.profile.replaceAll("_", " ");
  const candidateCount = Number.isFinite(Number(summary.candidate_count))
    ? `${formatNumber(summary.candidate_count)} candidates`
    : "No candidate count";
  const resultFile = summary.result_file || "No result file";
  const rules = Array.isArray(summary.rules) ? summary.rules.slice(0, 11) : [];
  const requirements = Array.isArray(summary.requirements) ? summary.requirements : [];

  els.profileName.textContent = profileLabel;
  els.profileResultFile.textContent = `${candidateCount} · ${resultFile}`;
  if (!rules.length && !requirements.length) {
    els.profileRuleGrid.innerHTML = `<div class="strategy-empty">No profile rules</div>`;
    return;
  }

  const ruleMarkup = rules
    .map((rule) => `
      <div class="strategy-rule">
        <span>${escapeHtml(rule.group || "Rule")}</span>
        <b>${escapeHtml(rule.label || "-")}</b>
        <em>${escapeHtml(rule.value || "-")}</em>
      </div>
    `)
    .join("");
  const requiredGates = requirements.filter((requirement) => requirement.required).map((requirement) => requirement.label).filter(Boolean);
  const optionalGates = requirements.filter((requirement) => !requirement.required).map((requirement) => requirement.label).filter(Boolean);
  const requiredGateLabel = requiredGates.length > 2 ? `${requiredGates.length} required` : requiredGates.join(", ") || "None";
  const optionalGateLabel = optionalGates.length ? `${optionalGates.length} optional` : "None";
  const requirementMarkup = `
    <div class="strategy-requirement ${requiredGates.length ? "required" : "optional"}" title="${escapeHtml(requiredGates.join(", ") || "None")}">
      <span>Required gates</span>
      <b>${escapeHtml(requiredGateLabel)}</b>
    </div>
    <div class="strategy-requirement optional" title="${escapeHtml(optionalGates.join(", ") || "None")}">
      <span>Optional gates</span>
      <b>${escapeHtml(optionalGateLabel)}</b>
    </div>
  `;
  els.profileRuleGrid.innerHTML = `${ruleMarkup}${requirementMarkup}`;
}

function renderActionCenter(center) {
  const counts = center.action_counts || {};
  const focus = center.focus_candidates || [];
  const tasks = center.tasks || [];
  const queueableCount = priorityActionCandidates().filter((candidate) => !isQueued(candidate.ticker)).length;
  const posture = actionPostureLabel(center.posture);
  els.actionPosture.textContent = posture;
  els.actionBrief.textContent = `${formatNumber(center.high_quality_count || 0)} high-quality · ${formatSummaryPercent((center.recommended_exposure || 0) * 100)} exposure`;
  els.actionMetrics.innerHTML = [
    ["Buy zone", counts.actionable || 0, "ready"],
    ["Near pivot", counts.watch_breakout || 0, "watch"],
    ["Base", counts.building_base || 0, "base"],
    ["Extended", counts.extended || 0, "extended"],
  ]
    .map(([label, value, klass]) => `
      <div class="action-metric ${escapeHtml(klass)}">
        <span>${escapeHtml(label)}</span>
        <b>${escapeHtml(formatNumber(value))}</b>
      </div>
    `)
    .join("");

  const taskMarkup = tasks.length
    ? tasks.map((task) => `
      <div class="action-task ${escapeHtml(task.severity || "muted")}">
        <b>${escapeHtml(task.label || "Action")}</b>
        <span>${escapeHtml(task.detail || "")}</span>
      </div>
    `).join("")
    : "";
  const commandMarkup = focus.length
    ? `
      <div class="action-command">
        <div>
          <b>Morning queue</b>
          <span>${escapeHtml(queueableCount ? `${queueableCount} priority candidate(s)` : "Priority candidates queued")}</span>
        </div>
        <button type="button" data-action-queue-all ${queueableCount ? "" : "disabled"}>${queueableCount ? "Queue" : "Queued"}</button>
      </div>
    `
    : "";
  const focusMarkup = focus.length
    ? focus.map((candidate) => `
      <div class="action-candidate ${escapeHtml(candidate.action || "research")} ${isQueued(candidate.ticker) ? "queued" : ""}">
        <button class="action-candidate-main" type="button" data-ticker="${escapeHtml(candidate.ticker || "")}">
          <span>${escapeHtml(renderActionLabelText(candidate.action))}</span>
          <b>${escapeHtml(candidate.ticker || "-")}</b>
          <em>${escapeHtml(formatScore(candidate.canslim_score))}</em>
          <small>${escapeHtml(candidate.reason || candidate.setup_status || "")}</small>
        </button>
        <button class="action-queue-button" type="button" data-action-queue="${escapeHtml(candidate.ticker || "")}" ${isQueued(candidate.ticker) ? "disabled" : ""}>
          ${isQueued(candidate.ticker) ? "Queued" : "Queue"}
        </button>
      </div>
    `).join("")
    : `<div class="action-empty">No priority candidates</div>`;
  els.actionList.innerHTML = `${commandMarkup}${taskMarkup}${focusMarkup}`;
}

function renderDecisionBrief(brief = state.overview?.decision_brief || {}) {
  if (!els.decisionBrief) return;
  const level = decisionLevel(brief.level);
  const summary = state.reviewSummary || calculateReviewSummary();
  const metrics = [
    ...(Array.isArray(brief.metrics) ? brief.metrics : []),
    decisionQueueMetric(summary),
    decisionRiskMetric(summary),
  ].slice(0, 7);
  els.decisionBrief.className = `decision-brief ${level}`;
  els.decisionTitle.textContent = brief.title || "Session pending";
  els.decisionSummary.textContent = brief.summary || "Syncing session checks";
  els.decisionMetrics.innerHTML = metrics.length
    ? metrics.map(renderDecisionMetric).join("")
    : `<div class="decision-empty">No session metrics</div>`;
  renderDecisionFocus(brief.focus || []);
  renderDecisionSteps(brief.next_steps || [], brief.blockers || []);
}

function renderDecisionMetric(metric) {
  const level = decisionLevel(metric.level);
  return `
    <div class="decision-metric ${escapeHtml(level)}">
      <span>${escapeHtml(metric.label || "Metric")}</span>
      <b>${escapeHtml(metric.value ?? "-")}</b>
      <small>${escapeHtml(metric.detail || "")}</small>
    </div>
  `;
}

function decisionQueueMetric(summary = {}) {
  const active = Number(summary.active_items || 0);
  const ready = Number(summary.status_counts?.ready || 0);
  const incomplete = Number(summary.checklist_incomplete_items || 0);
  const stale = Number(summary.aging?.stale_ready_count || 0) + Number(summary.aging?.stale_active_count || 0);
  return {
    label: "Queue",
    value: formatNumber(active),
    detail: stale
      ? `${formatNumber(stale)} stale · ${formatNumber(ready)} ready`
      : `${formatNumber(ready)} ready · ${formatNumber(incomplete)} checklist`,
    level: stale ? "warning" : active ? (ready ? "ready" : "watch") : "muted",
  };
}

function decisionRiskMetric(summary = {}) {
  const warnings = Array.isArray(summary.warnings) ? summary.warnings : [];
  const riskPct = numericValue(summary.risk_budget_pct);
  const riskLimit = numericValue(summary.risk?.max_queue_risk_pct ?? state.risk.max_queue_risk_pct);
  const overLimit = Number.isFinite(riskPct) && Number.isFinite(riskLimit) && riskPct > riskLimit;
  return {
    label: "Risk",
    value: formatSummaryPercent(riskPct),
    detail: warnings.length ? `${warnings.length} guardrail warning(s)` : `${formatCurrency(summary.total_risk_amount || 0)} planned`,
    level: overLimit ? "blocked" : warnings.length ? "warning" : "ready",
  };
}

function renderDecisionFocus(focus) {
  const rows = Array.isArray(focus) ? focus.filter(Boolean).slice(0, 4) : [];
  if (!rows.length) {
    els.decisionFocus.innerHTML = `<div class="decision-empty">No priority focus</div>`;
    return;
  }
  els.decisionFocus.innerHTML = rows
    .map((item) => `
      <button class="decision-focus-item ${escapeHtml(item.action || "research")}" type="button" data-ticker="${escapeHtml(item.ticker || "")}">
        <span>${escapeHtml(renderActionLabelText(item.action))}</span>
        <b>${escapeHtml(item.ticker || "-")}</b>
        <em>${escapeHtml(formatScore(item.canslim_score))}</em>
        <small>${escapeHtml(item.reason || item.setup_status || "")}</small>
      </button>
    `)
    .join("");
}

function renderDecisionSteps(steps, blockers) {
  const stepRows = Array.isArray(steps) ? steps.filter(Boolean).slice(0, 4) : [];
  const blockerRows = Array.isArray(blockers) ? blockers.filter(Boolean).slice(0, 2) : [];
  const rows = [
    ...blockerRows.map((item) => ({
      label: item.label,
      detail: item.detail,
      action: item.action,
      level: decisionLevel(item.level),
    })),
    ...stepRows.map((item) => ({
      label: item.label,
      detail: item.detail,
      action: item.action,
      level: item.priority === "high" ? "ready" : "watch",
    })),
  ].slice(0, 5);
  if (!rows.length) {
    els.decisionSteps.innerHTML = `<div class="decision-empty">No immediate next step</div>`;
    return;
  }
  els.decisionSteps.innerHTML = rows
    .map((item) => {
      const action = decisionAction(item.action);
      return `
        <div class="decision-step ${escapeHtml(item.level)}">
          <div>
            <b>${escapeHtml(item.label || "Review")}</b>
            <span>${escapeHtml(item.detail || "")}</span>
          </div>
          ${action ? `<button class="subtle" type="button" data-decision-action="${escapeHtml(action)}">${escapeHtml(decisionActionLabel(action))}</button>` : ""}
        </div>
      `;
    })
    .join("");
}

function decisionAction(action) {
  const normalized = String(action || "").replaceAll("_", "-");
  if (["download", "parse", "enrich", "screen", "tv-export", "review", "queue", "quality", "snapshot"].includes(normalized)) {
    return normalized;
  }
  return "";
}

function decisionActionLabel(action) {
  const labels = {
    download: "Download",
    parse: "Parse",
    enrich: "Enrich",
    screen: "Screen",
    "tv-export": "TV Export",
    review: "Review",
    queue: "Queue",
    quality: "Quality",
    snapshot: "Snapshot",
  };
  return labels[action] || action.replaceAll("-", " ");
}

function handleDecisionAction(action) {
  const normalized = decisionAction(action);
  if (!normalized) return;
  if (["download", "parse", "enrich", "screen", "tv-export"].includes(normalized)) {
    startPipelineJob(normalized);
    return;
  }
  if (normalized === "queue") {
    addPriorityActionCandidatesToReview();
    return;
  }
  if (normalized === "snapshot") {
    exportWorkspaceSnapshot();
    return;
  }
  if (normalized === "quality") {
    els.candidateQuality?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  document.querySelector(".review-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function decisionLevel(level) {
  const normalized = String(level || "").trim().toLowerCase();
  return ["ready", "watch", "warning", "blocked", "muted"].includes(normalized) ? normalized : "muted";
}

function renderSessionJournal(journal) {
  const payload = normalizeSessionJournal(journal);
  state.sessionJournal = payload;
  state.journalDirty = false;
  state.sessionJournalDate = payload.date;
  els.sessionJournalDate.value = payload.date;
  els.journalMarketThesis.value = payload.market_thesis;
  els.journalWatchlistFocus.value = payload.watchlist_focus;
  els.journalRiskNotes.value = payload.risk_notes;
  els.journalPostReview.value = payload.post_session_review;
  renderJournalStatus(payload.updated_at ? `Saved ${formatTime(payload.updated_at)}` : "Not saved");
}

function renderJournalStatus(label) {
  els.journalSavedAt.textContent = label;
  els.saveJournalButton.disabled = false;
}

function currentSessionJournalPayload(options = {}) {
  return normalizeSessionJournal({
    profile: state.profile,
    date: options.date || ensureJournalDate(),
    market_thesis: els.journalMarketThesis.value,
    watchlist_focus: els.journalWatchlistFocus.value,
    risk_notes: els.journalRiskNotes.value,
    post_session_review: els.journalPostReview.value,
  });
}

function normalizeSessionJournal(payload) {
  return {
    profile: payload?.profile || state.profile,
    date: normalizeJournalDate(payload?.date),
    market_thesis: cleanJournalNote(payload?.market_thesis),
    watchlist_focus: cleanJournalNote(payload?.watchlist_focus),
    risk_notes: cleanJournalNote(payload?.risk_notes),
    post_session_review: cleanJournalNote(payload?.post_session_review),
    updated_at: String(payload?.updated_at || ""),
  };
}

function ensureJournalDate() {
  if (!els.sessionJournalDate.value) {
    els.sessionJournalDate.value = localDateValue();
  }
  return normalizeJournalDate(els.sessionJournalDate.value);
}

function normalizeJournalDate(value) {
  const text = String(value || "").slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : localDateValue();
}

function localDateValue(date = new Date()) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function cleanJournalNote(value) {
  return String(value || "").replaceAll("\r\n", "\n").replaceAll("\r", "\n").replaceAll("\0", "").trim().slice(0, 2000);
}

async function saveSessionJournal(options = {}) {
  if (!state.sessionJournal && options.onlyIfDirty) return null;
  if (!state.journalDirty && options.onlyIfDirty) return state.sessionJournal;
  const payload = currentSessionJournalPayload({ date: options.date });
  if (!options.silent) {
    els.saveJournalButton.disabled = true;
    renderJournalStatus("Saving");
  }
  try {
    const saved = await api("/api/session/journal", {}, { method: "POST", body: payload });
    state.sessionJournal = normalizeSessionJournal(saved);
    state.sessionJournalDate = state.sessionJournal.date;
    state.journalDirty = false;
    if (!options.silent) {
      renderSessionJournal(saved);
      setAppStatus("online", "Journal saved");
    } else {
      renderJournalStatus(saved.updated_at ? `Saved ${formatTime(saved.updated_at)}` : "Saved");
    }
    return saved;
  } catch (error) {
    if (!options.silent) {
      setAppStatus("offline", "Journal local", userMessage(error));
      renderJournalStatus("Save failed");
    }
    return null;
  } finally {
    els.saveJournalButton.disabled = false;
  }
}

function actionPostureLabel(posture) {
  const labels = {
    risk_on: "Risk-on tape",
    selective: "Selective tape",
    defensive: "Defensive tape",
    unknown: "Market pending",
  };
  return labels[posture] || labels.unknown;
}

function profileStateLabel(stateValue) {
  const labels = {
    ready: "Ready",
    empty: "Empty",
    missing: "Missing",
  };
  return labels[stateValue] || labels.missing;
}

function profileRunLabel(stateValue) {
  if (stateValue === "ready") return "Rerun";
  return "Run screen";
}

function renderNews(news) {
  els.newsList.innerHTML = news
    .map((item) => {
      const href = safeExternalHref(item.url);
      const target = href !== "#" ? `target="_blank" rel="noreferrer"` : "";
      const published = item.published ? formatDate(item.published) : item.source || "";
      return `
        <a class="news-item" href="${escapeHtml(href)}" ${target}>
          <b>${escapeHtml(item.title || "Untitled")}</b>
          <span>${escapeHtml(item.source || "market")} ${published ? `· ${escapeHtml(published)}` : ""}</span>
        </a>
      `;
    })
    .join("");
}

function renderDataHealth(health) {
  const level = health.level || "unknown";
  const labels = {
    ready: "Ready",
    warning: "Ready with warnings",
    stale_market: "Market data stale",
    stale_results: "Results stale",
    missing_timestamp: "Timestamp missing",
    empty_results: "No candidates",
    needs_pipeline: "Pipeline action needed",
    unknown: "Unknown",
  };
  const resultAge = formatAgeHours(health.result_age_hours);
  const marketAge = formatMarketFreshness(health);
  els.healthSummary.innerHTML = `
    <div class="health-badge ${escapeHtml(level)}">
      <b>${escapeHtml(labels[level] || labels.unknown)}</b>
      <span>${escapeHtml(health.ready_checks ?? 0)}/${escapeHtml(health.total_checks ?? 0)} checks · ${escapeHtml(health.candidate_count ?? 0)} candidates</span>
    </div>
    <div class="freshness-grid">
      <div><span>Results</span><b>${escapeHtml(resultAge)}</b></div>
      <div><span>Market</span><b>${escapeHtml(marketAge)}</b></div>
    </div>
  `;
  els.healthChecks.innerHTML = (health.checks || [])
    .map((check) => {
      const count = check.count === null || check.count === undefined ? (check.ready ? "ready" : "pending") : formatNumber(check.count);
      return `
        <div class="check-item ${check.ready ? "ready" : "pending"}">
          <i></i>
          <span>${escapeHtml(check.label)}</span>
          <b>${escapeHtml(count)}</b>
        </div>
      `;
    })
    .join("");

  const notes = [];
  if (health.next_action && health.next_action !== "none" && health.recommended_commands?.[0]) {
    notes.push(`<code>${escapeHtml(health.recommended_commands[0])}</code>`);
  }
  (health.warnings || []).forEach((warning) => notes.push(`<span>${escapeHtml(warning)}</span>`));
  const findings = renderHealthFindings(health.source_findings || []);
  const noteHtml = notes.length ? notes.map((note) => `<p>${note}</p>`).join("") : "";
  els.healthWarnings.innerHTML = findings || noteHtml
    ? `${findings}${noteHtml}`
    : `<p>Pipeline ready</p>`;
  renderJobControls(health);
  renderOpsRunbook();
}

function renderHealthFindings(findings) {
  const rows = Array.isArray(findings) ? findings.slice(0, 5) : [];
  if (!rows.length) return "";
  return `
    <div class="source-findings">
      ${rows.map((finding) => `
        <div class="source-finding ${escapeHtml(finding.level || "warning")}">
          <b>${escapeHtml(sourceFindingLevel(finding.level))}</b>
          <span title="${escapeHtml(finding.path || finding.as_of || "")}">${escapeHtml(finding.label || "Data source")}</span>
          <em>${escapeHtml(finding.detail || "")}</em>
          ${finding.next_action && finding.next_action !== "none" ? `<small>${escapeHtml(String(finding.next_action).replaceAll("_", " "))}</small>` : ""}
        </div>
      `).join("")}
    </div>
  `;
}

function sourceFindingLevel(level) {
  const labels = {
    missing: "Missing",
    stale: "Stale",
    unknown: "Unknown",
    warning: "Warning",
  };
  return labels[level] || labels.warning;
}

function renderCandidateQuality(quality = {}) {
  if (!els.candidateQuality) return;
  const coverage = Array.isArray(quality.coverage) ? quality.coverage : [];
  const issueRows = Array.isArray(quality.issue_rows) ? quality.issue_rows : [];
  const level = qualityLevel(quality.level);
  if (!coverage.length) {
    els.candidateQuality.innerHTML = `
      <div class="quality-head ${escapeHtml(level)}">
        <div>
          <b>Candidate quality</b>
          <span>${escapeHtml(quality.summary || "No candidate rows")}</span>
        </div>
        <em>${escapeHtml(qualityLevelLabel(level))}</em>
      </div>
    `;
    return;
  }
  const criticalTotal = Number(quality.critical_total) || coverage.filter((field) => field.critical).length;
  const criticalReady = Number(quality.critical_ready) || coverage.filter((field) => field.critical && qualityLevel(field.level) === "ready").length;
  els.candidateQuality.innerHTML = `
    <div class="quality-head ${escapeHtml(level)}">
      <div>
        <b>Candidate quality</b>
        <span>${escapeHtml(quality.summary || `${criticalReady}/${criticalTotal} critical fields ready`)}</span>
      </div>
      <em>${escapeHtml(formatNumber(quality.row_count || 0))} rows</em>
    </div>
    <div class="quality-coverage-grid">
      ${coverage.slice(0, 11).map((field) => `
        <div class="quality-field ${escapeHtml(qualityLevel(field.level))} ${field.critical ? "critical" : ""}">
          <span>${escapeHtml(field.label || field.key || "Field")}</span>
          <b>${escapeHtml(formatSummaryPercent(field.coverage_pct))}</b>
          <meter min="0" max="100" value="${escapeHtml(clamp(Number(field.coverage_pct) || 0, 0, 100))}"></meter>
        </div>
      `).join("")}
    </div>
    ${issueRows.length ? `
      <div class="quality-issue-list">
        ${issueRows.slice(0, 5).map((row) => `
          <button class="quality-issue-row" type="button" data-ticker="${escapeHtml(row.ticker || "")}">
            <b>${escapeHtml(row.ticker || "-")}</b>
            <span title="${escapeHtml(row.name || "")}">${escapeHtml((row.missing || []).join(", "))}</span>
            <em>${escapeHtml(formatScore(row.score))}</em>
          </button>
        `).join("")}
      </div>
    ` : ""}
  `;
}

function qualityLevel(level) {
  const normalized = String(level || "").trim().toLowerCase();
  return ["ready", "warning", "blocked"].includes(normalized) ? normalized : "warning";
}

function qualityLevelLabel(level) {
  const labels = {
    ready: "Ready",
    warning: "Check",
    blocked: "Blocked",
  };
  return labels[qualityLevel(level)] || labels.warning;
}

function renderProvenance(payload, errorMessage = "") {
  if (!payload) {
    els.provenanceSummary.innerHTML = `
      <div class="provenance-status missing">
        <b>Unavailable</b>
        <span>${escapeHtml(errorMessage || "Evidence metadata unavailable")}</span>
      </div>
    `;
    els.provenanceList.innerHTML = "";
    return;
  }

  const missingCount = payload.missing_required?.length || 0;
  const staleCount = payload.stale_sources?.length || 0;
  const statusClass = missingCount ? "missing" : staleCount ? "stale" : "ready";
  const statusLabel = missingCount ? "Missing source" : staleCount ? "Stale source" : "Traceable";
  els.provenanceSummary.innerHTML = `
    <div class="provenance-status ${statusClass}">
      <b>${escapeHtml(statusLabel)}</b>
      <span>${escapeHtml(payload.source_count || 0)} sources · ${escapeHtml(formatSummaryPercent(payload.readiness_pct))} ready</span>
    </div>
  `;

  const sources = payload.sources || [];
  if (!sources.length) {
    els.provenanceList.innerHTML = `<div class="empty-state">No source files detected</div>`;
    return;
  }
  els.provenanceList.innerHTML = sources
    .map((source) => {
      const stale = Boolean(source.stale);
      const stateClass = !source.exists ? "missing" : stale ? "stale" : "ready";
      const stateLabel = !source.exists ? "Missing" : stale ? formatAgeHours(source.age_hours) : "Ready";
      const detail = source.exists
        ? `${formatBytes(source.size)}${source.rows !== undefined ? ` · ${formatNumber(source.rows)} rows` : ""}`
        : source.required ? "required" : "optional";
      return `
        <div class="provenance-item ${stateClass}">
          <i></i>
          <div>
            <b>${escapeHtml(source.label)}</b>
            <span title="${escapeHtml(source.path)}">${escapeHtml(source.path)}</span>
          </div>
          <em title="${escapeHtml(source.sha256_12 || "")}">${escapeHtml(source.sha256_12 || stateLabel)}</em>
          <small>${escapeHtml(detail)}</small>
        </div>
      `;
    })
    .join("");
}

async function loadCurrentJob() {
  try {
    state.job = await api("/api/jobs/current");
  } catch (error) {
    recordSyncIssue("Jobs offline", error);
    state.job = { status: "unavailable", running: false, log: [error.message || "Job API unavailable"] };
  }
  return state.job;
}

async function loadJobHistory() {
  try {
    const payload = await api("/api/jobs/history", { limit: 6 });
    state.jobHistory = Array.isArray(payload?.jobs) ? payload.jobs : [];
  } catch (error) {
    recordSyncIssue("Job history offline", error);
    state.jobHistory = [];
  }
  renderJobHistory();
  return state.jobHistory;
}

function renderJobControls(health = state.overview?.data_health || {}) {
  const job = state.job || { status: "idle", running: false };
  const running = Boolean(job.running);
  const nextMode = nextActionMode(health.next_action);
  const latestLog = (job.log || []).slice(-3).filter(Boolean);
  const statusText = job.status === "idle" ? "Ready" : job.status;
  els.jobStatus.innerHTML = `
    <div class="job-state ${escapeHtml(job.status || "idle")}">
      <b>${escapeHtml(statusText)}</b>
      <span>${escapeHtml(job.mode || nextMode || "pipeline")} ${job.profile ? `· ${escapeHtml(job.profile)}` : ""}</span>
    </div>
    ${latestLog.length ? `<pre>${latestLog.map(escapeHtml).join("\n")}</pre>` : ""}
  `;
  els.runNextButton.dataset.mode = nextMode || "";
  els.runNextButton.disabled = running || !nextMode;
  els.runEnrichButton.disabled = running;
  els.runScreenButton.disabled = running;
  els.runTvExportButton.disabled = running;
  els.cancelJobButton.disabled = !running || job.status === "cancelling";
  renderJobHistory();
  renderProfileMatrix(state.overview?.profiles || []);
  renderOpsRunbook();
}

function renderJobHistory() {
  const jobs = state.jobHistory || [];
  if (!jobs.length) {
    els.jobHistory.innerHTML = `<div class="job-history-empty">No job history</div>`;
    return;
  }
  els.jobHistory.innerHTML = jobs
    .slice(0, 5)
    .map((job) => {
      const status = String(job.status || "unknown");
      const time = job.finished_at || job.started_at || "";
      const rerunMode = jobHistoryRerunMode(job.mode);
      const canRerun = Boolean(rerunMode && !state.job?.running);
      const logTail = (job.log_tail || []).map((line) => String(line || "")).filter(Boolean).slice(-8);
      const latestLog = logTail.slice(-1)[0] || job.command || "";
      const meta = [
        job.id ? `#${job.id}` : "",
        job.returncode !== null && job.returncode !== undefined ? `rc ${job.returncode}` : "",
        job.pid ? `pid ${job.pid}` : "",
      ].filter(Boolean).join(" · ");
      return `
        <details class="job-history-item ${escapeHtml(status)}">
          <summary>
            <i></i>
            <div>
              <b>${escapeHtml(job.mode || "pipeline")}</b>
              <span>${escapeHtml(job.profile || "default")} · ${escapeHtml(formatTime(time) || "-")}</span>
              ${latestLog ? `<small title="${escapeHtml(latestLog)}">${escapeHtml(latestLog)}</small>` : ""}
            </div>
            <em>${escapeHtml(status)}</em>
          </summary>
          <div class="job-history-detail">
            <span>${escapeHtml(meta || "No process metadata")}</span>
            ${job.command ? `<code>${escapeHtml(job.command)}</code>` : ""}
            ${logTail.length ? `<pre>${logTail.map(escapeHtml).join("\n")}</pre>` : `<small>No captured log lines</small>`}
            <div class="job-history-actions">
              <button
                class="subtle"
                type="button"
                data-job-rerun="${escapeHtml(rerunMode)}"
                data-job-profile="${escapeHtml(job.profile || "")}"
                ${canRerun ? "" : "disabled"}
              >Rerun</button>
            </div>
          </div>
        </details>
      `;
    })
    .join("");
}

function jobHistoryRerunMode(mode) {
  const normalized = String(mode || "").trim().replaceAll("_", "-");
  const allowed = new Set(["status", "download", "parse", "enrich", "screen", "update", "tv-export"]);
  return nextActionMode(normalized) || (allowed.has(normalized) ? normalized : "");
}

function renderArtifacts(payload = state.artifacts, errorMessage = "") {
  if (!els.artifactList) return;
  if (!payload) {
    els.artifactList.innerHTML = `
      <div class="artifact-list-head">
        <b>Artifacts</b>
        <span>${escapeHtml(errorMessage || "Unavailable")}</span>
      </div>
      <div class="artifact-empty">No artifact metadata</div>
    `;
    renderOpsRunbook();
    return;
  }

  const artifacts = payload.artifacts || [];
  const readyCount = artifacts.filter((artifact) => artifact.exists).length;
  const totalCount = artifacts.length;
  if (!artifacts.length) {
    els.artifactList.innerHTML = `
      <div class="artifact-list-head">
        <b>Artifacts</b>
        <span>0 ready</span>
      </div>
      <div class="artifact-empty">No generated files</div>
    `;
    renderOpsRunbook();
    return;
  }

  els.artifactList.innerHTML = `
    <div class="artifact-list-head">
      <b>Artifacts</b>
      <span>${escapeHtml(readyCount)}/${escapeHtml(totalCount)} ready</span>
    </div>
    ${artifacts
      .map((artifact) => {
        const exists = Boolean(artifact.exists);
        const details = artifactDetails(artifact);
        const fallbackHref = `/api/artifacts/download?profile=${encodeURIComponent(payload.profile || state.profile)}&id=${encodeURIComponent(artifact.id || "")}`;
        const href = safeSameOriginApiHref(artifact.download_url, fallbackHref);
        return `
          <div class="artifact-item ${exists ? "ready" : "missing"}">
            <i></i>
            <div>
              <b>${escapeHtml(artifact.label || artifact.id || "Artifact")}</b>
              <span title="${escapeHtml(artifact.path || "")}">${escapeHtml(artifact.path || artifact.filename || "-")}</span>
              <small>${escapeHtml(details)}</small>
            </div>
            ${
              exists
                ? `<a href="${escapeHtml(href)}" data-artifact-download="${escapeHtml(href)}" data-artifact-filename="${escapeHtml(artifact.filename || "")}">Download</a>`
                : `<em>Missing</em>`
            }
          </div>
        `;
      })
      .join("")}
  `;
  renderOpsRunbook();
  renderDecisionBrief();
}

function renderDiagnostics(payload = state.diagnostics, errorMessage = "") {
  if (!els.diagnosticsPanel) return;
  if (!payload) {
    els.diagnosticsPanel.innerHTML = `
      <div class="diagnostics-head blocked">
        <div>
          <b>System diagnostics</b>
          <span>${escapeHtml(errorMessage || "Unavailable")}</span>
        </div>
        <em>offline</em>
      </div>
    `;
    renderSecurityPosture(null, errorMessage || "Unavailable");
    renderReleaseReadiness(null, errorMessage || "Unavailable");
    return;
  }

  const checks = Array.isArray(payload.checks) ? payload.checks : [];
  const level = diagnosticLevel(payload.level);
  const counts = payload.counts || {};
  const warningCount = Number(counts.warning) || 0;
  const blockedCount = Number(counts.blocked) || 0;
  const detail = blockedCount
    ? `${blockedCount} blocked · ${warningCount} warning`
    : warningCount
    ? `${warningCount} warning`
    : "ready";
  els.diagnosticsPanel.innerHTML = `
    <div class="diagnostics-head ${escapeHtml(level)}">
      <div>
        <b>System diagnostics</b>
        <span>${escapeHtml(payload.summary || `${checks.length} checks`)}</span>
      </div>
      <em>${escapeHtml(detail)}</em>
    </div>
    <div class="diagnostic-list">
      ${checks.map((check) => `
        <div class="diagnostic-row ${escapeHtml(diagnosticLevel(check.level))}">
          <i></i>
          <div>
            <b>${escapeHtml(check.label || "Check")}</b>
            <span title="${escapeHtml(check.path || "")}">${escapeHtml(check.detail || check.path || "")}</span>
          </div>
          ${
            check.next_action
              ? `<button class="subtle" type="button" data-diagnostic-action="${escapeHtml(check.next_action)}">${escapeHtml(diagnosticActionLabel(check.next_action))}</button>`
              : `<em>${escapeHtml(diagnosticLevelLabel(check.level))}</em>`
          }
        </div>
      `).join("")}
    </div>
  `;
  renderSecurityPosture(payload.security || null);
  renderReleaseReadiness(payload.release_readiness || null, "", payload.deployment || null);
}

function renderSecurityPosture(payload, errorMessage = "") {
  if (!els.securityPosturePanel) return;
  if (!payload) {
    els.securityPosturePanel.innerHTML = `
      <div class="security-posture-head blocked">
        <div>
          <b>Security posture</b>
          <span>${escapeHtml(errorMessage || "Unavailable")}</span>
        </div>
        <em>offline</em>
      </div>
    `;
    return;
  }
  const controls = Array.isArray(payload.controls) ? payload.controls : [];
  const level = diagnosticLevel(payload.level);
  els.securityPosturePanel.innerHTML = `
    <div class="security-posture-head ${escapeHtml(level)}">
      <div>
        <b>Security posture</b>
        <span>${escapeHtml(payload.summary || `${controls.length} controls`)}</span>
      </div>
      <em>${escapeHtml(diagnosticLevelLabel(level))}</em>
    </div>
    <div class="security-posture-list">
      ${controls.map((control) => `
        <div class="security-posture-row ${escapeHtml(diagnosticLevel(control.level))}">
          <i></i>
          <div>
            <b>${escapeHtml(control.label || "Control")}</b>
            <span>${escapeHtml(control.detail || "")}</span>
          </div>
          <em>${escapeHtml(diagnosticLevelLabel(control.level))}</em>
        </div>
      `).join("")}
    </div>
  `;
}

function renderReleaseReadiness(payload, errorMessage = "", deployment = null) {
  if (!els.releaseReadinessPanel) return;
  if (!payload) {
    els.releaseReadinessPanel.innerHTML = `
      <div class="release-readiness-head blocked">
        <div>
          <b>Release readiness</b>
          <span>${escapeHtml(errorMessage || "Unavailable")}</span>
        </div>
        <em>offline</em>
      </div>
    `;
    return;
  }
  const items = Array.isArray(payload.items) ? payload.items : [];
  const level = diagnosticLevel(payload.level);
  const counts = payload.counts || {};
  const attention = (Number(counts.warning) || 0) + (Number(counts.blocked) || 0);
  els.releaseReadinessPanel.innerHTML = `
    <div class="release-readiness-head ${escapeHtml(level)}">
      <div>
        <b>Release readiness</b>
        <span>${escapeHtml(payload.summary || `${items.length} gates`)}</span>
      </div>
      <em>${escapeHtml(attention ? `${attention} action${attention === 1 ? "" : "s"}` : "ready")}</em>
    </div>
    <div class="release-readiness-summary ${escapeHtml(level)}">
      ${escapeHtml(payload.recommendation || diagnosticLevelLabel(level))}
    </div>
    <div class="release-readiness-list">
      ${items.map((item) => `
        <div class="release-readiness-row ${escapeHtml(diagnosticLevel(item.level))}">
          <i></i>
          <div>
            <b>${escapeHtml(item.label || "Gate")}</b>
            <span title="${escapeHtml(item.path || "")}">${escapeHtml(item.detail || item.path || "")}</span>
          </div>
          ${
            item.next_action
              ? `<button class="subtle" type="button" data-diagnostic-action="${escapeHtml(item.next_action)}">${escapeHtml(diagnosticActionLabel(item.next_action))}</button>`
              : `<em>${escapeHtml(diagnosticLevelLabel(item.level))}</em>`
          }
        </div>
      `).join("")}
    </div>
    ${renderDeploymentGuide(deployment)}
  `;
}

function renderDeploymentGuide(guide) {
  if (!guide || !Array.isArray(guide.commands)) return "";
  const commands = guide.commands.slice(0, 3);
  const notes = Array.isArray(guide.notes) ? guide.notes.slice(0, 3) : [];
  return `
    <div class="deployment-guide">
      <div class="deployment-guide-head">
        <b>Deployment handoff</b>
        <span>${escapeHtml(guide.auth_env || "CANSLIM_DASHBOARD_AUTH")}</span>
      </div>
      ${renderReadinessProbe(guide.probe)}
      <div class="deployment-command-list">
        ${commands.map((item) => `
          <div class="deployment-command">
            <b>${escapeHtml(item.label || item.id || "Command")}</b>
            <code>${escapeHtml(item.command || "")}</code>
            <span>${escapeHtml(item.detail || "")}</span>
          </div>
        `).join("")}
      </div>
      ${
        notes.length
          ? `<div class="deployment-notes">${notes.map((note) => `<span>${escapeHtml(note)}</span>`).join("")}</div>`
          : ""
      }
    </div>
  `;
}

function renderReadinessProbe(probe) {
  if (!probe) return "";
  return `
    <div class="readiness-probe">
      <b>Readiness probe</b>
      <code>${escapeHtml(probe.method || "GET")} ${escapeHtml(probe.path || "/api/readiness")}</code>
      <span>${escapeHtml(probe.success || probe.detail || "")}</span>
    </div>
  `;
}

function diagnosticLevel(level) {
  const normalized = String(level || "").trim().toLowerCase();
  return ["ready", "warning", "blocked"].includes(normalized) ? normalized : "warning";
}

function diagnosticLevelLabel(level) {
  const labels = {
    ready: "Ready",
    warning: "Check",
    blocked: "Blocked",
  };
  return labels[diagnosticLevel(level)] || labels.warning;
}

function diagnosticActionLabel(action) {
  const normalized = String(action || "").replaceAll("_", "-");
  const labels = {
    download: "Download",
    parse: "Parse",
    enrich: "Enrich",
    screen: "Screen",
    "tv-export": "TV Export",
    "profile-sweep": "Screen all",
    "cleanup-workspace-temps": "Clean temp files",
    "repair-workspace-audit": "Repair audit",
    "open-workspace-backups": "Restore backup",
    "configure-auth": "Configure auth",
  };
  return labels[normalized] || normalized.replaceAll("-", " ");
}

function renderRequestTrace(payload = state.requestTrace, errorMessage = "") {
  if (!els.requestTracePanel) return;
  if (!payload) {
    els.requestTracePanel.innerHTML = `
      <div class="request-trace-head warning">
        <div>
          <b>Request trace</b>
          <span>${escapeHtml(errorMessage || "Unavailable")}</span>
        </div>
        <em>offline</em>
      </div>
    `;
    return;
  }
  const requests = Array.isArray(payload.requests) ? payload.requests : [];
  const errorCount = requests.filter((request) => Number(request.status || 0) >= 400).length;
  els.requestTracePanel.innerHTML = `
    <div class="request-trace-head ${errorCount ? "warning" : "ready"}">
      <div>
        <b>Request trace</b>
        <span>${escapeHtml(formatNumber(requests.length))} recent · ${escapeHtml(formatNumber(errorCount))} error${errorCount === 1 ? "" : "s"}</span>
      </div>
      <em>${escapeHtml(errorCount ? "check" : "ready")}</em>
    </div>
    <div class="request-trace-list">
      ${
        requests.length
          ? requests.slice(0, 6).map((request) => renderRequestTraceRow(request)).join("")
          : `<div class="request-trace-empty">No API requests yet</div>`
      }
    </div>
  `;
}

function renderRequestTraceRow(request) {
  const status = Number(request.status || 0);
  const failed = status >= 400;
  const requestId = String(request.request_id || "");
  const meta = [
    request.method || "GET",
    status || "-",
    Number.isFinite(Number(request.duration_ms)) ? `${Number(request.duration_ms).toFixed(1)} ms` : "",
    requestId ? `req ${requestId}` : "",
  ].filter(Boolean).join(" · ");
  const detail = request.error || request.error_code || meta;
  return `
    <div class="request-trace-row ${failed ? "warning" : "ready"}">
      <i></i>
      <div>
        <b title="${escapeHtml(request.path || "")}">${escapeHtml(request.path || "-")}</b>
        <span title="${escapeHtml(detail)}">${escapeHtml(detail)}</span>
      </div>
      <em>${escapeHtml(meta)}</em>
    </div>
  `;
}

function renderClientEvents(payload = state.clientEvents, errorMessage = "") {
  if (!els.clientEventsPanel) return;
  if (!payload) {
    els.clientEventsPanel.innerHTML = `
      <div class="client-events-head warning">
        <div>
          <b>Browser events</b>
          <span>${escapeHtml(errorMessage || "Unavailable")}</span>
        </div>
        <em>offline</em>
      </div>
    `;
    return;
  }
  const events = Array.isArray(payload.events) ? payload.events : [];
  els.clientEventsPanel.innerHTML = `
    <div class="client-events-head ${events.length ? "warning" : "ready"}">
      <div>
        <b>Browser events</b>
        <span>${escapeHtml(formatNumber(events.length))} recent client issue${events.length === 1 ? "" : "s"}</span>
      </div>
      <em>${escapeHtml(events.length ? "check" : "ready")}</em>
    </div>
    <div class="client-events-list">
      ${
        events.length
          ? events.slice(0, 6).map((event) => renderClientEventRow(event)).join("")
          : `<div class="client-events-empty">No browser runtime events</div>`
      }
    </div>
  `;
}

function renderClientEventRow(event) {
  const kind = String(event.kind || "error").replaceAll("_", " ");
  const location = [
    event.source || event.page_path || "",
    Number.isFinite(Number(event.line)) ? `:${Number(event.line)}` : "",
    Number.isFinite(Number(event.column)) ? `:${Number(event.column)}` : "",
  ].join("");
  return `
    <div class="client-event-row warning">
      <i></i>
      <div>
        <b title="${escapeHtml(event.message || "")}">${escapeHtml(event.message || "Client event")}</b>
        <span title="${escapeHtml(location || event.page_path || "")}">${escapeHtml(location || event.page_path || "-")}</span>
      </div>
      <em>${escapeHtml(kind)}</em>
    </div>
  `;
}

function artifactDetails(artifact) {
  if (!artifact.exists) return "not generated";
  const details = [];
  if (Number.isFinite(Number(artifact.size))) details.push(formatBytes(artifact.size));
  if (Number.isFinite(Number(artifact.rows))) details.push(`${formatNumber(artifact.rows)} rows`);
  if (artifact.age_hours !== undefined && artifact.age_hours !== null) details.push(formatAgeHours(artifact.age_hours));
  return details.length ? details.join(" · ") : "ready";
}

function renderOpsRunbook() {
  if (!els.opsRunbook) return;
  const health = state.overview?.data_health || {};
  const summary = state.reviewSummary || calculateReviewSummary();
  const artifacts = Array.isArray(state.artifacts?.artifacts) ? state.artifacts.artifacts : [];
  const jobRunning = Boolean(state.job?.running);
  const activeItems = Number(summary.active_items || 0);
  const readyItems = Number(summary.status_counts?.ready || 0);
  const unsizedItems = Number(summary.unsized_items || 0);
  const warnings = Array.isArray(summary.warnings) ? summary.warnings : [];
  const nextMode = nextActionMode(health.next_action);
  const resultReady = health.next_action === "none" && Number(health.ready_checks || 0) === Number(health.total_checks || 0);
  const marketLag = Number(health.market_session_lag);
  const marketAge = Number(health.market_age_days);
  const marketFresh = Number.isFinite(marketLag)
    ? marketLag <= 0
    : Number.isFinite(marketAge)
    ? marketAge <= 3
    : false;
  const reviewPlan = artifacts.find((artifact) => artifact.id === "tradingview_review_plan");
  const resultsCsv = artifacts.find((artifact) => artifact.id === "results_csv");
  const checklist = [
    {
      level: jobRunning ? "pending" : resultReady ? "ready" : "warning",
      title: "Pipeline",
      detail: jobRunning
        ? `${state.job.mode || "pipeline"} running`
        : resultReady
        ? `${formatNumber(health.candidate_count || 0)} candidates ready`
        : `${String(health.next_action || "pipeline").replaceAll("_", " ")} needed`,
      action: !jobRunning && nextMode ? "run-next" : "",
      actionLabel: nextMode ? `Run ${nextMode}` : "",
    },
    {
      level: marketFresh ? "ready" : "warning",
      title: "Market Tape",
      detail: formatMarketFreshness(health),
      action: marketFresh || jobRunning ? "" : "enrich",
      actionLabel: "Refresh",
    },
    {
      level: activeItems ? (readyItems ? "ready" : "pending") : "warning",
      title: "Review Queue",
      detail: activeItems ? `${readyItems} ready · ${activeItems} active` : "no active review items",
      action: "review",
      actionLabel: activeItems ? "Open" : "Queue",
    },
    {
      level: !activeItems ? "pending" : warnings.length ? "warning" : unsizedItems ? "warning" : "ready",
      title: "Risk Plan",
      detail: !activeItems
        ? "waiting for queue"
        : warnings.length
        ? `${warnings.length} guardrail warning(s)`
        : unsizedItems
        ? `${unsizedItems} unsized`
        : "sized inside guardrails",
      action: "review",
      actionLabel: "Review",
    },
    {
      level: reviewPlan?.exists ? "ready" : resultsCsv?.exists ? "pending" : "warning",
      title: "Outputs",
      detail: reviewPlan?.exists ? "TradingView plan ready" : resultsCsv?.exists ? "TV plan not generated" : "results missing",
      action: !jobRunning && resultsCsv?.exists && !reviewPlan?.exists ? "tv-export" : "snapshot",
      actionLabel: !jobRunning && resultsCsv?.exists && !reviewPlan?.exists ? "TV Export" : "Snapshot",
    },
    {
      level: state.analysis?.found ? "ready" : "pending",
      title: "Dossier",
      detail: state.analysis?.found ? `${state.analysis.ticker} analysis ready` : "analyze a ticker",
      action: state.analysis?.found ? "dossier" : "",
      actionLabel: state.analysis?.found ? "Save" : "",
    },
  ];

  const readyCount = checklist.filter((item) => item.level === "ready").length;
  els.opsRunbook.innerHTML = `
    <div class="ops-runbook-head">
      <b>Session Runbook</b>
      <span>${readyCount}/${checklist.length} ready</span>
    </div>
    ${checklist
      .map((item) => `
        <div class="ops-runbook-item ${escapeHtml(item.level)}">
          <i></i>
          <div>
            <b>${escapeHtml(item.title)}</b>
            <span>${escapeHtml(item.detail)}</span>
          </div>
          ${
            item.action
              ? `<button class="subtle" type="button" data-runbook-action="${escapeHtml(item.action)}">${escapeHtml(item.actionLabel)}</button>`
              : `<em>${escapeHtml(item.level)}</em>`
          }
        </div>
      `)
      .join("")}
  `;
}

async function startPipelineJob(mode, profile = state.profile) {
  const normalized = nextActionMode(mode) || mode;
  if (!normalized) return;
  const targetProfile = profile || state.profile;
  state.job = { status: "starting", running: true, mode: normalized, profile: targetProfile, log: [] };
  renderJobControls();
  renderProfileMatrix(state.overview?.profiles || []);
  try {
    state.job = await api("/api/jobs", {}, { method: "POST", body: { mode: normalized, profile: targetProfile } });
    await loadJobHistory();
    setAppStatus("online", "Job started");
    renderJobControls();
    renderProfileMatrix(state.overview?.profiles || []);
    pollJob();
  } catch (error) {
    setAppStatus("error", "Job failed", userMessage(error));
    state.job = { status: "failed", running: false, mode: normalized, profile: targetProfile, log: [error.message || "Unable to start job"] };
    renderJobControls();
    renderProfileMatrix(state.overview?.profiles || []);
  }
}

async function cancelPipelineJob() {
  if (!state.job?.running) return;
  setAppStatus("syncing", "Cancelling job");
  try {
    state.job = await api("/api/jobs/cancel", {}, { method: "POST", body: {} });
    await loadJobHistory();
    renderJobControls();
    if (state.job?.running) {
      pollJob();
    } else {
      await loadDashboard();
    }
  } catch (error) {
    setAppStatus("error", "Cancel failed", userMessage(error));
  }
}

function handleDiagnosticAction(action) {
  const normalized = String(action || "").replaceAll("_", "-");
  if (!normalized) return;
  if (normalized === "cleanup-workspace-temps") {
    cleanupWorkspaceTempFiles();
    return;
  }
  if (normalized === "repair-workspace-audit") {
    repairWorkspaceAuditStore();
    return;
  }
  if (normalized === "open-workspace-backups") {
    openWorkspaceBackupModal();
    return;
  }
  if (normalized === "configure-auth") {
    const authEnv = state.diagnostics?.deployment?.auth_env || "CANSLIM_DASHBOARD_AUTH";
    els.releaseReadinessPanel?.scrollIntoView({ behavior: "smooth", block: "start" });
    setAppStatus("online", "Auth setup", `Set ${authEnv} and restart with --require-auth`);
    return;
  }
  const mode = nextActionMode(normalized) || normalized;
  startPipelineJob(mode);
}

let jobTimer = null;
const reviewNoteTimers = new Map();
const reviewTagTimers = new Map();
const reviewPriceTimers = new Map();
const reviewExecutionTimers = new Map();

async function pollJob() {
  clearTimeout(jobTimer);
  await loadCurrentJob();
  await loadJobHistory();
  renderJobControls();
  if (state.job?.running) {
    jobTimer = setTimeout(pollJob, 2000);
    return;
  }
  await loadDashboard();
}

function nextActionMode(action) {
  const normalized = String(action || "").replaceAll("_", "-");
  const modes = {
    download: "download",
    parse: "parse",
    enrich: "enrich",
    "institutional-data": "enrich",
    screen: "screen",
    "profile-sweep": "profile-sweep",
    "screen-profiles": "profile-sweep",
    "profile-outputs": "profile-sweep",
  };
  return modes[normalized] || "";
}

async function analyzeTicker(ticker) {
  const value = String(ticker || "").trim().toUpperCase();
  if (!value) return;
  setAnalysisLoading(value);
  try {
    const result = await api("/api/analyze", { ticker: value, profile: state.profile });
    state.analysis = result;
    renderAnalysis();
  } catch (error) {
    setAppStatus("error", "Analysis failed", userMessage(error));
    setAnalysisError(value, error);
  }
}

function renderAnalysis() {
  const result = state.analysis || {};
  if (!result.found) {
    setAnalysisError(result.ticker || "-", new Error(result.error || "Ticker not found in local company list"));
    return;
  }

  els.analysisTicker.textContent = result.ticker || "-";
  els.analysisName.textContent = result.name || "Unknown";
  els.analysisScore.textContent = formatScore(result.canslim_score);
  els.analysisBand.textContent = result.score_band || "score";
  const brief = result.research_brief || makeResearchBrief(result);
  renderMetrics(result);
  renderTradePlan(brief);
  renderSetupBrief(brief);
  renderComponents(result.component_scores || makeComponents(result));
  renderReasons(result.pass_reasons || [], result.fail_reasons || []);
  drawPriceChart(result.price_history || [], result.ticker, brief.trade_plan || {});
  drawScoreDial(Number(result.canslim_score || 0), result.score_band || "");
  els.reviewAnalysisButton.disabled = false;
  els.analysisExportButton.disabled = false;
  renderOpsRunbook();
}

function renderMetrics(result) {
  const metrics = [
    ["Price", formatCurrency(result.current_price)],
    ["Market cap", formatMoney(result.market_cap)],
    ["EPS Q", formatPercent(result.quarterly_eps_growth)],
    ["Annual EPS", formatPercent(result.annual_eps_cagr)],
    ["Revenue", formatPercent(result.revenue_growth)],
    ["ROE", formatPercent(result.roe)],
  ];
  els.analysisMetrics.innerHTML = metrics
    .map(([label, value]) => `<div class="metric"><span>${label}</span><b>${value}</b></div>`)
    .join("");
}

function renderTradePlan(brief) {
  const plan = brief?.trade_plan || {};
  const action = brief?.action || "research";
  const sizing = calculatePositionSize(plan);
  const cells = [
    ["Action", renderActionLabel(action)],
    ["Pivot", formatCurrency(plan.pivot_price)],
    ["Buy zone", formatRange(plan.buy_zone_low, plan.buy_zone_high)],
    ["Stop", formatCurrency(plan.stop_loss_price)],
    ["Target", formatRange(plan.profit_target_low, plan.profit_target_high)],
    ["R/R", formatRiskReward(plan.risk_reward_low, plan.risk_reward_high)],
    ["Risk", formatCurrency(sizing.riskAmount)],
    ["Shares", formatShares(sizing.shares)],
  ];
  els.tradePlan.innerHTML = cells
    .map(([label, value]) => `<div class="trade-cell"><span>${label}</span><b>${value}</b></div>`)
    .join("");
}

function renderSetupBrief(brief) {
  const setup = brief?.setup || {};
  const score = brief?.score || {};
  const plan = brief?.trade_plan || {};
  const reasons = [
    ...(setup.reasons || []).slice(0, 3),
    ...(brief?.reasons?.watch || []).slice(0, 2),
  ];
  const strongest = score.strongest_components || [];
  els.setupBrief.innerHTML = `
    <div>
      <span>Setup</span>
      <b>${escapeHtml((setup.status || "unclassified").replaceAll("_", " "))}</b>
      <small>${escapeHtml(setup.type || "candidate")}</small>
    </div>
    <div>
      <span>Distance</span>
      <b>${formatStoredPercent(plan.pivot_distance_pct)}</b>
      <small>${plan.in_buy_zone ? "inside buy zone" : plan.extended_from_pivot ? "extended" : "watch levels"}</small>
    </div>
    <div>
      <span>Strength</span>
      <b>${escapeHtml(strongest[0] || "Mixed")}</b>
      <small>${escapeHtml(strongest.slice(1).join(" · ") || "review components")}</small>
    </div>
    <div class="setup-reasons">
      <span>Notes</span>
      <ul>${renderReasonItems(reasons.length ? reasons : ["No setup notes available"])}</ul>
    </div>
  `;
}

function renderComponents(components) {
  const labels = [
    ["c", "Current"],
    ["a", "Annual"],
    ["n", "New"],
    ["s", "Supply"],
    ["l", "Leader"],
    ["i", "Inst."],
    ["m", "Market"],
  ];
  els.componentScores.innerHTML = labels
    .map(([key, label]) => {
      const value = clamp(Number(components[key] ?? 0), 0, 100);
      return `
        <div class="component">
          <div class="component-top"><span>${label}</span><b>${Math.round(value)}</b></div>
          <meter class="component-meter" min="0" max="100" value="${escapeHtml(value)}" aria-label="${escapeHtml(`${label} score ${Math.round(value)}`)}"></meter>
        </div>
      `;
    })
    .join("");
}

function renderReasons(passReasons, failReasons) {
  els.passReasons.innerHTML = renderReasonItems(passReasons);
  els.failReasons.innerHTML = renderReasonItems(failReasons);
}

function renderReasonItems(items) {
  if (!items.length) return `<li class="loading">none</li>`;
  return items.slice(0, 8).map((item) => `<li>${escapeHtml(String(item))}</li>`).join("");
}

function currentScreenerViewPayload() {
  return {
    query: cleanScreenerQuery(els.candidateSearch.value),
    min_score: boundedNumber(els.minScore.value, 70, 0, 100),
    setup: normalizeScreenerSetup(els.setupFilter.value),
    sort_by: normalizeSortBy(state.sortBy),
    sort_dir: normalizeSortDir(state.sortDir),
  };
}

function renderScreenerViews() {
  const activeId = matchingScreenerViewId();
  els.screenerViewSelect.innerHTML = [
    `<option value="">Unsaved view</option>`,
    ...state.screenerViews.map((view) => `<option value="${escapeHtml(view.id)}">${escapeHtml(view.name)}</option>`),
  ].join("");
  els.screenerViewSelect.value = activeId;
  if (pendingScreenerViewDeleteId && pendingScreenerViewDeleteId !== activeId) {
    pendingScreenerViewDeleteId = "";
  }
  renderDeleteScreenerViewButton(activeId);
}

function renderDeleteScreenerViewButton(activeId = matchingScreenerViewId()) {
  const pending = Boolean(activeId && pendingScreenerViewDeleteId === activeId);
  els.deleteScreenerViewButton.disabled = els.screenerViewSelect.disabled || !activeId;
  els.deleteScreenerViewButton.classList.toggle("danger", pending);
  els.deleteScreenerViewButton.textContent = pending ? "!" : "×";
  els.deleteScreenerViewButton.title = pending ? "Click again to delete screener view" : "Delete selected screener view";
  els.deleteScreenerViewButton.setAttribute(
    "aria-label",
    pending ? "Confirm delete selected screener view" : "Delete selected screener view",
  );
}

function matchingScreenerViewId() {
  const payload = currentScreenerViewPayload();
  const match = state.screenerViews.find((view) => screenerViewMatches(view, payload));
  return match?.id || "";
}

function screenerViewMatches(view, payload) {
  return (
    cleanScreenerQuery(view.query) === payload.query &&
    Number(view.min_score) === payload.min_score &&
    normalizeScreenerSetup(view.setup) === payload.setup &&
    normalizeSortBy(view.sort_by) === payload.sort_by &&
    normalizeSortDir(view.sort_dir) === payload.sort_dir
  );
}

function screenerViewNameSuggestion() {
  const payload = currentScreenerViewPayload();
  const parts = [];
  if (payload.setup) {
    parts.push(els.setupFilter.selectedOptions?.[0]?.textContent?.trim() || payload.setup);
  }
  parts.push(`Score ${formatPreferenceNumber(payload.min_score, 1)}+`);
  if (payload.query) parts.push(payload.query);
  return parts.join(" / ").slice(0, 40);
}

async function saveScreenerView() {
  const selected = state.screenerViews.find((view) => view.id === els.screenerViewSelect.value);
  const matching = state.screenerViews.find((view) => screenerViewMatches(view, currentScreenerViewPayload()));
  const existing = selected || matching;
  const rawName = await requestViewName({
    mode: "Screener View",
    title: existing ? "Update screener view" : "Save screener view",
    summary: "Search, score, setup, and sort",
    initialValue: existing?.name || screenerViewNameSuggestion(),
  });
  if (rawName === null) return;
  const name = cleanScreenerViewName(rawName);
  if (!name) {
    setAppStatus("error", "View needs name");
    return;
  }
  const sameName = state.screenerViews.find((view) => view.name.toLowerCase() === name.toLowerCase());
  const target = existing || sameName;
  if (!target && state.screenerViews.length >= SCREENER_VIEW_LIMIT) {
    setAppStatus("error", "View limit reached");
    return;
  }
  const view = {
    id: target?.id || screenerViewId(name),
    name,
    ...currentScreenerViewPayload(),
  };
  state.screenerViews = target
    ? state.screenerViews.map((item) => (item.id === target.id ? view : item))
    : [view, ...state.screenerViews];
  renderScreenerViews();
  els.screenerViewSelect.value = view.id;
  await saveWorkspacePreferences();
  renderScreenerViews();
  setAppStatus("online", "View saved");
}

async function applyScreenerView(viewId) {
  const view = state.screenerViews.find((item) => item.id === viewId);
  if (!view) {
    renderScreenerViews();
    return;
  }
  els.candidateSearch.value = view.query;
  els.minScore.value = formatPreferenceNumber(view.min_score, 1);
  els.setupFilter.value = view.setup;
  state.sortBy = view.sort_by;
  state.sortDir = view.sort_dir;
  renderSortButtons();
  renderScreenerViews();
  saveWorkspacePreferencesDebounced();
  await refreshScreenerData();
}

async function deleteScreenerView() {
  const viewId = els.screenerViewSelect.value;
  const view = state.screenerViews.find((item) => item.id === viewId);
  if (!view) return;
  if (pendingScreenerViewDeleteId !== viewId) {
    pendingScreenerViewDeleteId = viewId;
    renderScreenerViews();
    setAppStatus("syncing", "Confirm delete", `Click again to delete ${view.name}`);
    return;
  }
  pendingScreenerViewDeleteId = "";
  state.screenerViews = state.screenerViews.filter((item) => item.id !== viewId);
  renderScreenerViews();
  await saveWorkspacePreferences();
  setAppStatus("online", "View deleted");
}

function renderScreener() {
  const payload = state.screener;
  if (!payload) return;
  state.sortBy = payload.sort?.by || state.sortBy;
  state.sortDir = payload.sort?.dir || state.sortDir;
  pruneCandidateCompareSelection(payload.candidates || []);
  renderSortButtons();
  renderScreenerViews();
  renderCandidateStats(payload.stats || {});
  renderCandidateCompare();
  const rows = payload.candidates || [];
  els.exportScreenerButton.disabled = !rows.length;
  els.bulkReviewButton.disabled = !rows.length;
  if (!rows.length) {
    els.candidateRows.innerHTML = `<tr><td colspan="11" class="loading">${escapeHtml(payload.message || "No candidates")}</td></tr>`;
    return;
  }
  els.candidateRows.innerHTML = rows
    .map((row) => {
      const scoreClass = Number(row.canslim_score || 0) >= 85 ? "up" : Number(row.canslim_score || 0) >= 70 ? "flat" : "down";
      const queued = isQueued(row.ticker);
      const compared = state.selectedCompareTickers.has(String(row.ticker || "").toUpperCase());
      return `
        <tr>
          <td><button class="compare-button ${compared ? "active" : ""}" data-compare="${escapeHtml(row.ticker)}" aria-label="${compared ? "Remove from comparison" : "Compare candidate"}" aria-pressed="${compared ? "true" : "false"}" title="${compared ? "In comparison" : "Compare"}">${compared ? "◆" : "◇"}</button></td>
          <td><button class="ticker-button" data-ticker="${escapeHtml(row.ticker)}">${escapeHtml(row.ticker || "-")}</button></td>
          <td class="company-cell" title="${escapeHtml(row.name || "")}">${escapeHtml(row.name || "-")}</td>
          <td class="${scoreClass}"><b>${formatScore(row.canslim_score)}</b></td>
          <td><span class="badge">${escapeHtml(row.setup_status || "-")}</span></td>
          <td>${formatScore(row.rs_rating)}</td>
          <td>${formatPercent(row.quarterly_eps_growth)}</td>
          <td>${formatPercent(row.revenue_growth)}</td>
          <td>${formatStoredPercent(row.pivot_distance_pct)}</td>
          <td>${formatMoney(row.market_cap)}</td>
          <td><button class="queue-button ${queued ? "active" : ""}" data-add-review="${escapeHtml(row.ticker)}" aria-label="${queued ? "Update review item" : "Add to review queue"}" title="${queued ? "In review queue" : "Add to review queue"}">${queued ? "✓" : "+"}</button></td>
        </tr>
      `;
    })
    .join("");
}

async function refreshScreenerData() {
  try {
    state.screener = await loadScreenerData();
    renderScreener();
  } catch (error) {
    setAppStatus("error", "Screener error", userMessage(error));
    els.candidateRows.innerHTML = `<tr><td colspan="10" class="loading">${escapeHtml(userMessage(error))}</td></tr>`;
  }
}

function renderSortButtons() {
  document.querySelectorAll("[data-sort]").forEach((button) => {
    const active = button.dataset.sort === state.sortBy;
    button.classList.toggle("active", active);
    button.dataset.dir = active ? state.sortDir : "";
    button.setAttribute(
      "aria-sort",
      active ? (state.sortDir === "asc" ? "ascending" : "descending") : "none",
    );
  });
}

function renderCandidateStats(stats) {
  const cells = [
    ["Candidates", stats.count ?? 0],
    ["Avg score", formatScore(stats.avg_score)],
    ["Top score", formatScore(stats.top_score)],
    ["Near pivot", stats.near_pivot ?? 0],
    ["Base", stats.forming_base ?? 0],
    ["Extended", stats.extended ?? 0],
  ];
  els.candidateStats.innerHTML = cells
    .map(([label, value]) => `<div class="stat"><span>${label}</span><b>${value}</b></div>`)
    .join("");
}

function pruneCandidateCompareSelection(rows) {
  const available = new Set(rows.map((row) => String(row.ticker || "").toUpperCase()).filter(Boolean));
  [...state.selectedCompareTickers].forEach((ticker) => {
    if (!available.has(ticker)) state.selectedCompareTickers.delete(ticker);
  });
}

function toggleCandidateCompare(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  if (!normalized) return;
  if (state.selectedCompareTickers.has(normalized)) {
    state.selectedCompareTickers.delete(normalized);
  } else if (state.selectedCompareTickers.size < COMPARE_LIMIT) {
    state.selectedCompareTickers.add(normalized);
  } else {
    setAppStatus("error", `Compare max ${COMPARE_LIMIT}`);
  }
  renderScreener();
}

function selectedCompareRows() {
  const candidates = state.screener?.candidates || [];
  return [...state.selectedCompareTickers]
    .map((ticker) => candidates.find((row) => String(row.ticker || "").toUpperCase() === ticker))
    .filter(Boolean);
}

function renderCandidateCompare() {
  const rows = selectedCompareRows();
  els.candidateCompare.hidden = rows.length === 0;
  els.exportCompareButton.disabled = rows.length === 0;
  els.compareSummary.textContent = `${rows.length}/${COMPARE_LIMIT} selected`;
  if (!rows.length) {
    els.compareGrid.innerHTML = "";
    return;
  }
  els.compareGrid.innerHTML = rows.map(renderCompareCard).join("");
}

function renderCompareCard(row) {
  const brief = row.research_brief || makeResearchBrief(row);
  const plan = brief.trade_plan || {};
  const action = brief.action || "research";
  const passCount = Array.isArray(row.pass_reasons) ? row.pass_reasons.length : 0;
  const watchCount = Array.isArray(row.fail_reasons) ? row.fail_reasons.length : 0;
  return `
    <article class="compare-card">
      <div class="compare-card-head">
        <button class="text-button" type="button" data-ticker="${escapeHtml(row.ticker || "")}">${escapeHtml(row.ticker || "-")}</button>
        <button class="icon-button subtle" type="button" data-compare="${escapeHtml(row.ticker || "")}" aria-label="Remove ${escapeHtml(row.ticker || "")} from comparison" title="Remove from comparison">×</button>
      </div>
      <b>${escapeHtml(row.name || "Unknown")}</b>
      <span>${escapeHtml(row.sector || row.industry || "Unclassified")}</span>
      <div class="compare-score">
        <strong>${escapeHtml(formatScore(row.canslim_score))}</strong>
        <em>${escapeHtml(renderActionLabelText(action))}</em>
      </div>
      <dl>
        ${compareMetric("Setup", row.setup_status || brief.setup?.status)}
        ${compareMetric("RS", formatScore(row.rs_rating))}
        ${compareMetric("EPS Q", formatPercent(row.quarterly_eps_growth))}
        ${compareMetric("Revenue", formatPercent(row.revenue_growth))}
        ${compareMetric("Pivot", formatStoredPercent(plan.pivot_distance_pct ?? row.pivot_distance_pct))}
        ${compareMetric("Buy zone", formatRange(plan.buy_zone_low ?? row.buy_zone_low, plan.buy_zone_high ?? row.buy_zone_high))}
        ${compareMetric("Stop", formatCurrency(plan.stop_loss_price ?? row.stop_loss_price))}
        ${compareMetric("R/R", formatRiskReward(plan.risk_reward_low, plan.risk_reward_high))}
        ${compareMetric("Reasons", `${passCount}/${watchCount}`)}
      </dl>
    </article>
  `;
}

function compareMetric(label, value) {
  return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value || "-")}</dd></div>`;
}

function clearCandidateCompare() {
  state.selectedCompareTickers.clear();
  renderScreener();
}

function exportCandidateCompare() {
  const tickers = [...state.selectedCompareTickers];
  if (!tickers.length) return;
  const url = new URL("/api/compare", window.location.origin);
  url.searchParams.set("profile", state.profile);
  url.searchParams.set("tickers", tickers.join(","));
  const link = document.createElement("a");
  link.href = url.toString();
  link.download = `canslim-compare-${state.profile}-${tickers.join("-")}.json`;
  document.body.append(link);
  link.click();
  link.remove();
}

function setAnalysisLoading(ticker) {
  els.analysisTicker.textContent = ticker;
  els.analysisName.textContent = "loading";
  els.analysisScore.textContent = "-";
  els.analysisBand.textContent = "score";
  els.analysisMetrics.innerHTML = `<div class="metric"><span>Status</span><b>Loading</b></div>`;
  els.tradePlan.innerHTML = "";
  els.setupBrief.innerHTML = "";
  els.componentScores.innerHTML = "";
  els.passReasons.innerHTML = "";
  els.failReasons.innerHTML = "";
  els.reviewAnalysisButton.disabled = true;
  els.analysisExportButton.disabled = true;
  renderOpsRunbook();
  drawPriceChart([], ticker);
  drawScoreDial(0, "");
}

function setAnalysisError(ticker, error) {
  const message = userMessage(error);
  els.analysisTicker.textContent = ticker;
  els.analysisName.textContent = message || "analysis failed";
  els.analysisScore.textContent = "-";
  els.analysisBand.textContent = "error";
  els.analysisMetrics.innerHTML = `<div class="metric"><span>Status</span><b>Unavailable</b></div>`;
  els.tradePlan.innerHTML = "";
  els.setupBrief.innerHTML = "";
  els.componentScores.innerHTML = "";
  els.passReasons.innerHTML = "";
  els.failReasons.innerHTML = `<li>${escapeHtml(message || "analysis failed")}</li>`;
  els.reviewAnalysisButton.disabled = true;
  els.analysisExportButton.disabled = true;
  renderOpsRunbook();
  drawPriceChart([], ticker);
  drawScoreDial(0, "");
}

function renderError(error) {
  els.newsList.innerHTML = `<div class="news-item"><b>Dashboard error</b><span>${escapeHtml(userMessage(error))}</span></div>`;
}

function setLoading(isLoading) {
  els.refreshButton.disabled = isLoading;
  els.workspaceImportButton.disabled = isLoading;
  els.workspaceExportButton.disabled = isLoading;
  els.workspaceBackupButton.disabled = isLoading;
  if (els.workspaceAuditExportButton) {
    els.workspaceAuditExportButton.disabled = isLoading;
  }
  els.sessionReportButton.disabled = isLoading;
  els.supportBundleButton.disabled = isLoading;
  if (els.profileSweepButton) {
    els.profileSweepButton.disabled = isLoading || Boolean(state.job?.running);
  }
  els.sessionJournalDate.disabled = isLoading;
  els.journalMarketThesis.disabled = isLoading;
  els.journalWatchlistFocus.disabled = isLoading;
  els.journalRiskNotes.disabled = isLoading;
  els.journalPostReview.disabled = isLoading;
  els.saveJournalButton.disabled = isLoading;
  els.screenerViewSelect.disabled = isLoading;
  els.saveScreenerViewButton.disabled = isLoading;
  els.deleteScreenerViewButton.disabled = isLoading || !els.screenerViewSelect.value;
  els.reviewViewSelect.disabled = isLoading;
  els.saveReviewViewButton.disabled = isLoading;
  els.deleteReviewViewButton.disabled = isLoading || !els.reviewViewSelect.value;
  els.exportScreenerButton.disabled = isLoading || !(state.screener?.candidates || []).length;
  els.refreshButton.textContent = isLoading ? "…" : "↻";
  if (!isLoading) {
    renderScreenerViews();
    renderReviewViews();
  }
}

function setAppStatus(kind, label, detail = "") {
  const normalized = ["online", "syncing", "offline", "error"].includes(kind) ? kind : "syncing";
  els.appStatus.className = `app-status ${normalized}`;
  els.appStatusText.textContent = label;
  els.appStatus.title = detail ? `${label}: ${detail}` : label;
}

function renderRuntimeBadge() {
  if (!els.runtimeBadge) return;
  const runtime = state.runtime || {};
  const app = runtime.app || {};
  const version = String(app.version || "").trim();
  els.runtimeBadge.textContent = version ? `v${version}` : "v-";
  els.runtimeBadge.title = runtimeStatusDetail() || "Runtime metadata unavailable";
}

function runtimeStatusDetail() {
  const runtime = state.runtime || {};
  const app = runtime.app || {};
  const source = runtime.source || {};
  const parts = [];
  if (app.name || app.version) {
    parts.push(`${app.name || "Dashboard"}${app.version ? ` v${app.version}` : ""}`);
  }
  if (source.git_commit) {
    parts.push(`git ${source.git_commit}`);
  }
  if (source.git_branch) {
    parts.push(source.git_branch);
  }
  if (source.git_dirty || source.git_untracked) {
    parts.push("dirty workspace");
  }
  if (runtime.run_id) {
    parts.push(`run ${runtime.run_id}`);
  }
  return parts.join(" · ");
}

function recordSyncIssue(label, error) {
  const detail = userMessage(error);
  state.syncIssues.push(`${label}: ${detail}`);
  setAppStatus("offline", label, detail);
}

function renderReviewQueue() {
  const totalItems = state.reviewQueue.length;
  const items = visibleReviewItems();
  const filtersActive = reviewFiltersActive();
  pruneReviewSelection(items);
  renderReviewSummary(calculateReviewSummary());
  renderReviewActivity();
  renderReviewImportReport();
  renderReviewBulkControls(items);
  renderReviewTagFilterOptions();
  renderReviewFilterControls(filtersActive);
  renderReviewViews();
  els.reviewCount.textContent = filtersActive ? `${items.length}/${totalItems}` : totalItems;
  els.reviewExportFormat.disabled = !totalItems;
  els.exportReviewButton.disabled = !totalItems;
  renderClearReviewButton(totalItems);
  if (!items.length) {
    els.reviewList.innerHTML = filtersActive && totalItems
      ? `
        <div class="empty-state review-empty-state">
          <span>No items match filter</span>
          <button class="subtle" type="button" data-clear-review-filters>Clear filters</button>
        </div>
      `
      : `<div class="empty-state">No tickers selected</div>`;
    return;
  }
  els.reviewList.innerHTML = items
    .map((item) => {
      const entry = numericValue(item.buy_zone_low) ?? numericValue(item.pivot_price);
      const entryLabel = !isBlank(item.buy_zone_low) && !isBlank(item.buy_zone_high)
        ? `Buy ${formatRange(item.buy_zone_low, item.buy_zone_high)}`
        : `Entry ${formatCurrency(entry)}`;
      const status = item.decision_status || "watch";
      const priority = normalizeReviewPriority(item.review_priority);
      const sizing = calculatePositionSize(item);
      const checked = state.selectedReviewTickers.has(item.ticker) ? "checked" : "";
      const readinessBlockers = readinessBlockersForItem(item, sizing);
      const readyBlocked = readinessBlockers.length > 0;
      return `
        <div class="review-item status-${escapeHtml(status)} ${readyBlocked ? "readiness-blocked" : ""}">
          <label class="review-select">
            <input type="checkbox" data-review-select="${escapeHtml(item.ticker)}" aria-label="Select ${escapeHtml(item.ticker)}" ${checked} />
            <span></span>
          </label>
          <div class="review-main">
            <button class="text-button" data-ticker="${escapeHtml(item.ticker)}">${escapeHtml(item.ticker)}</button>
            <span title="${escapeHtml(item.name || "")}">${escapeHtml(item.name || "Unknown")}</span>
          </div>
          <div class="review-meta">
            <b>${formatScore(item.canslim_score)}</b>
            <span class="review-priority-badge priority-${escapeHtml(priority)}">${escapeHtml(reviewPriorityLabel(priority))}</span>
            <span>${escapeHtml(item.setup_status || "unclassified")}</span>
            <span>${formatStoredPercent(item.pivot_distance_pct)}</span>
          </div>
          <div class="review-levels">
            <span data-review-entry="${escapeHtml(item.ticker)}">${escapeHtml(entryLabel)}</span>
            <span data-review-stop-display="${escapeHtml(item.ticker)}">Stop ${formatCurrency(item.stop_loss_price)}</span>
            <span data-review-sizing="${escapeHtml(item.ticker)}">Shares ${formatShares(sizing.shares)}</span>
            <span class="review-readiness-badge" data-review-readiness="${escapeHtml(item.ticker)}" ${readyBlocked ? "" : "hidden"}>${escapeHtml(readinessBlockerSummary(readinessBlockers))}</span>
          </div>
          <div class="review-price-edits">
            <label>
              <span>Entry</span>
              <input type="number" min="0" step="0.01" inputmode="decimal" value="${escapeHtml(formatInputNumber(entry))}" data-review-price="${escapeHtml(item.ticker)}" data-review-field="buy_zone_low" aria-label="Entry price for ${escapeHtml(item.ticker)}" />
            </label>
            <label>
              <span>Stop</span>
              <input type="number" min="0" step="0.01" inputmode="decimal" value="${escapeHtml(formatInputNumber(item.stop_loss_price))}" data-review-price="${escapeHtml(item.ticker)}" data-review-field="stop_loss_price" aria-label="Stop price for ${escapeHtml(item.ticker)}" />
            </label>
          </div>
          ${status === "bought" || status === "sold" ? renderExecutionFields(item) : ""}
          ${status === "sold" ? renderExitFields(item) : ""}
          ${renderReviewChecklist(item)}
          <div class="review-decision">
            <select data-review-status="${escapeHtml(item.ticker)}" aria-label="Decision status for ${escapeHtml(item.ticker)}">
              ${renderStatusOptions(status)}
            </select>
            <select data-review-priority="${escapeHtml(item.ticker)}" aria-label="Review priority for ${escapeHtml(item.ticker)}">
              ${renderPriorityOptions(priority)}
            </select>
            <input data-review-tags="${escapeHtml(item.ticker)}" maxlength="160" placeholder="Tags" value="${escapeHtml(reviewTagsText(item.review_tags))}" aria-label="Review tags for ${escapeHtml(item.ticker)}" />
            <textarea data-review-note="${escapeHtml(item.ticker)}" rows="2" maxlength="800" placeholder="Decision note">${escapeHtml(item.review_note || "")}</textarea>
          </div>
          <button class="remove-button" data-remove-review="${escapeHtml(item.ticker)}" aria-label="Remove ${escapeHtml(item.ticker)} from review">×</button>
        </div>
      `;
    })
    .join("");
  renderReviewBulkControls(items);
}

function renderReviewImportReport(report = state.reviewImportReport) {
  if (!report) {
    els.reviewImportReport.hidden = true;
    els.reviewImportReport.innerHTML = "";
    return;
  }
  const requestedCount = Array.isArray(report.requested) ? report.requested.length : 0;
  const failures = Array.isArray(report.failures) ? report.failures : [];
  const importedCount = Number(report.imported_count) || 0;
  const truncatedCount = Number(report.truncated_count) || 0;
  els.reviewImportReport.hidden = false;
  els.reviewImportReport.classList.toggle("has-failures", failures.length > 0 || truncatedCount > 0);
  els.reviewImportReport.innerHTML = `
    <div class="import-report-head">
      <b>${escapeHtml(importedCount)} imported</b>
      <span>${escapeHtml(formatImportScope(requestedCount, failures.length, truncatedCount))}</span>
    </div>
    ${failures.length ? `
      <div class="import-failures">
        ${failures.slice(0, 6).map((failure) => `
          <span><b>${escapeHtml(failure.ticker || "-")}</b> ${escapeHtml(failure.error || "Import failed")}</span>
        `).join("")}
      </div>
    ` : ""}
  `;
}

function formatImportScope(requestedCount, failureCount, truncatedCount) {
  const parts = [`${requestedCount} requested`];
  if (failureCount) parts.push(`${failureCount} failed`);
  if (truncatedCount) parts.push(`${truncatedCount} over limit`);
  return parts.join(" · ");
}

function visibleReviewItems() {
  return sortedReviewItems(filteredReviewItems(state.reviewQueue));
}

function pruneReviewSelection(visibleItems = null) {
  const validTickers = new Set(state.reviewQueue.map((item) => item.ticker));
  const visibleTickers = visibleItems && reviewFiltersActive()
    ? new Set(visibleItems.map((item) => item.ticker))
    : null;
  [...state.selectedReviewTickers].forEach((ticker) => {
    if (!validTickers.has(ticker) || (visibleTickers && !visibleTickers.has(ticker))) {
      state.selectedReviewTickers.delete(ticker);
    }
  });
}

function renderReviewBulkControls(visibleItems = visibleReviewItems()) {
  pruneReviewSelection(visibleItems);
  const selectedCount = selectedReviewTickers().length;
  const visibleTickers = visibleItems.map((item) => item.ticker);
  const visibleSelected = visibleTickers.filter((ticker) => state.selectedReviewTickers.has(ticker)).length;
  const hasVisibleItems = visibleTickers.length > 0;
  const hasSelection = selectedCount > 0;
  const hasBulkTags = parseReviewTags(els.reviewBulkTags.value).length > 0;
  els.reviewBulkBar.classList.toggle("has-selection", hasSelection);
  els.reviewSelectedCount.textContent = `${selectedCount} selected`;
  els.reviewBulkApply.disabled = !hasSelection;
  els.reviewBulkPriorityApply.disabled = !hasSelection;
  els.reviewBulkTagAdd.disabled = !hasSelection || !hasBulkTags;
  els.reviewBulkTagReplace.disabled = !hasSelection || !hasBulkTags;
  els.reviewBulkExport.disabled = !hasSelection;
  els.reviewBulkRemove.disabled = !hasSelection;
  els.reviewBulkStatus.disabled = !hasSelection;
  els.reviewBulkPriority.disabled = !hasSelection;
  els.reviewBulkTags.disabled = !hasSelection;
  els.reviewSelectVisible.disabled = !hasVisibleItems;
  els.reviewSelectVisible.checked = hasVisibleItems && visibleSelected === visibleTickers.length;
  els.reviewSelectVisible.indeterminate = visibleSelected > 0 && visibleSelected < visibleTickers.length;
}

function renderReviewFilterControls(filtersActive = reviewFiltersActive()) {
  els.reviewSearchInput.classList.toggle("is-active", Boolean(state.reviewQuery));
  els.reviewStatusFilter.classList.toggle("is-active", Boolean(state.reviewStatus));
  els.reviewPriorityFilter.classList.toggle("is-active", Boolean(state.reviewPriority));
  els.reviewTagFilter.classList.toggle("is-active", Boolean(state.reviewTag));
  els.reviewClearFiltersButton.hidden = !filtersActive;
  els.reviewClearFiltersButton.disabled = !filtersActive;
}

function renderReviewTagFilterOptions() {
  const tags = availableReviewTags();
  const selected = normalizeReviewTag(state.reviewTag);
  const options = [`<option value="">All tags</option>`];
  if (selected && !tags.includes(selected)) {
    options.push(`<option value="${escapeHtml(selected)}">${escapeHtml(selected)}</option>`);
  }
  options.push(...tags.map((tag) => `<option value="${escapeHtml(tag)}">${escapeHtml(tag)}</option>`));
  els.reviewTagFilter.innerHTML = options.join("");
  els.reviewTagFilter.value = selected;
}

function renderReviewViews() {
  const activeId = matchingReviewViewId();
  els.reviewViewSelect.innerHTML = [
    `<option value="">Unsaved queue</option>`,
    ...state.reviewViews.map((view) => `<option value="${escapeHtml(view.id)}">${escapeHtml(view.name)}</option>`),
  ].join("");
  els.reviewViewSelect.value = activeId;
  if (pendingReviewViewDeleteId && pendingReviewViewDeleteId !== activeId) {
    pendingReviewViewDeleteId = "";
  }
  renderDeleteReviewViewButton(activeId);
}

function renderDeleteReviewViewButton(activeId = matchingReviewViewId()) {
  const pending = Boolean(activeId && pendingReviewViewDeleteId === activeId);
  els.deleteReviewViewButton.disabled = els.reviewViewSelect.disabled || !activeId;
  els.deleteReviewViewButton.classList.toggle("danger", pending);
  els.deleteReviewViewButton.textContent = pending ? "!" : "×";
  els.deleteReviewViewButton.title = pending ? "Click again to delete review view" : "Delete selected review view";
  els.deleteReviewViewButton.setAttribute(
    "aria-label",
    pending ? "Confirm delete selected review view" : "Delete selected review view",
  );
}

function currentReviewViewPayload() {
  return {
    query: cleanReviewQuery(state.reviewQuery),
    sort_by: normalizeReviewSortBy(state.reviewSortBy),
    sort_dir: normalizeSortDir(state.reviewSortDir),
    status: normalizeReviewStatus(state.reviewStatus),
    priority: normalizeReviewPriorityFilter(state.reviewPriority),
    tag: normalizeReviewTag(state.reviewTag),
  };
}

function matchingReviewViewId() {
  const payload = currentReviewViewPayload();
  const match = state.reviewViews.find((view) => reviewViewMatches(view, payload));
  return match?.id || "";
}

function reviewViewMatches(view, payload) {
  return (
    cleanReviewQuery(view.query) === payload.query &&
    normalizeReviewSortBy(view.sort_by) === payload.sort_by &&
    normalizeSortDir(view.sort_dir) === payload.sort_dir &&
    normalizeReviewStatus(view.status) === payload.status &&
    normalizeReviewPriorityFilter(view.priority) === payload.priority &&
    normalizeReviewTag(view.tag) === payload.tag
  );
}

function reviewViewNameSuggestion() {
  const payload = currentReviewViewPayload();
  const parts = [];
  if (payload.status) parts.push(reviewStatusLabel(payload.status));
  if (payload.priority) parts.push(reviewPriorityLabel(payload.priority));
  if (payload.tag) parts.push(`#${payload.tag}`);
  if (payload.query) parts.push(payload.query);
  if (!parts.length) parts.push("All queue");
  return parts.join(" / ").slice(0, 40);
}

async function saveReviewView() {
  const selected = state.reviewViews.find((view) => view.id === els.reviewViewSelect.value);
  const matching = state.reviewViews.find((view) => reviewViewMatches(view, currentReviewViewPayload()));
  const existing = selected || matching;
  const rawName = await requestViewName({
    mode: "Review View",
    title: existing ? "Update review view" : "Save review view",
    summary: "Queue filters, sort, priority, and tags",
    initialValue: existing?.name || reviewViewNameSuggestion(),
  });
  if (rawName === null) return;
  const name = cleanReviewViewName(rawName);
  if (!name) {
    setAppStatus("error", "Review view needs name");
    return;
  }
  const sameName = state.reviewViews.find((view) => view.name.toLowerCase() === name.toLowerCase());
  const target = existing || sameName;
  if (!target && state.reviewViews.length >= REVIEW_VIEW_LIMIT) {
    setAppStatus("error", "Review view limit reached");
    return;
  }
  const view = {
    id: target?.id || reviewViewId(name),
    name,
    ...currentReviewViewPayload(),
  };
  state.reviewViews = target
    ? state.reviewViews.map((item) => (item.id === target.id ? view : item))
    : [view, ...state.reviewViews];
  renderReviewViews();
  els.reviewViewSelect.value = view.id;
  await saveWorkspacePreferences();
  renderReviewViews();
  setAppStatus("online", "Review view saved");
}

async function applyReviewView(viewId) {
  const view = state.reviewViews.find((item) => item.id === viewId);
  if (!view) {
    renderReviewViews();
    return;
  }
  state.reviewQuery = cleanReviewQuery(view.query);
  state.reviewSortBy = normalizeReviewSortBy(view.sort_by);
  state.reviewSortDir = normalizeSortDir(view.sort_dir);
  state.reviewStatus = normalizeReviewStatus(view.status);
  state.reviewPriority = normalizeReviewPriorityFilter(view.priority);
  state.reviewTag = normalizeReviewTag(view.tag);
  els.reviewSearchInput.value = state.reviewQuery;
  els.reviewSortSelect.value = state.reviewSortBy;
  els.reviewStatusFilter.value = state.reviewStatus;
  els.reviewPriorityFilter.value = state.reviewPriority;
  els.reviewTagFilter.value = state.reviewTag;
  renderReviewSortDirection();
  renderReviewQueue();
  saveWorkspacePreferencesDebounced();
  setAppStatus("online", "Review view applied");
}

async function deleteReviewView() {
  const viewId = els.reviewViewSelect.value;
  const view = state.reviewViews.find((item) => item.id === viewId);
  if (!view) return;
  if (pendingReviewViewDeleteId !== viewId) {
    pendingReviewViewDeleteId = viewId;
    renderReviewViews();
    setAppStatus("syncing", "Confirm delete", `Click again to delete ${view.name}`);
    return;
  }
  pendingReviewViewDeleteId = "";
  state.reviewViews = state.reviewViews.filter((item) => item.id !== viewId);
  renderReviewViews();
  await saveWorkspacePreferences();
  setAppStatus("online", "Review view deleted");
}

function availableReviewTags() {
  return [...new Set(state.reviewQueue.flatMap((item) => parseReviewTags(item.review_tags)))].sort((left, right) =>
    left.localeCompare(right),
  );
}

function renderReviewChecklist(item) {
  const checks = normalizedReviewChecks(item.review_checks);
  const progress = reviewChecklistProgress(checks);
  const status = normalizeReviewStatus(item.decision_status) || "watch";
  const readyChecklistBlocked = status === "ready" && !progress.done;
  return `
    <div class="review-checklist" data-review-checklist="${escapeHtml(item.ticker)}">
      <div class="checklist-head" data-review-check-head="${escapeHtml(item.ticker)}">
        <span>Checklist</span>
        <div>
          <em class="checklist-blocker" data-review-check-blocker="${escapeHtml(item.ticker)}" ${readyChecklistBlocked ? "" : "hidden"}>Ready blocked</em>
          <b class="${progress.done ? "complete" : readyChecklistBlocked ? "blocked" : ""}" data-review-check-progress="${escapeHtml(item.ticker)}">${escapeHtml(progress.label)}</b>
        </div>
      </div>
      <div class="checklist-options">
        ${REVIEW_CHECK_OPTIONS.map(([key, label]) => `
          <label class="${checks[key] ? "checked" : ""}">
            <input type="checkbox" data-review-check="${escapeHtml(item.ticker)}" data-review-check-key="${escapeHtml(key)}" ${checks[key] ? "checked" : ""} />
            <span>${escapeHtml(label)}</span>
          </label>
        `).join("")}
      </div>
    </div>
  `;
}

function renderExecutionFields(item) {
  const execution = calculateExecution(item);
  const monitor = calculatePositionMonitor(item);
  const status = normalizeReviewStatus(item.decision_status) || "watch";
  return `
    <div class="review-execution" data-review-execution-panel="${escapeHtml(item.ticker)}">
      <label>
        <span>Fill price</span>
        <input type="number" min="0" step="0.01" inputmode="decimal" value="${escapeHtml(formatInputNumber(item.execution_price))}" data-review-execution="${escapeHtml(item.ticker)}" data-review-execution-field="execution_price" aria-label="Execution price for ${escapeHtml(item.ticker)}" />
      </label>
      <label>
        <span>Shares</span>
        <input type="number" min="0" step="1" inputmode="numeric" value="${escapeHtml(formatInputShares(item.execution_shares))}" data-review-execution="${escapeHtml(item.ticker)}" data-review-execution-field="execution_shares" aria-label="Execution shares for ${escapeHtml(item.ticker)}" />
      </label>
      <label>
        <span>Date</span>
        <input type="date" value="${escapeHtml(formatDateInput(item.executed_at))}" data-review-execution="${escapeHtml(item.ticker)}" data-review-execution-field="executed_at" aria-label="Execution date for ${escapeHtml(item.ticker)}" />
      </label>
      ${status === "bought" ? `
        <label>
          <span>Last</span>
          <input type="number" min="0" step="0.01" inputmode="decimal" value="${escapeHtml(formatInputNumber(item.current_price))}" data-review-execution="${escapeHtml(item.ticker)}" data-review-execution-field="current_price" aria-label="Last price for ${escapeHtml(item.ticker)}" />
        </label>
      ` : ""}
      <b data-review-execution-value="${escapeHtml(item.ticker)}">${escapeHtml(execution.valueLabel)}</b>
      <em class="${escapeHtml(monitor.pnlClass)}" data-review-position-pnl="${escapeHtml(item.ticker)}">${escapeHtml(monitor.label)}</em>
      <span class="position-alert-control" data-review-position-alert-control="${escapeHtml(item.ticker)}">
        ${renderPositionAlertControl(item.ticker, monitor)}
      </span>
    </div>
  `;
}

function renderPositionAlertControl(ticker, monitor) {
  if (!positionAlertNeedsAttention(monitor.alertStatus)) return "";
  if (monitor.alertAcknowledged) {
    return `
      <strong class="position-alert acknowledged ${escapeHtml(positionAlertClass(monitor.alertStatus))}" title="${escapeHtml(monitor.alertAcknowledgedAt || "Acknowledged")}">
        Acknowledged
      </strong>
      <button class="position-alert reopen" type="button" data-clear-position-alert="${escapeHtml(ticker || "")}" title="Reopen acknowledged alert">
        Reopen
      </button>
    `;
  }
  return `
    <button class="position-alert ${escapeHtml(positionAlertClass(monitor.alertStatus))}" type="button" data-ack-position-alert="${escapeHtml(ticker || "")}" title="${escapeHtml(monitor.alertReason || positionAlertLabel(monitor.alertStatus))}">
      ${escapeHtml(positionAlertLabel(monitor.alertStatus))}
    </button>
  `;
}

function renderExitFields(item) {
  const exit = calculateExit(item);
  return `
    <div class="review-exit" data-review-exit-panel="${escapeHtml(item.ticker)}">
      <label>
        <span>Exit price</span>
        <input type="number" min="0" step="0.01" inputmode="decimal" value="${escapeHtml(formatInputNumber(item.exit_price))}" data-review-exit="${escapeHtml(item.ticker)}" data-review-exit-field="exit_price" aria-label="Exit price for ${escapeHtml(item.ticker)}" />
      </label>
      <label>
        <span>Shares</span>
        <input type="number" min="0" step="1" inputmode="numeric" value="${escapeHtml(formatInputShares(item.exit_shares || item.execution_shares))}" data-review-exit="${escapeHtml(item.ticker)}" data-review-exit-field="exit_shares" aria-label="Exit shares for ${escapeHtml(item.ticker)}" />
      </label>
      <label>
        <span>Date</span>
        <input type="date" value="${escapeHtml(formatDateInput(item.exited_at))}" data-review-exit="${escapeHtml(item.ticker)}" data-review-exit-field="exited_at" aria-label="Exit date for ${escapeHtml(item.ticker)}" />
      </label>
      <label>
        <span>Reason</span>
        <input type="text" maxlength="120" value="${escapeHtml(item.exit_reason || "")}" data-review-exit="${escapeHtml(item.ticker)}" data-review-exit-field="exit_reason" aria-label="Exit reason for ${escapeHtml(item.ticker)}" />
      </label>
      <b class="${escapeHtml(exit.pnlClass)}" data-review-exit-pnl="${escapeHtml(item.ticker)}">${escapeHtml(exit.label)}</b>
    </div>
  `;
}

function normalizedReviewChecks(value = {}) {
  const source = value && typeof value === "object" ? value : {};
  return Object.fromEntries(REVIEW_CHECK_OPTIONS.map(([key]) => [key, Boolean(source[key])]));
}

function reviewChecklistProgress(checks) {
  const total = REVIEW_CHECK_OPTIONS.length;
  const complete = REVIEW_CHECK_OPTIONS.reduce((count, [key]) => count + (checks[key] ? 1 : 0), 0);
  return { complete, total, done: complete === total, label: `${complete}/${total}` };
}

function updateReviewChecklistDisplay(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  const item = state.reviewQueue.find((candidate) => candidate.ticker === normalized);
  if (!item) return;
  const checks = normalizedReviewChecks(item.review_checks);
  const progress = reviewChecklistProgress(checks);
  const status = normalizeReviewStatus(item.decision_status) || "watch";
  const readyChecklistBlocked = status === "ready" && !progress.done;
  updateReviewReadinessDisplay(normalized);
  const progressEl = els.reviewList.querySelector(`[data-review-check-progress="${cssEscape(normalized)}"]`);
  if (progressEl) {
    progressEl.textContent = progress.label;
    progressEl.classList.toggle("complete", progress.done);
    progressEl.classList.toggle("blocked", readyChecklistBlocked);
  }
  const blockerEl = els.reviewList.querySelector(`[data-review-check-blocker="${cssEscape(normalized)}"]`);
  if (blockerEl) {
    blockerEl.hidden = !readyChecklistBlocked;
  }
  REVIEW_CHECK_OPTIONS.forEach(([key]) => {
    const input = els.reviewList.querySelector(
      `[data-review-check="${cssEscape(normalized)}"][data-review-check-key="${cssEscape(key)}"]`,
    );
    if (input) {
      input.closest("label")?.classList.toggle("checked", Boolean(checks[key]));
    }
  });
}

function selectedReviewTickers() {
  const validTickers = new Set(state.reviewQueue.map((item) => item.ticker));
  return [...state.selectedReviewTickers].filter((ticker) => validTickers.has(ticker));
}

function renderReviewActivity() {
  const events = (state.reviewActivity || []).slice(0, 4);
  if (!events.length) {
    els.reviewActivity.innerHTML = `<div class="activity-empty">No review activity</div>`;
    return;
  }
  els.reviewActivity.innerHTML = events
    .map((event) => {
      const label = activityLabel(event);
      const detail = activityDetail(event);
      const canUndo = canUndoActivity(event);
      return `
        <div class="activity-item ${canUndo ? "restorable" : ""}">
          <div>
            <b>${escapeHtml(label)}</b>
            <span>${escapeHtml(detail)}</span>
          </div>
          ${
            canUndo
              ? `<button class="activity-undo" type="button" data-activity-undo="${escapeHtml(event.at || "")}">Undo</button>`
              : ""
          }
        </div>
      `;
    })
    .join("");
}

function activityLabel(event) {
  const ticker = event.ticker ? ` ${event.ticker}` : "";
  const labels = {
    added: `Added${ticker}`,
    bulk_added: "Added visible",
    bulk_removed: "Removed selected",
    bulk_updated: "Updated selected",
    imported: "Imported queue",
    restored: "Restored queue",
    updated: `Updated${ticker}`,
    removed: `Removed${ticker}`,
    cleared: "Cleared queue",
  };
  return labels[event.action] || `Changed${ticker}`;
}

function activityDetail(event) {
  const parts = [];
  if (Array.isArray(event.changed_fields) && event.changed_fields.length) {
    parts.push(event.changed_fields.join(", "));
  }
  if (event.status) {
    parts.push(event.status);
  }
  if (event.imported_count !== undefined) {
    parts.push(`${event.imported_count} imported`);
  }
  if (event.added_count !== undefined) {
    parts.push(`${event.added_count} added`);
  }
  if (event.removed_count) {
    parts.push(event.action === "imported" ? `${event.removed_count} replaced` : `${event.removed_count} removed`);
  }
  if (event.action === "restored" && event.restored_count) {
    parts.push(`${event.restored_count} restored`);
  }
  if (event.restored_at) {
    parts.push("restored");
  }
  if (event.updated_count) {
    parts.push(`${event.updated_count} updated`);
  }
  if (event.at) {
    parts.push(formatTime(event.at));
  }
  return parts.join(" · ") || "-";
}

function canUndoActivity(event) {
  return Boolean(
    event?.at &&
      !event.restored_at &&
      Array.isArray(event.restorable_items) &&
      event.restorable_items.length,
  );
}

function renderClearReviewButton(totalItems = state.reviewQueue.length) {
  const confirming = Date.now() < state.clearConfirmUntil;
  els.clearReviewButton.disabled = !totalItems;
  els.clearReviewButton.classList.toggle("danger", confirming);
  els.clearReviewButton.textContent = confirming ? "!" : "×";
  els.clearReviewButton.title = confirming ? "Click again to clear review queue" : "Clear review queue";
  els.clearReviewButton.setAttribute(
    "aria-label",
    confirming ? "Confirm clear review queue" : "Clear review queue",
  );
}

function filteredReviewItems(items) {
  const query = cleanReviewQuery(state.reviewQuery).toLowerCase();
  const status = normalizeReviewStatus(state.reviewStatus);
  const priority = normalizeReviewPriorityFilter(state.reviewPriority);
  const tag = normalizeReviewTag(state.reviewTag);
  return items.filter((item) => {
    const queryMatches = !query || reviewItemMatchesQuery(item, query);
    const statusMatches = !status || (item.decision_status || "watch") === status;
    const priorityMatches = !priority || normalizeReviewPriority(item.review_priority) === priority;
    const tagMatches = !tag || parseReviewTags(item.review_tags).includes(tag);
    return queryMatches && statusMatches && priorityMatches && tagMatches;
  });
}

function reviewItemMatchesQuery(item, query) {
  return [item.ticker, item.name, item.review_note, reviewTagsText(item.review_tags)].some((value) =>
    String(value || "").toLowerCase().includes(query),
  );
}

function sortedReviewItems(items) {
  return [...items].sort((left, right) => compareReviewItems(left, right));
}

function compareReviewItems(left, right) {
  const direction = state.reviewSortDir === "asc" ? 1 : -1;
  const field = normalizeReviewSortBy(state.reviewSortBy);
  const leftValue = reviewSortValue(left, field);
  const rightValue = reviewSortValue(right, field);
  const nullCompare = compareNulls(leftValue, rightValue);
  if (nullCompare !== 0) return nullCompare;
  let result = 0;
  if (typeof leftValue === "string" || typeof rightValue === "string") {
    result = String(leftValue || "").localeCompare(String(rightValue || ""));
  } else {
    result = Number(leftValue) - Number(rightValue);
  }
  if (result === 0) {
    return String(left.ticker || "").localeCompare(String(right.ticker || ""));
  }
  return result * direction;
}

function reviewSortValue(item, field) {
  const sizing = calculatePositionSize(item);
  if (field === "ticker") return String(item.ticker || "");
  if (field === "status") return REVIEW_STATUS_PRIORITY[item.decision_status || "watch"] ?? REVIEW_STATUS_PRIORITY.watch;
  if (field === "priority") return reviewPriorityRank(item.review_priority);
  if (field === "score") return sortableNumber(item.canslim_score);
  if (field === "risk") return sortableNumber(sizing.riskAmount);
  if (field === "capital") return sortableNumber(sizing.plannedCapital);
  if (field === "shares") return sortableNumber(sizing.shares);
  return sortableDate(item.added_at);
}

function compareNulls(leftValue, rightValue) {
  const leftMissing = leftValue === null || leftValue === undefined || Number.isNaN(leftValue);
  const rightMissing = rightValue === null || rightValue === undefined || Number.isNaN(rightValue);
  if (leftMissing && rightMissing) return 0;
  if (leftMissing) return 1;
  if (rightMissing) return -1;
  return 0;
}

function renderReviewSummary(summary = calculateReviewSummary()) {
  state.reviewSummary = summary;
  const warnings = Array.isArray(summary.warnings) ? summary.warnings : [];
  const alertCounts = summary.open_position_alert_counts || summary.position_alert_counts || {};
  const stopAlertCount = positionAlertCount(alertCounts, "stop_breached") + positionAlertCount(alertCounts, "near_stop");
  const cells = [
    ["Active", formatNumber(summary.active_items || 0)],
    ["Ready", formatNumber(summary.status_counts?.ready || 0)],
    [
      "Checklist",
      `${formatNumber(summary.checklist_complete_items || 0)} / ${formatNumber(summary.active_items || 0)}`,
    ],
    ["Queue risk", formatCurrency(summary.total_risk_amount || 0)],
    ["Capital", `${formatCurrency(summary.total_planned_capital || 0)} · ${formatSummaryPercent(summary.planned_capital_pct)}`],
    ["Sized", `${formatNumber(summary.sized_items || 0)} / ${formatNumber(summary.active_items || 0)}`],
    ["Executed", `${formatNumber(summary.executed_items || 0)} / ${formatNumber(summary.status_counts?.bought || 0)}`],
    ["Fill value", formatCurrency(summary.total_execution_value || 0)],
    ["Open P/L", `${formatCurrency(summary.total_position_pnl || 0)} · ${formatSummaryPercent(summary.total_position_pnl_pct)}`],
    ["Closed", `${formatNumber(summary.realized_items || 0)} / ${formatNumber(summary.status_counts?.sold || 0)}`],
    ["Realized P/L", `${formatCurrency(summary.total_realized_pnl || 0)} · ${formatSummaryPercent(summary.total_realized_pnl_pct)}`],
    ["Stale", `${formatNumber(summary.aging?.stale_ready_count || 0)} ready · ${formatNumber(summary.aging?.stale_active_count || 0)} active`],
    ["Stop alerts", `${formatNumber(stopAlertCount)} / ${formatNumber(summary.executed_items || 0)}`],
    ["Unsized", formatNumber(summary.unsized_items || 0)],
  ];
  els.reviewSummary.innerHTML = `
    ${cells
      .map(
        ([label, value]) => `
          <div class="summary-cell">
            <span>${escapeHtml(label)}</span>
            <b>${escapeHtml(value)}</b>
          </div>
        `,
      )
      .join("")}
    ${renderSummaryMeters(summary)}
    ${renderRiskActions(summary)}
    ${renderReadinessBlockers(summary)}
    ${renderReviewAging(summary)}
    ${renderPositionAlerts(summary)}
    ${renderOpenPositionRisk(summary)}
    ${renderOpenPositionConcentration(summary)}
    ${renderConcentration(summary)}
    ${renderStatusLedger(summary)}
    ${renderRealizedPerformance(summary)}
    ${renderLargestPositions(summary)}
    ${warnings.map((warning) => `<div class="summary-warning">${escapeHtml(warning)}</div>`).join("")}
  `;
  renderOpsRunbook();
}

function renderRiskActions(summary) {
  const actions = Array.isArray(summary.risk_actions) ? summary.risk_actions.slice(0, 8) : [];
  if (!actions.length) return "";
  return `
    <div class="risk-actions">
      <div class="summary-exposures-head">
        <b>Risk actions</b>
        <span>${escapeHtml(formatNumber(actions.length))} priority item(s)</span>
      </div>
      ${actions.map((item) => {
        const tickers = riskActionTickers(item);
        const actionLabel = riskActionLabel(item.action);
        return `
          <div class="risk-action-row ${escapeHtml(riskActionClass(item.severity))}">
            <span>${escapeHtml(riskActionSeverityLabel(item.severity))}</span>
            <div>
              <b>${escapeHtml(item.label || "Review risk")}</b>
              <em>${escapeHtml(item.detail || "")}</em>
            </div>
            <button
              class="risk-action-command"
              type="button"
              data-risk-action="${escapeHtml(item.action || "")}"
              data-risk-category="${escapeHtml(item.category || "")}"
              data-risk-tickers="${escapeHtml(tickers.join(","))}"
              title="Focus matching review items"
              aria-label="${escapeHtml(`${actionLabel} matching review items`)}"
            >${escapeHtml(actionLabel)}</button>
            ${tickers.length ? `
              <div class="risk-action-tickers">
                ${tickers.map((ticker) => `
                  <button class="text-button" type="button" data-ticker="${escapeHtml(ticker)}">${escapeHtml(ticker)}</button>
                `).join("")}
              </div>
            ` : ""}
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function riskActionClass(severity) {
  return String(severity || "warning").replaceAll("_", "-");
}

function riskActionSeverityLabel(severity) {
  const labels = {
    critical: "Critical",
    warning: "Watch",
    info: "Info",
  };
  return labels[severity] || "Watch";
}

function riskActionLabel(action) {
  const labels = {
    review_exit: "Review exit",
    review_stop: "Review stop",
    refresh_prices: "Refresh price",
    set_stops: "Set stops",
    reduce_queue: "Reduce queue",
    review_open_risk: "Open risk",
    rebalance_queue: "Rebalance plan",
    rebalance_open: "Rebalance open",
    set_trade_plan: "Set levels",
    complete_checklist: "Checklist",
    record_fills: "Record fills",
    record_exits: "Record exits",
    refresh_review: "Refresh review",
  };
  return labels[action] || String(action || "Review").replaceAll("_", " ");
}

function riskActionTickers(item) {
  return Array.isArray(item?.tickers)
    ? item.tickers.map((ticker) => String(ticker || "").trim().toUpperCase()).filter(Boolean).slice(0, 8)
    : [];
}

function focusRiskActionItems(action, requestedTickers = []) {
  const normalizedAction = String(action || "");
  const explicitTickers = normalizeTickerTokens(requestedTickers);
  const derivedTickers = explicitTickers.length ? explicitTickers : riskActionMatchingTickers(normalizedAction);
  const matchedTickers = reviewQueueTickers(derivedTickers);
  const fallbackStatus = matchedTickers.length ? "" : riskActionStatusFilter(normalizedAction);
  state.reviewQuery = "";
  state.reviewStatus = fallbackStatus;
  state.reviewPriority = "";
  state.reviewTag = "";
  state.selectedReviewTickers = new Set(matchedTickers);
  els.reviewSearchInput.value = "";
  els.reviewStatusFilter.value = fallbackStatus;
  els.reviewPriorityFilter.value = "";
  els.reviewTagFilter.value = "";
  applyRiskActionSort(normalizedAction);
  renderReviewQueue();
  document.querySelector(".review-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  if (matchedTickers.length) {
    setAppStatus("online", "Risk action focused", `${matchedTickers.length} review item(s) selected`);
    return;
  }
  if (fallbackStatus) {
    setAppStatus("online", "Risk action focused", `${riskActionLabel(normalizedAction)} filter applied`);
    return;
  }
  setAppStatus("online", "Risk action checked", "No matching review items");
}

function normalizeTickerTokens(tickers) {
  const source = Array.isArray(tickers) ? tickers : String(tickers || "").split(",");
  const seen = new Set();
  return source
    .map((ticker) => String(ticker || "").trim().toUpperCase())
    .filter((ticker) => {
      if (!ticker || seen.has(ticker)) return false;
      seen.add(ticker);
      return true;
    });
}

function reviewQueueTickers(tickers) {
  const requested = new Set(normalizeTickerTokens(tickers));
  if (!requested.size) return [];
  return state.reviewQueue
    .map((item) => String(item.ticker || "").toUpperCase())
    .filter((ticker) => requested.has(ticker));
}

function riskActionMatchingTickers(action) {
  return riskActionMatchingItems(action).map((item) => String(item.ticker || "").toUpperCase()).filter(Boolean);
}

function riskActionMatchingItems(action) {
  const activeItems = state.reviewQueue.filter((item) => !["pass", "sold"].includes(reviewItemStatus(item)));
  const boughtItems = state.reviewQueue.filter((item) => reviewItemStatus(item) === "bought");
  const sizedActiveItems = activeItems
    .map((item) => ({ item, sizing: calculatePositionSize(item) }))
    .filter(({ sizing }) => Number.isFinite(sizing.shares) && sizing.shares > 0);
  const executedBoughtItems = boughtItems
    .map((item) => ({ item, execution: calculateExecution(item), monitor: calculatePositionMonitor(item) }))
    .filter(({ execution }) => execution.recorded);
  if (action === "review_exit") {
    return executedBoughtItems.filter(({ monitor }) => monitor.alertStatus === "stop_breached").map(({ item }) => item);
  }
  if (action === "review_stop") {
    return executedBoughtItems.filter(({ monitor }) => monitor.alertStatus === "near_stop").map(({ item }) => item);
  }
  if (action === "refresh_prices") {
    return executedBoughtItems.filter(({ monitor }) => monitor.alertStatus === "missing_current_price").map(({ item }) => item);
  }
  if (action === "set_stops") {
    return executedBoughtItems.filter(({ monitor }) => monitor.alertStatus === "missing_stop_loss").map(({ item }) => item);
  }
  if (action === "review_open_risk" || action === "rebalance_open") {
    return executedBoughtItems.map(({ item }) => item);
  }
  if (action === "reduce_queue" || action === "rebalance_queue") {
    return sizedActiveItems
      .sort((left, right) => Number(right.sizing.plannedCapital || 0) - Number(left.sizing.plannedCapital || 0))
      .map(({ item }) => item);
  }
  if (action === "set_trade_plan") {
    return activeItems.filter((item) => {
      const sizing = calculatePositionSize(item);
      return !Number.isFinite(sizing.shares) || sizing.shares <= 0;
    });
  }
  if (action === "complete_checklist") {
    return state.reviewQueue.filter((item) =>
      reviewItemStatus(item) === "ready" && !reviewChecklistProgress(normalizedReviewChecks(item.review_checks)).done,
    );
  }
  if (action === "record_fills") {
    return boughtItems.filter((item) => !calculateExecution(item).recorded);
  }
  if (action === "record_exits") {
    return state.reviewQueue.filter((item) => reviewItemStatus(item) === "sold" && !calculateExit(item).recorded);
  }
  if (action === "refresh_review") {
    const staleTickers = Array.isArray(state.reviewSummary?.aging?.stale_items)
      ? state.reviewSummary.aging.stale_items.map((item) => item.ticker)
      : [];
    return reviewQueueTickers(staleTickers)
      .map((ticker) => state.reviewQueue.find((item) => String(item.ticker || "").toUpperCase() === ticker))
      .filter(Boolean);
  }
  return [];
}

function reviewItemStatus(item) {
  return normalizeReviewStatus(item?.decision_status) || "watch";
}

function riskActionStatusFilter(action) {
  const filters = {
    review_exit: "bought",
    review_stop: "bought",
    refresh_prices: "bought",
    set_stops: "bought",
    review_open_risk: "bought",
    rebalance_open: "bought",
    complete_checklist: "ready",
    record_fills: "bought",
    record_exits: "sold",
  };
  return filters[action] || "";
}

function applyRiskActionSort(action) {
  const sortBy = {
    reduce_queue: "capital",
    rebalance_queue: "capital",
    rebalance_open: "capital",
    review_open_risk: "risk",
    set_trade_plan: "risk",
  }[action];
  if (!sortBy) return;
  state.reviewSortBy = sortBy;
  state.reviewSortDir = REVIEW_SORT_DEFAULT_DIR[sortBy] || "desc";
  els.reviewSortSelect.value = state.reviewSortBy;
  renderReviewSortDirection();
}

function renderSummaryMeters(summary) {
  const risk = summary.risk || state.risk || {};
  const rows = [
    {
      label: "Capital guardrail",
      value: numericValue(summary.planned_capital_pct),
      limit: numericValue(risk.max_capital_pct),
      amount: formatCurrency(summary.total_planned_capital || 0),
    },
    {
      label: "Queue risk guardrail",
      value: numericValue(summary.risk_budget_pct),
      limit: numericValue(risk.max_queue_risk_pct),
      amount: formatCurrency(summary.total_risk_amount || 0),
    },
    {
      label: "Open stop-risk guardrail",
      value: numericValue(summary.open_position_risk?.stop_risk_pct),
      limit: numericValue(risk.max_open_position_risk_pct),
      amount: formatCurrency(summary.open_position_risk?.total_stop_risk || 0),
    },
  ];
  return `
    <div class="summary-meters">
      ${rows.map((row) => {
        const percent = Number.isFinite(row.value) ? row.value : 0;
        const limit = Number.isFinite(row.limit) && row.limit > 0 ? row.limit : 100;
        const fill = clamp((percent / Math.max(limit, percent, 1)) * 100, 0, 100);
        const overLimit = Number.isFinite(row.value) && Number.isFinite(row.limit) && row.value > row.limit;
        return `
          <div class="summary-meter ${overLimit ? "over" : ""}">
            <div>
              <span>${escapeHtml(row.label)}</span>
              <b>${escapeHtml(formatSummaryPercent(row.value))} / ${escapeHtml(formatGuardrailPercent(row.limit))}</b>
              <em>${escapeHtml(row.amount)}</em>
            </div>
            <meter min="0" max="100" value="${escapeHtml(fill)}"></meter>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderReadinessBlockers(summary) {
  const items = Array.isArray(summary.readiness_blocker_items) ? summary.readiness_blocker_items.slice(0, 8) : [];
  const counts = summary.readiness_blocker_counts && typeof summary.readiness_blocker_counts === "object"
    ? summary.readiness_blocker_counts
    : {};
  const countRows = Object.entries(counts).filter(([, count]) => Number(count) > 0);
  if (!items.length && !countRows.length) return "";
  return `
    <div class="readiness-blockers">
      <div class="summary-exposures-head">
        <b>Ready blockers</b>
        <span>${escapeHtml(formatNumber(items.length))} blocked</span>
      </div>
      ${countRows.length ? `
        <div class="blocker-counts">
          ${countRows.map(([code, count]) => `
            <span>${escapeHtml(readinessBlockerLabel(code))}<b>${escapeHtml(formatNumber(count))}</b></span>
          `).join("")}
        </div>
      ` : ""}
      ${items.map((item) => `
        <div class="blocker-row">
          <button class="text-button" data-ticker="${escapeHtml(item.ticker || "")}">${escapeHtml(item.ticker || "-")}</button>
          <span title="${escapeHtml(item.name || "")}">${escapeHtml(item.name || "Unknown")}</span>
          <div class="blocker-tags">
            ${normalizedReadinessBlockers(item).map((code) => `
              <em>${escapeHtml(readinessBlockerLabel(code))}</em>
            `).join("")}
          </div>
          <small>${escapeHtml(formatNumber(item.checklist_complete_count || 0))}/${escapeHtml(formatNumber(item.checklist_total_count || REVIEW_CHECK_OPTIONS.length))} checks</small>
        </div>
      `).join("")}
    </div>
  `;
}

function renderReviewAging(summary) {
  const aging = summary.aging || {};
  const staleItems = Array.isArray(aging.stale_items) ? aging.stale_items.slice(0, 8) : [];
  const buckets = aging.buckets || {};
  const staleReady = Number(aging.stale_ready_count || 0);
  const staleActive = Number(aging.stale_active_count || 0);
  if (!staleItems.length && !staleReady && !staleActive) return "";
  return `
    <div class="review-aging">
      <div class="summary-exposures-head">
        <b>Review aging</b>
        <span>${escapeHtml(formatNumber(staleReady))} ready stale · ${escapeHtml(formatNumber(staleActive))} active stale</span>
      </div>
      <div class="aging-counts">
        <span>Fresh<b>${escapeHtml(formatNumber(buckets.fresh || 0))}</b></span>
        <span>Aging<b>${escapeHtml(formatNumber(buckets.aging || 0))}</b></span>
        <span>Stale<b>${escapeHtml(formatNumber(buckets.stale || 0))}</b></span>
        <span>Oldest idle<b>${escapeHtml(formatAgeDays(aging.oldest_idle_days))}</b></span>
      </div>
      ${staleItems.map((item) => `
        <div class="aging-row ${escapeHtml(reviewAgingClass(item.staleness))}">
          <button class="text-button" data-ticker="${escapeHtml(item.ticker || "")}">${escapeHtml(item.ticker || "-")}</button>
          <span title="${escapeHtml(item.name || "")}">${escapeHtml(item.name || "Unknown")}</span>
          <em>${escapeHtml(reviewStatusLabel(item.decision_status))}</em>
          <b>${escapeHtml(formatAgeDays(item.idle_days))} idle</b>
          <small>${escapeHtml(reviewAgingLabel(item.staleness))}</small>
        </div>
      `).join("")}
    </div>
  `;
}

function reviewAgingClass(staleness) {
  const normalized = String(staleness || "").replaceAll("_", "-");
  return normalized || "fresh";
}

function reviewAgingLabel(staleness) {
  const labels = {
    ready_stale: `ready ${READY_STALE_DAYS}+d`,
    active_stale: `active ${REVIEW_STALE_DAYS}+d`,
    fresh: "fresh",
  };
  return labels[staleness] || String(staleness || "fresh").replaceAll("_", " ");
}

function renderPositionAlerts(summary) {
  const items = Array.isArray(summary.position_alert_items) ? summary.position_alert_items.slice(0, 8) : [];
  const acknowledgedItems = Array.isArray(summary.acknowledged_position_alert_items)
    ? summary.acknowledged_position_alert_items.slice(0, 4)
    : [];
  const counts = summary.open_position_alert_counts && typeof summary.open_position_alert_counts === "object"
    ? summary.open_position_alert_counts
    : summary.position_alert_counts && typeof summary.position_alert_counts === "object"
    ? summary.position_alert_counts
    : {};
  const acknowledgedCount = Number(summary.acknowledged_position_alerts) || 0;
  const attentionCounts = Object.entries(POSITION_ALERT_ATTENTION_ORDER)
    .map(([status]) => [status, Number(counts[status]) || 0])
    .filter(([, count]) => count > 0);
  if (!items.length && !attentionCounts.length && !acknowledgedCount) return "";
  const alertTotal = attentionCounts.reduce((sum, [, count]) => sum + count, 0);
  return `
    <div class="position-alerts">
      <div class="summary-exposures-head">
        <b>Position alerts</b>
        <span>${escapeHtml(formatNumber(alertTotal))} open · ${escapeHtml(formatNumber(acknowledgedCount))} acknowledged</span>
      </div>
      ${attentionCounts.length ? `
        <div class="position-alert-counts">
          ${attentionCounts.map(([status, count]) => `
            <span class="${escapeHtml(positionAlertClass(status))}">${escapeHtml(positionAlertLabel(status))}<b>${escapeHtml(formatNumber(count))}</b></span>
          `).join("")}
        </div>
      ` : ""}
      ${items.map((item) => `
        <div class="position-alert-row ${escapeHtml(positionAlertClass(item.alert_status))}">
          <button class="text-button" data-ticker="${escapeHtml(item.ticker || "")}">${escapeHtml(item.ticker || "-")}</button>
          <span title="${escapeHtml(item.name || "")}">${escapeHtml(item.name || "Unknown")}</span>
          <em>${escapeHtml(positionAlertLabel(item.alert_status))}</em>
          <b>${escapeHtml(formatCurrency(item.position_pnl || 0))} · ${escapeHtml(formatSummaryPercent(item.position_pnl_pct))}</b>
          <small>${escapeHtml(formatPositionAlertDistance(item))}</small>
          <button type="button" data-ack-position-alert="${escapeHtml(item.ticker || "")}">Ack</button>
        </div>
      `).join("")}
      ${acknowledgedItems.length ? `
        <div class="acknowledged-alerts">
          <span>Acknowledged</span>
          ${acknowledgedItems.map((item) => `
            <button type="button" data-clear-position-alert="${escapeHtml(item.ticker || "")}">${escapeHtml(item.ticker || "-")} · Reopen</button>
          `).join("")}
        </div>
      ` : ""}
    </div>
  `;
}

function renderOpenPositionRisk(summary) {
  const risk = summary.open_position_risk || {};
  const positionCount = Number(risk.position_count) || 0;
  if (!positionCount) return "";
  const items = Array.isArray(risk.largest_stop_risk_items) ? risk.largest_stop_risk_items.slice(0, 4) : [];
  const metrics = [
    ["Market value", `${formatCurrency(risk.total_market_value || 0)} · ${formatSummaryPercent(risk.market_value_pct)}`],
    ["Stop risk", `${formatCurrency(risk.total_stop_risk || 0)} · ${formatSummaryPercent(risk.stop_risk_pct)}`],
    ["Avg stop room", formatSummaryPercent(risk.average_stop_distance_pct)],
    ["Stop coverage", `${formatNumber(risk.stop_covered_count || 0)} / ${formatNumber(positionCount)}`],
  ];
  return `
    <div class="open-position-risk">
      <div class="summary-exposures-head">
        <b>Open position risk</b>
        <span>${escapeHtml(formatNumber(risk.monitored_count || 0))} priced · ${escapeHtml(formatNumber(risk.missing_current_price_count || 0))} stale price · ${escapeHtml(formatNumber(risk.missing_stop_loss_count || 0))} no stop</span>
      </div>
      <div class="open-risk-metrics">
        ${metrics.map(([label, value]) => `
          <div>
            <span>${escapeHtml(label)}</span>
            <b>${escapeHtml(value)}</b>
          </div>
        `).join("")}
      </div>
      ${items.length ? `
        <div class="open-risk-rows">
          ${items.map((item) => `
            <div class="open-risk-row ${escapeHtml(positionAlertClass(item.alert_status))}">
              <button class="text-button" data-ticker="${escapeHtml(item.ticker || "")}">${escapeHtml(item.ticker || "-")}</button>
              <span>${escapeHtml(formatCurrency(item.stop_risk_amount || 0))}</span>
              <b>${escapeHtml(formatSummaryPercent(item.stop_distance_pct))}</b>
              <em>${escapeHtml(positionAlertLabel(item.alert_status))}</em>
            </div>
          `).join("")}
        </div>
      ` : ""}
    </div>
  `;
}

function renderOpenPositionConcentration(summary) {
  const concentration = summary.open_position_concentration || {};
  const sectorRows = Array.isArray(concentration.sector) ? concentration.sector.slice(0, 4) : [];
  const setupRows = Array.isArray(concentration.setup) ? concentration.setup.slice(0, 4) : [];
  const warningSharePct = numericValue(concentration.warning_share_pct) ?? 60;
  if (!sectorRows.length && !setupRows.length) return "";
  return `
    <div class="concentration-panel open-concentration-panel">
      <div class="summary-exposures-head">
        <b>Open concentration</b>
        <span>${escapeHtml(openConcentrationSummaryText(concentration))}</span>
      </div>
      <div class="concentration-columns">
        ${renderOpenPositionConcentrationColumn("Sector", sectorRows, warningSharePct)}
        ${renderOpenPositionConcentrationColumn("Setup", setupRows, warningSharePct)}
      </div>
    </div>
  `;
}

function openConcentrationSummaryText(concentration) {
  const sector = concentration.top_sector?.label;
  const setup = concentration.top_setup?.label;
  if (sector && setup) return `${sector} · ${setup}`;
  return sector || setup || "no open exposure";
}

function renderOpenPositionConcentrationColumn(label, rows, warningSharePct) {
  if (!rows.length) {
    return `
      <div class="concentration-column">
        <b>${escapeHtml(label)}</b>
        <span class="concentration-empty">No open exposure</span>
      </div>
    `;
  }
  return `
    <div class="concentration-column">
      <b>${escapeHtml(label)}</b>
      ${rows.map((row) => {
        const share = numericValue(row.share_of_market_value_pct) ?? 0;
        const width = clamp(share, 0, 100);
        const crowded = Number(row.priced_count || 0) >= 2 && share >= warningSharePct;
        return `
          <div class="concentration-row ${crowded ? "crowded" : ""}">
            <div>
              <span title="${escapeHtml((row.tickers || []).join(", "))}">${escapeHtml(row.label || "Unclassified")}</span>
              <em>${escapeHtml(formatNumber(row.count || 0))} positions · ${escapeHtml(formatNumber(row.priced_count || 0))} priced</em>
            </div>
            <b>${escapeHtml(formatSummaryPercent(row.share_of_market_value_pct))}</b>
            <small>${escapeHtml(formatCurrency(row.market_value || 0))}</small>
            <meter min="0" max="100" value="${escapeHtml(width)}"></meter>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderConcentration(summary) {
  const concentration = summary.concentration || {};
  const sectorRows = Array.isArray(concentration.sector) ? concentration.sector.slice(0, 4) : [];
  const setupRows = Array.isArray(concentration.setup) ? concentration.setup.slice(0, 4) : [];
  const warningSharePct = numericValue(concentration.warning_share_pct) ?? 60;
  if (!sectorRows.length && !setupRows.length) return "";
  return `
    <div class="concentration-panel">
      <div class="summary-exposures-head">
        <b>Concentration</b>
        <span>${escapeHtml(concentrationSummaryText(concentration))}</span>
      </div>
      <div class="concentration-columns">
        ${renderConcentrationColumn("Sector", sectorRows, warningSharePct)}
        ${renderConcentrationColumn("Setup", setupRows, warningSharePct)}
      </div>
    </div>
  `;
}

function concentrationSummaryText(concentration) {
  const sector = concentration.top_sector?.label;
  const setup = concentration.top_setup?.label;
  if (sector && setup) return `${sector} · ${setup}`;
  return sector || setup || "no active exposure";
}

function renderConcentrationColumn(label, rows, warningSharePct) {
  if (!rows.length) {
    return `
      <div class="concentration-column">
        <b>${escapeHtml(label)}</b>
        <span class="concentration-empty">No active exposure</span>
      </div>
    `;
  }
  return `
    <div class="concentration-column">
      <b>${escapeHtml(label)}</b>
      ${rows.map((row) => {
        const share = numericValue(row.share_of_planned_capital_pct) ?? 0;
        const width = clamp(share, 0, 100);
        const crowded = Number(row.sized_count || 0) >= 2 && share >= warningSharePct;
        return `
          <div class="concentration-row ${crowded ? "crowded" : ""}">
            <div>
              <span title="${escapeHtml((row.tickers || []).join(", "))}">${escapeHtml(row.label || "Unclassified")}</span>
              <em>${escapeHtml(formatNumber(row.count || 0))} items · ${escapeHtml(formatNumber(row.sized_count || 0))} sized</em>
            </div>
            <b>${escapeHtml(formatSummaryPercent(row.share_of_planned_capital_pct))}</b>
            <small>${escapeHtml(formatCurrency(row.planned_capital || 0))}</small>
            <meter min="0" max="100" value="${escapeHtml(width)}"></meter>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderStatusLedger(summary) {
  const breakdown = summaryStatusBreakdown(summary);
  if (!breakdown.length) return "";
  return `
    <div class="summary-ledger">
      ${breakdown.map((row) => `
        <div class="ledger-row status-${escapeHtml(row.status)}">
          <span>${escapeHtml(reviewStatusLabel(row.status))}</span>
          <b>${escapeHtml(formatNumber(row.count || 0))}</b>
          <em>${escapeHtml(formatCurrency(row.risk_amount || 0))} risk</em>
          <small>${escapeHtml(formatCurrency(row.planned_capital || 0))}</small>
        </div>
      `).join("")}
    </div>
  `;
}

function renderRealizedPerformance(summary) {
  const performance = summary.realized_performance || {};
  const tradeCount = Number(performance.trade_count) || 0;
  if (!tradeCount) return "";
  const best = performance.best_trade || null;
  const worst = performance.worst_trade || null;
  const curve = Array.isArray(performance.cumulative_pnl_curve) ? performance.cumulative_pnl_curve : [];
  const metrics = [
    ["Win rate", formatSummaryPercent(performance.win_rate_pct)],
    ["Expectancy", formatRMultiple(performance.expectancy_r ?? performance.average_realized_r)],
    ["Avg P/L", formatCurrency(performance.expectancy_pnl ?? performance.average_realized_pnl)],
    ["Max DD", formatCurrency(performance.max_drawdown)],
    ["Payoff", formatRatio(performance.payoff_ratio)],
    ["Profit factor", formatRatio(performance.profit_factor)],
  ];
  return `
    <div class="realized-performance">
      <div class="summary-exposures-head">
        <b>Realized performance</b>
        <span>${escapeHtml(formatNumber(tradeCount))} closed · ${escapeHtml(formatNumber(performance.winners || 0))}W ${escapeHtml(formatNumber(performance.losers || 0))}L ${escapeHtml(formatNumber(performance.flat || 0))}F</span>
      </div>
      <div class="performance-metrics">
        ${metrics.map(([label, value]) => `
          <div>
            <span>${escapeHtml(label)}</span>
            <b>${escapeHtml(value)}</b>
          </div>
        `).join("")}
      </div>
      <div class="performance-trades">
        ${best ? renderPerformanceTrade("Best", best, "best") : ""}
        ${worst ? renderPerformanceTrade("Worst", worst, "worst") : ""}
      </div>
      ${renderPerformanceCurve(curve, performance.max_drawdown)}
    </div>
  `;
}

function renderPerformanceTrade(label, trade, kind) {
  return `
    <div class="performance-trade ${escapeHtml(kind)}">
      <span>${escapeHtml(label)}</span>
      <button class="text-button" data-ticker="${escapeHtml(trade.ticker || "")}">${escapeHtml(trade.ticker || "-")}</button>
      <b>${escapeHtml(formatCurrency(trade.realized_pnl || 0))} · ${escapeHtml(formatRMultiple(trade.realized_r_multiple))}</b>
      <small>${escapeHtml(trade.exit_reason || trade.exited_at || "")}</small>
    </div>
  `;
}

function renderPerformanceCurve(curve, maxDrawdown) {
  if (!curve.length) return "";
  const rows = curve.slice(-5);
  return `
    <div class="performance-curve">
      <div class="performance-curve-head">
        <span>Equity path</span>
        <b>Max DD ${escapeHtml(formatCurrency(maxDrawdown))}</b>
      </div>
      ${rows.map((row) => {
        const cumulative = Number(row.cumulative_pnl);
        const cumulativeClass = cumulative > 0 ? "up" : cumulative < 0 ? "down" : "flat";
        return `
          <div class="curve-row">
            <button class="text-button" data-ticker="${escapeHtml(row.ticker || "")}">${escapeHtml(row.ticker || "-")}</button>
            <span class="${cumulativeClass}">${escapeHtml(formatCurrency(row.cumulative_pnl))}</span>
            <em>DD ${escapeHtml(formatCurrency(row.drawdown || 0))}</em>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderLargestPositions(summary) {
  const positions = Array.isArray(summary.largest_positions) ? summary.largest_positions.slice(0, 3) : [];
  if (!positions.length) {
    return `<div class="summary-exposures empty">No sized active positions</div>`;
  }
  return `
    <div class="summary-exposures">
      <div class="summary-exposures-head">
        <b>Largest planned positions</b>
        <span>by capital</span>
      </div>
      ${positions.map((position) => `
        <div class="exposure-row status-${escapeHtml(position.decision_status || "watch")}">
          <button class="text-button" data-ticker="${escapeHtml(position.ticker || "")}">${escapeHtml(position.ticker || "-")}</button>
          <span>${escapeHtml(reviewStatusLabel(position.decision_status))}</span>
          <b>${escapeHtml(formatCurrency(position.planned_capital || 0))}</b>
          <em>${escapeHtml(formatCurrency(position.risk_amount || 0))}</em>
        </div>
      `).join("")}
    </div>
  `;
}

function calculateReviewSummary() {
  const statusCounts = { bought: 0, pass: 0, ready: 0, sold: 0, watch: 0 };
  const activeItems = [];
  state.reviewQueue.forEach((item) => {
    const status = REVIEW_STATUS_OPTIONS.some(([value]) => value === item.decision_status) ? item.decision_status : "watch";
    statusCounts[status] += 1;
    if (!["pass", "sold"].includes(status)) {
      activeItems.push(item);
    }
  });
  const sizedItems = activeItems
    .map((item) => ({ item, sizing: calculatePositionSize(item) }))
    .filter(({ sizing }) => Number.isFinite(sizing.shares) && sizing.shares > 0);
  const totalRiskAmount = sizedItems.reduce((sum, { sizing }) => sum + (Number(sizing.riskAmount) || 0), 0);
  const totalPlannedCapital = sizedItems.reduce((sum, { sizing }) => sum + (Number(sizing.plannedCapital) || 0), 0);
  const boughtItems = activeItems.filter((item) => (normalizeReviewStatus(item.decision_status) || "watch") === "bought");
  const executedPositions = boughtItems
    .map((item) => ({ item, execution: calculateExecution(item), monitor: calculatePositionMonitor(item) }))
    .filter(({ execution }) => execution.recorded);
  const executedItems = executedPositions.map(({ execution }) => execution);
  const totalExecutionValue = executedItems.reduce((sum, execution) => sum + execution.value, 0);
  const monitoredPositions = executedPositions
    .map(({ monitor }) => monitor)
    .filter((monitor) => monitor.monitored);
  const totalPositionPnl = monitoredPositions.reduce((sum, monitor) => sum + monitor.pnl, 0);
  const totalPositionPnlPct = totalExecutionValue > 0 ? (totalPositionPnl / totalExecutionValue) * 100 : null;
  const positionAlertCounts = localPositionAlertCounts(executedPositions);
  const openPositionAlertCounts = localPositionAlertCounts(executedPositions, false);
  const positionAlertItems = localPositionAlertItems(executedPositions, false);
  const acknowledgedPositionAlertItems = localPositionAlertItems(executedPositions, true);
  const acknowledgedPositionAlerts = executedPositions.filter(({ monitor }) => monitor.alertAcknowledged).length;
  const equity = Number(state.risk?.account_equity);
  const openPositionRisk = localOpenPositionRisk(executedPositions, equity);
  const openPositionConcentration = localOpenPositionConcentration(executedPositions);
  const boughtExecutionMissing = Math.max(0, boughtItems.length - executedItems.length);
  const soldItems = state.reviewQueue.filter((item) => (normalizeReviewStatus(item.decision_status) || "watch") === "sold");
  const realizedExits = soldItems.map((item) => calculateExit(item)).filter((exit) => exit.recorded);
  const soldExitMissing = Math.max(0, soldItems.length - realizedExits.length);
  const totalExitValue = realizedExits.reduce((sum, exit) => sum + exit.value, 0);
  const totalRealizedPnl = realizedExits.reduce((sum, exit) => sum + exit.pnl, 0);
  const totalExitEntryValue = realizedExits.reduce((sum, exit) => sum + exit.entryValue, 0);
  const totalRealizedPnlPct = totalExitEntryValue > 0 ? (totalRealizedPnl / totalExitEntryValue) * 100 : null;
  const realizedPerformance = localRealizedPerformance(soldItems);
  const plannedCapitalPct = equity > 0 ? (totalPlannedCapital / equity) * 100 : null;
  const riskBudgetPct = equity > 0 ? (totalRiskAmount / equity) * 100 : null;
  const unsizedItems = Math.max(0, activeItems.length - sizedItems.length);
  const checklistCompleteItems = activeItems.filter((item) =>
    reviewChecklistProgress(normalizedReviewChecks(item.review_checks)).done,
  ).length;
  const checklistIncompleteItems = Math.max(0, activeItems.length - checklistCompleteItems);
  const readyChecklistBlockers = activeItems.filter((item) => {
    const status = normalizeReviewStatus(item.decision_status) || "watch";
    return status === "ready" && !reviewChecklistProgress(normalizedReviewChecks(item.review_checks)).done;
  }).length;
  const readinessBlockerItems = localReadinessBlockerItems(activeItems);
  const readinessBlockerCounts = localReadinessBlockerCounts(readinessBlockerItems);
  const aging = localReviewAging(activeItems);
  const concentration = localConcentration(activeItems);
  const largestPositions = sizedItems
    .map(({ item, sizing }) => ({
      ticker: item.ticker,
      name: item.name || "",
      decision_status: item.decision_status || "watch",
      planned_capital: sizing.plannedCapital,
      risk_amount: sizing.riskAmount,
      planned_shares: sizing.shares,
      entry_price: numericValue(item.buy_zone_low) ?? numericValue(item.pivot_price),
      stop_loss_price: numericValue(item.stop_loss_price),
    }))
    .sort((left, right) => Number(right.planned_capital || 0) - Number(left.planned_capital || 0))
    .slice(0, 5);
  const summary = {
    risk: state.risk,
    active_items: activeItems.length,
    sized_items: sizedItems.length,
    unsized_items: unsizedItems,
    executed_items: executedItems.length,
    monitored_positions: monitoredPositions.length,
    bought_execution_missing: boughtExecutionMissing,
    sold_exit_missing: soldExitMissing,
    total_execution_value: totalExecutionValue,
    total_position_pnl: totalPositionPnl,
    total_position_pnl_pct: totalPositionPnlPct,
    open_position_risk: openPositionRisk,
    open_position_concentration: openPositionConcentration,
    closed_items: soldItems.length,
    realized_items: realizedExits.length,
    total_exit_value: totalExitValue,
    total_realized_pnl: totalRealizedPnl,
    total_realized_pnl_pct: totalRealizedPnlPct,
    realized_performance: realizedPerformance,
    position_alert_distance_pct: POSITION_ALERT_NEAR_STOP_PCT,
    position_alert_counts: positionAlertCounts,
    open_position_alert_counts: openPositionAlertCounts,
    position_alert_items: positionAlertItems,
    open_position_alerts: positionAlertItems.length,
    acknowledged_position_alerts: acknowledgedPositionAlerts,
    acknowledged_position_alert_items: acknowledgedPositionAlertItems,
    checklist_complete_items: checklistCompleteItems,
    checklist_incomplete_items: checklistIncompleteItems,
    ready_checklist_blockers: readyChecklistBlockers,
    readiness_blocker_counts: readinessBlockerCounts,
    readiness_blocker_items: readinessBlockerItems,
    aging,
    concentration,
    status_counts: statusCounts,
    total_risk_amount: totalRiskAmount,
    total_planned_capital: totalPlannedCapital,
    planned_capital_pct: plannedCapitalPct,
    risk_budget_pct: riskBudgetPct,
    status_breakdown: localStatusBreakdown(state.reviewQueue),
    largest_positions: largestPositions,
    warnings: summaryWarnings(
      unsizedItems,
      readyChecklistBlockers,
      boughtExecutionMissing,
      soldExitMissing,
      openPositionAlertCounts,
      aging.stale_active_count,
      aging.stale_ready_count,
      [...concentration.warnings, ...openPositionConcentration.warnings],
      plannedCapitalPct,
      riskBudgetPct,
      openPositionRisk.stop_risk_pct,
    ),
  };
  summary.risk_actions = localRiskActions(summary);
  return summary;
}

function localOpenPositionConcentration(executedPositions) {
  const sectorRows = openPositionConcentrationBreakdown(executedPositions, "sector", "Unclassified");
  const setupRows = openPositionConcentrationBreakdown(executedPositions, "setup_status", "Unclassified");
  const warningSharePct = concentrationGuardrailPct("max_open_concentration_pct", 60);
  return {
    top_limit: 5,
    warning_share_pct: warningSharePct,
    sector: sectorRows,
    setup: setupRows,
    top_sector: sectorRows[0] || null,
    top_setup: setupRows[0] || null,
    warnings: [
      ...openPositionConcentrationWarnings(sectorRows, "sector", warningSharePct),
      ...openPositionConcentrationWarnings(setupRows, "setup", warningSharePct),
    ],
  };
}

function openPositionConcentrationBreakdown(executedPositions, field, fallback) {
  const preparedRows = executedPositions.map(({ item, execution, monitor }) => {
    const shares = Number(execution?.shares);
    const lastPrice = Number(monitor?.lastPrice);
    const marketValue = Number.isFinite(shares) && shares > 0 && Number.isFinite(lastPrice) && lastPrice > 0
      ? roundMetric(shares * lastPrice)
      : null;
    const stop = numericValue(item.stop_loss_price);
    const stopRiskAmount = marketValue !== null && Number.isFinite(stop) && stop > 0
      ? roundMetric(Math.max(0, (lastPrice - stop) * shares))
      : null;
    return { item, marketValue, stopRiskAmount };
  });
  const totalMarketValue = preparedRows.reduce((sum, row) => sum + (Number(row.marketValue) || 0), 0);
  const totalStopRisk = preparedRows.reduce((sum, row) => sum + (Number(row.stopRiskAmount) || 0), 0);
  const equity = Number(state.risk?.account_equity);
  const buckets = new Map();
  preparedRows.forEach(({ item, marketValue, stopRiskAmount }) => {
    const label = concentrationLabel(item[field], fallback);
    if (!buckets.has(label)) {
      buckets.set(label, {
        label,
        count: 0,
        priced_count: 0,
        stop_covered_count: 0,
        market_value: 0,
        stop_risk_amount: 0,
        tickers: [],
      });
    }
    const bucket = buckets.get(label);
    bucket.count += 1;
    if (item.ticker && bucket.tickers.length < 8) bucket.tickers.push(item.ticker);
    if (marketValue !== null) {
      bucket.priced_count += 1;
      bucket.market_value += Number(marketValue) || 0;
    }
    if (stopRiskAmount !== null) {
      bucket.stop_covered_count += 1;
      bucket.stop_risk_amount += Number(stopRiskAmount) || 0;
    }
  });
  return [...buckets.values()]
    .map((bucket) => ({
      ...bucket,
      market_value: roundMetric(bucket.market_value),
      stop_risk_amount: roundMetric(bucket.stop_risk_amount),
      share_of_market_value_pct: totalMarketValue > 0
        ? roundMetric((bucket.market_value / totalMarketValue) * 100)
        : null,
      share_of_stop_risk_pct: totalStopRisk > 0 ? roundMetric((bucket.stop_risk_amount / totalStopRisk) * 100) : null,
      market_value_pct: equity > 0 ? roundMetric((bucket.market_value / equity) * 100) : null,
      stop_risk_pct: equity > 0 ? roundMetric((bucket.stop_risk_amount / equity) * 100) : null,
    }))
    .sort((left, right) => {
      const valueResult = (Number(right.market_value) || 0) - (Number(left.market_value) || 0);
      if (valueResult !== 0) return valueResult;
      const riskResult = (Number(right.stop_risk_amount) || 0) - (Number(left.stop_risk_amount) || 0);
      if (riskResult !== 0) return riskResult;
      const countResult = (Number(right.count) || 0) - (Number(left.count) || 0);
      if (countResult !== 0) return countResult;
      return String(left.label || "").localeCompare(String(right.label || ""));
    })
    .slice(0, 5);
}

function openPositionConcentrationWarnings(rows, groupLabel, warningSharePct) {
  const top = rows[0];
  if (!top || top.label === "Unclassified") return [];
  const share = Number(top.share_of_market_value_pct) || 0;
  if (Number(top.priced_count || 0) >= 2 && share >= warningSharePct) {
    return [`open ${groupLabel} concentration: ${top.label} is ${formatSummaryPercent(share)} of open market value`];
  }
  return [];
}

function localConcentration(items) {
  const sectorRows = concentrationBreakdown(items, "sector", "Unclassified");
  const setupRows = concentrationBreakdown(items, "setup_status", "Unclassified");
  const warningSharePct = concentrationGuardrailPct("max_concentration_pct", 60);
  return {
    top_limit: 5,
    warning_share_pct: warningSharePct,
    sector: sectorRows,
    setup: setupRows,
    top_sector: sectorRows[0] || null,
    top_setup: setupRows[0] || null,
    warnings: [
      ...concentrationWarnings(sectorRows, "sector", warningSharePct),
      ...concentrationWarnings(setupRows, "setup", warningSharePct),
    ],
  };
}

function concentrationBreakdown(items, field, fallback) {
  const rows = items.map((item) => ({ item, sizing: calculatePositionSize(item) }));
  const totalCapital = rows.reduce((sum, { sizing }) => sum + (Number(sizing.plannedCapital) || 0), 0);
  const totalRisk = rows.reduce((sum, { sizing }) => {
    if (!Number.isFinite(sizing.shares) || sizing.shares <= 0) return sum;
    return sum + (Number(sizing.riskAmount) || 0);
  }, 0);
  const equity = Number(state.risk?.account_equity);
  const buckets = new Map();
  rows.forEach(({ item, sizing }) => {
    const label = concentrationLabel(item[field], fallback);
    if (!buckets.has(label)) {
      buckets.set(label, {
        label,
        count: 0,
        sized_count: 0,
        risk_amount: 0,
        planned_capital: 0,
        tickers: [],
      });
    }
    const bucket = buckets.get(label);
    bucket.count += 1;
    if (item.ticker && bucket.tickers.length < 8) bucket.tickers.push(item.ticker);
    if (Number.isFinite(sizing.shares) && sizing.shares > 0) {
      bucket.sized_count += 1;
      bucket.risk_amount += Number(sizing.riskAmount) || 0;
      bucket.planned_capital += Number(sizing.plannedCapital) || 0;
    }
  });
  return [...buckets.values()]
    .map((bucket) => ({
      ...bucket,
      risk_amount: roundMetric(bucket.risk_amount),
      planned_capital: roundMetric(bucket.planned_capital),
      share_of_planned_capital_pct: totalCapital > 0 ? roundMetric((bucket.planned_capital / totalCapital) * 100) : null,
      share_of_risk_pct: totalRisk > 0 ? roundMetric((bucket.risk_amount / totalRisk) * 100) : null,
      planned_capital_pct: equity > 0 ? roundMetric((bucket.planned_capital / equity) * 100) : null,
      risk_budget_pct: equity > 0 ? roundMetric((bucket.risk_amount / equity) * 100) : null,
    }))
    .sort((left, right) => {
      const capitalResult = (Number(right.planned_capital) || 0) - (Number(left.planned_capital) || 0);
      if (capitalResult !== 0) return capitalResult;
      const countResult = (Number(right.count) || 0) - (Number(left.count) || 0);
      if (countResult !== 0) return countResult;
      return String(left.label || "").localeCompare(String(right.label || ""));
    })
    .slice(0, 5);
}

function concentrationLabel(value, fallback) {
  const label = String(value || "").trim().replaceAll("_", " ");
  return label || fallback;
}

function concentrationGuardrailPct(key, fallback) {
  const value = Number(state.risk?.[key]);
  if (!Number.isFinite(value) || value < 0) return fallback;
  return Math.min(100, value);
}

function concentrationWarnings(rows, groupLabel, warningSharePct) {
  const top = rows[0];
  if (!top || top.label === "Unclassified") return [];
  const share = Number(top.share_of_planned_capital_pct) || 0;
  if (Number(top.sized_count || 0) >= 2 && share >= warningSharePct) {
    return [`${groupLabel} concentration: ${top.label} is ${formatSummaryPercent(share)} of planned capital`];
  }
  return [];
}

function localReadinessBlockerItems(items) {
  return items
    .map((item) => {
      const sizing = calculatePositionSize(item);
      const blockers = readinessBlockersForItem(item, sizing);
      const checks = normalizedReviewChecks(item.review_checks);
      const progress = reviewChecklistProgress(checks);
      return {
        ticker: item.ticker || "",
        name: item.name || "",
        decision_status: normalizeReviewStatus(item.decision_status) || "watch",
        readiness_status: blockers.length ? "blocked" : "ready",
        readiness_blockers: blockers,
        checklist_complete_count: progress.complete,
        checklist_total_count: progress.total,
        planned_shares: Number.isFinite(sizing.shares) ? sizing.shares : 0,
        entry_price: numericValue(item.buy_zone_low) ?? numericValue(item.pivot_price),
        stop_loss_price: numericValue(item.stop_loss_price),
      };
    })
    .filter((item) => item.decision_status === "ready" && item.readiness_blockers.length)
    .slice(0, 8);
}

function localReadinessBlockerCounts(items) {
  const counts = { checklist_incomplete: 0, missing_position_size: 0 };
  items.forEach((item) => {
    normalizedReadinessBlockers(item).forEach((code) => {
      counts[code] = (counts[code] || 0) + 1;
    });
  });
  return counts;
}

function localReviewAging(items) {
  const snapshots = items.map((item) => reviewAgingSnapshot(item)).filter(Boolean);
  const staleItems = snapshots
    .filter((item) => ["ready_stale", "active_stale"].includes(item.staleness))
    .sort((left, right) => {
      const typeResult = (left.staleness === "ready_stale" ? 0 : 1) - (right.staleness === "ready_stale" ? 0 : 1);
      if (typeResult !== 0) return typeResult;
      const idleResult = (Number(right.idle_days) || 0) - (Number(left.idle_days) || 0);
      if (idleResult !== 0) return idleResult;
      return String(left.ticker || "").localeCompare(String(right.ticker || ""));
    });
  const idleDays = snapshots.map((item) => Number(item.idle_days)).filter(Number.isFinite);
  const activeDays = snapshots.map((item) => Number(item.age_days)).filter(Number.isFinite);
  return {
    active_count: snapshots.length,
    review_stale_days: REVIEW_STALE_DAYS,
    ready_stale_days: READY_STALE_DAYS,
    oldest_active_days: activeDays.length ? Math.max(...activeDays) : null,
    oldest_idle_days: idleDays.length ? Math.max(...idleDays) : null,
    stale_active_count: staleItems.filter((item) => item.staleness === "active_stale").length,
    stale_ready_count: staleItems.filter((item) => item.staleness === "ready_stale").length,
    buckets: {
      fresh: snapshots.filter((item) => (Number(item.idle_days) || 0) <= 1).length,
      aging: snapshots.filter((item) => (Number(item.idle_days) || 0) >= 2 && (Number(item.idle_days) || 0) <= 4).length,
      stale: snapshots.filter((item) => (Number(item.idle_days) || 0) >= REVIEW_STALE_DAYS).length,
    },
    stale_items: staleItems.slice(0, 8),
  };
}

function reviewAgingSnapshot(item) {
  const status = normalizeReviewStatus(item.decision_status) || "watch";
  if (["pass", "sold"].includes(status)) return null;
  const addedAt = parseReviewDate(item.added_at);
  const updatedAt = parseReviewDate(item.updated_at) || addedAt;
  const ageDays = dateAgeDays(addedAt);
  const idleDays = dateAgeDays(updatedAt);
  const effectiveIdleDays = Number.isFinite(idleDays) ? idleDays : ageDays;
  let staleness = "fresh";
  if (status === "ready" && Number.isFinite(effectiveIdleDays) && effectiveIdleDays >= READY_STALE_DAYS) {
    staleness = "ready_stale";
  } else if (Number.isFinite(effectiveIdleDays) && effectiveIdleDays >= REVIEW_STALE_DAYS) {
    staleness = "active_stale";
  }
  return {
    ticker: item.ticker || "",
    name: item.name || "",
    decision_status: status,
    review_priority: item.review_priority || "normal",
    age_days: Number.isFinite(ageDays) ? ageDays : null,
    idle_days: Number.isFinite(effectiveIdleDays) ? effectiveIdleDays : null,
    added_at: item.added_at || "",
    updated_at: item.updated_at || "",
    staleness,
  };
}

function localPositionAlertCounts(executedPositions, acknowledged = null) {
  const counts = {
    ok: 0,
    stop_breached: 0,
    near_stop: 0,
    missing_current_price: 0,
    missing_stop_loss: 0,
  };
  executedPositions.forEach(({ monitor }) => {
    const status = monitor?.alertStatus || "ok";
    if (Object.prototype.hasOwnProperty.call(counts, status)) {
      if (acknowledged !== null && Boolean(monitor?.alertAcknowledged) !== acknowledged) {
        return;
      }
      counts[status] += 1;
    }
  });
  return counts;
}

function localPositionAlertItems(executedPositions, acknowledged) {
  return executedPositions
    .filter(({ monitor }) =>
      positionAlertNeedsAttention(monitor?.alertStatus) && Boolean(monitor?.alertAcknowledged) === acknowledged,
    )
    .map(({ item, monitor }) => ({
      ticker: item.ticker || "",
      name: item.name || "",
      alert_status: monitor.alertStatus,
      alert_reason: monitor.alertReason,
      alert_signature: monitor.alertSignature,
      alert_acknowledged: monitor.alertAcknowledged,
      alert_acknowledged_at: monitor.alertAcknowledgedAt,
      position_last_price: monitor.lastPrice,
      stop_loss_price: numericValue(item.stop_loss_price) ?? "",
      stop_distance_pct: monitor.stopDistancePct,
      position_pnl: monitor.pnl,
      position_pnl_pct: monitor.pnlPct,
      position_r_multiple: monitor.rMultiple,
    }))
    .sort((left, right) => {
      const statusResult = (POSITION_ALERT_ATTENTION_ORDER[left.alert_status] ?? 99)
        - (POSITION_ALERT_ATTENTION_ORDER[right.alert_status] ?? 99);
      if (statusResult !== 0) return statusResult;
      const leftDistance = Number.isFinite(left.stop_distance_pct) ? left.stop_distance_pct : 999;
      const rightDistance = Number.isFinite(right.stop_distance_pct) ? right.stop_distance_pct : 999;
      if (leftDistance !== rightDistance) return leftDistance - rightDistance;
      return String(left.ticker || "").localeCompare(String(right.ticker || ""));
    })
    .slice(0, 8);
}

function localOpenPositionRisk(executedPositions, equity) {
  let totalMarketValue = 0;
  let totalStopRisk = 0;
  let stopDistanceWeightedSum = 0;
  let stopDistanceWeight = 0;
  let monitoredCount = 0;
  let stopCoveredCount = 0;
  let missingCurrentPriceCount = 0;
  let missingStopLossCount = 0;
  const items = [];

  executedPositions.forEach(({ item, execution, monitor }) => {
    if (monitor?.alertStatus === "missing_current_price") missingCurrentPriceCount += 1;
    if (monitor?.alertStatus === "missing_stop_loss") missingStopLossCount += 1;
    const lastPrice = Number(monitor?.lastPrice);
    const shares = Number(execution?.shares);
    if (!Number.isFinite(lastPrice) || lastPrice <= 0 || !Number.isFinite(shares) || shares <= 0) return;

    monitoredCount += 1;
    const marketValue = roundMetric(lastPrice * shares);
    totalMarketValue += marketValue;
    const stop = numericValue(item.stop_loss_price);
    if (!Number.isFinite(stop) || stop <= 0) return;

    stopCoveredCount += 1;
    const stopRiskAmount = roundMetric(Math.max(0, (lastPrice - stop) * shares));
    const stopDistancePct = Number.isFinite(monitor.stopDistancePct) ? roundMetric(monitor.stopDistancePct) : null;
    totalStopRisk += stopRiskAmount;
    if (Number.isFinite(stopDistancePct)) {
      stopDistanceWeightedSum += stopDistancePct * marketValue;
      stopDistanceWeight += marketValue;
    }
    items.push({
      ticker: item.ticker || "",
      name: item.name || "",
      market_value: marketValue,
      stop_risk_amount: stopRiskAmount,
      stop_distance_pct: stopDistancePct,
      position_pnl: roundMetric(monitor.pnl),
      position_pnl_pct: roundMetric(monitor.pnlPct),
      alert_status: monitor.alertStatus || "",
    });
  });

  items.sort((left, right) => {
    const riskResult = (Number(right.stop_risk_amount) || 0) - (Number(left.stop_risk_amount) || 0);
    if (riskResult !== 0) return riskResult;
    const distanceResult = alertDistanceSortValue(left.stop_distance_pct) - alertDistanceSortValue(right.stop_distance_pct);
    if (distanceResult !== 0) return distanceResult;
    return String(left.ticker || "").localeCompare(String(right.ticker || ""));
  });

  return {
    position_count: executedPositions.length,
    monitored_count: monitoredCount,
    stop_covered_count: stopCoveredCount,
    missing_current_price_count: missingCurrentPriceCount,
    missing_stop_loss_count: missingStopLossCount,
    total_market_value: roundMetric(totalMarketValue),
    market_value_pct: equity > 0 ? roundMetric((totalMarketValue / equity) * 100) : null,
    total_stop_risk: roundMetric(totalStopRisk),
    stop_risk_pct: equity > 0 ? roundMetric((totalStopRisk / equity) * 100) : null,
    average_stop_distance_pct: stopDistanceWeight > 0 ? roundMetric(stopDistanceWeightedSum / stopDistanceWeight) : null,
    stop_coverage_pct: executedPositions.length ? roundMetric((stopCoveredCount / executedPositions.length) * 100) : null,
    largest_stop_risk_items: items.slice(0, 5),
  };
}

function alertDistanceSortValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 999;
}

function localRealizedPerformance(items) {
  const trades = items
    .map((item) => ({ item, exit: calculateExit(item) }))
    .filter(({ exit }) => exit.recorded);
  const tradeCount = trades.length;
  const winners = trades.filter(({ exit }) => exit.pnl > 0);
  const losers = trades.filter(({ exit }) => exit.pnl < 0);
  const flat = trades.filter(({ exit }) => exit.pnl === 0);
  const totalPnl = trades.reduce((sum, { exit }) => sum + exit.pnl, 0);
  const winnerPnl = winners.reduce((sum, { exit }) => sum + exit.pnl, 0);
  const loserPnl = losers.reduce((sum, { exit }) => sum + exit.pnl, 0);
  const averagePnl = tradeCount ? roundMetric(totalPnl / tradeCount) : null;
  const averageWinnerPnl = winners.length ? roundMetric(winnerPnl / winners.length) : null;
  const averageLoserPnl = losers.length ? roundMetric(loserPnl / losers.length) : null;
  const rValues = trades.map(({ exit }) => exit.rMultiple).filter((value) => Number.isFinite(value));
  const averageR = rValues.length ? roundMetric(rValues.reduce((sum, value) => sum + value, 0) / rValues.length) : null;
  const sorted = [...trades].sort((left, right) => {
    const pnlResult = right.exit.pnl - left.exit.pnl;
    if (pnlResult !== 0) return pnlResult;
    return String(left.item.ticker || "").localeCompare(String(right.item.ticker || ""));
  });
  const curve = localRealizedCurve(trades);
  const maxDrawdown = curve.length
    ? Math.max(...curve.map((row) => Number(row.drawdown) || 0))
    : null;
  const maxDrawdownPeak = curve.reduce((peak, row) => {
    if (maxDrawdown === null || (Number(row.drawdown) || 0) !== maxDrawdown) return peak;
    const cumulative = Number(row.cumulative_pnl);
    const drawdown = Number(row.drawdown);
    return Number.isFinite(cumulative) && Number.isFinite(drawdown) ? Math.max(peak, cumulative + drawdown) : peak;
  }, 0);
  return {
    trade_count: tradeCount,
    winners: winners.length,
    losers: losers.length,
    flat: flat.length,
    win_rate_pct: tradeCount ? (winners.length / tradeCount) * 100 : null,
    average_realized_pnl: averagePnl,
    average_realized_r: averageR,
    average_winner_pnl: averageWinnerPnl,
    average_loser_pnl: averageLoserPnl,
    expectancy_pnl: averagePnl,
    expectancy_r: averageR,
    profit_factor: loserPnl < 0 ? winnerPnl / Math.abs(loserPnl) : null,
    payoff_ratio: averageWinnerPnl !== null && averageLoserPnl !== null && averageLoserPnl < 0
      ? averageWinnerPnl / Math.abs(averageLoserPnl)
      : null,
    max_drawdown: maxDrawdown,
    max_drawdown_pct: maxDrawdown !== null && maxDrawdownPeak > 0 ? (maxDrawdown / maxDrawdownPeak) * 100 : null,
    cumulative_pnl_curve: curve,
    best_trade: sorted[0] ? localRealizedTradeSnapshot(sorted[0]) : null,
    worst_trade: sorted.length ? localRealizedTradeSnapshot(sorted[sorted.length - 1]) : null,
  };
}

function localRealizedCurve(trades) {
  const ordered = [...trades].sort((left, right) => {
    const leftDate = String(left.item.exited_at || left.item.updated_at || left.item.added_at || "");
    const rightDate = String(right.item.exited_at || right.item.updated_at || right.item.added_at || "");
    const dateResult = leftDate.localeCompare(rightDate);
    if (dateResult !== 0) return dateResult;
    return String(left.item.ticker || "").localeCompare(String(right.item.ticker || ""));
  });
  let cumulativePnl = 0;
  let peakPnl = 0;
  return ordered.map((trade) => {
    cumulativePnl = roundMetric(cumulativePnl + trade.exit.pnl);
    peakPnl = Math.max(peakPnl, cumulativePnl);
    return {
      ...localRealizedTradeSnapshot(trade),
      cumulative_pnl: cumulativePnl,
      drawdown: roundMetric(Math.max(0, peakPnl - cumulativePnl)),
    };
  });
}

function localRealizedTradeSnapshot({ item, exit }) {
  return {
    ticker: item.ticker || "",
    name: item.name || "",
    realized_pnl: exit.pnl,
    realized_pnl_pct: exit.pnlPct,
    realized_r_multiple: exit.rMultiple,
    exit_reason: item.exit_reason || "",
    exited_at: item.exited_at || "",
  };
}

function roundMetric(value, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return Number(number.toFixed(digits));
}

function readinessBlockersForItem(item, sizing = calculatePositionSize(item)) {
  const status = normalizeReviewStatus(item.decision_status) || "watch";
  if (status !== "ready") return [];
  const blockers = [];
  if (!reviewChecklistProgress(normalizedReviewChecks(item.review_checks)).done) {
    blockers.push("checklist_incomplete");
  }
  if (!Number.isFinite(sizing.shares) || sizing.shares <= 0) {
    blockers.push("missing_position_size");
  }
  return blockers;
}

function normalizedReadinessBlockers(item) {
  const source = Array.isArray(item?.readiness_blockers)
    ? item.readiness_blockers
    : String(item?.readiness_blockers || "").split(",");
  return source.map((code) => String(code || "").trim()).filter(Boolean);
}

function readinessBlockerLabel(code) {
  return READINESS_BLOCKER_LABELS[code] || String(code || "Unknown").replaceAll("_", " ");
}

function readinessBlockerSummary(blockers) {
  const labels = (Array.isArray(blockers) ? blockers : []).map(readinessBlockerLabel);
  return labels.length ? `Blocked: ${labels.join(", ")}` : "";
}

function positionAlertCount(source, status) {
  const counts = source?.position_alert_counts || source;
  if (!counts || typeof counts !== "object") return 0;
  return Number(counts[status]) || 0;
}

function positionAlertLabel(status) {
  return POSITION_ALERT_LABELS[status] || String(status || "Position alert").replaceAll("_", " ");
}

function positionAlertClass(status) {
  return String(status || "ok").replaceAll("_", "-");
}

function positionAlertNeedsAttention(status) {
  return Object.prototype.hasOwnProperty.call(POSITION_ALERT_ATTENTION_ORDER, status);
}

function positionAlertIsOpen(monitor) {
  return positionAlertNeedsAttention(monitor?.alertStatus) && !monitor?.alertAcknowledged;
}

function formatPositionAlertDistance(item) {
  const status = String(item?.alert_status || "");
  const stopDistance = numericValue(item?.stop_distance_pct);
  const lastPrice = numericValue(item?.position_last_price);
  const stopPrice = numericValue(item?.stop_loss_price);
  if (Number.isFinite(stopDistance)) {
    return `${formatSummaryPercent(stopDistance)} to stop`;
  }
  if (Number.isFinite(lastPrice) && Number.isFinite(stopPrice)) {
    return `${formatCurrency(lastPrice)} / ${formatCurrency(stopPrice)}`;
  }
  if (status === "missing_current_price") return "No last price";
  if (status === "missing_stop_loss") return "No stop";
  return "-";
}

function summaryStatusBreakdown(summary) {
  if (Array.isArray(summary.status_breakdown) && summary.status_breakdown.length) {
    return summary.status_breakdown;
  }
  return localStatusBreakdown(state.reviewQueue);
}

function localStatusBreakdown(items) {
  const statuses = ["ready", "watch", "bought", "sold", "pass"];
  const buckets = Object.fromEntries(
    statuses.map((status) => [status, { status, count: 0, risk_amount: 0, planned_capital: 0 }]),
  );
  items.forEach((item) => {
    const status = normalizeReviewStatus(item.decision_status) || "watch";
    const bucket = buckets[status] || buckets.watch;
    bucket.count += 1;
    if (["pass", "sold"].includes(status)) return;
    const sizing = calculatePositionSize(item);
    if (!Number.isFinite(sizing.shares) || sizing.shares <= 0) return;
    bucket.risk_amount += Number(sizing.riskAmount) || 0;
    bucket.planned_capital += Number(sizing.plannedCapital) || 0;
  });
  const equity = Number(state.risk?.account_equity);
  return statuses.map((status) => {
    const bucket = buckets[status];
    return {
      ...bucket,
      risk_budget_pct: equity > 0 ? (bucket.risk_amount / equity) * 100 : null,
      planned_capital_pct: equity > 0 ? (bucket.planned_capital / equity) * 100 : null,
    };
  });
}

function summaryWarnings(
  unsizedItems,
  readyChecklistBlockers,
  boughtExecutionMissing,
  soldExitMissing,
  positionAlertCounts,
  staleActiveCount,
  staleReadyCount,
  concentrationWarnings,
  plannedCapitalPct,
  riskBudgetPct,
  openPositionRiskPct,
) {
  const warnings = [];
  if (unsizedItems) warnings.push(`${unsizedItems} active review item(s) are missing buy or stop levels`);
  if (readyChecklistBlockers) {
    warnings.push(`${readyChecklistBlockers} ready review item(s) have incomplete pre-buy checklists`);
  }
  if (boughtExecutionMissing) {
    warnings.push(`${boughtExecutionMissing} bought review item(s) are missing execution records`);
  }
  if (soldExitMissing) {
    warnings.push(`${soldExitMissing} sold review item(s) are missing exit records`);
  }
  if (staleReadyCount) {
    warnings.push(`${staleReadyCount} ready review item(s) have not been touched for ${READY_STALE_DAYS}+ days`);
  }
  if (staleActiveCount) {
    warnings.push(`${staleActiveCount} active review item(s) have not been touched for ${REVIEW_STALE_DAYS}+ days`);
  }
  (Array.isArray(concentrationWarnings) ? concentrationWarnings : []).forEach((warning) => {
    if (warning) warnings.push(String(warning));
  });
  const stopBreached = Number(positionAlertCounts?.stop_breached) || 0;
  const nearStop = Number(positionAlertCounts?.near_stop) || 0;
  const missingCurrentPrice = Number(positionAlertCounts?.missing_current_price) || 0;
  const missingStopLoss = Number(positionAlertCounts?.missing_stop_loss) || 0;
  if (stopBreached) warnings.push(`${stopBreached} bought position(s) are at or below stop loss`);
  if (nearStop) warnings.push(`${nearStop} bought position(s) are within ${POSITION_ALERT_NEAR_STOP_PCT}% of stop loss`);
  if (missingCurrentPrice) warnings.push(`${missingCurrentPrice} executed bought position(s) are missing current prices`);
  if (missingStopLoss) warnings.push(`${missingStopLoss} executed bought position(s) are missing stop levels`);
  const maxCapitalPct = Number(state.risk?.max_capital_pct);
  const maxQueueRiskPct = Number(state.risk?.max_queue_risk_pct);
  const maxOpenRiskPct = Number(state.risk?.max_open_position_risk_pct);
  if (Number.isFinite(plannedCapitalPct) && plannedCapitalPct > 100) {
    warnings.push("planned capital exceeds account equity");
  } else if (Number.isFinite(plannedCapitalPct) && Number.isFinite(maxCapitalPct) && plannedCapitalPct > maxCapitalPct) {
    warnings.push(`planned capital uses more than ${formatGuardrailPercent(maxCapitalPct)} of account equity`);
  }
  if (Number.isFinite(riskBudgetPct) && Number.isFinite(maxQueueRiskPct) && riskBudgetPct > maxQueueRiskPct) {
    warnings.push(`planned queue risk exceeds ${formatGuardrailPercent(maxQueueRiskPct)} of account equity`);
  }
  if (
    Number.isFinite(openPositionRiskPct)
    && Number.isFinite(maxOpenRiskPct)
    && openPositionRiskPct > maxOpenRiskPct
  ) {
    warnings.push(`open position stop risk exceeds ${formatGuardrailPercent(maxOpenRiskPct)} of account equity`);
  }
  return warnings;
}

function localRiskActions(summary) {
  const actions = [];
  const add = (severity, category, label, detail, action, extras = {}) => {
    actions.push({
      severity,
      category,
      label,
      detail,
      action,
      tickers: Array.isArray(extras.tickers) ? extras.tickers.slice(0, 8) : [],
      count: Number.isFinite(Number(extras.count)) ? Number(extras.count) : (extras.tickers || []).length,
      ...(Number.isFinite(Number(extras.amount)) ? { amount: Number(extras.amount) } : {}),
    });
  };
  const alertItems = Array.isArray(summary.position_alert_items) ? summary.position_alert_items : [];
  const alertTickers = (status) => alertItems
    .filter((item) => item.alert_status === status)
    .map((item) => String(item.ticker || "").toUpperCase())
    .filter(Boolean)
    .slice(0, 8);
  const stopBreached = alertTickers("stop_breached");
  if (stopBreached.length) {
    add("critical", "position_alert", "Stop breached", `${stopBreached.length} bought position(s) are at or below stop loss`, "review_exit", { tickers: stopBreached });
  }
  const nearStop = alertTickers("near_stop");
  if (nearStop.length) {
    add("warning", "position_alert", "Near stop", `${nearStop.length} bought position(s) are within ${POSITION_ALERT_NEAR_STOP_PCT}% of stop loss`, "review_stop", { tickers: nearStop });
  }
  const missingPrices = alertTickers("missing_current_price");
  if (missingPrices.length) {
    add("warning", "position_alert", "Refresh open prices", `${missingPrices.length} executed bought position(s) are missing current prices`, "refresh_prices", { tickers: missingPrices });
  }
  const missingStops = alertTickers("missing_stop_loss");
  if (missingStops.length) {
    add("warning", "position_alert", "Add open stops", `${missingStops.length} executed bought position(s) are missing stop levels`, "set_stops", { tickers: missingStops });
  }

  const maxCapitalPct = Number(state.risk?.max_capital_pct);
  const maxQueueRiskPct = Number(state.risk?.max_queue_risk_pct);
  const maxOpenRiskPct = Number(state.risk?.max_open_position_risk_pct);
  if (Number.isFinite(summary.planned_capital_pct) && summary.planned_capital_pct > 100) {
    add("critical", "guardrail", "Reduce planned capital", "Planned capital exceeds account equity", "reduce_queue");
  } else if (Number.isFinite(summary.planned_capital_pct) && Number.isFinite(maxCapitalPct) && summary.planned_capital_pct > maxCapitalPct) {
    add("warning", "guardrail", "Reduce planned capital", `Planned capital uses ${formatSummaryPercent(summary.planned_capital_pct)} vs ${formatGuardrailPercent(maxCapitalPct)} guardrail`, "reduce_queue");
  }
  if (Number.isFinite(summary.risk_budget_pct) && Number.isFinite(maxQueueRiskPct) && summary.risk_budget_pct > maxQueueRiskPct) {
    add("warning", "guardrail", "Reduce queue risk", `Planned queue risk is ${formatSummaryPercent(summary.risk_budget_pct)} vs ${formatGuardrailPercent(maxQueueRiskPct)} guardrail`, "reduce_queue");
  }
  const openRiskPct = numericValue(summary.open_position_risk?.stop_risk_pct);
  if (Number.isFinite(openRiskPct) && Number.isFinite(maxOpenRiskPct) && openRiskPct > maxOpenRiskPct) {
    add("warning", "guardrail", "Reduce open stop risk", `Open stop risk is ${formatSummaryPercent(openRiskPct)} vs ${formatGuardrailPercent(maxOpenRiskPct)} guardrail`, "review_open_risk");
  }

  riskActionsForConcentration(summary.concentration, false).forEach((item) => actions.push(item));
  riskActionsForConcentration(summary.open_position_concentration, true).forEach((item) => actions.push(item));

  if (summary.unsized_items) {
    add("warning", "trade_plan", "Complete trade plans", `${summary.unsized_items} active review item(s) are missing buy or stop levels`, "set_trade_plan", { count: summary.unsized_items });
  }
  if (summary.ready_checklist_blockers) {
    add("warning", "readiness", "Complete ready checklists", `${summary.ready_checklist_blockers} ready review item(s) have incomplete pre-buy checklists`, "complete_checklist", { count: summary.ready_checklist_blockers });
  }
  if (summary.bought_execution_missing) {
    add("warning", "execution", "Record bought fills", `${summary.bought_execution_missing} bought review item(s) are missing execution records`, "record_fills", { count: summary.bought_execution_missing });
  }
  if (summary.sold_exit_missing) {
    add("warning", "execution", "Record exits", `${summary.sold_exit_missing} sold review item(s) are missing exit records`, "record_exits", { count: summary.sold_exit_missing });
  }
  const staleReady = Number(summary.aging?.stale_ready_count) || 0;
  const staleActive = Number(summary.aging?.stale_active_count) || 0;
  const staleTickers = Array.isArray(summary.aging?.stale_items)
    ? summary.aging.stale_items.map((item) => String(item.ticker || "").toUpperCase()).filter(Boolean).slice(0, 8)
    : [];
  if (staleReady) {
    add("warning", "aging", "Revalidate ready ideas", `${staleReady} ready review item(s) have not been touched for ${READY_STALE_DAYS}+ days`, "refresh_review", { tickers: staleTickers, count: staleReady });
  }
  if (staleActive) {
    add("warning", "aging", "Refresh stale reviews", `${staleActive} active review item(s) have not been touched for ${REVIEW_STALE_DAYS}+ days`, "refresh_review", { tickers: staleTickers, count: staleActive });
  }
  return actions.slice(0, 8);
}

function riskActionsForConcentration(concentration, openPosition) {
  const actions = [];
  const warningSharePct = numericValue(concentration?.warning_share_pct) ?? 60;
  [
    ["top_sector", "sector"],
    ["top_setup", "setup"],
  ].forEach(([key, label]) => {
    const row = concentration?.[key];
    if (!row || row.label === "Unclassified") return;
    const count = Number(row[openPosition ? "priced_count" : "sized_count"]) || 0;
    const share = Number(row[openPosition ? "share_of_market_value_pct" : "share_of_planned_capital_pct"]) || 0;
    if (count < 2 || share < warningSharePct) return;
    const scope = openPosition ? "Open" : "Plan";
    actions.push({
      severity: "warning",
      category: "concentration",
      label: `${scope} ${label} concentration`,
      detail: `${row.label} is ${formatSummaryPercent(share)} of ${openPosition ? "open market value" : "planned capital"}`,
      action: openPosition ? "rebalance_open" : "rebalance_queue",
      tickers: Array.isArray(row.tickers) ? row.tickers.slice(0, 8) : [],
      count,
      amount: Number(row[openPosition ? "market_value" : "planned_capital"]) || 0,
    });
  });
  return actions;
}

async function addToReview(row) {
  const ticker = String(row?.ticker || "").trim().toUpperCase();
  if (!ticker) return;
  const item = reviewItemFromCandidate(row);
  state.reviewQueue = [item, ...state.reviewQueue.filter((candidate) => candidate.ticker !== ticker)].slice(0, 30);
  saveReviewQueue();
  renderReviewQueue();
  renderScreener();
  renderActionCenter(state.overview?.action_center || {});
  try {
    const payload = await api("/api/review", {}, { method: "POST", body: { profile: state.profile, item } });
    applyReviewPayload(payload);
    setAppStatus("online", "Review saved");
    renderReviewQueue();
    renderScreener();
    renderActionCenter(state.overview?.action_center || {});
  } catch (error) {
    setAppStatus("offline", "Review local", userMessage(error));
    renderReviewQueue();
    renderActionCenter(state.overview?.action_center || {});
  }
}

async function addVisibleToReview() {
  const rows = state.screener?.candidates || [];
  if (!rows.length) return;
  await addCandidatesToReview(rows, {
    successLabel: `Review added ${rows.length}`,
    offlineLabel: "Bulk review local",
    control: els.bulkReviewButton,
  });
}

async function addActionCandidateToReview(ticker) {
  const candidate = actionCandidateByTicker(ticker);
  if (!candidate) return;
  await addCandidatesToReview([candidate], {
    successLabel: `Queued ${candidate.ticker}`,
    offlineLabel: "Action queue local",
  });
}

async function addPriorityActionCandidatesToReview() {
  const rows = priorityActionCandidates().filter((candidate) => !isQueued(candidate.ticker));
  if (!rows.length) return;
  await addCandidatesToReview(rows, {
    successLabel: `Queued ${rows.length} priority`,
    offlineLabel: "Action queue local",
  });
}

async function addCandidatesToReview(rows, { successLabel = "Review saved", offlineLabel = "Review local", control = null } = {}) {
  const normalizedRows = rows.map(resolveCandidateForReview).filter((row) => String(row?.ticker || "").trim());
  if (!normalizedRows.length) return;
  const items = normalizedRows.map(reviewItemFromCandidate);
  const tickers = new Set(items.map((item) => item.ticker));
  const existingByTicker = new Map(state.reviewQueue.map((item) => [item.ticker, item]));
  const mergedItems = items.map((item) => {
    const existing = existingByTicker.get(item.ticker);
    return existing ? { ...existing, ...item, added_at: existing.added_at || item.added_at } : item;
  });
  state.reviewQueue = [
    ...mergedItems,
    ...state.reviewQueue.filter((candidate) => !tickers.has(candidate.ticker)),
  ].slice(0, 50);
  saveReviewQueue();
  renderReviewQueue();
  renderScreener();
  renderActionCenter(state.overview?.action_center || {});
  if (control) control.disabled = true;
  try {
    const payload = await api("/api/review/bulk", {}, { method: "POST", body: { profile: state.profile, items } });
    applyReviewPayload(payload);
    setAppStatus("online", successLabel);
    renderReviewQueue();
    renderScreener();
    renderActionCenter(state.overview?.action_center || {});
  } catch (error) {
    setAppStatus("offline", offlineLabel, userMessage(error));
    renderReviewQueue();
    renderActionCenter(state.overview?.action_center || {});
  } finally {
    if (control) control.disabled = false;
  }
}

async function updateSelectedReviewStatus() {
  const tickers = selectedReviewTickers();
  const status = normalizeReviewStatus(els.reviewBulkStatus.value) || "watch";
  if (!tickers.length) return;
  const selected = new Set(tickers);
  state.reviewQueue = state.reviewQueue.map((item) => (
    selected.has(item.ticker) ? { ...item, ...reviewStatusTransitionPatch(item, status), updated_at: new Date().toISOString() } : item
  ));
  clearSelectedReviewTickers(tickers);
  saveReviewQueue();
  renderReviewQueue();
  try {
    const payload = await api("/api/review/actions", {}, {
      method: "POST",
      body: { profile: state.profile, action: "status", tickers, decision_status: status },
    });
    applyReviewPayload(payload);
    setAppStatus("online", `Updated ${tickers.length}`);
    renderReviewQueue();
  } catch (error) {
    setAppStatus("offline", "Bulk local", userMessage(error));
    renderReviewQueue();
  }
}

function reviewStatusTransitionPatch(item, status) {
  const normalizedStatus = normalizeReviewStatus(status) || "watch";
  const patch = { decision_status: normalizedStatus };
  if (normalizedStatus === "bought" && item && !item.executed_at) {
    patch.executed_at = new Date().toISOString().slice(0, 10);
  }
  if (normalizedStatus === "sold" && item) {
    if (!item.exited_at) patch.exited_at = new Date().toISOString().slice(0, 10);
    if (isBlank(item.exit_price) && !isBlank(item.current_price)) patch.exit_price = numericValue(item.current_price);
    if (isBlank(item.exit_shares) && !isBlank(item.execution_shares)) {
      const executionShares = numericValue(item.execution_shares);
      if (Number.isFinite(executionShares)) patch.exit_shares = Math.floor(executionShares);
    }
  }
  return patch;
}

async function updateSelectedReviewPriority() {
  const tickers = selectedReviewTickers();
  const priority = normalizeReviewPriority(els.reviewBulkPriority.value);
  if (!tickers.length) return;
  const selected = new Set(tickers);
  state.reviewQueue = state.reviewQueue.map((item) => (
    selected.has(item.ticker) ? { ...item, review_priority: priority, updated_at: new Date().toISOString() } : item
  ));
  clearSelectedReviewTickers(tickers);
  saveReviewQueue();
  renderReviewQueue();
  try {
    const payload = await api("/api/review/actions", {}, {
      method: "POST",
      body: { profile: state.profile, action: "priority", tickers, review_priority: priority },
    });
    applyReviewPayload(payload);
    setAppStatus("online", `Prioritized ${tickers.length}`);
    renderReviewQueue();
  } catch (error) {
    setAppStatus("offline", "Bulk local", userMessage(error));
    renderReviewQueue();
  }
}

async function updateSelectedReviewTags(mode = "add") {
  const tickers = selectedReviewTickers();
  const tags = parseReviewTags(els.reviewBulkTags.value);
  const normalizedMode = mode === "replace" ? "replace" : "add";
  if (!tickers.length) return;
  if (!tags.length) {
    setAppStatus("error", "Tag required");
    renderReviewBulkControls();
    return;
  }
  const selected = new Set(tickers);
  state.reviewQueue = state.reviewQueue.map((item) => {
    if (!selected.has(item.ticker)) return item;
    const existingTags = parseReviewTags(item.review_tags);
    const reviewTags = normalizedMode === "replace" ? tags : parseReviewTags([...existingTags, ...tags]);
    return { ...item, review_tags: reviewTags, updated_at: new Date().toISOString() };
  });
  clearSelectedReviewTickers(tickers);
  els.reviewBulkTags.value = "";
  saveReviewQueue();
  renderReviewQueue();
  try {
    const payload = await api("/api/review/actions", {}, {
      method: "POST",
      body: { profile: state.profile, action: "tags", tickers, mode: normalizedMode, review_tags: tags },
    });
    applyReviewPayload(payload);
    setAppStatus("online", normalizedMode === "replace" ? `Retagged ${tickers.length}` : `Tagged ${tickers.length}`);
    renderReviewQueue();
  } catch (error) {
    setAppStatus("offline", "Tags local", userMessage(error));
    renderReviewQueue();
  }
}

async function removeSelectedReviewItems() {
  const tickers = selectedReviewTickers();
  if (!tickers.length) return;
  const selected = new Set(tickers);
  state.reviewQueue = state.reviewQueue.filter((item) => !selected.has(item.ticker));
  selected.forEach((ticker) => state.selectedReviewTickers.delete(ticker));
  saveReviewQueue();
  renderReviewQueue();
  renderScreener();
  try {
    const payload = await api("/api/review/actions", {}, {
      method: "POST",
      body: { profile: state.profile, action: "remove", tickers },
    });
    applyReviewPayload(payload);
    setAppStatus("online", `Removed ${tickers.length}`);
    renderReviewQueue();
    renderScreener();
  } catch (error) {
    setAppStatus("offline", "Bulk local", userMessage(error));
    renderReviewQueue();
  }
}

function clearSelectedReviewTickers(tickers) {
  tickers.forEach((ticker) => state.selectedReviewTickers.delete(ticker));
}

async function importReviewTickers() {
  const text = els.reviewImportTickers.value.trim();
  if (!text) return;
  els.reviewImportButton.disabled = true;
  setAppStatus("syncing", "Importing tickers");
  try {
    const payload = await api("/api/review/import-tickers", {}, {
      method: "POST",
      timeoutMs: 45000,
      body: { profile: state.profile, text },
    });
    applyReviewPayload(payload);
    const meta = payload.imported || {};
    state.reviewImportReport = meta;
    if (Number(meta.imported_count) > 0) {
      els.reviewImportTickers.value = "";
    }
    renderReviewImportReport();
    renderReviewQueue();
    renderScreener();
    const failureCount = Array.isArray(meta.failures) ? meta.failures.length : 0;
    const label = failureCount ? `Imported ${meta.imported_count || 0}/${meta.requested?.length || 0}` : `Imported ${meta.imported_count || 0}`;
    const detail = importTickerDetail(meta);
    setAppStatus(failureCount ? "offline" : "online", label, detail);
  } catch (error) {
    setAppStatus("error", "Import failed", userMessage(error));
  } finally {
    els.reviewImportButton.disabled = false;
  }
}

async function updateReviewPricesFromPaste() {
  const parsed = parseReviewPriceUpdates(els.reviewPriceUpdates.value);
  if (!parsed.updates.length) {
    setAppStatus("error", "No prices parsed", parsed.failures.slice(0, 3).join(" | "));
    return;
  }
  els.reviewPriceButton.disabled = true;
  setAppStatus("syncing", "Updating prices");
  const updatesByTicker = new Map(parsed.updates.map((item) => [item.ticker, item.current_price]));
  let localUpdated = 0;
  state.reviewQueue = state.reviewQueue.map((item) => {
    const price = updatesByTicker.get(String(item.ticker || "").toUpperCase());
    if (!Number.isFinite(price)) return item;
    localUpdated += 1;
    return { ...item, current_price: price, updated_at: new Date().toISOString() };
  });
  if (localUpdated) {
    saveReviewQueue();
    renderReviewQueue();
  }
  try {
    const payload = await api("/api/review/actions", {}, {
      method: "POST",
      body: { profile: state.profile, action: "prices", prices: parsed.updates },
    });
    applyReviewPayload(payload);
    els.reviewPriceUpdates.value = "";
    renderReviewQueue();
    const detail = parsed.failures.length ? parsed.failures.slice(0, 3).join(" | ") : "";
    setAppStatus(parsed.failures.length ? "offline" : "online", `Updated ${localUpdated || parsed.updates.length} price(s)`, detail);
  } catch (error) {
    setAppStatus("offline", "Prices local", userMessage(error));
    renderReviewQueue();
  } finally {
    els.reviewPriceButton.disabled = false;
  }
}

function parseReviewPriceUpdates(text) {
  const updatesByTicker = new Map();
  const failures = [];
  String(text || "")
    .split(/[\n;]+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const match = line.match(/^(?:[A-Z]+:)?([A-Z0-9._-]{1,15})\s*[,=\s]\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?)$/i);
      if (!match) {
        failures.push(`${line}: expected TICKER PRICE`);
        return;
      }
      const ticker = normalizePastedTicker(match[1]);
      const price = Number(match[2].replaceAll(",", ""));
      if (!ticker || !Number.isFinite(price) || price < 0) {
        failures.push(`${line}: invalid price`);
        return;
      }
      updatesByTicker.set(ticker, { ticker, current_price: Number(price.toFixed(4)) });
    });
  return { updates: [...updatesByTicker.values()], failures };
}

function normalizePastedTicker(value) {
  const ticker = String(value || "").trim().toUpperCase().replaceAll(".", "-");
  return /^[A-Z0-9][A-Z0-9_-]{0,14}$/.test(ticker) ? ticker : "";
}

function importTickerDetail(meta = {}) {
  const parts = [];
  if (meta.truncated_count) {
    parts.push(`${meta.truncated_count} over limit`);
  }
  if (Array.isArray(meta.failures) && meta.failures.length) {
    parts.push(meta.failures.map((failure) => `${failure.ticker}: ${failure.error}`).join(" | "));
  }
  return parts.join(" · ");
}

function reviewItemFromCandidate(row) {
  return {
    ticker: String(row?.ticker || "").trim().toUpperCase(),
    name: row.name || "",
    sector: row.sector || "",
    industry: row.industry || "",
    canslim_score: row.canslim_score,
    score_band: row.score_band,
    setup_status: row.setup_status,
    current_price: row.current_price,
    pivot_price: row.pivot_price,
    pivot_distance_pct: row.pivot_distance_pct,
    buy_zone_low: row.buy_zone_low,
    buy_zone_high: row.buy_zone_high,
    stop_loss_price: row.stop_loss_price,
    profit_target_low: row.profit_target_low,
    profit_target_high: row.profit_target_high,
    review_priority: normalizeReviewPriority(row.review_priority),
    review_tags: parseReviewTags(row.review_tags),
    review_checks: normalizedReviewChecks(row.review_checks),
    profile: state.profile,
    added_at: new Date().toISOString(),
  };
}

async function updateReviewItem(ticker, patch, { rerender = true } = {}) {
  const normalized = String(ticker || "").toUpperCase();
  const existing = state.reviewQueue.find((item) => item.ticker === normalized);
  if (!existing) return;
  const item = { ...existing, ...patch, ticker: normalized, profile: state.profile };
  state.reviewQueue = [item, ...state.reviewQueue.filter((candidate) => candidate.ticker !== normalized)];
  saveReviewQueue();
  if (rerender) renderReviewQueue();
  try {
    const payload = await api("/api/review", {}, { method: "POST", body: { profile: state.profile, item } });
    applyReviewPayload(payload);
    setAppStatus("online", "Review saved");
    if (rerender) renderReviewQueue();
  } catch (error) {
    setAppStatus("offline", "Review local", userMessage(error));
    if (rerender) renderReviewQueue();
  }
}

function updateReviewPriceInput(input) {
  const normalized = String(input.dataset.reviewPrice || "").toUpperCase();
  const field = input.dataset.reviewField;
  if (!["buy_zone_low", "stop_loss_price"].includes(field)) return;
  const existing = state.reviewQueue.find((item) => item.ticker === normalized);
  if (!existing) return;
  const value = numericInputValue(input.value);
  existing[field] = value;
  saveReviewQueue();
  renderReviewSummary(calculateReviewSummary());
  updateReviewLevelDisplays(normalized);
  const timerKey = `${normalized}:${field}`;
  clearTimeout(reviewPriceTimers.get(timerKey));
  reviewPriceTimers.set(
    timerKey,
    setTimeout(() => {
      updateReviewItem(normalized, { [field]: value }, { rerender: false });
    }, 450),
  );
}

function updateReviewLevelDisplays(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  const item = state.reviewQueue.find((candidate) => candidate.ticker === normalized);
  if (!item) return;
  const entry = numericValue(item.buy_zone_low) ?? numericValue(item.pivot_price);
  const entryLabel = !isBlank(item.buy_zone_low) && !isBlank(item.buy_zone_high)
    ? `Buy ${formatRange(item.buy_zone_low, item.buy_zone_high)}`
    : `Entry ${formatCurrency(entry)}`;
  const sizing = calculatePositionSize(item);
  const entryEl = els.reviewList.querySelector(`[data-review-entry="${cssEscape(normalized)}"]`);
  const stopEl = els.reviewList.querySelector(`[data-review-stop-display="${cssEscape(normalized)}"]`);
  const sizingEl = els.reviewList.querySelector(`[data-review-sizing="${cssEscape(normalized)}"]`);
  if (entryEl) entryEl.textContent = entryLabel;
  if (stopEl) stopEl.textContent = `Stop ${formatCurrency(item.stop_loss_price)}`;
  if (sizingEl) sizingEl.textContent = `Shares ${formatShares(sizing.shares)}`;
  updateReviewReadinessDisplay(normalized);
  updateReviewExecutionDisplay(normalized);
  updateReviewExitDisplay(normalized);
}

function updateReviewExecutionInput(input) {
  const normalized = String(input.dataset.reviewExecution || "").toUpperCase();
  const field = input.dataset.reviewExecutionField;
  if (!["execution_price", "execution_shares", "executed_at", "current_price"].includes(field)) return;
  const existing = state.reviewQueue.find((item) => item.ticker === normalized);
  if (!existing) return;
  const value = field === "executed_at" ? String(input.value || "") : numericInputValue(input.value);
  existing[field] = field === "execution_shares" && value !== null ? Math.floor(value) : value;
  saveReviewQueue();
  renderReviewSummary(calculateReviewSummary());
  updateReviewExecutionDisplay(normalized);
  updateReviewExitDisplay(normalized);
  const timerKey = `${normalized}:${field}`;
  clearTimeout(reviewExecutionTimers.get(timerKey));
  reviewExecutionTimers.set(
    timerKey,
    setTimeout(() => {
      updateReviewItem(normalized, { [field]: existing[field] }, { rerender: false });
    }, 450),
  );
}

function updateReviewExitInput(input) {
  const normalized = String(input.dataset.reviewExit || "").toUpperCase();
  const field = input.dataset.reviewExitField;
  if (!["exit_price", "exit_shares", "exited_at", "exit_reason"].includes(field)) return;
  const existing = state.reviewQueue.find((item) => item.ticker === normalized);
  if (!existing) return;
  const value = ["exited_at", "exit_reason"].includes(field) ? String(input.value || "") : numericInputValue(input.value);
  existing[field] = field === "exit_shares" && value !== null ? Math.floor(value) : value;
  saveReviewQueue();
  renderReviewSummary(calculateReviewSummary());
  updateReviewExitDisplay(normalized);
  const timerKey = `${normalized}:${field}`;
  clearTimeout(reviewExecutionTimers.get(timerKey));
  reviewExecutionTimers.set(
    timerKey,
    setTimeout(() => {
      updateReviewItem(normalized, { [field]: existing[field] }, { rerender: false });
    }, 450),
  );
}

function updateReviewExitDisplay(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  const item = state.reviewQueue.find((candidate) => candidate.ticker === normalized);
  if (!item) return;
  const exitEl = els.reviewList.querySelector(`[data-review-exit-pnl="${cssEscape(normalized)}"]`);
  if (!exitEl) return;
  const exit = calculateExit(item);
  exitEl.textContent = exit.label;
  exitEl.classList.toggle("up", exit.pnlClass === "up");
  exitEl.classList.toggle("down", exit.pnlClass === "down");
  exitEl.classList.toggle("flat", exit.pnlClass === "flat");
}

function updateReviewExecutionDisplay(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  const item = state.reviewQueue.find((candidate) => candidate.ticker === normalized);
  if (!item) return;
  const valueEl = els.reviewList.querySelector(`[data-review-execution-value="${cssEscape(normalized)}"]`);
  if (valueEl) {
    valueEl.textContent = calculateExecution(item).valueLabel;
  }
  const pnlEl = els.reviewList.querySelector(`[data-review-position-pnl="${cssEscape(normalized)}"]`);
  if (pnlEl) {
    const monitor = calculatePositionMonitor(item);
    pnlEl.textContent = monitor.label;
    pnlEl.classList.toggle("up", monitor.pnlClass === "up");
    pnlEl.classList.toggle("down", monitor.pnlClass === "down");
    pnlEl.classList.toggle("flat", monitor.pnlClass === "flat");
  }
  const alertControl = els.reviewList.querySelector(`[data-review-position-alert-control="${cssEscape(normalized)}"]`);
  if (alertControl) {
    alertControl.innerHTML = renderPositionAlertControl(normalized, calculatePositionMonitor(item));
  }
}

function updateReviewReadinessDisplay(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  const item = state.reviewQueue.find((candidate) => candidate.ticker === normalized);
  if (!item) return;
  const blockers = readinessBlockersForItem(item);
  const itemEl = els.reviewList
    .querySelector(`[data-review-readiness="${cssEscape(normalized)}"]`)
    ?.closest(".review-item");
  itemEl?.classList.toggle("readiness-blocked", blockers.length > 0);
  const badge = els.reviewList.querySelector(`[data-review-readiness="${cssEscape(normalized)}"]`);
  if (badge) {
    badge.hidden = blockers.length === 0;
    badge.textContent = readinessBlockerSummary(blockers);
  }
}

async function removeFromReview(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  state.reviewQueue = state.reviewQueue.filter((item) => item.ticker !== normalized);
  state.selectedReviewTickers.delete(normalized);
  saveReviewQueue();
  renderReviewQueue();
  renderScreener();
  try {
    const payload = await api("/api/review", { profile: state.profile, ticker: normalized }, { method: "DELETE" });
    applyReviewPayload(payload);
    setAppStatus("online", "Review saved");
    renderReviewQueue();
    renderScreener();
  } catch (error) {
    setAppStatus("offline", "Review local", userMessage(error));
    renderReviewQueue();
  }
}

async function clearReviewQueue() {
  if (!state.reviewQueue.length) return;
  if (Date.now() >= state.clearConfirmUntil) {
    state.clearConfirmUntil = Date.now() + CLEAR_CONFIRM_MS;
    renderClearReviewButton();
    setAppStatus("syncing", "Confirm clear", "Click clear again within 8 seconds");
    clearTimeout(clearConfirmTimer);
    clearConfirmTimer = setTimeout(() => {
      state.clearConfirmUntil = 0;
      renderClearReviewButton();
      setAppStatus("online", "Clear cancelled");
    }, CLEAR_CONFIRM_MS);
    return;
  }
  clearTimeout(clearConfirmTimer);
  state.clearConfirmUntil = 0;
  state.reviewQueue = [];
  state.selectedReviewTickers.clear();
  saveReviewQueue();
  renderReviewQueue();
  renderScreener();
  try {
    const payload = await api("/api/review", { profile: state.profile, confirm: "clear" }, { method: "DELETE" });
    applyReviewPayload(payload);
    setAppStatus("online", "Review cleared");
    renderReviewQueue();
    renderScreener();
  } catch (error) {
    setAppStatus("offline", "Review local", userMessage(error));
    renderReviewQueue();
  }
}

async function undoReviewActivity(activityAt) {
  const token = String(activityAt || "");
  if (!token) return;
  setAppStatus("syncing", "Restoring review");
  try {
    const payload = await api("/api/review/undo", {}, { method: "POST", body: { profile: state.profile, activity_at: token } });
    applyReviewPayload(payload);
    setAppStatus("online", "Review restored");
    renderReviewQueue();
    renderScreener();
    renderActionCenter(state.overview?.action_center || {});
    await loadReviewSummary();
  } catch (error) {
    setAppStatus("error", "Restore failed", userMessage(error));
  }
}

async function acknowledgePositionAlert(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  const item = state.reviewQueue.find((candidate) => candidate.ticker === normalized);
  if (!item) return;
  const monitor = calculatePositionMonitor(item);
  if (!positionAlertIsOpen(monitor) || !monitor.alertSignature) return;
  const patch = {
    position_alert_ack_signature: monitor.alertSignature,
    position_alert_acknowledged_at: new Date().toISOString(),
  };
  Object.assign(item, patch);
  saveReviewQueue();
  renderReviewQueue();
  setAppStatus("syncing", "Alert acknowledged");
  try {
    await updateReviewItem(normalized, patch, { rerender: true });
    await loadReviewSummary();
    setAppStatus("online", "Alert acknowledged");
  } catch (error) {
    setAppStatus("offline", "Alert local", userMessage(error));
    renderReviewQueue();
  }
}

async function clearPositionAlertAcknowledgement(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  const item = state.reviewQueue.find((candidate) => candidate.ticker === normalized);
  if (!item) return;
  const patch = {
    position_alert_ack_signature: "",
    position_alert_acknowledged_at: "",
  };
  Object.assign(item, patch);
  saveReviewQueue();
  renderReviewQueue();
  setAppStatus("syncing", "Alert reopened");
  try {
    await updateReviewItem(normalized, patch, { rerender: true });
    await loadReviewSummary();
    setAppStatus("online", "Alert reopened");
  } catch (error) {
    setAppStatus("offline", "Alert local", userMessage(error));
    renderReviewQueue();
  }
}

async function exportScreenerView() {
  const rows = state.screener?.candidates || [];
  if (!rows.length) return;
  const url = new URL("/api/screener/export", window.location.origin);
  Object.entries({
    profile: state.profile,
    q: els.candidateSearch.value,
    min_score: els.minScore.value,
    setup: els.setupFilter.value,
    sort_by: state.sortBy,
    sort_dir: state.sortDir,
    limit: 300,
  }).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });
  await triggerDownload(url, screenerExportFilename());
}

function screenerExportFilename() {
  const parts = [];
  if (els.setupFilter.value) parts.push(els.setupFilter.value);
  if (els.minScore.value) parts.push(`score${String(els.minScore.value).replace(".", "_")}`);
  if (els.candidateSearch.value.trim()) parts.push("search");
  const suffix = parts.length ? `-${parts.join("-")}` : "";
  return `canslim-screener-${state.profile}${suffix}.csv`;
}

async function exportReviewQueue() {
  if (!state.reviewQueue.length) return;
  const format = els.reviewExportFormat.value || "csv";
  const url = new URL("/api/review/export", window.location.origin);
  Object.entries({ ...reviewRiskParams(), ...reviewExportFilters(), format }).forEach(([key, value]) => {
    if (value !== "") {
      url.searchParams.set(key, value);
    }
  });
  await triggerDownload(url, reviewExportFilename(format));
}

async function exportAnalysisDossier() {
  const ticker = state.analysis?.ticker || els.analysisTicker.textContent;
  const normalized = String(ticker || "").trim().toUpperCase();
  if (!normalized || !state.analysis?.found) return;
  const url = new URL("/api/analyze/export", window.location.origin);
  url.searchParams.set("profile", state.profile);
  url.searchParams.set("ticker", normalized);
  if (await triggerDownload(url, `canslim-dossier-${state.profile}-${normalized}.json`)) {
    setAppStatus("online", "Dossier exported");
  }
}

async function exportSelectedReviewItems() {
  const tickers = selectedReviewTickers();
  if (!tickers.length) return;
  const format = els.reviewExportFormat.value || "csv";
  const url = new URL("/api/review/export", window.location.origin);
  Object.entries({ ...reviewRiskParams(), format, tickers: tickers.join(",") }).forEach(([key, value]) => {
    url.searchParams.set(key, value);
  });
  await triggerDownload(url, reviewExportFilename(format, { selected: true }));
}

function reviewExportFilename(format, options = {}) {
  const normalized = String(format || "csv");
  const filterSuffix = options.selected ? "-selected" : reviewExportFilterSuffix();
  if (normalized === "tradingview") return `canslim-tradingview-review-${state.profile}${filterSuffix}.json`;
  const extension = normalized === "txt" ? "txt" : normalized === "json" ? "json" : "csv";
  return `canslim-review-${state.profile}${filterSuffix}.${extension}`;
}

function reviewExportFilters() {
  return {
    q: cleanReviewQuery(state.reviewQuery),
    status: normalizeReviewStatus(state.reviewStatus),
    priority: normalizeReviewPriorityFilter(state.reviewPriority),
    tag: normalizeReviewTag(state.reviewTag),
  };
}

function reviewExportFilterSuffix() {
  const filters = reviewExportFilters();
  const parts = [filters.status, filters.priority, filters.tag].filter(Boolean);
  if (filters.q) parts.push("search");
  return parts.length ? `-${parts.join("-")}` : "";
}

async function exportWorkspaceSnapshot() {
  setAppStatus("syncing", "Preparing snapshot");
  await saveWorkspacePreferences();
  await saveSessionJournal({ onlyIfDirty: true, silent: true });
  const url = new URL("/api/workspace/export", window.location.origin);
  Object.entries(reviewRiskParams()).forEach(([key, value]) => {
    url.searchParams.set(key, value);
  });
  if (await triggerDownload(url, `canslim-workspace-${state.profile}.json`)) {
    setAppStatus("online", "Snapshot exported");
  }
}

async function exportSessionReport() {
  setAppStatus("syncing", "Preparing report");
  await saveWorkspacePreferences();
  await saveSessionJournal({ onlyIfDirty: true, silent: true });
  const url = new URL("/api/session/report", window.location.origin);
  Object.entries({ ...reviewRiskParams(), date: ensureJournalDate(), format: "md" }).forEach(([key, value]) => {
    url.searchParams.set(key, value);
  });
  if (await triggerDownload(url, `canslim-session-${state.profile}.md`)) {
    setAppStatus("online", "Report exported");
  }
}

async function exportSupportBundle() {
  setAppStatus("syncing", "Preparing support");
  const url = new URL("/api/support/bundle", window.location.origin);
  url.searchParams.set("profile", state.profile);
  if (await triggerDownload(url, `canslim-support-${state.profile}.json`)) {
    setAppStatus("online", "Support exported");
  }
}

function chooseWorkspaceSnapshot() {
  els.workspaceImportInput.value = "";
  els.workspaceImportInput.click();
}

async function importWorkspaceSnapshot(file) {
  if (!file) return;
  if (file.size > 1_000_000) {
    setAppStatus("error", "Import rejected", "Snapshot file is larger than 1 MB");
    return;
  }
  setLoading(true);
  setAppStatus("syncing", "Checking snapshot");
  try {
    const snapshot = JSON.parse(await file.text());
    const preview = await api("/api/workspace/import/preview", {}, { method: "POST", body: { snapshot } });
    if (!(await requestWorkspaceImportConfirmation(preview, file.name))) {
      setAppStatus("online", "Import canceled");
      return;
    }
    setAppStatus("syncing", "Importing snapshot");
    const payload = await api("/api/workspace/import", {}, { method: "POST", body: { snapshot, confirm: "import" } });
    applyWorkspacePreferences(payload.preferences);
    applyReviewPayload(payload.review);
    state.reviewSummary = payload.review_summary;
    state.profile = payload.profile;
    state.analysis = null;
    state.selectedCompareTickers.clear();
    await loadDashboard();
    const quarantinedCount = Array.isArray(payload.quarantined_stores) ? payload.quarantined_stores.length : 0;
    setAppStatus(
      "online",
      `Restored ${payload.review?.items?.length || 0} item(s)`,
      quarantinedCount
        ? `Quarantined ${quarantinedCount} corrupt store${quarantinedCount === 1 ? "" : "s"}`
        : workspaceBackupStatusDetail(payload.backup),
    );
  } catch (error) {
    setAppStatus("error", "Import failed", userMessage(error));
  } finally {
    setLoading(false);
  }
}

function requestWorkspaceImportConfirmation(preview, filename) {
  if (
    !els.workspaceImportModal
    || !els.workspaceImportMetrics
    || !els.workspaceImportDetail
    || !els.workspaceImportConfirmButton
    || !els.workspaceImportCancelButton
  ) {
    setAppStatus(
      "error",
      "Import dialog unavailable",
      "Workspace snapshot import is blocked until the import review dialog is available",
    );
    return Promise.resolve(false);
  }
  renderWorkspaceImportPreview(preview, filename);
  openManagedModal(els.workspaceImportModal, els.workspaceImportConfirmButton);
  return new Promise((resolve) => {
    workspaceImportConfirmation = resolve;
  });
}

function resolveWorkspaceImportConfirmation(confirmed) {
  if (!workspaceImportConfirmation) return;
  const resolve = workspaceImportConfirmation;
  workspaceImportConfirmation = null;
  closeManagedModal(els.workspaceImportModal);
  resolve(Boolean(confirmed));
}

function requestViewName({ mode, title, summary, initialValue }) {
  if (
    !els.viewNameModal
    || !els.viewNameInput
    || !els.viewNameConfirmButton
    || !els.viewNameCancelButton
  ) {
    setAppStatus("error", "Name dialog unavailable");
    return Promise.resolve(null);
  }
  if (els.viewNameMode) els.viewNameMode.textContent = mode || "Saved View";
  if (els.viewNameModalTitle) els.viewNameModalTitle.textContent = title || "Save view";
  if (els.viewNameSummary) els.viewNameSummary.textContent = summary || "Current filters";
  els.viewNameInput.value = String(initialValue || "");
  renderViewNameError("");
  openManagedModal(els.viewNameModal, els.viewNameInput);
  requestAnimationFrame(() => {
    els.viewNameInput.select();
  });
  return new Promise((resolve) => {
    viewNameConfirmation = resolve;
  });
}

function resolveViewNameConfirmation(value) {
  if (!viewNameConfirmation) return;
  const resolve = viewNameConfirmation;
  viewNameConfirmation = null;
  renderViewNameError("");
  closeManagedModal(els.viewNameModal);
  resolve(value);
}

function renderViewNameError(message) {
  const text = String(message || "");
  els.viewNameForm?.classList.toggle("is-invalid", Boolean(text));
  if (!els.viewNameError) return;
  els.viewNameError.hidden = !text;
  els.viewNameError.textContent = text;
}

function openManagedModal(modal, initialFocus) {
  if (!modal) return;
  modalReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  activeModal = modal;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  setPageInert(true, modal);
  requestAnimationFrame(() => {
    const target = initialFocus || modalFocusableElements(modal)[0] || modal;
    if (target && typeof target.focus === "function") {
      target.focus();
    }
  });
}

function closeManagedModal(modal) {
  if (!modal) return;
  modal.hidden = true;
  if (activeModal === modal) {
    activeModal = null;
  }
  document.body.classList.remove("modal-open");
  setPageInert(false, modal);
  const returnTarget = modalReturnFocus;
  modalReturnFocus = null;
  if (returnTarget && document.contains(returnTarget) && typeof returnTarget.focus === "function") {
    returnTarget.focus();
  }
}

function setPageInert(inert, modal) {
  [document.querySelector(".topbar"), document.querySelector(".workspace")]
    .filter((element) => element && element !== modal)
    .forEach((element) => {
      element.inert = Boolean(inert);
    });
}

function modalFocusableElements(modal) {
  return [...modal.querySelectorAll(MODAL_FOCUS_SELECTOR)].filter((element) => {
    const style = window.getComputedStyle(element);
    return style.visibility !== "hidden" && style.display !== "none";
  });
}

function trapModalFocus(event) {
  if (!activeModal || event.key !== "Tab") return;
  const focusable = modalFocusableElements(activeModal);
  if (!focusable.length) {
    event.preventDefault();
    activeModal.focus();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function renderWorkspaceImportPreview(preview, filename) {
  const review = preview?.review || {};
  const journal = preview?.journal || {};
  const preferences = preview?.preferences || {};
  const recovery = preview?.recovery || {};
  els.workspaceImportFilename.textContent = filename || "workspace snapshot";
  els.workspaceImportMetrics.innerHTML = [
    workspaceImportMetric("Incoming", review.imported_count || 0, "review items"),
    workspaceImportMetric("New", review.new_count || 0, "tickers"),
    workspaceImportMetric("Updated", review.updated_count || 0, "tickers"),
    workspaceImportMetric("Removed", review.removed_count || 0, "current tickers"),
  ].join("");
  const cleanupHtml = (review.duplicate_count || review.truncated_count)
    ? `<div class="workspace-import-note warning"><b>Cleanup</b><span>${escapeHtml(formatNumber(review.duplicate_count || 0))} duplicate · ${escapeHtml(formatNumber(review.truncated_count || 0))} over limit</span></div>`
    : "";
  const journalHtml = journal.will_replace
    ? `<div class="workspace-import-note"><b>Journal</b><span>${escapeHtml(formatNumber(journal.incoming_count || 0))} incoming · ${escapeHtml(formatNumber(journal.existing_count || 0))} existing</span></div>`
    : `<div class="workspace-import-note"><b>Journal</b><span>Unchanged</span></div>`;
  const recoveryHtml = recovery.quarantine_required
    ? `<div class="workspace-import-note warning"><b>Recovery</b><span>${escapeHtml(formatNumber(recovery.current_store_errors?.length || 0))} unreadable store${Number(recovery.current_store_errors?.length || 0) === 1 ? "" : "s"} will be quarantined before import</span></div>`
    : "";
  els.workspaceImportDetail.innerHTML = `
    <div class="workspace-import-note"><b>Profile</b><span>${escapeHtml(preview?.profile || "-")}</span></div>
    <div class="workspace-import-note"><b>Saved views</b><span>${escapeHtml(formatNumber(preferences.incoming_screener_view_count || 0))} screener · ${escapeHtml(formatNumber(preferences.incoming_review_view_count || 0))} review</span></div>
    ${journalHtml}
    ${recoveryHtml}
    ${cleanupHtml}
    ${workspaceImportTickers("New", review.new_tickers)}
    ${workspaceImportTickers("Updated", review.updated_tickers)}
    ${workspaceImportTickers("Removed", review.removed_tickers, "danger")}
  `;
}

function workspaceImportMetric(label, value, caption) {
  return `
    <div class="workspace-import-metric">
      <span>${escapeHtml(label)}</span>
      <b>${escapeHtml(formatNumber(value))}</b>
      <em>${escapeHtml(caption)}</em>
    </div>
  `;
}

function workspaceImportTickers(label, tickers, tone = "") {
  if (!Array.isArray(tickers) || !tickers.length) return "";
  return `
    <div class="workspace-import-tickers ${escapeHtml(tone)}">
      <b>${escapeHtml(label)}</b>
      <span>${tickers.slice(0, 12).map((ticker) => `<i>${escapeHtml(ticker)}</i>`).join("")}</span>
    </div>
  `;
}

async function openWorkspaceBackupModal() {
  pendingBackupRestoreFilename = "";
  pendingBackupDeleteFilename = "";
  state.workspaceAuditLimit = workspaceAuditBaseLimit();
  openManagedModal(els.workspaceBackupModal, els.workspaceBackupCloseButton);
  els.workspaceBackupSummary.textContent = "Loading backups";
  els.workspaceBackupList.innerHTML = `<div class="workspace-backup-empty">Loading backups</div>`;
  if (els.workspaceAuditList) {
    els.workspaceAuditList.innerHTML = `<div class="workspace-backup-empty">Loading operations</div>`;
  }
  await Promise.all([loadWorkspaceBackups(), loadWorkspaceAudit()]);
}

function closeWorkspaceBackupModal() {
  pendingBackupRestoreFilename = "";
  pendingBackupRestorePreview = null;
  pendingBackupDeleteFilename = "";
  closeManagedModal(els.workspaceBackupModal);
}

async function loadWorkspaceBackups() {
  try {
    const payload = await api("/api/workspace/backups", { profile: state.profile, limit: 12 });
    state.workspaceBackups = Array.isArray(payload.backups) ? payload.backups : [];
    const filenames = new Set(state.workspaceBackups.map((backup) => String(backup.filename || "")));
    if (pendingBackupRestoreFilename && !filenames.has(pendingBackupRestoreFilename)) {
      pendingBackupRestoreFilename = "";
      pendingBackupRestorePreview = null;
    }
    if (pendingBackupDeleteFilename && !filenames.has(pendingBackupDeleteFilename)) {
      pendingBackupDeleteFilename = "";
    }
    renderWorkspaceBackups();
  } catch (error) {
    state.workspaceBackups = [];
    renderWorkspaceBackups(userMessage(error));
  }
}

async function loadWorkspaceAudit() {
  if (!els.workspaceAuditList) return;
  const requestId = ++workspaceAuditRequestId;
  const auditQuery = cleanWorkspaceAuditQuery(state.workspaceAuditQuery);
  const auditCategory = String(state.workspaceAuditType || "");
  const limit = normalizeWorkspaceAuditLimit(state.workspaceAuditLimit);
  state.workspaceAuditLimit = limit;
  try {
    const payload = await api(
      "/api/workspace/audit",
      { limit, query: auditQuery, category: auditCategory },
    );
    if (requestId !== workspaceAuditRequestId) return;
    state.workspaceAudit = Array.isArray(payload.events) ? payload.events : [];
    state.workspaceAuditMeta = normalizeWorkspaceAuditMeta(payload);
    renderWorkspaceAudit();
  } catch (error) {
    if (requestId !== workspaceAuditRequestId) return;
    state.workspaceAudit = [];
    state.workspaceAuditMeta = null;
    renderWorkspaceAudit(userMessage(error));
  }
}

function renderWorkspaceBackups(error = "") {
  const backups = state.workspaceBackups || [];
  els.workspaceBackupSummary.textContent = error
    ? "Backup list unavailable"
    : `${formatNumber(backups.length)} recent backup${backups.length === 1 ? "" : "s"}`;
  if (error) {
    els.workspaceBackupList.innerHTML = `<div class="workspace-backup-empty">${escapeHtml(error)}</div>`;
    return;
  }
  if (!backups.length) {
    els.workspaceBackupList.innerHTML = `<div class="workspace-backup-empty">No backups yet</div>`;
    return;
  }
  els.workspaceBackupList.innerHTML = backups.map((backup) => {
    const filename = String(backup.filename || "");
    const pending = pendingBackupRestoreFilename === filename;
    const deleting = pendingBackupDeleteFilename === filename;
    const preview = pending ? pendingBackupRestorePreview : null;
    const fingerprint = backup.sha256_12 ? ` · sha ${backup.sha256_12}` : "";
    const rowClass = [
      "workspace-backup-row",
      preview ? "is-previewing" : "",
      deleting ? "is-deleting" : "",
    ].filter(Boolean).join(" ");
    return `
      <article class="${rowClass}">
        <div>
          <b>${escapeHtml(formatDateTime(backup.created_at))}</b>
          <span>${escapeHtml(backup.profile || state.profile)} · ${escapeHtml(formatNumber(backup.review_item_count || 0))} review · ${escapeHtml(formatNumber(backup.journal_entry_count || 0))} journal</span>
          <em>${escapeHtml(filename)} · ${escapeHtml(formatBytes(backup.size_bytes || 0))}${escapeHtml(fingerprint)}</em>
        </div>
        <div class="workspace-backup-actions">
          <button class="subtle" type="button" data-download-workspace-backup="${escapeHtml(filename)}">Download</button>
          <button class="${pending ? "danger" : "subtle"}" type="button" data-restore-workspace-backup="${escapeHtml(filename)}">
            ${pending && preview ? "Confirm restore" : pending ? "Checking" : "Restore"}
          </button>
          <button class="${deleting ? "danger" : "subtle"}" type="button" data-delete-workspace-backup="${escapeHtml(filename)}">
            ${deleting ? "Confirm delete" : "Delete"}
          </button>
        </div>
        ${preview ? renderWorkspaceRestorePreview(preview) : ""}
      </article>
    `;
  }).join("");
}

function renderWorkspaceAudit(error = "") {
  if (!els.workspaceAuditList) return;
  const events = state.workspaceAudit || [];
  syncWorkspaceAuditControls();
  if (error) {
    els.workspaceAuditList.innerHTML = `
      <div class="workspace-audit-error">
        <div>
          <b>Recent operations</b>
          <span>${escapeHtml(error)}</span>
        </div>
        <button class="subtle" type="button" data-repair-workspace-audit>Repair audit</button>
      </div>
    `;
    return;
  }
  const filteredEvents = filteredWorkspaceAuditEvents(events);
  const countLabel = workspaceAuditCountLabel(filteredEvents, events);
  if (!filteredEvents.length) {
    if (!workspaceAuditHasActiveFilter()) {
      els.workspaceAuditList.innerHTML = `<div class="workspace-audit-head"><b>Recent operations</b><span>No workspace operations yet</span></div>`;
      return;
    }
    els.workspaceAuditList.innerHTML = `
      <div class="workspace-audit-head">
        <b>Recent operations</b>
        <span>${escapeHtml(countLabel)}</span>
      </div>
      <div class="workspace-backup-empty">No matching operations</div>
    `;
    return;
  }
  const loadMoreButton = workspaceAuditHasMore(filteredEvents)
    ? `
      <div class="workspace-audit-more">
        <button class="subtle" type="button" data-load-more-workspace-audit>
          ${escapeHtml(workspaceAuditLoadMoreLabel(filteredEvents))}
        </button>
      </div>
    `
    : "";
  els.workspaceAuditList.innerHTML = `
    <div class="workspace-audit-head">
      <b>Recent operations</b>
      <span>${escapeHtml(countLabel)}</span>
    </div>
    ${filteredEvents.map((event) => {
      const details = workspaceAuditDetails(event);
      return `
      <div class="workspace-audit-row">
        <i>${escapeHtml(workspaceAuditActionLabel(event.action))}</i>
        <div>
          <b>${escapeHtml(event.summary || workspaceAuditActionLabel(event.action))}</b>
          <span>${escapeHtml(formatDateTime(event.at))}${event.profile ? ` · ${escapeHtml(event.profile)}` : ""}</span>
          ${details ? `<em>${details.map((item) => `<small>${escapeHtml(item)}</small>`).join("")}</em>` : ""}
        </div>
      </div>
    `;
    }).join("")}
    ${loadMoreButton}
  `;
}

function syncWorkspaceAuditControls() {
  const hasFilter = workspaceAuditHasActiveFilter();
  if (els.workspaceAuditSearch && els.workspaceAuditSearch.value !== state.workspaceAuditQuery) {
    els.workspaceAuditSearch.value = state.workspaceAuditQuery;
  }
  if (els.workspaceAuditType && els.workspaceAuditType.value !== state.workspaceAuditType) {
    els.workspaceAuditType.value = state.workspaceAuditType;
  }
  els.workspaceAuditSearch?.classList.toggle("is-active", Boolean(cleanWorkspaceAuditQuery(state.workspaceAuditQuery)));
  els.workspaceAuditType?.classList.toggle("is-active", Boolean(state.workspaceAuditType));
  if (els.workspaceAuditClearButton) {
    els.workspaceAuditClearButton.disabled = !hasFilter;
    els.workspaceAuditClearButton.classList.toggle("is-active", hasFilter);
  }
  if (els.workspaceAuditExportButton) {
    els.workspaceAuditExportButton.textContent = hasFilter ? "Download filtered" : "Download operations";
    els.workspaceAuditExportButton.title = hasFilter
      ? "Download matching workspace operations"
      : "Download workspace operations";
  }
}

function normalizeWorkspaceAuditMeta(payload) {
  return {
    query: String(payload?.query || ""),
    category: String(payload?.category || ""),
    limit: Number(payload?.limit || 0),
    total_count: Number(payload?.total_count ?? 0),
    filtered_count: Number(payload?.filtered_count ?? 0),
  };
}

function workspaceAuditBaseLimit() {
  return workspaceAuditHasActiveFilter() ? WORKSPACE_AUDIT_FILTER_LIMIT : WORKSPACE_AUDIT_DEFAULT_LIMIT;
}

function normalizeWorkspaceAuditLimit(value) {
  const number = Number(value);
  const requested = Number.isFinite(number) ? Math.floor(number) : workspaceAuditBaseLimit();
  return Math.max(
    workspaceAuditBaseLimit(),
    Math.min(WORKSPACE_AUDIT_MAX_LIMIT, requested),
  );
}

function workspaceAuditHasActiveFilter() {
  return Boolean(cleanWorkspaceAuditQuery(state.workspaceAuditQuery) || state.workspaceAuditType);
}

function workspaceAuditShownTargetCount() {
  const meta = state.workspaceAuditMeta || {};
  const filteredCount = Number(meta.filtered_count);
  if (Number.isFinite(filteredCount)) return filteredCount;
  const totalCount = Number(meta.total_count);
  return Number.isFinite(totalCount) ? totalCount : (state.workspaceAudit || []).length;
}

function workspaceAuditHasMore(events) {
  const shown = Array.isArray(events) ? events.length : 0;
  return shown < workspaceAuditShownTargetCount() && shown < WORKSPACE_AUDIT_MAX_LIMIT;
}

function workspaceAuditLoadMoreLabel(events) {
  const shown = Array.isArray(events) ? events.length : 0;
  const remaining = Math.max(0, workspaceAuditShownTargetCount() - shown);
  const nextCount = Math.min(WORKSPACE_AUDIT_LIMIT_STEP, remaining);
  return `Show ${formatNumber(nextCount)} more`;
}

function workspaceAuditCountLabel(filteredEvents, sourceEvents) {
  const shown = Array.isArray(filteredEvents) ? filteredEvents.length : 0;
  const sourceCount = Array.isArray(sourceEvents) ? sourceEvents.length : shown;
  const meta = state.workspaceAuditMeta || {};
  const filteredCount = Number.isFinite(meta.filtered_count) ? meta.filtered_count : shown;
  const totalCount = Number.isFinite(meta.total_count) ? meta.total_count : sourceCount;
  if (workspaceAuditHasActiveFilter()) {
    const matchWord = filteredCount === 1 ? "match" : "matches";
    return `${formatNumber(shown)} of ${formatNumber(filteredCount)} ${matchWord}`;
  }
  if (totalCount > shown) {
    return `${formatNumber(shown)} of ${formatNumber(totalCount)} events`;
  }
  return `${formatNumber(shown)} event${shown === 1 ? "" : "s"}`;
}

function filteredWorkspaceAuditEvents(events) {
  const type = String(state.workspaceAuditType || "");
  const query = cleanWorkspaceAuditQuery(state.workspaceAuditQuery).toLowerCase();
  return events.filter((event) => {
    if (type && workspaceAuditCategory(event.action) !== type) return false;
    return workspaceAuditMatchesQuery(event, query);
  });
}

function cleanWorkspaceAuditQuery(value) {
  return String(value || "").trim().replace(/\s+/g, " ").slice(0, 80);
}

function workspaceAuditCategory(action) {
  const normalized = String(action || "");
  if (normalized === "artifact_download" || normalized.includes("download") || normalized.endsWith("_export")) {
    return "download";
  }
  if (["cleanup_temp_files", "repair_audit_store"].includes(normalized)) {
    return "maintenance";
  }
  return "workspace";
}

function workspaceAuditMatchesQuery(event, query) {
  if (!query) return true;
  const detail = event?.detail || {};
  const detailValues = Object.values(detail).map((value) => String(value || ""));
  const haystack = [
    workspaceAuditActionLabel(event?.action),
    event?.action,
    event?.summary,
    event?.profile,
    event?.at,
    ...workspaceAuditDetails(event),
    ...detailValues,
  ].join(" ").toLowerCase();
  return haystack.includes(query);
}

function workspaceAuditActionLabel(action) {
  const labels = {
    artifact_download: "Artifact",
    import_workspace: "Import",
    restore_backup: "Restore",
    delete_backup: "Delete",
    cleanup_temp_files: "Cleanup",
    repair_audit_store: "Repair",
    review_queue_export: "Review",
    screener_export: "Screener",
    session_report_export: "Report",
    stock_dossier_export: "Dossier",
    support_bundle_export: "Support",
    workspace_audit_export: "Audit",
    workspace_backup_download: "Backup",
    workspace_snapshot_export: "Snapshot",
  };
  return labels[String(action || "")] || String(action || "Operation").replaceAll("_", " ");
}

function workspaceAuditDetails(event) {
  const detail = event?.detail || {};
  const parts = [];
  if (detail.filename) parts.push(detail.filename);
  if (detail.artifact_id) parts.push(`artifact ${detail.artifact_id}`);
  if (detail.format) parts.push(`format ${detail.format}`);
  if (detail.ticker) parts.push(String(detail.ticker).toUpperCase());
  if (detail.route) parts.push(detail.route);
  if (detail.sha256_12) parts.push(`sha ${detail.sha256_12}`);
  if (Number.isFinite(Number(detail.size_bytes))) parts.push(formatBytes(Number(detail.size_bytes)));
  if (Number.isFinite(Number(detail.deleted_count))) parts.push(`${formatNumber(detail.deleted_count)} deleted`);
  if (Number.isFinite(Number(detail.failed_count))) parts.push(`${formatNumber(detail.failed_count)} failed`);
  if (detail.quarantined_store_count !== undefined) parts.push(`${formatNumber(detail.quarantined_store_count)} quarantined`);
  return parts.filter(Boolean).slice(0, 6);
}

function renderWorkspaceRestorePreview(preview) {
  const review = preview?.review || {};
  const journal = preview?.journal || {};
  const recovery = preview?.recovery || {};
  return `
    <div class="workspace-backup-preview">
      <span><b>${escapeHtml(formatNumber(review.imported_count || 0))}</b> incoming</span>
      <span><b>${escapeHtml(formatNumber(review.new_count || 0))}</b> new</span>
      <span><b>${escapeHtml(formatNumber(review.updated_count || 0))}</b> updated</span>
      <span class="${Number(review.removed_count || 0) ? "danger" : ""}"><b>${escapeHtml(formatNumber(review.removed_count || 0))}</b> removed</span>
      <span><b>${escapeHtml(formatNumber(journal.incoming_count || 0))}</b> journal</span>
      ${recovery.quarantine_required ? `<span class="danger"><b>${escapeHtml(formatNumber(recovery.current_store_errors?.length || 0))}</b> quarantine</span>` : ""}
    </div>
  `;
}

function workspaceBackupStatusDetail(backup) {
  if (!backup?.filename) return "";
  return backup.recovery_only ? `Recovery saved: ${backup.filename}` : `Backup saved: ${backup.filename}`;
}

async function downloadWorkspaceBackup(filename) {
  const normalized = String(filename || "");
  if (!normalized) return;
  const url = new URL("/api/workspace/backups/download", window.location.origin);
  url.searchParams.set("filename", normalized);
  await triggerDownload(url, normalized);
}

async function exportWorkspaceAudit() {
  const url = new URL("/api/workspace/audit/export", window.location.origin);
  url.searchParams.set("limit", "120");
  const auditQuery = cleanWorkspaceAuditQuery(state.workspaceAuditQuery);
  if (auditQuery) url.searchParams.set("query", auditQuery);
  if (state.workspaceAuditType) url.searchParams.set("category", state.workspaceAuditType);
  await triggerDownload(url, "canslim-workspace-audit.json");
}

function scheduleWorkspaceAuditReload() {
  clearTimeout(workspaceAuditFilterTimer);
  workspaceAuditFilterTimer = setTimeout(loadWorkspaceAudit, 180);
}

function clearWorkspaceAuditFilters() {
  if (!workspaceAuditHasActiveFilter()) return;
  state.workspaceAuditQuery = "";
  state.workspaceAuditType = "";
  state.workspaceAuditMeta = null;
  state.workspaceAuditLimit = workspaceAuditBaseLimit();
  renderWorkspaceAudit();
  loadWorkspaceAudit();
}

async function loadMoreWorkspaceAudit() {
  state.workspaceAuditLimit = normalizeWorkspaceAuditLimit(state.workspaceAuditLimit + WORKSPACE_AUDIT_LIMIT_STEP);
  renderWorkspaceAudit();
  await loadWorkspaceAudit();
}

async function restoreWorkspaceBackup(filename) {
  const normalized = String(filename || "");
  if (!normalized) return;
  if (pendingBackupRestoreFilename !== normalized) {
    pendingBackupRestoreFilename = normalized;
    pendingBackupRestorePreview = null;
    pendingBackupDeleteFilename = "";
    renderWorkspaceBackups();
    setAppStatus("syncing", "Checking restore");
    try {
      pendingBackupRestorePreview = await api("/api/workspace/backups/preview", { filename: normalized });
      renderWorkspaceBackups();
      setAppStatus("syncing", "Confirm restore", "Review restore impact, then click Confirm restore");
    } catch (error) {
      pendingBackupRestoreFilename = "";
      pendingBackupRestorePreview = null;
      renderWorkspaceBackups();
      setAppStatus("error", "Restore check failed", userMessage(error));
    }
    return;
  }
  if (!pendingBackupRestorePreview) return;
  setLoading(true);
  setAppStatus("syncing", "Restoring backup");
  try {
    const expectedSha = String(pendingBackupRestorePreview?.backup?.sha256_12 || "");
    const payload = await api(
      "/api/workspace/backups/restore",
      {},
      { method: "POST", body: { filename: normalized, confirm: "restore", expected_sha256_12: expectedSha } },
    );
    applyWorkspacePreferences(payload.preferences);
    applyReviewPayload(payload.review);
    state.reviewSummary = payload.review_summary;
    state.profile = payload.profile;
    state.analysis = null;
    state.selectedCompareTickers.clear();
    closeWorkspaceBackupModal();
    await loadDashboard();
    const quarantinedCount = Array.isArray(payload.quarantined_stores) ? payload.quarantined_stores.length : 0;
    setAppStatus(
      "online",
      `Restored backup`,
      quarantinedCount
        ? `Quarantined ${quarantinedCount} corrupt store${quarantinedCount === 1 ? "" : "s"}`
        : payload.backup?.filename ? workspaceBackupStatusDetail(payload.backup) : `Restored from ${normalized}`,
    );
  } catch (error) {
    setAppStatus("error", "Restore failed", userMessage(error));
    pendingBackupRestoreFilename = "";
    await loadWorkspaceBackups();
  } finally {
    setLoading(false);
  }
}

async function deleteWorkspaceBackup(filename) {
  const normalized = String(filename || "");
  if (!normalized) return;
  const backup = state.workspaceBackups.find((item) => String(item.filename || "") === normalized) || {};
  if (pendingBackupDeleteFilename !== normalized) {
    pendingBackupDeleteFilename = normalized;
    pendingBackupRestoreFilename = "";
    pendingBackupRestorePreview = null;
    renderWorkspaceBackups();
    setAppStatus("syncing", "Confirm delete", "Click Confirm delete to remove the backup file");
    return;
  }
  setLoading(true);
  setAppStatus("syncing", "Deleting backup");
  try {
    const expectedSha = String(backup.sha256_12 || "");
    const payload = await api(
      "/api/workspace/backups",
      {},
      { method: "DELETE", body: { filename: normalized, confirm: "delete", expected_sha256_12: expectedSha } },
    );
    pendingBackupDeleteFilename = "";
    state.workspaceBackups = state.workspaceBackups.filter((item) => String(item.filename || "") !== normalized);
    renderWorkspaceBackups();
    await loadWorkspaceAudit();
    setAppStatus("online", "Backup deleted", payload.backup?.sha256_12 ? `sha ${payload.backup.sha256_12}` : normalized);
  } catch (error) {
    pendingBackupDeleteFilename = "";
    setAppStatus("error", "Delete failed", userMessage(error));
    await loadWorkspaceBackups();
  } finally {
    setLoading(false);
  }
}

function formatWorkspaceImportPreview(preview, filename) {
  const review = preview?.review || {};
  const journal = preview?.journal || {};
  const preferences = preview?.preferences || {};
  const lines = [
    `Import ${filename || "workspace snapshot"}?`,
    "",
    `Profile: ${preview?.profile || "-"}`,
    `Review queue: ${formatNumber(review.imported_count || 0)} incoming, ${formatNumber(review.new_count || 0)} new, ${formatNumber(review.updated_count || 0)} updated, ${formatNumber(review.removed_count || 0)} removed`,
  ];
  if (review.duplicate_count || review.truncated_count) {
    lines.push(
      `Review cleanup: ${formatNumber(review.duplicate_count || 0)} duplicate, ${formatNumber(review.truncated_count || 0)} over limit`,
    );
  }
  if (journal.will_replace) {
    lines.push(
      `Journal: ${formatNumber(journal.incoming_count || 0)} incoming, ${formatNumber(journal.existing_count || 0)} existing`,
    );
  } else {
    lines.push("Journal: unchanged");
  }
  if (preview?.recovery?.quarantine_required) {
    lines.push(
      `Recovery: ${formatNumber(preview.recovery.current_store_errors?.length || 0)} unreadable store(s) will be quarantined`,
    );
  }
  lines.push(
    `Saved views: ${formatNumber(preferences.incoming_screener_view_count || 0)} screener, ${formatNumber(preferences.incoming_review_view_count || 0)} review`,
    "",
    "This will replace the current workspace state for the imported profile.",
  );
  return lines.join("\n");
}

function reviewRiskParams() {
  const risk = currentWorkspacePreferences().risk;
  return {
    profile: state.profile,
    account_equity: risk.account_equity,
    risk_pct: risk.risk_pct,
    max_capital_pct: risk.max_capital_pct,
    max_queue_risk_pct: risk.max_queue_risk_pct,
    max_open_position_risk_pct: risk.max_open_position_risk_pct,
    max_concentration_pct: risk.max_concentration_pct,
    max_open_concentration_pct: risk.max_open_concentration_pct,
  };
}

function updateReviewSort(sortBy) {
  const normalized = normalizeReviewSortBy(sortBy);
  if (state.reviewSortBy === normalized) {
    state.reviewSortDir = state.reviewSortDir === "asc" ? "desc" : "asc";
  } else {
    state.reviewSortBy = normalized;
    state.reviewSortDir = REVIEW_SORT_DEFAULT_DIR[normalized] || "desc";
  }
  els.reviewSortSelect.value = state.reviewSortBy;
  renderReviewSortDirection();
  renderReviewQueue();
  saveWorkspacePreferencesDebounced();
}

function renderReviewSortDirection() {
  const isAsc = state.reviewSortDir === "asc";
  els.reviewSortDirection.textContent = isAsc ? "↑" : "↓";
  els.reviewSortDirection.dataset.dir = state.reviewSortDir;
  els.reviewSortDirection.title = isAsc ? "Ascending" : "Descending";
}

function updateReviewStatusFilter(status) {
  state.reviewStatus = normalizeReviewStatus(status);
  els.reviewStatusFilter.value = state.reviewStatus;
  renderReviewQueue();
  saveWorkspacePreferencesDebounced();
}

function updateReviewPriorityFilter(priority) {
  state.reviewPriority = normalizeReviewPriorityFilter(priority);
  els.reviewPriorityFilter.value = state.reviewPriority;
  renderReviewQueue();
  saveWorkspacePreferencesDebounced();
}

function updateReviewTagFilter(tag) {
  state.reviewTag = normalizeReviewTag(tag);
  renderReviewQueue();
  saveWorkspacePreferencesDebounced();
}

function updateReviewQueryFilter(query) {
  state.reviewQuery = cleanReviewQuery(query);
  els.reviewSearchInput.value = state.reviewQuery;
  renderReviewQueue();
  saveWorkspacePreferencesDebounced();
}

function clearReviewFilters() {
  if (!reviewFiltersActive()) return;
  state.reviewQuery = "";
  state.reviewStatus = "";
  state.reviewPriority = "";
  state.reviewTag = "";
  els.reviewSearchInput.value = "";
  els.reviewStatusFilter.value = "";
  els.reviewPriorityFilter.value = "";
  els.reviewTagFilter.value = "";
  renderReviewQueue();
  saveWorkspacePreferencesDebounced();
}

function reviewFiltersActive() {
  return Boolean(
    cleanReviewQuery(state.reviewQuery)
    || normalizeReviewStatus(state.reviewStatus)
    || normalizeReviewPriorityFilter(state.reviewPriority)
    || normalizeReviewTag(state.reviewTag),
  );
}

function findCandidateByTicker(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  const pools = [
    state.screener?.candidates || [],
    state.overview?.top_candidates || [],
    state.overview?.action_center?.focus_candidates || [],
  ];
  return pools.flat().find((row) => String(row.ticker || "").toUpperCase() === normalized) || { ticker: normalized };
}

function actionCandidateByTicker(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  const candidate = (state.overview?.action_center?.focus_candidates || []).find(
    (row) => String(row.ticker || "").toUpperCase() === normalized,
  );
  return candidate ? resolveCandidateForReview(candidate) : null;
}

function priorityActionCandidates() {
  const candidates = state.overview?.action_center?.focus_candidates || [];
  const priorityActions = new Set(["actionable", "watch_breakout"]);
  return candidates.filter((candidate) => priorityActions.has(candidate.action)).map(resolveCandidateForReview);
}

function resolveCandidateForReview(candidate) {
  const ticker = String(candidate?.ticker || "").toUpperCase();
  if (!ticker) return candidate;
  const fromScreener = (state.screener?.candidates || []).find((row) => String(row.ticker || "").toUpperCase() === ticker);
  const fromOverview = (state.overview?.top_candidates || []).find((row) => String(row.ticker || "").toUpperCase() === ticker);
  return { ...(fromOverview || {}), ...(fromScreener || {}), ...candidate, ticker };
}

function isQueued(ticker) {
  const normalized = String(ticker || "").toUpperCase();
  return state.reviewQueue.some((item) => item.ticker === normalized);
}

function applyLocalReviewBucket(profile = state.profile) {
  const bucket = loadReviewBucket(profile);
  state.reviewQueue = bucket.items;
  state.reviewActivity = bucket.activity;
  pruneReviewSelection();
  renderReviewActivity();
}

function loadReviewBucket(profile = state.profile) {
  try {
    const store = loadReviewStore();
    const bucket = store.profiles?.[reviewStorageProfile(profile)] || {};
    return {
      items: Array.isArray(bucket.items) ? bucket.items.filter((item) => item?.ticker).slice(0, 50) : [],
      activity: Array.isArray(bucket.activity) ? bucket.activity.slice(0, 10) : [],
    };
  } catch (error) {
    return { items: [], activity: [] };
  }
}

function applyReviewPayload(payload) {
  state.reviewQueue = Array.isArray(payload?.items) ? payload.items.slice(0, 50) : [];
  state.reviewActivity = Array.isArray(payload?.activity) ? payload.activity.slice(0, 10) : state.reviewActivity;
  pruneReviewSelection();
  saveReviewQueue();
  renderReviewActivity();
}

function saveReviewQueue() {
  try {
    const store = loadReviewStore();
    const profile = reviewStorageProfile(state.profile);
    store.profiles[profile] = {
      items: state.reviewQueue.slice(0, 50),
      activity: state.reviewActivity.slice(0, 10),
      updated_at: new Date().toISOString(),
    };
    localStorage.setItem(REVIEW_STORAGE_KEY, JSON.stringify(store));
  } catch (error) {
    // Local persistence is optional; the in-memory queue still works.
  }
}

function loadReviewStore() {
  const parsed = JSON.parse(localStorage.getItem(REVIEW_STORAGE_KEY) || "{}");
  if (Array.isArray(parsed)) {
    return {
      version: 2,
      profiles: {
        canslim_score_rank: {
          items: parsed.filter((item) => item?.ticker).slice(0, 50),
          activity: [],
        },
      },
    };
  }
  const profiles = parsed && typeof parsed === "object" && parsed.profiles && typeof parsed.profiles === "object"
    ? parsed.profiles
    : {};
  return { version: 2, profiles };
}

function reviewStorageProfile(profile) {
  const normalized = String(profile || "canslim_score_rank").trim();
  return /^[A-Za-z0-9_-]+$/.test(normalized) ? normalized : "canslim_score_rank";
}

function renderStatusOptions(selectedStatus) {
  return REVIEW_STATUS_OPTIONS.map(([value, label]) => {
    const selected = value === selectedStatus ? "selected" : "";
    return `<option value="${escapeHtml(value)}" ${selected}>${escapeHtml(label)}</option>`;
  }).join("");
}

function renderPriorityOptions(selectedPriority) {
  return REVIEW_PRIORITY_OPTIONS.map(([value, label]) => {
    const selected = value === selectedPriority ? "selected" : "";
    return `<option value="${escapeHtml(value)}" ${selected}>${escapeHtml(label)}</option>`;
  }).join("");
}

function reviewStatusLabel(status) {
  const match = REVIEW_STATUS_OPTIONS.find(([value]) => value === status);
  return match ? match[1] : "Watch";
}

function normalizeReviewPriority(value) {
  const normalized = String(value || "normal").toLowerCase();
  return REVIEW_PRIORITY_OPTIONS.some(([allowed]) => allowed === normalized) ? normalized : "normal";
}

function reviewPriorityLabel(priority) {
  const normalized = normalizeReviewPriority(priority);
  const match = REVIEW_PRIORITY_OPTIONS.find(([value]) => value === normalized);
  return match ? match[1] : "Normal";
}

function reviewPriorityRank(priority) {
  const ranks = { high: 0, normal: 1, low: 2 };
  return ranks[normalizeReviewPriority(priority)] ?? ranks.normal;
}

function drawPriceChart(points, ticker, tradePlan = {}) {
  const canvas = els.priceCanvas;
  const { ctx, width, height } = prepareCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#f7fafb";
  ctx.fillRect(0, 0, width, height);
  drawGrid(ctx, width, height);

  if (!points.length) {
    ctx.fillStyle = "#5d6673";
    ctx.font = "18px Avenir Next, sans-serif";
    ctx.fillText(`${ticker || "Ticker"} price history unavailable`, 28, 48);
    return;
  }

  const values = points.map((point) => Number(point.close)).filter(Number.isFinite);
  const overlayValues = tradePlanValues(tradePlan);
  const min = Math.min(...values, ...overlayValues);
  const max = Math.max(...values, ...overlayValues);
  const pad = 24;
  const span = max - min || 1;
  const yFor = (value) => height - pad - ((Number(value) - min) / span) * (height - pad * 2);
  drawTradePlanOverlay(ctx, tradePlan, yFor, width, height, pad);
  const coords = points.map((point, index) => {
    const x = pad + (index / Math.max(points.length - 1, 1)) * (width - pad * 2);
    const y = yFor(point.close);
    return [x, y];
  });

  ctx.beginPath();
  coords.forEach(([x, y], index) => {
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineWidth = 3;
  ctx.strokeStyle = values.at(-1) >= values[0] ? "#107c55" : "#bb3e35";
  ctx.stroke();

  const gradient = ctx.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, "rgba(16, 124, 85, 0.18)");
  gradient.addColorStop(1, "rgba(16, 124, 85, 0)");
  ctx.lineTo(width - pad, height - pad);
  ctx.lineTo(pad, height - pad);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  ctx.fillStyle = "#121417";
  ctx.font = "17px Avenir Next, sans-serif";
  ctx.fillText(`${ticker} · ${formatCurrency(values.at(-1))}`, 26, 34);
  ctx.fillStyle = "#5d6673";
  ctx.font = "13px Avenir Next, sans-serif";
  ctx.fillText(`${formatCurrency(min)} - ${formatCurrency(max)}`, 26, height - 18);
}

function prepareCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const fallbackWidth = Number(canvas.getAttribute("width")) || canvas.width || 760;
  const fallbackHeight = Number(canvas.getAttribute("height")) || canvas.height || 260;
  const cssWidth = Math.max(1, Math.round(rect.width || fallbackWidth));
  const cssHeight = Math.max(1, Math.round(rect.height || fallbackHeight));
  const scale = Math.max(1, window.devicePixelRatio || 1);
  const targetWidth = Math.round(cssWidth * scale);
  const targetHeight = Math.round(cssHeight * scale);
  if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
    canvas.width = targetWidth;
    canvas.height = targetHeight;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  return { ctx, width: cssWidth, height: cssHeight };
}

function drawTradePlanOverlay(ctx, plan, yFor, width, height, pad) {
  const buyZone = normalizedBand(plan.buy_zone_low, plan.buy_zone_high);
  const targetZone = normalizedBand(plan.profit_target_low, plan.profit_target_high);
  if (buyZone) {
    drawPriceBand(ctx, buyZone, "Buy zone", "#aa7600", "rgba(170, 118, 0, 0.12)", yFor, width, height, pad);
  }
  if (targetZone) {
    drawPriceBand(ctx, targetZone, "Target", "#107c55", "rgba(16, 124, 85, 0.08)", yFor, width, height, pad);
  }
  drawPriceLevel(ctx, plan.pivot_price, "Pivot", "#1d5f96", yFor, width, height, pad, [6, 5]);
  drawPriceLevel(ctx, plan.stop_loss_price, "Stop", "#bb3e35", yFor, width, height, pad);
}

function drawPriceBand(ctx, band, label, color, fill, yFor, width, height, pad) {
  const top = clamp(yFor(band.high), pad, height - pad);
  const bottom = clamp(yFor(band.low), pad, height - pad);
  const bandHeight = Math.max(2, bottom - top);
  ctx.save();
  ctx.fillStyle = fill;
  ctx.fillRect(pad, top, width - pad * 2, bandHeight);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  [top, bottom].forEach((y) => {
    ctx.beginPath();
    ctx.moveTo(pad, y);
    ctx.lineTo(width - pad, y);
    ctx.stroke();
  });
  ctx.restore();
  drawLevelLabel(ctx, `${label} ${formatRange(band.low, band.high)}`, color, top + bandHeight / 2, width, height, pad);
}

function drawPriceLevel(ctx, value, label, color, yFor, width, height, pad, dash = []) {
  const price = numericValue(value);
  if (price === null) return;
  const y = clamp(yFor(price), pad, height - pad);
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.setLineDash(dash);
  ctx.beginPath();
  ctx.moveTo(pad, y);
  ctx.lineTo(width - pad, y);
  ctx.stroke();
  ctx.restore();
  drawLevelLabel(ctx, `${label} ${formatCurrency(price)}`, color, y, width, height, pad);
}

function drawLevelLabel(ctx, label, color, y, width, height, pad) {
  ctx.save();
  ctx.font = "11px Avenir Next, sans-serif";
  const textWidth = ctx.measureText(label).width;
  const boxWidth = textWidth + 10;
  const boxHeight = 18;
  const x = width - pad - boxWidth;
  const boxY = clamp(y - boxHeight / 2, pad + 2, height - pad - boxHeight);
  ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
  ctx.fillRect(x, boxY, boxWidth, boxHeight);
  ctx.strokeStyle = color;
  ctx.strokeRect(x, boxY, boxWidth, boxHeight);
  ctx.fillStyle = color;
  ctx.fillText(label, x + 5, boxY + 13);
  ctx.restore();
}

function normalizedBand(low, high) {
  const lowValue = numericValue(low);
  const highValue = numericValue(high);
  if (lowValue === null || highValue === null) return null;
  return { low: Math.min(lowValue, highValue), high: Math.max(lowValue, highValue) };
}

function tradePlanValues(plan) {
  return [
    plan.pivot_price,
    plan.buy_zone_low,
    plan.buy_zone_high,
    plan.stop_loss_price,
    plan.profit_target_low,
    plan.profit_target_high,
  ].map(numericValue).filter((value) => value !== null && value > 0);
}

function drawScoreDial(score, label) {
  const canvas = els.scoreCanvas;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const center = width / 2;
  const radius = 72;
  ctx.clearRect(0, 0, width, height);
  ctx.lineWidth = 14;
  ctx.strokeStyle = "#e8edf2";
  ctx.beginPath();
  ctx.arc(center, height / 2, radius, 0, Math.PI * 2);
  ctx.stroke();

  const end = -Math.PI / 2 + Math.PI * 2 * clamp(score / 100, 0, 1);
  ctx.strokeStyle = label === "exceptional" ? "#107c55" : score >= 70 ? "#1d5f96" : "#bb3e35";
  ctx.beginPath();
  ctx.arc(center, height / 2, radius, -Math.PI / 2, end);
  ctx.stroke();
}

function drawGrid(ctx, width, height) {
  ctx.strokeStyle = "#d6dce3";
  ctx.lineWidth = 1;
  for (let x = 0; x <= width; x += 76) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }
  for (let y = 0; y <= height; y += 52) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
}

function makeComponents(result) {
  return {
    c: result.c_score,
    a: result.a_score,
    n: result.n_score,
    s: result.s_score,
    l: result.l_score,
    i: result.i_score,
    m: result.m_score,
  };
}

function makeResearchBrief(result) {
  return {
    action: result.in_buy_zone ? "actionable" : result.extended_from_pivot ? "extended" : result.setup_status === "near_pivot" ? "watch_breakout" : "research",
    trade_plan: {
      current_price: result.current_price,
      pivot_price: result.pivot_price,
      pivot_distance_pct: result.pivot_distance_pct,
      buy_zone_low: result.buy_zone_low,
      buy_zone_high: result.buy_zone_high,
      in_buy_zone: result.in_buy_zone,
      extended_from_pivot: result.extended_from_pivot,
      stop_loss_price: result.stop_loss_price,
      profit_target_low: result.profit_target_low,
      profit_target_high: result.profit_target_high,
    },
    setup: {
      status: result.setup_status,
      type: result.setup_type,
      reasons: result.setup_reasons || [],
    },
    score: {
      strongest_components: [],
    },
    reasons: {
      watch: result.fail_reasons || [],
    },
  };
}

function formatPercent(value, options = {}) {
  if (isBlank(value)) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const sign = options.signed !== false && number > 0 ? "+" : "";
  return `${sign}${(number * 100).toFixed(1)}%`;
}

function formatSummaryPercent(value) {
  if (isBlank(value)) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number.toFixed(1)}%`;
}

function formatRMultiple(value) {
  if (isBlank(value)) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number.toFixed(2)}R`;
}

function formatRatio(value) {
  if (isBlank(value)) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(2).replace(/\.?0+$/, "");
}

function formatScore(value) {
  if (isBlank(value)) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(number >= 10 ? 1 : 2).replace(/\.0$/, "");
}

function formatNumber(value, suffix = "") {
  if (isBlank(value)) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const digits = Math.abs(number) >= 100 ? 0 : 2;
  return `${number.toLocaleString(undefined, { maximumFractionDigits: digits })}${suffix}`;
}

function formatCurrency(value) {
  if (isBlank(value)) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `$${number.toLocaleString(undefined, { maximumFractionDigits: number >= 100 ? 0 : 2 })}`;
}

function formatInputNumber(value) {
  if (isBlank(value)) return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number.toFixed(2).replace(/\.?0+$/, "");
}

function formatInputShares(value) {
  if (isBlank(value)) return "";
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return "";
  return String(Math.floor(number));
}

function formatDateInput(value) {
  if (isBlank(value)) return "";
  const text = String(value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 10);
}

function formatMoney(value) {
  if (isBlank(value)) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (Math.abs(number) >= 1_000_000_000_000) return `$${(number / 1_000_000_000_000).toFixed(2)}T`;
  if (Math.abs(number) >= 1_000_000_000) return `$${(number / 1_000_000_000).toFixed(2)}B`;
  if (Math.abs(number) >= 1_000_000) return `$${(number / 1_000_000).toFixed(1)}M`;
  return formatCurrency(number);
}

function formatBytes(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return "-";
  if (number >= 1_000_000_000) return `${(number / 1_000_000_000).toFixed(2)} GB`;
  if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(1)} MB`;
  if (number >= 1_000) return `${(number / 1_000).toFixed(1)} KB`;
  return `${Math.round(number)} B`;
}

function formatRange(low, high) {
  if (isBlank(low) || isBlank(high)) return "-";
  if (!Number.isFinite(Number(low)) || !Number.isFinite(Number(high))) return "-";
  return `${formatCurrency(low)}-${formatCurrency(high)}`;
}

function calculatePositionSize(plan = {}) {
  const entry = numericValue(plan.buy_zone_low) ?? numericValue(plan.pivot_price);
  const stop = numericValue(plan.stop_loss_price);
  const equity = Number(state.risk?.account_equity);
  const riskPct = Number(state.risk?.risk_pct);
  const riskAmount = equity * (riskPct / 100);
  const riskPerShare = entry - stop;
  if (
    !Number.isFinite(entry) ||
    !Number.isFinite(stop) ||
    !Number.isFinite(riskAmount) ||
    entry <= 0 ||
    riskPerShare <= 0 ||
    riskAmount <= 0
  ) {
    return {
      riskAmount: Number.isFinite(riskAmount) && riskAmount > 0 ? riskAmount : null,
      riskPerShare: Number.isFinite(riskPerShare) && riskPerShare > 0 ? riskPerShare : null,
      shares: null,
      plannedCapital: null,
    };
  }
  const shares = Math.floor(riskAmount / riskPerShare);
  return { riskAmount, riskPerShare, shares, plannedCapital: shares > 0 ? shares * entry : null };
}

function calculateExecution(item = {}) {
  const price = numericValue(item.execution_price);
  const shares = numericValue(item.execution_shares);
  if (!Number.isFinite(price) || !Number.isFinite(shares) || price <= 0 || shares <= 0) {
    return { recorded: false, price, shares, value: 0, valueLabel: "Fill -" };
  }
  const roundedShares = Math.floor(shares);
  const value = roundedShares * price;
  return {
    recorded: roundedShares > 0,
    price,
    shares: roundedShares,
    value,
    valueLabel: `Fill ${formatCurrency(value)}`,
  };
}

function calculateExit(item = {}) {
  const execution = calculateExecution(item);
  const exitPrice = numericValue(item.exit_price);
  const exitShares = numericValue(item.exit_shares) ?? execution.shares;
  if (
    !execution.recorded
    || !Number.isFinite(exitPrice)
    || !Number.isFinite(exitShares)
    || exitPrice <= 0
    || exitShares <= 0
  ) {
    return {
      recorded: false,
      price: exitPrice,
      shares: Number.isFinite(exitShares) ? Math.floor(exitShares) : null,
      value: 0,
      pnl: 0,
      pnlPct: null,
      rMultiple: null,
      entryValue: 0,
      pnlClass: "flat",
      label: "Realized -",
    };
  }
  const roundedShares = Math.floor(exitShares);
  const value = exitPrice * roundedShares;
  const entryValue = execution.price * roundedShares;
  const pnl = (exitPrice - execution.price) * roundedShares;
  const pnlPct = execution.price > 0 ? ((exitPrice - execution.price) / execution.price) * 100 : null;
  const stop = numericValue(item.stop_loss_price);
  const riskPerShare = Number.isFinite(stop) ? execution.price - stop : null;
  const rMultiple = riskPerShare && riskPerShare > 0 ? (exitPrice - execution.price) / riskPerShare : null;
  const pnlClass = pnl > 0 ? "up" : pnl < 0 ? "down" : "flat";
  const rLabel = Number.isFinite(rMultiple) ? `${rMultiple.toFixed(2)}R` : "R -";
  return {
    recorded: true,
    price: exitPrice,
    shares: roundedShares,
    value,
    pnl,
    pnlPct,
    rMultiple,
    entryValue,
    pnlClass,
    label: `Realized ${formatCurrency(pnl)} · ${formatSummaryPercent(pnlPct)} · ${rLabel}`,
  };
}

function calculatePositionMonitor(item = {}) {
  if ((normalizeReviewStatus(item.decision_status) || "watch") === "sold") {
    return {
      monitored: false,
      pnl: 0,
      pnlPct: null,
      rMultiple: null,
      stopDistancePct: null,
      lastPrice: null,
      alertStatus: "not_applicable",
      alertReason: "",
      alertSignature: "",
      alertAcknowledged: false,
      alertAcknowledgedAt: "",
      pnlClass: "flat",
      label: "Closed",
    };
  }
  const execution = calculateExecution(item);
  const lastPrice = numericValue(item.current_price);
  if (!execution.recorded || !Number.isFinite(lastPrice) || lastPrice <= 0) {
    const alertStatus = execution.recorded ? "missing_current_price" : "not_applicable";
    const stop = numericValue(item.stop_loss_price);
    const alertSignature = positionAlertSignature(alertStatus, null, stop);
    const alertAcknowledged = positionAlertAcknowledged(item, alertSignature);
    return {
      monitored: false,
      pnl: 0,
      pnlPct: null,
      rMultiple: null,
      stopDistancePct: null,
      lastPrice: null,
      alertStatus,
      alertReason: execution.recorded ? "current price unavailable" : "",
      alertSignature,
      alertAcknowledged,
      alertAcknowledgedAt: alertAcknowledged ? String(item.position_alert_acknowledged_at || "") : "",
      pnlClass: "flat",
      label: "P/L -",
    };
  }
  const pnl = (lastPrice - execution.price) * execution.shares;
  const pnlPct = execution.price > 0 ? ((lastPrice - execution.price) / execution.price) * 100 : null;
  const stop = numericValue(item.stop_loss_price);
  const riskPerShare = Number.isFinite(stop) ? execution.price - stop : null;
  const rMultiple = riskPerShare && riskPerShare > 0 ? (lastPrice - execution.price) / riskPerShare : null;
  const stopDistancePct = Number.isFinite(stop) && stop > 0 ? ((lastPrice - stop) / lastPrice) * 100 : null;
  const alert = positionAlertStatus(lastPrice, stop, stopDistancePct);
  const alertSignature = positionAlertSignature(alert.status, lastPrice, stop);
  const alertAcknowledged = positionAlertAcknowledged(item, alertSignature);
  const pnlClass = pnl > 0 ? "up" : pnl < 0 ? "down" : "flat";
  const pctLabel = Number.isFinite(pnlPct) ? formatSummaryPercent(pnlPct) : "-";
  const rLabel = Number.isFinite(rMultiple) ? `${rMultiple.toFixed(2)}R` : "R -";
  return {
    monitored: true,
    pnl,
    pnlPct,
    rMultiple,
    stopDistancePct,
    lastPrice,
    alertStatus: alert.status,
    alertReason: alert.reason,
    alertSignature,
    alertAcknowledged,
    alertAcknowledgedAt: alertAcknowledged ? String(item.position_alert_acknowledged_at || "") : "",
    pnlClass,
    label: `${formatCurrency(pnl)} · ${pctLabel} · ${rLabel}`,
  };
}

function positionAlertStatus(lastPrice, stopPrice, stopDistancePct) {
  if (!Number.isFinite(stopPrice) || stopPrice <= 0) {
    return { status: "missing_stop_loss", reason: "stop loss unavailable" };
  }
  if (lastPrice <= stopPrice) {
    return { status: "stop_breached", reason: "last price is at or below stop loss" };
  }
  if (Number.isFinite(stopDistancePct) && stopDistancePct <= POSITION_ALERT_NEAR_STOP_PCT) {
    return { status: "near_stop", reason: `last price is within ${POSITION_ALERT_NEAR_STOP_PCT}% of stop loss` };
  }
  return { status: "ok", reason: "" };
}

function positionAlertSignature(status, lastPrice, stopPrice) {
  if (!positionAlertNeedsAttention(status)) return "";
  const lastToken = Number.isFinite(lastPrice) ? lastPrice.toFixed(2) : "";
  const stopToken = Number.isFinite(stopPrice) ? stopPrice.toFixed(2) : "";
  return `${status}|${lastToken}|${stopToken}`;
}

function positionAlertAcknowledged(item, signature) {
  return Boolean(
    signature
    && item?.position_alert_ack_signature === signature
    && String(item?.position_alert_acknowledged_at || "").trim(),
  );
}

function numericValue(value) {
  if (isBlank(value)) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function numericInputValue(value) {
  if (isBlank(value)) return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function formatShares(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "-";
  return Math.floor(number).toLocaleString();
}

function formatStoredPercent(value) {
  if (isBlank(value)) return "-";
  return formatPercent(Number(value) / 100);
}

function formatAgeHours(value) {
  if (isBlank(value)) return "-";
  const hours = Number(value);
  if (!Number.isFinite(hours)) return "-";
  if (hours < 1) return "<1h";
  if (hours < 48) return `${Math.round(hours)}h`;
  return `${Math.round(hours / 24)}d`;
}

function formatMarketFreshness(health = {}) {
  const lag = Number(health.market_session_lag);
  const days = Number(health.market_age_days);
  const sessionLabel = Number.isFinite(lag) ? `${Math.max(0, lag)} session${lag === 1 ? "" : "s"}` : "";
  const calendarLabel = Number.isFinite(days) ? `${Math.max(0, days)}d` : "";
  if (sessionLabel && calendarLabel) return `${sessionLabel} · ${calendarLabel}`;
  return sessionLabel || calendarLabel || "unknown";
}

function formatRiskReward(low, high) {
  if (isBlank(low) && isBlank(high)) return "-";
  const lowNumber = Number(low);
  const highNumber = Number(high);
  if (!Number.isFinite(lowNumber) && !Number.isFinite(highNumber)) return "-";
  if (!Number.isFinite(highNumber) || Math.abs(highNumber - lowNumber) < 0.01) {
    return `${lowNumber.toFixed(1)}R`;
  }
  if (!Number.isFinite(lowNumber)) return `${highNumber.toFixed(1)}R`;
  return `${lowNumber.toFixed(1)}-${highNumber.toFixed(1)}R`;
}

function renderActionLabel(action) {
  return escapeHtml(renderActionLabelText(action));
}

function renderActionLabelText(action) {
  const labels = {
    actionable: "Actionable",
    watch_breakout: "Watch breakout",
    building_base: "Building base",
    extended: "Extended",
    research: "Research",
  };
  return labels[action] || labels.research;
}

function normalizeSortBy(value) {
  const allowed = new Set(["ticker", "name", "score", "setup", "rs", "eps", "revenue", "pivot", "market_cap"]);
  const normalized = String(value || "score");
  return allowed.has(normalized) ? normalized : "score";
}

function normalizeSortDir(value) {
  return String(value || "desc") === "asc" ? "asc" : "desc";
}

function normalizeScreenerSetup(value) {
  const normalized = String(value || "");
  return SCREENER_SETUP_OPTIONS.has(normalized) ? normalized : "";
}

function normalizeReviewSortBy(value) {
  const allowed = new Set(["added_at", "ticker", "status", "priority", "score", "risk", "capital", "shares"]);
  const normalized = String(value || "added_at");
  return allowed.has(normalized) ? normalized : "added_at";
}

function normalizeReviewStatus(value) {
  const allowed = new Set(["", "watch", "ready", "pass", "bought", "sold"]);
  const normalized = String(value || "");
  return allowed.has(normalized) ? normalized : "";
}

function normalizeReviewPriorityFilter(value) {
  const normalized = String(value || "").toLowerCase();
  return REVIEW_PRIORITY_OPTIONS.some(([allowed]) => allowed === normalized) ? normalized : "";
}

function normalizeReviewTag(value) {
  const cleaned = String(value || "").trim().replace(/\s+/g, "-").toLowerCase();
  return cleaned.replace(/[^a-z0-9_-]/g, "").replace(/^-+|-+$/g, "").slice(0, 24);
}

function parseReviewTags(value) {
  const source = Array.isArray(value) ? value : String(value || "").split(/[,;\n|]+/);
  const seen = new Set();
  const tags = [];
  source.forEach((tag) => {
    const normalized = normalizeReviewTag(tag);
    if (!normalized || seen.has(normalized)) return;
    seen.add(normalized);
    tags.push(normalized);
  });
  return tags.slice(0, 8);
}

function reviewTagsText(value) {
  return parseReviewTags(value).join(", ");
}

function cleanReviewQuery(value) {
  return String(value || "").trim().replace(/\s+/g, " ").slice(0, 80);
}

function sortableNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function sortableDate(value) {
  const time = new Date(value || 0).getTime();
  return Number.isFinite(time) ? time : null;
}

function isBlank(value) {
  return value === null || value === undefined || value === "";
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value || "-");
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function parseReviewDate(value) {
  if (isBlank(value)) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateAgeDays(value, now = new Date()) {
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return null;
  return Math.max(0, Math.floor((now.getTime() - value.getTime()) / 86_400_000));
}

function formatAgeDays(value) {
  if (isBlank(value)) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${Math.max(0, Math.floor(number))}d`;
}

function formatTime(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function userMessage(error) {
  const raw = error?.message || String(error || "Unknown error");
  try {
    const payload = JSON.parse(raw);
    if (payload?.error) return String(payload.error);
  } catch (parseError) {
    // The message is already plain text.
  }
  return raw.length > 180 ? `${raw.slice(0, 177)}...` : raw;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function boundedNumber(value, fallback, min, max) {
  const number = Number(value);
  return Number.isFinite(number) ? clamp(number, min, max) : fallback;
}

function formatPreferenceNumber(value, digits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number.toFixed(digits).replace(/\.0+$/, "");
}

function formatGuardrailPercent(value) {
  if (isBlank(value)) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number.toFixed(1).replace(/\.0$/, "")}%`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function cssEscape(value) {
  if (window.CSS?.escape) return window.CSS.escape(String(value));
  return String(value).replace(/["\\]/g, "\\$&");
}

els.refreshButton.addEventListener("click", async () => {
  await saveSessionJournal({ onlyIfDirty: true, silent: true });
  await loadDashboard();
});
els.profileSelect.addEventListener("change", (event) => {
  switchProfile(event.target.value);
});
els.profileMatrix.addEventListener("click", (event) => {
  const runButton = event.target.closest("[data-profile-run]");
  if (runButton) {
    startPipelineJob(runButton.dataset.profileRunMode || "screen", runButton.dataset.profileRun || state.profile);
    return;
  }
  const switchButton = event.target.closest("[data-profile-switch]");
  if (!switchButton) return;
  switchProfile(switchButton.dataset.profileSwitch);
});

async function switchProfile(profile) {
  const nextProfile = String(profile || "").trim();
  if (!nextProfile || nextProfile === state.profile) return;
  await saveSessionJournal({ onlyIfDirty: true, silent: true });
  state.profile = nextProfile;
  state.analysis = null;
  state.selectedReviewTickers.clear();
  state.selectedCompareTickers.clear();
  state.reviewImportReport = null;
  await saveWorkspacePreferences();
  await loadDashboard();
}
els.tickerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  analyzeTicker(els.tickerInput.value);
});
els.reviewAnalysisButton.addEventListener("click", () => {
  if (state.analysis?.found) {
    addToReview(state.analysis);
  }
});
els.analysisExportButton.addEventListener("click", exportAnalysisDossier);
[
  els.accountEquity,
  els.riskPerTrade,
  els.maxCapitalPct,
  els.maxQueueRiskPct,
  els.maxOpenRiskPct,
  els.maxConcentrationPct,
  els.maxOpenConcentrationPct,
].forEach((input) => {
  input.addEventListener("input", updateRiskFromControls);
});
els.reviewSortSelect.addEventListener("change", (event) => {
  updateReviewSort(event.target.value);
});
els.reviewSortDirection.addEventListener("click", () => {
  state.reviewSortDir = state.reviewSortDir === "asc" ? "desc" : "asc";
  renderReviewSortDirection();
  renderReviewQueue();
  saveWorkspacePreferencesDebounced();
});
els.reviewSearchInput.addEventListener("input", (event) => {
  updateReviewQueryFilter(event.target.value);
});
els.reviewStatusFilter.addEventListener("change", (event) => {
  updateReviewStatusFilter(event.target.value);
});
els.reviewPriorityFilter.addEventListener("change", (event) => {
  updateReviewPriorityFilter(event.target.value);
});
els.reviewTagFilter.addEventListener("change", (event) => {
  updateReviewTagFilter(event.target.value);
});
els.reviewClearFiltersButton.addEventListener("click", clearReviewFilters);
els.reviewViewSelect.addEventListener("change", async () => {
  await applyReviewView(els.reviewViewSelect.value);
});
els.saveReviewViewButton.addEventListener("click", saveReviewView);
els.deleteReviewViewButton.addEventListener("click", deleteReviewView);
els.reviewSelectVisible.addEventListener("change", (event) => {
  const visibleTickers = visibleReviewItems().map((item) => item.ticker);
  if (event.target.checked) {
    visibleTickers.forEach((ticker) => state.selectedReviewTickers.add(ticker));
  } else {
    visibleTickers.forEach((ticker) => state.selectedReviewTickers.delete(ticker));
  }
  renderReviewQueue();
});
els.reviewBulkApply.addEventListener("click", updateSelectedReviewStatus);
els.reviewBulkPriorityApply.addEventListener("click", updateSelectedReviewPriority);
els.reviewBulkTags.addEventListener("input", () => renderReviewBulkControls());
els.reviewBulkTagAdd.addEventListener("click", () => updateSelectedReviewTags("add"));
els.reviewBulkTagReplace.addEventListener("click", () => updateSelectedReviewTags("replace"));
els.reviewBulkExport.addEventListener("click", exportSelectedReviewItems);
els.reviewBulkRemove.addEventListener("click", removeSelectedReviewItems);
els.reviewActivity.addEventListener("click", (event) => {
  const button = event.target.closest("[data-activity-undo]");
  if (button) {
    undoReviewActivity(button.dataset.activityUndo);
  }
});
els.jobHistory.addEventListener("click", (event) => {
  const button = event.target.closest("[data-job-rerun]");
  if (!button || button.disabled) return;
  startPipelineJob(button.dataset.jobRerun, button.dataset.jobProfile || state.profile);
});
els.artifactList.addEventListener("click", (event) => {
  const link = event.target.closest("[data-artifact-download]");
  if (!link) return;
  event.preventDefault();
  triggerDownload(new URL(link.dataset.artifactDownload, window.location.origin), link.dataset.artifactFilename || "");
});
els.diagnosticsPanel.addEventListener("click", (event) => {
  const button = event.target.closest("[data-diagnostic-action]");
  if (!button || button.disabled) return;
  handleDiagnosticAction(button.dataset.diagnosticAction);
});
els.releaseReadinessPanel.addEventListener("click", (event) => {
  const button = event.target.closest("[data-diagnostic-action]");
  if (!button || button.disabled) return;
  handleDiagnosticAction(button.dataset.diagnosticAction);
});
els.opsRunbook.addEventListener("click", (event) => {
  const button = event.target.closest("[data-runbook-action]");
  if (!button || button.disabled) return;
  const action = button.dataset.runbookAction;
  if (action === "run-next") {
    startPipelineJob(els.runNextButton.dataset.mode);
    return;
  }
  if (action === "enrich" || action === "tv-export") {
    startPipelineJob(action);
    return;
  }
  if (action === "snapshot") {
    exportWorkspaceSnapshot();
    return;
  }
  if (action === "dossier") {
    exportAnalysisDossier();
    return;
  }
  if (action === "review") {
    document.querySelector(".review-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});
els.reviewImportForm.addEventListener("submit", (event) => {
  event.preventDefault();
  importReviewTickers();
});
els.reviewPriceForm.addEventListener("submit", (event) => {
  event.preventDefault();
  updateReviewPricesFromPaste();
});
els.actionList.addEventListener("click", (event) => {
  const queueAllButton = event.target.closest("[data-action-queue-all]");
  if (queueAllButton) {
    addPriorityActionCandidatesToReview();
    return;
  }
  const queueButton = event.target.closest("[data-action-queue]");
  if (queueButton) {
    addActionCandidateToReview(queueButton.dataset.actionQueue);
    return;
  }
  const button = event.target.closest("[data-ticker]");
  if (button?.dataset.ticker) {
    els.tickerInput.value = button.dataset.ticker;
    analyzeTicker(button.dataset.ticker);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
});
els.decisionBrief.addEventListener("click", (event) => {
  const actionButton = event.target.closest("[data-decision-action]");
  if (actionButton) {
    handleDecisionAction(actionButton.dataset.decisionAction);
    return;
  }
  const tickerButton = event.target.closest("[data-ticker]");
  if (tickerButton?.dataset.ticker) {
    els.tickerInput.value = tickerButton.dataset.ticker;
    analyzeTicker(tickerButton.dataset.ticker);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
});
els.reviewSummary.addEventListener("click", (event) => {
  const riskActionButton = event.target.closest("[data-risk-action]");
  if (riskActionButton) {
    focusRiskActionItems(riskActionButton.dataset.riskAction, riskActionButton.dataset.riskTickers);
    return;
  }
  const ackButton = event.target.closest("[data-ack-position-alert]");
  if (ackButton) {
    acknowledgePositionAlert(ackButton.dataset.ackPositionAlert);
    return;
  }
  const clearAlertButton = event.target.closest("[data-clear-position-alert]");
  if (clearAlertButton) {
    clearPositionAlertAcknowledgement(clearAlertButton.dataset.clearPositionAlert);
    return;
  }
  const button = event.target.closest("[data-ticker]");
  if (button?.dataset.ticker) {
    els.tickerInput.value = button.dataset.ticker;
    analyzeTicker(button.dataset.ticker);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
});
els.candidateQuality.addEventListener("click", (event) => {
  const button = event.target.closest("[data-ticker]");
  if (button?.dataset.ticker) {
    els.tickerInput.value = button.dataset.ticker;
    analyzeTicker(button.dataset.ticker);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
});
els.exportScreenerButton.addEventListener("click", exportScreenerView);
els.bulkReviewButton.addEventListener("click", addVisibleToReview);
els.screenerViewSelect.addEventListener("change", async () => {
  await applyScreenerView(els.screenerViewSelect.value);
});
els.saveScreenerViewButton.addEventListener("click", saveScreenerView);
els.deleteScreenerViewButton.addEventListener("click", deleteScreenerView);
els.candidateRows.addEventListener("click", (event) => {
  const compareButton = event.target.closest("[data-compare]");
  if (compareButton) {
    toggleCandidateCompare(compareButton.dataset.compare);
    return;
  }
  const addButton = event.target.closest("[data-add-review]");
  if (addButton) {
    addToReview(findCandidateByTicker(addButton.dataset.addReview));
    return;
  }
  const button = event.target.closest("[data-ticker]");
  if (button) {
    els.tickerInput.value = button.dataset.ticker;
    analyzeTicker(button.dataset.ticker);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
});
els.compareGrid.addEventListener("click", (event) => {
  const compareButton = event.target.closest("[data-compare]");
  if (compareButton) {
    toggleCandidateCompare(compareButton.dataset.compare);
    return;
  }
  const tickerButton = event.target.closest("[data-ticker]");
  if (tickerButton) {
    els.tickerInput.value = tickerButton.dataset.ticker;
    analyzeTicker(tickerButton.dataset.ticker);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
});
els.clearCompareButton.addEventListener("click", clearCandidateCompare);
els.exportCompareButton.addEventListener("click", exportCandidateCompare);
document.querySelectorAll("[data-sort]").forEach((button) => {
  button.addEventListener("click", async () => {
    const requested = button.dataset.sort;
    if (state.sortBy === requested) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortBy = requested;
      state.sortDir = requested === "ticker" || requested === "name" || requested === "setup" ? "asc" : "desc";
    }
    renderSortButtons();
    renderScreenerViews();
    saveWorkspacePreferencesDebounced();
    await refreshScreenerData();
  });
});
els.reviewList.addEventListener("click", (event) => {
  const clearFiltersButton = event.target.closest("[data-clear-review-filters]");
  if (clearFiltersButton) {
    clearReviewFilters();
    return;
  }
  const ackButton = event.target.closest("[data-ack-position-alert]");
  if (ackButton) {
    acknowledgePositionAlert(ackButton.dataset.ackPositionAlert);
    return;
  }
  const clearAlertButton = event.target.closest("[data-clear-position-alert]");
  if (clearAlertButton) {
    clearPositionAlertAcknowledgement(clearAlertButton.dataset.clearPositionAlert);
    return;
  }
  const removeButton = event.target.closest("[data-remove-review]");
  if (removeButton) {
    removeFromReview(removeButton.dataset.removeReview);
    return;
  }
  const button = event.target.closest("[data-ticker]");
  if (button) {
    els.tickerInput.value = button.dataset.ticker;
    analyzeTicker(button.dataset.ticker);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
});
els.reviewList.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-review-select]");
  if (checkbox) {
    const ticker = String(checkbox.dataset.reviewSelect || "").toUpperCase();
    if (checkbox.checked) {
      state.selectedReviewTickers.add(ticker);
    } else {
      state.selectedReviewTickers.delete(ticker);
    }
    renderReviewBulkControls();
    return;
  }
  const statusSelect = event.target.closest("[data-review-status]");
  if (statusSelect) {
    const normalized = String(statusSelect.dataset.reviewStatus || "").toUpperCase();
    const existing = state.reviewQueue.find((item) => item.ticker === normalized);
    const patch = reviewStatusTransitionPatch(existing, statusSelect.value);
    updateReviewItem(normalized, patch);
    return;
  }
  const prioritySelect = event.target.closest("[data-review-priority]");
  if (prioritySelect) {
    const normalized = String(prioritySelect.dataset.reviewPriority || "").toUpperCase();
    updateReviewItem(normalized, { review_priority: normalizeReviewPriority(prioritySelect.value) });
    return;
  }
  const checkField = event.target.closest("[data-review-check]");
  if (checkField) {
    const normalized = String(checkField.dataset.reviewCheck || "").toUpperCase();
    const key = checkField.dataset.reviewCheckKey;
    if (!REVIEW_CHECK_OPTIONS.some(([allowed]) => allowed === key)) return;
    const existing = state.reviewQueue.find((item) => item.ticker === normalized);
    if (!existing) return;
    const checks = { ...normalizedReviewChecks(existing.review_checks), [key]: checkField.checked };
    existing.review_checks = checks;
    saveReviewQueue();
    renderReviewSummary(calculateReviewSummary());
    updateReviewChecklistDisplay(normalized);
    updateReviewItem(normalized, { review_checks: checks }, { rerender: false });
  }
});
els.reviewList.addEventListener("input", (event) => {
  const priceField = event.target.closest("[data-review-price]");
  if (priceField) {
    updateReviewPriceInput(priceField);
    return;
  }
  const executionField = event.target.closest("[data-review-execution]");
  if (executionField) {
    updateReviewExecutionInput(executionField);
    return;
  }
  const exitField = event.target.closest("[data-review-exit]");
  if (exitField) {
    updateReviewExitInput(exitField);
    return;
  }
  const tagsField = event.target.closest("[data-review-tags]");
  if (tagsField) {
    const normalized = String(tagsField.dataset.reviewTags || "").toUpperCase();
    const existing = state.reviewQueue.find((item) => item.ticker === normalized);
    if (!existing) return;
    const tags = parseReviewTags(tagsField.value);
    existing.review_tags = tags;
    saveReviewQueue();
    renderReviewTagFilterOptions();
    clearTimeout(reviewTagTimers.get(normalized));
    reviewTagTimers.set(
      normalized,
      setTimeout(() => {
        updateReviewItem(normalized, { review_tags: tags }, { rerender: false });
      }, 450),
    );
    return;
  }
  const noteField = event.target.closest("[data-review-note]");
  if (!noteField) return;
  const ticker = noteField.dataset.reviewNote;
  const normalized = String(ticker || "").toUpperCase();
  const existing = state.reviewQueue.find((item) => item.ticker === normalized);
  if (existing) {
    existing.review_note = noteField.value;
    saveReviewQueue();
  }
  clearTimeout(reviewNoteTimers.get(normalized));
  reviewNoteTimers.set(
    normalized,
    setTimeout(() => {
      updateReviewItem(normalized, { review_note: noteField.value }, { rerender: false });
    }, 450),
  );
});
els.exportReviewButton.addEventListener("click", exportReviewQueue);
document.querySelector(".skip-link")?.addEventListener("click", (event) => {
  const href = event.currentTarget?.getAttribute("href") || "";
  const target = href ? document.querySelector(href) : null;
  if (target && typeof target.focus === "function") {
    requestAnimationFrame(() => target.focus());
  }
});
els.workspaceImportButton.addEventListener("click", chooseWorkspaceSnapshot);
els.workspaceImportInput.addEventListener("change", (event) => {
  importWorkspaceSnapshot(event.target.files?.[0]);
});
els.workspaceImportCancelButton.addEventListener("click", () => resolveWorkspaceImportConfirmation(false));
els.workspaceImportConfirmButton.addEventListener("click", () => resolveWorkspaceImportConfirmation(true));
els.workspaceImportModal.addEventListener("click", (event) => {
  if (event.target === els.workspaceImportModal) {
    resolveWorkspaceImportConfirmation(false);
  }
});
els.viewNameCancelButton?.addEventListener("click", () => resolveViewNameConfirmation(null));
els.viewNameForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const value = cleanScreenerViewName(els.viewNameInput?.value || "");
  if (!value) {
    renderViewNameError("Enter a view name.");
    els.viewNameInput?.focus();
    return;
  }
  renderViewNameError("");
  resolveViewNameConfirmation(value);
});
els.viewNameInput?.addEventListener("input", () => {
  if (els.viewNameForm?.classList.contains("is-invalid") && cleanScreenerViewName(els.viewNameInput.value)) {
    renderViewNameError("");
  }
});
els.viewNameModal?.addEventListener("click", (event) => {
  if (event.target === els.viewNameModal) {
    resolveViewNameConfirmation(null);
  }
});
els.workspaceExportButton.addEventListener("click", exportWorkspaceSnapshot);
els.workspaceBackupButton.addEventListener("click", openWorkspaceBackupModal);
els.workspaceAuditExportButton?.addEventListener("click", exportWorkspaceAudit);
els.workspaceAuditSearch?.addEventListener("input", (event) => {
  state.workspaceAuditQuery = String(event.target.value || "").slice(0, 80);
  state.workspaceAuditMeta = null;
  state.workspaceAuditLimit = workspaceAuditBaseLimit();
  renderWorkspaceAudit();
  scheduleWorkspaceAuditReload();
});
els.workspaceAuditType?.addEventListener("change", (event) => {
  state.workspaceAuditType = String(event.target.value || "");
  state.workspaceAuditMeta = null;
  state.workspaceAuditLimit = workspaceAuditBaseLimit();
  renderWorkspaceAudit();
  loadWorkspaceAudit();
});
els.workspaceAuditClearButton?.addEventListener("click", clearWorkspaceAuditFilters);
els.workspaceBackupCloseButton.addEventListener("click", closeWorkspaceBackupModal);
els.workspaceBackupModal.addEventListener("click", (event) => {
  if (event.target === els.workspaceBackupModal) {
    closeWorkspaceBackupModal();
  }
  const downloadButton = event.target.closest("[data-download-workspace-backup]");
  if (downloadButton) {
    downloadWorkspaceBackup(downloadButton.dataset.downloadWorkspaceBackup);
    return;
  }
  const restoreButton = event.target.closest("[data-restore-workspace-backup]");
  if (restoreButton) {
    restoreWorkspaceBackup(restoreButton.dataset.restoreWorkspaceBackup);
    return;
  }
  const deleteButton = event.target.closest("[data-delete-workspace-backup]");
  if (deleteButton) {
    deleteWorkspaceBackup(deleteButton.dataset.deleteWorkspaceBackup);
    return;
  }
  const repairAuditButton = event.target.closest("[data-repair-workspace-audit]");
  if (repairAuditButton) {
    repairWorkspaceAuditStore();
    return;
  }
  const loadMoreAuditButton = event.target.closest("[data-load-more-workspace-audit]");
  if (loadMoreAuditButton) {
    loadMoreWorkspaceAudit();
  }
});
els.clearReviewButton.addEventListener("click", clearReviewQueue);
els.runNextButton.addEventListener("click", () => startPipelineJob(els.runNextButton.dataset.mode));
els.runEnrichButton.addEventListener("click", () => startPipelineJob("enrich"));
els.runScreenButton.addEventListener("click", () => startPipelineJob("screen"));
els.runTvExportButton.addEventListener("click", () => startPipelineJob("tv-export"));
els.profileSweepButton?.addEventListener("click", () => startPipelineJob("profile-sweep"));
els.sessionReportButton.addEventListener("click", exportSessionReport);
els.supportBundleButton.addEventListener("click", exportSupportBundle);
els.cancelJobButton.addEventListener("click", cancelPipelineJob);
els.saveJournalButton.addEventListener("click", () => saveSessionJournal());
els.sessionJournalDate.addEventListener("change", async () => {
  const previousDate = state.sessionJournalDate || state.sessionJournal?.date;
  await saveSessionJournal({ onlyIfDirty: true, silent: true, date: previousDate });
  await loadSessionJournal();
});

let journalTimer = null;
[els.journalMarketThesis, els.journalWatchlistFocus, els.journalRiskNotes, els.journalPostReview].forEach((input) => {
  input.addEventListener("input", () => {
    state.journalDirty = true;
    renderJournalStatus("Unsaved");
    clearTimeout(journalTimer);
    journalTimer = setTimeout(() => {
      saveSessionJournal({ onlyIfDirty: true, silent: true });
    }, 900);
  });
});

let screenerTimer = null;
[els.candidateSearch, els.minScore, els.setupFilter].forEach((input) => {
  input.addEventListener("input", () => {
    renderScreenerViews();
    clearTimeout(screenerTimer);
    screenerTimer = setTimeout(async () => {
      saveWorkspacePreferencesDebounced();
      await refreshScreenerData();
    }, 180);
  });
});

let canvasResizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(canvasResizeTimer);
  canvasResizeTimer = setTimeout(redrawAnalysisCanvases, 120);
});
window.addEventListener("keydown", (event) => {
  trapModalFocus(event);
  if (event.key !== "Escape") return;
  if (workspaceImportConfirmation && activeModal === els.workspaceImportModal) {
    event.preventDefault();
    resolveWorkspaceImportConfirmation(false);
    return;
  }
  if (viewNameConfirmation && activeModal === els.viewNameModal) {
    event.preventDefault();
    resolveViewNameConfirmation(null);
    return;
  }
  if (activeModal === els.workspaceBackupModal) {
    event.preventDefault();
    closeWorkspaceBackupModal();
  }
});

function redrawAnalysisCanvases() {
  const result = state.analysis || {};
  if (result.found) {
    const brief = result.research_brief || makeResearchBrief(result);
    drawPriceChart(result.price_history || [], result.ticker, brief.trade_plan || {});
    drawScoreDial(Number(result.canslim_score || 0), result.score_band || "");
    return;
  }
  drawPriceChart([], result.ticker || "");
  drawScoreDial(0, "");
}

async function initApp() {
  drawPriceChart([], "");
  drawScoreDial(0, "");
  renderReviewQueue();
  await loadWorkspacePreferences();
  await loadDashboard();
}

installClientEventReporting();
initApp();
