"""Tier 5: compact dashboard, calendar drop-down + cursor flow on New Bill, one customer picker and routed F-keys on New Order,
and the Smart Importer that reads an order photo with Tesseract."""
import os
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox

import pytest

from app.models.billing import BillCreate, BillLine
from app.models.common import CurrentUser
from app.services.billing_service import BillingService
from app.services.ocr_service import SmartOcrService
from app.ui.components.calendar_popup import CalendarPopup, attach_date_picker, parse_date
from tests.conftest import MockMongoDatabase

NIRMALA = r"C:\Windows\Fonts\Nirmala.ttc"
USER = CurrentUser(user_id="U", username="admin", roles=["Admin"])


@pytest.fixture
def quiet(monkeypatch):
    shown = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: shown.append((_n, t, m)))
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    return shown


# ------------------------------------------------------------------ dashboard
def test_dashboard_cards_are_compact_six_across_with_quick_actions(tk_root):
    from app.ui.dashboard import DashboardFrame
    went = []
    f = DashboardFrame(tk_root, MockMongoDatabase(), BillingService(MockMongoDatabase()), USER, on_navigate=went.append)
    try:
        assert len(f.card_widgets) == 18                                   # sales, orders, purchases: six each
        from tkinter import font as tkfont
        for val, _sub in f.card_widgets.values():
            assert int(tkfont.Font(font=val.cget("font")).cget("size")) <= 14
        cols = {int(val.master.grid_info()["column"]) for val, _ in f.card_widgets.values()}
        assert cols == {0, 1, 2, 3, 4, 5}
        assert set(f.quick_buttons) == {"New Bill", "Item Master", "Customer Master", "Supplier Master", "Bill History"}
        for page, btn in f.quick_buttons.items():
            btn.event_generate("<Button-1>")
        f._go("Bill History")
        assert went[-1] == "Bill History"
        assert "pur_yesterday" in f.card_widgets and "pur_last_week" in f.card_widgets
    finally:
        f.destroy()


# ------------------------------------------------------------------ calendar
def test_parse_date_accepts_the_ways_people_type_it():
    assert parse_date("13/10/2026") == date(2026, 10, 13)
    assert parse_date("13 - 10 - 2026", "%d - %m - %Y") == date(2026, 10, 13)
    assert parse_date("13-10-2026") == date(2026, 10, 13) and parse_date("2026-10-13") == date(2026, 10, 13)
    assert parse_date("13.10.26") == date(2026, 10, 13)
    assert parse_date("32/13/2026") is None and parse_date("") is None


def test_picking_a_date_fills_the_box_and_reports_it(tk_root):
    got = []
    ent = tk.Entry(tk_root)
    ent.insert(0, "05/10/2026")
    ctrl = attach_date_picker(ent, "%d/%m/%Y", on_selected=got.append)
    try:
        ctrl.open()
        pop = ctrl.popup
        assert isinstance(pop, CalendarPopup) and pop.selected == date(2026, 10, 5)
        pop._move(7)                                                       # arrow down: a week later
        pop._pick(pop.selected)
        assert ent.get() == "12/10/2026" and got == [date(2026, 10, 12)]
        assert ctrl.popup is None
        ctrl.open()                                                        # suppressed straight after a pick: no re-open
        assert ctrl.popup is None
    finally:
        ent.destroy()


def test_enter_in_the_box_accepts_a_typed_date_and_a_bad_one_stays(tk_root):
    got = []
    ent = tk.Entry(tk_root)
    ctrl = attach_date_picker(ent, "%d/%m/%Y", on_selected=got.append)
    try:
        ent.insert(0, "7-3-26")
        ctrl._typed()
        assert ent.get() == "07/03/2026" and got == [date(2026, 3, 7)]
        ctrl._suppress = False
        ent.delete(0, tk.END)
        ent.insert(0, "garbage")
        ctrl._typed()
        assert got == [date(2026, 3, 7)]
    finally:
        ent.destroy()


# ------------------------------------------------------------------ New Bill flow
@pytest.fixture
def billing(fake_db, tk_root, quiet):
    from app.ui.billing import BillingFrame
    for i in range(1, 8):
        fake_db.collection("items").insert_one({"item_id": f"F{i}", "item_alias": f"F{i}", "name": f"Fruit {i}", "unit": "Kg",
                                                "standard_rate": 10.0, "status": "active", "is_deleted": 0})
    f = BillingFrame(tk_root, fake_db, BillingService(fake_db), USER)
    yield f
    f.destroy()


