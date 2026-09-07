"""Invoice HTML pages."""

from __future__ import annotations

from django.shortcuts import render
from django.views import View

from reports.services.invoices import INVOICE_STATUS_FILTER_OPTIONS, InvoiceListFilters, InvoiceService
from reports.views.mixins import InvoiceAccessMixin


class InvoiceListView(View):
    template_name = "reports/invoices/list.html"

    def get(self, request):
        page = max(1, int(request.GET.get("page", "1")))
        filters = InvoiceListFilters.from_request(request.GET)
        orders, page, pages = InvoiceService.filter_page(request.user, filters, page)
        filtered_qs = InvoiceService.filtered_qs(request.user, filters)
        agg = InvoiceService.aggregate_qs(filtered_qs)
        return render(
            request,
            self.template_name,
            {
                "orders": [
                    InvoiceService.serialize_order_list(o, user=request.user) for o in orders
                ],
                "page": page,
                "pages": pages,
                "filters": filters,
                "query": filters.q,
                "aggregate": agg,
                "visitor_options": InvoiceService.list_visitor_options(request.user),
                "status_options": INVOICE_STATUS_FILTER_OPTIONS,
                "prev_url": filters.page_url(page - 1) if page > 1 else None,
                "next_url": filters.page_url(page + 1) if page < pages else None,
            },
        )


class InvoiceDetailView(InvoiceAccessMixin, View):
    template_name = "reports/invoices/detail.html"

    def get(self, request, order_code: str):
        order = InvoiceService.get_order(request.user, order_code)
        if not order:
            from django.http import Http404

            raise Http404()
        lines_page = max(1, int(request.GET.get("lines_page", "1")))
        raw = InvoiceService._effective_raw_data(order)
        payload = InvoiceService.serialize_order(
            order,
            user=request.user,
            include_lines=True,
            lines_page=lines_page,
            raw=raw,
        )
        return render(
            request,
            self.template_name,
            {
                "invoice": payload,
                "order": order,
                "raw_fields": _raw_field_rows(raw),
                "lines_page": lines_page,
            },
        )


_FIELD_LABELS = {
    "OrderCode": "کد فاکتور",
    "OrderPreCode": "شماره فاکتور",
    "OrderDate": "تاریخ فاکتور",
    "PreOrderDate": "تاریخ پیش‌فاکتور",
    "WarehouseDocumentDate": "تاریخ سند انبار",
    "PartnerCode": "کد مشتری",
    "PartnerName": "نام مشتری",
    "PartnerAddress": "آدرس مشتری",
    "PartnerPhone": "تلفن مشتری",
    "PartnerGroups": "گروه مشتری",
    "VisitorCode": "کد ویزیتور",
    "VisitorName": "نام ویزیتور",
    "DriverName": "نام راننده",
    "PayeeName": "تحویل‌گیرنده",
    "InsertedUser": "ثبت‌کننده",
    "StuffsQuantitySum": "تعداد اقلام",
    "StuffsPriceSum": "جمع اقلام",
    "OrderDiscountAmount": "تخفیف فاکتور",
    "OrderCashDiscountAmount": "تخفیف نقدی",
    "OrderTotalVAT": "مالیات",
    "SaleReversionAmount": "برگشت از فروش",
    "OrderFinalPrice": "مبلغ نهایی فاکتور",
    "FinalizedCostForCustomer": "بهای تمام‌شده",
}


def _raw_field_rows(raw: dict) -> list[dict]:
    rows = []
    seen = set()
    for key, label in _FIELD_LABELS.items():
        value = raw.get(key)
        if value in (None, "", "0", 0):
            continue
        rows.append({"key": key, "label": label, "value": value})
        seen.add(key)
    for key, value in sorted(raw.items()):
        if key in seen or key.startswith("_"):
            continue
        if value in (None, "", "0", 0):
            continue
        rows.append({"key": key, "label": key, "value": value})
    return rows
