import os
import io
import json
import zipfile
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_

import models
import schemas
from database import get_db, engine, Base
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin,
)
from excel_export import build_report_workbook, build_summary_workbook, build_lbp_form1_workbook

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Provincial Budget Proposal System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your real domain(s) once deployed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- helpers --

def account_classification_str(a: models.Account) -> str:
    return a.classification.value if hasattr(a.classification, "value") else a.classification


def line_to_out(line: models.ProposalLine) -> schemas.ProposalLineOut:
    supplementals = sorted(line.current_supplementals, key=lambda s: s.supplemental_number)
    supp_total = sum(s.amount or 0 for s in supplementals)
    current_total = (line.current_annual or 0) + supp_total
    difference = (line.proposed_amount or 0) - current_total
    return schemas.ProposalLineOut(
        id=line.id,
        account_id=line.account_id,
        account_code=line.account.code,
        account_name=line.account.name,
        classification=account_classification_str(line.account),
        prev_year_actual=line.prev_year_actual or 0,
        current_annual=line.current_annual or 0,
        current_supplementals=[
            schemas.CurrentSupplementalOut(supplemental_number=s.supplemental_number, amount=s.amount or 0)
            for s in supplementals
        ],
        current_total=current_total,
        proposed_amount=line.proposed_amount or 0,
        difference=difference,
        adjusted_proposal=line.adjusted_proposal,
        remarks_adjusted=line.remarks_adjusted,
        approved_amount=line.approved_amount,
        remarks=line.remarks,
        attachments=[
            schemas.AttachmentOut(
                id=a.id, filename=a.filename, uploaded_by=a.uploaded_by,
                uploaded_at=a.uploaded_at.isoformat() + "Z",
            ) for a in line.attachments
        ],
    )


def proposal_to_out(p: models.Proposal) -> schemas.ProposalOut:
    lines = sorted(p.lines, key=lambda l: (l.account.classification.value, l.account.code, l.account.name))
    return schemas.ProposalOut(
        id=p.id,
        office_id=p.office_id,
        office_name=p.office.name,
        office_code=p.office.code,
        office_sector=p.office.sector,
        year=p.year,
        budget_type=p.budget_type.value if hasattr(p.budget_type, "value") else p.budget_type,
        supplemental_number=p.supplemental_number,
        status=p.status.value if hasattr(p.status, "value") else p.status,
        approval_status=p.approval_status.value if hasattr(p.approval_status, "value") else p.approval_status,
        locked_by_admin=p.locked_by_admin,
        lines=[line_to_out(l) for l in lines],
    )


def log_action(db: Session, proposal: models.Proposal, user: models.User, action: str, detail: Optional[str] = None):
    db.add(models.AuditLog(
        proposal_id=proposal.id,
        user_id=user.id,
        username=user.username,
        action=action,
        detail=detail,
    ))


def get_or_create_proposal(db: Session, office_id: int, year: int, budget_type: str,
                            supplemental_number: Optional[int] = None) -> models.Proposal:
    if budget_type == "supplemental" and not supplemental_number:
        supplemental_number = 1  # default to No. 1 if not specified

    proposal = (
        db.query(models.Proposal)
        .filter(
            models.Proposal.office_id == office_id,
            models.Proposal.year == year,
            models.Proposal.budget_type == budget_type,
            models.Proposal.supplemental_number == (supplemental_number if budget_type == "supplemental" else None),
        )
        .first()
    )
    if proposal:
        return proposal

    proposal = models.Proposal(
        office_id=office_id, year=year, budget_type=budget_type,
        supplemental_number=supplemental_number if budget_type == "supplemental" else None,
    )
    db.add(proposal)
    db.flush()  # get proposal.id

    accounts = db.query(models.Account).all()
    for acc in accounts:
        db.add(models.ProposalLine(proposal_id=proposal.id, account_id=acc.id))
    db.commit()
    db.refresh(proposal)
    return proposal


def enforce_office_access(user: models.User, office_id: int):
    if user.role == models.Role.client and user.office_id != office_id:
        raise HTTPException(status_code=403, detail="You can only access your own office's data.")


# -------------------------------------------------------------------- auth --

@app.post("/api/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token({"sub": str(user.id)})
    office_name = user.office.name if user.office else None
    return schemas.LoginResponse(
        access_token=token,
        role=user.role.value if hasattr(user.role, "value") else user.role,
        office_id=user.office_id,
        office_name=office_name,
        username=user.username,
    )


@app.get("/api/me")
def me(user: models.User = Depends(get_current_user)):
    return {
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "office_id": user.office_id,
        "office_name": user.office.name if user.office else None,
    }


# ----------------------------------------------------------------- offices --

@app.get("/api/offices", response_model=List[schemas.OfficeOut])
def list_offices(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Office).order_by(models.Office.name).all()


@app.post("/api/offices", response_model=schemas.OfficeOut)
def create_office(payload: schemas.OfficeCreate, db: Session = Depends(get_db),
                   admin: models.User = Depends(require_admin)):
    office = models.Office(**payload.model_dump())
    db.add(office)
    db.commit()
    db.refresh(office)
    return office


# ---------------------------------------------------------------- branding --
# Logos are visual-only, not sensitive, so the GET (serving) endpoints are
# deliberately public/unauthenticated -- this lets a plain <img src="..."> tag
# display them directly (including on the login screen, before anyone is
# signed in), without needing to fetch+blob just to attach an auth header.
# Uploading/removing a logo remains admin-only.

MAX_LOGO_BYTES = 3 * 1024 * 1024  # 3 MB -- logos should always be small
ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/svg+xml"}


async def _read_and_validate_logo(file: UploadFile) -> tuple:
    if file.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(status_code=400, detail="Logo must be a PNG, JPG, WEBP, or SVG image.")
    contents = await file.read()
    if len(contents) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=400, detail=f"Logo must be smaller than {MAX_LOGO_BYTES // (1024*1024)} MB.")
    return contents, file.content_type


def _get_or_create_setting(db: Session, key: str) -> models.AppSetting:
    setting = db.query(models.AppSetting).filter(models.AppSetting.key == key).first()
    if not setting:
        setting = models.AppSetting(key=key)
        db.add(setting)
        db.flush()
    return setting


def _serve_image_or_404(data: Optional[bytes], content_type: Optional[str]):
    if not data:
        raise HTTPException(status_code=404, detail="No logo set.")
    return Response(content=data, media_type=content_type or "image/png")


@app.get("/api/branding/login-logo")
def get_login_logo(db: Session = Depends(get_db)):
    setting = db.query(models.AppSetting).filter(models.AppSetting.key == "login_logo").first()
    return _serve_image_or_404(setting.value_data if setting else None, setting.value_content_type if setting else None)


@app.get("/api/branding/default-logo")
def get_default_logo(db: Session = Depends(get_db)):
    setting = db.query(models.AppSetting).filter(models.AppSetting.key == "default_logo").first()
    return _serve_image_or_404(setting.value_data if setting else None, setting.value_content_type if setting else None)


@app.post("/api/admin/branding/login-logo")
async def upload_login_logo(file: UploadFile = File(...), db: Session = Depends(get_db),
                             admin: models.User = Depends(require_admin)):
    contents, content_type = await _read_and_validate_logo(file)
    setting = _get_or_create_setting(db, "login_logo")
    setting.value_data = contents
    setting.value_content_type = content_type
    db.commit()
    return {"ok": True}


