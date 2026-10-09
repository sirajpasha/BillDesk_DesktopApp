"""The user guide and the Help screen (F9): the guide's source, the data built from it, the search, the screen."""
import importlib.util
import re
import sys
import tkinter as tk
from pathlib import Path

import pytest

from app.services.help_service import HELP_DIR, HelpService, tokens

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "Docs"


def _builder():
    spec = importlib.util.spec_from_file_location("build_user_guide", ROOT / "scripts" / "build_user_guide.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod                            # dataclasses look the module up by name
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def guide():
    b = _builder()
    g = b.parse_source((DOCS / "BillDesk_Native_User_Guide.src.md").read_text(encoding="utf-8"))
    return b, g


@pytest.fixture(scope="module")
def svc():
    return HelpService()


# ------------------------------------------------------------------ the source and what was built from it
def test_the_guide_source_is_consistent(guide):
    b, g = guide
    b.validate(g)                                             # unique ids, every link / related topic / image exists
    assert len(g.chapters) == 10 and len(g.topics()) >= 60
    for t in g.topics():
        assert t.keywords, f"{t.id} has no keywords (search could not find it)"
        assert any(bl["t"] in ("p", "ol", "ul", "table") for bl in t.blocks), f"{t.id} has no text"


def test_every_screen_has_a_screenshot_and_every_form_is_covered(guide):
    _, g = guide
    imgs = {Path(bl["src"]).name for t in g.topics() for bl in t.blocks if bl["t"] == "image"}
    on_disk = {p.name for p in (DOCS / "user-guide-native" / "img").glob("*.png")}
    assert imgs <= on_disk
    assert len(imgs) >= 75
    for must in ("10-new-bill-empty", "34-return-goods", "44-smart-importer", "51-add-item", "53-add-customer", "55-add-supplier", "57-add-fixed-rate",
                 "61-stock-adjustment", "63-waste-dialog", "67-add-vendor-bill", "71-return-to-supplier", "82-receipt-dialog", "85-supplier-payment",
                 "87-add-bank", "89-journal-dialog", "111-open-drawer", "113-add-user", "115-company-dialog", "100-daybook", "121-help-search"):
        assert f"{must}.png" in imgs, f"no screenshot of {must}"


def test_the_built_files_are_in_step_with_the_source(guide):
    """Fails when someone edits the .src.md (or a screenshot) and forgets `python scripts/build_user_guide.py`."""
    b, g = guide
    published = (DOCS / "BillDesk_Native_User_Guide.md").read_text(encoding="utf-8")
    assert published == b.published_markdown(g), "Docs/BillDesk_Native_User_Guide.md is out of date: run python scripts/build_user_guide.py"
    import json
    built = json.loads((HELP_DIR / "guide.json").read_text(encoding="utf-8"))
    assert list(built["topics"]) == [t.id for t in g.topics()], "app/assets/help/guide.json is out of date: run python scripts/build_user_guide.py"
    for name in (".docx", ".pdf", ".ipynb"):
        assert (DOCS / f"BillDesk_Native_User_Guide{name}").stat().st_size > 100_000
    imgs = {Path(bl["src"]).name for t in g.topics() for bl in t.blocks if bl["t"] == "image"}
    assert imgs <= {p.name for p in (HELP_DIR / "img").glob("*.png")}


def test_the_notebook_carries_a_working_search(guide):
    import json
    nb = json.loads((DOCS / "BillDesk_Native_User_Guide.ipynb").read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4 and sum(len(c.get("attachments", {})) for c in nb["cells"]) >= 75
    code = "".join(nb["cells"][-1]["source"]).replace("ask('how do I return goods')", "")
    ns = {}
    exec(code, ns)
    assert [h.topic["id"] for h in ns["_help"].search("cancel a bill")][0] == "history-void"
    assert callable(ns["ask"])


# ------------------------------------------------------------------ search
@pytest.mark.parametrize("question,expected", [
    ("how do I return goods", "return-goods"), ("return goods to the supplier", "purchase-return"), ("cancel a bill", "history-void"),
    ("delete bill", "history-void"), ("I made a return by mistake", "cancel-return"), ("who has not paid", "history-filters"),
    ("customer owes money", {"receivables", "statement", "receipt"}), ("backup", "backup"), ("how to back up my data", "backup"),
    ("change the date of the bill", "bill-date"), ("calendar", {"bill-date", "dates-everywhere"}), ("forgot password", "signing-in"),
    ("add a new user", "users"), ("add new item", "items"), ("fixed rate for a customer", "fixed-rates"), ("print invoice", "bill-print"),
    ("read order from photo", "smart-importer"), ("tamil", "smart-importer"), ("pay supplier", "supplier-payment"), ("stock count", "stock-adjust"),
    ("rotten vegetables", "waste"), ("park bill", "bill-park"), ("shortcut keys", "shortcuts"), ("daybook", "daybook"), ("best selling item", "item-wise"),
    ("count the cash drawer", "cash-drawer"), ("company logo", "company"), ("books do not add up", "integrity"), ("trial balance", "statements"),
    ("what does Cr mean", {"customers", "glossary", "faq"}), ("order matrix how much to buy", "order-matrix"), ("convert order to bill", "order-convert"),
    ("credit note", {"credit-notes", "return-goods"}), ("customer statement", "statement"), ("bank ifsc", "banking"), ("crates", "crates"),
])
def test_questions_in_plain_words_find_the_right_topic(svc, question, expected):
    top = [h.topic["id"] for h in svc.search(question, 3)]
    want = expected if isinstance(expected, set) else {expected}
    assert top and (top[0] in want or (isinstance(expected, str) and expected in top[:2])), f"{question!r} -> {top}"


def test_typos_synonyms_and_noise_words_are_forgiven(svc):
    assert svc.search("retun goods")[0].topic["id"] == "return-goods"
    assert svc.search("how can i get my money back from the vendor")[0].topic["id"] in ("purchase-return", "supplier-payment", "vendor-bill", "payables")
    assert svc.search("")  == [] and svc.search("the a an of to") == []
    from app.services.help_service import _canon
    assert _canon(tokens("Cancelling")[0]) == _canon("cancel") == _canon(tokens("voided")[0])


def test_results_carry_the_first_steps_and_why(svc):
    hit = svc.search("how do I return goods")[0]
    assert hit.topic["id"] == "return-goods" and len(hit.steps) >= 3 and hit.snippet
    intent = [h for h in svc.search("sell to a walk-in customer for cash") if h.why]
    assert intent and intent[0].topic["id"] == "bill-customer"


def test_nothing_found_still_offers_ideas(svc):
    assert svc.search("zzzzqqq") == [] and len(svc.suggestions(5)) == 5


# ------------------------------------------------------------------ F9 context help
def test_every_menu_screen_has_its_own_help_topic(svc):
    src = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    pages = set(re.findall(r'\("[^"]+",\s*"([^"]+)",\s*"[^"]*"\)', src))
    pages = {p for p in pages if not p.startswith("/")} - {"Logout", "Exit", "Help", "Help:shortcuts", "Help:messages", "Help:about-guide", "Orders", "Master Data"}
    missing = sorted(p for p in pages if svc.for_page(p) == "start-here")
    assert not missing, f"screens whose F9 would only show the start page: {missing}"
    assert svc.for_page("New Bill") == "new-bill-overview" and svc.for_page("Item Master") == "items"
    assert svc.for_page("Somewhere Else") == "start-here"


def test_the_help_menu_and_f9_are_wired_in_the_main_window():
    from app.ui.main_window import MainWindow
    src = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert '"Help & User Guide", "Help", "F9"' in src and "bind_all(\"<F9>\"" in src
    # F9 on a screen opens that screen's topic; on the Help screen it just focuses the search box
    calls = []

    class Stub:
        active_page = "Bill History"

        def __init__(self):
            self.help_view = type("H", (), {"svc": HelpService(), "open_topic": lambda s, t: calls.append(("topic", t)),
                                            "query_ent": type("E", (), {"focus_set": lambda s: calls.append("focus")})()})()

        def show_page(self, name):
            calls.append(("page", name))
    s = Stub()
    MainWindow._on_f9(s)
    s.active_page = "Help"
    MainWindow._on_f9(s)
    assert calls == [("page", "Help"), ("topic", "history"), "focus"]


# ------------------------------------------------------------------ the Help screen
@pytest.fixture
def help_frame(tk_root):
    from app.ui.help_view import HelpFrame
    f = HelpFrame(tk_root)
    f.pack()
    yield f
    f.destroy()


def _text(f):
    return f.text.get("1.0", "end")


def test_the_contents_lists_every_chapter_and_topic(help_frame, svc):
    assert len(help_frame.tree.get_children()) == 10
    body = _text(help_frame)
    assert "Start here" in body and "Return goods (credit note)" in body and "Cancel a return" in body
    topics_in_tree = sum(len(help_frame.tree.get_children(c)) for c in help_frame.tree.get_children())
    assert topics_in_tree == len(svc.topics)


def test_searching_shows_results_with_steps_and_a_link_opens_the_topic(help_frame):
    help_frame.query_var.set("how do I return goods")
    help_frame.search()
    body = _text(help_frame)
    assert "Results for \"how do I return goods\"" in body and "Return goods (credit note)" in body and "Quick steps" in body
    help_frame.show_topic("return-goods")
    body = _text(help_frame)
    assert "Press Return Goods" in body.replace("\n", " ") or "Return Goods" in body
    assert help_frame._photos, "the topic's screenshot is not shown"
    assert "See also" in body
    help_frame.back()                                          # back to the search results
    assert "Results for" in _text(help_frame)


def test_a_search_with_no_match_offers_ideas(help_frame):
    help_frame.query_var.set("zzzzqqq")
    help_frame.search()
    assert "Nothing matched" in _text(help_frame) and "Ideas to try" in _text(help_frame)


def test_tables_links_and_chips_work(help_frame):
    help_frame.show_topic("start-here")
    assert help_frame.text.window_names(), "the 'I want to...' table is not shown"
    chips = [w for w in help_frame.chips.winfo_children() if isinstance(w, tk.Label) and w.cget("text") != "Try:"]
    assert chips
    help_frame._ask(chips[0].cget("text"))
    assert help_frame.query_var.get() == chips[0].cget("text") and "Results for" in _text(help_frame)


def test_open_topic_selects_it_in_the_contents(help_frame):
    help_frame.open_topic("bill-date")
    assert help_frame.current_topic == "bill-date" and help_frame.tree.selection() == ("t:bill-date",)
