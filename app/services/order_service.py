from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid
from app.repositories.order_repo import OrderRepository
from app.repositories.master_repo import ItemRepository, CustomerRepository, SupplierRepository
from app.repositories.billing_repo import BillRepository
from app.repositories.procurement_repo import ProcurementRepository
from app.repositories.inventory_repo import InventoryRepository
from app.models.order import OrderCreate, OrderItem
from app.models.billing import BillCreate, BillItem
from app.utils.currency import money
from app.services.billing_service import BillingService
from app.services.procurement_service import ProcurementService

class OrderService:
    def __init__(self, db: Any):
        self.db = db
        self.order_repo = OrderRepository(db)
        self.item_repo = ItemRepository(db)
        self.cust_repo = CustomerRepository(db)
        self.supp_repo = SupplierRepository(db)
        self.bill_repo = BillRepository(db)
        self.proc_repo = ProcurementRepository(db)
        self.inv_repo = InventoryRepository(db)
        self.billing_svc = BillingService(db)
        self.procurement_svc = ProcurementService(db)

    def next_order_number(self) -> str:
        return self.order_repo.next_order_number()

    def get_orders(self, query: str = "", status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return self.order_repo.search_orders(query, status, limit)

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        return self.order_repo.find_one({"order_id": order_id, "is_deleted": 0})

    def create_order(self, order_data: OrderCreate) -> Dict[str, Any]:
        if not order_data.items:
            raise ValueError("Order must contain at least one item")
        for item in order_data.items:
            if item.qty <= 0:
                raise ValueError("Item quantity must be greater than zero")

        order_id = self.next_order_number()
        total_amount = money(sum(money(float(i.qty) * float(i.rate)) for i in order_data.items))
        now = datetime.now(timezone.utc)

        doc = {
            "order_id": order_id,
            "order_date": order_data.order_date or now,
            "delivery_date": order_data.delivery_date or now,
            "customer_id": order_data.customer_id,
            "customer_name": order_data.customer_name,
            "company_id": order_data.company_id,
            "items": [i.model_dump() for i in order_data.items],
            "total_amount": total_amount,
            "status": order_data.status or "pending",
            "crates_issued": int(order_data.crates_issued or 0),
            "crates_returned": int(order_data.crates_returned or 0),
            "commission_amt": float(order_data.commission_amt or 0.0),
            "mandi_fee_amt": float(order_data.mandi_fee_amt or 0.0),
            "linked_bill_ids": [],
            "linked_purchase_ids": [],
            "is_deleted": 0,
            "notes": order_data.notes,
            "created_at": now,
            "created_by": order_data.created_by,
        }
        return self.order_repo.insert_one(doc)

    def update_order(self, order_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing customer order."""
        existing = self.get_order(order_id)
        if not existing:
            raise ValueError(f"Order {order_id} not found")
        
        now = datetime.now(timezone.utc)
        clean_update = {**update_data, "updated_at": now}
        clean_update.pop("_id", None)
        clean_update.pop("order_id", None)
        
        self.order_repo.update_one({"order_id": order_id}, {"$set": clean_update})
        return self.get_order(order_id) or {}

    CONVERTIBLE_STATUSES = ("pending", "confirmed", "delivered")

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.get("status") == "billed" or order.get("linked_bill_ids"):
            raise ValueError(f"Order {order_id} is already billed (invoice {', '.join(order.get('linked_bill_ids') or [])}); void the invoice instead")
        if order.get("status") == "cancelled":
            raise ValueError(f"Order {order_id} is already cancelled")
        self.order_repo.update_one({"order_id": order_id}, {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc)}})
        return self.get_order(order_id) or {}

    def convert_to_bill(self, order_id: str, user_id: str = "system") -> Dict[str, Any]:
        """1-Click convert order into a sales invoice.

        Goes through BillingService.create_bill so the invoice gets exactly the same controls as a bill
        keyed in at the counter: credit-limit check, stock decrement + stock transactions, due date,
        crate handling and the CREATE audit row.
        """
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        status = order.get("status")
        if status == "billed" or order.get("linked_bill_ids"):
            raise ValueError(f"Order {order_id} is already billed")
        if status not in self.CONVERTIBLE_STATUSES:
            raise ValueError(f"Order {order_id} is '{status}' and cannot be converted to a bill")

        # Claim the order so a second click / second counter cannot convert it twice.
        if not self.order_repo.update_one({"order_id": order_id, "status": status}, {"$set": {"status": "billing"}}):
            raise ValueError(f"Order {order_id} is being converted by someone else")
        try:
            lines = []
            for it in order.get("items", []):
                qty, rate = float(it["qty"]), float(it.get("rate", 0.0))
                lines.append(BillItem(item_id=it["item_id"], item_alias=it.get("item_alias"), name=it["name"],
                                      qty=qty, unit=it["unit"], rate=rate, amount=money(qty * rate)))
            total = money(sum(l.amount for l in lines))      # the invoice total always equals its lines
            bill = self.billing_svc.create_bill(BillCreate(
                invoice_date=datetime.now().strftime("%Y-%m-%d"),
                customer_id=order["customer_id"], customer_name=order["customer_name"], company_id=order.get("company_id"),
                items=lines, total_amount=total, balance_due=total, created_by=user_id,
                crates_issued=float(order.get("crates_issued") or 0), crates_returned=float(order.get("crates_returned") or 0),
                notes=f"Converted from Order {order_id}",
            ))
        except Exception:
            self.order_repo.update_one({"order_id": order_id, "status": "billing"}, {"$set": {"status": status}})
            raise

        invoice_no = bill["invoice_no"]
        self.bill_repo.update_one({"invoice_no": invoice_no}, {"$set": {"linked_source_id": order_id}})
        self.order_repo.update_one(
            {"order_id": order_id},
            {"$set": {"status": "billed"}, "$push": {"linked_bill_ids": invoice_no}}
        )
        return {"order_id": order_id, "invoice_no": invoice_no, "total_amount": total}

    def convert_to_purchase(self, order_id: str, supplier_id: str, supplier_name: str = "", user_id: str = "system") -> Dict[str, Any]:
        """Convert order demand into a supplier purchase bill (TDS applied) and increment warehouse stock."""
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.get("status") == "cancelled":
            raise ValueError(f"Order {order_id} is cancelled and cannot be converted to a purchase")
        if order.get("linked_purchase_ids"):
            raise ValueError(f"Order {order_id} is already converted to purchase {', '.join(order['linked_purchase_ids'])}")

        items = [{"item_id": it["item_id"], "name": it["name"], "qty": float(it["qty"]), "unit": it["unit"],
                  "rate": float(it.get("rate", 0.0)), "amount": float(it["qty"]) * float(it.get("rate", 0.0))}
                 for it in order.get("items", [])]
        # Validates the supplier, computes TDS/payable and books the supplier balance.
        pur = self.procurement_svc.create_purchase_bill(
            supplier_id=supplier_id, supplier_bill_no=order_id, items=items,
            notes=f"Converted from Order {order_id}", user_id=user_id,
        )
        purchase_id = pur["purchase_id"]
        for it in items:
            self.item_repo.increment_stock(it["item_id"], it["qty"])
            self.inv_repo.record_stock_txn(
                item_id=it["item_id"], item_name=it["name"], qty=abs(it["qty"]), txn_type="purchase",
                reference_id=purchase_id, notes=f"Converted from Order {order_id}", created_by=user_id,
            )
        self.order_repo.update_one({"order_id": order_id}, {"$push": {"linked_purchase_ids": purchase_id}})
        return {"order_id": order_id, "purchase_id": purchase_id}

    def get_order_matrix(self, delivery_date: Optional[str] = None) -> Dict[str, Any]:
        """Generate Order Matrix (Item x Customer Demand vs Current Stock & Shortfall)."""
        filter_doc: Dict[str, Any] = {"status": {"$in": ["pending", "confirmed"]}, "is_deleted": 0}
        orders = self.order_repo.find(filter_doc)

        items_map: Dict[str, Dict[str, Any]] = {}
        customers_set = set()

        for ord in orders:
            cust_name = ord.get("customer_name", "Unknown")
            customers_set.add(cust_name)
            for it in ord.get("items", []):
                i_id = it["item_id"]
                if i_id not in items_map:
                    db_item = self.item_repo.find_one({"item_id": i_id}) or {}
                    items_map[i_id] = {
                        "item_id": i_id,
                        "name": it.get("name", i_id),
                        "unit": it.get("unit", "kg"),
                        "current_stock": float(db_item.get("stock", 0.0)),
                        "total_demand": 0.0,
                        "customer_demand": {},
                    }
                qty = float(it.get("qty", 0.0))
                items_map[i_id]["total_demand"] += qty
                items_map[i_id]["customer_demand"][cust_name] = (
                    items_map[i_id]["customer_demand"].get(cust_name, 0.0) + qty
                )

        customers = sorted(list(customers_set))
        matrix_rows = []
        for i_id, data in items_map.items():
            shortfall = max(0.0, data["total_demand"] - data["current_stock"])
            row = {
                "item_id": data["item_id"],
                "name": data["name"],
                "unit": data["unit"],
                "current_stock": data["current_stock"],
                "total_demand": data["total_demand"],
                "shortfall": shortfall,
                "customer_quantities": [data["customer_demand"].get(c, 0.0) for c in customers],
            }
            matrix_rows.append(row)

        return {"customers": customers, "rows": matrix_rows}
