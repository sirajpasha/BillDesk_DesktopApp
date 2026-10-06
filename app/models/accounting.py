from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field

class PaymentAllocation(BaseModel):
    invoice_id: str
    amount: float
    allocated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Payment(BaseModel):
    payment_id: str
    company_id: Optional[str] = None
    party_id: str
    party_type: str = "customer"  # customer or supplier
    amount: float
    payment_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payment_method: str = "Cash"  # Cash, UPI, NEFT, RTGS, IMPS, Cheque
    bank_account_id: Optional[str] = None
    reference_no: Optional[str] = None
    reference_date: Optional[datetime] = None
    clearance_date: Optional[datetime] = None
    is_advance: bool = False
    allocation_status: str = "unallocated"  # unallocated, partial, full
    allocations: List[PaymentAllocation] = Field(default_factory=list)
    reconciliation_status: str = "unreconciled"
    reconciled_at: Optional[datetime] = None
    reconciled_by: Optional[str] = None
    notes: Optional[str] = None
    is_deleted: int = 0
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LedgerTransaction(BaseModel):
    transaction_id: str
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    company_id: Optional[str] = None
    account_id: str  # Customer ID or Supplier ID
    account_name: str
    type: str  # debit or credit
    amount: float
    reference_id: Optional[str] = None
    reference_type: str = "bill"  # bill, purchase, payment, opening_balance
    description: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Account(BaseModel):
    code: str  # e.g., "1010", "1200-AR", "4000-SALES"
    company_id: Optional[str] = None
    name: str
    type: str  # Asset, Liability, Equity, Income, Expense
    root_type: str = "Asset"
    level: int = 3
    parent_id: Optional[str] = None
    is_group: bool = False
    is_pl_account: bool = False
    is_bs_account: bool = False
    branch_id: Optional[str] = None
    cost_center: Optional[str] = None
    balance: float = 0.0
    status: str = "active"
    is_deleted: int = 0

class JournalLine(BaseModel):
    account_id: str
    debit: float = 0.0
    credit: float = 0.0
    base_debit: float = 0.0
    base_credit: float = 0.0
    currency: str = "INR"
    exchange_rate: float = 1.0
    partner_id: Optional[str] = None
    partner_type: Optional[str] = None
    branch_id: Optional[str] = None
    cost_center: Optional[str] = None
    description: Optional[str] = None

class JournalEntry(BaseModel):
    entry_id: str
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reference: str
    source_type: str = "pos_sale"  # pos_sale, vendor_bill, bank_statement, inventory_adjustment, manual
    lines: List[JournalLine]
    state: str = "posted"  # draft, posted
    company_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"

class BankAccount(BaseModel):
    account_id: str
    entity_id: Optional[str] = None
    bank_name: str
    account_number: str
    account_type: str = "Current"  # Savings, Current, OD, Cash
    gl_control_id: str = "1100-BANK"
    currency: str = "INR"
    opening_balance: float = 0.0
    current_balance: float = 0.0
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"

class BankStatementLine(BaseModel):
    line_id: str
    txn_date: datetime
    value_date: Optional[datetime] = None
    description: str
    reference_no: Optional[str] = None
    debit: float = 0.0
    credit: float = 0.0
    balance: float = 0.0
    reconciliation_status: str = "unreconciled"
    matched_payment_id: Optional[str] = None

class BankStatement(BaseModel):
    statement_id: str
    account_id: Optional[str] = None
    bank_name: Optional[str] = None
    import_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    period_start: datetime
    period_end: datetime
    uploaded_by: Optional[str] = None
    lines: List[BankStatementLine] = Field(default_factory=list)
    status: str = "open"  # open, closed

class InternalBankTransaction(BaseModel):
    txn_id: str
    account_id: str
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str
    reference_no: Optional[str] = None
    debit: float = 0.0
    credit: float = 0.0
    source_type: str = "payment"
    source_id: str = ""
    reconciliation_status: str = "unreconciled"
    company_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MiscellaneousEntry(BaseModel):
    entry_id: str
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: str  # income or expense
    category: str
    amount: float
    payment_method: str = "Cash"
    bank_account_id: Optional[str] = None
    reference_no: Optional[str] = None
    notes: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
