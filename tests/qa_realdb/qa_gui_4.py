from qa_gui_common import *
from datetime import datetime, timedelta, timezone
import tkinter as tk, tempfile, warnings
warnings.filterwarnings("ignore")

# ================================================================= CURRENCY / WORDS (pure functions)
from app.utils.currency import format_inr, amount_in_words
for amt, exp in [(0, "₹ 0.00"), (999, "₹ 999.00"), (1000, "₹ 1,000.00"), (123456.5, "₹ 1,23,456.50"), (12345678.9, "₹ 1,23,45,678.90"), (-2500, "-₹ 2,500.00"), (None, "₹ 0.00"), (0.5, "₹ 0.50")]:
    check(f"CUR-fmt-{amt}", f"format_inr({amt}) -> {exp}", format_inr(amt) == exp, format_inr(amt))
for amt, exp in [(0, "Zero Rupees Only"), (1, "One Rupee Only"), (21, "Twenty One Rupees Only"), (100, "One Hundred Rupees Only"), (1234.5, "One Thousand Two Hundred Thirty Four Rupees and Fifty Paise Only"),
                 (100000, "One Lakh Rupees Only"), (12345678, "One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight Rupees Only"), (-50, "Minus Fifty Rupees Only")]:
    check(f"CUR-words-{amt}", f"amount_in_words({amt})", amount_in_words(amt) == exp, amount_in_words(amt))
check("CUR-words-singular", "1 rupee reads 'One Rupee Only' (singular)", amount_in_words(1) == "One Rupee Only", amount_in_words(1))
for amt in [99.999, 0.995, 1.999, 19999.995]:
    try: w = amount_in_words(amt); ok = True; ev = w
    except Exception as e: ok = False; ev = f"{type(e).__name__}: {e}"
    check(f"CUR-words-rounding-{amt}", f"amount_in_words({amt}) (fractional paise from qty x rate) does not crash", ok, ev)
try: w = amount_in_words(1000000000); ok = True
except Exception as e: ok = False; w = f"{type(e).__name__}: {e}"
check("CUR-words-crore100", "amount >= 100 crore (Rs 100,00,00,000) converts without crashing", ok, w)

# ================================================================= app boot + seed some activity
root, db, auth, billing, user, win = boot()
raw = db.db
def setv(w, v): w.delete(0, tk.END); w.insert(0, v)
from app.models.billing import BillCreate, BillItem
from app.services.payment_service import PaymentService
from app.services.master_service import MasterService
from app.services.admin_service import AdminService
from app.services.ledger_service import LedgerService
ms, ads, ps, ls = MasterService(db), AdminService(db), PaymentService(db), LedgerService(db)

# bills for reports / pdf
def mkbill(cid, cname, lines, user="admin", **extra):
    items = [BillItem(item_id=i, item_alias=a, name=n, qty=q, unit="kg", rate=r, amount=q * r) for i, a, n, q, r in lines]
    tot = sum(x.amount for x in items)
    return billing.create_bill(BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id=cid, customer_name=cname, items=items, total_amount=tot, balance_due=tot, created_by=user, **extra))
raw.customers.update_one({"cust_id": "Cust0001"}, {"$set": {"credit_limit": 0.0}})
b1 = mkbill("Cust0001", "Anna Adarsh Hostel", [("FRU0001", "101", "Apple", 12.5, 33.33), ("VEG0001", "102", "Avarai", 7, 18.0)])
b2 = mkbill("Cust0001", "Anna Adarsh Hostel", [("FRU0002", "105", "Banana Green", 40, 25.0)])
b3 = mkbill("CASH", "Cash Customer", [("VEG0002", "104", "Bajji Chilli", 3, 99.99)], amount_received=299.97)   # walk-in, paid in cash

