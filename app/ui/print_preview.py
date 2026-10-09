from __future__ import annotations
import os
from app import paths
import shutil
import subprocess
import platform
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from app.ui import theme

try:
    import pymupdf
    HAS_PYMUPDF = True
except ImportError:
    try:
        import fitz as pymupdf
        HAS_PYMUPDF = True
    except ImportError:
        HAS_PYMUPDF = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class PrintPreviewDialog(tk.Toplevel):
    """
    Native Desktop Print Preview Modal Dialog.
    Renders PDF pages directly with high DPI rasterization,
    multi-page navigation, zoom in/out, fit width, direct printer dispatch,
    and save/download options.
    """
    def __init__(
        self,
        parent,
        pdf_path: str,
        title: str = "Print Preview",
        default_filename: str = "Document.pdf"
    ):
        super().__init__(parent)
        self.pdf_path = os.path.abspath(pdf_path)
        self.doc_title = title
        self.default_filename = default_filename or os.path.basename(pdf_path)
        self.title(f"BillDesk — {self.doc_title}")

        # Window sizing and centering
        self.geometry("1020x860")
        self.minsize(720, 520)
        self.configure(bg=theme.BG)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w, h = 1020, 860
        x = max(20, px + (pw - w) // 2)
        y = max(20, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        # PDF document state
        self.doc = None
        self.page_count = 0
        self.current_page_idx = 0
        self.zoom_level = 1.0  # 1.0 = 100%
        self._current_photo = None

        self._load_document()
        self._build_ui()
        self._bind_shortcuts()
        self._render_page()

    def _load_document(self):
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

        if HAS_PYMUPDF:
            try:
                self.doc = pymupdf.open(self.pdf_path)
                self.page_count = len(self.doc)
            except Exception:
                self.doc = None
                self.page_count = 1

    def _build_ui(self):
        # 1. Top Indigo Accent Strip
        tk.Frame(self, bg=theme.PRIMARY, height=3).pack(fill="x")

        # 2. Control Toolbar
        toolbar = tk.Frame(self, bg=theme.SURFACE, bd=1, relief="solid", padx=16, pady=8)
        toolbar.pack(fill="x")

        # Left Section: Document title and badge
        left_box = tk.Frame(toolbar, bg=theme.SURFACE)
        left_box.pack(side="left")

        tk.Label(
            left_box,
            text=f"📄 {self.doc_title}",
            font=theme.F_H11B,
            fg=theme.TEXT,
            bg=theme.SURFACE
        ).pack(side="left", padx=(0, 10))

        pages_label = f"{self.page_count} Pages" if self.page_count > 1 else "1 Page"
        tk.Label(
            left_box,
            text=pages_label,
            font=theme.F_LABEL,
            fg=theme.PRIMARY,
            bg="#e0e7ff",
            padx=8,
            pady=2
        ).pack(side="left")

        # Right Section: Action Buttons
        right_box = tk.Frame(toolbar, bg=theme.SURFACE)
        right_box.pack(side="right")

        self.print_btn = tk.Button(
            right_box,
            text="🖨️ Print",
            font=theme.F_BOLD,
            bg=theme.PRIMARY,
            fg=theme.SURFACE,
            activebackground=theme.PRIMARY_DARK,
            activeforeground=theme.SURFACE,
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._on_print
        )
        self.print_btn.pack(side="left", padx=(0, 6))

        self.save_btn = tk.Button(
            right_box,
            text="💾 Save PDF",
            font=theme.F_BOLD,
            bg=theme.SURFACE,
            fg=theme.SLATE_700,
            activebackground=theme.HEADING_BG,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._on_save
        )
        self.save_btn.pack(side="left", padx=(0, 8))

        tk.Button(
            right_box,
            text="✕ Close",
            font=theme.F_BODY,
            bg=theme.HEADING_BG,
            fg=theme.SLATE_600,
            relief="solid",
            bd=1,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.destroy
        ).pack(side="left")

        # Center Section: Navigation & Zoom controls
        center_box = tk.Frame(toolbar, bg=theme.SURFACE)
        center_box.pack(side="right", padx=(0, 24))

        # Page navigation (if multi-page)
        if self.page_count > 1:
            nav_box = tk.Frame(center_box, bg=theme.BG, bd=1, relief="solid", padx=6, pady=2)
            nav_box.pack(side="left", padx=(0, 16))

            self.prev_btn = tk.Button(
                nav_box,
                text="◀",
                font=theme.F_LABEL,
                bg=theme.BG,
                fg=theme.SLATE_700,
                relief="flat",
                bd=0,
                padx=6,
                cursor="hand2",
                command=self._prev_page
            )
            self.prev_btn.pack(side="left")

            self.page_lbl = tk.Label(
                nav_box,
                text=f"Page 1 of {self.page_count}",
                font=theme.F_BOLD,
                fg=theme.TEXT_STRONG,
                bg=theme.BG,
                padx=8
            )
            self.page_lbl.pack(side="left")

            self.next_btn = tk.Button(
                nav_box,
                text="▶",
                font=theme.F_LABEL,
                bg=theme.BG,
                fg=theme.SLATE_700,
                relief="flat",
                bd=0,
                padx=6,
                cursor="hand2",
                command=self._next_page
            )
            self.next_btn.pack(side="left")

        # Zoom controls
        zoom_box = tk.Frame(center_box, bg=theme.BG, bd=1, relief="solid", padx=6, pady=2)
        zoom_box.pack(side="left")

        tk.Button(
            zoom_box,
            text="➖",
            font=theme.F_SMALL,
            bg=theme.BG,
            fg=theme.SLATE_600,
            relief="flat",
            bd=0,
            padx=4,
            cursor="hand2",
            command=self._zoom_out
        ).pack(side="left")

        self.zoom_lbl = tk.Label(
            zoom_box,
            text="100%",
            font=theme.F_LABEL,
            fg=theme.SLATE_600,
            bg=theme.BG,
            width=5
        )
        self.zoom_lbl.pack(side="left")

        tk.Button(
            zoom_box,
            text="➕",
            font=theme.F_SMALL,
            bg=theme.BG,
            fg=theme.SLATE_600,
            relief="flat",
            bd=0,
            padx=4,
            cursor="hand2",
            command=self._zoom_in
        ).pack(side="left")

        tk.Button(
            zoom_box,
            text="Fit",
            font=theme.F_LABEL,
            bg="#e0e7ff",
            fg=theme.PRIMARY,
            relief="flat",
            bd=0,
            padx=6,
            cursor="hand2",
            command=self._zoom_fit
        ).pack(side="left", padx=(4, 0))

        # 3. Canvas Viewing Container
        view_container = tk.Frame(self, bg=theme.BORDER)
        view_container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(view_container, bg=theme.BORDER, highlightthickness=0)
        self.vsb = ttk.Scrollbar(view_container, orient="vertical", command=self.canvas.yview)
        self.hsb = ttk.Scrollbar(view_container, orient="horizontal", command=self.canvas.xview)

        self.canvas.configure(xscrollcommand=self.hsb.set, yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.hsb.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        # Mouse Wheel bindings
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)

    def _bind_shortcuts(self):
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Left>", lambda _e: self._prev_page())
        self.bind("<Right>", lambda _e: self._next_page())
        self.bind("<Prior>", lambda _e: self._prev_page())  # Page Up
        self.bind("<Next>", lambda _e: self._next_page())   # Page Down
        self.bind("<Control-p>", lambda _e: self._on_print())
        self.bind("<Control-s>", lambda _e: self._on_save())
        self.bind("<plus>", lambda _e: self._zoom_in())
        self.bind("<equal>", lambda _e: self._zoom_in())
        self.bind("<minus>", lambda _e: self._zoom_out())

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_shift_mousewheel(self, event):
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_ctrl_mousewheel(self, event):
        if event.delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    def _render_page(self):
        self.canvas.delete("all")

        if not HAS_PYMUPDF or not HAS_PIL or not self.doc:
            # Fallback placeholder when rasterizer is not available
            cx = self.winfo_width() // 2 or 450
            self.canvas.create_text(
                cx, 250,
                text="Document Preview Ready\n\nClick 'Print' to print directly,\nor 'Save PDF' to export.",
                font=("Segoe UI", 13, "bold"),
                fill=theme.SLATE_600,
                justify="center"
            )
            return

        try:
            page = self.doc[self.current_page_idx]

            # Calculate DPI based on zoom level (base DPI 120 gives crisp A4 text)
            effective_dpi = int(120 * self.zoom_level)
            pix = page.get_pixmap(dpi=effective_dpi)

            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            self._current_photo = ImageTk.PhotoImage(img)

            # Viewport dimensions
            canvas_w = max(self.canvas.winfo_width(), pix.width + 80)
            canvas_h = max(self.canvas.winfo_height(), pix.height + 60)

            # Center page horizontally
            x_pos = max(40, (canvas_w - pix.width) // 2)
            y_pos = 30

            # Subtle drop shadow behind page
            self.canvas.create_rectangle(
                x_pos + 4, y_pos + 4,
                x_pos + pix.width + 4, y_pos + pix.height + 4,
                fill=theme.BORDER_DARK, outline=""
            )

            # Draw white page border outline
            self.canvas.create_rectangle(
                x_pos - 1, y_pos - 1,
                x_pos + pix.width + 1, y_pos + pix.height + 1,
                fill=theme.SURFACE, outline=theme.TEXT_FAINT
            )

            # Draw page image
            self.canvas.create_image(x_pos, y_pos, image=self._current_photo, anchor="nw")

            # Configure scrollable region
            scroll_w = max(canvas_w, x_pos + pix.width + 40)
            scroll_h = max(canvas_h, y_pos + pix.height + 40)
            self.canvas.configure(scrollregion=(0, 0, scroll_w, scroll_h))

            # Update toolbar labels & buttons
            self.zoom_lbl.config(text=f"{int(self.zoom_level * 100)}%")
            if hasattr(self, "page_lbl"):
                self.page_lbl.config(text=f"Page {self.current_page_idx + 1} of {self.page_count}")
                self.prev_btn.config(state="normal" if self.current_page_idx > 0 else "disabled")
                self.next_btn.config(state="normal" if self.current_page_idx < self.page_count - 1 else "disabled")

        except Exception as ex:
            self.canvas.create_text(
                300, 200,
                text=f"Failed to render preview:\n{ex}",
                font=theme.F_TEXT11,
                fill=theme.DANGER
            )

    def _prev_page(self):
        if self.current_page_idx > 0:
            self.current_page_idx -= 1
            self._render_page()

    def _next_page(self):
        if self.current_page_idx < self.page_count - 1:
            self.current_page_idx += 1
            self._render_page()

    def _zoom_in(self):
        if self.zoom_level < 2.5:
            self.zoom_level = round(self.zoom_level + 0.15, 2)
            self._render_page()

    def _zoom_out(self):
        if self.zoom_level > 0.4:
            self.zoom_level = round(self.zoom_level - 0.15, 2)
            self._render_page()

    def _zoom_fit(self):
        self.zoom_level = 1.0
        self._render_page()

    def _on_print(self):
        """Send PDF to Windows default printer or open print dialog."""
        if not os.path.exists(self.pdf_path):
            messagebox.showerror("Error", "PDF file not found.", parent=self)
            return

        try:
            if platform.system() == "Windows":
                # Try printing via Windows shell print verb
                try:
                    os.startfile(self.pdf_path, "print")
                    messagebox.showinfo("Printing", f"Sent document to default printer:\n{self.default_filename}", parent=self)
                    return
                except Exception:
                    # Fallback to opening system viewer
                    os.startfile(self.pdf_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["lpr", self.pdf_path])
                messagebox.showinfo("Printing", f"Sent to printer via lpr:\n{self.default_filename}", parent=self)
            else:
                subprocess.Popen(["lpr", self.pdf_path])
                messagebox.showinfo("Printing", f"Sent to printer via lpr:\n{self.default_filename}", parent=self)
        except Exception as ex:
            messagebox.showerror("Print Failed", f"Could not print automatically:\n{ex}", parent=self)

    def _on_save(self):
        """Export PDF to a user-chosen path."""
        out_dir = str(paths.output_dir())
        os.makedirs(out_dir, exist_ok=True)

        dest_path = filedialog.asksaveasfilename(
            parent=self,
            title="Save PDF Document",
            initialdir=out_dir,
            initialfile=self.default_filename,
            defaultextension=".pdf",
            filetypes=[("PDF Documents", "*.pdf"), ("All Files", "*.*")]
        )

        if not dest_path:
            return

        try:
            shutil.copy2(self.pdf_path, dest_path)
            messagebox.showinfo("Saved", f"Document saved successfully:\n{dest_path}", parent=self)
        except Exception as ex:
            messagebox.showerror("Save Error", f"Failed to save PDF:\n{ex}", parent=self)


def show_print_preview(
    parent,
    pdf_path: str,
    title: str = "Print Preview",
    default_filename: str = ""
) -> PrintPreviewDialog:
    """Convenience helper to open the modal Print Preview window."""
    return PrintPreviewDialog(parent, pdf_path, title=title, default_filename=default_filename)
