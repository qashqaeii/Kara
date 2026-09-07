"""Parse Kara LostBenefit (P&L) HTML print output."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from reports.services.parsers.values import parse_decimal

_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _cell_text(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub("", html)).strip()


def _parse_amount(value: str) -> Decimal | None:
    return parse_decimal(value)


def parse_lost_benefit_html(html: str) -> dict[str, Any]:
    """
    Extract company-level P&L figures from LostBenefit HTML.

    Prefer labeled summary rows (جمع / سود عملیاتی / سود خالص).
    """
    if not html or "<" not in html:
        return {}

    rows: list[list[str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.DOTALL | re.IGNORECASE):
        cells = [_cell_text(td) for td in _TD_RE.findall(tr)]
        cells = [c for c in cells if c is not None]
        if cells:
            rows.append(cells)

    labeled: dict[str, Decimal] = {}
    collect_totals: list[Decimal] = []

    for cells in rows:
        joined = " ".join(cells)
        amounts = [a for a in (_parse_amount(c) for c in cells) if a is not None]
        if not amounts:
            continue

        label = cells[0]
        if "سود(زیان) عملیاتی" in joined or "سود(زیان) عملیاتی" in label:
            labeled["operating_profit"] = amounts[-1]
        elif "سود(زیان) خالص" in joined or "سود(زیان) خالص" in label:
            labeled["net_profit"] = amounts[-1]
        elif label.startswith("جمع") or "جمع:" in label:
            collect_totals.append(amounts[-1])

    # Order of جمع rows: net sales, COGS (often negative when ending inventory
    # dominates), income total, expense total.
    net_pure_sale = collect_totals[0] if len(collect_totals) >= 1 else None
    cogs_raw = collect_totals[1] if len(collect_totals) >= 2 else None
    income_total = collect_totals[2] if len(collect_totals) >= 3 else None
    expense_total = collect_totals[3] if len(collect_totals) >= 4 else None

    # Keep signed COGS so gross matches Kara: sales − (−COGS) when inventory dominates.
    cogs = cogs_raw

    operating_raw = labeled.get("operating_profit")
    net_profit = labeled.get("net_profit")

    # Gross ≈ sales − signed COGS (matches Kara's pre-opex operating line).
    gross_profit = None
    if net_pure_sale is not None and cogs is not None:
        gross_profit = net_pure_sale - cogs
    elif operating_raw is not None:
        gross_profit = operating_raw

    # Kara's «سود عملیاتی» appears before opex. Prefer post-opex figure when
    # expense totals exist so the KPI is not an inflated pre-expense number.
    operating = operating_raw
    if operating is not None and expense_total is not None:
        operating = operating - abs(expense_total) + abs(income_total or Decimal("0"))

    margin = Decimal("0")
    if gross_profit is not None and net_pure_sale and abs(net_pure_sale) > 0:
        margin = (gross_profit / net_pure_sale * 100).quantize(Decimal("0.01"))

    return {
        "net_pure_sale": str(net_pure_sale or 0),
        "cost_of_goods_sold": str(cogs if cogs is not None else 0),
        "gross_profit": str(gross_profit or 0),
        "operating_profit": str(operating or 0),
        "net_profit": str(net_profit or 0),
        "gross_margin_rate": str(margin),
        "line_items": {
            "collect_totals": [str(v) for v in collect_totals],
            "operating_profit_raw": str(operating_raw or 0),
            "operating_profit": str(operating or 0),
            "net_profit": str(net_profit or 0),
            "cogs_signed": str(cogs if cogs is not None else 0),
        },
    }


def parsed_to_sum_row(parsed: dict[str, Any]) -> dict[str, str]:
    return {
        "NetPureSale": parsed.get("net_pure_sale", "0"),
        "CostOfGoodsSold": parsed.get("cost_of_goods_sold", "0"),
        "GrossProfit": parsed.get("gross_profit", "0"),
        "OperatingProfit": parsed.get("operating_profit", "0"),
        "NetProfit": parsed.get("net_profit", "0"),
        "GrossMarginRate": parsed.get("gross_margin_rate", "0"),
    }
