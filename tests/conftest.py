import os
import sys
import re
import copy
import pytest

# Ensure Windows TCL/TK paths are reliably discovered
tcl_candidate = os.path.join(sys.prefix, "tcl", "tcl8.6")
tk_candidate = os.path.join(sys.prefix, "tcl", "tk8.6")
if os.path.exists(tcl_candidate) and "TCL_LIBRARY" not in os.environ:
    os.environ["TCL_LIBRARY"] = tcl_candidate
if os.path.exists(tk_candidate) and "TK_LIBRARY" not in os.environ:
    os.environ["TK_LIBRARY"] = tk_candidate

@pytest.fixture(autouse=True)
def _isolated_parked_bills_file(tmp_path, monkeypatch):
    """Parked bills are persisted to a file; never let a test touch the real %APPDATA% one."""
    from app.config.settings import settings
    monkeypatch.setattr(settings, "parked_bills_file", str(tmp_path / "parked_bills.json"))


@pytest.fixture(scope="session")
def tk_root():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass

class MockCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, key_or_list, direction=1):
        if isinstance(key_or_list, list):
            for k, d in reversed(key_or_list):
                self._docs.sort(key=lambda x: x.get(k, 0), reverse=(d == -1))
        else:
            self._docs.sort(key=lambda x: x.get(key_or_list, 0), reverse=(direction == -1))
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)

    def __list__(self):
        return list(self._docs)

class MockCollection:
    def __init__(self, name):
        self.name = name
        self.docs = []

    def _matches(self, doc, query):
        if not query:
            return True
        for k, v in query.items():
            if k == "$or":
                if not any(self._matches(doc, branch) for branch in v):
                    return False
            elif isinstance(v, dict):
                val = doc.get(k)
                for op, target in v.items():
                    if op == "$regex":
                        flags = re.IGNORECASE if v.get("$options") == "i" else 0
                        if not re.search(str(target), str(val or ""), flags):
                            return False
                    elif op == "$lte":
                        if val is None or val > target:
                            return False
                    elif op == "$gte":
                        if val is None or val < target:
                            return False
                    elif op == "$in":
                        if val not in target:
                            return False
                    elif op == "$nin":
                        if val in target:
                            return False
                    elif op == "$ne":
                        if val == target:
                            return False
                    elif op == "$exists":
                        if (k in doc) != bool(target):
                            return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    def find_one(self, query=None, sort=None):
        docs = [copy.deepcopy(d) for d in self.docs if self._matches(d, query or {})]
        if sort:
            cursor = MockCursor(docs).sort(sort)
            docs = cursor._docs
        return docs[0] if docs else None

    def find(self, query=None, sort=None):
        docs = [copy.deepcopy(d) for d in self.docs if self._matches(d, query or {})]
        cursor = MockCursor(docs)
        if sort:
            cursor.sort(sort)
        return cursor

    def insert_one(self, doc, session=None):
        stored = copy.deepcopy(doc)
        if "_id" not in stored:
            stored["_id"] = f"id_{len(self.docs) + 1}"
        self.docs.append(stored)
        return stored

    def update_one(self, filter_query, update_doc, session=None):
        for doc in self.docs:
            if self._matches(doc, filter_query):
                if "$inc" in update_doc:
                    for field, inc_val in update_doc["$inc"].items():
                        doc[field] = doc.get(field, 0.0) + inc_val
                if "$set" in update_doc:
                    for field, set_val in update_doc["$set"].items():
                        doc[field] = copy.deepcopy(set_val)
                if "$push" in update_doc:
                    for field, push_val in update_doc["$push"].items():
                        if field not in doc:
                            doc[field] = []
                        doc[field].append(copy.deepcopy(push_val))
                return True
        return False

    def update_many(self, filter_query, update_doc, session=None):
        import types
        n = 0
        for doc in self.docs:
            if self._matches(doc, filter_query):
                for field, set_val in update_doc.get("$set", {}).items():
                    doc[field] = copy.deepcopy(set_val)
                n += 1
        return types.SimpleNamespace(modified_count=n)

    def count_documents(self, query=None):
        return len([d for d in self.docs if self._matches(d, query or {})])

    def delete_one(self, filter_query):
        for idx, doc in enumerate(self.docs):
            if self._matches(doc, filter_query):
                del self.docs[idx]
                return True
        return False

    def delete_many(self, filter_query):
        initial = len(self.docs)
        self.docs = [d for d in self.docs if not self._matches(d, filter_query)]
        return len(self.docs) < initial

