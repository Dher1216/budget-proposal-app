requireLogin("admin");
document.getElementById("whoami").textContent = getUsername() + " (admin)";

// ---------------------------------------------------------------- tabs ----
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
  });
});

let OFFICES = [];

async function loadOfficesIntoSelects() {
  try {
    const { data } = await apiGet("/api/offices", { cacheable: true });
    OFFICES = data;
    const selects = [document.getElementById("p_office"), document.getElementById("r_office"), document.getElementById("u_office")];
    selects.forEach(sel => {
      sel.innerHTML = data.map(o => `<option value="${o.id}">${o.name}</option>`).join("");
    });
    renderOfficeList();
  } catch (err) {
    console.error(err);
  }
}

function officeLogoUrl(officeId) {
  return `/api/offices/${officeId}/logo?t=${Date.now()}`;
}

function renderOfficeList() {
  const list = document.getElementById("o_list");
  if (!OFFICES.length) { list.innerHTML = "<li>No offices yet.</li>"; return; }
  list.innerHTML = OFFICES.map(o => `
    <li>
      <div class="office-row-left">
        <img class="office-row-logo" src="${officeLogoUrl(o.id)}" alt="" onerror="this.style.visibility='hidden'">
        <span>${o.name}${o.code ? " — " + o.code : ""}${o.sector ? " (" + o.sector + ")" : ""}</span>
      </div>
      <div>
        <input type="file" id="office-logo-file-${o.id}" accept="image/png,image/jpeg,image/webp,image/svg+xml" style="display:none;" onchange="uploadOfficeLogo(${o.id})">
        <button class="btn secondary" style="padding:4px 10px;" onclick="document.getElementById('office-logo-file-${o.id}').click()">${o.has_logo ? "Change logo" : "Add logo"}</button>
        ${o.has_logo ? `<button class="btn danger" style="padding:4px 10px;" onclick="removeOfficeLogo(${o.id})">Remove logo</button>` : ""}
      </div>
    </li>
  `).join("");
}

