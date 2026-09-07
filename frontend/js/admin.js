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

function renderOfficeList() {
  const list = document.getElementById("o_list");
  if (!OFFICES.length) { list.innerHTML = "<li>No offices yet.</li>"; return; }
  list.innerHTML = OFFICES.map(o =>
    `<li><span>${o.name}${o.code ? " — " + o.code : ""}${o.sector ? " (" + o.sector + ")" : ""}</span></li>`
  ).join("");
}

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

// ------------------------------------------------------------- proposals --

function buildRows(lines, { editableApproved = false } = {}) {
  const byClass = {};
  CLASSIFICATION_ORDER.forEach(c => byClass[c] = []);
  lines.forEach(l => { (byClass[l.classification] ||= []).push(l); });

  let rows = "";
  CLASSIFICATION_ORDER.forEach(cls => {
    const group = byClass[cls] || [];
    if (!group.length) return;
    rows += `<tr class="section-row"><td colspan="11">${CLASSIFICATION_LABELS[cls]}</td></tr>`;
    let subtotals = { prev: 0, annual: 0, supp: 0, total: 0, proposed: 0, diff: 0, approved: 0 };
    group.sort((a, b) => a.account_code.localeCompare(b.account_code) || a.account_name.localeCompare(b.account_name));
    group.forEach(l => {
      subtotals.prev += l.prev_year_actual;
      subtotals.annual += l.current_annual;
      subtotals.supp += l.current_supplemental;
      subtotals.total += l.current_total;
      subtotals.proposed += l.proposed_amount;
      subtotals.diff += l.difference;
      subtotals.approved += (l.approved_amount || 0);
      const approvedCell = editableApproved
        ? `<input type="number" step="0.01" data-account="${l.account_id}" class="approved-input" value="${l.approved_amount ?? ""}">`
        : (l.approved_amount != null ? money(l.approved_amount) : "—");
      const attachmentsHtml = (l.attachments || []).length
        ? `<div class="attachment-list">${l.attachments.map(a =>
            `<div class="attachment-item"><a href="#" onclick="downloadAttachment(${a.id}, '${a.filename.replace(/'/g, "\\'")}'); return false;">${a.filename}</a></div>`
          ).join("")}</div>`
        : "—";
      rows += `<tr>
        <td>${l.account_name}</td>
        <td>${l.account_code}</td>
        <td class="num">${money(l.prev_year_actual)}</td>
        <td class="num">${money(l.current_annual)}</td>
        <td class="num">${money(l.current_supplemental)}</td>
        <td class="num">${money(l.current_total)}</td>
        <td class="num">${money(l.proposed_amount)}</td>
        <td class="remarks-cell">${l.remarks ? l.remarks.replace(/</g, "&lt;") : "—"}</td>
        <td class="attachments-cell">${attachmentsHtml}</td>
        <td class="num">${money(l.difference)}</td>
        <td class="num">${approvedCell}</td>
      </tr>`;
    });
    rows += `<tr class="subtotal-row">
      <td>Total ${CLASSIFICATION_LABELS[cls]}</td><td></td>
      <td class="num">${money(subtotals.prev)}</td>
      <td class="num">${money(subtotals.annual)}</td>
      <td class="num">${money(subtotals.supp)}</td>
      <td class="num">${money(subtotals.total)}</td>
      <td class="num">${money(subtotals.proposed)}</td>
      <td></td><td></td>
      <td class="num">${money(subtotals.diff)}</td>
      <td class="num">${money(subtotals.approved)}</td>
    </tr>`;
  });
  return rows;
}

function tableHeader() {
  return `<thead><tr>
    <th>Object of Expenditures</th><th>Account Code</th>
    <th class="num">Prev Year Actual</th><th class="num">Current Annual</th>
    <th class="num">Current Supplemental</th><th class="num">Current Total</th>
    <th class="num">Proposed</th><th>Remarks</th><th>Supporting Documents</th>
    <th class="num">Difference</th><th class="num">Approved</th>
  </tr></thead>`;
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
  el.innerHTML = "<h4>Activity</h4>" + entries.map(e => {
    const when = new Date(e.timestamp).toLocaleString();
    return `<div class="audit-entry">
      <div><strong>${e.username}</strong> ${actionLabel(e.action)}</div>
      <div class="who-when">${when}${e.detail ? " — " + e.detail : ""}</div>
    </div>`;
  }).join("");
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

    document.getElementById("p_table").innerHTML = tableHeader() + "<tbody>" + buildRows(data.lines, { editableApproved: !isApproved }) + "</tbody>";
    if (fromCache) { statusEl.textContent = "Showing last saved data (offline)."; statusEl.className = "status-msg"; }
    loadAuditLog(data.id, "p_auditLog");
    loadBalance(year, budget_type, supp, "p_balancePanel");
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
    .map(inp => ({ account_id: Number(inp.dataset.account), approved_amount: Number(inp.value) }));
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
    document.getElementById("r_table").innerHTML = tableHeader() + "<tbody>" + buildRows(data.lines) + "</tbody>";
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

function renderBalancePanel(containerId, summary) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!summary) { el.innerHTML = ""; return; }
  const balanceClass = summary.balance < 0 ? "negative" : "positive";
  const balanceText = (summary.balance < 0 ? "-" : "") + "₱" + money(Math.abs(summary.balance));
  el.innerHTML = `
    <div class="balance-item">
      <div class="label">Available Budget</div>
      <div class="value">₱${money(summary.available_budget)}</div>
    </div>
    <div class="balance-item">
      <div class="label">Total Proposed (All Offices)</div>
      <div class="value">₱${money(summary.total_proposed)}</div>
    </div>
    <div class="balance-item">
      <div class="label">Running Balance</div>
      <div class="value ${balanceClass}">${balanceText}</div>
    </div>
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
          <input type="number" step="0.01" class="fund-amount-input" data-id="${s.id}" value="${s.amount}">
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
    await apiPut(`/api/fund-sources/${id}`, { amount: Number(input.value) });
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
  const amount = Number(document.getElementById("f_amount").value);
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
loadAccounts();
loadUsers();
loadFundCategories();
