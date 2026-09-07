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
    prev_year_actual: Optional[float] = None
    current_annual: Optional[float] = None
    current_supplemental: Optional[float] = None
    proposed_amount: Optional[float] = None
    remarks: Optional[str] = None


class AttachmentOut(BaseModel):
    id: int
    filename: str
    uploaded_by: str
    uploaded_at: str


class ProposalLineOut(BaseModel):
    id: int
    account_id: int
    account_code: str
    account_name: str
    classification: str
    prev_year_actual: float
    current_annual: float
    current_supplemental: float
    current_total: float
    proposed_amount: float
    difference: float
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
    balance: float