class MockMongoDatabase:
    def __init__(self):
        import types
        self._collections = {}
        self.supports_transactions = False
        self.client = None
        self.settings = types.SimpleNamespace(mongodb_url="mongodb://127.0.0.1:27018", db_name="sv_billing")

    def collection(self, name: str) -> MockCollection:
        if name not in self._collections:
            self._collections[name] = MockCollection(name)
        return self._collections[name]

    def list_collection_names(self):
        return list(self._collections.keys())

    def transaction(self):
        import contextlib
        return contextlib.nullcontext()

class SeederDbAdapter:
    """Gives the in-memory mock the pymongo Database access styles (db.items / db['items']) the seeder uses."""
    def __init__(self, fake): self._f = fake
    def __getattr__(self, name): return self._f.collection(name)
    def __getitem__(self, name): return self._f.collection(name)


@pytest.fixture(scope="session")
def seeder():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "scripts" / "seed_database.py"
    spec = importlib.util.spec_from_file_location("seed_database", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def seeded_mock_db(seeder):
    """Hermetic stand-in for a freshly seeded database (repo seed data + data/items.json), never a live MongoDB."""
    db = MockMongoDatabase()
    seeder.seed_collections(SeederDbAdapter(db), seeder.load_seed_json(), seeder.load_extra_items())
    return db


@pytest.fixture
def fake_db():
    db = MockMongoDatabase()
    # Seed default collections
    db.collection("items").insert_one({
        "item_id": "ITEM001",
        "item_alias": "TOM",
        "name": "Tomato",
        "unit": "kg",
        "category": "Vegetables",
        "stock": 100.0,
        "status": "active",
        "is_deleted": 0,
    })
    db.collection("customers").insert_one({
        "cust_id": "CUST001",
        "name": "Metro Retailers",
        "credit_limit": 50000.0,
        "current_balance": 10000.0,
        "payment_terms_days": 30,
        "status": "active",
        "is_deleted": 0,
        "crate_balances": [],
    })
    db.collection("suppliers").insert_one({
        "supplier_id": "SUP001",
        "name": "Green Farms Ltd",
        "tds_applicable": True,
        "tds_rate": 2.0,
        "tds_section": "194C",
        "current_balance": 0.0,
        "status": "active",
        "is_deleted": 0,
    })
    return db


# ==============================================================================
# Automated Test Traceability & GitHub Task Alignment Matrix
# ==============================================================================
TRACEABILITY_MAP = {
    # tests/test_billing_interaction.py
    "test_code_entered_fetches_item_and_focuses_qty": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.1: Keyboard-First Line Item Entry",
        "task": "Task-2.1.1",
        "epic_issue": 2,
        "story_issue": 3,
        "issue_status": "CLOSED (Completed)",
        "note": "Typing alias (e.g. 101) & Enter auto-fetches Item Name, default unit, pricing, and focuses Qty.",
    },
    "test_qty_entered_focuses_unit": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.1: Keyboard-First Line Item Entry",
        "task": "Task-2.1.2",
        "epic_issue": 2,
        "story_issue": 3,
        "issue_status": "CLOSED (Completed)",
        "note": "Pressing Enter on Qty field shifts keyboard focus directly to Unit dropdown.",
    },
    "test_unit_entered_or_selected_focuses_rate": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.1: Keyboard-First Line Item Entry",
        "task": "Task-2.1.3",
        "epic_issue": 2,
        "story_issue": 3,
        "issue_status": "CLOSED (Completed)",
        "note": "Selecting or pressing Enter on Unit shifts keyboard focus to Rate entry.",
    },
    "test_realtime_rate_calculation_keystroke_by_keystroke": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.1: Keyboard-First Line Item Entry",
        "task": "Task-2.1.4",
        "epic_issue": 2,
        "story_issue": 3,
        "issue_status": "CLOSED (Completed)",
        "note": "Keystroke-by-keystroke real-time rate calculation updates line total instantly (typing 6 -> 6*Qty, typing 5 -> 65*Qty).",
    },
    "test_gap_compaction_moves_item_to_first_empty_row": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.2: Gap Compaction & Row Management",
        "task": "Task-2.2.1",
        "epic_issue": 2,
        "story_issue": 4,
        "issue_status": "CLOSED (Completed)",
        "note": "Entering line item in arbitrary empty row (e.g. row 10) automatically shifts to row 1 without leaving gaps.",
    },
    "test_gap_compaction_with_preexisting_rows": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.2: Gap Compaction & Row Management",
        "task": "Task-2.2.1",
        "epic_issue": 2,
        "story_issue": 4,
        "issue_status": "CLOSED (Completed)",
        "note": "Entering out-of-order item at row 10 when rows 1-2 are filled shifts item smoothly to row 3 (N+1).",
    },
    "test_dynamic_row_creation_at_table_end": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.2: Gap Compaction & Row Management",
        "task": "Task-2.2.3",
        "epic_issue": 2,
        "story_issue": 4,
        "issue_status": "CLOSED (Completed)",
        "note": "Completing the final visible row in the table dynamically appends a new row for continuous billing.",
    },

    # tests/test_billing_logic.py
    "test_invoice_number_format": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.3: Mandi Tax, Cess & Payments",
        "task": "Task-2.3.1",
        "epic_issue": 2,
        "story_issue": 2,
        "issue_status": "CLOSED (Completed)",
        "note": "Verifies invoice numbering follows strictly formatted mandi sequence YYYYMMDD-XXXX.",
    },

    # tests/test_consolidated_billing.py
    "test_date_helpers": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.1: Invoice & Statement PDF Generator",
        "task": "Task-6.1.4",
        "epic_issue": 13,
        "story_issue": 14,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates date parsing, weekly/monthly range helpers, and statement period formatting.",
    },
    "test_consolidated_report_aggregation": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.1: Invoice & Statement PDF Generator",
        "task": "Task-6.1.4",
        "epic_issue": 13,
        "story_issue": 14,
        "issue_status": "CLOSED (Completed)",
        "note": "Asserts aggregation engine calculates net bill amounts, payments, and balances across date ranges.",
    },
    "test_unique_bill_to_entities": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.1: Invoice & Statement PDF Generator",
        "task": "Task-6.1.4",
        "epic_issue": 13,
        "story_issue": 14,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates distinct grouping and statement separation by Delivery Challan entity (bill_to_name).",
    },
    "test_generate_consolidated_pdf": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.1: Invoice & Statement PDF Generator",
        "task": "Task-6.1.4",
        "epic_issue": 13,
        "story_issue": 14,
        "issue_status": "CLOSED (Completed)",
        "note": "Generates high-fidelity consolidated periodic customer statement PDF.",
    },
    "test_consolidated_report_ui_frame": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.1: Invoice & Statement PDF Generator",
        "task": "Task-6.1.4",
        "epic_issue": 13,
        "story_issue": 14,
        "issue_status": "CLOSED (Completed)",
        "note": "Asserts ConsolidatedReportFrame renders customer selectors, date pickers, and executes report queries.",
    },

    # tests/test_field_mutation_cascade.py
    "test_bill_line_qty_mutation_recalculates_and_cascades": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.1: Keyboard-First Line Item Entry",
        "task": "Task-2.1.2",
        "epic_issue": 2,
        "story_issue": 3,
        "issue_status": "CLOSED (Completed)",
        "note": "Mutating line Qty recalculates amount, bill total, updates stock in inventory, and logs audit.",
    },
    "test_bill_line_rate_mutation_recalculates_and_cascades": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.1: Keyboard-First Line Item Entry",
        "task": "Task-2.1.4",
        "epic_issue": 2,
        "story_issue": 3,
        "issue_status": "CLOSED (Completed)",
        "note": "Mutating line Rate recalculates total and balance due while keeping inventory quantity invariant.",
    },
    "test_bill_mandi_fee_and_commission_mutation_cascades": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.3: Mandi Tax, Cess & Payments",
        "task": "Task-2.3.1",
        "epic_issue": 2,
        "story_issue": 2,
        "issue_status": "CLOSED (Completed)",
        "note": "Mutating Mandi Cess (1%) and Commission recalculates total bill and customer ledger balance.",
    },
    "test_bill_customer_credit_limit_validation": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.3: Mandi Tax, Cess & Payments",
        "task": "Task-2.3.2",
        "epic_issue": 2,
        "story_issue": 2,
        "issue_status": "CLOSED (Completed)",
        "note": "Asserts customer credit limit validation warns/blocks when uncollected balance exceeds limit.",
    },
    "test_payment_allocation_mutation_cascades": {
        "epic": "EPIC-02: Fast Mandi Billing Engine",
        "story": "Story-02.3: Mandi Tax, Cess & Payments",
        "task": "Task-2.3.3",
        "epic_issue": 2,
        "story_issue": 2,
        "issue_status": "CLOSED (Completed)",
        "note": "Recording payment reduces bill balance due, transitions status from unpaid to paid, and updates AR.",
    },
    "test_fixed_pricing_contract_rate_resolution": {
        "epic": "EPIC-05: Master Data Management",
        "story": "Story-05.2: Item Master & Baseline Rates",
        "task": "Task-5.2.2",
        "epic_issue": 11,
        "story_issue": 29,
        "issue_status": "CLOSED (Completed)",
        "note": "Asserts pricing service resolves customer-specific contract rates prior to default item rates.",
    },
    "test_inventory_manual_adjustment_mutation_cascades": {
        "epic": "EPIC-07: Enterprise Financial Ledger & Inventory",
        "story": "Story-07.3: Inventory Control & Sessions",
        "task": "Task-7.3.1",
        "epic_issue": 16,
        "story_issue": 33,
        "issue_status": "CLOSED (Completed)",
        "note": "Manual stock adjustment updates inventory on hand and logs audit trail in stock_transactions.",
    },
    "test_general_ledger_double_entry_invariants": {
        "epic": "EPIC-07: Enterprise Financial Ledger & Inventory",
        "story": "Story-07.1: Double-Entry General Ledger",
        "task": "Task-7.1.1",
        "epic_issue": 16,
        "story_issue": 31,
        "issue_status": "CLOSED (Completed)",
        "note": "Asserts fundamental accounting invariant: sum of Debits == sum of Credits for every journal posting.",
    },
    "test_void_bill_reversal_cascade": {
        "epic": "EPIC-03: Bill History, Audit Ledger & Reversals",
        "story": "Story-03.2: Void Bill Cascading Reversal",
        "task": "Task-3.2.2",
        "epic_issue": 5,
        "story_issue": 7,
        "issue_status": "CLOSED (Completed)",
        "note": "Voiding a bill marks status as void, restores inventory batch stock, and generates contra ledger entries.",
    },
    "test_order_status_lifecycle_and_conversion_cascade": {
        "epic": "EPIC-04: Customer Order Management",
        "story": "Story-04.3: Order Lifecycle & Conversion",
        "task": "Task-4.3.1",
        "epic_issue": 8,
        "story_issue": 8,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates order lifecycle (draft -> confirmed -> billed) and ensures conversion creates active sales bill.",
    },
    "test_procurement_grn_and_tds_purchase_bill_cascade": {
        "epic": "EPIC-07: Enterprise Financial Ledger & Inventory",
        "story": "Story-07.2: Procurement GRN & Vendor Bills",
        "task": "Task-7.2.1",
        "epic_issue": 16,
        "story_issue": 32,
        "issue_status": "CLOSED (Completed)",
        "note": "GRN creation increases warehouse stock, creates purchase bill, and calculates TDS deduction.",
    },
    "test_inventory_service_waste_tracking": {
        "epic": "EPIC-07: Enterprise Financial Ledger & Inventory",
        "story": "Story-07.3: Inventory Control & Sessions",
        "task": "Task-7.3.1",
        "epic_issue": 16,
        "story_issue": 33,
        "issue_status": "CLOSED (Completed)",
        "note": "Logging perishable produce spoilage/waste decreases stock and books inventory write-off expense.",
    },
    "test_cash_session_and_drawer_variance": {
        "epic": "EPIC-07: Enterprise Financial Ledger & Inventory",
        "story": "Story-07.3: Inventory Control & Sessions",
        "task": "Task-7.3.2",
        "epic_issue": 16,
        "story_issue": 33,
        "issue_status": "CLOSED (Completed)",
        "note": "Cash drawer session calculates expected cash from cash sales, compares with counted cash, and logs variance.",
    },
    "test_main_window_all_views_initialization": {
        "epic": "EPIC-01: Core GUI Shell & Launchers",
        "story": "Story-01.2: Native Desktop GUI Shell",
        "task": "Task-1.2.1",
        "epic_issue": 1,
        "story_issue": 27,
        "issue_status": "CLOSED (Completed)",
        "note": "Initializes all main window navigation frames and confirms zero runtime errors.",
    },

    # tests/test_launcher.py
    "test_powershell_launcher_check_only": {
        "epic": "EPIC-01: Core GUI Shell & Launchers",
        "story": "Story-01.1: Multiplatform Self-Healing Launchers",
        "task": "Task-1.1.1",
        "epic_issue": 1,
        "story_issue": 26,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates PowerShell launcher syntax and dependency verification routines (start.ps1).",
    },
    "test_batch_launcher_check_only": {
        "epic": "EPIC-01: Core GUI Shell & Launchers",
        "story": "Story-01.1: Multiplatform Self-Healing Launchers",
        "task": "Task-1.1.2",
        "epic_issue": 1,
        "story_issue": 26,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates Windows batch launcher syntax and mongod environment checks (start.bat).",
    },
    "test_bash_launcher_check_only": {
        "epic": "EPIC-01: Core GUI Shell & Launchers",
        "story": "Story-01.1: Multiplatform Self-Healing Launchers",
        "task": "Task-1.1.3",
        "epic_issue": 1,
        "story_issue": 26,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates Linux/macOS bash launcher syntax and process launching (start.sh).",
    },

    # tests/test_order_form.py
    "test_order_form_view_structure": {
        "epic": "EPIC-04: Customer Order Management",
        "story": "Story-04.1: Visual Order Form matching UI Guide",
        "task": "Task-4.1.1",
        "epic_issue": 8,
        "story_issue": 9,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates OrderFormView layout, input fields, and action buttons matching screenshot 13-order-new.png.",
    },
    "test_order_form_smart_importer_and_recalc": {
        "epic": "EPIC-04: Customer Order Management",
        "story": "Story-04.2: WhatsApp Freeform Order Smart Importer",
        "task": "Task-4.2.1",
        "epic_issue": 8,
        "story_issue": 10,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates freeform multi-line WhatsApp order parser extracting item names, units, and quantities.",
    },
    "test_order_form_load_order_for_edit": {
        "epic": "EPIC-04: Customer Order Management",
        "story": "Story-04.1: Visual Order Form matching UI Guide",
        "task": "Task-4.1.3",
        "epic_issue": 8,
        "story_issue": 9,
        "issue_status": "CLOSED (Completed)",
        "note": "Loads an existing order document into the order form table for editing and recalculation.",
    },
    "test_order_form_code_entered_fetches_item_and_focuses_qty": {
        "epic": "EPIC-04: Customer Order Management",
        "story": "Story-04.1: Visual Order Form matching UI Guide",
        "task": "Task-4.1.2",
        "epic_issue": 8,
        "story_issue": 9,
        "issue_status": "CLOSED (Completed)",
        "note": "Order Form auto-fetches Item Name, master Unit, and resolved Rate on Code Enter, focusing on Qty.",
    },
    "test_order_form_qty_and_unit_navigation": {
        "epic": "EPIC-04: Customer Order Management",
        "story": "Story-04.1: Visual Order Form matching UI Guide",
        "task": "Task-4.1.4",
        "epic_issue": 8,
        "story_issue": 9,
        "issue_status": "CLOSED (Completed)",
        "note": "Order Form keyboard navigation traverses from Qty to Unit, and from Unit to Rate.",
    },
    "test_order_form_realtime_rate_calculation_keystroke_by_keystroke": {
        "epic": "EPIC-04: Customer Order Management",
        "story": "Story-04.1: Visual Order Form matching UI Guide",
        "task": "Task-4.1.5",
        "epic_issue": 8,
        "story_issue": 9,
        "issue_status": "CLOSED (Completed)",
        "note": "Order Form recalculates Line Amount and Grand Total keystroke-by-keystroke when typing Rate.",
    },
    "test_order_form_gap_compaction_moves_to_first_empty_row": {
        "epic": "EPIC-04: Customer Order Management",
        "story": "Story-04.1: Visual Order Form matching UI Guide",
        "task": "Task-4.1.6",
        "epic_issue": 8,
        "story_issue": 9,
        "issue_status": "CLOSED (Completed)",
        "note": "Order Form compacts row gaps on Rate Enter, shifting out-of-order lines to first available empty slot.",
    },
    "test_order_form_dynamic_row_creation_at_table_end": {
        "epic": "EPIC-04: Customer Order Management",
        "story": "Story-04.1: Visual Order Form matching UI Guide",
        "task": "Task-4.1.7",
        "epic_issue": 8,
        "story_issue": 9,
        "issue_status": "CLOSED (Completed)",
        "note": "Order Form dynamically adds and enables new row when reaching table boundary on Rate Enter.",
    },
    "test_order_form_delete_row_shifts_up": {
        "epic": "EPIC-04: Customer Order Management",
        "story": "Story-04.1: Visual Order Form matching UI Guide",
        "task": "Task-4.1.8",
        "epic_issue": 8,
        "story_issue": 9,
        "issue_status": "CLOSED (Completed)",
        "note": "Order Form row delete button clears row, shifts subsequent rows up, and recalculates totals.",
    },

    # tests/test_pdf_printing.py
    "test_render_invoice_html": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.1: Invoice & Statement PDF Generator",
        "task": "Task-6.1.1",
        "epic_issue": 13,
        "story_issue": 14,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates invoice document data structure and HTML fallback rendering.",
    },
    "test_render_dc_html": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.1: Invoice & Statement PDF Generator",
        "task": "Task-6.1.2",
        "epic_issue": 13,
        "story_issue": 14,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates delivery challan data structure and HTML fallback rendering.",
    },
    "test_generate_invoice_pdf_file": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.1: Invoice & Statement PDF Generator",
        "task": "Task-6.1.1",
        "epic_issue": 13,
        "story_issue": 14,
        "issue_status": "CLOSED (Completed)",
        "note": "Generates authentic ReportLab PDF Invoice file matching Inv- 20260911-0006.pdf.",
    },
    "test_generate_dc_pdf_file": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.1: Invoice & Statement PDF Generator",
        "task": "Task-6.1.2",
        "epic_issue": 13,
        "story_issue": 14,
        "issue_status": "CLOSED (Completed)",
        "note": "Generates authentic ReportLab Delivery Challan PDF file matching DC- 20260911-0006.pdf.",
    },
    "test_attached_anna_adarsh_dc": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.1: Invoice & Statement PDF Generator",
        "task": "Task-6.1.2",
        "epic_issue": 13,
        "story_issue": 14,
        "issue_status": "CLOSED (Completed)",
        "note": "Verifies sample Anna Adarsh hostel delivery challan renders with exact item lines and addresses.",
    },
    "test_attached_kids_clinic_dc_and_invoice": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.1: Invoice & Statement PDF Generator",
        "task": "Task-6.1.1",
        "epic_issue": 13,
        "story_issue": 14,
        "issue_status": "CLOSED (Completed)",
        "note": "Verifies sample Kids Clinic invoice and DC render correctly with customer details.",
    },

    # tests/test_print_preview.py
    "test_print_preview_dialog": {
        "epic": "EPIC-06: Pixel-Perfect PDF Printing & Statements",
        "story": "Story-06.2: Native In-App Print Preview Dialog",
        "task": "Task-6.2.1",
        "epic_issue": 13,
        "story_issue": 15,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates PrintPreviewDialog renders PDF pages using PyMuPDF (fitz) and navigation controls operate.",
    },

    # tests/test_ui_visual_structure.py
    "test_all_ui_views_visual_structure": {
        "epic": "EPIC-01: Core GUI Shell & Launchers",
        "story": "Story-01.2: Native Desktop GUI Shell",
        "task": "Task-1.2.1",
        "epic_issue": 1,
        "story_issue": 27,
        "issue_status": "CLOSED (Completed)",
        "note": "Validates layout and widgets across Dashboard, Billing, History, Masters, Inventory, and Finance.",
    },
    "test_customer_master_dc_company_fetching": {
        "epic": "EPIC-05: Master Data Management",
        "story": "Story-05.1: Customer Master with DC Company",
        "task": "Task-5.1.1",
        "epic_issue": 11,
        "story_issue": 12,
        "issue_status": "CLOSED (Completed)",
        "note": "Asserts Customer Master form fetches, displays, and saves Delivery Challan Company Name (bill_to_name).",
    },
}

