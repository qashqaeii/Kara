"""Invoice HTML pages."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views import View

from reports.services.invoice_print import (
    InvoicePrintError,
    can_print,
    fetch_print_html,
    resolve_kara_order_id,
    verify_print_token,
)
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


class InvoicePrintView(View):
    """Proxy Kara's official invoice HTML through the portal."""

    unavailable_template = "reports/invoices/print_unavailable.html"

    def get(self, request, order_code: str):
        code = (order_code or "").strip()
        if not code:
            raise Http404()

        user = self._resolve_user(request, code)
        if user is None:
            raise Http404()
        if not InvoiceService.can_access_order(user, code):
            raise Http404()

        order = InvoiceService.get_order(user, code)
        if not order:
            raise Http404()
        if not can_print(order):
            return render(
                request,
                self.unavailable_template,
                {
                    "order_code": code,
                    "order_pre_code": order.order_pre_code,
                    "reason": "شناسه چاپ این فاکتور هنوز از کارا sync نشده است.",
                },
                status=404,
            )

        try:
            html = fetch_print_html(resolve_kara_order_id(order))
        except InvoicePrintError as exc:
            return render(
                request,
                self.unavailable_template,
                {
                    "order_code": code,
                    "order_pre_code": order.order_pre_code,
                    "reason": str(exc),
                },
                status=503,
            )

        response = HttpResponse(html, content_type="text/html; charset=utf-8")
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response

    def _resolve_user(self, request, order_code: str) -> User | None:
        token = (request.GET.get("token") or "").strip()
        if token:
            try:
                token_code, user_id = verify_print_token(token)
            except InvoicePrintError:
                return None
            if token_code != order_code:
                return None
            return User.objects.filter(pk=user_id).first()

        if request.user.is_authenticated:
            return request.user
        return None


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
