"""Guards against the tech debt that was cleaned up coming back."""
import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "app" / "ui"


def test_the_code_is_clean_under_ruff():
    """Unused imports / variables, undefined names (each was once a real crash) and syntax newer than Python 3.11."""
    try:
        import ruff  # noqa: F401
        cmd = [sys.executable, "-m", "ruff", "check", "."]
    except ImportError:
        exe = shutil.which("ruff")
        if not exe:
            pytest.skip("ruff is not installed (pip install -r requirements-dev.txt)")
        cmd = [exe, "check", "."]
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr


def test_screens_use_the_theme_not_their_own_colour_and_font_literals():
    """The shared palette / type scale lives in app/ui/theme.py; a repeat of one of its colours or fonts belongs there."""
    palette = {"#ffffff", "#f8fafc", "#64748b", "#4f46e5", "#0f172a", "#475569", "#1e293b", "#e2e8f0", "#f1f5f9", "#334155",
               "#94a3b8", "#059669", "#d97706", "#cbd5e1", "#dc2626", "#4338ca"}
    fonts = re.compile(r'\(\s*"Segoe UI"\s*,\s*(?:8|9|10|11|12)(?:\s*,\s*"bold")?\s*\)')
    offenders = []
    for path in sorted(UI.rglob("*.py")):
        if path.name == "theme.py":
            continue
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r'"(#[0-9a-fA-F]{6})"', src):
            if m.group(1).lower() in palette:
                offenders.append(f"{path.name}: {m.group(1)}")
        offenders += [f"{path.name}: {m.group(0)}" for m in fonts.finditer(src)]
    assert not offenders, f"use app.ui.theme instead ({len(offenders)} places), e.g. {offenders[:5]}"


def test_only_the_main_window_binds_keys_for_the_whole_application():
    """bind_all in a screen fires on every screen; function keys are routed by MainWindow."""
    offenders = []
    for path in sorted(UI.rglob("*.py")):
        if path.name == "main_window.py":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "bind_all(" in line and "<F" in line and not line.strip().startswith(("#", '"""')):
                offenders.append(f"{path.name}: {line.strip()}")
    assert not offenders, offenders


def test_the_two_line_grids_share_one_implementation_of_the_common_behaviour():
    from app.ui.billing import BillingFrame
    from app.ui.components.line_grid import LineGridMixin
    from app.ui.order_form_view import OrderFormView
    shared = ("_add_row", "_on_mousewheel", "_scroll_to_row", "_is_row_empty", "focus_first_empty_row")
    for cls, file in ((BillingFrame, "billing.py"), (OrderFormView, "order_form_view.py")):
        assert issubclass(cls, LineGridMixin)
        defined_here = {f.name for n in ast.parse((UI / file).read_text(encoding="utf-8")).body if isinstance(n, ast.ClassDef) and n.name == cls.__name__
                        for f in n.body if isinstance(f, ast.FunctionDef)}
        assert not defined_here & set(shared), f"{file} redefines {defined_here & set(shared)}"
        assert all(getattr(cls, name) is getattr(LineGridMixin, name) for name in shared)


def test_the_repository_declares_its_line_endings_and_lint_settings():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "* text=auto" in attrs and "*.py text eol=lf" in attrs
    assert "select" in (ROOT / "ruff.toml").read_text(encoding="utf-8")
