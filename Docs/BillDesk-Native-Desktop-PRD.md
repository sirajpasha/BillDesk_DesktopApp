# BillDesk Native Desktop — Product Requirements Document

**Product:** BillDesk / SV Billing  
**Target:** Native Windows-first desktop application, with future macOS/Linux portability  
**UI:** Python Tkinter/ttk  
**Application logic:** Python in-process services  
**Database:** MongoDB, local or remote/Atlas  
**API:** None between UI and business logic; no FastAPI/REST/browser runtime  
**Source of truth:** Reverse-engineered from the supplied BillDesk GitHub ZIP, including `docs/PRD.md`, detailed feature documentation, backend models/routers/services, desktop wrapper, seed/configuration files, and test documentation.  
**PRD status:** Target specification for the native rewrite  
**Prepared:** 2026-10-05

---

## Executive Summary

BillDesk is a wholesale produce/mandi billing, inventory, procurement, receivables/payables, banking, reconciliation, and accounting system designed for high-speed operational use.

The supplied repository already contains a substantial business system. Its current architecture is web/API-centric: Next.js/React frontend, FastAPI backend, MongoDB, and an Electron/PyWebView-style desktop wrapper. That wrapper is not a true native desktop application because it still hosts the web UI and communicates with the backend over HTTP.

This PRD defines the replacement architecture:

```text
Tkinter / ttk desktop forms
        |
        v
Python application services
        |
        v
Repositories / MongoDB driver
        |
        v
MongoDB
  |             |
Local        MongoDB Atlas
```

The native application must not require a browser, localhost HTTP server, FastAPI process, Node.js runtime, Electron, PyWebView, or a REST API.

The existing MongoDB domain model and business rules should be preserved wherever practical so that an existing `sv_billing` database can be migrated or reused. The rewrite should focus on replacing presentation, transport, and web-session concerns with native desktop concerns while hardening financial, stock, authentication, audit, and transactional correctness.

---

# 1. Problem Statement

## 1.1 User problem

Wholesale produce businesses operate under time pressure. Billing staff need to enter short item codes, quantities, and prices rapidly; managers need stock and pricing control; purchase staff need procurement workflows; accountants need receivables, payables, bank reconciliation, and financial statements.

The current BillDesk codebase already models these workflows, but the desktop experience is built around a web application wrapped as a desktop application. This introduces unnecessary runtime components:

- browser/web rendering
- Next.js/React
- FastAPI
- HTTP requests between UI and backend
- Electron/PyWebView packaging
- web-session concepts that are unnecessary for a single native process

The desired product is a genuine desktop application where the user opens BillDesk and interacts directly with Python forms and Python business logic.

## 1.2 Product problem

The rewrite must not accidentally become a second, simplified billing application. It must preserve the existing domain breadth:

- billing
- orders
- inventory
- procurement
- customer/supplier masters
- fixed pricing
- AR/AP
- TDS
- banking
- reconciliation
- general ledger
- reports
- crates/mandi operations
- audit
- backups
- OCR/import
- printing

The central product requirement is therefore:

> Extract the existing BillDesk business system from its web/API architecture and expose the same business capabilities through a native Python desktop application.

---

# 2. Product Vision

BillDesk Native is a fast, reliable, keyboard-first desktop operating system for a wholesale produce business.

A billing clerk should be able to:

1. log in;
2. select a customer;
3. enter item aliases and quantities;
4. accept or override applicable pricing;
5. save and print an invoice;
6. have stock, customer balance, crates, audit history, and accounting consequences updated correctly.

A manager should be able to control:

- item and customer masters;
- fixed pricing;
- stock;
- orders;
- purchases;
- users and permissions;
- company configuration;
- reports.

An accountant should be able to:

- collect customer payments;
- manage supplier payments;
- reconcile bank statements;
- inspect ledgers;
- run trial balance, P&L, and balance sheet.

The system should feel like a purpose-built desktop billing terminal rather than a website running in a desktop window.

---

# 3. Goals

## 3.1 Primary goals

1. Replace the web/Electron desktop experience with a genuine Tkinter desktop application.
2. Preserve the existing BillDesk domain model and business behavior.
3. Use MongoDB directly from Python.
4. Support MongoDB on local machine and MongoDB Atlas/remote deployments.
5. Provide a keyboard-first billing workflow.
6. Maintain financial and inventory integrity.
7. Provide role-based access and auditability.
8. Provide reliable invoice and report printing.
9. Support offline operation when the configured MongoDB is local and available.
10. Make the codebase modular enough that business logic can be tested without a GUI.

## 3.2 Secondary goals

