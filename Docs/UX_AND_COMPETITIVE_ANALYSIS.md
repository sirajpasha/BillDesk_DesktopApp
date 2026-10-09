# BillDesk Native: UX / flow audit and competitor comparison

Method: every screen was opened in the running app against a restored copy of the production data (848 bills, 812 orders) at 1380x880 and 1366x700, and the billing keyboard flow was scripted and measured. Competitor facts come from vendor pages and comparison sites; prices differ between sources, so check the vendors before deciding anything. Screenshots are in `Docs/ux-audit/`.

## 1. What looks good (keep)

| Area | Why it works |
| :-- | :-- |
| Billing grid | Spreadsheet-style, keyboard-first, gap compaction, live totals, parked bills that survive a restart. This is the closest thing to how a mandi counter really works. |
| Pricing | Fixed/contract rates per customer, applied automatically. |
| Order intake | WhatsApp-text importer (code-aware), order to bill/purchase conversion, order matrix. |
| Documents | Delivery challan without prices, Bill-To / ship-to consolidated statements, crates in/out on the bill. |
| Accounting | Real double-entry ledger, trial balance, P&L with COGS, balance sheet, integrity check. |
| Safety | Verified backups plus restore, atomic saves (replica set), self-testing installer, audit trail on bills, role permissions. |
| Visual style | Dashboard, Billing, History, Orders, Masters, Finance home, Company Configuration and Integrity share a clean card style. |
| Speed | Startup (login to all screens built) 2.9 s; opening a screen takes 120-490 ms. Acceptable. |

## 2. What to modify (UX defects, by priority)

**P1: can cause wrong bills or block the counter**
1. Billing item search: typing "ban" silently picks "Banana Leaves (E)" out of 9 matches. There is no suggestion list (the order form has one). Wrong-item risk.
2. Customer picker (F5) cannot be used with the keyboard (Down/Enter/Tab do nothing).
3. Payment dialog does not take focus; Enter does not post, Esc does not close.
4. Four Enter presses per line (code, qty, unit, rate). The unit step should be skipped when the item has a default unit.
5. Receivables come from three sources and disagree: Finance Home 1,15,453.20 (bill aging), Customer Master / ledger 47,148.70, and the AR screen shows a customer as owing 2,709.20 where the master shows 29,202.80 credit. Pick the ledger as the single source.
6. Orders KPI says "Total Orders 200" while the database has 812 (query limited to 200).

**P2: confusing or hard to read**
7. Bill History: status shows "active" for 838 of 848 legacy bills; no paid/unpaid/partial view or filter. Action text "Inv DC Edit" is cryptic.
8. Search and date inputs render as thin slivers (Bill History, Orders, Masters).
9. Customer Master columns "Company / DC Company / Customer Name" are unclear; negative balances show as "-₹ 29,202.80" with no "advance / Cr" wording.
10. Item Master Rate column is "-" and live stock is 0 for every item, so the screen looks broken.
11. Dashboard is 12 identical zero tiles: no trend chart, outstanding, low stock, top customers or today's collection.
12. Billing grid shows 20 empty boxes with blank unit combos, no stock or last-price hint; only about 10 rows visible.
13. At 1366x700 the Bill History action buttons are clipped.
14. Fonts are 8-9 pt (186 of 187 labels) and there is no DPI-awareness call, so text is small or blurry on high-DPI laptops.
15. Menu shortcut clashes: F6 (Bills History vs User Management) and F11 (Customer Master vs Company Settings).
16. Empty screens (Procurement) are large blank areas with no guidance on what to do first.

**P3: consistency**
17. Inventory, Procurement, Admin (cash sessions, users) and Database Settings still use the default gray ttk look.
18. Database Settings wording is for developers (URI, Atlas), and the backup panel is buried under "MongoDB Connection". Backup should be its own prominent page.

## 3. What to remove or clean up (tech debt, measured)

| Item | Measure | Action |
| :-- | :-- | :-- |
| Hard-coded colours | 1,184 hex literals, 80 distinct | One `theme.py` with named tokens |
| Fonts | 30 specs, 18 sizes | Define 4-5 text styles |
| Duplicated grid logic | `billing.py` (1,242 lines) and `order_form_view.py` (1,404 lines) share 17 same-named methods | Extract one `LineGrid` widget |
| Legacy ttk screens | 4 with no theming | Port to the card style |
| `messagebox` | 138 calls | Non-blocking toast for success; keep dialogs for confirmations |
| `bind_all` | 24 calls | Scope to the active page to avoid cross-screen key hits |
| Sales return | Model and repo exist, no service or UI | Finish it or delete it |
| CSV export | Only companies and orders | Add to every list or remove the partial feature |
| Localisation | None, English only | Add a string layer before more screens are written |