# ================================================================= DASHBOARD
win.show_page("Dashboard"); pump(root, 4); dv = win.frames["Dashboard"]; dv.refresh(); pump(root, 3)
shot(root, "dashboard_with_data")
today_total = sum(b["total_amount"] for b in raw.bills.find({"invoice_date": datetime.now().strftime("%Y-%m-%d"), "status": {"$ne": "void"}}))
shown = dv.card_widgets["sales_today"][0].cget("text")
check("GUI-DASH-01", "dashboard 'Sales Today' equals sum of today's non-void bills", f"{today_total:,.2f}".replace(",", "") in shown.replace(",", "").replace("₹", "").replace(" ", "") or abs(float(''.join(c for c in shown if c.isdigit() or c=='.') or 0) - today_total) < 0.01, f"ui={shown!r} db={today_total}")
check("GUI-DASH-02", "dashboard bill count = 3", dv.card_widgets["sales_today"][1].cget("text") == "3 bills", dv.card_widgets["sales_today"][1].cget("text"))

# ================================================================= PDFs
from app.printing.invoice import generate_invoice_pdf, generate_dc_pdf, render_invoice_html
import fitz
tmp = tempfile.mkdtemp(dir=SCRATCH)
comp = ms.get_company(None); cust = raw.customers.find_one({"cust_id": "Cust0001"})
p = generate_invoice_pdf(os.path.join(tmp, "inv.pdf"), b1, company=comp, customer=cust)
doc = fitz.open(p); txt = "".join(pg.get_text() for pg in doc)
check("PDF-INV-01", "invoice PDF has 1 page for a 2-line bill", len(doc) == 1, len(doc))
check("PDF-INV-02", "invoice PDF contains invoice number", b1["invoice_no"] in txt, b1["invoice_no"])
check("PDF-INV-03", "invoice PDF contains customer name", "Anna Adarsh" in txt)
total = b1["total_amount"]
check("PDF-INV-04", f"invoice PDF contains grand total {total:,.2f}", f"{total:,.2f}" in txt, [l for l in txt.splitlines() if "Total" in l][:4])
check("PDF-INV-05", "invoice PDF contains amount in words", "Rupees" in txt, [l for l in txt.splitlines() if "Rupee" in l][:2])
check("PDF-INV-06", "invoice PDF shows line items (Apple, Avarai)", "Apple" in txt and "Avarai" in txt)
page = doc[0].get_pixmap(dpi=70); page.save(os.path.join(SCRATCH, "shots", "invoice_pdf.png"))
pd = generate_dc_pdf(os.path.join(tmp, "dc.pdf"), b1, company=comp, customer=cust)
dtxt = "".join(pg.get_text() for pg in fitz.open(pd))
check("PDF-DC-01", "delivery challan omits rates/amounts", f"{total:,.2f}" not in dtxt and "33.33" not in dtxt, "contains total" if f"{total:,.2f}" in dtxt else "ok")
check("PDF-DC-02", "delivery challan lists items & qty", "Apple" in dtxt and "12.5" in dtxt, dtxt[:200].replace("\n", " | "))
# bigger bill => multipage?
many = dict(b1); many["items"] = [dict(b1["items"][0], name=f"Item {i}", item_id=f"X{i}") for i in range(60)]; many["total_amount"] = 60 * b1["items"][0]["amount"]
pm = generate_invoice_pdf(os.path.join(tmp, "many.pdf"), many, company=comp, customer=cust)
dm = fitz.open(pm); tm = "".join(pg.get_text() for pg in dm)
check("PDF-INV-07", "60-line invoice paginates without losing lines", "Item 59" in tm and len(dm) >= 2, f"pages={len(dm)} has Item 59={'Item 59' in tm}")
weird = dict(b1); weird["customer_name"] = "Ünï & <b>Co</b> — தமிழ்"; weird["items"] = [dict(b1["items"][0], name="Tomato <script>alert(1)</script> & Co")]
try:
    pw = generate_invoice_pdf(os.path.join(tmp, "weird.pdf"), weird, company=comp, customer=dict(cust, name=weird["customer_name"])); wt = "".join(pg.get_text() for pg in fitz.open(pw)); ok = True
