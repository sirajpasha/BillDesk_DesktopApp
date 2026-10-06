# BillDesk Desktop — Native Mandi POS & ERP

[![Tests](https://img.shields.io/badge/tests-42%20passed-brightgreen.svg)](#test-suite--quality-assurance)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Database](https://img.shields.io/badge/mongodb-27018%20%7C%20Atlas-green.svg)](https://www.mongodb.com/)
[![GitHub Issues](https://img.shields.io/badge/issues-Epics%20%26%20Stories-purple.svg)](https://github.com/sirajpasha/BillDesk_DesktopApp/issues)

A high-performance, keyboard-driven native desktop Point-of-Sale (POS) and Enterprise Resource Planning (ERP) platform purpose-built for wholesale produce markets, vegetable mandis, and commission agents.

---

## 1. Key Capabilities

* **Keyboard-First Fast Mandi Billing**: Complete invoice entry in seconds using numeric aliases (101–167) and intuitive keyboard navigation:
  `Code -> Enter -> Auto-fetch Item -> Qty -> Enter -> Unit -> Enter -> Rate -> Amount`.
* **Dynamic Keystroke Calculations**: Line total calculates in real-time as each digit of Rate is typed.
* **Intelligent Gap Compaction**: Automatically moves out-of-order line items to the next available empty row ($N+1$) with dynamic table expansion.
* **Pixel-Perfect PDF Generation**: Authentic thermal and A4 PDF Invoices and Delivery Challans (DC) matching live wholesale trade documents.
* **In-App Print Preview**: High-DPI page rendering using PyMuPDF (`fitz`) with zoom, page navigation, and direct printing to the Windows spooler.
* **WhatsApp Smart Order Importer**: NLP and heuristic parser extracting items, units, and quantities from freeform WhatsApp messages into draft orders with one-click bill conversion.
* **Consolidated Billing Statements**: Weekly and monthly billing statements grouped by customer and Delivery Challan entity (`bill_to_name`).
* **Double-Entry General Ledger & Accounting**: Real-time balance sheet, trial balance, profit & loss statements, void bill reversals, and bank reconciliation.
* **Perishable Inventory & Procurement**: Goods Receipt Notes (GRN), TDS calculation, vendor purchase bills, stock adjustments, and waste logs.
* **Cash Drawer Sessions**: Opening cash declaration, live variance tracking, and end-of-shift handover reports.
* **Zero Hardcoded Values**: All settings, units, rates, company info, and database endpoints are configurable via environment variables (`.env`) or database settings.

---

## 2. Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                 Tkinter / ttk Desktop UI                    │
│   (Keyboard-first, F1-F12 shortcuts, Treeviews, Dialogs)    │
└──────────────────────────────┬──────────────────────────────┘
                               │ In-process method calls
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
└─────────────────────────────────────────────────────────────┘
```

* **No Web Overhead**: No Next.js, Node.js, Electron, FastAPI, or Chromium subprocesses.
* **Instant Startup**: Starts in sub-second time on counter desktop machines.
* **Direct Database Wire Protocol**: Pure synchronous PyMongo drivers with explicit transaction and fallback support.

---

## 3. Quick Start & Launchers

### One-Click Launchers (Automated Dependency Check & MongoDB Startup)
The repository includes self-healing startup scripts that automatically verify Python packages, check for local MongoDB (port 27018), start the database daemon if not running, and launch the application:

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

### Manual Launch
```bash
# 1. Install dependencies
python -m pip install -r requirements.txt

# 2. Seed database (optional, for fresh installation)
python scripts/seed_database.py

# 3. Launch application
python main.py
```

---

## 4. Database Initialization & Seeding

To populate initial items (vegetables, fruits with aliases 101–167), sample customers, suppliers, roles, and default users into MongoDB:
```bash
python scripts/seed_database.py
```
* The seeder is **100% idempotent** and only inserts missing records without overwriting existing data.
* Seed templates are defined in [`data/seed_data.json`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/data/seed_data.json) and [`data/items.json`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/data/items.json).

---

## 5. Test Suite & Quality Assurance

The application features a comprehensive test suite asserting UI visual structures, field mutation cascades, double-entry ledger invariants, PDF generation, and launchers:

```bash
# Run all tests
python -m pytest tests/ -v
```

**Results:**
```text
============================= 42 passed in 17.47s =============================
```

---

## 6. Project Management & Agile Roadmap

The project is tracked via Epics, User Stories, and Tasks on GitHub:
👉 **[sirajpasha/BillDesk_DesktopApp Issues Board](https://github.com/sirajpasha/BillDesk_DesktopApp/issues)**

| Epic | Description | Status |
| :--- | :--- | :---: |
| **[EPIC-01](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/1)** | Core GUI Shell, Authentication & Multiplatform Launcher | `Closed (Completed)` |
| **[EPIC-02](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/2)** | Fast Mandi Billing Engine & Interactive Spreadsheet Form | `Closed (Completed)` |
| **[EPIC-03](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/5)** | Bill History, Audit Ledger & Financial Reversals | `Closed (Completed)` |
| **[EPIC-04](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/8)** | Customer Order Management & WhatsApp Smart Importer | `Closed (Completed)` |
| **[EPIC-05](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/11)** | Master Data Management (Customer, Item, Supplier, RBAC) | `Closed (Completed)` |
| **[EPIC-06](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/13)** | Pixel-Perfect PDF Printing, Delivery Challan & Print Preview | `Closed (Completed)` |
| **[EPIC-07](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/16)** | Enterprise Financial Ledger, Inventory & Procurement | `Closed (Completed)` |
| **[EPIC-08](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/17)** | Desktop Packaging, Auto-Build & Production Distribution | `Open (In Progress)` |
| **[EPIC-09](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/20)** | Hardware Integrations & Direct Thermal Receipt Printing | `Open (Planned)` |
| **[EPIC-10](https://github.com/sirajpasha/BillDesk_DesktopApp/issues/23)** | Omnichannel Messaging & Offline OCR Supplier Bill Digitization | `Open (Planned)` |

For full requirements and traceability, see:
* [`Docs/EPICS_USER_STORIES_TASKS.md`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/Docs/EPICS_USER_STORIES_TASKS.md)
* [`Docs/CONTEXT_AND_IMPLEMENTATION_PLAN.md`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/Docs/CONTEXT_AND_IMPLEMENTATION_PLAN.md)
* [`Docs/BillDesk-Native-Desktop-PRD.md`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/Docs/BillDesk-Native-Desktop-PRD.md)
* [`Docs/USER_GUIDE.md`](file:///c:/Users/PashaLOQ/Downloads/BillDesk-Native-Tkinter-27018/desktopapp_native/Docs/USER_GUIDE.md)
