"""Value normalization utilities for Kara grid payloads."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_EMPTY_MARKERS = {"", "---", "-", "null", "none", "n/a", "—"}


def normalize_digits(value: str) -> str:
    return value.translate(_PERSIAN_DIGITS).translate(_ARABIC_DIGITS)


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and normalize_digits(value.strip()).lower() in _EMPTY_MARKERS:
        return True
    return False


def parse_decimal(value: Any) -> Decimal | None:
    """Parse Persian/English formatted amounts to Decimal (never float)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if not isinstance(value, str):
        return None

    text = normalize_digits(value.strip())
    if not text or text.lower() in _EMPTY_MARKERS:
        return None

    # Accounting format: (1,234) means negative
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]

    # Percentages like "12.5%" → 12.5
    text = text.replace("%", "").replace(",", "").replace("٬", "").replace(" ", "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def parse_number(value: Any) -> float | None:
    """Backward-compatible float parser for UI sorting."""
    dec = parse_decimal(value)
    return float(dec) if dec is not None else None


def parse_int(value: Any) -> int | None:
    dec = parse_decimal(value)
    if dec is None:
        return None
    try:
        return int(dec)
    except (ValueError, OverflowError):
        return None


def parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if not isinstance(value, str):
        return None
    text = normalize_digits(value.strip()).lower()
    if text in _EMPTY_MARKERS:
        return None
    if text in {"بله", "true", "1", "yes", "y"}:
        return True
    if text in {"خیر", "false", "0", "no", "n"}:
        return False
    return None


def format_number(value: Any, decimal_places: int = 0) -> str:
    num = parse_decimal(value)
    if num is None:
        return "—" if is_empty(value) else str(value)
    if decimal_places == 0:
        return f"{num:,.0f}"
    return f"{num:,.{decimal_places}f}"


def format_money(value: Any, unit_label: str | None = None) -> str:
    """Format monetary Rial value using configured display unit (default Toman)."""
    from reports.services.currency import currency_label, format_money_number

    formatted = format_money_number(value)
    if formatted == "—":
        return formatted
    label = unit_label if unit_label is not None else currency_label()
    return f"{formatted} {label}"
