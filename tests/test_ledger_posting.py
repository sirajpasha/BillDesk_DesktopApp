"""D-07: every business event posts a balanced journal; statements are derived from the ledger."""
from datetime import datetime

from app.models.billing import BillCreate, BillLine
from app.models.common import CurrentUser
from app.services.billing_service import BillingService
from app.services.inventory_service import InventoryService
from app.services.ledger_service import LedgerService
from app.services.payment_service import PaymentService
from app.services.procurement_service import ProcurementService
from app.ui.finance_view import FinanceView


def _bill(customer="CUST001", qty=10.0, rate=20.0, **kw):
    amount = round(qty * rate, 2)
    fees = kw.get("commission_amt", 0.0) + kw.get("mandi_fee_amt", 0.0)
    line = BillLine(item_id="ITEM001", name="Tomato", qty=qty, unit="kg", rate=rate, amount=amount)
    return BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id=customer, customer_name="x",
                      items=[line], total_amount=amount + fees, balance_due=amount + fees, created_by="t", **kw)


def _bal(db, code):
    t = LedgerService(db).get_account_balances().get(code, {"debit": 0.0, "credit": 0.0})
    return round(t["debit"] - t["credit"], 2)           # debit-positive


def _assert_ledger_balanced(db):
    tb = LedgerService(db).get_trial_balance()
    assert tb["is_balanced"], tb
    for j in db.collection("journal_entries").docs:
        assert round(sum(l["debit"] for l in j["lines"]) - sum(l["credit"] for l in j["lines"]), 2) == 0, j


def test_credit_sale_posts_receivable_sales_and_fee_income(fake_db):
    BillingService(fake_db).create_bill(_bill(commission_amt=10.0))        # 200 + 10
    assert _bal(fake_db, "1200") == 210.0 and _bal(fake_db, "4000") == -200.0 and _bal(fake_db, "4100") == -10.0
    _assert_ledger_balanced(fake_db)


def test_walk_in_sale_debits_cash_directly_and_only_the_unpaid_remainder_to_receivables(fake_db):
    svc = BillingService(fake_db)
    svc.create_bill(_bill(customer="CASH", amount_received=200.0))
    assert _bal(fake_db, "1000") == 200.0 and _bal(fake_db, "1200") == 0.0
    svc.create_bill(_bill(customer="CASH", amount_received=120.0, payment_method="UPI"))
    assert _bal(fake_db, "1100") == 120.0 and _bal(fake_db, "1200") == 80.0
    _assert_ledger_balanced(fake_db)


def test_customer_receipt_clears_receivables_to_cash_or_bank(fake_db):
    svc = BillingService(fake_db)
    svc.create_bill(_bill(amount_received=50.0))                           # cash
    svc.create_bill(_bill(amount_received=70.0, payment_method="NEFT/RTGS"))
    assert _bal(fake_db, "1000") == 50.0 and _bal(fake_db, "1100") == 70.0
    assert _bal(fake_db, "1200") == 400.0 - 120.0
    PaymentService(fake_db).record_customer_payment("CUST001", 30.0, payment_method="Cash")
    assert _bal(fake_db, "1000") == 80.0 and _bal(fake_db, "1200") == 250.0
    _assert_ledger_balanced(fake_db)


def test_receivables_ledger_tracks_the_customer_sub_ledger(fake_db):
    svc, pay = BillingService(fake_db), PaymentService(fake_db)
    before = fake_db.collection("customers").find_one({"cust_id": "CUST001"})["current_balance"]
    a = svc.create_bill(_bill(qty=7.0, rate=33.33))
    svc.create_bill(_bill(qty=3.0, rate=11.11, amount_received=10.0))
    pay.record_customer_payment("CUST001", 100.0, invoice_no=a["invoice_no"])
    svc.void_bill(a["invoice_no"])
    after = fake_db.collection("customers").find_one({"cust_id": "CUST001"})["current_balance"]
    assert round(after - before, 2) == _bal(fake_db, "1200")
    _assert_ledger_balanced(fake_db)


