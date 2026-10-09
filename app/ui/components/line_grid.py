"""Behaviour shared by the two line-item grids (New Bill and New Customer Order).

The screens keep their own cell widgets (one stores Entry widgets, the other StringVars), so they supply two small hooks:

    _row_code_and_name(row) -> (code_text, name_text)       what is typed in the Code and Item boxes of a row
    _create_row_widget(index) -> dict                         builds one row

Everything that does not depend on how a row stores its text lives here, once."""
from __future__ import annotations

import logging
from typing import Tuple


class LineGridMixin:
    row_widgets: list
    rows_frame: object
    t_canvas: object

    def _row_code_and_name(self, row: dict) -> Tuple[str, str]:        # pragma: no cover - overridden
        raise NotImplementedError

    def _add_row(self) -> int:
        new_idx = len(self.row_widgets)
        row_data = self._create_row_widget(new_idx)
        self.row_widgets.append(row_data)
        self.rows_frame.update_idletasks()
        self.t_canvas.configure(scrollregion=self.t_canvas.bbox("all"))
        return new_idx

    def _on_mousewheel(self, event):
        if hasattr(self, "t_canvas") and event.delta:
            self.t_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _scroll_to_row(self, row_idx: int):
        try:
            if row_idx < 0 or row_idx >= len(self.row_widgets):
                return
            self.rows_frame.update_idletasks()
            total_rows = len(self.row_widgets)
            if total_rows > 0:
                fraction = max(0.0, min(1.0, row_idx / total_rows))
                self.t_canvas.yview_moveto(fraction)
        except Exception:
            logging.getLogger(__name__).warning("Ignored error", exc_info=True)

    def _is_row_empty(self, row_idx: int) -> bool:
        if row_idx < 0 or row_idx >= len(self.row_widgets):
            return True
        row = self.row_widgets[row_idx]
        code, name = self._row_code_and_name(row)
        return not code.strip() and not name.strip() and not row.get("item_id")

    def focus_first_empty_row(self) -> int:
        """The first row with nothing in it (row N+1 when N rows are filled): its Code box gets the cursor."""
        idx = next((i for i in range(len(self.row_widgets)) if self._is_row_empty(i)), None)
        if idx is None:
            idx = self._add_row()
        self._scroll_to_row(idx)
        self.row_widgets[idx]["code"].focus_set()
        return idx
