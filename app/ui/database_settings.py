import tkinter as tk
from tkinter import ttk, messagebox

from app.database.connection import MongoDatabase
from app.config.settings import Settings


class DatabaseSettingsFrame(ttk.Frame):
    def __init__(self, parent, db, billing=None):
        super().__init__(parent, padding=10)
        self.db = db
        ttk.Label(self, text="MongoDB Connection", style="Title.TLabel").pack(anchor="w", pady=(0, 20))

        form = ttk.Frame(self)
        form.pack(fill="x", anchor="nw")
        ttk.Label(form, text="MongoDB URI").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=8)
        default_url = getattr(self.db.settings, "mongodb_url", "mongodb://127.0.0.1:27018") if hasattr(self.db, "settings") and self.db.settings else "mongodb://127.0.0.1:27018"
        default_db = getattr(self.db.settings, "db_name", "sv_billing") if hasattr(self.db, "settings") and self.db.settings else "sv_billing"
        self.url = ttk.Entry(form, width=70)
        self.url.insert(0, default_url)
        self.url.grid(row=0, column=1, sticky="ew", pady=8)
        ttk.Label(form, text="Database").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=8)
        self.name = ttk.Entry(form, width=50)
        self.name.insert(0, default_db)
        self.name.grid(row=1, column=1, sticky="ew", pady=8)
        form.columnconfigure(1, weight=1)

        ttk.Button(form, text="Test Connection", command=self.test).grid(row=2, column=1, sticky="w", pady=15)
        ttk.Label(self, text="Local example: mongodb://127.0.0.1:27018\nAtlas example: mongodb+srv://username:password@cluster.mongodb.net/", foreground="#555").pack(anchor="w", pady=10)

    def test(self):
        try:
            candidate_settings = Settings(mongodb_url=self.url.get().strip(), db_name=self.name.get().strip())
            candidate = MongoDatabase(candidate_settings)
            candidate.connect()
            candidate.ensure_indexes()
            candidate.close()
            messagebox.showinfo("Connection OK", "MongoDB connection succeeded.", parent=self)
        except Exception as exc:
            messagebox.showerror("Connection failed", str(exc), parent=self)
