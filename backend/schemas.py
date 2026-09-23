from pydantic import BaseModel
from typing import Optional, List


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    role: str
    office_id: Optional[int] = None
    office_name: Optional[str] = None
    username: str


class OfficeCreate(BaseModel):
    name: str
    code: Optional[str] = None
    sector: Optional[str] = None


class OfficeOut(OfficeCreate):
    id: int
    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    password: str
    role: str                     # "admin" | "client"
    office_id: Optional[int] = None


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    office_id: Optional[int] = None
    office_name: Optional[str] = None
    class Config:
        from_attributes = True


class AccountCreate(BaseModel):
    classification: str           # "PS" | "MOOE" | "CO" | "FE"
    code: str
    name: str


class AccountOut(AccountCreate):
    id: int
    class Config:
        from_attributes = True


class AccountUpdate(BaseModel):
    classification: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None


class ProposalLineIn(BaseModel):
    account_id: int
    current_annual: Optional[float] = None
    proposed_amount: Optional[float] = None
    remarks: Optional[str] = None
    # supplemental_number (as string key) -> amount, for THIS current-year
    # reference (e.g. {"1": 500000, "2": 120000}). Office-entered.
    current_supplementals: Optional[dict] = None


class AdminLineUpdateIn(BaseModel):
    """Fields only an admin can set, independent of the submit/approve locks."""
    account_id: int
    prev_year_actual: Optional[float] = None
    adjusted_proposal: Optional[float] = None
    remarks_adjusted: Optional[str] = None


class AdminLinesUpdateRequest(BaseModel):
    lines: List[AdminLineUpdateIn]


class AttachmentOut(BaseModel):
    id: int
    filename: str
    uploaded_by: str
    uploaded_at: str


class CurrentSupplementalOut(BaseModel):
    supplemental_number: int
    amount: float


class ProposalLineOut(BaseModel):
    id: int
    account_id: int
    account_code: str
    account_name: str
    classification: str
    prev_year_actual: float
    current_annual: float
    current_supplementals: List[CurrentSupplementalOut] = []
    current_total: float
    proposed_amount: float
    difference: float
    adjusted_proposal: Optional[float] = None
    remarks_adjusted: Optional[str] = None
    approved_amount: Optional[float] = None
    remarks: Optional[str] = None
    attachments: List[AttachmentOut] = []


class ProposalOut(BaseModel):
    id: int
    office_id: int
    office_name: str
    office_code: Optional[str] = None
    office_sector: Optional[str] = None
    year: int
    budget_type: str
    supplemental_number: Optional[int] = None
    status: str
    approval_status: str
    lines: List[ProposalLineOut]


class AuditLogOut(BaseModel):
    id: int
    username: str
    action: str
    detail: Optional[str] = None
    timestamp: str


class ApprovalLineIn(BaseModel):
    account_id: int
    approved_amount: float


class SaveLinesRequest(BaseModel):
    lines: List[ProposalLineIn]
    submit: bool = False


class ApproveLinesRequest(BaseModel):
    lines: List[ApprovalLineIn]


class AddCurrentSupplementalRequest(BaseModel):
    pass  # no body needed -- just adds the next supplemental_number


class FundSourceCreate(BaseModel):
    year: int
    budget_type: str                       # "annual" | "supplemental"
    supplemental_number: Optional[int] = None
    category: str
    particulars: str
    amount: float


class FundSourceSeedRequest(BaseModel):
    year: int
    budget_type: str
    supplemental_number: Optional[int] = None


class FundSourceUpdate(BaseModel):
    category: Optional[str] = None
    particulars: Optional[str] = None
    amount: Optional[float] = None


class FundSourceOut(BaseModel):
    id: int
    year: int
    budget_type: str
    supplemental_number: Optional[int] = None
    category: str
    particulars: str
    amount: float
    class Config:
        from_attributes = True


class BudgetSummaryOut(BaseModel):
    year: int
    budget_type: str
    supplemental_number: Optional[int] = None
    available_budget: float
    total_proposed: float
    total_adjusted: float
    balance_vs_proposed: float
    balance_vs_adjusted: float


class CleanupAttachmentsRequest(BaseModel):
    year: int


class PurgeYearRequest(BaseModel):
    year: int
    confirm_year: int


class SummaryAccountRow(BaseModel):
    account_id: int
    account_code: str
    account_name: str
    classification: str
    total_prev_year_actual: float
    total_current_annual: float
    total_current_total: float
    total_proposed: float
    total_adjusted: float
    total_approved: float
    offices_included: int


class SummaryReportOut(BaseModel):
    year: int
    budget_type: str
    supplemental_number: Optional[int] = None
    offices_count: int
    rows: List[SummaryAccountRow]


class ProrateRequest(BaseModel):
    year: int
    budget_type: str
    supplemental_number: Optional[int] = None
    account_id: int
    months: float


class ProratePreviewRow(BaseModel):
    office_id: int
    office_name: str
    current_proposed: float
    new_adjusted: float
    change: float


class ProratePreviewOut(BaseModel):
    account_name: str
    months: float
    rows: List[ProratePreviewRow]
    total_current_proposed: float
    total_new_adjusted: float
    total_change: float
