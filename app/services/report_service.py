"""Day-to-day reports: daybook, item-wise sales, customer-wise sales."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.utils.currency import money


def _dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str) and value:
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return d.replace(tzinfo=None) if d.tzinfo else d
        except ValueError:
            return None
    return None


def _f(v: Any) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


class ReportService:
    def __init__(self, db: Any):
        self.db = db

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _bounds(date_from: Optional[datetime], date_to: Optional[datetime]):
        lo = _dt(date_from)
        hi = _dt(date_to)
        if lo is not None:
            lo = lo.replace(hour=0, minute=0, second=0, microsecond=0)
        if hi is not None:
            hi = hi.replace(hour=23, minute=59, second=59, microsecond=999999)
        return lo, hi

    @staticmethod
    def _within(d: Optional[datetime], lo, hi) -> bool:
        if d is None:
            return lo is None and hi is None
        return (lo is None or d >= lo) and (hi is None or d <= hi)

    def _live_bills(self, lo, hi) -> List[Dict[str, Any]]:
        out = []
        for b in self.db.collection("bills").find({"is_deleted": 0, "status": {"$nin": ["void", "cancelled"]}}):
            d = _dt(b.get("invoice_date") or b.get("created_at"))
            if self._within(d, lo, hi):
                b = dict(b)
                b["_date"] = d
                out.append(b)
        return out

    def _returns(self, lo, hi) -> List[Dict[str, Any]]:
        out = []
        for r in self.db.collection("sales_returns").find({"is_deleted": 0, "status": {"$ne": "cancelled"}}):
            d = _dt(r.get("return_date") or r.get("created_at"))
            if self._within(d, lo, hi):
                r = dict(r)
                r["_date"] = d
                out.append(r)
        return out

    # ------------------------------------------------------------------ daybook
    def daybook(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> Dict[str, Any]:
        """Every money event in date order. `money_in` / `money_out` are cash-or-bank movements; sales and purchases on
        credit are shown for the record (in the Billed / Bought columns) but are not money moved yet."""
        lo, hi = self._bounds(date_from, date_to)
        rows: List[Dict[str, Any]] = []
        for b in self._live_bills(lo, hi):
            rows.append({"date": b["_date"], "type": "Sale", "ref": b.get("invoice_no", ""), "party": b.get("customer_name", ""),
                         "billed": _f(b.get("total_amount")), "bought": 0.0, "money_in": 0.0, "money_out": 0.0})
        for r in self._returns(lo, hi):
            walk_in = not r.get("customer_id") or r.get("customer_id") == "CASH"
            rows.append({"date": r["_date"], "type": "Return", "ref": r.get("return_id", ""), "party": r.get("customer_name", ""),
                         "billed": -_f(r.get("total_refund_amount")), "bought": 0.0, "money_in": 0.0,
                         "money_out": _f(r.get("total_refund_amount")) if walk_in else 0.0})
        for p in self.db.collection("payments").find({"is_deleted": {"$ne": 1}}):
            d = _dt(p.get("payment_date") or p.get("created_at"))
            if not self._within(d, lo, hi):
                continue
            rows.append({"date": d, "type": "Receipt", "ref": p.get("payment_id", ""), "party": p.get("party_id", ""),
                         "billed": 0.0, "bought": 0.0, "money_in": _f(p.get("amount")), "money_out": 0.0})
        for p in self.db.collection("purchase_bills").find({"is_deleted": 0}):
            d = _dt(p.get("bill_date") or p.get("created_at"))
            if self._within(d, lo, hi):
                rows.append({"date": d, "type": "Purchase", "ref": p.get("purchase_id", ""), "party": p.get("supplier_name", ""),
                             "billed": 0.0, "bought": _f(p.get("payable_amount")), "money_in": 0.0, "money_out": 0.0})
        for p in self.db.collection("ap_payments").find({"is_deleted": {"$ne": 1}}):
            d = _dt(p.get("payment_date") or p.get("created_at"))
            if self._within(d, lo, hi):
                rows.append({"date": d, "type": "Paid out", "ref": p.get("payment_id", p.get("purchase_id", "")), "party": p.get("supplier_id", ""),
                             "billed": 0.0, "bought": 0.0, "money_in": 0.0, "money_out": _f(p.get("net_amount_paid"))})
        order = {"Sale": 0, "Return": 1, "Purchase": 2, "Receipt": 3, "Paid out": 4}
        rows.sort(key=lambda r: (r["date"] or datetime.min, order.get(r["type"], 9), str(r["ref"])))
        totals = {k: money(sum(r[k] for r in rows)) for k in ("billed", "bought", "money_in", "money_out")}
        totals["net_money"] = money(totals["money_in"] - totals["money_out"])
        return {"rows": rows, "totals": totals}

    # ------------------------------------------------------------------ item-wise
    def item_sales(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> Dict[str, Any]:
        lo, hi = self._bounds(date_from, date_to)
        agg: Dict[str, Dict[str, Any]] = {}

        def slot(item_id, name, unit):
            s = agg.setdefault(item_id, {"item_id": item_id, "name": name, "unit": unit, "qty": 0.0, "amount": 0.0,
                                         "bills": set(), "returned_qty": 0.0, "returned_amount": 0.0, "names": Counter()})
            s["names"][name] += 1                  # older bills let the name be typed over the code: label by the usual one
            return s
        for b in self._live_bills(lo, hi):
            for l in b.get("items", []):
                s = slot(l.get("item_id"), l.get("name", ""), l.get("unit", ""))
                s["qty"] += _f(l.get("qty"))
                s["amount"] += _f(l.get("amount"))
                s["bills"].add(b.get("invoice_no"))
        for r in self._returns(lo, hi):
            for l in r.get("items", []):
                s = slot(l.get("item_id"), l.get("name", ""), l.get("unit", ""))
                s["returned_qty"] += _f(l.get("qty"))
                s["returned_amount"] += _f(l.get("amount"))
        rows = []
        for s in agg.values():
            net_qty, net_amt = s["qty"] - s["returned_qty"], s["amount"] - s["returned_amount"]
            rows.append({"item_id": s["item_id"], "name": s["names"].most_common(1)[0][0] or s["name"], "unit": s["unit"], "bills": len(s["bills"]),
                         "qty": round(s["qty"], 3), "returned_qty": round(s["returned_qty"], 3), "net_qty": round(net_qty, 3),
                         "net_amount": money(net_amt), "avg_rate": money(net_amt / net_qty) if net_qty > 0 else 0.0})
        rows.sort(key=lambda r: r["net_amount"], reverse=True)
        return {"rows": rows, "totals": {"net_amount": money(sum(r["net_amount"] for r in rows)), "items": len(rows)}}

    # ------------------------------------------------------------------ customer-wise
    def customer_sales(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> Dict[str, Any]:
        lo, hi = self._bounds(date_from, date_to)
        agg: Dict[str, Dict[str, Any]] = {}

        def slot(cid, name):
            return agg.setdefault(cid, {"customer_id": cid, "name": name, "bills": 0, "billed": 0.0, "returned": 0.0})
        for b in self._live_bills(lo, hi):
            s = slot(b.get("customer_id"), b.get("customer_name", ""))
            s["bills"] += 1
            s["billed"] += _f(b.get("total_amount"))
        for r in self._returns(lo, hi):
            slot(r.get("customer_id"), r.get("customer_name", ""))["returned"] += _f(r.get("total_refund_amount"))
        balances = {c.get("cust_id"): _f(c.get("current_balance")) for c in self.db.collection("customers").find({"is_deleted": 0})}
        rows = []
        for s in agg.values():
            rows.append({"customer_id": s["customer_id"], "name": s["name"], "bills": s["bills"], "billed": money(s["billed"]),
                         "returned": money(s["returned"]), "net": money(s["billed"] - s["returned"]),
                         "balance": balances.get(s["customer_id"], 0.0)})
        rows.sort(key=lambda r: r["net"], reverse=True)
        return {"rows": rows, "totals": {"net": money(sum(r["net"] for r in rows)), "customers": len(rows),
                                         "bills": sum(r["bills"] for r in rows)}}