except Exception as e: ok = False; wt = repr(e)
check("PDF-INV-08", "special characters / markup in names do not break PDF generation", ok, wt[:120].replace("\n", " "))

# ================================================================= MASTERS (service CRUD)
r = ms.save_item({"item_id": "QAI001", "item_alias": "901", "name": "QA Mango", "unit": "kg", "category": "Fruit"}, is_new=True)
check("GUI-MST-01", "new item saved with is_deleted=0 / active defaults (visible to billing)", raw.items.find_one({"item_id": "QAI001"}).get("is_deleted") == 0 and raw.items.find_one({"item_id": "QAI001"}).get("status") == "active", {k: raw.items.find_one({"item_id": "QAI001"}).get(k) for k in ("is_deleted", "status", "stock", "default_rate", "standard_rate")})
for bad, why, exp in [({"item_id": "QAI001", "item_alias": "902", "name": "dup id"}, "duplicate item id", "already exists"), ({"item_id": "QAI002", "item_alias": "901", "name": "dup alias"}, "duplicate alias", "in use"), ({"item_id": "", "name": "x"}, "blank id", "required"), ({"item_id": "QAI003", "name": "  "}, "blank name", "required")]:
    try: ms.save_item(bad, is_new=True); check(f"GUI-MST-dup-{why}", f"item {why} rejected", False, "accepted")
    except Exception as e: check(f"GUI-MST-dup-{why}", f"item {why} rejected", exp in str(e).lower() or "required" in str(e).lower(), e)
try:
    ms.save_item({"item_id": "QAI009", "item_alias": "909", "name": "Neg", "unit": "kg", "category": "Veg", "standard_rate": -5}, is_new=True)
    check("GUI-MST-04", "negative standard rate rejected", False, "accepted rate -5")
except Exception as e: check("GUI-MST-04", "negative standard rate rejected", True, e)
ms.delete_item("QAI001")
check("GUI-MST-05", "deleted item disappears from search & billing lookup", not [i for i in billing.search_items("QA Mango")], billing.search_items("QA Mango"))
try: ms.save_item({"item_id": "QAI001", "item_alias": "901", "name": "QA Mango2"}, is_new=True); check("GUI-MST-06", "re-creating a soft-deleted item id/alias is blocked or resurrects correctly", False, "silently created second doc with same id")
except Exception as e: check("GUI-MST-06", "re-creating a soft-deleted item id/alias is blocked or resurrects correctly", True, e)
c = ms.save_customer({"cust_id": "QAC001", "name": "QA Cust", "credit_limit": 1000.0, "bill_to_name": "QA Group"}, is_new=True)
cd = raw.customers.find_one({"cust_id": "QAC001"})
check("GUI-MST-07", "new customer is active/non-deleted and billable", cd.get("is_deleted") == 0 and cd.get("status") == "active", {k: cd.get(k) for k in ("is_deleted", "status", "current_balance", "credit_limit")})
try: ms.save_customer({"cust_id": "QAC001", "name": "dup"}, is_new=True); check("GUI-MST-08", "duplicate customer id rejected", False, "accepted")
except Exception as e: check("GUI-MST-08", "duplicate customer id rejected", True, e)
raw.customers.update_one({"cust_id": "QAC001"}, {"$set": {"current_balance": 777.0}})
try: ms.delete_customer("QAC001")
except ValueError: pass
check("GUI-MST-09", "customer with outstanding balance (777) cannot be deleted", raw.customers.find_one({"cust_id": "QAC001"}).get("is_deleted") == 0, f"is_deleted={raw.customers.find_one({'cust_id': 'QAC001'}).get('is_deleted')} despite balance 777")
ms.save_customer({"cust_id": "QAC001", "name": "QA Cust", "current_balance": 0.0}, is_new=False)
check("GUI-MST-10", "editing a customer record cannot overwrite the ledger balance (current_balance)", raw.customers.find_one({"cust_id": "QAC001"})["current_balance"] == 777.0, f"balance after edit={raw.customers.find_one({'cust_id': 'QAC001'})['current_balance']}")
raw.customers.update_one({"cust_id": "QAC001"}, {"$set": {"current_balance": 0.0}})   # test artefact: this balance never went through the ledger
now = datetime.now(timezone.utc)
for args, why in [((("Cust0001", "FRU0001", 0, now, now + timedelta(days=1))), "zero rate"), ((("Cust0001", "FRU0001", 10, now + timedelta(days=2), now)), "start after end")]:
    try: ms.save_fixed_price(*args); check(f"GUI-MST-fp-{why}", f"fixed price {why} rejected", False, "accepted")
    except ValueError as e: check(f"GUI-MST-fp-{why}", f"fixed price {why} rejected", True, e)