def test_after_the_customer_the_cursor_goes_to_the_date_then_to_the_next_empty_row(billing):
    focused = []
    billing._focus_date = lambda: focused.append("date")
    billing._apply_customer({"cust_id": "CUST001", "name": "Metro"})
    billing.update()
    billing.after(100)
    billing.update()
    assert focused == ["date"] and billing.customer_var.get() == "Metro"
    for i in range(5):                                                     # five lines already entered
        r = billing.row_widgets[i]
        r["code"].insert(0, f"F{i + 1}")
        billing._on_code_entered(i, focus_next=False)
    assert billing.focus_first_empty_row() == 5                            # the 6th row, Code box
    billing._on_date_chosen(date.today())
    billing.update()


def test_the_bill_date_comes_from_the_date_box(billing, fake_db):
    billing.date_ent.delete(0, tk.END)
    billing.date_ent.insert(0, "05/01/2026")
    assert billing._invoice_date_iso() == "2026-01-05"
    billing.date_ent.delete(0, tk.END)
    billing.date_ent.insert(0, (date.today() + timedelta(days=3)).strftime("%d/%m/%Y"))
    with pytest.raises(ValueError, match="future"):
        billing._invoice_date_iso()
    billing.date_ent.delete(0, tk.END)
    billing.date_ent.insert(0, "nonsense")
    with pytest.raises(ValueError, match="not valid"):
        billing._invoice_date_iso()


def test_a_back_dated_bill_keeps_its_date_and_numbers_itself_by_that_day(fake_db):
    line = BillLine(item_id="ITEM001", name="Tomato", qty=1.0, unit="kg", rate=20.0, amount=20.0)
    bill = BillCreate(invoice_date="2026-01-05", customer_id="CUST001", customer_name="x", items=[line], total_amount=20.0, balance_due=20.0, created_by="t")
    saved = BillingService(fake_db).create_bill(bill)
    assert saved["invoice_no"] == "20260105-0001"
    again = BillingService(fake_db).create_bill(bill.model_copy(update={"invoice_no": None}))
    assert again["invoice_no"] == "20260105-0002"


def test_the_date_box_opens_a_calendar_on_focus_and_a_pick_moves_to_the_items(billing):
    moved = []
    billing.focus_first_empty_row = lambda: moved.append("row") or 0
    ctrl = billing.date_ent._date_picker
    ctrl.open()
    assert ctrl.popup is not None
    ctrl.popup._pick(date.today())
    billing.update()
    billing.after(150)
    billing.update()
    assert moved == ["row"] and billing.date_ent.get() == date.today().strftime("%d/%m/%Y")


# ------------------------------------------------------------------ New Order: one picker, routed keys
# (a full MainWindow per test would use up Windows' limited menu handles, so the routing methods run on a small stand-in)
@pytest.fixture
def routing(fake_db, tk_root, quiet):
    from app.ui.main_window import MainWindow
    from app.ui.order_form_view import OrderFormView
    form = OrderFormView(tk_root, fake_db, current_user=USER)
    bill = __import__("app.ui.billing", fromlist=["BillingFrame"]).BillingFrame(tk_root, fake_db, BillingService(fake_db), USER)

    class Stub:
        ORDER_PAGES = MainWindow.ORDER_PAGES
        _order_form, _on_f2, _on_f3, _on_f5, _on_f8, _on_f10, _on_escape = (MainWindow._order_form, MainWindow._on_f2, MainWindow._on_f3,
                                                                           MainWindow._on_f5, MainWindow._on_f8, MainWindow._on_f10,
                                                                           MainWindow._on_escape)
        def __init__(self):
            self.active_page, self.order_form_view, self.db = "New Order", form, fake_db
            self.frames, self.opened, self.quiet = {"New Bill": bill}, [], quiet

        def show_page(self, name):
            self.opened.append(name)
    yield Stub()
    form.destroy()
    bill.destroy()


def _toplevels(widget):
    return [w for w in widget.winfo_children() if isinstance(w, tk.Toplevel)]


