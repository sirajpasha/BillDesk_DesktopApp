"""The built-in help: topics from the user guide, searched in plain words ("how do I cancel a bill?") with step-by-step guidance.

The topics live in app/assets/help/guide.json, generated from Docs/BillDesk_Native_User_Guide.md by scripts/build_user_guide.py,
so the printed guide and the help screen can never disagree."""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

HELP_DIR = Path(__file__).resolve().parent.parent / "assets" / "help"

# words people use for the same thing here; every group is treated as one word when searching
SYNONYMS = [
    {"bill", "invoice", "sale", "sales", "billing", "receipt-bill"},
    {"customer", "buyer", "party", "client", "hotel"},
    {"supplier", "vendor", "farmer", "seller"},
    {"return", "returned", "credit-note", "creditnote", "sales-return", "give-back", "bring-back"},
    {"debit-note", "debitnote", "purchase-return"},
    {"cancel", "void", "delete", "remove", "undo", "reverse", "cancelled", "voided"},
    {"pay", "payment", "paid", "receipt", "collect", "collection", "received", "cash", "upi"},
    {"owe", "owes", "due", "outstanding", "balance", "receivable", "receivables", "pending-amount", "unpaid"},
    {"backup", "back-up", "restore", "copy", "safe"},
    {"password", "login", "log-in", "signin", "sign-in", "username", "locked"},
    {"print", "printing", "pdf", "preview", "download", "save-pdf"},
    {"date", "calendar", "day", "when"},
    {"stock", "inventory", "quantity", "qty", "godown"},
    {"waste", "spoilage", "spoiled", "rotten", "damaged", "wastage"},
    {"order", "orders", "enquiry"},
    {"image", "photo", "picture", "ocr", "scan", "whatsapp", "handwritten", "tamil", "translate"},
    {"report", "reports", "daybook", "statement", "ledger", "summary"},
    {"user", "users", "staff", "role", "roles", "access", "permission", "permissions"},
    {"company", "logo", "address", "gstin", "letterhead"},
    {"shortcut", "shortcuts", "key", "keys", "keyboard", "hotkey", "f1", "f2", "f3", "f5"},
    {"error", "problem", "wrong", "not-working", "fails", "failed", "message", "issue", "trouble"},
    {"bank", "banking", "brs", "reconciliation", "cheque", "neft", "ifsc"},
    {"journal", "accounting", "trial", "balance-sheet", "profit", "loss", "p&l"},
    {"crate", "crates", "jali", "returnable"},
    {"park", "parked", "hold", "recall", "pause"},
]
STOP = {"the", "a", "an", "to", "of", "in", "on", "for", "i", "how", "do", "does", "can", "my", "is", "it", "and", "or", "with", "what", "where",
        "want", "need", "should", "when", "from", "this", "that", "me", "we", "you", "please", "there", "are", "be", "by", "at", "get", "make", "use"}