1. Preserve compatibility with the existing `sv_billing` data model where practical.
2. Support Windows first.
3. Keep macOS/Linux portability possible.
4. Provide a simple installer and first-run setup.
5. Make database connection configuration explicit and safe.
6. Make backup and restore operationally understandable.
7. Improve known correctness/security gaps identified in the supplied repository.

---

# 4. Non-Goals

The following are not part of the first native rewrite unless explicitly added later:

1. A REST API between desktop forms and business logic.
2. A browser-based UI.
3. Next.js/React as the desktop UI.
4. Electron as the primary runtime.
5. FastAPI as an application dependency.
6. Payroll.
7. GST return filing.
8. GSTR automation.
9. E-invoicing/e-way bill integration.
10. Multi-currency accounting.
11. A native mobile application.
12. Rebuilding the accounting domain from scratch.
13. Deliberately changing existing MongoDB semantics without a migration decision.
14. Replacing MongoDB with SQL.

---

# 5. Personas and Roles

## 5.1 Owner / Super Admin

Primary responsibilities:

- company setup
- user management
- role management
- permissions
- backup/restore
- system settings
- all operational workflows
- audit review

## 5.2 Manager

Primary responsibilities:

- master data
- pricing
- stock adjustments
- billing supervision
- order supervision
- procurement
- reports
- bank account administration

## 5.3 Billing Clerk / User

Primary responsibilities:

- customer orders
- billing
- invoice printing
- bill lookup
- dashboard

Restrictions:

- no unrestricted accounting administration
- no user/role administration
- no company configuration

## 5.4 Accountant

Primary responsibilities:

- AR
- AP
- customer/supplier payments
- ledger
- trial balance
- P&L
- balance sheet
- bank reconciliation
- financial reports

## 5.5 Purchase Officer

Primary responsibilities:

- purchase orders
- GRN
- procurement workflows
- vendor bills

## 5.6 Customer Portal Identity

The existing project has a `Customer` role and user-to-customer mapping. In the native application this concept should remain available for compatibility, but the first desktop release should treat it primarily as a restricted identity model rather than assume a separate customer-facing application.

---

# 6. Domain Language

The following terms are canonical for the native application.

| Term | Meaning |
|---|---|
| Item | A sellable or stock-tracked product |
| Item Alias | Short code used for fast entry |
| Customer | Party to whom sales are billed |
| Supplier | Party from whom purchases are made |
| Bill | Sales financial document |
| Order | Customer demand before billing |
| Purchase Order | Request/commitment to supplier |
| GRN | Goods receipt against procurement |
| Purchase Bill | Supplier financial document |
| Payment | Money received from customer or paid to supplier |
| AR | Accounts receivable |
| AP | Accounts payable |
| Fixed Price | Customer/item contract price |
| Stock Transaction | Immutable inventory movement record |
| Crate Transaction | Returnable crate movement |
| Journal Entry | Balanced double-entry accounting transaction |
| Session | Cashier cash session |
| Audit | Record of who did what and when |
| Print Layout | Configurable document layout |
| Opening Balance | Starting financial position for a party/account |
| Soft Delete | Marking a record deleted/inactive without physically removing it |

Important distinction:

- **User** is an authenticated application identity.
- **Customer** is a commercial party.
- **Supplier** is a commercial party.
- A customer may have one or more user mappings, but the concepts must not be conflated.

---

# 7. Target Architecture

## 7.1 Architectural principle

The highest useful seam is the **application service layer**.

The UI should not contain business rules and should not directly mutate MongoDB documents.

```text
Tkinter UI
   |
   | commands / queries
   v
Application Services
   |
   +--> Domain validation/calculation
   |
   +--> Repositories
   |
   v
MongoDB
```

This is the primary testing seam.

A billing test should be able to call a billing application service with a request and verify the resulting bill, stock transaction, customer balance, audit event, and accounting effects without starting Tkinter.

## 7.2 UI layer

Use:

- `tkinter`
- `ttk`
- `tkinter.messagebox`
- `tkinter.filedialog`
- `tkinter.scrolledtext`
- native menus/dialogs
- `Treeview` for transactional tables
- keyboard bindings
- modal forms where appropriate

The UI must not know MongoDB collection details.

## 7.3 Application services

Core services:

- AuthenticationService
- AuthorizationService
- CompanySettingsService
- ItemService
- CustomerService
- SupplierService
- PricingService
- BillingService
- OrderService
- InventoryService
- ProcurementService
- PaymentService
- ARService
- APService
- BankingService
- ReconciliationService
- LedgerService
- ReportingService
- PrintingService
- OCRService
- SessionService
- AuditService
- BackupService

## 7.4 Repository layer

Repositories encapsulate MongoDB access.

Examples:

- ItemRepository
- CustomerRepository
- SupplierRepository
- BillRepository
- PaymentRepository
- OrderRepository
- StockTransactionRepository
- PurchaseRepository
- JournalRepository
- AuditRepository

