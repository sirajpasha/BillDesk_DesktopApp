"""Indian Currency Formatter and Amount in Words converter.
Formats currency using the Indian grouping convention (e.g. ₹ 12,34,567.89)
and converts numerical amounts into words (Crores, Lakhs, Thousands, Rupees, Paise).
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP

ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen"
]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

def _two_digits(n: int) -> str:
    if n < 20:
        return ONES[n]
    tens_val = TENS[n // 10]
    ones_val = ONES[n % 10]
    return f"{tens_val} {ones_val}".strip()

def _three_digits(n: int) -> str:
    hundred = n // 100
    rem = n % 100
    res = ""
    if hundred > 0:
        res = f"{ONES[hundred]} Hundred"
    if rem > 0:
        two = _two_digits(rem)
        res = f"{res} {two}".strip() if res else two
    return res

def money(value: float | int | str | None) -> float:
    """Round a monetary value to 2 decimals, half-up (416.625 -> 416.63), avoiding binary-float surprises."""
    if value is None:
        return 0.0
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_inr(amount: float | int | None, symbol: bool = True) -> str:
    """Format a number into Indian currency notation: 12,34,567.89"""
    if amount is None:
        amount = 0.0
    val = float(amount)
    is_neg = val < 0
    val = abs(val)

    parts = f"{val:.2f}".split(".")
    integer_part = parts[0]
    decimal_part = parts[1]

    if len(integer_part) <= 3:
        formatted_int = integer_part
    else:
        last3 = integer_part[-3:]
        remaining = integer_part[:-3]
        groups = []
        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.insert(0, remaining)
        groups.append(last3)
        formatted_int = ",".join(groups)

    sign = "-" if is_neg else ""
    sym = "₹ " if symbol else ""
    return f"{sign}{sym}{formatted_int}.{decimal_part}"

def _int_words(n: int) -> str:
    """Indian-system words for a non-negative integer (any size: '... Crore' recurses)."""
    if n == 0:
        return ""
    parts = []
    crore, rem = divmod(n, 10000000)
    lakh, rem = divmod(rem, 100000)
    thousand, rem = divmod(rem, 1000)
    if crore:
        parts.append(f"{_int_words(crore)} Crore")
    if lakh:
        parts.append(f"{_two_digits(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two_digits(thousand)} Thousand")
    if rem:
        parts.append(_three_digits(rem))
    return " ".join(parts)


def amount_in_words(amount: float | int | None) -> str:
    """Convert a numeric amount into words using the Indian numbering system."""
    if amount is None:
        return "Zero Rupees Only"
    # Work in whole paise so amounts like 99.999 or 0.995 roll over correctly (-> 100 rupees).
    total_paise = int(round(abs(float(amount)) * 100))
    if total_paise == 0:
        return "Zero Rupees Only"
    is_neg = float(amount) < 0

    integer_part, paise_part = divmod(total_paise, 100)
    rupees_words = _int_words(integer_part)
    res = ""
    if rupees_words:
        res = f"{rupees_words} {'Rupee' if integer_part == 1 else 'Rupees'}"

    if paise_part > 0:
        paise_str = f"{_two_digits(paise_part)} Paise"
        res = f"{res} and {paise_str}" if res else paise_str

    res = f"{res} Only"
    return f"Minus {res}" if is_neg else res


def format_balance(amount: float | int | None) -> str:
    """Customer balance for people: what they owe as 'Dr', what we hold for them (advance) as 'Cr'."""
    val = round(float(amount or 0.0), 2)
    if val < 0:
        return f"{format_inr(-val)} Cr"
    return f"{format_inr(val)} Dr" if val else format_inr(0.0)
