requireLogin("client");
document.getElementById("whoami").textContent = `${getUsername()} — ${getOfficeName()}`;

let currentProposal = null;
let loadedKey = null;   // tracks which {type, year, supplementalNumber} currentProposal actually belongs to

function currentSelectionKey() {
  const budget_type = document.getElementById("c_type").value;
  const year = document.getElementById("c_year").value;
  const supp = budget_type === "supplemental" ? document.getElementById("c_supplementalNumber").value : "";
  return `${budget_type}|${year}|${supp}`;
}

function resetLoadedProposal() {
  currentProposal = null;
  loadedKey = null;
  document.getElementById("c_result").style.display = "none";
}

// Any time the office changes what they're looking at, force an explicit
// reload before letting them save/submit -- otherwise a save could silently
// land on whatever proposal happened to be loaded before (e.g. Annual on
// first page load), even though the screen looks like it's showing
// Supplemental.
["c_type", "c_year", "c_supplementalNumber"].forEach(id => {
  document.getElementById(id).addEventListener("input", resetLoadedProposal);
  document.getElementById(id).addEventListener("change", resetLoadedProposal);
});

function yearLabels(year) {
  return {
    prevYear: year - 2,
    currentYear: year - 1,
  };
}

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

function maxSupplementalCount(lines) {
  let max = 0;
  lines.forEach(l => (l.current_supplementals || []).forEach(s => { if (s.supplemental_number > max) max = s.supplemental_number; }));
  return Math.max(max, 1);
}

function renderAttachmentList(line, editable) {
  const items = (line.attachments || []).map(a => `
    <div class="attachment-item" data-attachment-id="${a.id}">
      <a href="#" onclick="downloadAttachment(${a.id}, '${a.filename.replace(/'/g, "\\'")}'); return false;">${a.filename}</a>
      ${editable ? `<button class="attachment-remove" onclick="removeAttachment(${a.id})" title="Remove">✕</button>` : ""}
    </div>
  `).join("");
  const uploadControl = editable ? `
    <div class="attachment-upload">
      <input type="file" id="file-${line.account_id}" style="display:none;" onchange="handleAttachmentUpload(${line.id}, ${line.account_id})">
      <button class="btn secondary" style="padding:4px 10px; font-size:12px;" onclick="document.getElementById('file-${line.account_id}').click()">+ Attach file</button>
    </div>` : "";
  return `<div class="attachment-list">${items}</div>${uploadControl}`;
}

const NUM_TABLE_COLS = 12; // base columns excluding dynamic supplementals

