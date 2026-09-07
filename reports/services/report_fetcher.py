"""
Orchestrates fetching reports from Kara and persisting snapshots.

Prefer SyncOrchestrator for new code. This module keeps backward-compatible
APIs used by existing views.
"""

from __future__ import annotations

from django.utils import timezone

from reports.constants import PRIMARY_KPI_REPORT
from reports.exceptions import ReportNotFoundError
from reports.models import KaraReportSnapshot
from reports.services.analytics import AnalyticsService
from reports.services.kara_client import KaraClient
from reports.services.report_filter import ReportFilter
from reports.services.report_parser import ReportParser, flatten_rows
from reports.services.report_registry import ReportRegistry, get_report_config
from reports.services.sync import SyncOrchestrator


class ReportFetcher:
    def __init__(self, client: KaraClient | None = None) -> None:
        self.client = client or KaraClient()
        self.orchestrator = SyncOrchestrator(client=self.client)

    def fetch_and_save(
        self,
        report_key: str,
        report_filter: ReportFilter | None = None,
    ) -> KaraReportSnapshot:
        report_filter = report_filter or ReportFilter()
        job = self.orchestrator.sync_report(
            report_key,
            triggered_by="manual",
            personnel_code=report_filter.personnel_code,
            personnel_name=report_filter.personnel_name,
        )
        snapshot = (
            KaraReportSnapshot.objects.filter(sync_job=job).order_by("-fetched_at").first()
        )
        if snapshot:
            return snapshot
        # Deduplicated sync — return latest existing
        existing = self.get_latest_snapshot(
            report_key, personnel_code=report_filter.personnel_code
        )
        if existing:
            return existing
        # Failed sync with no data
        return KaraReportSnapshot(
            report_key=report_key,
            report_title=get_report_config(report_key).title,
            fetched_at=timezone.now(),
            raw_data={"Data": [], "SumRowData": None},
            rows_count=0,
            personnel_code=report_filter.personnel_code,
            personnel_name=report_filter.personnel_name,
        )

    def fetch_all_and_save(self, triggered_by: str = "auto") -> list[KaraReportSnapshot]:
        jobs = self.orchestrator.sync_all(triggered_by=triggered_by)
        snapshots = []
        for job in jobs:
            snap = (
                KaraReportSnapshot.objects.filter(sync_job=job)
                .order_by("-fetched_at")
                .first()
            )
            if snap:
                snapshots.append(snap)
            else:
                latest = self.get_latest_snapshot(job.report_key)
                if latest:
                    snapshots.append(latest)
        return snapshots

    @staticmethod
    def get_latest_snapshot(
        report_key: str,
        personnel_code: str = "",
    ) -> KaraReportSnapshot | None:
        try:
            get_report_config(report_key)
        except ReportNotFoundError:
            return None
        return AnalyticsService.get_latest_snapshot(report_key, personnel_code)

    @staticmethod
    def get_dashboard_data() -> list[dict]:
        return AnalyticsService.report_cards()

    @staticmethod
    def get_aggregate_kpis(reports: list[dict] | None = None) -> dict[str, dict]:
        """
        Company KPIs from the primary report only.

        Historically this summed visitor + head visitor KPIs which double-counted
        identical SumRowData totals. That bug is fixed here.
        """
        return AnalyticsService.company_kpis()

    def search_personnel(self, query: str, report_key: str) -> list[dict]:
        config = get_report_config(report_key)
        return self.client.search_personnel(query, config.referer_path)
