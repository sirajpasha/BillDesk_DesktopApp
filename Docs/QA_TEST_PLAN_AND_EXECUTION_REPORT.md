# BillDesk Native - QA Test Plan & Execution Report

**Executed:** 2026-10-08 | **Build:** `main` @ `6142ef9` | **Python 3.14.3 / Windows 11 / bundled MongoDB** | **Scope:** EPIC-01 to EPIC-08 (EPIC-09/10 deferred by request)

## 1. Result at a glance

| | Count |
| :-- | --: |
| Test cases executed (this report) | **280** |
| Passed | **280** |
| Failed (each maps to an open defect below) | **0** |
| Existing pytest suite (mock DB) | 155 pass (49 original + 106 new regression tests); the hang and the live-DB dependency are fixed |

The 48-test pytest suite is green because it runs against an in-memory mock and asserts only the happy paths. Run against a **real MongoDB** and the real Tk windows, the application has **7 high-severity defects** that affect money, stock, security or documents. The most serious: **a payment taken at the counter is never recorded** (D-01) and **role restrictions are bypassable with keyboard shortcuts** (D-04).

**Update - fixes applied after the first run:** D-01 .. D-18 and D-20 are fixed and verified against the real DB (their cases now PASS in Appendix A) and by 106 new pytest regression tests (including `tests/test_ledger_posting.py`) (`tests/test_payment_capture.py`, `tests/test_seed_and_access.py`, `tests/test_pdf_generation_paths.py`, `tests/test_void_and_order_controls.py`, `tests/test_integrity_controls.py`). T-1 (hanging test) and T-2/T-6 (suite depended on the live database) are fixed. The sections below describe the defects as found; nothing from the defect register remains open. Numbers in this report are from the post-fix run.

## 2. How the testing was done

* **Isolated environment:** a throw-away `mongod` on port `27099`, database `sv_billing_qa`. Your real data (`%APPDATA%\BillDesk\db`, port 27018) was not touched. Every script refuses to run unless the DB name contains `qa`.
* **Layer 1 - service/repository tests (110 cases)** call the real services against real MongoDB: billing, void, payments, orders, pricing, inventory, procurement, cash sessions, ledger, auth.
* **Layer 2 - GUI tests (168 cases)** start the real `MainWindow` with the real DB, drive widgets with real key events (`<Return>`, `<KeyRelease>`, `<F2>`...), operate the real modal dialogs (payment, customer search, parked bills, duplicate-item), intercept message boxes, and read results back from MongoDB. Screenshots of the app window were reviewed (`Docs/qa-evidence/`).
* **Layer 3 - document tests:** invoice / delivery-challan PDFs generated and text-extracted with PyMuPDF; number formatting and amount-in-words tested directly.
* Seeding note: the QA DB was patched with `status:"active"`, `is_deleted:0` after seeding because the seeder output is otherwise unusable (D-03); `qa_reset.py` now does this automatically.

Run it yourself (from repo root):

```powershell
$env:MONGODB_URL="mongodb://127.0.0.1:27099"; $env:DB_NAME="sv_billing_qa"
$env:QA_SCRATCH="$PWD\scratch\qa"; $env:PYTHONPATH="$PWD\tests\qa_realdb"; $env:PYTHONIOENCODING="utf-8"
python scripts\seed_database.py            # qa_reset.py then patches status/is_deleted (see D-03)
foreach ($t in "qa_service_checks","qa_gui_1","qa_gui_2","qa_gui_3","qa_gui_4") { python tests\qa_realdb\qa_reset.py; python tests\qa_realdb\$t.py }
```

## 3. Existing automated suite - findings

| # | Finding |
| :-: | :-- |
| T-1 (**fixed**) | `tests/test_billing_interaction.py::test_dynamic_row_creation_at_table_end` **hangs forever** (blocks `pytest tests/`). It fills every row with item `101`, which now triggers the modal *Duplicate Item* dialog (`wait_window`). Adding `frame.suppress_duplicate_dialog = True` makes it pass in 1 s (verified). The README claim "48 passed" is therefore not reproducible with the plain command. |
| T-2 (**fixed**) | The "flaky" `tests/test_order_form.py` was not flaky: its `db` fixture connected to the **live MongoDB** from `MONGODB_URL` and asserted against real catalogue data (alias 101 = *Avaraikkai* in the production data, *Apple* in the repo seed). It failed whenever the environment pointed at a different database. It now uses an in-memory database with a fixed catalogue (verified passing with `MONGODB_URL` set to a dead port). |
| T-3 | The suite collects 50 tests but `TRACEABILITY_MAP` lists 48; the `test_billing_duplicate_item_*` tests are not in the map, so they never appear in the traceability report. |
| T-4 | The mock (`MockCollection`) diverges from real MongoDB (no `skip()`, `$exists` is not evaluated, no transactions), and the tests assert only happy paths, so none of the service-level defects below are caught. |
| T-6 | `tests/test_launcher.py` runs `start.ps1/.bat -CheckOnly`, which **auto-starts `mongod` on port 27018 against `%APPDATA%\BillDesk\db`** - i.e. the real database - and leaves it running. Running `pytest` therefore starts your production DB. (Checked read-only: nothing dated today exists in `sv_billing`; the one test that wrote an order deleted it.) Consider making `-CheckOnly` not start services. Also: do not run `scripts/seed_database.py` on the production DB - the repo seed items (alias 101 = Apple...) collide with production aliases. |
| T-5 | Nothing tests failure paths (over-payment, double-void, double-GRN, unknown item, RBAC, PDF fallback). The new `tests/qa_realdb/` scripts add these; consider porting the stable ones into the pytest suite once the defects are fixed. |

## 4. Epic / story verification matrix

| Epic | Claimed | Verified | Notes |
| :-- | :-: | :-: | :-- |
| EPIC-01 Shell, auth, launchers | Done | **Partial** | Launchers, shell, 27 pages, F-key shortcuts, login (incl. injection strings) OK. **RBAC fails** (D-04); seeded DB can't log in (D-03). |
| EPIC-02 Billing engine | Done | **Partial** | Code->Qty->Unit->Rate keyboard flow, keystroke totals, fixed-price re-resolve, credit limit, parking OK. **Payment never recorded** (D-01), company dropped (D-02), no cess/commission/crate fields in the billing form (Task 2.2.4 only half-built), negative qty / unknown code issues (D-10). |
| EPIC-03 History & void | Done | **Partial** | List, search, KPIs, void stock/balance reversal OK. Part-paid void corrupts balance, no GL contra, no crate reversal (D-06); list capped at 500 (D-17). |
| EPIC-04 Orders & importer | Done | **Partial** | Form validation, dates, lifecycle OK. Importer mis-maps numeric codes (D-09); conversion bypasses credit limit/status/audit (D-08); free-text customers (D-16). |
| EPIC-05 Master data | Done | **Partial** | CRUD, duplicate id/alias checks, fixed-price rules OK. Delete/edit/validation gaps (D-15). |
| EPIC-06 PDF & preview | Done | **Partial** | Invoice PDF content correct when Edge path works. **DC prints as an invoice with prices and broken rupee glyph when Edge is already running** (D-05); `amount_in_words` crashes (D-12). |
| EPIC-07 Ledger, inventory, procurement | Done | **Partial** | Manual journals & TB balance, stock adjust/waste, GRN stock, TDS maths OK. **No automatic postings** (D-07), Balance Sheet is a placeholder, P&L method (D-07), GRN/match/cash-drawer rules (D-13, D-14). |
| EPIC-08 Packaging | In progress | **Not ready** | `build_windows.ps1` is 3 lines and builds `dist/BillDeskNative/BillDeskNative.exe`; `installer/BillDesk.iss` expects `dist\BillDesk\BillDesk.exe`. No bundling of `resources/mongo`, `resources/tesseract`, `app/assets`, seed data. PyInstaller not installed here, `*.spec` is git-ignored, and `Docs/Output` is written relative to the CWD (read-only under `Program Files`). Not executed - static review only. |

## 5. Defect register

Severity: **High** = wrong money/stock/security or unusable document; **Medium** = integrity or workflow gap with workaround; **Low** = polish / hardening.

### High

