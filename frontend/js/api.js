// Point this at wherever the backend is deployed. If the frontend is served
// by the same FastAPI app (the default), leave this empty.
const API_BASE = "";

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
    const res = await fetch(attachmentDownloadUrl(id), {
      headers: { "Authorization": "Bearer " + getToken() }
    });
    if (!res.ok) throw new Error("Could not download — check your connection.");
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
  } catch (err) {
    alert(err.message);
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
