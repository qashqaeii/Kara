"""Shared helpers for analytics ranking pages."""

from __future__ import annotations

from typing import Any

from reports.services.currency import currency_label, format_money_number
from reports.services.display import period_preset_label


PERIOD_OPTIONS = (
    ("all", "کل داده‌ها"),
    ("today", "امروز"),
    ("yesterday", "دیروز"),
    ("current_week", "هفته جاری"),
    ("current_month", "ماه جاری"),
    ("last_7_days", "۷ روز اخیر"),
    ("last_30_days", "۳۰ روز اخیر"),
)


def enrich_ranking_rows(items: list[dict]) -> list[dict]:
    """Attach share_percent relative to the #1 row for bar visuals."""
    if not items:
        return []
    top = float(items[0].get("total_sale") or items[0].get("pure_sale") or 0) or 1.0
    enriched = []
    for row in items:
        amount = float(row.get("total_sale") or row.get("pure_sale") or 0)
        item = dict(row)
        item["share_of_leader"] = round(min(100.0, amount / top * 100), 1)
        item["amount"] = amount
        if "formatted" not in item:
            item["formatted"] = row.get("total_sale_formatted") or row.get("pure_sale_formatted") or format_money_number(amount)
        enriched.append(item)
    return enriched


def ranking_summary(items: list[dict], *, label_singular: str = "نفر") -> dict[str, Any]:
    """Aggregate KPIs for a ranking list (salespersons / supervisors / regions)."""
    if not items:
        return {
            "count": 0,
            "total": 0,
            "total_formatted": "0",
            "avg_formatted": "0",
            "top_name": "—",
            "top_formatted": "—",
            "top_share": 0,
            "orders": 0,
            "label_singular": label_singular,
            "unit": currency_label(),
        }

    amounts = [float(r.get("total_sale") or r.get("pure_sale") or r.get("amount") or 0) for r in items]
    total = sum(amounts)
    orders = sum(int(r.get("order_count") or 0) for r in items)
    top = items[0]
    top_amount = amounts[0]
    return {
        "count": len(items),
        "total": total,
        "total_formatted": format_money_number(total),
        "avg_formatted": format_money_number(total / len(items) if items else 0),
        "top_name": top.get("name") or "—",
        "top_formatted": top.get("total_sale_formatted") or top.get("formatted") or format_money_number(top_amount),
        "top_share": round(top_amount / total * 100, 1) if total else 0,
        "orders": orders,
        "label_singular": label_singular,
        "unit": currency_label(),
    }


def chart_payload(items: list[dict], *, limit: int = 8) -> list[dict]:
    """Chart points use display currency (Toman) to match UI formatting."""
    from reports.services.currency import display_float

    rows = []
    for r in items[:limit]:
        if r.get("value") is not None:
            value = float(r["value"] or 0)
            raw = r.get("total_sale") or r.get("pure_sale") or r.get("amount") or 0
        else:
            raw = r.get("total_sale") or r.get("pure_sale") or r.get("amount") or 0
            value = display_float(raw)
        rows.append(
            {
                "name": (r.get("name") or "")[:28],
                "value": value,
                "formatted": r.get("total_sale_formatted")
                or r.get("formatted")
                or format_money_number(raw),
            }
        )
    return rows


def _parse_order_count(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace(",", "").replace("٬", "").strip()
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def team_share_payload(items: list[dict], *, limit: int = 6) -> list[dict]:
    """Aggregate sales by supervisor/team for a doughnut chart."""
    from collections import defaultdict
    from decimal import Decimal

    from reports.services.currency import display_float

    buckets: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in items:
        team = (row.get("head_visitor") or "").strip() or "بدون سرپرست"
        buckets[team] += Decimal(str(row.get("total_sale") or row.get("amount") or 0))

    ranked = sorted(buckets.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return []

    top = ranked[: max(1, limit - 1)] if len(ranked) > limit else ranked
    rest = ranked[len(top) :]
    rows = [
        {
            "name": name[:24],
            "value": display_float(amount),
            "formatted": format_money_number(amount),
        }
        for name, amount in top
        if amount > 0
    ]
    if rest:
        other = sum((amount for _, amount in rest), Decimal("0"))
        if other > 0:
            rows.append(
                {
                    "name": "سایر",
                    "value": display_float(other),
                    "formatted": format_money_number(other),
                }
            )
    return rows


def orders_chart_payload(items: list[dict], *, limit: int = 8) -> list[dict]:
    """Top visitors by final order count (non-money chart values)."""
    ranked = sorted(items, key=lambda row: _parse_order_count(row.get("order_count")), reverse=True)
    rows = []
    for row in ranked[:limit]:
        orders = _parse_order_count(row.get("order_count"))
        if orders <= 0:
            continue
        rows.append(
            {
                "name": (row.get("name") or "")[:28],
                "value": orders,
                "formatted": f"{orders:,}",
            }
        )
    return rows


def period_context(preset: str) -> dict[str, Any]:
    return {
        "preset": preset,
        "preset_label": period_preset_label(preset),
        "period_options": PERIOD_OPTIONS,
    }
