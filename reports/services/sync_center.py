"""Context builder for the professional sync / integration center page."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from reports.constants import SyncStatus
from reports.models import KaraSyncJob
from reports.services.analytics import AnalyticsService
from reports.services.auto_refresh import scheduler_jobs
from reports.services.dates import format_jalali_datetime
from reports.services.display import report_title, sync_status_label, sync_trigger_label
from reports.services.report_registry import ReportRegistry


def build_sync_center_context() -> dict[str, Any]:
    connection = AnalyticsService.connection_status()
    jobs_qs = list(KaraSyncJob.objects.all()[:60])
    sched = {j["report_key"]: j for j in scheduler_jobs() if j.get("report_key")}

    recent = list(KaraSyncJob.objects.all()[:80])
    success_n = sum(1 for j in recent if j.status == SyncStatus.SUCCESS)
    failed_n = sum(1 for j in recent if j.status == SyncStatus.FAILED)
    running_n = sum(1 for j in recent if j.status == SyncStatus.RUNNING)
    total_n = len(recent) or 1
    success_rate = round(success_n / total_n * 100, 1)

    reports = []
    fresh_n = aging_n = overdue_n = 0
    for item in AnalyticsService.data_explorer_reports():
        cfg = ReportRegistry.get(item["key"])
        interval = max(1, int(cfg.suggested_interval_minutes or 15))
        snap = item.get("snapshot")
        fetched_at = snap.fetched_at if snap else None
        age_min = None
        if fetched_at:
            age_min = (timezone.now() - fetched_at).total_seconds() / 60

        if age_min is None:
            freshness = "missing"
            freshness_label = "بدون داده"
            overdue_n += 1
        elif age_min <= interval:
            freshness = "fresh"
            freshness_label = "به‌روز"
            fresh_n += 1
        elif age_min <= interval * 2:
            freshness = "aging"
            freshness_label = "نزدیک به موعد"
            aging_n += 1
        else:
            freshness = "stale"
            freshness_label = "منقضی"
            overdue_n += 1

        last_job = (
            KaraSyncJob.objects.filter(report_key=item["key"])
            .order_by("-started_at")
            .first()
        )
        next_info = sched.get(item["key"]) or {}
        next_due = _estimate_next_due(fetched_at, interval, next_info.get("next_run_at"))

        reports.append(
            {
                "key": item["key"],
                "title": item["title"],
                "slug": item["slug"],
                "is_primary": item.get("is_primary"),
                "enabled": cfg.enabled,
                "interval": interval,
                "interval_label": _interval_label(interval),
                "rows_count": item.get("rows_count") or 0,
                "fetched_at": fetched_at,
                "fetched_label": format_jalali_datetime(fetched_at) if fetched_at else "—",
                "age_label": _age_label(age_min),
                "freshness": freshness,
                "freshness_label": freshness_label,
                "last_job_status": last_job.status if last_job else "",
                "last_job_status_label": (
                    sync_status_label(last_job.status) if last_job else "—"
                ),
                "last_job_error": (
                    (last_job.friendly_error or last_job.error_message or "")
                    if last_job and last_job.status == SyncStatus.FAILED
                    else ""
                ),
                "next_run_label": next_info.get("next_run_label") or next_due,
                "progress": _progress(age_min, interval),
            }
        )

    history = []
    for job in jobs_qs:
        history.append(
            {
                "job": job,
                "report_title": report_title(job.report_key),
                "status_label": sync_status_label(job.status),
                "trigger_label": sync_trigger_label(job.triggered_by),
                "message": job.friendly_error or "—",
                "is_fail": job.status == SyncStatus.FAILED,
                "is_run": job.status == SyncStatus.RUNNING,
                "is_ok": job.status == SyncStatus.SUCCESS,
            }
        )

    intervals = sorted({r["interval"] for r in reports}) if reports else [5]

    return {
        "connection": connection,
        "reports": reports,
        "history": history,
        "jobs": jobs_qs,
        "summary": {
            "report_count": len(reports),
            "fresh_count": fresh_n,
            "aging_count": aging_n,
            "overdue_count": overdue_n,
            "success_rate": success_rate,
            "success_n": success_n,
            "failed_n": failed_n,
            "running_n": running_n,
            "scheduler_enabled": bool(getattr(settings, "AUTO_REFRESH_ENABLED", True)),
            "scheduler_jobs": len(sched),
            "stagger_seconds": int(getattr(settings, "AUTO_REFRESH_STAGGER_SECONDS", 50)),
            "mode_label": "زمان‌بندی جداگانه هر گزارش",
            "interval_band": _interval_band(intervals),
        },
    }


def _interval_label(minutes: int) -> str:
    if minutes < 60:
        return f"هر {minutes} دقیقه"
    hours = minutes // 60
    rem = minutes % 60
    if rem:
        return f"هر {hours} ساعت و {rem} دقیقه"
    return f"هر {hours} ساعت"


def _interval_band(intervals: list[int]) -> str:
    if not intervals:
        return "—"
    lo, hi = min(intervals), max(intervals)
    if lo == hi:
        return _interval_label(lo)
    return f"{lo} تا {hi} دقیقه"


def _age_label(age_min: float | None) -> str:
    if age_min is None:
        return "—"
    if age_min < 1:
        return "همین الان"
    if age_min < 60:
        return f"{int(age_min)} دقیقه پیش"
    hours = age_min / 60
    if hours < 24:
        return f"{hours:.1f} ساعت پیش"
    return f"{int(hours / 24)} روز پیش"


def _progress(age_min: float | None, interval: int) -> float:
    if age_min is None or interval <= 0:
        return 100.0
    return float(min(100.0, round(age_min / interval * 100, 1)))


def _estimate_next_due(fetched_at, interval: int, scheduled_iso: str | None) -> str:
    if scheduled_iso:
        try:
            from django.utils.dateparse import parse_datetime

            dt = parse_datetime(scheduled_iso)
            if dt:
                return format_jalali_datetime(dt)
        except Exception:
            pass
    if fetched_at and interval:
        due = fetched_at + timedelta(minutes=interval)
        if due < timezone.now():
            return "آماده همگام‌سازی"
        return format_jalali_datetime(due)
    return "—"
