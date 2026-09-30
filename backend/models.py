from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, DateTime, UniqueConstraint, Enum, Text, LargeBinary
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from database import Base


class Role(str, enum.Enum):
    admin = "admin"
    client = "client"


class Classification(str, enum.Enum):
    PS = "PS"        # Personal Services
    MOOE = "MOOE"     # Maintenance and Other Operating Expenditures
    CO = "CO"        # Capital Outlay
    FE = "FE"        # Financial Expenses


class BudgetType(str, enum.Enum):
    annual = "annual"
    supplemental = "supplemental"


class ProposalStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"


class Office(Base):
    __tablename__ = "offices"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    code = Column(String, nullable=True)          # e.g. "1000 1 01 001"
    sector = Column(String, nullable=True)         # e.g. "GENERAL PUBLIC SERVICES"
    logo_data = Column(LargeBinary, nullable=True)       # falls back to the default/province logo if not set
    logo_content_type = Column(String, nullable=True)

    @property
    def has_logo(self) -> bool:
        return self.logo_data is not None

    users = relationship("User", back_populates="office")
    proposals = relationship("Proposal", back_populates="office")


class SpecialPurposeAppropriation(Base):
    """Mandatory deductions from available funds before offices can be
    allocated anything -- e.g. the 20% Development Fund and 5% LDRRMF,
    which are computed automatically from fund sources, plus fixed/editable
    ones like Aid to Barangays, plus any other custom ones admin adds."""
    __tablename__ = "special_purpose_appropriations"
    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    budget_type = Column(Enum(BudgetType), nullable=False)
    supplemental_number = Column(Integer, nullable=True)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False, default=0)      # stored value; ignored/recomputed for auto_computed rows
    auto_computed = Column(String, nullable=True)  # None | "dev_fund_20pct" | "ldrrmf_5pct"
    sort_order = Column(Integer, nullable=False, default=0)


class AppSetting(Base):
    """Small key/value store for branding assets that apply app-wide rather
    than to one office -- the login screen logo and the default/province
    logo (used as the fallback wherever an office has no logo of its own)."""
    __tablename__ = "app_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    value_data = Column(LargeBinary, nullable=True)
    value_content_type = Column(String, nullable=True)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False)
    office_id = Column(Integer, ForeignKey("offices.id"), nullable=True)  # null for admins

    office = relationship("Office", back_populates="users")


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    classification = Column(Enum(Classification), nullable=False)
    code = Column(String, nullable=False)
    # Account names must be unique across the ENTIRE chart of accounts --
    # not just within one classification. Two different accounts can still
    # share the same code (that's expected -- see e.g. Salaries & Wages
    # variants), but never the same name.
    name = Column(String, nullable=False, unique=True)


class Proposal(Base):
    __tablename__ = "proposals"
    id = Column(Integer, primary_key=True)
    office_id = Column(Integer, ForeignKey("offices.id"), nullable=False)
    year = Column(Integer, nullable=False)          # the proposed/budgeted year, e.g. 2027
    budget_type = Column(Enum(BudgetType), nullable=False)
    # Only used when budget_type == supplemental. Offices can submit several
    # supplemental proposals in the same year (No. 1, No. 2, ... up to however
    # many they need), so this is an open-ended integer, not capped at any
    # fixed number.
    supplemental_number = Column(Integer, nullable=True)
    status = Column(Enum(ProposalStatus), default=ProposalStatus.draft, nullable=False)
    # Separate from `status` above. `status` = office's draft/submitted state.
    # `approval_status` = admin's own pending/approved state for the Approved
    # column. Reopening one must never flip the other.
    approval_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    office = relationship("Office", back_populates="proposals")
    lines = relationship("ProposalLine", back_populates="proposal", cascade="all, delete-orphan")
    audit_entries = relationship("AuditLog", back_populates="proposal", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("office_id", "year", "budget_type", "supplemental_number", name="uq_proposal"),
    )


