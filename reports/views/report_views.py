from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from reports.exceptions import (
    AuthenticationError,
    InvalidResponseError,
    KaraError,
    KaraNetworkError,
    LoginExpiredError,
    ReportNotFoundError,
)
from reports.services.analytics import AnalyticsService
from reports.services.access_control import AccessControlService
from reports.services.export_service import ExportService
from reports.services.report_fetcher import ReportFetcher
from reports.services.report_filter import ReportFilter
from reports.services.report_parser import ReportParser, flatten_rows
from reports.services.report_registry import ReportRegistry, get_report_config
from reports.views.mixins import KaraAdminRequiredMixin, KaraManagementRequiredMixin


def _handle_kara_error(request, error: KaraError) -> HttpResponse:
    if isinstance(error, LoginExpiredError):
        messages.error(request, str(error))
    elif isinstance(error, KaraNetworkError):
        messages.error(request, f"خطای شبکه: {error}")
    elif isinstance(error, AuthenticationError):
        messages.error(request, str(error))
    elif isinstance(error, InvalidResponseError):
        messages.error(request, str(error))
    else:
        messages.error(request, f"خطا: {error}")
    return redirect(request.META.get("HTTP_REFERER", "reports:dashboard"))


_KPI_ICONS = {
    "total_sale": "bi-cash-stack",
    "total_pure_sale": "bi-wallet2",
    "final_order_count": "bi-basket3",
    "settlement_remainder": "bi-hourglass-split",
    "distribution_reversion": "bi-truck",
    "sale_reversion": "bi-arrow-return-left",
    "order_count": "bi-receipt",
    "partner_count": "bi-people",
}


def _enrich_kpi_items(kpis: dict) -> list[dict]:
    items = []
    for index, (key, kpi) in enumerate(kpis.items()):
        items.append(
            {
                **kpi,
                "key": key,
                "icon": _KPI_ICONS.get(key, "bi-graph-up"),
                "is_lead": index == 0,
                "is_money": bool(kpi.get("unit")),
            }
        )
    return items


def _chart_leaders(top_rows: list[dict]) -> list[dict]:
    from reports.services.currency import display_float

    return [
        {
            "name": (item.get("name") or "")[:28],
            "value": display_float(item.get("total_sale") or 0),
            "formatted": item.get("total_sale_formatted") or "—",
        }
        for item in top_rows
    ]


def _build_report_context(config, snapshot, report_filter: ReportFilter, user=None) -> dict:
    rows = flatten_rows(snapshot.raw_data) if snapshot else []
    rows = AccessControlService.filter_visitor_rows(user, rows)
    columns = ReportParser.get_visible_columns(config)
    kpis = (
        ReportParser.extract_kpis(snapshot.sum_row_data, config)
        if snapshot and snapshot.sum_row_data
        else {}
    )
    kpi_items = _enrich_kpi_items(kpis)

    table_rows = []
    for row in rows:
        cells = []
        for col in columns:
            display = ReportParser.get_cell_display(
                row, col["key"], col["numeric"], col.get("money", False)
            )
            sort_value = (
                ReportParser.parse_number(row.get(col["key"]))
                if col["numeric"]
                else row.get(col["key"], "")
            )
            cells.append(
                {
                    "display": display,
                    "sort": sort_value if sort_value is not None else display,
                }
            )
        table_rows.append(cells)

    sum_cells = []
    if snapshot and snapshot.sum_row_data:
        for i, col in enumerate(columns):
            if i == 0:
                sum_cells.append({"display": "جمع کل", "sort": ""})
            else:
                display = ReportParser.get_sum_row_display(
                    snapshot.sum_row_data,
                    col["key"],
                    col["numeric"],
                    col.get("money", False),
                )
                sum_cells.append({"display": display, "sort": display})

    ranked = ReportParser.get_top_performers(rows, limit=8) if rows else []
    top_performers = ranked[:3]
    chart_leaders = _chart_leaders(ranked)

    lead_kpi = kpi_items[0] if kpi_items else None

    return {
        "config": config,
        "snapshot": snapshot,
        "rows": rows,
        "table_rows": table_rows,
        "columns": columns,
        "kpis": kpis,
        "kpi_items": kpi_items,
        "lead_kpi": lead_kpi,
        "sum_row": snapshot.sum_row_data if snapshot else None,
        "sum_cells": sum_cells,
        "report_filter": report_filter,
        "top_performers": top_performers,
        "chart_leaders": chart_leaders,
        "has_leaders": bool(top_performers),
        "connection": AnalyticsService.connection_status(),
        "row_count": snapshot.rows_count if snapshot else 0,
        "column_count": len(columns),
    }