The service layer owns business rules; repositories own persistence queries.

## 7.5 Database driver

Use PyMongo directly.

Beanie/Motor/FastAPI dependencies should not be required by the native application.

The application may use Pydantic models for validation and DTOs, but persistence should be explicit and understandable.

---

# 8. MongoDB Deployment Modes

## 8.1 Local MongoDB

Default development/desktop configuration:

```text
mongodb://127.0.0.1:27018
```

Database:

```text
sv_billing
```

The port must be configurable rather than hard-coded.

## 8.2 MongoDB Atlas

Support:

```text
mongodb+srv://...
```

Requirements:

- TLS
- least-privilege database user
- connection timeout
- server selection timeout
- clear connection diagnostics
- credentials stored outside source code

## 8.3 Configuration

The application must provide a native database configuration screen with:

- deployment type: Local / Remote
- MongoDB URI
- database name
- username/password when not embedded in URI
- TLS toggle where appropriate
- Test Connection
- Save
- Reset to defaults

The application should also support environment/config-file configuration for managed deployments.

## 8.4 Connection failure behavior

When MongoDB is unavailable:

- do not silently exit;
- display a useful native error;
- provide Retry;
- provide Database Settings;
- log the diagnostic locally;
- never show credentials in the error.

---

# 9. Authentication and Security

## 9.1 Native authentication

The login form contains:

- username
- password
- company context if multi-company is enabled

Successful login creates an in-process authenticated user context.

There is no JWT requirement for communication between UI and services because there is no HTTP boundary.

## 9.2 Passwords

Use bcrypt/Argon2-compatible password verification.

The native application must never store or display plaintext passwords.

The existing `password_plain` concept must be removed from the native target.

## 9.3 Session model

The application maintains a process-local current-user session and persists an audit/session record where needed.

Logout:

- clears current user context;
- closes the relevant session;
- returns to login.

Logout-all may close other persisted sessions if the business policy requires it.

## 9.4 RBAC

Authorization must be enforced at the service/action layer, not only by hiding menus.

Example:

```text
User
  -> may create bill
  -> may not modify company settings

Manager
  -> may adjust stock
  -> may edit pricing

Accountant
  -> may record payments
  -> may run financial reports
```

A hidden button is not a security boundary.

## 9.5 Audit

Financial mutations must record:

- actor
- action
- entity
- entity identifier
- timestamp
- before/after or relevant change details
- correlation/reference identifier

Sensitive values must be masked.

---

# 10. Master Data Requirements

## 10.1 Item Master

Fields:

- item ID/code
- alias
- name
- category
- unit
- status
- stock
- crate flag where applicable

Requirements:

- alias unique
- item code unique
- active/inactive
- soft deletion
- fast search
- category filter
- duplicate validation
- prevent unsafe deletion when referenced by active transactions

Categories include:

- Vegetables
- Fruits
- Groceries
- Dairy
- Others

Units include:

- kg
- unit
- bunch
- packet
- crate
- box
- other configured units

## 10.2 Customer Master

Fields include:

- customer ID
- name
- company
- delivery/ship-to address
- bill-to name/address
- phone
- WhatsApp
- email
- GST number
- opening balance
- opening balance date
- debit/credit type
- credit limit
- payment terms
- current balance
- crate balance

Rules:

- `credit_limit = 0` means unlimited
- default payment terms = 30 days
- GSTIN validation when supplied
- customer search must be fast enough for billing use

## 10.3 Supplier Master

Fields include:

- supplier ID
- name
- address
- email
- phone
- GST
- PAN
- MSME flag
- TDS applicability
- TDS rate
- TDS section
- payment terms
- opening balance
- AP control account

---

# 11. Fixed Pricing

The system must support customer/item fixed pricing.

Price precedence:

```text
active fixed price
      >
user-entered/default rate
```

Requirements:

- effective dates
- expiry dates
- customer-specific pricing
- item-specific pricing
- bulk import/update
- expiry monitoring
- audit trail
- price lookup during billing and order conversion

If a fixed price is active, the billing UI should clearly indicate that the rate was sourced from fixed pricing.

---

# 12. Billing Requirements

Billing is the primary operational workflow.

## 12.1 New Bill

The billing form must support:

- customer selection
- date
- invoice number
- item alias/code
- item name
- quantity
- unit
- rate
- amount
- discount/charges where applicable
- commission
- mandi fee
- crate movement
- notes
- payment mode where applicable

## 12.2 Keyboard-first behavior

Retain the existing F-key workflow where useful:

