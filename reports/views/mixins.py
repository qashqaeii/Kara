"""View mixins for role-based access on the web dashboard."""

from __future__ import annotations

from django.contrib import messages
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect

from reports.services.access_control import AccessControlService


class KaraAdminRequiredMixin:
    """Sync center, data refresh, and integration tools."""

    def dispatch(self, request, *args, **kwargs):
        if not AccessControlService.can_manage_integration(request.user):
            if request.path.startswith("/reports/api/"):
                from django.http import JsonResponse

                return JsonResponse(
                    {"ok": False, "error": "دسترسی مدیریتی لازم است."},
                    status=403,
                )
            messages.error(request, "این بخش فقط برای مدیر سیستم در دسترس است.")
            return redirect("reports:my_performance")
        return super().dispatch(request, *args, **kwargs)


class KaraManagementRequiredMixin:
    """Company-wide analytics and executive dashboards."""

    def dispatch(self, request, *args, **kwargs):
        if not AccessControlService.can_view_company(request.user):
            if request.path.startswith("/reports/api/"):
                from django.http import JsonResponse

                return JsonResponse(
                    {"ok": False, "error": "دسترسی به نمای سازمانی ندارید."},
                    status=403,
                )
            messages.error(request, "این بخش برای نقش شما در دسترس نیست.")
            return redirect("reports:my_performance")
        return super().dispatch(request, *args, **kwargs)


class VisitorDetailAccessMixin:
    """Block viewing another visitor/supervisor's personnel_code."""

    personnel_kwarg = "personnel_code"

    def dispatch(self, request, *args, **kwargs):
        code = (kwargs.get(self.personnel_kwarg) or "").strip()
        if code and not AccessControlService.can_access_visitor(request.user, code):
            raise Http404("پرونده یافت نشد یا دسترسی ندارید.")
        return super().dispatch(request, *args, **kwargs)


class InvoiceAccessMixin:
    order_kwarg = "order_code"

    def dispatch(self, request, *args, **kwargs):
        from reports.services.invoices import InvoiceService

        code = (kwargs.get(self.order_kwarg) or "").strip()
        if code and not InvoiceService.can_access_order(request.user, code):
            raise Http404("فاکتور یافت نشد یا دسترسی ندارید.")
        return super().dispatch(request, *args, **kwargs)
