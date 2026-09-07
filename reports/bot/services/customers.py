"""Customer list derived from invoice snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Count, Max, Sum

from reports.bot.services.invoices import BotInvoiceService
from reports.bot.services.settlement import BotSettlementService
from reports.models import SaleOrderSnapshot


@dataclass
class CustomerSummary:
    partner_code: str
    partner_name: str
    order_count: int
    total_sale: Decimal
    last_order_date: str
    outstanding: Decimal | None


class BotCustomerService:
    PAGE_SIZE = 8

    @classmethod
    def _aggregate_qs(cls, user: User):
        qs = BotInvoiceService._base_qs(user)
        with_code = (
            qs.exclude(partner_code="")
            .values("partner_code", "partner_name")
            .annotate(
                order_count=Count("id"),
                total_sale=Sum("order_final_price"),
                last_order_date=Max("order_date"),
            )
        )
        without_code = (
            qs.filter(partner_code="")
            .exclude(partner_name="")
            .values("partner_name")
            .annotate(
                partner_code=Max("partner_code"),
                order_count=Count("id"),
                total_sale=Sum("order_final_price"),
                last_order_date=Max("order_date"),
            )
        )
        rows = list(with_code) + list(without_code)
        rows.sort(key=lambda r: (-Decimal(str(r["total_sale"] or 0)), r.get("partner_name") or ""))
        return rows

    @classmethod
    def overview(cls, user: User) -> dict:
        agg = cls._aggregate_qs(user)
        total_customers = len(agg)
        totals = BotInvoiceService.aggregate(user)
        return {
            "has_data": total_customers > 0,
            "customer_count": total_customers,
            "total_orders": totals["count"],
            "total_sale": totals["amount"],
        }

    @classmethod
    def list_page(cls, user: User, page: int = 1) -> tuple[list[CustomerSummary], int, int]:
        agg = cls._aggregate_qs(user)
        total = len(agg)
        pages = max(1, (total + cls.PAGE_SIZE - 1) // cls.PAGE_SIZE)
        page = max(1, min(page, pages))
        offset = (page - 1) * cls.PAGE_SIZE
        slice_rows = agg[offset : offset + cls.PAGE_SIZE]
        items = []
        for row in slice_rows:
            code = row.get("partner_code") or ""
            name = (row.get("partner_name") or "—").strip() or "—"
            outstanding = BotSettlementService.partner_outstanding(user, code) if code else None
            items.append(
                CustomerSummary(
                    partner_code=code or name,
                    partner_name=name,
                    order_count=int(row["order_count"] or 0),
                    total_sale=Decimal(str(row["total_sale"] or 0)),
                    last_order_date=str(row["last_order_date"] or "—"),
                    outstanding=outstanding,
                )
            )
        return items, page, pages

    @classmethod
    def get_customer(cls, user: User, partner_code: str) -> CustomerSummary | None:
        if not partner_code:
            return None
        for row in cls._aggregate_qs(user):
            code = row.get("partner_code") or ""
            name = (row.get("partner_name") or "").strip()
            if code == partner_code or (not code and name == partner_code):
                outstanding = BotSettlementService.partner_outstanding(user, code) if code else None
                return CustomerSummary(
                    partner_code=code or name,
                    partner_name=name or "—",
                    order_count=int(row["order_count"] or 0),
                    total_sale=Decimal(str(row["total_sale"] or 0)),
                    last_order_date=str(row["last_order_date"] or "—"),
                    outstanding=outstanding,
                )
        return None

    @classmethod
    def recent_orders(
        cls, user: User, partner_code: str, limit: int = 5
    ) -> list[SaleOrderSnapshot]:
        qs = BotInvoiceService._base_qs(user)
        if partner_code.isdigit() or len(partner_code) <= 20:
            rows = list(qs.filter(partner_code=partner_code).order_by("-order_date", "-order_code")[:limit])
            if rows:
                return rows
        return list(
            qs.filter(partner_name=partner_code)
            .order_by("-order_date", "-order_code")[:limit]
        )