async function uploadOfficeLogo(officeId) {
  const input = document.getElementById(`office-logo-file-${officeId}`);
  const file = input.files[0];
  if (!file) return;
  const statusEl = document.getElementById("o_status");
  try {
    await apiUpload(`/api/offices/${officeId}/logo`, file);
    statusEl.textContent = "Office logo updated.";
    statusEl.className = "status-msg ok";
    await loadOfficesIntoSelects();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
}

async function removeOfficeLogo(officeId) {
  if (!confirm("Remove this office's logo? It will fall back to the default logo.")) return;
  const statusEl = document.getElementById("o_status");
  try {
    await apiDelete(`/api/offices/${officeId}/logo`);
    statusEl.textContent = "Office logo removed.";
    statusEl.className = "status-msg ok";
    await loadOfficesIntoSelects();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
}

function setOfficeLogo(imgId, officeId) {
  const img = document.getElementById(imgId);
  if (!img) return;
  if (!officeId) { img.style.display = "none"; return; }
  img.onload = () => { img.style.display = "block"; };
  img.onerror = () => { img.style.display = "none"; };
  img.src = officeLogoUrl(officeId);
}

document.getElementById("r_print").addEventListener("click", () => {
  window.print();
});

document.getElementById("o_add").addEventListener("click", async () => {
  const name = document.getElementById("o_name").value.trim();
  const code = document.getElementById("o_code").value.trim();
  const sector = document.getElementById("o_sector").value.trim();
  const statusEl = document.getElementById("o_status");
  if (!name) { statusEl.textContent = "Office name is required."; statusEl.className = "status-msg error"; return; }
  try {
    await apiPost("/api/offices", { name, code, sector });
    statusEl.textContent = "Office added.";
    statusEl.className = "status-msg ok";
    document.getElementById("o_name").value = "";
    document.getElementById("o_code").value = "";
    document.getElementById("o_sector").value = "";
    await loadOfficesIntoSelects();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

// -------------------------------------------------------------- branding --

function loadBrandingPreviews() {
  const loginImg = document.getElementById("brand_loginPreview");
  const defaultImg = document.getElementById("brand_defaultPreview");
  const bust = Date.now();
  loginImg.onload = () => { loginImg.style.display = "block"; };
  loginImg.onerror = () => { loginImg.style.display = "none"; };
  loginImg.src = `/api/branding/login-logo?t=${bust}`;
  defaultImg.onload = () => { defaultImg.style.display = "block"; };
  defaultImg.onerror = () => { defaultImg.style.display = "none"; };
  defaultImg.src = `/api/branding/default-logo?t=${bust}`;
}

document.getElementById("brand_loginFile").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById("brand_status");
  try {
    await apiUpload("/api/admin/branding/login-logo", file);
    statusEl.textContent = "Login logo updated.";
    statusEl.className = "status-msg ok";
    loadBrandingPreviews();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

document.getElementById("brand_defaultFile").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById("brand_status");
  try {
    await apiUpload("/api/admin/branding/default-logo", file);
    statusEl.textContent = "Default logo updated.";
    statusEl.className = "status-msg ok";
    loadBrandingPreviews();
    await loadOfficesIntoSelects(); // offices without their own logo now show the new default
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

document.getElementById("brand_loginRemove").addEventListener("click", async () => {
  if (!confirm("Remove the login screen logo?")) return;
  const statusEl = document.getElementById("brand_status");
  try {
    await apiDelete("/api/admin/branding/login-logo");
    statusEl.textContent = "Login logo removed.";
    statusEl.className = "status-msg ok";
    loadBrandingPreviews();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

document.getElementById("brand_defaultRemove").addEventListener("click", async () => {
  if (!confirm("Remove the default/province logo? Offices without their own logo will show no logo until a new default is set.")) return;
  const statusEl = document.getElementById("brand_status");
  try {
    await apiDelete("/api/admin/branding/default-logo");
    statusEl.textContent = "Default logo removed.";
    statusEl.className = "status-msg ok";
    loadBrandingPreviews();
    await loadOfficesIntoSelects();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

// ------------------------------------------------------------- proposals --

function yearLabels(year) {
  return { prevYear: year - 2, currentYear: year - 1 };
}

function maxSupplementalCount(lines) {
  let max = 0;
  lines.forEach(l => (l.current_supplementals || []).forEach(s => { if (s.supplemental_number > max) max = s.supplemental_number; }));
  return Math.max(max, 1);
}

const NUM_TABLE_COLS = 12; // base columns excluding dynamic supplementals

function tableHeader(proposalYear, suppColCount) {
  const { prevYear, currentYear } = yearLabels(proposalYear);
  let suppHeaders = "";
  for (let i = 1; i <= suppColCount; i++) {
    suppHeaders += `<th class="num">${currentYear} Supplemental Budget No.${i}</th>`;
  }
  return `<thead><tr>
    <th>Object of Expenditures</th><th>Account Code</th>
    <th class="num">${prevYear} Actual</th>
    <th class="num">Current Year ${currentYear}</th>
    ${suppHeaders}
    <th class="num">${currentYear} Total</th>
    <th class="num">Proposed</th>
    <th class="num">Difference</th>
    <th>Supporting Documents</th>
    <th>Remarks for Proposal</th>
    <th class="num">Adjusted Proposal</th>
    <th>Remarks for Adjusted Proposal</th>
    <th class="num">Approved</th>
  </tr></thead>`;
}

function buildRows(lines, { editableApproved = false, editableAdminFields = false, suppColCount = 1 } = {}) {
  const byClass = {};
  CLASSIFICATION_ORDER.forEach(c => byClass[c] = []);
  lines.forEach(l => { (byClass[l.classification] ||= []).push(l); });
  const totalCols = NUM_TABLE_COLS + suppColCount;

  let rows = "";
  CLASSIFICATION_ORDER.forEach(cls => {
    const group = byClass[cls] || [];
    if (!group.length) return;
    rows += `<tr class="section-row"><td colspan="${totalCols}">${CLASSIFICATION_LABELS[cls]}</td></tr>`;
    let subtotals = { prev: 0, annual: 0, supps: new Array(suppColCount).fill(0), total: 0, proposed: 0, diff: 0, adjusted: 0, approved: 0 };
    group.sort((a, b) => a.account_code.localeCompare(b.account_code) || a.account_name.localeCompare(b.account_name));
    group.forEach(l => {
      subtotals.prev += l.prev_year_actual;
      subtotals.annual += l.current_annual;
      const suppByNum = {};
      (l.current_supplementals || []).forEach(s => { suppByNum[s.supplemental_number] = s.amount; });
      for (let i = 1; i <= suppColCount; i++) subtotals.supps[i - 1] += (suppByNum[i] || 0);
      subtotals.total += l.current_total;
      subtotals.proposed += l.proposed_amount;
      subtotals.diff += l.difference;
      subtotals.adjusted += (l.adjusted_proposal != null ? l.adjusted_proposal : l.proposed_amount);
      subtotals.approved += (l.approved_amount || 0);

      const approvedCell = editableApproved
        ? `<input type="text" inputmode="decimal" oninput="formatMoneyInput(this)" data-account="${l.account_id}" class="approved-input" value="${l.approved_amount != null ? money(l.approved_amount) : ''}">`
        : (l.approved_amount != null ? money(l.approved_amount) : "—");

      const prevCell = editableAdminFields
        ? `<input type="text" inputmode="decimal" oninput="formatMoneyInput(this)" data-account="${l.account_id}" data-field="prev_year_actual" class="admin-field-input" value="${money(l.prev_year_actual ?? 0)}">`
        : money(l.prev_year_actual);

      const adjustedCell = editableAdminFields
        ? `<input type="text" inputmode="decimal" oninput="formatMoneyInput(this)" data-account="${l.account_id}" data-field="adjusted_proposal" class="admin-field-input" value="${l.adjusted_proposal != null ? money(l.adjusted_proposal) : ''}">`
        : (l.adjusted_proposal != null ? money(l.adjusted_proposal) : "—");

      const remarksAdjCell = editableAdminFields
        ? `<textarea data-account="${l.account_id}" data-field="remarks_adjusted" class="admin-field-input remarks-input" rows="2" placeholder="Reason for adjustment...">${l.remarks_adjusted ?? ""}</textarea>`
        : (l.remarks_adjusted ? l.remarks_adjusted.replace(/</g, "&lt;") : "—");

      const attachmentsHtml = (l.attachments || []).length
        ? `<div class="attachment-list">${l.attachments.map(a =>
            `<div class="attachment-item"><a href="#" onclick="downloadAttachment(${a.id}, '${a.filename.replace(/'/g, "\\'")}'); return false;">${a.filename}</a></div>`
          ).join("")}</div>`
        : "—";

      let suppCells = "";
      for (let i = 1; i <= suppColCount; i++) suppCells += `<td class="num">${money(suppByNum[i] ?? 0)}</td>`;

      rows += `<tr>
        <td>${l.account_name}</td>
        <td>${l.account_code}</td>
        <td class="num">${prevCell}</td>
        <td class="num">${money(l.current_annual)}</td>
        ${suppCells}
        <td class="num">${money(l.current_total)}</td>
        <td class="num">${money(l.proposed_amount)}</td>
        <td class="num">${money(l.difference)}</td>
        <td class="attachments-cell">${attachmentsHtml}</td>
        <td class="remarks-cell">${l.remarks ? l.remarks.replace(/</g, "&lt;") : "—"}</td>
        <td class="num">${adjustedCell}</td>
        <td class="remarks-cell">${remarksAdjCell}</td>
        <td class="num">${approvedCell}</td>
      </tr>`;
    });
    let suppSubtotalCells = "";
    for (let i = 0; i < suppColCount; i++) suppSubtotalCells += `<td class="num">${money(subtotals.supps[i])}</td>`;
    rows += `<tr class="subtotal-row">
      <td>Total ${CLASSIFICATION_LABELS[cls]}</td><td></td>
      <td class="num">${money(subtotals.prev)}</td>
      <td class="num">${money(subtotals.annual)}</td>
      ${suppSubtotalCells}
      <td class="num">${money(subtotals.total)}</td>
      <td class="num">${money(subtotals.proposed)}</td>
      <td class="num">${money(subtotals.diff)}</td>
      <td></td><td></td>
      <td class="num">${money(subtotals.adjusted)}</td>
      <td></td>
      <td class="num">${money(subtotals.approved)}</td>
    </tr>`;
  });
  return rows;
}

let currentProposal = null;

document.getElementById("p_type").addEventListener("change", (e) => {
  document.getElementById("p_supplementalField").style.display = e.target.value === "supplemental" ? "block" : "none";
});

function actionLabel(action) {
  return {
    draft_saved: "saved a draft",
    submitted: "submitted the proposal",
    reopened: "reopened the proposal for office editing",
    approved: "saved and locked approved amounts",
    approval_reopened: "reopened the approved amounts for editing",
    attachment_added: "added a supporting document",
    attachment_removed: "removed a supporting document",
  }[action] || action;
}

function renderAuditLog(containerId, entries) {
  const el = document.getElementById(containerId);
  if (!entries.length) { el.innerHTML = ""; return; }
  const items = entries.map(e => {
    const when = new Date(e.timestamp).toLocaleString();
    return `<div class="audit-entry">
      <div><strong>${e.username}</strong> ${actionLabel(e.action)}</div>
      <div class="who-when">${when}${e.detail ? " — " + e.detail : ""}</div>
    </div>`;
  }).join("");
  el.innerHTML = `<h4>Activity</h4><div class="audit-log-scroll">${items}</div>`;
}

async function loadAuditLog(proposalId, containerId) {
  try {
    const { data } = await apiGet(`/api/proposal/${proposalId}/audit-log`, { cacheable: true });
    renderAuditLog(containerId, data);
  } catch (err) {
    document.getElementById(containerId).innerHTML = "";
  }
}

document.getElementById("p_load").addEventListener("click", async () => {
  const office_id = document.getElementById("p_office").value;
  const year = document.getElementById("p_year").value;
  const budget_type = document.getElementById("p_type").value;
  const supp = document.getElementById("p_supplementalNumber").value;
  const statusEl = document.getElementById("p_status");
  statusEl.textContent = "";
  if (!office_id) { statusEl.textContent = "Choose an office first."; statusEl.className = "status-msg error"; return; }
  let path = `/api/proposal?office_id=${office_id}&year=${year}&budget_type=${budget_type}`;
  if (budget_type === "supplemental") path += `&supplemental_number=${supp}`;
  try {
    const { data, fromCache } = await apiGet(path, { cacheable: true });
    currentProposal = data;
    document.getElementById("p_result").style.display = "block";
    const label = budget_type === "supplemental" ? `supplemental No. ${data.supplemental_number}` : "annual";
    document.getElementById("p_officeTitle").textContent = `${data.office_name} — ${label} ${year}`;
    setOfficeLogo("p_officeLogo", data.office_id);

    const statusBadge = document.getElementById("p_statusBadge");
    statusBadge.textContent = data.status === "submitted" ? "Submitted by office" : "Draft (office still editing)";
    statusBadge.className = "badge " + data.status;

    const approvalBadge = document.getElementById("p_approvalBadge");
    const isApproved = data.approval_status === "approved";
    approvalBadge.textContent = isApproved ? "Approved" : "Pending approval";
    approvalBadge.className = "badge " + data.approval_status;

    document.getElementById("p_approveBtn").style.display = isApproved ? "none" : "inline-block";
    document.getElementById("p_reopenApprovalBtn").style.display = isApproved ? "inline-block" : "none";
    document.getElementById("p_approvalNote").textContent = isApproved
      ? "Approved amounts are locked. Click \"Reopen approved amounts\" to change them — this does not affect the office's submission."
      : "Enter approved amounts below, then click \"Save approved amounts\" to lock them in.";

    const suppColCount = maxSupplementalCount(data.lines);
    document.getElementById("p_table").innerHTML =
      tableHeader(data.year, suppColCount) + "<tbody>" +
      buildRows(data.lines, { editableApproved: !isApproved, editableAdminFields: true, suppColCount }) +
      "</tbody>";
    if (fromCache) { statusEl.textContent = "Showing last saved data (offline)."; statusEl.className = "status-msg"; }
    loadAuditLog(data.id, "p_auditLog");
    loadBalance(year, budget_type, supp, "p_balancePanel");
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

document.getElementById("p_saveAdminFieldsBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("p_status");
  if (!currentProposal) return;
  const inputs = document.querySelectorAll(".admin-field-input");
  const byAccount = {};
  inputs.forEach(inp => {
    const id = inp.dataset.account;
    byAccount[id] ||= { account_id: Number(id) };
    if (inp.dataset.field === "remarks_adjusted") {
      byAccount[id].remarks_adjusted = inp.value;
    } else {
      byAccount[id][inp.dataset.field] = inp.value === "" ? null : parseMoney(inp.value);
    }
  });
  try {
    await apiPut(`/api/proposal/${currentProposal.id}/admin-lines`, { lines: Object.values(byAccount) });
    statusEl.textContent = "Previous Year Actual and Adjusted Proposal fields saved.";
    statusEl.className = "status-msg ok";
    document.getElementById("p_load").click();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

document.getElementById("p_approveBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("p_status");
  if (!currentProposal) return;
  const inputs = document.querySelectorAll(".approved-input");
  const lines = Array.from(inputs)
    .filter(inp => inp.value !== "")
    .map(inp => ({ account_id: Number(inp.dataset.account), approved_amount: parseMoney(inp.value) }));
  try {
    await apiPut(`/api/proposal/${currentProposal.id}/approve`, { lines });
    statusEl.textContent = "Approved amounts saved.";
    statusEl.className = "status-msg ok";
    document.getElementById("p_load").click();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

document.getElementById("p_reopenBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("p_status");
  if (!currentProposal) return;
  if (!confirm("Reopen this proposal for the OFFICE to edit? This puts it back to draft status on their side; it does not touch any approved amounts.")) return;
  try {
    await apiPut(`/api/proposal/${currentProposal.id}/reopen`, {});
    statusEl.textContent = "Reopened for the office to edit.";
    statusEl.className = "status-msg ok";
    document.getElementById("p_load").click();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

document.getElementById("p_reopenApprovalBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("p_status");
  if (!currentProposal) return;
  try {
    await apiPut(`/api/proposal/${currentProposal.id}/reopen-approval`, {});
    statusEl.textContent = "Approved amounts reopened for editing.";
    statusEl.className = "status-msg ok";
    document.getElementById("p_load").click();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

// --------------------------------------------------------------- reports --

let currentReport = null;

document.getElementById("r_type").addEventListener("change", (e) => {
  document.getElementById("r_supplementalField").style.display = e.target.value === "supplemental" ? "block" : "none";
});

document.getElementById("r_load").addEventListener("click", async () => {
  const office_id = document.getElementById("r_office").value;
  const year = document.getElementById("r_year").value;
  const budget_type = document.getElementById("r_type").value;
  const supp = document.getElementById("r_supplementalNumber").value;
  if (!office_id) return;
  let path = `/api/proposal?office_id=${office_id}&year=${year}&budget_type=${budget_type}`;
  if (budget_type === "supplemental") path += `&supplemental_number=${supp}`;
  try {
    const { data } = await apiGet(path, { cacheable: true });
    currentReport = data;
    document.getElementById("r_result").style.display = "block";
    const label = budget_type === "supplemental" ? `supplemental No. ${data.supplemental_number}` : "annual";
    const approvalText = data.approval_status === "approved" ? "Approved" : "Pending approval";
    const statusText = data.status === "submitted" ? "Submitted" : "Draft";
    document.getElementById("r_officeTitle").textContent = `${data.office_name} — ${label} ${year} (${statusText} · ${approvalText})`;
    setOfficeLogo("r_officeLogo", data.office_id);
    const suppColCount = maxSupplementalCount(data.lines);
    document.getElementById("r_table").innerHTML =
      tableHeader(data.year, suppColCount) + "<tbody>" + buildRows(data.lines, { suppColCount }) + "</tbody>";
    loadAuditLog(data.id, "r_auditLog");
    loadBalance(year, budget_type, supp, "r_balancePanel");
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("r_download").addEventListener("click", async () => {
  if (!currentReport) { await document.getElementById("r_load").click(); }
  if (!currentReport) return;
  const url = `/api/proposal/${currentReport.id}/excel`;
  try {
    const res = await fetch(url, { headers: { Authorization: "Bearer " + getToken() } });
    if (!res.ok) throw new Error("Could not download — check your connection.");
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${currentReport.office_name}_${currentReport.budget_type}_${currentReport.year}.xlsx`;
    a.click();
  } catch (err) {
    alert(err.message);
  }
});

// -------------------------------------------------------------- accounts --

let ACCOUNTS_CACHE = [];
let editingAccountId = null;

async function loadAccounts() {
  const cls = document.getElementById("a_filter").value;
  const path = "/api/accounts" + (cls ? `?classification=${cls}` : "");
  try {
    const { data } = await apiGet(path, { cacheable: true });
    ACCOUNTS_CACHE = data;
    renderAccountsTable();
  } catch (err) { console.error(err); }
}

function renderAccountsTable() {
  const table = document.getElementById("a_table");
  const rows = ACCOUNTS_CACHE.map(a => {
    if (a.id === editingAccountId) {
      return `<tr>
        <td>
          <select class="edit-classification">
            <option value="PS" ${a.classification === "PS" ? "selected" : ""}>Personal Services</option>
            <option value="MOOE" ${a.classification === "MOOE" ? "selected" : ""}>MOOE</option>
            <option value="CO" ${a.classification === "CO" ? "selected" : ""}>Capital Outlay</option>
            <option value="FE" ${a.classification === "FE" ? "selected" : ""}>Financial Expenses</option>
          </select>
        </td>
        <td><input type="text" class="edit-code" value="${a.code}"></td>
        <td><input type="text" class="edit-name" value="${a.name}" style="width:100%;"></td>
        <td>
          <button class="btn secondary" style="padding:4px 10px;" onclick="saveAccountEdit(${a.id})">Save</button>
          <button class="btn secondary" style="padding:4px 10px;" onclick="cancelAccountEdit()">Cancel</button>
        </td>
      </tr>`;
    }
    return `<tr>
      <td>${CLASSIFICATION_LABELS[a.classification] || a.classification}</td>
      <td>${a.code}</td>
      <td>${a.name}</td>
      <td>
        <button class="btn secondary" style="padding:4px 10px;" onclick="startAccountEdit(${a.id})">Edit</button>
        <button class="btn danger" style="padding:4px 10px;" onclick="deleteAccount(${a.id})">Delete</button>
      </td>
    </tr>`;
  }).join("");
  table.innerHTML = "<thead><tr><th>Classification</th><th>Code</th><th>Name</th><th>Actions</th></tr></thead><tbody>" + rows + "</tbody>";
}

function startAccountEdit(id) {
  editingAccountId = id;
  renderAccountsTable();
}

function cancelAccountEdit() {
  editingAccountId = null;
  renderAccountsTable();
}

async function saveAccountEdit(id) {
  const row = [...document.querySelectorAll("#a_table tbody tr")].find(tr => tr.querySelector(".edit-name"));
  const classification = row.querySelector(".edit-classification").value;
  const code = row.querySelector(".edit-code").value.trim();
  const name = row.querySelector(".edit-name").value.trim();
  const statusEl = document.getElementById("a_status");
  try {
    await apiPut(`/api/accounts/${id}`, { classification, code, name });
    statusEl.textContent = "Account updated.";
    statusEl.className = "status-msg ok";
    editingAccountId = null;
    await loadAccounts();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
}

async function deleteAccount(id) {
  if (!confirm("Delete this account? This can't be undone.")) return;
  const statusEl = document.getElementById("a_status");
  try {
    await apiDelete(`/api/accounts/${id}`);
    statusEl.textContent = "Account deleted.";
    statusEl.className = "status-msg ok";
    await loadAccounts();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
}
document.getElementById("a_filter").addEventListener("change", loadAccounts);

document.getElementById("a_add").addEventListener("click", async () => {
  const classification = document.getElementById("a_classification").value;
  const code = document.getElementById("a_code").value.trim();
  const name = document.getElementById("a_name").value.trim();
  const statusEl = document.getElementById("a_status");
  if (!code || !name) { statusEl.textContent = "Code and name are both required."; statusEl.className = "status-msg error"; return; }
  try {
    await apiPost("/api/accounts", { classification, code, name });
    statusEl.textContent = "Account added.";
    statusEl.className = "status-msg ok";
    document.getElementById("a_code").value = "";
    document.getElementById("a_name").value = "";
    await loadAccounts();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

// ----------------------------------------------------------------- users --

document.getElementById("u_role").addEventListener("change", (e) => {
  document.getElementById("u_officeField").style.display = e.target.value === "client" ? "block" : "none";
});

async function loadUsers() {
  try {
    const { data } = await apiGet("/api/users", { cacheable: true });
    const list = document.getElementById("u_list");
    list.innerHTML = data.map(u => `
      <li>
        <span>${u.username} — ${u.role}${u.office_name ? " (" + u.office_name + ")" : ""}</span>
        ${u.username === "Dher" ? "" : `<button class="btn danger" data-id="${u.id}" style="padding:4px 10px;">Remove</button>`}
      </li>
    `).join("");
    list.querySelectorAll("button[data-id]").forEach(btn => {
      btn.addEventListener("click", async () => {
        if (!confirm("Remove this user?")) return;
        await apiDelete(`/api/users/${btn.dataset.id}`);
        loadUsers();
      });
    });
  } catch (err) { console.error(err); }
}

document.getElementById("u_add").addEventListener("click", async () => {
  const username = document.getElementById("u_username").value.trim();
  const password = document.getElementById("u_password").value;
  const role = document.getElementById("u_role").value;
  const office_id = role === "client" ? Number(document.getElementById("u_office").value) : null;
  const statusEl = document.getElementById("u_status");
  if (!username || !password) { statusEl.textContent = "Username and password are required."; statusEl.className = "status-msg error"; return; }
  try {
    await apiPost("/api/users", { username, password, role, office_id });
    statusEl.textContent = "User added.";
    statusEl.className = "status-msg ok";
    document.getElementById("u_username").value = "";
    document.getElementById("u_password").value = "";
    loadUsers();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

// -------------------------------------------------------- running balance --

function balanceBlock(label, value, colorClass) {
  const text = (value < 0 ? "-" : "") + "₱" + money(Math.abs(value));
  return `
    <div class="balance-item">
      <div class="label">${label}</div>
      <div class="value ${colorClass}">${text}</div>
    </div>`;
}

function renderBalancePanel(containerId, summary) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!summary) { el.innerHTML = ""; return; }
  const proposedClass = summary.balance_vs_proposed < 0 ? "negative" : "positive";
  const adjustedClass = summary.balance_vs_adjusted < 0 ? "negative" : "positive";
  const approvedClass = summary.balance_vs_approved < 0 ? "negative" : "positive";
  el.innerHTML = `
    <div class="balance-item">
      <div class="label">Available Budget</div>
      <div class="value">₱${money(summary.available_budget)}</div>
    </div>
    <div class="balance-item">
      <div class="label">Total Proposed (All Offices)</div>
      <div class="value">₱${money(summary.total_proposed)}</div>
    </div>
    ${balanceBlock("Available Balance vs Total Proposed", summary.balance_vs_proposed, proposedClass)}
    <div class="balance-item">
      <div class="label">Total Adjusted (All Offices)</div>
      <div class="value">₱${money(summary.total_adjusted)}</div>
    </div>
    ${balanceBlock("Available Balance vs Adjusted Proposal", summary.balance_vs_adjusted, adjustedClass)}
    <div class="balance-item">
      <div class="label">Total Approved (All Offices)</div>
      <div class="value">₱${money(summary.total_approved)}</div>
    </div>
    ${balanceBlock("Available Balance vs Approved", summary.balance_vs_approved, approvedClass)}
  `;
}

async function loadBalance(year, budget_type, supp, containerId) {
  let path = `/api/budget-summary?year=${year}&budget_type=${budget_type}`;
  if (budget_type === "supplemental") path += `&supplemental_number=${supp}`;
  try {
    const { data } = await apiGet(path, { cacheable: true });
    renderBalancePanel(containerId, data);
  } catch (err) {
    renderBalancePanel(containerId, null);
  }
}

// -------------------------------------------------------------- funding tab

document.getElementById("f_type").addEventListener("change", (e) => {
  document.getElementById("f_supplementalField").style.display = e.target.value === "supplemental" ? "block" : "none";
});

let FUND_CATEGORIES = [];
async function loadFundCategories() {
  try {
    const { data } = await apiGet("/api/fund-source-categories", { cacheable: true });
    FUND_CATEGORIES = data;
    document.getElementById("f_categoryOptions").innerHTML = data.map(c => `<option value="${c}">`).join("");
  } catch (err) { console.error(err); }
}

let currentFundContext = null;

function renderFundTable(sources) {
  const table = document.getElementById("f_table");
  if (!sources.length) {
    table.innerHTML = "<thead><tr><th>Particulars</th><th class='num'>Amount</th><th>Actions</th></tr></thead><tbody><tr><td colspan='3'>No fund sources added yet for this budget cycle. Click \"Add standard fund sources\" to start from the usual list, or add one below.</td></tr></tbody>";
    return;
  }
  const byCategory = {};
  sources.forEach(s => { (byCategory[s.category] ||= []).push(s); });

  let total = 0;
  let rows = "";
  Object.keys(byCategory).sort().forEach(cat => {
    rows += `<tr class="section-row"><td colspan="3">${cat}</td></tr>`;
    byCategory[cat].forEach(s => {
      total += s.amount;
      rows += `<tr>
        <td>${s.particulars}</td>
        <td class="num">
          <input type="text" inputmode="decimal" oninput="formatMoneyInput(this)" class="fund-amount-input" data-id="${s.id}" value="${money(s.amount)}">
        </td>
        <td>
          <button class="btn secondary" style="padding:4px 10px;" onclick="saveFundAmount(${s.id})">Save</button>
          <button class="btn danger" style="padding:4px 10px;" onclick="deleteFundSource(${s.id})">Delete</button>
        </td>
      </tr>`;
    });
  });
  rows += `<tr class="subtotal-row"><td>Total Available Budget</td><td class="num">${money(total)}</td><td></td></tr>`;
  table.innerHTML = "<thead><tr><th>Particulars</th><th class='num'>Amount</th><th>Actions</th></tr></thead><tbody>" + rows + "</tbody>";
}

async function saveFundAmount(id) {
  const input = document.querySelector(`.fund-amount-input[data-id="${id}"]`);
  const statusEl = document.getElementById("f_status");
  try {
    await apiPut(`/api/fund-sources/${id}`, { amount: parseMoney(input.value) });
    statusEl.textContent = "Amount saved.";
    statusEl.className = "status-msg ok";
    document.getElementById("f_load").click();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
}

document.getElementById("f_load").addEventListener("click", async () => {
  const year = document.getElementById("f_year").value;
  const budget_type = document.getElementById("f_type").value;
  const supp = document.getElementById("f_supplementalNumber").value;
  currentFundContext = { year, budget_type, supp };
  let path = `/api/fund-sources?year=${year}&budget_type=${budget_type}`;
  if (budget_type === "supplemental") path += `&supplemental_number=${supp}`;
  try {
    const { data } = await apiGet(path, { cacheable: true });
    document.getElementById("f_result").style.display = "block";
    renderFundTable(data);
    loadBalance(year, budget_type, supp, "f_balancePanel");
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("f_add").addEventListener("click", async () => {
  const statusEl = document.getElementById("f_status");
  if (!currentFundContext) { statusEl.textContent = "Load a budget cycle first."; statusEl.className = "status-msg error"; return; }
  const category = document.getElementById("f_category").value.trim();
  const particulars = document.getElementById("f_particulars").value.trim();
  const amount = parseMoney(document.getElementById("f_amount").value);
  if (!category || !particulars || !amount) {
    statusEl.textContent = "Category, particulars, and amount are all required.";
    statusEl.className = "status-msg error";
    return;
  }
  try {
    await apiPost("/api/fund-sources", {
      year: Number(currentFundContext.year),
      budget_type: currentFundContext.budget_type,
      supplemental_number: currentFundContext.budget_type === "supplemental" ? Number(currentFundContext.supp) : null,
      category, particulars, amount,
    });
    statusEl.textContent = "Fund source added.";
    statusEl.className = "status-msg ok";
    document.getElementById("f_category").value = "";
    document.getElementById("f_particulars").value = "";
    document.getElementById("f_amount").value = "";
    document.getElementById("f_load").click();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

document.getElementById("f_seedStandard").addEventListener("click", async () => {
  const statusEl = document.getElementById("f_status");
  if (!currentFundContext) return;
  try {
    await apiPost("/api/fund-sources/seed-standard", {
      year: Number(currentFundContext.year),
      budget_type: currentFundContext.budget_type,
      supplemental_number: currentFundContext.budget_type === "supplemental" ? Number(currentFundContext.supp) : null,
    });
    statusEl.textContent = "Standard fund sources added — fill in the amounts below.";
    statusEl.className = "status-msg ok";
    document.getElementById("f_load").click();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

async function deleteFundSource(id) {
  if (!confirm("Delete this fund source?")) return;
  try {
    await apiDelete(`/api/fund-sources/${id}`);
    document.getElementById("f_load").click();
  } catch (err) {
    alert(err.message);
  }
}

// ------------------------------------------------------------------ init --
loadOfficesIntoSelects();
loadBrandingPreviews();
loadAccounts();
loadUsers();
loadFundCategories();
loadProrateAccountOptions();

// ---------------------------------------------------------- summary report

document.getElementById("s_type").addEventListener("change", (e) => {
  document.getElementById("s_supplementalField").style.display = e.target.value === "supplemental" ? "block" : "none";
});

function summaryTableHeader() {
  return `<thead><tr>
    <th>Object of Expenditures</th><th>Account Code</th>
    <th class="num">Prev Year Actual (Total)</th><th class="num">Current Year (Total)</th>
    <th class="num">Current Total</th>
    <th class="num">Total Proposed (All Offices)</th>
    <th class="num">Total Adjusted (All Offices)</th>
    <th class="num">Total Approved (All Offices)</th>
    <th class="num"># Offices</th>
  </tr></thead>`;
}

function buildSummaryRows(rows) {
  const byClass = {};
  CLASSIFICATION_ORDER.forEach(c => byClass[c] = []);
  rows.forEach(r => { (byClass[r.classification] ||= []).push(r); });

  let html = "";
  CLASSIFICATION_ORDER.forEach(cls => {
    const group = byClass[cls] || [];
    if (!group.length) return;
    html += `<tr class="section-row"><td colspan="9">${CLASSIFICATION_LABELS[cls]}</td></tr>`;
    let t = { prev: 0, annual: 0, total: 0, proposed: 0, adjusted: 0, approved: 0 };
    group.sort((a, b) => a.account_code.localeCompare(b.account_code) || a.account_name.localeCompare(b.account_name));
    group.forEach(r => {
      t.prev += r.total_prev_year_actual; t.annual += r.total_current_annual; t.total += r.total_current_total;
      t.proposed += r.total_proposed; t.adjusted += r.total_adjusted; t.approved += r.total_approved;
      html += `<tr>
        <td>${r.account_name}</td><td>${r.account_code}</td>
        <td class="num">${money(r.total_prev_year_actual)}</td>
        <td class="num">${money(r.total_current_annual)}</td>
        <td class="num">${money(r.total_current_total)}</td>
        <td class="num">${money(r.total_proposed)}</td>
        <td class="num">${money(r.total_adjusted)}</td>
        <td class="num">${money(r.total_approved)}</td>
        <td class="num">${r.offices_included}</td>
      </tr>`;
    });
    html += `<tr class="subtotal-row">
      <td>Total ${CLASSIFICATION_LABELS[cls]}</td><td></td>
      <td class="num">${money(t.prev)}</td><td class="num">${money(t.annual)}</td>
      <td class="num">${money(t.total)}</td><td class="num">${money(t.proposed)}</td>
      <td class="num">${money(t.adjusted)}</td><td class="num">${money(t.approved)}</td><td></td>
    </tr>`;
  });
  return html;
}

let currentSummary = null;

document.getElementById("s_load").addEventListener("click", async () => {
  const year = document.getElementById("s_year").value;
  const budget_type = document.getElementById("s_type").value;
  const supp = document.getElementById("s_supplementalNumber").value;
  let path = `/api/admin/summary-report?year=${year}&budget_type=${budget_type}`;
  if (budget_type === "supplemental") path += `&supplemental_number=${supp}`;
  try {
    const { data } = await apiGet(path, { cacheable: true });
    currentSummary = data;
    document.getElementById("s_result").style.display = "block";
    const label = budget_type === "supplemental" ? `supplemental No. ${data.supplemental_number}` : "annual";
    document.getElementById("s_title").textContent = `${label} ${year} — ${data.offices_count} office(s) with a proposal`;
    const sLogo = document.getElementById("s_logo");
    sLogo.onload = () => { sLogo.style.display = "block"; };
    sLogo.onerror = () => { sLogo.style.display = "none"; };
    sLogo.src = `/api/branding/default-logo?t=${Date.now()}`;
    document.getElementById("s_table").innerHTML = summaryTableHeader() + "<tbody>" + buildSummaryRows(data.rows) + "</tbody>";
    loadBalance(year, budget_type, supp, "s_balancePanel");
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("s_download").addEventListener("click", async () => {
  const year = document.getElementById("s_year").value;
  const budget_type = document.getElementById("s_type").value;
  const supp = document.getElementById("s_supplementalNumber").value;
  let path = `/api/admin/summary-report/excel?year=${year}&budget_type=${budget_type}`;
  if (budget_type === "supplemental") path += `&supplemental_number=${supp}`;
  try {
    const res = await fetch(path, { headers: { Authorization: "Bearer " + getToken() } });
    if (!res.ok) throw new Error("Could not download — check your connection.");
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `Summary_${budget_type}_${year}.xlsx`;
    a.click();
  } catch (err) {
    alert(err.message);
  }
});

// -------------------------------------------------------------- prorate tool

document.getElementById("pr_type").addEventListener("change", (e) => {
  document.getElementById("pr_supplementalField").style.display = e.target.value === "supplemental" ? "block" : "none";
});

async function loadProrateAccountOptions() {
  try {
    const { data } = await apiGet("/api/accounts", { cacheable: true });
    const sel = document.getElementById("pr_account");
    sel.innerHTML = data.map(a => `<option value="${a.id}">${a.name} (${a.code})</option>`).join("");
    // Nudge toward the two accounts this tool is meant for, if present.
    const target = data.find(a => /other general services|other professional services/i.test(a.name));
    if (target) sel.value = target.id;
  } catch (err) { console.error(err); }
}

function renderProratePreview(preview) {
  const table = document.getElementById("pr_previewTable");
  const rows = preview.rows.map(r => `
    <tr>
      <td>${r.office_name}</td>
      <td class="num">${money(r.current_proposed)}</td>
      <td class="num">${money(r.new_adjusted)}</td>
      <td class="num">${money(r.change)}</td>
    </tr>
  `).join("");
  table.innerHTML = `<thead><tr><th>Office</th><th class="num">Current Proposed</th><th class="num">New Adjusted (${preview.months} mo.)</th><th class="num">Change</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="4">No offices have proposed an amount for this account in this budget cycle yet.</td></tr>'}
    <tr class="subtotal-row">
      <td>Total</td>
      <td class="num">${money(preview.total_current_proposed)}</td>
      <td class="num">${money(preview.total_new_adjusted)}</td>
      <td class="num">${money(preview.total_change)}</td>
    </tr></tbody>`;
  document.getElementById("pr_previewWrap").style.display = "block";
  document.getElementById("pr_applyRow").style.display = preview.rows.length ? "block" : "none";
}

let lastProratePayload = null;

document.getElementById("pr_previewBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("pr_status");
  const payload = {
    year: Number(document.getElementById("pr_year").value),
    budget_type: document.getElementById("pr_type").value,
    supplemental_number: document.getElementById("pr_type").value === "supplemental"
      ? Number(document.getElementById("pr_supplementalNumber").value) : null,
    account_id: Number(document.getElementById("pr_account").value),
    months: Number(document.getElementById("pr_months").value),
  };
  lastProratePayload = payload;
  try {
    const preview = await apiPost("/api/admin/prorate-account/preview", payload);
    renderProratePreview(preview);
    statusEl.textContent = `Previewing "${preview.account_name}" prorated to ${preview.months} of 12 months. Nothing has been saved yet.`;
    statusEl.className = "status-msg";
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

document.getElementById("pr_applyBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("pr_status");
  if (!lastProratePayload) return;
  if (!confirm(`Apply this adjustment to ALL offices' Adjusted Proposal for this account? This does not change the original Proposed amount or any already-Approved amount.`)) return;
  try {
    const result = await apiPost("/api/admin/prorate-account/apply", lastProratePayload);
    renderProratePreview(result);
    statusEl.textContent = `Applied — Adjusted Proposal updated for ${result.rows.length} office(s).`;
    statusEl.className = "status-msg ok";
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

// --------------------------------------------------------- backup/cleanup --

document.getElementById("bk_downloadBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("bk_downloadStatus");
  statusEl.textContent = "Preparing backup... this may take a moment if there are many attachments.";
  statusEl.className = "status-msg";
  try {
    const res = await fetch("/api/admin/backup", { headers: { Authorization: "Bearer " + getToken() } });
    if (!res.ok) throw new Error("Backup failed — check your connection and try again.");
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const stamp = new Date().toISOString().replace(/[:T]/g, "-").slice(0, 19);
    a.download = `budget_app_backup_${stamp}.zip`;
    a.click();
    statusEl.textContent = "Backup downloaded.";
    statusEl.className = "status-msg ok";
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

document.getElementById("bk_cleanupAttachments").addEventListener("click", async () => {
  const statusEl = document.getElementById("bk_cleanupStatus");
  const year = Number(document.getElementById("bk_attachYear").value);
  if (!confirm(`Delete all attachment files for ${year}? Proposal amounts and remarks for that year are NOT affected — only the uploaded files. Make sure you've downloaded a backup first. This cannot be undone.`)) return;
  try {
    const result = await apiPost("/api/admin/cleanup-attachments", { year });
    const mb = (result.bytes_freed / (1024 * 1024)).toFixed(2);
    statusEl.textContent = `Deleted ${result.deleted_count} attachment(s), freeing about ${mb} MB.`;
    statusEl.className = "status-msg ok";
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

function checkPurgeConfirmMatch() {
  const year = document.getElementById("bk_purgeYear").value;
  const confirmVal = document.getElementById("bk_purgeConfirm").value;
  document.getElementById("bk_purgeBtn").disabled = !(year && confirmVal && year === confirmVal);
}
document.getElementById("bk_purgeYear").addEventListener("input", checkPurgeConfirmMatch);
document.getElementById("bk_purgeConfirm").addEventListener("input", checkPurgeConfirmMatch);

document.getElementById("bk_purgeBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("bk_purgeStatus");
  const year = Number(document.getElementById("bk_purgeYear").value);
  const confirmYear = Number(document.getElementById("bk_purgeConfirm").value);
  if (!confirm(`FINAL CONFIRMATION: permanently delete ALL proposal data for ${year}, for every office? This cannot be undone. Have you already downloaded a backup?`)) return;
  try {
    const res = await fetch("/api/admin/purge-year", {
      method: "DELETE",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + getToken() },
      body: JSON.stringify({ year, confirm_year: confirmYear }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Delete failed.");
    }
    const result = await res.json();
    statusEl.textContent = `Deleted ${result.deleted_proposals} proposal(s), ${result.deleted_lines} line item(s), and ${result.deleted_attachments} attachment(s) for ${year}.`;
    statusEl.className = "status-msg ok";
    document.getElementById("bk_purgeConfirm").value = "";
    checkPurgeConfirmMatch();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});