function buildRows(lines, editable, suppColCount) {
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

      const field = (key, val) => editable
        ? `<input type="text" inputmode="decimal" oninput="formatMoneyInput(this)" data-account="${l.account_id}" data-field="${key}" class="edit-input" value="${money(val ?? 0)}">`
        : money(val);

      const remarksCell = editable
        ? `<textarea data-account="${l.account_id}" data-field="remarks" class="edit-input remarks-input" rows="2" placeholder="Justify this amount...">${l.remarks ?? ""}</textarea>`
        : (l.remarks ? l.remarks.replace(/</g, "&lt;") : "—");

      let suppCells = "";
      for (let i = 1; i <= suppColCount; i++) {
        const val = suppByNum[i] ?? 0;
        suppCells += `<td class="num">${editable
          ? `<input type="text" inputmode="decimal" oninput="formatMoneyInput(this)" data-account="${l.account_id}" data-field="supp" data-supp-num="${i}" class="edit-input" value="${money(val)}">`
          : money(val)}</td>`;
      }

      rows += `<tr>
        <td>${l.account_name}</td>
        <td>${l.account_code}</td>
        <td class="num">${money(l.prev_year_actual)}</td>
        <td class="num">${field("current_annual", l.current_annual)}</td>
        ${suppCells}
        <td class="num">${money(l.current_total)}</td>
        <td class="num">${field("proposed_amount", l.proposed_amount)}</td>
        <td class="num">${money(l.difference)}</td>
        <td class="attachments-cell">${renderAttachmentList(l, editable)}</td>
        <td class="remarks-cell">${remarksCell}</td>
        <td class="num">${l.adjusted_proposal != null ? money(l.adjusted_proposal) : "—"}</td>
        <td class="remarks-cell">${l.remarks_adjusted ? l.remarks_adjusted.replace(/</g, "&lt;") : "—"}</td>
        <td class="num">${l.approved_amount != null ? money(l.approved_amount) : "—"}</td>
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

function renderProposal(data, fromCache) {
  currentProposal = data;
  const editable = data.status === "draft";
  document.getElementById("c_result").style.display = "block";
  const typeLabel = data.budget_type === "supplemental"
    ? `SUPPLEMENTAL BUDGET NO. ${data.supplemental_number} ${document.getElementById("c_year").value}`
    : `ANNUAL BUDGET ${document.getElementById("c_year").value}`;
  document.getElementById("c_titleMain").textContent = typeLabel;
  document.getElementById("c_titleSub").textContent = getOfficeName();
  const officeLogo = document.getElementById("c_officeLogo");
  officeLogo.onload = () => { officeLogo.style.display = "block"; };
  officeLogo.onerror = () => { officeLogo.style.display = "none"; };
  officeLogo.src = `/api/offices/${getOfficeId()}/logo?t=${Date.now()}`;
  const badge = document.getElementById("c_statusBadge");
  badge.textContent = data.status;
  badge.className = "badge " + data.status;

  if (data.locked_by_admin) {
    document.getElementById("c_lockNote").style.display = "block";
    document.getElementById("c_lockNote").textContent =
      "This proposal has been locked by the admin (e.g. for a budget hearing). Only the admin can reopen it — please contact them if you need to make changes.";
    document.getElementById("c_editBtn").style.display = "none";
  } else {
    document.getElementById("c_lockNote").style.display = editable ? "none" : "block";
    document.getElementById("c_lockNote").textContent =
      "This proposal has been submitted. Click \"Edit this proposal\" if you need to make corrections — it stays the same proposal (no duplicate is created), it just reopens for editing.";
    document.getElementById("c_editBtn").style.display = editable ? "none" : "inline-block";
  }
  document.getElementById("c_saveBtn").disabled = !editable;
  document.getElementById("c_submitBtn").disabled = !editable;
  document.getElementById("c_addSupplementalBtn").style.display = editable ? "inline-block" : "none";

  const suppColCount = maxSupplementalCount(data.lines);
  document.getElementById("c_table").innerHTML =
    tableHeader(data.year, suppColCount) + "<tbody>" + buildRows(data.lines, editable, suppColCount) + "</tbody>";

  const statusEl = document.getElementById("c_status");
  statusEl.textContent = fromCache ? "Showing last saved data (offline)." : "";
  statusEl.className = "status-msg";
}

document.getElementById("c_type").addEventListener("change", (e) => {
  document.getElementById("c_supplementalField").style.display = e.target.value === "supplemental" ? "block" : "none";
});

document.getElementById("c_load").addEventListener("click", async () => {
  const key = currentSelectionKey();
  const year = document.getElementById("c_year").value;
  const budget_type = document.getElementById("c_type").value;
  const supp = document.getElementById("c_supplementalNumber").value;
  const statusEl = document.getElementById("c_status");
  let path = `/api/proposal?office_id=${getOfficeId()}&year=${year}&budget_type=${budget_type}`;
  if (budget_type === "supplemental") path += `&supplemental_number=${supp}`;
  try {
    const { data, fromCache } = await apiGet(path, { cacheable: true });
    loadedKey = key;
    renderProposal(data, fromCache);
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

function collectEditedLines() {
  const inputs = document.querySelectorAll(".edit-input");
  const byAccount = {};
  inputs.forEach(inp => {
    const id = inp.dataset.account;
    byAccount[id] ||= { account_id: Number(id) };
    if (inp.dataset.field === "remarks") {
      byAccount[id].remarks = inp.value;
    } else if (inp.dataset.field === "supp") {
      byAccount[id].current_supplementals ||= {};
      byAccount[id].current_supplementals[inp.dataset.suppNum] = parseMoney(inp.value);
    } else {
      byAccount[id][inp.dataset.field] = parseMoney(inp.value);
    }
  });
  return Object.values(byAccount);
}

document.getElementById("c_addSupplementalBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("c_status");
  if (!currentProposal) return;
  try {
    const data = await apiPost(`/api/proposal/${currentProposal.id}/add-current-supplemental`, {});
    renderProposal(data, false);
    statusEl.textContent = "Added a new current-year supplemental column — fill in its amounts below.";
    statusEl.className = "status-msg ok";
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

async function handleAttachmentUpload(lineId, accountId) {
  const input = document.getElementById(`file-${accountId}`);
  const file = input.files[0];
  if (!file) return;
  const statusEl = document.getElementById("c_status");
  try {
    const attachment = await apiUpload(`/api/proposal-lines/${lineId}/attachments`, file);
    // Update just this cell so any unsaved edits elsewhere in the table survive.
    const listEl = input.closest(".attachment-list") || input.closest(".attachments-cell").querySelector(".attachment-list");
    const filenameEscaped = attachment.filename.replace(/'/g, "\\'");
    const item = document.createElement("div");
    item.className = "attachment-item";
    item.dataset.attachmentId = attachment.id;
    item.innerHTML = `<a href="#" onclick="downloadAttachment(${attachment.id}, '${filenameEscaped}'); return false;">${attachment.filename}</a>
      <button class="attachment-remove" onclick="removeAttachment(${attachment.id})" title="Remove">✕</button>`;
    listEl.appendChild(item);
    input.value = "";
    statusEl.textContent = "File attached.";
    statusEl.className = "status-msg ok";
    if (currentProposal) {
      const line = currentProposal.lines.find(l => l.id === lineId);
      if (line) line.attachments.push(attachment);
    }
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
}

async function removeAttachment(attachmentId) {
  if (!confirm("Remove this attachment?")) return;
  const statusEl = document.getElementById("c_status");
  try {
    await apiDelete(`/api/attachments/${attachmentId}`);
    const el = document.querySelector(`.attachment-item[data-attachment-id="${attachmentId}"]`);
    if (el) el.remove();
    statusEl.textContent = "Attachment removed.";
    statusEl.className = "status-msg ok";
    if (currentProposal) {
      currentProposal.lines.forEach(l => {
        l.attachments = (l.attachments || []).filter(a => a.id !== attachmentId);
      });
    }
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
}

async function saveLines(submit) {
  const statusEl = document.getElementById("c_status");
  if (!currentProposal || loadedKey !== currentSelectionKey()) {
    statusEl.textContent = "Click \"Load proposal\" for the selected type/year first — the selection changed since it was last loaded.";
    statusEl.className = "status-msg error";
    return;
  }
  if (submit && !confirm("Submit this proposal? Once submitted you won't be able to edit it unless you or the admin reopens it.")) return;
  try {
    const lines = collectEditedLines();
    await apiPut(`/api/proposal/${currentProposal.id}/lines`, { lines, submit });
    statusEl.textContent = submit ? "Proposal submitted." : "Draft saved.";
    statusEl.className = "status-msg ok";
    document.getElementById("c_load").click();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
}

document.getElementById("c_saveBtn").addEventListener("click", () => saveLines(false));
document.getElementById("c_submitBtn").addEventListener("click", () => saveLines(true));

document.getElementById("c_editBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("c_status");
  if (!currentProposal) return;
  if (!confirm("Reopen this proposal for editing? It stays the same proposal — no duplicate will be created.")) return;
  try {
    await apiPut(`/api/proposal/${currentProposal.id}/reopen`, {});
    statusEl.textContent = "Reopened — you can edit and resubmit.";
    statusEl.className = "status-msg ok";
    document.getElementById("c_load").click();
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "status-msg error";
  }
});

document.getElementById("c_downloadBtn").addEventListener("click", async () => {
  if (!currentProposal) return;
  try {
    const res = await fetch(`/api/proposal/${currentProposal.id}/excel`, {
      headers: { Authorization: "Bearer " + getToken() }
    });
    if (!res.ok) throw new Error("Could not download — check your connection.");
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${getOfficeName()}_${currentProposal.budget_type}_${currentProposal.year}.xlsx`;
    a.click();
  } catch (err) {
    alert(err.message);
  }
});

// Auto-load current year's annual proposal on first visit.
document.getElementById("c_load").click();
