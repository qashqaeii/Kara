from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from reports.constants import SyncStatus
from reports.exceptions import KaraError, ReportNotFoundError
from reports.models import KaraSyncJob
from reports.services.analytics import AnalyticsService
from reports.services.auto_refresh import refresh_all_reports
from reports.services.dates import format_jalali_datetime
from reports.services.display import (
    report_title,
    severity_label,
    sync_status_label,
    sync_trigger_label,
)
from reports.services.kara_client import KaraClient
from reports.services.report_fetcher import ReportFetcher
from reports.services.report_registry import get_report_config
from reports.services.sync import SyncOrchestrator
from reports.views.mixins import KaraAdminRequiredMixin, KaraManagementRequiredMixin


class DashboardAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        from reports.constants import DEFAULT_PERIOD_PRESET

        preset = request.GET.get("period") or DEFAULT_PERIOD_PRESET
        ctx = AnalyticsService.dashboard_context(preset=preset, user=request.user)
        explorer = AnalyticsService.data_explorer_reports()
        reports = []
        for r in explorer:
            snap = r["snapshot"]
            reports.append(
                {
                    "key": r["key"],
                    "title": r["title"],
                    "slug": r["slug"],
                    "has_data": r["has_data"],
                    "is_primary": r["is_primary"],
                    "rows_count": snap.rows_count if snap else 0,
                    "fetched_at": snap.fetched_at.isoformat() if snap else None,
                    "fetched_at_display": (
                        format_jalali_datetime(snap.fetched_at) if snap else None
                    ),
                    "kpis": {
                        k: {"label": v["label"], "formatted": v["formatted"]}
                        for k, v in r.get("kpis", {}).items()
                    },
                }
            )

        return JsonResponse(
            {
                "preset": preset,
                "company_kpis": {
                    k: {
                        "label": v["label"],
                        "formatted": v["formatted"],
                        "numeric": v.get("numeric"),
                    }
                    for k, v in ctx["company_kpis"].items()
                },
                "profitability": ctx["profitability"],
                # Keep aggregate_kpis alias for older JS (same as company_kpis, NOT summed)
                "aggregate_kpis": {
                    k: {"label": v["label"], "formatted": v["formatted"]}
                    for k, v in ctx["company_kpis"].items()
                    if k
                    in {
                        "total_sale",
                        "total_pure_sale",
                        "final_order_count",
                        "settlement_remainder",
                        "distribution_reversion",
                        "sale_reversion",
                        "reversion_rate",
                        "avg_order_value",
                        "active_visitors",
                    }
                },
                "reports": reports,
                "visitor_ranking": ctx["visitor_ranking"],
                "head_visitor_ranking": ctx["head_visitor_ranking"],
                "geo_summary": ctx["geo_summary"],
                "connection": ctx["connection"],
                "alerts": [
                    {
                        "id": a.id,
                        "severity": a.severity,
                        "severity_label": severity_label(a.severity),
                        "title": a.title,
                        "description": a.description,
                        "entity": a.entity,
                    }
                    for a in ctx["alerts"]
                ],
                "refresh_status": {
                    "status": ctx["connection"]["status"],
                    "last_refresh": ctx["connection"]["last_sync_at"],
                    "last_refresh_display": ctx["connection"]["last_sync_label"],
                    "interval_minutes": ctx["connection"]["interval_minutes"],
                    "auto_refresh_enabled": ctx["connection"]["auto_refresh_enabled"],
                },
                "server_time": timezone.now().isoformat(),
            }
        )


class RefreshAllAPIView(KaraAdminRequiredMixin, View):
    def post(self, request):
        result = refresh_all_reports(triggered_by="manual")
        status = 200 if result.get("success") else 500
        return JsonResponse(result, status=status)


