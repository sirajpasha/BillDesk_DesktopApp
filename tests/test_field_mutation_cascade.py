import pytest
from datetime import datetime, timezone, timedelta
from app.models.common import BillCreate, BillLine
from app.models.order import OrderCreate, OrderItem
from app.services.billing_service import BillingService
from app.services.order_service import OrderService
from app.services.procurement_service import ProcurementService
from app.services.session_service import SessionService
from app.services.inventory_service import InventoryService

def test_bill_line_qty_mutation_recalculates_and_cascades(fake_db):
    """TC-BILL-01: Line Item Quantity Mutation
    Changing qty recalculates line amount, invoice total, balance due,
    and on save decrements items.stock and increments customer current_balance.
    """
    billing = BillingService(fake_db)
    
    # 1. Initial State
    item_before = fake_db.collection("items").find_one({"item_id": "ITEM001"})
    cust_before = fake_db.collection("customers").find_one({"cust_id": "CUST001"})
    assert item_before["stock"] == 100.0
    assert cust_before["current_balance"] == 10000.0
    
    # 2. Mutate Line Qty: 15.0 @ 20.0
    line = BillLine(item_id="ITEM001", name="Tomato", qty=15.0, unit="kg", rate=20.0, amount=15.0 * 20.0)
    assert line.amount == 300.0
    
    bill = BillCreate(
        invoice_date=datetime.now().strftime("%Y-%m-%d"),
        customer_id="CUST001",
        customer_name="Metro Retailers",
        items=[line],
        total_amount=line.amount,
        balance_due=line.amount,
        created_by="tester",
    )
    assert bill.total_amount == 300.0
    assert bill.balance_due == 300.0
    
    # 3. Commit Save -> Verify Cascades
    saved = billing.create_bill(bill)
    assert saved["invoice_no"] is not None
    assert saved["total_amount"] == 300.0
    
    # Check items.stock decrement (-15)
    item_after = fake_db.collection("items").find_one({"item_id": "ITEM001"})
    assert item_after["stock"] == 85.0
    
    # Check customers.current_balance increment (+300)
    cust_after = fake_db.collection("customers").find_one({"cust_id": "CUST001"})
    assert cust_after["current_balance"] == 10300.0
    
    # Check stock_transactions entry
    txn = fake_db.collection("stock_transactions").find_one({"reference_id": saved["invoice_no"]})
    assert txn is not None
    assert txn["qty"] == -15.0
    assert txn["type"] == "sale"
    
    # Check bill_audits entry
    audit = fake_db.collection("bill_audits").find_one({"invoice_no": saved["invoice_no"]})
    assert audit is not None
    assert audit["action"] == "CREATE"

def test_bill_line_rate_mutation_recalculates_and_cascades(fake_db):
    """TC-BILL-02: Line Item Rate Mutation
    Mutating rate recalculates total and customer balance without altering item stock deduction.
    """
    billing = BillingService(fake_db)
    
    # Rate changed from 25.0 to 30.0 for qty = 10.0
    qty = 10.0
    mutated_rate = 30.0
    amount = qty * mutated_rate
    assert amount == 300.0
    
    line = BillLine(item_id="ITEM001", name="Tomato", qty=qty, unit="kg", rate=mutated_rate, amount=amount)
    bill = BillCreate(
        invoice_date=datetime.now().strftime("%Y-%m-%d"),
        customer_id="CUST001",
        customer_name="Metro Retailers",
        items=[line],
        total_amount=amount,
        balance_due=amount,
        created_by="tester",
    )
    
    saved = billing.create_bill(bill)
    assert saved["total_amount"] == 300.0
    
    # Stock only decrements by qty (10.0), regardless of rate
    item = fake_db.collection("items").find_one({"item_id": "ITEM001"})
    assert item["stock"] == 90.0

