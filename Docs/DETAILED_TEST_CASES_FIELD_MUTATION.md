# BillDesk Native Desktop — Detailed Test Cases: Field Mutation & Cascade Verification

## 1. Overview and Testing Philosophy

In an integrated mandi billing, inventory, procurement, and accounting system, a mutation to a single field in one document typically produces cascading updates across multiple related collections and running aggregates. 

This test specification defines the exact **cause-and-effect relationship** for every field update across the pre-existing collections in `sv_billing`:
- **Direct Dependent Fields:** Values within the same model or form recalculated immediately (e.g., line `amount = qty * rate`, invoice `total_amount = sum(line.amount) + fees`).
- **Cascading Cross-Collection Fields:** Records in external collections updated as a side effect (e.g., stock levels, customer balances, crate counts, journal entries, audit trails).
- **Invariant Rules & Rejections:** Invariants that must be maintained (e.g., non-negative balances, credit limits, double-entry debits = credits, payment allocations $\le$ balance due).

---

## 2. Field Mutation & Reactive Dependency Matrix

```text
┌─────────────────────────┐       recalculates      ┌─────────────────────────┐
│   Source Field Mutated  │ ──────────────────────> │  Direct Dependent Field │
│  (e.g., qty, rate, TDS) │                         │ (amount, total, due)    │
└───────────┬─────────────┘                         └────────────┬────────────┘
            │                                                    │
            │ triggers cascade on commit                         │ verified against
            ▼                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 Cross-Collection Cascading Side Effects                     │
│  - items.stock (±qty)                 - customers.current_balance (±total)  │
│  - stock_transactions (logged)        - customers.crate_balances (±crates)  │
│  - bill_audits (logged)               - journal_entries (sum debit = credit)│
│  - payments.allocation_status         - bills.status (unpaid/partial/paid)  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Comprehensive Test Suite

### Module 1: Billing & Invoice Field Mutations

#### TC-BILL-01: Line Item Quantity (`qty`) Mutation
- **Objective:** Verify that mutating line item quantity recalculates line amount, invoice total, balance due, and on save decrements stock, updates customer balance, and creates an audit entry.
- **Trigger / Mutation:** Change `qty` from `10.0` to `15.0` for an item with `rate = 20.0`.
- **Direct Dependent Field Assertions:**
  - `BillLine.amount`: $15.0 \times 20.0 = 300.0$ (previously 200.0).
  - `Bill.total_amount`: increased by $100.0$.
  - `Bill.balance_due`: increased by $100.0$.
- **Cascading Cross-Collection Assertions (on save):**
  - `items[item_id].stock`: Decremented by $15.0$.
  - `stock_transactions`: Record created with `qty = -15.0`, `type = "sale"`, `reference_id = invoice_no`.
  - `customers[cust_id].current_balance`: Incremented by $300.0$.
  - `bill_audits`: Record created with `action = "CREATE"`.
- **Negative / Boundary Tests:**
  - `qty = 0.0` $\rightarrow$ Raise `ValueError("Quantity must be greater than zero")`.
  - `qty = -5.0` $\rightarrow$ Raise `ValueError("Quantity must be greater than zero")`.

#### TC-BILL-02: Line Item Rate (`rate`) Mutation
- **Objective:** Verify that updating item rate recalculates line amount and invoice totals without mutating stock quantity.
- **Trigger / Mutation:** Change `rate` from $25.0$ to $30.0$ on a line with `qty = 10.0`.
- **Direct Dependent Field Assertions:**
  - `BillLine.amount`: $10.0 \times 30.0 = 300.0$ (previously 250.0).
  - `Bill.total_amount`: $300.0$.
  - `Bill.balance_due`: $300.0$.
- **Cascading Assertions:**
  - `items[item_id].stock`: Decremented only by $10.0$ (quantity unchanged by price edit).
  - `customers[cust_id].current_balance`: Incremented by $300.0$.
- **Negative / Boundary Tests:**
  - `rate = -10.0` $\rightarrow$ Raise `ValueError("Rate cannot be negative")`.

#### TC-BILL-03: Mandi Fee & Commission Rate Mutation
- **Objective:** Verify that adding mandi fee or commission percentage updates total invoice value and customer balance.
- **Trigger / Mutation:** On subtotal $10,000.0$, set `commission_rate = 2.0%` and `mandi_fee_rate = 1.5%`.
- **Direct Dependent Field Assertions:**
  - `Bill.commission_amt`: $10,000 \times 0.02 = 200.0$.
  - `Bill.mandi_fee_amt`: $10,000 \times 0.015 = 150.0$.
  - `Bill.total_amount`: $10,000 + 200 + 150 = 10,350.0$.
  - `Bill.balance_due`: $10,350.0$.
- **Cascading Assertions:**
  - `customers[cust_id].current_balance`: Incremented by $10,350.0$.

#### TC-BILL-04: Crate Movement Fields (`crates_issued`, `crates_returned`)
- **Objective:** Verify that entering crates issued and returned updates customer crate balance and creates crate transaction records.
- **Trigger / Mutation:** In bill form, enter `crates_issued = 5`, `crates_returned = 2`, `crate_item_id = "CRATE-PLASTIC"`.
- **Direct Dependent Field Assertions:**
  - `Bill.crates_issued`: $5.0$.
  - `Bill.crates_returned`: $2.0$.
- **Cascading Cross-Collection Assertions:**
  - `customers[cust_id].crate_balances["CRATE-PLASTIC"]`: Net change $+3$ crates outstanding.
  - `crate_transactions`: Record created with `issued_qty = 5.0`, `returned_qty = 2.0`, `party_id = cust_id`.

#### TC-BILL-05: Customer Field Mutation & Credit Limit Check
- **Objective:** Verify that selecting a customer validates their credit limit against existing balance + new bill total.
- **Trigger / Mutation:** Select customer with `current_balance = 45,000.0` and `credit_limit = 50,000.0`. Enter bill total $6,000.0$.
- **Expected Outcome:**
  - $45,000 + 6,000 = 51,000 > 50,000$.
  - Validation blocks save: Raise `ValueError("Credit limit exceeded (50000.00)")`.
  - Zero mutations committed to `bills`, `items`, `customers`, or `stock_transactions`.
- **Positive Control:**
  - Select customer with `credit_limit = 0.0` (unlimited credit) $\rightarrow$ Bill saves successfully regardless of balance.

#### TC-BILL-06: Bill Void / Cancellation Mutation
- **Objective:** Verify that voiding a bill performs a full financial and stock reversal.
- **Trigger / Mutation:** Call `void_bill(invoice_no)`.
- **Direct Dependent Field Assertions:**
  - `Bill.status`: Changed to `"void"`.
- **Cascading Cross-Collection Assertions:**
  - `items[item_id].stock`: Restored by $+qty$ for all lines.
  - `customers[cust_id].current_balance`: Decremented by $-total\_amount$.
  - `customers[cust_id].crate_balances`: Restored by $-(crates\_issued - crates\_returned)$.
  - `bill_audits`: Record created with `action = "VOID"`.
  - `stock_transactions`: Reversal transaction logged (`type = "adjustment"`, reference = `invoice_no`).

---

### Module 2: Payment & AR Allocation Field Mutations

#### TC-PAY-01: Partial Payment Allocation Mutation
- **Objective:** Verify that recording a partial payment decrements invoice balance due, updates invoice status to `partial`, and reduces customer current balance.
- **Trigger / Mutation:** Customer pays $5,000.0$ against invoice with `total_amount = 8,000.0`, `balance_due = 8,000.0`.
- **Direct Dependent Field Assertions:**
  - `Payment.amount`: $5,000.0$.
  - `Payment.allocations[0].amount`: $5,000.0$.
  - `Payment.allocation_status`: `"full"`.
- **Cascading Cross-Collection Assertions:**
  - `bills[invoice_no].balance_due`: Decreases from $8,000.0$ to $3,000.0$.
  - `bills[invoice_no].status`: Transitions from `"unpaid"` to `"partial"`.
  - `customers[cust_id].current_balance`: Decreases by $5,000.0$.
  - `ledger_transactions`: Entry created (`type = "credit"`, `amount = 5000.0`).

#### TC-PAY-02: Full Payment Settlement Mutation
- **Objective:** Verify that paying the exact remaining balance due marks invoice status as `paid`.
- **Trigger / Mutation:** Record payment of $3,000.0$ against invoice with `balance_due = 3,000.0`.
- **Cascading Cross-Collection Assertions:**
  - `bills[invoice_no].balance_due`: Reaches exactly $0.0$.
  - `bills[invoice_no].status`: Transitions from `"partial"` to `"paid"`.

#### TC-PAY-03: Over-Allocation Invariant Check
- **Objective:** Verify that allocating more than the remaining balance due is rejected.
- **Trigger / Mutation:** Attempt to allocate $6,000.0$ to an invoice with `balance_due = 4,000.0`.
- **Expected Outcome:**
  - System raises `ValueError("Allocation amount 6000.00 exceeds invoice balance due 4000.00")`.
  - Invoice balance due remains $4,000.0$.
  - No payment or ledger mutations saved.

#### TC-PAY-04: Payment Reversal / Deletion Mutation
- **Objective:** Verify that reversing a payment restores invoice balance due and customer outstanding balance.
- **Trigger / Mutation:** Call `reverse_payment(payment_id)`.
- **Cascading Cross-Collection Assertions:**
  - `bills[invoice_no].balance_due`: Restored by $+amount$.
  - `bills[invoice_no].status`: Reverted to `"partial"` or `"unpaid"`.
  - `customers[cust_id].current_balance`: Restored by $+amount$.

---

### Module 3: Customer Fixed Pricing & Contract Rate Mutations

#### TC-PRICE-01: Active Fixed Price Lookup Mutation
- **Objective:** Verify that when a valid fixed price exists, the billing form and price resolver automatically use the contract rate instead of the default item rate.
- **Setup:** Item Tomato default rate = $30.0$. Cust A has active fixed price = $22.0$ valid from 2026-10-01 to 2026-10-31.
- **Test Trigger:** Resolve rate for Cust A on 2026-10-15.
- **Assertion:** Resolved rate = $22.0$ (`is_fixed = True`).

#### TC-PRICE-02: Expired Fixed Price Fallback
- **Test Trigger:** Resolve rate for Cust A on 2026-11-01 (after expiry).
- **Assertion:** Resolved rate = $30.0$ (default rate, `is_fixed = False`).

#### TC-PRICE-03: Fixed Price Value Update Mutation
- **Test Trigger:** Manager edits fixed price rate from $22.0$ to $24.0$.
- **Direct Dependent Field Assertions:**
  - `fixed_prices.rate`: Updated to $24.0$.
- **Cascading Assertions:**
  - Subsequent rate resolutions return $24.0$.
  - Previously saved bills retain their original billed rate (historical integrity preserved).

---

### Module 4: Order Management & 1-Click Conversions

#### TC-ORD-01: Order Item Quantity & Rate Mutation
- **Objective:** Verify that editing order line items dynamically recalculates line amount and order total amount.
- **Trigger / Mutation:** Change order item `qty` from $20.0$ to $50.0$ at `rate = 15.0`.
- **Direct Dependent Field Assertions:**
  - `OrderItem.amount`: $50.0 \times 15.0 = 750.0$ (previously 300.0).
  - `Order.total_amount`: Updated from $300.0$ to $750.0$.

#### TC-ORD-02: 1-Click Convert Order to Bill Mutation
- **Objective:** Verify that converting an order to a bill transitions order status, links invoice number, deducts stock, and debits customer balance.
- **Trigger / Mutation:** Call `convert_order_to_bill(order_id)`.
- **Cascading Cross-Collection Assertions:**
  - `orders[order_id].status`: Transitions from `"pending"` / `"confirmed"` to `"billed"`.
  - `orders[order_id].linked_bill_ids`: Appends the generated `invoice_no`.
  - `bills`: New invoice created with exact items and total from order.
  - `items[item_id].stock`: Decremented by item quantities.
  - `customers[cust_id].current_balance`: Incremented by order total amount.

#### TC-ORD-03: 1-Click Convert Order to Purchase Bill Mutation
- **Objective:** Verify that converting an order to a supplier purchase increments stock and creates purchase bill.
- **Trigger / Mutation:** Call `convert_order_to_purchase(order_id, supplier_id)`.
- **Cascading Cross-Collection Assertions:**
  - `orders[order_id].linked_purchase_ids`: Appends generated `purchase_id`.
  - `purchase_bills`: New purchase bill created.
  - `items[item_id].stock`: Incremented by item quantities (positive stock movement).

---

### Module 5: Procurement & Vendor Bill Field Mutations

#### TC-PROC-01: Purchase Bill Line Item Mutation
- **Trigger / Mutation:** Update purchase item `rate` from $40.0$ to $50.0$ for `qty = 100.0`.
- **Direct Dependent Field Assertions:**
  - `PurchaseItem.amount`: $5,000.0$.
  - `PurchaseBill.total_amount`: $5,000.0$.
  - `PurchaseBill.balance_due`: $5,000.0$ (or net payable).

#### TC-PROC-02: Supplier TDS Deduction Mutation
- **Trigger / Mutation:** Create purchase bill for supplier with `tds_applicable = True`, `tds_rate = 2.0%` on `total_amount = 50,000.0`.
- **Direct Dependent Field Assertions:**
  - `PurchaseBill.tds_amount`: $50,000.0 \times 0.02 = 1,000.0$.
  - `PurchaseBill.payable_amount`: $50,000.0 - 1,000.0 = 49,000.0$.
  - `PurchaseBill.balance_due`: $49,000.0$.
- **Cascading Cross-Collection Assertions:**
  - `suppliers[supplier_id].current_balance`: Incremented by $49,000.0$.

#### TC-PROC-03: Goods Receipt Note (GRN) Mutation
- **Trigger / Mutation:** Record GRN with `qty = 100.0` against PO `ordered_qty = 100.0`.
- **Cascading Cross-Collection Assertions:**
  - `items[item_id].stock`: Incremented by $+100.0$.
  - `stock_transactions`: Record created with `type = "purchase"`, `qty = +100.0`.
  - `purchase_orders.status`: Updated to `"received"`.

---

### Module 6: Inventory Adjustments & Spoilage Field Mutations

#### TC-INV-01: Stock Adjustment Mutation
- **Trigger / Mutation:** Clerk performs manual count adjustment: enter `qty = -12.5`, `reason = "Drying loss"`.
- **Cascading Cross-Collection Assertions:**
  - `items[item_id].stock`: Decremented by $12.5$.
  - `stock_transactions`: Logged with `qty = -12.5`, `type = "adjustment"`.

#### TC-INV-02: Waste Log Recording Mutation
- **Trigger / Mutation:** Clerk logs produce spoilage: `qty = 10.0`, `rate = 25.0`, `reason = "Rotten"`.
- **Direct Dependent Field Assertions:**
  - `WasteLog.amount`: $10.0 \times 25.0 = 250.0$.
- **Cascading Cross-Collection Assertions:**
  - `items[item_id].stock`: Decremented by $10.0$.
  - `stock_transactions`: Logged with `qty = -10.0`, `type = "waste"`.

---

### Module 7: Cash Sessions & Cashier Drawer Field Mutations

#### TC-SESS-01: Cash Transactions Accumulation
- **Trigger / Mutation:** Open session with `opening_cash = 2,000.0`. Execute a cash bill of $3,500.0$ and a cash payment receipt of $500.0$.
- **Direct Dependent Field Assertions:**
  - `Session.expected_cash`: $2,000 + 3,500 + 500 = 6,000.0$.

#### TC-SESS-02: Drawer Close Variance Mutation
- **Trigger / Mutation:** Cashier closes session and enters `actual_cash = 5,950.0`.
- **Direct Dependent Field Assertions:**
  - `Session.difference`: $5,950.0 - 6,000.0 = -50.0$ (shortage).
  - `Session.status`: `"closed"`.
  - `Session.end_time`: Set to current timestamp.

---

### Module 8: General Ledger Double-Entry Invariants

#### TC-GL-01: Balanced Journal Entry Mutation
- **Trigger / Mutation:** Post journal entry with `lines = [debit AR 1500.0, credit Sales 1500.0]`.
- **Assertion:** $\sum\text{Debits} == \sum\text{Credits} = 1500.0$. Saves with `state = "posted"`.

#### TC-GL-02: Unbalanced Journal Entry Rejection
- **Trigger / Mutation:** Post journal entry with `lines = [debit AR 1500.0, credit Sales 1200.0]`.
- **Assertion:** System raises `ValueError("Sum of debits (1500.00) must equal sum of credits (1200.00)")`. Zero entries persisted.

---

## 4. Automation and Execution

All test cases specified above are implemented as automated test functions in `tests/test_field_mutation_cascade.py` using a lightweight in-memory mock MongoDB test harness in `tests/conftest.py`. They can be executed anytime via:

```powershell
python -m pytest tests/ -v
```