ms.save_fixed_price("Cust0001", "FRU0001", 15.0, now - timedelta(days=1), now + timedelta(days=5))
ms.save_fixed_price("Cust0001", "FRU0001", 16.0, now - timedelta(days=1), now + timedelta(days=5))
check("GUI-MST-11", "re-saving a fixed price leaves exactly one active price", raw.fixed_prices.count_documents({"customer_id": "Cust0001", "item_id": "FRU0001", "is_active": True}) == 1, raw.fixed_prices.count_documents({"customer_id": "Cust0001", "item_id": "FRU0001", "is_active": True}))

# masters UI pages
for pg in ["Item Master", "Customer Master", "Supplier Master", "Fixed Rates"]:
    win.show_page(pg); pump(root, 3)
shot(root, "masters_fixed_rates")
win.show_page("Customer Master"); pump(root, 3); shot(root, "masters_customers")

# ================================================================= FINANCE UI
# (journals are kept: the automatic postings from the bills above are part of the ledger under test)
ls.post_journal_entry("QA-OPEN", "manual", [{"account_id": "1000", "debit": 5000.0, "credit": 0.0}, {"account_id": "3000", "debit": 0.0, "credit": 5000.0}], "admin")
win.show_page("Finance"); pump(root, 3); fv = win.frames["Finance"]
shot(root, "finance_home")
win.show_page("Trial Balance"); pump(root, 6); shot(root, "finance_trial_balance")
tb = ls.get_trial_balance()
check("GUI-FIN-01", "trial balance includes the automatic postings from the 3 bills AND the manual opening journal, and balances", tb["is_balanced"] and tb["total_debit"] > 5000.0 and any(r["account_code"] == "4000" for r in tb["rows"]) and any(r["account_code"] == "1000" for r in tb["rows"]), f"rows={[(r['account_code'], r['debit'], r['credit']) for r in tb['rows']]}")
win.show_page("Profit & Loss"); pump(root, 6); shot(root, "finance_pl")
pl = ls.get_profit_and_loss()
check("GUI-FIN-02", "P&L total revenue = sum of non-void bills", abs(pl["total_revenue"] - sum(b["total_amount"] for b in raw.bills.find({"status": {"$ne": "void"}}))) < 0.01, pl)
fv._view_balance_sheet(); bs_msg = fv.last_report[1]
check("GUI-FIN-05", "Balance Sheet screen shows real asset/liability/equity figures and balances (EPIC-07 Task 7.2)", "Total assets" in bs_msg and "Cash on Hand" in bs_msg and "YES" in bs_msg, bs_msg.replace(chr(10), " | ")[:160])
from app.services.procurement_service import ProcurementService as _PS
_PS(db).create_purchase_bill("SUP001", "QA-PB-1", [{"item_id": "FRU0001", "name": "Apple", "qty": 100, "rate": 40.0}], user_id="admin")   # buy 4000 of stock
pl2 = ls.get_profit_and_loss()
check("GUI-FIN-06", "P&L charges COGS only (goods sold), not every purchase: buying Rs4000 stock and selling ~Rs1,100 must not show a ~Rs-2,900 'loss' while stock is still on the shelf", pl2["net_profit"] > -1000, f"sales={pl2['total_sales']:.2f} purchases={pl2['total_purchases']:.2f} net_profit={pl2['net_profit']:.2f}")
fv._view_trial_balance(); tb_msg = fv.last_report[1]
check("GUI-FIN-07", "Trial Balance dialog lists per-account debit/credit rows (not just totals)", "Cash on Hand" in tb_msg and "Debits equal credits: YES" in tb_msg, tb_msg.replace(chr(10), " | ")[:160])
win.show_page("Balance Sheet"); pump(root, 6); shot(root, "finance_bs")
win.show_page("Accounts Receivables"); pump(root, 4); shot(root, "finance_ar")
ps.record_customer_payment("Cust0001", 100.0, user_id="admin")
ag = ps.get_ar_aging()
check("GUI-FIN-03", "AR aging total equals sum of open balance_due", abs(ag["summary"]["total"] - sum(b["balance_due"] for b in raw.bills.find({"status": {"$in": ["unpaid", "partial"]}, "is_deleted": 0}))) < 0.01, ag["summary"])
check("GUI-FIN-04", "AR aging total equals sum of customer.current_balance (sub-ledger = control account)", abs(ag["summary"]["total"] - sum(c.get("current_balance", 0) for c in raw.customers.find())) < 0.01, f"aging={ag['summary']['total']} vs customers={sum(c.get('current_balance',0) for c in raw.customers.find())}")
win.show_page("Accounts Payables"); pump(root, 4)
win.show_page("BRS"); pump(root, 4); shot(root, "finance_brs")

