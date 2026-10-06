# ==============================================================================
# Script to populate GitHub Issues as Epics, User Stories, and Tasks
# for sirajpasha/BillDesk_DesktopApp
# ==============================================================================

$p = "protocol=https`nhost=github.com`n" | git credential fill
$token = ($p | Select-String "password=(.+)").Matches.Groups[1].Value
$headers = @{
    "Authorization" = "Bearer $token"
    "Accept" = "application/vnd.github+json"
    "User-Agent" = "BillDesk-DesktopApp-Agent"
}

$repoUrl = "https://api.github.com/repos/sirajpasha/BillDesk_DesktopApp/issues"

function Create-Issue($title, $body, $labels, [bool]$isClosed = $false) {
    $payload = @{
        title = $title
        body = $body
        labels = $labels
    } | ConvertTo-Json -Depth 5

    try {
        $res = Invoke-RestMethod -Uri $repoUrl -Headers $headers -Method Post -Body $payload -ContentType "application/json"
        Write-Host "[CREATED] Issue #$($res.number): $title"
        if ($isClosed) {
            Start-Sleep -Milliseconds 200
            $closePayload = @{ state = "closed"; state_reason = "completed" } | ConvertTo-Json
            Invoke-RestMethod -Uri "$repoUrl/$($res.number)" -Headers $headers -Method Patch -Body $closePayload -ContentType "application/json" | Out-Null
            Write-Host "          -> Closed as completed"
        }
        Start-Sleep -Milliseconds 400
        return $res.number
    } catch {
        Write-Host "[ERROR] Failed to create issue: $($_.Exception.Message)"
        return $null
    }
}

Write-Host "Creating Epics and User Stories..."

# --- COMPLETED EPICS & STORIES ---

# EPIC 2
Create-Issue -title "[EPIC-02] Fast Mandi Billing Engine & Interactive Spreadsheet Form" `
    -body @"
## Epic Description
Ultra-fast, keyboard-driven mandi billing table with automated field navigation, real-time keystroke rate calculation, gap compaction, dynamic row expansion, customer credit limit alerts, mandi cess, and multi-mode payment settlement.

### Implemented Capabilities
- [x] Full-width 18-row responsive line item entry grid matching high-speed mandi POS requirements
- [x] Keyboard traversal: Code -> Enter -> Item Name fetch -> Qty -> Enter -> Unit -> Enter -> Rate -> Amount
- [x] Real-time line item total calculation on each keystroke of Rate entry
- [x] Out-of-order entry gap compaction (moves item to next available row N+1)
- [x] Row deletion with automatic shift-up and re-indexing
- [x] Dynamic row addition on table exhaustion
- [x] Mandi cess (1%), Commission (0%), Customer credit limit validation, and round-off calculation
- [x] Multi-payment mode handling: Cash, UPI, Credit, Bank Transfer

### Acceptance Criteria
- Verified by unit tests in `tests/test_billing_interaction.py` and `tests/test_field_mutation_cascade.py`.
"@ `
    -labels @("epic", "status:completed") -isClosed $true

# Stories for Epic 2
Create-Issue -title "[Story-02.1] Keyboard-First Line Item Entry & Navigation" `
    -body @"
**As a** Mandi billing operator,
**I want to** enter items rapidly using only the keyboard (Code -> Qty -> Unit -> Rate),
**So that** I can process customer orders during peak auction rush in seconds.

### Tasks
- [x] Task 2.1.1: Implement `_on_code_entered` to auto-resolve item by alias/id and pre-fill default unit & rate.
- [x] Task 2.1.2: Bind Return and Tab keys to jump sequentially between Code, Qty, Unit, Rate.
- [x] Task 2.1.3: Real-time calculation callback recalculating Line Total on every rate keystroke.
"@ `
    -labels @("user-story", "status:completed") -isClosed $true

Create-Issue -title "[Story-02.2] Intelligent Gap Compaction & Dynamic Row Management" `
    -body @"
**As a** billing cashier,
**I want** items entered in arbitrary rows to automatically move up without leaving blank lines,
**So that** the printed bill and database records remain compact and orderly.

### Tasks
- [x] Task 2.2.1: Implement `_compact_row_gap` to detect first empty row and shift entered line item.
- [x] Task 2.2.2: Implement `_delete_row_and_shift_up` with confirmation and line renumbering.
- [x] Task 2.2.3: Implement `_add_row` to automatically append new rows when user reaches the end of the table.
"@ `
    -labels @("user-story", "status:completed") -isClosed $true

