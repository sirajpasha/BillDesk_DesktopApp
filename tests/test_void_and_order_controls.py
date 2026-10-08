"""Regression tests for D-06 (void reversal) and D-08 (order conversion must obey the normal bill controls)."""
from datetime import datetime

import pytest

from app.models.billing import BillCreate, BillLine
from app.models.order import OrderCreate, OrderItem
from app.services.billing_service import BillingService
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService


def _bill(total=200.0, **kw):
    line = BillLine(item_id="ITEM001", name="Tomato", qty=10.0, unit="kg", rate=total / 10.0, amount=total)
    return BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id="CUST001", customer_name="Metro Retailers",
                      items=[line], total_amount=total, balance_due=total, created_by="tester", **kw)


def _cust(db):
    return db.collection("customers").find_one({"cust_id": "CUST001"})


def _stock(db):
    return db.collection("items").find_one({"item_id": "ITEM001"})["stock"]


# ------------------------------------------------------------------ D-06 void
def test_void_of_part_paid_bill_turns_the_payment_into_unallocated_credit(fake_db):
    svc, pay = BillingService(fake_db), PaymentService(fake_db)
    saved = svc.create_bill(_bill())                                       # 10000 -> 10200
    pay.record_customer_payment("CUST001", 120.0, invoice_no=saved["invoice_no"])   # -> 10080
    res = svc.void_bill(saved["invoice_no"], "admin")
    assert res["credit_released"] == 120.0
    assert _cust(fake_db)["current_balance"] == 9880.0                    # 10000 - 120 customer credit
    p = fake_db.collection("payments").find_one({"party_id": "CUST001"})
    assert p["allocations"] == [] and p["allocation_status"] == "unallocated" and p["is_advance"] is True
    assert "voided" in p["notes"]
    assert _stock(fake_db) == 100.0


def test_void_of_unpaid_bill_restores_balance_exactly(fake_db):
    svc = BillingService(fake_db)
    saved = svc.create_bill(_bill())
    svc.void_bill(saved["invoice_no"])
    assert _cust(fake_db)["current_balance"] == 10000.0


def test_crate_balance_is_tracked_on_bill_and_reversed_on_void(fake_db):
    svc = BillingService(fake_db)
    saved = svc.create_bill(_bill(crates_issued=5, crates_returned=2, crate_item_id="CRATE-PLASTIC"))
    assert _cust(fake_db)["crate_balances"] == [{"item_id": "CRATE-PLASTIC", "balance": 3.0}]
    svc.void_bill(saved["invoice_no"])
    assert _cust(fake_db)["crate_balances"] == [{"item_id": "CRATE-PLASTIC", "balance": 0.0}]
    txns = fake_db.collection("crate_transactions").docs
    assert len(txns) == 2 and txns[1]["issued_qty"] == 2 and txns[1]["returned_qty"] == 5   # mirror image


def test_void_twice_is_rejected(fake_db):
    svc = BillingService(fake_db)
    saved = svc.create_bill(_bill())
    svc.void_bill(saved["invoice_no"])
    with pytest.raises(ValueError, match="already voided"):
        svc.void_bill(saved["invoice_no"])


# ------------------------------------------------------------------ D-08 orders
def _order(db, qty=50.0, rate=20.0, status="pending", **kw):
    return OrderService(db).create_order(OrderCreate(
        customer_id="CUST001", customer_name="Metro Retailers", created_by="tester", status=status,
        items=[OrderItem(item_id="ITEM001", name="Tomato", qty=qty, unit="kg", rate=rate, amount=qty * rate)], **kw))


def test_convert_to_bill_enforces_credit_limit_and_leaves_everything_untouched(fake_db):
    fake_db.collection("customers").update_one({"cust_id": "CUST001"}, {"$set": {"credit_limit": 10500.0}})
    o = _order(fake_db)                                                    # 1000 > 500 headroom
    svc = OrderService(fake_db)
    with pytest.raises(ValueError, match="Credit limit"):
        svc.convert_to_bill(o["order_id"], "admin")
    assert fake_db.collection("bills").count_documents({}) == 0
    assert _stock(fake_db) == 100.0 and _cust(fake_db)["current_balance"] == 10000.0
    assert svc.get_order(o["order_id"])["status"] == "pending"            # claim rolled back, can be retried


def test_convert_to_bill_gets_audit_row_due_date_and_links(fake_db):
    svc = OrderService(fake_db)
    o = _order(fake_db)
    res = svc.convert_to_bill(o["order_id"], "admin")
    bill = fake_db.collection("bills").find_one({"invoice_no": res["invoice_no"]})
    assert bill["linked_source_id"] == o["order_id"] and bill["due_date"] is not None and bill["status"] == "unpaid"
    assert fake_db.collection("bill_audits").count_documents({"invoice_no": res["invoice_no"], "action": "CREATE"}) == 1
    assert _stock(fake_db) == 50.0 and _cust(fake_db)["current_balance"] == 11000.0
    order = svc.get_order(o["order_id"])
    assert order["status"] == "billed" and order["linked_bill_ids"] == [res["invoice_no"]]


def test_billed_or_cancelled_orders_cannot_be_converted_again(fake_db):
    svc = OrderService(fake_db)
    o = _order(fake_db)
    svc.convert_to_bill(o["order_id"])
    with pytest.raises(ValueError, match="already billed"):
        svc.convert_to_bill(o["order_id"])
    c = _order(fake_db, status="cancelled")
    with pytest.raises(ValueError, match="cannot be converted"):
        svc.convert_to_bill(c["order_id"])
    assert fake_db.collection("bills").count_documents({}) == 1


def test_cancel_order_rules(fake_db):
    svc = OrderService(fake_db)
    pending, billed = _order(fake_db), _order(fake_db)
    svc.convert_to_bill(billed["order_id"])
    assert svc.cancel_order(pending["order_id"])["status"] == "cancelled"
    with pytest.raises(ValueError, match="already billed"):
        svc.cancel_order(billed["order_id"])
    with pytest.raises(ValueError, match="already cancelled"):
        svc.cancel_order(pending["order_id"])
    assert svc.get_order(billed["order_id"])["status"] == "billed"


def test_convert_to_purchase_applies_tds_updates_stock_once(fake_db):
    svc = OrderService(fake_db)
    o = _order(fake_db, qty=100.0, rate=50.0)                              # 5000
    res = svc.convert_to_purchase(o["order_id"], "SUP001", "Green Farms Ltd", "admin")
    pur = fake_db.collection("purchase_bills").find_one({"purchase_id": res["purchase_id"]})
    assert pur["tds_amount"] == 100.0 and pur["payable_amount"] == 4900.0       # 2% TDS
    assert fake_db.collection("suppliers").find_one({"supplier_id": "SUP001"})["current_balance"] == 4900.0
    assert _stock(fake_db) == 200.0
    with pytest.raises(ValueError, match="already converted"):
        svc.convert_to_purchase(o["order_id"], "SUP001", "Green Farms Ltd")
    assert _stock(fake_db) == 200.0


def test_convert_to_purchase_rejects_unknown_supplier_and_cancelled_orders(fake_db):
    svc = OrderService(fake_db)
    o = _order(fake_db)
    with pytest.raises(ValueError, match="not found"):
        svc.convert_to_purchase(o["order_id"], "NOPE", "x")
    assert _stock(fake_db) == 100.0 and not svc.get_order(o["order_id"]).get("linked_purchase_ids")
    c = _order(fake_db, status="cancelled")
    with pytest.raises(ValueError, match="cancelled"):
        svc.convert_to_purchase(c["order_id"], "SUP001", "x")