def test_f5_on_the_order_form_opens_the_same_customer_picker_as_new_bill(routing):
    form = routing.order_form_view
    routing._on_f5()
    dlgs = _toplevels(form)
    assert dlgs and dlgs[0].title() == "Select Customer (F5)"
    assert hasattr(dlgs[0], "pick_highlighted")                            # the shared component, keyboard-driven
    cust = routing.db.collection("customers").find_one({"is_deleted": 0})
    dlgs[0].destroy()
    form._apply_customer(cust)
    assert form.customer_var.get() == cust["name"]
    routing.active_page = "New Bill"
    routing._on_f5()
    assert _toplevels(routing.frames["New Bill"])                          # and the bill's own


def test_f3_saves_the_order_f8_opens_the_smart_importer_and_other_pages_are_left_alone(routing):
    form = routing.order_form_view
    routing._on_f3()                                                       # no customer: the save is attempted and says so
    assert routing.quiet[-1][0] == "showwarning" and "customer" in routing.quiet[-1][2].lower()
    routing._on_f8()
    dlg = getattr(form, "smart_dialog", None)
    assert dlg is not None and dlg.winfo_exists() and dlg.title() == "Smart Importer (F8)"
    dlg.destroy()
    routing.active_page = "Dashboard"
    before = len(_toplevels(form))
    routing._on_f8()                                                       # F8 only means something on the order form
    routing._on_escape()                                                   # Esc on another page must not jump to Orders
    assert len(_toplevels(form)) == before and routing.opened == []
    routing._on_f10()
    assert routing.opened == ["Item Master"]                               # F10 keeps its meaning elsewhere


def test_the_order_form_shows_f3_as_save(routing):
    texts = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Label):
                texts.append(c.cget("text"))
            walk(c)
    walk(routing.order_form_view)
    assert "F3" in texts and "F2" not in texts


# ------------------------------------------------------------------ OCR
ITEMS = [{"item_id": "V1", "item_alias": "162", "name": "Tomatto (Country)", "unit": "Kg", "standard_rate": 20},
         {"item_id": "V2", "item_alias": "145", "name": "Onion", "unit": "Kg"},
         {"item_id": "V3", "item_alias": "148", "name": "Potato", "unit": "Kg"},
         {"item_id": "V4", "item_alias": "140", "name": "Brinjal", "unit": "Kg"},
         {"item_id": "V5", "item_alias": "143", "name": "Mint big", "unit": "Bunch"}]
CUSTOMERS = [{"cust_id": "C1", "name": "Anna Stores"}, {"cust_id": "C2", "name": "Raja catering"}]


def test_date_and_customer_are_read_from_the_top_of_the_note():
    assert SmartOcrService.find_date("20.01.26\nANNA") == date(2026, 1, 20)
    assert SmartOcrService.find_date("on ௨௦/௦௧/௨௦௨௬") == date(2026, 1, 20)           # Tamil digits
    assert SmartOcrService.find_date("no date here") is None
    got = SmartOcrService.guess_customer(["ANNA", "தக்காளி 10"], CUSTOMERS)
    assert got["text"] == "ANNA" and got["customer"]["name"] == "Anna Stores"
    unknown = SmartOcrService.guess_customer(["Zzyzx", "x"], CUSTOMERS)
    assert unknown["customer"] is None and unknown["text"] == "Zzyzx"


def test_a_misread_tamil_word_is_still_translated(tk_root):
    o = SmartOcrService()
    assert o._match_produce_item("வங்காயம்", ITEMS)["name"] == "Onion"            # 'வெங்காயம்' with a letter lost
    assert o._match_produce_item("உரளகைகிழங்க", ITEMS)["name"] == "Potato"
    assert o._match_produce_item("தக்காளி", ITEMS)["name"].startswith("Tomatto")


class _NoEngine(SmartOcrService):
    def __init__(self):
        self.tesseract_exe = None
        self.tessdata_dir = None