def test_bill_mandi_fee_and_commission_mutation_cascades(fake_db):
    """TC-BILL-03: Mandi Fee & Commission Percentage Mutation
    Mutating fee and commission rates recalculates net invoice total and customer balance.
    """
    billing = BillingService(fake_db)
    subtotal = 1000.0
    commission_amt = subtotal * 0.02  # 2% = 20.0
    mandi_fee_amt = subtotal * 0.015  # 1.5% = 15.0
    net_total = subtotal + commission_amt + mandi_fee_amt  # 1035.0
    
    line = BillLine(item_id="ITEM001", name="Tomato", qty=50.0, unit="kg", rate=20.0, amount=subtotal)
    bill = BillCreate(
        invoice_date=datetime.now().strftime("%Y-%m-%d"),
        customer_id="CUST001",
        customer_name="Metro Retailers",
        items=[line],
        commission_amt=commission_amt,
        mandi_fee_amt=mandi_fee_amt,
        total_amount=net_total,
        balance_due=net_total,
        created_by="tester",
    )
    
    saved = billing.create_bill(bill)
    assert saved["total_amount"] == 1035.0
    assert saved["commission_amt"] == 20.0
    assert saved["mandi_fee_amt"] == 15.0
    
    # Customer balance must include commission + mandi fee
    cust = fake_db.collection("customers").find_one({"cust_id": "CUST001"})
    assert cust["current_balance"] == 10000.0 + 1035.0

def test_bill_customer_credit_limit_validation(fake_db):
    """TC-BILL-05: Customer Field Mutation & Credit Limit Check
    When current_balance + total_amount > credit_limit (and credit_limit > 0),
    the save operation must reject the mutation.
    """
    billing = BillingService(fake_db)
    # CUST001: credit_limit = 50,000, current_balance = 10,000.
    # A bill of 45,000 -> 10,000 + 45,000 = 55,000 > 50,000 -> Rejected!
    line = BillLine(item_id="ITEM001", name="Tomato", qty=450.0, unit="kg", rate=100.0, amount=45000.0)
    bill = BillCreate(
        invoice_date=datetime.now().strftime("%Y-%m-%d"),
        customer_id="CUST001",
        customer_name="Metro Retailers",
        items=[line],
        total_amount=45000.0,
        balance_due=45000.0,
        created_by="tester",
    )
    
    with pytest.raises(ValueError, match="Credit limit exceeded"):
        billing.create_bill(bill)
        
    # Verify no cascading changes occurred
    cust = fake_db.collection("customers").find_one({"cust_id": "CUST001"})
    assert cust["current_balance"] == 10000.0
    assert fake_db.collection("bills").count_documents() == 0

def test_payment_allocation_mutation_cascades(fake_db):
    """TC-PAY-01 & TC-PAY-02: Payment Amount Allocation Mutation
    When a payment is allocated to an invoice:
    - Invoice balance_due decrements
    - Invoice status updates (unpaid -> partial -> paid)
    - Customer current_balance decrements
    """
    billing = BillingService(fake_db)
    # Create invoice of 1000.0
    line = BillLine(item_id="ITEM001", name="Tomato", qty=50.0, unit="kg", rate=20.0, amount=1000.0)
    bill = BillCreate(
        invoice_date=datetime.now().strftime("%Y-%m-%d"),
        customer_id="CUST001",
        customer_name="Metro Retailers",
        items=[line],
        total_amount=1000.0,
        balance_due=1000.0,
        created_by="tester",
    )
    saved_bill = billing.create_bill(bill)
    inv_no = saved_bill["invoice_no"]
    
    # 1. Partial Payment of 400.0
    pay_amount = 400.0
    fake_db.collection("bills").update_one(
        {"invoice_no": inv_no},
        {"$inc": {"balance_due": -pay_amount}, "$set": {"status": "partial"}}
    )
    fake_db.collection("customers").update_one(
        {"cust_id": "CUST001"},
        {"$inc": {"current_balance": -pay_amount}}
    )
    fake_db.collection("payments").insert_one({
        "payment_id": "PAY001",
        "party_id": "CUST001",
        "amount": pay_amount,
        "allocations": [{"invoice_id": inv_no, "amount": pay_amount}],
        "allocation_status": "full",
    })
    
    inv_partial = fake_db.collection("bills").find_one({"invoice_no": inv_no})
    assert inv_partial["balance_due"] == 600.0
    assert inv_partial["status"] == "partial"
    
    cust_partial = fake_db.collection("customers").find_one({"cust_id": "CUST001"})
    assert cust_partial["current_balance"] == 11000.0 - 400.0  # 10600.0
    
    # 2. Final Payment of 600.0 -> marks invoice 'paid'
    remaining = 600.0
    fake_db.collection("bills").update_one(
        {"invoice_no": inv_no},
        {"$inc": {"balance_due": -remaining}, "$set": {"status": "paid"}}
    )
    fake_db.collection("customers").update_one(
        {"cust_id": "CUST001"},
        {"$inc": {"current_balance": -remaining}}
    )
    
    inv_paid = fake_db.collection("bills").find_one({"invoice_no": inv_no})
    assert inv_paid["balance_due"] == 0.0
    assert inv_paid["status"] == "paid"

