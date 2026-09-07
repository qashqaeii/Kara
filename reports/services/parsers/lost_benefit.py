"""Parsers for Accounting LostBenefitSeparate + MonthlyStuffGroupDetailedLostBenefit."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from reports.constants import JALALI_MONTHS
from reports.services.currency import display_float, format_money_number
from reports.services.parsers.grid import flatten_rows
from reports.services.parsers.values import parse_decimal


def product_profit_ranking(rows: list[dict], *, limit: int = 10) -> list[dict[str, Any]]:
    """
    Aggregate LostBenefitSeparate rows by StuffCode.

    BenefitLostPrice is Kara's product margin (sale − buy) in Rial.
    """
    products: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("StuffCode") or "").strip()
        if not code:
            continue
        sale = parse_decimal(row.get("SalePrice")) or Decimal("0")
        buy = parse_decimal(row.get("BuyPrice")) or Decimal("0")
        benefit = parse_decimal(row.get("BenefitLostPrice"))
        if benefit is None:
            benefit = sale - buy
        # Skip pure zero rows (often fully reverted distribution lines).
        if sale == 0 and buy == 0 and benefit == 0:
            continue
        bucket = products.get(code)
        if not bucket:
            bucket = {
                "code": code,
                "name": (row.get("StuffName") or "").strip() or code,
                "group": (row.get("StuffGroupName") or "").strip() or "—",
                "subgroup": (row.get("StuffSubGroupName") or "").strip(),
                "sale_amount": Decimal("0"),
                "buy_amount": Decimal("0"),
                "benefit_amount": Decimal("0"),
            }
            products[code] = bucket
        if not bucket["name"] and row.get("StuffName"):
            bucket["name"] = str(row.get("StuffName")).strip()
        if bucket["group"] == "—" and row.get("StuffGroupName"):
            bucket["group"] = str(row.get("StuffGroupName")).strip()
        bucket["sale_amount"] += sale
        bucket["buy_amount"] += buy
        bucket["benefit_amount"] += benefit

    ranked = sorted(
        products.values(),
        key=lambda item: Decimal(item["benefit_amount"]),
        reverse=True,
    )
    result: list[dict[str, Any]] = []
    for item in ranked:
        benefit = Decimal(item["benefit_amount"])
        sale = Decimal(item["sale_amount"])
        buy = Decimal(item["buy_amount"])
        if benefit == 0 and sale == 0:
            continue
        margin = float((benefit / buy * 100) if buy > 0 else Decimal("0"))
        result.append(
            {
                "rank": len(result) + 1,
                "code": item["code"],
                "name": item["name"],
                "group": item["group"],
                "subgroup": item["subgroup"],
                "sale_amount": float(sale),
                "buy_amount": float(buy),
                "benefit_amount": float(benefit),
                "value": display_float(benefit),
                "sale_formatted": format_money_number(sale),
                "buy_formatted": format_money_number(buy),
                "benefit_formatted": format_money_number(benefit),
                "margin_percent": round(margin, 1),
                "margin_formatted": f"{margin:.1f}",
            }
        )
        if len(result) >= limit:
            break
    return result


def group_benefit_ranking(rows: list[dict], *, limit: int = 10) -> list[dict[str, Any]]:
    """Rank monthly-group LostBenefit rows by TotalBenefit (group or subgroup)."""
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        group = (row.get("StuffGroupName") or "").strip()
        if not group:
            continue
        subgroup = (row.get("StuffSubGroupName") or "").strip()
        key = f"{group}||{subgroup}" if subgroup else group
        benefit = parse_decimal(row.get("TotalBenefit")) or Decimal("0")
        bucket = groups.get(key)
        if not bucket:
            bucket = {
                "name": f"{group} / {subgroup}" if subgroup else group,
                "group": group,
                "subgroup": subgroup,
                "benefit_amount": Decimal("0"),
            }
            groups[key] = bucket
        bucket["benefit_amount"] += benefit

    ranked = sorted(
        groups.values(),
        key=lambda item: Decimal(item["benefit_amount"]),
        reverse=True,
    )
    result: list[dict[str, Any]] = []
    for item in ranked:
        benefit = Decimal(item["benefit_amount"])
        if benefit == 0:
            continue
        result.append(
            {
                "rank": len(result) + 1,
                "name": item["name"],
                "group": item["group"],
                "subgroup": item["subgroup"],
                "benefit_amount": float(benefit),
                "value": display_float(benefit),
                "formatted": format_money_number(benefit),
            }
        )
        if len(result) >= limit:
            break
    return result


def monthly_group_benefit_series(rows: list[dict]) -> dict[str, Any]:
    """
    Sum Benefit1..Benefit12 across all groups into a fiscal-year series.

    Kara months align with Jalali: Benefit1=فروردین … Benefit12=اسفند.
    """
    totals = [Decimal("0")] * 12
    for row in rows:
        for i in range(12):
            totals[i] += parse_decimal(row.get(f"Benefit{i + 1}")) or Decimal("0")

    series = []
    for idx, (key, _field, label) in enumerate(JALALI_MONTHS):
        amount = totals[idx]
        series.append(
            {
                "key": key,
                "label": label,
                "month_index": idx + 1,
                "value": display_float(amount),
                "amount": float(amount),
                "formatted": format_money_number(amount),
            }
        )
    total = sum(totals, Decimal("0"))
    return {
        "available": any(v != 0 for v in totals),
        "series": series,
        "total": float(total),
        "total_formatted": format_money_number(total),
        "source": "monthly_stuff_group_lost_benefit",
        "source_label": "سود ماهانه گروه کالا",
    }


def ranking_from_snapshot(snapshot, *, limit: int = 10) -> list[dict[str, Any]]:
    if not snapshot:
        return []
    return product_profit_ranking(flatten_rows(snapshot.raw_data), limit=limit)


def monthly_series_from_snapshot(snapshot) -> dict[str, Any]:
    if not snapshot:
        return {
            "available": False,
            "series": [],
            "total": 0.0,
            "total_formatted": "—",
            "source": "monthly_stuff_group_lost_benefit",
            "source_label": "سود ماهانه گروه کالا",
        }
    return monthly_group_benefit_series(flatten_rows(snapshot.raw_data))