## 4. Missing features compared with the market

Legend: Yes = present, Part = partly, No = absent, n/a = not applicable.

| Feature | BillDesk | Vyapar | Zoho Books | Tally Prime | Busy / Marg | myBillBook / Khatabook | Mandi software (MandiGrow etc.) |
| :-- | :--: | :--: | :--: | :--: | :--: | :--: | :--: |
| Keyboard-first fast counter billing | **Yes** | Part | No | Part | Yes | No | Yes |
| Per-customer fixed rates | **Yes** | Part | Part | Yes | Yes | No | Yes |
| WhatsApp order text import | **Yes** | No | No | No | No | No | Part |
| Delivery challan without prices | **Yes** | Yes | Yes | Yes | Yes | Part | Yes |
| Crates / returnable packaging ledger | Part (fields on bill) | No | No | No | No | No | **Yes** (per buyer) |
| Double-entry ledger, TB, P&L, BS | Yes | Part | Yes | Yes | Yes | No | Part |
| Verified local backup and restore | **Yes** | Cloud | Cloud | Manual | Manual | Cloud | Cloud |
| Offline / no subscription | **Yes** | Yes | No | Yes | Yes | Part | Part |
| GST invoicing, e-invoice, e-way bill | n/a (not needed) | Yes | Yes | Yes | Yes | Yes | Yes |
| Customer statement / ledger drill-down | **No** | Yes | Yes | Yes | Yes | Yes | Yes |
| Daybook / cashbook | **No** | Yes | Yes | Yes | Yes | Yes | Yes |
| Item-wise / customer-wise sales reports | **No** | Yes | Yes | Yes | Yes | Yes | Yes |
| WhatsApp bill send and payment reminders | **No** | Yes | Yes | Part | Part | Yes | Yes |
| UPI QR on invoice | **No** | Yes | Yes | No | Part | Yes | Part |
| Thermal printer / barcode / weighing scale | **No** (deferred EPIC-09) | Yes | Part | Part | Yes | Part | Yes |
| Low-stock alerts, batch / expiry | **No** | Yes | Yes (higher plans) | Yes | Yes (Marg strong) | Part | Part |
| Farmer / supplier settlement (patti) | **No** | No | No | No | No | No | **Yes** |
| Auto mandi charges (hamali, tulai, market fee, arhat) | Part (commission/fee rates, 0 now) | No | No | No | No | No | **Yes** |
| Tamil / regional-language UI | **No** | Part | Part | Part | Part | Part | **Yes** |
| Mobile app, multi-device sync | **No** | Yes | Yes | Part | Part | Yes | Yes (gate app) |
| Sales returns / credit notes | **No** (data model only) | Yes | Yes | Yes | Yes | Yes | Yes |

Competitor cells are my reading of vendor and comparison pages, not hands-on testing. Treat "Part" as a prompt to verify.

Indicative prices (sources disagree): Vyapar desktop about ₹3,800-4,100 a year; Zoho Books free below ₹25 lakh turnover, paid ₹749-7,999 a month; Tally Prime Silver about ₹22,500 one-time; Busy about ₹5,000-10,000; MandiGrow from about ₹1,999 a month.

**Where BillDesk is already better:** counter speed, fixed-rate handling, WhatsApp order import, price-less challans, local-first with verified backups, no subscription, a genuine ledger with an integrity check.

**Where it loses:** reporting (statements, daybook, item/customer reports), customer communication (WhatsApp, UPI QR, reminders), hardware (thermal, scale), regional language, mobile, and mandi-specific settlement (patti, hamali/tulai).

## 5. Suggested roadmap

1. **Fix the billing flow (P1 items 1-6).** Suggestion list, keyboard customer picker, payment-dialog focus, skip the unit step, one receivables source, Orders count.
2. **Reports people ask for daily.** Customer statement with running balance, daybook/cashbook, item-wise and customer-wise sales, paid/unpaid filter on Bill History.
3. **Visual unification.** `theme.py`, port the four gray screens, fix the sliver inputs, bigger fonts and DPI awareness, a real dashboard.
4. **Customer communication.** UPI QR and a WhatsApp send/reminder (the original EPIC-10 scope).
5. **Mandi specifics.** Crate ledger per buyer, patti/farmer settlement, hamali/tulai/market-fee charges (needs your accounting rules; today the fee is 0).
6. **Hardware.** Thermal printing and scale (EPIC-09).
7. **Tamil UI** via a string layer, then think about mobile.
8. **Tech debt** in parallel: shared `LineGrid`, fewer message boxes, scoped key bindings, finish or delete sales returns.

## 6. Caveats

- Memory use was not measured (my probe returned 0 MB); timing figures are on this machine only.
- Competitor features and prices come from public pages and may be out of date.
- Nothing here has been changed in the code.
