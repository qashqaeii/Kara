"""Display currency conversion — storage stays Rial; UI may show Toman."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from reports.constants import CurrencyUnit
from reports.services.parsers.values import format_number, is_empty, parse_decimal

CURRENCY_UNIT_LABELS = {
    CurrencyUnit.RIAL: "ریال",
    CurrencyUnit.TOMAN: "تومان",
}

# KPI keys whose values are monetary (Rial in storage).
MONEY_KPI_KEYS = frozenset(
    {
        "total_sale",
        "total_pure_sale",
        "settlement_remainder",
        "distribution_reversion",
        "sale_reversion",
        "avg_order_value",
        "gross_profit",
        "finalized_cost",
        "invoice_revenue",
        "net_profit",
        "pnl_net_pure_sale",
        "pnl_cogs",
        "pnl_gross_profit",
        "pnl_operating_profit",
        "pnl_net_profit",
    }
)


def get_currency_unit() -> CurrencyUnit:
    try:
        from django.conf import settings

        raw = str(getattr(settings, "KARA_CURRENCY_UNIT", CurrencyUnit.TOMAN)).strip().lower()
    except Exception:
        raw = CurrencyUnit.TOMAN
    if raw in (CurrencyUnit.RIAL, "rial", "ریال"):
        return CurrencyUnit.RIAL
    return CurrencyUnit.TOMAN


def currency_label() -> str:
    return CURRENCY_UNIT_LABELS[get_currency_unit()]


def to_display_amount(rial_value: Any) -> Decimal | None:
    """Convert a Rial amount to the configured display unit."""
    num = parse_decimal(rial_value)
    if num is None:
        return None
    if get_currency_unit() == CurrencyUnit.TOMAN:
        return (num / Decimal("10")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return num


def format_money_number(value: Any, decimal_places: int = 0) -> str:
    """Format a Rial storage value for UI (Toman or Rial per settings)."""
    display = to_display_amount(value)
    if display is None:
        return "—" if is_empty(value) else str(value)
    return format_number(display, decimal_places=decimal_places)


def format_money(value: Any, *, with_unit: bool = True) -> str:
    formatted = format_money_number(value)
    if formatted == "—" or not with_unit:
        return formatted
    return f"{formatted} {currency_label()}"


def display_float(rial_value: Any) -> float:
    """Numeric display amount for charts/JSON (still converted)."""
    display = to_display_amount(rial_value)
    return float(display) if display is not None else 0.0