| Key | Action |
|---|---|
| F1 | Dashboard |
| F2 | Save transaction |
| F3 | Save and print |
| F5 | Customer/supplier search |
| F6 | Park bill |
| F7 | View parked bills |
| F8 | Smart importer |
| F10 | Item master |
| F11 | Customer master |
| F12 | Logout |

The UI must allow the clerk to complete a normal bill with minimal mouse interaction.

## 12.3 Billing validation

Reject:

- empty bill
- zero total
- no line items
- zero/negative quantity
- invalid rate
- duplicate item line where business policy disallows it
- unknown item
- inactive item
- customer credit-limit breach
- invalid date
- duplicate invoice number

## 12.4 Invoice numbering

Default:

```text
YYYYMMDD-NNNN
```

The sequence resets daily.

Requirements:

- unique
- concurrency-safe
- configurable format
- no duplicate numbers even under multiple clients

## 12.5 Price and balance rules

Due date:

```text
invoice date + customer payment terms
```

Bill status:

```text
unpaid -> partial -> paid
```

Cancelled/inactive bills are excluded from active AR.

## 12.6 Bill save transaction

The save operation must be atomic when MongoDB deployment supports transactions.

The logical operation is:

1. validate bill;
2. resolve prices;
3. validate stock;
4. calculate totals;
5. reserve/generate invoice number;
6. create bill;
7. decrement stock;
8. create stock transactions;
9. update customer balance;
10. update crate balance;
11. create ledger postings where required;
12. create audit entry.

If any required step fails, the operation must not leave financial/stock state partially committed.

For standalone local MongoDB without transactions, the implementation must use a documented consistency/recovery strategy and provide reconciliation tooling. Replica-set/Atlas deployments should use MongoDB transactions.

---

# 13. Bill History

Requirements:

- invoice number search
- customer search
- date filter
- status filter
- pagination
- newest first
- open/view
- print
- duplicate/clone where permitted
- edit where permitted
- void/cancel where permitted
- audit history

Search input must be treated literally; regex/operator injection must not be possible.

---

# 14. Bill Editing and Voiding

Editing financial documents must be controlled.

Requirements:

- role restriction
- audit before/after
- recalculation
- stock reversal/reapplication where relevant
- customer balance reversal/reapplication
- crate reversal/reapplication
- ledger reversal where relevant

Void is not a physical delete.

A voided bill remains auditable.

If payments are allocated to a bill, the system must either:

- require payment allocation reversal first; or
- execute a complete financial reversal workflow.

---

# 15. Printing

The native app must generate:

- invoice PDF
- customer statement
- consolidated report
- order matrix
- purchase order
- delivery challan where supported
- payment advice
- Z/cash session report where supported

Requirements:

- A4
- Indian currency formatting
- amount in words
- company header
- customer information
- invoice metadata
- repeating table headers
- multi-page support
- configurable print layout
- direct print option
- PDF preview/save

The print engine should be independent of the UI so that reports can be generated from services.

---

# 16. Order Management

Order lifecycle:

```text
pending
  -> confirmed
  -> delivered
  -> billed
```

Cancellation is a terminal path.

Requirements:

- create order
- customer
- delivery date
- item lines
- quantities
- notes
- status
- edit
- cancel
- convert to bill
- convert to purchase
- audit
- print
- consolidation

Customer-role users must only access mapped customers.

Past delivery dates must be validated according to an explicit business cut-off policy.

---

# 17. Order Consolidation

The system must support:

### Order Matrix

Item x Customer demand compared with current stock.

The report should identify:

- total demand
- available stock
- shortfall
- customer quantities
- delivery date

Shortfall must be obvious.

### Consolidated Order Report

Group pending demand for operational picking/packing.

Cancelled and already-billed orders must be excluded.

---

# 18. Inventory

Inventory requirements:

- current stock view
- opening stock
- manual adjustment
- waste
- stock history
- sale movements
- purchase movements
- adjustment movements
- waste movements
- reconciliation

Stock convention:

```text
sale      = negative
purchase  = positive
waste     = negative
adjustment = signed
```

The system must avoid lost updates. Atomic MongoDB increments should be preferred for stock changes.

A reconciliation operation should be able to verify:

```text
current stock ≈ sum of stock transactions
```

Any difference must be reportable.

---

# 19. Mandi Operations

## 19.1 Commission and mandi fee

Support configured percentages.

The target product must make the financial treatment explicit:

- whether these are included in totals;
- whether they are deducted from payable;
- whether they are separate ledger lines.

This is a domain decision that must not remain implicit.

## 19.2 Crates

Track:

- issued
- returned
- customer balance
- supplier balance
- transaction history

Rules must define whether negative crate balances are permitted.

Crate deposits, if introduced, must have explicit accounting treatment.

---

# 20. Procurement

## 20.1 Purchase Order

Fields:

- supplier
- order number
- date
- items
- quantities
- rates
- status

Capabilities:

- create
- edit
- print
- email
- WhatsApp
- discrepancy notice

## 20.2 GRN

A GRN records goods received against a PO.

Effects:

- increase stock
- create purchase stock transaction
- update PO receipt progress

Over-receipt must trigger a configurable warning/tolerance rule.

## 20.3 Vendor Bill

A purchase bill may reference a GRN.

Requirements:

- supplier
- supplier invoice number
- bill date
- item lines
- taxable amount
- TDS
- payable amount
- AP posting

Three-way match target:

```text
PO quantity >= GRN quantity >= Vendor Bill quantity
```

with configured tolerance where required.

---

# 21. Accounts Receivable

## 21.1 Aging

Buckets:

- Current
- 1–30
- 31–60
- 61–90
- 90+

Based on due date.

## 21.2 Customer payments

Payment methods:

- NEFT
- RTGS
- IMPS
- UPI
- Cheque
- Cash

Support:

- FIFO allocation
- specific invoice allocation
- date-range allocation
- advance/unallocated payments
- knock-off against later invoices
- payment reference
- clearance information for cheques

Rules:

- allocation <= invoice balance
- allocation <= payment amount
- no negative invoice balance
- payment updates customer balance
- invoice status updates

Payment creation must be idempotent.

---

# 22. Accounts Payable and TDS

Support:

- AP invoice list
- aging
- stats
- payment forecasting
- supplier payment
- payment advice
- TDS alerts

TDS requirements:

- supplier applicability
- section
- rate
- taxable amount
- deduction
- payable amount
- liability register in future phase

Automatic TDS calculation is preferred over manual entry.

---

# 23. Banking and Reconciliation

## 23.1 Bank accounts

Support:

- account creation
- account listing
- account details
- role restrictions

## 23.2 Statement import

Import:

- date
- narration
- reference
- debit
- credit

Detect duplicates.

## 23.3 Auto-match

Match based on:

- amount
- reference
- date tolerance
- payment type where relevant

Statuses:

- unreconciled
- reconciled
- discrepancy

## 23.4 BRS

Report:

- book balance
- bank balance
- unreconciled items
- matched items
- discrepancy

Manual match/unmatch should be a target feature.

---

# 24. General Ledger

The accounting subsystem is double-entry.

Rules:

```text
sum(debits) == sum(credits)
```

for every journal entry.

Support:

- chart of accounts
- journal entries
- sales posting
- payment posting
- opening balance posting
- entity ledger
- branch dimension
- cost centre dimension
- drill-down

Reports:

- trial balance
- P&L
- balance sheet

Accounting invariants:

```text
Trial balance debits = credits
Assets = Liabilities + Equity
```

The native application must never delete posted financial history. Corrections should use reversal entries.

---

# 25. Sales Returns

Support:

- return against invoice
- optional original invoice
- item
- quantity
- rate
- refund amount
- waste/non-waste choice

Validation:

```text
returned quantity <= billed quantity
```

Effects must be explicit:

- stock returned to saleable stock, or
- stock treated as waste
- customer balance/credit note
- ledger reversal/credit

---

# 26. Miscellaneous Entries

Support:

- income
- expense
- category
- amount
- payment method
- bank account
- date
- notes

The entry must post to the ledger/cash session as appropriate.

---

# 27. Cash Sessions

Cashier session lifecycle:

```text
closed -> open -> closed
```

Opening cash is captured.

Expected cash:

```text
opening cash
+ cash sales
+ cash receipts
- cash payouts
```

Close captures:

- expected cash
- actual cash
- difference
- closing time
- cashier

Only one open session per user.

The business policy must define whether billing/payment is blocked when no session is open.

---

# 28. OCR and Smart Import

The existing product supports OCR for:

- image/slip
- manual upload
- email ingestion
- WhatsApp ingestion

Native desktop target:

- F8 opens Smart Importer
- select image/file
- run OCR
- extract candidate item lines
- fuzzy match against item master
- show confidence
- allow corrections
- create draft order/bill

OCR must fail gracefully if Tesseract is unavailable.

The UI must never silently turn an uncertain OCR result into a final financial transaction.

Human confirmation is required before financial posting.

Tamil/English input and existing translation/fuzzy matching behavior should be retained.

---

# 29. Dashboard and Analytics

Dashboard should be role-aware.

Metrics:

- today's sales
- monthly sales
- outstanding receivables
- overdue receivables
- payable amount
- stock value where available
- open orders
- low-stock/shortfall signals
- cash session status

Accountants may have view-only access to operational dashboards.

Heavy aggregates should be optimized or cached where required.

---

# 30. Settings

## Company