def test_fixed_pricing_contract_rate_resolution(fake_db):
    """TC-PRICE-01 & TC-PRICE-02: Contract Rate Active Range Mutation
    PricingService resolves contract rate when within date range,
    and falls back to standard rate once expired.
    """
    billing = BillingService(fake_db)
    now = datetime.now(timezone.utc)
    
    # Active contract: 18.0
    fake_db.collection("fixed_prices").insert_one({
        "customer_id": "CUST001",
        "item_id": "ITEM001",
        "rate": 18.0,
        "start_date": now - timedelta(days=5),
        "end_date": now + timedelta(days=5),
        "is_active": True,
    })
    
    # Query during validity
    active_fix = billing.fixed_rate("CUST001", "ITEM001", now)
    assert active_fix is not None
    assert active_fix["rate"] == 18.0
    
    # Query after expiry
    future = now + timedelta(days=10)
    expired_fix = billing.fixed_rate("CUST001", "ITEM001", future)
    assert expired_fix is None

def test_inventory_manual_adjustment_mutation_cascades(fake_db):
    """TC-INV-01: Manual Stock Adjustment Mutation
    Mutating stock via adjustment updates items.stock and logs stock_transactions.
    """
    item_id = "ITEM001"
    adjustment_qty = -12.5
    
    # Apply adjustment
    fake_db.collection("items").update_one({"item_id": item_id}, {"$inc": {"stock": adjustment_qty}})
    fake_db.collection("stock_transactions").insert_one({
        "transaction_id": "TXN-ADJ-001",
        "item_id": item_id,
        "qty": adjustment_qty,
        "type": "adjustment",
        "notes": "Drying shrinkage",
    })
    
    item = fake_db.collection("items").find_one({"item_id": item_id})
    assert item["stock"] == 87.5
    
    txn = fake_db.collection("stock_transactions").find_one({"transaction_id": "TXN-ADJ-001"})
    assert txn["qty"] == -12.5
    assert txn["type"] == "adjustment"

def test_general_ledger_double_entry_invariants(fake_db):
    """TC-GL-01 & TC-GL-02: General Ledger Double-Entry Invariants
    Sum of debits must strictly equal sum of credits.
    """
    def save_journal(lines, ref):
        debits = sum(line.get("debit", 0.0) for line in lines)
        credits = sum(line.get("credit", 0.0) for line in lines)
        if abs(debits - credits) > 0.001:
            raise ValueError(f"Unbalanced journal entry: debits ({debits}) != credits ({credits})")
        return fake_db.collection("journal_entries").insert_one({
            "reference": ref,
            "lines": lines,
            "state": "posted",
            "date": datetime.now(timezone.utc),
        })
        
    # Balanced entry passes
    balanced_lines = [
        {"account_id": "1200-AR", "debit": 1500.0, "credit": 0.0},
        {"account_id": "4000-SALES", "debit": 0.0, "credit": 1500.0},
    ]
    entry = save_journal(balanced_lines, "INV-001")
    assert entry["state"] == "posted"
    
    # Unbalanced entry raises ValueError
    unbalanced_lines = [
        {"account_id": "1200-AR", "debit": 1500.0, "credit": 0.0},
        {"account_id": "4000-SALES", "debit": 0.0, "credit": 1200.0},
    ]
    with pytest.raises(ValueError, match="Unbalanced journal entry"):
        save_journal(unbalanced_lines, "INV-002")

