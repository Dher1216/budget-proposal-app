import os
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
from excel_export import build_report_workbook

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
    current_total = (line.current_annual or 0) + (line.current_supplemental or 0)
    difference = (line.proposed_amount or 0) - current_total
    return schemas.ProposalLineOut(
        id=line.id,
        account_id=line.account_id,
        account_code=line.account.code,
        account_name=line.account.name,
        classification=account_classification_str(line.account),
        prev_year_actual=line.prev_year_actual or 0,
        current_annual=line.current_annual or 0,
        current_supplemental=line.current_supplemental or 0,
        current_total=current_total,
        proposed_amount=line.proposed_amount or 0,
        difference=difference,
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
        (l.current_supplemental or 0) != 0 or (l.proposed_amount or 0) != 0 or
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
        if item.prev_year_actual is not None and item.prev_year_actual != line.prev_year_actual:
            line.prev_year_actual = item.prev_year_actual
            touched = True
        if item.current_annual is not None and item.current_annual != line.current_annual:
            line.current_annual = item.current_annual
            touched = True
        if item.current_supplemental is not None and item.current_supplemental != line.current_supplemental:
            line.current_supplemental = item.current_supplemental
            touched = True
        if item.proposed_amount is not None and item.proposed_amount != line.proposed_amount:
            line.proposed_amount = item.proposed_amount
            touched = True
        if item.remarks is not None and item.remarks != line.remarks:
            line.remarks = item.remarks
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
    proposal.status = models.ProposalStatus.draft
    who = "the admin" if user.role == models.Role.admin else "the office"
    log_action(db, proposal, user, "reopened", f"Reopened for editing by {who}")
    db.commit()
    db.refresh(proposal)
    return proposal_to_out(proposal)


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
    for p in prop_q.all():
        for l in p.lines:
            total_proposed += (l.proposed_amount or 0)

    return schemas.BudgetSummaryOut(
        year=year, budget_type=budget_type,
        supplemental_number=(supplemental_number or 1) if budget_type == "supplemental" else None,
        available_budget=available_budget,
        total_proposed=total_proposed,
        balance=available_budget - total_proposed,
    )


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
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024  # 15 MB per file


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

    contents = await file.read()
    if len(contents) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=400, detail="File is larger than the 15 MB limit.")

    attachment = models.ProposalLineAttachment(
        proposal_line_id=line_id,
        filename=file.filename or "attachment",
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


# ------------------------------------------------------------- serve the frontend --
# Static frontend files live in ../frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    @app.get("/")
    def root():
        return RedirectResponse(url="/app/")