- company ID
- legal/company name
- registered address
- phone
- email
- GST
- terms
- signatory
- logo

## Invoice

- invoice format
- date format
- default commission
- default mandi fee
- print header
- default layout

## Notifications

Templates:

- order confirmation
- invoice
- delivery challan
- price expiry

Unknown placeholders must remain literal rather than crash rendering.

## Backup

Configure:

- schedule
- local destination
- GDrive/S3 where supported
- retention
- test backup
- restore

Secrets must never be displayed in plain text.

---

# 31. Backup and Restore

Backup is a P0 operational capability.

Requirements:

- manual backup
- scheduled backup
- local backup
- optional cloud backup
- retention
- backup validation
- restore workflow
- restore test procedure

A backup is not considered successful merely because a command exited successfully; the application should validate that a usable backup artifact exists.

Restore must have an explicit confirmation step.

---

# 32. Native UI Information Architecture

Main navigation:

```text
Dashboard

Sales
  New Bill
  Bill History
  Sales Returns

Orders
  New Order
  Orders
  Consolidated
  Order Matrix

Masters
  Items
  Customers
  Suppliers
  Fixed Pricing

Inventory
  Stock
  Stock Adjustments
  Waste
  Crates

Purchase
  Purchase Orders
  GRN
  Purchase Bills

Accounts
  Receivables
  Payables
  Payments
  Banking
  Reconciliation
  General Ledger

Reports
  Sales
  Inventory
  AR
  AP
  Trial Balance
  P&L
  Balance Sheet
  Statements

Administration
  Users
  Roles
  Company
  Settings
  Audit
  Backup

Tools
  Smart Importer
  Database Settings
```

Visibility is permission-driven.

---

# 33. UI/UX Requirements

## 33.1 Desktop-first

Target:

- Windows 10+
- 1366x768 minimum supported working layout
- 1920x1080 optimized

## 33.2 Keyboard-first

Billing should not require continuous mouse interaction.

## 33.3 Native feedback

Use:

- clear validation messages
- confirmation dialogs for destructive/financial actions
- progress indicators for long operations
- non-blocking background work where practical
- actionable MongoDB/printing/OCR errors

## 33.4 Tables

Use `ttk.Treeview` with:

- sortable columns where useful
- row selection
- keyboard navigation
- contextual actions
- paging for large datasets

---

# 34. Data Model

The native target should preserve the conceptual models already present in the repository:

- Item
- Customer
- Supplier
- User
- Company
- UserCustomerMapping
- UserActivityAudit
- BankAccount
- InternalBankTransaction
- BankStatement
- Bill
- Payment
- Role
- RolePermission
- BillAudit
- ManualInvoice
- SystemSettings
- Order
- StockTransaction
- WasteLog
- PurchaseBill
- APPayment
- LedgerTransaction
- Account
- JournalEntry
- PurchaseOrder
- GRN
- PrintLayout
- FixedPrice
- CrateTransaction
- SalesReturn
- MiscellaneousEntry
- Session
- WebSession compatibility data where migration requires it

The native implementation may introduce additional fields for:

- idempotency
- reversal references
- migration state
- native session metadata
- desktop installation metadata

Such changes require a migration decision.

---

# 35. Migration Strategy

## 35.1 Principle

Do not destroy the existing `sv_billing` database.

The migration should be additive and reversible where possible.

## 35.2 Compatibility

Phase 1:

- read existing users
- read existing roles
- read existing items
- read existing customers
- read existing suppliers
- read existing fixed pricing
- read existing bills
- read existing stock
- read existing accounting data

Phase 2:

- native application writes new transactions using compatible schemas.

Phase 3:

- backfill missing indexes and consistency data.

Phase 4:

- reconcile stock, customer balances, AR/AP, and GL.

## 35.3 Data migration checks

Before production cutover:

- item counts match
- customer counts match
- supplier counts match
- bill counts match
- open AR matches
- open AP matches
- stock balances reconcile
- crate balances reconcile
- trial balance balances
- backup/restore succeeds

---

# 36. Native-Specific Security Risks

Direct MongoDB access from a desktop application creates a different threat model from the existing API architecture.

For remote MongoDB:

1. Use least-privilege database credentials.
2. Use TLS.
3. Restrict Atlas IP access where practical.
4. Do not embed an administrator credential.
5. Do not store credentials in source code.
6. Protect local configuration.
7. Consider OS credential storage for secrets.
8. Log connection failures without secrets.

A desktop application cannot provide the same secret isolation as a server-side API. This is an explicit architecture trade-off.

---

# 37. Reliability Requirements

P0 financial operations must be all-or-nothing wherever MongoDB transactions are available.

Required transactional workflows:

- bill
- customer payment
- supplier payment
- GRN
- purchase bill
- sales return
- journal posting
- reconciliation state changes