# ================================================================= ADMIN
win.show_page("User Management"); pump(root, 4); shot(root, "admin_users")
users = ads.get_users()
check("GUI-ADM-01", "user list never exposes password hashes", all("password_hash" not in u for u in users))
try: ads.create_user("tester", "pw12345", ["user"]); ok = True
except Exception as e: ok = False
check("GUI-ADM-02", "create user", ok)
try: ads.create_user("tester", "pw12345", ["user"]); check("GUI-ADM-03", "duplicate username rejected", False, "accepted")
except ValueError as e: check("GUI-ADM-03", "duplicate username rejected", True, e)
try: ads.create_user("weak", "1", ["user"]); check("GUI-ADM-04", "password policy enforced (min length)", False, "accepted 1-char password")
except ValueError as e: check("GUI-ADM-04", "password policy enforced (min length)", True, e)
try: ads.create_user("longpw", "a" * 100 + "X", ["user"]); au = AuthService(db); lg = None
except Exception as e: lg = e
try:
    AuthService(db).login("longpw", "a" * 100 + "Y"); check("GUI-ADM-05", "passwords longer than 72 bytes differing after char 72 are distinguished", False, "different password accepted (bcrypt 72-byte truncation)")
except ValueError: check("GUI-ADM-05", "passwords longer than 72 bytes differing after char 72 are distinguished", True)
ads.update_user_status(raw.users.find_one({"username": "tester"})["user_id"], "inactive")
try: AuthService(db).login("tester", "pw12345"); check("GUI-ADM-06", "deactivated user cannot sign in", False)
except ValueError: check("GUI-ADM-06", "deactivated user cannot sign in", True)
try: ads.create_user("rolex", "pw12345", ["nonexistent_role"]); check("GUI-ADM-07", "unknown role rejected", False, "accepted role 'nonexistent_role'")
except ValueError: check("GUI-ADM-07", "unknown role rejected", True)

# ================================================================= INVENTORY / PROCUREMENT UI
win.show_page("Inventory"); pump(root, 4); shot(root, "inventory")
win.show_page("Waste Management"); pump(root, 4)
win.show_page("Procurement"); pump(root, 4); shot(root, "procurement")
win.show_page("DB Connection"); pump(root, 3); shot(root, "db_settings")
finish(root)
