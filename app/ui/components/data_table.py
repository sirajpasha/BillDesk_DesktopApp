import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Tuple, Any, Dict
from app.ui import theme

class DataTable(ttk.Frame):
    """Reusable Treeview data table with sorting, search filter, and double-click callbacks."""
    def __init__(
        self,
        parent,
        columns: List[Tuple[str, str, int]],  # [(col_id, heading_text, width_px)]
        on_select: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_double_click: Optional[Callable[[Dict[str, Any]], None]] = None,
        show_search: bool = True,
        empty_text: str = "",
        **kwargs
    ):
        super().__init__(parent, **kwargs)
        self.columns = columns
        self.on_select = on_select
        self.on_double_click = on_double_click
        self.raw_data: List[Dict[str, Any]] = []
        self.sort_descending = False
        self.empty_text = empty_text
        self._shown: List[Dict[str, Any]] = []         # the rows on screen (after the filter), in order

        if show_search:
            search_bar = ttk.Frame(self)
            search_bar.pack(fill="x", padx=2, pady=(0, 6))
            ttk.Label(search_bar, text="Filter:").pack(side="left", padx=(0, 6))
            self.search_var = tk.StringVar()
            self.search_var.trace_add("write", self._on_filter)
            self.search_entry = ttk.Entry(search_bar, textvariable=self.search_var, width=28)
            self.search_entry.pack(side="left")
            self.count_label = ttk.Label(search_bar, text="", foreground="#666666")
            self.count_label.pack(side="right")

        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True)

        col_ids = [c[0] for c in columns]
        self.tree = ttk.Treeview(table_frame, columns=col_ids, show="headings", selectmode="browse")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        for col_id, heading, width in columns:
            self.tree.heading(col_id, text=heading, command=lambda c=col_id: self._sort_column(c))
            self.tree.column(col_id, width=width, anchor="w")

        # Striped tag colors
        self.tree.tag_configure("odd", background=theme.SURFACE)
        self.tree.tag_configure("even", background="#f9fafb")

        self.empty_lbl = tk.Label(self.tree, text=self.empty_text, font=theme.F_TEXT10, fg=theme.TEXT_MUTED, bg=theme.SURFACE,
                                  justify="center", wraplength=420)
        self.tree.bind("<<TreeviewSelect>>", self._handle_select)
        if self.on_double_click:
            self.tree.bind("<Double-1>", self._handle_double_click)

    def set_data(self, data: List[Dict[str, Any]]):
        self.raw_data = data
        self._render(data)

    def _render(self, rows: List[Dict[str, Any]]):
        self.tree.delete(*self.tree.get_children())
        self._shown = list(rows)
        if self.empty_text and not rows:
            self.empty_lbl.config(text=self.empty_text if not self.raw_data else "Nothing matches the filter.")
            self.empty_lbl.place(relx=0.5, rely=0.4, anchor="center")
        else:
            self.empty_lbl.place_forget()
        for idx, item in enumerate(rows):
            vals = [item.get(c[0], "") for c in self.columns]
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree.insert("", "end", iid=str(idx), values=vals, tags=(tag,))
        if hasattr(self, "count_label"):
            self.count_label.config(text=f"{len(rows)} records")

    def _on_filter(self, *args):
        query = self.search_var.get().lower().strip()
        if not query:
            self._render(self.raw_data)
            return
        filtered = []
        for d in self.raw_data:
            match = any(query in str(v).lower() for v in d.values() if v is not None)
            if match:
                filtered.append(d)
        self._render(filtered)

    def _sort_column(self, col_id: str):
        self.sort_descending = not self.sort_descending
        try:
            self.raw_data.sort(
                key=lambda x: float(x.get(col_id, 0)) if str(x.get(col_id, "")).replace(".", "", 1).isdigit() else str(x.get(col_id, "")).lower(),
                reverse=self.sort_descending
            )
        except Exception:
            self.raw_data.sort(key=lambda x: str(x.get(col_id, "")).lower(), reverse=self.sort_descending)
        self._on_filter()

    def get_selected(self) -> Optional[Dict[str, Any]]:
        sel = self.tree.selection()
        if sel:
            idx = int(sel[0])
            return self._shown[idx] if idx < len(self._shown) else None
        return None

    def _handle_select(self, event):
        if self.on_select:
            item = self.get_selected()
            if item:
                self.on_select(item)

    def _handle_double_click(self, event):
        if self.on_double_click:
            item = self.get_selected()
            if item:
                self.on_double_click(item)