class SyncRunAPIView(KaraAdminRequiredMixin, View):
    def post(self, request):
        report_key = (request.POST.get("report") or request.GET.get("report") or "").strip()
        orchestrator = SyncOrchestrator()
        if report_key:
            try:
                get_report_config(report_key)
            except ReportNotFoundError:
                return JsonResponse({"ok": False, "error": "گزارش یافت نشد."}, status=404)
            job = orchestrator.sync_report(report_key, triggered_by="manual")
            return JsonResponse(
                {
                    "ok": job.status == SyncStatus.SUCCESS,
                    "job_id": job.id,
                    "report_key": job.report_key,
                    "report_title": report_title(job.report_key),
                    "status": job.status,
                    "status_label": sync_status_label(job.status),
                    "received_count": job.received_count,
                    "skipped_count": job.skipped_count,
                    "error": job.friendly_error,
                }
            )
        jobs = orchestrator.sync_all(triggered_by="manual")
        return JsonResponse(
            {
                "ok": all(j.status == SyncStatus.SUCCESS for j in jobs),
                "jobs": [
                    {
                        "report_key": j.report_key,
                        "report_title": report_title(j.report_key),
                        "status": j.status,
                        "status_label": sync_status_label(j.status),
                        "received_count": j.received_count,
                        "error": j.friendly_error,
                    }
                    for j in jobs
                ],
            }
        )


class SyncStatusAPIView(KaraAdminRequiredMixin, View):
    def get(self, request):
        jobs = list(KaraSyncJob.objects.all()[:20])
        return JsonResponse(
            {
                "connection": AnalyticsService.connection_status(),
                "jobs": [
                    {
                        "id": j.id,
                        "report_key": j.report_key,
                        "report_title": report_title(j.report_key),
                        "status": j.status,
                        "status_label": sync_status_label(j.status),
                        "started_at": j.started_at.isoformat(),
                        "started_at_display": format_jalali_datetime(j.started_at, with_seconds=True),
                        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
                        "finished_at_display": (
                            format_jalali_datetime(j.finished_at, with_seconds=True)
                            if j.finished_at
                            else None
                        ),
                        "received_count": j.received_count,
                        "inserted_count": j.inserted_count,
                        "skipped_count": j.skipped_count,
                        "error": j.friendly_error,
                        "triggered_by": j.triggered_by,
                        "triggered_by_label": sync_trigger_label(j.triggered_by),
                    }
                    for j in jobs
                ],
            }
        )


class TestConnectionAPIView(KaraAdminRequiredMixin, View):
    def post(self, request):
        result = KaraClient().test_connection()
        return JsonResponse(result, status=200 if result.get("ok") else 502)


class PersonnelSearchAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        query = request.GET.get("q", "").strip()
        report_key = request.GET.get("report_key", "head_visitor_sale").strip()

        if len(query) < 1:
            return JsonResponse({"results": []})

        try:
            get_report_config(report_key)
        except ReportNotFoundError:
            return JsonResponse({"error": "گزارش یافت نشد."}, status=404)

        fetcher = ReportFetcher()
        try:
            results = fetcher.search_personnel(query, report_key)
            return JsonResponse({"results": results})
        except KaraError as exc:
            return JsonResponse({"error": str(exc)}, status=502)


class VisitorRankingAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        rank_by = request.GET.get("rank_by", "TotalSale")
        limit = min(int(request.GET.get("limit", 50)), 200)
        return JsonResponse(
            {
                "results": AnalyticsService.visitor_ranking(
                    limit=limit, rank_by=rank_by, user=request.user
                )
            }
        )


class AlertsAPIView(KaraManagementRequiredMixin, View):
    def get(self, request):
        alerts = AnalyticsService.open_alerts()
        return JsonResponse(
            {
                "results": [
                    {
                        "id": a.id,
                        "severity": a.severity,
                        "severity_label": severity_label(a.severity),
                        "title": a.title,
                        "description": a.description,
                        "entity": a.entity,
                        "detected_at": a.detected_at.isoformat(),
                        "detected_at_display": format_jalali_datetime(a.detected_at),
                    }
                    for a in alerts
                ]
            }
        )

    def post(self, request):
        AnalyticsService.evaluate_alerts()
        return JsonResponse({"ok": True})
