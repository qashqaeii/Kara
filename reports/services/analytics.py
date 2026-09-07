"""Analytics services — KPIs, rankings, alerts from local DB only."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.utils import timezone

from reports.constants import (
    CONNECTION_STATUS_LABELS,
    DEFAULT_PERIOD_PRESET,
    FEATURE_FLAGS,
    LOST_BENEFIT_SEPARATE_REPORT,
    MONTHLY_GROUP_LOST_BENEFIT_REPORT,
    PRIMARY_KPI_REPORT,
    PRODUCT_REPORT,
    PROFIT_REPORT,
    ProfitabilityStatus,
    AlertSeverity,
    AlertStatus,
    ConnectionStatus,
)
from reports.models import (
    DashboardRefreshLog,
    KaraConnection,
    KaraReportSnapshot,
    KaraSyncJob,
    ManagementAlert,
)
from reports.services.access_control import AccessControlService
from reports.services.alert_engine import AlertEngine
from reports.services.analytics_query import AnalyticsQueryService
from reports.services.currency import currency_label, display_float, format_money_number
from reports.services.dates import DateRange, format_jalali_datetime, parse_business_date
from reports.services.display import report_title, sync_status_label
from reports.services.period_comparison import PeriodComparisonService
from reports.services.parsers import ReportParser, flatten_rows, format_number, parse_decimal, parse_int
from reports.services.report_registry import ReportRegistry


def _person_initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0][:1]
    return f"{parts[0][:1]}{parts[-1][:1]}"


def _enrich_tv_ranking(items: list[dict], *, kind: str = "visitor") -> dict[str, Any]:
    """Add share, AOV, initials and board summary for TV ranking slides."""
    from reports.services.parsers.values import parse_number

    rows = [dict(item) for item in items]
    total_sale = sum(float(r.get("total_sale") or 0) for r in rows)
    leader_sale = float(rows[0].get("total_sale") or 0) if rows else 0.0
    total_orders = 0

    for row in rows:
        sale = float(row.get("total_sale") or 0)
        orders = parse_number(row.get("order_count")) or 0
        try:
            orders_n = int(orders)
        except (TypeError, ValueError):
            orders_n = 0
        total_orders += max(orders_n, 0)
        row["orders_n"] = orders_n
        row["share_percent"] = round(100.0 * sale / total_sale, 1) if total_sale else 0.0
        row["bar_percent"] = round(100.0 * sale / leader_sale, 1) if leader_sale else 0.0
        row["initials"] = _person_initials(row.get("name") or "")
        row["avg_order_formatted"] = (
            format_money_number(sale / orders_n) if orders_n > 0 and sale > 0 else "—"
        )
        row["medal"] = {1: "gold", 2: "silver", 3: "bronze"}.get(int(row.get("rank") or 0), "")
        row["kind"] = kind

    chart = [
        {
            "name": r.get("name") or "—",
            "code": r.get("code") or "",
            "value": display_float(r.get("total_sale") or 0),
            "share": r.get("share_percent") or 0,
            "rank": r.get("rank"),
        }
        for r in rows[:6]
    ]

    return {
        "items": rows,
        "count": len(rows),
        "total_sale": total_sale,
        "total_sale_formatted": format_money_number(total_sale) if total_sale else "—",
        "total_orders": total_orders,
        "total_orders_formatted": format_number(total_orders) if total_orders else "۰",
        "leader_share": rows[0]["share_percent"] if rows else 0.0,
        "leader": rows[0] if rows else None,
        "runners": rows[1:3],
        "rest": rows[3:],
        "podium": rows[:3],
        "chart": chart,
        "kind": kind,
    }


def _ago_label(dt) -> str:
    if not dt:
        return "هنوز همگام‌سازی نشده"
    delta = timezone.now() - dt
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "همین الان"
    if minutes < 60:
        return f"{minutes} دقیقه قبل"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ساعت قبل"
    days = hours // 24
    return f"{days} روز قبل"


def _snapshot_covers_full_period(snapshot: KaraReportSnapshot) -> bool:
    """True when snapshot is YTD / multi-day (suitable for «کل داده‌ها»)."""
    pf = parse_business_date(snapshot.period_from)
    pt = parse_business_date(snapshot.period_to)
    if pf and pt and (pt - pf).days > 0:
        return True
    active = parse_int(
        (snapshot.sum_row_data or {}).get("ActiveDayCountBasedOnFinalOrder")
    ) or 0
    return active > 1


class AnalyticsService:
    """All dashboard numbers are read from local snapshots — never live Kara."""

    @staticmethod
    def get_latest_snapshot(report_key: str, personnel_code: str = "") -> KaraReportSnapshot | None:
        return (
            KaraReportSnapshot.objects.filter(
                report_key=report_key,
                personnel_code=personnel_code or "",
            )
            .order_by("-fetched_at")
            .first()
        )

    @classmethod
    def get_full_period_snapshot(
        cls, report_key: str, personnel_code: str = ""
    ) -> KaraReportSnapshot | None:
        """Latest snapshot that covers more than a single day (YTD / full)."""
        qs = KaraReportSnapshot.objects.filter(
            report_key=report_key,
            personnel_code=personnel_code or "",
        ).order_by("-fetched_at")[:30]
        for snap in qs:
            if _snapshot_covers_full_period(snap) and (
                snap.sum_row_data or flatten_rows(snap.raw_data)
            ):
                return snap
        # Fallback: any snapshot with a non-empty sum row.
        for snap in qs:
            if snap.sum_row_data:
                return snap
        return None

    @classmethod
    def company_kpis(cls, preset: str = DEFAULT_PERIOD_PRESET) -> dict[str, dict]:
        """
        Company KPIs from analytics layer; falls back to latest snapshot if no history.
        """
        preset = preset or DEFAULT_PERIOD_PRESET

        # «کل داده‌ها» همیشه از اسنپ‌شات کامل/YTD — نه جمع روزهای مخلوط.
        if PeriodComparisonService.uses_latest_snapshot(preset):
            kpis = cls._company_kpis_from_snapshot(full_period=True)
            if kpis:
                pnl = AnalyticsQueryService.company_pnl_kpis()
                if pnl:
                    if "pnl_operating_profit" in pnl:
                        kpis["operating_profit"] = {
                            **pnl["pnl_operating_profit"],
                            "label": "سود عملیاتی (حسابداری YTD)",
                        }
                    if "pnl_net_profit" in pnl:
                        kpis["net_profit"] = {
                            **pnl["pnl_net_profit"],
                            "label": "سود خالص (حسابداری YTD)",
                        }
                    if "pnl_operating_margin_rate" in pnl:
                        kpis["operating_margin_rate"] = {
                            **pnl["pnl_operating_margin_rate"],
                            "label": pnl["pnl_operating_margin_rate"].get(
                                "label", "حاشیه عملیاتی حسابداری (YTD)"
                            ),
                        }
                    if "pnl_margin_rate" in pnl and "gross_margin_rate" not in kpis:
                        kpis["gross_margin_rate"] = {
                            **pnl["pnl_margin_rate"],
                            "label": "حاشیه ناخالص حسابداری (YTD)",
                        }
                return kpis

        current_range, _ = PeriodComparisonService.comparison_range(preset)
        if current_range and AnalyticsQueryService.has_history():
            kpis = AnalyticsQueryService.company_kpis_for_range(
                current_range, preset=preset
            )
            profit_kpis = AnalyticsQueryService.profit_kpis_for_range(
                current_range, preset=preset
            )
            if profit_kpis:
                kpis.update(profit_kpis)
            for key in ("total_sale", "total_pure_sale", "final_order_count"):
                cmp = PeriodComparisonService.compare_field(
                    "total_pure_sale" if key == "total_pure_sale" else (
                        "order_count" if key == "final_order_count" else "total_sale"
                    ),
                    preset,
                )
                if key in kpis and cmp.is_comparable:
                    kpis[key]["comparison"] = cmp.as_dict()
            return kpis

        return cls._company_kpis_from_snapshot(full_period=False)

    @classmethod
    def _company_kpis_from_snapshot(cls, *, full_period: bool = False) -> dict[str, dict]:
        config = ReportRegistry.primary_kpi_report()
        snapshot = (
            cls.get_full_period_snapshot(config.key)
            if full_period
            else cls.get_latest_snapshot(config.key)
        )
        if not snapshot or not snapshot.sum_row_data:
            return {}
        kpis = ReportParser.extract_kpis(snapshot.sum_row_data, config)
        total_sale = parse_decimal(kpis.get("total_sale", {}).get("raw")) or Decimal("0")
        order_count = parse_decimal(kpis.get("final_order_count", {}).get("raw")) or Decimal("0")
        dist_rev = parse_decimal(kpis.get("distribution_reversion", {}).get("raw")) or Decimal("0")
        sale_rev = parse_decimal(kpis.get("sale_reversion", {}).get("raw")) or Decimal("0")
        avg_order = (total_sale / order_count) if order_count > 0 else Decimal("0")
        rev = abs(dist_rev) + abs(sale_rev)
        base = abs(total_sale) + rev
        reversion_rate = (rev / base * 100) if base > 0 else Decimal("0")
        rows = flatten_rows(snapshot.raw_data)
        active_visitors = sum(1 for r in rows if (parse_decimal(r.get("TotalSale")) or 0) > 0)
        kpis["avg_order_value"] = {
            "label": "میانگین مبلغ سفارش",
            "numeric": display_float(avg_order),
            "formatted": format_money_number(avg_order),
            "unit": currency_label(),
        }
        kpis["reversion_rate"] = {
            "label": "نرخ برگشت (٪)",
            "numeric": float(reversion_rate),
            "formatted": f"{reversion_rate:.1f}",
        }
        kpis["active_visitors"] = {
            "label": "ویزیتور فعال",
            "numeric": float(active_visitors),
            "formatted": format_number(active_visitors),
        }
        return kpis

    @classmethod
    def has_product_profit(cls) -> bool:
        snap = cls.get_latest_snapshot(LOST_BENEFIT_SEPARATE_REPORT)
        if not snap or not snap.raw_data:
            return False
        from reports.services.parsers.lost_benefit import ranking_from_snapshot

        return bool(ranking_from_snapshot(snap, limit=1))

    @classmethod
    def product_profit_ranking(cls, *, limit: int = 8) -> list[dict]:
        """Top products by BenefitLostPrice from LostBenefitSeparate."""
        snap = (
            cls.get_full_period_snapshot(LOST_BENEFIT_SEPARATE_REPORT)
            or cls.get_latest_snapshot(LOST_BENEFIT_SEPARATE_REPORT)
        )
        from reports.services.parsers.lost_benefit import ranking_from_snapshot

        return ranking_from_snapshot(snap, limit=limit)

    @classmethod
    def monthly_group_benefit(cls) -> dict[str, Any]:
        snap = cls.get_latest_snapshot(MONTHLY_GROUP_LOST_BENEFIT_REPORT)
        from reports.services.parsers.lost_benefit import monthly_series_from_snapshot

        return monthly_series_from_snapshot(snap)

    @classmethod
    def group_benefit_ranking(cls, *, limit: int = 8) -> list[dict]:
        snap = cls.get_latest_snapshot(MONTHLY_GROUP_LOST_BENEFIT_REPORT)
        if not snap:
            return []
        from reports.services.parsers.lost_benefit import group_benefit_ranking
        from reports.services.parsers import flatten_rows

        return group_benefit_ranking(flatten_rows(snap.raw_data), limit=limit)

    @classmethod
    def profitability_status(cls) -> dict[str, Any]:
        """Profitability from accounting P&L, product COGS, or sale_orders."""
        product_profit_available = cls.has_product_profit()

        if AnalyticsQueryService.has_company_pnl():
            message = (
                "سود عملیاتی و سود خالص از گزارش سود و زیان حسابداری استخراج شده است."
            )
            if product_profit_available:
                message += " سود به تفکیک کالا از گزارش سود و زیان تفکیکی در دسترس است."
            else:
                message += (
                    " برای سود کالا، گزارش «سود و زیان تفکیکی» را همگام‌سازی کنید."
                )
            return {
                "status": ProfitabilityStatus.AVAILABLE,
                "label": "سود و زیان حسابداری",
                "message": message,
                "can_show_profit": True,
                "product_profit_available": product_profit_available,
                "source": "profit_and_loss",
                "source_label": report_title("profit_and_loss"),
            }

        if product_profit_available:
            return {
                "status": ProfitabilityStatus.AVAILABLE,
                "label": "سود کالا (تفکیکی)",
                "message": (
                    "سود/زیان کالا از گزارش سود و زیان تفکیکی (فروش − بهای تمام‌شده) محاسبه می‌شود."
                ),
                "can_show_profit": True,
                "product_profit_available": True,
                "source": LOST_BENEFIT_SEPARATE_REPORT,
                "source_label": report_title(LOST_BENEFIT_SEPARATE_REPORT),
            }

        if AnalyticsQueryService.has_profit_history():
            return {
                "status": ProfitabilityStatus.AVAILABLE,
                "label": "سود ناخالص (فاکتور)",
                "message": (
                    "سود ناخالص از تفاوت مبلغ فاکتور و بهای تمام‌شده مشتری "
                    "محاسبه می‌شود — سود به تفکیک کالا در دسترس نیست."
                ),
                "can_show_profit": True,
                "product_profit_available": False,
                "source": "sale_orders",
                "source_label": report_title("sale_orders"),
            }

        snap = cls.get_latest_snapshot(PROFIT_REPORT)
        if snap and snap.sum_row_data:
            cost = parse_decimal(snap.sum_row_data.get("FinalizedCostForCustomer"))
            revenue = parse_decimal(snap.sum_row_data.get("OrderFinalPrice"))
            if cost is not None and cost > 0 and revenue is not None and revenue > 0:
                return {
                    "status": ProfitabilityStatus.AVAILABLE,
                    "label": "سود ناخالص (فاکتور)",
                    "message": (
                        "سود ناخالص از تفاوت مبلغ فاکتور و بهای تمام‌شده فاکتور محاسبه می‌شود — "
                        "سود به تفکیک کالا در دسترس نیست."
                    ),
                    "can_show_profit": True,
                    "product_profit_available": False,
                    "source": "sale_orders",
                }

        if cls.get_latest_snapshot(PRODUCT_REPORT) or AnalyticsQueryService.has_product_history():
            return {
                "status": ProfitabilityStatus.DATA_NOT_SUFFICIENT,
                "label": "سود ناخالص",
                "message": (
                    "گزارش فروش کالا همگام شده؛ بهای تمام‌شده در سطح کالا وجود ندارد — "
                    "گزارش «سود و زیان تفکیکی» یا سود و زیان حسابداری را همگام کنید."
                ),
                "can_show_profit": False,
                "product_profit_available": False,
            }

        if FEATURE_FLAGS.get("profitability"):
            return {
                "status": ProfitabilityStatus.AVAILABLE,
                "label": "سود ناخالص",
                "message": "",
                "can_show_profit": True,
                "product_profit_available": False,
            }

        return {
            "status": ProfitabilityStatus.API_NOT_DISCOVERED,
            "label": "سود ناخالص",
            "message": (
                "داده سودآوری هنوز کامل نیست — گزارش سود و زیان تفکیکی، "
                "سود و زیان حسابداری، یا فاکتور را همگام‌سازی کنید."
            ),
            "can_show_profit": False,
            "product_profit_available": False,
        }

    @classmethod
    def geo_summary(cls, *, limit: int = 5, preset: str = DEFAULT_PERIOD_PRESET, dr=None) -> dict[str, Any]:
        preset = preset or DEFAULT_PERIOD_PRESET
        # Full-data mode: aggregate from the full/YTD stuff_group snapshot.
        if PeriodComparisonService.uses_latest_snapshot(preset):
            return cls._geo_from_snapshot(limit=limit, full_period=True)
        if AnalyticsQueryService.has_history():
            if dr is None:
                current, _ = PeriodComparisonService.comparison_range(preset)
                dr = DateRange(current.start, current.end) if current else None
            cities = AnalyticsQueryService.region_ranking(
                "city", dr=dr, limit=limit, preset=preset
            )
            zones = AnalyticsQueryService.region_ranking(
                "zone", dr=dr, limit=limit, preset=preset
            )
            return {
                "available": bool(cities or zones),
                "cities": cities,
                "zones": zones,
            }
        return cls._geo_from_snapshot(limit=limit, full_period=False)

    @classmethod
    def _stuff_group_snapshot(cls, *, full_period: bool = True) -> KaraReportSnapshot | None:
        if full_period:
            return cls.get_full_period_snapshot("stuff_group_sale") or cls.get_latest_snapshot(
                "stuff_group_sale"
            )
        return cls.get_latest_snapshot("stuff_group_sale")

    @classmethod
    def product_groups_from_snapshot(
        cls, *, limit: int = 6, full_period: bool = True
    ) -> list[dict]:
        """Aggregate StuffGroupName from Kara stuff_group_sale (matches panel totals)."""
        snapshot = cls._stuff_group_snapshot(full_period=full_period)
        if not snapshot:
            return []
        rows = flatten_rows(snapshot.raw_data)
        totals: dict[str, dict[str, Decimal | int]] = {}
        for row in rows:
            group = (row.get("StuffGroupName") or row.get("StuffGroupName1") or "").strip()
            if not group or group in ("---", "-"):
                continue
            pure = parse_decimal(row.get("PureSalePrice")) or Decimal("0")
            rev = abs(parse_decimal(row.get("SaleReversionPrice")) or Decimal("0")) + abs(
                parse_decimal(row.get("DistributionReversionPrice")) or Decimal("0")
            )
            bucket = totals.get(group)
            if not bucket:
                totals[group] = {
                    "pure_sale": pure,
                    "reversion_amount": rev,
                    "order_count": parse_int(row.get("OrderCount")) or 0,
                }
            else:
                bucket["pure_sale"] = Decimal(bucket["pure_sale"]) + pure
                bucket["reversion_amount"] = Decimal(bucket["reversion_amount"]) + rev
                bucket["order_count"] = int(bucket["order_count"]) + (
                    parse_int(row.get("OrderCount")) or 0
                )
        ranked = sorted(
            totals.items(),
            key=lambda item: Decimal(item[1]["pure_sale"]),
            reverse=True,
        )[:limit]
        total_pure = sum((Decimal(v["pure_sale"]) for _, v in ranked), Decimal("0")) or Decimal(
            "1"
        )
        return [
            {
                "name": name,
                "code": name,
                "pure_sale": float(data["pure_sale"]),
                "reversion_amount": float(data["reversion_amount"]),
                "value": display_float(data["pure_sale"]),
                "formatted": format_money_number(data["pure_sale"]),
                "share_percent": float(Decimal(data["pure_sale"]) / total_pure * 100),
                "order_count": int(data["order_count"]),
            }
            for name, data in ranked
            if Decimal(data["pure_sale"]) > 0
        ]

    @classmethod
    def products_from_snapshot(
        cls,
        *,
        limit: int = 8,
        rank_by: str = "pure_sale",
        full_period: bool = True,
    ) -> list[dict]:
        """Aggregate products from Kara stuff_group_sale for «کل داده‌ها»."""
        snapshot = cls._stuff_group_snapshot(full_period=full_period)
        if not snapshot:
            return []
        rows = flatten_rows(snapshot.raw_data)
        products: dict[str, dict[str, Any]] = {}
        for row in rows:
            code = str(row.get("StuffCode") or "").strip()
            if not code:
                continue
            bucket = products.get(code)
            if not bucket:
                bucket = {
                    "stuff_name": (row.get("StuffName") or "").strip(),
                    "stuff_group_name": (
                        row.get("StuffGroupName") or row.get("StuffGroupName1") or ""
                    ).strip(),
                    "pure_sale": Decimal("0"),
                    "sale_amount": Decimal("0"),
                    "sale_quantity": 0,
                    "sale_reversion_amount": Decimal("0"),
                }
                products[code] = bucket
            if not bucket["stuff_name"]:
                bucket["stuff_name"] = (row.get("StuffName") or "").strip()
            if not bucket["stuff_group_name"]:
                bucket["stuff_group_name"] = (
                    row.get("StuffGroupName") or row.get("StuffGroupName1") or ""
                ).strip()
            bucket["pure_sale"] += parse_decimal(row.get("PureSalePrice")) or Decimal("0")
            bucket["sale_amount"] += parse_decimal(row.get("NotPureSalePrice")) or Decimal("0")
            bucket["sale_quantity"] += parse_int(
                row.get("PureSaleQuantity") or row.get("NotPureSaleQuantity")
            ) or 0
            bucket["sale_reversion_amount"] += abs(
                parse_decimal(row.get("SaleReversionPrice")) or Decimal("0")
            ) + abs(parse_decimal(row.get("DistributionReversionPrice")) or Decimal("0"))

        field = (
            "sale_reversion_amount"
            if rank_by == "sale_reversion_amount"
            else "pure_sale"
        )
        ranked = sorted(
            products.items(),
            key=lambda item: Decimal(item[1][field]),
            reverse=True,
        )
        result = []
        for code, data in ranked:
            metric = Decimal(data[field])
            if metric <= 0:
                continue
            result.append(
                {
                    "rank": len(result) + 1,
                    "code": code,
                    "name": data["stuff_name"] or code,
                    "group": data["stuff_group_name"] or "—",
                    "pure_sale": float(data["pure_sale"]),
                    "value": display_float(data["pure_sale"]),
                    "pure_sale_formatted": format_money_number(data["pure_sale"]),
                    "sale_amount": float(data["sale_amount"]),
                    "sale_amount_formatted": format_money_number(data["sale_amount"]),
                    "sale_quantity": int(data["sale_quantity"]),
                    "sale_reversion_amount": float(data["sale_reversion_amount"]),
                    "sale_reversion_formatted": format_money_number(
                        data["sale_reversion_amount"]
                    ),
                }
            )
            if len(result) >= limit:
                break
        return result

    @classmethod
    def _geo_from_snapshot(cls, *, limit: int = 5, full_period: bool = True) -> dict[str, Any]:
        snapshot = cls._stuff_group_snapshot(full_period=full_period)
        if not snapshot:
            return {"available": False, "cities": [], "zones": []}

        rows = flatten_rows(snapshot.raw_data)
        city_totals: dict[str, Decimal] = {}
        zone_totals: dict[str, Decimal] = {}
        for row in rows:
            city = (row.get("City") or "").strip()
            zone = (row.get("Zone") or "").strip()
            amount = parse_decimal(row.get("PureSalePrice")) or Decimal("0")
            if city and city not in ("---", "-"):
                city_totals[city] = city_totals.get(city, Decimal("0")) + amount
            if zone and zone not in ("---", "-"):
                zone_totals[zone] = zone_totals.get(zone, Decimal("0")) + amount

        def top_items(totals: dict[str, Decimal]) -> list[dict]:
            ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:limit]
            return [
                {
                    "name": name,
                    "amount": float(val),
                    "value": display_float(val),
                    "formatted": format_money_number(val),
                }
                for name, val in ranked
            ]

        return {
            "available": bool(city_totals or zone_totals),
            "cities": top_items(city_totals),
            "zones": top_items(zone_totals),
        }

    @classmethod
    def data_explorer_reports(cls) -> list[dict]:
        """Report list for Data Explorer / Sync Center — not main dashboard."""
        items = []
        for key, config in ReportRegistry.syncable().items():
            snapshot = cls.get_latest_snapshot(key)
            kpis = (
                ReportParser.extract_kpis(snapshot.sum_row_data, config)
                if snapshot and snapshot.sum_row_data
                else {}
            )
            items.append(
                {
                    "key": key,
                    "title": config.title,
                    "slug": config.slug,
                    "snapshot": snapshot,
                    "has_data": snapshot is not None,
                    "kpis": kpis,
                    "is_primary": config.is_primary_kpi_source,
                    "rows_count": snapshot.rows_count if snapshot else 0,
                    "fetched_at": snapshot.fetched_at if snapshot else None,
                }
            )
        return items

    @classmethod
    def report_cards(cls) -> list[dict]:
        """Backward-compatible alias for data explorer."""
        return cls.data_explorer_reports()

    @classmethod
    def tv_context(cls) -> dict[str, Any]:
        preset = DEFAULT_PERIOD_PRESET
        kpis = cls.company_kpis(preset)
        dr, _ = PeriodComparisonService.comparison_range(preset)
        from reports.services.dates import DateRange

        date_range = DateRange(dr.start, dr.end) if dr else None
        if PeriodComparisonService.uses_latest_snapshot(preset):
            product_groups = cls.product_groups_from_snapshot(limit=5, full_period=True)
            product_group_reversions = [
                {
                    **g,
                    "formatted": format_money_number(g["reversion_amount"]),
                    "share_percent": g.get("share_percent", 0),
                }
                for g in sorted(
                    cls.product_groups_from_snapshot(limit=20, full_period=True),
                    key=lambda x: x.get("reversion_amount", 0),
                    reverse=True,
                )[:5]
                if g.get("reversion_amount", 0) > 0
            ]
            top_products = cls.products_from_snapshot(limit=5, full_period=True)
            top_reversions = cls.products_from_snapshot(
                limit=5, rank_by="sale_reversion_amount", full_period=True
            )
        else:
            product_groups = AnalyticsQueryService.product_group_ranking(
                dr=date_range, limit=5, preset=preset
            )
            product_group_reversions = AnalyticsQueryService.product_group_reversion_ranking(
                dr=date_range, limit=5, preset=preset
            )
            top_products = AnalyticsQueryService.product_ranking(
                dr=date_range, limit=5, preset=preset
            )
            top_reversions = AnalyticsQueryService.product_ranking(
                dr=date_range, limit=5, rank_by="sale_reversion_amount", preset=preset
            )
        monthly_sales = AnalyticsQueryService.monthly_sales_series()
        from reports.services.display import period_preset_label
        from reports.services.insights import InsightsService

        trend_days = 30
        if date_range:
            trend_days = min(120, max(7, (date_range.end - date_range.start).days + 1))
        trend = AnalyticsQueryService.trend(
            "total_pure_sale",
            days=trend_days,
            start=date_range.start if date_range else None,
            end=date_range.end if date_range else None,
        )
        preset_label = period_preset_label(preset)
        trend_points = len(trend)
        if trend_points:
            trend_from = trend[0].get("date_label") or ""
            trend_to = trend[-1].get("date_label") or ""
            if PeriodComparisonService.uses_latest_snapshot(preset):
                trend_subtitle = (
                    f"نمودار روزانه · کل داده‌ها ({trend_points} روز"
                    f"{f' · {trend_from} تا {trend_to}' if trend_from and trend_to else ''})"
                )
            else:
                trend_subtitle = (
                    f"نمودار روزانه · {preset_label} ({trend_points} روز"
                    f"{f' · {trend_from} تا {trend_to}' if trend_from and trend_to else ''})"
                )
        else:
            trend_subtitle = f"نمودار روزانه · {preset_label}"

        visitor_board = _enrich_tv_ranking(
            cls.visitor_ranking(limit=5, preset=preset), kind="visitor"
        )
        supervisor_board = _enrich_tv_ranking(
            cls.head_visitor_ranking(limit=5, preset=preset), kind="supervisor"
        )

        return {
            "connection": cls.connection_status(),
            "profitability": cls.profitability_status(),
            "pulse": {
                "total_pure_sale": kpis.get("total_pure_sale", {}),
                "total_sale": kpis.get("total_sale", {}),
                "final_order_count": kpis.get("final_order_count", {}),
                "avg_order_value": kpis.get("avg_order_value", {}),
                "distribution_reversion": kpis.get("distribution_reversion", {}),
                "sale_reversion": kpis.get("sale_reversion", {}),
                "reversion_rate": kpis.get("reversion_rate", {}),
                "active_visitors": kpis.get("active_visitors", {}),
                "operating_profit": kpis.get("operating_profit", {}),
                "operating_margin_rate": kpis.get("operating_margin_rate", {}),
                "gross_profit": kpis.get("gross_profit", {}),
                "gross_margin_rate": kpis.get("gross_margin_rate", {}),
                "net_profit": kpis.get("net_profit", {}),
            },
            "comparisons": {
                "total_pure_sale": PeriodComparisonService.compare_field("total_pure_sale", preset).as_dict(),
            },
            "trend": trend,
            "trend_subtitle": trend_subtitle,
            "trend_points": trend_points,
            "preset_label": preset_label,
            "period_subtitle": f"{preset_label} · منبع گزارش فروش ویزیتور",
            "top_visitors": visitor_board["items"],
            "visitor_board": visitor_board,
            "top_supervisors": supervisor_board["items"],
            "supervisor_board": supervisor_board,
            "geo": cls.geo_summary(limit=6, preset=preset, dr=date_range),
            "product_groups": product_groups,
            "product_group_reversions": product_group_reversions,
            "top_products": top_products,
            "top_product_reversions": top_reversions,
            "top_product_profits": cls.product_profit_ranking(limit=5),
            "group_benefits": cls.group_benefit_ranking(limit=5),
            "monthly_group_benefit": cls.monthly_group_benefit(),
            "monthly_sales": monthly_sales,
            "company_pnl": AnalyticsQueryService.company_pnl_kpis(),
            "receivables": AnalyticsQueryService.receivables_summary(),
            "insights": InsightsService.for_dashboard(preset=preset),
            "alerts": [
                {
                    "severity": a.severity,
                    "title": a.title,
                    "description": a.description,
                    "current_value": a.current_value,
                    "detected_at": a.detected_at.isoformat(),
                }
                for a in cls.open_alerts(limit=6)
            ],
            "has_company_data": bool(kpis),
            "has_history": AnalyticsQueryService.has_history(),
            "preset": preset,
        }

    @classmethod
    def dashboard_context(
        cls, preset: str = DEFAULT_PERIOD_PRESET, *, user=None
    ) -> dict[str, Any]:
        preset = preset or DEFAULT_PERIOD_PRESET
        kpis = cls.company_kpis(preset)
        if not AnalyticsQueryService.has_history():
            profit_snap = cls.get_latest_snapshot(PROFIT_REPORT)
            if profit_snap and profit_snap.sum_row_data:
                from reports.services.report_registry import get_report_config

                profit_kpis = ReportParser.extract_kpis(
                    profit_snap.sum_row_data, get_report_config(PROFIT_REPORT)
                )
                revenue = parse_decimal(profit_kpis.get("invoice_revenue", {}).get("raw")) or Decimal("0")
                cost = parse_decimal(profit_kpis.get("finalized_cost", {}).get("raw")) or Decimal("0")
                sale_rev = parse_decimal(profit_kpis.get("sale_reversion", {}).get("raw")) or Decimal("0")
                gross = revenue - cost - sale_rev
                if revenue > 0 or cost > 0:
                    margin = (gross / revenue * 100) if revenue > 0 else Decimal("0")
                    kpis["gross_profit"] = {
                        "label": "سود ناخالص (فاکتور)",
                        "formatted": format_money_number(gross),
                        "numeric": float(gross),
                        "unit": currency_label(),
                        "tooltip": "بر اساس بهای تمام‌شده فاکتور",
                    }
                    if cost > 0 and Decimal("0") <= margin <= Decimal("100"):
                        kpis["gross_margin_rate"] = {
                            "label": "حاشیه سود ناخالص",
                            "formatted": f"{margin:.1f}",
                            "numeric": float(margin),
                        }
        conn = cls.connection_status()
        alerts = cls.open_alerts()
        visitor_rank = cls.visitor_ranking(limit=10, preset=preset, user=user)
        head_rank = cls.head_visitor_ranking(limit=10, preset=preset, user=user)
        comparisons = {
            "total_pure_sale": PeriodComparisonService.compare_field("total_pure_sale", preset).as_dict(),
            "total_sale": PeriodComparisonService.compare_field("total_sale", preset).as_dict(),
            "order_count": PeriodComparisonService.compare_field("order_count", preset).as_dict(),
        }
        monthly_sales = AnalyticsQueryService.monthly_sales_series()
        company_pnl = AnalyticsQueryService.company_pnl_kpis()
        from reports.services.insights import InsightsService
        from reports.services.dates import DateRange as DR

        dr, _ = PeriodComparisonService.comparison_range(preset)
        date_range = DR(dr.start, dr.end) if dr else None
        trend_days = 30
        if date_range:
            trend_days = min(120, max(7, (date_range.end - date_range.start).days + 1))
        trend = AnalyticsQueryService.trend(
            "total_pure_sale",
            days=trend_days,
            start=date_range.start if date_range else None,
            end=date_range.end if date_range else None,
        )
        if PeriodComparisonService.uses_latest_snapshot(preset):
            top_products = cls.products_from_snapshot(limit=8, full_period=True)
            top_product_reversions = cls.products_from_snapshot(
                limit=5, rank_by="sale_reversion_amount", full_period=True
            )
            product_groups = cls.product_groups_from_snapshot(limit=6, full_period=True)
        else:
            top_products = AnalyticsQueryService.product_ranking(
                dr=date_range, limit=8, preset=preset
            )
            top_product_reversions = AnalyticsQueryService.product_ranking(
                dr=date_range, limit=5, rank_by="sale_reversion_amount", preset=preset
            )
            product_groups = AnalyticsQueryService.product_group_ranking(
                dr=date_range, limit=6, preset=preset
            )
        return {
            "company_kpis": kpis,
            "profitability": cls.profitability_status(),
            "feature_flags": FEATURE_FLAGS,
            "connection": conn,
            "alerts": alerts,
            "visitor_ranking": visitor_rank,
            "head_visitor_ranking": head_rank,
            "geo_summary": cls.geo_summary(limit=5, preset=preset, dr=date_range),
            "trend": trend,
            "monthly_sales": monthly_sales,
            "comparisons": comparisons,
            "company_pnl": company_pnl,
            "receivables": AnalyticsQueryService.receivables_summary(),
            "top_products": top_products,
            "top_product_reversions": top_product_reversions,
            "top_product_profits": cls.product_profit_ranking(limit=5),
            "group_benefits": cls.group_benefit_ranking(limit=5),
            "monthly_group_benefit": cls.monthly_group_benefit(),
            "product_groups": product_groups,
            "insights": InsightsService.for_dashboard(preset=preset),
            "has_history": AnalyticsQueryService.has_history(),
            "preset": preset,
            "refresh_interval": conn["interval_minutes"],
            "latest_log": DashboardRefreshLog.latest(),
        }

    @classmethod
    def visitor_ranking(
        cls, *, limit: int = 50, rank_by: str = "TotalSale", user=None, preset: str = DEFAULT_PERIOD_PRESET
    ) -> list[dict]:
        preset = preset or DEFAULT_PERIOD_PRESET
        # «کل داده‌ها» from full/YTD snapshot rows — avoids summing mixed daily dumps.
        if PeriodComparisonService.uses_latest_snapshot(preset):
            snapshot = cls.get_full_period_snapshot(PRIMARY_KPI_REPORT) or cls.get_latest_snapshot(
                PRIMARY_KPI_REPORT
            )
            if not snapshot:
                return []
            rows = flatten_rows(snapshot.raw_data)
            ranked = ReportParser.ranking_table(rows, rank_by=rank_by, limit=limit)
            for item in ranked:
                item["rank_label"] = "برترین از نظر فروش"
            return AccessControlService.filter_ranking_rows(user, ranked)

        if AnalyticsQueryService.has_history():
            dr, _ = PeriodComparisonService.comparison_range(preset)
            if dr:
                return AnalyticsQueryService.salesperson_ranking(
                    dr=DateRange(dr.start, dr.end), limit=limit, user=user, preset=preset
                )
        snapshot = cls.get_latest_snapshot(PRIMARY_KPI_REPORT)
        if not snapshot:
            return []
        rows = flatten_rows(snapshot.raw_data)
        ranked = ReportParser.ranking_table(rows, rank_by=rank_by, limit=limit)
        for item in ranked:
            item["rank_label"] = "برترین از نظر فروش"
        return AccessControlService.filter_ranking_rows(user, ranked)

    @classmethod
    def head_visitor_ranking(
        cls, *, limit: int = 50, preset: str = DEFAULT_PERIOD_PRESET, user=None
    ) -> list[dict]:
        preset = preset or DEFAULT_PERIOD_PRESET
        if PeriodComparisonService.uses_latest_snapshot(preset):
            snapshot = cls.get_full_period_snapshot("head_visitor_sale") or cls.get_latest_snapshot(
                "head_visitor_sale"
            )
            if not snapshot:
                return []
            rows = flatten_rows(snapshot.raw_data)
            ranked = ReportParser.get_top_performers(
                rows,
                name_key="VisitorName",
                code_key="VisitorCode",
                limit=limit,
            )
            return AccessControlService.filter_ranking_rows(user, ranked)

        if AnalyticsQueryService.has_history():
            dr, _ = PeriodComparisonService.comparison_range(preset)
            if dr:
                return AccessControlService.filter_ranking_rows(
                    user,
                    AnalyticsQueryService.supervisor_ranking(
                        dr=DateRange(dr.start, dr.end), limit=limit, preset=preset
                    ),
                )
        snapshot = cls.get_latest_snapshot("head_visitor_sale")
        if not snapshot:
            return []
        rows = flatten_rows(snapshot.raw_data)
        ranked = ReportParser.get_top_performers(
            rows,
            name_key="VisitorName",
            code_key="VisitorCode",
            limit=limit,
        )
        return AccessControlService.filter_ranking_rows(user, ranked)

    @classmethod
    def connection_status(cls) -> dict[str, Any]:
        conn = KaraConnection.get_active()
        interval = getattr(settings, "AUTO_REFRESH_INTERVAL_MINUTES", 5)
        latest_job = KaraSyncJob.objects.order_by("-started_at").first()
        latest_snapshot = (
            KaraReportSnapshot.objects.filter(personnel_code="")
            .order_by("-fetched_at")
            .first()
        )
        last_sync = (
            conn.last_successful_sync_at
            if conn and conn.last_successful_sync_at
            else (latest_snapshot.fetched_at if latest_snapshot else None)
        )

        status = conn.connection_status if conn else ConnectionStatus.UNKNOWN
        if last_sync:
            age_min = (timezone.now() - last_sync).total_seconds() / 60
            if age_min > interval * 3 and status == ConnectionStatus.CONNECTED:
                status = ConnectionStatus.STALE

        return {
            "status": status,
            "status_label": CONNECTION_STATUS_LABELS.get(
                ConnectionStatus(status) if status in ConnectionStatus._value2member_map_ else ConnectionStatus.UNKNOWN,
                "نامشخص",
            ),
            "last_sync_at": last_sync.isoformat() if last_sync else None,
            "last_sync_label": _ago_label(last_sync),
            "last_login_at": conn.last_login_at.isoformat() if conn and conn.last_login_at else None,
            "last_login_at_display": (
                format_jalali_datetime(conn.last_login_at)
                if conn and conn.last_login_at
                else None
            ),
            "last_error": conn.last_error_message if conn else "",
            "interval_minutes": interval,
            "schedule_mode": "per_report",
            "schedule_mode_label": "زمان‌بندی جداگانه هر گزارش",
            "stagger_seconds": int(getattr(settings, "AUTO_REFRESH_STAGGER_SECONDS", 50)),
            "auto_refresh_enabled": getattr(settings, "AUTO_REFRESH_ENABLED", True),
            "latest_job": {
                "report_key": latest_job.report_key,
                "report_title": report_title(latest_job.report_key),
                "status": latest_job.status,
                "status_label": sync_status_label(latest_job.status),
                "friendly_error": latest_job.friendly_error,
            }
            if latest_job
            else None,
        }

    @classmethod
    def open_alerts(cls, limit: int = 20) -> list[ManagementAlert]:
        # One row per rule_key (keep newest) so duplicate period keys don't spam the UI.
        seen: set[str] = set()
        result: list[ManagementAlert] = []
        for alert in ManagementAlert.objects.filter(status=AlertStatus.OPEN).order_by(
            "-detected_at"
        ):
            key = f"{alert.rule_key}:{alert.entity_type}:{alert.entity_code}"
            if key in seen:
                continue
            seen.add(key)
            result.append(alert)
            if len(result) >= limit:
                break
        return result

    @classmethod
    def evaluate_alerts(cls) -> list[ManagementAlert]:
        return AlertEngine.evaluate_all()

    @staticmethod
    def _ensure_alert(**kwargs) -> ManagementAlert:
        title = kwargs["title"]
        entity = kwargs.get("entity", "")
        existing = ManagementAlert.objects.filter(
            title=title, entity=entity, status=AlertStatus.OPEN
        ).first()
        if existing:
            return existing
        return ManagementAlert.objects.create(**kwargs)