For standalone MongoDB deployments that cannot support multi-document transactions, the product must either:

1. require a replica-set configuration for production use; or
2. use a carefully designed recovery/outbox/reconciliation strategy.

Production guidance should prefer MongoDB replica set / Atlas.

---

# 38. Performance Requirements

Targets:

| Operation | Target |
|---|---|
| Application startup | < 3 seconds after DB connection |
| Item alias lookup | < 100 ms typical |
| Customer search | < 200 ms typical |
| Save bill | < 1 sec p95 for <= 50 lines |
| Bill history page | < 500 ms typical |
| Dashboard | < 2 sec typical |
| PDF invoice | < 2 sec typical for normal bill |
| OCR | Progress-based; no UI freeze |

Long-running operations must run outside the Tkinter event loop.

---

# 39. Observability

The native app should maintain:

- local application log
- startup log
- database connection diagnostics
- exception traceback
- audit log
- operation timing where useful

The user-facing UI must show a friendly error while the log contains technical detail.

Example:

```text
Unable to connect to MongoDB.

Check:
- MongoDB is running
- host/port
- credentials
- network access

[Retry] [Database Settings]
```

---

# 40. Testing Strategy

This section follows the Matt Pocock specification approach: test behavior at the highest useful seam and avoid coupling tests to implementation details.

## 40.1 Primary seam

The primary seam is the application service layer.

Example:

```text
BillingService.create_bill(...)
```

A good test verifies:

- invoice created
- correct total
- stock changed
- customer balance changed
- audit created
- correct status

It should not verify which helper method was called internally.

## 40.2 Repository tests

Use integration tests against a disposable MongoDB/replica set where transaction behavior is tested.

Test:

- indexes
- queries
- unique constraints
- transaction behavior
- aggregation correctness

## 40.3 UI tests

Keep UI tests small.

Test:

- application launches
- login works
- dashboard appears
- billing form opens
- keyboard shortcuts work
- a representative bill can be entered
- connection error is shown

Do not make every business rule a Tkinter test.

## 40.4 Financial invariant tests

P0:

- debits = credits
- invoice numbers unique
- stock reconciliation
- customer balance reconciliation
- payment allocations do not exceed invoice balance
- payment allocations do not exceed payment amount
- no duplicate financial posting
- returns cannot exceed billed quantity

## 40.5 Security tests

Test:

- inactive users cannot log in
- deleted users cannot log in
- unauthorized actions are rejected
- role restrictions are enforced at service level
- secrets are not logged
- passwords are never returned
- unsafe MongoDB operators are not accepted as user filters

---

# 41. Acceptance Criteria

The native product is ready for production pilot when all P0 criteria pass.

## P0 acceptance

1. App launches without browser or web server.
2. MongoDB local connection works.
3. MongoDB Atlas connection works.
4. Existing `sv_billing` data can be read.
5. User can log in.
6. Role restrictions work.
7. Customer can be selected.
8. Item can be entered by alias.
9. Bill can be saved.
10. Invoice number is unique.
11. Stock is updated correctly.
12. Customer balance is updated correctly.
13. Audit record is created.
14. Invoice PDF is generated.
15. Bill history shows the bill.
16. Payment can be recorded.
17. AR balance updates correctly.
18. Supplier purchase can update stock.
19. Journal entries remain balanced.
20. Trial balance balances.
21. Backup succeeds.
22. Restore has been tested.
23. Application does not expose secrets in logs.
24. Existing database indexes do not cause startup failures.
25. Application reports MongoDB failures instead of silently exiting.

---

# 42. Known Existing-Code Gaps to Carry into Native Rewrite

The supplied repository identifies or suggests the following gaps. These should not be blindly copied into the native implementation.

## Security

- login rate limiting/lockout
- complete endpoint authorization coverage becomes service-level authorization
- plaintext password concept must be removed
- secret masking
- seed/debug functionality must be development-only
- session invalidation policy

## Financial integrity

- bill void reversal
- payment idempotency
- sales return quantity validation
- return credit/ledger behavior
- bill-to-GL consistency
- period close/lock
- reversal journals instead of deletion

## Inventory

- atomic stock updates
- stock reconciliation
- concurrent update safety

## Procurement

- three-way match
- over-receipt tolerance
- purchase returns

## Banking

- duplicate statement detection
- manual match/unmatch
- partial-match tolerance

## Operations

- restore testing
- backup validation
- cash-session policy
- Z report

These should be treated as requirements for the native target, not as reasons to reproduce known defects.

---

# 43. Implementation Phases

## Phase 0 — Foundation

Deliver:

- Python package structure
- Tkinter shell
- configuration
- logging
- MongoDB connection
- index reconciliation
- startup error handling
- application lifecycle