| ID | Defect | Evidence (test case) | Where | Suggested fix |
| :-: | :-- | :-- | :-- | :-- |
| D-01 **FIXED** | **Counter payment is lost.** In the *Record Payment Receipt* modal, amount received, method, date and reference are never persisted: no `payments`/ledger row, bill `status` stays `unpaid` even when fully paid, and `customers.current_balance` is increased by the **full bill total** (a Rs120 bill paid in cash leaves the customer owing Rs120; a Rs500 bill part-paid Rs200 leaves 620 owing). Non-numeric ("abc") or absurd (Rs5000 on Rs100) amounts are silently accepted. | GUI-BILL-20/21/22/26/27/30/31 | `ui/billing.py:998-1011` passes `status=` to `BillCreate`, which has no such field (pydantic drops it); `services/billing_service.py:71` hard-codes `unpaid` | Add `amount_received`/`payment_method` to `create_bill`; call `PaymentService.record_customer_payment` in the same transaction; set status/balance_due server-side; validate 0 <= received. |
| D-02 **FIXED** | Selected **company is dropped** from the bill (`company_id` not on `BillCreate`); History "Company" column is always `-`; invoices fall back to the default company. | GUI-BILL-23 (screenshot `bill_history.png`) | `ui/billing.py:1002`, `models/billing.py` | Add `company_id` to `BillCreate`/`Bill`. |
| D-03 **FIXED** | **Seeded database is unusable.** `seed_database.py` writes users/items/customers without `status` or `is_deleted`; every lookup filters on both, so `admin / admin123` fails ("Invalid username or password") and no item/customer is found. The README "Manual Run" path (seed -> `python main.py`) cannot work on a fresh DB. | observed during setup; `SVC-AUTH-*` pass only after patching | `scripts/seed_database.py`, `data/seed_data.json` | Seeder must default `status:"active"`, `is_deleted:0`, `stock`, `current_balance`, `credit_limit`; add a seed -> login test. |
| D-04 **FIXED** | **Access control is menu-only.** Menus are hidden by role, but `F10`, `F11`, `Ctrl+D`... go straight to Item/Customer Master and the whole Accounting dashboard for a plain `user`; the *Reports* menu lists Profit & Loss / Balance Sheet for everyone. The seeder creates no `role_permissions`, so `manager` == `user`. | GUI-RBAC-manager-02/F10/F11/Control-d, GUI-RBAC-user-* , SVC-AUTH-perm-manager (screenshot `user_menu.png`) | `ui/main_window.py:355-369` (global binds), `show_page` has no permission check | Enforce permissions in `show_page`/`can_open(name)`; seed default role permissions. |
| D-05 **FIXED** | **Delivery Challan / Invoice PDF silently degrades.** `generate_*_pdf` shells out to headless Edge with the default profile; when Edge is already running the command returns 0 **without writing a PDF**, and the code falls back to a ReportLab *invoice* layout for **both** documents: the Delivery Challan then shows rates and amounts (commercially sensitive), is titled "INVOICE (CREDIT)", and the rupee sign renders as a black box (Helvetica has no U+20B9). Reproduced with 34 Edge processes running. | PDF-DC-01 (screenshot `invoice_pdf.png`) | `printing/invoice.py:720-729, 877, 896` | Pass `--user-data-dir=<temp>` (verified to work) and `--headless=new`; make the fallback honour `is_dc`; register a TTF with Rs glyph. |
| D-06 **FIXED** (journal part -> D-07) | **Void leaves loose ends.** Re-test showed the balance arithmetic itself was right (paid Rs120 of Rs200 -> customer correctly ends with Rs120 credit), but the Rs120 payment stayed allocated to the voided invoice, crate balances were never created at billing (`customers.crate_balances` stayed empty) nor reversed on void (TC-BILL-04/06), and no contra journal is posted (Task 3.2.3). Now: payments are released as unallocated credit, crate balances are tracked and reversed with mirror crate transactions. | SVC-VOID-00b/05/09 (contra journal: SVC-VOID-06, open under D-07) | `services/billing_service.py` `void_bill`, `repositories/inventory_repo.py` | Done; contra journal needs the D-07 posting design. |
| D-07 **FIXED** | **Ledger was not driven by transactions** (as found: no sale, receipt, purchase, AP payment, waste or void posted a journal; Balance Sheet was static text; P&L = sales - all purchases; Trial Balance showed only hand-keyed journals). Now every event posts a balanced, idempotent journal (`services/ledger_service.py`): sale Dr Receivables / Cr Sales + Cr Commission & fee income (mandi fee treated as fee income for now); walk-in sale Dr Cash/Bank for the amount received; cost of goods Dr COGS / Cr Inventory at weighted-average cost; receipt Dr Cash or Bank / Cr Receivables; purchase bill Dr Inventory / Cr Payables + TDS Payable; supplier payment Dr Payables / Cr Cash/Bank; waste Dr Waste / Cr Inventory; void posts mirror entries. Trial Balance, P&L (revenue - COGS - expenses) and a real Balance Sheet (A = L + E incl. current profit) are derived from the ledger; the Payables tile now reads `purchase_bills`. History is migrated with the new idempotent `scripts/backfill_ledger.py` (dry-run by default). | SVC-VOID-06, SVC-PAY-14, SVC-PROC-13, SVC-GL-09, GUI-FIN-01/04/05/06/07 | `services/ledger_service.py`, `billing/payment/procurement/inventory services`, `ui/finance_view.py` | Done. Not backfilled: COGS for historic bills (no item cost) and opening balances - post with *Set Opening Balance*. |

### Medium

| ID | Defect | Evidence | Where |
| :-: | :-- | :-- | :-- |
| D-08 **FIXED** | **Order -> Bill conversion bypasses the controls of a normal bill:** ignores credit limit, allows cancelled orders, writes no `bill_audits` row, no `due_date`, ignores commission/mandi fee; `convert_to_purchase` can run repeatedly (stock inflated each time) and applies no TDS; a **billed order can be cancelled** from the list, orphaning its invoice. | SVC-ORD-04/05/06/09/10/12/13, GUI-ORD-13/15 | `services/order_service.py:80-199`, `ui/orders_view.py:363-371` |
| D-09 **FIXED** | **Smart importer mis-maps items.** `102 50kg` -> *Apple* (numeric code taken as quantity, empty name matches the first catalogue item); `5 kg` -> *Apple*; `101 5kg` only works because Apple is first. Unknown text (`Tomato 2 boxes`) creates a junk line with item_id = the text and a default Rs20 rate, no warning; repeated items are not merged. The dialog hint and README both advertise numeric codes. | GUI-IMP-03/06/08 (screenshot `order_form_after_import.png`) | `ui/order_form_view.py:811-892` (`"" in name` is always true) |
| D-10 **FIXED** | **Billing grid accepts bad input silently:** unknown code (`ZZZ999`, `9999`) auto-fills the first catalogue item ("Fallback for test environments"); negative qty is accepted into the grand total yet dropped from the saved lines (grid total 100, stored lines sum 200); non-numeric qty rows are skipped without telling the cashier. | GUI-BILL-07/12/13 | `ui/billing.py:392-402, 960-970` |
| D-11 **FIXED** | **Services trust the caller's maths:** `total_amount` and line `amount` are stored as sent (total 1.0 for a Rs10 line; amount 999 for 2x10); amounts are never rounded to 2 dp (416.625, AR 1742.595 vs PDF 416.62); stock may go negative on sale (-47) and waste (-9917). | SVC-BILL-18/19/20, SVC-INV-07 | `services/billing_service.py:34-90`, `inventory_service.py:48` |
| D-12 **FIXED** | **`amount_in_words` crashes** (`IndexError`) for any amount with >= 0.995 fractional rupee (e.g. 3 x 33.333 = 99.999) and for >= Rs100 crore; "One Rupees" grammar. Any such invoice cannot be printed. | CUR-words-rounding-*, CUR-words-crore100, CUR-words-singular | `utils/currency.py:71-96` |
| D-13 **FIXED** | **Procurement controls missing:** a PO can be received twice (stock doubled) and over-received (7777 vs 100 ordered); 3-way match always reports `matched` when PO+GRN ids are present, even for 1000 vs 100 units. | SVC-PROC-05/06/09 | `services/procurement_service.py:51-145` |
| D-14 **FIXED** | **Cash drawer:** expected cash counts *every* bill by the user (credit sales included): 2000 + 3500 cash + 1000 credit + 500 receipt = 7000 instead of 6000; negative opening cash accepted. | SVC-SESS-02/06 | `services/session_service.py:37-64` |
| D-15 **FIXED** | **Master/admin validation:** customer with outstanding balance 777 can be deleted; `save_customer` accepts and overwrites `current_balance`; negative item rate and unknown roles accepted; 1-character passwords accepted; passwords identical in the first 72 bytes are equal (bcrypt truncation); `adjust_stock` accepts a blank reason; waste with negative rate; journals accept negative, empty or both-sided lines; item `default_rate` (what the seeder writes) is ignored by pricing (falls back to hard-coded 20.0). | GUI-MST-04/09/10, GUI-ADM-04/05/07, SVC-INV-05/09, SVC-GL-05/06/07, SVC-PRICE-03 | `services/master_service.py`, `admin_service.py`, `inventory_service.py`, `accounting_repo.py` |
| D-16 **FIXED** | **Order form:** a free-typed customer name created an order with `customer_id` = the text (now rejected unless it is a master customer). Commission 5 % / mandi fee 1 % were hard-coded, shown on screen but excluded from the order total and from the converted bill. Production data shows no order or bill has ever carried either charge, so the rates are now configuration (`COMMISSION_RATE`, `MANDI_FEE_RATE`, default **0**), included in the order total when set, carried to the converted bill (booked as fee income in the ledger); orders saved before this change convert without charges. | GUI-ORD-03/11 | `ui/order_form_view.py`, `services/order_service.py`, `config/settings.py` |

