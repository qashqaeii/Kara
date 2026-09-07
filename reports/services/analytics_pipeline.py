"""Build daily metrics from Kara snapshots — idempotent analytics pipeline."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from reports.constants import (
    ACCOUNT_BALANCE_REPORT,
    MONTHLY_SALE_REPORT,
    PRIMARY_KPI_REPORT,
    PRODUCT_REPORT,
    PROFIT_LOSS_REPORT,
    PROFIT_REPORT,
    RECEIVABLES_AGING_REPORT,
    AGING_BUCKET_KEYS,
    MONTH_BALANCE_KEYS,
    SyncStatus,
)
from reports.models import (
    AnalyticsPeriod,
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
from reports.services.monthly_sales import (
    extract_monthly_amounts,
    jalali_fiscal_year,
    monthly_total,
)
from reports.services.dates import gregorian_to_jalali, snapshot_business_date
from reports.services.parsers import flatten_rows, parse_decimal, parse_int
from reports.services.report_registry import ReportRegistry

logger = logging.getLogger(__name__)

CACHE_VERSION_KEY = "analytics_cache_version"


def _dec(value) -> Decimal:
    return parse_decimal(value) or Decimal("0")


def _int(value) -> int:
    return parse_int(value) or 0


def _reversion_rate(total_sale: Decimal, sale_rev: Decimal, dist_rev: Decimal) -> Decimal:
    """
    Return rate as share of gross-before-returns.

    TotalSale from Kara is typically net; dividing returns by net alone can exceed 100%.
    """
    rev = abs(sale_rev) + abs(dist_rev)
    base = abs(total_sale) + rev
    if base <= 0:
        return Decimal("0")
    return (rev / base * 100).quantize(Decimal("0.01"))


def _invalid_dimension_name(name: str) -> bool:
    return not name or name in ("---", "-", "بدون سرپرست")


# Canonical Persian city names — merge Latin/alias duplicates from Kara.
_CITY_ALIASES: dict[str, str] = {
    "tehran": "تهران",
    "teharn": "تهران",
    "طهران": "تهران",
    "تهران": "تهران",
}


def normalize_region_name(name: str, *, dimension_type: str = "") -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        return cleaned
    if dimension_type in ("city", RegionDailyMetric.DIMENSION_CITY):
        mapped = _CITY_ALIASES.get(cleaned.lower())
        if mapped:
            return mapped
    return cleaned


class AnalyticsPipeline:
    """Snapshot → normalized daily metrics."""

    REPORT_HANDLERS = (
        PRIMARY_KPI_REPORT,
        "head_visitor_sale",
        "stuff_group_sale",
        PROFIT_REPORT,
        PRODUCT_REPORT,
        MONTHLY_SALE_REPORT,
        ACCOUNT_BALANCE_REPORT,
        RECEIVABLES_AGING_REPORT,
        PROFIT_LOSS_REPORT,
    )

    @classmethod
    def process_snapshot(cls, snapshot: KaraReportSnapshot) -> bool:
        if snapshot.personnel_code:
            return False
        try:
            with transaction.atomic():
                if snapshot.report_key == PRIMARY_KPI_REPORT:
                    cls._process_visitor_sale(snapshot)
                elif snapshot.report_key == "head_visitor_sale":
                    cls._process_head_visitor_sale(snapshot)
                elif snapshot.report_key == "stuff_group_sale":
                    cls._process_stuff_group_sale(snapshot)
                elif snapshot.report_key == PROFIT_REPORT:
                    cls._process_sale_orders(snapshot)
                elif snapshot.report_key == PRODUCT_REPORT:
                    cls._process_sale_stuffs(snapshot)
                elif snapshot.report_key == MONTHLY_SALE_REPORT:
                    cls._process_monthly_sale(snapshot)
                elif snapshot.report_key == ACCOUNT_BALANCE_REPORT:
                    cls._process_account_balance(snapshot)
                elif snapshot.report_key == RECEIVABLES_AGING_REPORT:
                    cls._process_receivables_aging(snapshot)
                elif snapshot.report_key == PROFIT_LOSS_REPORT:
                    cls._process_profit_and_loss(snapshot)
                else:
                    return False
                cls._mark_period(snapshot, SyncStatus.SUCCESS)
            cls.bump_cache()
            return True
        except Exception:
            logger.exception("Analytics pipeline failed for snapshot %s", snapshot.id)
            cls._mark_period(snapshot, SyncStatus.FAILED)
            return False

    @classmethod
    def rebuild(
        cls,
        *,
        report_key: str | None = None,
        from_date=None,
        to_date=None,
    ) -> dict[str, int]:
        """Rebuild metrics from stored snapshots."""
        qs = KaraReportSnapshot.objects.filter(personnel_code="").order_by(
            "report_key", "-fetched_at"
        )
        if report_key:
            qs = qs.filter(report_key=report_key)
        keys = [report_key] if report_key else list(cls.REPORT_HANDLERS)

        stats = {"processed": 0, "skipped": 0, "failed": 0}
        seen: set[tuple[str, str]] = set()

        for snap in qs.iterator():
            if snap.report_key not in keys:
                continue
            bdate = snapshot_business_date(
                period_to=snap.period_to,
                period_from=snap.period_from,
                fetched_at=snap.fetched_at,
            )
            if from_date and bdate < from_date:
                stats["skipped"] += 1
                continue
            if to_date and bdate > to_date:
                stats["skipped"] += 1
                continue
            dedupe_key = (snap.report_key, bdate.isoformat())
            if dedupe_key in seen:
                stats["skipped"] += 1
                continue
            seen.add(dedupe_key)
            if cls.process_snapshot(snap):
                stats["processed"] += 1
            else:
                stats["failed"] += 1

        from reports.services.alert_engine import AlertEngine

        AlertEngine.evaluate_all()
        cls.bump_cache()
        return stats

    @classmethod
    def bump_cache(cls) -> None:
        try:
            cache.incr(CACHE_VERSION_KEY)
        except ValueError:
            cache.set(CACHE_VERSION_KEY, 1, None)

    @classmethod
    def _mark_period(cls, snapshot: KaraReportSnapshot, status: str) -> None:
        bdate = snapshot_business_date(
            period_to=snapshot.period_to,
            period_from=snapshot.period_from,
            fetched_at=snapshot.fetched_at,
        )
        AnalyticsPeriod.objects.update_or_create(
            report_key=snapshot.report_key,
            business_date=bdate,
            defaults={"status": status, "snapshot": snapshot},
        )

    @classmethod
    def _process_visitor_sale(cls, snapshot: KaraReportSnapshot) -> None:
        from reports.services.parsers import ReportParser
        from reports.services.report_registry import get_report_config

        bdate = snapshot_business_date(
            period_to=snapshot.period_to,
            period_from=snapshot.period_from,
            fetched_at=snapshot.fetched_at,
        )
        sum_row = snapshot.sum_row_data or {}
        config = get_report_config(PRIMARY_KPI_REPORT)
        kpis = ReportParser.extract_kpis(sum_row, config)

        total_sale = _dec(kpis.get("total_sale", {}).get("raw"))
        total_pure = _dec(kpis.get("total_pure_sale", {}).get("raw"))
        order_count = _int(kpis.get("final_order_count", {}).get("raw"))
        dist_rev = _dec(kpis.get("distribution_reversion", {}).get("raw"))
        sale_rev = _dec(kpis.get("sale_reversion", {}).get("raw"))
        total_rev = dist_rev + sale_rev
        avg_order = (total_sale / order_count) if order_count > 0 else Decimal("0")

        rows = flatten_rows(snapshot.raw_data)
        active = sum(
            1
            for r in rows
            if _dec(r.get("TotalSale")) > 0 or _int(r.get("OrderCountBasedOnFinalOrder")) > 0
        )

        DailyBusinessMetric.objects.update_or_create(
            metric_date=gregorian_to_jalali(bdate),
            source_report=PRIMARY_KPI_REPORT,
            defaults={
                "business_date": bdate,
                "total_sale": total_sale,
                "total_pure_sale": total_pure,
                "order_count": order_count,
                "average_order_value": avg_order.quantize(Decimal("1")),
                "distribution_reversion": dist_rev,
                "sale_reversion": sale_rev,
                "total_reversion": total_rev,
                "reversion_rate": _reversion_rate(total_sale, sale_rev, dist_rev),
                "settlement_remainder": _dec(
                    kpis.get("settlement_remainder", {}).get("raw")
                ),
                "active_visitors": active,
                "snapshot": snapshot,
            },
        )

        for row in rows:
            code = (row.get("VisitorCode") or "").strip()
            if not code:
                continue
            row_sale = _dec(row.get("TotalSale"))
            row_orders = _int(row.get("OrderCountBasedOnFinalOrder"))
            row_dist = _dec(row.get("TotalDistributionReversion"))
            row_sale_rev = _dec(row.get("TotalSaleReversion"))
            SalespersonDailyMetric.objects.update_or_create(
                business_date=bdate,
                personnel_code=code,
                defaults={
                    "personnel_name": (row.get("VisitorName") or "").strip(),
                    "supervisor_code": (row.get("HeadVisitorCode") or "").strip(),
                    "supervisor_name": (row.get("HeadVisitorName") or "").strip(),
                    "total_sale": row_sale,
                    "total_pure_sale": _dec(row.get("TotalPureSale")),
                    "final_order_count": row_orders,
                    "preorder_count": _int(row.get("OrderCountBasedOnPreOrder")),
                    "average_order_value": (
                        (row_sale / row_orders) if row_orders > 0 else Decimal("0")
                    ).quantize(Decimal("1")),
                    "sale_reversion": row_sale_rev,
                    "distribution_reversion": row_dist,
                    "reversion_rate": _reversion_rate(row_sale, row_sale_rev, row_dist),
                    "is_active": row_sale > 0 or row_orders > 0,
                    "snapshot": snapshot,
                },
            )

    @classmethod
    def _process_head_visitor_sale(cls, snapshot: KaraReportSnapshot) -> None:
        bdate = snapshot_business_date(
            period_to=snapshot.period_to,
            period_from=snapshot.period_from,
            fetched_at=snapshot.fetched_at,
        )
        rows = flatten_rows(snapshot.raw_data)
        for row in rows:
            code = (row.get("VisitorCode") or "").strip()
            if not code:
                continue
            total_sale = _dec(row.get("TotalSale"))
            order_count = _int(row.get("OrderCountBasedOnFinalOrder"))
            dist_rev = _dec(row.get("TotalDistributionReversion"))
            sale_rev = _dec(row.get("TotalSaleReversion"))
            SupervisorDailyMetric.objects.update_or_create(
                business_date=bdate,
                supervisor_code=code,
                defaults={
                    "supervisor_name": (row.get("VisitorName") or "").strip(),
                    "total_sale": total_sale,
                    "total_pure_sale": _dec(row.get("TotalPureSale")),
                    "final_order_count": order_count,
                    "salesperson_count": _int(row.get("PartnerNumberBasedOnFinalOrder")),
                    "active_salesperson_count": 1 if total_sale > 0 else 0,
                    "average_sale_per_person": total_sale,
                    "reversion_rate": _reversion_rate(total_sale, sale_rev, dist_rev),
                    "snapshot": snapshot,
                },
            )

    @classmethod
    def _process_stuff_group_sale(cls, snapshot: KaraReportSnapshot) -> None:
        bdate = snapshot_business_date(
            period_to=snapshot.period_to,
            period_from=snapshot.period_from,
            fetched_at=snapshot.fetched_at,
        )
        rows = flatten_rows(snapshot.raw_data)

        # Rebuild regions for this day — never accumulate across re-syncs.
        RegionDailyMetric.objects.filter(business_date=bdate).delete()

        regions: dict[tuple[str, str], dict] = {}

        def add_region(dim_type: str, code: str, name: str, row: dict) -> None:
            if _invalid_dimension_name(name) or not code:
                return
            key = (dim_type, code)
            pure = _dec(row.get("PureSalePrice"))
            not_pure = _dec(row.get("NotPureSalePrice"))
            rev = _dec(row.get("DistributionReversionPrice")) + _dec(
                row.get("SaleReversionPrice")
            )
            bucket = regions.get(key)
            if not bucket:
                regions[key] = {
                    "dimension_type": dim_type,
                    "dimension_code": code,
                    "dimension_name": name,
                    "total_sale": not_pure,
                    "pure_sale": pure,
                    "order_count": _int(row.get("OrderCount")),
                    "reversion_amount": rev,
                }
                return
            bucket["dimension_name"] = name or bucket["dimension_name"]
            bucket["total_sale"] += not_pure
            bucket["pure_sale"] += pure
            bucket["order_count"] += _int(row.get("OrderCount"))
            bucket["reversion_amount"] += rev

        # Aggregate products in-memory — stuff_group rows are detail combinations.
        products: dict[str, dict] = {}
        for row in rows:
            city = normalize_region_name(
                (row.get("City") or "").strip(),
                dimension_type=RegionDailyMetric.DIMENSION_CITY,
            )
            zone = normalize_region_name((row.get("Zone") or "").strip())
            group = (row.get("StuffGroupName") or row.get("StuffGroupName1") or "").strip()
            if not _invalid_dimension_name(city):
                add_region(RegionDailyMetric.DIMENSION_CITY, city, city, row)
            if not _invalid_dimension_name(zone):
                add_region(RegionDailyMetric.DIMENSION_ZONE, zone, zone, row)
            if not _invalid_dimension_name(group):
                add_region(
                    RegionDailyMetric.DIMENSION_PRODUCT_GROUP, group, group, row
                )

            code = str(row.get("StuffCode") or "").strip()
            if not code:
                continue
            bucket = products.get(code)
            if not bucket:
                bucket = {
                    "stuff_name": (row.get("StuffName") or "").strip(),
                    "stuff_group_name": group,
                    "sale_quantity": 0,
                    "sale_amount": Decimal("0"),
                    "sale_reversion_quantity": 0,
                    "sale_reversion_amount": Decimal("0"),
                    "pure_sale": Decimal("0"),
                }
                products[code] = bucket
            if not bucket["stuff_name"]:
                bucket["stuff_name"] = (row.get("StuffName") or "").strip()
            if not bucket["stuff_group_name"] and group:
                bucket["stuff_group_name"] = group
            bucket["sale_quantity"] += _int(row.get("PureSaleQuantity") or row.get("NotPureSaleQuantity"))
            bucket["sale_amount"] += _dec(row.get("NotPureSalePrice"))
            bucket["sale_reversion_amount"] += abs(
                _dec(row.get("SaleReversionPrice"))
            ) + abs(_dec(row.get("DistributionReversionPrice")))
            bucket["sale_reversion_quantity"] += _int(
                row.get("SaleReversionQuantity")
            ) + _int(row.get("DistributionReversionQuantity"))
            bucket["pure_sale"] += _dec(row.get("PureSalePrice"))

        if regions:
            RegionDailyMetric.objects.bulk_create(
                [
                    RegionDailyMetric(
                        business_date=bdate,
                        snapshot=snapshot,
                        **data,
                    )
                    for data in regions.values()
                ],
                batch_size=200,
            )

        for code, data in products.items():
            ProductDailyMetric.objects.update_or_create(
                business_date=bdate,
                stuff_code=code,
                defaults={**data, "snapshot": snapshot},
            )

    @classmethod
    def _process_sale_orders(cls, snapshot: KaraReportSnapshot) -> None:
        from reports.services.parsers import ReportParser
        from reports.services.report_registry import get_report_config

        bdate = snapshot_business_date(
            period_to=snapshot.period_to,
            period_from=snapshot.period_from,
            fetched_at=snapshot.fetched_at,
        )
        sum_row = snapshot.sum_row_data or {}
        config = get_report_config(PROFIT_REPORT)
        kpis = ReportParser.extract_kpis(sum_row, config)

        revenue = _dec(kpis.get("invoice_revenue", {}).get("raw"))
        cost = _dec(kpis.get("finalized_cost", {}).get("raw"))
        sale_rev = _dec(kpis.get("sale_reversion", {}).get("raw"))
        gross_profit = revenue - cost - sale_rev
        margin = (
            (gross_profit / revenue * 100).quantize(Decimal("0.01"))
            if revenue > 0
            else Decimal("0")
        )
        rows = flatten_rows(snapshot.raw_data)

        ProfitDailyMetric.objects.update_or_create(
            business_date=bdate,
            defaults={
                "invoice_count": len(rows),
                "invoice_revenue": revenue,
                "finalized_cost": cost,
                "sale_reversion_amount": sale_rev,
                "gross_profit": gross_profit,
                "gross_margin_rate": margin,
                "snapshot": snapshot,
            },
        )

    @classmethod
    def _process_sale_stuffs(cls, snapshot: KaraReportSnapshot) -> None:
        """Merge sale_stuffs rows. Avoid wiping rich stuff_group sales with return-only rows."""
        bdate = snapshot_business_date(
            period_to=snapshot.period_to,
            period_from=snapshot.period_from,
            fetched_at=snapshot.fetched_at,
        )
        rows = flatten_rows(snapshot.raw_data)
        for row in rows:
            code = str(row.get("StuffCode") or "").strip()
            if not code:
                continue
            sale_amount = _dec(row.get("SaleSum") or row.get("SalePrice"))
            reversion = abs(_dec(row.get("SaleReversionSum") or row.get("SaleReversionPrice")))
            pure_sale = _dec(row.get("PureSale"))
            qty = _int(row.get("SaleStuffQuantity"))
            rev_qty = _int(row.get("SaleReversionStuffQuantity"))
            name = (row.get("StuffName") or "").strip()
            group = (row.get("StuffGroupName") or "").strip()

            existing = ProductDailyMetric.objects.filter(
                business_date=bdate, stuff_code=code
            ).first()
            # Return-only Kara rows (SaleSum=0, PureSale negative) must not overwrite
            # aggregated stuff_group sales for the same product/day.
            if existing and sale_amount <= 0 and existing.sale_amount > 0:
                ProductDailyMetric.objects.filter(pk=existing.pk).update(
                    sale_reversion_amount=max(existing.sale_reversion_amount, reversion),
                    sale_reversion_quantity=max(existing.sale_reversion_quantity, rev_qty),
                    snapshot=snapshot,
                )
                continue

            ProductDailyMetric.objects.update_or_create(
                business_date=bdate,
                stuff_code=code,
                defaults={
                    "stuff_name": name or (existing.stuff_name if existing else ""),
                    "stuff_group_name": group or (existing.stuff_group_name if existing else ""),
                    "sale_quantity": qty,
                    "sale_amount": sale_amount,
                    "sale_reversion_quantity": rev_qty,
                    "sale_reversion_amount": reversion,
                    "pure_sale": pure_sale,
                    "snapshot": snapshot,
                },
            )

    @classmethod
    def _process_monthly_sale(cls, snapshot: KaraReportSnapshot) -> None:
        sum_row = snapshot.sum_row_data or {}
        if not sum_row:
            return
        fiscal_year = jalali_fiscal_year(snapshot.fetched_at)
        amounts = extract_monthly_amounts(sum_row)
        MonthlyCompanySales.objects.update_or_create(
            fiscal_year=fiscal_year,
            defaults={
                "monthly_totals": {k: str(v) for k, v in amounts.items()},
                "total_ytd": monthly_total(amounts),
                "snapshot": snapshot,
            },
        )

    @classmethod
    def _process_account_balance(cls, snapshot: KaraReportSnapshot) -> None:
        bdate = snapshot_business_date(
            period_to=snapshot.period_to,
            period_from=snapshot.period_from,
            fetched_at=snapshot.fetched_at,
        )
        rows = flatten_rows(snapshot.raw_data)
        partner_total = Decimal("0")
        for row in rows:
            for key in MONTH_BALANCE_KEYS:
                partner_total += _dec(row.get(key))

        existing = ReceivableDailyMetric.objects.filter(business_date=bdate).first()
        ReceivableDailyMetric.objects.update_or_create(
            business_date=bdate,
            defaults={
                "partner_balance_total": partner_total,
                "partner_count": len(rows),
                "bucket_totals": (existing.bucket_totals if existing else {}),
                "total_outstanding": (
                    existing.total_outstanding if existing else Decimal("0")
                ),
                "row_count": existing.row_count if existing else 0,
                "snapshot": snapshot,
            },
        )

    @classmethod
    def _process_receivables_aging(cls, snapshot: KaraReportSnapshot) -> None:
        bdate = snapshot_business_date(
            period_to=snapshot.period_to,
            period_from=snapshot.period_from,
            fetched_at=snapshot.fetched_at,
        )
        rows = flatten_rows(snapshot.raw_data)
        bucket_totals = {key: Decimal("0") for key in AGING_BUCKET_KEYS}
        total = Decimal("0")
        for row in rows:
            for key in AGING_BUCKET_KEYS:
                amount = _dec(row.get(key))
                bucket_totals[key] += amount
                total += amount

        existing = ReceivableDailyMetric.objects.filter(business_date=bdate).first()
        # Partial/empty aging syncs must not wipe a richer metric for the same day.
        if existing and _dec(existing.total_outstanding) > 0:
            if total <= 0 or len(rows) < max(5, int((existing.row_count or 0) * 0.3)):
                return

        ReceivableDailyMetric.objects.update_or_create(
            business_date=bdate,
            defaults={
                "bucket_totals": {k: str(v) for k, v in bucket_totals.items()},
                "total_outstanding": total,
                "row_count": len(rows),
                "partner_balance_total": (
                    existing.partner_balance_total if existing else Decimal("0")
                ),
                "partner_count": existing.partner_count if existing else 0,
                "snapshot": snapshot,
            },
        )

    @classmethod
    def _process_profit_and_loss(cls, snapshot: KaraReportSnapshot) -> None:
        bdate = snapshot_business_date(
            period_to=snapshot.period_to,
            period_from=snapshot.period_from,
            fetched_at=snapshot.fetched_at,
        )
        parsed = snapshot.raw_data.get("parsed") or {}
        sum_row = snapshot.sum_row_data or {}
        if not parsed and sum_row:
            parsed = {
                "net_pure_sale": sum_row.get("NetPureSale", "0"),
                "cost_of_goods_sold": sum_row.get("CostOfGoodsSold", "0"),
                "gross_profit": sum_row.get("GrossProfit", "0"),
                "operating_profit": sum_row.get("OperatingProfit", "0"),
                "net_profit": sum_row.get("NetProfit", "0"),
                "gross_margin_rate": sum_row.get("GrossMarginRate", "0"),
                "line_items": {},
            }

        CompanyProfitLossMetric.objects.update_or_create(
            business_date=bdate,
            defaults={
                "period_from": snapshot.period_from,
                "period_to": snapshot.period_to,
                "net_pure_sale": _dec(parsed.get("net_pure_sale")),
                "cost_of_goods_sold": _dec(parsed.get("cost_of_goods_sold")),
                "gross_profit": _dec(parsed.get("gross_profit")),
                "operating_profit": _dec(parsed.get("operating_profit")),
                "net_profit": _dec(parsed.get("net_profit")),
                "gross_margin_rate": _dec(parsed.get("gross_margin_rate")),
                "line_items": parsed.get("line_items") or {},
                "snapshot": snapshot,
            },
        )
