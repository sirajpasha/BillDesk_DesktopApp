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
        total_amount = sum(float(i.qty) * float(i.rate) for i in order_data.items)
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

    def convert_to_bill(self, order_id: str, user_id: str = "system") -> Dict[str, Any]:
        """1-Click convert order into sales invoice, decrement stock, and update customer balance."""
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.get("status") == "billed":
            raise ValueError(f"Order {order_id} is already billed")

        invoice_no = self.bill_repo.next_invoice_number()
        today_str = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now(timezone.utc)

        bill_items = []
        for it in order.get("items", []):
            item_id = it["item_id"]
            qty = float(it["qty"])
            rate = float(it.get("rate", 0.0))
            bill_items.append({
                "item_id": item_id,
                "name": it["name"],
                "qty": qty,
                "unit": it["unit"],
                "rate": rate,
                "amount": qty * rate,
            })
            # Deduct stock
            self.item_repo.decrement_stock(item_id, qty)
            self.inv_repo.record_stock_txn(
                item_id=item_id,
                item_name=it["name"],
                qty=-abs(qty),
                txn_type="sale",
                reference_id=invoice_no,
                notes=f"Converted from Order {order_id}",
                created_by=user_id,
            )

        bill_doc = {
            "invoice_no": invoice_no,
            "invoice_date": today_str,
            "customer_id": order["customer_id"],
            "customer_name": order["customer_name"],
            "items": bill_items,
            "total_amount": float(order["total_amount"]),
            "balance_due": float(order["total_amount"]),
            "status": "unpaid",
            "linked_source_id": order_id,
            "created_by": user_id,
            "created_at": now,
            "is_deleted": 0,
            "currency_code": "INR",
        }
        self.bill_repo.insert_one(bill_doc)

        # Update customer balance
        self.cust_repo.update_balance(order["customer_id"], float(order["total_amount"]))

        # Update order status
        self.order_repo.update_one(
            {"order_id": order_id},
            {"$set": {"status": "billed"}, "$push": {"linked_bill_ids": invoice_no}}
        )
        return {"order_id": order_id, "invoice_no": invoice_no, "total_amount": bill_doc["total_amount"]}

    def convert_to_purchase(self, order_id: str, supplier_id: str, supplier_name: str, user_id: str = "system") -> Dict[str, Any]:
        """Convert order demand into a supplier purchase bill and increment warehouse stock."""
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        purchase_id = self.proc_repo.next_purchase_id()
        now = datetime.now(timezone.utc)

        pur_items = []
        for it in order.get("items", []):
            item_id = it["item_id"]
            qty = float(it["qty"])
            rate = float(it.get("rate", 0.0))
            pur_items.append({
                "item_id": item_id,
                "name": it["name"],
                "qty": qty,
                "unit": it["unit"],
                "rate": rate,
                "amount": qty * rate,
            })
            # Increment stock
            self.item_repo.increment_stock(item_id, qty)
            self.inv_repo.record_stock_txn(
                item_id=item_id,
                item_name=it["name"],
                qty=abs(qty),
                txn_type="purchase",
                reference_id=purchase_id,
                notes=f"Converted from Order {order_id}",
                created_by=user_id,
            )

        pur_doc = {
            "purchase_id": purchase_id,
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "bill_date": now,
            "items": pur_items,
            "total_amount": float(order["total_amount"]),
            "payable_amount": float(order["total_amount"]),
            "balance_due": float(order["total_amount"]),
            "status": "active",
            "created_by": user_id,
            "created_at": now,
            "is_deleted": 0,
        }
        self.proc_repo.bills.insert_one(pur_doc)
        self.supp_repo.update_balance(supplier_id, float(order["total_amount"]))

        self.order_repo.update_one(
            {"order_id": order_id},
            {"$push": {"linked_purchase_ids": purchase_id}}
        )
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