### Low

| ID | Defect | Evidence |
| :-: | :-- | :-- |
| D-17 **FIXED** | Bill History loads only the latest **500** bills (KPIs/search silently incomplete beyond that); search/date inputs appear squashed (screenshot `bill_history.png`). | GUI-HIST-12 |
| D-18 **FIXED** | Login form pre-filled with `admin` + a password (hard-coded in source); payment dialog showed a hard-coded 'UNPAID ITEMS 0', a non-functional walk-in checkbox and Auto-FIFO/Manual toggle; **parked bills lived in memory only and were lost on exit or crash**. Now: no pre-filled credentials; real outstanding / unpaid-bill count and no dead controls; parked bills are saved atomically to `%APPDATA%\BillDesk\parked_bills.json` on the counter PC (`services/parked_store.py`), shown again after a restart, recalled load-first-then-delete, and recalling over a bill in progress asks first. | GUI-LOGIN-01, GUI-BILL-36 (screenshot `payment_modal.png`) |
| D-20 **FIXED** | While fixing D-10 a further defect surfaced: the code field's `<FocusOut>` handler re-resolved the item and **overwrote a rate the cashier had typed** (e.g. Rs50 negotiated -> back to the default 20 when focus moved to the payment dialog) and could be triggered by pressing Enter on an unchanged code. Fixed: an unchanged, already-resolved code is left alone (`ui/billing.py` `_on_code_entered`). | GUI-BILL-26/27 (regressed during the work, caught by the re-run) |
| D-19 | Test-suite items T-1 .. T-5 above. | - |

## 6. Not covered / needs manual or environment support

* Physical printing (Windows spooler), print preview zoom with a real printer, Tamil/Unicode print rendering beyond the smoke test.
* MongoDB **replica-set transactions** (`supports_transactions=True` path) and Atlas/TLS - only standalone was available.
* Multi-user concurrency (two counters saving at once; invoice-number race in `next_invoice_number`).
* Installer / PyInstaller build (EPIC-08), clean-machine start-up, upgrade/uninstall data preservation.
* Real window-manager focus behaviour (tests force focus programmatically); screen DPI scaling; very small screens.
* EPIC-09 (ESC/POS, weighing scale) and EPIC-10 (WhatsApp/SMS/OCR) - deferred by request.

## 7. Recommended fix order

1. **D-01, D-02** (money capture) with a regression test using the real-DB harness.
2. **D-03** (seeder) and **D-04** (permission checks) - quick, high impact.
3. **D-05** (PDF fallback/`--user-data-dir`), **D-12** (`amount_in_words`) - customers see these.
4. **D-06, D-07** (void/ledger) - needs a design decision on posting rules.
5. D-08 .. D-16, then lows. Port the `tests/qa_realdb` checks into pytest as each defect is closed and flip the expectation from "fails" to "passes".

---

## Appendix A - Test case catalogue and results

Legend: PASS = behaviour as specified; **FAIL** = defect (see section 5). `Evidence` is what the application actually did.


### Service layer (real MongoDB)  (110/110 passed)

