# BillDesk Desktop - Epics, User Stories & Engineering Tasks Matrix

This document tracks all project requirements, user stories, and technical tasks across the development lifecycle, mapped directly to GitHub Issues on [sirajpasha/BillDesk_DesktopApp](https://github.com/sirajpasha/BillDesk_DesktopApp/issues).

---

## Summary Status

| Category | Total | Completed | In Progress | Planned |
| :--- | :---: | :---: | :---: | :---: |
| **Epics** | 10 | 7 | 1 | 2 |
| **User Stories** | 15 | 9 | 1 | 5 |
| **Verification** | 48 Tests Passed | 100% | — | — |

---

## Detailed Breakdown

### EPIC 01: Core GUI Shell, Authentication & Multiplatform Launcher
* **GitHub Issue**: [#1](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/1)
* **Status**: `COMPLETED`
* **Labels**: `epic`, `status:completed`
* **Implementation**: [`app/ui/main_window.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/ui/main_window.py), [`app/ui/login_window.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/ui/login_window.py), [`start.ps1`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/start.ps1), [`start.bat`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/start.bat), [`start.sh`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/start.sh)
* **Tests**: [`tests/test_launcher.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_launcher.py), [`tests/test_ui_visual_structure.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_ui_visual_structure.py)

#### Tasks:
- [x] **Task 1.1**: Multiplatform self-healing launchers (`start.ps1`, `start.bat`, `start.sh`) checking Python packages and auto-starting local MongoDB (port 27018).
- [x] **Task 1.2**: Modern Tkinter main window shell with collapsible sidebar navigation, live digital clock, status bar, and brand icon.
- [x] **Task 1.3**: Authentic login screen matching `01-login.png` with Bcrypt password verification and role-based permissions (Admin, Manager, User).
- [x] **Task 1.4**: Global keyboard shortcuts (F1: Billing, F2: Bills, F3: Orders, F4: Masters, Escape: Exit/Cancel).

---

### EPIC 02: Fast Mandi Billing Engine & Interactive Spreadsheet Form
* **GitHub Issue**: [#2](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/2)
* **Status**: `COMPLETED`
* **Labels**: `epic`, `status:completed`
* **Implementation**: [`app/ui/billing.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/ui/billing.py), [`app/services/billing_service.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/services/billing_service.py), [`app/services/pricing_service.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/services/pricing_service.py)
* **Tests**: [`tests/test_billing_interaction.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_billing_interaction.py), [`tests/test_field_mutation_cascade.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_field_mutation_cascade.py)

#### User Stories:
* **Story 02.1**: Keyboard-First Line Item Entry & Navigation ([#3](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/3)) `[COMPLETED]`
  - [x] **Task 2.1.1**: Enter Item Code (Alias / ID) -> presses Enter -> auto-fetches Item Name, pre-fills default Unit, resolves contract/master Rate, and moves focus directly to Qty.
  - [x] **Task 2.1.2**: Enter Qty -> presses Enter -> moves focus to Unit dropdown.
  - [x] **Task 2.1.3**: Unit selection / Enter -> moves focus to Rate.
  - [x] **Task 2.1.4**: Real-time keystroke rate calculation: Typing digits into Rate recalculates Line Amount on the fly (e.g. typing 6 calculates 6*Qty; typing 5 makes 65*Qty).
* **Story 02.2**: Intelligent Gap Compaction & Dynamic Row Management ([#4](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/4)) `[COMPLETED]`
  - [x] **Task 2.2.1**: Pressing Enter on Rate compacts lines entered out-of-order (e.g. entry on line 10 or 5 shifts smoothly to the next available empty row $N+1$).
  - [x] **Task 2.2.2**: Row deletion shifts all subsequent lines up with automatic row re-numbering.
  - [x] **Task 2.2.3**: Dynamic table growth automatically appending new rows when the cashier exhausts the default table size.
  - [x] **Task 2.2.4**: Mandi cess (1%), Commission (0%), Customer credit limits validation, and payment settlement (Cash, UPI, Credit, Bank).

---

### EPIC 03: Bill History, Audit Ledger & Financial Reversals
* **GitHub Issue**: [#5](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/5)
* **Status**: `COMPLETED`
* **Labels**: `epic`, `status:completed`
* **Implementation**: [`app/ui/history.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/ui/history.py), [`app/repositories/billing_repo.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/repositories/billing_repo.py)
* **Tests**: [`tests/test_ui_visual_structure.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_ui_visual_structure.py), [`tests/test_field_mutation_cascade.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_field_mutation_cascade.py)

#### User Stories:
* **Story 03.1**: Authentic Bill History View & Search ([#6](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/6)) `[COMPLETED]`
  - [x] **Task 3.1.1**: Visual table matching screenshot `08-bills-history.png` with Date, Bill #, Customer Name, Phone, Items count, Total, and Payment Status.
  - [x] **Task 3.1.2**: Live multi-field search and calendar date range filtering.
  - [x] **Task 3.1.3**: Actions menu: View Details, Print Invoice, Print Delivery Challan, Export CSV.
* **Story 03.2**: Void Bill Cascading Reversal & Audit Integrity ([#7](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/7)) `[COMPLETED]`
  - [x] **Task 3.2.1**: Void bill confirmation dialog and audit state transition.
  - [x] **Task 3.2.2**: Automatic stock restoration returning item quantities back to active inventory batches.
  - [x] **Task 3.2.3**: General ledger contra journal entries ensuring balance sheet invariants.

---

### EPIC 04: Customer Order Management & WhatsApp Smart Importer
* **GitHub Issue**: [#8](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/8)
* **Status**: `COMPLETED`
* **Labels**: `epic`, `status:completed`
* **Implementation**: [`app/ui/order_form_view.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/ui/order_form_view.py), [`app/ui/orders_view.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/ui/orders_view.py), [`app/services/order_service.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/services/order_service.py)
* **Tests**: [`tests/test_order_form.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_order_form.py)

#### User Stories:
* **Story 04.1**: Visual Order Form matching UI Guide ([#9](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/9)) `[COMPLETED]`
  - [x] **Task 4.1.1**: Design matching screenshot `13-order-new.png` with Order Date, Delivery Date, Delivery Slot, and Notes.
  - [x] **Task 4.1.2**: Auto-fetch Item Name, default Unit from master, and customer contract Rate on Code Enter, focusing on Qty.
  - [x] **Task 4.1.3**: Order edit mode loading existing order documents and lifecycle status tracking.
  - [x] **Task 4.1.4**: Fluid keyboard navigation across Qty, Unit Combobox, and Rate fields.
  - [x] **Task 4.1.5**: Keystroke-by-keystroke real-time Line Amount and Grand Total recalculation.
  - [x] **Task 4.1.6**: Out-of-order entry gap compaction shifting lines to $N+1$ contiguous position on Rate Enter.
  - [x] **Task 4.1.7**: Dynamic row addition when user completes the last available line.
  - [x] **Task 4.1.8**: Row deletion (`✕`) clearing row, shifting subsequent lines up, and updating totals.
* **Story 04.2**: WhatsApp Freeform Order Smart Importer ([#10](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/10)) `[COMPLETED]`
  - [x] **Task 4.2.1**: Multi-line paste modal parsing freeform text (e.g. `101 5kg`, `Tomato 2 boxes`).
  - [x] **Task 4.2.2**: Intelligent token matcher resolving item aliases and master descriptions.
  - [x] **Task 4.2.3**: Populating parsed items into the order table with validation checks.

---

### EPIC 05: Master Data Management (Customer, Item, Supplier, RBAC)
* **GitHub Issue**: [#11](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/11)
* **Status**: `COMPLETED`
* **Labels**: `epic`, `status:completed`
* **Implementation**: [`app/ui/masters_view.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/ui/masters_view.py), [`app/services/master_service.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/services/master_service.py), [`scripts/seed_database.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/scripts/seed_database.py)
* **Tests**: [`tests/test_ui_visual_structure.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_ui_visual_structure.py)

#### User Stories:
* **Story 05.1**: Customer Master with DC Company (`bill_to_name`) & Credit Limits ([#12](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/12)) `[COMPLETED]`
  - [x] **Task 5.1.1**: Full CRUD for Customer Master including Delivery Challan Company Name (`bill_to_name`).
  - [x] **Task 5.1.2**: Persistent database storage and autofill on Customer selection in Billing & Order forms.
  - [x] **Task 5.1.3**: Item Master managing fruit/veg categories, numeric aliases (101-167), default units, and baseline rates.
  - [x] **Task 5.1.4**: Supplier Master with vendor contact, GSTIN, and banking information.
  - [x] **Task 5.1.5**: Dynamic database seeder (`scripts/seed_database.py`) and schema definitions (`data/seed_data.json`).

---

### EPIC 06: Pixel-Perfect PDF Printing, Delivery Challan & Print Preview
* **GitHub Issue**: [#13](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/13)
* **Status**: `COMPLETED`
* **Labels**: `epic`, `status:completed`
* **Implementation**: [`app/printing/invoice.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/printing/invoice.py), [`app/printing/consolidated.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/printing/consolidated.py), [`app/ui/print_preview.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/ui/print_preview.py)
* **Tests**: [`tests/test_pdf_printing.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_pdf_printing.py), [`tests/test_print_preview.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_print_preview.py), [`tests/test_consolidated_billing.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_consolidated_billing.py)

#### User Stories:
* **Story 06.1**: Authentic Invoice & Delivery Challan PDF Generator ([#14](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/14)) `[COMPLETED]`
  - [x] **Task 6.1.1**: ReportLab canvas layout matching live invoice sample `Inv- 20260911-0006.pdf` and screenshot `48-invoice-print.png`.
  - [x] **Task 6.1.2**: ReportLab Delivery Challan layout matching live DC sample `DC- 20260911-0006.pdf` (omitting rates and amounts).
  - [x] **Task 6.1.3**: Number-to-words currency formatting in Indian numbering format (Lakhs/Crores).
  - [x] **Task 6.1.4**: Consolidated weekly/monthly statements grouped by customer and bill-to entity.
* **Story 06.2**: Native In-App Print Preview Dialog with Zoom & Print ([#15](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/15)) `[COMPLETED]`
  - [x] **Task 6.2.1**: High-DPI PDF page rasterization using PyMuPDF (`fitz`).
  - [x] **Task 6.2.2**: In-dialog Zoom In, Zoom Out, Fit to Page, Fit to Width, and Page Navigation.
  - [x] **Task 6.2.3**: One-click direct print button invoking the Windows printer spooler.

---

### EPIC 07: Enterprise Financial Ledger, Inventory & Procurement
* **GitHub Issue**: [#16](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/16)
* **Status**: `COMPLETED`
* **Labels**: `epic`, `status:completed`
* **Implementation**: [`app/ui/finance_view.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/ui/finance_view.py), [`app/ui/inventory_view.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/ui/inventory_view.py), [`app/ui/procurement_view.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/ui/procurement_view.py), [`app/services/ledger_service.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/app/services/ledger_service.py)
* **Tests**: [`tests/test_field_mutation_cascade.py`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/tests/test_field_mutation_cascade.py)

#### Tasks:
- [x] **Task 7.1**: General Ledger double-entry engine generating automated journal entries for sales, purchases, and receipts.
- [x] **Task 7.2**: Financial statements: Trial Balance, Balance Sheet, and Profit & Loss reports.
- [x] **Task 7.3**: Bank Reconciliation Statement (BRS) module for bank statement statement matching.
- [x] **Task 7.4**: Procurement Goods Receipt Notes (GRN), TDS calculation, and vendor payment tracking.
- [x] **Task 7.5**: Perishable stock waste logging, manual inventory adjustments, and physical count reconciliation.
- [x] **Task 7.6**: Cash drawer sessions: Opening balance, drawer variance calculations, and handover reports.

---

### EPIC 08: Desktop Packaging, Auto-Build & Production Distribution
* **GitHub Issue**: [#17](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/17)
* **Status**: `IN PROGRESS`
* **Labels**: `epic`, `status:in-progress`
* **Target Milestone**: `v1.1.0`

#### User Stories:
* **Story 08.1**: PyInstaller Windows Standalone Build Pipeline ([#18](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/18)) `[IN PROGRESS]`
  - [ ] **Task 8.1.1**: Configure PyInstaller spec bundling Tkinter, PyMuPDF, ReportLab, and `app/assets/`.
  - [ ] **Task 8.1.2**: Write PowerShell build script `build_desktop.ps1` with clean, build, and test steps.
  - [ ] **Task 8.1.3**: Validate standalone execution on a clean Windows machine without Python installed.
* **Story 08.2**: Inno Setup Windows One-Click Installer ([#19](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/19)) `[PLANNED]`
  - [x] **Task 8.2.1**: Base Inno Setup installer script written ([`installer/BillDesk.iss`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/installer/BillDesk.iss)).
  - [ ] **Task 8.2.2**: Compile installer with bundled MongoDB server (`resources/mongo/win32-x64/mongod.exe`).
  - [ ] **Task 8.2.3**: Configure desktop shortcuts, start menu entries, and uninstaller data preservation in `%APPDATA%\BillDesk`.

---

### EPIC 09: Hardware Integrations & Direct Thermal Receipt Printing
* **GitHub Issue**: [#20](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/20)
* **Status**: `PLANNED`
* **Labels**: `epic`, `status:planned`
* **Target Milestone**: `v1.2.0`

#### User Stories:
* **Story 09.1**: Direct ESC/POS Thermal Receipt Printing ([#21](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/21)) `[PLANNED]`
  - [ ] **Task 9.1.1**: Raw ESC/POS byte generator supporting 80mm and 58mm thermal paper rolls.
  - [ ] **Task 9.1.2**: Direct USB and Network IP printer output bypassing system print dialog.
  - [ ] **Task 9.1.3**: Automated paper-cut command and cash drawer kick pulse.
* **Story 09.2**: Electronic Weighing Scale COM Port Auto-Reader ([#22](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/22)) `[PLANNED]`
  - [ ] **Task 9.2.1**: Serial RS-232 / USB driver reading live scale weight from digital weighing indicators.
  - [ ] **Task 9.2.2**: Auto-populate billing quantity field upon stable scale weight reading or F9 shortcut.

---

### EPIC 10: Omnichannel Messaging & Offline OCR Supplier Bill Digitization
* **GitHub Issue**: [#23](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/23)
* **Status**: `PLANNED`
* **Labels**: `epic`, `status:planned`
* **Target Milestone**: `v1.3.0`

#### User Stories:
* **Story 10.1**: WhatsApp Cloud API & SMS Customer Delivery ([#24](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/24)) `[PLANNED]`
  - [ ] **Task 10.1.1**: WhatsApp Cloud API integration dispatching invoice PDF links to customer's WhatsApp number.
  - [ ] **Task 10.1.2**: SMS gateway integration for instant payment acknowledgements and outstanding balance alerts.
* **Story 10.2**: Offline Tesseract OCR Paper Bill Digitization ([#25](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/25)) `[PLANNED]`
  - [ ] **Task 10.2.1**: Integrate offline Tesseract engine ([`scripts/fetch-tesseract.ps1`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/scripts/fetch-tesseract.ps1)) for scanned supplier paper bills.
  - [ ] **Task 10.2.2**: Interactive OCR Workbench UI for verifying recognized line items into Goods Receipt Notes (GRN).

---

## Traceability & Verification
All completed user stories and tasks are backed by automated unit and integration tests:
* Run full verification suite: `python -m pytest tests/ -v`
* Total passing tests: **48 tests passed in ~19.5s**