def _stem(w: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


_GROUP: Dict[str, int] = {}
for _i, _g in enumerate(SYNONYMS):
    for _w in _g:
        _GROUP.setdefault(_stem(_w), _i)


def tokens(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9&]+(?:-[a-z0-9]+)*", (text or "").lower())
    out = []
    for w in words:
        if w in STOP:
            continue
        out.append(_stem(w))
        if "-" in w:
            out += [_stem(p) for p in w.split("-") if p not in STOP and len(p) > 1]
    return out


def _canon(tok: str) -> str:
    g = _GROUP.get(tok)
    return f"~{g}" if g is not None else tok


@dataclass
class Hit:
    topic: Dict[str, Any]
    score: float
    snippet: str = ""
    why: str = ""
    steps: List[str] = field(default_factory=list)


class HelpService:
    def __init__(self, data: Optional[Dict[str, Any]] = None, path: Optional[Path] = None):
        if data is None:
            p = path or (HELP_DIR / "guide.json")
            data = json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else {"title": "User Guide", "chapters": [], "topics": {}, "intents": [], "faq": []}
        self.data = data
        self.topics: Dict[str, Dict[str, Any]] = data.get("topics", {})
        self.chapters: List[Dict[str, Any]] = data.get("chapters", [])
        self.intents: List[Dict[str, str]] = data.get("intents", [])
        self.faq: List[Dict[str, str]] = data.get("faq", [])
        self.context: Dict[str, str] = data.get("context", {})
        self._index = {tid: self._prepare(t) for tid, t in self.topics.items()}
        self._vocab = sorted({w for ix in self._index.values() for w in ix["all"]} | set(_GROUP))

    # ------------------------------------------------------------------ lookups
    def get(self, topic_id: str) -> Optional[Dict[str, Any]]:
        return self.topics.get(topic_id)

    def for_page(self, page: str) -> str:
        """The topic that explains the screen the user is on (context help)."""
        return self.context.get(page) or self.context.get((page or "").lower()) or "start-here"

    def related(self, topic_id: str) -> List[Dict[str, Any]]:
        t = self.get(topic_id) or {}
        return [self.topics[r] for r in t.get("related", []) if r in self.topics]

    def chapter_topics(self, chapter_id: str) -> List[Dict[str, Any]]:
        for c in self.chapters:
            if c["id"] == chapter_id:
                return [self.topics[t] for t in c["topics"] if t in self.topics]
        return []

    # ------------------------------------------------------------------ search
    def _prepare(self, t: Dict[str, Any]) -> Dict[str, Any]:
        title = tokens(t.get("title", ""))
        kw = tokens(" ".join(t.get("keywords", [])))
        heads = tokens(" ".join(t.get("headings", [])))
        body = tokens(t.get("text", ""))
        return {"title_x": set(title), "kw_x": set(kw),
                "title": {_canon(w) for w in title}, "kw": {_canon(w) for w in kw}, "heads": {_canon(w) for w in heads},
                "body": [_canon(w) for w in body], "all": set(title + kw + heads + body)}

    def _fix_typos(self, toks: List[str]) -> List[str]:
        fixed = []
        for w in toks:
            if w in self._vocab or len(w) < 4:
                fixed.append(w)
                continue
            near = difflib.get_close_matches(w, self._vocab, n=1, cutoff=0.78)
            fixed.append(near[0] if near else w)
        return fixed

    def search(self, query: str, limit: int = 8) -> List[Hit]:
        raw = tokens(query)
        if not raw:
            return []
        qtoks = self._fix_typos(raw)
        q = [_canon(w) for w in qtoks]
        qtext = " ".join((query or "").lower().split())
        scores: Dict[str, float] = {}
        why: Dict[str, str] = {}
        for tid, ix in self._index.items():
            s = 0.0
            for w in qtoks:                                   # the very word typed (not just a synonym of it) counts for more
                if w in ix["title_x"]:
                    s += 6
                if w in ix["kw_x"]:
                    s += 4
            for w in q:
                if w in ix["title"]:
                    s += 12
                if w in ix["kw"]:
                    s += 8
                if w in ix["heads"]:
                    s += 4
                s += min(ix["body"].count(w), 5) * 1.0
            if qtext and qtext in (self.topics[tid].get("title", "").lower()):
                s += 25
            if s:
                scores[tid] = s
        for intent in self.intents:                                    # "I want to ..." sentences written for exactly this purpose
            itoks = {_canon(w) for w in tokens(intent["phrase"])}
            if not itoks:
                continue
            overlap = len(itoks & set(q)) / max(len(itoks), 1)
            cover = len(itoks & set(q)) / max(len(set(q)), 1)
            if overlap >= 0.5 and cover >= 0.5:
                bonus = 30 * overlap * cover + (20 if qtext and qtext in intent["phrase"].lower() else 0)
                scores[intent["topic"]] = scores.get(intent["topic"], 0) + bonus
                why[intent["topic"]] = f"Matches \"{intent['phrase']}\""
        for f in self.faq:
            ftoks = {_canon(w) for w in tokens(f["q"])}
            if ftoks and len(ftoks & set(q)) / max(len(ftoks), 1) >= 0.5 and f.get("topic") in self.topics:
                scores[f["topic"]] = scores.get(f["topic"], 0) + 15
                why.setdefault(f["topic"], f"Answers: {f['q']}")
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        hits = []
        for tid, sc in ranked:
            t = self.topics[tid]
            hits.append(Hit(t, round(sc, 1), self._snippet(t, qtoks), why.get(tid, ""), list(t.get("steps", []))[:6]))
        return hits

    def _snippet(self, t: Dict[str, Any], qtoks: List[str]) -> str:
        want = {_canon(w) for w in qtoks}
        best, best_n = t.get("summary", ""), 0
        for sent in re.split(r"(?<=[.!?])\s+|\n", t.get("text", "")):
            n = len(want & {_canon(w) for w in tokens(sent)})
            if n > best_n and 20 < len(sent) < 260:
                best, best_n = sent.strip(), n
        return best if best_n >= min(2, len(want)) else t.get("summary", "")

    def suggestions(self, limit: int = 6) -> List[str]:
        """Phrases to try: taken from the guide's own 'I want to...' list."""
        return [i["phrase"] for i in self.intents[:limit]]
