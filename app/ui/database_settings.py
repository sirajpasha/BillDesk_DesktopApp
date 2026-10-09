import os
import tkinter as tk
from tkinter import ttk, messagebox

from app.database.connection import MongoDatabase
from app.config.settings import Settings
from app.logging_setup import log_path
from app.services.backup_service import BackupService
from app.ui import theme


class DatabaseSettingsFrame(ttk.Frame):
    """Backups first (what an owner needs), then where the data lives (rarely touched)."""

    def __init__(self, parent, db, billing=None):
        super().__init__(parent)
        self.db = db
        theme.page_header(self, "Backup & Database", "Keep a safe copy of your data").pack(fill="x", padx=28, pady=(20, 12))
        self._build_backup_section()
        self._build_connection_section()

    # ------------------------------------------------------------------ connection
    def _build_connection_section(self):
        box = theme.card(self)
        box.pack(fill="x", padx=28, pady=(0, 16))
        inner = tk.Frame(box, bg=theme.SURFACE, padx=18, pady=14)
        inner.pack(fill="x")
        tk.Label(inner, text="Where your data is kept", font=theme.F_SECTION, fg=theme.TEXT, bg=theme.SURFACE).pack(anchor="w")
        tk.Label(inner, text="Normally this is the database on this computer. Change it only if you were asked to.",
                 font=theme.F_BODY, fg=theme.TEXT_MUTED, bg=theme.SURFACE).pack(anchor="w", pady=(0, 10))
        form = tk.Frame(inner, bg=theme.SURFACE)
        form.pack(fill="x")
        default_url = getattr(self.db.settings, "mongodb_url", "mongodb://127.0.0.1:27018") if hasattr(self.db, "settings") and self.db.settings else "mongodb://127.0.0.1:27018"
        default_db = getattr(self.db.settings, "db_name", "sv_billing") if hasattr(self.db, "settings") and self.db.settings else "sv_billing"
        tk.Label(form, text="Database address", font=theme.F_BOLD, fg=theme.TEXT_MUTED, bg=theme.SURFACE).grid(row=0, column=0, sticky="w", padx=(0, 12), pady=6)
        self.url = ttk.Entry(form, width=70)
        self.url.insert(0, default_url)
        self.url.grid(row=0, column=1, sticky="ew", pady=6)
        tk.Label(form, text="Database name", font=theme.F_BOLD, fg=theme.TEXT_MUTED, bg=theme.SURFACE).grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.name = ttk.Entry(form, width=50)
        self.name.insert(0, default_db)
        self.name.grid(row=1, column=1, sticky="ew", pady=6)
        form.columnconfigure(1, weight=1)
        theme.secondary_button(form, "Test Connection", self.test).grid(row=2, column=1, sticky="w", pady=(10, 0))
        tk.Label(inner, text="This computer: mongodb://127.0.0.1:27018     Online (Atlas): mongodb+srv://user:password@cluster.mongodb.net/",
                 font=theme.F_SMALL, fg=theme.TEXT_FAINT, bg=theme.SURFACE).pack(anchor="w", pady=(10, 0))

    # ------------------------------------------------------------------ backups
    def _build_backup_section(self):
        box = theme.card(self)
        box.pack(fill="x", padx=28, pady=(0, 16))
        inner = tk.Frame(box, bg=theme.SURFACE, padx=18, pady=14)
        inner.pack(fill="x")
        tk.Label(inner, text="Backups", font=theme.F_SECTION, fg=theme.TEXT, bg=theme.SURFACE).pack(anchor="w")
        self.backup_status = tk.Label(inner, text="", font=(theme.FONT, 11), fg=theme.TEXT, bg=theme.SURFACE)
        self.backup_status.pack(anchor="w", pady=(4, 10))
        row = tk.Frame(inner, bg=theme.SURFACE)
        row.pack(anchor="w")
        theme.primary_button(row, "Back Up Now", self.backup_now).pack(side="left")
        theme.secondary_button(row, "Open Backup Folder", self.open_backup_folder).pack(side="left", padx=8)
        theme.secondary_button(row, "Open Log File", lambda: self._open(log_path())).pack(side="left")
        tk.Label(inner, font=theme.F_BODY, fg=theme.TEXT_MUTED, bg=theme.SURFACE, justify="left",
                 text="A backup is taken automatically once a day while BillDesk is used, and each one is checked after it is written.\n"
                      "To restore: python scripts/restore_backup.py <backup.zip> --target-db <new name>").pack(anchor="w", pady=(10, 0))
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