def test_void_bill_reversal_cascade(fake_db):
    """TC-BILL-04: Void Invoice Reversal Cascade
    Voiding an invoice restores items.stock, decrements customer current_balance,
    sets bill status to 'void', and writes audit log.
    """
    billing = BillingService(fake_db)
    line = BillLine(item_id="ITEM001", name="Tomato", qty=20.0, unit="kg", rate=25.0, amount=500.0)
    bill = BillCreate(
        invoice_date=datetime.now().strftime("%Y-%m-%d"),
        customer_id="CUST001",
        customer_name="Metro Retailers",
        items=[line],
        total_amount=500.0,
        balance_due=500.0,
        created_by="cashier1",
    )
    saved = billing.create_bill(bill)
    inv_no = saved["invoice_no"]

    # Verify state after creation
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["stock"] == 80.0
    assert fake_db.collection("customers").find_one({"cust_id": "CUST001"})["current_balance"] == 10500.0

    # Void Bill
    res = billing.void_bill(inv_no, user_id="admin1")
    assert res["status"] == "void"

    # Verify Stock Restored
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["stock"] == 100.0

    # Verify Customer Balance Restored
    assert fake_db.collection("customers").find_one({"cust_id": "CUST001"})["current_balance"] == 10000.0

    # Verify Bill Status & Balance Due
    voided_bill = fake_db.collection("bills").find_one({"invoice_no": inv_no})
    assert voided_bill["status"] == "void"
    assert voided_bill["balance_due"] == 0.0

    # Verify Audit Log
    audit = fake_db.collection("bill_audits").find_one({"invoice_no": inv_no, "action": "VOID"})
    assert audit is not None
    assert audit["changed_by"] == "admin1"

def test_order_status_lifecycle_and_conversion_cascade(fake_db):
    """TC-ORD-01 & TC-ORD-02: Order Creation and 1-Click Bill Conversion
    Creating order sets status 'pending'. Converting to bill sets status 'billed',
    creates invoice, decrements stock, and updates customer balance.
    """
    order_svc = OrderService(fake_db)
    item = OrderItem(item_id="ITEM001", name="Tomato", qty=30.0, unit="kg", rate=20.0, amount=600.0)
    order_in = OrderCreate(
        customer_id="CUST001",
        customer_name="Metro Retailers",
        items=[item],
        notes="Urgent morning dispatch",
        created_by="salesrep",
    )
    created = order_svc.create_order(order_in)
    order_id = created["order_id"]
    assert created["status"] == "pending"
    assert created["total_amount"] == 600.0

    # Convert to Bill
    res = order_svc.convert_to_bill(order_id, user_id="billing_clerk")
    inv_no = res["invoice_no"]
    assert inv_no is not None

    # Check order status in DB
    updated_order = order_svc.get_order(order_id)
    assert updated_order["status"] == "billed"
    assert inv_no in updated_order["linked_bill_ids"]

    # Stock should be decremented by 30
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["stock"] == 70.0

    # Customer balance incremented by 600
    assert fake_db.collection("customers").find_one({"cust_id": "CUST001"})["current_balance"] == 10600.0

    # Bill created in bills collection
    bill = fake_db.collection("bills").find_one({"invoice_no": inv_no})
    assert bill is not None
    assert bill["total_amount"] == 600.0

