"""Application logging: rotating file in %APPDATA%\\BillDesk\\logs plus a friendly dialog for unexpected errors.

A packaged (windowed) build has no console, so without this every error would vanish.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE_NAME = "billdesk.log"
_configured = False


def log_dir() -> Path:
    override = os.getenv("BILLDESK_LOG_DIR")
    if override:
        return Path(override)
    from app import paths
    return paths.user_data_dir() / "logs"


def log_path() -> Path:
    return log_dir() / LOG_FILE_NAME


def setup_logging(level: int = logging.INFO, console: bool | None = None) -> logging.Logger:
    """Configure the root logger once (idempotent) and route uncaught exceptions to it."""
    global _configured
    root = logging.getLogger()
    if _configured:
        return root
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        d = log_dir()
        d.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(d / LOG_FILE_NAME, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass                                   # logging must never stop the application from starting
    if console is None:
        console = sys.stderr is not None and getattr(sys.stderr, "isatty", lambda: False)()
    if console:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

    def _excepthook(exc_type, exc, tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            logging.getLogger("uncaught").critical("Uncaught exception", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _excepthook
    threading.excepthook = lambda a: logging.getLogger("thread").critical(
        "Uncaught exception in thread %s", getattr(a.thread, "name", "?"), exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    logging.captureWarnings(True)
    _configured = True
    logging.getLogger(__name__).info("Logging started (%s)", log_path())
    return root


def install_tk_exception_handler(root, min_seconds_between_dialogs: float = 5.0) -> None:
    """Errors inside Tk callbacks are otherwise printed to a console nobody sees. Log them and tell the user once."""
    from tkinter import messagebox
    state = {"last": 0.0}

    def handler(exc_type, exc, tb):
        logging.getLogger("tk").error("Unhandled error in UI callback", exc_info=(exc_type, exc, tb))
        now = time.monotonic()
        if now - state["last"] >= min_seconds_between_dialogs:
            state["last"] = now
            try:
                messagebox.showerror(
                    "Something went wrong",
                    f"An unexpected error occurred:\n\n{exc_type.__name__}: {exc}\n\n"
                    f"Your data was not changed by this message. Details were saved to:\n{log_path()}",
                )
            except Exception:                       # the dialog itself must not raise
                traceback.print_exc()

    root.report_callback_exception = handler
