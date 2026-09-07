"""Supervisor team roster and member drill-down for bot."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.utils import timezone

from reports.bot.services.invoices import BotInvoiceService
from reports.bot.services.scope import can_access_visitor, is_supervisor, supervisor_code
from reports.bot.services.settlement import BotSettlementService
from reports.models import (
    HeadVisitorSaleSnapshot,
    SalespersonDailyMetric,
    SupervisorDailyMetric,
    VisitorSaleSnapshot,
)
from reports.services.retention import find_latest_full_snapshot
from reports.services.analytics import AnalyticsService
from reports.services.currency import format_money
from reports.services.supervisor_detail import _company_rank, build_supervisor_detail


@dataclass
class TeamMemberSummary:
    personnel_code: str
    personnel_name: str
    total_sale: Decimal
    order_count: int
    active_days: int
    team_share: float


class BotTeamService:
    PAGE_SIZE = 8

    @classmethod
    def overview(cls, user: User) -> dict:
        if not is_supervisor(user):
            return {"has_data": False}
        code = supervisor_code(user)
        members = cls.roster(user)
        if not members:
            return {"has_data": False, "supervisor_code": code}

        active = sum(
            1 for m in members if m.total_sale > 0 or m.order_count > 0
        )
        total_sale = sum((m.total_sale for m in members), Decimal("0"))
        rank_info = _company_rank(code, preset="all")
        return {
            "has_data": True,
            "supervisor_code": code,
            "supervisor_name": rank_info.get("name") or cls._supervisor_name(code) or code,
            "team_size": len(members),
            "active_count": active,
            "total_sale": format_money(total_sale) if total_sale else "—",
            "company_rank": rank_info.get("label") or "—",
            "member_count": len(members),
        }

    @classmethod
    def _supervisor_name(cls, code: str) -> str:
        snap = find_latest_full_snapshot("head_visitor_sale")
        if snap:
            row = (
                HeadVisitorSaleSnapshot.objects.filter(
                    snapshot=snap, head_visitor_code=code
                )
                .order_by("-last_seen_at")
                .first()
            )
            if row and row.head_visitor_name:
                return row.head_visitor_name
        vsnap = find_latest_full_snapshot("visitor_sale")
        if vsnap:
            row = (
                VisitorSaleSnapshot.objects.filter(
                    snapshot=vsnap, head_visitor_code=code
                )
                .exclude(head_visitor_name="")
                .first()
            )
            if row:
                return row.head_visitor_name
        return ""

    @classmethod
    def _roster_from_metrics(cls, user: User) -> list[TeamMemberSummary]:
        from reports.bot.services.scope import supervisor_code

        code = supervisor_code(user)
        if not code:
            return []
        rows = list(
            SalespersonDailyMetric.objects.filter(supervisor_code=code)
            .values("personnel_code", "personnel_name")
            .annotate(
                total_sale=Sum("total_sale"),
                order_count=Sum("final_order_count"),
                active_days=Count("business_date"),
            )
            .order_by("-total_sale")
        )
        if not rows:
            return []

        total_team_sale = sum(
            (Decimal(str(r["total_sale"] or 0)) for r in rows), Decimal("0")
        ) or Decimal("1")
        result: list[TeamMemberSummary] = []
        for row in rows:
            sale = Decimal(str(row["total_sale"] or 0))
            share = float((sale / total_team_sale * 100).quantize(Decimal("0.1")))
            result.append(
                TeamMemberSummary(
                    personnel_code=str(row["personnel_code"] or ""),
                    personnel_name=str(row["personnel_name"] or row["personnel_code"] or "—"),
                    total_sale=sale,
                    order_count=int(row["order_count"] or 0),
                    active_days=int(row["active_days"] or 0),
                    team_share=share,
                )
            )
        return result

    @classmethod
    def _roster_from_snapshot(cls, user: User) -> list[TeamMemberSummary]:
        code = supervisor_code(user)
        if not code:
            return []
        snap = find_latest_full_snapshot("visitor_sale")
        if not snap:
            return []
        rows = list(
            VisitorSaleSnapshot.objects.filter(snapshot=snap, head_visitor_code=code)
            .order_by("-total_pure_sale", "-total_sale", "visitor_name")
        )
        if not rows:
            return []

        total_team_sale = sum(
            (Decimal(str(r.total_pure_sale or r.total_sale or 0)) for r in rows),
            Decimal("0"),
        ) or Decimal("1")
        result: list[TeamMemberSummary] = []
        for row in rows:
            sale = Decimal(str(row.total_pure_sale or row.total_sale or 0))
            share = float((sale / total_team_sale * 100).quantize(Decimal("0.1")))
            result.append(
                TeamMemberSummary(
                    personnel_code=str(row.visitor_code or ""),
                    personnel_name=str(row.visitor_name or row.visitor_code or "—"),
                    total_sale=sale,
                    order_count=int(row.order_count or 0),
                    active_days=0,
                    team_share=share,
                )
            )
        return result

    @classmethod
    def roster(cls, user: User) -> list[TeamMemberSummary]:
        if not is_supervisor(user):
            return []
        members = cls._roster_from_metrics(user)
        if members:
            return members
        members = cls._roster_from_snapshot(user)
        if members:
            return members
        code = supervisor_code(user)
        detail = build_supervisor_detail(code, preset="all", user=user)
        members_data = detail.get("team_members") or []
        result: list[TeamMemberSummary] = []
        for m in members_data:
            sale = Decimal(str(m.get("total_sale") or 0))
            result.append(
                TeamMemberSummary(
                    personnel_code=str(m.get("code") or ""),
                    personnel_name=str(m.get("name") or m.get("code") or "—"),
                    total_sale=sale,
                    order_count=int(m.get("order_count") or 0),
                    active_days=int(m.get("active_days") or 0),
                    team_share=float(m.get("team_share") or 0),
                )
            )
        return result

    @classmethod
    def list_page(cls, user: User, page: int = 1) -> tuple[list[TeamMemberSummary], int, int]:
        members = cls.roster(user)
        total = len(members)
        pages = max(1, (total + cls.PAGE_SIZE - 1) // cls.PAGE_SIZE)
        page = max(1, min(page, pages))
        offset = (page - 1) * cls.PAGE_SIZE
        return members[offset : offset + cls.PAGE_SIZE], page, pages

    @classmethod
    def get_member(cls, user: User, visitor_code: str) -> TeamMemberSummary | None:
        if not can_access_visitor(user, visitor_code):
            return None
        for member in cls.roster(user):
            if member.personnel_code == visitor_code:
                return member
        if can_access_visitor(user, visitor_code):
            return TeamMemberSummary(
                personnel_code=visitor_code,
                personnel_name=visitor_code,
                total_sale=Decimal("0"),
                order_count=0,
                active_days=0,
                team_share=0.0,
            )
        return None

    @classmethod
    def member_snapshot(cls, user: User, visitor_code: str) -> dict:
        member = cls.get_member(user, visitor_code)
        if not member:
            return {"has_data": False}

        today = timezone.localdate()
        today_jalali = BotInvoiceService._jalali_today()
        month_prefix = BotInvoiceService._jalali_month_prefix()

        qs = BotInvoiceService._base_qs_for_visitor(user, visitor_code)
        today_inv = qs.filter(order_date=today_jalali).aggregate(
            total=Sum("order_final_price"), count=Count("id")
        )
        month_inv = qs.filter(order_date__startswith=month_prefix).aggregate(
            total=Sum("order_final_price"), count=Count("id")
        )
        inv_agg = BotInvoiceService.aggregate_for_visitor(user, visitor_code)

        today_row = SalespersonDailyMetric.objects.filter(
            personnel_code=visitor_code, business_date=today
        ).first()
        month_start = today.replace(day=1)
        month_rows = list(
            SalespersonDailyMetric.objects.filter(
                personnel_code=visitor_code,
                business_date__gte=month_start,
                business_date__lte=today,
            )
        )
        month_sale_metric = sum(
            (Decimal(str(r.total_pure_sale or 0)) for r in month_rows), Decimal("0")
        )
        month_orders_metric = sum(int(r.final_order_count or 0) for r in month_rows)

        metric_qs = SalespersonDailyMetric.objects.filter(personnel_code=visitor_code)
        active_days = (
            metric_qs.filter(total_pure_sale__gt=0)
            .values("business_date")
            .distinct()
            .count()
        )

        connection = AnalyticsService.connection_status()

        today_orders = int(today_inv["count"] or 0)
        today_sale_raw = today_inv["total"] or Decimal("0")
        if today_row and today_orders == 0:
            row_orders = int(today_row.final_order_count or 0)
            row_sale = Decimal(str(today_row.total_pure_sale or 0))
            if row_orders or row_sale:
                today_orders = row_orders
                today_sale_raw = row_sale

        month_orders = int(month_inv["count"] or 0) or month_orders_metric
        month_sale_raw = month_inv["total"] or month_sale_metric or Decimal("0")

        return {
            "has_data": True,
            "personnel_code": member.personnel_code,
            "personnel_name": member.personnel_name,
            "team_share": member.team_share,
            "today_orders": today_orders,
            "today_sale": format_money(today_sale_raw) if today_sale_raw else None,
            "month_sale": format_money(month_sale_raw) if month_sale_raw else None,
            "month_orders": month_orders or None,
            "total_invoices": inv_agg["count"] or None,
            "active_days": active_days or None,
            "total_sale": format_money(member.total_sale) if member.total_sale else None,
            "order_count": member.order_count or None,
            "sync_label": connection.get("last_sync_label") or "—",
        }

    @classmethod
    def supervisor_performance(cls, user: User) -> dict:
        if not is_supervisor(user):
            return {"has_data": False}

        code = supervisor_code(user)
        if not code:
            return {"has_data": False}

        today = timezone.localdate()
        month_start = today.replace(day=1)
        today_jalali = BotInvoiceService._jalali_today()
        month_prefix = BotInvoiceService._jalali_month_prefix()
        connection = AnalyticsService.connection_status()
        settlement = BotSettlementService.overview(user)

        today_inv = BotInvoiceService.period_aggregate(user, jalali_exact=today_jalali)
        month_inv = BotInvoiceService.period_aggregate(
            user, jalali_month_prefix=month_prefix
        )

        today_row = SupervisorDailyMetric.objects.filter(
            supervisor_code=code, business_date=today
        ).first()
        month_rows = list(
            SupervisorDailyMetric.objects.filter(
                supervisor_code=code,
                business_date__gte=month_start,
                business_date__lte=today,
            )
        )
        month_sale_metric = sum(
            (Decimal(str(r.total_pure_sale or 0)) for r in month_rows), Decimal("0")
        )
        month_orders_metric = sum(int(r.final_order_count or 0) for r in month_rows)

        inv_agg = BotInvoiceService.aggregate(user)
        members = cls.roster(user)
        rank_info = _company_rank(code, preset="all")

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
        active_count = sum(
            1 for m in members if m.total_sale > 0 or m.order_count > 0
        )
        total_team_sale = sum((m.total_sale for m in members), Decimal("0"))

        return {
            "has_data": bool(
                members
                or today_row
                or month_rows
                or inv_agg["count"]
            ),
            "mode": "supervisor",
            "supervisor_name": cls._supervisor_name(code) or code,
            "company_rank": rank_info.get("label") or "—",
            "team_size": len(members),
            "active_count": active_count,
            "today_orders": today_orders,
            "today_sale": format_money(today_sale_raw) if today_sale_raw else None,
            "month_sale": format_money(month_sale_raw) if month_sale_raw else None,
            "month_orders": month_orders or None,
            "total_invoices": inv_agg["count"] or None,
            "total_sale": format_money(total_team_sale) if total_team_sale else None,
            "avg_per_person": (
                format_money(total_team_sale / len(members))
                if members and total_team_sale
                else None
            ),
            "settlement_remainder": settlement.get("settlement_remainder_label"),
            "total_outstanding": settlement.get("total_outstanding_label"),
            "sync_label": connection.get("last_sync_label") or "—",
        }