_test_outcomes = {}

def pytest_runtest_logreport(report):
    if report.when == "call":
        # Extract raw test function name
        test_func_name = report.nodeid.split("::")[-1].split("[")[0]
        _test_outcomes[test_func_name] = report.outcome.upper()

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    tr = terminalreporter
    tr.write_sep("=", "TRACEABILITY & TASK ALIGNMENT SUMMARY", cyan=True, bold=True)
    tr.write_line("Aligned against Epics, User Stories, and Tasks on sirajpasha/BillDesk_DesktopApp:\n")

    # Group by Epic
    epics_dict = {}
    passed_count = 0
    failed_count = 0
    run_count = 0

    for test_name, meta in TRACEABILITY_MAP.items():
        outcome = _test_outcomes.get(test_name)
        epic = meta["epic"]
        if epic not in epics_dict:
            epics_dict[epic] = []
        epics_dict[epic].append((test_name, meta, outcome))

        if outcome == "PASSED":
            passed_count += 1
            run_count += 1
        elif outcome is not None:
            failed_count += 1
            run_count += 1

    for epic_name, tests in epics_dict.items():
        tr.write_line(f"■ {epic_name}:", bold=True, cyan=True)
        for test_name, meta, outcome in tests:
            story = meta["story"]
            task = meta["task"]
            epic_no = meta["epic_issue"]
            story_no = meta["story_issue"]
            note = meta["note"]
            issue_status = meta["issue_status"]

            if outcome == "PASSED":
                status_tag = "  ✔ [PASSED] "
                color = {"green": True}
            elif outcome is not None:
                status_tag = f"  ✘ [{outcome}] "
                color = {"red": True, "bold": True}
            else:
                status_tag = "  ○ [NOT RUN]"
                color = {"yellow": True}

            tr.write(status_tag, **color)
            tr.write(f"{task} | {story} -> ", bold=True)
            tr.write_line(f"{test_name}")
            tr.write_line(f"         * Task Note: {note}")
            tr.write_line(f"         * GitHub: Epic #{epic_no} | Story #{story_no} [{issue_status}]")
        tr.write_line("")

    tr.write_sep("-", cyan=True)
    total_mapped = len(TRACEABILITY_MAP)
    if run_count == total_mapped and failed_count == 0:
        tr.write_line(f"Traceability Coverage: All {passed_count}/{total_mapped} tasks verified (100% PASSED).", bold=True, green=True)
        tr.write_line("All mapped GitHub Epics & Stories are successfully CLOSED and verified in green state.\n", green=True)
    else:
        tr.write_line(f"Session Summary: {passed_count} passed, {failed_count} failed out of {run_count} executed ({total_mapped} total mapped tasks).", bold=True)


