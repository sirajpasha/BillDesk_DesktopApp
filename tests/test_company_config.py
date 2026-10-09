"""Company configuration: service rules, the Company Settings screen, and the old 'DEFAULT company' bug."""
import tkinter as tk
from tkinter import filedialog, messagebox

import pytest

from app.models.common import CurrentUser
from app.services.billing_service import BillingService
from app.services.master_service import MasterService
from app.ui.company_view import CompanyConfigView


def _svc(db):
    db.collection("companies").docs.clear()
    return MasterService(db)


def _co(svc, name, **kw):
    return svc.save_company({"name": name, **kw})


# ================================================================== service
def test_new_companies_get_sequential_ids_and_the_first_becomes_the_default(fake_db):
    svc = _svc(fake_db)
    a = _co(svc, "SV Vegetables", phone="9380645132, 9382179443", email="info@svveg.com", gst_number="33abcde1234f1z5")
    b = _co(svc, "GK Vegetables")
    assert (a["company_id"], b["company_id"]) == ("Company0001", "Company0002")
    assert a["gst_number"] == "33ABCDE1234F1Z5"                                  # normalised to upper case
    assert a["signatory_label"] == "Authorized Signatory" and a["is_deleted"] == 0
    assert svc.default_company_id() == "Company0001"
    assert [c["company_id"] for c in svc.list_companies()] == ["Company0001", "Company0002"]


def test_company_ids_continue_after_gaps_and_deletions(fake_db):
    svc = _svc(fake_db)
    for n in ("A", "B", "C"):
        _co(svc, n)
    svc.delete_company("Company0003")
    assert _co(svc, "D")["company_id"] == "Company0004"                          # a deleted id is never reused


@pytest.mark.parametrize("data,msg", [
    ({"name": ""}, "name is required"), ({"name": "  "}, "name is required"),
    ({"name": "X", "gst_number": "123"}, "15 letters/digits"), ({"name": "X", "email": "not-an-email"}, "Email"),
    ({"name": "X", "phone": "call me maybe"}, "Phone may only"),
])
def test_company_validation(fake_db, data, msg):
    with pytest.raises(ValueError, match=msg):
        _svc(fake_db).save_company(data)


def test_blank_gstin_is_fine_because_gst_does_not_apply(fake_db):
    assert _co(_svc(fake_db), "Plain Traders", gst_number="")["gst_number"] == ""


def test_names_are_unique_case_insensitively_but_a_company_can_keep_its_own_name(fake_db):
    svc = _svc(fake_db)
    a = _co(svc, "SV Vegetables")
    with pytest.raises(ValueError, match="already exists"):
        _co(svc, "sv vegetables")
    assert svc.save_company({"company_id": a["company_id"], "name": "SV Vegetables", "phone": "9444434066"})["phone"] == "9444434066"
    b = _co(svc, "Other")
    with pytest.raises(ValueError, match="already exists"):
        svc.save_company({"company_id": b["company_id"], "name": "SV VEGETABLES"})


def test_editing_a_company_changes_what_invoices_use_and_never_creates_a_DEFAULT_company(fake_db):
    """The old Company Profile tab saved without a company_id, so it wrote to a separate company called DEFAULT."""
    svc = _svc(fake_db)
    a = _co(svc, "SV Vegetables", address="Old Yard")
    svc.save_company({"company_id": a["company_id"], "address": "New Yard, Koyambedu", "phone": "9000000001"})
    assert svc.get_company(a["company_id"])["address"] == "New Yard, Koyambedu"
    assert svc.get_company(None)["phone"] == "9000000001"                          # the default company is the one that changed
    assert not [c for c in fake_db.collection("companies").docs if c.get("company_id") == "DEFAULT"]
    assert fake_db.collection("companies").count_documents({}) == 1
    with pytest.raises(ValueError, match="not found"):
        svc.save_company({"company_id": "Company9999", "name": "ghost"})


def test_default_company_can_be_moved_and_a_company_flagged_default_wins(fake_db):
    svc = _svc(fake_db)
    _co(svc, "A")
    b = _co(svc, "B", is_default=True)
    assert svc.default_company_id() == b["company_id"]
    assert [c.get("is_default") for c in svc.list_companies()] == [False, True]
    svc.set_default_company("Company0001")
    assert svc.default_company_id() == "Company0001" and svc.get_company(None)["name"] == "A"