# EPIC 3
Create-Issue -title "[EPIC-03] Bill History, Audit Ledger & Financial Reversals" `
    -body @"
## Epic Description
Authentic invoice history view matching design screenshot `08-bills-history.png`, real-time invoice filtering, print actions, and cascading financial reversals for voided bills.

### Implemented Capabilities
- [x] Search & filter bar: Date picker, live search across Invoice #, Customer Name, Bill-to Phone
- [x] Bills table with Invoice Date, Bill #, Customer Name, Phone, Items, Total, Payment Status
- [x] Contextual actions: View Details, Print Invoice, Print Delivery Challan, Void Bill, Export CSV
- [x] Full-lifecycle void bill handling: status update to 'void', inventory stock restoration, general ledger contra-entries

### Acceptance Criteria
- Verified by `tests/test_ui_visual_structure.py` and `tests/test_field_mutation_cascade.py`.
"@ `
    -labels @("epic", "status:completed") -isClosed $true

Create-Issue -title "[Story-03.1] Authentic Bill History View & Search" `
    -body @"
**As an** accountant or shop owner,
**I want to** view past bills and filter them by date and customer,
**So that** I can track daily collections and reprint bills on demand.

### Tasks
- [x] Task 3.1.1: Build `BillHistoryFrame` with visual layout matching `08-bills-history.png`.
- [x] Task 3.1.2: Implement debounce search across multiple fields (Invoice #, Name, Phone).
- [x] Task 3.1.3: Wire quick actions for viewing details and launching print previews.
"@ `
    -labels @("user-story", "status:completed") -isClosed $true

Create-Issue -title "[Story-03.2] Void Bill Cascading Reversal & Audit Integrity" `
    -body @"
**As an** administrator,
**I want to** void incorrectly created bills with complete financial reversals,
**So that** stock and accounting books remain accurate without manual ledger editing.

### Tasks
- [x] Task 3.2.1: Implement void confirmation modal and bill state transition.
- [x] Task 3.2.2: Automatically restore inventory batch quantities for all voided line items.
- [x] Task 3.2.3: Generate balancing contra journal entries in General Ledger.
"@ `
    -labels @("user-story", "status:completed") -isClosed $true

# EPIC 4
Create-Issue -title "[EPIC-04] Customer Order Management & WhatsApp Smart Importer" `
    -body @"
## Epic Description
Order booking module matching design screenshot `13-order-new.png`, smart NLP importer for parsing customer WhatsApp messages into structured order items, and one-click bill conversion.

### Implemented Capabilities
- [x] Customer order creation view with Customer selection, Order Date, Delivery Date, Delivery Slot, and Notes
- [x] Smart Importer dialog parsing freeform multi-line WhatsApp messages into item name, unit, and quantity
- [x] Interactive item lines table with search dialog and real-time total estimation
- [x] Order lifecycle tracking: Draft -> Confirmed -> Billed -> Delivered -> Cancelled
- [x] One-click conversion of Confirmed Orders into active Mandi Bills

### Acceptance Criteria
- Verified by `tests/test_order_form.py`.
"@ `
    -labels @("epic", "status:completed") -isClosed $true

Create-Issue -title "[Story-04.1] Visual Order Form matching UI Guide" `
    -body @"
**As an** order booking agent,
**I want to** create customer orders with delivery dates, priorities, and line items,
**So that** procurement and delivery schedules can be planned ahead of mandi auctions.

### Tasks
- [x] Task 4.1.1: Implement `OrderFormView` layout matching screenshot `13-order-new.png`.
- [x] Task 4.1.2: Add item picker dialog with live category filtering and search.
- [x] Task 4.1.3: Save order to MongoDB and emit order created events.
"@ `
    -labels @("user-story", "status:completed") -isClosed $true