def test_without_the_engine_the_dialog_says_so_and_offers_nothing_to_import(tk_root, tmp_path, quiet):
    from PIL import Image
    from app.ui.smart_import_dialog import SmartImportDialog
    path = tmp_path / "note.png"
    Image.new("RGB", (300, 200), "white").save(path)
    dlg = SmartImportDialog(tk_root, ITEMS, CUSTOMERS, on_import=lambda *a: None, ocr=_NoEngine())
    try:
        dlg.load_image(str(path), wait=True)
        assert "warnings" in dlg.banner_lbl.cget("text") and "Tesseract" in dlg.msg_lbl.cget("text")
        assert str(dlg.import_btn.cget("state")) == "disabled"
    finally:
        dlg.destroy()


@pytest.mark.skipif(not os.path.exists(NIRMALA), reason="needs the Windows Tamil font to draw a test picture")
def test_a_printed_tamil_order_photo_becomes_english_rows_in_the_order_grid(tk_root, tmp_path, quiet, fake_db):
    from PIL import Image, ImageDraw, ImageFont
    from app.models.common import CurrentUser
    from app.ui.order_form_view import OrderFormView
    if not SmartOcrService().engine_ready() or "tam" not in SmartOcrService().get_available_languages():
        pytest.skip("Tesseract with Tamil data is not available here")
    font = ImageFont.truetype(NIRMALA, 44)
    im = Image.new("RGB", (900, 520), "white")
    d = ImageDraw.Draw(im)
    for i, line in enumerate(["20.01.26", "ANNA", "தக்காளி - 10", "வெங்காயம் - 15", "உருளைக்கிழங்கு - 6", "கத்தரிக்காய் - 2", "புதினா - 2"]):
        d.text((40, 20 + i * 60), line, font=font, fill="black")
    path = tmp_path / "order.png"
    im.save(path)

    for it in ITEMS:
        fake_db.collection("items").insert_one({**it, "status": "active", "is_deleted": 0})
    fake_db.collection("customers").insert_one({"cust_id": "C1", "name": "Anna Stores", "status": "active", "is_deleted": 0})
    form = OrderFormView(tk_root, fake_db, current_user=CurrentUser(user_id="U", username="admin", roles=["Admin"]))
    try:
        dlg = form._open_smart_importer()
        dlg.load_image(str(path), wait=True)
        names = [r["name"] for r in dlg.rows if r["matched"]]
        assert {"Tomatto (Country)", "Onion", "Potato", "Brinjal", "Mint big"} <= set(names)
        assert dlg.order_date == date(2026, 1, 20) and dlg.customer["name"] == "Anna Stores"
        assert dlg.banner_lbl.cget("text").startswith("Data extracted")
        qty = {r["name"]: r["qty"] for r in dlg.rows if r["matched"]}
        assert qty["Tomatto (Country)"] == 10 and qty["Onion"] == 15
        dlg.import_rows()
        filled = [r["item_var"].get() for r in form.row_widgets if r["item_var"].get()]
        assert "Onion" in filled and len(filled) >= 5
        assert form.customer_var.get() == "Anna Stores" and form.date_var.get() == "20 - 01 - 2026"
    finally:
        form.destroy()


def test_a_line_the_ocr_could_not_match_can_be_corrected_before_import(tk_root, quiet):
    from app.ui.smart_import_dialog import SmartImportDialog
    got = []
    dlg = SmartImportDialog(tk_root, ITEMS, CUSTOMERS, on_import=lambda rows, c, d: got.append(rows))
    try:
        dlg._finish({"rows": [{"matched": True, "item_id": "V2", "name": "Onion", "qty": 5, "unit": "Kg", "raw_query": "வெங்காயம்"},
                              {"matched": False, "raw_query": "???", "qty": 2, "unit": "Kg", "name": "???"}],
                     "warnings": ["1 line(s) could not be matched to an item. Check them before importing."], "customer": None, "date": None})
        assert dlg.banner_lbl.cget("text") == "Data extracted with warnings"
        assert dlg.tree.item("1")["values"][0].startswith("?")
        dlg.tree.selection_set("1")
        dlg.edit_selected()
        dlg.rows[1].update({"item_id": "V3", "name": "Potato", "matched": True})       # what saving the correction dialog does
        dlg.edit_dialog.destroy()
        dlg._render()
        dlg.import_rows()
        assert [(r["name"], r["qty"]) for r in got[0]] == [("Onion", 5.0), ("Potato", 2.0)]
    finally:
        if dlg.winfo_exists():
            dlg.destroy()