class FundSource(Base):
    """A line item of available funding (e.g. Real Property Tax, IRA/NTA,
    Share from National Wealth) for a specific budget cycle. Used to compute
    the running balance: available funds vs. total proposed amounts."""
    __tablename__ = "fund_sources"
    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    budget_type = Column(Enum(BudgetType), nullable=False)
    supplemental_number = Column(Integer, nullable=True)  # only used when budget_type == supplemental
    category = Column(String, nullable=False)   # e.g. "Local Sources - Tax Revenue", "External Sources"
    particulars = Column(String, nullable=False)  # e.g. "Real Property Tax (RPT)"
    amount = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    """Records who changed what on a proposal, and when -- shown to admins
    (and the owning office) as an activity/history log."""
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String, nullable=False)
    action = Column(String, nullable=False)   # "draft_saved" | "submitted" | "reopened" | "approved"
    detail = Column(String, nullable=True)     # short human-readable summary of what changed
    timestamp = Column(DateTime, default=datetime.utcnow)

    proposal = relationship("Proposal", back_populates="audit_entries")


class ProposalLine(Base):
    __tablename__ = "proposal_lines"
    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)

    prev_year_actual = Column(Float, default=0)         # e.g. 2025 actual -- ADMIN-ENTERED ONLY
    current_annual = Column(Float, default=0)           # e.g. 2026 annual budget -- office-entered
    proposed_amount = Column(Float, default=0)          # e.g. 2027 proposal - client-entered
    approved_amount = Column(Float, nullable=True)       # admin-entered only, locked by approval_status
    remarks = Column(Text, nullable=True)                # office's justification for the proposed amount

    # Admin's own working adjustment, separate from the final Approved figure
    # (e.g. used by the job-order/contract-of-service proration tool). Always
    # admin-editable, independent of the approval lock.
    adjusted_proposal = Column(Float, nullable=True)
    remarks_adjusted = Column(Text, nullable=True)

    proposal = relationship("Proposal", back_populates="lines")
    account = relationship("Account")
    attachments = relationship("ProposalLineAttachment", back_populates="line", cascade="all, delete-orphan")
    current_supplementals = relationship(
        "ProposalLineCurrentSupplemental", back_populates="line",
        cascade="all, delete-orphan", order_by="ProposalLineCurrentSupplemental.supplemental_number"
    )

    __table_args__ = (UniqueConstraint("proposal_id", "account_id", name="uq_proposal_line"),)


class ProposalLineCurrentSupplemental(Base):
    """One of possibly several supplemental-budget reference amounts for the
    CURRENT year (e.g. if 2026 had Supplemental No.1 and No.2, a 2027
    proposal's lines can carry both as separate reference columns)."""
    __tablename__ = "proposal_line_current_supplementals"
    id = Column(Integer, primary_key=True)
    proposal_line_id = Column(Integer, ForeignKey("proposal_lines.id"), nullable=False)
    supplemental_number = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False, default=0)

    line = relationship("ProposalLine", back_populates="current_supplementals")

    __table_args__ = (UniqueConstraint("proposal_line_id", "supplemental_number", name="uq_line_current_supp"),)


class ProposalLineAttachment(Base):
    """A supporting document (PDF, image, spreadsheet, etc.) the office
    uploads to justify a specific proposed amount. The file itself is stored
    directly in the database (not on local disk) so it survives restarts and
    redeploys even on hosts with an ephemeral filesystem, like Render's free
    tier."""
    __tablename__ = "proposal_line_attachments"
    id = Column(Integer, primary_key=True)
    proposal_line_id = Column(Integer, ForeignKey("proposal_lines.id"), nullable=False)
    filename = Column(String, nullable=False)          # original filename, shown to users
    content_type = Column(String, nullable=True)
    file_data = Column(LargeBinary, nullable=False)     # the actual file bytes
    file_size = Column(Integer, nullable=False, default=0)
    uploaded_by = Column(String, nullable=False)        # username, for display
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    line = relationship("ProposalLine", back_populates="attachments")