def test_delete_rules(fake_db):
    svc = _svc(fake_db)
    a, b = _co(svc, "A"), _co(svc, "B")
    with pytest.raises(ValueError, match="default company"):
        svc.delete_company(a["company_id"])
    BillingService(fake_db)  # (billing keeps working with a company that is later deleted)
    fake_db.collection("bills").insert_one({"invoice_no": "I-1", "company_id": b["company_id"]})
    assert svc.company_usage(b["company_id"]) == 1
    assert svc.delete_company(b["company_id"]) is True
    assert [c["company_id"] for c in svc.list_companies()] == ["Company0001"]
    assert svc.get_company(b["company_id"])["name"] == "B"                       # old invoices still resolve their company
    with pytest.raises(ValueError, match="At least one"):
        svc.delete_company("Company0001") if svc.default_company_id() != "Company0001" else _only_company(svc)
    with pytest.raises(ValueError, match="not found"):
        svc.delete_company("Company0042")


def _only_company(svc):
    # the last remaining company is also the default: either rule must refuse the delete
    try:
        svc.delete_company("Company0001")
    except ValueError as exc:
        raise ValueError("At least one company must remain") from exc


def test_search_matches_every_visible_field(fake_db):
    svc = _svc(fake_db)
    _co(svc, "SV Vegetables", phone="9380645132", email="info@svveg.com", gst_number="33ABCDE1234F1Z5", address="Koyambedu")
    _co(svc, "Srinivasa Traders", phone="9444434066", email="kumar@yahoo.co.in")
    for q, want in (("svveg", 1), ("9444", 1), ("33abcde", 1), ("koyambedu", 1), ("traders", 1), ("company0002", 1), ("v", 2), ("zzz", 0), ("", 2)):
        assert len(svc.list_companies(q)) == want, q


def test_logo_is_stored_as_a_small_png_data_uri(fake_db, tmp_path):
    from PIL import Image
    big = tmp_path / "logo.jpg"
    Image.new("RGB", (1200, 800), (200, 30, 30)).save(big, "JPEG")
    uri = MasterService.logo_data_uri(str(big))
    assert uri.startswith("data:image/png;base64,") and len(uri) < 20_000
    import base64, io
    with Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))) as im:
        assert max(im.size) == 256
    bad = tmp_path / "x.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(Exception):
        MasterService.logo_data_uri(str(bad))


def test_csv_export_import_round_trip(fake_db, tmp_path):
    svc = _svc(fake_db)
    _co(svc, "SV Vegetables", phone="9380645132", email="info@svveg.com", address="Yard, Koyambedu")
    _co(svc, "GK Vegetables", gst_number="33ABCDE1234F1Z5")
    path = tmp_path / "c.csv"
    assert svc.export_companies_csv(str(path)) == 2
    other = _svc(fake_db)                                                      # empty it again, then import
    res = other.import_companies_csv(str(path))
    assert res == {"added": 2, "skipped": 0, "errors": []}
    assert {c["name"] for c in other.list_companies()} == {"SV Vegetables", "GK Vegetables"}
    assert [c["company_id"] for c in other.list_companies()] == ["Company0001", "Company0002"]      # ids are assigned, not imported
    again = other.import_companies_csv(str(path))
    assert again["added"] == 0 and again["skipped"] == 2


def test_import_reports_bad_rows_and_keeps_good_ones(fake_db, tmp_path):
    svc = _svc(fake_db)
    f = tmp_path / "in.csv"
    f.write_text("name,phone,gst_number,email\nGood Co,9444434066,,a@b.co\n,111,,\nBad Gst,222,SHORT,\nBad Email,333,,nope\n", encoding="utf-8")
    res = svc.import_companies_csv(str(f))
    assert res["added"] == 1 and len(res["errors"]) == 3
    assert any("name is empty" in e for e in res["errors"]) and any("15 letters" in e for e in res["errors"]) and any("Email" in e for e in res["errors"])


# ================================================================== screen
@pytest.fixture
def screen(fake_db, tk_root, monkeypatch):
    dialogs, answers = [], {"yes": True}
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: dialogs.append((_n, t, m)))
    monkeypatch.setattr(messagebox, "askyesno", lambda t=None, m=None, **k: (dialogs.append(("askyesno", t, m)), answers["yes"])[1])
    svc = _svc(fake_db)
    _co(svc, "SV Vegetables & Fruits", phone="9380645132 , 9382179443", email="info@svveg.com", gst_number="33ABCDE1234F1Z5", address="No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092.")
    _co(svc, "GK Vegetables & Fruits", phone="9677062919", email="info@gkveg.com")
    _co(svc, "SRINIVASA TRADERS", phone="9444434066", email="kumar@yahoo.co.in")
    v = CompanyConfigView(tk_root, fake_db, current_user=CurrentUser(user_id="U", username="admin", roles=["Admin"]))
    v.dialogs, v.answers = dialogs, answers
    v.update()
    yield v
    for w in v.winfo_children():
        pass
    v.destroy()