Create-Issue -title "[Story-04.2] WhatsApp Freeform Order Smart Importer" `
    -body @"
**As an** operator receiving orders over WhatsApp,
**I want to** paste the message text into a smart importer,
**So that** items and quantities are automatically matched without manual typing.

### Tasks
- [x] Task 4.2.1: Build regex and heuristic parser for lines like 'Apple 5kg', '102 10kg', 'Tomato 2 boxes'.
- [x] Task 4.2.2: Fuzzy-match extracted tokens against Item Master aliases and names.
- [x] Task 4.2.3: Populate imported rows into the order line items table with validation indicators.
"@ `
    -labels @("user-story", "status:completed") -isClosed $true

# EPIC 5
Create-Issue -title "[EPIC-05] Master Data Management (Customer, Item, Supplier, RBAC)" `
    -body @"
## Epic Description
Comprehensive CRUD management for Customers, Items, Suppliers, and Users with dynamic configuration and persistent database storage.

### Implemented Capabilities
- [x] Customer Master: Credit limits, WhatsApp, phone, email, and Delivery Challan Company Name (`bill_to_name`)
- [x] Item Master: Fruit/Veg categories, numeric aliases (101-167), default units, and baseline rates
- [x] Supplier Master: Vendor details, GSTIN, and bank accounts
- [x] User Management & RBAC: Password hashing, role assignments (Admin, Manager, User)
- [x] Dynamic database seeder (`scripts/seed_database.py`) and seed definitions (`data/seed_data.json`)

### Acceptance Criteria
- Verified by `tests/test_ui_visual_structure.py`.
"@ `
    -labels @("epic", "status:completed") -isClosed $true

Create-Issue -title "[Story-05.1] Customer Master with DC Company (`bill_to_name`) & Credit Limits" `
    -body @"
**As a** sales administrator,
**I want to** configure customer details including their Delivery Challan entity name and credit limits,
**So that** invoices and delivery notes reflect the proper entity and credit limits are enforced.

### Tasks
- [x] Task 5.1.1: Add `bill_to_name` field to Customer model and persistence repository.
- [x] Task 5.1.2: Populate `bill_to_name` input in Customer Master form and fetch on edit.
- [x] Task 5.1.3: Integrate credit limit validation into billing workflow.
"@ `
    -labels @("user-story", "status:completed") -isClosed $true

# EPIC 6
Create-Issue -title "[EPIC-06] Pixel-Perfect PDF Printing, Delivery Challan & Print Preview" `
    -body @"
## Epic Description
High-fidelity thermal and A4 PDF invoice generation matching attached live business documents, Delivery Challan (DC) generation, consolidated statements, and native print preview dialog.

### Implemented Capabilities
- [x] Invoice PDF generator (`app/printing/invoice.py`) matching live sample `Inv- 20260911-0006.pdf`
- [x] Delivery Challan PDF generator matching live sample `DC- 20260911-0006.pdf`
- [x] Consolidated periodic customer statements (`app/printing/consolidated.py`)
- [x] Native in-app Print Preview dialog (`app/ui/print_preview.py`) using PyMuPDF (fitz)
- [x] Number-to-words currency formatting in Indian numbering format (Lakhs / Crores)

### Acceptance Criteria
- Verified by `tests/test_pdf_printing.py`, `tests/test_print_preview.py`, and `tests/test_consolidated_billing.py`.
"@ `
    -labels @("epic", "status:completed") -isClosed $true

Create-Issue -title "[Story-06.1] Authentic Invoice & Delivery Challan PDF Generator" `
    -body @"
**As a** business owner,
**I want** generated invoices and Delivery Challans to exactly match my established printed format,
**So that** customers and delivery drivers receive professional, legally compliant documents.

### Tasks
- [x] Task 6.1.1: Implement ReportLab canvas and table layout matching `Inv- 20260911-0006.pdf`.
- [x] Task 6.1.2: Implement Delivery Challan layout omitting rates/amounts as per `DC- 20260911-0006.pdf`.
- [x] Task 6.1.3: Include Tamil / Indian number-to-words conversion and bank details.
"@ `
    -labels @("user-story", "status:completed") -isClosed $true

Create-Issue -title "[Story-06.2] Native In-App Print Preview Dialog with Zoom & Print" `
    -body @"
**As a** cashier,
**I want to** preview generated invoices inside the application before printing,
**So that** I can verify line items and print directly to the default printer.

### Tasks
- [x] Task 6.2.1: Render PDF pages to high-DPI images using PyMuPDF (`fitz`).
- [x] Task 6.2.2: Add Zoom In, Zoom Out, Fit to Page, and Page Navigation controls.
- [x] Task 6.2.3: Trigger Windows native printing spooler directly from dialog.
"@ `
    -labels @("user-story", "status:completed") -isClosed $true

