"""Analytics API endpoints."""

from django.http import JsonResponse
from django.views import View

from reports.constants import DEFAULT_PERIOD_PRESET
from reports.services.analytics import AnalyticsService
from reports.services.analytics_query import AnalyticsQueryService
from reports.services.period_comparison import PeriodComparisonService
from reports.views.mixins import KaraAdminRequiredMixin, KaraManagementRequiredMixin


def _preset(request) -> str:
    return request.GET.get("period") or DEFAULT_PERIOD_PRESET


class AnalyticsOverviewAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        preset = _preset(request)
        ctx = AnalyticsService.dashboard_context(preset=preset, user=request.user)
        return JsonResponse(
            {
                "company_kpis": ctx["company_kpis"],
                "comparisons": ctx["comparisons"],
                "profitability": ctx["profitability"],
                "has_history": ctx["has_history"],
                "connection": ctx["connection"],
            }
        )


class AnalyticsTrendAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        field = request.GET.get("field", "total_pure_sale")
        days = int(request.GET.get("days", "7"))
        return JsonResponse({"field": field, "series": AnalyticsQueryService.trend(field, days=days)})


class AnalyticsSalespersonsAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        preset = _preset(request)
        limit = int(request.GET.get("limit", "50"))
        return JsonResponse(
            {
                "items": AnalyticsService.visitor_ranking(
                    limit=limit, preset=preset, user=request.user
                ),
            }
        )


class AnalyticsSupervisorsAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        preset = _preset(request)
        limit = int(request.GET.get("limit", "50"))
        return JsonResponse(
            {
                "items": AnalyticsService.head_visitor_ranking(
                    limit=limit, preset=preset, user=request.user
                ),
            }
        )


class AnalyticsRegionsAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        preset = _preset(request)
        dr, _ = PeriodComparisonService.comparison_range(preset)
        from reports.services.dates import DateRange

        date_range = DateRange(dr.start, dr.end) if dr else None
        return JsonResponse(
            {
                "cities": AnalyticsQueryService.region_ranking("city", dr=date_range),
                "zones": AnalyticsQueryService.region_ranking("zone", dr=date_range),
            }
        )


class AnalyticsProductGroupsAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        preset = _preset(request)
        dr, _ = PeriodComparisonService.comparison_range(preset)
        from reports.services.dates import DateRange

        date_range = DateRange(dr.start, dr.end) if dr else None
        return JsonResponse(
            {"items": AnalyticsQueryService.product_group_ranking(dr=date_range)}
        )


class AnalyticsProductsAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        preset = _preset(request)
        dr, _ = PeriodComparisonService.comparison_range(preset)
        from reports.services.dates import DateRange

        date_range = DateRange(dr.start, dr.end) if dr else None
        limit = int(request.GET.get("limit", "20"))
        rank_by = request.GET.get("rank_by", "pure_sale")
        return JsonResponse(
            {
                "items": AnalyticsQueryService.product_ranking(
                    dr=date_range, limit=limit, rank_by=rank_by
                ),
                "profitability": AnalyticsService.profitability_status(),
            }
        )


class AnalyticsMonthlyAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        year_param = request.GET.get("fiscal_year", "").strip()
        fiscal_year = int(year_param) if year_param.isdigit() else None
        return JsonResponse(AnalyticsQueryService.monthly_sales_series(fiscal_year=fiscal_year))


class AnalyticsReceivablesAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        return JsonResponse(AnalyticsQueryService.receivables_summary())


class AnalyticsAlertsAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        alerts = AnalyticsService.open_alerts()
        return JsonResponse(
            {
                "items": [
                    {
                        "severity": a.severity,
                        "title": a.title,
                        "description": a.description,
                        "current_value": a.current_value,
                        "rule_key": a.rule_key,
                        "detected_at": a.detected_at.isoformat(),
                    }
                    for a in alerts
                ]
            }
        )


class TvSlidesAPIView(View):
    def get(self, request):
        return JsonResponse(AnalyticsService.tv_context())


class MyPerformanceAPIView(View):
    def get(self, request):
        from reports.services.my_performance import build_my_performance

        ctx = build_my_performance(request.user, preset=_preset(request))
        scope = ctx.get("scope")
        payload = {
            "mode": ctx.get("mode"),
            "mode_label": ctx.get("mode_label"),
            "role": getattr(scope, "role", None),
            "preset": ctx.get("preset"),
            "preset_label": ctx.get("preset_label"),
            "user_display": ctx.get("user_display"),
            "pulse": ctx.get("pulse"),
            "visitor_summary": ctx.get("visitor_summary"),
            "visitors": ctx.get("visitors") or ctx.get("peers") or [],
            "supervisors": ctx.get("supervisors") or [],
            "alerts": ctx.get("alerts") or [],
            "insights": ctx.get("insights") or [],
            "connection": ctx.get("connection"),
        }
        if ctx.get("mode") == "personal":
            detail = ctx.get("detail") or {}
            payload["personnel_code"] = detail.get("personnel_code")
            payload["name"] = detail.get("name")
            payload["kpis"] = detail.get("kpis")
            payload["my_row"] = ctx.get("my_row")
        if ctx.get("mode") == "team":
            detail = ctx.get("detail") or {}
            payload["team"] = {
                "name": detail.get("name"),
                "kpis": detail.get("kpis"),
                "has_data": detail.get("has_data"),
            }
        return JsonResponse(payload)
