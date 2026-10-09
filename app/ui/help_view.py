"""Help & User Guide: browse the guide by chapter, or type a question in plain words and get the matching topics with the steps.

Opened from the Help menu or F9 (F9 on any screen opens the topic for that screen)."""
from __future__ import annotations

import logging
import re
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

from PIL import Image, ImageTk

from app.services.help_service import HELP_DIR, HelpService
from app.ui import theme

log = logging.getLogger(__name__)

INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[[^\]]+\]\(#[A-Za-z0-9_-]+\))")
LINK = re.compile(r"\[([^\]]+)\]\(#([A-Za-z0-9_-]+)\)")
MAX_IMG_W = 760


class HelpFrame(tk.Frame):
    def __init__(self, parent, help_service: Optional[HelpService] = None, **kwargs):
        super().__init__(parent, bg=theme.BG, **kwargs)
        self.svc = help_service or HelpService()
        self._history: List[Dict[str, Any]] = []
        self._photos: List[Any] = []
        self.current_topic: Optional[str] = None
        self._link_n = 0

        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=28, pady=(18, 6))
        tk.Label(head, text="Help & User Guide", font=theme.F_TITLE, fg=theme.TEXT, bg=theme.BG).pack(side="left")
        self.back_btn = theme.secondary_button(head, "◀ Back", self.back)
        self.back_btn.pack(side="right")
        theme.secondary_button(head, "Contents", self.show_start).pack(side="right", padx=(0, 8))

        bar = tk.Frame(self, bg=theme.SURFACE, highlightbackground=theme.BORDER, highlightthickness=1, padx=12, pady=8)
        bar.pack(fill="x", padx=28, pady=(0, 6))
        tk.Label(bar, text="🔍", font=theme.F_H12B, bg=theme.SURFACE).pack(side="left")
        self.query_var = tk.StringVar()
        self.query_ent = tk.Entry(bar, textvariable=self.query_var, font=theme.F_TEXT11, relief="flat", bd=0)
        self.query_ent.pack(side="left", fill="x", expand=True, padx=8, ipady=4)
        self.query_ent.bind("<Return>", lambda _e: self.search())
        theme.primary_button(bar, "Search", self.search).pack(side="left")
        tk.Label(bar, text="Ask in your own words, for example: how do I return goods?", font=theme.F_SMALL, fg=theme.TEXT_FAINT, bg=theme.SURFACE).pack(side="left", padx=10)

        self.chips = tk.Frame(self, bg=theme.BG)
        self.chips.pack(fill="x", padx=28, pady=(0, 8))
        tk.Label(self.chips, text="Try:", font=theme.F_SMALL, fg=theme.TEXT_MUTED, bg=theme.BG).pack(side="left", padx=(0, 6))
        for phrase in self.svc.suggestions(6):
            chip = tk.Label(self.chips, text=phrase, font=theme.F_SMALL, fg=theme.PRIMARY, bg=theme.HEADING_BG, padx=8, pady=3, cursor="hand2")
            chip.pack(side="left", padx=3)
            chip.bind("<Button-1>", lambda _e, p=phrase: self._ask(p))

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=28, pady=(0, 14))
        left = tk.Frame(body, bg=theme.SURFACE, highlightbackground=theme.BORDER, highlightthickness=1)
        left.pack(side="left", fill="y")
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse", height=24)
        self.tree.column("#0", width=270)
        vs = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._fill_tree()

        right = tk.Frame(body, bg=theme.SURFACE, highlightbackground=theme.BORDER, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.text = tk.Text(right, wrap="word", bg=theme.SURFACE, fg=theme.TEXT, relief="flat", bd=0, padx=24, pady=16, font=theme.F_TEXT10,
                            spacing1=2, spacing3=4, cursor="arrow", state="disabled")
        ts = ttk.Scrollbar(right, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=ts.set)
        ts.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self._configure_tags()
        self.show_start()

    # ------------------------------------------------------------------ plumbing
    def _configure_tags(self):
        t = self.text
        t.tag_configure("h1", font=(theme.FONT, 18, "bold"), foreground=theme.TEXT, spacing1=4, spacing3=8)
        t.tag_configure("h2", font=(theme.FONT, 14, "bold"), foreground=theme.TEXT_STRONG, spacing1=10, spacing3=4)
        t.tag_configure("h3", font=(theme.FONT, 11, "bold"), foreground=theme.PRIMARY, spacing1=8, spacing3=2)
        t.tag_configure("bold", font=(theme.FONT, 10, "bold"))
        t.tag_configure("italic", font=(theme.FONT, 10, "italic"))
        t.tag_configure("code", font=("Consolas", 10), background=theme.HEADING_BG)
        t.tag_configure("muted", foreground=theme.TEXT_MUTED, font=theme.F_SMALL)
        t.tag_configure("quote", background="#fffbeb", foreground="#92400e", lmargin1=14, lmargin2=14, rmargin=14, spacing1=6, spacing3=6)
        t.tag_configure("step", lmargin1=16, lmargin2=34)
        t.tag_configure("bullet", lmargin1=16, lmargin2=30)
        t.tag_configure("block", font=("Consolas", 9), background=theme.HEADING_BG, lmargin1=10, lmargin2=10)
        t.tag_configure("link", foreground=theme.PRIMARY, underline=True)
        t.tag_configure("card_title", font=(theme.FONT, 12, "bold"), foreground=theme.PRIMARY, underline=True, spacing1=10)
        t.tag_configure("why", foreground=theme.SUCCESS, font=theme.F_SMALL)

    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        for ch in self.svc.chapters:
            self.tree.insert("", "end", iid=f"c:{ch['id']}", text=ch["title"], open=False)
            for tid in ch["topics"]:
                t = self.svc.get(tid)
                if t:
                    self.tree.insert(f"c:{ch['id']}", "end", iid=f"t:{tid}", text=t["title"])

    def _on_tree_select(self, _e=None):
        sel = self.tree.selection()
        if sel and sel[0].startswith("t:"):
            self.show_topic(sel[0][2:], from_tree=True)

    def _clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self._photos.clear()
        for tag in [t for t in self.text.tag_names() if t.startswith("lnk")]:
            self.text.tag_delete(tag)

    def _end(self):
        self.text.config(state="disabled")
        self.text.yview_moveto(0)

    def _push(self, entry: Dict[str, Any]):
        if not self._history or self._history[-1] != entry:
            self._history.append(entry)

    # ------------------------------------------------------------------ inline text and links
    def _inline(self, text: str, base_tag: Optional[str] = None):
        tags = (base_tag,) if base_tag else ()
        for part in INLINE.split(text):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**"):
                self.text.insert("end", part[2:-2], tags + ("bold",))
            elif part.startswith("`") and part.endswith("`"):
                self.text.insert("end", part[1:-1], tags + ("code",))
            elif LINK.fullmatch(part):
                label, target = LINK.fullmatch(part).groups()
                self._link(label, target, tags)
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                self.text.insert("end", part[1:-1], tags + ("italic",))
            else:
                self.text.insert("end", part, tags)

    def _link(self, label: str, topic_id: str, tags=()):
        self._link_n += 1
        tag = f"lnk{self._link_n}"
        self.text.insert("end", label, tags + ("link", tag))
        self.text.tag_bind(tag, "<Button-1>", lambda _e, t=topic_id: self.show_topic(t))
        self.text.tag_bind(tag, "<Enter>", lambda _e: self.text.config(cursor="hand2"))
        self.text.tag_bind(tag, "<Leave>", lambda _e: self.text.config(cursor="arrow"))

    # ------------------------------------------------------------------ screens of the help
    def show_start(self):
        self._push({"kind": "start"})
        self.current_topic = None
        self._clear()
        d = self.svc.data
        self.text.insert("end", f"{d.get('title', 'BillDesk User Guide')}\n", "h1")
        self.text.insert("end", "Pick a chapter on the left, or search above in your own words.\n\n", "muted")
        start = self.svc.get("start-here")
        if start:
            self._link("▶ Start here: how to use this help", "start-here")
            self.text.insert("end", "\n\n")
        for ch in self.svc.chapters:
            self.text.insert("end", f"{ch['title']}\n", "h2")
            for tid in ch["topics"]:
                t = self.svc.get(tid)
                if t:
                    self.text.insert("end", "   • ", "bullet")
                    self._link(t["title"], tid)
                    summary = t.get("summary", "")
                    if summary:
                        self.text.insert("end", f" - {summary[:110]}{'…' if len(summary) > 110 else ''}", "muted")
                    self.text.insert("end", "\n")
        self._end()
        self.back_btn.config(state="normal" if len(self._history) > 1 else "disabled")

    def show_topic(self, topic_id: str, from_tree: bool = False):
        t = self.svc.get(topic_id)
        if not t:
            return
        self._push({"kind": "topic", "id": topic_id})
        self.current_topic = topic_id
        self._clear()
        self.text.insert("end", f"{t.get('chapter_title', '')}\n", "muted")
        self.text.insert("end", f"{t['title']}\n", "h1")
        if t.get("screen"):
            self.text.insert("end", f"Screen: {t['screen']}\n", "muted")
        self._render_blocks(t.get("blocks", []))
        rel = self.svc.related(topic_id)
        if rel:
            self.text.insert("end", "\nSee also\n", "h3")
            for r in rel:
                self.text.insert("end", "   • ", "bullet")
                self._link(r["title"], r["id"])
                self.text.insert("end", "\n")
        self._end()
        if not from_tree and self.tree.exists(f"t:{topic_id}"):
            self.tree.selection_set(f"t:{topic_id}")
            self.tree.see(f"t:{topic_id}")
        self.back_btn.config(state="normal" if len(self._history) > 1 else "disabled")

    def _ask(self, phrase: str):
        self.query_var.set(phrase)
        self.search()

    def search(self):
        q = self.query_var.get().strip()
        if not q:
            self.show_start()
            return
        hits = self.svc.search(q)
        self._push({"kind": "search", "q": q})
        self.current_topic = None
        self._clear()
        self.text.insert("end", f"Results for \"{q}\"\n", "h1")
        if not hits:
            self.text.insert("end", "Nothing matched. Try fewer or simpler words (for example \"return\", \"backup\", \"date\"), or browse the chapters on the left.\n\n")
            self.text.insert("end", "Ideas to try\n", "h3")
            for phrase in self.svc.suggestions(8):
                self.text.insert("end", "   • ", "bullet")
                self._link_phrase(phrase)
                self.text.insert("end", "\n")
        else:
            self.text.insert("end", f"{len(hits)} topic{'s' if len(hits) != 1 else ''} found. The best match is first.\n", "muted")
            for n, h in enumerate(hits, start=1):
                self._link_card(f"{n}. {h.topic['title']}", h.topic["id"])
                loc = " > ".join(x for x in (h.topic.get("chapter_title"), h.topic.get("screen")) if x)
                if loc:
                    self.text.insert("end", f"   {loc}\n", "muted")
                if h.why:
                    self.text.insert("end", f"   {h.why}\n", "why")
                if h.snippet:
                    self.text.insert("end", f"   {h.snippet}\n")
                if n <= 3 and h.steps:
                    self.text.insert("end", "   Quick steps:\n", "bold")
                    for i, step in enumerate(h.steps[:4], start=1):
                        self.text.insert("end", f"      {i}. ", "step")
                        self._inline(step)
                        self.text.insert("end", "\n")
        self._end()
        self.back_btn.config(state="normal" if len(self._history) > 1 else "disabled")

    def _link_phrase(self, phrase: str):
        self._link_n += 1
        tag = f"lnk{self._link_n}"
        self.text.insert("end", phrase, ("link", tag))
        self.text.tag_bind(tag, "<Button-1>", lambda _e, p=phrase: self._ask(p))

    def _link_card(self, label: str, topic_id: str):
        self._link_n += 1
        tag = f"lnk{self._link_n}"
        self.text.insert("end", label + "\n", ("card_title", tag))
        self.text.tag_bind(tag, "<Button-1>", lambda _e, t=topic_id: self.show_topic(t))

    def back(self):
        if len(self._history) < 2:
            return
        self._history.pop()
        prev = self._history.pop()
        if prev["kind"] == "topic":
            self.show_topic(prev["id"])
        elif prev["kind"] == "search":
            self.query_var.set(prev["q"])
            self.search()
        else:
            self.show_start()

    def open_topic(self, topic_id: str):
        self.query_var.set("")
        self.show_topic(topic_id)

    def refresh(self):
        """Called each time the page is shown: keep what the user was reading."""
        return None

    # ------------------------------------------------------------------ the blocks of a topic
    def _render_blocks(self, blocks: List[Dict[str, Any]]):
        for b in blocks:
            kind = b.get("t")
            if kind in ("h2", "h3", "h4"):
                self.text.insert("end", b["text"] + "\n", "h2" if kind == "h2" else "h3")
            elif kind == "p":
                self._inline(b["text"])
                self.text.insert("end", "\n")
            elif kind == "ul":
                for item in b["items"]:
                    self.text.insert("end", "  • ", "bullet")
                    self._inline(item, "bullet")
                    self.text.insert("end", "\n")
            elif kind == "ol":
                for i, item in enumerate(b["items"], start=1):
                    self.text.insert("end", f"  {i}. ", "step")
                    self._inline(item, "step")
                    self.text.insert("end", "\n")
            elif kind == "quote":
                self._inline(b["text"], "quote")
                self.text.insert("end", "\n")
            elif kind == "code":
                self.text.insert("end", b["text"] + "\n", "block")
            elif kind == "table":
                self._table(b["rows"])
            elif kind == "image":
                self._image(b["src"], b.get("alt", ""))

    def _table(self, rows: List[List[str]]):
        if not rows:
            return
        frame = tk.Frame(self.text, bg=theme.BORDER)
        ncols = max(len(r) for r in rows)
        for r, row in enumerate(rows):
            for c in range(ncols):
                cell = re.sub(r"\[\[?([^\]]+)\]?\]\(#[^)]+\)", r"\1", row[c] if c < len(row) else "")
                cell = cell.replace("**", "").replace("`", "")
                tk.Label(frame, text=cell, wraplength=250 if ncols > 2 else 330, justify="left", anchor="nw", padx=6, pady=3,
                         font=theme.F_BOLD if r == 0 else theme.F_BODY, bg=theme.HEADING_BG if r == 0 else theme.SURFACE).grid(row=r, column=c, sticky="nsew", padx=(0, 1), pady=(0, 1))
        self.text.window_create("end", window=frame, padx=4, pady=6)
        self.text.insert("end", "\n")

    def _image(self, src: str, alt: str):
        path = HELP_DIR / "img" / src
        if not path.exists():
            self.text.insert("end", f"[{alt or src}]\n", "muted")
            return
        try:
            im = Image.open(path)
            if im.width > MAX_IMG_W:
                im = im.resize((MAX_IMG_W, int(im.height * MAX_IMG_W / im.width)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(im)
        except Exception:
            log.warning("Could not load help image %s", path, exc_info=True)
            return
        self._photos.append(photo)
        self.text.image_create("end", image=photo, padx=4, pady=6)
        self.text.insert("end", "\n")
        if alt:
            self.text.insert("end", alt + "\n", "muted")
