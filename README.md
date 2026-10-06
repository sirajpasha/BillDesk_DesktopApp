# BillDesk Native Desktop

A true native Python desktop application for BillDesk.

## Architecture

`Tkinter/ttk UI -> Python services -> PyMongo -> MongoDB`

There is no browser, FastAPI server, REST API, Electron, or PyWebView in this application.

## Supported MongoDB modes

- Local: `mongodb://127.0.0.1:27018`
- MongoDB Atlas / remote: any valid `mongodb://` or `mongodb+srv://` URI

## Quick start

1. Install Python 3.12+.
2. Install dependencies: `python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set `MONGODB_URL` / `DB_NAME` if required.
4. Start MongoDB locally or configure Atlas.
5. Run: `python main.py`.

The first launch can use the Settings -> Database Connection dialog to test/save a connection.

## Existing database compatibility

The native app intentionally uses the existing collection names: `users`, `items`, `customers`, `bills`, `stock_transactions`, `bill_audits`, `role_permissions`, etc. It does not require the FastAPI backend to be running.

## Current native slice

- MongoDB connection management
- Login using the existing `users` collection/password hashes
- Local in-process session instead of JWT/WebSession
- RBAC menu filtering via `role_permissions`
- Dashboard shell
- Item/customer lookup
- New Bill workflow
- Existing invoice numbering convention `YYYYMMDD-XXXX`
- Customer credit-limit validation
- Fixed-price lookup
- Inventory deduction + stock transaction
- Customer balance update
- Bill audit record
- Invoice PDF generation
- Bill history
- Database connection settings

## Existing MongoDB index conflict

If the existing BillDesk database already has indexes, the native app reuses an existing index with the same generated name instead of attempting to recreate it. This avoids MongoDB `IndexKeySpecsConflict` errors when the web application created the index previously.

The included `.env` defaults to local MongoDB on port `27018`.
