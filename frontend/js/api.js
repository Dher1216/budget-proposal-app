// Point this at wherever the backend is deployed. If the frontend is served
// by the same FastAPI app (the default), leave this empty.
const API_BASE = "";

// Registers the service worker that caches this app's own HTML/CSS/JS so
// the pages load even with no internet connection at all (e.g. after a
// restart while offline). Only caches static files -- never touches API
// calls, which the rest of this file already handles for offline use.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/app/sw.js").catch(() => {
      // Not fatal -- the app still works online, it just won't be able to
      // load itself with zero connectivity until this succeeds once.
    });
  });
}

function getToken() { return localStorage.getItem("budget_token"); }
function getRole() { return localStorage.getItem("budget_role"); }
function getOfficeId() { return localStorage.getItem("budget_office_id"); }
function getOfficeName() { return localStorage.getItem("budget_office_name"); }
function getUsername() { return localStorage.getItem("budget_username"); }

function saveSession(data) {
  localStorage.setItem("budget_token", data.access_token);
  localStorage.setItem("budget_role", data.role);
  localStorage.setItem("budget_office_id", data.office_id ?? "");
  localStorage.setItem("budget_office_name", data.office_name ?? "");
  localStorage.setItem("budget_username", data.username);
}

function clearSession() {
  ["budget_token", "budget_role", "budget_office_id", "budget_office_name", "budget_username"]
    .forEach(k => localStorage.removeItem(k));
}

function requireLogin(expectedRole) {
  const token = getToken();
  const role = getRole();
  if (!token || (expectedRole && role !== expectedRole)) {
    window.location.href = "/app/index.html";
  }
}

function logout() {
  clearSession();
  window.location.href = "/app/index.html";
}

function handleUnauthorized() {
  clearSession();
  sessionStorage.setItem("budget_session_expired", "1");
  window.location.href = "/app/index.html";
}

// Cache key for a given GET request, used so views can still show the last
// known data when the device has no connection.
function cacheKey(path) { return "cache:" + path; }

async function apiGet(path, { cacheable = false } = {}) {
  const url = API_BASE + path;
  try {
    const res = await fetch(url, {
      headers: { "Authorization": "Bearer " + getToken() }
    });
    if (res.status === 401) { handleUnauthorized(); throw new Error("Session expired"); }
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    if (cacheable) localStorage.setItem(cacheKey(path), JSON.stringify(data));
    return { data, fromCache: false };
  } catch (err) {
    if (cacheable && getToken()) {
      const cached = localStorage.getItem(cacheKey(path));
      if (cached) return { data: JSON.parse(cached), fromCache: true };
    }
    throw err;
  }
}

