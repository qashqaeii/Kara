"""Rule-based management alerts with deduplication."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from reports.constants import AlertSeverity, AlertStatus, ConnectionStatus, SyncStatus
from reports.models import (
    KaraSyncJob,
    ManagementAlert,
    SalespersonDailyMetric,
    SupervisorDailyMetric,
)
from reports.services.currency import format_money
from reports.services.parsers import format_number
from reports.services.period_comparison import PeriodComparisonService


def _connection_status() -> dict:
    from reports.services.analytics import AnalyticsService

    return AnalyticsService.connection_status()


class AlertEngine:
    @classmethod
    def evaluate_all(cls) -> list[ManagementAlert]:
        created: list[ManagementAlert] = []
        created.extend(cls._rule_stale_data())
        created.extend(cls._rule_sync_failed())
        created.extend(cls._rule_sales_drop())
        created.extend(cls._rule_reversion_increase())
        created.extend(cls._rule_inactive_salesperson())
        created.extend(cls._rule_supervisor_drop())
        created.extend(cls._rule_high_receivables())
        return created

    @classmethod
    def _threshold(cls, key: str, default: float) -> float:
        thresholds = getattr(settings, "ALERT_THRESHOLDS", {})
        return float(thresholds.get(key, default))

    @classmethod
    def _close_open(cls, *, rule_key: str, entity_code: str | None = None) -> int:
        qs = ManagementAlert.objects.filter(rule_key=rule_key, status=AlertStatus.OPEN)
        if entity_code is not None:
            qs = qs.filter(entity_code=entity_code)
        return qs.update(status=AlertStatus.CLOSED)

    @classmethod
    def _ensure(
        cls,
        *,
        rule_key: str,
        entity_type: str,
        entity_code: str,
        period: str,
        severity: str,
        title: str,
        description: str,
        metric: str = "",
        current_value: str = "",
        expected_value: str = "",
        entity: str = "",
    ) -> ManagementAlert:
        alert, created = ManagementAlert.objects.get_or_create(
            rule_key=rule_key,
            entity_type=entity_type,
            entity_code=entity_code,
            period=period,
            defaults={
                "severity": severity,
                "title": title,
                "description": description,
                "metric": metric,
                "current_value": current_value,
                "expected_value": expected_value,
                "entity": entity or entity_code,
                "status": AlertStatus.OPEN,
            },
        )
        if not created:
            updates = ["description", "current_value", "severity", "title"]
            alert.description = description
            alert.current_value = current_value
            alert.severity = severity
            alert.title = title
            if alert.status != AlertStatus.OPEN:
                alert.status = AlertStatus.OPEN
                updates.append("status")
            alert.save(update_fields=updates)
        return alert

    @classmethod
    def _rule_stale_data(cls) -> list[ManagementAlert]:
        conn = _connection_status()
        period = timezone.localdate().isoformat()
        # Only true staleness — transient network blips are covered by sync_failed.
        if conn["status"] == ConnectionStatus.STALE:
            return [
                cls._ensure(
                    rule_key="stale_data",
                    entity_type="system",
                    entity_code="sync",
                    period=period,
                    severity=AlertSeverity.WARNING,
                    title="داده قدیمی",
                    description=f"آخرین همگام‌سازی: {conn['last_sync_label']}",
                    metric="sync_lag",
                    current_value=conn["last_sync_label"],
                )
            ]
        cls._close_open(rule_key="stale_data")
        return []

    @classmethod
    def _rule_sync_failed(cls) -> list[ManagementAlert]:
        period = timezone.localdate().isoformat()
        cutoff = timezone.now() - timedelta(hours=6)

        failed_jobs = (
            KaraSyncJob.objects.filter(
                status=SyncStatus.FAILED,
                started_at__gte=cutoff,
            )
            .order_by("-started_at")
        )

        active: list[KaraSyncJob] = []
        seen: set[str] = set()
        for job in failed_jobs:
            if job.report_key in seen:
                continue
            seen.add(job.report_key)
            recovered = KaraSyncJob.objects.filter(
                report_key=job.report_key,
                status=SyncStatus.SUCCESS,
                started_at__gt=job.started_at,
            ).exists()
            if recovered:
                continue
            active.append(job)

        active_keys = {job.report_key for job in active}
        for alert in ManagementAlert.objects.filter(
            rule_key="sync_failed", status=AlertStatus.OPEN
        ):
            if alert.entity_code not in active_keys:
                alert.status = AlertStatus.CLOSED
                alert.save(update_fields=["status"])

        if not active:
            return []

        from reports.services.display import report_title, sync_status_label

        alerts: list[ManagementAlert] = []
        for job in active[:10]:
            alerts.append(
                cls._ensure(
                    rule_key="sync_failed",
                    entity_type="report",
                    entity_code=job.report_key,
                    period=period,
                    severity=AlertSeverity.CRITICAL,
                    title="همگام‌سازی ناموفق",
                    description=(
                        f"{report_title(job.report_key)}: "
                        f"{job.friendly_error or job.error_message}"
                    ),
                    metric="sync_status",
                    current_value=sync_status_label(job.status),
                    entity=report_title(job.report_key),
                )
            )
        return alerts

    @classmethod
    def _rule_sales_drop(cls) -> list[ManagementAlert]:
        threshold = cls._threshold("sales_drop_percent", 20.0)
        cmp = PeriodComparisonService.compare_field("total_pure_sale", "last_7_days")
        period = "last_7_days"
        if not cmp.is_comparable or cmp.percent_change is None:
            cls._close_open(rule_key="sales_drop")
            return []
        if cmp.percent_change <= -threshold:
            return [
                cls._ensure(
                    rule_key="sales_drop",
                    entity_type="company",
                    entity_code="all",
                    period=period,
                    severity=AlertSeverity.CRITICAL,
                    title="افت فروش خالص",
                    description=f"فروش خالص {cmp.percent_change}% نسبت به دوره قبل کاهش یافته است.",
                    metric="total_pure_sale",
                    current_value=format_number(cmp.current),
                    expected_value=f"> {threshold}% افت",
                )
            ]
        cls._close_open(rule_key="sales_drop")
        return []

    @classmethod
    def _rule_reversion_increase(cls) -> list[ManagementAlert]:
        threshold = cls._threshold("reversion_rate_percent", 10.0)
        from reports.services.analytics_query import AnalyticsQueryService

        period = "all"
        current_range, _ = PeriodComparisonService.comparison_range(period)
        if not current_range:
            cls._close_open(rule_key="reversion_rate_increase")
            return []
        kpis = AnalyticsQueryService.company_kpis_for_range(current_range, preset=period)
        rate = float(kpis.get("reversion_rate", {}).get("numeric") or 0)
        if rate <= threshold:
            cls._close_open(rule_key="reversion_rate_increase")
            return []
        # Close legacy per-day / last_7_days period keys left from older alert rules.
        ManagementAlert.objects.filter(
            rule_key="reversion_rate_increase",
            status=AlertStatus.OPEN,
        ).exclude(period=period).update(status=AlertStatus.CLOSED)
        return [
            cls._ensure(
                rule_key="reversion_rate_increase",
                entity_type="company",
                entity_code="all",
                period=period,
                severity=AlertSeverity.WARNING,
                title="افزایش نرخ برگشت",
                description=f"نرخ برگشت {rate}% است.",
                metric="reversion_rate",
                current_value=str(rate),
                expected_value=f"< {threshold}%",
            )
        ]

    @classmethod
    def _rule_inactive_salesperson(cls) -> list[ManagementAlert]:
        today = timezone.localdate()
        period = today.isoformat()
        alerts = []
        active_codes: set[str] = set()
        for row in SalespersonDailyMetric.objects.filter(
            business_date=today, is_active=False
        )[:20]:
            active_codes.add(row.personnel_code)
            alerts.append(
                cls._ensure(
                    rule_key="inactive_salesperson",
                    entity_type="salesperson",
                    entity_code=row.personnel_code,
                    period=period,
                    severity=AlertSeverity.INFO,
                    title="ویزیتور بدون فروش",
                    description=f"{row.personnel_name or row.personnel_code} در این دوره فروشی ندارد.",
                    metric="total_sale",
                    current_value="0",
                    entity=row.personnel_name,
                )
            )
        for alert in ManagementAlert.objects.filter(
            rule_key="inactive_salesperson", status=AlertStatus.OPEN
        ):
            if alert.entity_code not in active_codes:
                alert.status = AlertStatus.CLOSED
                alert.save(update_fields=["status"])
        return alerts

    @classmethod
    def _rule_supervisor_drop(cls) -> list[ManagementAlert]:
        threshold = cls._threshold("supervisor_drop_percent", 25.0)
        today = timezone.localdate()
        period = today.isoformat()
        alerts = []
        active_codes: set[str] = set()
        for sup in SupervisorDailyMetric.objects.filter(business_date=today)[:50]:
            prev = SupervisorDailyMetric.objects.filter(
                supervisor_code=sup.supervisor_code,
                business_date__lt=today,
            ).order_by("-business_date").first()
            if not prev or prev.total_sale <= 0:
                continue
            drop = (prev.total_sale - sup.total_sale) / prev.total_sale * 100
            if drop >= Decimal(str(threshold)):
                active_codes.add(sup.supervisor_code)
                alerts.append(
                    cls._ensure(
                        rule_key="supervisor_drop",
                        entity_type="supervisor",
                        entity_code=sup.supervisor_code,
                        period=period,
                        severity=AlertSeverity.WARNING,
                        title="افت عملکرد سرپرست",
                        description=f"{sup.supervisor_name}: افت {drop:.1f}% نسبت به آخرین دوره.",
                        metric="total_sale",
                        current_value=format_number(sup.total_sale),
                        entity=sup.supervisor_name,
                    )
                )
        for alert in ManagementAlert.objects.filter(
            rule_key="supervisor_drop", status=AlertStatus.OPEN
        ):
            if alert.entity_code not in active_codes:
                alert.status = AlertStatus.CLOSED
                alert.save(update_fields=["status"])
        return alerts

    @classmethod
    def _rule_high_receivables(cls) -> list[ManagementAlert]:
        from reports.models import ReceivableDailyMetric

        metric = ReceivableDailyMetric.objects.order_by("-business_date").first()
        if not metric or metric.total_outstanding <= 0:
            cls._close_open(rule_key="high_receivables")
            return []
        # Stable period key — one open alert, not one per sync day.
        period = "current"
        ManagementAlert.objects.filter(
            rule_key="high_receivables",
            status=AlertStatus.OPEN,
        ).exclude(period=period).update(status=AlertStatus.CLOSED)
        return [
            cls._ensure(
                rule_key="high_receivables",
                entity_type="company",
                entity_code="all",
                period=period,
                severity=AlertSeverity.WARNING,
                title="معوقات باز",
                description=(
                    f"جمع مطالبات سررسیدگذشته: {format_money(metric.total_outstanding)}"
                ),
                metric="total_outstanding",
                current_value=format_money(metric.total_outstanding, with_unit=False),
            )
        ]