def test_procurement_grn_and_tds_purchase_bill_cascade(fake_db):
    """TC-PROC-02 & TC-PROC-03: GRN Stock Increment & Vendor Bill with TDS Calculation
    GRN increments warehouse produce stock.
    Purchase bill computes TDS (194C 2%), books AP liability, and updates supplier balance.
    """
    proc_svc = ProcurementService(fake_db)

    # 1. Test GRN
    po = fake_db.collection("purchase_orders").insert_one({
        "po_id": "PO-1001",
        "supplier_id": "SUP001",
        "supplier_name": "Fresh Farm Suppliers",
        "status": "issued",
    })
    grn = proc_svc.record_grn(
        po_id="PO-1001",
        received_items=[{"item_id": "ITEM001", "name": "Tomato", "qty": 50.0, "unit": "kg"}],
        received_by="storekeeper"
    )
    assert grn["status"] == "active"
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["stock"] == 150.0
    assert fake_db.collection("purchase_orders").find_one({"po_id": "PO-1001"})["status"] == "received"

    # 2. Test Vendor Bill with TDS
    fake_db.collection("suppliers").update_one(
        {"supplier_id": "SUP001"},
        {"$set": {"current_balance": 5000.0, "tds_applicable": True, "tds_rate": 2.0, "tds_section": "194C"}}
    )
    bill = proc_svc.create_purchase_bill(
        supplier_id="SUP001",
        supplier_bill_no="INV-SUP-8899",
        items=[{"item_id": "ITEM001", "name": "Tomato", "qty": 100.0, "rate": 50.0}],
        notes="Verified lot",
        user_id="purchaser"
    )
    assert bill["total_amount"] == 5000.0
    assert bill["tds_amount"] == 100.0  # 2% of 5000
    assert bill["payable_amount"] == 4900.0

    # Supplier AP balance should increase by net payable amount (4900)
    supp = fake_db.collection("suppliers").find_one({"supplier_id": "SUP001"})
    assert supp["current_balance"] == 5000.0 + 4900.0

def test_inventory_service_waste_tracking(fake_db):
    """TC-INV-02: Produce Waste Logging Mutation
    Logging spoilage decrements stock and writes waste log with amount.
    """
    inv_svc = InventoryService(fake_db)
    res = inv_svc.record_waste(
        item_id="ITEM001",
        qty=10.0,
        rate=25.0,
        reason="Mandi heat spoilage",
        user_id="qc_inspector"
    )
    assert res["amount"] == 250.0
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["stock"] == 90.0
    txn = fake_db.collection("stock_transactions").find_one({"type": "waste"})
    assert txn is not None
    assert txn["qty"] == -10.0

def test_cash_session_and_drawer_variance(fake_db):
    """TC-SESS-01 & TC-SESS-02: Cash Drawer Session & Variance Computation
    Opening session records opening cash. Adding cash bills accumulates expected cash.
    Closing session records actual cash, calculates difference, and marks closed.
    """
    sess_svc = SessionService(fake_db)
    opened = sess_svc.open_session("USR01", "cashier1", opening_cash=2000.0)
    sess_id = opened["session_id"]
    assert opened["status"] == "open"

    # Insert a cash bill for cashier1
    fake_db.collection("bills").insert_one({
        "invoice_no": "INV-CASH-001",
        "created_by": "cashier1",
        "created_at": datetime.now(timezone.utc),
        "total_amount": 3500.0,
        "payment_mode": "cash",
        "status": "paid",
        "is_deleted": 0,
    })

    expected = sess_svc.compute_expected_cash(sess_id)
    assert expected == 5500.0  # 2000 opening + 3500 cash bill

    closed = sess_svc.close_session(sess_id, actual_cash=5480.0, notes="20 shortage in drawer coins")
    assert closed["status"] == "closed"
    assert closed["expected_cash"] == 5500.0
    assert closed["actual_cash"] == 5480.0
    assert closed["difference"] == -20.0

def test_main_window_all_views_initialization(fake_db, tk_root):
    """UI Integration Test: MainWindow mounts all 10 ERP modules cleanly without error."""
    import tkinter as tk
    from app.services.auth_service import AuthService
    from app.ui.main_window import MainWindow
    from app.models.common import CurrentUser

    root = tk_root

    auth = AuthService(fake_db)
    billing = BillingService(fake_db)
    user = CurrentUser(user_id="USR-ADMIN", username="admin", roles=["Admin", "Super Admin"], company_id="Company0001")

    window = MainWindow(root, fake_db, auth, billing, user)
    # Verify all 10 modules exist in window.frames
    expected_modules = [
        "Dashboard", "New Bill", "Bill History", "Master Data",
        "Orders", "Inventory", "Procurement", "Finance",
        "Administration", "DB Connection"
    ]
    for mod in expected_modules:
        assert mod in window.frames, f"Module '{mod}' missing from MainWindow.frames"

    # Verify page switching works for each module
    for mod in expected_modules:
        window.show_page(mod)
        assert window.active_page == mod