def _stock_the_shelf(db):
    """Buy 100 kg of tomato at 40 (2% TDS) - the cost basis for later sales."""
    return ProcurementService(db).create_purchase_bill("SUP001", "B1", [{"item_id": "ITEM001", "name": "Tomato", "qty": 100.0, "rate": 40.0}])


def test_purchase_bill_posts_inventory_payables_and_tds(fake_db):
    pb = _stock_the_shelf(fake_db)
    assert pb["tds_amount"] == 80.0
    assert _bal(fake_db, "1300") == 4000.0 and _bal(fake_db, "2100") == -3920.0 and _bal(fake_db, "2200") == -80.0
    PaymentService(fake_db).record_supplier_payment(pb["purchase_id"], "SUP001", 920.0, payment_method="NEFT")
    assert _bal(fake_db, "2100") == -3000.0 and _bal(fake_db, "1100") == -920.0
    _assert_ledger_balanced(fake_db)


def test_cost_of_goods_uses_weighted_average_cost_and_drives_profit(fake_db):
    _stock_the_shelf(fake_db)
    ProcurementService(fake_db).create_purchase_bill("SUP001", "B2", [{"item_id": "ITEM001", "name": "Tomato", "qty": 100.0, "rate": 60.0}])
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["avg_cost"] == 50.0       # (100*40 + 100*60)/200
    BillingService(fake_db).create_bill(_bill(customer="CASH", qty=10.0, rate=80.0, amount_received=800.0))
    pl = LedgerService(fake_db).get_profit_and_loss()
    assert pl["total_sales"] == 800.0 and pl["cost_of_goods_sold"] == 500.0 and pl["gross_profit"] == 300.0 and pl["net_profit"] == 300.0
    assert _bal(fake_db, "1300") == 10000.0 - 500.0
    _assert_ledger_balanced(fake_db)


def test_waste_is_expensed_out_of_inventory(fake_db):
    _stock_the_shelf(fake_db)
    InventoryService(fake_db).record_waste("ITEM001", 5.0, 40.0, "rotten")
    assert _bal(fake_db, "5100") == 200.0 and _bal(fake_db, "1300") == 4000.0 - 200.0
    assert LedgerService(fake_db).get_profit_and_loss()["net_profit"] == -200.0


def test_void_posts_mirror_entries_and_restores_cost_basis(fake_db):
    _stock_the_shelf(fake_db)
    svc = BillingService(fake_db)
    sale = svc.create_bill(_bill(qty=10.0, rate=80.0))
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["cost_qty"] == 90.0
    svc.void_bill(sale["invoice_no"])
    assert _bal(fake_db, "1200") == 0.0 and _bal(fake_db, "4000") == 0.0 and _bal(fake_db, "5050") == 0.0
    assert _bal(fake_db, "1300") == 4000.0
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["cost_qty"] == 100.0
    originals = [j for j in fake_db.collection("journal_entries").docs if j["source_type"] in ("sale", "cogs")]
    assert len(originals) == 2 and all(j.get("reversed_by") for j in originals)
    _assert_ledger_balanced(fake_db)


def test_void_of_part_paid_bill_leaves_the_customer_credit_in_the_ledger(fake_db):
    svc = BillingService(fake_db)
    sale = svc.create_bill(_bill(amount_received=120.0))                    # 200 bill, 120 paid
    svc.void_bill(sale["invoice_no"])
    assert _bal(fake_db, "1200") == -120.0 and _bal(fake_db, "1000") == 120.0
    _assert_ledger_balanced(fake_db)


def test_posting_is_idempotent_per_reference(fake_db):
    led = LedgerService(fake_db)
    bill = {"invoice_no": "X-1", "customer_id": "CUST001", "total_amount": 100.0, "items": [{"amount": 100.0}]}
    assert led.post_sale(bill) is not None and led.post_sale(bill) is None
    assert fake_db.collection("journal_entries").count_documents({"reference": "X-1"}) == 1


