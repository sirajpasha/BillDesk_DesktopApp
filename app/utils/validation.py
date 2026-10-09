"""Checks for what people type into forms. Every function returns the cleaned value or raises ValueError with a sentence that can be
shown to the user as it is (names the field, says what is wrong). Services call these, so a form cannot slip bad data past them."""
from __future__ import annotations

import math
import re
from typing import Any, Optional

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
GSTIN_RE = re.compile(r"^[0-9A-Z]{15}$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,29}$")
PHONE_CHARS_RE = re.compile(r"^[0-9+()\-\s,/]+$")


def text(value: Any, label: str, *, required: bool = True, max_len: int = 100) -> str:
    s = "" if value is None else str(value).strip()
    s = re.sub(r"\s+", " ", s)
    if not s:
        if required:
            raise ValueError(f"{label} is required.")
        return ""
    if len(s) > max_len:
        raise ValueError(f"{label} is too long (at most {max_len} characters).")
    return s


def number(value: Any, label: str, *, minimum: Optional[float] = None, maximum: Optional[float] = None, required: bool = True,
           greater_than: Optional[float] = None, default: Optional[float] = None) -> Optional[float]:
    """A real number: not blank, not NaN or infinity, inside the limits. `greater_than=0` means strictly positive."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"{label} is required.")
        return default
    try:
        n = float(str(value).replace(",", "").strip()) if not isinstance(value, (int, float)) else float(value)
    except ValueError:
        raise ValueError(f"{label} must be a number.") from None
    if math.isnan(n) or math.isinf(n):
        raise ValueError(f"{label} must be a number.")
    if greater_than is not None and n <= greater_than:
        raise ValueError(f"{label} must be greater than {greater_than:g}.")
    if minimum is not None and n < minimum:
        raise ValueError(f"{label} cannot be negative." if minimum == 0 else f"{label} cannot be less than {minimum:g}.")
    if maximum is not None and n > maximum:
        raise ValueError(f"{label} cannot be more than {maximum:,g}.")
    return n


def phone(value: Any, label: str = "Phone") -> str:
    """Optional. One to three numbers separated by comma or slash, each 7-15 digits (a leading + or std code is fine)."""
    s = "" if value is None else str(value).strip()
    if not s:
        return ""
    if not PHONE_CHARS_RE.match(s):
        raise ValueError(f"{label} may only contain digits, spaces and + ( ) - , /")
    parts = [p for p in re.split(r"[,/]", s) if p.strip()]
    if not parts or len(parts) > 3:
        raise ValueError(f"{label} is not valid (give up to three numbers separated by commas).")
    for p in parts:
        digits = re.sub(r"\D", "", p)
        if not 7 <= len(digits) <= 15:
            raise ValueError(f"{label} '{p.strip()}' is not valid: a phone number has 7 to 15 digits.")
    return s


def email(value: Any, label: str = "Email") -> str:
    s = "" if value is None else str(value).strip()
    if s and not EMAIL_RE.match(s):
        raise ValueError(f"{label} is not valid (example: name@shop.com).")
    return s


def gstin(value: Any, label: str = "GSTIN") -> str:
    """Optional (GST does not apply to fresh produce), but 15 letters/digits when given."""
    s = "" if value is None else str(value).strip().upper()
    if s and not GSTIN_RE.match(s):
        raise ValueError(f"{label} must be 15 letters/digits (leave it blank if not applicable).")
    return s


def username(value: Any) -> str:
    s = "" if value is None else str(value).strip()
    if not s:
        raise ValueError("Username is required.")
    if not USERNAME_RE.match(s):
        raise ValueError("Username must be 3 to 30 characters: letters, digits, dot, dash or underscore, starting with a letter or digit.")
    return s


def ifsc(value: Any) -> str:
    s = "" if value is None else str(value).strip().upper()
    if s and not IFSC_RE.match(s):
        raise ValueError("IFSC must be 11 characters: 4 letters, a 0, then 6 letters/digits (example: SBIN0001234).")
    return s


def account_number(value: Any) -> str:
    s = "" if value is None else re.sub(r"\s+", "", str(value))
    if not s:
        raise ValueError("Account number is required.")
    if not s.isdigit() or not 6 <= len(s) <= 20:
        raise ValueError("Account number must be 6 to 20 digits.")
    return s


def choice(value: Any, label: str, options, *, case_insensitive: bool = True) -> str:
    s = "" if value is None else str(value).strip()
    for o in options:
        if (o.lower() == s.lower()) if case_insensitive else (o == s):
            return o
    raise ValueError(f"{label} must be one of: {', '.join(options)}.")