async function apiSend(method, path, body) {
  const url = API_BASE + path;
  const res = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + getToken()
    },
    body: JSON.stringify(body)
  });
  if (res.status === 401) { handleUnauthorized(); throw new Error("Session expired"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}

function apiPost(path, body) { return apiSend("POST", path, body); }
function apiPut(path, body) { return apiSend("PUT", path, body); }

async function apiDelete(path) {
  const res = await fetch(API_BASE + path, {
    method: "DELETE",
    headers: { "Authorization": "Bearer " + getToken() }
  });
  if (res.status === 401) { handleUnauthorized(); throw new Error("Session expired"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}

async function apiUpload(path, file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Authorization": "Bearer " + getToken() },  // no Content-Type -- browser sets the multipart boundary
    body: formData
  });
  if (res.status === 401) { handleUnauthorized(); throw new Error("Session expired"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}

function attachmentDownloadUrl(id) {
  return API_BASE + `/api/attachments/${id}/download`;
}

async function downloadAttachment(id, filename) {
  try {
    let blob = await getCachedAttachment(id);
    if (!blob) {
      const res = await fetch(attachmentDownloadUrl(id), {
        headers: { "Authorization": "Bearer " + getToken() }
      });
      if (!res.ok) throw new Error("Could not download — check your connection.");
      blob = await res.blob();
    }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
  } catch (err) {
    alert(navigator.onLine ? err.message : "This file isn't available offline yet — it needs to be opened once while online first.");
  }
}

function updateOfflineBanner() {
  const banner = document.getElementById("offlineBanner");
  if (!banner) return;
  banner.classList.toggle("show", !navigator.onLine);
}
window.addEventListener("online", updateOfflineBanner);
window.addEventListener("offline", updateOfflineBanner);
document.addEventListener("DOMContentLoaded", updateOfflineBanner);

function money(n) {
  n = Number(n || 0);
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ======================================================================
// Offline support: queues writes made with no connection (so they aren't
// lost, just delayed) and caches attachment files locally so they can be
// opened with no connection. Intended for a SINGLE admin device working
// on a proposal that's been locked (so the office can't also be editing
// it at the same time) -- e.g. during a budget hearing with poor signal.
// ======================================================================

const OFFLINE_DB_NAME = "budget_offline";
const OFFLINE_DB_VERSION = 1;
let _offlineDbPromise = null;

function openOfflineDb() {
  if (_offlineDbPromise) return _offlineDbPromise;
  _offlineDbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(OFFLINE_DB_NAME, OFFLINE_DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("pendingWrites")) {
        db.createObjectStore("pendingWrites", { keyPath: "id", autoIncrement: true });
      }
      if (!db.objectStoreNames.contains("attachmentCache")) {
        db.createObjectStore("attachmentCache", { keyPath: "attachmentId" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return _offlineDbPromise;
}

async function queuePendingWrite(method, path, body, description) {
  const db = await openOfflineDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("pendingWrites", "readwrite");
    tx.objectStore("pendingWrites").add({ method, path, body, description, queuedAt: new Date().toISOString() });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getPendingWrites() {
  const db = await openOfflineDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("pendingWrites", "readonly");
    const req = tx.objectStore("pendingWrites").getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function removePendingWrite(id) {
  const db = await openOfflineDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("pendingWrites", "readwrite");
    tx.objectStore("pendingWrites").delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// Tries a write immediately; if the network itself is unreachable (not just
// a server error), queues it instead of failing, so the user's edit isn't
// lost. Returns { queued: true } or { queued: false, data }.
async function offlineAwareSend(method, path, body, description) {
  try {
    const data = await apiSend(method, path, body);
    return { queued: false, data };
  } catch (err) {
    if (err instanceof TypeError || err.message === "Failed to fetch" || !navigator.onLine) {
      await queuePendingWrite(method, path, body, description);
      updatePendingSyncBadge();
      return { queued: true };
    }
    throw err; // a real server error (e.g. validation) -- don't hide it by queueing
  }
}

let _syncInProgress = false;

async function syncPendingWrites(onProgress) {
  if (_syncInProgress) {
    return { succeeded: 0, failed: 0, total: 0, alreadyRunning: true };
  }
  _syncInProgress = true;
  try {
    const writes = await getPendingWrites();
    let succeeded = 0, failed = 0;
    for (const w of writes) {
      try {
        await apiSend(w.method, w.path, w.body);
        await removePendingWrite(w.id);
        succeeded++;
      } catch (err) {
        failed++; // leave it queued, try again next sync
      }
      if (onProgress) onProgress(succeeded + failed, writes.length);
    }
    updatePendingSyncBadge();
    return { succeeded, failed, total: writes.length };
  } finally {
    _syncInProgress = false;
  }
}

async function updatePendingSyncBadge() {
  const badge = document.getElementById("pendingSyncBadge");
  if (!badge) return;
  try {
    const writes = await getPendingWrites();
    if (writes.length > 0) {
      badge.textContent = `${writes.length} change(s) waiting to sync`;
      badge.style.display = "inline-block";
    } else {
      badge.style.display = "none";
    }
  } catch (e) { /* IndexedDB not available -- ignore */ }
}

window.addEventListener("online", () => {
  syncPendingWrites().then(result => {
    if (result.total > 0) updatePendingSyncBadge();
  });
});
document.addEventListener("DOMContentLoaded", updatePendingSyncBadge);

// ---- attachment caching for offline viewing ----

async function cacheAttachmentForOffline(attachmentId) {
  try {
    const res = await fetch(attachmentDownloadUrl(attachmentId), {
      headers: { Authorization: "Bearer " + getToken() }
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const db = await openOfflineDb();
    const tx = db.transaction("attachmentCache", "readwrite");
    tx.objectStore("attachmentCache").put({ attachmentId, blob, cachedAt: new Date().toISOString() });
  } catch (err) { /* offline or failed -- just skip caching this one */ }
}

async function getCachedAttachment(attachmentId) {
  try {
    const db = await openOfflineDb();
    return new Promise((resolve) => {
      const tx = db.transaction("attachmentCache", "readonly");
      const req = tx.objectStore("attachmentCache").get(attachmentId);
      req.onsuccess = () => resolve(req.result ? req.result.blob : null);
      req.onerror = () => resolve(null);
    });
  } catch (err) {
    return null;
  }
}

// Formats a text input as the user types: 1234567 -> 1,234,567 (keeps up to
// 2 decimal places). Used instead of type="number" so commas are allowed
// while typing large amounts, which is easy to miscount otherwise.
function formatMoneyInput(el) {
  const caretFromEnd = el.value.length - el.selectionStart;
  let raw = el.value.replace(/[^0-9.\-]/g, "");
  const negative = raw.startsWith("-");
  if (negative) raw = raw.slice(1);
  const firstDot = raw.indexOf(".");
  let intPart = firstDot === -1 ? raw : raw.slice(0, firstDot);
  let decPart = firstDot === -1 ? "" : "." + raw.slice(firstDot + 1).replace(/\./g, "").slice(0, 2);
  intPart = intPart.replace(/^0+(?=\d)/, "");
  const withCommas = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  el.value = (negative ? "-" : "") + withCommas + decPart;
  const pos = Math.max(0, el.value.length - caretFromEnd);
  el.setSelectionRange(pos, pos);
}

// Strips commas back out before sending a value to the API.
function parseMoney(str) {
  if (str === null || str === undefined) return 0;
  const cleaned = String(str).replace(/,/g, "").trim();
  const n = parseFloat(cleaned);
  return isNaN(n) ? 0 : n;
}

const CLASSIFICATION_LABELS = {
  PS: "Personal Services",
  MOOE: "Maintenance and Other Operating Expenditures",
  FE: "Financial Expenses",
  CO: "Capital Outlay",
};
const CLASSIFICATION_ORDER = ["PS", "MOOE", "FE", "CO"];