class DashboardView(KaraManagementRequiredMixin, View):
    template_name = "reports/dashboard.html"

    def get(self, request):
        from reports.constants import DEFAULT_PERIOD_PRESET

        preset = request.GET.get("period") or DEFAULT_PERIOD_PRESET
        context = AnalyticsService.dashboard_context(preset=preset, user=request.user)
        return render(request, self.template_name, context)


class SyncCenterView(KaraAdminRequiredMixin, View):
    template_name = "reports/sync.html"

    def get(self, request):
        from reports.services.sync_center import build_sync_center_context

        return render(request, self.template_name, build_sync_center_context())


class ReportDetailView(KaraManagementRequiredMixin, View):
    template_name = "reports/report_detail.html"

    def get(self, request, slug: str):
        try:
            config = ReportRegistry.get_by_slug(slug)
        except ReportNotFoundError:
            messages.error(request, "گزارش مورد نظر یافت نشد.")
            return redirect("reports:dashboard")

        report_filter = ReportFilter.from_request(request)
        snapshot = ReportFetcher.get_latest_snapshot(
            config.key, personnel_code=report_filter.personnel_code
        )
        context = _build_report_context(config, snapshot, report_filter, user=request.user)
        return render(request, self.template_name, context)


class ReportRefreshView(KaraAdminRequiredMixin, View):
    def post(self, request, report_key: str):
        try:
            config = get_report_config(report_key)
        except ReportNotFoundError:
            messages.error(request, "گزارش مورد نظر یافت نشد.")
            return redirect("reports:dashboard")

        report_filter = ReportFilter.from_request(request)
        fetcher = ReportFetcher()
        try:
            snapshot = fetcher.fetch_and_save(report_key, report_filter=report_filter)
            if snapshot.rows_count == 0 and report_filter.is_filtered:
                messages.warning(
                    request,
                    f"گزارش «{report_filter.personnel_name or report_filter.personnel_code}» "
                    "داده‌ای نداشت.",
                )
            else:
                messages.success(
                    request,
                    f"گزارش با {snapshot.rows_count} ردیف همگام‌سازی شد.",
                )
        except KaraError as error:
            return _handle_kara_error(request, error)

        if report_filter.is_filtered:
            from urllib.parse import urlencode

            from django.urls import reverse

            base = reverse("reports:report_detail", kwargs={"slug": config.slug})
            params = urlencode(
                {
                    "personnel_code": report_filter.personnel_code,
                    "personnel_name": report_filter.personnel_name,
                }
            )
            return redirect(f"{base}?{params}")
        return redirect("reports:report_detail", slug=config.slug)


class ReportExportView(KaraManagementRequiredMixin, View):
    def get(self, request, report_key: str, export_format: str):
        try:
            config = get_report_config(report_key)
        except ReportNotFoundError:
            messages.error(request, "گزارش مورد نظر یافت نشد.")
            return redirect("reports:dashboard")

        report_filter = ReportFilter.from_request(request)
        snapshot = ReportFetcher.get_latest_snapshot(
            report_key, personnel_code=report_filter.personnel_code
        )
        if not snapshot:
            messages.warning(request, "داده‌ای برای خروجی وجود ندارد. ابتدا همگام‌سازی کنید.")
            return redirect("reports:report_detail", slug=config.slug)

        suffix = f"_{report_filter.personnel_code}" if report_filter.is_filtered else ""

        if export_format == "csv":
            content = ExportService.to_csv(snapshot, config)
            response = HttpResponse(content, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = (
                f'attachment; filename="{report_key}{suffix}_{snapshot.fetched_at:%Y%m%d_%H%M}.csv"'
            )
            return response

        if export_format == "excel":
            content = ExportService.to_excel(snapshot, config)
            response = HttpResponse(
                content,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = (
                f'attachment; filename="{report_key}{suffix}_{snapshot.fetched_at:%Y%m%d_%H%M}.xlsx"'
            )
            return response

        messages.error(request, "فرمت خروجی نامعتبر است.")
        return redirect("reports:report_detail", slug=config.slug)
