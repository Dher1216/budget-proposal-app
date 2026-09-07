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

function tableHeader() {
  return `<thead><tr>
    <th>Object of Expenditures</th><th>Account Code</th>
    <th class="num">Prev Year Actual</th><th class="num">Current Annual</th>
    <th class="num">Current Supplemental</th><th class="num">Current Total</th>
    <th class="num">Proposed</th><th>Remarks</th><th>Supporting Documents</th>
    <th class="num">Difference</th><th class="num">Approved</th>
  </tr></thead>`;
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

function buildRows(lines, editable) {
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

      const field = (key, val) => editable
        ? `<input type="number" step="0.01" data-account="${l.account_id}" data-field="${key}" class="edit-input" value="${val ?? 0}">`
        : money(val);

      const remarksCell = editable
        ? `<textarea data-account="${l.account_id}" data-field="remarks" class="edit-input remarks-input" rows="2" placeholder="Justify this amount...">${l.remarks ?? ""}</textarea>`
        : (l.remarks ? l.remarks.replace(/</g, "&lt;") : "—");

      rows += `<tr>
        <td>${l.account_name}</td>
        <td>${l.account_code}</td>
        <td class="num">${field("prev_year_actual", l.prev_year_actual)}</td>
        <td class="num">${field("current_annual", l.current_annual)}</td>
        <td class="num">${field("current_supplemental", l.current_supplemental)}</td>
        <td class="num">${money(l.current_total)}</td>
        <td class="num">${field("proposed_amount", l.proposed_amount)}</td>
        <td class="remarks-cell">${remarksCell}</td>
        <td class="attachments-cell">${renderAttachmentList(l, editable)}</td>
        <td class="num">${money(l.difference)}</td>
        <td class="num">${l.approved_amount != null ? money(l.approved_amount) : "—"}</td>
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

function renderProposal(data, fromCache) {
  currentProposal = data;
  const editable = data.status === "draft";
  document.getElementById("c_result").style.display = "block";
  const typeLabel = data.budget_type === "supplemental" ? `supplemental No. ${data.supplemental_number}` : "annual";
  document.getElementById("c_title").textContent = `${typeLabel} proposal — ${document.getElementById("c_year").value}`;
  const badge = document.getElementById("c_statusBadge");
  badge.textContent = data.status;
  badge.className = "badge " + data.status;
  document.getElementById("c_lockNote").style.display = editable ? "none" : "block";
  document.getElementById("c_saveBtn").disabled = !editable;
  document.getElementById("c_submitBtn").disabled = !editable;
  document.getElementById("c_editBtn").style.display = editable ? "none" : "inline-block";
  document.getElementById("c_table").innerHTML = tableHeader() + "<tbody>" + buildRows(data.lines, editable) + "</tbody>";

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
    } else {
      byAccount[id][inp.dataset.field] = Number(inp.value || 0);
    }
  });
  return Object.values(byAccount);
}

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
