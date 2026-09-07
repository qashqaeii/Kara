"""TV Mode and Data Explorer views."""

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from reports.services.access_control import AccessControlService
from reports.services.analytics import AnalyticsService
from reports.views.mixins import KaraAdminRequiredMixin, KaraManagementRequiredMixin


class DataExplorerView(KaraManagementRequiredMixin, View):
    """Drill-down tables, export, debug — management only."""

    template_name = "reports/data_explorer.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                "reports": AnalyticsService.data_explorer_reports(),
                "connection": AnalyticsService.connection_status(),
            },
        )


class TvModeView(View):
    template_name = "reports/tv_mode.html"

    def get(self, request):
        if not AccessControlService.can_access_tv(request.user):
            messages.error(request, "دسترسی به حالت تلویزیون ندارید.")
            return redirect("reports:my_performance")
        ctx = AnalyticsService.tv_context()
        ctx.setdefault("preset", "all")
        ctx.setdefault("preset_label", "کل داده‌ها")
        ctx.setdefault(
            "period_subtitle",
            f"{ctx['preset_label']} · منبع گزارش فروش ویزیتور",
        )
        ctx.setdefault(
            "trend_subtitle",
            f"نمودار روزانه · {ctx['preset_label']}",
        )
        ctx.setdefault("trend_points", len(ctx.get("trend") or []))
        ctx["slide_interval"] = getattr(settings, "TV_SLIDE_INTERVAL_SECONDS", 20)
        ctx["refresh_seconds"] = getattr(settings, "TV_AUTO_REFRESH_SECONDS", 60)
        return render(request, self.template_name, ctx)


class TvModeAPIView(View):
    def get(self, request):
        if not AccessControlService.can_access_tv(request.user):
            return JsonResponse({"error": "دسترسی ندارید."}, status=403)
        ctx = AnalyticsService.tv_context()
        ctx["slide_interval_seconds"] = getattr(settings, "TV_SLIDE_INTERVAL_SECONDS", 20)
        return JsonResponse(ctx, safe=False)
