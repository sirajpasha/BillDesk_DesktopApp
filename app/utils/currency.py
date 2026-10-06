"""Indian Currency Formatter and Amount in Words converter.
Formats currency using the Indian grouping convention (e.g. ₹ 12,34,567.89)
and converts numerical amounts into words (Crores, Lakhs, Thousands, Rupees, Paise).
"""
from __future__ import annotations

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

def amount_in_words(amount: float | int | None) -> str:
    """Convert a numeric amount into words using the Indian numbering system."""
    if amount is None or amount == 0:
        return "Zero Rupees Only"
    val = float(amount)
    is_neg = val < 0
    val = abs(val)

    integer_part = int(val)
    paise_part = round((val - integer_part) * 100)

    crore = integer_part // 10000000
    rem = integer_part % 10000000

    lakh = rem // 100000
    rem = rem % 100000

    thousand = rem // 1000
    rem = rem % 1000

    words = []
    if crore > 0:
        words.append(f"{_two_digits(crore)} Crore")
    if lakh > 0:
        words.append(f"{_two_digits(lakh)} Lakh")
    if thousand > 0:
        words.append(f"{_two_digits(thousand)} Thousand")
    if rem > 0:
        words.append(_three_digits(rem))

    rupees_str = " ".join(words).strip()
    res = f"{rupees_str} Rupees" if rupees_str else ""

    if paise_part > 0:
        paise_str = f"{_two_digits(paise_part)} Paise"
        if res:
            res = f"{res} and {paise_str}"
        else:
            res = paise_str

    res = f"{res} Only"
    return f"Minus {res}" if is_neg else res
