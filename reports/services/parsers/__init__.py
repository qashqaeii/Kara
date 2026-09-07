"""Public parser API — re-exports + ReportParser class."""

from __future__ import annotations

import re
from typing import Any

from reports.services.parsers.grid import extract_sum_row, flatten_rows
from reports.services.parsers.values import (
    format_money,
    format_number,
    normalize_digits,
    parse_bool,
    parse_decimal,
    parse_int,
    parse_number,
)
from reports.services.report_registry import ReportConfig, ReportDefinition

__all__ = [
    "ReportParser",
    "flatten_rows",
    "extract_sum_row",
    "parse_number",
    "parse_decimal",
    "parse_int",
    "parse_bool",
    "format_number",
    "format_money",
    "normalize_digits",
]


KPI_LABELS = {
    "total_sale": "فروش نهایی",
    "total_pure_sale": "فروش خالص",
    "final_order_count": "تعداد سفارش نهایی",
    "settlement_remainder": "مانده تسویه",
    "distribution_reversion": "برگشت از توزیع",
    "sale_reversion": "برگشت از فروش",
}


class ReportParser:
    parse_number = staticmethod(parse_number)
    parse_decimal = staticmethod(parse_decimal)

    @staticmethod
    def extract_kpis(
        sum_row_data: dict | None,
        config: ReportDefinition | ReportConfig,
    ) -> dict[str, dict]:
        if not sum_row_data:
            return {}

        kpis: dict[str, dict] = {}
        from reports.services.currency import MONEY_KPI_KEYS, currency_label, display_float, format_money_number

        for kpi_key, field_name in config.kpi_fields.items():
            raw_value = sum_row_data.get(field_name)
            numeric = parse_number(raw_value)
            is_money = kpi_key in MONEY_KPI_KEYS
            kpis[kpi_key] = {
                "label": KPI_LABELS.get(kpi_key, field_name),
                "raw": raw_value,
                "numeric": display_float(raw_value) if is_money else numeric,
                "decimal": str(parse_decimal(raw_value)) if parse_decimal(raw_value) is not None else None,
                "formatted": format_money_number(raw_value) if is_money else format_number(raw_value),
                "source_field": field_name,
                "unit": currency_label() if is_money else "",
            }
        return kpis

    @staticmethod
    def get_visible_columns(config: ReportDefinition | ReportConfig) -> list[dict]:
        return [
            {
                "key": col.key,
                "label": col.label,
                "numeric": col.numeric,
                "money": getattr(col, "money", False),
            }
            for col in config.columns
            if col.visible
        ]

    @staticmethod
    def get_cell_display(
        row: dict, column_key: str, numeric: bool = False, money: bool = False
    ) -> str:
        from reports.services.currency import format_money_number

        value = row.get(column_key)
        if value is None or value == "":
            return "—"
        if money:
            return format_money_number(value)
        if numeric:
            return format_number(value)
        return str(value)

    @staticmethod
    def get_sum_row_display(
        sum_row_data: dict | None,
        column_key: str,
        numeric: bool = False,
        money: bool = False,
    ) -> str:
        from reports.services.currency import format_money_number

        if not sum_row_data:
            return "—"
        value = sum_row_data.get(column_key)
        if value is None:
            return "—"
        if money:
            return format_money_number(value)
        if numeric:
            return format_number(value)
        return str(value) if value else "—"

    @staticmethod
    def get_top_performers(
        rows: list[dict],
        *,
        name_key: str = "VisitorName",
        code_key: str = "VisitorCode",
        rank_key: str = "TotalSale",
        limit: int = 3,
    ) -> list[dict]:
        from reports.services.currency import format_money_number

        ranked = []
        for row in rows:
            name = (row.get(name_key) or "").strip()
            if not name:
                continue
            sale = parse_number(row.get(rank_key))
            if sale is None or sale <= 0:
                continue
            ranked.append(
                {
                    "rank": 0,
                    "name": name,
                    "code": (row.get(code_key) or "").strip() or "—",
                    "total_sale": sale,
                    "total_sale_formatted": format_money_number(row.get(rank_key)),
                    "order_count": format_number(row.get("OrderCountBasedOnFinalOrder")),
                    "pure_sale_formatted": format_money_number(row.get("TotalPureSale")),
                    "head_visitor": (row.get("HeadVisitorName") or "").strip(),
                    "partners": format_number(row.get("PartnerNumberBasedOnFinalOrder")),
                    "distribution_reversion": format_money_number(row.get("TotalDistributionReversion")),
                    "sale_reversion": format_money_number(row.get("TotalSaleReversion")),
                }
            )

        ranked.sort(key=lambda item: item["total_sale"], reverse=True)
        top = ranked[:limit]
        for i, item in enumerate(top, start=1):
            item["rank"] = i
        return top

    @staticmethod
    def get_top_performers_from_snapshot(snapshot, limit: int = 10) -> list[dict]:
        if not snapshot:
            return []
        rows = flatten_rows(snapshot.raw_data)
        # Head visitor report uses VisitorName as supervisor name
        name_key = "VisitorName"
        code_key = "VisitorCode"
        return ReportParser.get_top_performers(
            rows, name_key=name_key, code_key=code_key, limit=limit
        )

    @staticmethod
    def search_rows(rows: list[dict], query: str) -> list[dict]:
        if not query:
            return rows
        query_lower = normalize_digits(query.lower())
        pattern = re.compile(re.escape(query_lower), re.IGNORECASE)
        filtered = []
        for row in rows:
            haystack = " ".join(
                normalize_digits(str(v)) for v in row.values() if v is not None
            ).lower()
            if pattern.search(haystack):
                filtered.append(row)
        return filtered

    @staticmethod
    def ranking_table(
        rows: list[dict],
        *,
        rank_by: str = "TotalSale",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        ranked = ReportParser.get_top_performers(
            rows, rank_key=rank_by, limit=limit or len(rows)
        )
        return ranked
