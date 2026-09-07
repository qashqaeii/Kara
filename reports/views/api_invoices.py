"""REST-style invoice APIs backed by synced sale_orders data."""

from __future__ import annotations

from django.http import JsonResponse
from django.views import View

from reports.services.invoices import InvoiceService


class InvoiceListAPIView(View):
    def get(self, request):
        page = max(1, int(request.GET.get("page", "1")))
        page_size = min(100, max(1, int(request.GET.get("page_size", str(InvoiceService.PAGE_SIZE)))))
        orders, page, pages = InvoiceService.list_page(request.user, page, page_size=page_size)
        agg = InvoiceService.aggregate(request.user)
        return JsonResponse(
            {
                "items": [
                    InvoiceService.serialize_order_list(order, user=request.user)
                    for order in orders
                ],
                "page": page,
                "pages": pages,
                "total": agg["count"],
                "total_amount": str(agg["amount"]),
                "sync": InvoiceService.sync_status(),
            }
        )


class InvoiceDetailAPIView(View):
    def get(self, request, order_code: str):
        order = InvoiceService.get_order(request.user, order_code)
        if not order:
            return JsonResponse({"ok": False, "error": "فاکتور یافت نشد یا دسترسی ندارید."}, status=404)
        lines_page = max(1, int(request.GET.get("lines_page", "1")))
        return JsonResponse(
            {
                "ok": True,
                "invoice": InvoiceService.serialize_order(
                    order,
                    user=request.user,
                    include_lines=True,
                    lines_page=lines_page,
                ),
                "sync": InvoiceService.sync_status(),
            }
        )


class InvoiceSearchAPIView(View):
    def get(self, request):
        number = (request.GET.get("number") or "").strip()
        customer = (request.GET.get("customer") or "").strip()
        page = max(1, int(request.GET.get("page", "1")))

        if number:
            order = InvoiceService.search_by_number(request.user, number)
            if not order:
                return JsonResponse({"ok": True, "items": [], "total": 0})
            return JsonResponse(
                {
                    "ok": True,
                    "items": [InvoiceService.serialize_order_list(order, user=request.user)],
                    "total": 1,
                }
            )

        if customer:
            items, page, pages = InvoiceService.search_by_customer(request.user, customer, page)
            return JsonResponse(
                {
                    "ok": True,
                    "items": [
                        InvoiceService.serialize_order_list(order, user=request.user)
                        for order in items
                    ],
                    "page": page,
                    "pages": pages,
                    "total": len(items),
                }
            )

        return JsonResponse({"ok": False, "error": "پارامتر number یا customer لازم است."}, status=400)


class InvoiceStatsAPIView(View):
    def get(self, request):
        today = InvoiceService.period_aggregate(
            request.user, jalali_exact=InvoiceService._jalali_today()
        )
        month = InvoiceService.period_aggregate(
            request.user, jalali_month_prefix=InvoiceService._jalali_month_prefix()
        )
        total = InvoiceService.aggregate(request.user)
        return JsonResponse(
            {
                "today": {"count": today["count"], "amount": str(today["amount"])},
                "month": {"count": month["count"], "amount": str(month["amount"])},
                "total": {"count": total["count"], "amount": str(total["amount"])},
                "sync": InvoiceService.sync_status(),
            }
        )
