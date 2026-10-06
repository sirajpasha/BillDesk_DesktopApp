# BillDesk Desktop — Native Mandi POS & ERP

<div align="center">

[![Tests Passing](https://img.shields.io/badge/pytest-48%20passed%20(100%25)-success?style=for-the-badge&logo=pytest)](Docs/TEST_TRACEABILITY_REPORT.md)
[![Jupyter Notebook](https://img.shields.io/badge/Jupyter-Interactive%20Walkthrough-orange?style=for-the-badge&logo=jupyter)](README.ipynb)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.14-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Database](https://img.shields.io/badge/MongoDB-27018%20%7C%20Atlas-forestgreen?style=for-the-badge&logo=mongodb)](https://www.mongodb.com/)
[![GitHub Issues](https://img.shields.io/badge/GitHub-Epics%20%26%20Stories-purple?style=for-the-badge&logo=github)](https://github.com/sirajpasha/BillDesk_DesktopApp/issues)

<p align="center">
  <b>High-speed, keyboard-driven native desktop Point-of-Sale (POS) and Enterprise Resource Planning (ERP) platform purpose-built for wholesale produce markets, vegetable mandis, and commission agents.</b>
</p>

[📓 Open Interactive Jupyter Notebook](README.ipynb) • [📋 Test Traceability Matrix](Docs/TEST_TRACEABILITY_REPORT.md) • [📖 User Guide](Docs/USER_GUIDE.md) • [🎯 Epics & Tasks](Docs/EPICS_USER_STORIES_TASKS.md)

</div>

---

## 📸 Visual Showcase & Screen Flows

<table align="center" width="100%">
  <tr>
    <td width="50%" align="center">
      <b>Secure Role-Based Login Screen</b><br/>
      <sub>Theme matching botanical wholesale produce motif</sub><br/><br/>
      <img src="Docs/user-guide/img/01-login.png" width="95%" alt="Login Screen" />
    </td>
    <td width="50%" align="center">
      <b>Fast Mandi Billing Entry Grid</b><br/>
      <sub>Full-width 18-row spreadsheet with keystroke rate calculations</sub><br/><br/>
      <img src="Docs/user-guide/img/04-billing-empty.png" width="95%" alt="Billing Form" />
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <b>Customer Order Booking & Smart Importer</b><br/>
      <sub>Freeform WhatsApp produce parser & delivery scheduling</sub><br/><br/>
      <img src="Docs/user-guide/img/13-order-new.png" width="95%" alt="Customer Orders" />
    </td>
    <td width="50%" align="center">
      <b>Invoice & Delivery Challan Ledger</b><br/>
      <sub>Live search, print preview, and full void ledger reversal</sub><br/><br/>
      <img src="Docs/user-guide/img/08-bills-history.png" width="95%" alt="Bill History Ledger" />
    </td>
  </tr>
</table>

---

## ⚡ Interactive Technical Walkthrough (Jupyter Notebook)

Explore the application interactively in **[`README.ipynb`](README.ipynb)**. The notebook contains runnable code demonstrations of:

1. **Dynamic Configuration & Zero Hardcoding**: Inspect active business settings loaded from environment variables and database records.
2. **Fast Mandi Billing Engine Simulator**: Live keystroke-by-keystroke calculation (`Qty * Rate`) and automatic gap compaction ($N+1$).
3. **WhatsApp Smart Order Importer**: Heuristic regex token matcher parsing multi-line customer orders.
4. **Double-Entry General Ledger Validator**: Verifies that debits equal credits ($\sum \text{Debits} == \sum \text{Credits}$) on commercial transactions.
5. **PDF Generator & PyMuPDF Viewer**: Generates pixel-perfect ReportLab invoices and renders high-DPI page previews.
6. **Live Traceability Runner**: Interactive display of all 48 automated tests mapped to GitHub Epics and Stories.

---

## 🏗️ Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                 Tkinter / ttk Desktop UI                    │
│   (Keyboard-first, F1-F12 shortcuts, Treeviews, Dialogs)    │
└──────────────────────────────┬──────────────────────────────┘
                               │ In-process synchronous calls
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  Application Service Layer                  │
│    (Business rules, calculations, validation, invariants)   │
└──────────────────────────────┬──────────────────────────────┘
                               │ Query / Command execution
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  Repository Layer (PyMongo)                 │
│      (Direct binding to pre-existing sv_billing collections) │
└──────────────────────────────┬──────────────────────────────┘
                               │ Direct MongoDB wire protocol
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             Pre-Existing MongoDB Collections                │
│    (Local port 27018 / Standalone or MongoDB Atlas Cluster) │
└──────────────────────────────┴──────────────────────────────┘
```

* **Zero Web Overhead**: No Next.js, Node.js, Electron, FastAPI, Chromium, or REST API latency.
* **Instant Sub-Second Startup**: Optimized for busy mandi counter PCs.
* **Database Compatibility**: Direct binding to pre-existing MongoDB collections with graceful transaction fallbacks.

---

## 🚀 Quick Start & Launchers

### One-Click Launchers (Automated Dependency & MongoDB Check)
Self-healing launchers verify Python packages, check for MongoDB on port 27018, auto-start the local database daemon if needed, and start the app:

* **Windows PowerShell**:
  ```powershell
  .\start.ps1
  ```
* **Windows Command Prompt / Batch**:
  ```cmd
  start.bat
  ```
* **Linux / macOS Bash**:
  ```bash
  ./start.sh
  ```

### Manual Run
```bash
# 1. Install dependencies
python -m pip install -r requirements.txt

# 2. Seed database (idempotent, only inserts missing records)
python scripts/seed_database.py

# 3. Launch application
python main.py
```

---

## 🧪 Automated Test Suite & Traceability Alignment

Every automated test is mapped to a specific **Epic**, **User Story**, and **Task** on [sirajpasha/BillDesk_DesktopApp Issues](https://github.com/sirajpasha/BillDesk_DesktopApp/issues).

To run all 48 tests with the terminal traceability report:
```bash
python -m pytest tests/ -v
# or standalone runner:
python tests/run_traceability_tests.py
```

### Traceability Summary Table

| Status | Epic | User Story | Task | Automated Test Script | Task Note | GitHub Issue |
| :---: | :--- | :--- | :---: | :--- | :--- | :---: |
| **✔ PASS** | `EPIC-01` | Story-01.1 | `Task-1.1.1` | `test_powershell_launcher_check_only` | Validates PowerShell launcher syntax and dependency verification (`start.ps1`) | [#26](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/26) |
| **✔ PASS** | `EPIC-01` | Story-01.1 | `Task-1.1.2` | `test_batch_launcher_check_only` | Validates Windows batch launcher syntax and mongod environment checks (`start.bat`) | [#26](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/26) |
| **✔ PASS** | `EPIC-01` | Story-01.1 | `Task-1.1.3` | `test_bash_launcher_check_only` | Validates Linux/macOS bash launcher syntax and process launching (`start.sh`) | [#26](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/26) |
| **✔ PASS** | `EPIC-01` | Story-01.2 | `Task-1.2.1` | `test_main_window_all_views_initialization` | Initializes all main window navigation frames and confirms zero runtime errors | [#27](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/27) |
| **✔ PASS** | `EPIC-01` | Story-01.2 | `Task-1.2.1` | `test_all_ui_views_visual_structure` | Validates layout and widgets across Dashboard, Billing, History, Masters, Inventory | [#27](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/27) |
| **✔ PASS** | `EPIC-02` | Story-02.1 | `Task-2.1.1` | `test_code_entered_fetches_item_and_focuses_qty` | Code entry auto-fetches Item Name, default unit, pricing, and shifts focus to Qty | [#3](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/3) |
| **✔ PASS** | `EPIC-02` | Story-02.1 | `Task-2.1.2` | `test_qty_entered_focuses_unit` | Pressing Enter on Qty field shifts keyboard focus directly to Unit dropdown | [#3](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/3) |
| **✔ PASS** | `EPIC-02` | Story-02.1 | `Task-2.1.3` | `test_unit_entered_or_selected_focuses_rate` | Selecting or pressing Enter on Unit shifts keyboard focus to Rate entry | [#3](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/3) |
| **✔ PASS** | `EPIC-02` | Story-02.1 | `Task-2.1.4` | `test_realtime_rate_calculation_keystroke_by_keystroke` | Keystroke-by-keystroke real-time rate calculation updates line total instantly | [#3](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/3) |
| **✔ PASS** | `EPIC-02` | Story-02.2 | `Task-2.2.1` | `test_gap_compaction_moves_item_to_first_empty_row` | Out-of-order line entry (e.g. row 10) shifts to row 1 without leaving blank rows | [#4](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/4) |
| **✔ PASS** | `EPIC-02` | Story-02.2 | `Task-2.2.1` | `test_gap_compaction_with_preexisting_rows` | Entering item at row 10 when rows 1-2 are filled shifts smoothly to row 3 (N+1) | [#4](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/4) |
| **✔ PASS** | `EPIC-02` | Story-02.2 | `Task-2.2.3` | `test_dynamic_row_creation_at_table_end` | Completing the final visible row in the table dynamically appends a new row | [#4](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/4) |
| **✔ PASS** | `EPIC-02` | Story-02.1 | `Task-2.1.2` | `test_bill_line_qty_mutation_recalculates_and_cascades` | Mutating line Qty recalculates amount, bill total, updates stock in inventory, and logs audit | [#3](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/3) |
| **✔ PASS** | `EPIC-02` | Story-02.1 | `Task-2.1.4` | `test_bill_line_rate_mutation_recalculates_and_cascades` | Mutating line Rate recalculates total and balance due while keeping inventory invariant | [#3](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/3) |
| **✔ PASS** | `EPIC-02` | Story-02.3 | `Task-2.3.1` | `test_invoice_number_format` | Verifies invoice numbering follows strictly formatted mandi sequence `YYYYMMDD-XXXX` | [#2](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/2) |
| **✔ PASS** | `EPIC-02` | Story-02.3 | `Task-2.3.1` | `test_bill_mandi_fee_and_commission_mutation_cascades` | Mutating Mandi Cess (1%) and Commission recalculates total bill and customer ledger balance | [#2](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/2) |
| **✔ PASS** | `EPIC-02` | Story-02.3 | `Task-2.3.2` | `test_bill_customer_credit_limit_validation` | Customer credit limit validation warns/blocks when balance exceeds credit limit | [#2](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/2) |
| **✔ PASS** | `EPIC-02` | Story-02.3 | `Task-2.3.3` | `test_payment_allocation_mutation_cascades` | Recording payment reduces bill balance due, transitions status, and updates AR | [#2](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/2) |
| **✔ PASS** | `EPIC-03` | Story-03.2 | `Task-3.2.2` | `test_void_bill_reversal_cascade` | Voiding a bill marks status void, restores inventory stock, and posts contra entries | [#7](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/7) |
| **✔ PASS** | `EPIC-04` | Story-04.1 | `Task-4.1.1` | `test_order_form_view_structure` | Validates OrderFormView layout and input fields matching screenshot `13-order-new.png` | [#9](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/9) |
| **✔ PASS** | `EPIC-04` | Story-04.1 | `Task-4.1.2` | `test_order_form_code_entered_fetches_item_and_focuses_qty` | Order Form auto-fetches Item Name, master Unit, and resolved Rate on Code Enter, focusing Qty | [#9](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/9) |
| **✔ PASS** | `EPIC-04` | Story-04.1 | `Task-4.1.3` | `test_order_form_load_order_for_edit` | Loads existing order document into the order form table for editing and recalculation | [#9](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/9) |
| **✔ PASS** | `EPIC-04` | Story-04.1 | `Task-4.1.4` | `test_order_form_qty_and_unit_navigation` | Order Form keyboard navigation traverses from Qty to Unit, and from Unit to Rate | [#9](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/9) |
| **✔ PASS** | `EPIC-04` | Story-04.1 | `Task-4.1.5` | `test_order_form_realtime_rate_calculation_keystroke_by_keystroke` | Order Form recalculates Line Amount and Grand Total keystroke-by-keystroke when typing Rate | [#9](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/9) |
| **✔ PASS** | `EPIC-04` | Story-04.1 | `Task-4.1.6` | `test_order_form_gap_compaction_moves_to_first_empty_row` | Order Form compacts row gaps on Rate Enter, shifting out-of-order lines to first available slot | [#9](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/9) |
| **✔ PASS** | `EPIC-04` | Story-04.1 | `Task-4.1.7` | `test_order_form_dynamic_row_creation_at_table_end` | Order Form dynamically adds and enables new row when reaching table boundary on Rate Enter | [#9](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/9) |
| **✔ PASS** | `EPIC-04` | Story-04.1 | `Task-4.1.8` | `test_order_form_delete_row_shifts_up` | Order Form row delete button clears row, shifts subsequent rows up, and recalculates totals | [#9](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/9) |
| **✔ PASS** | `EPIC-04` | Story-04.2 | `Task-4.2.1` | `test_order_form_smart_importer_and_recalc` | Freeform multi-line WhatsApp order parser extracting item names, units, and quantities | [#10](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/10) |
| **✔ PASS** | `EPIC-04` | Story-04.3 | `Task-4.3.1` | `test_order_status_lifecycle_and_conversion_cascade` | Validates order lifecycle (`draft` -> `confirmed` -> `billed`) and bill conversion | [#8](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/8) |
| **✔ PASS** | `EPIC-05` | Story-05.1 | `Task-5.1.1` | `test_customer_master_dc_company_fetching` | Customer Master form fetches, displays, and saves DC Company Name (`bill_to_name`) | [#12](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/12) |
| **✔ PASS** | `EPIC-05` | Story-05.2 | `Task-5.2.2` | `test_fixed_pricing_contract_rate_resolution` | Pricing service resolves customer-specific contract rates prior to default item rates | [#29](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/29) |
| **✔ PASS** | `EPIC-06` | Story-06.1 | `Task-6.1.1` | `test_render_invoice_html` | Validates invoice document data structure and HTML fallback rendering | [#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14) |
| **✔ PASS** | `EPIC-06` | Story-06.2 | `Task-6.1.2` | `test_render_dc_html` | Validates delivery challan data structure and HTML fallback rendering | [#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14) |
| **✔ PASS** | `EPIC-06` | Story-06.1 | `Task-6.1.1` | `test_generate_invoice_pdf_file` | Generates authentic ReportLab PDF Invoice file matching `Inv- 20260911-0006.pdf` | [#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14) |
| **✔ PASS** | `EPIC-06` | Story-06.2 | `Task-6.1.2` | `test_generate_dc_pdf_file` | Generates authentic ReportLab Delivery Challan PDF file matching `DC- 20260911-0006.pdf` | [#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14) |
| **✔ PASS** | `EPIC-06` | Story-06.2 | `Task-6.1.2` | `test_attached_anna_adarsh_dc` | Verifies sample Anna Adarsh hostel delivery challan renders with exact item lines | [#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14) |
| **✔ PASS** | `EPIC-06` | Story-06.1 | `Task-6.1.1` | `test_attached_kids_clinic_dc_and_invoice` | Verifies sample Kids Clinic invoice and DC render correctly with customer details | [#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14) |
| **✔ PASS** | `EPIC-06` | Story-06.1 | `Task-6.1.4` | `test_date_helpers` | Validates date parsing, weekly/monthly range helpers, and statement period formatting | [#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14) |
| **✔ PASS** | `EPIC-06` | Story-06.1 | `Task-6.1.4` | `test_consolidated_report_aggregation` | Aggregation engine calculates net bill amounts, payments, and balances across dates | [#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14) |
| **✔ PASS** | `EPIC-06` | Story-06.1 | `Task-6.1.4` | `test_unique_bill_to_entities` | Distinct grouping and statement separation by Delivery Challan entity (`bill_to_name`) | [#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14) |
| **✔ PASS** | `EPIC-06` | Story-06.1 | `Task-6.1.4` | `test_generate_consolidated_pdf` | Generates high-fidelity consolidated periodic customer statement PDF | [#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14) |
| **✔ PASS** | `EPIC-06` | Story-06.1 | `Task-6.1.4` | `test_consolidated_report_ui_frame` | ConsolidatedReportFrame renders customer selectors, date pickers, and queries | [#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14) |
| **✔ PASS** | `EPIC-06` | Story-06.2 | `Task-6.2.1` | `test_print_preview_dialog` | PrintPreviewDialog renders PDF pages using PyMuPDF (`fitz`) with zoom & print controls | [#15](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/15) |
| **✔ PASS** | `EPIC-07` | Story-07.1 | `Task-7.1.1` | `test_general_ledger_double_entry_invariants` | Fundamental accounting invariant: sum of Debits == sum of Credits for every journal posting | [#31](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/31) |
| **✔ PASS** | `EPIC-07` | Story-07.2 | `Task-7.2.1` | `test_procurement_grn_and_tds_purchase_bill_cascade` | GRN creation increases warehouse stock, creates purchase bill, and calculates TDS deduction | [#32](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/32) |
| **✔ PASS** | `EPIC-07` | Story-07.3 | `Task-7.3.1` | `test_inventory_manual_adjustment_mutation_cascades` | Manual stock adjustment updates inventory on hand and logs audit trail | [#33](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/33) |
| **✔ PASS** | `EPIC-07` | Story-07.3 | `Task-7.3.1` | `test_inventory_service_waste_tracking` | Logging perishable produce spoilage/waste decreases stock and books write-off expense | [#33](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/33) |
| **✔ PASS** | `EPIC-07` | Story-07.3 | `Task-7.3.2` | `test_cash_session_and_drawer_variance` | Cash drawer session calculates expected cash, compares with counted cash, and logs variance | [#33](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/33) |

**Overall Verification: 48/48 Tasks Passed (100% Green). All mapped GitHub issues are verified and CLOSED.**

---

## 🎯 Epics & Agile Roadmap

Tracked on [sirajpasha/BillDesk_DesktopApp Issues](https://github.com/sirajpasha/BillDesk_DesktopApp/issues):

| Epic | Scope & User Stories | Status |
| :--- | :--- | :---: |
| **[EPIC-01: Core GUI Shell & Launchers](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/1)** | Multiplatform self-healing launchers, responsive shell, RBAC login | `Closed (Completed)` |
| **[EPIC-02: Fast Mandi Billing Engine](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/2)** | Keyboard traversal, keystroke calculations, gap compaction, mandi cess | `Closed (Completed)` |
| **[EPIC-03: Bill History & Reversals](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/5)** | Ledger view matching screenshot 08, search, void cascading reversal | `Closed (Completed)` |
| **[EPIC-04: Customer Order Management](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/8)** | Order form matching screenshot 13, WhatsApp smart importer, bill conversion | `Closed (Completed)` |
| **[EPIC-05: Master Data Management](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/11)** | Customer Master (`bill_to_name`), Item Master (aliases 101-167), Supplier Master | `Closed (Completed)` |
| **[EPIC-06: PDF Printing & Preview](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/13)** | Thermal & A4 Invoice, Delivery Challan, Consolidated PDF, PyMuPDF preview | `Closed (Completed)` |
| **[EPIC-07: Enterprise Financial Ledger](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/16)** | Double-entry GL, Trial Balance, P&L, Procurement GRN, Waste logs, Cash drawer | `Closed (Completed)` |
| **[EPIC-08: Desktop Packaging & Auto-Build](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/17)** | Standalone PyInstaller binary, Inno Setup installer (`BillDesk-Setup.exe`) | `Open (In Progress)` |
| **[EPIC-09: Hardware Integrations](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/20)** | Raw ESC/POS thermal printing, electronic weighing scale serial RS-232 reader | `Open (Planned)` |
| **[EPIC-10: Omnichannel Messaging & OCR](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/23)** | WhatsApp Cloud API PDF dispatch, local Tesseract OCR paper invoice digitizer | `Open (Planned)` |

---

## 📚 Documentation Reference

* **[`README.ipynb`](README.ipynb)**: Interactive Jupyter Notebook walkthrough with runnable code.
* **[`Docs/TEST_TRACEABILITY_REPORT.md`](Docs/TEST_TRACEABILITY_REPORT.md)**: Full automated test traceability matrix.
* **[`Docs/EPICS_USER_STORIES_TASKS.md`](Docs/EPICS_USER_STORIES_TASKS.md)**: Complete requirements and issue traceability matrix.
* **[`Docs/CONTEXT_AND_IMPLEMENTATION_PLAN.md`](Docs/CONTEXT_AND_IMPLEMENTATION_PLAN.md)**: Architecture context and implementation plan.
* **[`Docs/USER_GUIDE.md`](Docs/USER_GUIDE.md)**: Illustrated user guide following a working mandi day.
* **[`Docs/BillDesk-Native-Desktop-PRD.md`](Docs/BillDesk-Native-Desktop-PRD.md)**: Product requirements document.
