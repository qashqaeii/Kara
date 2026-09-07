"""Settlement / receivables queries for bot."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Count, QuerySet, Sum

from reports.constants import AGING_BUCKET_KEYS, AGING_BUCKET_LABELS
from reports.models import (
    HeadVisitorSaleSnapshot,
    KaraReportSnapshot,
    ReceivableAgingSnapshot,
    VisitorSaleSnapshot,
)
from reports.bot.services.scope import apply_visitor_scope, is_supervisor, supervisor_code
from reports.services.access_control import AccessControlService
from reports.services.currency import format_money
from reports.services.retention import find_latest_full_snapshot


@dataclass
class SettlementPartnerRow:
    partner_code: str
    partner_name: str
    city_name: str
    total_outstanding: Decimal
    bucket_amounts: dict


class BotSettlementService:
    PAGE_SIZE = 8

    @classmethod
    def _personnel_code(cls, user: User) -> str | None:
        scope = AccessControlService.resolve_scope(user)
        return scope.personnel_code or None

    @classmethod
    def _aging_snapshot(cls) -> KaraReportSnapshot | None:
        snap = find_latest_full_snapshot("receivables_aging")
        if snap:
            return snap
        return (
            KaraReportSnapshot.objects.filter(report_key="receivables_aging")
            .order_by("-fetched_at")
            .first()
        )

    @classmethod
    def _base_qs(cls, user: User) -> QuerySet[ReceivableAgingSnapshot]:
        snap = cls._aging_snapshot()
        if not snap:
            return ReceivableAgingSnapshot.objects.none()
        qs = ReceivableAgingSnapshot.objects.filter(snapshot=snap)
        qs = apply_visitor_scope(qs, user)
        return qs.filter(total_outstanding__gt=0).order_by("-total_outstanding")

    @classmethod
    def _settlement_remainder(cls, user: User) -> Decimal | None:
        if is_supervisor(user):
            code = supervisor_code(user)
            if not code:
                return None
            snap = find_latest_full_snapshot("head_visitor_sale")
            if not snap:
                snap = (
                    KaraReportSnapshot.objects.filter(report_key="head_visitor_sale")
                    .order_by("-fetched_at")
                    .first()
                )
            if not snap:
                return None
            row = (
                HeadVisitorSaleSnapshot.objects.filter(
                    snapshot=snap, head_visitor_code=code
                )
                .order_by("-last_seen_at")
                .first()
            )
            if not row:
                return None
            return Decimal(str(row.settlement_remainder or 0))

        code = cls._personnel_code(user)
        if not code:
            return None
        snap = find_latest_full_snapshot("visitor_sale")
        if not snap:
            snap = (
                KaraReportSnapshot.objects.filter(report_key="visitor_sale")
                .order_by("-fetched_at")
                .first()
            )
        if not snap:
            return None
        row = (
            VisitorSaleSnapshot.objects.filter(snapshot=snap, visitor_code=code)
            .order_by("-last_seen_at")
            .first()
        )
        if not row:
            return None
        return Decimal(str(row.settlement_remainder or 0))

    @classmethod
    def overview(cls, user: User) -> dict:
        qs = cls._base_qs(user)
        agg = qs.aggregate(
            total=Sum("total_outstanding"),
            partners=Count("id"),
        )
        total = Decimal(str(agg["total"] or 0))
        partner_count = int(agg["partners"] or 0)

        bucket_totals: dict[str, Decimal] = {k: Decimal("0") for k in AGING_BUCKET_KEYS}
        for row in qs.only("bucket_amounts"):
            buckets = row.bucket_amounts or {}
            for key in AGING_BUCKET_KEYS:
                bucket_totals[key] += Decimal(str(buckets.get(key) or 0))

        top_buckets = []
        for key in AGING_BUCKET_KEYS:
            amount = bucket_totals[key]
            if amount > 0:
                top_buckets.append(
                    {
                        "key": key,
                        "label": AGING_BUCKET_LABELS.get(key, key),
                        "amount": format_money(amount),
                        "raw": amount,
                    }
                )

        remainder = cls._settlement_remainder(user)
        return {
            "has_data": bool(total or remainder),
            "total_outstanding": total,
            "total_outstanding_label": format_money(total) if total else None,
            "partner_count": partner_count,
            "settlement_remainder": remainder,
            "settlement_remainder_label": (
                format_money(remainder) if remainder is not None else None
            ),
            "top_buckets": top_buckets[:6],
        }

    @classmethod
    def partner_outstanding(cls, user: User, partner_code: str) -> Decimal | None:
        if not partner_code:
            return None
        row = cls._base_qs(user).filter(partner_code=partner_code).first()
        if not row:
            return None
        return Decimal(str(row.total_outstanding or 0))

    @classmethod
    def list_page(cls, user: User, page: int = 1) -> tuple[list[SettlementPartnerRow], int, int]:
        qs = cls._base_qs(user)
        total = qs.count()
        pages = max(1, (total + cls.PAGE_SIZE - 1) // cls.PAGE_SIZE)
        page = max(1, min(page, pages))
        offset = (page - 1) * cls.PAGE_SIZE
        rows = []
        for row in qs[offset : offset + cls.PAGE_SIZE]:
            rows.append(
                SettlementPartnerRow(
                    partner_code=row.partner_code,
                    partner_name=row.partner_name or "—",
                    city_name=row.city_name or "",
                    total_outstanding=Decimal(str(row.total_outstanding or 0)),
                    bucket_amounts=row.bucket_amounts or {},
                )
            )
        return rows, page, pages

    @classmethod
    def get_partner(cls, user: User, partner_code: str) -> SettlementPartnerRow | None:
        row = cls._base_qs(user).filter(partner_code=partner_code).first()
        if not row:
            return None
        return SettlementPartnerRow(
            partner_code=row.partner_code,
            partner_name=row.partner_name or "—",
            city_name=row.city_name or "",
            total_outstanding=Decimal(str(row.total_outstanding or 0)),
            bucket_amounts=row.bucket_amounts or {},
        )