Exit criteria:

- app starts
- connection can be tested
- failures are visible
- no web dependencies

## Phase 1 — Identity and Masters

Deliver:

- login
- RBAC
- users
- roles
- company
- items
- customers
- suppliers
- fixed pricing

## Phase 2 — Core Billing

Deliver:

- new bill
- bill history
- numbering
- stock
- customer balance
- audit
- invoice printing
- payments

This is the first pilot-ready milestone.

## Phase 3 — Orders and Inventory

Deliver:

- orders
- conversion to bill
- order matrix
- consolidated report
- stock adjustment
- waste
- crates

## Phase 4 — Procurement

Deliver:

- purchase orders
- GRN
- purchase bills
- supplier payments
- TDS

## Phase 5 — Finance

Deliver:

- AR
- AP
- banking
- reconciliation
- ledger
- trial balance
- P&L
- balance sheet

## Phase 6 — Intelligence and Operations

Deliver:

- OCR
- Smart Importer
- email/WhatsApp ingestion where technically appropriate
- notifications
- advanced reports
- backup/restore
- print editor

## Phase 7 — Production Hardening

Deliver:

- installer
- upgrade strategy
- migration tooling
- backup verification
- crash recovery
- performance testing
- security review
- production documentation

---

# 44. Definition of Done

A native feature is complete when:

1. Its business rules are documented.
2. Its service-level behavior is implemented.
3. Its MongoDB persistence is tested.
4. Authorization is enforced.
5. Financial mutations are auditable.
6. Errors are user-readable.
7. Relevant keyboard behavior is implemented.
8. Relevant print/report output is tested.
9. Existing data compatibility is considered.
10. P0 invariants have tests.
11. No web/API dependency has been introduced.
12. The feature is included in the native navigation and permissions model.

---

# 45. Further Notes and Architectural Decisions

## ADR-like decision: native UI

**Decision:** Tkinter/ttk.

**Reason:** The user explicitly requires Python forms and a non-browser desktop application. Tkinter is included with Python and avoids a large external UI runtime.

## ADR-like decision: direct MongoDB

**Decision:** PyMongo from the application.

**Reason:** No API server is desired. The desktop process owns the application logic and directly persists data.

**Trade-off:** Remote MongoDB credentials are necessarily available to the desktop application. Least privilege and TLS are mandatory.

## ADR-like decision: services as primary seam

**Decision:** Business logic lives in application services rather than Tkinter callbacks.

**Reason:** This keeps the UI thin, makes business behavior testable, and prevents the native rewrite from becoming a monolithic GUI.

## ADR-like decision: preserve MongoDB concepts

**Decision:** Preserve existing collections and field semantics wherever practical.

**Reason:** The supplied project already contains meaningful operational history and a developed domain model. Reusing it lowers migration risk.

## ADR-like decision: no API compatibility layer in the desktop runtime

**Decision:** Do not embed FastAPI as a hidden local server.

**Reason:** That would recreate the architecture the native rewrite is intended to remove.

---

# 46. Native MVP Screen Inventory

### Authentication

- Login

### Core

- Dashboard
- New Bill
- Bill History
- Bill Detail

### Masters

- Items
- Customers
- Suppliers
- Fixed Pricing

### Operations

- Orders
- Inventory
- Purchase
- Payments

### Finance

- AR
- AP
- Banking
- Reconciliation
- Ledger
- Trial Balance
- P&L
- Balance Sheet

### Administration

- Users
- Roles
- Company
- Settings
- Audit
- Backup
- Database Connection

### Tools

- Smart Importer
- Print Layouts

---

# 47. Suggested Initial Ticket Sequence

1. Native application bootstrap and logging
2. MongoDB configuration and connection diagnostics
3. Safe index initialization
4. Authentication service
5. RBAC service
6. Main window/navigation shell
7. Item master
8. Customer master
9. Supplier master
10. Fixed pricing
11. Billing domain/service
12. Billing form
13. Invoice numbering
14. Stock transaction service
15. Customer balance service
16. Audit service
17. Invoice PDF
18. Bill history
19. Customer payment/AR
20. Integration tests for end-to-end billing
21. Existing database reconciliation
22. Orders
23. Procurement
24. Accounting
25. Reports
26. OCR
27. Backup/restore
28. Installer and production hardening

---

# 48. Final Product Principle

The native BillDesk should not be understood as:

> "A Tkinter version of the website."

It should be understood as:

> **The same BillDesk business system, with a native desktop application boundary replacing the web/API boundary.**

The UI is replaceable.

The business rules are the product.

The MongoDB data is long-lived business state.

The service layer is the seam that keeps those concerns independent.

That is the architecture this PRD specifies.
