"""Invoice queries for the Bale bot — delegates to core InvoiceService."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import QuerySet

from reports.models import SaleOrderSnapshot
from reports.services.invoices import (
    InvoiceService,
    InvoiceSummary,
    derive_order_status,
    normalize_fa,
)

# Re-export for backward compatibility with existing bot imports.
__all__ = [
    "BotInvoiceService",
    "InvoiceSummary",
    "derive_order_status",
    "normalize_fa",
]


class BotInvoiceService:
    PAGE_SIZE = 8
    ITEMS_PAGE_SIZE = 5

    @classmethod
    def _invoice_snapshot(cls):
        return InvoiceService.invoice_snapshot()

    @classmethod
    def _line_items_snapshot(cls):
        return InvoiceService.line_items_snapshot()

    @classmethod
    def _base_qs(cls, user: User) -> QuerySet[SaleOrderSnapshot]:
        return InvoiceService.orders_qs(user)

    @classmethod
    def _base_qs_for_visitor(cls, user: User, visitor_code: str) -> QuerySet[SaleOrderSnapshot]:
        from reports.bot.services.scope import can_access_visitor

        if not can_access_visitor(user, visitor_code):
            return SaleOrderSnapshot.objects.none()
        snap = cls._invoice_snapshot()
        if not snap:
            return SaleOrderSnapshot.objects.none()
        return (
            SaleOrderSnapshot.objects.filter(snapshot=snap, visitor_code=visitor_code)
            .order_by("-order_date", "-order_code")
        )

    @classmethod
    def can_access_order(cls, user: User, order_code: str) -> bool:
        return InvoiceService.can_access_order(user, order_code)

    @classmethod
    def get_order(cls, user: User, order_code: str) -> SaleOrderSnapshot | None:
        return InvoiceService.get_order(user, order_code)

    @classmethod
    def list_page_for_visitor(
        cls, user: User, visitor_code: str, page: int = 1
    ) -> tuple[list[SaleOrderSnapshot], int, int]:
        qs = cls._base_qs_for_visitor(user, visitor_code)
        total = qs.count()
        page_size = cls.PAGE_SIZE
        pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, pages))
        offset = (page - 1) * page_size
        return list(qs[offset : offset + page_size]), page, pages

    @classmethod
    def aggregate_for_visitor(cls, user: User, visitor_code: str) -> dict:
        qs = cls._base_qs_for_visitor(user, visitor_code)
        from django.db.models import Count, Sum

        agg = qs.aggregate(total=Count("id"), amount=Sum("order_final_price"))
        return {
            "count": int(agg["total"] or 0),
            "amount": agg["amount"] or 0,
        }

    @classmethod
    def list_page(cls, user: User, page: int = 1) -> tuple[list[SaleOrderSnapshot], int, int]:
        return InvoiceService.list_page(user, page, page_size=cls.PAGE_SIZE)

    @classmethod
    def aggregate(cls, user: User) -> dict:
        return InvoiceService.aggregate(user)

    @classmethod
    def to_summary(cls, order: SaleOrderSnapshot) -> InvoiceSummary:
        return InvoiceService.to_summary(order)

    @classmethod
    def period_aggregate(
        cls,
        user: User,
        *,
        jalali_exact: str | None = None,
        jalali_month_prefix: str | None = None,
    ) -> dict:
        return InvoiceService.period_aggregate(
            user,
            jalali_exact=jalali_exact,
            jalali_month_prefix=jalali_month_prefix,
        )

    @classmethod
    def _effective_raw_data(cls, order: SaleOrderSnapshot) -> dict:
        return InvoiceService._effective_raw_data(order)

    @classmethod
    def financial_breakdown(cls, order: SaleOrderSnapshot) -> list[dict]:
        return InvoiceService.financial_breakdown(order)

    @classmethod
    def extra_fields(cls, order: SaleOrderSnapshot) -> dict:
        return InvoiceService.extra_fields(order)

    @classmethod
    def search_by_number(cls, user: User, number: str) -> SaleOrderSnapshot | None:
        return InvoiceService.search_by_number(user, number)

    @classmethod
    def search_by_customer(
        cls, user: User, name: str, page: int = 1
    ) -> tuple[list[SaleOrderSnapshot], int, int]:
        from django.db.models import Q

        term = normalize_fa(name)
        if not term:
            return [], 1, 1
        qs = cls._base_qs(user).filter(
            Q(partner_name__icontains=term) | Q(partner_name__icontains=name.strip())
        )
        total = qs.count()
        page_size = cls.PAGE_SIZE
        pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, pages))
        offset = (page - 1) * page_size
        return list(qs[offset : offset + page_size]), page, pages

    @classmethod
    def line_items_from_order(cls, order: SaleOrderSnapshot) -> list[dict]:
        return InvoiceService.line_items_as_dicts(order)

    @classmethod
    def line_items_page(
        cls, order: SaleOrderSnapshot, page: int = 1
    ) -> tuple[list[dict], int, int, int]:
        items, page_n, pages, total = InvoiceService.line_items_page(order, page)
        if not items and total == 0:
            return [], page, pages, total
        size = cls.ITEMS_PAGE_SIZE
        all_items = InvoiceService.line_items_as_dicts(order)
        total = len(all_items)
        pages = max(1, (total + size - 1) // size) if total else 1
        page = max(1, min(page, pages))
        if not all_items:
            return [], page, pages, 0
        offset = (page - 1) * size
        return all_items[offset : offset + size], page, pages, total

    @classmethod
    def has_line_items(cls, order: SaleOrderSnapshot) -> bool:
        return InvoiceService.has_line_items(order)