@app.delete("/api/admin/branding/login-logo")
def delete_login_logo(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    setting = db.query(models.AppSetting).filter(models.AppSetting.key == "login_logo").first()
    if setting:
        db.delete(setting)
        db.commit()
    return {"ok": True}


@app.post("/api/admin/branding/default-logo")
async def upload_default_logo(file: UploadFile = File(...), db: Session = Depends(get_db),
                               admin: models.User = Depends(require_admin)):
    contents, content_type = await _read_and_validate_logo(file)
    setting = _get_or_create_setting(db, "default_logo")
    setting.value_data = contents
    setting.value_content_type = content_type
    db.commit()
    return {"ok": True}


@app.delete("/api/admin/branding/default-logo")
def delete_default_logo(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    setting = db.query(models.AppSetting).filter(models.AppSetting.key == "default_logo").first()
    if setting:
        db.delete(setting)
        db.commit()
    return {"ok": True}


@app.get("/api/branding/province-name")
def get_province_name(db: Session = Depends(get_db)):
    setting = db.query(models.AppSetting).filter(models.AppSetting.key == "province_name").first()
    name = setting.value_data.decode("utf-8") if setting and setting.value_data else ""
    return {"name": name}


@app.post("/api/admin/branding/province-name")
def set_province_name(payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    name = (payload.get("name") or "").strip()
    setting = _get_or_create_setting(db, "province_name")
    setting.value_data = name.encode("utf-8")
    setting.value_content_type = "text/plain"
    db.commit()
    return {"name": name}


@app.get("/api/offices/{office_id}/logo")
def get_office_logo(office_id: int, db: Session = Depends(get_db)):
    office = db.query(models.Office).get(office_id)
    if office and office.logo_data:
        return Response(content=office.logo_data, media_type=office.logo_content_type or "image/png")
    # Fall back to the default/province logo when this office has none of its own.
    default = db.query(models.AppSetting).filter(models.AppSetting.key == "default_logo").first()
    return _serve_image_or_404(default.value_data if default else None, default.value_content_type if default else None)


@app.post("/api/offices/{office_id}/logo", response_model=schemas.OfficeOut)
async def upload_office_logo(office_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                              admin: models.User = Depends(require_admin)):
    office = db.query(models.Office).get(office_id)
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")
    contents, content_type = await _read_and_validate_logo(file)
    office.logo_data = contents
    office.logo_content_type = content_type
    db.commit()
    db.refresh(office)
    return office


@app.delete("/api/offices/{office_id}/logo", response_model=schemas.OfficeOut)
def delete_office_logo(office_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    office = db.query(models.Office).get(office_id)
    if not office:
        raise HTTPException(status_code=404, detail="Office not found")
    office.logo_data = None
    office.logo_content_type = None
    db.commit()
    db.refresh(office)
    return office


# ------------------------------------------------------------------- users --

@app.get("/api/users", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    users = db.query(models.User).order_by(models.User.username).all()
    return [
        schemas.UserOut(
            id=u.id, username=u.username,
            role=u.role.value if hasattr(u.role, "value") else u.role,
            office_id=u.office_id,
            office_name=u.office.name if u.office else None,
        ) for u in users
    ]


@app.post("/api/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if payload.role not in ("admin", "client"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'client'")
    if payload.role == "client" and not payload.office_id:
        raise HTTPException(status_code=400, detail="Client users must be assigned an office")

    u = models.User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        office_id=payload.office_id if payload.role == "client" else None,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return schemas.UserOut(
        id=u.id, username=u.username, role=payload.role,
        office_id=u.office_id, office_name=u.office.name if u.office else None,
    )


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    u = db.query(models.User).get(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.username == "Dher":
        raise HTTPException(status_code=400, detail="Cannot delete the primary admin account")
    db.delete(u)
    db.commit()
    return {"ok": True}


@app.put("/api/users/{user_id}/password")
def reset_user_password(user_id: int, payload: schemas.PasswordResetRequest, db: Session = Depends(get_db),
                         admin: models.User = Depends(require_admin)):
    """Sets a new password for a user. Note: there is no way to retrieve a
    user's EXISTING password -- passwords are stored as one-way hashes (the
    standard, secure way), which can never be reversed back into the
    original text, by design. Setting a new one is the secure equivalent of
    'knowing' a user's password: whatever admin sets it to here IS the
    password from that point on."""
    u = db.query(models.User).get(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if len(payload.new_password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")
    u.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- accounts --

@app.get("/api/accounts", response_model=List[schemas.AccountOut])
def list_accounts(classification: Optional[str] = None, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    q = db.query(models.Account)
    if classification:
        q = q.filter(models.Account.classification == classification)
    accounts = q.all()
    accounts = sorted(accounts, key=lambda a: (a.classification.value, a.code, a.name))
    return accounts


def find_duplicate_account_name(db: Session, name: str, exclude_id: Optional[int] = None) -> Optional[models.Account]:
    q = db.query(models.Account).filter(models.Account.name.ilike(name.strip()))
    if exclude_id:
        q = q.filter(models.Account.id != exclude_id)
    return q.first()


@app.post("/api/accounts", response_model=schemas.AccountOut)
def create_account(payload: schemas.AccountCreate, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    if payload.classification not in ("PS", "MOOE", "CO", "FE"):
        raise HTTPException(status_code=400, detail="classification must be one of PS, MOOE, CO, FE")
    name = payload.name.strip()
    dupe = find_duplicate_account_name(db, name)
    if dupe:
        raise HTTPException(
            status_code=400,
            detail=f"An account named \"{name}\" already exists (under {dupe.classification.value}, code {dupe.code}). "
                   f"Account names must be unique across every classification."
        )
    acc = models.Account(classification=payload.classification, code=payload.code.strip(), name=name)
    db.add(acc)
    db.commit()
    db.refresh(acc)

    # Add this account as a zero-value line to every existing proposal so
    # it shows up consistently across all offices/years going forward.
    proposals = db.query(models.Proposal).all()
    for p in proposals:
        exists = db.query(models.ProposalLine).filter(
            models.ProposalLine.proposal_id == p.id, models.ProposalLine.account_id == acc.id
        ).first()
        if not exists:
            db.add(models.ProposalLine(proposal_id=p.id, account_id=acc.id))
    db.commit()
    return acc


@app.put("/api/accounts/{account_id}", response_model=schemas.AccountOut)
def update_account(account_id: int, payload: schemas.AccountUpdate, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    acc = db.query(models.Account).get(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")

    if payload.classification is not None:
        if payload.classification not in ("PS", "MOOE", "CO", "FE"):
            raise HTTPException(status_code=400, detail="classification must be one of PS, MOOE, CO, FE")
        acc.classification = payload.classification
    if payload.code is not None:
        acc.code = payload.code.strip()
    if payload.name is not None:
        name = payload.name.strip()
        dupe = find_duplicate_account_name(db, name, exclude_id=acc.id)
        if dupe:
            raise HTTPException(
                status_code=400,
                detail=f"An account named \"{name}\" already exists (under {dupe.classification.value}, code {dupe.code}). "
                       f"Account names must be unique across every classification."
            )
        acc.name = name

    db.commit()
    db.refresh(acc)
    return acc


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    acc = db.query(models.Account).get(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")

    lines = db.query(models.ProposalLine).filter(models.ProposalLine.account_id == account_id).all()
    has_real_data = any(
        (l.prev_year_actual or 0) != 0 or (l.current_annual or 0) != 0 or
        any((s.amount or 0) != 0 for s in l.current_supplementals) or
        (l.proposed_amount or 0) != 0 or (l.adjusted_proposal or None) not in (None, 0) or
        l.approved_amount not in (None, 0)
        for l in lines
    )
    if has_real_data:
        raise HTTPException(
            status_code=400,
            detail="This account has proposal data entered against it in one or more proposals, "
                   "so it can't be deleted. Edit it instead, or clear that data first."
        )

    for l in lines:
        db.delete(l)
    db.delete(acc)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------- proposals --

@app.get("/api/proposal", response_model=schemas.ProposalOut)
def get_proposal(office_id: int, year: int, budget_type: str, supplemental_number: Optional[int] = None,
                  db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    enforce_office_access(user, office_id)
    if budget_type not in ("annual", "supplemental"):
        raise HTTPException(status_code=400, detail="budget_type must be 'annual' or 'supplemental'")
    proposal = get_or_create_proposal(db, office_id, year, budget_type, supplemental_number)
    return proposal_to_out(proposal)


@app.get("/api/proposal/{proposal_id}/audit-log", response_model=List[schemas.AuditLogOut])
def get_audit_log(proposal_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    proposal = db.query(models.Proposal).get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    enforce_office_access(user, proposal.office_id)
    entries = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.proposal_id == proposal_id)
        .order_by(models.AuditLog.timestamp.desc())
        .all()
    )
    return [
        schemas.AuditLogOut(
            id=e.id, username=e.username, action=e.action, detail=e.detail,
            timestamp=e.timestamp.isoformat() + "Z",
        ) for e in entries
    ]


@app.put("/api/proposal/{proposal_id}/lines", response_model=schemas.ProposalOut)
def save_lines(proposal_id: int, payload: schemas.SaveLinesRequest,
               db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    proposal = db.query(models.Proposal).get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    enforce_office_access(user, proposal.office_id)
    if user.role == models.Role.client and proposal.status == models.ProposalStatus.submitted:
        raise HTTPException(status_code=400, detail="This proposal has already been submitted. Contact the admin to reopen it.")

    lines_by_account = {l.account_id: l for l in proposal.lines}
    changed_accounts = []
    for item in payload.lines:
        line = lines_by_account.get(item.account_id)
        if not line:
            continue
        touched = False
        # Note: prev_year_actual is intentionally NOT settable here -- it's
        # admin-only, via PUT /api/proposal/{id}/admin-lines.
        if item.current_annual is not None and item.current_annual != line.current_annual:
            line.current_annual = item.current_annual
            touched = True
        if item.proposed_amount is not None and item.proposed_amount != line.proposed_amount:
            line.proposed_amount = item.proposed_amount
            touched = True
        if item.remarks is not None and item.remarks != line.remarks:
            line.remarks = item.remarks
            touched = True
        if item.current_supplementals:
            existing_supps = {s.supplemental_number: s for s in line.current_supplementals}
            for supp_num_str, amount in item.current_supplementals.items():
                supp_num = int(supp_num_str)
                existing = existing_supps.get(supp_num)
                if existing:
                    if existing.amount != amount:
                        existing.amount = amount
                        touched = True
                else:
                    db.add(models.ProposalLineCurrentSupplemental(
                        proposal_line_id=line.id, supplemental_number=supp_num, amount=amount
                    ))
                    touched = True
        if touched:
            changed_accounts.append(line.account.code)

    if changed_accounts:
        detail = f"Updated {len(changed_accounts)} account(s): " + ", ".join(changed_accounts[:10])
        if len(changed_accounts) > 10:
            detail += f" and {len(changed_accounts) - 10} more"
        log_action(db, proposal, user, "submitted" if payload.submit else "draft_saved", detail)
    elif payload.submit:
        log_action(db, proposal, user, "submitted", "Submitted with no further changes")

    if payload.submit:
        proposal.status = models.ProposalStatus.submitted
        proposal.submitted_at = datetime.utcnow()

    proposal.last_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(proposal)
    return proposal_to_out(proposal)


@app.post("/api/proposal/{proposal_id}/add-current-supplemental", response_model=schemas.ProposalOut)
def add_current_supplemental(proposal_id: int, db: Session = Depends(get_db),
                              user: models.User = Depends(get_current_user)):
    """Adds one more 'Current Year Supplemental' reference column (e.g. the
    2026 Supplemental No.2 column on a 2027 proposal), initialized to 0
    across every line of this proposal."""
    proposal = db.query(models.Proposal).get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    enforce_office_access(user, proposal.office_id)
    if user.role == models.Role.client and proposal.status == models.ProposalStatus.submitted:
        raise HTTPException(status_code=400, detail="This proposal has already been submitted. Reopen it first.")

    for line in proposal.lines:
        existing_nums = {s.supplemental_number for s in line.current_supplementals}
        next_num = (max(existing_nums) + 1) if existing_nums else 1
        db.add(models.ProposalLineCurrentSupplemental(
            proposal_line_id=line.id, supplemental_number=next_num, amount=0
        ))
    db.commit()
    db.refresh(proposal)
    return proposal_to_out(proposal)


@app.put("/api/proposal/{proposal_id}/admin-lines", response_model=schemas.ProposalOut)
def update_admin_lines(proposal_id: int, payload: schemas.AdminLinesUpdateRequest,
                        db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """Admin-only fields: Previous Year Actual, Adjusted Proposal, and its
    remarks. Always editable by admin -- independent of the office's
    submit/reopen status and independent of the Approved-amount lock."""
    proposal = db.query(models.Proposal).get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    lines_by_account = {l.account_id: l for l in proposal.lines}
    changed_accounts = []
    for item in payload.lines:
        line = lines_by_account.get(item.account_id)
        if not line:
            continue
        touched = False
        if item.prev_year_actual is not None and item.prev_year_actual != line.prev_year_actual:
            line.prev_year_actual = item.prev_year_actual
            touched = True
        if item.adjusted_proposal is not None and item.adjusted_proposal != line.adjusted_proposal:
            line.adjusted_proposal = item.adjusted_proposal
            touched = True
        if item.remarks_adjusted is not None and item.remarks_adjusted != line.remarks_adjusted:
            line.remarks_adjusted = item.remarks_adjusted
            touched = True
        if touched:
            changed_accounts.append(line.account.code)

    if changed_accounts:
        detail = f"Updated admin fields (Previous Year Actual / Adjusted Proposal) for {len(changed_accounts)} account(s): " + ", ".join(changed_accounts[:10])
        if len(changed_accounts) > 10:
            detail += f" and {len(changed_accounts) - 10} more"
        log_action(db, proposal, admin, "admin_fields_updated", detail)

    proposal.last_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(proposal)
    return proposal_to_out(proposal)


@app.put("/api/proposal/{proposal_id}/reopen", response_model=schemas.ProposalOut)
def reopen_proposal(proposal_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    proposal = db.query(models.Proposal).get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    # Admins can reopen any office's proposal; a client can only reopen
    # their own office's proposal. Reopening does NOT create a new/duplicate
    # proposal -- it's the same underlying record (unique per office+year+
    # budget_type+supplemental_number), just switched back to editable.
    enforce_office_access(user, proposal.office_id)
    if user.role == models.Role.client and proposal.locked_by_admin:
        raise HTTPException(
            status_code=403,
            detail="This proposal was locked by the admin (e.g. for a hearing) and can only be reopened by them."
        )
    proposal.status = models.ProposalStatus.draft
    proposal.locked_by_admin = False
    who = "the admin" if user.role == models.Role.admin else "the office"
    log_action(db, proposal, user, "reopened", f"Reopened for editing by {who}")
    db.commit()
    db.refresh(proposal)
    return proposal_to_out(proposal)


@app.put("/api/proposal/{proposal_id}/lock", response_model=schemas.ProposalOut)
def lock_proposal_for_admin(proposal_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """Locks a proposal so the OFFICE can no longer edit it -- intended for
    when admin is about to work on it directly (e.g. during a budget
    hearing, including offline), and needs to be the only one making
    changes to avoid the office's edits colliding with admin's. Technically
    the same lock as a normal submission, just admin-triggered and logged
    distinctly so it's clear why it happened."""
    proposal = db.query(models.Proposal).get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    proposal.status = models.ProposalStatus.submitted
    proposal.locked_by_admin = True
    log_action(db, proposal, admin, "locked_by_admin",
               "Locked by admin — the office cannot edit until this is reopened.")
    db.commit()
    db.refresh(proposal)
    return proposal_to_out(proposal)


@app.put("/api/proposals/bulk-lock")
def bulk_lock_proposals(year: int, budget_type: str, supplemental_number: Optional[int] = None,
                         db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """Locks every office's EXISTING proposal for this budget cycle at once
    -- e.g. before a hearing day, instead of locking each office one at a
    time. Only affects proposals that already exist (an office that hasn't
    started one yet has nothing to lock)."""
    if budget_type not in ("annual", "supplemental"):
        raise HTTPException(status_code=400, detail="budget_type must be 'annual' or 'supplemental'")
    proposals = _matching_proposals(db, year, budget_type, supplemental_number)
    locked = 0
    for p in proposals:
        if p.status != models.ProposalStatus.submitted or not p.locked_by_admin:
            p.status = models.ProposalStatus.submitted
            p.locked_by_admin = True
            log_action(db, p, admin, "locked_by_admin",
                       "Locked by admin (bulk action) — the office cannot edit until this is reopened.")
            locked += 1
    db.commit()
    return {"locked_count": locked, "already_locked_count": len(proposals) - locked, "total_proposals": len(proposals)}


@app.put("/api/proposals/bulk-unlock")
def bulk_unlock_proposals(year: int, budget_type: str, supplemental_number: Optional[int] = None,
                           db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """Reopens every office's proposal for this budget cycle at once --
    e.g. after a hearing day ends, handing editing control back to every
    office in one action instead of one at a time."""
    if budget_type not in ("annual", "supplemental"):
        raise HTTPException(status_code=400, detail="budget_type must be 'annual' or 'supplemental'")
    proposals = _matching_proposals(db, year, budget_type, supplemental_number)
    unlocked = 0
    for p in proposals:
        if p.status != models.ProposalStatus.draft:
            p.status = models.ProposalStatus.draft
            p.locked_by_admin = False
            log_action(db, p, admin, "reopened", "Reopened for editing by the admin (bulk action)")
            unlocked += 1
    db.commit()
    return {"unlocked_count": unlocked, "already_unlocked_count": len(proposals) - unlocked, "total_proposals": len(proposals)}


@app.put("/api/proposal/{proposal_id}/approve", response_model=schemas.ProposalOut)
def approve_lines(proposal_id: int, payload: schemas.ApproveLinesRequest,
                   db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    proposal = db.query(models.Proposal).get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.approval_status == models.ApprovalStatus.approved:
        raise HTTPException(
            status_code=400,
            detail="Approved amounts are locked. Click 'Reopen approved amounts' first if you need to change them."
        )

    lines_by_account = {l.account_id: l for l in proposal.lines}
    changed_accounts = []
    for item in payload.lines:
        line = lines_by_account.get(item.account_id)
        if line and item.approved_amount != line.approved_amount:
            line.approved_amount = item.approved_amount
            changed_accounts.append(line.account.code)

    proposal.approval_status = models.ApprovalStatus.approved
    detail = f"Approved amounts saved and locked for {len(changed_accounts)} account(s): " + ", ".join(changed_accounts[:10])
    if len(changed_accounts) > 10:
        detail += f" and {len(changed_accounts) - 10} more"
    log_action(db, proposal, admin, "approved", detail)

    proposal.last_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(proposal)
    return proposal_to_out(proposal)


@app.put("/api/proposal/{proposal_id}/reopen-approval", response_model=schemas.ProposalOut)
def reopen_approval(proposal_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """Unlocks the Approved-amount fields for editing again. This is
    completely separate from the office's draft/submitted status -- it never
    touches `proposal.status`, so the proposal does NOT appear as a draft to
    the client."""
    proposal = db.query(models.Proposal).get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    proposal.approval_status = models.ApprovalStatus.pending
    log_action(db, proposal, admin, "approval_reopened", "Reopened approved amounts for editing")
    db.commit()
    db.refresh(proposal)
    return proposal_to_out(proposal)


@app.get("/api/proposals", response_model=List[schemas.ProposalOut])
def list_proposals(office_id: Optional[int] = None, year: Optional[int] = None,
                    budget_type: Optional[str] = None, status: Optional[str] = None,
                    db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    q = db.query(models.Proposal)
    if office_id:
        q = q.filter(models.Proposal.office_id == office_id)
    if year:
        q = q.filter(models.Proposal.year == year)
    if budget_type:
        q = q.filter(models.Proposal.budget_type == budget_type)
    if status:
        q = q.filter(models.Proposal.status == status)
    return [proposal_to_out(p) for p in q.all()]


# ------------------------------------------------------------ fund sources --
# Based on the province's actual income/receipts statement. These are the
# standard line items -- admins can seed a budget cycle with all of them at
# once (amount = 0) and then just fill in the numbers, instead of retyping
# category + particulars every time. New/one-off sources can still be added
# individually at any time.
STANDARD_FUND_SOURCES = [
    ("Beginning Cash Balance", "Share from the Utilization of National Wealth (80%) - (Prior Years)"),

    ("Local Sources - Tax Revenue", "Basic RPT (Current)"),
    ("Local Sources - Tax Revenue", "Special Education Fund (SEF)"),
    ("Local Sources - Tax Revenue", "Business Tax"),
    ("Local Sources - Tax Revenue", "Other Local Tax"),

    ("Local Sources - Non-Tax Revenue", "Regulatory Fees"),
    ("Local Sources - Non-Tax Revenue", "Service/User Charges"),
    ("Local Sources - Non-Tax Revenue", "Receipts from Economic Enterprise"),
    ("Local Sources - Non-Tax Revenue", "Other Receipts"),

    ("External Sources - IRA / National Tax Allocation", "IRA / National Tax Allocation (NTA)"),

    ("External Sources - Share from National Wealth", "Share from National Wealth"),

    ("External Sources - Other Shares", "Share from GOCC's (PAGCOR & PCSO)"),
    ("External Sources - Other Shares", "Share from Ecozone"),
    ("External Sources - Other Shares", "Share from EVAT"),
    ("External Sources - Other Shares", "Share from Tobacco Excise Tax"),
    ("External Sources - Other Shares", "Inter-Local Transfer"),
    ("External Sources - Other Shares", "Extraordinary Receipts/Grants/Donations/Aids"),

    ("Non-Income Receipts", "Proceeds from Sale of Assets"),
    ("Non-Income Receipts", "Proceeds from Sale of Debt Securities of other Entities"),
    ("Non-Income Receipts", "Collections from Loan Receivable"),
    ("Non-Income Receipts", "Acquisition of Loans"),
    ("Non-Income Receipts", "Issuance of Bonds"),
]
SUGGESTED_FUND_CATEGORIES = sorted({cat for cat, _ in STANDARD_FUND_SOURCES})


@app.get("/api/fund-source-categories")
def fund_source_categories(admin: models.User = Depends(require_admin)):
    return SUGGESTED_FUND_CATEGORIES


@app.post("/api/fund-sources/seed-standard", response_model=List[schemas.FundSourceOut])
def seed_standard_fund_sources(payload: schemas.FundSourceSeedRequest, db: Session = Depends(get_db),
                                admin: models.User = Depends(require_admin)):
    """Adds the province's standard fund source line items (at amount = 0)
    into the given budget cycle, skipping any that already exist there by
    name, so admins can just fill in amounts instead of retyping everything
    each cycle."""
    if payload.budget_type not in ("annual", "supplemental"):
        raise HTTPException(status_code=400, detail="budget_type must be 'annual' or 'supplemental'")
    supp = (payload.supplemental_number or 1) if payload.budget_type == "supplemental" else None

    existing = db.query(models.FundSource).filter(
        models.FundSource.year == payload.year,
        models.FundSource.budget_type == payload.budget_type,
        models.FundSource.supplemental_number == supp,
    ).all()
    existing_names = {fs.particulars.strip().lower() for fs in existing}

    created = []
    for category, particulars in STANDARD_FUND_SOURCES:
        if particulars.strip().lower() in existing_names:
            continue
        fs = models.FundSource(
            year=payload.year, budget_type=payload.budget_type, supplemental_number=supp,
            category=category, particulars=particulars, amount=0,
        )
        db.add(fs)
        created.append(fs)
    db.commit()
    for fs in created:
        db.refresh(fs)
    return db.query(models.FundSource).filter(
        models.FundSource.year == payload.year,
        models.FundSource.budget_type == payload.budget_type,
        models.FundSource.supplemental_number == supp,
    ).order_by(models.FundSource.category, models.FundSource.particulars).all()


@app.get("/api/fund-sources", response_model=List[schemas.FundSourceOut])
def list_fund_sources(year: int, budget_type: str, supplemental_number: Optional[int] = None,
                       db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    q = db.query(models.FundSource).filter(
        models.FundSource.year == year,
        models.FundSource.budget_type == budget_type,
    )
    if budget_type == "supplemental":
        q = q.filter(models.FundSource.supplemental_number == (supplemental_number or 1))
    else:
        q = q.filter(models.FundSource.supplemental_number.is_(None))
    return q.order_by(models.FundSource.category, models.FundSource.particulars).all()


@app.post("/api/fund-sources", response_model=schemas.FundSourceOut)
def create_fund_source(payload: schemas.FundSourceCreate, db: Session = Depends(get_db),
                        admin: models.User = Depends(require_admin)):
    if payload.budget_type not in ("annual", "supplemental"):
        raise HTTPException(status_code=400, detail="budget_type must be 'annual' or 'supplemental'")
    fs = models.FundSource(
        year=payload.year,
        budget_type=payload.budget_type,
        supplemental_number=(payload.supplemental_number or 1) if payload.budget_type == "supplemental" else None,
        category=payload.category.strip(),
        particulars=payload.particulars.strip(),
        amount=payload.amount,
    )
    db.add(fs)
    db.commit()
    db.refresh(fs)
    return fs


@app.put("/api/fund-sources/bulk-update", response_model=List[schemas.FundSourceOut])
def bulk_update_fund_sources(payload: schemas.FundSourceBulkUpdateRequest, db: Session = Depends(get_db),
                              admin: models.User = Depends(require_admin)):
    """Saves every edited fund source amount in one request/transaction, so
    editing several rows and saving once doesn't risk any row's unsaved
    edit being wiped by a reload triggered by saving a different row."""
    updated = []
    for item in payload.items:
        fs = db.query(models.FundSource).get(item.id)
        if fs:
            fs.amount = item.amount
            updated.append(fs)
    db.commit()
    for fs in updated:
        db.refresh(fs)
    return updated


@app.put("/api/fund-sources/{source_id}", response_model=schemas.FundSourceOut)
def update_fund_source(source_id: int, payload: schemas.FundSourceUpdate, db: Session = Depends(get_db),
                        admin: models.User = Depends(require_admin)):
    fs = db.query(models.FundSource).get(source_id)
    if not fs:
        raise HTTPException(status_code=404, detail="Fund source not found")
    if payload.category is not None:
        fs.category = payload.category.strip()
    if payload.particulars is not None:
        fs.particulars = payload.particulars.strip()
    if payload.amount is not None:
        fs.amount = payload.amount
    db.commit()
    db.refresh(fs)
    return fs


@app.delete("/api/fund-sources/{source_id}")
def delete_fund_source(source_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    fs = db.query(models.FundSource).get(source_id)
    if not fs:
        raise HTTPException(status_code=404, detail="Fund source not found")
    db.delete(fs)
    db.commit()
    return {"ok": True}


# --------------------------------------------------- special purpose appropriations --
# Mandatory deductions taken from available funds BEFORE offices can be
# allocated anything. Two are computed automatically from fund sources
# (20% Development Fund, 5% LDRRMF); others (Aid to Barangays, and any
# custom ones admin adds) are plain editable amounts.

BEGINNING_CASH_CAT = "Beginning Cash Balance"


def _fund_source_totals_by_category(db: Session, year: int, budget_type: str, supplemental_number: Optional[int]):
    q = db.query(models.FundSource).filter(
        models.FundSource.year == year, models.FundSource.budget_type == budget_type,
    )
    if budget_type == "supplemental":
        q = q.filter(models.FundSource.supplemental_number == (supplemental_number or 1))
    else:
        q = q.filter(models.FundSource.supplemental_number.is_(None))
    totals = {}
    for fs in q.all():
        totals[fs.category] = totals.get(fs.category, 0.0) + fs.amount
    return totals


def _compute_dev_fund_20pct(by_category: dict) -> float:
    nta = by_category.get("External Sources - IRA / National Tax Allocation", 0.0)
    return round(nta * 0.20, 2)


def _compute_ldrrmf_5pct(by_category: dict) -> float:
    # 5% of TOTAL RECEIPTS excluding only the Beginning Cash Balance
    # category. This deliberately includes "External Sources - Share from
    # National Wealth" (a normal receipt) -- it's a different amount from
    # the similarly-named "Share from the Utilization of National Wealth
    # (80%)" line that lives under Beginning Cash Balance, which is a
    # restricted account used only for electricity and is excluded here
    # because it's a beginning-balance item, not because of its name.
    base = sum(amount for category, amount in by_category.items() if category != BEGINNING_CASH_CAT)
    return round(base * 0.05, 2)


def _ensure_default_spa_rows(db: Session, year: int, budget_type: str, supplemental_number: Optional[int]):
    supp = (supplemental_number or 1) if budget_type == "supplemental" else None
    existing = db.query(models.SpecialPurposeAppropriation).filter(
        models.SpecialPurposeAppropriation.year == year,
        models.SpecialPurposeAppropriation.budget_type == budget_type,
        models.SpecialPurposeAppropriation.supplemental_number == supp,
    ).all()
    if existing:
        return existing

    defaults = [
        ("Appropriation for Development Programs/Projects (20% Development Fund)", "dev_fund_20pct", 0),
        ("Appropriation for Local Disaster Risk Reduction and Management Programs/Projects (5% LDRRMF)", "ldrrmf_5pct", 1),
        ("Aid to Barangays", None, 2),
    ]
    rows = []
    for name, computed_key, order in defaults:
        row = models.SpecialPurposeAppropriation(
            year=year, budget_type=budget_type, supplemental_number=supp,
            name=name, amount=590000 if name == "Aid to Barangays" else 0,
            auto_computed=computed_key, sort_order=order,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for r in rows:
        db.refresh(r)
    return rows


def _spa_rows_with_live_amounts(db: Session, year: int, budget_type: str, supplemental_number: Optional[int]):
    rows = _ensure_default_spa_rows(db, year, budget_type, supplemental_number)
    by_category = _fund_source_totals_by_category(db, year, budget_type, supplemental_number)
    out = []
    for r in sorted(rows, key=lambda r: r.sort_order):
        amount = r.amount
        if r.auto_computed == "dev_fund_20pct":
            amount = _compute_dev_fund_20pct(by_category)
        elif r.auto_computed == "ldrrmf_5pct":
            amount = _compute_ldrrmf_5pct(by_category)
        out.append(schemas.SpaOut(
            id=r.id, year=r.year, budget_type=r.budget_type, supplemental_number=r.supplemental_number,
            name=r.name, amount=amount, auto_computed=r.auto_computed,
        ))
    return out


def _total_spa(db: Session, year: int, budget_type: str, supplemental_number: Optional[int]) -> float:
    return sum(r.amount for r in _spa_rows_with_live_amounts(db, year, budget_type, supplemental_number))


@app.get("/api/spa", response_model=List[schemas.SpaOut])
def list_spa(year: int, budget_type: str, supplemental_number: Optional[int] = None,
             db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    if budget_type not in ("annual", "supplemental"):
        raise HTTPException(status_code=400, detail="budget_type must be 'annual' or 'supplemental'")
    return _spa_rows_with_live_amounts(db, year, budget_type, supplemental_number)


@app.post("/api/spa", response_model=schemas.SpaOut)
def create_spa(payload: schemas.SpaCreate, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    if payload.budget_type not in ("annual", "supplemental"):
        raise HTTPException(status_code=400, detail="budget_type must be 'annual' or 'supplemental'")
    _ensure_default_spa_rows(db, payload.year, payload.budget_type, payload.supplemental_number)
    supp = (payload.supplemental_number or 1) if payload.budget_type == "supplemental" else None
    max_order = db.query(models.SpecialPurposeAppropriation).filter(
        models.SpecialPurposeAppropriation.year == payload.year,
        models.SpecialPurposeAppropriation.budget_type == payload.budget_type,
        models.SpecialPurposeAppropriation.supplemental_number == supp,
    ).count()
    row = models.SpecialPurposeAppropriation(
        year=payload.year, budget_type=payload.budget_type, supplemental_number=supp,
        name=payload.name.strip(), amount=payload.amount, auto_computed=None, sort_order=max_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return schemas.SpaOut(id=row.id, year=row.year, budget_type=row.budget_type,
                           supplemental_number=row.supplemental_number, name=row.name,
                           amount=row.amount, auto_computed=row.auto_computed)


@app.put("/api/spa/{spa_id}", response_model=schemas.SpaOut)
def update_spa(spa_id: int, payload: schemas.SpaUpdate, db: Session = Depends(get_db),
               admin: models.User = Depends(require_admin)):
    row = db.query(models.SpecialPurposeAppropriation).get(spa_id)
    if not row:
        raise HTTPException(status_code=404, detail="Special Purpose Appropriation not found")
    if row.auto_computed and payload.amount is not None:
        raise HTTPException(
            status_code=400,
            detail="This amount is computed automatically from fund sources and can't be edited directly."
        )
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.amount is not None:
        row.amount = payload.amount
    db.commit()
    db.refresh(row)
    amount = row.amount
    if row.auto_computed:
        by_category = _fund_source_totals_by_category(db, row.year, row.budget_type, row.supplemental_number)
        amount = _compute_dev_fund_20pct(by_category) if row.auto_computed == "dev_fund_20pct" else _compute_ldrrmf_5pct(by_category)
    return schemas.SpaOut(id=row.id, year=row.year, budget_type=row.budget_type,
                           supplemental_number=row.supplemental_number, name=row.name,
                           amount=amount, auto_computed=row.auto_computed)


@app.delete("/api/spa/{spa_id}")
def delete_spa(spa_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    row = db.query(models.SpecialPurposeAppropriation).get(spa_id)
    if not row:
        raise HTTPException(status_code=404, detail="Special Purpose Appropriation not found")
    if row.auto_computed:
        raise HTTPException(status_code=400, detail="This mandatory deduction can't be removed, only added to below it.")
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.get("/api/budget-summary", response_model=schemas.BudgetSummaryOut)
def budget_summary(year: int, budget_type: str, supplemental_number: Optional[int] = None,
                    db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    if budget_type not in ("annual", "supplemental"):
        raise HTTPException(status_code=400, detail="budget_type must be 'annual' or 'supplemental'")

    fs_q = db.query(models.FundSource).filter(
        models.FundSource.year == year, models.FundSource.budget_type == budget_type,
    )
    if budget_type == "supplemental":
        fs_q = fs_q.filter(models.FundSource.supplemental_number == (supplemental_number or 1))
    else:
        fs_q = fs_q.filter(models.FundSource.supplemental_number.is_(None))
    available_budget = sum(fs.amount for fs in fs_q.all())

    prop_q = db.query(models.Proposal).filter(
        models.Proposal.year == year, models.Proposal.budget_type == budget_type,
    )
    if budget_type == "supplemental":
        prop_q = prop_q.filter(models.Proposal.supplemental_number == (supplemental_number or 1))
    else:
        prop_q = prop_q.filter(models.Proposal.supplemental_number.is_(None))

    total_proposed = 0.0
    total_adjusted = 0.0
    total_approved = 0.0
    for p in prop_q.all():
        for l in p.lines:
            proposed = l.proposed_amount or 0
            total_proposed += proposed
            # Adjusted falls back to the proposed amount wherever no
            # adjustment has been made yet, so this reflects "what the
            # balance would look like using admin's adjustments so far."
            total_adjusted += l.adjusted_proposal if l.adjusted_proposal is not None else proposed
            # Approved only counts once an admin has actually approved that
            # line -- this reflects the real, locked-in commitment, which
            # matters once a prorated/adjusted amount has been approved.
            total_approved += l.approved_amount or 0

    # Special Purpose Appropriations (mandatory deductions like the 20%
    # Development Fund and 5% LDRRMF) are committed against available funds
    # BEFORE offices are allocated anything, so they reduce the balance the
    # same way office expenditures do.
    total_spa = _total_spa(db, year, budget_type, supplemental_number)

    return schemas.BudgetSummaryOut(
        year=year, budget_type=budget_type,
        supplemental_number=(supplemental_number or 1) if budget_type == "supplemental" else None,
        available_budget=available_budget,
        total_spa=total_spa,
        total_proposed=total_proposed,
        total_adjusted=total_adjusted,
        total_approved=total_approved,
        balance_vs_proposed=available_budget - total_spa - total_proposed,
        balance_vs_adjusted=available_budget - total_spa - total_adjusted,
        balance_vs_approved=available_budget - total_spa - total_approved,
    )


# --------------------------------------------------------------- summary report --

@app.get("/api/admin/summary-report", response_model=schemas.SummaryReportOut)
def summary_report(year: int, budget_type: str, supplemental_number: Optional[int] = None,
                    db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """Consolidated totals per account, across every office's proposal for
    this budget cycle -- the answer to 'how much is being asked for, in
    total, for each account?'"""
    if budget_type not in ("annual", "supplemental"):
        raise HTTPException(status_code=400, detail="budget_type must be 'annual' or 'supplemental'")

    prop_q = db.query(models.Proposal).filter(
        models.Proposal.year == year, models.Proposal.budget_type == budget_type,
    )
    if budget_type == "supplemental":
        prop_q = prop_q.filter(models.Proposal.supplemental_number == (supplemental_number or 1))
    else:
        prop_q = prop_q.filter(models.Proposal.supplemental_number.is_(None))
    proposals = prop_q.all()

    totals = {}  # account_id -> accumulator dict
    for p in proposals:
        for l in p.lines:
            acc = l.account
            entry = totals.setdefault(acc.id, {
                "account_id": acc.id, "account_code": acc.code, "account_name": acc.name,
                "classification": account_classification_str(acc),
                "total_prev_year_actual": 0.0, "total_current_annual": 0.0, "total_current_total": 0.0,
                "total_proposed": 0.0, "total_adjusted": 0.0, "total_approved": 0.0,
                "offices_included": 0,
            })
            supp_total = sum(s.amount or 0 for s in l.current_supplementals)
            current_total = (l.current_annual or 0) + supp_total
            proposed = l.proposed_amount or 0
            entry["total_prev_year_actual"] += (l.prev_year_actual or 0)
            entry["total_current_annual"] += (l.current_annual or 0)
            entry["total_current_total"] += current_total
            entry["total_proposed"] += proposed
            entry["total_adjusted"] += l.adjusted_proposal if l.adjusted_proposal is not None else proposed
            entry["total_approved"] += (l.approved_amount or 0)
            if proposed != 0:
                entry["offices_included"] += 1

    rows = [schemas.SummaryAccountRow(**v) for v in totals.values()]
    rows.sort(key=lambda r: (r.classification, r.account_code, r.account_name))

    return schemas.SummaryReportOut(
        year=year, budget_type=budget_type,
        supplemental_number=(supplemental_number or 1) if budget_type == "supplemental" else None,
        offices_count=len(proposals),
        rows=rows,
    )


@app.get("/api/admin/summary-report/excel")
def summary_report_excel(year: int, budget_type: str, supplemental_number: Optional[int] = None,
                          db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    report = summary_report(year, budget_type, supplemental_number, db, admin)
    buf = build_summary_workbook(report.model_dump())
    supp_part = f"_No{report.supplemental_number}" if report.supplemental_number else ""
    filename = f"Summary_{budget_type}{supp_part}_{year}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/admin/lbp-form1-excel")
def lbp_form1_excel(year: int, budget_type: str, supplemental_number: Optional[int] = None,
                     db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """The full 'Budget of Expenditures and Sources of Financing' report
    (LBP Form No. 1 layout) -- fund sources/receipts, office expenditures by
    classification, mandatory Special Purpose Appropriations, and the
    resulting ending balance, all in one document."""
    report = summary_report(year, budget_type, supplemental_number, db, admin)

    fs_q = db.query(models.FundSource).filter(
        models.FundSource.year == year, models.FundSource.budget_type == budget_type,
    )
    if budget_type == "supplemental":
        fs_q = fs_q.filter(models.FundSource.supplemental_number == (supplemental_number or 1))
    else:
        fs_q = fs_q.filter(models.FundSource.supplemental_number.is_(None))
    fund_sources = [{"category": fs.category, "particulars": fs.particulars, "amount": fs.amount} for fs in fs_q.all()]

    spa_rows = [
        {"name": s.name, "amount": s.amount, "auto_computed": s.auto_computed}
        for s in _spa_rows_with_live_amounts(db, year, budget_type, supplemental_number)
    ]

    province_setting = db.query(models.AppSetting).filter(models.AppSetting.key == "province_name").first()
    province_name = province_setting.value_data.decode("utf-8") if province_setting and province_setting.value_data else ""

    data = report.model_dump()
    data["summary_rows"] = data["rows"]
    data["fund_sources"] = fund_sources
    data["spa_rows"] = spa_rows
    data["province_name"] = province_name

    buf = build_lbp_form1_workbook(data)
    supp_part = f"_No{report.supplemental_number}" if report.supplemental_number else ""
    filename = f"LBP_Form1_{budget_type}{supp_part}_{year}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------- account proration --

def _matching_proposals(db: Session, year: int, budget_type: str, supplemental_number: Optional[int]):
    q = db.query(models.Proposal).filter(
        models.Proposal.year == year, models.Proposal.budget_type == budget_type,
    )
    if budget_type == "supplemental":
        q = q.filter(models.Proposal.supplemental_number == (supplemental_number or 1))
    else:
        q = q.filter(models.Proposal.supplemental_number.is_(None))
    return q.all()


@app.post("/api/admin/prorate-account/preview", response_model=schemas.ProratePreviewOut)
def prorate_preview(payload: schemas.ProrateRequest, db: Session = Depends(get_db),
                     admin: models.User = Depends(require_admin)):
    """Shows what applying a month-based proration (e.g. budget for 6 of 12
    months, for job-order/contract-of-service salary accounts) would do to
    every office's proposed amount for one account -- WITHOUT saving
    anything yet."""
    account = db.query(models.Account).get(payload.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if payload.budget_type not in ("annual", "supplemental"):
        raise HTTPException(status_code=400, detail="budget_type must be 'annual' or 'supplemental'")
    if payload.months <= 0 or payload.months > 12:
        raise HTTPException(status_code=400, detail="months must be between 0 and 12")

    proposals = _matching_proposals(db, payload.year, payload.budget_type, payload.supplemental_number)
    factor = payload.months / 12.0

    rows = []
    total_current = 0.0
    total_new = 0.0
    for p in proposals:
        line = next((l for l in p.lines if l.account_id == payload.account_id), None)
        if not line:
            continue
        current_proposed = line.proposed_amount or 0
        new_adjusted = round(current_proposed * factor, 2)
        rows.append(schemas.ProratePreviewRow(
            office_id=p.office_id, office_name=p.office.name,
            current_proposed=current_proposed, new_adjusted=new_adjusted,
            change=new_adjusted - current_proposed,
        ))
        total_current += current_proposed
        total_new += new_adjusted

    return schemas.ProratePreviewOut(
        account_name=f"{account.name} ({account.code})",
        months=payload.months,
        rows=rows,
        total_current_proposed=total_current,
        total_new_adjusted=total_new,
        total_change=total_new - total_current,
    )


@app.post("/api/admin/prorate-account/apply", response_model=schemas.ProratePreviewOut)
def prorate_apply(payload: schemas.ProrateRequest, db: Session = Depends(get_db),
                   admin: models.User = Depends(require_admin)):
    """Applies the proration: writes into Adjusted Proposal (and a matching
    Remarks for Adjusted Proposal note) for every office's line for this
    account, for this budget cycle. Does not touch the original Proposed
    amount or the final Approved amount."""
    preview = prorate_preview(payload, db, admin)  # reuses validation + calculation

    proposals = _matching_proposals(db, payload.year, payload.budget_type, payload.supplemental_number)
    note = f"Prorated to {payload.months} of 12 months (Job Order / Contract of Service) — {datetime.utcnow().strftime('%Y-%m-%d')}"
    touched_count = 0
    for p in proposals:
        line = next((l for l in p.lines if l.account_id == payload.account_id), None)
        if not line:
            continue
        current_proposed = line.proposed_amount or 0
        line.adjusted_proposal = round(current_proposed * (payload.months / 12.0), 2)
        line.remarks_adjusted = note
        log_action(db, p, admin, "admin_fields_updated",
                   f"Adjusted Proposal set via proration tool for {line.account.code}: {note}")
        touched_count += 1
    db.commit()

    return preview


# ------------------------------------------------------------------ report --

@app.get("/api/proposal/{proposal_id}/excel")
def download_excel(proposal_id: int, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    proposal = db.query(models.Proposal).get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    enforce_office_access(user, proposal.office_id)

    data = proposal_to_out(proposal).model_dump()
    buf = build_report_workbook(data)
    type_part = proposal.budget_type.value
    if proposal.budget_type == models.BudgetType.supplemental and proposal.supplemental_number:
        type_part += f"No{proposal.supplemental_number}"
    filename = f"{proposal.office.name.replace(' ', '_')}_{type_part}_{proposal.year}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ------------------------------------------------------------- attachments --
# Files are stored as bytes directly in the database (see models.py) rather
# than on local disk. This matters for hosting on platforms with an
# ephemeral filesystem (e.g. Render's free tier) -- as long as the database
# itself is persistent (e.g. an external free Postgres like Neon/Supabase),
# attachments survive restarts and redeploys without needing a paid disk.
# PDF-only, capped at 8 MB per file. Reasoning: a typical scanned multi-page
# supporting document (quotation, canvass, PR) at a normal scan quality runs
# well under this, but 15 MB (the old limit) let a single file eat 3% of
# Neon's free 0.5 GB tier -- 8 MB keeps individual files reasonable while
# still comfortably fitting a 10-20 page scanned PDF.
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024  # 8 MB per file


def get_line_or_404(db: Session, line_id: int) -> models.ProposalLine:
    line = db.query(models.ProposalLine).get(line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Proposal line not found")
    return line


@app.post("/api/proposal-lines/{line_id}/attachments", response_model=schemas.AttachmentOut)
async def upload_attachment(line_id: int, file: UploadFile = File(...),
                             db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    line = get_line_or_404(db, line_id)
    proposal = line.proposal
    enforce_office_access(user, proposal.office_id)
    if user.role == models.Role.client and proposal.status == models.ProposalStatus.submitted:
        raise HTTPException(
            status_code=400,
            detail="This proposal has already been submitted. Reopen it before adding attachments."
        )

    filename = file.filename or "attachment"
    is_pdf = (file.content_type == "application/pdf") or filename.lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Only PDF files are accepted for supporting documents.")

    contents = await file.read()
    if len(contents) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File is larger than the {MAX_ATTACHMENT_BYTES // (1024*1024)} MB limit for supporting documents."
        )

    attachment = models.ProposalLineAttachment(
        proposal_line_id=line_id,
        filename=filename,
        content_type=file.content_type,
        file_data=contents,
        file_size=len(contents),
        uploaded_by=user.username,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    log_action(db, proposal, user, "attachment_added", f"Attached \"{attachment.filename}\" to {line.account.code}")
    db.commit()

    return schemas.AttachmentOut(
        id=attachment.id, filename=attachment.filename, uploaded_by=attachment.uploaded_by,
        uploaded_at=attachment.uploaded_at.isoformat() + "Z",
    )


@app.get("/api/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db),
                         user: models.User = Depends(get_current_user)):
    attachment = db.query(models.ProposalLineAttachment).get(attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    proposal = attachment.line.proposal
    enforce_office_access(user, proposal.office_id)

    return Response(
        content=attachment.file_data,
        media_type=attachment.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{attachment.filename}"'},
    )


@app.delete("/api/attachments/{attachment_id}")
def delete_attachment(attachment_id: int, db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)):
    attachment = db.query(models.ProposalLineAttachment).get(attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    line = attachment.line
    proposal = line.proposal
    enforce_office_access(user, proposal.office_id)
    if user.role == models.Role.client and proposal.status == models.ProposalStatus.submitted:
        raise HTTPException(
            status_code=400,
            detail="This proposal has already been submitted. Reopen it before removing attachments."
        )

    log_action(db, proposal, user, "attachment_removed", f"Removed \"{attachment.filename}\" from {line.account.code}")
    db.delete(attachment)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------- backup & cleanup --
# These give the admin a way to (1) download everything as a real backup file
# they keep on their own computer, and (2) free up space on a limited-storage
# database plan (like Neon's free tier) by removing old attachments or whole
# old years -- always AFTER a backup exists, since these operations are
# permanent.

def _table_to_dicts(rows, exclude=()):
    """Serialize a list of SQLAlchemy model instances to plain dicts,
    converting datetimes to ISO strings and skipping excluded columns
    (e.g. password hashes)."""
    out = []
    for r in rows:
        d = {}
        for col in r.__table__.columns:
            if col.name in exclude:
                continue
            val = getattr(r, col.name)
            if isinstance(val, datetime):
                val = val.isoformat() + "Z"
            d[col.name] = val
        out.append(d)
    return out


@app.get("/api/admin/backup")
def download_backup(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """Exports every table (minus password hashes) as JSON, plus every
    attachment's actual file bytes, all inside one downloadable .zip."""
    offices = db.query(models.Office).all()
    users = db.query(models.User).all()
    accounts = db.query(models.Account).all()
    proposals = db.query(models.Proposal).all()
    lines = db.query(models.ProposalLine).all()
    attachments = db.query(models.ProposalLineAttachment).all()
    fund_sources = db.query(models.FundSource).all()
    audit_log = db.query(models.AuditLog).all()

    data = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "offices": _table_to_dicts(offices),
        "users": _table_to_dicts(users, exclude=("password_hash",)),
        "accounts": _table_to_dicts(accounts),
        "proposals": _table_to_dicts(proposals),
        "proposal_lines": _table_to_dicts(lines),
        "attachments_index": _table_to_dicts(attachments, exclude=("file_data",)),
        "fund_sources": _table_to_dicts(fund_sources),
        "audit_log": _table_to_dicts(audit_log),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(data, indent=2, default=str))
        for a in attachments:
            safe_name = f"{a.id}_{a.filename}".replace("/", "_").replace("\\", "_")
            zf.writestr(f"attachments/{safe_name}", a.file_data)
    buf.seek(0)

    filename = f"budget_app_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/admin/cleanup-attachments")
def cleanup_attachments(payload: schemas.CleanupAttachmentsRequest, db: Session = Depends(get_db),
                         admin: models.User = Depends(require_admin)):
    """Deletes attachment FILES for a given year to free up storage, while
    leaving all proposal data (amounts, remarks, everything else) untouched.
    Strongly recommend downloading a backup first -- this cannot be undone."""
    attachments = (
        db.query(models.ProposalLineAttachment)
        .join(models.ProposalLine)
        .join(models.Proposal)
        .filter(models.Proposal.year == payload.year)
        .all()
    )
    count = len(attachments)
    bytes_freed = sum(a.file_size or len(a.file_data or b"") for a in attachments)
    for a in attachments:
        db.delete(a)
    db.commit()
    return {"deleted_count": count, "bytes_freed": bytes_freed}


@app.delete("/api/admin/purge-year")
def purge_year(payload: schemas.PurgeYearRequest, db: Session = Depends(get_db),
               admin: models.User = Depends(require_admin)):
    """Permanently deletes ALL proposals (and their lines, attachments, and
    audit history) for a given year, across every office and every budget
    type/supplemental. Requires typing the year twice as a safety check.
    Download a backup first -- there is no undo."""
    if payload.year != payload.confirm_year:
        raise HTTPException(status_code=400, detail="Year confirmation did not match. Nothing was deleted.")

    proposals = db.query(models.Proposal).filter(models.Proposal.year == payload.year).all()
    proposal_count = len(proposals)
    line_count = sum(len(p.lines) for p in proposals)
    attachment_count = sum(len(l.attachments) for p in proposals for l in p.lines)

    for p in proposals:
        db.delete(p)  # cascades to lines, attachments, and audit log entries
    db.commit()

    return {
        "deleted_proposals": proposal_count,
        "deleted_lines": line_count,
        "deleted_attachments": attachment_count,
    }


# ------------------------------------------------------------- serve the frontend --
# Static frontend files live in ../frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    @app.get("/")
    def root():
        return RedirectResponse(url="/app/")

    @app.get("/sw.js")
    def service_worker():
        """Served from the SITE ROOT (not /app/sw.js) specifically so its
        default registration scope covers the entire origin, including the
        bare domain -- not just pages under /app/. This matters because
        people naturally bookmark/type the bare site address, which would
        otherwise fall outside the service worker's coverage and fail to
        load offline."""
        sw_path = os.path.join(FRONTEND_DIR, "sw.js")
        return FileResponse(sw_path, media_type="application/javascript")
