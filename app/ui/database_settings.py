import os
import tkinter as tk
from tkinter import ttk, messagebox

from app.database.connection import MongoDatabase
from app.config.settings import Settings
from app.logging_setup import log_path
from app.services.backup_service import BackupService


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

        self._build_backup_section()

    # ------------------------------------------------------------------ backups
    def _build_backup_section(self):
        box = ttk.LabelFrame(self, text="Backups", padding=12)
        box.pack(fill="x", anchor="nw", pady=(16, 0))
        self.backup_status = ttk.Label(box, text="")
        self.backup_status.pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(box)
        row.pack(anchor="w")
        ttk.Button(row, text="Back Up Now", command=self.backup_now).pack(side="left")
        ttk.Button(row, text="Open Backup Folder", command=self.open_backup_folder).pack(side="left", padx=8)
        ttk.Button(row, text="Open Log File", command=lambda: self._open(log_path())).pack(side="left")
        ttk.Label(box, foreground="#555", text="A backup is taken automatically once a day while BillDesk is used. "
                  "To restore, use: python scripts/restore_backup.py <backup.zip> --target-db <new name>").pack(anchor="w", pady=(8, 0))
        self.refresh_backup_status()

    def refresh_backup_status(self):
        try:
            last = BackupService(self.db).last_backup()
            text = (f"Last backup: {last['created']:%d/%m/%Y %H:%M}  ({last['size'] / 1_000_000:.1f} MB)" if last
                    else "No backup has been taken yet.")
        except Exception as exc:
            text = f"Could not read the backup folder: {exc}"
        self.backup_status.config(text=text)

    def backup_now(self):
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            path = BackupService(self.db).create_backup("manual")
            messagebox.showinfo("Backup complete", f"Backup saved and verified:\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Backup failed", str(exc), parent=self)
        finally:
            self.config(cursor="")
            self.refresh_backup_status()

    def open_backup_folder(self):
        d = BackupService(self.db).dir
        d.mkdir(parents=True, exist_ok=True)
        self._open(d)

    @staticmethod
    def _open(path):
        try:
            os.startfile(str(path))                      # Windows
        except (AttributeError, OSError):
            pass

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