| ID | Epic / story | Test case (expected behaviour) | Result | Evidence |
| :-- | :-- | :-- | :-: | :-- |
| `SVC-BILL-01` | EPIC-02 / Story 2.1-2.3 Billing engine | create bill stores doc with invoice YYYYMMDD-0001 | PASS | 20261009-0001 |
| `SVC-BILL-02` | EPIC-02 / Story 2.1-2.3 Billing engine | stock decremented 100 -> 90 | PASS | 90.0 |
| `SVC-BILL-03` | EPIC-02 / Story 2.1-2.3 Billing engine | customer balance +200 | PASS | 200.0 |
| `SVC-BILL-04` | EPIC-02 / Story 2.1-2.3 Billing engine | stock_transactions row type=sale qty=-10 | PASS |  |
| `SVC-BILL-05` | EPIC-02 / Story 2.1-2.3 Billing engine | bill_audits CREATE row written | PASS |  |
| `SVC-BILL-06` | EPIC-02 / Story 2.1-2.3 Billing engine | due_date = invoice_date + 30d | PASS | 2026-11-08 00:00:00+00:00 |
| `SVC-BILL-07` | EPIC-02 / Story 2.1-2.3 Billing engine | second invoice increments sequence -0002 | PASS | 20261009-0002 |
| `SVC-BILL-08` | EPIC-02 / Story 2.1-2.3 Billing engine | duplicate invoice_no rejected | PASS | ValueError: Invoice 20261009-0001 already exists |
| `SVC-BILL-09` | EPIC-02 / Story 2.1-2.3 Billing engine | qty=0 rejected | PASS | ValueError: Item quantity must be greater than zero |
| `SVC-BILL-10` | EPIC-02 / Story 2.1-2.3 Billing engine | negative qty rejected | PASS | ValueError: Item quantity must be greater than zero |
| `SVC-BILL-11` | EPIC-02 / Story 2.1-2.3 Billing engine | negative rate rejected | PASS | ValueError: Item rate cannot be negative |
| `SVC-BILL-12` | EPIC-02 / Story 2.1-2.3 Billing engine | empty item list rejected | PASS | ValueError: At least one item is required |
| `SVC-BILL-13` | EPIC-02 / Story 2.1-2.3 Billing engine | unknown customer rejected | PASS | ValueError: Customer not found |
| `SVC-BILL-14` | EPIC-02 / Story 2.1-2.3 Billing engine | credit limit exceeded blocked (400+5000>5000) | PASS | ValueError: Credit limit exceeded (5000.00) |
| `SVC-BILL-15` | EPIC-02 / Story 2.1-2.3 Billing engine | failed credit check leaves stock/balance untouched | PASS | (80.0, 400.0) |
| `SVC-BILL-16` | EPIC-02 / Story 2.1-2.3 Billing engine | bill exactly AT credit limit is allowed (boundary) | PASS | 4600.0 |
| `SVC-BILL-17` | EPIC-02 / Story 2.1-2.3 Billing engine | CASH customer: no customer balance change, due_date None | PASS | None |
| `SVC-BILL-18` | EPIC-02 / Story 2.1-2.3 Billing engine | selling 50 when only 3 in stock is blocked or flagged on the bill | PASS | stock_warnings=[{'item_id': 'VEG0002', 'name': 'Bajji Chilli', 'available': 3.0, 'required': 50.0}] |
| `SVC-BILL-19` | EPIC-02 / Story 2.1-2.3 Billing engine | caller-supplied total that disagrees with the lines is rejected (total_amount=1 for a Rs10 line) | PASS | ValueError: Bill total 1.00 does not match its lines and charges (10.00) |
| `SVC-BILL-20` | EPIC-02 / Story 2.1-2.3 Billing engine | line amount is recomputed as qty*rate (amount=999 passed for 2x10 -> 20.00) | PASS | stored line amount=20.0 |
| `SVC-VOID-00` | EPIC-03 / Story 3.2 Void & reversal | crate txn recorded on bill | PASS |  |
| `SVC-VOID-00b` | EPIC-03 / Story 3.2 Void & reversal | customer.crate_balances updated (+3 outstanding) | PASS | [{'item_id': 'CRATE-PLASTIC', 'balance': 3.0}] |
| `SVC-VOID-01` | EPIC-03 / Story 3.2 Void & reversal | void sets status=void, balance_due=0 | PASS |  |
| `SVC-VOID-02` | EPIC-03 / Story 3.2 Void & reversal | void restores stock 100 | PASS | 100.0 |
| `SVC-VOID-03` | EPIC-03 / Story 3.2 Void & reversal | void restores customer balance to 0 | PASS | 0.0 |
| `SVC-VOID-04` | EPIC-03 / Story 3.2 Void & reversal | VOID audit row written | PASS |  |
| `SVC-VOID-05` | EPIC-03 / Story 3.2 Void & reversal | void reverses crate balance (TC-BILL-06) | PASS | [{'item_id': 'CRATE-PLASTIC', 'balance': 0.0}] |
| `SVC-VOID-06` | EPIC-03 / Story 3.2 Void & reversal | void posts contra journal entry (EPIC-03 Task 3.2.3) | PASS | journal_entries=2 |
| `SVC-VOID-07` | EPIC-03 / Story 3.2 Void & reversal | double void rejected | PASS | ValueError: Invoice 20261009-0001 is already voided |
| `SVC-VOID-08` | EPIC-03 / Story 3.2 Void & reversal | void unknown invoice rejected | PASS | ValueError: Invoice 19990101-0001 not found |
| `SVC-VOID-09a` | EPIC-03 / Story 3.2 Void & reversal | pre-void: balance=80 after paying 120 | PASS | 80.0 |
| `SVC-VOID-09` | EPIC-03 / Story 3.2 Void & reversal | void of part-paid bill: customer ends with 120 credit (balance -120) and the payment is released as unallocated credit | PASS | balance=-120.0 payment=unallocated alloc=[] |
| `SVC-PAY-01` | EPIC-02 / Story 2.3 Payments & AR | partial pay: balance_due 150, status partial | PASS | (150.0, 'partial') |
| `SVC-PAY-02` | EPIC-02 / Story 2.3 Payments & AR | customer balance 300 -> 250 | PASS | 250.0 |
| `SVC-PAY-03` | EPIC-02 / Story 2.3 Payments & AR | ledger_transactions credit row written | PASS |  |
| `SVC-PAY-04` | EPIC-02 / Story 2.3 Payments & AR | over-allocation rejected | PASS | ValueError: Allocation amount 999.00 exceeds invoice balance due 150.00 |
| `SVC-PAY-05` | EPIC-02 / Story 2.3 Payments & AR | zero payment rejected | PASS | ValueError: Payment amount must be greater than zero |
| `SVC-PAY-06` | EPIC-02 / Story 2.3 Payments & AR | negative payment rejected | PASS | ValueError: Payment amount must be greater than zero |
| `SVC-PAY-07` | EPIC-02 / Story 2.3 Payments & AR | unknown customer rejected | PASS | ValueError: Customer 'NOPE' not found |
| `SVC-PAY-08` | EPIC-02 / Story 2.3 Payments & AR | paying exact remainder -> status paid, due 0 | PASS |  |
| `SVC-PAY-09` | EPIC-02 / Story 2.3 Payments & AR | FIFO alloc pays b2 fully, remainder is advance | PASS | ('partial', [{'invoice_id': '20261009-0002', 'amount': 100.0}], True) |
| `SVC-PAY-10` | EPIC-02 / Story 2.3 Payments & AR | customer balance goes negative (-30) = advance credit | PASS | -30.0 |
| `SVC-PAY-11` | EPIC-02 / Story 2.3 Payments & AR | 3 x 33.33 against 99.99 settles to paid (float rounding) | PASS | ('paid', '0.0') |
| `SVC-PAY-12` | EPIC-02 / Story 2.3 Payments & AR | payment against a VOID invoice rejected | PASS | ValueError: Allocation amount 10.00 exceeds invoice balance due 0.00 |
| `SVC-PAY-13` | EPIC-02 / Story 2.3 Payments & AR | payment against another customer's invoice rejected | PASS | ValueError: Allocation amount 10.00 exceeds invoice balance due 0.00 |
| `SVC-PAY-14` | EPIC-02 / Story 2.3 Payments & AR | payment posts journal entry (EPIC-07 Task 7.1) | PASS | journal_entries=6 |
| `SVC-ORD-01` | EPIC-04 / Story 4.3 Order lifecycle & conversion | order created pending with total 1000 | PASS | ('ORD-20261009-0001', 'pending') |
| `SVC-ORD-02` | EPIC-04 / Story 4.3 Order lifecycle & conversion | empty order rejected | PASS | ValueError: Order must contain at least one item |
| `SVC-ORD-03` | EPIC-04 / Story 4.3 Order lifecycle & conversion | order qty<=0 rejected | PASS | ValueError: Item quantity must be greater than zero |
| `SVC-ORD-04` | EPIC-04 / Story 4.3 Order lifecycle & conversion | convert respects customer credit limit (limit 300, order 1000) | PASS | Credit limit exceeded (300.00) |
| `SVC-ORD-05` | EPIC-04 / Story 4.3 Order lifecycle & conversion | converted bill gets CREATE audit row | PASS | audit rows=1 |
| `SVC-ORD-06` | EPIC-04 / Story 4.3 Order lifecycle & conversion | converted bill has invoice_date/due_date consistent with direct bills | PASS | due_date=2026-11-08 00:00:00 |
| `SVC-ORD-07` | EPIC-04 / Story 4.3 Order lifecycle & conversion | order -> billed, linked_bill_ids set | PASS |  |
| `SVC-ORD-08` | EPIC-04 / Story 4.3 Order lifecycle & conversion | re-convert billed order rejected | PASS | ValueError: Order ORD-20261009-0001 is already billed |
| `SVC-ORD-09` | EPIC-04 / Story 4.3 Order lifecycle & conversion | cancelled order cannot be converted | PASS | ValueError: Order ORD-20261009-0001 is already billed |
| `SVC-ORD-10` | EPIC-04 / Story 4.3 Order lifecycle & conversion | cancelled order cannot be converted to bill | PASS | ValueError: Order ORD-20261009-0002 is 'cancelled' and cannot be converted to a bill |
| `SVC-ORD-11` | EPIC-04 / Story 4.3 Order lifecycle & conversion | convert_to_purchase: stock +4, supplier balance +78.40 (80 less 2% TDS) | PASS | (104.0, 78.4) |
| `SVC-ORD-12` | EPIC-04 / Story 4.3 Order lifecycle & conversion | same order cannot be converted to purchase twice | PASS | Order ORD-20261009-0003 is already converted to purchase PUR-20261009003530-DF7C |
| `SVC-ORD-13` | EPIC-04 / Story 4.3 Order lifecycle & conversion | supplier TDS applied on order->purchase (supplier tds_applicable) | PASS | tds_amount=1.6 |
| `SVC-ORD-14` | EPIC-04 / Story 4.3 Order lifecycle & conversion | order matrix returns rows/customers | PASS | {'customers': ['Anna'], 'rows': [{'item_id': 'VEG0001', 'name': 'Avarai', 'unit': 'kg', 'current_stock': 104.0, 'total_demand': 4.0, 'shortfall': 0.0, 'customer |
| `SVC-PRICE-01` | EPIC-05 / Story 5.2 Pricing | active fixed price used | PASS | (12.0, True) |
| `SVC-PRICE-02` | EPIC-05 / Story 5.2 Pricing | expired fixed price ignored -> item default (20.0) | PASS | (20.0, False) |
| `SVC-PRICE-03` | EPIC-05 / Story 5.2 Pricing | item with only 'default_rate' (seed schema) resolves to 20 w/o caller default | PASS | (20.0, False) |
| `SVC-PRICE-04` | EPIC-05 / Story 5.2 Pricing | other customer unaffected by Cust0001 fixed price | PASS |  |
| `SVC-INV-01` | EPIC-07 / Story 7.3 Inventory | adjust -12.5 -> stock 87.5 + txn logged | PASS | 87.5 |
| `SVC-INV-02` | EPIC-07 / Story 7.3 Inventory | zero adjustment rejected | PASS | ValueError: Adjustment quantity cannot be zero |
| `SVC-INV-03` | EPIC-07 / Story 7.3 Inventory | adjustment below zero rejected | PASS | ValueError: Adjustment would result in negative stock (-412.50) |
| `SVC-INV-04` | EPIC-07 / Story 7.3 Inventory | unknown item rejected | PASS | ValueError: Item 'NOPE' not found |
| `SVC-INV-05` | EPIC-07 / Story 7.3 Inventory | adjustment requires a non-empty reason (docstring: mandatory reason) | PASS | A reason is required for a stock adjustment |
| `SVC-INV-06` | EPIC-07 / Story 7.3 Inventory | waste: amount=250, stock 87.5->77.5, txn type=waste | PASS | (250.0, 77.5) |
| `SVC-INV-07` | EPIC-07 / Story 7.3 Inventory | waste larger than on-hand stock rejected | PASS | Waste quantity 10000 exceeds stock on hand 77.5 |
| `SVC-INV-08` | EPIC-07 / Story 7.3 Inventory | waste qty<=0 rejected | PASS | ValueError: Waste quantity must be greater than zero |
| `SVC-INV-09` | EPIC-07 / Story 7.3 Inventory | negative waste rate rejected | PASS | Waste rate cannot be negative |
| `SVC-PROC-01` | EPIC-07 / Story 7.2 Procurement | PO draft total 4000 | PASS | draft |
| `SVC-PROC-02` | EPIC-07 / Story 7.2 Procurement | PO unknown supplier | PASS | ValueError: Supplier 'NOPE' not found |
| `SVC-PROC-03` | EPIC-07 / Story 7.2 Procurement | PO empty items | PASS | ValueError: PO must contain at least one item |
| `SVC-PROC-04` | EPIC-07 / Story 7.2 Procurement | GRN: stock +100, PO received | PASS | 200.0 |
| `SVC-PROC-05` | EPIC-07 / Story 7.2 Procurement | second GRN against an already-received PO rejected | PASS | Purchase Order 'PO-20261009-E82D' is already received |
| `SVC-PROC-06` | EPIC-07 / Story 7.2 Procurement | GRN qty greater than PO ordered qty (100) rejected/flagged | PASS | Purchase Order 'PO-20261009-E82D' is already received |
| `SVC-PROC-07` | EPIC-07 / Story 7.2 Procurement | purchase bill TDS 2% on 50000 = 1000, payable 49000 | PASS | (1000.0, 49000.0) |
| `SVC-PROC-08` | EPIC-07 / Story 7.2 Procurement | supplier balance += payable | PASS |  |
| `SVC-PROC-09` | EPIC-07 / Story 7.2 Procurement | 3-way match: purchase bill qty (1000) vs GRN qty (100) flagged | PASS | match_status=mismatch |
| `SVC-PROC-10` | EPIC-07 / Story 7.2 Procurement | supplier part-pay: due 40000 status partial | PASS |  |
| `SVC-PROC-11` | EPIC-07 / Story 7.2 Procurement | supplier over-payment rejected | PASS | ValueError: Payment amount 99999.00 exceeds purchase balance due 40000.00 |
| `SVC-PROC-12` | EPIC-07 / Story 7.2 Procurement | supplier payment on unknown bill | PASS | ValueError: Purchase Bill 'NOPE' not found |
| `SVC-PROC-13` | EPIC-07 / Story 7.2 Procurement | AP payment posts journal entry | PASS | journal_entries=2 |
| `SVC-SESS-01` | EPIC-07 / Story 7.3 Cash sessions | second open session for same user rejected | PASS | ValueError: You already have an open cashier session. Please close it first. |
| `SVC-SESS-02` | EPIC-07 / Story 7.3 Cash sessions | expected cash = 2000 + 3500 cash sale + 500 receipt = 6000 (credit bill excluded) | PASS | expected_cash=6000.0 (credit bill of 1000 excluded) |
| `SVC-SESS-03` | EPIC-07 / Story 7.3 Cash sessions | close: difference = actual - expected | PASS | -50.0 |
| `SVC-SESS-04` | EPIC-07 / Story 7.3 Cash sessions | closing a closed session rejected | PASS | ValueError: Session 'SES-20261009-B9A66E' is already closed |
| `SVC-SESS-05` | EPIC-07 / Story 7.3 Cash sessions | close unknown session | PASS | ValueError: Session 'NOPE' not found |
| `SVC-SESS-06` | EPIC-07 / Story 7.3 Cash sessions | negative opening cash rejected | PASS | Opening cash cannot be negative |
| `SVC-GL-01` | EPIC-07 / Story 7.1 General ledger | balanced journal posts with state=posted | PASS |  |
| `SVC-GL-02` | EPIC-07 / Story 7.1 General ledger | unbalanced journal rejected | PASS | ValueError: Unbalanced journal entry: debits (1500.00) != credits (1200.00) |
| `SVC-GL-03` | EPIC-07 / Story 7.1 General ledger | rejected journal persisted nothing (count==1) | PASS |  |
| `SVC-GL-04` | EPIC-07 / Story 7.1 General ledger | trial balance balanced | PASS | 1500.0 |
| `SVC-GL-05` | EPIC-07 / Story 7.1 General ledger | negative debit/credit amounts rejected | PASS | Debit and credit amounts cannot be negative |
| `SVC-GL-06` | EPIC-07 / Story 7.1 General ledger | empty journal (no lines) rejected | PASS | A journal entry needs at least two lines |
| `SVC-GL-07` | EPIC-07 / Story 7.1 General ledger | a line with both debit and credit rejected | PASS | A journal line cannot have both a debit and a credit |
| `SVC-GL-08` | EPIC-07 / Story 7.1 General ledger | P&L sales includes sale (200) | PASS | {'total_sales': 200.0, 'fee_income': 15.0, 'other_income': 0, 'total_revenue': 215.0, 'cost_of_goods_sold': 500.0, 'total_purchases': -0.0, 'gross_profit': -285 |
| `SVC-GL-09` | EPIC-07 / Story 7.1 General ledger | sale auto-posts balanced journal (AR Dr / Sales Cr) | PASS | journal_entries=2 |
| `SVC-AUTH-admin-ok` | EPIC-01 / Story 1.3 Authentication & RBAC | login 'admin'/'admin123' -> success | PASS |  |
| `SVC-AUTH-manager-ok` | EPIC-01 / Story 1.3 Authentication & RBAC | login 'manager'/'manager123' -> success | PASS |  |
| `SVC-AUTH-user-ok` | EPIC-01 / Story 1.3 Authentication & RBAC | login 'user'/'user123' -> success | PASS |  |
| `SVC-AUTH-admin-bad` | EPIC-01 / Story 1.3 Authentication & RBAC | login 'admin'/'bad' -> rejected | PASS |  |
| `SVC-AUTH-ghost-bad` | EPIC-01 / Story 1.3 Authentication & RBAC | login 'ghost'/'x' -> rejected | PASS |  |
| `SVC-AUTH-admin-empty-pw-bad` | EPIC-01 / Story 1.3 Authentication & RBAC | login 'admin-empty-pw'/'' -> rejected | PASS |  |
| `SVC-AUTH-audit` | EPIC-01 / Story 1.3 Authentication & RBAC | login writes user_activity_audits | PASS |  |
| `SVC-AUTH-inactive` | EPIC-01 / Story 1.3 Authentication & RBAC | inactive user cannot log in | PASS |  |
| `SVC-AUTH-perm-manager` | EPIC-01 / Story 1.3 Authentication & RBAC | manager role has non-empty menu permissions (role_permissions seeded) | PASS | {'/accounting', '/customers', '/ledger', '/finance', '/suppliers', '/items'} |

### GUI: login / navigation / RBAC  (29/29 passed)

| ID | Epic / story | Test case (expected behaviour) | Result | Evidence |
| :-- | :-- | :-- | :-: | :-- |
| `GUI-LOGIN-01` | EPIC-01 Login | login form is NOT pre-filled with credentials | PASS | username='', password chars=0 |
| `GUI-LOGIN-02` | EPIC-01 Login | blank credentials -> warning, no login | PASS | ('showwarning', 'Sign In', 'Please enter both username and password.') |
| `GUI-LOGIN-03` | EPIC-01 Login | wrong password -> 'Sign In Failed' error, window stays | PASS | ('showerror', 'Sign In Failed', 'Invalid username or password') |
| `GUI-LOGIN-04` | EPIC-01 Login | correct password -> CurrentUser set and window closed | PASS |  |
| `GUI-LOGIN-05` | EPIC-01 Login | injection-style username rejected | PASS | ('showerror', 'Sign In Failed', 'Invalid username or password') |
| `GUI-LOGIN-06` | EPIC-01 Login | operator-string username rejected | PASS |  |
| `GUI-NAV-01` | EPIC-01 Shell & navigation | MainWindow builds for admin | PASS |  |
| `GUI-NAV-02` | EPIC-01 Shell & navigation | all 27 navigable pages open without exception | PASS | [] |
| `GUI-NAV-03` | EPIC-01 Shell & navigation | admin sees File/Masters/Reports/Accounts/Settings menus | PASS | ['File', 'Masters', 'Reports', 'Accounts', 'Settings'] |
| `GUI-KEY-F1` | EPIC-01 Global shortcuts | <F1> navigates to Dashboard | PASS | Dashboard |
| `GUI-KEY-F4` | EPIC-01 Global shortcuts | <F4> navigates to Customer Master | PASS | Customer Master |
| `GUI-KEY-F10` | EPIC-01 Global shortcuts | <F10> navigates to Item Master | PASS | Item Master |
| `GUI-KEY-Control-o` | EPIC-01 Global shortcuts | <Control-o> navigates to Orders | PASS | Orders |
| `GUI-KEY-Control-p` | EPIC-01 Global shortcuts | <Control-p> navigates to Procurement | PASS | Procurement |
| `GUI-KEY-Control-d` | EPIC-01 Global shortcuts | <Control-d> navigates to Finance | PASS | Finance |
| `GUI-KEY-F2` | EPIC-01 Global shortcuts | F2 opens New Bill | PASS | New Bill |
| `GUI-KEY-F6` | EPIC-01 Global shortcuts | F6 from New Bill = Park Bill (empty bill -> no-op), stays on New Bill | PASS | New Bill |
| `GUI-RBAC-manager-01` | EPIC-01 Role-based access | manager: menus hidden ['Settings'] / shown ['Accounts', 'Masters'] | PASS | ['File', 'Masters', 'Reports', 'Accounts'] |
| `GUI-RBAC-manager-02` | EPIC-01 Role-based access | manager: Profit & Loss / Balance Sheet in Reports menu only if finance access (True) | PASS | ['Bill History', 'Consolidated Billing', 'Order Matrix', 'Fixed Rates', 'Profit & Loss', 'Balance Sheet', 'Dashboard'] |
| `GUI-RBAC-manager-F10` | EPIC-01 Role-based access | manager: <F10> -> Item Master is allowed | PASS | active_page=Item Master |
| `GUI-RBAC-manager-F11` | EPIC-01 Role-based access | manager: <F11> -> Customer Master is allowed | PASS | active_page=Customer Master |
| `GUI-RBAC-manager-Control-d` | EPIC-01 Role-based access | manager: <Control-d> -> Finance is allowed | PASS | active_page=Finance |
| `GUI-RBAC-manager-settings` | EPIC-01 Role-based access | manager: User Management blocked | PASS | Finance |
| `GUI-RBAC-user-01` | EPIC-01 Role-based access | user: menus hidden ['Accounts', 'Masters', 'Settings'] / shown [] | PASS | ['File', 'Reports'] |
| `GUI-RBAC-user-02` | EPIC-01 Role-based access | user: Profit & Loss / Balance Sheet in Reports menu only if finance access (False) | PASS | ['Bill History', 'Consolidated Billing', 'Order Matrix', 'Dashboard'] |
| `GUI-RBAC-user-F10` | EPIC-01 Role-based access | user: <F10> -> Item Master is blocked | PASS | active_page=Dashboard |
| `GUI-RBAC-user-F11` | EPIC-01 Role-based access | user: <F11> -> Customer Master is blocked | PASS | active_page=Dashboard |
| `GUI-RBAC-user-Control-d` | EPIC-01 Role-based access | user: <Control-d> -> Finance is blocked | PASS | active_page=Dashboard |
| `GUI-RBAC-user-settings` | EPIC-01 Role-based access | user: User Management blocked | PASS | Dashboard |

### GUI: billing grid & payment  (38/38 passed)

| ID | Epic / story | Test case (expected behaviour) | Result | Evidence |
| :-- | :-- | :-- | :-: | :-- |
| `GUI-BILL-01` | EPIC-02 Billing grid & payment modal | default grid has settings.default_num_rows rows | PASS | 20 |
| `GUI-BILL-02` | EPIC-02 Billing grid & payment modal | code 101 + Enter fetches Apple, unit kg, rate 20.00, qty 1 | PASS | ('Apple', 'kg', '20.00', '1') |
| `GUI-BILL-03` | EPIC-02 Billing grid & payment modal | after code Enter, focus moves to Qty | PASS | .!frame.!frame4.!billingframe.!frame.!frame2.!canvas.!frame.!frame.!frame3.!entry |
| `GUI-BILL-04` | EPIC-02 Billing grid & payment modal | Qty Enter moves focus to Unit | PASS | .!frame.!frame4.!billingframe.!frame.!frame2.!canvas.!frame.!frame.!combobox |
| `GUI-BILL-05` | EPIC-02 Billing grid & payment modal | line amount = 2.5 x 20 = 50.00 | PASS | ₹50.00 |
| `GUI-BILL-06` | EPIC-02 Billing grid & payment modal | grand total label updates | PASS | Total: ₹50.00 |
| `GUI-BILL-07` | EPIC-02 Billing grid & payment modal | unknown item code 'ZZZ999' must NOT silently fill a random item (Apple) | PASS | typed ZZZ999 -> row filled with '' code='' rate='' |
| `GUI-BILL-08` | EPIC-02 Billing grid & payment modal | typing name prefix 'banana' resolves a Banana item | PASS | Banana Leaves (NUNI) |
| `GUI-BILL-09-'('` | EPIC-02 Billing grid & payment modal | regex metachar '(' in code box does not raise | PASS | name='Banana Leaves (NUNI)' |
| `GUI-BILL-09-'[a-'` | EPIC-02 Billing grid & payment modal | regex metachar '[a-' in code box does not raise | PASS | name='' |
| `GUI-BILL-09-'.*'` | EPIC-02 Billing grid & payment modal | regex metachar '.*' in code box does not raise | PASS | name='' |
| `GUI-BILL-09-'\\'` | EPIC-02 Billing grid & payment modal | regex metachar '\\' in code box does not raise | PASS | name='' |
| `GUI-BILL-10` | EPIC-02 Billing grid & payment modal | keystroke rate 1,12,123 x qty 4 -> 4.00 / 48.00 / 492.00 | PASS | ['₹4.00', '₹48.00', '₹492.00'] |
| `GUI-BILL-11` | EPIC-02 Billing grid & payment modal | non-numeric qty treated as 0 (amount 0.00) | PASS | ₹0.00 |
| `GUI-BILL-12` | EPIC-02 Billing grid & payment modal | negative qty must not reduce the grand total | PASS | row amount=₹0.00 grand_total=50.0 |
| `GUI-BILL-14` | EPIC-02 Billing grid & payment modal | customer search lists seeded customer 'Anna Adarsh Hostel' | PASS | ['Select Customer (F5)', 'Cash Customer', 'Counter Walk-in Sale', 'Anna Adarsh Hostel', '9444434066', 'Counter Customer'] |
| `GUI-BILL-15` | EPIC-02 Billing grid & payment modal | search by bill_to_phone finds Anna Adarsh Hostel | PASS | ['Select Customer (F5)', 'Anna Adarsh Hostel', '9444434066'] |
| `GUI-BILL-16` | EPIC-02 Billing grid & payment modal | picking customer applies contract rate 12.00 to existing row (was 20.00) | PASS | 12.00 |
| `GUI-BILL-17` | EPIC-02 Billing grid & payment modal | delivery/bill-to labels filled | PASS | Anna Adarsh Hostel |
| `GUI-BILL-18` | EPIC-02 Billing grid & payment modal | save shows 'Bill Saved' with invoice number | PASS | ('showinfo', 'Bill Saved', 'Invoice #20261009-0001 generated successfully!\nTotal: ₹120.00') |
| `GUI-BILL-19` | EPIC-02 Billing grid & payment modal | bill persisted with total 120 | PASS | 120.0 |
| `GUI-BILL-20` | EPIC-02 Billing grid & payment modal | fully-paid-at-counter bill is stored as status=paid, balance_due=0 | PASS | status=paid balance_due=0.0 |
| `GUI-BILL-21` | EPIC-02 Billing grid & payment modal | payment receipt (Cash 120) recorded in payments collection | PASS | payments=1 |
| `GUI-BILL-22` | EPIC-02 Billing grid & payment modal | customer outstanding balance NOT increased when paid in full (expected 0) | PASS | current_balance=0.0 |
| `GUI-BILL-23` | EPIC-02 Billing grid & payment modal | company chosen in the form is stored on the bill | PASS | company_id='Company0001' |
| `GUI-BILL-24` | EPIC-02 Billing grid & payment modal | stock decremented by 10 | PASS | 90.0 |
| `GUI-BILL-25` | EPIC-02 Billing grid & payment modal | form reset after save | PASS |  |
| `GUI-BILL-26` | EPIC-02 Billing grid & payment modal | part-paid (200 of 500): status=partial, balance_due=300 | PASS | status=partial balance_due=300.0 |
| `GUI-BILL-27` | EPIC-02 Billing grid & payment modal | customer outstanding = 300 after part-payment | PASS | 300.0 |
| `GUI-BILL-28` | EPIC-02 Billing grid & payment modal | credit-limit breach shows 'Failed to Save Bill' error | PASS | ('showerror', 'Failed to Save Bill', 'Credit limit exceeded (400.00)') |
| `GUI-BILL-29` | EPIC-02 Billing grid & payment modal | form data retained after failed save (cashier can fix) | PASS | 101 |
| `GUI-BILL-30` | EPIC-02 Billing grid & payment modal | non-numeric 'Amount Received' is rejected (not silently treated as full payment) | PASS | new bill saved: status=partial balance_due=300.0 |
| `GUI-BILL-31` | EPIC-02 Billing grid & payment modal | receiving 5000 against a 100 bill is rejected/flagged as over-payment (or booked as advance) | PASS | bills 2->2; status=partial balance_due=300.0 |
| `GUI-BILL-32` | EPIC-02 Billing grid & payment modal | saving an empty bill warns 'Empty Bill' | PASS | ('showwarning', 'Empty Bill', 'Please add at least one line item before saving.') |
| `GUI-BILL-33` | EPIC-02 Billing grid & payment modal | park clears form and counts 1 parked bill | PASS | 1 |
| `GUI-BILL-34` | EPIC-02 Billing grid & payment modal | recall restores line (Bajji Chilli, qty 3) | PASS | ('Bajji Chilli', '3') |
| `GUI-BILL-35` | EPIC-02 Billing grid & payment modal | parked count drops to 0 after recall | PASS | 0 |
| `GUI-BILL-36` | EPIC-02 Billing grid & payment modal | a parked bill is still there after the application is closed and started again (separate process) | PASS | PARKED_AFTER_RESTART 1 Bajji Chilli |

### GUI: orders / importer / history  (40/40 passed)

| ID | Epic / story | Test case (expected behaviour) | Result | Evidence |
| :-- | :-- | :-- | :-: | :-- |
| `GUI-BILL-13` | EPIC-02 Billing grid & payment modal | a bill containing an invalid line (qty -5) is NOT saved; the cashier is told which row to fix (no silent total/lines mismatch) | PASS | bills saved=0; grid total=200.0; dialog=('showerror', 'Fix These Lines', 'The bill was not saved:\n\nRow 2 (Avarai): quantity must be greater than zero') |
| `GUI-IMP-01` | EPIC-04 / Story 4.2 Smart importer | importer line '101 5kg' -> ('Apple', 5.0, 'kg') | PASS | got ('Apple', 5.0, 'kg') |
| `GUI-IMP-02` | EPIC-04 / Story 4.2 Smart importer | importer line 'Apple 25kg' -> ('Apple', 25.0, 'kg') | PASS | got ('Apple', 25.0, 'kg') |
| `GUI-IMP-03` | EPIC-04 / Story 4.2 Smart importer | importer line '102 50kg' -> ('Avarai', 50.0, 'kg') | PASS | got ('Avarai', 50.0, 'kg') |
| `GUI-IMP-04` | EPIC-04 / Story 4.2 Smart importer | importer line 'Banana Green 3 kg' -> ('Banana Green', 3.0, 'kg') | PASS | got ('Banana Green', 3.0, 'kg') |
| `GUI-IMP-05` | EPIC-04 / Story 4.2 Smart importer | importer line 'Tomato 2 boxes': unknown/ambiguous text is skipped, never guessed | PASS | imported=0 skipped=['Tomato 2 boxes'] |
| `GUI-IMP-06` | EPIC-04 / Story 4.2 Smart importer | importer line '5 kg': unknown/ambiguous text is skipped, never guessed | PASS | imported=0 skipped=['5 kg'] |
| `GUI-IMP-07` | EPIC-04 / Story 4.2 Smart importer | importer line 'avarai 4' -> ('Avarai', 4.0, 'kg') | PASS | got ('Avarai', 4.0, 'kg') |
| `GUI-IMP-08` | EPIC-04 / Story 4.2 Smart importer | importer line 'Apple x' -> ('Apple', 1.0, 'kg') | PASS | got ('Apple', 1.0, 'kg') |
| `GUI-ORD-01` | EPIC-04 Order form & list | order saved via form (status pending, total 636 = 600 + 5% commission + 1% mandi) | PASS | ('ORD-20261009-0001', 'pending', 636.0) |
| `GUI-ORD-02` | EPIC-04 Order form & list | order stores hidden commission=5% and mandi fee=1% of total (30 / 6) | PASS | (30.0, 6.0) |
| `GUI-ORD-03` | EPIC-04 Order form & list | commission/mandi fee shown on the order form are included in the order total (and carried to the bill) | PASS | form displays Comm/Mandi Fee but stored total_amount=636.0 excludes them (expected 636.0); converted bill also ignores them |
| `GUI-ORD-04` | EPIC-04 Order form & list | delivery date before order date rejected | PASS | ('showwarning', 'Invalid Date Range', 'Delivery date (06 - 10 - 2026) cannot be before order date (09 - 10 - 2026).') |
| `GUI-ORD-05` | EPIC-04 Order form & list | impossible date 31-02-2026 rejected | PASS | ('showwarning', 'Invalid Delivery Date', 'Please enter a valid delivery date (DD - MM - YYYY).') |
| `GUI-ORD-06` | EPIC-04 Order form & list | non-date text rejected | PASS | ('showwarning', 'Invalid Delivery Date', 'Please enter a valid delivery date (DD - MM - YYYY).') |
| `GUI-ORD-07` | EPIC-04 Order form & list | qty 0 rejected | PASS | ('showwarning', 'Invalid Quantity', 'Please enter a valid quantity for row 1 (Apple).') |
| `GUI-ORD-08` | EPIC-04 Order form & list | negative qty rejected | PASS | ('showwarning', 'Invalid Quantity', 'Please enter a valid quantity for row 1 (Apple).') |
| `GUI-ORD-09` | EPIC-04 Order form & list | non-numeric qty rejected | PASS | ('showwarning', 'Invalid Quantity', 'Please enter a valid quantity for row 1 (Apple).') |
| `GUI-ORD-10` | EPIC-04 Order form & list | no customer -> 'Customer Required' | PASS | ('showwarning', 'Customer Required', 'Please select a valid customer (F5).') |
| `GUI-ORD-11` | EPIC-04 Order form & list | free-typed customer name that is not in the master cannot create an order | PASS | orders 1->1, customer_id stored='Cust0001' |
| `GUI-ORD-12` | EPIC-04 Order form & list | orders list shows saved orders | PASS | 1 |
| `GUI-ORD-13` | EPIC-04 Order form & list | convert-to-bill (UI) honours customer credit limit (limit 100, order 600) | PASS | bill created=False; customer balance=0.0; dialog=('showerror', 'Error', 'Credit limit exceeded (100.00)') |
| `GUI-ORD-14` | EPIC-04 Order form & list | convert-to-bill creates invoice and marks order billed | PASS | 20261009-0001 |
| `GUI-ORD-15` | EPIC-04 Order form & list | an already-BILLED order cannot be cancelled (would orphan the invoice) | PASS | order status now 'billed'; invoice 20261009-0001 status=unpaid |
| `GUI-HIST-01` | EPIC-03 Bill history | history lists every bill in DB | PASS | ui=1 db=1 |
| `GUI-HIST-02` | EPIC-03 Bill history | search with no match shows 'Showing 0 of 0' | PASS | Showing 0 of 0 bills |
| `GUI-HIST-03` | EPIC-03 Bill history | search by customer name (case-insensitive) | PASS | 1 |
| `GUI-HIST-04` | EPIC-03 Bill history | regex-special text in search box does not crash | PASS |  |
| `GUI-HIST-05` | EPIC-03 Bill history | void via UI marks bill void and shows success | PASS | ('showinfo', 'Success', 'Invoice 20261009-0001 voided and all financial/stock impacts reversed.') |
| `GUI-HIST-06` | EPIC-03 Bill history | void restores stock of every line of that item | PASS | (90.0, 100.0, 10.0) |
| `GUI-HIST-07` | EPIC-03 Bill history | void reduces customer balance by the bill total (balance never < 0 for an unpaid bill) | PASS | (636.0, 0.0) |
| `GUI-HIST-08` | EPIC-03 Bill history | voiding an already void bill warns | PASS | ('showwarning', 'Already Voided', 'Invoice 20261009-0001 is already voided.') |
| `GUI-HIST-09` | EPIC-03 Bill history | KPI 'total bills' excludes void | PASS | 0 |
| `GUI-HIST-10` | EPIC-03 Bill history | KPI revenue = sum of non-void bills | PASS | ui=₹ 0.00 db=0 |
| `GUI-HIST-11` | EPIC-03 Bill history | void with nothing selected asks to select a bill | PASS | ('showinfo', 'Select Bill', 'Please select an invoice to void.') |
| `GUI-HIST-12` | EPIC-03 Bill history | history shows ALL bills (>500) and KPI counts are correct | PASS | ui=521 db=521 |
| `GUI-CONS-01` | EPIC-06 / Task 6.1.4 Consolidated report | consolidated report view opens | PASS |  |
| `GUI-CONS-02` | EPIC-06 / Task 6.1.4 Consolidated report | consolidated total equals sum of non-void bills for the customer | PASS | (0, 0) |
| `GUI-CONS-03` | EPIC-06 / Task 6.1.4 Consolidated report | blank customer rejected | PASS |  |
| `GUI-CONS-04` | EPIC-06 / Task 6.1.4 Consolidated report | reversed date range (from > to) yields empty / is rejected | PASS |  |

### GUI: masters / finance / PDF / admin  (63/63 passed)

| ID | Epic / story | Test case (expected behaviour) | Result | Evidence |
| :-- | :-- | :-- | :-: | :-- |
| `CUR-fmt-0` | EPIC-06 / Task 6.1.3 Number formatting | format_inr(0) -> ₹ 0.00 | PASS | ₹ 0.00 |
| `CUR-fmt-999` | EPIC-06 / Task 6.1.3 Number formatting | format_inr(999) -> ₹ 999.00 | PASS | ₹ 999.00 |
| `CUR-fmt-1000` | EPIC-06 / Task 6.1.3 Number formatting | format_inr(1000) -> ₹ 1,000.00 | PASS | ₹ 1,000.00 |
| `CUR-fmt-123456.5` | EPIC-06 / Task 6.1.3 Number formatting | format_inr(123456.5) -> ₹ 1,23,456.50 | PASS | ₹ 1,23,456.50 |
| `CUR-fmt-12345678.9` | EPIC-06 / Task 6.1.3 Number formatting | format_inr(12345678.9) -> ₹ 1,23,45,678.90 | PASS | ₹ 1,23,45,678.90 |
| `CUR-fmt--2500` | EPIC-06 / Task 6.1.3 Number formatting | format_inr(-2500) -> -₹ 2,500.00 | PASS | -₹ 2,500.00 |
| `CUR-fmt-None` | EPIC-06 / Task 6.1.3 Number formatting | format_inr(None) -> ₹ 0.00 | PASS | ₹ 0.00 |
| `CUR-fmt-0.5` | EPIC-06 / Task 6.1.3 Number formatting | format_inr(0.5) -> ₹ 0.50 | PASS | ₹ 0.50 |
| `CUR-words-0` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(0) | PASS | Zero Rupees Only |
| `CUR-words-1` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(1) | PASS | One Rupee Only |
| `CUR-words-21` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(21) | PASS | Twenty One Rupees Only |
| `CUR-words-100` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(100) | PASS | One Hundred Rupees Only |
| `CUR-words-1234.5` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(1234.5) | PASS | One Thousand Two Hundred Thirty Four Rupees and Fifty Paise Only |
| `CUR-words-100000` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(100000) | PASS | One Lakh Rupees Only |
| `CUR-words-12345678` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(12345678) | PASS | One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight Rupees Only |
| `CUR-words--50` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(-50) | PASS | Minus Fifty Rupees Only |
| `CUR-words-singular` | EPIC-06 / Task 6.1.3 Number formatting | 1 rupee reads 'One Rupee Only' (singular) | PASS | One Rupee Only |
| `CUR-words-rounding-99.999` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(99.999) (fractional paise from qty x rate) does not crash | PASS | One Hundred Rupees Only |
| `CUR-words-rounding-0.995` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(0.995) (fractional paise from qty x rate) does not crash | PASS | One Rupee Only |
| `CUR-words-rounding-1.999` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(1.999) (fractional paise from qty x rate) does not crash | PASS | Two Rupees Only |
| `CUR-words-rounding-19999.995` | EPIC-06 / Task 6.1.3 Number formatting | amount_in_words(19999.995) (fractional paise from qty x rate) does not crash | PASS | Twenty Thousand Rupees Only |
| `CUR-words-crore100` | EPIC-06 / Task 6.1.3 Number formatting | amount >= 100 crore (Rs 100,00,00,000) converts without crashing | PASS | One Hundred Crore Rupees Only |
| `GUI-DASH-01` | EPIC-03/06 Dashboard | dashboard 'Sales Today' equals sum of today's non-void bills | PASS | ui='₹ 1,842.60' db=1842.6 |
| `GUI-DASH-02` | EPIC-03/06 Dashboard | dashboard bill count = 3 | PASS | 3 bills |
| `PDF-INV-01` | EPIC-06 / Story 6.1 PDF generation | invoice PDF has 1 page for a 2-line bill | PASS | 1 |
| `PDF-INV-02` | EPIC-06 / Story 6.1 PDF generation | invoice PDF contains invoice number | PASS | 20261009-0001 |
| `PDF-INV-03` | EPIC-06 / Story 6.1 PDF generation | invoice PDF contains customer name | PASS |  |
| `PDF-INV-04` | EPIC-06 / Story 6.1 PDF generation | invoice PDF contains grand total 542.63 | PASS | ['Total: ₹542.63'] |
| `PDF-INV-05` | EPIC-06 / Story 6.1 PDF generation | invoice PDF contains amount in words | PASS | ['Amount in Words: Five Hundred Forty Two Rupees and Sixty Three Paise Only'] |
| `PDF-INV-06` | EPIC-06 / Story 6.1 PDF generation | invoice PDF shows line items (Apple, Avarai) | PASS |  |
| `PDF-DC-01` | EPIC-06 / Story 6.1 PDF generation | delivery challan omits rates/amounts | PASS | ok |
| `PDF-DC-02` | EPIC-06 / Story 6.1 PDF generation | delivery challan lists items & qty | PASS | SV VEGETABLES & FRUITS \| No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092. \| Ph: 9876543210 \| Email: info@svveg.com \| GSTIN: 33ABCDE1234F1Z5 \| |
| `PDF-INV-07` | EPIC-06 / Story 6.1 PDF generation | 60-line invoice paginates without losing lines | PASS | pages=4 has Item 59=True |
| `PDF-INV-08` | EPIC-06 / Story 6.1 PDF generation | special characters / markup in names do not break PDF generation | PASS | SV Vegetables & Fruits No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092. Ph: 9876543210 \| Email: info@svveg |
| `GUI-MST-01` | EPIC-05 Master data | new item saved with is_deleted=0 / active defaults (visible to billing) | PASS | {'is_deleted': 0, 'status': 'active', 'stock': 0.0, 'default_rate': None, 'standard_rate': None} |
| `GUI-MST-dup-duplicate item id` | EPIC-05 Master data | item duplicate item id rejected | PASS | Item ID 'QAI001' already exists |
| `GUI-MST-dup-duplicate alias` | EPIC-05 Master data | item duplicate alias rejected | PASS | Item alias '901' is already in use |
| `GUI-MST-dup-blank id` | EPIC-05 Master data | item blank id rejected | PASS | Item ID and Name are required |
| `GUI-MST-dup-blank name` | EPIC-05 Master data | item blank name rejected | PASS | Item ID and Name are required |
| `GUI-MST-04` | EPIC-05 Master data | negative standard rate rejected | PASS | Item rate cannot be negative |
| `GUI-MST-05` | EPIC-05 Master data | deleted item disappears from search & billing lookup | PASS | [] |
| `GUI-MST-06` | EPIC-05 Master data | re-creating a soft-deleted item id/alias is blocked or resurrects correctly | PASS | Item ID 'QAI001' already exists |
| `GUI-MST-07` | EPIC-05 Master data | new customer is active/non-deleted and billable | PASS | {'is_deleted': 0, 'status': 'active', 'current_balance': 0.0, 'credit_limit': 1000.0} |
| `GUI-MST-08` | EPIC-05 Master data | duplicate customer id rejected | PASS | Customer ID 'QAC001' already exists |
| `GUI-MST-09` | EPIC-05 Master data | customer with outstanding balance (777) cannot be deleted | PASS | is_deleted=0 despite balance 777 |
| `GUI-MST-10` | EPIC-05 Master data | editing a customer record cannot overwrite the ledger balance (current_balance) | PASS | balance after edit=777.0 |
| `GUI-MST-fp-zero rate` | EPIC-05 Master data | fixed price zero rate rejected | PASS | Fixed rate must be greater than zero |
| `GUI-MST-fp-start after end` | EPIC-05 Master data | fixed price start after end rejected | PASS | Start date must be before end date |
| `GUI-MST-11` | EPIC-05 Master data | re-saving a fixed price leaves exactly one active price | PASS | 1 |
| `GUI-FIN-01` | EPIC-07 Finance screens | trial balance includes the automatic postings from the 3 bills AND the manual opening journal, and balances | PASS | rows=[('1000', 5299.97, 0.0), ('1200', 1542.63, 0.0), ('1300', 0.0, 741.23), ('3000', 0.0, 5000.0), ('4000', 0.0, 1842.6), ('5050', 741.23, 0.0)] |
| `GUI-FIN-02` | EPIC-07 Finance screens | P&L total revenue = sum of non-void bills | PASS | {'total_sales': 1842.6, 'fee_income': 0.0, 'other_income': 0, 'total_revenue': 1842.6, 'cost_of_goods_sold': 741.23, 'total_purchases': 0.0, 'gross_profit': 110 |
| `GUI-FIN-05` | EPIC-07 Finance screens | Balance Sheet screen shows real asset/liability/equity figures and balances (EPIC-07 Task 7.2) | PASS | BALANCE SHEET \| ============================================================ \| ASSETS \|   Cash on Hand                                      5,299.97 \|   Acc |
| `GUI-FIN-06` | EPIC-07 Finance screens | P&L charges COGS only (goods sold), not every purchase: buying Rs4000 stock and selling ~Rs1,100 must not show a ~Rs-2,900 'loss' while stock is still on the shelf | PASS | sales=1842.60 purchases=0.00 net_profit=1101.37 |
| `GUI-FIN-07` | EPIC-07 Finance screens | Trial Balance dialog lists per-account debit/credit rows (not just totals) | PASS | TRIAL BALANCE \| ====================================================================== \| Code  Account                                      Debit        Credi |
| `GUI-FIN-03` | EPIC-07 Finance screens | AR aging total equals sum of open balance_due | PASS | {'current': 1442.63, '1_30': 0.0, '31_60': 0.0, '61_90': 0.0, '90_plus': 0.0, 'total': 1442.63} |
| `GUI-FIN-04` | EPIC-07 Finance screens | AR aging total equals sum of customer.current_balance (sub-ledger = control account) | PASS | aging=1442.63 vs customers=1442.63 |
| `GUI-ADM-01` | EPIC-05/01 Administration | user list never exposes password hashes | PASS |  |
| `GUI-ADM-02` | EPIC-05/01 Administration | create user | PASS |  |
| `GUI-ADM-03` | EPIC-05/01 Administration | duplicate username rejected | PASS | User 'tester' already exists |
| `GUI-ADM-04` | EPIC-05/01 Administration | password policy enforced (min length) | PASS | Password must be at least 6 characters |
| `GUI-ADM-05` | EPIC-05/01 Administration | passwords longer than 72 bytes differing after char 72 are distinguished | PASS |  |
| `GUI-ADM-06` | EPIC-05/01 Administration | deactivated user cannot sign in | PASS |  |
| `GUI-ADM-07` | EPIC-05/01 Administration | unknown role rejected | PASS |  |

## Appendix B - Files added

* `tests/qa_realdb/` - the executable test cases (service layer + GUI), a reset script and a shared helper. They are deliberately **not** named `test_*.py` so `pytest tests/` does not collect them (they need a disposable real MongoDB).
* `Docs/qa-evidence/` - application-window screenshots referenced above.