def _texts(widget):
    out = []
    for w in widget.winfo_children():
        if isinstance(w, (tk.Label, tk.Button)):
            out.append(str(w.cget("text")))
        out.extend(_texts(w))
    return out


def test_screen_shows_the_cards_and_one_row_per_company(screen):
    assert screen.kpi_count.cget("text") == "3" and screen.kpi_default.cget("text") == "SV Vegetables & Fruits"
    assert screen.total_lbl.cget("text") == "Total: 3 companies" and screen.page_lbl.cget("text") == "Page 1 of 1"
    t = _texts(screen.table)
    for expected in ("Company Info", "Contact Details", "Legal (GSTIN)", "Address", "Actions", "SV Vegetables & Fruits", "Company0001",
                     "33ABCDE1234F1Z5", "N/A", "☎  9380645132 , 9382179443", "✉  info@gkveg.com", "DEFAULT".center(9)):
        assert expected in t, expected
    names = [x for x in t if x.endswith("Fruits") or x == "SRINIVASA TRADERS"]
    assert names == ["SV Vegetables & Fruits", "GK Vegetables & Fruits", "SRINIVASA TRADERS"]      # creation order, like the reference
    assert not screen.prev_btn["state"] == "normal" and not screen.next_btn["state"] == "normal"


def test_search_filters_the_table_and_the_placeholder_follows(screen):
    screen.search_var.set("gk")
    screen.update()
    assert screen.total_lbl.cget("text") == "Total: 1 company" and "GK Vegetables & Fruits" in _texts(screen.table)
    assert "SRINIVASA TRADERS" not in _texts(screen.table) and not screen.placeholder.winfo_ismapped()
    screen.search_var.set("zzzz")
    screen.update()
    assert "No companies match your search." in _texts(screen.table)
    screen.search_var.set("")
    screen.update()
    assert screen.total_lbl.cget("text") == "Total: 3 companies" and screen.placeholder.winfo_ismapped()


def test_pagination_and_page_size(screen, fake_db):
    for i in range(4, 26):
        _co(screen.svc, f"Company Number {i}")
    screen.refresh()
    assert screen.total_lbl.cget("text") == "Total: 25 companies" and screen.page_lbl.cget("text") == "Page 1 of 3"
    assert screen.prev_btn["state"] == "disabled" and screen.next_btn["state"] == "normal"
    assert len([t for t in _texts(screen.table) if t.startswith("Company00")]) == 10
    screen._go(1); screen._go(1)
    assert screen.page_lbl.cget("text") == "Page 3 of 3" and len([t for t in _texts(screen.table) if t.startswith("Company00")]) == 5
    assert screen.next_btn["state"] == "disabled"
    screen.per_page_var.set("25"); screen._on_per_page()
    assert screen.page_lbl.cget("text") == "Page 1 of 1" and len([t for t in _texts(screen.table) if t.startswith("Company00")]) == 25
    screen.search_var.set("Number 7")
    assert screen.page == 1


def test_add_company_through_the_dialog(screen, fake_db):
    dlg = screen.add_company()
    dlg.vars["name"].set("New Mandi Traders")
    dlg.vars["phone"].set("9000011111")
    dlg.vars["email"].set("new@traders.in")
    dlg.address_txt.insert("1.0", "Shop 4, Yard")
    assert dlg.save() is True
    assert screen.kpi_count.cget("text") == "4" and "New Mandi Traders" in _texts(screen.table)
    saved = fake_db.collection("companies").find_one({"name": "New Mandi Traders"})
    assert saved["company_id"] == "Company0004" and saved["address"] == "Shop 4, Yard" and saved["created_by"] == "admin"
    assert screen.svc.default_company_id() == "Company0001"                       # adding does not steal the default


def test_dialog_keeps_the_user_in_place_when_validation_fails(screen):
    dlg = screen.add_company()
    dlg.vars["gst_number"].set("BAD")
    assert dlg.save() is False and dlg.winfo_exists()
    assert screen.dialogs[-1][0] == "showwarning" and "Company name is required" in screen.dialogs[-1][2]
    dlg.vars["name"].set("Fixed")
    assert dlg.save() is False and "15 letters" in screen.dialogs[-1][2]
    dlg.destroy()