def test_balance_sheet_balances_with_opening_capital_and_earnings(fake_db):
    led = LedgerService(fake_db)
    led.post_journal_entry("OPEN", "manual", [{"account_id": "1000", "debit": 10000.0, "credit": 0.0},
                                              {"account_id": "3000", "debit": 0.0, "credit": 10000.0}])
    pb = _stock_the_shelf(fake_db)
    BillingService(fake_db).create_bill(_bill(customer="CASH", qty=10.0, rate=80.0, amount_received=800.0))
    PaymentService(fake_db).record_supplier_payment(pb["purchase_id"], "SUP001", 1000.0)
    InventoryService(fake_db).record_waste("ITEM001", 2.0, 40.0, "rotten")
    bs = led.get_balance_sheet()
    assert bs["is_balanced"], bs
    assert bs["total_equity"] == 10000.0 + led.get_profit_and_loss()["net_profit"]
    assert bs["total_assets"] == bs["total_liabilities"] + bs["total_equity"]
    _assert_ledger_balanced(fake_db)


def test_finance_screens_render_real_figures(fake_db, tk_root):
    BillingService(fake_db).create_bill(_bill(customer="CASH", amount_received=200.0))
    fv = FinanceView(tk_root, fake_db, current_user=CurrentUser(user_id="U", username="admin", roles=["Admin"]))
    try:
        fv._view_balance_sheet()
        title, text = fv.last_report
        assert title == "Balance Sheet" and "Cash on Hand" in text and "200.00" in text and "YES" in text
        fv._view_trial_balance()
        assert "Produce Sales Revenue" in fv.last_report[1] and "Debits equal credits: YES" in fv.last_report[1]
        fv._view_pl()
        assert "NET PROFIT" in fv.last_report[1] and "200.00" in fv.last_report[1]
    finally:
        for w in tk_root.winfo_children():
            if w.winfo_class() == "Toplevel":
                w.destroy()
        fv.destroy()


# ------------------------------------------------------------------ backfill of pre-existing (legacy) data
def test_backfill_posts_history_once_with_original_dates_and_stays_balanced(fake_db):
    import importlib.util
    from datetime import timezone
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("backfill_ledger", Path(__file__).resolve().parent.parent / "scripts" / "backfill_ledger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    jan = datetime(2026, 1, 5, tzinfo=timezone.utc)
    docs = fake_db.collection("bills")
    docs.insert_one({"invoice_no": "L-1", "customer_id": "CUST001", "status": "unpaid", "total_amount": 500.0, "is_deleted": 0, "created_at": jan,
                     "items": [{"amount": 500.0}]})
    docs.insert_one({"invoice_no": "L-2", "customer_id": "CASH", "status": "paid", "total_amount": 300.0, "is_deleted": 0, "created_at": jan,
                     "items": [{"amount": 300.0}]})
    docs.insert_one({"invoice_no": "L-3", "customer_id": "CUST001", "status": "void", "total_amount": 100.0, "is_deleted": 0, "created_at": jan,
                     "items": [{"amount": 100.0}]})
    fake_db.collection("payments").insert_one({"payment_id": "PAY-1", "party_type": "customer", "party_id": "CUST001", "amount": 200.0,
                                               "payment_method": "UPI", "payment_date": jan, "is_deleted": 0})

    dry = mod.backfill(fake_db, apply=False)
    assert dry["sale"] == 3 and dry["receipt"] == 1 and fake_db.collection("journal_entries").count_documents({}) == 0   # dry run writes nothing

    done = mod.backfill(fake_db, apply=True)
    assert done["sale"] == 3 and done["sale_reversal"] == 1 and done["receipt"] == 1
    assert all(j["date"] == jan for j in fake_db.collection("journal_entries").docs)
    assert _bal(fake_db, "1200") == 500.0 - 200.0 and _bal(fake_db, "1000") == 300.0 and _bal(fake_db, "1100") == 200.0
    _assert_ledger_balanced(fake_db)

    again = mod.backfill(fake_db, apply=True)                       # idempotent
    assert again["sale"] == again["receipt"] == again["sale_reversal"] == 0 and again["skipped_existing"] >= 4