# EPIC 7
Create-Issue -title "[EPIC-07] Enterprise Financial Ledger, Inventory & Procurement" `
    -body @"
## Epic Description
Integrated double-entry accounting engine, balance sheet, trial balance, procurement Goods Receipt Notes (GRN), perishable stock waste tracking, and cashier drawer management.

### Implemented Capabilities
- [x] Double-entry general ledger with automated journal entries for sales, purchases, and receipts
- [x] Trial Balance, Profit & Loss, and Balance Sheet report generation
- [x] Bank Reconciliation Statement (BRS) module
- [x] Procurement Goods Receipt Notes (GRN), TDS calculation, and purchase bills
- [x] Inventory stock adjustments, perishable waste tracking, and physical inventory audits
- [x] Cash drawer sessions, opening balances, and handover reports

### Acceptance Criteria
- Verified by `tests/test_field_mutation_cascade.py`.
"@ `
    -labels @("epic", "status:completed") -isClosed $true


# --- INCOMPLETE & FUTURE ROADMAP EPICS ---

# EPIC 8 (In Progress / Next Up)
Create-Issue -title "[EPIC-08] Desktop Packaging, Auto-Build & Production Distribution" `
    -body @"
## Epic Description
Automated build pipeline packaging the Python native Tkinter application, embedded MongoDB server, and assets into a standalone Windows executable and Inno Setup installer.

### Scope & Planned User Stories
- [ ] **Story 8.1**: PyInstaller Single-Directory & OneFile Windows Build Pipeline
- [ ] **Story 8.2**: Inno Setup One-Click Desktop Installer (`BillDesk-Setup.exe`)
- [ ] **Story 8.3**: Automated GitHub Actions CI/CD Release Workflow

### Tasks
- [x] Task 8.1.1: Create base Inno Setup configuration (`installer/BillDesk.iss`).
- [ ] Task 8.1.2: Create `build_desktop.ps1` utilizing PyInstaller to bundle Tkinter, PyMuPDF, ReportLab, and `app/assets/`.
- [ ] Task 8.1.3: Bundle embedded MongoDB Community binary (`resources/mongo/win32-x64/mongod.exe`) into installer.
- [ ] Task 8.1.4: Configure single-instance application mutex and auto-update checks.

### Target Milestone: v1.1.0
"@ `
    -labels @("epic", "status:in-progress") -isClosed $false

Create-Issue -title "[Story-08.1] PyInstaller Windows Standalone Build Pipeline" `
    -body @"
**As an** administrator or technician,
**I want to** build a standalone binary distribution of BillDesk,
**So that** client machines do not need Python or manual package installations.

### Tasks
- [ ] Task 8.1.1: Configure PyInstaller spec file bundling Tkinter, PyMuPDF, ReportLab, and assets.
- [ ] Task 8.1.2: Add PowerShell build script with automated clean and verification checks.
- [ ] Task 8.1.3: Validate application startup from clean Windows sandbox without Python installed.
"@ `
    -labels @("user-story", "status:in-progress") -isClosed $false

Create-Issue -title "[Story-08.2] Inno Setup Windows One-Click Installer" `
    -body @"
**As an** end-user,
**I want to** install BillDesk with a familiar Windows setup wizard,
**So that** desktop shortcuts and start menu entries are created automatically.

### Tasks
- [x] Task 8.2.1: Write `installer/BillDesk.iss` with per-user lowest privilege mode.
- [ ] Task 8.2.2: Add installer compiler script (`compile_installer.ps1`) targeting `ISCC.exe`.
- [ ] Task 8.2.3: Test uninstall clean-up preserving database files in `%APPDATA%\BillDesk`.
"@ `
    -labels @("user-story", "status:planned") -isClosed $false

