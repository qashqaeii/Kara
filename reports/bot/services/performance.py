"""Visitor and supervisor performance snapshot for bot."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Sum
from django.utils import timezone

from reports.models import SalespersonDailyMetric
from reports.services.access_control import AccessControlService
from reports.services.analytics import AnalyticsService
from reports.services.currency import format_money
from reports.bot.services.customers import BotCustomerService
from reports.bot.services.invoices import BotInvoiceService
from reports.bot.services.scope import is_supervisor
from reports.bot.services.settlement import BotSettlementService
from reports.bot.services.team import BotTeamService


class BotPerformanceService:
    @classmethod
    def snapshot(cls, user: User) -> dict:
        if is_supervisor(user):
            return BotTeamService.supervisor_performance(user)

        scope = AccessControlService.resolve_scope(user)
        code = scope.personnel_code
        if not code:
            return {"has_data": False}

        today = timezone.localdate()
        today_jalali = BotInvoiceService._jalali_today()
        month_prefix = BotInvoiceService._jalali_month_prefix()

        today_inv = BotInvoiceService.period_aggregate(user, jalali_exact=today_jalali)
        month_inv = BotInvoiceService.period_aggregate(
            user, jalali_month_prefix=month_prefix
        )

        today_row = SalespersonDailyMetric.objects.filter(
            personnel_code=code, business_date=today
        ).first()

        month_start = today.replace(day=1)
        month_rows = list(
            SalespersonDailyMetric.objects.filter(
                personnel_code=code,
                business_date__gte=month_start,
                business_date__lte=today,
            )
        )
        month_sale_metric = sum(
            (Decimal(str(r.total_pure_sale or 0)) for r in month_rows), Decimal("0")
        )
        month_orders_metric = sum(int(r.final_order_count or 0) for r in month_rows)

        metric_qs = SalespersonDailyMetric.objects.filter(personnel_code=code)
        agg = metric_qs.aggregate(orders=Sum("final_order_count"))
        total_invoice_count = int(agg["orders"] or 0)
        has_historical_metrics = metric_qs.exists()
        inv_agg = BotInvoiceService.aggregate(user)

        active_days = (
            metric_qs.filter(total_pure_sale__gt=0)
            .values("business_date")
            .distinct()
            .count()
        )

        customer_overview = BotCustomerService.overview(user)
        settlement = BotSettlementService.overview(user)

        today_orders = today_inv["count"]
        today_sale_raw = today_inv["amount"]
        if today_row and today_orders == 0:
            row_orders = int(today_row.final_order_count or 0)
            row_sale = Decimal(str(today_row.total_pure_sale or 0))
            if row_orders or row_sale:
                today_orders = row_orders
                today_sale_raw = row_sale

        month_orders = month_inv["count"] or month_orders_metric
        month_sale_raw = month_inv["amount"] or month_sale_metric
        avg_order = month_sale_raw / month_orders if month_orders else Decimal("0")

        visitor_remainder = settlement.get("settlement_remainder")
        connection = AnalyticsService.connection_status()

        return {
            "has_data": bool(
                today_inv["count"]
                or month_inv["count"]
                or inv_agg["count"]
                or has_historical_metrics
            ),
            "mode": "visitor",
            "today_orders": today_orders,
            "today_sale": format_money(today_sale_raw) if today_sale_raw else None,
            "month_sale": format_money(month_sale_raw) if month_sale_raw else None,
            "month_orders": month_orders or None,
            "total_invoices": inv_agg["count"] or total_invoice_count or None,
            "active_days": active_days or None,
            "customer_count": customer_overview.get("customer_count"),
            "avg_order_value": format_money(avg_order) if avg_order else None,
            "settlement_remainder": (
                settlement.get("settlement_remainder_label")
                if visitor_remainder is not None
                else None
            ),
            "total_outstanding": settlement.get("total_outstanding_label"),
            "sync_label": connection.get("last_sync_label") or "—",
        }
