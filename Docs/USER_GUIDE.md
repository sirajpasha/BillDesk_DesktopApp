> **This is the guide of the older web version.** The guide for the desktop program (with search, screenshots of every screen, and the same text inside the program under Help / F9) is [BillDesk_Native_User_Guide.md](BillDesk_Native_User_Guide.md).

# BillDesk User Guide

BillDesk (SV Billing) is a billing, stock, orders and accounts system for a vegetable and fruit business. The desktop version runs
on one Windows PC, works without internet, and keeps its data on that PC.

This guide follows a normal working day. Every screen shown here is a real screenshot of the app with sample data
(a small wholesaler called "SV Vegetables & Fruits").

**Contents**
1. [Starting BillDesk](#1-starting-billdesk)
2. [Signing in and finding your way](#2-signing-in-and-finding-your-way)
3. [Dashboard](#3-dashboard)
4. [Billing (making a sale)](#4-billing-making-a-sale)
5. [Bill history](#5-bill-history)
6. [Orders](#6-orders)
7. [Purchases](#7-purchases)
8. [Items, stock, waste and fixed rates](#8-items-stock-waste-and-fixed-rates)
9. [Customers and suppliers](#9-customers-and-suppliers)
10. [Money in and out: receivables, payables and entries](#10-money-in-and-out)
11. [Bank reconciliation](#11-bank-reconciliation)
12. [Reports and printing](#12-reports-and-printing)
13. [Administration](#13-administration)
14. [Keyboard shortcuts](#14-keyboard-shortcuts)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Starting BillDesk

* Open **BillDesk** from the Start menu or run `BillDesk.exe`. The first start takes several seconds while the built-in database
  starts. Do not open it twice; a second copy just brings the first one forward.
* Your data lives in `%APPDATA%\BillDesk\` (type that in the File Explorer address bar). It holds the database, backups, logs
  and uploads. **Uninstalling or updating the program does not delete this folder.** Copy it when you move to a new PC.
* On the very first start the app creates two sample users (see the next section). Change their passwords straight away.
* To use a database on another machine or in the cloud instead of the built-in one, use **BillDesk Database Settings** in the
  Start menu (it edits `billdesk.ini`). Most shops never need this.

## 2. Signing in and finding your way

![Login](user-guide/img/01-login.png)

Sign in with your user name and password. Sample logins created on first start:

| User | Password | Can do |
|---|---|---|
| `admin` | `admin123` | Everything |
| `user` | `user123` | Dashboard, billing and bill history only |

Create real users in **Settings > User Management** (section 13) and then change or remove these two.

### The menu bar

Every screen has the same menu bar at the top and a **shortcut bar at the bottom** that lists the keys that work on that screen.

![Masters menu](user-guide/img/03-menu-masters.png)

| Menu | What is inside |
|---|---|
| **File** | New Bill, Ordering System, Purchase system, Logout, Logout from All Devices, Exit |
| **Masters** | Item Master, Customer Master, Supplier Master, Waste Management |
| **Reports** | Bills History, Order Consolidation, Profit & Loss, Balance Sheet, Fixed Rates, Dashboard |
| **Accounts** | Accounting Dashboard, Trial Balance, Profit & Loss, Balance Sheet, BRS (bank reconciliation), Sales Return, Expense & Income Entry, Handover & Settlement, Accounts Receivables, Accounts Payables |
| **Settings** | OCR Workbench, User Management, Roles & Permissions, Verify Access Audit, User-Customer Mapping, Company Settings, Print Settings, Backup & Recovery, Omnichannel, System Audit Logs |

You only see the menus your role is allowed to use. If a menu item is missing, ask an administrator (section 13, Roles).

## 3. Dashboard

![Dashboard](user-guide/img/02-dashboard.png)

The dashboard shows sales, orders and purchases for today, yesterday, this week, last week, this month and
last month. Sales are counted by **invoice date**, and cancelled or deleted bills are left out. Scroll down for the purchase figures.

## 4. Billing (making a sale)

Open **File > New Bill** or press **F2**.

![Billing screen](user-guide/img/04-billing-empty.png)

1. **Billing Company**: choose the company the bill is issued from (needed when you run more than one).
2. **Doc Type**: *Bill/Invoice*, *Estimate* or *Delivery Note*.
3. **Customer**: press **F5** or click the customer box, type part of the name and click the customer. Leave it as *Cash Customer* for
   a walk-in sale.

   ![Customer search](user-guide/img/05-billing-customer-search.png)

4. **Items**: in the *Code* column type the item code (its alias, for example `201`) and press **Enter**. The name and unit fill in.
   Type the **Qty** and check the **Rate**. If the customer has a *fixed rate* for that item (section 8) the fixed rate is used.
   Add as many rows as you need; the total updates as you type.

   ![Bill with three items](user-guide/img/06-billing-filled.png)

5. Press **F2** (Save Bill) or **F3** (Save & Print). The payment dialog opens:

   ![Payment dialog](user-guide/img/07-billing-payment.png)

   * Check the **amount received**, **payment date** and **method** (Cash, NEFT/RTGS, UPI, Cheque, or **Credit/Due**).
   * **Credit/Due** saves the bill with nothing paid; it then appears under *Accounts Receivable* as unpaid.
   * **Auto FIFO** puts the money against the customer's oldest unpaid bills first; **Manual** lets you choose the bills.
   * Click **Post Payment**. The bill number is shown and stock is reduced by the quantities billed.

Handy: **F6** parks the bill so you can serve someone else and **F7** brings parked bills back. **F8** (Smart Loader) fills the bill
from a photo of an order slip (section 7, OCR).

## 5. Bill history

**Reports > Bills History**.

![Bill history](user-guide/img/08-bills-history.png)

* Search by invoice number or customer name, or pick an invoice date.
* The status shows **unpaid**, **partial** or **paid**.
* The icons at the end of each row download the PDF, open the print view, or edit the bill.
* Editing a bill changes stock and the amount still due to match the new quantities; money already received is kept.
* **Consolidated Bills** prints several bills of one customer as one statement.

## 6. Orders

**File > Ordering System**. Orders record what customers want before it is billed.

![Orders](user-guide/img/12-orders.png)

* **Create New Order** opens the order sheet. Choose the customer (F5), the order and delivery dates, and enter items and quantities.
  The sheet also has *crates out / in* and the commission and mandi fee boxes for market-style trading.

  ![New order](user-guide/img/13-order-new.png)

* In the list, the icons at the end of each row edit the order, convert it to a **sales bill**, convert it to a **purchase bill**
  (hover over an icon to see its name), or delete it.
* Click an order number to open its detail page.

  ![Order detail](user-guide/img/49-order-detail.png)

* **Reports > Order Consolidation** adds up one day's orders per item and customer, which is what you send to the market.

  ![Order consolidation](user-guide/img/24-order-matrix.png)

## 7. Purchases

**File > Purchase system** lists what you bought from suppliers.

![Purchases](user-guide/img/14-purchase.png)

* **Create New Purchase** opens the purchase entry sheet: pick the supplier (F5), type the supplier's bill number and date, then
  enter items, quantities and rates. Saving **adds the quantities to stock** and adds the amount to what you owe the supplier.

  ![New purchase](user-guide/img/36-purchase-new.png)

* **Import (F8)** reads an order slip or supplier bill from a **photo** with the built-in text reader (OCR) and fills the rows.
  Check every line before saving. **Settings > OCR Workbench** is the same tool in a larger view.

  ![OCR workbench](user-guide/img/47-ocr-workbench.png)

  *The reader works offline on printed or typed text (English and Tamil). Handwriting is not reliable, and PDFs are not read, only images.*
* **Purchase Order** lists purchase orders you sent to suppliers.

  ![Purchase orders](user-guide/img/37-purchase-orders.png)

## 8. Items, stock, waste and fixed rates

**Masters > Item Master**.

![Items](user-guide/img/10-items.png)

* **Add Item**: give it an *alias* (the short code you type when billing), a name, a category and a unit.

  ![Add item](user-guide/img/19-add-item.png)

* **Manual Stock** (button on the item screen) corrects stock after a physical count. Enter a plus or minus quantity and a note;
  every change is recorded in the stock history.

  ![Stock adjustment](user-guide/img/17-stock-adjust.png)

* **Masters > Waste Management** records spoiled goods. Waste reduces stock and is kept with the reason.

  ![Waste](user-guide/img/15-waste.png)

* **Fixed Pricing** gives a customer a fixed rate for an item between two dates. While it is valid, billing uses that rate
  automatically. **Reports > Fixed Rates** lists them.

  ![Fixed rates](user-guide/img/16-fixed-rates.png)

## 9. Customers and suppliers

**Masters > Customer Master** and **Masters > Supplier Master**.

![Customers](user-guide/img/09-customers.png)

* **Add Customer / Add Supplier** opens a form. Only the name (and, for customers, the company) is required, but fill in the phone
  number, address and GST number when you have them; they print on the invoice.

  ![Add customer](user-guide/img/18-add-customer.png)

  ![Suppliers](user-guide/img/11-suppliers.png)

  ![Add supplier](user-guide/img/20-add-supplier.png)

* A customer can have a **credit limit**; a bill that would take the customer over the limit is refused.
* An **opening balance** (with its date and *Receivable/Payable* type) brings in what was owed before you started using BillDesk.
* **Export**, **Template** and **Import** move many records at once through a spreadsheet: download the template, fill it, import it.
* The eye, pencil and bin icons view, edit and delete (deleted records are hidden, not erased).

## 10. Money in and out

### Accounts Receivable (what customers owe you)

**Accounts > Accounts Receivables**.

![Receivables, invoices](user-guide/img/32-receivables-invoices.png)

* The cards show the total outstanding, the overdue amount, what is due this week and the average days customers take to pay.
* **Invoices** lists every bill with its due date, balance and status. Filter by status or dates. The icons view the invoice,
  **record a payment** against it, or **send a reminder** to the customer.
* **Record Receipt** (top right) books money received without opening a bill.
* **Payment Register** lists every receipt:

  ![Payment register](user-guide/img/33-receivables-payments.png)

* **Aging Summary** shows, per customer, how much is current and how much is 1-30, 31-60, 61-90 and over 90 days late. *Ledger* shows
  the customer's account and *Statement* downloads a PDF statement.

  ![Aging](user-guide/img/34-receivables-aging.png)

### Accounts Payable (what you owe suppliers)

**Accounts > Accounts Payables**.

![Payables](user-guide/img/35-payables-bills.png)

* Every purchase appears as a bill with its payable amount and due date (the supplier's payment terms, 30 days by default).
* Use the payment icon at the end of a row to pay a bill; the balance due drops by what you pay.
* **Vendor Aging** and **Cash Outflow Forecast** show what falls due and when.

### Sales returns, expenses and the cash drawer

* **Accounts > Sales Return**: search the customer, optionally type the original invoice number, then search each item being returned
  and enter quantity and rate. Tick **To waste?** for goods that cannot be resold. Submitting reduces what the customer owes by the
  refund amount; returned goods go back into stock, and goods marked as waste are logged as waste instead.

  ![Sales return](user-guide/img/29-sales-return.png)

* **Accounts > Expense & Income Entry**: switch between **Expense** and **Income**, type a category (for example Electricity, Fuel,
  Rent), the amount, how it was paid and an optional reference, then press **Record**. Recent entries are listed on the right.

  ![Expense and income](user-guide/img/30-expense-entry.png)

* **Accounts > Handover & Settlement**: at the start of a shift enter the opening cash and press **Start Shift**; at the end
  count the drawer and close the session. The difference between expected and actual cash is kept in the history.

  ![Sessions](user-guide/img/31-handover.png)

## 11. Bank reconciliation

Reconciliation checks your books against the bank's statement so you know every receipt really reached the bank.

**Accounts > BRS**. For payments to show up here, choose the bank account when you record them (NEFT, cheque, UPI) and type the
**reference / UTR number**.

![Bank reconciliation](user-guide/img/38-brs-start.png)

1. Choose the **Bank Account** (a bank account must exist first; an administrator can add it).
2. Click **Choose File** and pick the bank statement as a **.csv** file with these columns in the first row:
   `Date, Description, Reference, Debit, Credit, Balance` (blank cells are fine, for example no Credit on a charge line).
3. Click **Upload & Analyze Statement**. The lines appear.

   ![Statement uploaded](user-guide/img/39-brs-uploaded.png)

4. Click **Run Smart Auto-Match**. BillDesk pairs each statement line with a payment in your books:
   * a **credit** on the statement matches a **receipt** in your books, a **debit** matches a **payment**;
   * the **amount must be exactly the same**;
   * an equal **reference number** makes it a sure match, and a date within three days adds confidence;
   * a line is matched automatically only when it clearly beats every other candidate. Anything doubtful is left for you and the
     message tells you how many possible matches need your review.

   ![After auto-match](user-guide/img/40-brs-matched.png)

5. The cards show how many lines are **Reconciled** and **Unreconciled**. Matched payments are marked reconciled with the bank's
   date as their clearance date. **View BRS Report** lists what is still unmatched on each side (bank charges you have not booked,
   cheques you issued that have not cleared) and the variance.

Running auto-match again is safe: it only looks at lines that are not matched yet.

## 12. Reports and printing

* **Accounts > Accounting Dashboard** is the starting point for the financial reports.

  ![Accounting](user-guide/img/25-accounting-home.png)

* **Trial Balance**, **Profit & Loss** and **Balance Sheet** are built from the postings made by bills, receipts, purchases and entries.

  ![Trial balance](user-guide/img/26-trial-balance.png)

  ![Profit and loss](user-guide/img/27-profit-loss.png)

  ![Balance sheet](user-guide/img/28-balance-sheet.png)

* **Invoices** print from *Bills History* (print or download icons) or straight after saving with **F3**. The layout is a
  three-column invoice with your company details, bill-to and ship-to, and the item table.

  ![Invoice](user-guide/img/48-invoice-print.png)

* **Settings > Print Settings** controls the invoice layout.

  ![Print settings](user-guide/img/42-print-settings.png)

## 13. Administration

*(Administrator screens: Settings menu.)*

### Users and roles

**Settings > User Management** lists the users. **Add User** creates one: user name, password, email, phone, one or more roles
and an *Active/Inactive* status. An inactive user cannot sign in.

![Users](user-guide/img/22-users.png)

![Add user](user-guide/img/21-add-user.png)

**Settings > Roles & Permissions** decides which menu items each role (Admin, Manager, User, Accountant, Purchase Officer,
Customer) can open. Tick or untick a box and the change applies the next time that person signs in.

![Roles](user-guide/img/23-roles.png)

**User-Customer Mapping** limits a customer-role login to its own customers (it then sees only their orders and rates).

![Mapping](user-guide/img/46-user-mapping.png)

### Company, backup, audit

* **Company Settings**: company name, address, phone, GST number and logo that print on invoices.

  ![Company settings](user-guide/img/41-company-settings.png)

* **Backup & Recovery**: choose where backups go (this PC only, or also cloud storage), how many days to keep local backups
  (default 7) and the date format. **Test Backup Now** runs one immediately. The app also backs up automatically at midnight and
  3 pm. Backups are files in `%APPDATA%\BillDesk\backups`; copy that folder to a USB drive or another PC regularly.

  ![Backup](user-guide/img/43-backup.png)

  *There is no "restore" button yet. To go back to a backup, ask whoever supports your installation to restore it.*

* **System Audit Logs**: who did what and when (sign-ins, bills created or edited, settings changed). Passwords are never stored in it.

  ![Audit log](user-guide/img/44-audit-log.png)

* **Omnichannel**: settings for receiving orders from WhatsApp or email and for sending reminders, when those services are configured.

  ![Omnichannel](user-guide/img/45-omnichannel.png)

## 14. Keyboard shortcuts

The function keys are **not the same on every screen**, so read the bar at the bottom of the screen you are on. What the app shows:

| Screen | Keys |
|---|---|
| Billing | **F2** Save Bill (opens the payment dialog), **F3** Save & Print, **F5** Customer Search, **F6** Park Bill, **F7** View Parked Bills, **F8** Smart Loader, **F9** Tender (payment dialog), **F12** Logout |
| Dashboard | **F1** Refresh, **F2** New Bill, **F3** Items, **F4** Customers, **F5** Suppliers, **F6** Bills History, **F12** Logout |
| Customer master | **F1** Search, **F2** Add Customer, **F5** Refresh, **F12** Back |
| Bill history | **F1** Search, **F2** New Bill, **F5** Refresh, **F12** Back |
| Order and purchase sheets | **F5** customer or supplier search, **F8** Smart Loader / Import, **Esc** close |
| Most other screens | **F1** Dashboard, **F2** Billing |

The menus also show a shortcut beside some items (for example **Ctrl+O** for Ordering System, **Ctrl+P** for Purchase system and
**Ctrl+D** for the Accounting Dashboard). If a key does nothing on a particular screen, use the menu instead.


## 15. Troubleshooting

| Problem | What to do |
|---|---|
| Windows says it protected your PC, or the app will not start | The program is not code-signed yet. Choose *More info > Run anyway*, or ask your administrator to allow it. (Windows *Smart App Control* can block it completely.) |
| "Failed to fetch" on the login screen | The app's own server is not running. Close BillDesk fully (check Task Manager) and start it again. |
| A page says "Initializing Session..." and never loads | Reloading a page deep inside the app used to leave it stuck. Update to the latest build; as a workaround close BillDesk completely and start it again, then open the screen from the menu. |
| "Application error: a client-side exception" | Close and reopen BillDesk once. If it comes back, note what you clicked, and send the newest file in `%APPDATA%\BillDesk\logs\` to support. |
| Totals look wrong after a bill was edited | Open the bill again and check the quantities and rates; the stock history (*Manual Stock* screen) shows every change. |
| Bank auto-match found nothing | Amounts must match to the paisa, and the payment must have been recorded with that **bank account**. Check the statement is for the same account and the dates are within ten days. |
| Two copies of the app, or "port already in use" | BillDesk reuses a database it finds running on its own port. If another program holds the port it starts its own on a free one; just restart BillDesk. |
| Where are my files? | `%APPDATA%\BillDesk\` (data, `backups\`, `logs\`, `uploads\`). |
| I forgot the administrator password | Another administrator can set a new one in User Management. If there is none, ask whoever supports your installation. |

---

### For maintainers: refreshing the screenshots

The pictures in this guide are produced by a script, so they can be regenerated whenever the screens change. It runs the app on a
temporary database with sample data and never touches real data:

```powershell
$env:BUILD_TARGET="export"; $env:NEXT_PUBLIC_API_URL="/api"; npm run build     # once, so out/ is current
backend\.venv-build\Scripts\python desktopapp\make_user_guide_shots.py          # writes docs/user-guide/img/*.png
```
