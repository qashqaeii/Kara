"""Analytics drill-down pages."""

from django.shortcuts import render
from django.views import View

from reports.constants import DEFAULT_PERIOD_PRESET
from reports.services.analytics import AnalyticsService
from reports.services.analytics_query import AnalyticsQueryService
from reports.services.dates import DateRange
from reports.services.period_comparison import PeriodComparisonService
from reports.services.ranking_pages import (
    chart_payload,
    enrich_ranking_rows,
    orders_chart_payload,
    period_context,
    ranking_summary,
    team_share_payload,
)
from reports.views.mixins import (
    KaraManagementRequiredMixin,
    VisitorDetailAccessMixin,
)


class AnalyticsSalespersonsView(KaraManagementRequiredMixin, View):
    template_name = "reports/analytics/salespersons.html"

    def get(self, request):
        preset = request.GET.get("period") or DEFAULT_PERIOD_PRESET
        items = enrich_ranking_rows(
            AnalyticsService.visitor_ranking(limit=100, preset=preset, user=request.user)
        )
        ctx = period_context(preset)
        ctx.update(
            {
                "items": items,
                "podium": items[:3],
                "summary": ranking_summary(items, label_singular="ویزیتور"),
                "chart_data": chart_payload(items, limit=8),
                "team_chart_data": team_share_payload(items, limit=6),
                "orders_chart_data": orders_chart_payload(items, limit=8),
                "connection": AnalyticsService.connection_status(),
            }
        )
        return render(request, self.template_name, ctx)


class AnalyticsSalespersonDetailView(VisitorDetailAccessMixin, View):
    template_name = "reports/analytics/salesperson_detail.html"

    def get(self, request, personnel_code: str):
        from reports.services.salesperson_detail import build_salesperson_detail

        preset = request.GET.get("period") or DEFAULT_PERIOD_PRESET
        ctx = build_salesperson_detail(personnel_code, preset=preset)
        ctx["connection"] = AnalyticsService.connection_status()
        return render(request, self.template_name, ctx)


class AnalyticsSupervisorsView(KaraManagementRequiredMixin, View):
    template_name = "reports/analytics/supervisors.html"

    def get(self, request):
        preset = request.GET.get("period") or DEFAULT_PERIOD_PRESET
        items = enrich_ranking_rows(
            AnalyticsService.head_visitor_ranking(limit=100, preset=preset, user=request.user)
        )
        ctx = period_context(preset)
        ctx.update(
            {
                "items": items,
                "podium": items[:3],
                "summary": ranking_summary(items, label_singular="سرپرست"),
                "chart_data": chart_payload(items, limit=8),
                "connection": AnalyticsService.connection_status(),
            }
        )
        return render(request, self.template_name, ctx)


class AnalyticsSupervisorDetailView(VisitorDetailAccessMixin, View):
    template_name = "reports/analytics/supervisor_detail.html"

    def get(self, request, personnel_code: str):
        from reports.services.supervisor_detail import build_supervisor_detail

        preset = request.GET.get("period") or DEFAULT_PERIOD_PRESET
        ctx = build_supervisor_detail(
            personnel_code, preset=preset, user=request.user
        )
        ctx["connection"] = AnalyticsService.connection_status()
        return render(request, self.template_name, ctx)


class AnalyticsRegionsView(KaraManagementRequiredMixin, View):
    template_name = "reports/analytics/regions.html"

    def get(self, request):
        preset = request.GET.get("period") or DEFAULT_PERIOD_PRESET
        dr, _ = PeriodComparisonService.comparison_range(preset)
        date_range = DateRange(dr.start, dr.end) if dr else None
        cities = enrich_ranking_rows(
            AnalyticsQueryService.region_ranking(
                "city", dr=date_range, limit=20, preset=preset
            )
        )
        zones = enrich_ranking_rows(
            AnalyticsQueryService.region_ranking(
                "zone", dr=date_range, limit=20, preset=preset
            )
        )
        ctx = period_context(preset)
        ctx.update(
            {
                "cities": cities,
                "zones": zones,
                "city_summary": ranking_summary(cities, label_singular="شهر"),
                "zone_summary": ranking_summary(zones, label_singular="منطقه"),
                "city_chart": chart_payload(cities, limit=6),
                "zone_chart": chart_payload(zones, limit=8),
                "connection": AnalyticsService.connection_status(),
            }
        )
        return render(request, self.template_name, ctx)


class AnalyticsReversionsView(KaraManagementRequiredMixin, View):
    template_name = "reports/analytics/reversions.html"

    def get(self, request):
        preset = request.GET.get("period") or DEFAULT_PERIOD_PRESET
        kpis = AnalyticsService.company_kpis(preset)
        return render(request, self.template_name, {"kpis": kpis, "preset": preset})


class AnalyticsReceivablesView(KaraManagementRequiredMixin, View):
    template_name = "reports/analytics/receivables.html"

    def get(self, request):
        from reports.services.receivables_page import build_receivables_page

        ctx = build_receivables_page()
        ctx["connection"] = AnalyticsService.connection_status()
        ctx["receivables"] = ctx
        ctx["currency_unit"] = ctx.get("unit") or ""
        return render(request, self.template_name, ctx)


class MyPerformanceView(View):
    template_name = "reports/my_performance.html"

    def get(self, request):
        from reports.services.my_performance import build_my_performance

        preset = request.GET.get("period") or DEFAULT_PERIOD_PRESET
        ctx = build_my_performance(request.user, preset=preset)
        return render(request, self.template_name, ctx)
