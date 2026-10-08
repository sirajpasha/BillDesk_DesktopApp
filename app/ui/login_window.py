import logging
import tkinter as tk
from tkinter import messagebox
from typing import Optional
from app.config.settings import settings


class LoginWindow(tk.Toplevel):
    """
    Login Window matching 01-login.png:
    - Dark vegetable & warm bokeh ambient background.
    - Centered sleek white card.
    - 'SV' Circular Emblem with botanical motif.
    - Header text with configurable company name.
    - 'Billing System' subtitle.
    - Clean input fields with focused styling.
    - Purple pill 'Login' button (#5b54d6).
    - 'Developed and maintained by InfoDatSystems' footer credit.
    """
    def __init__(self, parent, auth, on_login_success=None):
        super().__init__(parent)
        self.auth = auth
        self.on_login_success = on_login_success
        self.current_user = None

        self.title(f"{settings.default_company_name} — Billing System")
        self.resizable(False, False)

        # Set window icon if available
        import os
        icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "icon.png")
        if os.path.exists(icon_path):
            try:
                self._icon_img = tk.PhotoImage(file=icon_path)
                self.iconphoto(False, self._icon_img)
            except Exception:
                logging.getLogger(__name__).warning("Ignored error", exc_info=True)

        # 960x640 dialog centered on screen
        w, h = 960, 640
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.configure(bg="#0c111d")

        # Bring window to front
        self.lift()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))
        self.focus_force()
        self.grab_set()

        self._build_ui(w, h)

    def _build_ui(self, width: int, height: int):
        # 1. Dark bokeh atmospheric canvas matching 01-login.png
        canvas = tk.Canvas(self, width=width, height=height, bg="#0c111d", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        # Ambient warm bokeh orbs
        canvas.create_oval(-40, 20, 260, 320, fill="#2d1511", outline="", tags="bokeh")
        canvas.create_oval(700, 30, 980, 310, fill="#3b200b", outline="", tags="bokeh")
        canvas.create_oval(600, 320, 920, 640, fill="#12251a", outline="", tags="bokeh")
        canvas.create_oval(40, 420, 300, 680, fill="#2a142e", outline="", tags="bokeh")
        canvas.create_oval(500, -80, 750, 170, fill="#281a0e", outline="", tags="bokeh")
        canvas.create_oval(150, 180, 280, 310, fill="#3d2c12", outline="", tags="bokeh")

        # 2. Centered sleek white card
        card_w, card_h = 420, 520
        cx = width // 2
        cy = height // 2

        card_frame = tk.Frame(canvas, bg="#ffffff", bd=0, padx=36, pady=28)
        card_window = canvas.create_window(cx, cy, window=card_frame, width=card_w, height=card_h)

        # 3. Logo Emblem (SV circular badge matching 01-login.png)
        logo_canvas = tk.Canvas(card_frame, width=72, height=72, bg="#ffffff", highlightthickness=0)
        logo_canvas.pack(pady=(0, 6))

        # Circular wreath ring
        logo_canvas.create_oval(4, 4, 68, 68, outline="#4f46e5", width=2, fill="#f8fafc")
        logo_canvas.create_oval(10, 10, 62, 62, outline="#818cf8", width=1, dash=(3, 2))
        logo_canvas.create_text(36, 32, text="SV", font=("Segoe UI", 16, "bold"), fill="#4338ca")
        logo_canvas.create_text(36, 48, text="VEG & FRUITS", font=("Segoe UI", 5, "bold"), fill="#6366f1")

        # 4. Brand Titles
        tk.Label(
            card_frame,
            text=settings.default_company_name,
            font=("Segoe UI", 17, "bold"),
            fg="#5b54d6",
            bg="#ffffff"
        ).pack(pady=(2, 2))

        tk.Label(
            card_frame,
            text="Billing System",
            font=("Segoe UI", 10),
            fg="#64748b",
            bg="#ffffff"
        ).pack(pady=(0, 22))

        # 5. Inputs (Username & Password with neat border)
        input_container = tk.Frame(card_frame, bg="#ffffff")
        input_container.pack(fill="x", pady=(0, 14))

        tk.Label(
            input_container,
            text="Username",
            font=("Segoe UI", 9, "bold"),
            fg="#475569",
            bg="#ffffff"
        ).pack(anchor="w", pady=(0, 4))

        u_border = tk.Frame(input_container, bg="#cbd5e1", padx=1, pady=1)
        u_border.pack(fill="x", pady=(0, 12))
        self.username_entry = tk.Entry(
            u_border,
            font=("Segoe UI", 11),
            bg="#ffffff",
            fg="#0f172a",
            relief="flat",
            bd=6
        )
        self.username_entry.pack(fill="x")
        self.username = self.username_entry  # Backwards compatibility

        tk.Label(
            input_container,
            text="Password",
            font=("Segoe UI", 9, "bold"),
            fg="#475569",
            bg="#ffffff"
        ).pack(anchor="w", pady=(0, 4))

        p_border = tk.Frame(input_container, bg="#cbd5e1", padx=1, pady=1)
        p_border.pack(fill="x", pady=(0, 18))
        self.password_entry = tk.Entry(
            p_border,
            show="•",
            font=("Segoe UI", 11),
            bg="#ffffff",
            fg="#0f172a",
            relief="flat",
            bd=6
        )
        self.password_entry.pack(fill="x")
        self.password = self.password_entry  # Backwards compatibility

        # 6. Purple Pill Login Button
        self.login_button = tk.Button(
            card_frame,
            text="Login",
            font=("Segoe UI", 11, "bold"),
            bg="#5b54d6",
            fg="#ffffff",
            activebackground="#4a42c4",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self._login
        )
        self.login_button.pack(fill="x", ipady=8, pady=(0, 20))

        # 7. Divider Line
        tk.Frame(card_frame, bg="#e2e8f0", height=1).pack(fill="x", pady=(0, 16))

        # 8. Footer Credit
        footer_box = tk.Frame(card_frame, bg="#ffffff")
        footer_box.pack()
        tk.Label(
            footer_box,
            text="Developed and maintained by ",
            font=("Segoe UI", 8),
            fg="#64748b",
            bg="#ffffff"
        ).pack(side="left")
        tk.Label(
            footer_box,
            text="InfoDatSystems",
            font=("Segoe UI", 8, "bold"),
            fg="#2563eb",
            bg="#ffffff"
        ).pack(side="left")

        # Focus & Enter Binding
        self.bind("<Return>", lambda _e: self._login())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.username_entry.focus_set()

    def _login(self):
        u = self.username_entry.get().strip()
        p = self.password_entry.get()
        if not u or not p:
            messagebox.showwarning("Sign In", "Please enter both username and password.", parent=self)
            return
        try:
            user = self.auth.login(u, p)
            self.current_user = user
            if self.on_login_success:
                self.on_login_success(user)
            self.grab_release()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Sign In Failed", str(exc), parent=self)
            self.password_entry.focus_set()

    def _close(self):
        self.grab_release()
        self.destroy()