# EPIC 9 (Planned)
Create-Issue -title "[EPIC-09] Hardware Integrations & Direct Thermal Receipt Printing" `
    -body @"
## Epic Description
Direct hardware interfaces for Mandi auction operations: ESC/POS direct thermal receipt printing without print dialogs, and serial/USB electronic weighing scale auto-reading.

### Scope & Planned User Stories
- [ ] **Story 9.1**: Direct ESC/POS 80mm & 58mm Thermal Printer Driver
- [ ] **Story 9.2**: Electronic Weighing Scale Auto-Capture via Serial/USB RS-232

### Tasks
- [ ] Task 9.1.1: Implement raw ESC/POS byte generator for 80mm and 58mm thermal rolls.
- [ ] Task 9.1.2: Add direct printer device selection in settings (USB / Network IP).
- [ ] Task 9.2.1: Implement `SerialScaleReader` listening to COM ports.
- [ ] Task 9.2.2: Automatically populate Billing Qty field with stable scale weight.

### Target Milestone: v1.2.0
"@ `
    -labels @("epic", "status:planned") -isClosed $false

Create-Issue -title "[Story-09.1] Direct ESC/POS Thermal Receipt Printing" `
    -body @"
**As a** high-volume cashier,
**I want to** print bills directly to an 80mm or 58mm thermal receipt printer with zero delay,
**So that** paper receipts are ejected immediately upon bill completion.

### Tasks
- [ ] Task 9.1.1: Implement raw ESC/POS formatting with paper cut and cash drawer kick signals.
- [ ] Task 9.1.2: Add silent print option bypassing the system print preview dialog.
"@ `
    -labels @("user-story", "status:planned") -isClosed $false

Create-Issue -title "[Story-09.2] Electronic Weighing Scale COM Port Auto-Reader" `
    -body @"
**As a** weighmaster at the mandi counter,
**I want** item weight to populate directly from the scale into the bill,
**So that** manual typing errors and weight fraud are eliminated.

### Tasks
- [ ] Task 9.2.1: Add `pyserial` connection handler with baud rate configuration in settings.
- [ ] Task 9.2.2: Trigger reading on F9 or when cursor enters the Qty entry box.
"@ `
    -labels @("user-story", "status:planned") -isClosed $false

# EPIC 10 (Planned)
Create-Issue -title "[EPIC-10] Omnichannel Messaging & Offline OCR Supplier Bill Digitization" `
    -body @"
## Epic Description
Automated digital bill dispatch over WhatsApp and SMS, plus offline OCR scanning for supplier paper invoices using local Tesseract OCR engine.

### Scope & Planned User Stories
- [ ] **Story 10.1**: WhatsApp Cloud API & SMS Customer Delivery
- [ ] **Story 10.2**: Offline Tesseract OCR Paper Bill Digitization

### Tasks
- [ ] Task 10.1.1: WhatsApp Cloud API webhook and template message integration.
- [ ] Task 10.1.2: Send customer PDF download link or payment acknowledgement.
- [ ] Task 10.2.1: Integrate `fetch-tesseract.ps1` binary and `pytesseract` for image recognition.
- [ ] Task 10.2.2: Build OCR Workbench UI for rectifying supplier invoice scans into GRNs.

### Target Milestone: v1.3.0
"@ `
    -labels @("epic", "status:planned") -isClosed $false

Create-Issue -title "[Story-10.1] WhatsApp Cloud API & SMS Customer Delivery" `
    -body @"
**As a** retail customer or restaurant manager,
**I want to** receive my invoice PDF directly on WhatsApp,
**So that** I have instant digital proof without carrying paper bills.

### Tasks
- [ ] Task 10.1.1: Build background dispatch worker with queueing and retry logic.
- [ ] Task 10.1.2: Integrate WhatsApp Cloud API endpoint with template support.
"@ `
    -labels @("user-story", "status:planned") -isClosed $false

Create-Issue -title "[Story-10.2] Offline Tesseract OCR Paper Bill Digitization" `
    -body @"
**As a** procurement manager,
**I want to** photograph or scan supplier paper bills to extract item lines,
**So that** supplier GRN entries are populated automatically without manual data entry.

### Tasks
- [ ] Task 10.2.1: Implement Tesseract image pre-processing (deskew, binarization).
- [ ] Task 10.2.2: Add OCR verification workbench view with side-by-side editing.
"@ `
    -labels @("user-story", "status:planned") -isClosed $false

Write-Host "All Epics, User Stories, and Tasks created successfully on GitHub!"
