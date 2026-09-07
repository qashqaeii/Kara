"""Helpers for Kara monthly sale report (MontlyReportGrid)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from reports.constants import JALALI_MONTHS
from reports.services.currency import display_float, format_money_number
from reports.services.parsers import parse_decimal


def extract_monthly_amounts(row: dict[str, Any]) -> dict[str, Decimal]:
    """Parse all 12 Jalali month columns from a grid row or SumRowData."""
    amounts: dict[str, Decimal] = {}
    for key, api_field, _label in JALALI_MONTHS:
        amounts[key] = parse_decimal(row.get(api_field)) or Decimal("0")
    return amounts


def monthly_total(amounts: dict[str, Decimal]) -> Decimal:
    return sum(amounts.values(), Decimal("0"))


def monthly_series_from_amounts(amounts: dict[str, Decimal]) -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": label,
            "value": display_float(amounts.get(key, Decimal("0"))),
            "formatted": format_money_number(amounts.get(key, Decimal("0"))),
        }
        for key, _api, label in JALALI_MONTHS
    ]


def jalali_fiscal_year(value: date | datetime | None = None) -> int:
    """Resolve Jalali fiscal year for monthly_sale snapshots."""
    from django.utils import timezone

    if value is None:
        d = timezone.localdate()
    elif isinstance(value, datetime):
        d = timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    else:
        d = value
    try:
        import jdatetime

        return jdatetime.date.fromgregorian(date=d).year
    except ImportError:
        return d.year