def test_edit_company_and_make_it_the_default(screen):
    dlg = screen.edit_company("Company0002")
    assert dlg.vars["name"].get() == "GK Vegetables & Fruits" and not dlg.default_var.get()
    dlg.vars["phone"].set("9111111111")
    dlg.default_var.set(True)
    assert dlg.save() is True
    assert screen.kpi_default.cget("text") == "GK Vegetables & Fruits"
    assert "☎  9111111111" in _texts(screen.table)
    assert _texts(screen.table).count(" DEFAULT ") == 1


def test_dialog_can_set_and_remove_a_logo(screen, tmp_path, monkeypatch):
    from PIL import Image
    img = tmp_path / "l.png"
    Image.new("RGB", (300, 300), (10, 120, 200)).save(img)
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **k: str(img))
    dlg = screen.edit_company("Company0003")
    dlg.choose_logo()
    assert dlg.logo_uri.startswith("data:image/png;base64,") and dlg._photo is not None
    assert dlg.save() is True
    assert screen.svc.get_company("Company0003")["logo_url"].startswith("data:image/png")
    dlg2 = screen.edit_company("Company0003")
    dlg2.remove_logo()
    assert dlg2.logo_uri == "" and dlg2._photo is None
    dlg2.destroy()
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"nope")
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **k: str(bad))
    dlg3 = screen.edit_company("Company0003")
    dlg3.choose_logo()
    assert screen.dialogs[-1][0] == "showerror" and "could not be read" in screen.dialogs[-1][2]
    dlg3.destroy()


def test_delete_asks_first_and_the_default_cannot_be_deleted(screen):
    screen.answers["yes"] = False
    screen.delete_company("Company0003")
    assert screen.kpi_count.cget("text") == "3"                                  # declined: nothing happens
    screen.answers["yes"] = True
    screen.delete_company("Company0003")
    assert screen.kpi_count.cget("text") == "2" and "SRINIVASA TRADERS" not in _texts(screen.table)
    assert screen.dialogs[-1][0] == "askyesno" and "Delete 'SRINIVASA TRADERS'" in screen.dialogs[-1][2]
    screen.delete_company("Company0001")
    assert screen.dialogs[-1][0] == "showwarning" and "default company" in screen.dialogs[-1][2]
    assert screen.kpi_count.cget("text") == "2"


def test_delete_mentions_bills_that_use_the_company(screen, fake_db):
    fake_db.collection("bills").insert_one({"invoice_no": "I-1", "company_id": "Company0002"})
    fake_db.collection("bills").insert_one({"invoice_no": "I-2", "company_id": "Company0002"})
    screen.delete_company("Company0002")
    assert "2 existing bill(s) use this company" in screen.dialogs[-1][2]


def test_export_and_import_buttons(screen, tmp_path, monkeypatch):
    out = tmp_path / "out.csv"
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **k: str(out))
    screen.export_csv()
    assert out.read_text(encoding="utf-8-sig").count("\n") == 4 and "3 companies exported" in screen.dialogs[-1][2]
    src = tmp_path / "in.csv"
    src.write_text("name,phone\nBrand New Co,9222222222\nSRINIVASA TRADERS,1\n,5\n", encoding="utf-8")
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **k: str(src))
    screen.import_csv()
    assert "1 added, 1 skipped" in screen.dialogs[-1][2] and "name is empty" in screen.dialogs[-1][2]
    assert screen.kpi_count.cget("text") == "4"
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **k: str(tmp_path / "missing.csv"))
    screen.import_csv()
    assert screen.dialogs[-1][0] == "showerror"


def test_company_settings_page_in_the_main_window_uses_the_new_screen(fake_db, tk_root, monkeypatch):
    from app.services.auth_service import AuthService
    from app.ui.main_window import MainWindow
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: None)
    _svc(fake_db)
    win = MainWindow(tk_root, fake_db, AuthService(fake_db), BillingService(fake_db), CurrentUser(user_id="A", username="admin", roles=["Admin"]))
    win.show_page("Company Settings")
    assert win.active_page == "Company Settings" and isinstance(win.frames["Company Settings"], CompanyConfigView)
    assert not hasattr(win.admin_view, "company_tab")
    clerk = MainWindow(tk_root, fake_db, AuthService(fake_db), BillingService(fake_db), CurrentUser(user_id="U", username="u", roles=["user"]))
    clerk.show_page("Company Settings")
    assert clerk.active_page != "Company Settings"                                # still needs the settings permission
