"""Read-only queries against analytics layer (not raw snapshots)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Max, Sum
from django.utils import timezone

from reports.constants import DEFAULT_PERIOD_PRESET, MONTHLY_SALE_REPORT
from reports.models import (
    CompanyProfitLossMetric,
    DailyBusinessMetric,
    KaraReportSnapshot,
    MonthlyCompanySales,
    ProductDailyMetric,
    ProfitDailyMetric,
    ReceivableDailyMetric,
    RegionDailyMetric,
    SalespersonDailyMetric,
    SupervisorDailyMetric,
)
from reports.services.access_control import AccessControlService
from reports.services.currency import currency_label, display_float, format_money_number
from reports.services.dates import DateRange, gregorian_to_jalali
from reports.services.display import aging_bucket_label, report_title
from reports.services.monthly_sales import (
    extract_monthly_amounts,
    monthly_series_from_amounts,
    monthly_total,
)
from reports.services.parsers import format_number
from reports.services.period_comparison import PeriodComparisonService


class AnalyticsQueryService:
    @classmethod
    def latest_company_metric(cls) -> DailyBusinessMetric | None:
        return DailyBusinessMetric.objects.order_by("-business_date", "-id").first()

    @classmethod
    def _default_range(cls) -> DateRange:
        return PeriodComparisonService.full_data_range() or DateRange(
            timezone.localdate(), timezone.localdate()
        )

    @classmethod
    def _deduped_company_rows(cls, dr: DateRange) -> list[DailyBusinessMetric]:
        """One DailyBusinessMetric per business_date (latest id wins)."""
        qs = DailyBusinessMetric.objects.filter(
            business_date__gte=dr.start,
            business_date__lte=dr.end,
        )
        latest_ids = (
            qs.values("business_date")
            .annotate(mid=Max("id"))
            .values_list("mid", flat=True)
        )
        return list(
            DailyBusinessMetric.objects.filter(id__in=latest_ids)
            .select_related("snapshot")
            .order_by("business_date")
        )

    @classmethod
    def _full_period_sale_reference(cls) -> Decimal | None:
        """
        Best-known YTD/full sale from multi-day visitor snapshots.

        Used to detect orphan daily rows that are actually full-period dumps
        (no snapshot FK / missing period meta).
        """
        from reports.services.dates import parse_business_date
        from reports.services.parsers import parse_decimal, parse_int

        best = Decimal("0")
        qs = KaraReportSnapshot.objects.filter(
            report_key="visitor_sale",
            personnel_code="",
        ).order_by("-fetched_at")[:40]
        for snap in qs:
            sale = parse_decimal((snap.sum_row_data or {}).get("TotalSale")) or Decimal("0")
            if sale <= 0:
                continue
            pf = parse_business_date(snap.period_from)
            pt = parse_business_date(snap.period_to)
            active = parse_int(
                (snap.sum_row_data or {}).get("ActiveDayCountBasedOnFinalOrder")
            ) or 0
            if (pf and pt and (pt - pf).days > 0) or active > 1:
                if sale > best:
                    best = sale
        return best if best > 0 else None

    @classmethod
    def _is_period_dump(
        cls,
        metric: DailyBusinessMetric,
        *,
        full_sale_ref: Decimal | None = None,
    ) -> bool:
        """True when the row is a multi-day Kara dump stamped onto one business_date."""
        from reports.services.dates import parse_business_date
        from reports.services.parsers import parse_int

        sale = Decimal(metric.total_sale or 0)
        snap = getattr(metric, "snapshot", None)
        if snap is not None:
            pf = parse_business_date(snap.period_from)
            pt = parse_business_date(snap.period_to)
            if pf and pt and (pt - pf).days > 0:
                return True
            active = parse_int(
                (snap.sum_row_data or {}).get("ActiveDayCountBasedOnFinalOrder")
            ) or 0
            if active > 1:
                return True

        # Orphan / poorly linked dumps: nearly equal to known full-period total.
        ref = full_sale_ref if full_sale_ref is not None else cls._full_period_sale_reference()
        if ref and sale > 0 and sale >= (ref * Decimal("0.80")):
            return True
        return False

    @classmethod
    def _should_use_latest_only(cls, rows: list[DailyBusinessMetric], *, preset: str = "") -> bool:
        # Only "کل داده‌ها" reads a single full snapshot — never for today/7d/etc.
        return PeriodComparisonService.uses_latest_snapshot(preset)

    @classmethod
    def _usable_business_dates(cls, dr: DateRange, *, preset: str = "") -> list[date]:
        rows = cls._deduped_company_rows(dr)
        if not rows:
            return []

        ref = cls._full_period_sale_reference()

        if PeriodComparisonService.uses_latest_snapshot(preset):
            dumps = [r for r in rows if cls._is_period_dump(r, full_sale_ref=ref)]
            if dumps:
                return [dumps[-1].business_date]
            if ref:
                oversized = [
                    r
                    for r in rows
                    if Decimal(r.total_sale or 0) >= (ref * Decimal("0.80"))
                ]
                if oversized:
                    return [oversized[-1].business_date]
            return [rows[-1].business_date]

        # Period filters: sum true daily rows only — never mix in YTD dumps.
        usable: list[date] = []
        for r in rows:
            if cls._is_period_dump(r, full_sale_ref=ref):
                continue
            usable.append(r.business_date)
        return usable

    @classmethod
    def _reversion_rate(cls, total_sale: Decimal, sale_rev: Decimal, dist_rev: Decimal) -> Decimal:
        rev = abs(sale_rev) + abs(dist_rev)
        base = abs(total_sale) + rev
        if base <= 0:
            return Decimal("0")
        return (rev / base * 100).quantize(Decimal("0.1"))

    @classmethod
    def company_kpis_for_range(cls, dr: DateRange, *, preset: str = "") -> dict[str, Any]:
        rows = cls._deduped_company_rows(dr)
        if not rows:
            return {}

        usable_dates = set(cls._usable_business_dates(dr, preset=preset))
        if not usable_dates:
            return {}

        use_latest = cls._should_use_latest_only(rows, preset=preset)
        if use_latest:
            metric = next(
                (r for r in reversed(rows) if r.business_date in usable_dates),
                rows[-1],
            )
            total_sale = Decimal(metric.total_sale or 0)
            total_pure = Decimal(metric.total_pure_sale or 0)
            order_count = int(metric.order_count or 0)
            dist = Decimal(metric.distribution_reversion or 0)
            sale_rev = Decimal(metric.sale_reversion or 0)
            settlement = metric.settlement_remainder or Decimal("0")
            active_visitors = (
                SalespersonDailyMetric.objects.filter(
                    business_date=metric.business_date,
                    is_active=True,
                )
                .values("personnel_code")
                .distinct()
                .count()
            )
        else:
            usable = [r for r in rows if r.business_date in usable_dates]
            if not usable:
                return {}
            total_sale = sum((Decimal(r.total_sale or 0) for r in usable), Decimal("0"))
            total_pure = sum((Decimal(r.total_pure_sale or 0) for r in usable), Decimal("0"))
            order_count = sum(int(r.order_count or 0) for r in usable)
            dist = sum((Decimal(r.distribution_reversion or 0) for r in usable), Decimal("0"))
            sale_rev = sum((Decimal(r.sale_reversion or 0) for r in usable), Decimal("0"))
            settlement = usable[-1].settlement_remainder if usable else Decimal("0")
            active_visitors = (
                SalespersonDailyMetric.objects.filter(
                    business_date__in=list(usable_dates),
                    is_active=True,
                )
                .values("personnel_code")
                .distinct()
                .count()
            )

        avg_order = (total_sale / order_count) if order_count > 0 else Decimal("0")
        rev_rate = cls._reversion_rate(total_sale, sale_rev, dist)

        def kpi(key: str, label: str, val, *, money: bool = False, unit: str = "") -> dict:
            if money:
                formatted = format_money_number(val)
                unit = unit or currency_label()
                numeric = display_float(val)
            else:
                formatted = format_number(val) if isinstance(val, (Decimal, int, float)) else str(val)
                numeric = float(val) if val is not None else 0
            return {
                "label": label,
                "formatted": formatted,
                "numeric": numeric,
                "unit": unit,
            }

        money = currency_label()
        return {
            "total_sale": kpi("total_sale", "فروش نهایی", total_sale, money=True, unit=money),
            "total_pure_sale": kpi(
                "total_pure_sale", "فروش خالص", total_pure, money=True, unit=money
            ),
            "final_order_count": kpi("final_order_count", "سفارش نهایی", order_count),
            "avg_order_value": kpi(
                "avg_order_value",
                "میانگین سفارش",
                avg_order.quantize(Decimal("1")),
                money=True,
                unit=money,
            ),
            "distribution_reversion": kpi(
                "distribution_reversion", "برگشت از توزیع", dist, money=True, unit=money
            ),
            "sale_reversion": kpi("sale_reversion", "برگشت از فروش", sale_rev, money=True, unit=money),
            "reversion_rate": kpi("reversion_rate", "نرخ برگشت (٪)", rev_rate),
            "settlement_remainder": kpi(
                "settlement_remainder",
                "مانده تسویه",
                settlement or 0,
                money=True,
                unit=money,
            ),
            "active_visitors": kpi("active_visitors", "ویزیتور فعال", active_visitors),
        }

    @classmethod
    def _ranking_anchor_date(cls, dr: DateRange, *, preset: str = "") -> date | None:
        """When using latest-snapshot mode, rank on a single business_date."""
        if not PeriodComparisonService.uses_latest_snapshot(preset):
            return None
        dates = cls._usable_business_dates(dr, preset=preset)
        return dates[-1] if dates else None

    @classmethod
    def salesperson_ranking(
        cls,
        *,
        dr: DateRange | None = None,
        limit: int = 50,
        user=None,
        preset: str = "",
    ) -> list[dict]:
        dr = dr or cls._default_range()
        anchor = cls._ranking_anchor_date(dr, preset=preset)
        if anchor is not None:
            qs = SalespersonDailyMetric.objects.filter(business_date=anchor)
        else:
            dates = cls._usable_business_dates(dr, preset=preset)
            if not dates:
                return []
            qs = SalespersonDailyMetric.objects.filter(business_date__in=dates)

        if user is not None:
            scope = AccessControlService.resolve_scope(user)
            if not scope.unrestricted and scope.personnel_code:
                qs = qs.filter(personnel_code=scope.personnel_code)
            elif not scope.unrestricted and scope.supervisor_code:
                qs = qs.filter(supervisor_code=scope.supervisor_code)

        rows = (
            qs.values("personnel_code", "personnel_name", "supervisor_name")
            .annotate(
                total_sale=Sum("total_sale"),
                final_order_count=Sum("final_order_count"),
                sale_reversion=Sum("sale_reversion"),
                distribution_reversion=Sum("distribution_reversion"),
            )
            .order_by("-total_sale")[:limit]
        )
        result = []
        for i, row in enumerate(rows, 1):
            total = Decimal(row["total_sale"] or 0)
            sale_rev = Decimal(row["sale_reversion"] or 0)
            dist_rev = Decimal(row["distribution_reversion"] or 0)
            rev_rate = float(cls._reversion_rate(total, sale_rev, dist_rev))
            result.append(
                {
                    "rank": i,
                    "code": row["personnel_code"],
                    "name": row["personnel_name"],
                    "head_visitor": row["supervisor_name"],
                    "total_sale": float(total),
                    "total_sale_formatted": format_money_number(total),
                    "order_count": int(row["final_order_count"] or 0),
                    "reversion_rate": round(rev_rate, 1),
                    "rank_label": "برترین از نظر فروش",
                }
            )
        return result

    @classmethod
    def supervisor_ranking(
        cls, *, dr: DateRange | None = None, limit: int = 50, preset: str = ""
    ) -> list[dict]:
        dr = dr or cls._default_range()
        anchor = cls._ranking_anchor_date(dr, preset=preset)
        if anchor is not None:
            qs = SupervisorDailyMetric.objects.filter(business_date=anchor)
        else:
            dates = cls._usable_business_dates(dr, preset=preset)
            if not dates:
                return []
            qs = SupervisorDailyMetric.objects.filter(business_date__in=dates)

        rows = (
            qs.values("supervisor_code", "supervisor_name")
            .annotate(
                total_sale=Sum("total_sale"),
                final_order_count=Sum("final_order_count"),
            )
            .order_by("-total_sale")[:limit]
        )
        return [
            {
                "rank": i,
                "code": r["supervisor_code"],
                "name": r["supervisor_name"],
                "total_sale": float(r["total_sale"] or 0),
                "total_sale_formatted": format_money_number(r["total_sale"]),
                "order_count": int(r["final_order_count"] or 0),
                "rank_label": "برترین از نظر فروش",
            }
            for i, r in enumerate(rows, 1)
        ]

    @classmethod
    def region_ranking(
        cls,
        dimension_type: str,
        *,
        dr: DateRange | None = None,
        limit: int = 10,
        rank_by: str = "pure_sale",
        preset: str = "",
    ) -> list[dict]:
        dr = dr or cls._default_range()
        order_field = {
            "pure_sale": "pure_sale",
            "total_sale": "total_sale",
            "reversion_amount": "reversion_amount",
        }.get(rank_by, "pure_sale")
        qs = RegionDailyMetric.objects.filter(
            dimension_type=dimension_type,
            business_date__gte=dr.start,
            business_date__lte=dr.end,
        )
        anchor = cls._ranking_anchor_date(dr, preset=preset)
        if anchor is not None:
            qs = RegionDailyMetric.objects.filter(
                dimension_type=dimension_type,
                business_date=anchor,
            )
        elif not PeriodComparisonService.uses_latest_snapshot(preset):
            dates = cls._usable_business_dates(dr, preset=preset)
            if not dates:
                return []
            qs = RegionDailyMetric.objects.filter(
                dimension_type=dimension_type,
                business_date__in=dates,
            )
        rows = list(
            qs.values("dimension_code", "dimension_name")
            .annotate(
                pure_sale=Sum("pure_sale"),
                total_sale=Sum("total_sale"),
                order_count=Sum("order_count"),
                reversion_amount=Sum("reversion_amount"),
            )
            .order_by(f"-{order_field}")[: limit * 3]
        )
        # Keep only meaningful positive ranks for the chosen metric
        filtered = []
        for r in rows:
            metric_val = Decimal(r.get(order_field) or 0)
            if metric_val <= 0:
                continue
            filtered.append(r)
            if len(filtered) >= limit:
                break
        if (
            not filtered
            and rank_by == "pure_sale"
            and not PeriodComparisonService.uses_latest_snapshot(preset)
        ):
            # Period modes only: never pull an unrelated day into «کل داده‌ها».
            filtered = cls._region_ranking_latest_day(dimension_type, limit=limit)

        total_pure = sum(Decimal(r["pure_sale"] or 0) for r in filtered) or Decimal("1")
        total_rev = sum(Decimal(r["reversion_amount"] or 0) for r in filtered) or Decimal("1")
        share_base = total_rev if order_field == "reversion_amount" else total_pure
        return [
            {
                "name": r["dimension_name"] or r["dimension_code"],
                "code": r["dimension_code"],
                "pure_sale": float(r["pure_sale"] or 0),
                "reversion_amount": float(r["reversion_amount"] or 0),
                "value": display_float(
                    r["reversion_amount"] if order_field == "reversion_amount" else r["pure_sale"]
                ),
                "formatted": format_money_number(
                    r["reversion_amount"] if order_field == "reversion_amount" else r["pure_sale"]
                ),
                "share_percent": float(
                    Decimal(
                        r["reversion_amount"]
                        if order_field == "reversion_amount"
                        else r["pure_sale"]
                        or 0
                    )
                    / share_base
                    * 100
                ),
                "order_count": int(r["order_count"] or 0),
            }
            for r in filtered
        ]

    @classmethod
    def _region_ranking_latest_day(cls, dimension_type: str, *, limit: int) -> list[dict]:
        latest = (
            RegionDailyMetric.objects.filter(dimension_type=dimension_type)
            .order_by("-business_date")
            .values_list("business_date", flat=True)
            .first()
        )
        if not latest:
            return []
        return list(
            RegionDailyMetric.objects.filter(
                dimension_type=dimension_type, business_date=latest, pure_sale__gt=0
            )
            .values("dimension_code", "dimension_name")
            .annotate(
                pure_sale=Sum("pure_sale"),
                total_sale=Sum("total_sale"),
                order_count=Sum("order_count"),
                reversion_amount=Sum("reversion_amount"),
            )
            .order_by("-pure_sale")[:limit]
        )

    @classmethod
    def product_group_ranking(
        cls, *, dr: DateRange | None = None, limit: int = 10, preset: str = ""
    ) -> list[dict]:
        return cls.region_ranking(
            RegionDailyMetric.DIMENSION_PRODUCT_GROUP,
            dr=dr,
            limit=limit,
            rank_by="pure_sale",
            preset=preset,
        )

    @classmethod
    def product_group_reversion_ranking(
        cls, *, dr: DateRange | None = None, limit: int = 10, preset: str = ""
    ) -> list[dict]:
        return cls.region_ranking(
            RegionDailyMetric.DIMENSION_PRODUCT_GROUP,
            dr=dr,
            limit=limit,
            rank_by="reversion_amount",
            preset=preset,
        )

    @classmethod
    def profit_kpis_for_range(
        cls, dr: DateRange | None = None, *, preset: str = ""
    ) -> dict[str, Any]:
        dr = dr or cls._default_range()
        qs = ProfitDailyMetric.objects.filter(
            business_date__gte=dr.start,
            business_date__lte=dr.end,
        )
        anchor = cls._ranking_anchor_date(dr, preset=preset)
        if anchor is not None:
            qs = ProfitDailyMetric.objects.filter(business_date=anchor)
        elif not PeriodComparisonService.uses_latest_snapshot(preset):
            dates = cls._usable_business_dates(dr, preset=preset)
            if not dates:
                return {}
            qs = ProfitDailyMetric.objects.filter(business_date__in=dates)
        agg = qs.aggregate(
            invoice_revenue=Sum("invoice_revenue"),
            finalized_cost=Sum("finalized_cost"),
            sale_reversion_amount=Sum("sale_reversion_amount"),
            gross_profit=Sum("gross_profit"),
            invoice_count=Sum("invoice_count"),
        )
        revenue = Decimal(agg["invoice_revenue"] or 0)
        cost = Decimal(agg["finalized_cost"] or 0)
        gross = Decimal(agg["gross_profit"] or 0)
        if gross == 0 and revenue > 0:
            gross = revenue - cost - Decimal(agg["sale_reversion_amount"] or 0)
        margin = (gross / revenue * 100) if revenue > 0 else Decimal("0")
        # Guard absurd margins from incomplete COGS on invoices.
        if margin > Decimal("100") or margin < Decimal("-50"):
            margin = Decimal("0") if revenue <= 0 else min(margin, Decimal("100"))
            if gross > revenue > 0:
                # COGS missing/too low — don't claim near-100% margin.
                margin = ((revenue - cost) / revenue * 100).quantize(Decimal("0.1"))
                if cost <= 0:
                    margin = Decimal("0")

        def kpi(label: str, val, *, money: bool = False, unit: str = "") -> dict:
            if money:
                return {
                    "label": label,
                    "formatted": format_money_number(val),
                    "numeric": display_float(val),
                    "unit": unit or currency_label(),
                }
            return {
                "label": label,
                "formatted": format_number(val),
                "numeric": float(val),
                "unit": unit,
            }

        if revenue <= 0 and cost <= 0:
            return {}

        result = {
            "gross_profit": kpi("سود ناخالص (فاکتور)", gross, money=True),
            "finalized_cost": kpi("بهای تمام‌شده فاکتور", cost, money=True),
            "invoice_revenue": kpi("فروش فاکتور", revenue, money=True),
            "invoice_count": kpi("تعداد فاکتور", int(agg["invoice_count"] or 0)),
        }
        # Only show margin when COGS looks complete (not near-zero vs revenue).
        if revenue > 0 and cost > 0:
            cost_share = cost / revenue
            if (
                Decimal("0.05") <= cost_share <= Decimal("1.5")
                and Decimal("0") <= margin <= Decimal("95")
            ):
                result["gross_margin_rate"] = kpi(
                    "حاشیه سود ناخالص",
                    margin.quantize(Decimal("0.1")),
                    unit="٪",
                )
        return result

    @classmethod
    def product_ranking(
        cls,
        *,
        dr: DateRange | None = None,
        limit: int = 10,
        rank_by: str = "pure_sale",
        preset: str = "",
    ) -> list[dict]:
        dr = dr or cls._default_range()
        field_map = {
            "pure_sale": "pure_sale",
            "sale_amount": "sale_amount",
            "sale_quantity": "sale_quantity",
            "sale_reversion_amount": "sale_reversion_amount",
        }
        order_field = field_map.get(rank_by, "pure_sale")
        qs = ProductDailyMetric.objects.filter(
            business_date__gte=dr.start,
            business_date__lte=dr.end,
        )
        anchor = cls._ranking_anchor_date(dr, preset=preset)
        if anchor is not None:
            qs = ProductDailyMetric.objects.filter(business_date=anchor)
        elif not PeriodComparisonService.uses_latest_snapshot(preset):
            dates = cls._usable_business_dates(dr, preset=preset)
            if not dates:
                return []
            qs = ProductDailyMetric.objects.filter(business_date__in=dates)
        qs = (
            qs.values("stuff_code", "stuff_name", "stuff_group_name")
            .annotate(
                pure_sale=Sum("pure_sale"),
                sale_amount=Sum("sale_amount"),
                sale_quantity=Sum("sale_quantity"),
                sale_reversion_amount=Sum("sale_reversion_amount"),
            )
            .order_by(f"-{order_field}")
        )
        rows = []
        for r in qs[: limit * 5]:
            metric = Decimal(r.get(order_field) or 0)
            # Bestsellers: only positive net/gross sales. Returns: only positive reversion.
            if metric <= 0:
                continue
            if order_field == "pure_sale" and Decimal(r.get("pure_sale") or 0) <= 0:
                continue
            rows.append(r)
            if len(rows) >= limit:
                break

        if not rows and order_field == "pure_sale":
            rows = cls._product_ranking_latest_day(limit=limit)

        return [
            {
                "rank": i,
                "code": r["stuff_code"],
                "name": r["stuff_name"] or r["stuff_code"],
                "group": r["stuff_group_name"] or "—",
                "pure_sale": float(max(Decimal(r["pure_sale"] or 0), Decimal("0"))),
                "value": display_float(max(Decimal(r["pure_sale"] or 0), Decimal("0"))),
                "pure_sale_formatted": format_money_number(
                    max(Decimal(r["pure_sale"] or 0), Decimal("0"))
                ),
                "sale_amount": float(r["sale_amount"] or 0),
                "sale_amount_formatted": format_money_number(r["sale_amount"]),
                "sale_quantity": int(r["sale_quantity"] or 0),
                "sale_reversion_amount": float(
                    abs(Decimal(r["sale_reversion_amount"] or 0))
                ),
                "sale_reversion_formatted": format_money_number(
                    abs(Decimal(r["sale_reversion_amount"] or 0))
                ),
            }
            for i, r in enumerate(rows, 1)
        ]

    @classmethod
    def _product_ranking_latest_day(cls, *, limit: int) -> list[dict]:
        latest = (
            ProductDailyMetric.objects.filter(pure_sale__gt=0)
            .order_by("-business_date")
            .values_list("business_date", flat=True)
            .first()
        )
        if not latest:
            return []
        return list(
            ProductDailyMetric.objects.filter(business_date=latest, pure_sale__gt=0)
            .values("stuff_code", "stuff_name", "stuff_group_name")
            .annotate(
                pure_sale=Sum("pure_sale"),
                sale_amount=Sum("sale_amount"),
                sale_quantity=Sum("sale_quantity"),
                sale_reversion_amount=Sum("sale_reversion_amount"),
            )
            .order_by("-pure_sale")[:limit]
        )

    @classmethod
    def has_profit_history(cls) -> bool:
        return ProfitDailyMetric.objects.filter(finalized_cost__gt=0).exists()

    @classmethod
    def has_product_history(cls) -> bool:
        return ProductDailyMetric.objects.exists()

    @classmethod
    def has_monthly_sales(cls) -> bool:
        return MonthlyCompanySales.objects.exists()

    @classmethod
    def monthly_sales_series(cls, fiscal_year: int | None = None) -> dict[str, Any]:
        qs = MonthlyCompanySales.objects.all()
        if fiscal_year:
            record = qs.filter(fiscal_year=fiscal_year).first()
        else:
            record = qs.order_by("-fiscal_year").first()

        if record:
            amounts = {
                key: Decimal(value or 0)
                for key, value in (record.monthly_totals or {}).items()
            }
            return {
                "available": True,
                "fiscal_year": record.fiscal_year,
                "series": monthly_series_from_amounts(amounts),
                "total": display_float(record.total_ytd),
                "total_formatted": format_money_number(record.total_ytd),
            }

        snap = (
            KaraReportSnapshot.objects.filter(
                report_key=MONTHLY_SALE_REPORT, personnel_code=""
            )
            .order_by("-fetched_at")
            .first()
        )
        if snap and snap.sum_row_data:
            amounts = extract_monthly_amounts(snap.sum_row_data)
            from reports.services.monthly_sales import jalali_fiscal_year

            fy = jalali_fiscal_year(snap.fetched_at)
            total = monthly_total(amounts)
            return {
                "available": True,
                "fiscal_year": fy,
                "series": monthly_series_from_amounts(amounts),
                "total": display_float(total),
                "total_formatted": format_money_number(total),
            }

        return {
            "available": False,
            "fiscal_year": fiscal_year,
            "series": [],
            "total": 0,
            "total_formatted": "0",
        }

    @classmethod
    def trend(
        cls,
        field: str,
        days: int = 30,
        *,
        start=None,
        end=None,
    ) -> list[dict]:
        return PeriodComparisonService.trend_series(
            field, days=days, start=start, end=end
        )

    @classmethod
    def has_history(cls) -> bool:
        return DailyBusinessMetric.objects.count() >= 2

    @classmethod
    def has_company_pnl(cls) -> bool:
        return (
            CompanyProfitLossMetric.objects.filter(net_profit__gt=0).exists()
            or CompanyProfitLossMetric.objects.filter(operating_profit__gt=0).exists()
        )

    @classmethod
    def company_pnl_kpis(cls) -> dict[str, Any]:
        metric = CompanyProfitLossMetric.objects.order_by("-business_date").first()
        if not metric:
            return {}

        def kpi(label: str, val, *, money: bool = True, unit: str = "") -> dict:
            if money:
                return {
                    "label": label,
                    "formatted": format_money_number(val),
                    "numeric": display_float(val),
                    "unit": unit or currency_label(),
                }
            return {
                "label": label,
                "formatted": format_number(val),
                "numeric": float(val),
                "unit": unit,
            }

        op_margin = (
            (metric.operating_profit / metric.net_pure_sale * 100).quantize(Decimal("0.01"))
            if metric.net_pure_sale and metric.net_pure_sale > 0
            else Decimal("0")
        )
        gross_margin = Decimal(metric.gross_margin_rate or 0)
        # Suppress absurd accounting margins (e.g. negative COGS from ending inventory).
        sane_op = Decimal("0") <= op_margin <= Decimal("100")
        sane_gross = Decimal("0") <= gross_margin <= Decimal("100")

        result = {
            "pnl_net_pure_sale": kpi("فروش خالص (سود و زیان)", metric.net_pure_sale),
            "pnl_cogs": kpi("بهای تمام‌شده", metric.cost_of_goods_sold),
            "pnl_gross_profit": kpi("سود ناخالص حسابداری", metric.gross_profit),
            "pnl_operating_profit": kpi("سود عملیاتی", metric.operating_profit),
            "pnl_net_profit": kpi("سود خالص", metric.net_profit),
            "source": "profit_and_loss",
            "source_label": report_title("profit_and_loss"),
            "business_date": metric.business_date.isoformat() if metric.business_date else None,
            "business_date_label": (
                gregorian_to_jalali(metric.business_date) if metric.business_date else None
            ),
            "period_from": metric.period_from,
            "period_to": metric.period_to,
        }
        if sane_gross:
            result["pnl_margin_rate"] = kpi(
                "حاشیه سود ناخالص حسابداری",
                gross_margin,
                money=False,
                unit="٪",
            )
        if sane_op:
            result["pnl_operating_margin_rate"] = kpi(
                "حاشیه سود عملیاتی",
                op_margin,
                money=False,
                unit="٪",
            )
        elif metric.net_pure_sale and metric.net_pure_sale > 0 and metric.net_profit:
            # Fallback: net margin is usually the honest rate when COGS sign is distorted.
            net_margin = (metric.net_profit / metric.net_pure_sale * 100).quantize(
                Decimal("0.01")
            )
            if Decimal("0") <= net_margin <= Decimal("100"):
                result["pnl_operating_margin_rate"] = kpi(
                    "حاشیه سود خالص حسابداری",
                    net_margin,
                    money=False,
                    unit="٪",
                )
        return result

    @classmethod
    def receivables_summary(cls) -> dict[str, Any]:
        metric = (
            ReceivableDailyMetric.objects.filter(total_outstanding__gt=0)
            .order_by("-business_date", "-calculated_at")
            .first()
            or ReceivableDailyMetric.objects.filter(partner_balance_total__gt=0)
            .order_by("-business_date", "-calculated_at")
            .first()
            or ReceivableDailyMetric.objects.order_by("-business_date").first()
        )
        if not metric:
            return {"available": False}

        buckets = []
        for key, raw in sorted((metric.bucket_totals or {}).items()):
            amount = Decimal(raw or 0)
            buckets.append(
                {
                    "key": key,
                    "label": aging_bucket_label(key),
                    "amount": float(amount),
                    "formatted": format_money_number(amount),
                }
            )
        return {
            "available": True,
            "business_date": metric.business_date.isoformat(),
            "business_date_label": gregorian_to_jalali(metric.business_date),
            "total_outstanding": float(metric.total_outstanding),
            "total_outstanding_formatted": format_money_number(metric.total_outstanding),
            "partner_balance_total": float(metric.partner_balance_total),
            "partner_balance_formatted": format_money_number(metric.partner_balance_total),
            "partner_count": metric.partner_count,
            "row_count": metric.row_count,
            "buckets": buckets,
            "unit": currency_label(),
        }
